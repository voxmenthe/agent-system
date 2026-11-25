#!/usr/bin/env python3
"""Drive `navigation.py peek`'s real fzf drill-down through an owned tmux session.

Target: SHELL/git-helpers/navigation.py `peek` -> nav_browser.browse(), which
needs a real TTY on stdin/stdout and spawns real fzf for commit -> file -> hunk
drill-down. This probe supplies the TTY via tmux (no fzf double), waits on
observable pane state with deadlines, sends one key at a time, exercises a
resize edge plus Ctrl-C interrupt/recovery, and proves the fixture Git repo is
not mutated and no owned process or session leaks.

Usage:
    python3 verify_peek_tui.py --helpers-dir /path/to/SHELL/git-helpers \
        --root /path/to/owned/workdir

Exit: 0 when every check passes; 2 on any failed state/check. Evidence (raw
tmux transcript, per-state captures, identity, mutation/leak audit, summary)
is written under <root>/evidence and the disposable fixture repo stays under
<root>/fixture-repo for inspection; delete <root> to remove everything.

Requires: tmux, fzf, git, python3 on PATH. No installation, no product edits.
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

HELPERS = ("navigation.py", "nav_browser.py", "nav_core.py", "nav_analysis.py", "classes.tsv")


class ProbeError(Exception):
    pass


def sh(args: list[str], *, env: dict | None = None, ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, env=env, check=False, timeout=20)
    if result.returncode not in ok:
        raise ProbeError(
            f"{shlex.join(args)} -> rc {result.returncode}: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Tmux:
    """One owned tmux session. Every command carries the exact session name."""

    def __init__(self, name: str, log) -> None:
        self.name = name
        self.log = log
        self.pane_pid: int | None = None
        self.owned_pids: set[int] = set()

    def __call__(self, *args: str, ok: tuple[int, ...] = (0,)) -> str:
        cmd = ["tmux", "-L", self.name, "-f", os.devnull, *args]
        try:
            result = subprocess.run(cmd, capture_output=True, check=False, timeout=10)
        except OSError as exc:
            raise ProbeError(f"{shlex.join(cmd)}: {exc}") from exc
        self.log(f"$ {shlex.join(cmd)} -> rc {result.returncode}")
        if result.returncode not in ok:
            raise ProbeError(
                f"{shlex.join(cmd)}: {result.stderr.decode('utf-8', 'replace').strip()}"
            )
        return result.stdout.decode("utf-8", "replace")

    def capture(self, esc: bool = False) -> str:
        # Current rendered frame only; scrollback could match a stale prompt.
        args = ["capture-pane", "-t", self.name, "-p"]
        if esc:
            args.append("-e")
        return self(*args)

    def send(self, *keys: str) -> None:
        self("send-keys", "-t", self.name, *keys)

    def pane_command(self) -> str:
        self.observe_owned_processes()
        return self("display-message", "-t", self.name, "-p", "#{pane_current_command}").strip()

    def observe_owned_processes(self) -> None:
        if self.pane_pid is None:
            return
        rows = sh(["ps", "-eo", "pid=,ppid="]).stdout.decode().splitlines()
        parents = {int(pid): int(parent) for pid, parent in (row.split() for row in rows)}
        found = {self.pane_pid}
        while children := {pid for pid, parent in parents.items() if parent in found} - found:
            found.update(children)
        self.owned_pids.update(found)

    def wait(self, pattern: str, deadline: float, label: str) -> tuple[str, float]:
        """Poll the pane screen for a regex; return (screen, seconds) or raise."""
        rx = re.compile(pattern)
        start = time.monotonic()
        screen = ""
        while time.monotonic() - start < deadline:
            self.observe_owned_processes()
            screen = self.capture()
            if rx.search(screen):
                return screen, time.monotonic() - start
            time.sleep(0.25)
        raise ProbeError(f"timed out after {deadline}s waiting for {label} ({pattern!r})")

    def wait_command(self, pattern: str, deadline: float, label: str) -> str:
        """Poll pane_current_command (foreground process of the pane's pty)."""
        rx = re.compile(pattern)
        start = time.monotonic()
        current = ""
        while time.monotonic() - start < deadline:
            current = self.pane_command()
            if rx.search(current):
                return current
            time.sleep(0.25)
        raise ProbeError(
            f"timed out after {deadline}s waiting for pane command {label}; "
            f"last={current!r}"
        )


def fixture_env() -> dict[str, str]:
    return dict(
        {key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="V02 Probe",
        GIT_COMMITTER_NAME="V02 Probe",
        GIT_AUTHOR_EMAIL="probe@example.invalid",
        GIT_COMMITTER_EMAIL="probe@example.invalid",
        GIT_CONFIG_COUNT="0",
        GIT_OPTIONAL_LOCKS="0",
    )


def build_fixture(repo: Path, log) -> None:
    """Disposable repo: c1 adds a .py module + test, c2 edits that module in two
    distant places (one file, two hunks), c3 is docs-only so the commit picker
    has both a suggested and an unsuggested row."""
    env = fixture_env()
    repo.mkdir(parents=True)
    sh(["git", "init", "-q", "-b", "main", str(repo)], env=env)
    sh(["git", "-C", str(repo), "config", "core.hooksPath", os.devnull], env=env)
    sh(["git", "-C", str(repo), "config", "commit.gpgsign", "false"], env=env)

    def write(name: str, text: str) -> None:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(msg: str) -> str:
        sh(["git", "-C", str(repo), "add", "--all"], env=env)
        sh(["git", "-C", str(repo), "commit", "-qm", msg], env=env)
        return sh(["git", "-C", str(repo), "rev-parse", "HEAD"], env=env).stdout.decode().strip()

    body = "HEADER = 1\n" + "".join(f"def fn_{i}():\n    return {i}\n\n" for i in range(20))
    write("src/task.py", body)
    write("tests/test_task.py", "from src.task import fn_0\nassert fn_0() == 0\n")
    c1 = commit("add task module and tests")
    revised = body.replace("HEADER = 1", "HEADER = 2").replace("return 19", "return 190")
    write("src/task.py", revised)
    c2 = commit("revise task module in two places")
    write("notes.md", "# notes only\n")
    c3 = commit("docs note")
    log(f"fixture commits: {c1[:8]} {c2[:8]} {c3[:8]}")


def repo_snapshot(repo: Path) -> dict:
    env = fixture_env()
    status = sh(
        ["git", "-C", str(repo), "status", "--porcelain=v1", "-z"], env=env
    ).stdout.decode("utf-8", "surrogateescape")
    head = sh(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], env=env
    ).stdout.decode().strip()
    files = {}
    for path in sorted(repo.rglob("*")):
        if path.is_file() and ".git" not in path.relative_to(repo).parts:
            files[str(path.relative_to(repo))] = sha256(path)
    index = repo / ".git" / "index"
    return {
        "status_z": status,
        "head": head,
        "index_sha256": sha256(index) if index.exists() else None,
        "worktree_sha256": files,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--helpers-dir", required=True, type=Path,
                    help="Directory containing navigation.py (read-only)")
    ap.add_argument("--root", required=True, type=Path,
                    help="Owned work dir; fixture repo + evidence live under it")
    ap.add_argument("--timeout", type=float, default=20.0,
                    help="Per-state wait deadline seconds")
    opts = ap.parse_args()
    if not 0 < opts.timeout <= 120:
        ap.error("--timeout must be positive and at most 120 seconds")

    helpers = opts.helpers_dir.resolve()
    cli = helpers / "navigation.py"
    for name in HELPERS:
        if not (helpers / name).is_file():
            print(f"input error: missing {helpers / name}", file=sys.stderr)
            return 2
    root = opts.root.resolve()
    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(f"input error: --root must not already exist: {root}", file=sys.stderr)
        return 2
    evidence = root / "evidence"
    evidence.mkdir()
    repo = root / "fixture-repo"
    session = f"v02-peek-{os.getpid()}-{uuid.uuid4().hex[:10]}"

    log_lines: list[str] = []

    def log(line: str) -> None:
        stamped = f"{time.strftime('%H:%M:%S')} {line}"
        log_lines.append(stamped)
        print(stamped)
        (evidence / "commands.log").write_text("\n".join(log_lines) + "\n")

    def save(name: str, text: str) -> None:
        (evidence / name).write_text(text)

    tm = Tmux(session, log)
    summary: dict = {"session": session, "checks": [], "failed": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        summary["checks"].append({"check": name, "ok": ok, "detail": detail})
        if not ok:
            summary["failed"].append(name)
        log(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""))

    pane_pid = None
    created = False
    try:
        for tool in ("tmux", "fzf", "git"):
            if not shutil.which(tool):
                raise ProbeError(f"prerequisite missing: {tool}")
        if sys.version_info < (3, 10):
            raise ProbeError("prerequisite: python 3.10+ to drive the probe")
        log("prerequisites present: tmux fzf git python3")

        # Identity of the code under test (source) and runtime.
        save("identity.json", json.dumps({
            "helpers_dir": str(helpers),
            "source_sha256": {n: sha256(helpers / n) for n in HELPERS},
            "runtime": {
                "python": sys.executable,
                "python_version": sys.version.split()[0],
                "fzf": sh(["fzf", "--version"]).stdout.decode().strip(),
                "tmux": sh(["tmux", "-V"]).stdout.decode().strip(),
                "git": sh(["git", "--version"]).stdout.decode().strip(),
            },
        }, indent=2))

        build_fixture(repo, log)
        before = repo_snapshot(repo)
        save("fixture-before.json", json.dumps(before, indent=2))

        # Private server/socket, no personal tmux config or interactive shell rc.
        tm("new-session", "-d", "-s", session, "-x", "100", "-y", "30", "/bin/bash --noprofile --norc")
        created = True
        tm("set-option", "-w", "-t", session, "window-size", "manual")
        pane_pid = tm("display-message", "-t", session, "-p", "#{pane_pid}").strip()
        tm.pane_pid = int(pane_pid)
        log(f"session {session} pane_pid {pane_pid}")
        tm("pipe-pane", "-t", session, "-o",
           f"cat >> {shlex.quote(str(evidence / 'transcript.raw'))}")

        # Prove the pane shell is alive before sending the real command.
        tm.send(f"echo PANE_READY_{os.getpid()}")
        tm.send("Enter")
        tm.wait(rf"(?m)^PANE_READY_{os.getpid()}$", opts.timeout, "pane shell readiness")

        launch = f"cd {shlex.quote(str(repo))} && " + shlex.join([
            "env", "GIT_CONFIG_GLOBAL=" + os.devnull, "GIT_CONFIG_NOSYSTEM=1",
            "GIT_CONFIG_COUNT=0", "PAGER=cat", "GIT_PAGER=cat", "TERM=xterm-256color",
            sys.executable, "-B", str(cli), "peek",
        ])
        tm.send(launch)
        tm.send("Enter")
        log("launched: " + launch)

        # Runtime identity: the pane's foreground process is our python.
        fg = tm.wait_command(r"python", opts.timeout, "python foreground")
        check("pane foreground is launched python", True, fg)
        save("pane-foreground.txt", fg + "\n")

        # State C: commit picker.
        screen, secs = tm.wait(r"commit \(\* suggested\)> ", opts.timeout, "commit picker")
        save("01-commit-picker.txt", screen)
        save("01-commit-picker.esc.txt", tm.capture(esc=True))
        check("commit picker rendered", True, f"{secs:.1f}s")
        check("suggested commits marked", bool(
            re.search(r"Suggested because|\*", screen)), "")

        # Enter -> file list of the selected commit.
        tm.send("Enter")
        screen, secs = tm.wait(r"file> ", opts.timeout, "file list")
        save("02-file-list.txt", screen)
        check("commit->file drill-down", "src/task.py" in screen, f"{secs:.1f}s")

        # Enter -> hunk list (fixture guarantees 2 hunks in src/task.py for c2).
        tm.send("Enter")
        screen, secs = tm.wait(r"hunk \(\d+/\d+\)> ", opts.timeout, "hunk list")
        save("03-hunk-list.txt", screen)
        m = re.search(r"hunk \((\d+)/(\d+)\)> ", screen)
        check("file->hunk drill-down", bool(m), m.group(0) if m else "")
        check("two hunks reachable", bool(m and m.group(2) == "2"),
              m.group(0) if m else "no prompt")

        # Esc -> back to file list; Esc -> back to commit picker.
        tm.send("Escape")
        screen, _ = tm.wait(r"file> ", opts.timeout, "back to file list")
        save("04-back-file.txt", screen)
        check("esc hunk->file", True)
        tm.send("Escape")
        screen, _ = tm.wait(r"commit \(\* suggested\)> ", opts.timeout, "back to commit list")
        save("05-back-commit.txt", screen)
        check("esc file->commit", True)

        # Interrupt inside drill-down: Enter -> file>, Ctrl-C -> fzf rc130 ->
        # choose() returns None -> inner loop breaks -> commit picker again.
        tm.send("Enter")
        tm.wait(r"file> ", opts.timeout, "file list for ctrl-c")
        save("06-pre-ctrlc.txt", tm.capture())
        tm.send("C-c")
        screen, secs = tm.wait(r"commit \(\* suggested\)> ", opts.timeout,
                               "in-app recovery after ctrl-c")
        save("07-ctrlc-recovery.txt", screen)
        check("ctrl-c in file list recovers to commit picker", True, f"{secs:.1f}s")

        # Resize edge: SIGWINCH to the pane; fzf must redraw and still accept
        # input. Proof is functional (transition still works), not pixel match.
        tm("resize-window", "-t", session, "-x", "132", "-y", "40")
        after_resize, _ = tm.wait(r"commit \(\* suggested\)> ", opts.timeout, "commit picker after resize")
        save("08-after-resize.txt", after_resize)
        geom = tm("display-message", "-t", session,
                  "-p", "#{window_width}x#{window_height}").strip()
        check("window resized to 132x40", geom == "132x40", geom)
        check("commit picker still rendered after resize",
              bool(re.search(r"commit \(\* suggested\)> ", after_resize)))
        tm.send("Down")
        tm.send("Enter")
        screen, secs = tm.wait(r"file> ", opts.timeout, "file list after resize")
        save("09-post-resize-drill.txt", screen)
        check("input+transition work after resize", "task.py" in screen, f"{secs:.1f}s")
        tm.send("Escape")
        tm.wait(r"commit \(\* suggested\)> ", opts.timeout, "commit picker again")

        # Ctrl-C at top level -> fzf exits -> browse() returns -> shell recovers.
        # Wait for the shell to be foreground again before typing, so the echo
        # cannot be swallowed by a still-live fzf query line.
        tm.send("C-c")
        fg = tm.wait_command(r"zsh|bash|sh", opts.timeout, "shell foreground after ctrl-c")
        tm.send("echo PROBE_EXITED_$?")
        tm.send("Enter")
        screen, _ = tm.wait(r"PROBE_EXITED_\d+", opts.timeout, "shell recovery echo")
        save("10-shell-recovered.txt", screen)
        m = re.search(r"PROBE_EXITED_(\d+)", screen)
        check("shell responsive after exit", bool(m), f"fg={fg}")
        check("peek exited cleanly via ctrl-c", bool(m and m.group(1) in {"0", "130"}),
              f"rc={m.group(1) if m else '?'}")

        # Fixture non-mutation by the browser path.
        after = repo_snapshot(repo)
        save("fixture-after.json", json.dumps(after, indent=2))
        check("git index unchanged", before["index_sha256"] == after["index_sha256"])
        check("worktree unchanged", before["worktree_sha256"] == after["worktree_sha256"])
        check("HEAD unchanged", before["head"] == after["head"])
        check("status unchanged", before["status_z"] == after["status_z"],
              repr(after["status_z"]))

    except (ProbeError, OSError, subprocess.SubprocessError) as exc:
        log(f"PROBE ERROR: {exc}")
        summary["failed"].append(f"probe-error: {exc}")
        try:
            save("99-failure-screen.txt", tm.capture())
            save("99-failure-screen.esc.txt", tm.capture(esc=True))
        except (ProbeError, OSError, subprocess.SubprocessError):
            pass
    finally:
        # Stop exactly the session we created; verify nothing owned survives.
        # Cleanup must tolerate a missing tmux (nothing could have been created).

        if created:
            try:
                tm.observe_owned_processes()
                # A failed state wait may leave fzf active. Back out through
                # hunk/file/commit before closing its controlling terminal.
                for _ in range(3):
                    if re.fullmatch(r"bash|sh", tm.pane_command()):
                        break
                    tm.send("C-c")
                    try:
                        tm.wait_command(r"^(bash|sh)$", 0.75, "shell during cleanup")
                        break
                    except ProbeError:
                        pass
                tm.observe_owned_processes()
                tm("kill-session", "-t", session)
                result = sh(["tmux", "-L", session, "has-session", "-t", session], ok=(0, 1))
                check("owned tmux session removed", result.returncode == 1)
                deadline = time.monotonic() + 5
                alive = set(tm.owned_pids)
                escalated = False
                while alive and time.monotonic() < deadline:
                    live = {int(line) for line in sh(["ps", "-eo", "pid="]).stdout.splitlines()}
                    alive.intersection_update(live)
                    if alive:
                        # SIGHUP can leave a stopped fzf orphan. Escalate only
                        # against observed descendants of this owned pane.
                        if not escalated:
                            for pid in alive:
                                try:
                                    os.kill(pid, signal.SIGCONT)
                                    os.kill(pid, signal.SIGTERM)
                                except ProcessLookupError:
                                    pass
                            escalated = True
                        time.sleep(0.1)
                if alive:
                    for pid in alive:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    deadline = time.monotonic() + 2
                    while alive and time.monotonic() < deadline:
                        live = {int(line) for line in sh(["ps", "-eo", "pid="]).stdout.splitlines()}
                        alive.intersection_update(live)
                        if alive:
                            time.sleep(0.1)
                check("no observed owned process leak", not alive, f"survivors={sorted(alive)}")
                summary["owned_pids"] = sorted(tm.owned_pids)
            except (ProbeError, OSError, subprocess.SubprocessError) as exc:
                check("owned cleanup", False, str(exc))
        save("summary.json", json.dumps(summary, indent=2))
        transcript = evidence / "transcript.raw"
        log(f"transcript bytes: {transcript.stat().st_size if transcript.exists() else 0}")

    ok = not summary["failed"]
    print("RESULT:", "PASS" if ok else "FAIL", "evidence:", evidence)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
