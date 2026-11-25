#!/usr/bin/env python3
"""Run a parallel wave of delegated Grok retrieval workers using the xgrok launcher.

This orchestrator manages concurrent Grok workers for multi-angle retrieval,
capturing individual logs, raw JSON responses, extracted Markdown packets, and a
consolidated execution manifest.

Examples:
    # Run against a directory of brief files:
    ./xgrok_wave.py --briefs-dir /path/to/briefs --output-dir /tmp/wave-results

    # Run specific brief files with 4 parallel workers:
    ./xgrok_wave.py brief-01.md brief-02.md --max-workers 4 --output-dir ./results

    # Dry run to inspect detected modes and execution plan:
    ./xgrok_wave.py --briefs-dir ./briefs --dry-run

    # Append one shared tail (window, method rules, return format) to every brief:
    ./xgrok_wave.py --briefs-dir ./briefs --common-tail ./common-tail.md --output-dir ./results

Before launch (and in --dry-run) every brief is validated: a macro-mode brief
must carry a "Delegated budget:" line, and no literal query may combine more
than four from: handles with keyword terms (longer combined queries silently
drop their since:/until: bounds).

A lane whose Grok session transcript shows no native X tool call is recorded as
failed, not as a thin success, and the wave stops when the first two lanes to
finish have all failed (--abort-after), since a bad login or quota fails every
lane the same way.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Any

# Projected skills are hash-tracked: no bytecode beside xgrok_roster, imported below.
sys.dont_write_bytecode = True

VALID_MODES = {"harvest", "whathappened", "list-summary", "macro", "dlresearch", "agents"}
DEFAULT_MODE = "harvest"
DEFAULT_MAX_WORKERS = 8
DEFAULT_TIMEOUT_SECONDS = 900.0
DEFAULT_STAGGER_SECONDS = 0.0

DEFAULT_ABORT_AFTER = 2
SESSION_ID_PATTERN = re.compile(r"^[0-9A-Za-z-]{8,64}$")
NO_X_CALLS_ERROR = (
    "0 native X tool calls in the worker's Grok session: the X tools were unavailable "
    "(worker login, account or quota) or the worker stopped before searching; read its packet"
)

VALID_EFFORTS = {"medium", "high"}  # low-effort workers answered without searching
VALID_SYSTEM_PROMPTS = {"lean", "default"}
MODEL_PATTERN = re.compile(r"^grok-[A-Za-z0-9.-]+$")

FRONTMATTER_DELIM_PATTERN = re.compile(r"^---\s*$")
COMMENT_SETTING_PATTERN = re.compile(
    r"^\s*(?:#|<!--)\s*([A-Za-z0-9_-]+)\s*:\s*(.+?)\s*(?:-->)?\s*$",
    re.MULTILINE,
)

# The /macro skill caps a delegated packet at six receipts / 1,500 words unless
# the parent expands it; a macro-mode brief must say so on this line.
DELEGATED_BUDGET_PATTERN = re.compile(r"^\s*(?:[-*]\s*)?\**\s*delegated budget\s*:", re.IGNORECASE | re.MULTILINE)

# Query-shape lint: roster-plus-keyword queries with more than this many
# from: handles returned out-of-window posts on 2026-09-21.
MAX_FROM_HANDLES_WITH_KEYWORDS = 4
FROM_HANDLE_PATTERN = re.compile(r"\bfrom:([A-Za-z0-9_]{1,15})\b")
QUERY_OPERATOR_PATTERN = re.compile(
    r"-?\b(?:from|to|since|until|within_time|min_faves|min_retweets|min_replies|filter"
    r"|conversation_id|quoted_tweet_id|in_reply_to_tweet_id|list|lang|url):\S+",
    re.IGNORECASE,
)
CODE_SPAN_PATTERN = re.compile(r"`([^`\n]+)`")
# A Search plan written on one line holds one query per call: "Call 1: ... Call 2: ..." (2026-10-15: four compliant
# calls read as one query with eight from: handles, and the wave was refused), "(1) ...; (2) ..." or "(A) ; (B)"
# (2026-10-19: "7 from: handles" and "27 OR terms" on lines whose queries were each fine), "1) ...; 2) ..." or "5-6)"
# after a space or ';' (2026-10-23: six briefs refused). A ';' splits only before a new query, so "...; the same
# batch with (bought OR ...)" stays one query. Never inside a code span.
CALL_SPLIT_PATTERN = re.compile(
    r"(?:\bCall \d+:|\(\d{1,2}\)(?=\s)|(?<![^\s;])\d{1,2}(?:-\d{1,2})?\)(?=\s)|;(?=\s*(?:\(|\$|\"|#|`|from:)))"
    r"(?=(?:[^`]*`[^`]*`)*[^`]*$)", re.IGNORECASE)
PAREN_OR_GROUP_PATTERN = re.compile(r"\(([^()]*\bOR\b[^()]*)\)")
KEYWORD_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9$#\"'][\w$#\"'.\-]*")
KEYWORD_STOP_WORDS = {"or", "and", "latest", "top"}
# An engagement floor on a long open OR list returned nothing on 2026-10-08 (14 terms, min_faves:5);
# the query playbook keeps a floored open query to about five terms. A list-scoped query keeps its own rule.
MAX_FLOORED_OR_TERMS = 8
FLOOR_PATTERN = re.compile(r"\bmin_(?:faves|retweets|replies):\d+", re.IGNORECASE)
SCOPE_PATTERN = re.compile(r"\b(?:from|list):\S", re.IGNORECASE)
# A one-ticker query that requires a broad macro word reads that word's other conversations (2026-10-21: "($AAPL OR
# Apple) rates" found another sense of "rates"); the company's own topic words keep the page on the company.
BROAD_TOPIC_WORDS = {"rates", "yields", "oil"}
CASHTAG_PATTERN = re.compile(r"\$[A-Za-z]{1,6}\b")
NEGATED_TERM_PATTERN = re.compile(r"(?<!\S)-\S+")


@dataclass(frozen=True)
class BriefJob:
    name: str
    brief_path: Path
    mode: str
    text: str
    effort: str | None = None
    model: str | None = None
    system_prompt: str | None = None


@dataclass(frozen=True)
class QueryFinding:
    line_no: int
    text: str
    from_count: int
    keywords: tuple[str, ...]

    @property
    def is_error(self) -> bool:
        return bool(self.keywords)

    def describe(self) -> str:
        if self.is_error:
            return (
                f"line {self.line_no}: {self.from_count} from: handles combined with keyword terms "
                f"{list(self.keywords)}; use at most {MAX_FROM_HANDLES_WITH_KEYWORDS} handles with keywords "
                f"or split roster from keywords: {self.text}"
            )
        return (
            f"line {self.line_no}: {self.from_count} from: handles on one line; if this is one OR batch, "
            f"split it (batch <= {MAX_FROM_HANDLES_WITH_KEYWORDS} under a short window; single-handle for "
            f"prolific posters or a cash-session window): {self.text}"
        )


def find_xgrok_bin(custom_path: str | None = None) -> Path:
    """Resolve the xgrok launcher binary."""
    if custom_path:
        p = Path(custom_path).expanduser().resolve()
        if p.is_file() and os.access(p, os.X_OK):
            return p
        raise FileNotFoundError(f"Specified xgrok binary not executable: {custom_path}")

    # Check same directory as this script
    script_dir = Path(__file__).resolve().parent
    local_xgrok = script_dir / "xgrok"
    if local_xgrok.is_file() and os.access(local_xgrok, os.X_OK):
        return local_xgrok

    # Check PATH
    which_path = shutil.which("xgrok")
    if which_path:
        return Path(which_path).resolve()

    # Check standard managed location
    managed_xgrok = Path.home() / ".agents" / "skills" / "xgrok" / "scripts" / "xgrok"
    if managed_xgrok.is_file() and os.access(managed_xgrok, os.X_OK):
        return managed_xgrok

    raise FileNotFoundError(
        "Could not find executable 'xgrok' launcher beside script, on PATH, or in ~/.agents/skills/xgrok/scripts/xgrok"
    )


def _normalize_setting_key(raw_key: str) -> str:
    key = raw_key.strip().lower().replace("-", "_")
    if key.startswith("xgrok_"):
        key = key[len("xgrok_"):]
    elif key.startswith("grok_"):
        key = key[len("grok_"):]
    return key


def _first_token(value: str) -> str:
    stripped = value.strip().strip("'\"").strip()
    if not stripped:
        return ""
    return stripped.split()[0].strip("'\"")


def parse_frontmatter(brief_text: str) -> dict[str, str]:
    """Parse a leading --- block of key: value lines."""
    lines = brief_text.splitlines()
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx >= len(lines):
        return {}
    first = lines[idx].lstrip("\ufeff")
    if not FRONTMATTER_DELIM_PATTERN.match(first.strip()):
        return {}
    data: dict[str, str] = {}
    for j in range(idx + 1, len(lines)):
        line = lines[j]
        if FRONTMATTER_DELIM_PATTERN.match(line.strip()):
            return data
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in line:
            continue
        raw_key, raw_value = line.split(":", 1)
        key = _normalize_setting_key(raw_key)
        token = _first_token(raw_value)
        if token and key not in data:
            data[key] = token
    return {}


def parse_comment_settings(brief_text: str) -> dict[str, str]:
    """Parse top-comment style settings (# key: value / <!-- key: value -->)."""
    data: dict[str, str] = {}
    for match in COMMENT_SETTING_PATTERN.finditer(brief_text):
        key = _normalize_setting_key(match.group(1))
        token = _first_token(match.group(2))
        if token and key not in data:
            data[key] = token
    return data


def infer_brief_mode(brief_text: str, default_mode: str = DEFAULT_MODE) -> str:
    """Infer the Grok retrieval mode from brief frontmatter or comments."""
    fm = parse_frontmatter(brief_text)
    if "mode" in fm:
        mode_candidate = fm["mode"].strip().lower()
        if mode_candidate in VALID_MODES:
            return mode_candidate

    comments = parse_comment_settings(brief_text)
    if "mode" in comments:
        mode_candidate = comments["mode"].strip().lower()
        if mode_candidate in VALID_MODES:
            return mode_candidate

    return default_mode


def infer_brief_effort(brief_text: str, default: str | None = None) -> str | None:
    """Infer the brief's stated reasoning effort, or None when unset; validate_jobs checks it."""
    fm = parse_frontmatter(brief_text)
    if "effort" in fm and fm["effort"].strip():
        return fm["effort"].strip().lower()
    comments = parse_comment_settings(brief_text)
    if "effort" in comments and comments["effort"].strip():
        return comments["effort"].strip().lower()
    return default


# Mid-scale, so "# priority: 99" means last, as a reader expects (10-20: it started before every unprioritized lane).
DEFAULT_PRIORITY = 50


def infer_brief_priority(brief_text: str) -> int | None:
    """A brief's launch priority (lower starts first), or None when unset."""
    value = parse_frontmatter(brief_text).get("priority") or parse_comment_settings(brief_text).get("priority")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"priority must be an integer, got '{value}'") from None


def launch_order(jobs: list[BriefJob]) -> list[BriefJob]:
    """JOBS by '# priority: N' (lower first), an unprioritized brief counting as DEFAULT_PRIORITY; ties keep their
    given order.

    Lanes past --max-workers queue in this order: on 10-14 the 13th of 13 lanes on 12 workers was the mood lane
    the user had asked about by name; it started last and timed out.
    """
    keyed = []
    for index, job in enumerate(jobs):
        try:
            priority = infer_brief_priority(job.text)
        except ValueError as e:
            raise ValueError(f"brief '{job.brief_path.name}': {e}") from None
        keyed.append((DEFAULT_PRIORITY if priority is None else priority, index, job))
    return [job for *_, job in sorted(keyed, key=lambda k: k[:2])]


def infer_brief_model(brief_text: str, default: str | None = None) -> str | None:
    """Infer Grok model id or None when unset."""
    fm = parse_frontmatter(brief_text)
    if "model" in fm and fm["model"].strip():
        return fm["model"].strip()
    comments = parse_comment_settings(brief_text)
    if "model" in comments and comments["model"].strip():
        return comments["model"].strip()
    return default


def infer_brief_system_prompt(brief_text: str, default: str | None = None) -> str | None:
    """Infer system-prompt profile (lean|default) or None when unset."""
    fm = parse_frontmatter(brief_text)
    if "system_prompt" in fm and fm["system_prompt"].strip():
        return fm["system_prompt"].strip().lower()
    comments = parse_comment_settings(brief_text)
    if "system_prompt" in comments and comments["system_prompt"].strip():
        return comments["system_prompt"].strip().lower()
    return default


def _manifest_field(entry: dict[str, Any], field: str) -> Any | None:
    for raw_key, value in entry.items():
        if _normalize_setting_key(str(raw_key)) == field:
            return value
    return None


def _normalize_effort_value(value: Any | None) -> str | None:
    if value is None:
        return None
    token = _first_token(str(value))
    if not token:
        return None
    return token.lower()


def _normalize_model_value(value: Any | None) -> str | None:
    if value is None:
        return None
    token = _first_token(str(value))
    return token or None


def _normalize_system_prompt_value(value: Any | None) -> str | None:
    if value is None:
        return None
    token = _first_token(str(value))
    if not token:
        return None
    return token.lower()


def collect_jobs(
    brief_paths: list[Path],
    briefs_dir: Path | None,
    manifest_file: Path | None,
    fallback_mode: str,
) -> list[BriefJob]:
    """Collect and validate all brief jobs to execute."""
    jobs: list[BriefJob] = []
    seen_names: set[str] = set()

    def add_job(
        name: str,
        path: Path,
        mode: str | None = None,
        effort: Any | None = None,
        model: Any | None = None,
        system_prompt: Any | None = None,
    ) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"Brief file does not exist: {path}")
        if path.stat().st_size == 0:
            raise ValueError(f"Brief file is empty: {path}")

        unique_name = name
        counter = 1
        while unique_name in seen_names:
            unique_name = f"{name}-{counter}"
            counter += 1
        seen_names.add(unique_name)

        text = path.read_text(encoding="utf-8")
        if not mode:
            mode = infer_brief_mode(text, fallback_mode)

        if mode not in VALID_MODES:
            raise ValueError(f"Unsupported mode '{mode}' for brief '{path.name}'. Must be one of: {sorted(VALID_MODES)}")

        if not effort:
            effort = infer_brief_effort(text)
        if not model:
            model = infer_brief_model(text)
        if not system_prompt:
            system_prompt = infer_brief_system_prompt(text)

        jobs.append(
            BriefJob(
                name=unique_name,
                brief_path=path.resolve(),
                mode=mode,
                text=text,
                effort=_normalize_effort_value(effort),
                model=_normalize_model_value(model),
                system_prompt=_normalize_system_prompt_value(system_prompt),
            )
        )

    if manifest_file:
        if not manifest_file.is_file():
            raise FileNotFoundError(f"Manifest file not found: {manifest_file}")
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        briefs_entry = manifest_data.get("briefs")
        if isinstance(briefs_entry, dict):
            for k, v in briefs_entry.items():
                if isinstance(v, dict):
                    b_path = Path(v.get("path", k))
                    if not b_path.is_absolute() and manifest_file:
                        b_path = manifest_file.parent / b_path
                    add_job(
                        k,
                        b_path,
                        _manifest_field(v, "mode"),
                        _manifest_field(v, "effort"),
                        _manifest_field(v, "model"),
                        _manifest_field(v, "system_prompt"),
                    )
                elif isinstance(v, str):
                    b_path = Path(v)
                    if not b_path.is_absolute() and manifest_file:
                        b_path = manifest_file.parent / b_path
                    add_job(k, b_path)
        elif isinstance(briefs_entry, list):
            for item in briefs_entry:
                if isinstance(item, dict):
                    b_path = Path(item["path"])
                    if not b_path.is_absolute() and manifest_file:
                        b_path = manifest_file.parent / b_path
                    add_job(
                        item.get("name", b_path.stem),
                        b_path,
                        _manifest_field(item, "mode"),
                        _manifest_field(item, "effort"),
                        _manifest_field(item, "model"),
                        _manifest_field(item, "system_prompt"),
                    )
                elif isinstance(item, str):
                    b_path = Path(item)
                    if not b_path.is_absolute() and manifest_file:
                        b_path = manifest_file.parent / b_path
                    add_job(b_path.stem, b_path)

    if briefs_dir:
        if not briefs_dir.is_dir():
            raise NotADirectoryError(f"Briefs directory not found: {briefs_dir}")
        for entry in sorted(briefs_dir.iterdir()):
            if entry.is_file() and entry.suffix in {".md", ".txt"} and not entry.name.startswith("."):
                add_job(entry.stem, entry)

    for p in brief_paths:
        add_job(p.stem, p)

    if not jobs:
        raise ValueError("No briefs provided. Specify brief files, --briefs-dir, or --manifest.")

    return jobs


def keyword_terms(query_text: str) -> list[str]:
    """Return the non-operator search terms in a query fragment (post IDs excluded)."""
    stripped = QUERY_OPERATOR_PATTERN.sub(" ", query_text)
    terms = []
    for token in KEYWORD_TOKEN_PATTERN.findall(stripped):
        bare = token.strip("\"'")
        if not bare or bare.isdigit() or bare.lower() in KEYWORD_STOP_WORDS:
            continue
        terms.append(token)
    return terms


def _lint_query(query: str, line_no: int) -> QueryFinding | None:
    from_count = len(FROM_HANDLE_PATTERN.findall(query))
    if from_count <= MAX_FROM_HANDLES_WITH_KEYWORDS:
        return None
    return QueryFinding(line_no, query.strip()[:160], from_count, tuple(keyword_terms(query)[:5]))


def lint_query_shapes(brief_text: str) -> list[QueryFinding]:
    """Find literal queries that batch too many from: handles.

    Code spans and fenced lines are checked as standalone queries. A prose line
    is checked when its from: handles sit outside code spans, because briefs
    routinely put the keyword group in backticks and the roster after it; the
    keyword group is then any non-from: code span or parenthesized OR group on
    the same line. Findings with keywords are errors; from:-only batches are
    warnings.
    """
    findings: list[QueryFinding] = []
    in_fence = False
    for line_no, line in enumerate(brief_text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            finding = _lint_query(line, line_no)
            if finding:
                findings.append(finding)
            continue
        for segment in CALL_SPLIT_PATTERN.split(line):
            line_keywords: list[str] = []
            for span in CODE_SPAN_PATTERN.findall(segment):
                if FROM_HANDLE_PATTERN.search(span):
                    finding = _lint_query(span, line_no)
                    if finding:
                        findings.append(finding)
                else:
                    line_keywords.extend(keyword_terms(span))
            remainder = CODE_SPAN_PATTERN.sub(" ", segment)
            outside_from = len(FROM_HANDLE_PATTERN.findall(remainder))
            if outside_from > MAX_FROM_HANDLES_WITH_KEYWORDS:
                for group in PAREN_OR_GROUP_PATTERN.findall(remainder):
                    line_keywords.extend(keyword_terms(group))
                findings.append(QueryFinding(line_no, segment.strip()[:160], outside_from, tuple(line_keywords[:5])))
    return findings


def brief_queries(brief_text: str) -> Iterator[tuple[int, str, bool]]:
    """(line number, query, literal) for each query a brief writes: each code span and fenced line (literal), then
    each call of a prose line with its code spans blanked."""
    in_fence = False
    for line_no, line in enumerate(brief_text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            yield line_no, line, True
            continue
        for span in CODE_SPAN_PATTERN.findall(line):
            yield line_no, span, True
        for segment in CALL_SPLIT_PATTERN.split(line):
            yield line_no, CODE_SPAN_PATTERN.sub(" ", segment), False


def lint_floored_or_lists(brief_text: str) -> list[str]:
    """Warn on a floored open query whose OR groups hold more than MAX_FLOORED_OR_TERMS terms.

    Each code span and fenced line is one query; otherwise each call of a prose line is. Open means no from: or list:
    scope. The terms are those of every parenthesized OR group in the query.
    """
    warnings: list[str] = []
    for line_no, query, _ in brief_queries(brief_text):
        if not FLOOR_PATTERN.search(query) or SCOPE_PATTERN.search(query):
            continue
        terms = sum(len(re.split(r"\s+OR\s+", group)) for group in PAREN_OR_GROUP_PATTERN.findall(query))
        if terms > MAX_FLOORED_OR_TERMS:
            warnings.append(
                f"line {line_no}: floored open query with {terms} OR terms; a floor on a long open list "
                f"returns little or nothing: keep about 5 terms, or split it into short floor-free queries: "
                f"{query.strip()[:160]}"
            )
    return warnings


def _required_broad_words(query: str) -> list[str]:
    """The broad macro words QUERY requires: a bare term, or an OR group of nothing else; a negated term is not."""
    query = NEGATED_TERM_PATTERN.sub(" ", query)
    required: list[str] = []
    for group in PAREN_OR_GROUP_PATTERN.findall(query):
        terms = {term.strip("\"'").lower() for term in keyword_terms(group)}
        if terms and terms <= BROAD_TOPIC_WORDS:
            required += sorted(terms)
    bare = (term.strip("\"'").lower() for term in keyword_terms(PAREN_OR_GROUP_PATTERN.sub(" ", query)))
    return list(dict.fromkeys(required + [term for term in bare if term in BROAD_TOPIC_WORDS]))


def lint_broad_topic_words(brief_text: str) -> list[str]:
    """Warn on a single-ticker query that requires a broad macro word (BROAD_TOPIC_WORDS). A prose call counts as a
    query only when it carries a search operator, so a sentence about a ticker and rates is not one."""
    warnings: list[str] = []
    for line_no, query, literal in brief_queries(brief_text):
        if not literal and not QUERY_OPERATOR_PATTERN.search(query):
            continue
        if len({tag.upper() for tag in CASHTAG_PATTERN.findall(query)}) != 1:
            continue
        if words := _required_broad_words(query):
            warnings.append(
                f"line {line_no}: single-ticker query requires a broad macro word ({', '.join(map(repr, words))}), "
                "which matches the word's other senses (2026-10-21: Apple with \"rates\" found another "
                f"conversation): use the company's own topic words, or none: {query.strip()[:160]}"
            )
    return warnings


def compose_brief(brief_text: str, tail_text: str, roles: str = "") -> str:
    """The brief, then its roster roles block when it has one, then the common tail, a blank line between each."""
    parts = [brief_text.rstrip("\n"), roles.strip("\n"), tail_text.strip("\n")]
    return "\n\n".join(part for part in parts if part) + "\n"


def roster_roles(brief_text: str, roster: dict) -> str:
    """A "Roster roles" block: the roster entry (registries and note) of each rostered handle the brief names, in
    order, or "" when it names none (TM, 10-20: a worker labeled @tracyalloway "off-list context" although the
    roster lists the account). ROSTER is xgrok_roster.load_roster's handle map."""
    from xgrok_roster import find_handle_mentions

    named = dict.fromkeys(handle.lower() for handle, _ in find_handle_mentions(brief_text))
    entries = [roster[handle] for handle in named if handle in roster]
    if not entries:
        return ""
    return "\n".join(["Roster roles (the roster's entry for each handle above; copy it into the receipt's Author "
                      "line instead of guessing):"]
                     + [f"- @{e.handle}: {e.registries}" + (f"; {e.note}" if e.note else "") for e in entries]) + "\n"


def validate_jobs(jobs: list[BriefJob], lint_queries: bool) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for pre-launch brief checks."""
    errors: list[str] = []
    warnings: list[str] = []
    for job in jobs:
        try:
            launch = datetime.now(timezone.utc)
            window = approved_window(job.text, launch)
            for token in re.findall(r"\buntil:([^\s`]+)", job.text):
                clock = _query_clock(token.rstrip(").,;"))
                if clock and clock > launch:
                    errors.append(f"{job.name}: literal query upper bound is in the future: {token}")
                elif clock and window and clock > _aware_clock(window["until"]):
                    errors.append(f"{job.name}: literal query widens the approved fresh cutoff: {token}")
        except ValueError as error:
            errors.append(f"{job.name}: {error}")
        if job.effort is not None and job.effort not in VALID_EFFORTS:
            errors.append(
                f"{job.name}: unsupported effort '{job.effort}'. Must be one of: {sorted(VALID_EFFORTS)}"
            )
        if job.model is not None and not MODEL_PATTERN.match(job.model):
            errors.append(
                f"{job.name}: unsupported model '{job.model}'. Must match ^grok-[A-Za-z0-9.-]+$"
            )
        if job.system_prompt is not None and job.system_prompt not in VALID_SYSTEM_PROMPTS:
            errors.append(
                f"{job.name}: unsupported system_prompt '{job.system_prompt}'. Must be one of: {sorted(VALID_SYSTEM_PROMPTS)}"
            )
        if job.mode == "macro" and not DELEGATED_BUDGET_PATTERN.search(job.text):
            errors.append(
                f"{job.name}: macro-mode brief has no 'Delegated budget:' line. The /macro skill caps a "
                "delegated packet at 6 receipts / 1,500 words unless the parent expands it; add e.g. "
                "'Delegated budget: the parent expands the /macro default to 30 receipts / 5,000 words.'"
            )
        if not lint_queries:
            continue
        for finding in lint_query_shapes(job.text):
            message = f"{job.name}: {finding.describe()}"
            (errors if finding.is_error else warnings).append(message)
        warnings.extend(f"{job.name}: {warning}" for warning in lint_floored_or_lists(job.text))
        warnings.extend(f"{job.name}: {warning}" for warning in lint_broad_topic_words(job.text))
    return errors, warnings


def session_homes(grok_home: str | None) -> list[Path]:
    """Grok homes a worker's transcript can be in: the launcher prefers ACCOUNT-xworker when it holds a login."""
    account = str(Path(grok_home or os.environ.get("GROK_HOME") or Path.home() / ".grok").expanduser()).rstrip("/")
    return [Path(f"{account}-xworker"), Path(account)]


def read_x_tool_calls(session_id: Any, homes: list[Path]) -> list[dict] | None:
    """Native X tool calls (x_*) recorded in a worker's session transcript; None when it cannot be found.

    The envelope's num_turns is 1 whether or not the worker searched, so the
    transcript's tool-call updates are the only reliable count. A call is
    "retried" when its request (the toolCallId before "_call-") had started
    before a retry_state update: the CLI retries a request whose response stream
    broke, and the retry runs its X calls again. Both attempts' calls ran, so
    both count; the worker's packet counts only the last (10-28 and 10-29: each
    of the 9 workers whose packet disagreed with execution had one such retry).
    """
    if (updates := _updates_file(session_id, homes)) is None:
        return None
    calls: dict[str, dict] = {}
    retried: set[str] = set()
    for line in updates.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        params = event.get("params") if isinstance(event, dict) else None
        update = (params.get("update") if isinstance(params, dict) else None) or {}
        if update.get("sessionUpdate") == "retry_state":
            retried |= {_request(call_id) for call_id in calls}
            continue
        raw = update.get("rawOutput") or {}
        if (update.get("sessionUpdate") == "tool_call_update" and isinstance(raw, dict)
                and str(raw.get("name", "")).startswith("x_")):
            call_id = str(update.get("toolCallId") or raw.get("call_id"))
            try:
                arguments = json.loads(raw["input"]) if isinstance(raw.get("input"), str) else raw.get("input")
            except json.JSONDecodeError:
                arguments = None
            old = calls.get(call_id, {})
            arguments = arguments if isinstance(arguments, dict) else old.get("arguments")
            stamp = event.get("timestamp")
            fetched = (datetime.fromtimestamp(stamp, timezone.utc).isoformat()
                       if update.get("status") == "completed" and isinstance(stamp, (int, float)) else
                       old.get("fetched_at"))
            calls[call_id] = {"id": call_id, "tool": raw["name"],
                              "arguments": {k: v for k, v in arguments.items() if k in
                                            {"query", "since", "until", "from_date", "to_date", "limit", "mode", "post_id", "tweet_id"}}
                              if arguments is not None else None, "fetched_at": fetched,
                              "outcome": "error" if update.get("status") == "failed" else "unknown",
                              "outcome_source": "execution-status" if update.get("status") == "failed" else
                                                "encrypted-result-unavailable"}
    return [{**call, "retried": _request(call["id"]) in retried} for call in calls.values()]


def _updates_file(session_id: Any, homes: list[Path]) -> Path | None:
    """A session's updates.jsonl in the first home holding it; None for a malformed ID or a missing transcript."""
    if not isinstance(session_id, str) or not SESSION_ID_PATTERN.match(session_id):
        return None
    return next((path for home in homes for path in (home / "sessions").glob(f"*/{session_id}/updates.jsonl")), None)


def _utc(stamp: Any) -> str | None:
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat() if isinstance(stamp, (int, float)) else None


def stream_events(session_id: Any, homes: list[Path]) -> dict[str, Any] | None:
    """The CLI's response-stream breaks (retry_state updates: when, and the reason it gives) and the transcript's last
    update time; None when the transcript cannot be found. A break before silence is an observation, not by itself
    the provider's root cause (E, 11-12: one 21:29:45 PT break hit all three lanes then running, then each streamed
    until the 900 s kill)."""
    if (updates := _updates_file(session_id, homes)) is None:
        return None
    breaks, last = [], None
    for line in updates.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        last = event.get("timestamp") if isinstance(event.get("timestamp"), (int, float)) else last
        params = event.get("params")
        update = (params.get("update") if isinstance(params, dict) else None) or {}
        if update.get("sessionUpdate") == "retry_state":
            breaks.append({"at": _utc(event.get("timestamp")), "reason": str(update.get("reason") or "")[:200]})
    return {"stream_breaks": breaks, "last_update_at": _utc(last)}


SESSION_CLOCK_SLACK = timedelta(seconds=2)  # a session's created_at against the runner's launch clock (E: +0.26 s)


def _session_prompt(session: Path) -> str:
    """The text a session was given: its user messages that the CLI did not add itself (no synthetic_reason)."""
    texts = []
    try:
        history = (session / "chat_history.jsonl").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in history.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "user" or "synthetic_reason" in entry:
            continue
        content = entry.get("content")
        texts += [content] if isinstance(content, str) else [part.get("text", "") for part in content or []
                                                             if isinstance(part, dict)]
    return "\n".join(texts)


def launched_session(homes: list[Path], request: str, started: datetime, ended: datetime) -> tuple[str | None, str]:
    """The session a lane launched when its envelope never arrived (timeout, cancellation, a crash): the one session
    in this account's homes created within the lane's launch window whose prompt carries the lane's whole request.
    (None, why) when none or several match: an ambiguous match stays unknown and is never attributed, and another
    account's homes are never searched."""
    request = request.strip()
    matches = []
    for home in homes if request else []:
        for summary in (home / "sessions").glob("*/*/summary.json"):
            try:
                created = _aware_clock(str(json.loads(summary.read_text())["created_at"]).replace("Z", "+00:00"))
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if started - SESSION_CLOCK_SLACK <= created <= ended and request in _session_prompt(summary.parent):
                matches.append(summary.parent.name)
    if len(matches) == 1:
        return matches[0], "matched: this account's session created in the launch window with the lane's whole request"
    return None, (f"ambiguous: {len(matches)} sessions in the launch window carry this request" if matches else
                  "no session in this account's homes carries this request within the launch window")


def lost_envelope_telemetry(job: BriefJob, grok_home: str | None, started: datetime,
                            ended: datetime) -> dict[str, Any]:
    """Execution counts for a lane that started but returned no envelope: its X calls and retried calls from the
    matched transcript, the stream breaks and last update, and how the session was found. Dollars stay unknown (no
    usage record arrives), and no call here is returned evidence: the lane has no packet (11-13 plan, item 12)."""
    homes = session_homes(grok_home)
    try:
        session_id, source = launched_session(homes, job.text, started, ended)
        calls = read_x_tool_calls(session_id, homes) if session_id else None
        events = stream_events(session_id, homes) if session_id else None
    except Exception as exc:  # accounting never costs the lane its record: unreadable is unknown
        session_id, source, calls, events = None, f"unreadable: {type(exc).__name__}: {exc}"[:300], None, None
    return {"session_id": session_id, "session_source": source,
            "x_tool_calls": len(calls) if calls is not None else None,
            "x_tool_calls_retried": sum(call["retried"] for call in calls) if calls is not None else None,
            "stream_breaks": events["stream_breaks"] if events else None,
            "last_update_at": events["last_update_at"] if events else None}


def query_outcomes(calls: list[dict] | None, packet: str) -> list[dict] | None:
    """Pair explicit worker-reported result outcomes to unique executed queries; completion alone proves no result."""
    if calls is None:
        return None
    reported: dict[str, list[dict]] = {}
    for line in packet.splitlines():
        if not (match := re.match(r"^- Query result:\s*(\{.*\})\s*$", line)):
            continue
        try:
            row = json.loads(match[1])
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("query"), str) and row.get("outcome") in ("returned", "error", "unknown"):
            reported.setdefault(" ".join(row["query"].split()), []).append(row)
    output = []
    for call in calls:
        query = " ".join(str((call.get("arguments") or {}).get("query", "")).split())
        matches = reported.get(query, [])
        repeats = sum(" ".join(str((c.get("arguments") or {}).get("query", "")).split()) == query
                      and not c.get("retried") for c in calls)
        if call["outcome"] == "unknown" and not call.get("retried") and len(matches) == 1 and repeats == 1:
            row = matches[0]
            outcome = row["outcome"]
            if outcome == "returned" and (type(row.get("count")) is not int or row["count"] < 0):
                outcome = "unknown"
            if row.get("error"):
                outcome = "error"
            call = {**call, "outcome": outcome, "outcome_source": "worker-reported",
                    "result_count": row.get("count") if type(row.get("count")) is int and row["count"] >= 0 else None,
                    "result_error": str(row.get("error") or "")[:300]}
        output.append(call)
    return output


def _request(call_id: str) -> str:
    """The model request a tool call belongs to: "ctc_REQUEST_call-..." gives "ctc_REQUEST"."""
    return call_id.split("_call-")[0]


def count_x_tool_calls(session_id: Any, homes: list[Path]) -> int | None:
    calls = read_x_tool_calls(session_id, homes)
    return len(calls) if calls is not None else None


def _aware_clock(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError(f"clock needs an explicit UTC offset: {value}")
    return moment


def approved_window(text: str, launch: datetime) -> dict[str, str | None] | None:
    settings = {**parse_comment_settings(text), **parse_frontmatter(text)}
    if not any(k in settings for k in ("fresh_since", "fresh_until", "context_since")):
        return None
    if "fresh_since" not in settings:
        raise ValueError("fresh_since is required with fresh_until or context_since")
    since = _aware_clock(settings["fresh_since"])
    until = _aware_clock(settings["fresh_until"]) if "fresh_until" in settings else launch
    context = _aware_clock(settings["context_since"]) if "context_since" in settings else None
    if since > until or (context and context > since):
        raise ValueError("reversed fresh/context window")
    if until > launch:
        raise ValueError("fresh upper bound is in the future at launch")
    return {"since": since.isoformat(), "until": until.isoformat(),
            "context_since": context.isoformat() if context else None}


def _query_clock(value: str) -> datetime | None:
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})_(\d{2}:\d{2}(?::\d{2})?)_(UTC|GMT|PDT|PST)", value)
    try:
        if match:
            zone = timezone(timedelta(hours={"UTC": 0, "GMT": 0, "PDT": -7, "PST": -8}[match[3]]))
            return datetime.fromisoformat(match[1] + "T" + match[2]).replace(tzinfo=zone)
        return _aware_clock(value)
    except ValueError:
        return None


def audit_query_clocks(calls: list[dict] | None, window: dict | None, launch: datetime) -> list[dict] | None:
    if calls is None:
        return None
    audited = []
    for call in calls:
        args = call["arguments"]
        bounds = dict(re.findall(r"\b(since|until):([^\s)]+)", str((args or {}).get("query", ""))))
        lower = (args or {}).get("since") or (args or {}).get("from_date") or bounds.get("since")
        upper = (args or {}).get("until") or (args or {}).get("to_date") or bounds.get("until")
        since, until = _query_clock(str(lower)) if lower else None, _query_clock(str(upper)) if upper else None
        status = "unavailable" if args is None or window is None else "unbounded"
        if window and ((lower and not since) or (upper and not until)):
            status = "unavailable-bound-clock"
        if window and since and until:
            fresh = _aware_clock(window["since"])
            end = _aware_clock(window["until"])
            context = _aware_clock(window["context_since"]) if window.get("context_since") else None
            if until > launch:
                status = "future"
            elif since > until:
                status = "reversed"
            elif until > end or (since < fresh and (not context or since < context)):
                status = "widened"
            elif since < fresh:
                status = "context-lookback"
            else:
                status = "within-approved-query-bounds"
        audited.append({**call, "sent_since": str(lower) if lower else None, "sent_until": str(upper) if upper else None,
                        "window_status": status, "silence_support": "not-established"})
    return audited


def _execute_worker(
    job: BriefJob,
    xgrok_bin: Path,
    output_dir: Path,
    timeout_seconds: float,
    grok_home: str | None = None,
    launch_path: Path | None = None,
    stop_requested: threading.Event | None = None,
) -> dict[str, Any]:
    """Execute a single xgrok worker and record its artifacts.

    ``launch_path`` is the composed brief (brief plus common tail) when a tail
    was given; otherwise the original brief file is launched.
    """
    start_time = time.time()
    launched_at = None
    log_path = output_dir / f"{job.name}.log"
    raw_json_path = output_dir / f"{job.name}-raw.json"
    packet_md_path = output_dir / f"{job.name}-packet.md"
    brief_to_launch = launch_path or job.brief_path

    cmd = [str(xgrok_bin), "--mode", job.mode]
    if grok_home:
        cmd.extend(["--grok-home", grok_home])
    cmd.append(str(brief_to_launch))
    worker_env = os.environ.copy()
    if job.effort is not None:
        worker_env["XGROK_EFFORT"] = job.effort
    if job.model is not None:
        worker_env["XGROK_MODEL"] = job.model
    if job.system_prompt is not None:
        worker_env["XGROK_SYSTEM_PROMPT"] = job.system_prompt
    sys.stderr.write(f"[{job.name}] Starting Grok worker (mode={job.mode})...\n")
    sys.stderr.flush()

    try:
        if stop_requested is not None and stop_requested.is_set():
            raise CancelledError("wave interrupted before launch")
        launched_at = datetime.now(timezone.utc).isoformat()
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env=worker_env,
        ) as process:
            try:
                deadline = time.monotonic() + timeout_seconds
                while True:
                    if stop_requested is not None and stop_requested.is_set():
                        raise CancelledError("wave interrupted")
                    remaining = max(0, deadline - time.monotonic())
                    try:
                        stdout, stderr = process.communicate(timeout=min(1, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() >= deadline:
                            raise
            except BaseException:
                # The launcher owns a Grok child; stopping only its shell leaks work.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.communicate(timeout=1)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    pass
                finally:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.communicate()
                raise
            res = subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
        elapsed = time.time() - start_time

        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(f"COMMAND: {' '.join(cmd)}\n")
            lf.write(f"RETURNCODE: {res.returncode}\n")
            lf.write(f"ELAPSED: {elapsed:.2f}s\n\n")
            lf.write(f"STDOUT:\n{res.stdout}\n\n")
            lf.write(f"STDERR:\n{res.stderr}\n")

        if res.returncode == 0 and res.stdout.strip():
            try:
                data = json.loads(res.stdout)
                with open(raw_json_path, "w", encoding="utf-8") as rf:
                    json.dump(data, rf, indent=2)

                packet_text = data.get("text", "")
                with open(packet_md_path, "w", encoding="utf-8") as pf:
                    pf.write(packet_text)

                out_tokens = data.get("usage", {}).get("output_tokens", 0)
                calls = read_x_tool_calls(data.get("sessionId"), session_homes(grok_home))
                x_calls = len(calls) if calls is not None else None
                retried = sum(call["retried"] for call in calls) if calls is not None else None
                # A packet from a worker that never searched reads like a silence finding.
                status, error = ("failed", NO_X_CALLS_ERROR) if x_calls == 0 else ("success", None)
                if error:
                    sys.stderr.write(f"[{job.name}] FAILED (0 native X tool calls; see its packet) in {elapsed:.1f}s\n")
                else:
                    sys.stderr.write(
                        f"[{job.name}] Success in {elapsed:.1f}s (tokens out: {out_tokens}, "
                        f"X calls: {'?' if x_calls is None else x_calls}"
                        f"{f', {retried} of them in a request the CLI retried' if retried else ''})\n"
                    )
                sys.stderr.flush()

                return {
                    "name": job.name,
                    "brief_path": str(job.brief_path),
                    "composed_brief_path": str(launch_path) if launch_path else None,
                    "mode": job.mode,
                    "effort": job.effort,
                    "model": job.model,
                    "system_prompt": job.system_prompt,
                    "status": status,
                    "returncode": 0,
                    "elapsed_seconds": round(elapsed, 2),
                    "packet_path": str(packet_md_path),
                    "raw_json_path": str(raw_json_path),
                    "log_path": str(log_path),
                    "usage": data.get("usage", {}),
                    "stop_reason": data.get("stopReason"),
                    "x_tool_calls": x_calls,
                    "x_tool_calls_retried": retried,
                    "error": error,
                }
            except json.JSONDecodeError as je:
                err_msg = f"JSON parse error: {je}"
                sys.stderr.write(f"[{job.name}] FAILED ({err_msg}) in {elapsed:.1f}s\n")
                sys.stderr.flush()
                return {
                    "name": job.name,
                    "brief_path": str(job.brief_path),
                    "composed_brief_path": str(launch_path) if launch_path else None,
                    "mode": job.mode,
                    "effort": job.effort,
                    "model": job.model,
                    "system_prompt": job.system_prompt,
                    "status": "failed",
                    "returncode": res.returncode,
                    "elapsed_seconds": round(elapsed, 2),
                    "packet_path": None,
                    "raw_json_path": None,
                    "log_path": str(log_path),
                    "usage": {},
                    "stop_reason": None,
                    "error": err_msg,
                }
        else:
            err_snippet = (res.stderr.strip() or res.stdout.strip())[:200]
            err_msg = f"Non-zero exit code {res.returncode}: {err_snippet}"
            sys.stderr.write(f"[{job.name}] FAILED (exit {res.returncode}) in {elapsed:.1f}s\n")
            sys.stderr.flush()
            return {
                "name": job.name,
                "brief_path": str(job.brief_path),
                "mode": job.mode,
                "effort": job.effort,
                "model": job.model,
                "system_prompt": job.system_prompt,
                "status": "failed",
                "returncode": res.returncode,
                "elapsed_seconds": round(elapsed, 2),
                "packet_path": None,
                "raw_json_path": None,
                "log_path": str(log_path),
                "usage": {},
                "stop_reason": None,
                "error": err_msg,
            }

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        err_msg = f"Timed out after {timeout_seconds}s"
        sys.stderr.write(f"[{job.name}] TIMED OUT after {elapsed:.1f}s\n")
        sys.stderr.flush()
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(f"COMMAND: {' '.join(cmd)}\n")
            lf.write(f"ERROR: {err_msg}\n")
            lf.write(f"ELAPSED: {elapsed:.2f}s\n")
        return {
            "name": job.name,
            "brief_path": str(job.brief_path),
            "composed_brief_path": str(launch_path) if launch_path else None,
            "mode": job.mode,
            "effort": job.effort,
            "model": job.model,
            "system_prompt": job.system_prompt,
            "status": "timeout",
            "returncode": -1,
            "elapsed_seconds": round(elapsed, 2),
            "packet_path": None,
            "raw_json_path": None,
            "log_path": str(log_path),
            "usage": {},
            "stop_reason": None,
            "error": err_msg,
        }

    except CancelledError as exc:
        elapsed = time.time() - start_time
        sys.stderr.write(f"[{job.name}] CANCELLED after {elapsed:.1f}s: {exc}\n")
        sys.stderr.flush()
        return {
            "name": job.name,
            "brief_path": str(job.brief_path),
            "composed_brief_path": str(launch_path) if launch_path else None,
            "mode": job.mode,
            "effort": job.effort,
            "model": job.model,
            "system_prompt": job.system_prompt,
            "status": "cancelled",
            "launched_at": launched_at,
            "returncode": -1,
            "elapsed_seconds": round(elapsed, 2),
            "packet_path": None,
            "raw_json_path": None,
            "log_path": None,
            "usage": {},
            "stop_reason": None,
            "error": str(exc),
        }

    except Exception as exc:
        elapsed = time.time() - start_time
        err_msg = f"Unexpected exception: {exc}"
        sys.stderr.write(f"[{job.name}] EXCEPTION after {elapsed:.1f}s: {exc}\n")
        sys.stderr.flush()
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(f"COMMAND: {' '.join(cmd)}\n")
            lf.write(f"EXCEPTION: {exc}\n")
            lf.write(f"ELAPSED: {elapsed:.2f}s\n")
        return {
            "name": job.name,
            "brief_path": str(job.brief_path),
            "composed_brief_path": str(launch_path) if launch_path else None,
            "mode": job.mode,
            "effort": job.effort,
            "model": job.model,
            "system_prompt": job.system_prompt,
            "status": "error",
            "returncode": -1,
            "elapsed_seconds": round(elapsed, 2),
            "packet_path": None,
            "raw_json_path": None,
            "log_path": str(log_path),
            "usage": {},
            "stop_reason": None,
            "error": err_msg,
        }


def run_single_worker(job: BriefJob, xgrok_bin: Path, output_dir: Path, timeout_seconds: float,
                      grok_home: str | None = None, launch_path: Path | None = None,
                      stop_requested: threading.Event | None = None) -> dict[str, Any]:
    launch = datetime.now(timezone.utc)
    window = approved_window(job.text, launch)
    result = _execute_worker(job, xgrok_bin, output_dir, timeout_seconds, grok_home, launch_path, stop_requested)
    calls = None
    if result.get("raw_json_path"):
        env = json.loads(Path(result["raw_json_path"]).read_text())
        calls = query_outcomes(read_x_tool_calls(env.get("sessionId"), session_homes(grok_home)), env.get("text", ""))
    elif not (result["status"] == "cancelled" and not result.get("launched_at")):  # never-started work ran nothing
        lost = lost_envelope_telemetry(job, grok_home, launch, datetime.now(timezone.utc))
        result.update(lost)
        breaks = ", ".join(b["at"][11:19] + "Z" for b in lost["stream_breaks"] or [] if b["at"])
        sys.stderr.write(f"[{job.name}] {result['status']}: "
                         + (f"{lost['x_tool_calls']} X calls ran ({lost['x_tool_calls_retried']} in a request the CLI "
                            f"retried)" + (f"; stream broke at {breaks}" if breaks else "")
                            + (f"; last update {lost['last_update_at'][11:19]}Z" if lost["last_update_at"] else "")
                            if lost["x_tool_calls"] is not None else f"X calls unknown ({lost['session_source']})")
                         + "\n")
    result.update({"launched_at": result.get("launched_at", launch.isoformat() if result["status"] != "cancelled" else None),
                   "completed_at": datetime.now(timezone.utc).isoformat(), "fresh_window": window,
                   "x_queries": audit_query_clocks(calls, window, launch)})
    fetched = [c["fetched_at"] for c in calls or [] if c["fetched_at"]]
    result["fetched_at"] = max(fetched) if fetched else None
    # The manifest waits for the slowest lane; this lane's entry is readable now (renamed into place whole).
    record = output_dir / f"{job.name}-result.json"
    staging = record.with_suffix(".json.tmp")
    staging.write_text(json.dumps(result, indent=2), encoding="utf-8")
    os.replace(staging, record)
    return result


NATIVE_PROBE_ATTEMPTS = 3  # attempts whose transcript shows no X call, before the probe refuses


def native_probe(workdir: Path, xgrok_bin: Path, grok_home: str | None) -> tuple[bool, str]:
    path = workdir / "native-probe.json"
    account = Path(grok_home or os.environ.get("GROK_HOME") or Path.home() / ".grok").expanduser().name
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "account": account,
              "launcher": os.environ.get("MKT_LAUNCHER") or "unknown/manual", "outcome": "unknown"}
    try:
        with path.open("x") as output:
            json.dump(record, output)
    except FileExistsError:
        prior = json.loads(path.read_text())
        ok = prior["account"] == account and prior["outcome"] == "returned"
        return ok, f"recorded native probe: {prior['outcome']} on {prior['account']} ({path})"
    directory = workdir / "native-probe"
    directory.mkdir(exist_ok=True)
    brief = directory / "transport.md"
    # It asks for a post ID only the tool can supply; a bare status template was often answered without a search.
    text = ('Run one x_keyword_search call now: query "from:Reuters", mode Latest, limit 1. This checks that the X '
            'search tool works; make only that call, with no retry, and do not switch accounts. Then reply with only '
            'this JSON, filled from the tool response: '
            '{"outcome":"returned|error|unknown","count":N,"post_id":"newest post ID or null","error":null}. '
            'returned: the tool responded, zero rows included. error: the tool reported an error; give its exact '
            'code/message. unknown: no tool response came back. A post ID can only come from the tool response.')
    brief.write_text(text)
    # High, not the lanes' medium: at medium the probe's one search was skipped in 5 of 22 attempts, at high in 0 of 30.
    # Only a zero-call attempt (its transcript proves it) runs again: an outage never searches.
    cost = 0.0
    for attempt in range(1, NATIVE_PROBE_ATTEMPTS + 1):
        attempt_dir = directory if attempt == 1 else directory / f"retry-{attempt - 1}"
        attempt_dir.mkdir(exist_ok=True)
        result = run_single_worker(BriefJob("transport", brief, "harvest", text, effort="high"), xgrok_bin,
                                   attempt_dir, 90, grok_home)
        if result.get("raw_json_path"):
            cost += json.loads(Path(result["raw_json_path"]).read_text()).get("total_cost_usd") or 0.0
        if result.get("x_tool_calls") != 0:
            break
    record["attempts"] = attempt
    record["worker_status"] = result["status"]
    record["calls"] = result.get("x_tool_calls")
    record["outcome_source"] = f"unmatched: no worker answer ({result['status']})"
    if result.get("raw_json_path"):
        env = json.loads(Path(result["raw_json_path"]).read_text())
        record["cost_usd"] = cost
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", env.get("text", "").strip())
        # The answer object ends the text; workers often write a sentence before it.
        match = re.search(r"\{[^{}]*\}$", content)
        try:
            answer = json.loads(match[0]) if match else {}
        except ValueError:
            answer = {}
        calls = result.get("x_queries") or []
        searched = (len(calls) == 1 and calls[0]["tool"] == "x_keyword_search"
                    and (calls[0].get("arguments") or {}).get("query") == "from:Reuters")
        answered = isinstance(answer, dict) and answer.get("outcome") in ("returned", "error", "unknown")
        # A's probe (11-12) read "matched to one executed keyword search" beside 0 calls: the source names what matched.
        record["outcome_source"] = (
            "worker-reported, matched to one executed keyword search" if result["status"] == "success" and searched
            and answered else
            f"unmatched: no X call executed in {attempt} attempt(s)" if result.get("x_tool_calls") == 0 else
            "unmatched: execution telemetry unavailable" if result.get("x_tool_calls") is None else
            f"unmatched: {len(calls)} executed X call(s), not one from:Reuters keyword search" if not searched else
            "unmatched: the answer has no outcome object")
        if record["outcome_source"].startswith("worker-reported"):
            record["outcome"] = answer["outcome"]
            record["error"] = str(answer.get("error") or "")[:300]
            record["count"] = answer.get("count")
            if record["outcome"] == "returned" and (type(record["count"]) is not int or record["count"] < 0):
                record["outcome"] = "unknown"
            if record["error"] or calls[0]["outcome"] == "error":
                record["outcome"] = "error"
    staging = path.with_suffix(".json.tmp")
    staging.write_text(json.dumps(record, indent=2) + "\n")
    os.replace(staging, path)
    return record["outcome"] == "returned", f"native probe {record['outcome']}: {record.get('error', '')} ({path})"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a concurrent wave of Grok retrieval briefs via xgrok.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "briefs",
        nargs="*",
        type=Path,
        help="One or more brief files to execute.",
    )
    parser.add_argument(
        "--briefs-dir",
        type=Path,
        default=None,
        help="Directory containing brief markdown/text files.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="JSON manifest file defining briefs and optional per-brief modes.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for logs, raw JSON, and extracted packets.",
    )
    parser.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        default=DEFAULT_MODE,
        help="Default retrieval mode for briefs that do not specify one.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="Maximum number of parallel Grok workers.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Timeout in seconds per worker.",
    )
    parser.add_argument(
        "--stagger",
        type=float,
        default=DEFAULT_STAGGER_SECONDS,
        help="Delay in seconds between the first launch and the rest, letting later workers reuse cached prefix.",
    )
    parser.add_argument(
        "--abort-after",
        type=int,
        default=DEFAULT_ABORT_AFTER,
        help="Stop the wave when the first N lanes to finish all failed (login, account, quota or missing X "
        "tools fail every lane the same way); 0 never stops early.",
    )
    parser.add_argument(
        "--xgrok-bin",
        type=str,
        default=None,
        help="Path to the xgrok binary (auto-discovered by default).",
    )
    parser.add_argument(
        "--grok-home",
        type=str,
        default=None,
        help="Custom GROK_HOME path for worker auth/state.",
    )
    account = parser.add_mutually_exclusive_group()
    account.add_argument(
        "--grok2",
        action="store_true",
        help="Route workers to the secondary Grok account (~/.grok2).",
    )
    account.add_argument(
        "--grok3",
        action="store_true",
        help="Route workers to the third Grok account (~/.grok3).",
    )
    parser.add_argument(
        "--common-tail",
        type=Path,
        default=None,
        help="Markdown file appended to every brief at launch; its sha256 is recorded in the manifest.",
    )
    parser.add_argument(
        "--no-query-lint",
        action="store_true",
        help="Skip the query-shape lint (long from: batches combined with keywords).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and show job schedule without executing.",
    )
    parser.add_argument("--transport-probe", action="store_true", help="require one recorded native search probe per workdir")
    parser.add_argument(
        "--roster",
        type=Path,
        default=Path.home() / ".grok" / "skills" / "macro" / "references" / "roster.tsv",
        help="Roster TSV whose entries the composed briefs carry as 'Roster roles' (with --common-tail).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        xgrok_bin = find_xgrok_bin(args.xgrok_bin)
    except FileNotFoundError as e:
        sys.stderr.write(f"xgrok_wave error: {e}\n")
        return 2

    try:
        jobs = launch_order(collect_jobs(args.briefs, args.briefs_dir, args.manifest, args.mode))
    except (OSError, ValueError, json.JSONDecodeError) as e:
        sys.stderr.write(f"xgrok_wave configuration error: {e}\n")
        return 2

    common_tail: dict[str, str] | None = None
    if args.common_tail:
        tail_path = args.common_tail.resolve()
        if not tail_path.is_file() or tail_path.stat().st_size == 0:
            sys.stderr.write(f"xgrok_wave configuration error: common tail missing or empty: {tail_path}\n")
            return 2
        tail_text = tail_path.read_text(encoding="utf-8")
        common_tail = {"path": str(tail_path), "sha256": hashlib.sha256(tail_text.encode("utf-8")).hexdigest()}
        from xgrok_roster import load_roster

        try:
            roster = load_roster(args.roster)
        except FileNotFoundError:
            sys.stderr.write(f"xgrok_wave warning: no roster at {args.roster}; briefs go out without roster roles\n")
            roster = {}
        except ValueError as e:
            sys.stderr.write(f"xgrok_wave configuration error: {e}\n")
            return 2
        jobs = [
            BriefJob(
                name=job.name,
                brief_path=job.brief_path,
                mode=job.mode,
                text=compose_brief(job.text, tail_text, roster_roles(job.text, roster)),
                effort=job.effort,
                model=job.model,
                system_prompt=job.system_prompt,
            )
            for job in jobs
        ]

    errors, warnings = validate_jobs(jobs, lint_queries=not args.no_query_lint)
    if queued := [job.name for job in jobs[max(1, args.max_workers):]]:
        warnings.append(
            f"{len(jobs)} lanes on {args.max_workers} workers, so {', '.join(queued)} wait for a free slot and can "
            "time out; give must-have lanes '# priority: 1' or raise --max-workers"
        )
    for warning in warnings:
        sys.stderr.write(f"xgrok_wave warning: {warning}\n")
    if errors:
        for error in errors:
            sys.stderr.write(f"xgrok_wave brief error: {error}\n")
        sys.stderr.write(f"xgrok_wave: {len(errors)} brief error(s); nothing launched.\n")
        return 2

    grok_home = args.grok_home
    if args.grok2 and not grok_home:
        grok_home = os.environ.get("GROK2_HOME", str(Path.home() / ".grok2"))
    if args.grok3 and not grok_home:
        grok_home = os.environ.get("GROK3_HOME", str(Path.home() / ".grok3"))

    if args.output_dir:
        output_dir = args.output_dir.resolve()
    else:
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_dir = Path.cwd() / f"xgrok-wave-{timestamp_str}"

    if args.dry_run:
        print("--- xgrok_wave Dry Run ---")
        print(f"xgrok launcher: {xgrok_bin}")
        if grok_home:
            print(f"GROK_HOME: {grok_home}")
        print(f"Output directory: {output_dir}")
        if common_tail:
            print(f"Common tail: {common_tail['path']} (sha256 {common_tail['sha256'][:12]})")
        print(f"Max workers: {args.max_workers}")
        print(f"Timeout: {args.timeout}s")
        print(f"Stagger: {args.stagger}s")
        print(f"Jobs ({len(jobs)} total):")
        for i, job in enumerate(jobs, 1):
            print(
                f"  {i:02d}. [{job.mode}] {job.name} -> {job.brief_path}"
                f" (effort={job.effort or '-'} model={job.model or '-'}"
                f" system_prompt={job.system_prompt or '-'})"
            )
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)

    if args.transport_probe:
        ok, note = native_probe(output_dir.parent, xgrok_bin, grok_home)
        print(note, file=sys.stderr)
        if not ok:
            refusal = note + "; no research lanes launched. Use the existing browser path; no account switching."
            (output_dir / "NOT-LAUNCHED.txt").write_text(refusal + "\n")
            return 3

    launched = output_dir / "launched.json"
    staging = launched.with_name(f".launched-{os.getpid()}.tmp")
    staging.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                                   "common_tail": common_tail}, indent=2) + "\n", encoding="utf-8")
    os.replace(staging, launched)

    launch_paths: dict[str, Path | None] = {job.name: None for job in jobs}
    if common_tail:
        composed_dir = output_dir / "composed"
        composed_dir.mkdir(exist_ok=True)
        for job in jobs:
            composed_path = composed_dir / f"{job.name}.md"
            composed_path.write_text(job.text, encoding="utf-8")
            launch_paths[job.name] = composed_path

    start_total = time.time()
    sys.stderr.write(
        f"Launching {len(jobs)} Grok retrieval workers (max concurrency: {args.max_workers})...\n"
    )
    if grok_home:
        sys.stderr.write(f"Using GROK_HOME: {grok_home}\n")
    sys.stderr.write(f"Output artifacts -> {output_dir}\n\n")
    sys.stderr.flush()

    results: list[dict[str, Any]] = []
    abort_reason: str | None = None
    stop_requested = threading.Event()
    stagger_seconds = max(0.0, float(args.stagger))

    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as executor:
        try:
            future_map: dict[Any, BriefJob] = {}
            if stagger_seconds > 0 and len(jobs) > 1:
                first_job = jobs[0]
                first_future = executor.submit(
                    run_single_worker, first_job, xgrok_bin, output_dir, args.timeout, grok_home,
                    launch_paths[first_job.name], stop_requested,
                )
                future_map[first_future] = first_job
                deadline = time.monotonic() + stagger_seconds
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    if first_future.done():
                        break
                    if stop_requested.is_set():
                        break
                    time.sleep(min(0.05, remaining))
                for job in jobs[1:]:
                    fut = executor.submit(
                        run_single_worker, job, xgrok_bin, output_dir, args.timeout, grok_home,
                        launch_paths[job.name], stop_requested,
                    )
                    future_map[fut] = job
            else:
                future_map = {
                    executor.submit(
                        run_single_worker, job, xgrok_bin, output_dir, args.timeout, grok_home,
                        launch_paths[job.name], stop_requested,
                    ): job
                    for job in jobs
                }
            for future in as_completed(future_map):
                if future.cancelled():
                    continue
                res = future.result()
                results.append(res)
                if (abort_reason is None and args.abort_after > 0 and len(results) == args.abort_after
                        and all(r["status"] != "success" for r in results)):
                    abort_reason = (
                        f"the first {args.abort_after} lanes to finish all failed "
                        f"({'; '.join(sorted({str(r['error'])[:120] for r in results}))}); "
                        "stopped the rest. Check the account (xgrok --usage, the worker home login) "
                        "before relaunching; --abort-after 0 disables this stop"
                    )
                    sys.stderr.write(f"xgrok_wave: {abort_reason}\n")
                    sys.stderr.flush()
                    stop_requested.set()
                    for queued in future_map:
                        queued.cancel()
        except KeyboardInterrupt:
            stop_requested.set()
            executor.shutdown(wait=True, cancel_futures=True)
            sys.stderr.write("xgrok_wave: interrupted; stopped active workers and cancelled queued briefs.\n")
            return 130

    total_elapsed = time.time() - start_total
    finished = {r["name"] for r in results}
    results += [
        {"name": job.name, "brief_path": str(job.brief_path), "mode": job.mode, "effort": job.effort,
         "model": job.model, "system_prompt": job.system_prompt, "status": "cancelled", "returncode": -1,
         "elapsed_seconds": 0.0, "packet_path": None, "raw_json_path": None, "log_path": None,
         "usage": {}, "stop_reason": None, "error": "never launched: the wave stopped early"}
        for job in jobs if job.name not in finished
    ]
    # Sort results to match original job ordering
    job_order = {job.name: i for i, job in enumerate(jobs)}
    results.sort(key=lambda r: job_order.get(r["name"], 9999))

    succeeded = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - succeeded

    manifest = {
        "schema_version": 2,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "xgrok_bin": str(xgrok_bin),
        "output_dir": str(output_dir),
        "common_tail": common_tail,
        "stagger_seconds": stagger_seconds,
        "total_briefs": len(jobs),
        "succeeded": succeeded,
        "failed": failed,
        "total_elapsed_seconds": round(total_elapsed, 2),
        "aborted": abort_reason,
        "workers": results,
    }

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Print summary to stdout
    print(f"\nWave execution completed in {total_elapsed:.1f}s: {succeeded}/{len(jobs)} succeeded.")
    print(f"Manifest written to: {manifest_path}\n")
    print(f"{'Name':<24} {'Mode':<12} {'Effort':<8} {'Model':<12} {'SysPrompt':<10} {'Status':<10} {'Elapsed':<10} {'Output Tokens':<14}")
    print("-" * 104)
    for r in results:
        out_tokens = r.get("usage", {}).get("output_tokens", "-")
        status_str = r["status"].upper()
        print(
            f"{r['name']:<24} {r['mode']:<12} {str(r.get('effort') or '-'):<8} {str(r.get('model') or '-'):<12} "
            f"{str(r.get('system_prompt') or '-'):<10} {status_str:<10} {r['elapsed_seconds']:<10.1f} {str(out_tokens):<14}"
        )

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
