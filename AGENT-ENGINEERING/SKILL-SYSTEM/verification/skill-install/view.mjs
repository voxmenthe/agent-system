// Reader's words for SkillInstall.tla, for the statechart skill (--view view.mjs).
// cmd.step is the step about to run, so a step's label comes from the `from` state.
const tree = (t) => (t === "none" ? "no tree" : `tree ${t}`);
const entry = (e) => (e === "none" ? "no entry" : `entry ${e}`);
const skills = (v) => Object.keys(v.live).sort();
const disk = (v) => skills(v).map((s) => `${s}: ${tree(v.live[s])}, ${entry(v.state[s])}`).join("; ");
const opOf = (v) => v.ops[v.cmd.op];
const running = { install: "Installing", quarantine: "Quarantining", rollback: "Rolling back" };

export const state = (v) =>
  v.cmd.kind === "idle"
    ? ["Idle", v.stuck ? "rollback refused" : disk(v)]
    : [`${running[v.cmd.kind]} ${opOf(v).skill}`, disk(v)];

const phase = {
  install: {
    prepared: "journals the install as started", preserve: "moves the old tree into preimage/",
    "preimage-preserved": "journals the old tree saved", install: "puts the new tree in place",
    "target-installed": "journals the new tree in place", state: "writes the new entry",
    "state-committed": "journals the entry written", committed: "journals the install as done",
  },
  quarantine: {
    prepared: "journals the quarantine as started", move: "moves the tree to quarantine",
    "target-quarantined": "journals the tree moved", state: "removes the entry",
    "state-committed": "journals the entry removed", committed: "journals the quarantine as done",
  },
  rollback: {
    begin: "journals rolling back", aside: "moves the new tree aside", restore: "puts the old tree back",
    state: "restores the entry", journal: "journals it as rolled back",
  },
};

export const step = (action, from, to) => {
  const name = action.replace(/\(.*$/, "");
  if (name === "StartInstall") return `you install ${opOf(to).skill}`;
  if (name === "StartQuarantine") return `you quarantine ${opOf(to).skill}`;
  if (name === "StartRollback") return `you roll back the ${opOf(to).kind} of ${opOf(to).skill}`;
  if (name === "RefuseRollback") return "you roll back an operation, and it refuses";
  if (name === "SourceUpdate") return `${skills(from).find((s) => from.src[s] !== to.src[s])}'s source changes`;
  if (name === "Stop") return "the command stops";
  if (to.stuck && !from.stuck) return `${from.cmd.kind} refuses: the target is occupied`;
  if (from.cmd.step === "preserve" && opOf(from).before === "none") return "install finds no old tree to save";
  // A broken variant can skip a write; say so rather than claim it.
  const wrote = ["live", "state", "ops"].some((k) => JSON.stringify(from[k]) !== JSON.stringify(to[k]));
  return `${from.cmd.kind} ${phase[from.cmd.kind][from.cmd.step]}${wrote ? "" : " (nothing changes)"}`;
};

export const group = (v) => (v.stuck ? "stuck" : v.cmd.kind === "idle" ? "rest" : "busy");
export const colors = { rest: "teal", busy: "blue", stuck: "orange" };
export const title = "Skill install, quarantine and rollback";
