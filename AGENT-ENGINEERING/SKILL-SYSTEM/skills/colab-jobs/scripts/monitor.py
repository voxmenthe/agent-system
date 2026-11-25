"""What colab_job.py prints for `jobs`, `stats` and `logs --grep`.

`jobs` gives each job's state, command and last log line; `stats` adds a
snapshot of the VM's CPU, memory, disk and GPU and each running job's share.
Pure formatting: the numbers come from the jobs and stats ops in vm_ops.py.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex

from log_view import clean_line


def grep_pattern(text: str) -> str:
    """argparse type for --grep: the VM compiles it, so reject a bad pattern here."""
    try:
        re.compile(text, re.IGNORECASE)
    except re.error as exc:
        raise argparse.ArgumentTypeError("%r is not a valid regular expression (%s); put \\ before "
                                         "special characters such as ( [ + *" % (text, exc))
    return text


def duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm %02ds" % divmod(seconds, 60)
    return "%dh %02dm" % (seconds // 3600, seconds % 3600 // 60)


def gigabytes(count: int) -> str:
    return "%.1f GB" % (count / 2**30)


def shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())  # one line, even for `python -c` code with newlines
    return text if len(text) <= limit else text[:limit - 3] + "..."


def command_text(job: dict) -> str:
    if job["kind"] == "install":  # the runner's argv is [python, vm_ops.py, "install", JSON]
        return shorten("install " + " ".join(json.loads(job["argv"][-1])["specs"]), 100)
    return shorten(shlex.join(job["argv"]), 100)


def last_line(tail: str) -> str:
    lines = [clean_line(line).strip() for line in tail.split("\n")]
    found = [line for line in lines if line]
    return shorten(found[-1], 160) if found else "(no output yet)"


def status(job: dict) -> str:
    took = duration(job["elapsed"])
    if job["state"] == "running":
        return "running for " + took
    if job["state"] == "lost":
        return "lost after %s (killed without an exit record)" % took
    return "%s in %s, exit %d" % (job["state"], took, job["exit_code"])


def format_jobs(name: str, result: dict) -> list[str]:
    if not result["jobs"]:
        return ["JOBS: none yet on %s" % name]
    lines = []
    for job in result["jobs"]:
        lines += ["JOB: %s | %s | %s" % (job["job"], status(job), command_text(job)),
                  "  LAST: " + last_line(job["tail"])]
    shown = "" if len(result["jobs"]) == result["total"] else " (the %d newest shown)" % len(result["jobs"])
    return lines + ["JOBS: %d on %s, newest first%s" % (result["total"], name, shown)]


def format_stats(name: str, result: dict) -> list[str]:
    lines = ["CPU: %d cores, load %.2f over the last minute" % (result["cpus"], result["load"])]
    mem = result["memory"]
    lines.append("RAM: %s used of %s" % (gigabytes(mem["total"] - mem["available"]), gigabytes(mem["total"]))
                 if mem else "RAM: unknown")
    lines.append("DISK: %s free of %s" % (gigabytes(result["disk"]["free"]), gigabytes(result["disk"]["total"])))
    for gpu in result["gpus"]:
        lines.append("GPU: nvidia-smi failed: %s" % gpu["error"] if "error" in gpu else
                     "GPU: %(name)s | %(busy_percent)s%% busy | memory %(memory_used_mib)s of "
                     "%(memory_total_mib)s MiB | %(temperature_c)s C" % gpu)
    if not result["gpus"]:
        lines.append("GPU: none")
    for job in result["running"]:
        usage = ("CPU %d%% | RAM %s | %d processes" % (job["cpu_percent"], gigabytes(job["rss_bytes"]), job["processes"])
                 if "cpu_percent" in job else "CPU and RAM unknown")
        lines += ["RUNNING: %s | %s | %s | %s" % (job["job"], duration(job["elapsed"]), usage, command_text(job)),
                  "  LAST: " + last_line(job["tail"])]
    if not result["running"]:
        lines.append("RUNNING: no jobs (jobs %s lists the finished ones)" % name)
    return lines
