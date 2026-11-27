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
from concurrent.futures import CancelledError, FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

# Projected skills are hash-tracked: no bytecode beside xgrok_roster, imported below.
sys.dont_write_bytecode = True

VALID_MODES = {"harvest", "whathappened", "list-summary", "macro", "dlresearch", "agents"}
DEFAULT_MODE = "harvest"
DEFAULT_MAX_WORKERS = 8
DEFAULT_TIMEOUT_SECONDS = 900.0
HEADLESS_DEADLINE_ENV = "GROK_HEADLESS_RETRY_DEADLINE_SECS"
HEADLESS_DEADLINE_FIELD = "headless_retry_deadline_secs"
DEFAULT_HEADLESS_DEADLINE_SECONDS = 600
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
    r"-?\b(?:from|to|since|until|since_time|until_time|within_time|min_faves|min_retweets|min_replies|filter"
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
# X applies these to the last term of an OR outside parentheses only (2026-11-19, DLR v7: "from:a OR ... OR from:d
# -filter:replies since:... until:..." returned the first handle's posts back to 2025).
OR_SCOPED_OPERATOR_PATTERN = re.compile(
    r"\b(?:since|until|since_time|until_time|within_time|filter|min_faves|min_retweets|min_replies|lang):\S",
    re.IGNORECASE,
)
QUOTED_PHRASE_PATTERN = re.compile(r'"[^"]*"')
TWITTER_EPOCH_MS = 1288834974657
NEAR_PRESENT_WARNING = timedelta(minutes=60)
LATE_SLICE_MAX_SPAN = timedelta(minutes=60)
LATE_SLICE_CONTROL_MAX_AGE = timedelta(minutes=30)
BOUND_TOKEN_PATTERN = re.compile(r"\b(since_time|until_time|since|until|within_time):([^\s`'\"),;/]+)", re.IGNORECASE)
PST_PDT_BOUND_PATTERN = re.compile(
    r"\b(since|until):(\d{4}-\d{2}-\d{2}_\d{2}:\d{2}(?::\d{2})?_(?:PST|PDT))\b", re.IGNORECASE
)
CANARY_FALLBACK_ORDER = "since_time:/until_time: epoch -> _UTC -> unbounded Latest post-filtered"
WINDOW_KEYS = ("fresh_since", "fresh_until", "context_since")


@dataclass(frozen=True)
class BriefJob:
    name: str
    brief_path: Path
    mode: str
    text: str
    effort: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    raw_text: str | None = None


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


def has_unscoped_or(query: str) -> bool:
    """True when QUERY has an OR outside every parenthesis and quoted phrase plus a bound or filter operator, which X
    then applies to the last OR term alone."""
    text = QUOTED_PHRASE_PATTERN.sub(" ", query)
    if not OR_SCOPED_OPERATOR_PATTERN.search(text):
        return False
    depth, top_level = 0, []
    for char in text:
        if char in "()":
            depth = depth + 1 if char == "(" else max(0, depth - 1)
            top_level.append(" ")
        else:
            top_level.append(char if depth == 0 else " ")
    return "OR" in "".join(top_level).split()


def lint_unscoped_or(brief_text: str) -> list[str]:
    """Warn on each literal query (code span or fenced line) for which has_unscoped_or holds."""
    return [
        f"line {line_no}: top-level OR with bounds or filters; X applies them to the last OR term only, so "
        f"parenthesize the OR group, as in (from:a OR from:b) since:...: {query.strip()[:160]}"
        for line_no, query, literal in brief_queries(brief_text)
        if literal and has_unscoped_or(query)
    ]


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


def snowflake_time(post_id: Any) -> datetime | None:
    """UTC timestamp decoded from a Twitter/X snowflake post ID, or None if malformed."""
    if not isinstance(post_id, str) or not re.fullmatch(r"\d{15,20}", post_id.strip()):
        return None
    ms = (int(post_id.strip()) >> 22) + TWITTER_EPOCH_MS
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _is_placeholder_bound(token: str) -> bool:
    val = token.rstrip(").,;")
    if not val or any(ch in val for ch in ("{", "}", "<", ">", "…")) or "..." in val:
        return True
    if val.upper() in {"EPOCH", "UTC", "PT", "PST", "PDT", "DATE", "TIME", "START", "END", "BOUND", "TIMESTAMP"}:
        return True
    return len(val) <= 2 and val.isalpha()


def _classify_single_bound(op: str, value: str) -> str:
    op_l = op.lower()
    val = value.rstrip(").,;")
    if op_l in ("since_time", "until_time"):
        return "epoch" if re.fullmatch(r"\d{9,11}", val) else "other"
    if op_l == "within_time":
        return "within-time"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{2}:\d{2}(?::\d{2})?_(?:UTC|GMT)", val):
        return "utc"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{2}:\d{2}(?::\d{2})?_(?:PST|PDT|PT)", val):
        return "pt"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
        return "date-only"
    try:
        _aware_clock(val)
        return "iso"
    except ValueError:
        return "other"


def classify_bound_form(
    query: str | None, args: dict[str, Any] | None = None, *, ignore_placeholders: bool = False
) -> str:
    """Classify the time-bound syntax used by QUERY/ARGS: epoch, utc, pt, date-only, within-time, iso, mixed, other, unbounded, or unavailable."""
    if query is None and args is None:
        return "unavailable"
    forms: set[str] = set()
    for op, value in BOUND_TOKEN_PATTERN.findall(query or ""):
        if ignore_placeholders and _is_placeholder_bound(value):
            continue
        forms.add(_classify_single_bound(op, value))
    if isinstance(args, dict):
        for key in ("since", "from_date", "until", "to_date"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                if ignore_placeholders and _is_placeholder_bound(val.strip()):
                    continue
                forms.add(_classify_single_bound("since", val.strip()))
    if not forms:
        return "unbounded"
    if len(forms) == 1:
        return next(iter(forms))
    return "mixed"


def pst_pdt_bounds(text: str) -> list[str]:
    """Distinct literal _PST/_PDT query bounds in TEXT (e.g. 'since:2026-11-22_00:00:00_PST')."""
    return list(dict.fromkeys(f"{op}:{val}" for op, val in PST_PDT_BOUND_PATTERN.findall(text)))


def _split_brief_and_tail(job: BriefJob) -> tuple[str, str]:
    """Return (brief_text, tail_text) for JOB, detecting appended common-tail blocks even if raw_text was omitted."""
    if job.raw_text is not None:
        prefix = job.raw_text.rstrip("\n")
        if job.text.startswith(prefix):
            return job.raw_text, job.text[len(prefix):]
        return job.raw_text, ""
    lines = job.text.splitlines(keepends=True)
    seen_window: set[str] = set()
    split_idx: int | None = None
    for idx, line in enumerate(lines):
        match = COMMENT_SETTING_PATTERN.match(line)
        if not match:
            continue
        key = _normalize_setting_key(match.group(1))
        if key in WINDOW_KEYS:
            if key in seen_window:
                split_idx = idx
                break
            seen_window.add(key)
    if split_idx is not None:
        # Walk back past a leading "Output orientation:" line that opens templates/common-tail.md.
        if split_idx > 0 and lines[split_idx - 1].strip().startswith("Output orientation:"):
            split_idx -= 1
        return "".join(lines[:split_idx]), "".join(lines[split_idx:])
    return job.text, ""


def brief_bound_forms(job: BriefJob) -> dict[str, Any]:
    """Per-call and tail bound forms for JOB so preflight can print them and detect mixed forms."""
    brief_part, tail_part = _split_brief_and_tail(job)
    calls: list[str] = []
    seen_spans: set[tuple[int, str]] = set()
    for line_no, query, literal in brief_queries(brief_part):
        if not literal and not QUERY_OPERATOR_PATTERN.search(query):
            continue
        if not BOUND_TOKEN_PATTERN.search(query) and not literal:
            continue
        norm = " ".join(query.split())
        if not norm or (line_no, norm) in seen_spans:
            continue
        seen_spans.add((line_no, norm))
        form = classify_bound_form(query, ignore_placeholders=True)
        if form != "unbounded" or FROM_HANDLE_PATTERN.search(query) or CASHTAG_PATTERN.search(query):
            calls.append(form)
    tail_line = next((line for line in tail_part.splitlines() if line.startswith("Exact query bounds:")), "")
    tail_form = classify_bound_form(tail_line, ignore_placeholders=True) if tail_line else None
    if tail_form == "unbounded":
        tail_form = None
    bounded = sorted({f for f in (*calls, tail_form) if f and f not in ("unbounded", "unavailable")})
    concrete = set()
    for f in bounded:
        if f == "mixed":
            # Recover individual forms present in the text for canary/summary visibility.
            for op, val in BOUND_TOKEN_PATTERN.findall(job.text):
                if not _is_placeholder_bound(val):
                    concrete.add(_classify_single_bound(op, val))
        else:
            concrete.add(f)
    return {
        "name": job.name,
        "calls": calls,
        "tail": tail_form,
        "forms": sorted(concrete),
        "mixed": len(concrete) > 1 or "mixed" in bounded,
    }


def format_bound_form_summary(jobs: list[BriefJob]) -> list[str]:
    """Human-readable per-brief bound-form lines for preflight/dry-run output."""
    lines: list[str] = []
    wave_forms: set[str] = set()
    for job in jobs:
        info = brief_bound_forms(job)
        wave_forms.update(info["forms"])
        if info["calls"]:
            calls_desc = ", ".join(f"call {i}={form}" for i, form in enumerate(info["calls"], 1))
        else:
            calls_desc = "no literal calls"
        tail_desc = f"; tail={info['tail']}" if info["tail"] else ""
        mixed_tag = " [MIXED]" if info["mixed"] else ""
        lines.append(f"  - {job.name}: {calls_desc}{tail_desc}{mixed_tag}")
    header = "Bound forms per brief" + (
        f" (WAVE MIXED: {', '.join(sorted(wave_forms))})" if len(wave_forms) > 1 else
        f" ({next(iter(wave_forms))})" if wave_forms else " (unbounded)"
    ) + ":"
    return [header, *lines]


def validate_jobs(
    jobs: list[BriefJob], lint_queries: bool, *, launch: datetime | None = None
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for pre-launch brief checks."""
    errors: list[str] = []
    warnings: list[str] = []
    now = launch or datetime.now(timezone.utc)
    for job in jobs:
        brief_part, tail_part = _split_brief_and_tail(job)
        brief_meta = {**parse_comment_settings(brief_part), **parse_frontmatter(brief_part)}
        brief_declares_until = "fresh_until" in brief_meta
        for bad_bound in pst_pdt_bounds(job.text):
            errors.append(
                f"{job.name}: _PST/_PDT query bound refused (broken on X native search; use _UTC or "
                f"since_time:/until_time: epoch): {bad_bound}"
            )
        try:
            window = approved_window(job.text, now, brief_text=brief_part if tail_part else job.raw_text)
            seen_near: set[str] = set()
            for segment, check_window in ((brief_part, True), (tail_part, not brief_declares_until)):
                if not segment:
                    continue
                for op, raw_token in re.findall(r"\b(until_time|until):([^\s`]+)", segment, re.IGNORECASE):
                    token = raw_token.rstrip(").,;")
                    is_epoch = op.lower() == "until_time"
                    clock = _query_clock(token, epoch=is_epoch)
                    if clock and clock > now:
                        errors.append(f"{job.name}: literal query upper bound is in the future: {token}")
                    elif check_window and clock and window and clock > _aware_clock(window["until"]):
                        errors.append(f"{job.name}: literal query widens the approved fresh cutoff: {token}")
                    elif (
                        check_window
                        and clock
                        and not is_epoch
                        and now - NEAR_PRESENT_WARNING <= clock <= now
                        and f"{op}:{token}" not in seen_near
                    ):
                        seen_near.add(f"{op}:{token}")
                        mins = int((now - clock).total_seconds() // 60)
                        warnings.append(
                            f"{job.name}: string upper bound {op}:{token} is within 60 min of launch ({mins}m ago; "
                            "near-present string bounds risk false empties — verify with bound canary or use "
                            "since_time:/until_time: epoch)"
                        )
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
        warnings.extend(f"{job.name}: {warning}" for warning in lint_unscoped_or(job.text))
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


def _window_meta_from_text(text: str) -> dict[str, str]:
    merged = {**parse_comment_settings(text), **parse_frontmatter(text)}
    return {k: merged[k] for k in WINDOW_KEYS if k in merged}


def approved_window(
    text: str, launch: datetime, *, brief_text: str | None = None
) -> dict[str, str | None] | None:
    if brief_text is not None:
        brief_meta = _window_meta_from_text(brief_text)
        prefix = brief_text.rstrip("\n")
        tail_part = text[len(prefix):] if text.startswith(prefix) else ""
        tail_meta = _window_meta_from_text(tail_part)
    else:
        lines = text.splitlines(keepends=True)
        fm_keys = set(parse_frontmatter(text).keys()) & set(WINDOW_KEYS)
        seen_window: set[str] = set(fm_keys)
        split_idx: int | None = None
        start_idx = 0
        if fm_keys:
            non_empty = next((i for i, l in enumerate(lines) if l.strip()), 0)
            if non_empty < len(lines) and FRONTMATTER_DELIM_PATTERN.match(lines[non_empty].lstrip("\ufeff").strip()):
                for j in range(non_empty + 1, len(lines)):
                    if FRONTMATTER_DELIM_PATTERN.match(lines[j].strip()):
                        start_idx = j + 1
                        break
        for idx in range(start_idx, len(lines)):
            match = COMMENT_SETTING_PATTERN.match(lines[idx])
            if not match:
                continue
            key = _normalize_setting_key(match.group(1))
            if key in WINDOW_KEYS:
                if key in seen_window:
                    split_idx = idx
                    break
                seen_window.add(key)
        if split_idx is not None:
            brief_meta = _window_meta_from_text("".join(lines[:split_idx]))
            tail_meta = _window_meta_from_text("".join(lines[split_idx:]))
        else:
            brief_meta = _window_meta_from_text(text)
            tail_meta = {}

    if not brief_meta and not tail_meta:
        return None

    if not tail_meta:
        settings = brief_meta
        if "fresh_since" not in settings:
            raise ValueError("fresh_since is required with fresh_until or context_since")
        since = _aware_clock(settings["fresh_since"])
        until = _aware_clock(settings["fresh_until"]) if "fresh_until" in settings else launch
        context = _aware_clock(settings["context_since"]) if "context_since" in settings else None
    elif not brief_meta:
        settings = tail_meta
        if "fresh_since" not in settings:
            raise ValueError("fresh_since is required with fresh_until or context_since")
        since = _aware_clock(settings["fresh_since"])
        until = _aware_clock(settings["fresh_until"]) if "fresh_until" in settings else launch
        context = _aware_clock(settings["context_since"]) if "context_since" in settings else None
    else:
        # Brief-declared harvest cutoffs deterministically override the common tail's window metadata.
        since_raw = brief_meta.get("fresh_since") or tail_meta.get("fresh_since")
        if not since_raw:
            raise ValueError("fresh_since is required with fresh_until or context_since")
        since = _aware_clock(since_raw)
        until_raw = brief_meta.get("fresh_until") or tail_meta.get("fresh_until")
        until = _aware_clock(until_raw) if until_raw else launch
        if "context_since" in brief_meta:
            context = _aware_clock(brief_meta["context_since"])
        elif "fresh_since" in brief_meta and "fresh_until" in brief_meta:
            context = None
        elif "context_since" in tail_meta:
            tail_context = _aware_clock(tail_meta["context_since"])
            context = tail_context if tail_context <= since else None
        else:
            context = None

    if since > until or (context and context > since):
        raise ValueError("reversed fresh/context window")
    if until > launch:
        raise ValueError("fresh upper bound is in the future at launch")
    return {"since": since.isoformat(), "until": until.isoformat(),
            "context_since": context.isoformat() if context else None}


def _query_clock(value: str, *, epoch: bool | None = None) -> datetime | None:
    if epoch is not False and re.fullmatch(r"\d{9,11}", value):
        sec = int(value)
        if 1_000_000_000 <= sec <= 9_999_999_999:
            return datetime.fromtimestamp(sec, timezone.utc)
        return None
    if epoch is True:
        return None
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
        query_str = str((args or {}).get("query", ""))
        bound_form = "unavailable" if args is None else classify_bound_form(query_str, args)
        raw_bounds = re.findall(r"\b(since_time|until_time|since|until):([^\s)]+)", query_str, re.IGNORECASE)
        bounds = {op.lower(): val for op, val in raw_bounds}

        lower_val = (args or {}).get("since") or (args or {}).get("from_date")
        lower_epoch = False
        if lower_val is None:
            if "since" in bounds:
                lower_val, lower_epoch = bounds["since"], False
            elif "since_time" in bounds:
                lower_val, lower_epoch = bounds["since_time"], True

        upper_val = (args or {}).get("until") or (args or {}).get("to_date")
        upper_epoch = False
        if upper_val is None:
            if "until" in bounds:
                upper_val, upper_epoch = bounds["until"], False
            elif "until_time" in bounds:
                upper_val, upper_epoch = bounds["until_time"], True

        since = _query_clock(str(lower_val), epoch=lower_epoch) if lower_val else None
        until = _query_clock(str(upper_val), epoch=upper_epoch) if upper_val else None
        status = "unavailable" if args is None or window is None else "unbounded"
        if window and ((lower_val and not since) or (upper_val and not until)):
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
        if args is not None and has_unscoped_or(query_str):
            status = "or-scope-unbounded"
        audited.append({
            **call,
            "sent_since": str(lower_val) if lower_val else None,
            "sent_until": str(upper_val) if upper_val else None,
            "bound_form": bound_form,
            "window_status": status,
            "silence_support": "not-established",
        })
    return audited


def _headless_retry_deadline(timeout_seconds: float) -> str | None:
    if HEADLESS_DEADLINE_ENV in os.environ:
        return os.environ[HEADLESS_DEADLINE_ENV]
    # The CLI accepts whole seconds and 0 disables the deadline. For a subsecond
    # (or one-second) worker timeout, the outer timer is the only suitable limit.
    if timeout_seconds > 1:
        return str(int(min(DEFAULT_HEADLESS_DEADLINE_SECONDS, max(1, timeout_seconds - 60))))
    return None


def _worker_error_detail(stdout: str, stderr: str) -> str:
    # Current Grok wraps the provider's error object in its CLI envelope's
    # message string; some builds expose error_kind/error at the top level.
    for candidate in (stdout, *reversed(stdout.splitlines())):
        try:
            envelope = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(envelope, dict):
            continue
        kind = envelope.get("error_kind")
        error = envelope.get("error")
        if not (envelope.get("type") == "error" or kind or error):
            continue
        message = envelope.get("message") or error
        details = error if isinstance(error, dict) else None
        if isinstance(message, str) and message.startswith("Internal error: "):
            try:
                inner = json.loads(message.removeprefix("Internal error: "))
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(inner, dict):
                    details = inner
        if details is not None:
            kind = kind or details.get("error_kind")
            message = details.get("message") or message
        detail = ": ".join(str(value).strip() for value in (kind, message) if value)
        if detail:
            return detail
    return ((stderr.strip() or stdout.strip()).splitlines() or [""])[-1].strip()


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
    headless_deadline = _headless_retry_deadline(timeout_seconds)
    if headless_deadline is not None:
        worker_env[HEADLESS_DEADLINE_ENV] = headless_deadline
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
            err_msg = f"Non-zero exit code {res.returncode}: {_worker_error_detail(res.stdout, res.stderr)[:200]}"
            sys.stderr.write(f"[{job.name}] FAILED ({err_msg}) in {elapsed:.1f}s\n")
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
    window = approved_window(job.text, launch, brief_text=job.raw_text)
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
PROBE_CONTAINER_KEYS = frozenset({"accounts", "bound_canaries", "bound_canary", "canary_failed", "late_slice_refreshes"})


def _account_name(grok_home: str | None) -> str:
    return Path(grok_home or os.environ.get("GROK_HOME") or Path.home() / ".grok").expanduser().name


def _load_probe_doc(path: Path) -> dict[str, Any] | None:
    """Load native-probe.json, normalizing legacy single-record files into per-account shape."""
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    doc = dict(raw)
    if "accounts" not in doc or not isinstance(doc["accounts"], dict):
        accounts: dict[str, dict[str, Any]] = {}
        if isinstance(doc.get("account"), str) and doc["account"]:
            accounts[doc["account"]] = {k: v for k, v in doc.items() if k not in PROBE_CONTAINER_KEYS}
        doc["accounts"] = accounts
    if "bound_canaries" not in doc or not isinstance(doc["bound_canaries"], dict):
        doc["bound_canaries"] = {}
    return doc


@contextmanager
def _edit_probe_doc(path: Path) -> Iterator[dict[str, Any]]:
    # Overlapping detached waves share this ledger. Lock the read-modify-write
    # only, never the Grok calls; readers always see a whole JSON document.
    with path.with_suffix(".lock").open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        doc = _load_probe_doc(path) or {"accounts": {}, "bound_canaries": {}}
        yield doc
        _write_json_atomic(path, doc)


def _extract_json_object(text: str) -> dict[str, Any]:
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    for candidate in reversed(re.findall(r"\{[^{}]*\}", content)):
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def native_probe(
    workdir: Path,
    xgrok_bin: Path,
    grok_home: str | None,
    *,
    force_refresh: bool = False,
) -> tuple[bool, str]:
    path = workdir / "native-probe.json"
    account = _account_name(grok_home)
    existing_doc = _load_probe_doc(path)
    if not force_refresh and existing_doc is not None and account in existing_doc["accounts"]:
        prior = existing_doc["accounts"][account]
        ok = prior.get("outcome") == "returned"
        return ok, f"recorded native probe: {prior.get('outcome')} on {account} ({path})"

    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "account": account,
        "launcher": os.environ.get("MKT_LAUNCHER") or "unknown/manual",
        "outcome": "unknown",
    }
    base_dir = workdir / "native-probe"
    base_dir.mkdir(exist_ok=True)
    account_dir = account.lstrip(".") or "account"
    if force_refresh:
        directory = Path(tempfile.mkdtemp(prefix=f"refresh-{account_dir}-", dir=base_dir))
        record["artifact_dir"] = str(directory.relative_to(workdir))
    else:
        directory = base_dir if not (base_dir / "transport.md").exists() else base_dir / account_dir
    directory.mkdir(exist_ok=True)
    brief = directory / "transport.md"
    # It asks for a post ID only the tool can supply; a bare status template was often answered without a search.
    text = ('Run one x_keyword_search call now: query "from:Reuters", mode Latest, limit 1. This checks that the X '
            'search tool works; make only that call, with no retry, and do not switch accounts. Then reply with only '
            'this JSON, filled from the tool response: '
            '{"outcome":"returned|error|unknown","count":N,"post_id":"newest post ID or null","error":null}. '
            'returned: the tool responded, zero rows included. error: the tool reported an error; give its exact '
            'code/message. unknown: no tool response came back. A post ID can only come from the tool response.')
    brief.write_text(text, encoding="utf-8")
    # High, not the lanes' medium: at medium the probe's one search was skipped in 5 of 22 attempts, at high in 0 of 30.
    # A startup probe may retry a verified zero-call attempt. A late-slice
    # refresh is opportunistic: make just one attempt, even after a skipped call.
    cost = 0.0
    attempt_limit = 1 if force_refresh else NATIVE_PROBE_ATTEMPTS
    for attempt in range(1, attempt_limit + 1):
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
        answer = _extract_json_object(env.get("text", ""))
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
            raw_pid = answer.get("post_id")
            pid_str = str(raw_pid).strip() if isinstance(raw_pid, (str, int)) and not isinstance(raw_pid, bool) else ""
            if pid_str and snowflake_time(pid_str) is not None:
                record["post_id"] = pid_str
                record["post_created_at"] = snowflake_time(pid_str).isoformat()
            if record["outcome"] == "returned" and (type(record["count"]) is not int or record["count"] < 0):
                record["outcome"] = "unknown"
            if record["error"] or calls[0]["outcome"] == "error":
                record["outcome"] = "error"

    with _edit_probe_doc(path) as doc:
        if force_refresh:
            # A failed refresh must not poison the startup probe for the
            # same-account unbounded Latest fallback.
            doc.setdefault("late_slice_refreshes", []).append(record)
        else:
            if "account" not in doc:
                doc.update(record)
            doc["accounts"][account] = record
    reason = record.get("error") or (record["outcome_source"] if record["outcome"] != "returned" else "")
    return record["outcome"] == "returned", (
        f"native {'refresh' if force_refresh else 'probe'} {record['outcome']} on {account}: {reason} ({path})"
    )


def _is_late_slice_wave(jobs: list[BriefJob], launch: datetime) -> bool:
    """True when every windowed job in JOBS declares a short (<=60m) near-present slice."""
    windows = []
    for job in jobs:
        brief_part, tail_part = _split_brief_and_tail(job)
        try:
            win = approved_window(job.text, launch, brief_text=brief_part if tail_part else job.raw_text)
        except ValueError:
            win = None
        if win:
            windows.append(win)
    if not windows:
        return False
    for win in windows:
        since = _aware_clock(win["since"])
        until = _aware_clock(win["until"])
        if until - since > LATE_SLICE_MAX_SPAN or launch - until > NEAR_PRESENT_WARNING:
            return False
    return True


def _find_canary_control(
    workdir: Path,
    doc: dict[str, Any] | None,
    account: str,
    launch: datetime,
    max_age: timedelta | None = None,
) -> tuple[str, str, datetime] | None:
    """Find (author, post_id, created_at) for the bound canary: transport probe's Reuters post first, then hydrated/*.json."""
    if doc:
        accounts_map = doc.get("accounts") if isinstance(doc.get("accounts"), dict) else {}
        candidates = []
        if max_age is not None:
            candidates.extend(
                rec for rec in reversed(doc.get("late_slice_refreshes", []))
                if rec.get("account") == account and rec.get("outcome") == "returned"
            )
        if account in accounts_map:
            candidates.append(accounts_map[account])
        elif doc.get("account") == account:
            candidates.append(doc)
        for other_acct, rec in accounts_map.items():
            if other_acct != account:
                candidates.append(rec)
        for acct in candidates:
            if not isinstance(acct, dict):
                continue
            raw_pid = acct.get("post_id")
            pid_str = str(raw_pid).strip() if isinstance(raw_pid, (str, int)) and not isinstance(raw_pid, bool) else ""
            created = snowflake_time(pid_str) if pid_str else None
            if created is not None and created <= launch and (max_age is None or launch - created < max_age):
                return ("Reuters", pid_str, created)
    hydrated_dir = workdir / "hydrated"
    best: tuple[datetime, str, str] | None = None
    if hydrated_dir.is_dir():
        for path in sorted(hydrated_dir.glob("*.json")):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(item, dict):
                continue
            pid = str(item.get("id_str") or item.get("id") or path.stem).strip()
            created = snowflake_time(pid)
            if created is None or created > launch:
                continue
            if max_age is not None and launch - created >= max_age:
                continue
            user = item.get("user") if isinstance(item.get("user"), dict) else {}
            author = str(user.get("screen_name") or item.get("author") or item.get("handle") or "").lstrip("@").strip()
            if not author or not re.fullmatch(r"[A-Za-z0-9_]{1,15}", author):
                continue
            if best is None or created > best[0]:
                best = (created, author, pid)
    if best is not None:
        return (best[1], best[2], best[0])
    return None


def _format_canary_query(author: str, created_at: datetime, launch: datetime, bound_form: str, is_late: bool) -> str:
    lo = created_at - timedelta(minutes=5)
    hi = launch if is_late else min(launch, created_at + timedelta(minutes=5))
    if hi < created_at:
        hi = created_at
    if bound_form == "epoch":
        return f"from:{author} since_time:{int(lo.timestamp())} until_time:{int(hi.timestamp())}"
    if bound_form == "date-only":
        return f"from:{author} since:{lo:%Y-%m-%d} until:{(hi + timedelta(days=1)):%Y-%m-%d}"
    return f"from:{author} since:{lo:%Y-%m-%d_%H:%M:%S}_UTC until:{hi:%Y-%m-%d_%H:%M:%S}_UTC"


def _record_bound_canary(path: Path, key: str, entry: dict[str, Any]) -> None:
    with _edit_probe_doc(path) as doc:
        doc["bound_canaries"][key] = entry
        doc["bound_canary"] = entry
        doc["canary_failed"] = entry["canary_failed"]


def bound_canary(
    workdir: Path,
    xgrok_bin: Path,
    grok_home: str | None,
    jobs: list[BriefJob],
    *,
    late_slice: bool = False,
    now: datetime | None = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Run a 1-call bound canary per wave bound form against a known-positive post before lane fan-out.

    Returns (ok, message, summary_dict_or_None). Unbounded waves skip the canary and return (True, '', None).
    """
    forms_to_test: list[str] = []
    for job in jobs:
        for form in brief_bound_forms(job)["forms"]:
            if form not in ("unbounded", "unavailable") and form not in forms_to_test:
                forms_to_test.append(form)
    if not forms_to_test:
        return True, "", None

    launch = now or datetime.now(timezone.utc)
    is_late = late_slice or _is_late_slice_wave(jobs, launch)
    slice_kind = "late-slice" if is_late else "normal"
    account = _account_name(grok_home)
    path = workdir / "native-probe.json"
    doc = _load_probe_doc(path) or {"accounts": {}, "bound_canaries": {}}
    last_entry: dict[str, Any] | None = None
    control_reason = "no known-positive in-window control post available for bound canary"
    control = (
        _find_canary_control(workdir, doc, account, launch, LATE_SLICE_CONTROL_MAX_AGE) if is_late else None
    )
    if is_late and control is None:
        refreshed, refresh_note = native_probe(workdir, xgrok_bin, grok_home, force_refresh=True)
        print(refresh_note, file=sys.stderr)
        if refreshed:
            launch = now or datetime.now(timezone.utc)
            control = _find_canary_control(workdir, _load_probe_doc(path), account, launch, LATE_SLICE_CONTROL_MAX_AGE)
            control_reason = "late-slice bound canary found no <30m known-positive control post after one refresh"
        else:
            control_reason = f"late-slice bound canary control refresh failed: {refresh_note}"

    for form in forms_to_test:
        key = f"{account}|{form}|{slice_kind}"
        if slice_kind == "normal" and key in doc["bound_canaries"]:
            prior = doc["bound_canaries"][key]
            last_entry = prior
            if prior.get("outcome") == "passed":
                continue
            return False, (
                f"recorded bound canary failed ({form}, {slice_kind}) on {account}: {prior.get('error', '')}; "
                f"fallback order: {CANARY_FALLBACK_ORDER} ({path})"
            ), prior

        if control is None and not is_late:
            control = _find_canary_control(workdir, doc, account, launch)
        if control is None:
            entry: dict[str, Any] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "account": account,
                "bound_form": form,
                "slice_kind": slice_kind,
                "outcome": "canary_failed",
                "canary_failed": True,
                "control_post_id": None,
                "control_author": None,
                "control_created_at": None,
                "query": None,
                "matched_post_id": False,
                "count": None,
                "attempts": 0,
                "calls": 0,
                "cost_usd": 0.0,
                "error": control_reason,
            }
            _record_bound_canary(path, key, entry)
            return False, (
                f"bound canary failed ({form}, {slice_kind}) on {account}: {control_reason}; "
                f"fallback order: {CANARY_FALLBACK_ORDER} ({path})"
            ), entry

        author, control_pid, control_created = control
        canary_query = _format_canary_query(author, control_created, launch, form, is_late)
        directory = workdir / "native-probe" / f"canary-{account.lstrip('.') or 'account'}-{form}-{slice_kind}"
        directory.mkdir(parents=True, exist_ok=True)
        brief = directory / "bound-canary.md"
        text = (
            f'Run one x_keyword_search call now with this exact query: "{canary_query}", mode Latest, limit 10. '
            f'This verifies that the wave\'s {form} time-bound syntax returns known in-window post {control_pid} '
            f'by @{author}. Make only that call, with no retry, and do not alter the bound syntax. '
            'Then reply with only this JSON filled from the tool response: '
            '{"outcome":"returned|error|unknown","count":N,"matched_post_id":true|false,"post_ids":["..."],"error":null}.'
        )
        brief.write_text(text, encoding="utf-8")
        cost = 0.0
        for attempt in range(1, NATIVE_PROBE_ATTEMPTS + 1):
            attempt_dir = directory if attempt == 1 else directory / f"retry-{attempt - 1}"
            attempt_dir.mkdir(exist_ok=True)
            result = run_single_worker(
                BriefJob("bound-canary", brief, "harvest", text, effort="high"),
                xgrok_bin, attempt_dir, 90, grok_home,
            )
            if result.get("raw_json_path"):
                cost += json.loads(Path(result["raw_json_path"]).read_text()).get("total_cost_usd") or 0.0
            if result.get("x_tool_calls") != 0:
                break

        answer: dict[str, Any] = {}
        if result.get("raw_json_path"):
            env = json.loads(Path(result["raw_json_path"]).read_text())
            answer = _extract_json_object(env.get("text", ""))
        calls = result.get("x_queries") or []
        searched = (
            len(calls) == 1
            and calls[0]["tool"] == "x_keyword_search"
            and " ".join(str((calls[0].get("arguments") or {}).get("query", "")).split()) == " ".join(canary_query.split())
        )
        returned_ids = [str(x).strip() for x in (answer.get("post_ids") or []) if isinstance(x, (str, int))]
        count = answer.get("count") if type(answer.get("count")) is int and answer.get("count") >= 0 else None
        matched = (
            result["status"] == "success"
            and searched
            and answer.get("outcome") == "returned"
            and not answer.get("error")
            and calls[0]["outcome"] != "error"
            and (answer.get("matched_post_id") is True or control_pid in returned_ids)
            and (count is None or count > 0)
        )
        err = ""
        if not matched:
            if answer.get("error"):
                err = str(answer["error"])[:300]
            elif not searched:
                err = f"unmatched: worker did not execute the exact {form} canary query"
            else:
                err = f"control post {control_pid} (@{author}) missed under {form} bound (count={count})"
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "account": account,
            "bound_form": form,
            "slice_kind": slice_kind,
            "outcome": "passed" if matched else "canary_failed",
            "canary_failed": not matched,
            "control_post_id": control_pid,
            "control_author": author,
            "control_created_at": control_created.isoformat(),
            "query": canary_query,
            "matched_post_id": bool(matched),
            "count": count,
            "attempts": attempt,
            "calls": result.get("x_tool_calls"),
            "cost_usd": cost,
            "error": err,
        }
        _record_bound_canary(path, key, entry)
        last_entry = entry
        if not matched:
            return False, (
                f"bound canary failed ({form}, {slice_kind}) on {account}: {err}; "
                f"fallback order: {CANARY_FALLBACK_ORDER} ({path})"
            ), entry

    return True, f"bound canary passed ({', '.join(forms_to_test)}, {slice_kind}) on {account} ({path})", last_entry


def _process_start(pid: int) -> str:
    found = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, check=False)
    return " ".join(found.stdout.split())


def _pid_alive(pid: int, expected_lstart: str = "") -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    if expected_lstart:
        actual = _process_start(pid)
        return bool(actual) and actual == expected_lstart
    return True


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    staging = path.with_name(f".{path.name}-{os.getpid()}.tmp")
    staging.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(staging, path)


def _extract_session_assistant(session: Path) -> tuple[str, bool, str | None]:
    """Extract (assistant_text, turn_completed, completed_at_iso) from a Grok session directory."""
    turn_completed = False
    completed_at: str | None = None
    updates_path = session / "updates.jsonl"
    if updates_path.is_file():
        for line in updates_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            params = event.get("params")
            update = (params.get("update") if isinstance(params, dict) else None) or {}
            if update.get("sessionUpdate") == "turn_completed":
                turn_completed = True
                completed_at = _utc(event.get("timestamp")) or completed_at
    assistant_texts: list[str] = []
    history_path = session / "chat_history.jsonl"
    if history_path.is_file():
        for line in history_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict) or entry.get("type") != "assistant":
                continue
            content = entry.get("content")
            if isinstance(content, str) and content.strip():
                assistant_texts.append(content)
            elif isinstance(content, list):
                joined = "".join(part.get("text", "") for part in content if isinstance(part, dict))
                if joined.strip():
                    assistant_texts.append(joined)
    return (assistant_texts[-1] if assistant_texts else ""), turn_completed, completed_at


def _find_session_dir(session_id: str, homes: list[Path]) -> Path | None:
    if not isinstance(session_id, str) or not SESSION_ID_PATTERN.match(session_id):
        return None
    for home in homes:
        for path in (home / "sessions").glob(f"*/{session_id}"):
            if path.is_dir():
                return path
    return None


def status_wave(wave_dir: Path) -> dict[str, Any]:
    """Inspect a wave directory and report its runner liveness, progress, and outcome."""
    wave_dir = wave_dir.resolve()
    if not wave_dir.is_dir():
        raise FileNotFoundError(f"Wave directory not found: {wave_dir}")
    refusal_path = wave_dir / "NOT-LAUNCHED.txt"
    manifest_path = wave_dir / "manifest.json"
    runner_path = wave_dir / "runner.json"
    launched_path = wave_dir / "launched.json"

    runner = json.loads(runner_path.read_text(encoding="utf-8")) if runner_path.is_file() else {}
    launched = json.loads(launched_path.read_text(encoding="utf-8")) if launched_path.is_file() else {}
    finished_results = sorted(wave_dir.glob("*-result.json"))
    composed = sorted((wave_dir / "composed").glob("*.md")) if (wave_dir / "composed").is_dir() else []
    total = (
        len(launched.get("briefs") or [])
        or len(runner.get("briefs") or [])
        or len(composed)
        or len(finished_results)
    )

    if refusal_path.is_file() and not manifest_path.is_file():
        return {
            "wave_dir": str(wave_dir),
            "state": "refused",
            "reason": refusal_path.read_text(encoding="utf-8", errors="replace").strip(),
            "finished": len(finished_results),
            "total": total,
        }
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        state = "recovered" if manifest.get("recovery") else "done"
        return {
            "wave_dir": str(wave_dir),
            "state": state,
            "succeeded": manifest.get("succeeded"),
            "failed": manifest.get("failed"),
            "total": manifest.get("total_briefs"),
            "aborted": manifest.get("aborted"),
            "timestamp": manifest.get("timestamp"),
        }
    pid = runner.get("pid")
    lstart = runner.get("lstart", "")
    if isinstance(pid, int) and _pid_alive(pid, lstart):
        return {
            "wave_dir": str(wave_dir),
            "state": "running",
            "pid": pid,
            "started_at": runner.get("started_at"),
            "finished": len(finished_results),
            "total": total,
            "log_path": runner.get("log_path"),
        }
    return {
        "wave_dir": str(wave_dir),
        "state": "interrupted",
        "pid": pid,
        "started_at": runner.get("started_at") or launched.get("timestamp"),
        "finished": len(finished_results),
        "total": total,
        "hint": f"xgrok_wave.py recover {wave_dir}",
    }


def recover_wave(
    wave_dir: Path,
    grok_home: str | None = None,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Recover an interrupted wave from native Grok session transcripts without launching any new Grok calls.

    Reuses launched_session(), assistant-text extraction, query_outcomes(), and audit_query_clocks().
    Missing dollar costs are explicitly marked 'unavailable' (never $0).
    """
    wave_dir = wave_dir.resolve()
    if not wave_dir.is_dir():
        raise FileNotFoundError(f"Wave directory not found: {wave_dir}")
    manifest_path = wave_dir / "manifest.json"
    if manifest_path.is_file() and not overwrite:
        raise FileExistsError(f"{manifest_path} already exists; pass --overwrite to re-recover")

    runner_path = wave_dir / "runner.json"
    runner = json.loads(runner_path.read_text(encoding="utf-8")) if runner_path.is_file() else {}
    pid = runner.get("pid")
    if isinstance(pid, int) and _pid_alive(pid, runner.get("lstart", "")):
        raise RuntimeError(f"wave runner pid {pid} is still running; wait for it to finish before recovering")

    launched_path = wave_dir / "launched.json"
    launched = json.loads(launched_path.read_text(encoding="utf-8")) if launched_path.is_file() else {}
    common_tail = launched.get("common_tail")
    effective_home = grok_home or runner.get("grok_home") or launched.get("grok_home")
    homes = session_homes(effective_home)

    launch_ts = launched.get("timestamp") or runner.get("started_at")
    if launch_ts:
        launch_dt = _aware_clock(str(launch_ts).replace("Z", "+00:00"))
    else:
        composed_files = sorted((wave_dir / "composed").glob("*.md")) if (wave_dir / "composed").is_dir() else []
        if composed_files:
            launch_dt = datetime.fromtimestamp(min(p.stat().st_mtime for p in composed_files), timezone.utc)
        else:
            launch_dt = datetime.now(timezone.utc)
    now_dt = datetime.now(timezone.utc)

    # Discover all lanes in the wave from launched/runner metadata, composed briefs, and existing results.
    lane_meta: dict[str, dict[str, Any]] = {}
    for entry in (launched.get("briefs") or runner.get("briefs") or []):
        if isinstance(entry, dict) and entry.get("name"):
            lane_meta[entry["name"]] = dict(entry)
    composed_dir = wave_dir / "composed"
    if composed_dir.is_dir():
        for path in sorted(composed_dir.glob("*.md")):
            lane_meta.setdefault(path.stem, {"name": path.stem})
            lane_meta[path.stem]["composed_brief_path"] = str(path)
    for res_path in sorted(wave_dir.glob("*-result.json")):
        name = res_path.name.removesuffix("-result.json")
        lane_meta.setdefault(name, {"name": name})

    if not lane_meta:
        raise ValueError(f"no composed briefs, launched metadata, or lane results found in {wave_dir}")

    workers: list[dict[str, Any]] = []
    existing_lanes: list[str] = []
    recovered_lanes: list[str] = []
    unmatched_lanes: list[str] = []

    for name in sorted(lane_meta):
        meta = lane_meta[name]
        existing_result = wave_dir / f"{name}-result.json"
        if existing_result.is_file():
            row = json.loads(existing_result.read_text(encoding="utf-8"))
            if row.get("x_queries") is not None and any(
                q.get("window_status") is None or "bound_form" not in q for q in row["x_queries"]
            ):
                win = row.get("fresh_window")
                l_dt = _aware_clock(str(row["launched_at"]).replace("Z", "+00:00")) if row.get("launched_at") else launch_dt
                row["x_queries"] = audit_query_clocks(row["x_queries"], win, l_dt)
                _write_json_atomic(existing_result, row)
            workers.append(row)
            existing_lanes.append(name)
            continue

        composed_path = Path(meta["composed_brief_path"]) if meta.get("composed_brief_path") else None
        brief_path = Path(meta["brief_path"]) if meta.get("brief_path") else None
        request_text = ""
        if composed_path and composed_path.is_file():
            request_text = composed_path.read_text(encoding="utf-8")
        elif brief_path and brief_path.is_file():
            request_text = brief_path.read_text(encoding="utf-8")

        raw_brief_text = brief_path.read_text(encoding="utf-8") if brief_path and brief_path.is_file() else None
        try:
            window = approved_window(request_text, launch_dt, brief_text=raw_brief_text)
        except ValueError:
            window = None

        mode = meta.get("mode") or infer_brief_mode(request_text, DEFAULT_MODE)
        effort = meta.get("effort") or infer_brief_effort(request_text)
        model = meta.get("model") or infer_brief_model(request_text)
        system_prompt = meta.get("system_prompt") or infer_brief_system_prompt(request_text)

        session_id, source = launched_session(homes, request_text, launch_dt, now_dt)
        if not session_id:
            unmatched_lanes.append(name)
            row = {
                "name": name,
                "brief_path": str(brief_path) if brief_path else None,
                "composed_brief_path": str(composed_path) if composed_path else None,
                "mode": mode,
                "effort": effort,
                "model": model,
                "system_prompt": system_prompt,
                "status": "failed",
                "returncode": -1,
                "elapsed_seconds": None,
                "packet_path": None,
                "raw_json_path": None,
                "log_path": str(wave_dir / f"{name}.log") if (wave_dir / f"{name}.log").is_file() else None,
                "usage": {},
                "cost_usd": "unavailable",
                "stop_reason": None,
                "x_tool_calls": None,
                "x_tool_calls_retried": None,
                "error": f"recovery failed: {source}",
                "session_id": None,
                "session_source": source,
                "launched_at": launch_dt.isoformat(),
                "completed_at": None,
                "fetched_at": None,
                "fresh_window": window,
                "x_queries": None,
                "recovered": True,
            }
            _write_json_atomic(existing_result, row)
            workers.append(row)
            continue

        session_dir = _find_session_dir(session_id, homes)
        packet_text, turn_completed, completed_at = (
            _extract_session_assistant(session_dir) if session_dir else ("", False, None)
        )
        created_dt = launch_dt
        created_at = launch_dt.isoformat()
        if session_dir and (session_dir / "summary.json").is_file():
            try:
                created_dt = _aware_clock(
                    str(json.loads((session_dir / "summary.json").read_text())["created_at"]).replace("Z", "+00:00")
                )
                created_at = created_dt.isoformat()
            except (OSError, ValueError, KeyError, TypeError):
                pass

        raw_calls = read_x_tool_calls(session_id, homes)
        events = stream_events(session_id, homes)
        calls = query_outcomes(raw_calls, packet_text) if packet_text else raw_calls
        audited = audit_query_clocks(calls, window, max(launch_dt, created_dt))
        x_calls = len(calls) if calls is not None else None
        retried = sum(call["retried"] for call in calls) if calls is not None else None
        fetched = [c["fetched_at"] for c in calls or [] if c.get("fetched_at")]

        packet_md_path = wave_dir / f"{name}-packet.md"
        raw_json_path = wave_dir / f"{name}-raw.json"
        stop_reason = (
            "recovered: turn_completed in native session transcript"
            if turn_completed
            else "recovered: assistant message in native session transcript"
            if packet_text
            else "recovered: incomplete session without assistant message"
        )

        if packet_text:
            packet_md_path.write_text(packet_text, encoding="utf-8")
            _write_json_atomic(
                raw_json_path,
                {
                    "text": packet_text,
                    "sessionId": session_id,
                    "stopReason": stop_reason,
                    "usage": {},
                    "total_cost_usd": None,
                    "cost_usd": "unavailable",
                    "recovered": True,
                },
            )
            if x_calls == 0:
                status, error, rc = "failed", NO_X_CALLS_ERROR, 0
            else:
                status, error, rc = "success", None, 0
        else:
            status, error, rc = "failed", "recovered session has no completed assistant response", -1

        recovered_lanes.append(name)
        row = {
            "name": name,
            "brief_path": str(brief_path) if brief_path else None,
            "composed_brief_path": str(composed_path) if composed_path else None,
            "mode": mode,
            "effort": effort,
            "model": model,
            "system_prompt": system_prompt,
            "status": status,
            "returncode": rc,
            "elapsed_seconds": None,
            "packet_path": str(packet_md_path) if packet_text else None,
            "raw_json_path": str(raw_json_path) if packet_text else None,
            "log_path": str(wave_dir / f"{name}.log") if (wave_dir / f"{name}.log").is_file() else None,
            "usage": {},
            "cost_usd": "unavailable",
            "stop_reason": stop_reason,
            "x_tool_calls": x_calls,
            "x_tool_calls_retried": retried,
            "stream_breaks": events["stream_breaks"] if events else None,
            "last_update_at": events["last_update_at"] if events else None,
            "error": error,
            "session_id": session_id,
            "session_source": source,
            "launched_at": created_at,
            "completed_at": completed_at or (events["last_update_at"] if events else None),
            "fetched_at": max(fetched) if fetched else None,
            "fresh_window": window,
            "x_queries": audited,
            "recovered": True,
        }
        _write_json_atomic(existing_result, row)
        workers.append(row)

    succeeded = sum(1 for r in workers if r["status"] == "success")
    failed = len(workers) - succeeded
    manifest = {
        "schema_version": 2,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(wave_dir),
        "common_tail": common_tail,
        "total_briefs": len(workers),
        "succeeded": succeeded,
        "failed": failed,
        "aborted": None,
        "recovery": {
            "recovered_at": datetime.now(timezone.utc).isoformat(),
            "grok_home": str(effective_home) if effective_home else None,
            "recovered_lanes": recovered_lanes,
            "existing_lanes": existing_lanes,
            "unmatched_lanes": unmatched_lanes,
            "cost_usd": "unavailable",
        },
        "workers": workers,
    }
    if HEADLESS_DEADLINE_FIELD in runner:
        manifest[HEADLESS_DEADLINE_FIELD] = runner[HEADLESS_DEADLINE_FIELD]
    _write_json_atomic(manifest_path, manifest)
    return manifest


def _resolve_grok_home(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Resolve account home from CLI args, failing loudly on empty GROK2_HOME/GROK3_HOME."""
    if getattr(args, "grok_home", None) == "":
        return None, "--grok-home requires a non-empty path"
    if getattr(args, "grok_home", None):
        return args.grok_home, None
    if getattr(args, "grok2", False):
        if "GROK2_HOME" in os.environ and os.environ["GROK2_HOME"] == "":
            return None, "GROK2_HOME is set but empty; unset it or set a valid path"
        return os.environ.get("GROK2_HOME") or str(Path.home() / ".grok2"), None
    if getattr(args, "grok3", False):
        if "GROK3_HOME" in os.environ and os.environ["GROK3_HOME"] == "":
            return None, "GROK3_HOME is set but empty; unset it or set a valid path"
        return os.environ.get("GROK3_HOME") or str(Path.home() / ".grok3"), None
    return None, None


def status_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="xgrok_wave.py status", description="Check a wave's status and runner PID.")
    parser.add_argument("wave_dir", type=Path, help="Wave output directory.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON status.")
    args = parser.parse_args(argv)
    try:
        info = status_wave(args.wave_dir)
    except FileNotFoundError as exc:
        sys.stderr.write(f"xgrok_wave status error: {exc}\n")
        return 2
    if args.as_json:
        print(json.dumps(info, indent=2))
        return 0
    state = info["state"]
    if state in ("done", "recovered"):
        aborted = f", aborted: {info['aborted']}" if info.get("aborted") else ""
        print(f"wave {Path(info['wave_dir']).name}: {state} ({info['succeeded']}/{info['total']} succeeded, {info['failed']} failed{aborted})")
    elif state == "running":
        print(f"wave {Path(info['wave_dir']).name}: running (pid {info['pid']}, {info['finished']}/{info['total']} lanes finished)")
    elif state == "refused":
        print(f"wave {Path(info['wave_dir']).name}: refused ({info['reason']})")
    else:
        print(f"wave {Path(info['wave_dir']).name}: interrupted ({info['finished']}/{info['total']} lanes finished); run: {info['hint']}")
    return 0


def recover_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="xgrok_wave.py recover",
        description="Recover packets and an audited manifest for an interrupted wave from native session transcripts.",
    )
    parser.add_argument("wave_dir", type=Path, help="Interrupted wave directory.")
    account = parser.add_mutually_exclusive_group()
    account.add_argument("--grok-home", type=str, default=None, help="Grok home path for session lookup.")
    account.add_argument("--grok2", action="store_true", help="Look up sessions under GROK2_HOME / ~/.grok2.")
    account.add_argument("--grok3", action="store_true", help="Look up sessions under GROK3_HOME / ~/.grok3.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing manifest.json.")
    args = parser.parse_args(argv)
    grok_home, err = _resolve_grok_home(args)
    if err:
        sys.stderr.write(f"xgrok_wave configuration error: {err}\n")
        return 2
    try:
        manifest = recover_wave(args.wave_dir, grok_home, overwrite=args.overwrite)
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError) as exc:
        sys.stderr.write(f"xgrok_wave recover error: {exc}\n")
        return 2
    rec = manifest["recovery"]
    print(
        f"Recovered {args.wave_dir}: {manifest['succeeded']}/{manifest['total_briefs']} succeeded "
        f"(recovered={len(rec['recovered_lanes'])}, existing={len(rec['existing_lanes'])}, "
        f"unmatched={len(rec['unmatched_lanes'])}; recovered cost_usd=unavailable)"
    )
    print(f"Manifest written to: {Path(manifest['output_dir']) / 'manifest.json'}")
    return 0 if manifest["failed"] == 0 else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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
    account = parser.add_mutually_exclusive_group()
    account.add_argument(
        "--grok-home",
        type=str,
        default=None,
        help="Custom GROK_HOME path for worker auth/state.",
    )
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
    parser.add_argument("--transport-probe", action="store_true", help="require one recorded native search probe + bound canary per account/bound form")
    parser.add_argument("--late-slice", action="store_true", help="treat this wave as a late slice (bound canary requires a <30m control post)")
    parser.add_argument("--detach", action="store_true", help="launch the wave in its own detached session (outlives shell timeouts)")
    parser.add_argument("--record-after-quota", nargs=2, type=Path, metavar=("HELPER", "FILE"),
                        help="for a detached run, use grok_account.py at exit to record the wave account's quota")
    parser.add_argument(
        "--roster",
        type=Path,
        default=Path.home() / ".grok" / "skills" / "macro" / "references" / "roster.tsv",
        help="Roster TSV whose entries the composed briefs carry as 'Roster roles' (with --common-tail).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] in ("recover", "status") and not Path(raw_argv[0]).is_file():
        return recover_main(raw_argv[1:]) if raw_argv[0] == "recover" else status_main(raw_argv[1:])

    args = parse_args(raw_argv)
    detached_child = os.environ.get("XGROK_WAVE_DETACHED") == "1"
    if args.record_after_quota and not (args.detach or detached_child):
        sys.stderr.write("xgrok_wave configuration error: --record-after-quota requires --detach\n")
        return 2
    if args.record_after_quota and not args.record_after_quota[0].is_file():
        sys.stderr.write(f"xgrok_wave configuration error: quota helper not found: {args.record_after_quota[0]}\n")
        return 2
    grok_home, home_err = _resolve_grok_home(args)
    if home_err:
        # A failed "$(xgrok --pick-account)" or empty GROK2_HOME="" must never silently run on ~/.grok.
        sys.stderr.write(f"xgrok_wave configuration error: {home_err}\n")
        return 2

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
                raw_text=job.text,
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

    if args.output_dir:
        output_dir = args.output_dir.resolve()
    else:
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_dir = Path.cwd() / f"xgrok-wave-{timestamp_str}"

    bound_lines = format_bound_form_summary(jobs)
    headless_deadline = _headless_retry_deadline(args.timeout)

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
        if headless_deadline is not None:
            print(f"Headless retry deadline setting (seconds): {headless_deadline}")
        print(f"Stagger: {args.stagger}s")
        print(f"Jobs ({len(jobs)} total):")
        for i, job in enumerate(jobs, 1):
            print(
                f"  {i:02d}. [{job.mode}] {job.name} -> {job.brief_path}"
                f" (effort={job.effort or '-'} model={job.model or '-'}"
                f" system_prompt={job.system_prompt or '-'})"
            )
        for line in bound_lines:
            print(line)
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    brief_records = [
        {
            "name": job.name,
            "brief_path": str(job.brief_path),
            "mode": job.mode,
            "effort": job.effort,
            "model": job.model,
            "system_prompt": job.system_prompt,
        }
        for job in jobs
    ]

    if args.detach:
        child_argv = [a for a in raw_argv if a != "--detach"]
        if not args.output_dir:
            child_argv.extend(["--output-dir", str(output_dir)])
        wave_log = output_dir / "wave.log"
        child_env = {**os.environ, "XGROK_WAVE_DETACHED": "1"}
        with wave_log.open("a", encoding="utf-8") as log_handle:
            proc = subprocess.Popen(
                [sys.executable, "-B", str(Path(__file__).resolve()), *child_argv],
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=child_env,
            )
        if (
            not (output_dir / "runner.json").is_file()
            and not (output_dir / "manifest.json").is_file()
            and not (output_dir / "NOT-LAUNCHED.txt").is_file()
        ):
            _write_json_atomic(
                output_dir / "runner.json",
                {
                    "pid": proc.pid,
                    "lstart": _process_start(proc.pid),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "status": "running",
                    "detached": True,
                    "grok_home": grok_home,
                    HEADLESS_DEADLINE_FIELD: headless_deadline,
                    "log_path": str(wave_log),
                    "total_briefs": len(jobs),
                    "briefs": brief_records,
                },
            )
        msg = (
            f"xgrok_wave: started detached (pid {proc.pid}); log: {wave_log}; "
            f"status: python3 {Path(__file__).resolve()} status {output_dir}"
        )
        print(msg)
        return 0

    for line in bound_lines:
        sys.stderr.write(line + "\n")
    sys.stderr.flush()

    runner_record = {
        "pid": os.getpid(),
        "lstart": _process_start(os.getpid()),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "detached": detached_child,
        "grok_home": grok_home,
        HEADLESS_DEADLINE_FIELD: headless_deadline,
        "log_path": str(output_dir / "wave.log") if (output_dir / "wave.log").is_file() else None,
        "total_briefs": len(jobs),
        "briefs": brief_records,
    }
    _write_json_atomic(output_dir / "runner.json", runner_record)

    def record_final_quota() -> None:
        if args.record_after_quota:
            helper, quota_log = args.record_after_quota
            account = grok_home or os.environ.get("GROK_HOME") or str(Path.home() / ".grok")
            try:
                subprocess.run(
                    [sys.executable, "-B", str(helper), "--record-at-exit", str(quota_log), "--home", account],
                    check=True,
                )
            except (OSError, subprocess.CalledProcessError) as exc:
                print(f"xgrok_wave: could not record the after-wave quota in {quota_log}: {exc}", file=sys.stderr)

    canary_summary: dict[str, Any] | None = None
    if args.transport_probe:
        ok, note = native_probe(output_dir.parent, xgrok_bin, grok_home)
        print(note, file=sys.stderr)
        if not ok:
            refusal = note + "; no research lanes launched. Use the existing browser path; no account switching."
            record_final_quota()
            (output_dir / "NOT-LAUNCHED.txt").write_text(refusal + "\n", encoding="utf-8")
            _write_json_atomic(output_dir / "runner.json", {**runner_record, "status": "refused", "returncode": 3})
            return 3
        canary_ok, canary_note, canary_summary = bound_canary(
            output_dir.parent, xgrok_bin, grok_home, jobs, late_slice=args.late_slice
        )
        if canary_note:
            print(canary_note, file=sys.stderr)
        if not canary_ok:
            refusal = canary_note + "; no research lanes launched."
            record_final_quota()
            (output_dir / "NOT-LAUNCHED.txt").write_text(refusal + "\n", encoding="utf-8")
            _write_json_atomic(output_dir / "runner.json", {**runner_record, "status": "refused", "returncode": 3})
            return 3

    _write_json_atomic(
        output_dir / "launched.json",
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "common_tail": common_tail,
            "grok_home": grok_home,
            "briefs": brief_records,
        },
    )

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
    max_workers = max(1, args.max_workers)
    pending = iter(jobs)

    def _record_done(done_futures: set[Future[dict[str, Any]]], in_flight: dict[Future[dict[str, Any]], BriefJob]) -> None:
        nonlocal abort_reason
        for future in done_futures:
            in_flight.pop(future, None)
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
                for queued in list(in_flight):
                    queued.cancel()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        try:
            in_flight: dict[Future[dict[str, Any]], BriefJob] = {}

            def submit_next() -> bool:
                if stop_requested.is_set():
                    return False
                job = next(pending, None)
                if job is None:
                    return False
                fut = executor.submit(
                    run_single_worker, job, xgrok_bin, output_dir, args.timeout, grok_home,
                    launch_paths[job.name], stop_requested,
                )
                in_flight[fut] = job
                return True

            if stagger_seconds > 0 and len(jobs) > 1:
                submit_next()
                deadline = time.monotonic() + stagger_seconds
                while in_flight and not stop_requested.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    done, _ = wait(in_flight, timeout=min(0.05, remaining), return_when=FIRST_COMPLETED)
                    if done:
                        _record_done(done, in_flight)
                        break

            while not stop_requested.is_set() and len(in_flight) < max_workers:
                if not submit_next():
                    break

            while in_flight:
                done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                _record_done(done, in_flight)
                while not stop_requested.is_set() and len(in_flight) < max_workers:
                    if not submit_next():
                        break
        except KeyboardInterrupt:
            stop_requested.set()
            executor.shutdown(wait=True, cancel_futures=True)
            record_final_quota()
            _write_json_atomic(output_dir / "runner.json", {**runner_record, "status": "interrupted", "returncode": 130})
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
        HEADLESS_DEADLINE_FIELD: headless_deadline,
        "output_dir": str(output_dir),
        "common_tail": common_tail,
        "bound_canary": canary_summary,
        "stagger_seconds": stagger_seconds,
        "total_briefs": len(jobs),
        "succeeded": succeeded,
        "failed": failed,
        "total_elapsed_seconds": round(total_elapsed, 2),
        "aborted": abort_reason,
        "workers": results,
    }

    manifest_path = output_dir / "manifest.json"
    record_final_quota()
    _write_json_atomic(manifest_path, manifest)
    _write_json_atomic(
        output_dir / "runner.json",
        {**runner_record, "status": "done", "returncode": 0 if failed == 0 else 1},
    )

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
