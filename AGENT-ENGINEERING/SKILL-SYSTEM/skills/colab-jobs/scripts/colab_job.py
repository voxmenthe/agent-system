#!/usr/bin/env python3
"""Set up and run work on a Google Colab runtime through the official `colab` CLI.

Commands: doctor, up, push, install, run, wait, logs, jobs, stats, pull, down.
Every command prints KEY: value lines; a failure prints ERROR: and NEXT: lines
and exits with a code from the table in SKILL.md. Standard library only.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True  # the installed skill is hash-tracked: no __pycache__ beside it
from archives import UnsafeArchive, make_archive, safe_extract  # noqa: E402
from log_view import LogPrinter  # noqa: E402
from monitor import format_jobs, format_stats, grep_pattern  # noqa: E402

HERE = Path(__file__).resolve().parent
VM_OPS = HERE / "vm_ops.py"
SCRIPT = "python3 " + str(Path(__file__).resolve())
MARK = "@@colab-jobs@@"
STATE = Path.home() / ".codex" / "state" / "colab-jobs"
LEASES = STATE / "leases"

EXIT_JOB_FAILED = 1
EXIT_USAGE = 2
EXIT_SIGNIN = 10
EXIT_NO_CLI = 11
EXIT_REFUSED = 12
EXIT_LOST = 13
EXIT_NAME_TAKEN = 14
EXIT_CLI_FAILED = 15
EXIT_STILL_RUNNING = 75

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
JOB_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
SESSION_LINE = re.compile(
    r"^\[(?P<name>[^\]]+)\] (?P<endpoint>\S+) \| Hardware: (?P<hardware>[^|]+?) "
    r"\| Shape: (?P<shape>[^|]+?) \| Variant: (?P<variant>\S+)"
)
SECRETS = (
    (re.compile(r"(colab-runtime-proxy-token=)[^&\s'\"]+"), r"\1<redacted>"),
    (re.compile(r"\bya29\.[A-Za-z0-9._-]+"), "<redacted>"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+"), "<redacted>"),
)
# the CLI prints this (typer's traceback) when the kernel websocket drops, then may hang on exit
EXCEPTION_LINE = re.compile(r"^[\w.]*(Error|Exception|Timeout)\b:? .*$", re.M)
LOST = re.compile(r"^RuntimeError: (Connection was lost|Kernel \w+ before the code finished)", re.M)
SIGNIN_MARKERS = ("To authorize colab-cli", "Enter the authorization code", "No valid default credentials")
FRAMEWORKS = {"torch", "torchvision", "torchaudio", "jax", "jaxlib", "tensorflow"}
PROBE_PACKAGES = ["torch", "transformers", "datasets", "accelerate", "peft", "trl", "bitsandbytes", "torchao"]
DEFAULT_WAIT = 100
DEFAULT_MAX_MB = 200
SIGNIN_NEXT = ("ask the user to run `colab whoami` in their own terminal and finish the Google "
               "sign-in; do not open the sign-in URL yourself")
RETRY_NEXT = "retry once; if it fails again, stop and report this message"


class ColabError(Exception):
    def __init__(self, code: int, message: str, next_step: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.next_step = next_step


# ---- the colab CLI edge ---------------------------------------------------

def colab_bin() -> str:
    path = shutil.which("colab")
    if path is None:
        raise ColabError(EXIT_NO_CLI, "the official `colab` CLI is not on PATH",
                         "uv tool install --python 3.12 google-colab-cli   then run doctor again")
    return path


def redact(text: str) -> str:
    for pattern, replacement in SECRETS:
        text = pattern.sub(replacement, text)
    return text


def tail(text: str, lines: int = 12) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def read_all(f) -> str:
    f.seek(0)
    return f.read().decode("utf-8", "replace")


def call_colab(args: list[str], *, stdin_text: str | None = None, timeout: float = 120) -> subprocess.CompletedProcess:
    """Run one `colab` command with stdin closed (or fed), so a sign-in prompt fails instead of hanging.

    After printing a lost kernel connection the CLI can hang on exit instead of
    quitting, so that line ends the call at once rather than at `timeout`."""
    with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
        proc = subprocess.Popen([colab_bin(), *args], stdout=out_f, stderr=err_f,
                                stdin=subprocess.DEVNULL if stdin_text is None else subprocess.PIPE)
        if stdin_text is not None:
            with contextlib.suppress(BrokenPipeError), proc.stdin:  # the CLI may exit before reading it
                proc.stdin.write(stdin_text.encode())
        deadline, lost = time.monotonic() + timeout, None
        while proc.poll() is None and time.monotonic() < deadline:
            lost = LOST.search(read_all(err_f)) or LOST.search(read_all(out_f))
            if lost:
                break
            try:
                proc.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                pass
        hung = proc.poll() is None
        if hung:
            proc.kill()
            proc.wait()
        out, err = redact(read_all(out_f)), redact(read_all(err_f))
    if any(marker in out + err for marker in SIGNIN_MARKERS):
        raise ColabError(EXIT_SIGNIN, "Colab is not signed in, or the sign-in expired", SIGNIN_NEXT)
    if hung:
        why = ("lost its connection to the VM (%s)" % lost.group(1) if lost
               else "did not finish within %ds%s" % (timeout, (": " + tail(out + err, 3)) if (out + err).strip() else ""))
        raise ColabError(EXIT_CLI_FAILED, "`colab %s` %s" % (args[0], why), RETRY_NEXT)
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)


def check_session(name: str, done: subprocess.CompletedProcess) -> None:
    text = done.stdout + done.stderr
    if "Session '%s' not found" % name in text or "appears to be lost" in text:
        raise ColabError(EXIT_LOST, "session %r is not running (stopped, expired, or never created)" % name,
                         "%s doctor   to see your sessions; then %s up NEW-NAME" % (SCRIPT, SCRIPT))


def with_retries(attempts: int, call):
    """Run call(); a transport failure (exit 15) is retried. Colab connections drop now
    and then while the next call works, but a lost reply can mean the call already ran,
    so only calls that are safe to repeat pass attempts > 1."""
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except ColabError as exc:
            if exc.code != EXIT_CLI_FAILED or attempt == attempts:
                raise
            print("[colab-jobs] %s; retrying automatically (%d of %d), nothing to do" % (exc, attempt + 1, attempts),
                  flush=True)
            time.sleep(5)


def failure(text: str) -> str:
    """The CLI's own error line (its tracebacks are boxed), else the last lines of its output."""
    found = [m.group(0).strip() for m in EXCEPTION_LINE.finditer(text)]
    return found[-1] if found else tail(text, 3)


def vm(name: str, op: str, args: dict, timeout: float = 120, attempts: int = 1) -> dict:
    """Run one vm_ops operation in the session's kernel and return its JSON result. Ops that
    are safe to repeat retry: probe, prepare, poll, remove, pack (a new archive each time),
    start (it recognizes its token) and unpack (it keeps a receipt)."""
    code = VM_OPS.read_text() + "\nrun_op(%r, json.loads(%r))\n" % (op, json.dumps(args))

    def once() -> dict:
        done = call_colab(["exec", "-s", name, "--timeout", "0"], stdin_text=code, timeout=timeout)
        check_session(name, done)
        marked = [line for line in done.stdout.splitlines() if line.startswith(MARK)]
        if not marked:
            raise ColabError(EXIT_CLI_FAILED, "no answer from the VM (%s): %s" % (
                op, failure(done.stderr + done.stdout)), RETRY_NEXT)
        return json.loads(marked[-1][len(MARK):])

    result = with_retries(attempts, once)
    if result.get("error") == "vm_error":
        raise ColabError(EXIT_CLI_FAILED, "the VM reported: %s" % result["detail"], RETRY_NEXT)
    return result


def transfer(name: str, verb: str, source: str, target: str, size: int) -> None:
    """Upload or download one file; both overwrite their target, so a retry is safe."""
    def once() -> None:
        done = call_colab([verb, "-s", name, source, target], timeout=120 + 5 * size // 2**20)
        check_session(name, done)
        if done.returncode != 0:
            raise ColabError(EXIT_CLI_FAILED, "%s failed: %s" % (verb, failure(done.stdout + done.stderr)), RETRY_NEXT)
    with_retries(3, once)


def fetch_sessions() -> list[dict]:
    def once() -> list[dict]:
        done = call_colab(["sessions"], timeout=60)
        if done.returncode != 0:
            raise ColabError(EXIT_CLI_FAILED, "could not list sessions: " + failure(done.stdout + done.stderr),
                             RETRY_NEXT)
        return [m.groupdict() for m in map(SESSION_LINE.match, done.stdout.splitlines()) if m]
    return with_retries(3, once)


def fetch_usage() -> dict[str, str]:
    done = call_colab(["usage"], timeout=90)
    return dict(re.findall(r"^(Current balance|Usage rate|Active assignments): (.*)$", done.stdout, re.M))


# ---- leases: a forgotten session stops itself --------------------------------

def lease_path(name: str) -> Path:
    return LEASES / ("%s.json" % name)


def read_lease(name: str) -> dict | None:
    try:
        return json.loads(lease_path(name).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value))
    os.replace(tmp, path)


def start_lease(name: str, hours: float) -> dict:
    lease = {"name": name, "token": secrets.token_hex(8), "hours": hours, "deadline": time.time() + hours * 3600}
    write_json(lease_path(name), lease)
    with open(STATE / "watchdog.log", "a") as log:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_watchdog", name, lease["token"]],
                         start_new_session=True, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    return lease


def end_lease(name: str) -> None:
    lease_path(name).unlink(missing_ok=True)


def cmd_watchdog(a: argparse.Namespace) -> int:
    while True:
        lease = read_lease(a.name)
        if lease is None or lease["token"] != a.token:
            return 0
        left = lease["deadline"] - time.time()
        if left <= 0:
            break
        time.sleep(min(30.0, left))
    try:
        done = call_colab(["stop", "-s", a.name], timeout=180)
        outcome = (done.stdout + done.stderr).strip()
    except ColabError as exc:
        outcome = "stop failed: %s" % exc
    lease.update(expired_at=time.time(), stop_output=outcome)
    write_json(STATE / "expired" / ("%s-%d.json" % (a.name, time.time())), lease)
    if (read_lease(a.name) or {}).get("token") == a.token:
        end_lease(a.name)
    print("%s lease expired for %s: %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), a.name, outcome), flush=True)
    return 0


def describe_lease(lease: dict | None) -> str:
    if lease is None:
        return "no colab-jobs lease (started some other way)"
    left = lease["deadline"] - time.time()
    if left < 0:
        return "lease overdue by %dm: run down" % (-left // 60)
    return "auto-stops in %dm" % (left // 60 + 1)


# ---- jobs --------------------------------------------------------------------

def new_job_id(prefix: str) -> str:
    return "%s-%s-%s" % (prefix, time.strftime("%H%M%S"), secrets.token_hex(2))


def start_job(name: str, job: str, *, kind: str, argv: list[str], cwd: str, install: dict | None = None) -> None:
    if not JOB_RE.match(job):
        raise ColabError(EXIT_USAGE, "job name %r: use letters, digits, - _ . (max 64)" % job, "omit --job")
    print("JOB: %s" % job, flush=True)
    try:
        # the token lets a retry recognize a start whose reply was lost, so the job never runs twice
        result = vm(name, "start", {"job": job, "kind": kind, "argv": argv, "cwd": cwd, "install": install,
                                    "token": secrets.token_hex(8), "source": VM_OPS.read_text()},
                    timeout=45, attempts=3)
    except ColabError as exc:
        if exc.code != EXIT_CLI_FAILED:
            raise
        raise ColabError(exc.code, "%s; the job may or may not have started" % exc,
                         "%s logs %s %s   shows whether it started; do not start it again until that "
                         "says no job named %s" % (SCRIPT, name, job, job))
    if result.get("error") == "job_exists":
        raise ColabError(EXIT_USAGE, "a job named %s already exists on %s" % (job, name), "omit --job or pick another name")
    if result.get("repeat"):
        print("[colab-jobs] the earlier attempt had started it; it runs once", flush=True)
    print("STARTED: %s   (in %s; it keeps running if this command stops)" % (shlex.join(argv), result["cwd"]), flush=True)


def poll(name: str, job: str, offset: int, grep: str | None = None) -> dict:
    """Read a job's state and log from `offset` (or the whole log's lines matching `grep`).
    Polls only read, so a transport failure is retried."""
    result = vm(name, "poll", {"job": job, "offset": offset, "limit": 262144, "grep": grep}, timeout=45, attempts=4)
    if result.get("error") == "no_jobs":
        raise ColabError(EXIT_USAGE, "no jobs have run on %s yet" % name, "%s run %s -- COMMAND" % (SCRIPT, name))
    if result.get("error") == "no_such_job":
        raise ColabError(EXIT_USAGE, "no job named %s on %s" % (job, name), "omit JOB to use the latest job")
    return result


def follow(name: str, job: str, *, wait: float, tail_lines: int | None = None) -> int:
    printer = LogPrinter()
    deadline = time.monotonic() + wait
    offset, first, pause = (-16384 if tail_lines else 0), True, 1.0
    while True:
        result = poll(name, job, offset)
        job = result["job"]
        if first and tail_lines:
            printer.feed(result["text"], keep_last=tail_lines, drop_first=result["offset"] > 0)
        else:
            printer.feed(result["text"])
        first, offset = False, result["next"]
        if offset < result["size"]:
            continue
        if result["state"] != "running":
            printer.close()
            return report_end(name, job, result)
        left = deadline - time.monotonic()
        if left <= 0:
            printer.close()
            print("STATE: running (%ds so far)" % result["elapsed"])
            raise ColabError(EXIT_STILL_RUNNING, "job %s is still running on %s" % (job, name),
                             "%s wait %s %s" % (SCRIPT, name, job))
        time.sleep(min(pause, left))
        pause = min(pause * 1.6, 15.0)


def report_end(name: str, job: str, result: dict) -> int:
    print("STATE: %s" % result["state"])
    if "exit_code" in result:
        print("EXIT_CODE: %d" % result["exit_code"])
    print("ELAPSED: %ds" % result["elapsed"])
    if result["state"] == "succeeded":
        return 0
    read_log = "%s logs %s %s --tail 100" % (SCRIPT, name, job)
    if result["state"] == "lost":
        raise ColabError(EXIT_JOB_FAILED, "job %s stopped without an exit record: its runner was killed "
                         "(the VM may have run out of memory or restarted)" % job, read_log)
    code = result["exit_code"]
    why = "exit code %d" % code
    if code < 0:
        why = "signal %d" % -code + (" (usually out of memory: use a smaller model, batch or sequence length)"
                                     if code == -9 else "")
    raise ColabError(EXIT_JOB_FAILED, "job %s failed with %s" % (job, why),
                     "read the log above (or %s), fix the cause, then run again" % read_log)


# ---- commands ------------------------------------------------------------------

def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return "%s***@%s" % (local[:1], domain)


def cmd_doctor(a: argparse.Namespace) -> int:
    path = colab_bin()
    print("CLI: %s (%s)" % (path, call_colab(["version"]).stdout.strip()))
    who = call_colab(["whoami"], timeout=90)
    email = re.search(r"^Email:\s*(\S+)", who.stdout, re.M)
    if who.returncode != 0 or not email:
        raise ColabError(EXIT_CLI_FAILED, "could not read the signed-in account: " + tail(who.stdout + who.stderr),
                         RETRY_NEXT)
    print("SIGNED_IN: %s" % mask_email(email.group(1)))
    usage = fetch_usage()
    print("BALANCE: %s" % usage.get("Current balance", "unknown"))
    print("USAGE_RATE: %s (account-wide, all sessions)" % usage.get("Usage rate", "unknown"))
    sessions = fetch_sessions()
    for s in sessions:
        if s["name"] == "?":
            note = "ORPHAN: this machine has no record of it; only the Colab web UI can stop it (Runtime > Manage sessions)"
        else:
            note = describe_lease(read_lease(s["name"]))
        print("SESSION: %s | %s %s | %s" % (s["name"], s["hardware"], s["shape"], note))
    if not sessions:
        print("SESSIONS: none")
    print("READY: signed in. doctor never allocates a runtime.")
    return 0


def cmd_up(a: argparse.Namespace) -> int:
    if not NAME_RE.match(a.name):
        raise ColabError(EXIT_USAGE, "session name %r: use 3-40 lowercase letters, digits and -" % a.name,
                         "for example: %s up exp-1" % SCRIPT)
    if a.gpu and a.tpu:
        raise ColabError(EXIT_USAGE, "choose --gpu or --tpu, not both", "omit both for the cheapest runtime (CPU)")
    if not 0 < a.hours <= 12:
        raise ColabError(EXIT_USAGE, "--hours must be more than 0 and at most 12", "for example --hours 2")
    if any(s["name"] == a.name for s in fetch_sessions()):
        raise ColabError(EXIT_NAME_TAKEN, "a session named %s is already running" % a.name,
                         "use it, or pick another name for a new one")
    lease = start_lease(a.name, a.hours)
    flags = ["new", "-s", a.name] + (["--gpu", a.gpu] if a.gpu else []) + (["--tpu", a.tpu] if a.tpu else [])
    try:
        done = call_colab(flags + (["--high-mem"] if a.high_mem else []), timeout=900)
    except ColabError:
        end_lease(a.name)
        raise
    text = done.stdout + done.stderr
    if done.returncode != 0:
        end_lease(a.name)
        if "Allocation refused" in text or "Backend rejected accelerator" in text:
            raise ColabError(EXIT_REFUSED, "Colab refused the runtime: " + tail(text, 3),
                             "%s doctor; stop a session of yours you no longer need; retry once after a minute, "
                             "or ask the user which other hardware to use" % SCRIPT)
        raise ColabError(EXIT_CLI_FAILED, "could not create the session: " + tail(text), RETRY_NEXT)
    mine = [s for s in fetch_sessions() if s["name"] == a.name]
    print("SESSION: %s" % a.name)
    if mine:
        print("HARDWARE: %s (%s)" % (mine[0]["hardware"], mine[0]["shape"]))
    probe = vm(a.name, "probe", {"packages": PROBE_PACKAGES}, timeout=60, attempts=3)
    print("GPU: %s" % (probe["gpu"] or "none"))
    print("PYTHON: %s   CPUS: %s   RAM_GB: %s   DISK_FREE_GB: %s" % (
        probe["python"], probe["cpus"], probe["ram_gb"], probe["disk_free_gb"]))
    print("PREINSTALLED: " + ", ".join("%s %s" % (k, v or "(not installed)") for k, v in probe["packages"].items()))
    print("USAGE_RATE: %s (whole account, not just this session)" % fetch_usage().get("Usage rate", "unknown"))
    print("LEASE: stops by itself at %s (%sh) unless you run down first" % (
        time.strftime("%H:%M", time.localtime(lease["deadline"])), a.hours))
    print("WORK_DIR: /content/work   (push puts files here; run starts here)")
    print("NEXT: %s push %s LOCAL_PATH | install %s PACKAGE... | run %s -- COMMAND..." % (
        SCRIPT, a.name, a.name, a.name))
    return 0


def files(count: int) -> str:
    return "1 file" if count == 1 else "%d files" % count


def size_check(size: int, max_mb: int, what: str) -> None:
    if size > max_mb * 2**20:
        raise ColabError(EXIT_USAGE, "%s is %.1f MB, over the %d MB limit" % (what, size / 2**20, max_mb),
                         "download large data on the VM inside your script (datasets.load_dataset, wget), "
                         "or raise --max-mb")


def cmd_push(a: argparse.Namespace) -> int:
    local = Path(a.local)
    if not local.exists():
        raise ColabError(EXIT_USAGE, "no such local file or directory: %s (looked in %s)" % (local, Path.cwd()),
                         "give an absolute path, or . for the current directory")
    dest = a.to or local.resolve().name
    if local.is_file():
        size_check(local.stat().st_size, a.max_mb, str(local))
        remote = vm(a.name, "prepare", {"path": dest}, timeout=60, attempts=3)["path"]
        transfer(a.name, "upload", str(local), remote, local.stat().st_size)
        print("PUSHED: %s -> %s (1 file, %d bytes)" % (local, remote, local.stat().st_size))
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "push.tar.gz"
        count, size = make_archive(local, archive)
        size_check(size, a.max_mb, str(local))
        xfer = vm(a.name, "prepare", {"path": dest}, timeout=60, attempts=3)["xfer"]
        archive_name = "push-%s.tar.gz" % secrets.token_hex(6)
        transfer(a.name, "upload", str(archive), "%s/%s" % (xfer, archive_name), archive.stat().st_size)
    result = vm(a.name, "unpack", {"archive": archive_name, "dest": dest}, timeout=300, attempts=3)
    if "error" in result:
        raise ColabError(EXIT_CLI_FAILED, "the VM refused the archive: %s" % result.get("detail"), RETRY_NEXT)
    print("PUSHED: %s -> %s (%s, %d bytes)" % (local, result["dest"], files(count), size))
    return 0


def requirement_name(spec: str) -> str | None:
    match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec)
    return match.group(1) if match and "://" not in spec else None


def cmd_install(a: argparse.Namespace) -> int:
    specs = list(a.packages)
    names = [n for n in map(requirement_name, specs) if n]
    if a.requirement:
        path = Path(a.requirement)
        if not path.is_file():
            raise ColabError(EXIT_USAGE, "no such requirements file: %s" % path, "check the path")
        lines = [line.split("#", 1)[0].strip() for line in path.read_text().splitlines()]
        names += [n for n in map(requirement_name, (l for l in lines if l and not l.startswith("-"))) if n]
        prepared = vm(a.name, "prepare", {"path": "requirements.txt"}, timeout=60, attempts=3)
        remote = "%s/requirements-%s.txt" % (prepared["xfer"], secrets.token_hex(4))
        transfer(a.name, "upload", str(path), remote, path.stat().st_size)
        specs += ["-r", remote]
    if not specs:
        raise ColabError(EXIT_USAGE, "name at least one package or -r FILE", "%s install %s trl peft" % (SCRIPT, a.name))
    frameworks = sorted(n for n in names if n.lower() in FRAMEWORKS)
    if frameworks and not a.allow_framework:
        raise ColabError(EXIT_USAGE, "refusing to install %s: Colab ships a build matched to its CUDA, and "
                         "reinstalling it can break the GPU" % ", ".join(frameworks),
                         "drop it (up printed the preinstalled version), or add --allow-framework if a "
                         "specific version is required")
    job = a.job or new_job_id("install")
    start_job(a.name, job, kind="install", argv=["install"] + specs, cwd=".",
              install={"specs": specs, "names": names})
    return follow(a.name, job, wait=a.wait)


def cmd_run(a: argparse.Namespace) -> int:
    if not a.command:
        raise ColabError(EXIT_USAGE, "give the command to run after --", "%s run %s -- python train.py" % (SCRIPT, a.name))
    job = a.job or new_job_id("job")
    start_job(a.name, job, kind="run", argv=a.command, cwd=a.cwd)
    return follow(a.name, job, wait=a.wait)


def cmd_wait(a: argparse.Namespace) -> int:
    return follow(a.name, a.job or "", wait=a.wait, tail_lines=20)


def cmd_logs(a: argparse.Namespace) -> int:
    result = poll(a.name, a.job or "", -262144, grep=a.grep)
    printer = LogPrinter(budget=10**9)
    printer.feed(result["text"], keep_last=a.tail, drop_first=result["offset"] > 0)
    printer.close()
    if a.grep:
        print("MATCHES: %d lines of the whole log match '%s' (case-insensitive); showing the last %d" % (
            result["matches"], a.grep, min(a.tail, result["text"].count("\n"))))
    print("JOB: %s   STATE: %s%s   ELAPSED: %ds" % (
        result["job"], result["state"],
        "   EXIT_CODE: %d" % result["exit_code"] if "exit_code" in result else "", result["elapsed"]))
    return 0


def cmd_jobs(a: argparse.Namespace) -> int:
    print("\n".join(format_jobs(a.name, vm(a.name, "jobs", {"limit": 30}, timeout=45, attempts=4))))
    return 0


def cmd_stats(a: argparse.Namespace) -> int:
    print("\n".join(format_stats(a.name, vm(a.name, "stats", {"sample": 1.0}, timeout=60, attempts=4))))
    return 0


def cmd_pull(a: argparse.Namespace) -> int:
    result = vm(a.name, "pack", {"path": a.remote, "max_bytes": a.max_mb * 2**20}, timeout=300, attempts=3)
    if result.get("error") == "missing":
        raise ColabError(EXIT_USAGE, "%s does not exist on the VM" % result["path"],
                         "list it with: %s run %s -- ls -la /content/work" % (SCRIPT, a.name))
    if result.get("error") == "too_big":
        size_check(result["size"], a.max_mb, result["path"])
    dest = Path(a.local_dir)
    target = dest / PurePosixPath(result["path"]).name
    if target.exists() and not a.overwrite:
        raise ColabError(EXIT_USAGE, "%s already exists" % target,
                         "use another LOCAL_DIR, or add --overwrite to replace files with the same names")
    dest.mkdir(parents=True, exist_ok=True)
    if result["type"] == "file":
        transfer(a.name, "download", result["path"], str(target), result["size"])
        print("SAVED: %s (1 file, %d bytes)" % (target, result["size"]))
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "pull.tar.gz"
        transfer(a.name, "download", result["archive"], str(archive), result["size"])
        vm(a.name, "remove", {"path": result["archive"]}, timeout=60, attempts=2)
        try:
            safe_extract(archive, dest)
        except UnsafeArchive as exc:
            raise ColabError(EXIT_CLI_FAILED, str(exc), RETRY_NEXT)
    print("SAVED: %s (%s, %d bytes)" % (target, files(result["files"]), result["size"]))
    return 0


def cmd_down(a: argparse.Namespace) -> int:
    mine = [s for s in fetch_sessions() if s["name"] == a.name]
    if not mine:
        end_lease(a.name)
        print("RELEASED: %s (it was not running)" % a.name)
        return 0
    endpoint = mine[0]["endpoint"]
    call_colab(["stop", "-s", a.name], timeout=180)
    for _ in range(4):
        if all(s["endpoint"] != endpoint for s in fetch_sessions()):
            break
        time.sleep(5)
    else:
        raise ColabError(EXIT_CLI_FAILED, "%s is still listed after stop" % a.name,
                         "run down again; if it stays, ask the user to stop it in the Colab web UI "
                         "(Runtime > Manage sessions)")
    end_lease(a.name)
    print("RELEASED: %s (the VM and every file on it are gone)" % a.name)
    print("USAGE_RATE: %s (account-wide, remaining sessions)" % fetch_usage().get("Usage rate", "unknown"))
    return 0


# ---- argument parsing ----------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="colab_job.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Quick start: doctor; up exp-1; push exp-1 ./project; install exp-1 trl; "
               "run exp-1 --cwd project -- python train.py; pull exp-1 project/outputs ./results; down exp-1")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    def add(name: str, func, help_text: str) -> argparse.ArgumentParser:
        command = sub.add_parser(name, help=help_text, description=help_text)
        command.set_defaults(func=func)
        return command

    add("doctor", cmd_doctor, "check the CLI, sign-in, compute units and sessions; allocates nothing")
    up = add("up", cmd_up, "create a session (CPU unless --gpu/--tpu: CPU is the cheapest) and probe it")
    up.add_argument("name", help="new session name, e.g. exp-1")
    up.add_argument("--gpu", type=str.upper, choices=["T4", "L4", "G4", "A100", "H100"],
                    help="GPU type; T4 is the cheapest GPU")
    up.add_argument("--tpu", type=str.lower, choices=["v5e1", "v6e1"], help="TPU type")
    up.add_argument("--high-mem", action="store_true", help="high-RAM shape (costs more)")
    up.add_argument("--hours", type=float, default=1.0, help="auto-stop after this many hours (default 1, max 12)")

    push = add("push", cmd_push, "copy a local file or directory to /content/work/<its name> on the VM")
    push.add_argument("name")
    push.add_argument("local")
    push.add_argument("--to", help="destination under /content/work (default: the local name)")
    push.add_argument("--max-mb", type=int, default=DEFAULT_MAX_MB)

    install = add("install", cmd_install, "pip-install packages on the VM and print their installed versions")
    install.add_argument("name")
    install.add_argument("packages", nargs="*", help="package specs, e.g. trl peft==0.21.2")
    install.add_argument("-r", "--requirement", help="a local requirements.txt")
    install.add_argument("--allow-framework", action="store_true", help="allow reinstalling torch/jax/tensorflow")
    install.add_argument("--job")
    install.add_argument("--wait", type=float, default=300, help="seconds to follow before returning (default 300)")

    run = add("run", cmd_run, "run a command on the VM as a job: run NAME -- python train.py --epochs 1")
    run.add_argument("name")
    run.add_argument("command", nargs="*", help=argparse.SUPPRESS)
    run.add_argument("--job", help="job name (default: job-<time>)")
    run.add_argument("--cwd", default=".", help="working directory, relative to /content/work (default)")
    run.add_argument("--wait", type=float, default=DEFAULT_WAIT,
                     help="seconds to follow the log before returning; the job keeps running (default %d)" % DEFAULT_WAIT)

    wait = add("wait", cmd_wait, "keep following a job (default: the latest) until it ends or --wait passes")
    wait.add_argument("name")
    wait.add_argument("job", nargs="?")
    wait.add_argument("--wait", type=float, default=DEFAULT_WAIT)

    logs = add("logs", cmd_logs, "print the last lines of a job's log (default: the latest job)")
    logs.add_argument("name")
    logs.add_argument("job", nargs="?")
    logs.add_argument("--tail", type=int, default=50)
    logs.add_argument("--grep", type=grep_pattern, metavar="REGEX",
                      help="only the lines matching REGEX (case-insensitive), searched over the whole log")
    add("jobs", cmd_jobs, "list the session's jobs, newest first, with state and last log line").add_argument("name")
    add("stats", cmd_stats, "show CPU, RAM, disk and GPU use, and each running job's share").add_argument("name")

    pull = add("pull", cmd_pull, "copy a file or directory from the VM into LOCAL_DIR")
    pull.add_argument("name")
    pull.add_argument("remote", help="path on the VM; relative paths are under /content/work")
    pull.add_argument("local_dir")
    pull.add_argument("--overwrite", action="store_true")
    pull.add_argument("--max-mb", type=int, default=DEFAULT_MAX_MB)

    down = add("down", cmd_down, "stop the session and confirm Colab released it (pull results first)")
    down.add_argument("name")

    watchdog = sub.add_parser("_watchdog")
    watchdog.add_argument("name")
    watchdog.add_argument("token")
    watchdog.set_defaults(func=cmd_watchdog)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, command = argv[:split], argv[split + 1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        args.command = args.command + command
    elif command:
        parser.error("`--` is only used by run")
    try:
        return args.func(args)
    except ColabError as exc:
        print("%s: %s" % ("RUNNING" if exc.code == EXIT_STILL_RUNNING else "ERROR", exc))
        if exc.next_step:
            print("NEXT: %s" % exc.next_step)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
