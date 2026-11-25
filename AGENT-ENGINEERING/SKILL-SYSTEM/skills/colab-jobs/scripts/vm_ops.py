"""Code that colab_job.py sends to the Colab VM through `colab exec`.

Each call appends `run_op(NAME, ARGS)` to this source and runs it in the
session's kernel. Ops print one marker line of JSON that the local helper
parses. Run as a script on the VM, it is also the job runner and installer:
`python3 vm_ops.py runner JOB_DIR` and `python3 vm_ops.py install ARGS_JSON`.
Standard library only; the VM runs Colab's Python.
"""
import collections
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import uuid

ROOT = "/content"
JOBS = ROOT + "/colab-jobs"
WORK = ROOT + "/work"
XFER = JOBS + "/_xfer"
SELF = JOBS + "/vm_ops.py"
MARK = "@@colab-jobs@@"
PROC = "/proc"


def emit(obj):
    print(MARK + json.dumps(obj), flush=True)


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def resolve(path):
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(WORK, path))


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        with open("/proc/%d/stat" % pid) as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return True


def job_state(job_dir):
    spec = read_json(os.path.join(job_dir, "spec.json"))
    finished = read_json(os.path.join(job_dir, "exit.json"))
    if finished is None:
        runner = read_json(os.path.join(job_dir, "runner.json"))
        if runner and alive(runner["pid"]):
            return {"state": "running", "elapsed": round(time.time() - spec["started_at"])}
        # The runner writes exit.json just before it exits; read once more.
        finished = read_json(os.path.join(job_dir, "exit.json"))
        if finished is None:
            return {"state": "lost", "elapsed": round(time.time() - spec["started_at"])}
    return {
        "state": "succeeded" if finished["exit_code"] == 0 else "failed",
        "exit_code": finished["exit_code"],
        "elapsed": round(finished["ended_at"] - spec["started_at"]),
    }


def op_probe(args):
    os.makedirs(WORK, exist_ok=True)
    report = {
        "python": sys.version.split()[0],
        "cpus": os.cpu_count(),
        "ram_gb": round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1),
        "disk_free_gb": round(shutil.disk_usage(ROOT).free / 2**30, 1),
        "uv": bool(shutil.which("uv")),
        "gpu": None,
        "packages": {},
    }
    if shutil.which("nvidia-smi"):
        query = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=30,
        )
        report["gpu"] = query.stdout.strip() or "nvidia-smi failed: " + query.stderr.strip()
    for name in args["packages"]:
        try:
            report["packages"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            report["packages"][name] = None
    return report


def op_start(args):
    """Start a job once. mkdir claims the name atomically; a repeat of the same
    start (same token, sent again after a lost reply) returns the job it started."""
    job_dir = os.path.join(JOBS, args["job"])
    os.makedirs(JOBS, exist_ok=True)
    try:
        os.mkdir(job_dir)
    except FileExistsError:
        spec = read_json(os.path.join(job_dir, "spec.json")) or {}
        if spec.get("token") == args["token"]:
            return {"job": args["job"], "cwd": spec["cwd"], "repeat": True}
        return {"error": "job_exists", "job": args["job"]}
    cwd = resolve(args["cwd"])
    os.makedirs(cwd, exist_ok=True)
    with open(SELF, "w") as f:
        f.write(args["source"])
    argv = args["argv"]
    if args["kind"] == "install":
        argv = [sys.executable, SELF, "install", json.dumps(args["install"])]
    write_json(os.path.join(job_dir, "spec.json"), {
        "argv": argv, "cwd": cwd, "kind": args["kind"], "started_at": time.time(), "token": args["token"],
    })
    with open(os.path.join(job_dir, "runner.err"), "ab") as err:
        runner = subprocess.Popen(
            [sys.executable, SELF, "runner", job_dir],
            start_new_session=True, close_fds=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
        )
    write_json(os.path.join(job_dir, "runner.json"), {"pid": runner.pid})
    return {"job": args["job"], "cwd": cwd}


def latest_job():
    if not os.path.isdir(JOBS):
        return None
    started = {}
    for name in os.listdir(JOBS):
        if not os.path.isdir(os.path.join(JOBS, name)):
            continue
        spec = read_json(os.path.join(JOBS, name, "spec.json"))
        if spec:
            started[name] = spec["started_at"]
    return max(started, key=started.get) if started else None


def grep_log(log_path, pattern):
    """Every line of the whole log matching pattern (case-insensitive): the count and
    the last 500, each cut to 500 characters. Progress-bar frames count as lines."""
    regex, found, count = re.compile(pattern, re.IGNORECASE), collections.deque(maxlen=500), 0
    if os.path.exists(log_path):
        with open(log_path, "rb") as f:
            for raw in f:
                for frame in raw.decode("utf-8", "replace").rstrip("\n").split("\r"):
                    if regex.search(frame):
                        found.append(frame[:500])
                        count += 1
    return "".join(line + "\n" for line in found), count


def op_poll(args):
    job = args["job"] or latest_job()
    if job is None:
        return {"error": "no_jobs"}
    job_dir = os.path.join(JOBS, job)
    if not os.path.isfile(os.path.join(job_dir, "spec.json")):
        return {"error": "no_such_job", "job": job}
    result = job_state(job_dir)
    log_path = os.path.join(job_dir, "log.txt")
    size = os.path.getsize(log_path) if os.path.exists(log_path) else 0
    if args.get("grep"):
        text, matches = grep_log(log_path, args["grep"])
        result.update(job=job, size=size, offset=0, next=size, text=text, matches=matches)
        return result
    offset = args["offset"] if args["offset"] >= 0 else max(0, size + args["offset"])
    chunk = b""
    if offset < size:
        with open(log_path, "rb") as f:
            f.seek(offset)
            chunk = f.read(args["limit"])
    result.update(job=job, size=size, offset=offset, next=offset + len(chunk),
                  text=chunk.decode("utf-8", "replace"))
    return result


def job_summary(job_dir, spec):
    """A job's command, state, runner pid and the raw end of its log, for jobs and stats."""
    runner = read_json(os.path.join(job_dir, "runner.json")) or {}
    summary = dict(job_state(job_dir), job=os.path.basename(job_dir), kind=spec["kind"], argv=spec["argv"],
                   cwd=spec["cwd"], started_at=spec["started_at"], pid=runner.get("pid"), tail="")
    log_path = os.path.join(job_dir, "log.txt")
    if os.path.exists(log_path):
        with open(log_path, "rb") as f:
            f.seek(max(0, os.path.getsize(log_path) - 2048))
            summary["tail"] = f.read().decode("utf-8", "replace")
    return summary


def all_jobs():
    """Every job on the VM, newest first."""
    found = []
    for name in os.listdir(JOBS) if os.path.isdir(JOBS) else []:
        spec = os.path.isdir(os.path.join(JOBS, name)) and read_json(os.path.join(JOBS, name, "spec.json"))
        if spec:  # JOBS also holds vm_ops.py and _xfer
            found.append(job_summary(os.path.join(JOBS, name), spec))
    return sorted(found, key=lambda job: job["started_at"], reverse=True)


def op_jobs(args):
    jobs = all_jobs()
    return {"jobs": jobs[:args["limit"]], "total": len(jobs)}


def proc_sessions():
    """CPU ticks, resident bytes and process count per session, from /proc. A job's runner
    starts its own session, which every process the job starts inherits (even one that
    makes its own process group, as `timeout` does), so the session id is the runner's pid."""
    sessions, page = {}, os.sysconf("SC_PAGE_SIZE")
    for entry in os.listdir(PROC) if os.path.isdir(PROC) else []:
        if not entry.isdigit():
            continue
        try:
            with open(os.path.join(PROC, entry, "stat")) as f:
                # after the ")" that ends the command name: state ppid pgrp session ... utime stime ... rss
                fields = f.read().rsplit(")", 1)[1].split()
        except OSError:
            continue  # it exited while we looked
        ticks, rss, count = sessions.get(int(fields[3]), (0, 0, 0))
        sessions[int(fields[3])] = (ticks + int(fields[11]) + int(fields[12]), rss + int(fields[21]) * page, count + 1)
    return sessions


def memory():
    try:
        with open(os.path.join(PROC, "meminfo")) as f:
            info = {key: int(value.split()[0]) * 1024 for key, value in (line.split(":", 1) for line in f)}
    except OSError:
        return None
    return {"total": info["MemTotal"], "available": info["MemAvailable"]}


def gpus():
    if not shutil.which("nvidia-smi"):
        return []
    keys = ["name", "busy_percent", "memory_used_mib", "memory_total_mib", "temperature_c"]
    try:
        query = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return [{"error": "nvidia-smi did not answer within 20 s"}]
    if query.returncode != 0:
        return [{"error": (query.stderr or query.stdout).strip()}]
    return [dict(zip(keys, (v.strip() for v in line.split(",")))) for line in query.stdout.strip().splitlines()]


def op_stats(args):
    """The VM's load, memory, disk and GPUs, and each running job's CPU (sampled over
    args["sample"] seconds; 100 is one full core), resident memory and process count."""
    before, started = proc_sessions(), time.monotonic()
    time.sleep(args["sample"])
    after, interval = proc_sessions(), time.monotonic() - started
    running = [job for job in all_jobs() if job["state"] == "running"]
    for job in running:
        if job["pid"] in after:
            ticks, rss, count = after[job["pid"]]
            spent = max(0, ticks - before.get(job["pid"], (ticks,))[0]) / os.sysconf("SC_CLK_TCK")
            job.update(cpu_percent=round(100 * spent / interval), rss_bytes=rss, processes=count)
    disk = shutil.disk_usage(ROOT)
    return {"cpus": os.cpu_count(), "load": round(os.getloadavg()[0], 2), "memory": memory(),
            "disk": {"free": disk.free, "total": disk.total}, "gpus": gpus(), "running": running}


def op_prepare(args):
    os.makedirs(os.path.dirname(resolve(args["path"])), exist_ok=True)
    os.makedirs(XFER, exist_ok=True)
    return {"path": resolve(args["path"]), "xfer": XFER}


def op_unpack(args):
    """Unpack a pushed archive once. A receipt written before the archive is removed
    lets a repeat (sent again after a lost reply) return the first result."""
    archive = os.path.join(XFER, args["archive"])
    receipt = archive + ".done"
    if not os.path.exists(archive):
        return read_json(receipt) or {"error": "missing_archive", "detail": args["archive"]}
    dest = resolve(args["dest"])
    os.makedirs(dest, exist_ok=True)
    try:
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            for member in members:
                if member.name.startswith("/") or ".." in member.name.split("/"):
                    return {"error": "unsafe_archive", "detail": member.name}
            if hasattr(tarfile, "data_filter"):
                tar.extractall(dest, members=members, filter="data")
            else:
                tar.extractall(dest, members=members)
        result = {"dest": dest, "files": sum(1 for m in members if m.isfile())}
        write_json(receipt, result)
        return result
    finally:
        os.remove(archive)


def op_pack(args):
    path = resolve(args["path"])
    if os.path.isfile(path):
        size = os.path.getsize(path)
        if size > args["max_bytes"]:
            return {"error": "too_big", "path": path, "size": size}
        return {"type": "file", "path": path, "size": size}
    if not os.path.isdir(path):
        return {"error": "missing", "path": path}
    size, files = 0, 0
    for parent, _dirs, names in os.walk(path, followlinks=True):
        for name in names:
            full = os.path.join(parent, name)
            if os.path.isfile(full):
                size += os.path.getsize(full)
                files += 1
    if size > args["max_bytes"]:
        return {"error": "too_big", "path": path, "size": size}
    os.makedirs(XFER, exist_ok=True)
    archive = os.path.join(XFER, "pull-%s.tar.gz" % uuid.uuid4().hex[:12])
    with tarfile.open(archive, "w:gz", dereference=True) as tar:
        tar.add(path, arcname=os.path.basename(path))
    return {"type": "dir", "path": path, "size": size, "files": files, "archive": archive}


def op_remove(args):
    target = os.path.normpath(args["path"])
    if os.path.dirname(target) != XFER:
        return {"error": "not_a_transfer_file", "path": target}
    if os.path.exists(target):
        os.remove(target)
    return {"removed": target}


OPS = {
    "probe": op_probe,
    "start": op_start,
    "poll": op_poll,
    "prepare": op_prepare,
    "unpack": op_unpack,
    "pack": op_pack,
    "remove": op_remove,
    "jobs": op_jobs,
    "stats": op_stats,
}


def run_op(name, args):
    try:
        emit(OPS[name](args))
    except (OSError, tarfile.TarError, subprocess.SubprocessError) as exc:
        emit({"error": "vm_error", "detail": "%s: %s" % (type(exc).__name__, exc)})


def run_job(job_dir):
    """Run the job's command, log its output, and record its exit code last."""
    spec = read_json(os.path.join(job_dir, "spec.json"))
    env = dict(os.environ, PYTHONUNBUFFERED="1", MPLBACKEND="Agg", COLAB_JOB_DIR=job_dir)
    with open(os.path.join(job_dir, "log.txt"), "ab", buffering=0) as log:
        try:
            child = subprocess.Popen(
                spec["argv"], cwd=spec["cwd"], env=env,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            log.write(("colab-jobs: cannot start %r: %s\n" % (spec["argv"][0], exc)).encode())
            code = 127
        else:
            code = child.wait()
    write_json(os.path.join(job_dir, "exit.json"), {"exit_code": code, "ended_at": time.time()})


def install(args):
    """Install packages, then report the installed version of each one requested."""
    base = ["uv", "pip", "install", "--system"] if shutil.which("uv") else [sys.executable, "-m", "pip", "install"]
    command = base + args["specs"]
    print("$ " + " ".join(command), flush=True)
    code = subprocess.call(command)
    if code != 0:
        print("colab-jobs: install failed with exit code %d" % code, flush=True)
        return code
    missing = False
    print("Installed versions:", flush=True)
    for name in args["names"]:
        try:
            print("  %s==%s" % (name, importlib.metadata.version(name)), flush=True)
        except importlib.metadata.PackageNotFoundError:
            print("  %s: NOT FOUND after install" % name, flush=True)
            missing = True
    return 3 if missing else 0


if __name__ == "__main__" and sys.argv[1:2] == ["runner"]:
    run_job(sys.argv[2])
elif __name__ == "__main__" and sys.argv[1:2] == ["install"]:
    sys.exit(install(json.loads(sys.argv[2])))
