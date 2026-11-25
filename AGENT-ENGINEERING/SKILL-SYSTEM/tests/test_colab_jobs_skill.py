"""colab-jobs: skill contract, registry record, and the helper end to end against a fake `colab`.

The fake runs the code the helper sends to `colab exec` in a local Python
process, with /content mapped to a temporary directory, so jobs, transfers and
exit codes go through the same VM-side code as on Colab. No network.
"""
from __future__ import annotations

import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest import mock

from skill_system.model import validate_skill_tree

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "colab-jobs"
HELPER = SKILL_ROOT / "scripts" / "colab_job.py"

FAKE_COLAB = r'''#!/usr/bin/env python3
import json, os, re, shutil, subprocess, sys, time
home = os.environ["FAKE_COLAB_HOME"]
state_path = os.path.join(home, "state.json")
state = json.load(open(state_path))
args = sys.argv[1:]
with open(os.path.join(home, "calls.jsonl"), "a") as log:
    log.write(json.dumps(args) + "\n")

def save():
    json.dump(state, open(state_path, "w"))

def opt(flag):
    return args[args.index(flag) + 1] if flag in args else None

def vm_root(name):
    return os.path.join(home, "vm", name)

def vm_path(name, remote):
    root = vm_root(name)
    if remote.startswith(root):
        return remote
    remote = remote.lstrip("/")
    return os.path.join(root, remote[len("content"):].lstrip("/"))

def need_session(name):
    if name not in state["sessions"]:
        print("[colab] Session '%s' not found." % name)
        sys.exit(1)

def need_signin():
    if not state["signed_in"]:
        sys.stderr.write("\nTo authorize colab-cli, visit this URL in any browser:\n\n  https://accounts.example/auth\n\n")
        sys.stdout.write("Enter the authorization code: \nAborted.\n")
        sys.exit(1)

cmd = args[0]
if cmd == "version":
    print("Version: 0.8.0"); sys.exit(0)
need_signin()
name = opt("-s")
if cmd == "whoami":
    print("Auth provider: oauth2\nEmail:         tester@example.com")
elif cmd == "usage":
    rate = 0.08 * len(state["sessions"])
    print("Current balance: 100.00 compute units\nUsage rate: %.2f/hr\nActive assignments: %d" % (rate, len(state["sessions"])))
elif cmd == "sessions":
    if state.get("fail_sessions"):
        state["fail_sessions"] -= 1; save()
        print("ReadTimeout: HTTPSConnectionPool(host='colab.example', port=443): Read timed out.")
        sys.exit(1)
    if not state["sessions"]:
        print("[colab] No active sessions found on server.")
    for n, s in state["sessions"].items():
        print("[%s] %s | Hardware: %s | Shape: Standard | Variant: DEFAULT" % (n, s["endpoint"], s["hardware"]))
elif cmd == "new":
    if state.get("refuse_new"):
        sys.stderr.write("[colab] Allocation refused (precondition failed). This can mean too many active sessions.\n")
        sys.exit(1)
    os.makedirs(vm_root(name), exist_ok=True)
    state["sessions"][name] = {"endpoint": "m-s-" + name, "hardware": opt("--gpu") or "CPU"}
    save()
    print("[colab] Creating session '%s'...\n[colab] Session READY." % name)
elif cmd == "stop":
    state["sessions"].pop(name, None); save()
    print("[colab] Session terminated.")
elif cmd == "exec":
    need_session(name)
    code = sys.stdin.read().replace("/content", vm_root(name))
    # fail_ops = {op: [mode, ...]}: "before" loses the call before it runs, "after" runs it and loses the reply,
    # "hang" prints the CLI's lost-connection error and then never exits (seen live on a T4)
    op = re.findall(r"run_op\('(\w+)'", code)[-1]
    modes = state.get("fail_ops", {}).get(op, [])
    mode = modes.pop(0) if modes else None
    save()
    if mode == "hang":
        sys.stderr.write("RuntimeError: Connection was lost.\n"); sys.stderr.flush()
        time.sleep(300)
    if mode != "before":
        done = subprocess.run([sys.executable, "-c", code], cwd=vm_root(name), capture_output=True, text=True)
    if mode:
        sys.stderr.write("RuntimeError: Connection was lost.\n")
        sys.exit(1)
    sys.stdout.write(done.stdout); sys.stderr.write(done.stderr)
elif cmd in ("upload", "download"):
    need_session(name)
    source, target = args[-2], args[-1]
    if cmd == "upload":
        target = vm_path(name, target)
        if state.get("fail_upload") or not os.path.isdir(os.path.dirname(target)):
            print("[colab] Upload failed: 500 Server Error for url: https://8080-vm.example/api/contents/x?authuser=0&colab-runtime-proxy-token=eyJhbGciOiJFUzI1NiJ9.eyJhdWQiOiJ4In0.SIGNATUREabc")
            sys.exit(1)
    else:
        source = vm_path(name, source)
        if not os.path.isfile(source):
            print("[colab] Download failed: File or directory not found: %s" % source); sys.exit(1)
        source = state.get("download_override") or source
    shutil.copyfile(source, target)
    print("[colab] done")
else:
    sys.exit("fake colab: unsupported command %r" % cmd)
'''


def load_helper():
    spec = importlib.util.spec_from_file_location("colab_job", HELPER)
    module = importlib.util.module_from_spec(spec)
    # run as a script, the helper imports its sibling log_view from its own directory
    with mock.patch.dict(sys.modules, {"colab_job": module}), \
            mock.patch.object(sys, "path", [str(HELPER.parent), *sys.path]), \
            mock.patch.object(sys, "dont_write_bytecode", True):
        spec.loader.exec_module(module)
    return module


class SkillPackageTests(unittest.TestCase):
    def test_validates_and_is_explicit_only(self) -> None:
        self.assertRegex(validate_skill_tree(SKILL_ROOT, "colab-jobs"), r"^sha256:")
        self.assertIn("disable-model-invocation: true", (SKILL_ROOT / "SKILL.md").read_text())
        metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text()
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("$colab-jobs", metadata)

    def test_registry_record_and_guide_entry(self) -> None:
        record = json.loads((ROOT / "registry.json").read_text())["skills"]["colab-jobs"]
        self.assertEqual("custom", record["ownership"])
        self.assertEqual("skills/colab-jobs", record["source"])
        self.assertEqual("external-write", record["effect_ceiling"])
        self.assertEqual(["~/.agents/skills/colab-jobs"], record["install_targets"])
        self.assertIn("[`colab-jobs`](skills/colab-jobs/SKILL.md)", (ROOT / "USER-GUIDE.md").read_text())

    def test_quick_start_commands_exist_in_the_helper(self) -> None:
        # Weaker agents copy the quick start verbatim; every command it names must parse.
        skill = (SKILL_ROOT / "SKILL.md").read_text()
        parser = load_helper().build_parser()
        commands = set(parser._subparsers._group_actions[0].choices)
        quoted = set(__import__("re").findall(r"colab_job\.py (\w+)", skill))
        self.assertTrue(quoted, "SKILL.md names no helper commands")
        self.assertLessEqual(quoted, commands)


class FakeColab:
    def __init__(self, root: Path, **state) -> None:
        self.home = root / "fake"
        (self.home / "vm").mkdir(parents=True)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        colab = bin_dir / "colab"
        colab.write_text(FAKE_COLAB)
        colab.chmod(0o755)
        self.state_path = self.home / "state.json"
        self.state_path.write_text(json.dumps({"sessions": {}, "signed_in": True, **state}))
        self.env = dict(os.environ, PATH="%s%s%s" % (bin_dir, os.pathsep, os.environ["PATH"]),
                        HOME=str(root / "home"), FAKE_COLAB_HOME=str(self.home))

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())

    def update(self, **values) -> None:
        self.state_path.write_text(json.dumps({**self.state(), **values}))

    def calls(self) -> list[list[str]]:
        path = self.home / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class HelperContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.fake = FakeColab(self.tmp)
        self.leases = self.tmp / "home" / ".codex" / "state" / "colab-jobs" / "leases"

    def helper(self, *argv: str, timeout: float = 120) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(HELPER), *argv], env=self.fake.env, cwd=self.tmp,
                              capture_output=True, text=True, timeout=timeout)

    def assertExit(self, code: int, done: subprocess.CompletedProcess) -> None:
        self.assertEqual(code, done.returncode, done.stdout + done.stderr)

    def test_signed_out_exits_10_and_never_shows_the_sign_in_url(self) -> None:
        self.fake.update(signed_in=False)
        done = self.helper("doctor", timeout=30)
        self.assertExit(10, done)
        self.assertIn("NEXT: ask the user to run `colab whoami`", done.stdout)
        self.assertNotIn("https://", done.stdout + done.stderr)

    def test_up_refuses_a_running_name_before_allocating(self) -> None:
        self.fake.update(sessions={"exp-1": {"endpoint": "m-s-exp-1", "hardware": "CPU"}})
        self.assertExit(14, self.helper("up", "exp-1"))
        self.assertNotIn("new", [call[0] for call in self.fake.calls()])

    def test_refused_allocation_exits_12_and_leaves_no_lease(self) -> None:
        self.fake.update(refuse_new=True)
        done = self.helper("up", "exp-1", "--gpu", "t4")
        self.assertExit(12, done)
        self.assertIn(["new", "-s", "exp-1", "--gpu", "T4"], self.fake.calls())
        self.assertFalse((self.leases / "exp-1.json").exists())

    def test_install_refuses_torch_unless_allowed(self) -> None:
        self.fake.update(sessions={"exp-1": {"endpoint": "m-s-exp-1", "hardware": "CPU"}})
        done = self.helper("install", "exp-1", "transformers", "torch==2.0")
        self.assertExit(2, done)
        self.assertIn("refusing to install torch", done.stdout)
        self.assertNotIn("exec", [call[0] for call in self.fake.calls()])

    def test_failed_upload_is_reported_without_the_runtime_token(self) -> None:
        self.fake.update(sessions={"exp-1": {"endpoint": "m-s-exp-1", "hardware": "CPU"}}, fail_upload=True)
        (self.fake.home / "vm" / "exp-1").mkdir()
        (self.tmp / "data.txt").write_text("x")
        done = self.helper("push", "exp-1", "data.txt")
        self.assertExit(15, done)
        self.assertIn("colab-runtime-proxy-token=<redacted>", done.stdout)
        self.assertNotIn("SIGNATUREabc", done.stdout + done.stderr)

    def test_session_lifecycle_end_to_end(self) -> None:
        up = self.helper("up", "exp-1")
        self.assertExit(0, up)
        self.assertIn("HARDWARE: CPU (Standard)", up.stdout)
        self.assertIn("LEASE: stops by itself", up.stdout)
        self.assertTrue((self.leases / "exp-1.json").exists())
        self.assertExit(14, self.helper("up", "exp-1"))

        project = self.tmp / "project"
        (project / ".git").mkdir(parents=True)
        (project / ".git" / "HEAD").write_text("ref")
        (project / "data").mkdir()
        (project / "data" / "rows.txt").write_text("a\nb\n")
        (project / "train.py").write_text(
            "import os, sys, time\n"
            "rows = open('data/rows.txt').read().split()\n"
            "for step in range(3):\n"
            "    sys.stdout.write('\\rprogress %d/3' % (step + 1)); sys.stdout.flush()\n"
            "print()\n"
            "os.makedirs('outputs', exist_ok=True)\n"
            "open('outputs/result.txt', 'w').write('rows=%d' % len(rows))\n"
            "print('done', len(rows))\n")
        pushed = self.helper("push", "exp-1", "project")
        self.assertExit(0, pushed)
        self.assertIn("(2 files,", pushed.stdout)
        self.assertFalse((self.fake.home / "vm" / "exp-1" / "work" / "project" / ".git").exists())

        ran = self.helper("run", "exp-1", "--cwd", "project", "--", sys.executable, "train.py")
        self.assertExit(0, ran)
        self.assertIn("progress 3/3", ran.stdout)
        self.assertNotIn("progress 1/3", ran.stdout)
        self.assertIn("done 2", ran.stdout)
        self.assertIn("STATE: succeeded", ran.stdout)

        noisy = "import sys\nfor i in range(5000): print('line', i)\nprint('FINAL ERROR')\nsys.exit(3)\n"
        failed = self.helper("run", "exp-1", "--", sys.executable, "-c", noisy)
        self.assertExit(1, failed)
        self.assertIn("EXIT_CODE: 3", failed.stdout)
        self.assertIn("FINAL ERROR", failed.stdout)
        self.assertIn("log lines not shown", failed.stdout)
        self.assertLess(len(failed.stdout), 20000)

        slow = self.helper("run", "exp-1", "--job", "slow", "--wait", "1", "--",
                           sys.executable, "-c", "import time; print('start', flush=True); time.sleep(4); print('end')")
        self.assertExit(75, slow)
        self.assertIn("STATE: running", slow.stdout)
        self.assertIn("wait exp-1 slow", slow.stdout)
        waited = self.helper("wait", "exp-1", "--wait", "30")
        self.assertExit(0, waited)
        self.assertIn("end", waited.stdout)
        self.assertIn("ELAPSED:", self.helper("logs", "exp-1", "slow").stdout)

        results = self.tmp / "results"
        pulled = self.helper("pull", "exp-1", "project/outputs", str(results))
        self.assertExit(0, pulled)
        self.assertEqual("rows=2", (results / "outputs" / "result.txt").read_text())
        self.assertExit(2, self.helper("pull", "exp-1", "project/outputs", str(results)))
        self.assertExit(0, self.helper("pull", "exp-1", "project/outputs/result.txt", str(self.tmp / "one")))
        self.assertExit(2, self.helper("pull", "exp-1", "project/missing", str(results)))

        down = self.helper("down", "exp-1")
        self.assertExit(0, down)
        self.assertIn("RELEASED: exp-1", down.stdout)
        self.assertEqual({}, self.fake.state()["sessions"])
        self.assertFalse((self.leases / "exp-1.json").exists())
        self.assertExit(13, self.helper("run", "exp-1", "--", "true"))
        self.assertExit(0, self.helper("down", "exp-1"))

    def test_a_lost_status_check_is_retried_while_following_a_job(self) -> None:
        # 11-22: on a live T4 one poll exec hung while its job had already finished
        self.assertExit(0, self.helper("up", "exp-3"))
        self.fake.update(fail_ops={"poll": ["before", "before"]})
        done = self.helper("run", "exp-3", "--", sys.executable, "-c", "print('ok')")
        self.assertExit(0, done)
        self.assertEqual(2, done.stdout.count("retrying"))
        self.assertIn("STATE: succeeded", done.stdout)
        self.assertExit(0, self.helper("down", "exp-3"))

    def test_a_lost_connection_that_hangs_the_cli_is_retried_at_once(self) -> None:
        # 11-22 wave 2: the CLI printed "Connection was lost." and then hung until the 45-120 s timeout
        self.assertExit(0, self.helper("up", "exp-5"))
        self.fake.update(fail_ops={"poll": ["hang"]})
        started = time.monotonic()
        done = self.helper("run", "exp-5", "--", sys.executable, "-c", "print('ok')")
        self.assertExit(0, done)
        self.assertLess(time.monotonic() - started, 30)
        self.assertIn("lost its connection to the VM", done.stdout)
        self.assertExit(0, self.helper("down", "exp-5"))

    def test_a_push_whose_unpack_reply_was_lost_and_a_slow_session_list_are_retried(self) -> None:
        # 11-22 wave 3: on an Asia T4 a push failed when its unpack reply was lost, and down failed
        # once on a ReadTimeout while listing sessions
        self.assertExit(0, self.helper("up", "exp-6"))
        project = self.tmp / "proj6"
        project.mkdir()
        (project / "a.txt").write_text("a")
        self.fake.update(fail_ops={"unpack": ["after"]})
        pushed = self.helper("push", "exp-6", str(project))
        self.assertExit(0, pushed)
        self.assertIn("retrying automatically (2 of 3)", pushed.stdout)
        self.assertIn("(1 file,", pushed.stdout)
        self.assertEqual("a", (self.fake.home / "vm" / "exp-6" / "work" / "proj6" / "a.txt").read_text())
        self.fake.update(fail_sessions=1)
        down = self.helper("down", "exp-6")
        self.assertExit(0, down)
        self.assertIn("ReadTimeout: HTTPSConnectionPool", down.stdout)
        self.assertIn("RELEASED: exp-6", down.stdout)

    def test_a_start_whose_reply_was_lost_is_retried_and_runs_once(self) -> None:
        # 11-22 wave 1: an install start exec hung for 120 s; the agent saw exit 15 and had to guess
        self.assertExit(0, self.helper("up", "exp-4"))
        self.fake.update(fail_ops={"start": ["after"]})
        count_run = "open('runs.txt', 'a').write('x'); print('ran')"
        done = self.helper("run", "exp-4", "--job", "once", "--", sys.executable, "-c", count_run)
        self.assertExit(0, done)
        self.assertIn("retrying automatically (2 of 3)", done.stdout)
        self.assertIn("the earlier attempt had started it", done.stdout)
        self.assertEqual("x", (self.fake.home / "vm" / "exp-4" / "work" / "runs.txt").read_text())
        again = self.helper("run", "exp-4", "--job", "once", "--", sys.executable, "-c", count_run)
        self.assertExit(2, again)
        self.assertIn("already exists", again.stdout)
        self.assertEqual("x", (self.fake.home / "vm" / "exp-4" / "work" / "runs.txt").read_text())
        self.assertExit(0, self.helper("down", "exp-4"))

    def test_pull_refuses_archives_with_escaping_or_linked_entries(self) -> None:
        self.assertExit(0, self.helper("up", "exp-7"))
        outputs = self.fake.home / "vm" / "exp-7" / "work" / "outputs"
        outputs.mkdir(parents=True)
        (outputs / "ok.txt").write_text("ok")
        escaping = tarfile.TarInfo("../evil.txt")
        escaping.size = 1
        link = tarfile.TarInfo("outputs/link")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        for member in (escaping, link):
            with self.subTest(member=member.name):
                bad = self.tmp / "bad.tar.gz"
                with tarfile.open(bad, "w:gz") as tar:
                    tar.addfile(member, io.BytesIO(b"x") if member.isfile() else None)
                self.fake.update(download_override=str(bad))
                dest = Path(tempfile.mkdtemp(dir=self.tmp)) / "results"
                done = self.helper("pull", "exp-7", "outputs", str(dest))
                self.assertExit(15, done)
                self.assertIn("refusing unsafe archive entry", done.stdout)
                self.assertEqual([], list(dest.iterdir()))
                self.assertFalse((dest.parent / "evil.txt").exists())

    def test_jobs_stats_and_grep_show_what_runs_and_what_ran(self) -> None:
        self.assertExit(0, self.helper("up", "exp-8"))
        self.assertIn("JOBS: none yet on exp-8", self.helper("jobs", "exp-8").stdout)
        smi = self.tmp / "bin" / "nvidia-smi"  # stands in for a T4's
        smi.write_text("#!/bin/sh\necho 'Tesla T4, 97, 9876, 15360, 64'\n")
        smi.chmod(0o755)
        # the first loss line ends up more than the 256 KB that plain logs reads before the end
        noisy = "print('step 1 loss 2.50')\nfor i in range(4000): print('x' * 80)\nprint('step 2 LOSS 1.25')\nraise SystemExit(4)\n"
        self.assertExit(1, self.helper("run", "exp-8", "--job", "noisy", "--", sys.executable, "-c", noisy))
        slow = "import time; print('epoch 1 loss 0.9', flush=True); time.sleep(8)"
        self.assertExit(75, self.helper("run", "exp-8", "--job", "slow", "--wait", "1", "--", sys.executable, "-c", slow))

        jobs = self.helper("jobs", "exp-8")
        self.assertExit(0, jobs)
        lines = jobs.stdout.splitlines()
        self.assertRegex(lines[0], r"^JOB: slow \| running for \d+s \| \S*python\S* -c 'import time")
        self.assertEqual("  LAST: epoch 1 loss 0.9", lines[1])
        self.assertRegex(lines[2], r"^JOB: noisy \| failed in \d+s, exit 4 \| ")
        self.assertEqual("  LAST: step 2 LOSS 1.25", lines[3])
        self.assertEqual("JOBS: 2 on exp-8, newest first", lines[4])

        stats = self.helper("stats", "exp-8")
        self.assertExit(0, stats)
        self.assertIn("GPU: Tesla T4 | 97% busy | memory 9876 of 15360 MiB | 64 C", stats.stdout)
        self.assertRegex(stats.stdout, r"\nRUNNING: slow \| \d+s \| ")
        self.assertNotIn("noisy", stats.stdout)

        grep = self.helper("logs", "exp-8", "noisy", "--grep", "loss")
        self.assertExit(0, grep)
        self.assertEqual(["step 1 loss 2.50", "step 2 LOSS 1.25"], grep.stdout.splitlines()[:2])
        self.assertIn("MATCHES: 2 lines of the whole log match 'loss' (case-insensitive); showing the last 2", grep.stdout)
        self.assertNotIn("step 1 loss", self.helper("logs", "exp-8", "noisy", "--tail", "9999").stdout)
        bad = self.helper("logs", "exp-8", "--grep", "loss(")
        self.assertExit(2, bad)
        self.assertIn("not a valid regular expression", bad.stderr)

        self.assertExit(0, self.helper("wait", "exp-8", "slow", "--wait", "30"))
        self.assertRegex(self.helper("jobs", "exp-8").stdout, r"JOB: slow \| succeeded in \d+s, exit 0 \| ")
        self.assertIn("RUNNING: no jobs", self.helper("stats", "exp-8").stdout)
        self.assertExit(0, self.helper("down", "exp-8"))

    def test_an_expired_lease_stops_the_session_by_itself(self) -> None:
        self.assertExit(0, self.helper("up", "exp-2", "--hours", "0.0005"))
        expired_dir = self.leases.parent / "expired"
        deadline = time.monotonic() + 20
        while not list(expired_dir.glob("exp-2-*.json")) and time.monotonic() < deadline:
            time.sleep(0.5)
        self.assertEqual({}, self.fake.state()["sessions"])
        expired = list(expired_dir.glob("exp-2-*.json"))
        self.assertEqual(1, len(expired))
        self.assertFalse((self.leases / "exp-2.json").exists())


if __name__ == "__main__":
    unittest.main()


class MonitorFormatTests(unittest.TestCase):
    def test_an_install_job_shows_its_packages_not_the_runner_command(self) -> None:
        spec = json.dumps({"specs": ["trl", "-r", "/content/colab-jobs/_xfer/requirements-ab.txt"], "names": ["trl"]})
        job = {"job": "install-1", "kind": "install", "argv": ["/usr/bin/python3", "/content/colab-jobs/vm_ops.py",
               "install", spec], "state": "succeeded", "exit_code": 0, "elapsed": 41, "tail": "  trl==0.25.1\n"}
        lines = load_helper().format_jobs("exp-1", {"jobs": [job], "total": 1})
        self.assertEqual(["JOB: install-1 | succeeded in 41s, exit 0 | install trl -r "
                          "/content/colab-jobs/_xfer/requirements-ab.txt", "  LAST: trl==0.25.1",
                          "JOBS: 1 on exp-1, newest first"], lines)


class ProcSamplingTests(unittest.TestCase):
    """stats reads Linux /proc on the VM; macOS has none, so a fabricated one stands in."""

    def test_sessions_sum_each_jobs_cpu_and_memory(self) -> None:
        spec = importlib.util.spec_from_file_location("vm_ops_under_test", SKILL_ROOT / "scripts" / "vm_ops.py")
        vm_ops = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(vm_ops)
        proc = Path(tempfile.mkdtemp())

        def stat(pid: int, comm: str, pgrp: int, session: int, utime: int, stime: int, rss_pages: int) -> None:
            # proc(5): pid (comm) state ppid pgrp session tty_nr tpgid flags minflt cminflt majflt cmajflt
            # utime stime cutime cstime priority nice num_threads itrealvalue starttime vsize rss ...
            (proc / str(pid)).mkdir()
            (proc / str(pid) / "stat").write_text(
                "%d (%s) S 1 %d %d 0 -1 4194560 10 0 0 0 %d %d 0 0 20 0 1 0 100 1000 %d 0 0\n"
                % (pid, comm, pgrp, session, utime, stime, rss_pages))

        stat(100, "python3", 100, 100, 5, 1, 10)  # a job's runner leads its own session
        stat(101, "pt_main (worker) 1", 101, 100, 30, 4, 200)  # own process group; ")" in its name
        stat(7, "jupyter", 7, 7, 999, 1, 50)
        (proc / "self").mkdir()
        (proc / "meminfo").write_text("MemTotal:       13290452 kB\nMemFree:  100 kB\nMemAvailable:   11000000 kB\n")
        with mock.patch.object(vm_ops, "PROC", str(proc)):
            groups, memory = vm_ops.proc_sessions(), vm_ops.memory()
        page = os.sysconf("SC_PAGE_SIZE")
        self.assertEqual((40, 210 * page, 2), groups[100])
        self.assertEqual((1000, 50 * page, 1), groups[7])
        self.assertEqual({"total": 13290452 * 1024, "available": 11000000 * 1024}, memory)
