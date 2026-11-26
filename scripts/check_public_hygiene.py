#!/usr/bin/env python3
"""Public-repository hygiene gate for agent-system.

Prevents secrets, machine-specific paths, personal emails, stale monorepo
references, host-owned config keys, and machine-local private deny-list terms
from being staged, committed, or pushed to the public repository.

Usage:
  scripts/check_public_hygiene.py --all
  scripts/check_public_hygiene.py --staged
  scripts/check_public_hygiene.py --commits origin/main..HEAD
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import fnmatch
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - Python 3.9/3.10 fallback
    tomllib = None  # type: ignore[assignment]


DEFAULT_DENYLIST = Path.home() / ".config" / "agent-system" / "hygiene-denylist.txt"

# Upstream license/notice files and explicitly reviewed synthetic fixtures.
EMAIL_ALLOW_DOMAINS = (
    "@example.com",
    "@example.org",
    "@example.net",
    "@example.invalid",
    "@test.invalid",
    "@localhost.localdomain",
)
EMAIL_ALLOW_PATH_GLOBS = (
    "LICENSE",
    "THIRD-PARTY-NOTICES.md",
    "*/LICENSE",
    "*/*.LICENSE",
    "*/NOTICE.md",
    "*/plugin.json",
)
EMAIL_ALLOW_EXACT = {
    ("AGENT-ENGINEERING/SKILL-SYSTEM/skills/chats/tests/test_chatgpt_transcript.py", "user@chatgpt.com"),
}

USERS_PATH_ALLOW = {
    ("AGENT-ENGINEERING/PERSISTENT-GUIDANCE/README.md", "/Users/a"),
    ("AGENT-ENGINEERING/PERSISTENT-GUIDANCE/README.md", "/Users/ab"),
}
VOLUMES_PATH_ALLOW = {
    ("AGENT-ENGINEERING/PERSISTENT-GUIDANCE/tests/test_hostlib.py", "/Volumes/b"),
}

# Narrow reviewed allowlist for pre-existing references in published workflow skills.
STALE_MONO_ALLOW_GLOBS: dict[str, tuple[str, ...]] = {
    "REFERENCE/": ("SHELL/README.md",),
    "PROMPTS/": ("AGENT-ENGINEERING/SKILL-SYSTEM/skills/synthesize-market-state/SKILL.md",),
    "grok-X-adhoc": (
        "AGENT-ENGINEERING/SKILL-SYSTEM/registry.json",
        "AGENT-ENGINEERING/SKILL-SYSTEM/skills/delegate/scripts/refusals.py",
        "AGENT-ENGINEERING/SKILL-SYSTEM/skills/delegate/tests/test_refusals.py",
        "AGENT-ENGINEERING/SKILL-SYSTEM/skills/options-levels/*",
        "AGENT-ENGINEERING/SKILL-SYSTEM/skills/options-levels/*/*",
    ),
    ".learning-workspace/": (
        "AGENT-ENGINEERING/PERSISTENT-GUIDANCE/README.md",
        "AGENT-ENGINEERING/PERSISTENT-GUIDANCE/hooks/piped_status_warning.py",
        "AGENT-ENGINEERING/SKILL-SYSTEM/skills/learning-workspace/SKILL.md",
        "AGENT-ENGINEERING/SKILL-SYSTEM/skills/solutionize/references/running.md",
    ),
}

# Built dynamically so this checker does not trigger itself when scanned.
RE_USERS_PATH = re.compile(
    r"/Users/(?!me(?:/|[^A-Za-z0-9._-]|$)|you(?:/|[^A-Za-z0-9._-]|$)|"
    r"example(?:/|[^A-Za-z0-9._-]|$)|user(?:/|[^A-Za-z0-9._-]|$)|<)[A-Za-z0-9._-]+"
)
RE_VOLUMES_PATH = re.compile(
    r"/Volumes/(?!External(?:/|[^A-Za-z0-9._-]|$)|<)[A-Za-z0-9._-]+"
)
RE_PRIVATE_VAR = re.compile(r"/private/var/folders/")
RE_EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

RE_STALE_MONO_HARD = re.compile(r"\bM" + r"[34]-BASH\b")
RE_STALE_MONO_SOFT = re.compile(
    r"\bgrok-" + r"X-adhoc\b|(?<![A-Za-z0-9_-])(?:"
    + r"REFER" + r"ENCE|"
    + r"\.learning-" + r"workspace|"
    + r"PROM" + r"PTS)/"
)

RE_SECRET_SK = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}")
RE_SECRET_GH = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}")
RE_SECRET_SLACK = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")
RE_SECRET_AWS = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
RE_SECRET_PRIVKEY = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
RE_SECRET_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}")
RE_SECRET_ENV_ASSIGN = re.compile(r"\b[A-Z0-9_]*API_KEY\s*=\s*['\"]?([A-Za-z0-9._-]{16,})")

TEST_FILE_MARKER = re.compile(r"(?:^|/)tests?/|/test_[^/]+\.py$|^scripts/test_[^/]+\.py$")
FAKE_SECRET_SENTINEL = re.compile(
    r"(?:test|fake|dummy|example|placeholder|sample|stale|dotenv|ambient|rotated|custom-env|renewed-access-token|not-real)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    rule: str
    location: str
    detail: str

    def format(self) -> str:
        return f"[{self.rule}] {self.location}: {self.detail}"


@dataclass(frozen=True)
class DenyRule:
    raw: str
    pattern: re.Pattern[str]
    allow_globs: tuple[str, ...]


def _run_git(repo: Path, args: list[str], *, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=text,
        check=False,
    )


def _matches_any_glob(path: str, globs: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def load_denylist(path: Path, *, required: bool) -> tuple[list[DenyRule], list[Finding]]:
    """Load machine-local private deny-list rules from outside git.

    Supported line forms:
      literal term
      re:<regex>
      word:<term>
      case:<exact-case-literal>
      <any of the above>  @allow:path/glob1,path/glob2
    """
    if not path.is_file():
        if required:
            return [], [
                Finding(
                    "denylist-missing",
                    str(path),
                    "required private deny-list file not found "
                    "(create it or unset AGENT_SYSTEM_REQUIRE_DENYLIST)",
                )
            ]
        return [], []

    rules: list[DenyRule] = []
    findings: list[Finding] = []
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        allow_globs: tuple[str, ...] = ()
        if "@allow:" in line:
            body, allow_part = line.split("@allow:", 1)
            line = body.strip()
            allow_globs = tuple(g.strip() for g in allow_part.split(",") if g.strip())
        if not line:
            continue
        try:
            if line.startswith("re:"):
                rx = re.compile(line[3:].strip(), re.IGNORECASE)
            elif line.startswith("word:"):
                rx = re.compile(r"\b" + re.escape(line[5:].strip()) + r"\b", re.IGNORECASE)
            elif line.startswith("case:"):
                rx = re.compile(re.escape(line[5:].strip()))
            else:
                rx = re.compile(re.escape(line), re.IGNORECASE)
        except re.error as exc:
            findings.append(Finding("denylist-syntax", f"{path}:{lineno}", f"invalid regex: {exc}"))
            continue
        rules.append(DenyRule(raw=line, pattern=rx, allow_globs=allow_globs))

    if required and not rules and not findings:
        findings.append(
            Finding("denylist-empty", str(path), "required private deny-list has no active rules")
        )
    return rules, findings


def scan_text(
    text: str,
    *,
    rel_path: str,
    location_prefix: str | None = None,
    denylist: list[DenyRule],
    is_commit_message: bool = False,
    start_line: int = 1,
) -> list[Finding]:
    """Scan text lines against generic public rules and machine-local deny-list."""
    findings: list[Finding] = []
    loc_base = location_prefix or rel_path
    is_test = (not is_commit_message) and bool(TEST_FILE_MARKER.search(rel_path))
    is_self_checker = (not is_commit_message) and rel_path == "scripts/check_public_hygiene.py"

    for offset, line in enumerate(text.splitlines()):
        lineno = start_line + offset
        loc = f"{loc_base}:{lineno}" if not is_commit_message else loc_base

        # 1. Secret patterns
        for m in RE_SECRET_SK.finditer(line):
            tok = m.group(0)
            if is_test and FAKE_SECRET_SENTINEL.search(tok):
                continue
            findings.append(Finding("secret-pattern", loc, f"sk- token pattern ({tok[:10]}...)"))
        if RE_SECRET_GH.search(line):
            findings.append(Finding("secret-pattern", loc, "GitHub token pattern"))
        if RE_SECRET_SLACK.search(line):
            findings.append(Finding("secret-pattern", loc, "Slack token pattern"))
        if RE_SECRET_AWS.search(line):
            findings.append(Finding("secret-pattern", loc, "AWS access key pattern"))
        if RE_SECRET_PRIVKEY.search(line) and not is_self_checker:
            findings.append(Finding("secret-pattern", loc, "private key block header"))
        for m in RE_SECRET_BEARER.finditer(line):
            tok = m.group(0)
            if is_test and FAKE_SECRET_SENTINEL.search(tok):
                continue
            findings.append(Finding("secret-pattern", loc, "Bearer token literal"))
        for m in RE_SECRET_ENV_ASSIGN.finditer(line):
            val = m.group(1)
            if is_test and FAKE_SECRET_SENTINEL.search(val):
                continue
            if val.startswith(("$", "<")):
                continue
            findings.append(Finding("secret-pattern", loc, "literal *_API_KEY assignment"))

        # 2. Machine-specific paths
        if not is_self_checker:
            for m in RE_USERS_PATH.finditer(line):
                val = m.group(0)
                if (rel_path, val) in USERS_PATH_ALLOW:
                    continue
                findings.append(Finding("machine-path", loc, f"personal home path {val!r}"))
            for m in RE_VOLUMES_PATH.finditer(line):
                val = m.group(0)
                if (rel_path, val) in VOLUMES_PATH_ALLOW:
                    continue
                findings.append(Finding("machine-path", loc, f"machine volume path {val!r}"))
            if RE_PRIVATE_VAR.search(line):
                findings.append(Finding("machine-path", loc, "macOS temp path '/private/var/folders/'"))

        # 3. Emails
        if not is_self_checker and not (
            not is_commit_message and _matches_any_glob(rel_path, EMAIL_ALLOW_PATH_GLOBS)
        ):
            for m in RE_EMAIL.finditer(line):
                addr = m.group(0)
                lower = addr.lower()
                if lower.endswith(EMAIL_ALLOW_DOMAINS):
                    continue
                if (rel_path, addr) in EMAIL_ALLOW_EXACT:
                    continue
                findings.append(Finding("email", loc, f"non-example email address {addr!r}"))

        # 4. Stale monorepo paths
        if not is_self_checker:
            for m in RE_STALE_MONO_HARD.finditer(line):
                findings.append(Finding("stale-monorepo-path", loc, f"monorepo shell path {m.group(0)!r}"))
            for m in RE_STALE_MONO_SOFT.finditer(line):
                val = m.group(0)
                allow_globs = STALE_MONO_ALLOW_GLOBS.get(val, ())
                if not is_commit_message and allow_globs and _matches_any_glob(rel_path, allow_globs):
                    continue
                findings.append(Finding("stale-monorepo-path", loc, f"monorepo reference {val!r}"))

        # 5. Private machine-local deny-list (never echo the matched secret/private string in detail)
        for idx, rule in enumerate(denylist, 1):
            if not is_commit_message and rule.allow_globs and _matches_any_glob(rel_path, rule.allow_globs):
                continue
            if rule.pattern.search(line):
                findings.append(
                    Finding(
                        "private-denylist",
                        loc,
                        f"matched local deny-list rule #{idx} (term redacted from output)",
                    )
                )

    return findings


def _parse_toml_minimal(text: str) -> dict:
    """Parse TOML using stdlib tomllib (3.11+) or a minimal key-presence fallback (3.9/3.10)."""
    if tomllib is not None:
        return tomllib.loads(text)
    root: dict = {}
    current = root
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            header = line.strip("[]").strip()
            current = root
            for part in header.split("."):
                key = part.strip().strip('"').strip("'")
                current = current.setdefault(key, {})
        elif "=" in line:
            key = line.split("=", 1)[0].strip().strip('"').strip("'")
            if key:
                current[key] = True
    return root


def _has_key_path(obj: dict, key_path: list[str]) -> bool:
    cur: object = obj
    for part in key_path:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False
    return True


def check_host_owned_keys(
    repo: Path,
    *,
    read_file_fn,
    only_paths: set[str] | None = None,
) -> list[Finding]:
    """Verify PERSISTENT-GUIDANCE/config/* contains no host_owned_keys declared in hosts.json."""
    hosts_rel = "AGENT-ENGINEERING/PERSISTENT-GUIDANCE/hosts.json"
    hosts_raw = read_file_fn(hosts_rel)
    if hosts_raw is None:
        hosts_disk = repo / hosts_rel
        if not hosts_disk.is_file():
            return []
        hosts_raw = hosts_disk.read_bytes()
    try:
        hosts = json.loads(hosts_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [Finding("host-owned-key", hosts_rel, f"failed to parse hosts.json: {exc}")]

    findings: list[Finding] = []
    for proj in hosts.get("projections", []):
        hok = proj.get("host_owned_keys") or []
        src = proj.get("source")
        if not hok or not src or not src.startswith("config/"):
            continue
        rel = f"AGENT-ENGINEERING/PERSISTENT-GUIDANCE/{src}"
        if only_paths is not None and rel not in only_paths:
            continue
        raw = read_file_fn(rel)
        if raw is None:
            continue
        try:
            text = raw.decode("utf-8")
            if rel.endswith(".json"):
                parsed = json.loads(text)
            elif rel.endswith(".toml"):
                parsed = _parse_toml_minimal(text)
            else:
                continue
        except Exception as exc:  # noqa: BLE001
            findings.append(Finding("host-owned-key", rel, f"failed to parse config: {exc}"))
            continue
        if not isinstance(parsed, dict):
            continue
        for key_path in hok:
            if _has_key_path(parsed, key_path):
                dotted = ".".join(key_path)
                findings.append(
                    Finding(
                        "host-owned-key",
                        rel,
                        f"contains host-owned key '{dotted}' (declared in hosts.json)",
                    )
                )
    return findings


def run_gitleaks(repo: Path, *, mode: str, commit_range: str | None = None) -> list[Finding]:
    """Run gitleaks if installed on PATH, respecting repo .gitleaks.toml."""
    gitleaks = shutil.which("gitleaks")
    if not gitleaks:
        return []
    config_args: list[str] = []
    config_file = repo / ".gitleaks.toml"
    if config_file.is_file():
        config_args = ["--config", str(config_file)]

    if mode == "staged":
        cmd = [gitleaks, "git", "--staged", "--no-banner", "--redact", *config_args, "."]
    elif mode == "commits" and commit_range:
        cmd = [
            gitleaks,
            "git",
            f"--log-opts={commit_range}",
            "--no-banner",
            "--redact",
            *config_args,
            ".",
        ]
    elif mode == "all":
        cmd = [gitleaks, "dir", "--no-banner", "--redact", *config_args, "."]
    else:
        return []

    proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return []
    detail_lines = [
        ln.strip()
        for ln in (proc.stdout + "\n" + proc.stderr).splitlines()
        if ln.strip() and not ln.strip().startswith("○")
    ]
    summary = " | ".join(detail_lines[-6:]) if detail_lines else f"gitleaks exited {proc.returncode}"
    return [Finding("gitleaks", f"gitleaks({mode})", summary)]


def check_all(repo: Path, denylist: list[DenyRule], *, use_gitleaks: bool) -> list[Finding]:
    proc = _run_git(repo, ["ls-files", "-z"], text=False)
    if proc.returncode != 0:
        return [Finding("git-error", str(repo), proc.stderr.decode("utf-8", errors="replace").strip())]
    rel_paths = [p.decode("utf-8", errors="surrogateescape") for p in proc.stdout.split(b"\x00") if p]

    findings: list[Finding] = []
    for rel in rel_paths:
        disk_path = repo / rel
        if not disk_path.is_file() or disk_path.is_symlink():
            continue
        data = disk_path.read_bytes()
        if _is_binary(data):
            continue
        findings.extend(
            scan_text(
                data.decode("utf-8", errors="replace"),
                rel_path=rel,
                denylist=denylist,
            )
        )

    def read_disk(rel: str) -> bytes | None:
        p = repo / rel
        return p.read_bytes() if p.is_file() else None

    findings.extend(check_host_owned_keys(repo, read_file_fn=read_disk))
    if use_gitleaks:
        findings.extend(run_gitleaks(repo, mode="all"))
    return findings


def check_staged(repo: Path, denylist: list[DenyRule], *, use_gitleaks: bool) -> list[Finding]:
    proc = _run_git(repo, ["diff", "--cached", "--diff-filter=ACMR", "--name-only", "-z"], text=False)
    if proc.returncode != 0:
        return [Finding("git-error", str(repo), proc.stderr.decode("utf-8", errors="replace").strip())]
    rel_paths = [p.decode("utf-8", errors="surrogateescape") for p in proc.stdout.split(b"\x00") if p]
    if not rel_paths:
        return []

    findings: list[Finding] = []
    staged_blobs: dict[str, bytes] = {}
    for rel in rel_paths:
        blob = _run_git(repo, ["show", f":{rel}"], text=False)
        if blob.returncode != 0:
            continue
        data = blob.stdout
        staged_blobs[rel] = data
        if _is_binary(data):
            continue
        findings.extend(
            scan_text(
                data.decode("utf-8", errors="replace"),
                rel_path=rel,
                denylist=denylist,
            )
        )

    def read_staged(rel: str) -> bytes | None:
        if rel in staged_blobs:
            return staged_blobs[rel]
        p = repo / rel
        return p.read_bytes() if p.is_file() else None

    findings.extend(check_host_owned_keys(repo, read_file_fn=read_staged, only_paths=set(rel_paths)))
    if use_gitleaks:
        findings.extend(run_gitleaks(repo, mode="staged"))
    return findings


def check_commits(
    repo: Path,
    commit_range: str,
    denylist: list[DenyRule],
    *,
    use_gitleaks: bool,
) -> list[Finding]:
    revs_proc = _run_git(repo, ["rev-list", commit_range])
    if revs_proc.returncode != 0:
        return [Finding("git-error", commit_range, revs_proc.stderr.strip())]
    commits = [sha.strip() for sha in revs_proc.stdout.splitlines() if sha.strip()]
    if not commits:
        return []

    findings: list[Finding] = []
    for sha in commits:
        short = sha[:9]
        # 1. Commit message
        msg_proc = _run_git(repo, ["log", "-1", "--format=%B", sha])
        if msg_proc.returncode == 0:
            findings.extend(
                scan_text(
                    msg_proc.stdout,
                    rel_path=f"commit:{short}",
                    location_prefix=f"commit {short} message",
                    denylist=denylist,
                    is_commit_message=True,
                )
            )

        # 2. Added lines in diff
        diff_proc = _run_git(repo, ["show", "--format=", "--unified=0", "--no-color", sha], text=False)
        if diff_proc.returncode != 0:
            continue
        diff_text = diff_proc.stdout.decode("utf-8", errors="replace")
        current_file: str | None = None
        current_line = 0
        touched_paths: set[str] = set()
        for raw_line in diff_text.splitlines():
            if raw_line.startswith("+++ b/"):
                current_file = raw_line[6:]
                touched_paths.add(current_file)
            elif raw_line.startswith("+++ /dev/null"):
                current_file = None
            elif raw_line.startswith("@@ "):
                m = re.search(r"\+(\d+)", raw_line)
                current_line = int(m.group(1)) if m else 1
            elif raw_line.startswith("+") and not raw_line.startswith("+++") and current_file:
                added = raw_line[1:]
                findings.extend(
                    scan_text(
                        added,
                        rel_path=current_file,
                        location_prefix=f"{short}:{current_file}",
                        denylist=denylist,
                        start_line=current_line,
                    )
                )
                current_line += 1

        # 3. Host-owned keys on any config file touched by this commit
        def read_at_commit(rel: str, _sha: str = sha) -> bytes | None:
            blob = _run_git(repo, ["show", f"{_sha}:{rel}"], text=False)
            return blob.stdout if blob.returncode == 0 else None

        findings.extend(
            check_host_owned_keys(repo, read_file_fn=read_at_commit, only_paths=touched_paths)
        )

    if use_gitleaks:
        findings.extend(run_gitleaks(repo, mode="commits", commit_range=commit_range))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Path to the public git repository (default: repo containing this script)",
    )
    parser.add_argument("--all", action="store_true", help="Scan all tracked files in the repository")
    parser.add_argument("--staged", action="store_true", help="Scan staged files (pre-commit mode)")
    parser.add_argument(
        "--commits",
        metavar="RANGE",
        help="Scan commit messages and added diff lines in RANGE (e.g. origin/main..HEAD)",
    )
    parser.add_argument(
        "--denylist",
        type=Path,
        default=Path(os.environ.get("AGENT_SYSTEM_HYGIENE_DENYLIST", str(DEFAULT_DENYLIST))).expanduser(),
        help="Path to machine-local private deny-list file",
    )
    parser.add_argument(
        "--require-denylist",
        action="store_true",
        default=os.environ.get("AGENT_SYSTEM_REQUIRE_DENYLIST") == "1",
        help="Fail loudly if the private deny-list file is missing or empty",
    )
    parser.add_argument("--no-gitleaks", action="store_true", help="Skip invoking gitleaks even if installed")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON findings")
    args = parser.parse_args(argv)

    repo = args.repo.expanduser().resolve()
    modes = [args.all, args.staged, bool(args.commits)]
    if not any(modes):
        args.all = True

    denylist, findings = load_denylist(args.denylist, required=args.require_denylist)
    use_gitleaks = not args.no_gitleaks

    if args.all:
        findings.extend(check_all(repo, denylist, use_gitleaks=use_gitleaks))
    if args.staged:
        findings.extend(check_staged(repo, denylist, use_gitleaks=use_gitleaks))
    if args.commits:
        findings.extend(check_commits(repo, args.commits, denylist, use_gitleaks=use_gitleaks))

    if args.json:
        payload = {
            "ok": not findings,
            "denylist_loaded": args.denylist.is_file(),
            "denylist_rules": len(denylist),
            "findings": [
                {"rule": f.rule, "location": f.location, "detail": f.detail} for f in findings
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        if findings:
            print(f"public hygiene FAILED ({len(findings)} finding(s)):", file=sys.stderr)
            for finding in findings:
                print(f"  - {finding.format()}", file=sys.stderr)
        else:
            dl_note = f"{len(denylist)} local deny-list rule(s)" if denylist else "no local deny-list"
            print(f"public hygiene OK ({dl_note})")

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
