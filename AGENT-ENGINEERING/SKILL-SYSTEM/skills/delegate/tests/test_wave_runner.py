"""CLI contracts using bounded local fixtures, never model calls."""
from __future__ import annotations

import csv
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

SKILL = Path(__file__).resolve().parents[1]
RUNNER = SKILL / "scripts/run-wave.sh"
SHELLS = list(dict.fromkeys(["/bin/bash", shutil.which("bash")]))
LAUNCHERS = """
agg aggbs aggb aggbbs agom agoh argm argh aghh aghhb aghx aghxb agcm agcmb agch agchb agnm agnmb agnh agnhb agnx agnxb kimm kimb kimbs
agg2 aggbs2 aggb2 aggbbs2 agom2 agoh2 argm2 argh2 aghh2 aghhb2 aghx2 aghxb2 agcm2 agcmb2 agch2 agchb2 agnm2 agnmb2 agnh2 agnhb2 agnx2 agnxb2
dglm dswe dargh dopmm doph dopx dopm grok grokxh grok2 grok2xh grok3 grok3xh
clm clmb clme clmbe clm2 clmb2 clme2 clmbe2 ctx ctxb ctx2 ctxb2 ctm ctmb ctm2 ctmb2
cdx cdxb cdxe cdxbe cdx2 cdxb2 cdxe2 cdxbe2 cdm cdmb cdme cdmbe
cdm2 cdmb2 cdme2 cdmbe2 cam camb cax caxb camm cammb cah cahb
cam2 camb2 cax2 caxb2 camm2 cammb2 cah2 cahb2
cdmM cdxX camM caxX cdmM2 cdxX2 camM2 caxX2 ocs ommp ocargh ocmm26 ochy4flash oclongcat ociceman
cmg cmds cmm26p cms cmdglyph cmdflint pihy4flash pilongcat piiceman
csm csu csx cshh csmm csbm csbu csbx csbh csbmm chm chu chx chh chmm
chbm chbu chbx chbh chbmm ccx ccbx ccm ccbm ccmm ccfh ccbfh ccfx ccbfx ccmM ccxX
cck cckm ccku cckx cckh cckmm cckbm cckbu cckbx cckbh cckbmm
cckfm cckfu cckfx cckfh cckfmm cckbfm cckbfu cckbfx cckbfh cckbfmm
""".split()
DEVIN_LAUNCHERS = {"dglm", "dswe", "dargh", "dopmm", "doph", "dopx", "dopm"}
FAKE = r'''#!/usr/bin/env python3
import os, signal, subprocess, sys, time
from pathlib import Path
assert sys.argv[2] == '--task-file'
task = Path(sys.argv[3])
assert task.is_absolute()
assert sys.stdin.read() == ''
name = task.stem
control = Path(os.environ['WAVE_CONTROL'])
(control / (name + '.cwd')).write_text(os.getcwd())
(control / (name + '.pid')).write_text(str(os.getpid()))
# WAVE_DESCENDANT: a child that ignores SIGTERM; WAVE_LEFTOVER: one that obeys it.
if os.environ.get('WAVE_DESCENDANT') or os.environ.get('WAVE_LEFTOVER'):
    ignore = "signal.signal(signal.SIGTERM, signal.SIG_IGN); " if os.environ.get('WAVE_DESCENDANT') else ""
    child = subprocess.Popen([sys.executable, '-c',
        "import signal,time; " + ignore +
        "open(__import__('sys').argv[1], 'w').write(str(__import__('os').getpid())); time.sleep(60)",
        str(control / (name + '.child'))])
    while not (control / (name + '.child')).exists():
        time.sleep(.01)
while not (control / (name + '.release')).exists():
    time.sleep(.01)
sys.stdout.buffer.write('STATUS: blocked\né\n'.encode())
sys.stderr.write('diagnostic:' + name + '\n')
# <name>.class: the failure class line run-worker.sh ends a failed run with.
if (control / (name + '.class')).exists():
    sys.stderr.write((control / (name + '.class')).read_text())
sys.exit(int((control / (name + '.release')).read_text() or '0'))
'''


class WaveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="delegate wave ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "work space"
        self.workspace.mkdir()
        self.control = self.root / "control"
        self.control.mkdir()
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        self.runner = self.scripts / "run-wave.sh"
        shutil.copy2(RUNNER, self.runner)
        shutil.copy2(SKILL / "scripts/launcher-routes.tsv", self.scripts / "launcher-routes.tsv")
        self.adapter = self.scripts / "run-worker.sh"
        self.adapter.write_text(FAKE)
        self.adapter.chmod(0o755)
        self.manifest = self.root / "wave.txt"
        self.env = dict(os.environ, WAVE_CONTROL=str(self.control),
                        BASH_AGENTS_FILE=str(self.root / "must-not-source"))
        self.sequence = 0

    def manifest_text(self, names: tuple[str, ...] = ("a",), role: str = "review") -> str:
        return (f"COMMON:\nROLE: {role}\nWORKSPACE: {self.workspace}\n"
                "CONTEXT: agreed contract\nCONSTRAINTS: bounded\n"
                "OBJECTIVE: check\nSCOPE: read only\nVERIFY: trace\n\n" +
                "".join(f"@@ launcher=agg name={name}\n" for name in names))

    def command(self, text: str, *flags: str, shell: str = "/bin/bash") -> tuple[list[str], Path]:
        self.sequence += 1
        self.manifest.write_bytes(text.encode())
        jobs = self.root / f"jobs {self.sequence}"
        return ([shell, str(self.runner), "--wave", "wave.txt", "--jobs-dir",
                 jobs.name, *flags], jobs)

    def run_wave(self, text: str, *flags: str, shell: str = "/bin/bash") -> tuple[subprocess.CompletedProcess, Path]:
        args, jobs = self.command(text, *flags, shell=shell)
        return subprocess.run(args, cwd=self.root, env=self.env, text=True,
                              capture_output=True, timeout=15), jobs

    def start(self, text: str, *flags: str, shell: str = "/bin/bash") -> tuple[subprocess.Popen, Path]:
        args, jobs = self.command(text, *flags, shell=shell)
        log = open(self.root / f"log-{self.sequence}", "w+")
        self.addCleanup(log.close)
        process = subprocess.Popen(args, cwd=self.root, env=self.env,
                                   stdout=log, stderr=log, start_new_session=True)
        self.addCleanup(self.stop, process)
        return process, jobs

    def stop(self, process: subprocess.Popen) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=9)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        # Fixture-only leak containment if the runner under test is defective.
        for pattern in ("*.pid", "*.child"):
            for path in self.control.glob(pattern):
                try:
                    os.kill(int(path.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def wait_path(self, path: Path, process: subprocess.Popen | None = None) -> None:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if path.exists() and path.stat().st_size:
                return
            if process is not None and process.poll() is not None:
                self.fail(f"runner exited {process.returncode} before {path}")
            time.sleep(.01)
        self.fail(f"deadline waiting for {path}")

    def release(self, name: str, code: int = 0) -> None:
        (self.control / f"{name}.release").write_text(str(code))

    def rows(self, jobs: Path) -> list[dict[str, str]]:
        with (jobs / "SUMMARY.tsv").open() as stream:
            return list(csv.DictReader(stream, delimiter="\t"))

    def test_reference_examples_and_literal_composition_on_both_shells(self) -> None:
        examples = re.findall(r"```text\n(.*?)```", (SKILL / "references/wave-runner.md").read_text(), re.S)
        self.assertEqual(2, len(examples))
        literal = '  $(touch NEVER) `touch NEVER` ${HOME} \\ "quoted"\n  @@ quoted\n  COMMON:\n'
        for shell in SHELLS:
            for example in examples:
                for ending in ("lf", "crlf", "no-final-newline"):
                    text = example.replace("/absolute/path/to/project", str(self.workspace))
                    text = text.replace("CONSTRAINTS:", literal + "CONSTRAINTS:")
                    if ending == "crlf":
                        text = text.replace("\n", "\r\n")
                    elif ending == "no-final-newline":
                        text = text.rstrip("\n")
                    with self.subTest(shell=shell, ending=ending, role=text.splitlines()[1]):
                        result, jobs = self.run_wave(text, "--dry-run", shell=shell)
                        self.assertEqual(0, result.returncode, result.stderr)
                        self.assertEqual([], list(self.control.iterdir()))
                        self.assertFalse((self.root / "NEVER").exists())
                        tasks = sorted(jobs.glob("*.task"))
                        self.assertEqual(len(tasks), len(list(jobs.iterdir())))
                        for task in tasks:
                            packet = task.read_text()
                            self.assertIn(literal, packet)
                            self.assertEqual(1, packet.count("\nRETURN:"))
                            expected = "CHANGED, VERIFICATION" if "ROLE: implement" in packet else "FINDINGS, EVIDENCE"
                            self.assertIn(expected, packet)
                            self.assertEqual(0o600, task.stat().st_mode & 0o777)
                        self.assertEqual(0o700, jobs.stat().st_mode & 0o777)

    def test_invalid_later_blocks_never_launch(self) -> None:
        valid = self.manifest_text()
        cases = ["", "before\n" + valid, valid + "COMMON:\n",
                 valid + "@@ launcher=arbitrary name=b\n",
                 valid + "@@ launcher=grkc name=b\n",
                 valid + "@@ launcher=grkg name=b\n",
                 valid + "@@ launcher=CDMM name=b\n",
                 valid + "@@ launcher=agg name=../bad\n",
                 valid + "@@ launcher=agg name=A\n",
                 valid + "@@ launcher=agg name=b extra=x\n",
                 valid + "@@ name=b launcher=agg\n",
                 valid + "@@ launcher=cmd: name=b\n",
                 valid + "@@ launcher=cmd:x;y name=b\n",
                 valid + "@@ launcher=cmd:x y name=b\n",
                 valid + "RETURN: mine\n", valid + "CONTEXT: nope\n",
                 valid + "VERIFY: override\n", valid + "UNKNOWN: nope\n",
                 valid + "unindented text\n",
                 valid.replace("ROLE: review", "ROLE: write"),
                 valid.replace("WORKSPACE: /", "WORKSPACE: relative/"),
                 valid.replace(str(self.workspace), str(self.root / "missing")),
                 valid.replace("CONTEXT: agreed contract", "CONTEXT:  "),
                 valid.replace("CONSTRAINTS: bounded\n", ""),
                 valid.replace("VERIFY: trace\n", ""),
                 valid.replace("SCOPE: read only", "SCOPE: one\nSCOPE: two"),
                 valid.replace("@@ launcher=agg name=a", "@@ launcher=agg name=a\nOBJECTIVE: twice")]
        for text in cases:
            with self.subTest(text=text):
                result, jobs = self.run_wave(text)
                self.assertEqual(2, result.returncode, result.stderr)
                self.assertIn("manifest line", result.stderr)
                self.assertFalse(jobs.exists())
                self.assertEqual([], list(self.control.iterdir()))

    def test_options_and_preflight(self) -> None:
        for flags in [("--jobs", "0"), ("--jobs", "-1"), ("--jobs", "1.5"),
                      ("--jobs", ""), ("--jobs", "2", "--jobs", "3"),
                      ("--dry-run", "--dry-run"), ("--unknown",), ("--jobs",),
                      ("--wave", "wave.txt"), ("--help",), ("--timeout", "0"),
                      ("--timeout", "-1"), ("--timeout", "1.5"), ("--timeout", "1m"),
                      ("--timeout", "01"), ("--timeout", "1", "--timeout", "2")]:
            with self.subTest(flags=flags):
                result, jobs = self.run_wave(self.manifest_text(), *flags)
                self.assertEqual(2, result.returncode)
                self.assertFalse(jobs.exists())
        for cap in ("0001", "9" * 80):
            result, _ = self.run_wave(self.manifest_text(), "--jobs", cap, "--dry-run")
            self.assertEqual(0, result.returncode, result.stderr)
        result, _ = self.run_wave(self.manifest_text(), "--timeout", "2700", "--dry-run")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], list(self.control.iterdir()))

    def test_existing_targets_and_exclusive_creation(self) -> None:
        args, jobs = self.command(self.manifest_text(), "--dry-run")
        target = self.root / "existing"
        target.mkdir()
        (target / "sentinel").write_text("keep")
        for symlink in (False, True):
            if symlink:
                jobs.symlink_to(target, target_is_directory=True)
            else:
                jobs.mkdir()
                (jobs / "sentinel").write_text("keep")
            result = subprocess.run(args, cwd=self.root, env=self.env, capture_output=True, timeout=5)
            self.assertEqual(2, result.returncode)
            self.assertEqual("keep", (jobs / "sentinel").read_text())
            if symlink:
                jobs.unlink()
            else:
                shutil.rmtree(jobs)
        processes = [subprocess.Popen(args, cwd=self.root, env=self.env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(2)]
        self.assertEqual([0, 2], sorted(p.wait(timeout=5) for p in processes))
        self.assertEqual([], list(self.control.iterdir()))

    def test_prelaunch_write_failure_starts_nothing(self) -> None:
        # A private temp PATH shim fails a task write after the exclusive mkdir.
        shim = self.root / "bin"
        shim.mkdir()
        mkdir = shutil.which("mkdir")
        (shim / "mkdir").write_text(f'#!/bin/bash\n"{mkdir}" "$@" || exit\n/bin/mkdir "${{@:$#}}/b.task"\n')
        (shim / "mkdir").chmod(0o755)
        self.env["PATH"] = str(shim) + os.pathsep + self.env["PATH"]
        result, jobs = self.run_wave(self.manifest_text(("a", "b")))
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertTrue((jobs / "a.task").is_file())
        self.assertEqual([], list(self.control.iterdir()))

    def test_refill_cap_order_outputs_and_failure_drain(self) -> None:
        for shell in SHELLS:
            with self.subTest(shell=shell):
                for path in self.control.iterdir():
                    path.unlink()
                process, jobs = self.start(self.manifest_text(("a", "b", "c", "d")), "--jobs", "2", shell=shell)
                for name in ("a", "b"):
                    self.wait_path(self.control / f"{name}.pid", process)
                self.assertFalse((self.control / "c.pid").exists())
                self.release("b", 23)
                self.wait_path(self.control / "c.pid", process)
                self.assertFalse((self.control / "d.pid").exists())
                self.assertFalse((jobs / "a.status").exists())
                self.release("c")
                self.wait_path(self.control / "d.pid", process)
                self.release("d")
                self.release("a")
                self.assertEqual(1, process.wait(timeout=8))
                rows = self.rows(jobs)
                self.assertEqual(["a", "b", "c", "d"], [row["name"] for row in rows])
                self.assertEqual(["0", "23", "0", "0"], [row["exit"] for row in rows])
                for row in rows:
                    name = row["name"]
                    self.assertEqual("agg", row["launcher"])
                    self.assertEqual("STATUS: blocked\né\n".encode(), (jobs / f"{name}.out").read_bytes())
                    self.assertEqual(str(len((jobs / f"{name}.out").read_bytes())), row["out-bytes"])
                    self.assertEqual(f"diagnostic:{name}\n", (jobs / f"{name}.stderr").read_text())
                    self.assertEqual(str(self.workspace.resolve()), (self.control / f"{name}.cwd").read_text())
                    self.assertEqual(row["exit"] + "\n", (jobs / f"{name}.status").read_text())

    def test_a_refused_launcher_starts_no_more_of_its_workers(self) -> None:
        text = self.manifest_text(()) + "".join(
            f"@@ launcher={launcher} name={name}\n"
            for launcher, name in (("agg", "a"), ("kimm", "b"), ("agg", "c"), ("kimm", "d"), ("agg", "e")))
        process, jobs = self.start(text, "--jobs", "2")
        for name in ("a", "b"):
            self.wait_path(self.control / f"{name}.pid", process)
        self.assertEqual("name\tlauncher\na\tagg\nb\tkimm\nc\tagg\nd\tkimm\ne\tagg\n",
                         (jobs / "WAVE.tsv").read_text())
        (self.control / "a.class").write_text("delegate worker: failure class: rate-limited: rate limit or quota\n")
        self.release("a", 1)
        self.wait_path(self.control / "d.pid", process)
        self.release("b")
        self.release("d")
        self.assertEqual(1, process.wait(timeout=8))
        self.assertFalse((self.control / "c.pid").exists())
        self.assertFalse((self.control / "e.pid").exists())
        self.assertFalse((jobs / "c.out").exists())
        refused = "not-started (rate-limited on agg)"
        self.assertEqual(["1", "0", refused, "0", refused], [row["exit"] for row in self.rows(jobs)])
        self.assertEqual(refused + "\n", (jobs / "c.status").read_text())
        self.assertIn("agg was rate-limited (a)", (self.root / f"log-{self.sequence}").read_text())

    def test_a_refused_workers_status_write_failure_stops_dispatch(self) -> None:
        text = self.manifest_text(()) + "@@ launcher=agg name=a\n@@ launcher=agg name=b\n@@ launcher=kimm name=c\n"
        process, jobs = self.start(text, "--jobs", "1")
        self.wait_path(self.control / "a.pid", process)
        (jobs / "b.status").mkdir()
        (self.control / "a.class").write_text("delegate worker: failure class: rate-limited: rate limit or quota\n")
        self.release("a", 1)
        self.assertEqual(1, process.wait(timeout=8))
        self.assertEqual("not-started\n", (jobs / "c.status").read_text())
        self.assertFalse((jobs / "c.out").exists())

    def test_an_exhausted_account_bars_its_launchers_and_nothing_else(self) -> None:
        exhausted = "delegate worker: failure class: rate-limited: account quota exhausted on codex\n"
        cases = {
            # The primary Codex account is out: its other launchers stop; codex2 and other harnesses go on.
            "primary": ((("cdm", "a"), ("cax", "b"), ("cdm2", "c"), ("agg", "d"), ("cdm", "e")),
                        ["1", "not-started (rate-limited on account codex)", "0", "0",
                         "not-started (rate-limited on account codex)"], "cdm exhausted account codex (a)"),
            # The secondary account is its own allowance: the primary stays eligible.
            "secondary": ((("cdm2", "a"), ("cah2", "b"), ("cdm", "c")),
                          ["1", "not-started (rate-limited on account codex:codex2)", "0"],
                          "cdm2 exhausted account codex:codex2 (a)"),
            "terra": ((("ctm2", "a"), ("ctxb2", "b"), ("ctxb", "c"), ("ctmb2", "d")),
                      ["1", "not-started (rate-limited on account codex:codex2)", "0",
                       "not-started (rate-limited on account codex:codex2)"],
                      "ctm2 exhausted account codex:codex2 (a)"),
            "api key": ((("cdxk:cdx", "a"), ("cdxk:cam", "b"), ("cdm", "c"), ("cdm2", "d"), ("cdxk:cdx", "e")),
                        ["1", "not-started (rate-limited on account codex:key)", "0", "0",
                         "not-started (rate-limited on account codex:key)"],
                        "cdxk:cdx exhausted account codex:key (a)"),
            # Another harness's account line is not this account's exhaustion: only the launcher stops.
            "other harness": ((("agg", "a"), ("aggb", "b"), ("agg", "c")),
                              ["1", "0", "not-started (rate-limited on agg)"], "agg was rate-limited (a)"),
        }
        for case, (workers, statuses, message) in cases.items():
            with self.subTest(case):
                for path in self.control.iterdir():
                    path.unlink()
                (self.control / "a.class").write_text(exhausted)
                for _, name in workers:
                    self.release(name, 1 if name == "a" else 0)
                text = self.manifest_text(()) + "".join(f"@@ launcher={launcher} name={name}\n"
                                                        for launcher, name in workers)
                result, jobs = self.run_wave(text, "--jobs", "1")
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertEqual(statuses, [row["exit"] for row in self.rows(jobs)])
                self.assertIn(message, result.stderr)
                for (_, name), status in zip(workers, statuses):
                    self.assertEqual(status.startswith("not-started"), not (self.control / f"{name}.pid").exists())

    def test_a_one_model_rate_limit_bars_only_its_launcher(self) -> None:
        (self.control / "a.class").write_text("delegate worker: failure class: rate-limited: rate limit or quota\n")
        for name, code in (("a", 1), ("b", 0), ("c", 0)):
            self.release(name, code)
        text = self.manifest_text(()) + "@@ launcher=cdm name=a\n@@ launcher=cax name=b\n@@ launcher=cdm name=c\n"
        result, jobs = self.run_wave(text, "--jobs", "1")
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual(["1", "0", "not-started (rate-limited on cdm)"], [row["exit"] for row in self.rows(jobs)])
        self.assertNotIn("exhausted account", result.stderr)

    def test_a_missing_routes_table_launches_nothing(self) -> None:
        (self.scripts / "launcher-routes.tsv").unlink()
        result, jobs = self.run_wave(self.manifest_text())
        self.assertEqual(2, result.returncode)
        self.assertIn("launcher-routes.tsv", result.stderr)
        self.assertFalse(jobs.exists())
        self.assertFalse((self.control / "a.pid").exists())

    def test_other_failures_do_not_stop_a_launcher(self) -> None:
        for name, line in (("a", "delegate worker: failure class: unclassified\n"),
                           ("b", "delegate worker: failure class: quarantined: no credential\nlater line\n")):
            (self.control / f"{name}.class").write_text(line)
            self.release(name, 1)
        self.release("c")
        result, jobs = self.run_wave(self.manifest_text(("a", "b", "c")), "--jobs", "1")
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual(["1", "1", "0"], [row["exit"] for row in self.rows(jobs)])
        self.assertNotIn("will not start", result.stderr)

    def test_default_cap_is_four(self) -> None:
        names = ("a", "b", "c", "d", "e")
        process, jobs = self.start(self.manifest_text(names))
        for name in names[:4]:
            self.wait_path(self.control / f"{name}.pid", process)
        self.assertFalse((self.control / "e.pid").exists())
        self.release("c")
        self.wait_path(self.control / "e.pid", process)
        for name in names:
            self.release(name)
        self.assertEqual(0, process.wait(timeout=5))
        self.assertEqual(list(names), [row["name"] for row in self.rows(jobs)])

    def test_summary_storage_failure_is_reported(self) -> None:
        process, jobs = self.start(self.manifest_text())
        self.wait_path(self.control / "a.pid", process)
        (jobs / "SUMMARY.tsv").mkdir()
        self.release("a")
        self.assertEqual(1, process.wait(timeout=5))
        self.assertEqual("0\n", (jobs / "a.status").read_text())
        self.assertIn("evidence is incomplete", (self.root / f"log-{self.sequence}").read_text())

    def test_codex_api_key_launchers_validate_before_writing_jobs(self) -> None:
        rows = (SKILL / "scripts/launcher-routes.tsv").read_text().splitlines()[1:]
        api_launchers = next(row.split("\t")[2].split() for row in rows if row.startswith("codex\tkey\t"))
        for launcher in api_launchers:
            with self.subTest(launcher=launcher):
                text = self.manifest_text(()) + f"@@ launcher={launcher} name=a\n"
                result, jobs = self.run_wave(text, "--dry-run")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn(f"--- a ({launcher}) ---", result.stdout)
        for launcher in ("cdxk:cdx2", "cdxk:agg", "cdxk:cckx", "cdxk:arbitrary", "cdxk:"):
            with self.subTest(launcher=launcher):
                text = self.manifest_text(()) + f"@@ launcher={launcher} name=a\n"
                result, jobs = self.run_wave(text, "--dry-run")
                self.assertEqual(2, result.returncode, result.stderr)
                self.assertFalse(jobs.exists())
                self.assertEqual([], list(self.control.iterdir()))

    def test_antigravity_api_key_launchers_validate_before_writing_jobs(self) -> None:
        rows = (SKILL / "scripts/launcher-routes.tsv").read_text().splitlines()[1:]
        api_launchers = next(row.split("\t")[2].split() for row in rows if row.startswith("antigravity\tkey\t"))
        for launcher in api_launchers:
            with self.subTest(launcher=launcher):
                text = self.manifest_text(()) + f"@@ launcher={launcher} name=a\n"
                result, jobs = self.run_wave(text, "--dry-run")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn(f"--- a ({launcher}) ---", result.stdout)
        for launcher in ("agk:agnh2", "agk:agom", "agk:agoh", "agk:cdx", "agk:arbitrary", "agk:"):
            with self.subTest(launcher=launcher):
                text = self.manifest_text(()) + f"@@ launcher={launcher} name=a\n"
                result, jobs = self.run_wave(text, "--dry-run")
                self.assertEqual(2, result.returncode, result.stderr)
                self.assertFalse(jobs.exists())
                self.assertEqual([], list(self.control.iterdir()))

    def test_adapter_eligibility_list_parity(self) -> None:
        # These case alternatives are the existing adapter's public eligibility boundary.
        dispatch = (SKILL / "scripts/run-worker.sh").read_text().split('case "$launcher" in', 1)[1].split("esac", 1)[0]
        cases = re.findall(r"^  ([A-Za-z0-9|]+)\)", dispatch, re.M)
        supported = {name for case in cases for name in case.split("|")}
        self.assertEqual(set(LAUNCHERS), supported)
        reference = (SKILL / "references/wave-runner.md").read_text()
        documented = re.search(r"Eligible launchers[^:]*: `([^`]+)`", reference).group(1).split()
        self.assertEqual(supported, set(documented))
        allowed = RUNNER.read_text().split("case $launcher in", 1)[1].split("esac", 1)[0]
        self.assertEqual(supported, set(re.search(r"^\s+([A-Za-z0-9|]+)\) ;;", allowed, re.M).group(1).split("|")))
        # Every ordinary launcher and every API-key-only compound has exactly one quota route.
        worker_text = (SKILL / "scripts/run-worker.sh").read_text()
        cdxk_dispatch = worker_text.split('case "${requested_launcher#cdxk:}" in', 1)[1].split("esac", 1)[0]
        cdxk_targets = re.findall(r"^    ([A-Za-z0-9|:-]+)\)", cdxk_dispatch, re.M)[0].split("|")
        agk_dispatch = worker_text.split('case "${requested_launcher#agk:}" in', 1)[1].split("esac", 1)[0]
        agk_targets = re.findall(r"^    ([A-Za-z0-9|:-]+)\)", agk_dispatch, re.M)[0].split("|")
        api_supported = {
            "cdxk", *(f"cdxk:{target}" for target in cdxk_targets),
            "agk", *(f"agk:{target}" for target in agk_targets),
        }
        rows = (SKILL / "scripts/launcher-routes.tsv").read_text().splitlines()[1:]
        routed = [launcher for row in rows for launcher in row.split("\t")[2].split()]
        api_routed = [
            launcher for launcher in routed
            if launcher in ("cdxk", "agk") or launcher.startswith(("cdxk:", "agk:"))
        ]
        ordinary_routed = [launcher for launcher in routed if launcher not in api_routed]
        self.assertEqual(sorted(supported), sorted(ordinary_routed))
        self.assertEqual(sorted(api_supported), sorted(api_routed))

    def test_serial_and_transport_success_is_not_task_acceptance(self) -> None:
        process, jobs = self.start(self.manifest_text(("a", "b")), "--jobs", "1")
        self.wait_path(self.control / "a.pid", process)
        self.assertFalse((self.control / "b.pid").exists())
        self.release("a")
        self.wait_path(self.control / "b.pid", process)
        self.assertEqual("0\n", (jobs / "a.status").read_text())
        self.release("b")
        self.assertEqual(0, process.wait(timeout=5))
        self.assertIn("STATUS: blocked", (jobs / "b.out").read_text())

    def test_signal_cleanup_descendants_and_unrelated_process(self) -> None:
        for shell in SHELLS:
            for sig, expected in [(signal.SIGTERM, 143), (signal.SIGINT, 130)]:
                with self.subTest(shell=shell, signal=sig):
                    for path in self.control.iterdir():
                        path.unlink()
                    self.env["WAVE_DESCENDANT"] = "1"
                    sentinel = subprocess.Popen(["sleep", "30"])
                    self.addCleanup(sentinel.wait)
                    self.addCleanup(sentinel.terminate)
                    process, jobs = self.start(self.manifest_text(("a", "b")), "--jobs", "1", shell=shell)
                    self.wait_path(self.control / "a.child", process)
                    pid = int((self.control / "a.pid").read_text())
                    child = int((self.control / "a.child").read_text())
                    os.kill(process.pid, sig)
                    self.assertEqual(expected, process.wait(timeout=9))
                    self.assertIsNone(sentinel.poll())
                    self.assertFalse((self.control / "b.pid").exists())
                    for owned in (pid, child):
                        with self.assertRaises(ProcessLookupError):
                            os.kill(owned, 0)
                    rows = self.rows(jobs)
                    self.assertTrue(rows[0]["exit"].isdigit(), rows)
                    self.assertEqual("not-started", rows[1]["exit"])
                    self.assertEqual("0", rows[1]["out-bytes"])
                    log = (self.root / f"log-{self.sequence}").read_text()
                    self.assertNotIn("live process group", log)
                    sentinel.terminate()
                    sentinel.wait(timeout=2)

    def test_timeout_stops_only_the_late_worker(self) -> None:
        for shell in SHELLS:
            with self.subTest(shell=shell):
                for path in self.control.iterdir():
                    path.unlink()
                self.release("b")
                started = time.monotonic()
                result, jobs = self.run_wave(self.manifest_text(("a", "b")), "--timeout", "2", shell=shell)
                self.assertLess(time.monotonic() - started, 5, "SIGTERM alone should stop a")
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertEqual(["timeout", "0"], [row["exit"] for row in self.rows(jobs)])
                self.assertIn("a exceeded 2s", result.stderr)
                self.assertNotIn("b exceeded", result.stderr)
                self.assertNotIn("live process group", result.stderr)
                with self.assertRaises(ProcessLookupError):
                    os.kill(int((self.control / "a.pid").read_text()), 0)

    def test_timeout_kills_a_group_that_ignores_sigterm(self) -> None:
        self.env["WAVE_DESCENDANT"] = "1"
        result, jobs = self.run_wave(self.manifest_text(), "--timeout", "1")
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual("timeout", self.rows(jobs)[0]["exit"])
        self.assertEqual("timeout\n", (jobs / "a.status").read_text())
        self.assertNotIn("unconfirmed", result.stderr)
        for owned in ("a.pid", "a.child"):
            with self.assertRaises(ProcessLookupError):
                os.kill(int((self.control / owned).read_text()), 0)

    def test_returned_worker_leftovers_are_stopped_without_failing_peers(self) -> None:
        # A Devin worker can return while its orphaned MCP server is still exiting.
        self.env["WAVE_LEFTOVER"] = "1"
        for shell in SHELLS:
            for code in (0, 3):
                with self.subTest(shell=shell, code=code):
                    for path in self.control.iterdir():
                        path.unlink()
                    self.release("a", code)
                    self.release("b")
                    result, jobs = self.run_wave(self.manifest_text(("a", "b")), "--jobs", "1", shell=shell)
                    self.assertEqual(1 if code else 0, result.returncode, result.stderr)
                    self.assertEqual([str(code), "0"], [row["exit"] for row in self.rows(jobs)])
                    self.assertIn("a returned with live process group", result.stderr)
                    self.assertIn("stopping its remaining processes", result.stderr)
                    for owned in ("a.child", "b.child"):
                        with self.assertRaises(ProcessLookupError):
                            os.kill(int((self.control / owned).read_text()), 0)

    def test_returned_worker_leftovers_ignoring_sigterm_are_killed(self) -> None:
        self.env["WAVE_DESCENDANT"] = "1"
        for shell in SHELLS:
            with self.subTest(shell=shell):
                for path in self.control.iterdir():
                    path.unlink()
                self.release("a")
                result, jobs = self.run_wave(self.manifest_text(), shell=shell)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("0\n", (jobs / "a.status").read_text())
                self.assertNotIn("unconfirmed", result.stderr)
                with self.assertRaises(ProcessLookupError):
                    os.kill(int((self.control / "a.child").read_text()), 0)

    def test_a_late_pass_sends_sigkill_before_failing_a_group(self) -> None:
        # SECONDS is wall-clock, so sleep or load can make one pass jump past the
        # whole stop window; 3.5-second passes go from second 3-4 straight to 7.
        bash_env = self.root / "slow-pass.bash"
        bash_env.write_text("sleep() { command sleep 3.5; }\n")
        self.env["BASH_ENV"] = str(bash_env)
        self.env["WAVE_DESCENDANT"] = "1"
        self.release("a")
        args, jobs = self.command(self.manifest_text())
        result = subprocess.run(args, cwd=self.root, env=self.env, text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("0\n", (jobs / "a.status").read_text())
        self.assertNotIn("survived SIGKILL", result.stderr)
        with self.assertRaises(ProcessLookupError):
            os.kill(int((self.control / "a.child").read_text()), 0)

    def test_leftovers_surviving_sigkill_fail_the_runner_as_unconfirmed(self) -> None:
        bash_env = self.root / "kill-failure.bash"
        bash_env.write_text('kill() { case "$1" in -KILL) return 1;; esac; builtin kill "$@"; }\n')
        self.env["BASH_ENV"] = str(bash_env)
        self.env["WAVE_DESCENDANT"] = "1"
        self.release("a")
        process, jobs = self.start(self.manifest_text())
        self.assertEqual(1, process.wait(timeout=25))
        log = (self.root / f"log-{self.sequence}").read_text()
        self.assertIn("a process group", log)
        self.assertIn("survived SIGKILL", log)
        self.assertIn("inspect before reusing scope", log)
        self.assertEqual("unconfirmed\n", (jobs / "a.status").read_text())

    def test_postlaunch_artifact_failure_cleans_children(self) -> None:
        process, jobs = self.start(self.manifest_text(("a", "b", "c")), "--jobs", "2")
        for name in ("a", "b"):
            self.wait_path(self.control / f"{name}.pid", process)
        (jobs / "a.status").mkdir()
        self.release("a")
        self.assertEqual(1, process.wait(timeout=8))
        self.assertFalse((self.control / "c.pid").exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(int((self.control / "b.pid").read_text()), 0)
        self.assertEqual("not-started", self.rows(jobs)[2]["exit"])

    def test_unconfirmed_cleanup_reports_scope_and_preserves_finished_status(self) -> None:
        # Model a host refusing group termination without weakening production code.
        bash_env = self.root / "kill-failure.bash"
        bash_env.write_text('kill() { case "$1" in -TERM|-KILL) return 1;; esac; builtin kill "$@"; }\n')
        self.env["BASH_ENV"] = str(bash_env)
        self.release("finished")
        process, jobs = self.start(self.manifest_text(("finished", "a", "b")), "--jobs", "1")
        self.wait_path(self.control / "a.pid", process)
        process.terminate()
        self.assertEqual(143, process.wait(timeout=9))
        rows = self.rows(jobs)
        self.assertEqual(["0", "unconfirmed", "not-started"], [row["exit"] for row in rows])
        self.assertEqual("0\n", (jobs / "finished.status").read_text())
        self.assertFalse((self.control / "b.pid").exists())
        pid = int((self.control / "a.pid").read_text())
        os.kill(pid, 0)
        log = (self.root / f"log-{self.sequence}").read_text()
        self.assertIn(f"pid/pgid={pid}", log)
        self.assertIn("inspect before reusing scope", log)

    def test_dispatch_output_failure_stops_and_cleans_peers(self) -> None:
        process, jobs = self.start(self.manifest_text(("a", "b", "c")), "--jobs", "2")
        for name in ("a", "b"):
            self.wait_path(self.control / f"{name}.pid", process)
        (jobs / "c.out").mkdir()
        self.release("a")
        self.assertEqual(1, process.wait(timeout=8))
        self.assertFalse((self.control / "c.pid").exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(int((self.control / "b.pid").read_text()), 0)
        self.assertEqual("not-started", self.rows(jobs)[2]["exit"])

    def test_real_adapter_allowlist_aliases_and_failure_suppression(self) -> None:
        shutil.copy2(SKILL / "scripts/run-worker.sh", self.adapter)
        shutil.copy2(SKILL / "scripts/refusals.py", self.scripts / "refusals.py")
        # Devin launchers need a session database; test_devin_worker.py covers them.
        launchers = [launcher for launcher in LAUNCHERS if launcher not in DEVIN_LAUNCHERS]
        wrappers = self.root / "wrappers"
        lines = []
        for launcher in launchers:
            if launcher in (
                "clm", "clmb", "clm2", "clmb2",
                "cdx", "cdxb", "cdx2", "cdxb2",
                "cdm", "cdmb", "cdm2", "cdmb2",
            ):
                continue
            if launcher.startswith("kim"):
                output = '{"role":"assistant","content":"FINAL"}'
            elif launcher.startswith("gr"):
                output = '{"text":"FINAL","thought":"PRIVATE"}'
            elif launcher in ("ocs", "ommp", "ocargh", "ocmm26", "ochy4flash", "oclongcat", "ociceman"):
                output = '{"type":"text","part":{"messageID":"m","text":"FINAL"}}'
            elif launcher in ("cmg", "cmds", "cmm26p", "cms", "cmdglyph", "cmdflint"):
                output = '{"type":"event","event":{"type":"text_delta","text":"PRIVATE"}}\n{"type":"result","subtype":"success","finalText":"FINAL"}'
            elif launcher.startswith(("cs", "cc", "ch")):
                output = '[{"type":"assistant","text":"PRIVATE"},{"type":"result","is_error":false,"result":"FINAL"}]'
            else:
                output = 'FINAL'
            output = output.replace("FINAL", f"FINAL:{launcher}")
            if launcher in (
                "ctx", "ctxb", "ctx2", "ctxb2", "ctm", "ctmb", "ctm2", "ctmb2",
                "cam", "camb", "cax", "caxb", "camm", "cammb", "cah", "cahb",
                "cam2", "camb2", "cax2", "caxb2", "camm2", "cammb2", "cah2", "cahb2",
                "cdmM", "cdxX", "camM", "caxX", "cdmM2", "cdxX2", "camM2", "caxX2",
                "agg", "aggbs", "aggb", "aggbbs", "agom", "agoh", "argm", "argh",
                "aghh", "aghhb", "aghx", "aghxb",
                "agcm", "agcmb", "agch", "agchb",
                "agnm", "agnmb", "agnh", "agnhb", "agnx", "agnxb",
            ):
                lines.append(f'{launcher}() {{ [[ $# -eq 2 && "$1" == -p ]] || return 9; '
                             f"printf '%s\\n' '{output}'; }}")
                continue
            lines.append(f"{launcher}() {{ printf '%s\\n' '{output}'; }}")
        # An exact Command Code model goes through am, which resolves and revalidates it.
        lines.append("am() { [[ $1 == cmd:vendor/model-1.5 && $2 == -- && $3 == --no-auto-update ]] || return 9; "
                     "printf '%s\\n' '{\"type\":\"result\",\"subtype\":\"success\",\"finalText\":\"FINAL:am\"}'; }")
        wrappers.write_text("\n".join(lines) + "\n")
        self.env["BASH_AGENTS_FILE"] = str(wrappers)
        names = {launcher: f"worker-{index}" for index, launcher in enumerate(launchers)}
        text = self.manifest_text().split("@@")[0] + "".join(
            f"@@ launcher={launcher} name={names[launcher]}\n" for launcher in launchers)
        text += "@@ launcher=cmd:vendor/model-1.5 name=routed\n"
        result, jobs = self.run_wave(text)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(len(launchers) + 1, len(self.rows(jobs)))
        self.assertEqual("FINAL:am\n", (jobs / "routed.out").read_text())
        remapped = {"clm": "clme", "clmb": "clmbe", "clm2": "clme2", "clmb2": "clmbe2",
                    "cdx": "cdxe", "cdxb": "cdxbe", "cdx2": "cdxe2", "cdxb2": "cdxbe2",
                    "cdm": "cdme", "cdmb": "cdmbe", "cdm2": "cdme2", "cdmb2": "cdmbe2"}
        for launcher in launchers:
            expected = remapped.get(launcher, launcher)
            self.assertEqual(f"FINAL:{expected}\n", (jobs / f"{names[launcher]}.out").read_text())
        wrappers.write_text('agg() { echo PRIVATE; echo fail >&2; return 19; }\n')
        result, jobs = self.run_wave(self.manifest_text())
        self.assertEqual(1, result.returncode)
        self.assertEqual(b"", (jobs / "a.out").read_bytes())
        self.assertNotIn("PRIVATE", (jobs / "a.stderr").read_text())
        self.assertTrue((jobs / "a.stderr").read_text().endswith("\ndelegate worker: failure class: unclassified\n"))
        self.assertEqual("19", self.rows(jobs)[0]["exit"])
        # The 10-24 Codex quota line: run-worker.sh classifies it, and the wave stops using the launcher.
        # The diagnostics end without a newline, and the class line still gets a line of its own. On agg,
        # an Antigravity launcher, Codex's account line is a rate limit like any other (it counts as an account's
        # only from a Codex launcher), so it bars only agg, never the Antigravity account.
        wrappers.write_text("agg() { echo 'ERROR: You’ve hit your usage limit. Upgrade to Pro' >&2; "
                            "printf 'tokens used\\n68,344' >&2; return 1; }\n")
        result, jobs = self.run_wave(self.manifest_text(("a", "b")), "--jobs", "1")
        self.assertEqual(1, result.returncode)
        self.assertTrue((jobs / "a.stderr").read_text().endswith(
            "\ndelegate worker: failure class: rate-limited: rate limit or quota\n"))
        self.assertEqual(["1", "not-started (rate-limited on agg)"], [row["exit"] for row in self.rows(jobs)])

    def test_removed_launchers_are_rejected_even_if_defined(self) -> None:
        wrappers = self.root / "wrappers"
        retired = ("grkc", "grkg", "ocsf", "cmm31", "ommm31z", "ommm31g")
        wrappers.write_text("".join(f'{launcher}() {{ echo WRONG; }}\n' for launcher in retired))
        for launcher in retired:
            with self.subTest(launcher=launcher):
                result = subprocess.run(
                    ["/bin/bash", str(SKILL / "scripts/run-worker.sh"), launcher],
                    input="TASK", text=True, capture_output=True,
                    env=dict(self.env, BASH_AGENTS_FILE=str(wrappers)))
                self.assertNotEqual(0, result.returncode)
                self.assertEqual("", result.stdout)
                self.assertIn(f"unsupported launcher: {launcher}", result.stderr)
                self.assertNotIn("failure class", result.stderr)
                text = self.manifest_text().replace("launcher=agg", f"launcher={launcher}")
                result, jobs = self.run_wave(text, "--dry-run")
                self.assertNotEqual(0, result.returncode)
                self.assertIn(f"unsupported launcher: {launcher}", result.stderr)
                self.assertFalse(jobs.exists())


if __name__ == "__main__":
    unittest.main()
