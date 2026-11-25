from __future__ import annotations

import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture_run.py"


class CaptureRunTests(unittest.TestCase):
    def build_argv(
        self,
        *,
        records: Path,
        cwd: Path,
        command: list[str],
        timeout: float | None = None,
        artifacts: tuple[str, ...] = (),
    ) -> list[str]:
        argv = [
            sys.executable,
            str(SCRIPT),
            "--records-dir",
            str(records),
            "--cwd",
            str(cwd),
            "--label",
            "focused probe",
            "--prediction",
            "the command emits the predicted observation",
            "--success-condition",
            "the expected output and artifact are inspectable",
        ]
        if timeout is not None:
            argv.extend(["--timeout", str(timeout)])
        for artifact in artifacts:
            argv.extend(["--artifact", artifact])
        argv.extend(["--", *command])
        return argv

    def invoke(
        self,
        *,
        records: Path,
        cwd: Path,
        command: list[str],
        timeout: float | None = None,
        artifacts: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        argv = self.build_argv(
            records=records,
            cwd=cwd,
            command=command,
            timeout=timeout,
            artifacts=artifacts,
        )
        return subprocess.run(argv, capture_output=True, text=True, check=False)

    def only_receipt(self, records: Path) -> tuple[Path, dict[str, object]]:
        run_dirs = list(records.iterdir())
        self.assertEqual(1, len(run_dirs))
        receipt_path = run_dirs[0] / "receipt.json"
        self.assertTrue(receipt_path.is_file())
        return run_dirs[0], json.loads(receipt_path.read_text())

    def test_success_streams_output_and_hashes_named_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            cwd = base / "work"
            cwd.mkdir()
            records = base / "records"
            command = [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    "Path('result.txt').write_text('accepted'); "
                    "print('metric=3')"
                ),
            ]

            result = self.invoke(
                records=records,
                cwd=cwd,
                command=command,
                artifacts=("result.txt",),
            )

            self.assertEqual(0, result.returncode, result.stderr)
            run_dir, receipt = self.only_receipt(records)
            self.assertEqual("completed", receipt["status"])
            self.assertEqual(0, receipt["exit_code"])
            self.assertEqual(command, receipt["command"])
            self.assertEqual("metric=3\n", (run_dir / "stdout.txt").read_text())
            self.assertEqual("", (run_dir / "stderr.txt").read_text())
            artifact = receipt["artifacts"][0]
            self.assertEqual("file", artifact["kind"])
            expected_hash = "sha256:" + hashlib.sha256(b"accepted").hexdigest()
            self.assertEqual(expected_hash, artifact["sha256"])
            self.assertTrue((run_dir / "started.json").is_file())

    def test_nonzero_child_exit_is_preserved_in_failed_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            cwd = base / "work"
            cwd.mkdir()
            records = base / "records"

            result = self.invoke(
                records=records,
                cwd=cwd,
                command=[sys.executable, "-c", "import sys; sys.exit(7)"],
            )

            self.assertEqual(7, result.returncode)
            _, receipt = self.only_receipt(records)
            self.assertEqual("failed", receipt["status"])
            self.assertEqual(7, receipt["exit_code"])
            self.assertFalse(receipt["timed_out"])

    def test_timeout_terminates_owned_process_and_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            cwd = base / "work"
            cwd.mkdir()
            records = base / "records"

            result = self.invoke(
                records=records,
                cwd=cwd,
                command=[sys.executable, "-c", "import time; time.sleep(10)"],
                timeout=0.05,
            )

            self.assertEqual(124, result.returncode, result.stderr)
            _, receipt = self.only_receipt(records)
            self.assertEqual("timed-out", receipt["status"])
            self.assertTrue(receipt["timed_out"])
            self.assertIsNotNone(receipt["exit_code"])

    @unittest.skipUnless(hasattr(signal, "SIGINT"), "SIGINT is unavailable")
    def test_interrupt_terminates_owned_process_and_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            cwd = base / "work"
            cwd.mkdir()
            records = base / "records"
            child_started = cwd / "child-started.txt"
            child_finished = cwd / "child-finished.txt"
            command = [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; import time; "
                    "Path('child-started.txt').touch(); "
                    "time.sleep(10); Path('child-finished.txt').touch()"
                ),
            ]
            process = subprocess.Popen(
                self.build_argv(records=records, cwd=cwd, command=command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.monotonic() + 5
            while not child_started.exists() and process.poll() is None:
                if time.monotonic() >= deadline:
                    process.kill()
                    self.fail("child did not reach the test barrier")
                time.sleep(0.01)

            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=5)

            self.assertEqual(130, process.returncode, stderr)
            self.assertIn("receipt:", stdout)
            _, receipt = self.only_receipt(records)
            self.assertEqual("interrupted", receipt["status"])
            self.assertTrue(receipt["interrupted"])
            self.assertFalse(child_finished.exists())

    def test_spawn_error_writes_receipt_without_retrying(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            cwd = base / "work"
            cwd.mkdir()
            records = base / "records"

            result = self.invoke(
                records=records,
                cwd=cwd,
                command=["definitely-not-a-real-command-evidence-loop"],
            )

            self.assertEqual(125, result.returncode)
            _, receipt = self.only_receipt(records)
            self.assertEqual("spawn-error", receipt["status"])
            self.assertIsNone(receipt["exit_code"])
            self.assertIn("FileNotFoundError", receipt["error"])

    def test_escaping_artifact_is_rejected_before_child_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            cwd = base / "work"
            cwd.mkdir()
            records = base / "records"
            marker = cwd / "should-not-exist.txt"

            result = self.invoke(
                records=records,
                cwd=cwd,
                command=[
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('should-not-exist.txt').touch()",
                ],
                artifacts=("../outside.txt",),
            )

            self.assertEqual(2, result.returncode)
            self.assertIn("artifact path escapes --cwd", result.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse(records.exists())


if __name__ == "__main__":
    unittest.main()
