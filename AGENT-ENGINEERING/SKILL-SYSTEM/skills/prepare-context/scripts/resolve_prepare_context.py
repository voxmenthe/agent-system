#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


LOS_ANGELES_TIMEZONE = ZoneInfo("America/Los_Angeles")
DEFAULT_OUTPUT_BASE = Path("PLANS") / "PREPARED_CONTEXT"
RECENT_PLAN_LIMIT = 5
RECENT_COMMIT_LIMIT = 5

IGNORED_DIR_NAMES = {
    ".git", ".hg", ".svn",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env",
    "__pycache__",
    "node_modules",
    ".next", ".nuxt",
    "dist", "build", "out",
    ".tox", ".eggs",
    "model_cache",
    ".workbench",
    "PREPARED_CONTEXT",
}
IGNORED_DIR_PREFIXES = ("pipeline_output", ".tmp")
ALLOWED_TEXT_SUFFIXES = {
    ".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml",
    ".js", ".ts", ".jsx", ".tsx",
    ".rs", ".go", ".rb",
    ".sh", ".bash", ".zsh",
    ".cfg", ".ini",
    ".html", ".css", ".scss",
}
STOPWORDS = {
    "about",
    "after",
    "against",
    "agent",
    "agents",
    "all",
    "also",
    "analysis",
    "analyze",
    "and",
    "any",
    "are",
    "build",
    "bundle",
    "code",
    "context",
    "current",
    "feedback",
    "file",
    "files",
    "for",
    "from",
    "give",
    "good",
    "have",
    "help",
    "into",
    "just",
    "make",
    "most",
    "need",
    "our",
    "parts",
    "plan",
    "plans",
    "prepare",
    "recommendations",
    "relevant",
    "review",
    "should",
    "task",
    "that",
    "the",
    "them",
    "these",
    "this",
    "use",
    "useful",
    "want",
    "what",
    "with",
}
OVERVIEW_ANCHOR_FILES = {
    "README.md": (14.0, "project readme"),
    "CLAUDE.md": (14.0, "claude context document"),
    "CLAUDE_TASK.md": (13.0, "claude task document"),
    "ARCHITECTURE.md": (12.0, "architecture documentation"),
    "DESIGN.md": (11.0, "design documentation"),
    "pyproject.toml": (8.0, "python project configuration"),
    "package.json": (8.0, "node project configuration"),
    "Cargo.toml": (8.0, "rust project configuration"),
    "go.mod": (8.0, "go project configuration"),
    "Gemfile": (7.0, "ruby project configuration"),
    "Makefile": (6.0, "build file"),
    "docker-compose.yml": (5.0, "docker compose configuration"),
    "docker-compose.yaml": (5.0, "docker compose configuration"),
    "Dockerfile": (5.0, "dockerfile"),
    ".env.example": (4.0, "environment variable template"),
    "CONTRIBUTING.md": (6.0, "contributing guide"),
    "CHANGELOG.md": (5.0, "changelog"),
    "TODO.md": (5.0, "project todo list"),
}
OVERVIEW_DOC_DIRS = {"docs", "doc", "documentation", "wiki", "guides"}


@dataclass(frozen=True)
class ContextCandidate:
    path: str
    score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["score"] = round(self.score, 2)
        return payload


@dataclass(frozen=True)
class PrepareContextRequest:
    focus_description: str


@dataclass(frozen=True)
class RecentContextHint:
    path: str
    modified_at: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve a free-form prepare_context request into a manifest with "
            "output paths, search roots, repo structure, and starter candidates."
        )
    )
    parser.add_argument(
        "request_text",
        help=(
            "Free-form focus/feedback request. Describes what parts of the repo "
            "to focus on and what feedback is needed."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Repository root. Defaults to the nearest ancestor containing .git/.",
    )
    parser.add_argument(
        "--title",
        help=(
            "Descriptive title for the output directory. If not provided, "
            "a slug is generated from the request text."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Explicit output directory (must be inside the repo).",
    )
    parser.add_argument(
        "--create-output-dir",
        action="store_true",
        help="Create the output directory and write the manifest JSON to disk.",
    )
    parser.add_argument(
        "--timestamp",
        help="Override timestamp (format: YYYYMMDD-HHMM). Mainly for testing.",
    )
    return parser.parse_args(argv)


def is_repo_root(candidate: Path) -> bool:
    """Check if a directory looks like a repository root."""
    if (candidate / ".git").exists():
        return True
    root_markers = [
        "pyproject.toml", "package.json", "Cargo.toml", "go.mod",
        "Gemfile", "Makefile", "CLAUDE.md",
    ]
    return any((candidate / marker).exists() for marker in root_markers)


def find_repo_root(start_directory: Path) -> Path:
    start_directory = start_directory.resolve()
    for candidate in (start_directory, *start_directory.parents):
        if is_repo_root(candidate):
            return candidate
    return start_directory


def resolve_repo_root(explicit_repo_root: Path | None) -> Path:
    if explicit_repo_root is None:
        return find_repo_root(Path.cwd())
    repo_root = explicit_repo_root.expanduser().resolve()
    if not repo_root.is_dir():
        raise SystemExit(f"--repo-root is not a directory: {repo_root}")
    return repo_root


def repo_relative_path(path: Path, repo_root: Path) -> str:
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise SystemExit(
            f"Expected a repository-relative path under {repo_root}, got: {resolved_path}"
        ) from exc


def parse_prepare_context_request(
    request_text: str,
) -> PrepareContextRequest:
    stripped = request_text.strip()
    if not stripped:
        raise SystemExit("request_text must not be empty")
    return PrepareContextRequest(focus_description=stripped)


def _tokenize(text: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }
    return tokens


def _safe_read_text(path: Path, *, limit: int = 12000) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    return text[:limit]


def _should_ignore_dir(dirname: str) -> bool:
    if dirname in IGNORED_DIR_NAMES:
        return True
    return any(dirname.startswith(prefix) for prefix in IGNORED_DIR_PREFIXES)


def _iter_repo_text_files(repo_root: Path, *, max_files: int = 2000) -> list[Path]:
    collected: list[Path] = []
    for current_root, dirnames, filenames in repo_root.walk():
        dirnames[:] = sorted(d for d in dirnames if not _should_ignore_dir(d))
        for filename in sorted(filenames):
            path = current_root / filename
            if path.suffix.lower() not in ALLOWED_TEXT_SUFFIXES:
                continue
            if path.name.endswith(".bak"):
                continue
            collected.append(path)
            if len(collected) >= max_files:
                return collected
    return collected


def _build_repo_structure_summary(
    repo_root: Path, *, max_depth: int = 3, max_files: int = 2000,
) -> dict[str, Any]:
    """Walk the repo and produce a lightweight structure summary for sub-agents."""
    top_level_entries: list[str] = []
    extension_counts: dict[str, int] = {}
    total_files = 0
    key_files_found: list[str] = []
    tree_lines: list[str] = []

    for entry in sorted(repo_root.iterdir()):
        name = entry.name
        if name.startswith(".") and name != ".env.example":
            continue
        if entry.is_dir() and not _should_ignore_dir(name):
            top_level_entries.append(name + "/")
        elif entry.is_file():
            top_level_entries.append(name)
            if name in OVERVIEW_ANCHOR_FILES:
                key_files_found.append(name)

    for current_root, dirnames, filenames in repo_root.walk():
        depth = len(current_root.relative_to(repo_root).parts)
        dirnames[:] = sorted(d for d in dirnames if not _should_ignore_dir(d))
        if depth < max_depth:
            indent = "  " * depth
            rel = current_root.relative_to(repo_root).as_posix()
            if rel != ".":
                tree_lines.append(f"{indent}{current_root.name}/")
        for filename in filenames:
            total_files += 1
            if total_files > max_files:
                break
            suffix = Path(filename).suffix.lower()
            if suffix:
                extension_counts[suffix] = extension_counts.get(suffix, 0) + 1
        if total_files > max_files:
            break

    top_extensions = sorted(extension_counts.items(), key=lambda x: -x[1])[:15]
    return {
        "top_level_entries": top_level_entries,
        "key_files_found": key_files_found,
        "total_files_scanned": min(total_files, max_files),
        "truncated": total_files > max_files,
        "extension_distribution": {ext: count for ext, count in top_extensions},
        "directory_tree_preview": tree_lines[:60],
    }


def _score_matches(
    path: Path,
    *,
    query_tokens: set[str],
) -> tuple[float, list[str]]:
    if not query_tokens:
        return 0.0, []

    reasons: list[str] = []
    score = 0.0
    relative_tokens = _tokenize(path.as_posix())
    path_matches = sorted(query_tokens & relative_tokens)
    if path_matches:
        score += 3.0 * len(path_matches)
        reasons.append(f"path matches query tokens: {', '.join(path_matches)}")

    content_tokens = _tokenize(_safe_read_text(path))
    content_matches = sorted((query_tokens & content_tokens) - set(path_matches))
    if content_matches:
        score += 1.5 * len(content_matches)
        reasons.append(f"content mentions: {', '.join(content_matches)}")

    return score, reasons


def _candidate(
    path: Path,
    *,
    repo_root: Path,
    base_score: float = 0.0,
    base_reason: str | None = None,
    query_tokens: set[str],
) -> ContextCandidate | None:
    score, reasons = _score_matches(path, query_tokens=query_tokens)
    total_score = base_score + score
    if total_score <= 0.0:
        return None

    if base_reason:
        reasons.insert(0, base_reason)
    reason = "; ".join(reasons) if reasons else "candidate surfaced by resolver"
    return ContextCandidate(
        path=repo_relative_path(path, repo_root),
        score=total_score,
        reason=reason,
    )


def _sort_candidates(
    candidates: list[ContextCandidate],
    *,
    limit: int,
) -> list[ContextCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: (-candidate.score, candidate.path),
    )[:limit]


def _select_overview_candidates(
    *,
    repo_root: Path,
    query_tokens: set[str],
) -> list[ContextCandidate]:
    """Select high-value project overview files."""
    candidates: list[ContextCandidate] = []

    for filename, (base_score, base_reason) in OVERVIEW_ANCHOR_FILES.items():
        path = repo_root / filename
        if not path.exists():
            continue
        candidate = _candidate(
            path,
            repo_root=repo_root,
            base_score=base_score,
            base_reason=base_reason,
            query_tokens=query_tokens,
        )
        if candidate is not None:
            candidates.append(candidate)

    for doc_dir_name in OVERVIEW_DOC_DIRS:
        doc_dir = repo_root / doc_dir_name
        if not doc_dir.is_dir():
            continue
        for path in sorted(doc_dir.rglob("*.md"))[:20]:
            candidate = _candidate(
                path,
                repo_root=repo_root,
                base_score=5.0,
                base_reason=f"documentation in {doc_dir_name}/",
                query_tokens=query_tokens,
            )
            if candidate is not None:
                candidates.append(candidate)

    for entry in sorted(repo_root.iterdir()):
        if entry.is_dir() and not _should_ignore_dir(entry.name):
            readme = entry / "README.md"
            if readme.exists():
                candidate = _candidate(
                    readme,
                    repo_root=repo_root,
                    base_score=6.0,
                    base_reason=f"subdirectory readme ({entry.name}/)",
                    query_tokens=query_tokens,
                )
                if candidate is not None:
                    candidates.append(candidate)

    return _sort_candidates(candidates, limit=12)


def _iter_plan_files(repo_root: Path) -> list[Path]:
    plans_root = repo_root / "PLANS"
    if not plans_root.is_dir():
        return []

    collected: list[Path] = []
    for current_root, dirnames, filenames in plans_root.walk():
        relative_root = current_root.relative_to(plans_root)
        if relative_root.parts[:1] in (("COMMITS",), ("PROMPTS",), ("PREPARED_CONTEXT",)):
            dirnames[:] = []
            continue
        dirnames[:] = sorted(dirnames)
        for filename in sorted(filenames):
            path = current_root / filename
            if path.suffix.lower() != ".md":
                continue
            collected.append(path)
    return collected


def _format_modified_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, LOS_ANGELES_TIMEZONE).isoformat()


def _recent_hint(path: Path, *, repo_root: Path, reason: str) -> RecentContextHint:
    return RecentContextHint(
        path=repo_relative_path(path, repo_root),
        modified_at=_format_modified_at(path),
        reason=reason,
    )


def _most_recent_paths(paths: list[Path], *, limit: int) -> list[Path]:
    return sorted(
        paths,
        key=lambda path: (-path.stat().st_mtime, path.as_posix()),
    )[:limit]


def _recent_plan_hints(repo_root: Path) -> list[RecentContextHint]:
    return [
        _recent_hint(path, repo_root=repo_root, reason="recently modified plan file")
        for path in _most_recent_paths(_iter_plan_files(repo_root), limit=RECENT_PLAN_LIMIT)
    ]


def _recent_commit_hints(repo_root: Path) -> list[RecentContextHint]:
    commits_root = repo_root / "PLANS" / "COMMITS"
    if not commits_root.is_dir():
        return []

    commit_files = [path for path in commits_root.glob("*.md") if path.is_file()]
    return [
        _recent_hint(path, repo_root=repo_root, reason="recently modified commit narrative")
        for path in _most_recent_paths(commit_files, limit=RECENT_COMMIT_LIMIT)
    ]


def _select_plan_candidates(
    *,
    repo_root: Path,
    query_tokens: set[str],
) -> list[ContextCandidate]:
    candidates: list[ContextCandidate] = []
    for path in _iter_plan_files(repo_root):
        candidate = _candidate(
            path,
            repo_root=repo_root,
            base_score=1.0,
            base_reason="plan document",
            query_tokens=query_tokens,
        )
        if candidate is None or candidate.score < 4.0:
            continue
        candidates.append(candidate)
    return _sort_candidates(candidates, limit=5)


def _select_commit_candidates(
    *,
    repo_root: Path,
    query_tokens: set[str],
) -> list[ContextCandidate]:
    commits_root = repo_root / "PLANS" / "COMMITS"
    if not commits_root.is_dir():
        return []

    candidates: list[ContextCandidate] = []
    for path in sorted(commits_root.glob("*.md"), reverse=True):
        candidate = _candidate(
            path,
            repo_root=repo_root,
            base_score=1.0,
            base_reason="recent narrative commit context",
            query_tokens=query_tokens,
        )
        if candidate is None or candidate.score < 4.0:
            continue
        candidates.append(candidate)
    return _sort_candidates(candidates, limit=5)


def _code_base_reason(path: Path, repo_root: Path) -> tuple[float, str]:
    """Assign a base score and reason based on file location within the repo."""
    relative = path.relative_to(repo_root).as_posix()
    parts = relative.split("/")
    if any(p in ("tests", "test", "spec", "__tests__") for p in parts):
        return 1.0, "test file"
    if parts[0] in ("src", "lib", "app", "pkg", "internal", "cmd"):
        return 1.5, f"source file in {parts[0]}/"
    if parts[0] in ("config", "infra", "deploy", "scripts"):
        return 0.5, f"config/infrastructure file in {parts[0]}/"
    return 0.0, "repository file"


def _select_code_candidates(
    *,
    repo_root: Path,
    query_tokens: set[str],
    excluded_paths: set[str],
) -> list[ContextCandidate]:
    candidates: list[ContextCandidate] = []
    for path in _iter_repo_text_files(repo_root):
        relative_path = repo_relative_path(path, repo_root)
        if relative_path in excluded_paths:
            continue
        base_score, base_reason = _code_base_reason(path, repo_root)
        candidate = _candidate(
            path,
            repo_root=repo_root,
            base_score=base_score,
            base_reason=base_reason,
            query_tokens=query_tokens,
        )
        if candidate is None or candidate.score < 4.0:
            continue
        candidates.append(candidate)
    return _sort_candidates(candidates, limit=15)


def _default_timestamp() -> str:
    return datetime.now(LOS_ANGELES_TIMEZONE).strftime("%Y%m%d-%H%M")


def _build_identifier(request_text: str) -> str:
    digest = hashlib.sha1(request_text.encode("utf-8")).hexdigest()
    return digest[:8]


def _slugify_title(title: str) -> str:
    """Convert a descriptive title to a filesystem-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower().strip())
    slug = slug.strip("-")
    return slug[:64] if slug else "context"


def _build_request_slug(request_text: str) -> str:
    tokens = [token for token in sorted(_tokenize(request_text)) if token]
    if not tokens:
        return "context"
    slug = "-".join(tokens[:6])
    return slug[:48]


def _resolve_output_dir(
    *,
    repo_root: Path,
    explicit_output_dir: Path | None,
    timestamp: str,
    title_slug: str,
    identifier: str,
) -> Path:
    if explicit_output_dir is not None:
        output_dir = explicit_output_dir.expanduser().resolve()
        try:
            output_dir.relative_to(repo_root)
        except ValueError as exc:
            raise SystemExit(
                f"--output-dir must stay inside the repository root {repo_root}"
            ) from exc
        return output_dir

    return repo_root / DEFAULT_OUTPUT_BASE / f"{timestamp}-{title_slug}-{identifier}"


def _existing_repo_relative_paths(paths: list[Path], repo_root: Path) -> list[str]:
    return [
        repo_relative_path(path, repo_root)
        for path in paths
        if path.exists()
    ]


def _default_ignore_patterns() -> list[str]:
    """Generic ignore patterns for any repository."""
    return [
        ".git/**",
        "**/__pycache__/**",
        "**/node_modules/**",
        "**/.venv/**",
        "**/venv/**",
        "**/dist/**",
        "**/build/**",
        "**/.pytest_cache/**",
        "**/.mypy_cache/**",
        "**/.next/**",
        "PLANS/PREPARED_CONTEXT/**",
    ]


def resolve_prepare_context(
    request_text: str,
    *,
    repo_root: Path,
    title: str | None = None,
    output_dir: Path | None = None,
    timestamp: str | None = None,
    create_output_dir: bool = False,
) -> dict[str, Any]:
    request = parse_prepare_context_request(request_text)
    timestamp_value = timestamp or _default_timestamp()
    identifier = _build_identifier(request.focus_description)
    title_slug = _slugify_title(title) if title else _build_request_slug(request.focus_description)

    query_tokens = _tokenize(request.focus_description)

    resolved_output_dir = _resolve_output_dir(
        repo_root=repo_root,
        explicit_output_dir=output_dir,
        timestamp=timestamp_value,
        title_slug=title_slug,
        identifier=identifier,
    )
    manifest_path = resolved_output_dir / f"{identifier}_context_manifest.json"
    request_summary_path = resolved_output_dir / f"{identifier}_request_summary.md"
    final_bundle_path = resolved_output_dir / f"{identifier}_prepared_context.md"
    component_paths = {
        "task_overview": resolved_output_dir / f"{identifier}_task_overview.md",
        "plan_context": resolved_output_dir / f"{identifier}_plan_context.md",
        "commit_context": resolved_output_dir / f"{identifier}_commit_context.md",
        "code_context": resolved_output_dir / f"{identifier}_code_context.md",
    }

    repo_structure = _build_repo_structure_summary(repo_root)

    overview_candidates = _select_overview_candidates(
        repo_root=repo_root,
        query_tokens=query_tokens,
    )
    excluded_paths = {c.path for c in overview_candidates}
    plan_candidates = _select_plan_candidates(repo_root=repo_root, query_tokens=query_tokens)
    commit_candidates = _select_commit_candidates(
        repo_root=repo_root,
        query_tokens=query_tokens,
    )
    code_candidates = _select_code_candidates(
        repo_root=repo_root,
        query_tokens=query_tokens,
        excluded_paths=excluded_paths,
    )

    search_roots_code = ["."]
    for entry_name in repo_structure["top_level_entries"]:
        clean = entry_name.rstrip("/")
        if clean in ("src", "lib", "app", "pkg", "internal", "cmd"):
            search_roots_code.append(clean)

    always_consider: dict[str, list[dict]] = {}
    plan_hints = _recent_plan_hints(repo_root)
    if plan_hints:
        always_consider["recent_plans"] = [h.to_dict() for h in plan_hints]
    commit_hints = _recent_commit_hints(repo_root)
    if commit_hints:
        always_consider["recent_commits"] = [h.to_dict() for h in commit_hints]

    recommended_tools = {
        "files": 'rg --files "{repo_root}"',
        "search": 'rg -n -m 20 -- "<pattern>" "{scoped_path}"',
    }

    manifest = {
        "focus_description": request.focus_description,
        "bundle_identifier": identifier,
        "request_slug": title_slug,
        "timestamp": timestamp_value,
        "repo_root": str(repo_root),
        "output_dir": repo_relative_path(resolved_output_dir, repo_root),
        "manifest_path": repo_relative_path(manifest_path, repo_root),
        "request_summary_path": repo_relative_path(request_summary_path, repo_root),
        "final_bundle_path": repo_relative_path(final_bundle_path, repo_root),
        "component_paths": {
            key: repo_relative_path(path, repo_root) for key, path in component_paths.items()
        },
        "assembly_order": [
            repo_relative_path(request_summary_path, repo_root),
            repo_relative_path(component_paths["task_overview"], repo_root),
            repo_relative_path(component_paths["plan_context"], repo_root),
            repo_relative_path(component_paths["commit_context"], repo_root),
            repo_relative_path(component_paths["code_context"], repo_root),
        ],
        "repo_structure": repo_structure,
        "search_roots": {
            "task_overview": ["."],
            "plans": ["PLANS"] if (repo_root / "PLANS").is_dir() else ["."],
            "commits": ["PLANS/COMMITS"] if (repo_root / "PLANS" / "COMMITS").is_dir() else [],
            "code": search_roots_code,
        },
        "ignore_patterns": _default_ignore_patterns(),
        "always_consider_policy": (
            "these recent artifacts should always be considered as possible relevant "
            "sources, even if they are outside a component's main starter list or "
            "live under otherwise ignored paths"
        ),
        "always_consider": always_consider,
        "starter_candidate_policy": (
            "starter_candidates_are_hints_not_ground_truth; agents should search "
            "inside the provided roots and decide relevance themselves"
        ),
        "starter_candidates": {
            "task_overview": [c.to_dict() for c in overview_candidates],
            "plans": [c.to_dict() for c in plan_candidates],
            "commits": [c.to_dict() for c in commit_candidates],
            "code": [c.to_dict() for c in code_candidates],
        },
        "recommended_tools": recommended_tools,
    }

    if create_output_dir:
        if resolved_output_dir.exists():
            raise SystemExit(f"Refusing to reuse existing output directory: {resolved_output_dir}")
        resolved_output_dir.mkdir(parents=True, exist_ok=False)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return manifest


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = resolve_repo_root(args.repo_root)
    manifest = resolve_prepare_context(
        args.request_text,
        repo_root=repo_root,
        title=args.title,
        output_dir=args.output_dir,
        timestamp=args.timestamp,
        create_output_dir=args.create_output_dir,
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
