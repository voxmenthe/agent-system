------------------------------ MODULE WaveRunner ------------------------------
(***************************************************************************)
(* The supervision loop of the delegate wave runner,                       *)
(* AGENT-ENGINEERING/SKILL-SYSTEM/skills/delegate/scripts/run-wave.sh,     *)
(* lines 179-367 at the sync commit in manifest.json: dispatch, reaping,   *)
(* refused-launcher and exhausted-account bars, timeout and leftover       *)
(* stopping, cleanup, status files, the summary and the exit code. Parsing *)
(* and task writing (lines 1-178) are not modelled: the model starts with  *)
(* every .task written and each worker's account read (lines 141-148).     *)
(*                                                                         *)
(* Worker w is index w-1 in the script. Each runner action is one loop     *)
(* iteration or one statement and cites its lines. Worker processes,       *)
(* signals, the clock and the disk are adversarial.                        *)
(*                                                                         *)
(* Atomicity. Within an iteration the script reads only its own worker's   *)
(* processes, and a dead leader or group never comes back, so a later read *)
(* sees what an earlier one would: one iteration is one step.             *)
(*                                                                         *)
(* The environment acts only just before the runner next reads what it     *)
(* changes: worker processes before each reap pass, stop pass, the line    *)
(* 308 check and cleanup wait step; timers before each stop pass; the      *)
(* cleanup deadline at each wait; a signal before each read of interrupted.*)
(* An event elsewhere gives the same outcomes moved to the next such point,*)
(* since no step in between reads what it changes. Inside a pass, worker   *)
(* k's event commutes with every other worker's iteration, so it moves to  *)
(* the point before the pass (k not yet visited) or after it (visited). A  *)
(* signal inside a reap pass only decides whether a reaped worker's        *)
(* leftovers get a SIGTERM before the cleanup that follows sends one.      *)
(***************************************************************************)
EXTENDS Integers, FiniteSets

CONSTANTS
    N,              \* workers in the manifest (count, line 138)
    Launchers,      \* launcher aliases the manifest may name
    Accounts,       \* quota accounts, rows of launcher-routes.tsv
    AccountOf,      \* each launcher's account (accounts[i], lines 141-148)
    JobChoices,     \* --jobs values explored, after the cap at the worker count
    TimeoutChoices, \* whether --timeout is given: a subset of BOOLEAN
    MaxIOFailures,  \* failed writes, redirections and sleeps explored per run
    Mutants         \* broken variants switched on; {} checks the real code

Workers == 1..N
\* Account assignments the configs substitute for AccountOf; they name
\* launchers L and M.
SharedAccount == [l \in Launchers |-> "A"]
SplitAccounts == [l \in Launchers |-> IF l = "L" THEN "A" ELSE "B"]
\* A leader that has exited and that Bash has reaped, so kill -0 fails, but
\* that reap_finished has not yet collected. "refused" is a nonzero exit whose
\* stderr ends with a rate-limited or quarantined failure class (line 210);
\* "exhausted" is one whose class is an account quota exhausted on the
\* launcher's own harness (lines 202-203). The same line naming another
\* harness is "refused".
Exited == {"ok", "fail", "refused", "exhausted"}
Settled == {"0", "nonzero", "timeout"}
Statuses == {"none", "barred", "notstarted", "unconfirmed"} \cup Settled

VARIABLES
    \* Options, fixed for the run (lines 15, 36-37, 140).
    launcher,       \* launchers[i]
    jobs,           \* --jobs, capped at the worker count
    hasTimeout,     \* --timeout given
    \* Environment.
    leader,         \* "queued", "running", an Exited value, "reaped" or "skipped"
    leftovers,      \* the worker's process group has members besides the leader;
                    \* they may ignore TERM and survive KILL
    timedOut,       \* SECONDS - started[i] >= timeout (line 259)
    deadline,       \* the current cleanup wait's deadline has passed (lines 317, 330)
    interrupted,    \* the INT or TERM trap has run (lines 185-186)
    \* Runner.
    pc, ix, ret,    \* program counter, loop index, reap_finished's caller
    ling,           \* stop_groups's local lingering (line 249)
    status,         \* statuses[i]
    file,           \* the <name>.status file: "missing", "bad" or a status
    owned,          \* groups[i] is not empty
    stop,           \* stopping[i] and killed[i] with their elapsed windows:
                    \* "none", "term", "term5" (5 s since TERM), "kill", "kill2"
    next, active, result, ignoring, runnerFailed, barred, lingering,
    summaryOk, exitCode, ioFailures,
    \* History, read only by the properties.
    launchedAfterFailure, launchedBarred, launchesAfterInterrupt, timeoutStopped,
    exhaustedAccounts

vars == <<launcher, jobs, hasTimeout, leader, leftovers, timedOut, deadline,
          interrupted, pc, ix, ret, ling, status, file, owned, stop,
          next, active, result, ignoring, runnerFailed, barred, lingering,
          summaryOk, exitCode, ioFailures, launchedAfterFailure,
          launchedBarred, launchesAfterInterrupt, timeoutStopped, exhaustedAccounts>>
cfg  == <<launcher, jobs, hasTimeout>>
hist == <<launchedAfterFailure, launchedBarred, launchesAfterInterrupt, timeoutStopped,
          exhaustedAccounts>>

\* kill -0 -- -pgid succeeds while any member of the group is alive.
GroupAlive(w) == leader[w] = "running" \/ leftovers[w]
Live == {w \in Workers : owned[w] /\ GroupAlive(w)}
Outcomes == IF ioFailures < MaxIOFailures THEN BOOLEAN ELSE {TRUE}
Spend(ok) == ioFailures' = IF ok THEN ioFailures ELSE ioFailures + 1
\* write_status, lines 189-194: a failed write leaves a truncated file.
Write(w, st, ok) ==
    /\ status' = [status EXCEPT ![w] = st]
    /\ file' = [file EXCEPT ![w] = IF ok THEN st ELSE "bad"]
    /\ runnerFailed' = (runnerFailed \/ ~ok)
    /\ Spend(ok)

Init ==
    /\ launcher \in [Workers -> Launchers]
    /\ jobs \in JobChoices
    /\ hasTimeout \in TimeoutChoices
    /\ leader = [w \in Workers |-> "queued"]
    /\ leftovers = [w \in Workers |-> FALSE]
    /\ timedOut = [w \in Workers |-> FALSE]
    /\ deadline = FALSE
    /\ interrupted = FALSE
    /\ pc = "loop" /\ ix = 1 /\ ret = "none" /\ ling = FALSE
    /\ status = [w \in Workers |-> "none"]
    /\ file = [w \in Workers |-> "missing"]
    /\ owned = [w \in Workers |-> FALSE]
    /\ stop = [w \in Workers |-> "none"]
    /\ next = 0 /\ active = 0 /\ result = 0
    /\ ignoring = FALSE /\ runnerFailed = FALSE
    /\ barred = {} /\ lingering = FALSE
    /\ summaryOk = FALSE /\ exitCode = -1 /\ ioFailures = 0
    /\ launchedAfterFailure = FALSE /\ launchedBarred = FALSE
    /\ launchesAfterInterrupt = 0
    /\ timeoutStopped = [w \in Workers |-> FALSE]
    /\ exhaustedAccounts = {}

-----------------------------------------------------------------------------
(* The main loop, lines 279-306. *)

Loop ==   \* line 280
    /\ pc = "loop"
    /\ IF next < N \/ active > 0 \/ lingering
         THEN pc' = "reap" /\ ret' = "stopi"
         ELSE pc' = "confirm" /\ ret' = ret
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ix,
                   ling, status, file, owned, stop, next, active,
                   result, ignoring, runnerFailed, barred, lingering, summaryOk,
                   exitCode, ioFailures, hist>>

(* reap_finished, lines 214-241, one index per step. *)

ReapSkip ==   \* lines 217-218: settled already, or kill -0 still finds the leader
    /\ pc = "reap" /\ ix <= next
    /\ status[ix] # "none" \/ leader[ix] = "running"
    /\ ix' = ix + 1
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, pc,
                   ret, ling, status, file, owned, stop, next, active,
                   result, ignoring, runnerFailed, barred, lingering, summaryOk,
                   exitCode, ioFailures, hist>>

ReapOne ==    \* lines 219-238 for a leader that has exited
    /\ pc = "reap" /\ ix <= next
    /\ status[ix] = "none" /\ leader[ix] \in Exited
    /\ LET w == ix
           st == IF stop[w] # "none" /\ "f" \notin Mutants THEN "timeout"   \* 220
                 ELSE IF leader[w] = "ok" THEN "0" ELSE "nonzero"           \* 219
       IN \E ok \in Outcomes:
            /\ Write(w, st, ok)                                             \* 221, 224
            /\ active' = active - 1                                         \* 222
            /\ result' = IF st = "0" THEN result ELSE 1                     \* 223
            \* bar_refused (line 225) reads the class of a nonzero, untimed exit
            \* (200); adding a bar already there changes nothing (204, 209).
            /\ barred' = CASE st \in {"0", "timeout"} -> barred
                         [] leader[w] = "exhausted"
                            \/ (leader[w] = "refused" /\ "o" \in Mutants) ->
                              barred \cup {AccountOf[launcher[w]]}           \* 202-207
                         [] leader[w] = "refused" -> barred \cup {launcher[w]}  \* 209-211
                         [] OTHER -> barred
            /\ exhaustedAccounts' =
                 IF st \notin {"0", "timeout"} /\ leader[w] = "exhausted"
                   THEN exhaustedAccounts \cup {AccountOf[launcher[w]]}
                   ELSE exhaustedAccounts
            /\ leader' = [leader EXCEPT ![w] = "reaped"]
            /\ timedOut' = [timedOut EXCEPT ![w] = FALSE]   \* never read again
            /\ IF leftovers[w]                                              \* 226
                 THEN /\ stop' = IF ~interrupted /\ ~runnerFailed' /\ stop[w] = "none"
                                   THEN [stop EXCEPT ![w] = "term"]         \* 230-233
                                   ELSE stop
                      /\ owned' = owned
                 ELSE /\ owned' = [owned EXCEPT ![w] = FALSE]               \* 237
                      /\ stop' = [stop EXCEPT ![w] = "none"]   \* never read again
    /\ ix' = ix + 1
    /\ UNCHANGED <<cfg, leftovers, deadline, interrupted, pc, ret,
                   ling, next, ignoring, lingering, summaryOk, exitCode,
                   launchedAfterFailure, launchedBarred, launchesAfterInterrupt,
                   timeoutStopped>>

ReapDone ==
    /\ pc = "reap" /\ ix > next
    /\ pc' = ret /\ ret' = "none" /\ ix' = 1 /\ ling' = FALSE
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted,
                   status, file, owned, stop, next, active, result,
                   ignoring, runnerFailed, barred, lingering, summaryOk,
                   exitCode, ioFailures, hist>>

(* stop_groups, lines 248-278, one index per step. *)

StopUnchanged ==
    UNCHANGED <<cfg, leader, leftovers, deadline, interrupted, pc,
                ret, status, file, next, active, result, ignoring, barred,
                lingering, summaryOk, exitCode, ioFailures>>

StopPass ==   \* line 251, and lines 259-260's continue
    /\ pc = "stopi" /\ ix <= next
    /\ \/ ~owned[ix]
       \/ /\ GroupAlive(ix) /\ stop[ix] = "none"
          /\ ~(hasTimeout /\ status[ix] = "none" /\ timedOut[ix] /\ leader[ix] = "running")
    /\ ix' = ix + 1
    /\ UNCHANGED <<ling, owned, stop, timedOut, runnerFailed, hist>>
    /\ StopUnchanged

StopVanished ==   \* lines 252-256
    /\ pc = "stopi" /\ ix <= next
    /\ owned[ix] /\ ~GroupAlive(ix)
    /\ IF status[ix] # "none"
         THEN /\ owned' = [owned EXCEPT ![ix] = FALSE]
              /\ stop' = [stop EXCEPT ![ix] = "none"]   \* never read again
         ELSE UNCHANGED <<owned, stop>>
    /\ ix' = ix + 1
    /\ UNCHANGED <<ling, timedOut, runnerFailed, hist>>
    /\ StopUnchanged

LingerIf(w) ==   \* line 275
    ling' = (ling \/ (status[w] # "none" /\ "i" \notin Mutants))

StopTimeout ==   \* lines 259-263: the leader is past --timeout
    /\ pc = "stopi" /\ ix <= next
    /\ owned[ix] /\ GroupAlive(ix) /\ stop[ix] = "none"
    /\ hasTimeout /\ status[ix] = "none" /\ timedOut[ix] /\ leader[ix] = "running"
    /\ stop' = [stop EXCEPT ![ix] = "term"]
    /\ timedOut' = [timedOut EXCEPT ![ix] = FALSE]   \* never read again
    /\ timeoutStopped' = [timeoutStopped EXCEPT ![ix] = TRUE]
    /\ LingerIf(ix)
    /\ ix' = ix + 1
    /\ UNCHANGED <<owned, runnerFailed, launchedAfterFailure,
                   launchedBarred, launchesAfterInterrupt, exhaustedAccounts>>
    /\ StopUnchanged

StopEscalate ==  \* lines 264-274 for a group already being stopped
    /\ pc = "stopi" /\ ix <= next
    /\ owned[ix] /\ GroupAlive(ix) /\ stop[ix] # "none"
    /\ CASE stop[ix] = "term5" ->                                    \* 265-267
              /\ stop' = [stop EXCEPT ![ix] = "kill"]
              /\ UNCHANGED runnerFailed
         [] stop[ix] = "kill2" ->                                    \* 269-273
              /\ runnerFailed' = (runnerFailed \/ "n" \notin Mutants)
              /\ UNCHANGED stop
         [] OTHER -> UNCHANGED <<stop, runnerFailed>>
    /\ LingerIf(ix)
    /\ ix' = ix + 1
    /\ UNCHANGED <<owned, timedOut, hist>>
    /\ StopUnchanged

StopDone ==   \* lines 277, 282
    /\ pc = "stopi" /\ ix > next
    /\ lingering' = ling /\ ling' = FALSE /\ ix' = 1
    /\ pc' = "brk1"
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ret,
                   status, file, owned, stop, next, active, result,
                   ignoring, runnerFailed, barred, summaryOk, exitCode,
                   ioFailures, hist>>

Brk1 ==   \* line 283
    /\ pc = "brk1"
    /\ pc' = IF interrupted \/ runnerFailed THEN "confirm" ELSE "guard"
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ix,
                   ret, ling, status, file, owned, stop, next, active,
                   result, ignoring, runnerFailed, barred, lingering, summaryOk,
                   exitCode, ioFailures, hist>>

(* The dispatch loop, lines 284-303. *)

DispatchOpen ==   \* line 284
    /\ next < N
    /\ IF "c" \in Mutants THEN active <= jobs ELSE active < jobs
    /\ ~interrupted \/ "g" \in Mutants
    /\ ~runnerFailed \/ "a" \in Mutants

GuardClosed ==
    /\ pc = "guard" /\ ~DispatchOpen
    /\ pc' = "brk2"
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ix,
                   ret, ling, status, file, owned, stop, next, active,
                   result, ignoring, runnerFailed, barred, lingering, summaryOk,
                   exitCode, ioFailures, hist>>

\* Lines 285-289: the worker's launcher is barred, or else its account.
Barred(w) == launcher[w] \in barred \/ (AccountOf[launcher[w]] \in barred /\ "x" \notin Mutants)

GuardBarred ==    \* lines 285-294: a barred worker does not start
    /\ pc = "guard" /\ DispatchOpen
    /\ Barred(next + 1) /\ "b" \notin Mutants
    /\ \E ok \in Outcomes: Write(next + 1, "barred", ok)
    /\ leader' = [leader EXCEPT ![next + 1] = "skipped"]
    /\ next' = next + 1
    /\ UNCHANGED <<cfg, leftovers, timedOut, deadline, interrupted, pc, ix, ret,
                   ling, owned, stop, active, result, ignoring,
                   barred, lingering, summaryOk, exitCode, hist>>

GuardLaunch ==
    /\ pc = "guard" /\ DispatchOpen
    /\ ~Barred(next + 1) \/ "b" \in Mutants
    /\ pc' = "fork"
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ix,
                   ret, ling, status, file, owned, stop, next, active,
                   result, ignoring, runnerFailed, barred, lingering, summaryOk,
                   exitCode, ioFailures, hist>>

ForkFails ==      \* lines 296-298: the evidence files cannot be opened
    /\ pc = "fork" /\ ioFailures < MaxIOFailures
    /\ runnerFailed' = TRUE /\ ioFailures' = ioFailures + 1
    /\ pc' = "brk2"
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ix,
                   ret, ling, status, file, owned, stop, next, active,
                   result, ignoring, barred, lingering, summaryOk, exitCode, hist>>

Fork ==           \* lines 299-302
    /\ pc = "fork"
    /\ LET w == next + 1 IN
         /\ leader' = [leader EXCEPT ![w] = "running"]
         /\ owned' = [owned EXCEPT ![w] = TRUE]
         /\ launchedAfterFailure' = (launchedAfterFailure \/ runnerFailed)
         /\ launchedBarred' = (launchedBarred \/ launcher[w] \in barred
                                \/ AccountOf[launcher[w]] \in barred)
         /\ launchesAfterInterrupt' =
              launchesAfterInterrupt + (IF interrupted THEN 1 ELSE 0)
    /\ next' = next + 1 /\ active' = active + 1
    /\ pc' = "guard"
    /\ UNCHANGED <<cfg, leftovers, timedOut, deadline, interrupted, ix, ret,
                   ling, status, file, stop, result, ignoring,
                   runnerFailed, barred, lingering, summaryOk, exitCode,
                   ioFailures, timeoutStopped, exhaustedAccounts>>

Brk2 ==   \* line 304
    /\ pc = "brk2"
    /\ pc' = IF interrupted \/ runnerFailed THEN "confirm" ELSE "sleep"
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ix,
                   ret, ling, status, file, owned, stop, next, active,
                   result, ignoring, runnerFailed, barred, lingering, summaryOk,
                   exitCode, ioFailures, hist>>

Sleep ==  \* line 305
    /\ pc = "sleep"
    /\ IF active > 0 \/ lingering
         THEN \E ok \in Outcomes:
                /\ runnerFailed' = (runnerFailed \/ ~ok) /\ Spend(ok)
                /\ pc' = IF ok THEN "loop" ELSE "confirm"
         ELSE pc' = "loop" /\ UNCHANGED <<runnerFailed, ioFailures>>
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ix,
                   ret, ling, status, file, owned, stop, next, active,
                   result, ignoring, barred, lingering, summaryOk, exitCode, hist>>

-----------------------------------------------------------------------------
(* After the loop, lines 307-367. *)

Confirm ==   \* lines 307-310
    /\ pc = "confirm"
    /\ runnerFailed' = (runnerFailed \/ (Live # {} /\ "h" \notin Mutants))
    /\ pc' = "cleanup"
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ix,
                   ret, ling, status, file, owned, stop, next, active,
                   result, ignoring, barred, lingering, summaryOk, exitCode,
                   ioFailures, hist>>

RestStart == IF "j" \in Mutants THEN 1 ELSE next + 1   \* line 348 starts at next

Cleanup ==   \* line 311
    /\ pc = "cleanup"
    /\ IF interrupted \/ runnerFailed
         THEN pc' = "term" /\ ix' = ix
         ELSE pc' = "rest" /\ ix' = RestStart
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ret,
                   ling, status, file, owned, stop, next, active,
                   result, ignoring, runnerFailed, barred, lingering, summaryOk,
                   exitCode, ioFailures, hist>>

Term ==      \* lines 312-316: ignore further signals, TERM every owned group
    /\ pc = "term"
    /\ ignoring' = TRUE
    /\ pc' = "w5"
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ix,
                   ret, ling, status, file, owned, stop, next, active,
                   result, runnerFailed, barred, lingering, summaryOk, exitCode,
                   ioFailures, hist>>

WaitUnchanged ==
    UNCHANGED <<cfg, leader, leftovers, timedOut, interrupted, ix, ling, status,
                file, owned, stop, next, active, result, ignoring, runnerFailed,
                barred, lingering, summaryOk, exitCode, ioFailures, hist>>

Wait(at, check, after) ==   \* lines 317-318 and 330-331
    /\ pc = at
    /\ IF deadline
         THEN pc' = after /\ deadline' = FALSE /\ ret' = ret
         ELSE pc' = "reap" /\ ret' = check /\ deadline' = deadline
    /\ WaitUnchanged

WaitCheck(at, loop, after) ==   \* lines 319-324 and 332-337
    /\ pc = at
    /\ IF Live # {}
         THEN pc' = loop /\ deadline' = deadline
         ELSE pc' = after /\ deadline' = FALSE
    /\ UNCHANGED ret
    /\ WaitUnchanged

KillAll ==   \* lines 326-329: KILL every owned group
    /\ pc = "killall"
    /\ pc' = "w1"
    /\ UNCHANGED <<deadline, ret>>
    /\ WaitUnchanged

MarkOne ==   \* lines 339-345
    /\ pc = "mark" /\ ix <= next
    /\ LET w == ix
           unconfirmed == (owned[w] /\ GroupAlive(w) /\ "d" \notin Mutants)
                            \/ status[w] = "none"
           st == IF unconfirmed THEN "unconfirmed" ELSE status[w]
       IN IF "m" \in Mutants
            THEN /\ status' = [status EXCEPT ![w] = st]
                 /\ UNCHANGED <<file, runnerFailed, ioFailures>>
            ELSE \E ok \in Outcomes: Write(w, st, ok)                 \* 342-344
    /\ ix' = ix + 1
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, pc,
                   ret, ling, owned, stop, next, active, result,
                   ignoring, barred, lingering, summaryOk, exitCode, hist>>

MarkDone ==  \* line 346
    /\ pc = "mark" /\ ix > next
    /\ result' = 1 /\ pc' = "rest" /\ ix' = RestStart
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ret,
                   ling, status, file, owned, stop, next, active,
                   ignoring, runnerFailed, barred, lingering, summaryOk,
                   exitCode, ioFailures, hist>>

RestOne ==   \* line 348
    /\ pc = "rest" /\ ix <= N /\ "k" \notin Mutants
    /\ \E ok \in Outcomes: Write(ix, "notstarted", ok)
    /\ ix' = ix + 1
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, pc,
                   ret, ling, owned, stop, next, active, result,
                   ignoring, barred, lingering, summaryOk, exitCode, hist>>

RestDone ==
    /\ pc = "rest" /\ (ix > N \/ "k" \in Mutants)
    /\ pc' = "summary" /\ ix' = 1
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ret,
                   ling, status, file, owned, stop, next, active,
                   result, ignoring, runnerFailed, barred, lingering, summaryOk,
                   exitCode, ioFailures, hist>>

Summary ==   \* lines 349-364
    /\ pc = "summary"
    /\ \E ok \in Outcomes:
         /\ summaryOk' = ok /\ runnerFailed' = (runnerFailed \/ ~ok) /\ Spend(ok)
    /\ pc' = "exit"
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ix,
                   ret, ling, status, file, owned, stop, next, active,
                   result, ignoring, barred, lingering, exitCode, hist>>

Exit ==      \* lines 365-367
    /\ pc = "exit"
    /\ exitCode' = CASE interrupted -> 130
                     [] runnerFailed /\ "e" \notin Mutants -> 1
                     [] OTHER -> result
    /\ pc' = "done"
    /\ UNCHANGED <<cfg, leader, leftovers, timedOut, deadline, interrupted, ix,
                   ret, ling, status, file, owned, stop, next, active,
                   result, ignoring, runnerFailed, barred, lingering, summaryOk,
                   ioFailures, hist>>

Runner ==
    \/ Loop \/ ReapSkip \/ ReapOne \/ ReapDone
    \/ StopPass \/ StopVanished \/ StopTimeout \/ StopEscalate \/ StopDone
    \/ Brk1 \/ GuardClosed \/ GuardBarred \/ GuardLaunch \/ ForkFails \/ Fork
    \/ Brk2 \/ Sleep \/ Confirm \/ Cleanup \/ Term
    \/ Wait("w5", "w5chk", "killall") \/ WaitCheck("w5chk", "w5", "killall")
    \/ KillAll
    \/ Wait("w1", "w1chk", "mark") \/ WaitCheck("w1chk", "w1", "mark")
    \/ MarkOne \/ MarkDone \/ RestOne \/ RestDone \/ Summary \/ Exit

-----------------------------------------------------------------------------
(* The environment, acting before the runner's next read until it exits. *)

BeforeStopPass == pc = "stopi" /\ ix = 1
ProcessesRead == BeforeStopPass \/ pc \in {"loop", "confirm", "w5", "w5chk", "w1", "w1chk"}
InterruptRead == BeforeStopPass \/ pc \in {"loop", "guard", "fork", "confirm", "exit"}

EnvUnchanged ==
    UNCHANGED <<cfg, pc, ix, ret, ling, status, file, owned, next, active,
                result, ignoring, runnerFailed, barred, lingering, summaryOk,
                exitCode, ioFailures, hist>>

\* An adapter exits on its own, or from a signal the runner sent.
LeaderExits(w) ==
    /\ ProcessesRead /\ leader[w] = "running"
    /\ \E k \in Exited: leader' = [leader EXCEPT ![w] = k]
    /\ UNCHANGED <<leftovers, timedOut, deadline, interrupted, stop>>
    /\ EnvUnchanged

\* Other members of a live group start, or all of them exit or are killed.
LeftoversChange(w) ==
    /\ ProcessesRead /\ GroupAlive(w)
    /\ leftovers' = [leftovers EXCEPT ![w] = ~leftovers[w]]
    /\ UNCHANGED <<leader, timedOut, deadline, interrupted, stop>>
    /\ EnvUnchanged

TimeoutElapses(w) ==
    /\ BeforeStopPass /\ hasTimeout /\ leader[w] = "running" /\ stop[w] = "none"
    /\ ~timedOut[w]
    /\ timedOut' = [timedOut EXCEPT ![w] = TRUE]
    /\ UNCHANGED <<leader, leftovers, deadline, interrupted, stop>>
    /\ EnvUnchanged

\* Five seconds pass after TERM, or two after KILL (lines 265, 269).
WindowElapses(w) ==
    /\ BeforeStopPass /\ stop[w] \in {"term", "kill"}
    /\ stop' = [stop EXCEPT ![w] = IF stop[w] = "term" THEN "term5" ELSE "kill2"]
    /\ UNCHANGED <<leader, leftovers, timedOut, deadline, interrupted>>
    /\ EnvUnchanged

DeadlinePasses ==
    /\ pc \in {"w5", "w1"} /\ ~deadline
    /\ deadline' = TRUE
    /\ UNCHANGED <<leader, leftovers, timedOut, interrupted, stop>>
    /\ EnvUnchanged

\* SIGINT or SIGTERM; the trap runs between two commands (lines 185-186).
Interrupt ==
    /\ InterruptRead /\ ~interrupted /\ ~ignoring
    /\ interrupted' = TRUE
    /\ UNCHANGED <<leader, leftovers, timedOut, deadline, stop>>
    /\ EnvUnchanged

Env ==
    \/ \E w \in Workers:
         LeaderExits(w) \/ LeftoversChange(w) \/ TimeoutElapses(w) \/ WindowElapses(w)
    \/ DeadlinePasses \/ Interrupt

Finished == pc = "done" /\ UNCHANGED vars

Next == Runner \/ Env \/ Finished

Spec == Init /\ [][Next]_vars

\* For Termination: the runner keeps running, time passes, and without
\* --timeout every adapter eventually exits on its own. The environment acts
\* only at some runner steps, so its fairness is strong.
FairSpec ==
    /\ Spec
    /\ WF_vars(Runner)
    /\ SF_vars(DeadlinePasses)
    /\ \A w \in Workers:
         /\ SF_vars(WindowElapses(w))
         /\ SF_vars(TimeoutElapses(w))
         /\ SF_vars(~hasTimeout /\ LeaderExits(w))

-----------------------------------------------------------------------------
(* Properties. *)

Done == pc = "done"

TypeOK ==
    /\ launcher \in [Workers -> Launchers] /\ jobs \in JobChoices /\ hasTimeout \in BOOLEAN
    /\ leader \in [Workers -> {"queued", "running", "reaped", "skipped"} \cup Exited]
    /\ leftovers \in [Workers -> BOOLEAN]
    /\ status \in [Workers -> Statuses]
    /\ file \in [Workers -> {"missing", "bad"} \cup Statuses]
    /\ stop \in [Workers -> {"none", "term", "term5", "kill", "kill2"}]
    /\ next \in 0..N /\ active \in 0..N /\ ioFailures \in 0..MaxIOFailures
    /\ AccountOf \in [Launchers -> Accounts] /\ Launchers \cap Accounts = {}
    /\ barred \subseteq Launchers \cup Accounts
    /\ exhaustedAccounts \subseteq Accounts
    /\ exitCode \in {-1, 0, 1, 130}

\* The counter the cap is enforced on equals the adapters launched and not yet collected.
ActiveCounts ==
    active = Cardinality({w \in Workers : leader[w] \in {"running"} \cup Exited})

\* At most --jobs adapters run at once (wave-runner.md: "at most N at once").
CapRespected ==
    Cardinality({w \in Workers : leader[w] \in {"running"} \cup Exited}) <= jobs

\* After a status, evidence, sleep or summary failure, or a group that
\* survived SIGKILL, no further worker starts.
NoLaunchAfterRunnerFailure == ~launchedAfterFailure

\* A launcher barred for a rate-limited or quarantined refusal, or an account
\* barred for an exhausted quota, starts no more of this wave's workers.
NoBarredLaunch == ~launchedBarred

\* Only a worker that exhausted its account's quota bars the account; any other
\* refusal leaves the account's other launchers eligible.
AccountBarsNeedExhaustion == barred \cap Accounts \subseteq exhaustedAccounts

\* A signal stops dispatch; only a launch already past the dispatch check
\* (line 284) can still start.
InterruptStopsDispatch == launchesAfterInterrupt <= 1

\* At exit every worker has a status.
EveryWorkerHasAStatus == Done => \A w \in Workers : status[w] # "none"

\* The runner never exits while a worker's process group is alive unless it
\* marks that worker unconfirmed and exits nonzero ("scopes are not released").
NoUnreportedLiveGroup ==
    Done => \A w \in Workers :
              GroupAlive(w) => status[w] = "unconfirmed" /\ exitCode # 0

\* Every .status file holds the worker's final status, or a write failed and
\* the wave exits nonzero.
StatusFilesMatch ==
    Done => \A w \in Workers :
              file[w] = status[w] \/ (file[w] = "bad" /\ exitCode # 0)

\* Exit 0 means every adapter exited 0, its status file says so, the summary
\* was written, and nothing the wave started is still alive.
ExitZeroIsClean ==
    Done /\ exitCode = 0 =>
        /\ summaryOk
        /\ \A w \in Workers : status[w] = "0" /\ file[w] = "0" /\ ~GroupAlive(w)

\* A worker stopped for passing --timeout never reads as an ordinary exit.
TimeoutIsReported ==
    \A w \in Workers :
        timeoutStopped[w] => status[w] \in {"none", "timeout", "unconfirmed"}

\* Completed statuses survive; only cleanup that cannot confirm a group ended
\* replaces one, with unconfirmed.
SettledStatusesSurvive ==
    [][\A w \in Workers :
         status[w] \in Settled \cup {"barred", "notstarted"} =>
           status'[w] \in {status[w], "unconfirmed"}]_status

\* The runner always exits: with --timeout even if adapters never exit,
\* and without it once they do.
Termination == <>Done
=============================================================================
