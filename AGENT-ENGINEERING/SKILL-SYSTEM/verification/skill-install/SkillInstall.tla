---------------------------- MODULE SkillInstall ----------------------------
(***************************************************************************)
(* The install, quarantine and rollback transactions of the skill system,  *)
(* AGENT-ENGINEERING/SKILL-SYSTEM/skill_system/operations.py at the sync   *)
(* commit in manifest.json: SkillSystem._install_under_lock, quarantine,   *)
(* rollback, _rollback_install, _rollback_quarantine, _begin_rollback,     *)
(* _restore_state_entry, _ensure_no_incomplete and                         *)
(* _ensure_no_newer_active_operation. refresh and sync run one             *)
(* _install_under_lock per candidate, so they are sequences of installs    *)
(* here. Lock migration, validation and host projections are not modelled. *)
(*                                                                         *)
(* One mutating command runs at a time (_lock takes a non-blocking         *)
(* exclusive flock), so commands run one after another. A command may stop *)
(* (a crash, or an exception such as a failed fsync) between any two of    *)
(* its writes, and what it wrote stays. Each write the code makes atomic   *)
(* (atomic_write_bytes, and same-filesystem renames) is one step. A        *)
(* command's reads and checks happen in the step that starts it: nothing   *)
(* else writes while it holds the lock.                                    *)
(*                                                                         *)
(* Trees and the install state are reduced to content hashes: "v1" and     *)
(* "v2" are canonical versions, "foreign" a tree the user made.            *)
(***************************************************************************)
EXTENDS Naturals, Sequences

CONSTANTS
    Skills,         \* registry skills, each with its own install target
    MaxOps,         \* installs and quarantines started per behavior
    StopWindows,    \* where a command may stop: a subset of
                    \* {"journal", "unjournaled", "rollback"} (see WindowOf)
    RollbackOrder,  \* "newest": only the newest live operation is rolled back;
                    \* "per-path": any operation the code accepts
    Mutants         \* broken variants switched on; {} checks the real code

None == "none"
Versions == {"v1", "v2"}
Trees == Versions \cup {"foreign"}
Idle == [kind |-> "idle", op |-> 0, step |-> None]

VARIABLES
    src,    \* canonical source hash of each skill (report.source_hashes)
    live,   \* each install target's tree hash, or None when absent
    state,  \* install-state.json: each managed entry's hash, or None
    ops,    \* transactions in creation order; see NewOp
    cmd,    \* the running command and its next step, or Idle
    stuck   \* a rollback refused because a check of its own trees failed

vars == <<src, live, state, ops, cmd, stuck>>

\* One transaction directory (operations.py 366-391). journal is "none"
\* until operation.json exists, then the journal status. before is the
\* target's hash when the operation started (target_hash_before or
\* target_hash), new the staged hash, statePre the state preimage. staged
\* says the staged tree is still in staged/, held is the tree moved into the
\* transaction (preimage/, or the quarantine path), aside the new tree
\* rollback moved to rollback-new/.
NewOp(kind, s, staged) ==
    [kind |-> kind, skill |-> s, journal |-> "none", phase |-> None,
     before |-> live[s], new |-> staged, statePre |-> state,
     staged |-> kind = "install", held |-> None, aside |-> None]

Indexes == 1..Len(ops)
\* list_incomplete_operations, journal.py 181-189.
Incomplete == {i \in Indexes : ops[i].journal \in {"in-progress", "rolling-back"}}

\* iter_skill_states, model.py 771-782.
Status(s) ==
    CASE live[s] = None /\ state[s] # None -> "missing-managed"
      [] live[s] = None -> "absent"
      [] state[s] = None -> "unmanaged-collision"
      [] live[s] # state[s] -> "locally-modified"
      [] src[s] # state[s] -> "source-updated"
      [] OTHER -> "current"

Init ==
    /\ src = [s \in Skills |-> "v1"]
    /\ live \in [Skills -> {None, "foreign"}]
    /\ state = [s \in Skills |-> None]
    /\ ops = <<>>
    /\ cmd = Idle
    /\ stuck = FALSE

Step(next) == cmd' = [cmd EXCEPT !.step = next]
Done == cmd' = Idle
SetOp(i, f, v) == ops' = [ops EXCEPT ![i][f] = v]

-----------------------------------------------------------------------------
(* install: _install_under_lock, operations.py 575-692. *)

StartInstall(s, force) ==   \* 583-662: checks, then an invisible staged copy
    /\ cmd = Idle /\ Len(ops) < MaxOps
    /\ Incomplete = {}                                            \* 583
    /\ ~(live[s] # None /\ state[s] = None /\ ~force)             \* 603-604
    /\ state[s] # None =>
         /\ live[s] # None                                        \* 608-609
         /\ (live[s] = state[s] \/ force)                         \* 610-613
         /\ ~(src[s] = state[s] /\ live[s] = src[s])              \* 614-619 already current
    /\ ops' = Append(ops, NewOp("install", s, src[s]))
    /\ cmd' = [kind |-> "install", op |-> Len(ops) + 1, step |-> "prepared"]
    /\ UNCHANGED <<src, live, state, stuck>>

InstallStep ==
    LET i == cmd.op
        op == ops[i]
        s == op.skill
    IN /\ cmd.kind = "install"
       /\ CASE cmd.step = "prepared" ->                           \* 663
                 /\ ops' = [ops EXCEPT ![i].journal = "in-progress", ![i].phase = "prepared"]
                 /\ Step("preserve") /\ UNCHANGED <<live, state>>
            [] cmd.step = "preserve" ->                           \* 664-667
                 /\ IF op.before # None
                      THEN live' = [live EXCEPT ![s] = None] /\ SetOp(i, "held", op.before)
                      ELSE UNCHANGED <<live, ops>>
                 /\ Step("preimage-preserved") /\ UNCHANGED state
            [] cmd.step = "preimage-preserved" ->                 \* 668
                 /\ SetOp(i, "phase", "preimage-preserved")
                 /\ Step("install") /\ UNCHANGED <<live, state>>
            [] cmd.step = "install" ->                            \* 669-672
                 /\ live' = [live EXCEPT ![s] = op.new] /\ SetOp(i, "staged", FALSE)
                 /\ Step("target-installed") /\ UNCHANGED state
            [] cmd.step = "target-installed" ->                   \* 673
                 /\ SetOp(i, "phase", "target-installed")
                 /\ Step("state") /\ UNCHANGED <<live, state>>
            [] cmd.step = "state" ->                              \* 674-688
                 /\ state' = [state EXCEPT ![s] = op.new]
                 /\ Step("state-committed") /\ UNCHANGED <<live, ops>>
            [] cmd.step = "state-committed" ->                    \* 689
                 /\ SetOp(i, "phase", "state-committed")
                 /\ Step("committed") /\ UNCHANGED <<live, state>>
            [] cmd.step = "committed" ->                          \* 690-691
                 /\ ops' = [ops EXCEPT ![i].journal = "committed", ![i].phase = "committed"]
                 /\ Done /\ UNCHANGED <<live, state>>
       /\ UNCHANGED <<src, stuck>>

-----------------------------------------------------------------------------
(* quarantine, operations.py 828-909. *)

StartQuarantine(s) ==       \* 836-885
    /\ cmd = Idle /\ Len(ops) < MaxOps
    /\ Incomplete = {}                                            \* 836
    /\ live[s] # None                                             \* 842-843
    /\ ops' = Append(ops, NewOp("quarantine", s, None))
    /\ cmd' = [kind |-> "quarantine", op |-> Len(ops) + 1, step |-> "prepared"]
    /\ UNCHANGED <<src, live, state, stuck>>

QuarantineStep ==
    LET i == cmd.op
        op == ops[i]
        s == op.skill
    IN /\ cmd.kind = "quarantine"
       /\ CASE cmd.step = "prepared" ->                           \* 886
                 /\ ops' = [ops EXCEPT ![i].journal = "in-progress", ![i].phase = "prepared"]
                 /\ Step("move") /\ UNCHANGED <<live, state>>
            [] cmd.step = "move" ->                               \* 887-889
                 /\ live' = [live EXCEPT ![s] = None] /\ SetOp(i, "held", op.before)
                 /\ Step("target-quarantined") /\ UNCHANGED state
            [] cmd.step = "target-quarantined" ->                 \* 890-895
                 /\ SetOp(i, "phase", "target-quarantined")
                 /\ Step("state") /\ UNCHANGED <<live, state>>
            [] cmd.step = "state" ->                              \* 896-899
                 /\ IF "d" \notin Mutants THEN state' = [state EXCEPT ![s] = None]
                                         ELSE UNCHANGED state
                 /\ Step("state-committed") /\ UNCHANGED <<live, ops>>
            [] cmd.step = "state-committed" ->                    \* 900
                 /\ SetOp(i, "phase", "state-committed")
                 /\ Step("committed") /\ UNCHANGED <<live, state>>
            [] cmd.step = "committed" ->                          \* 901-902
                 /\ ops' = [ops EXCEPT ![i].journal = "committed", ![i].phase = "committed"]
                 /\ Done /\ UNCHANGED <<live, state>>
       /\ UNCHANGED <<src, stuck>>

-----------------------------------------------------------------------------
(* rollback, operations.py 694-723, with _rollback_install (789-826),      *)
(* _rollback_quarantine (911-938), _begin_rollback (762-766) and           *)
(* _restore_state_entry (768-787). Both rollbacks decide what to undo from *)
(* the disk, here op.staged, op.aside and op.held, not from the journaled  *)
(* phase, and journal rolling-back once their checks pass.                 *)

\* _ensure_no_newer_active_operation, 732-753: a newer committed operation
\* on the same target refuses the rollback (README: LIFO per path).
NewerOnPath(i) ==
    \E j \in Indexes : j > i /\ ops[j].journal = "committed" /\ ops[j].skill = ops[i].skill

Live == {i \in Indexes : ops[i].journal \in {"in-progress", "rolling-back", "committed"}}

\* Refuse: stop the command with stuck set. A check of the rollback's own
\* trees failing in this model means the tool left them inconsistent, since
\* nothing else touches them.
Refuse == stuck' = TRUE /\ Done /\ UNCHANGED <<src, live, state, ops>>

RollbackAllowed(i) ==
    /\ cmd = Idle
    /\ i \in Live                                              \* 702-708
    /\ Incomplete \subseteq {i}                                \* 701
    /\ ~NewerOnPath(i) \/ "a" \in Mutants                      \* 709
    /\ RollbackOrder = "newest" => \A j \in Live : j <= i

\* The new tree is at the target (799): staged/ is empty and rollback-new/
\* is not. Mutant h decides it from the journaled phase, as before F3's fix.
NewLive(op) ==
    /\ op.kind = "install"
    /\ IF "h" \in Mutants
         THEN op.phase \in {"target-installed", "state-committed", "committed"}
         ELSE ~op.staged /\ op.aside = None

\* The old tree is held in preimage/ (807, 822) or the quarantine path
\* (918). Mutant i takes a prepared operation to have moved nothing, as
\* before F2's fix.
OldHeld(op) == op.held # None /\ ~("i" \in Mutants /\ op.phase = "prepared")

\* The checks before the rollback changes anything.
RollbackRefused(i) ==
    LET op == ops[i]
        s == op.skill
    IN IF NewLive(op)                                            \* 800-806, 817-818
         THEN live[s] # op.new \/ (op.before # None /\ ~OldHeld(op))
       ELSE IF OldHeld(op) \/ op.before = None                   \* 807-809, 919-921
         THEN live[s] # None
       ELSE live[s] # op.before                                  \* 810-816, 927-932

StartRollback(i) ==
    /\ RollbackAllowed(i) /\ ~RollbackRefused(i)
    /\ cmd' = [kind |-> "rollback", op |-> i, step |-> "begin"]
    /\ UNCHANGED <<src, live, state, ops, stuck>>

RefuseRollback(i) == RollbackAllowed(i) /\ RollbackRefused(i) /\ Refuse

RollbackStep ==
    LET i == cmd.op
        op == ops[i]
        s == op.skill
    IN /\ cmd.kind = "rollback"
       /\ CASE cmd.step = "begin" ->                              \* 819, 933, 762-766
                 /\ IF "j" \in Mutants THEN UNCHANGED ops         \* as before F4's fix
                    ELSE SetOp(i, "journal", "rolling-back")
                 /\ Step(IF NewLive(op) /\ "f" \notin Mutants THEN "aside" ELSE "restore")
                 /\ UNCHANGED <<src, live, state, stuck>>
            [] cmd.step = "aside" ->                              \* 820-821, 755-760
                 /\ live' = [live EXCEPT ![s] = None] /\ SetOp(i, "aside", live[s])
                 /\ Step("restore") /\ UNCHANGED <<src, state, stuck>>
            [] cmd.step = "restore" ->                            \* 822-825, 934-937
                 IF ~OldHeld(op)
                   THEN Step("state") /\ UNCHANGED <<src, live, state, ops, stuck>>
                 ELSE IF live[s] # None THEN Refuse               \* the rename finds the target occupied
                 ELSE /\ live' = [live EXCEPT ![s] = op.held] /\ SetOp(i, "held", None)
                      /\ Step("state") /\ UNCHANGED <<src, state, stuck>>
            [] cmd.step = "state" ->                              \* 826, 938, 768-787: this skill's entry
                 /\ state' = CASE "c" \in Mutants -> state
                               [] "g" \in Mutants -> op.statePre \* the whole file, as before F1's fix
                               [] OTHER -> [state EXCEPT ![s] = op.statePre[s]]
                 /\ Step("journal") /\ UNCHANGED <<src, live, ops, stuck>>
            [] cmd.step = "journal" ->                            \* 720-722
                 /\ ops' = [ops EXCEPT ![i].journal = "rolled-back", ![i].phase = "rolled-back"]
                 /\ Done /\ UNCHANGED <<src, live, state, stuck>>

-----------------------------------------------------------------------------
(* Stops and the environment. *)

\* Where a stop leaves the disk, named by the command's next step.
\* "journal": every visible change is journaled; fail_after injects here.
\* "unjournaled": a rename or state write the journal does not show yet.
\* "rollback": inside a rollback, after its checks.
WindowOf(c) ==
    LET op == ops[c.op] IN
    CASE c.kind = "rollback" -> "rollback"
      [] c.step = "preimage-preserved" /\ op.before = None -> "journal"
      [] c.step = "state-committed" /\ c.kind = "quarantine"
           /\ op.statePre[op.skill] = None -> "journal"
      [] c.step \in {"preimage-preserved", "target-installed", "target-quarantined",
                     "state-committed"} -> "unjournaled"
      [] OTHER -> "journal"

Stop ==
    /\ cmd # Idle /\ WindowOf(cmd) \in StopWindows
    /\ Done
    /\ UNCHANGED <<src, live, state, ops, stuck>>

\* The canonical source changes between commands.
SourceUpdate(s) ==
    /\ cmd = Idle /\ src[s] = "v1"
    /\ src' = [src EXCEPT ![s] = "v2"]
    /\ UNCHANGED <<live, state, ops, cmd, stuck>>

Next ==
    \/ \E s \in Skills, force \in BOOLEAN : StartInstall(s, force)
    \/ \E s \in Skills : StartQuarantine(s) \/ SourceUpdate(s)
    \/ \E i \in 1..MaxOps : StartRollback(i) \/ RefuseRollback(i)   \* i \in Live first
    \/ InstallStep \/ QuarantineStep \/ RollbackStep \/ Stop

Spec == Init /\ [][Next]_vars

-----------------------------------------------------------------------------
(* Properties. *)

TypeOK ==
    /\ src \in [Skills -> Versions]
    /\ live \in [Skills -> Trees \cup {None}]
    /\ state \in [Skills -> Versions \cup {None}]
    /\ stuck \in BOOLEAN

\* A rollback of the tool's own operation never refuses on its own trees.
NoStuckRollback == ~stuck

\* With no command running and no incomplete operation, status tells the
\* truth: no managed entry without its tree, no managed tree differing from
\* its entry, and no tree the tool installed shown as unmanaged.
StatusAgrees ==
    cmd = Idle /\ Incomplete = {} =>
        \A s \in Skills :
            /\ Status(s) \notin {"missing-managed", "locally-modified"}
            /\ Status(s) = "unmanaged-collision" => live[s] = "foreign"

\* A rollback that finishes leaves its skill as it was before the operation.
RollbackRestores ==
    [][cmd.kind = "rollback" /\ ops'[cmd.op].journal = "rolled-back" =>
         LET op == ops[cmd.op] IN
         live'[op.skill] = op.before /\ state'[op.skill] = op.statePre[op.skill]]_vars

\* A rollback changes no other skill's install-state entry.
RollbackStaysOnItsSkill ==
    [][cmd.kind = "rollback" =>
         \A t \in Skills \ {ops[cmd.op].skill} : state'[t] = state[t]]_vars
=============================================================================
