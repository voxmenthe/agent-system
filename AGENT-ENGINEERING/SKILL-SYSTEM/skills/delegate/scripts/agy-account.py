#!/usr/bin/env python3
"""Choose the Antigravity account a plain launcher name runs on.

    agy-account.py pick LAUNCHER      print LAUNCHER (the primary account) or its `2` twin (~/.agy2), whichever
                                      account has more of that launcher's model quota left
    agy-account.py overflow LAUNCHER  after LAUNCHER failed, from a fresh reading: "retry TWIN" when its account
                                      has none of that model's quota left and the other account has some,
                                      "exhausted GROUP" when no signed-in account has any, else "other"

Quota is AGY's own /usage reading (about 3 s an account; stale accounts are read at once), kept for
READING_TTL_SECONDS in $XDG_CACHE_HOME/agy-account/readings.json, so a wave's launches share one reading. A model
group's room is the least of its weekly and five-hour fractions; a disabled bucket (an exhausted week) has none.
The second account is read only once it holds a login: a signed-out AGY opens a browser login and waits.
An unreadable account is unknown: a readable account with room wins over it, and it wins over one with none.
Ties go to the primary account.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

READING_TTL_SECONDS = 180
# agy's --print-timeout is a turn budget, not a wall clock, so the query has its own.
QUERY_TIMEOUT_SECONDS = 25
TOKEN = ".gemini/antigravity-cli/antigravity-oauth-token"
# Under the second account's HOME there is no macOS keychain, and AGY's token saves there raise a "Keychain Not
# Found" dialog; in an SSH session AGY keeps tokens in its file without trying the keychain (as ~/.bash_agents does).
AGY2_SSH_CONNECTION = "127.0.0.1 0 127.0.0.1 0"
# /usage model groups, by the model each plain launcher pins in ~/.bash_agents.
GROUPS = {
    **dict.fromkeys(("agg", "aggbs", "aggtp", "aggb", "aggbbs", "aggbtp",
                     "aghh", "aghhb", "aghx", "aghxb",
                     "agcm", "agcmb", "agch", "agchb",
                     "agnm", "agnmb", "agnh", "agnhb", "agnx", "agnxb"), "Gemini Models"),
    **dict.fromkeys(("agom", "agoh"), "Claude and GPT models"),
    **dict.fromkeys(("argm", "argh"), "Gemini 4 Argon"),
}

Rooms = dict[str, float]


def account_homes() -> list[Path]:
    """The HOME each signed-in account runs AGY under, primary first."""
    second = Path(os.environ.get("AGY2_HOME", Path.home() / ".agy2"))
    token = second / TOKEN
    return [Path.home()] + ([second] if token.is_file() and token.stat().st_size else [])


def fetch_rooms(home: Path) -> Rooms | None:
    """Each model group's room on HOME's account, from AGY's /usage; None when unreadable."""
    env = {**os.environ, "HOME": str(home)}
    if home != Path.home():
        env["SSH_CONNECTION"] = os.environ.get("SSH_CONNECTION") or AGY2_SSH_CONNECTION
    try:
        result = subprocess.run(
            ["agy", "--print", "/usage", "--output-format", "json", "--agent", "agy-bare",
             "--print-timeout", f"{QUERY_TIMEOUT_SECONDS}s"],
            env=env, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=QUERY_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        reply = json.loads(result.stdout)
        if result.returncode != 0 or reply["status"] != "SUCCESS":
            return None
        return {
            group["name"]: min(0.0 if bucket.get("disabled") else float(bucket["remaining_fraction"])
                               for bucket in group["buckets"])
            for group in reply["command"]["data"]["groups"]
        }
    except (ValueError, KeyError, TypeError):
        return None


def readings(homes: list[Path], fresh: bool = False) -> dict[Path, Rooms | None]:
    """Each home's rooms, re-read when older than READING_TTL_SECONDS, or all of them when FRESH.

    The lock is held across the queries, so concurrent launches wait for one refresh instead of each querying AGY;
    each query is bounded by QUERY_TIMEOUT_SECONDS."""
    path = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"), "agy-account", "readings.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            cached = json.loads(path.read_text())
        except (OSError, ValueError):
            cached = {}
        now = time.time()
        stale = [home for home in homes
                 if fresh or now - cached.get(str(home), {}).get("at", 0) > READING_TTL_SECONDS]
        if stale:
            with ThreadPoolExecutor(max_workers=len(stale)) as pool:
                for home, rooms in zip(stale, pool.map(fetch_rooms, stale)):
                    cached[str(home)] = {"at": now, "rooms": rooms}
            temporary = path.with_name(f".{path.name}.{os.getpid()}")
            temporary.write_text(json.dumps(cached))
            os.replace(temporary, path)
        return {home: cached[str(home)]["rooms"] for home in homes}


def rank(rooms: Rooms | None, group: str) -> tuple[int, float]:
    """Higher is better: known room above zero, then unknown, then known to have none."""
    room = None if rooms is None else rooms.get(group)
    if room is None:
        return 1, 0.0
    return (2, room) if room > 0 else (0, 0.0)


def launcher_on(plain: str, homes: list[Path], home: Path) -> str:
    return plain if home == homes[0] else plain + "2"


def describe(homes: list[Path], rooms: dict[Path, Rooms | None], group: str) -> str:
    parts = []
    for number, home in enumerate(homes, 1):
        room = None if rooms[home] is None else rooms[home].get(group)
        parts.append(f"account {number} " + ("unknown" if room is None else f"{room * 100:.0f}% left"))
    return f"{group}: {', '.join(parts)}"


def pick(plain: str) -> str:
    homes = account_homes()
    if len(homes) == 1:
        return plain
    group = GROUPS[plain]
    rooms = readings(homes)
    if all(rooms[home] is not None and group not in rooms[home] for home in homes):
        print(f"agy-account: /usage has no {group!r} group; using the primary account", file=sys.stderr)
    # max keeps the first of equal ranks, so ties stay on the primary account.
    chosen = launcher_on(plain, homes, max(homes, key=lambda home: rank(rooms[home], group)))
    print(f"agy-account: {chosen} ({describe(homes, rooms, group)})", file=sys.stderr)
    return chosen


def overflow(failed: str) -> str:
    plain = failed[:-1] if failed.endswith("2") else failed
    group = GROUPS[plain]
    homes = account_homes()
    if failed != plain and len(homes) == 1:
        return "other"  # its login is gone; the launcher reports that itself
    failed_home = homes[0] if failed == plain else homes[1]
    rooms = readings(homes, fresh=True)
    if rank(rooms[failed_home], group)[0] != 0:
        return "other"
    others = [home for home in homes if home != failed_home and rank(rooms[home], group)[0] != 0]
    print(f"agy-account: {failed} has no quota left ({describe(homes, rooms, group)})", file=sys.stderr)
    return f"retry {launcher_on(plain, homes, others[0])}" if others else f"exhausted {group}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("pick", "overflow"))
    parser.add_argument("launcher", choices=sorted({*GROUPS, *(name + "2" for name in GROUPS)}))
    args = parser.parse_args()
    if args.command == "pick" and args.launcher not in GROUPS:
        parser.error("pick takes a plain launcher; a `2` name already pins the second account")
    print(pick(args.launcher) if args.command == "pick" else overflow(args.launcher))
    return 0


if __name__ == "__main__":
    sys.exit(main())
