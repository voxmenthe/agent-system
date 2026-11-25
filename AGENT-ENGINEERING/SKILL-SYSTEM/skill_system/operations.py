from __future__ import annotations

import copy
import errno
import fcntl
import json
import os
import shutil
import stat
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .claude import configure_claude
from .grok import GROK_HOMES, grok_status, project_grok, validate_grok_sources
from .journal import list_incomplete_operations, load_operation
from .mimo import configure_mimo
from .model import (
    CollisionError,
    IncompleteOperationError,
    LockBusyError,
    OPERATION_SCHEMA_VERSION,
    OperationResult,
    RefreshResult,
    StatusReport,
    ValidationError,
    content_hash,
    is_ignored_skill_path,
    iter_skill_states,
    load_enabled_hosts,
    load_install_state,
    load_json,
    resolve_target,
    sha256_bytes,
    validate_canonical,
    validate_install_state,
    validate_skill_tree,
)


EXPECTED_MATT_SKILLS = frozenset(
    {
        "ask-matt",
        "batch-grill-me",
        "code-review",
        "codebase-design",
        "design-an-interface",
        "diagnosing-bugs",
        "domain-modeling",
        "edit-article",
        "grill-me",
        "grill-with-docs",
        "grilling",
        "handoff",
        "implement",
        "improve-codebase-architecture",
        "loop-me",
        "prototype",
        "request-refactor-plan",
        "research",
        "scaffold-exercises",
        "tdd",
        "teach",
        "to-questionnaire",
        "to-spec",
        "ubiquitous-language",
        "wayfinder",
    }
)


class InjectedFailure(RuntimeError):
    """Deterministic test-only interruption after a durable journal phase."""

    def __init__(self, operation_id: str, phase: str):
        super().__init__(f"injected interruption after {phase} for {operation_id}")
        self.operation_id = operation_id
        self.phase = phase


@dataclass
class CodexSkillDeclaration:
    path: Path
    declared_name: str | None
    issues: list[str]


@dataclass
class CodexSymlink:
    path: Path
    target: str


@dataclass
class CodexAuditReport:
    root: Path
    ok: bool = True
    personal_skills: list[CodexSkillDeclaration] = field(default_factory=list)
    provider_entries: list[CodexSymlink | CodexSkillDeclaration] = field(default_factory=list)
    non_skill_entries: list[Path] = field(default_factory=list)
    symlinks: list[CodexSymlink] = field(default_factory=list)


def _codex_declared_name(path: Path) -> str | None:
    """Read a scalar name, not the stricter canonical package contract."""
    lines = path.read_text().splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        return None
    header = lines[1:lines.index("---", 1)]
    names = [line.split(":", 1)[1].strip() for line in header if line.startswith("name:")]
    if len(names) != 1:
        return None
    raw = names[0]
    if raw.startswith('"'):
        try:
            name = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return name if isinstance(name, str) and name.strip() else None
    if raw.startswith("'"):
        if len(raw) < 2 or not raw.endswith("'"):
            return None
        name = raw[1:-1].replace("''", "'")
        return name if name.strip() else None
    if not raw or raw[0] in "[{|>&*!%@`" or ": " in raw:
        return None
    name = raw.split(" #", 1)[0].strip()
    if name.lower() in {"null", "true", "false", "~"} or name.isdecimal():
        return None
    return name or None


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def operation_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{uuid.uuid4().hex[:12]}"


def _nearest_existing(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        if candidate.parent == candidate:
            raise ValidationError(f"no existing parent for {path}")
        candidate = candidate.parent
    return candidate


def same_filesystem(left: Path, right: Path) -> bool:
    return _nearest_existing(left).stat().st_dev == _nearest_existing(right).stat().st_dev


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _flush_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if is_ignored_skill_path(path, root):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            continue
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
        elif path.is_dir():
            _fsync_directory(path)
    _fsync_directory(root)


def atomic_write_bytes(path: Path, value: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, value: object) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
    atomic_write_bytes(path, payload)


class SkillSystem:
    """Narrow public boundary for validation, projection, and recovery."""

    def __init__(self, canonical_root: Path, home: Path):
        self.root = canonical_root.resolve()
        self.home = home.resolve()
        self.agents_root = self.home / ".agents"
        self.live_root = self.agents_root / "skills"
        self.state_root = self.agents_root / ".skill-system"
        self.state_path = self.state_root / "install-state.json"
        self.lock_path = self.state_root / "operation.lock"
        self.transactions = self.state_root / "transactions"
        self.quarantine_root = self.state_root / "quarantine"
        self.skill_lock_path = self.agents_root / ".skill-lock.json"

    @contextmanager
    def _lock(self, *, exclusive: bool, mutating: bool) -> Iterator[None]:
        if mutating:
            self.agents_root.mkdir(parents=True, exist_ok=True)
        if not self.agents_root.is_dir():
            yield
            return
        directory_fd = os.open(self.agents_root, os.O_RDONLY)
        lock_fd: int | None = None
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            try:
                fcntl.flock(directory_fd, operation | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    raise LockBusyError("skill-system operation lock is busy") from exc
                raise
            if mutating:
                self.state_root.mkdir(parents=True, exist_ok=True)
                lock_fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            elif self.lock_path.exists():
                lock_fd = os.open(self.lock_path, os.O_RDWR)
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, operation | fcntl.LOCK_NB)
                except OSError as exc:
                    if exc.errno in {errno.EACCES, errno.EAGAIN}:
                        raise LockBusyError("skill-system operation lock is busy") from exc
                    raise
            yield
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
            os.close(directory_fd)

    def validate(self):
        with self._lock(exclusive=False, mutating=False):
            _, report = validate_canonical(self.root, self.home)
            return replace(report, grok_skills=validate_grok_sources(self.root))

    def audit(self):
        with self._lock(exclusive=False, mutating=False):
            registry, report = validate_canonical(self.root, self.home)
            state = load_install_state(self.state_path)
            validate_install_state(state, registry, self.root, self.home)
            return replace(report, grok_skills=validate_grok_sources(self.root))

    def audit_codex(self) -> CodexAuditReport:
        """Inventory only the selected home's Codex skill tree, without writes.

        Symlinks are never traversed or read; regular-file targets are only
        statted to distinguish non-skill runtime links. The direct .system entry is a
        provider exception; its contents and other provider caches are not scanned.
        Name extraction is deliberately not full YAML or canonical validation.
        """
        codex_root = self.home / ".codex"
        report = CodexAuditReport(root=codex_root / "skills")
        try:
            for boundary in (codex_root, report.root):
                if boundary.is_symlink():
                    report.symlinks.append(CodexSymlink(boundary, str(boundary.readlink())))
                    report.ok = False
                    return report
            if not report.root.exists():
                return report
            pending = [report.root]
            while pending:
                directory = pending.pop()
                for path in sorted(directory.iterdir()):
                    if path == report.root / ".system":
                        if path.is_symlink():
                            report.provider_entries.append(CodexSymlink(path, str(path.readlink())))
                        else:
                            report.provider_entries.append(CodexSkillDeclaration(path, None, []))
                        continue
                    if path.is_symlink():
                        regular_file = False
                        if path.name != "SKILL.md":
                            try:
                                regular_file = stat.S_ISREG(path.stat().st_mode)
                            except OSError:
                                # Broken, cyclic, or inaccessible targets stay flagged.
                                pass
                        if regular_file:
                            report.non_skill_entries.append(path)
                        else:
                            report.symlinks.append(CodexSymlink(path, str(path.readlink())))
                    elif path.is_dir():
                        pending.append(path)
                        if not (path / "SKILL.md").is_file():
                            report.non_skill_entries.append(path)
                    elif path.name == "SKILL.md" and path.is_file():
                        try:
                            name = _codex_declared_name(path)
                        except UnicodeError:
                            name = None
                        issues = ["unmanaged-personal"]
                        if name is None:
                            issues.append("malformed-declaration")
                        if directory == report.root:
                            issues.append("root-declaration")
                        elif name is not None and name != directory.name:
                            issues.append("name-directory-mismatch")
                        report.personal_skills.append(CodexSkillDeclaration(path, name, issues))
                    else:
                        report.non_skill_entries.append(path)
        except OSError as exc:
            raise ValidationError(f"cannot audit Codex skills at {report.root}: {exc}") from exc
        report.personal_skills.sort(key=lambda entry: entry.path)
        report.non_skill_entries.sort()
        report.symlinks.sort(key=lambda entry: entry.path)
        report.ok = not (report.personal_skills or report.symlinks)
        return report

    def status(self) -> StatusReport:
        with self._lock(exclusive=False, mutating=False):
            registry, report = validate_canonical(self.root, self.home)
            state = load_install_state(self.state_path)
            validate_install_state(state, registry, self.root, self.home)
            skills = {item.name: item for item in iter_skill_states(
                registry, report, state, self.home
            )}
            return StatusReport(
                skills=skills,
                incomplete_operations=list_incomplete_operations(self.transactions),
                grok=grok_status(self.root, self.home),
            )

    def relocate(self, old_root: Path, *, apply: bool = False) -> OperationResult:
        """Point install state and Grok links that name `old_root` at this checkout.

        Install state records each managed skill's absolute source path, so a
        moved checkout fails validation until this runs. Only entries and links
        that name exactly the old root's copy of the same skill change; anything
        else is an error. Rerunning is safe; the previous state file is kept.
        """
        old_root = Path(os.path.abspath(old_root.expanduser()))
        with self._lock(exclusive=apply, mutating=apply):
            self._ensure_no_incomplete()
            registry, _report = validate_canonical(self.root, self.home)
            state = load_install_state(self.state_path)

            def old_paths(relative: str) -> set[str]:
                candidate = old_root / relative
                return {os.path.normpath(candidate), os.path.realpath(candidate)}

            changes: list[str] = []
            relocated = copy.deepcopy(state)
            for name, entry in sorted(relocated["managed"].items()):
                record = registry.skills.get(name)
                if record is None:
                    raise ValidationError(f"unknown managed skill: {name}")
                relative = (
                    record["source"] if record["ownership"] == "custom" else f"skills/{name}"
                )
                expected = str((self.root / relative).resolve())
                if entry["source"] == expected:
                    continue
                if entry["source"] not in old_paths(relative):
                    raise ValidationError(
                        f"managed state {name} names neither checkout: {entry['source']}"
                    )
                changes.append(f"state {name}: {entry['source']} -> {expected}")
                entry["source"] = expected
            links: list[tuple[Path, Path]] = []
            for account in GROK_HOMES:
                skills = self.home / account / "skills"
                if not skills.is_dir() or skills.is_symlink():
                    continue
                for link in sorted(skills.iterdir()):
                    if not link.is_symlink():
                        continue
                    if os.readlink(link) in old_paths(f"grok-skills/{link.name}"):
                        source = self.root / "grok-skills" / link.name
                        if not source.is_dir():
                            raise ValidationError(f"no Grok skill {link.name} in this checkout")
                        changes.append(f"link {link} -> {source}")
                        links.append((link, source))
            validate_install_state(relocated, registry, self.root, self.home)
            if not changes:
                return OperationResult(None, False, "already-current")
            if not apply:
                return OperationResult(None, False, "dry-run", tuple(changes))
            if relocated != state:
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
                atomic_write_bytes(
                    self.state_root / f"install-state.before-relocate-{stamp}.json",
                    self.state_path.read_bytes(),
                )
                atomic_write_json(self.state_path, relocated)
            for link, source in links:
                temporary = link.with_name(f".{link.name}.relocate-{uuid.uuid4().hex}")
                temporary.symlink_to(source, target_is_directory=True)
                os.replace(temporary, link)
                _fsync_directory(link.parent)
            return OperationResult(None, True, "relocated", tuple(changes))

    def configure_grok(self, *, apply: bool = False, force: bool = False) -> OperationResult:
        with self._lock(exclusive=apply, mutating=apply):
            self._ensure_no_incomplete()
            return project_grok(self.root, self.home, apply=apply, force=force)

    def _ensure_no_incomplete(self, *, allow: str | None = None) -> None:
        incomplete = [
            item
            for item in list_incomplete_operations(self.transactions)
            if item != allow
        ]
        if incomplete:
            names = ", ".join(incomplete)
            raise IncompleteOperationError(
                f"incomplete operation(s) require rollback before mutation: {names}"
            )

    def _initialize_mutation_dirs(self) -> None:
        self.live_root.mkdir(parents=True, exist_ok=True)
        self.transactions.mkdir(parents=True, exist_ok=True)
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        _fsync_directory(self.live_root)
        _fsync_directory(self.state_root)
        _fsync_directory(self.agents_root)

    def _create_transaction(self, identifier: str) -> Path:
        transaction = self.transactions / identifier
        transaction.mkdir()
        _fsync_directory(self.transactions)
        return transaction

    def _new_journal(
        self,
        kind: str,
        identifier: str,
        *,
        changes: list[str],
        details: dict[str, Any],
    ) -> dict[str, Any]:
        now = utc_now()
        return {
            "schema_version": OPERATION_SCHEMA_VERSION,
            "operation_id": identifier,
            "type": kind,
            "status": "in-progress",
            "phase": "prepared",
            "created_at": now,
            "updated_at": now,
            "changes": changes,
            "details": details,
        }

    def _write_journal(self, transaction: Path, journal: dict[str, Any]) -> None:
        journal["updated_at"] = utc_now()
        atomic_write_json(transaction / "operation.json", journal)

    def _phase(
        self,
        transaction: Path,
        journal: dict[str, Any],
        phase: str,
        fail_after: str | None,
    ) -> None:
        journal["phase"] = phase
        self._write_journal(transaction, journal)
        if fail_after == phase:
            raise InjectedFailure(journal["operation_id"], phase)

    def install(
        self,
        name: str,
        *,
        apply: bool = False,
        fail_after: str | None = None,
    ) -> OperationResult:
        with self._lock(exclusive=apply, mutating=apply):
            return self._install_under_lock(
                name,
                apply=apply,
                fail_after=fail_after,
            )

    def refresh(self, *, apply: bool = False) -> RefreshResult:
        with self._lock(exclusive=apply, mutating=apply):
            self._ensure_no_incomplete()
            registry, report = validate_canonical(self.root, self.home)
            state = load_install_state(self.state_path)
            validate_install_state(state, registry, self.root, self.home)
            candidates: list[str] = []
            excluded: dict[str, list[str]] = {}
            for item in iter_skill_states(registry, report, state, self.home):
                installable = (
                    item.ownership == "custom"
                    and item.lifecycle not in {"reference", "retired"}
                )
                if installable and item.state == "source-updated":
                    candidates.append(item.name)
                    continue
                if item.ownership == "custom" and item.lifecycle in {
                    "reference",
                    "retired",
                }:
                    reason = f"lifecycle-{item.lifecycle}"
                else:
                    reason = item.state
                excluded.setdefault(reason, []).append(item.name)
            if apply:
                for name in candidates:
                    record = registry.skills[name]
                    target = resolve_target(
                        self.home,
                        record["install_targets"][0],
                        name,
                    )
                    if not same_filesystem(self.state_root, target.parent):
                        raise ValidationError(
                            f"refresh candidate {name} requires transaction state "
                            "and live target on the same filesystem"
                        )
            results: dict[str, OperationResult] = {}
            for name in candidates:
                results[name] = self._install_under_lock(name, apply=apply)
            applied = any(result.applied for result in results.values())
            if not apply:
                reason = "dry-run"
            elif applied:
                reason = "refreshed"
            else:
                reason = "nothing-to-refresh"
            return RefreshResult(
                applied=applied,
                reason=reason,
                operations=results,
                excluded={
                    reason: tuple(names)
                    for reason, names in sorted(excluded.items())
                },
            )

    def sync(self, *, apply: bool = False, force: bool = False) -> RefreshResult:
        with self._lock(exclusive=apply, mutating=apply):
            self._ensure_no_incomplete()
            registry, report = validate_canonical(self.root, self.home)
            state = load_install_state(self.state_path)
            validate_install_state(state, registry, self.root, self.home)
            # ~/.agents/skills serves every host; the per-host stages run only for
            # hosts the machine file enables (all of them when it is absent).
            enabled = load_enabled_hosts(self.home)

            def host_enabled(host: str) -> bool:
                return enabled is None or host in enabled
            install_candidates: list[str] = []
            force_candidates: list[str] = []
            excluded: dict[str, list[str]] = {}
            for item in iter_skill_states(registry, report, state, self.home):
                if item.ownership != "custom":
                    excluded.setdefault(
                        f"ownership-{item.ownership}", []
                    ).append(item.name)
                    continue
                if item.lifecycle in {"reference", "retired"}:
                    excluded.setdefault(
                        f"lifecycle-{item.lifecycle}", []
                    ).append(item.name)
                    continue
                if item.state in {"absent", "source-updated"}:
                    install_candidates.append(item.name)
                elif item.state in {"unmanaged-collision", "locally-modified"}:
                    if force:
                        force_candidates.append(item.name)
                    else:
                        excluded.setdefault(item.state, []).append(item.name)
                else:
                    excluded.setdefault(item.state, []).append(item.name)
            candidates = install_candidates + force_candidates
            force_set = set(force_candidates)
            if apply:
                for name in candidates:
                    record = registry.skills[name]
                    target = resolve_target(
                        self.home,
                        record["install_targets"][0],
                        name,
                    )
                    if not same_filesystem(self.state_root, target.parent):
                        raise ValidationError(
                            f"sync candidate {name} requires transaction state "
                            "and live target on the same filesystem"
                        )
            results: dict[str, OperationResult] = {}
            for name in candidates:
                results[name] = self._install_under_lock(
                    name,
                    apply=apply,
                    force=name in force_set,
                )
            disabled = OperationResult(None, False, "host-disabled")
            claude_result = (
                configure_claude(self.root, self.home, apply=apply, force=force)
                if host_enabled("claude")
                else disabled
            )
            mimo_result = (
                configure_mimo(self.root, self.home, apply=apply, force=force)
                if host_enabled("mimo")
                else disabled
            )
            grok_result = project_grok(
                self.root,
                self.home,
                apply=apply,
                force=force,
                accounts=tuple(
                    account for account in GROK_HOMES if host_enabled(account.lstrip("."))
                ),
            )
            applied = (
                any(result.applied for result in results.values())
                or claude_result.applied
                or mimo_result.applied
                or grok_result.applied
            )
            if not apply:
                reason = "dry-run"
            elif applied:
                reason = "synced"
            else:
                reason = "nothing-to-sync"
            return RefreshResult(
                applied=applied,
                reason=reason,
                operations=results,
                excluded={
                    reason: tuple(names)
                    for reason, names in sorted(excluded.items())
                },
                claude=claude_result,
                mimo=mimo_result,
                grok=grok_result,
            )


    def _install_under_lock(
        self,
        name: str,
        *,
        apply: bool,
        fail_after: str | None = None,
        force: bool = False,
    ) -> OperationResult:
        self._ensure_no_incomplete()
        registry, report = validate_canonical(self.root, self.home)
        if name not in registry.skills:
            raise ValidationError(f"unknown registry skill: {name}")
        record = registry.skills[name]
        if record["ownership"] != "custom":
            raise ValidationError(f"{name} is not custom and cannot be installed")
        if record["lifecycle"] in {"reference", "retired"}:
            raise ValidationError(
                f"{name} lifecycle {record['lifecycle']} is not installable"
            )
        source = (self.root / record["source"]).resolve()
        source_hash = report.source_hashes[name]
        target = resolve_target(self.home, record["install_targets"][0], name)
        state = load_install_state(self.state_path)
        validate_install_state(state, registry, self.root, self.home)
        entry = state["managed"].get(name)
        target_hash = content_hash(target) if target.is_dir() else None
        if target.exists() and not target.is_dir():
            raise CollisionError(f"target exists but is not a directory: {target}")
        if target_hash is not None and entry is None and not force:
            raise CollisionError(f"refusing unmanaged target collision at {target}")
        if entry is not None:
            if entry["target"] != str(target) or entry["source"] != str(source):
                raise CollisionError(f"managed ownership paths disagree for {name}")
            if target_hash is None:
                raise CollisionError(f"managed target is unexpectedly missing: {target}")
            if target_hash != entry["target_hash"] and not force:
                raise CollisionError(
                    f"managed target is locally modified; preserve/import it before install: {target}"
                )
            if source_hash == entry["source_hash"] and target_hash == source_hash:
                return OperationResult(
                    operation_id=entry["operation_id"],
                    applied=False,
                    reason="already-current",
                )
        changes = [
            f"stage {source} ({source_hash})",
            f"project to {target}",
            f"update {self.state_path}",
        ]
        if not apply:
            return OperationResult(None, False, "dry-run", tuple(changes))
        if not same_filesystem(self.state_root, target.parent):
            raise ValidationError(
                "transaction state and live target must be on the same filesystem"
            )
        self._initialize_mutation_dirs()
        identifier = operation_id()
        transaction = self._create_transaction(identifier)
        staged_root = transaction / "staged"
        staged = staged_root / name
        shutil.copytree(source, staged, copy_function=shutil.copy2)
        _flush_tree(staged)
        _fsync_directory(staged_root)
        _fsync_directory(transaction)
        staged_hash = validate_skill_tree(staged, name)
        if staged_hash != source_hash:
            raise ValidationError("staged skill hash differs from canonical source")
        state_preimage_exists = self.state_path.exists()
        if state_preimage_exists:
            atomic_write_bytes(
                transaction / "state-preimage.json",
                self.state_path.read_bytes(),
            )
        details = {
            "skill": name,
            "source": str(source),
            "source_hash": source_hash,
            "target": str(target),
            "target_hash_before": target_hash,
            "new_hash": staged_hash,
            "preimage_exists": target_hash is not None,
            "state_preimage_exists": state_preimage_exists,
            "registry_revision": registry.revision,
        }
        journal = self._new_journal(
            "install", identifier, changes=changes, details=details
        )
        self._phase(transaction, journal, "prepared", fail_after)
        if target_hash is not None:
            target.rename(transaction / "preimage")
            _fsync_directory(target.parent)
            _fsync_directory(transaction)
        self._phase(transaction, journal, "preimage-preserved", fail_after)
        staged.rename(target)
        _fsync_directory(staged_root)
        _fsync_directory(target.parent)
        _fsync_directory(transaction)
        self._phase(transaction, journal, "target-installed", fail_after)
        installed_hash = validate_skill_tree(target, name)
        if installed_hash != source_hash:
            raise ValidationError("installed target hash differs from canonical source")
        new_state = copy.deepcopy(state)
        new_state["managed"][name] = {
            "source": str(source),
            "source_hash": source_hash,
            "target": str(target),
            "target_hash": installed_hash,
            "operation_id": identifier,
            "installed_at": utc_now(),
            "registry_revision": registry.revision,
            "status": "committed",
        }
        atomic_write_json(self.state_path, new_state)
        self._phase(transaction, journal, "state-committed", fail_after)
        journal["status"] = "committed"
        self._phase(transaction, journal, "committed", fail_after)
        return OperationResult(identifier, True, "installed", tuple(changes))

    def rollback(
        self,
        identifier: str,
        *,
        apply: bool = False,
    ) -> OperationResult:
        with self._lock(exclusive=apply, mutating=apply):
            self._ensure_no_incomplete(allow=identifier)
            transaction = self.transactions / identifier
            operation_path = transaction / "operation.json"
            if not operation_path.is_file():
                raise ValidationError(f"unknown operation ID: {identifier}")
            journal = load_operation(operation_path)
            if journal["status"] == "rolled-back":
                return OperationResult(identifier, False, "already-rolled-back")
            self._ensure_no_newer_active_operation(journal)
            changes = tuple(f"rollback: {item}" for item in journal["changes"])
            if not apply:
                return OperationResult(identifier, False, "dry-run", changes)
            kind = journal["type"]
            if kind == "install":
                self._rollback_install(transaction, journal)
            elif kind == "quarantine":
                self._rollback_quarantine(transaction, journal)
            else:
                self._rollback_lock(transaction, journal)
            journal["status"] = "rolled-back"
            journal["phase"] = "rolled-back"
            self._write_journal(transaction, journal)
            return OperationResult(identifier, True, "rolled-back", changes)

    @staticmethod
    def _operation_resource(journal: dict[str, Any]) -> str:
        details = journal["details"]
        if journal["type"] in {"install", "quarantine"}:
            return details["target"]
        return details["lock_path"]

    def _ensure_no_newer_active_operation(
        self,
        journal: dict[str, Any],
    ) -> None:
        current_key = (journal["created_at"], journal["operation_id"])
        resource = self._operation_resource(journal)
        if not self.transactions.is_dir():
            return
        for path in sorted(self.transactions.glob("*/operation.json")):
            other = load_operation(path)
            if other["operation_id"] == journal["operation_id"]:
                continue
            other_key = (other["created_at"], other["operation_id"])
            if (
                other["status"] == "committed"
                and other_key > current_key
                and self._operation_resource(other) == resource
            ):
                raise CollisionError(
                    "a newer operation still owns this path; roll it back "
                    f"first: {other['operation_id']}"
                )

    def _preserve_current(self, current: Path, destination: Path) -> None:
        if destination.exists():
            raise ValidationError(f"rollback preservation path already exists: {destination}")
        current.rename(destination)
        _fsync_directory(current.parent)
        _fsync_directory(destination.parent)

    def _begin_rollback(self, transaction: Path, journal: dict[str, Any]) -> None:
        # Journal the rollback before its first change, so a stop inside it is
        # reported as incomplete and a repeated rollback resumes from the disk.
        journal["status"] = "rolling-back"
        self._write_journal(transaction, journal)

    def _restore_state_entry(
        self, transaction: Path, details: dict[str, Any]
    ) -> None:
        # Restore only this operation's skill: writing back the whole saved file
        # would also undo newer operations on other skills.
        name = details["skill"]
        before = None
        if details["state_preimage_exists"]:
            preimage = transaction / "state-preimage.json"
            if not preimage.is_file():
                raise ValidationError("operation state preimage is missing")
            before = load_install_state(preimage)["managed"].get(name)
        state = load_install_state(self.state_path)
        if state["managed"].get(name) == before:
            return
        if before is None:
            del state["managed"][name]
        else:
            state["managed"][name] = before
        atomic_write_json(self.state_path, state)

    def _rollback_install(
        self, transaction: Path, journal: dict[str, Any]
    ) -> None:
        # Decide from the disk, not the journaled phase: a stop between a rename
        # and the journal write that records it leaves the phase one step behind.
        details = journal["details"]
        target = Path(details["target"])
        staged = transaction / "staged" / details["skill"]
        aside = transaction / "rollback-new"
        preimage = transaction / "preimage"
        new_live = not staged.exists() and not aside.exists()
        if new_live:
            if not target.is_dir():
                raise ValidationError("installed target missing during rollback")
            if content_hash(target) != details["new_hash"]:
                raise CollisionError(
                    f"installed target changed after operation; refusing rollback: {target}"
                )
        elif preimage.is_dir() or not details["preimage_exists"]:
            if target.exists():
                raise CollisionError(f"rollback target is occupied: {target}")
        elif (
            not target.is_dir()
            or content_hash(target) != details["target_hash_before"]
        ):
            raise CollisionError(
                f"target changed during operation; refusing rollback: {target}"
            )
        if new_live and details["preimage_exists"] and not preimage.is_dir():
            raise ValidationError("target preimage missing during rollback")
        self._begin_rollback(transaction, journal)
        if new_live:
            self._preserve_current(target, aside)
        if preimage.is_dir():
            preimage.rename(target)
            _fsync_directory(target.parent)
            _fsync_directory(transaction)
        self._restore_state_entry(transaction, details)

    def quarantine(
        self,
        name: str,
        *,
        apply: bool = False,
        fail_after: str | None = None,
    ) -> OperationResult:
        with self._lock(exclusive=apply, mutating=apply):
            self._ensure_no_incomplete()
            registry, _ = validate_canonical(self.root, self.home)
            if name not in registry.skills:
                raise ValidationError(f"unknown registry skill: {name}")
            record = registry.skills[name]
            target = resolve_target(self.home, record["install_targets"][0], name)
            if not target.is_dir():
                raise ValidationError(f"quarantine target is not a directory: {target}")
            target_hash = content_hash(target)
            if record["ownership"] == "legacy-unmanaged":
                expected = record["provenance"]["observed_hash"]
                if target_hash != expected:
                    raise CollisionError(
                        f"legacy target changed since snapshot; refusing quarantine: {target}"
                    )
            state = load_install_state(self.state_path)
            validate_install_state(state, registry, self.root, self.home)
            changes = (
                f"move {target} outside discovery",
                f"update {self.state_path} if managed",
            )
            if not apply:
                return OperationResult(None, False, "dry-run", changes)
            if not same_filesystem(target, self.quarantine_root):
                raise ValidationError(
                    "quarantine and live target must be on the same filesystem"
                )
            self._initialize_mutation_dirs()
            identifier = operation_id()
            transaction = self._create_transaction(identifier)
            dated = self.quarantine_root / datetime.now(UTC).strftime("%Y%m%d")
            dated.mkdir(parents=True, exist_ok=True)
            _fsync_directory(self.quarantine_root)
            destination = dated / f"{name}-{identifier}"
            state_preimage_exists = self.state_path.exists()
            if state_preimage_exists:
                atomic_write_bytes(
                    transaction / "state-preimage.json",
                    self.state_path.read_bytes(),
                )
            details = {
                "skill": name,
                "target": str(target),
                "target_hash": target_hash,
                "quarantine_path": str(destination),
                "state_preimage_exists": state_preimage_exists,
            }
            journal = self._new_journal(
                "quarantine", identifier, changes=list(changes), details=details
            )
            self._phase(transaction, journal, "prepared", fail_after)
            target.rename(destination)
            _fsync_directory(target.parent)
            _fsync_directory(destination.parent)
            self._phase(
                transaction,
                journal,
                "target-quarantined",
                fail_after,
            )
            if name in state["managed"]:
                new_state = copy.deepcopy(state)
                del new_state["managed"][name]
                atomic_write_json(self.state_path, new_state)
            self._phase(transaction, journal, "state-committed", fail_after)
            journal["status"] = "committed"
            self._phase(transaction, journal, "committed", None)
            return OperationResult(
                identifier,
                True,
                "quarantined",
                changes,
                quarantine_path=destination,
            )

    def _rollback_quarantine(
        self, transaction: Path, journal: dict[str, Any]
    ) -> None:
        # Decide from the disk, as install rollback does.
        details = journal["details"]
        target = Path(details["target"])
        quarantine = Path(details["quarantine_path"])
        moved = quarantine.exists()
        if moved:
            if target.exists():
                raise CollisionError(f"quarantine rollback target is occupied: {target}")
            if (
                not quarantine.is_dir()
                or content_hash(quarantine) != details["target_hash"]
            ):
                raise CollisionError(f"quarantined tree was modified: {quarantine}")
        elif not target.is_dir():
            raise ValidationError(f"quarantined tree is missing: {quarantine}")
        elif content_hash(target) != details["target_hash"]:
            raise CollisionError(
                f"target changed during operation; refusing rollback: {target}"
            )
        self._begin_rollback(transaction, journal)
        if moved:
            quarantine.rename(target)
            _fsync_directory(target.parent)
            _fsync_directory(quarantine.parent)
        self._restore_state_entry(transaction, details)

    def _validate_lock(self) -> tuple[dict[str, Any], bytes]:
        if not self.skill_lock_path.is_file():
            raise ValidationError(f"skill lock does not exist: {self.skill_lock_path}")
        raw = self.skill_lock_path.read_bytes()
        data = load_json(self.skill_lock_path, "skill lock")
        if not isinstance(data, dict) or data.get("version") != 3:
            raise ValidationError("skill lock must be a version-3 JSON object")
        skills = data.get("skills")
        if not isinstance(skills, dict):
            raise ValidationError("skill lock skills must be an object")
        matt_names = {
            name
            for name, entry in skills.items()
            if isinstance(entry, dict) and entry.get("source") == "mattpocock/skills"
        }
        if matt_names != EXPECTED_MATT_SKILLS:
            missing = sorted(EXPECTED_MATT_SKILLS - matt_names)
            unexpected = sorted(matt_names - EXPECTED_MATT_SKILLS)
            raise ValidationError(
                "skill lock expected Matt set mismatch; "
                f"missing={missing}, unexpected={unexpected}"
            )
        for name in EXPECTED_MATT_SKILLS:
            entry = skills.get(name)
            if not isinstance(entry, dict) or entry.get("source") != "mattpocock/skills":
                raise ValidationError(f"unexpected source owner for {name}")
        return data, raw

    def _matching_completed_lock_migration(self) -> str | None:
        if not self.transactions.is_dir() or not self.skill_lock_path.is_file():
            return None
        current_hash = sha256_bytes(self.skill_lock_path.read_bytes())
        for path in sorted(self.transactions.glob("*/operation.json"), reverse=True):
            journal = load_operation(path)
            if (
                journal["type"] == "lock-migration"
                and journal["status"] == "committed"
                and journal["details"].get("post_hash") == current_hash
            ):
                return journal["operation_id"]
        return None

    def migrate_lock(
        self,
        *,
        apply: bool = False,
        fail_after: str | None = None,
    ) -> OperationResult:
        with self._lock(exclusive=apply, mutating=apply):
            self._ensure_no_incomplete()
            try:
                data, raw = self._validate_lock()
            except ValidationError:
                completed = self._matching_completed_lock_migration()
                if completed is not None:
                    return OperationResult(completed, False, "already-current")
                raise
            removed = tuple(sorted(EXPECTED_MATT_SKILLS))
            changes = (
                f"back up exact preimage of {self.skill_lock_path}",
                f"remove exactly {len(removed)} mattpocock/skills entries",
                "preserve find-skills, UI state, and unknown top-level fields",
            )
            if not apply:
                return OperationResult(
                    None, False, "dry-run", changes, removed=removed
                )
            self._initialize_mutation_dirs()
            identifier = operation_id()
            transaction = self._create_transaction(identifier)
            atomic_write_bytes(transaction / "lock-preimage.json", raw)
            after = copy.deepcopy(data)
            for name in removed:
                del after["skills"][name]
            after_bytes = json.dumps(after, indent=2, sort_keys=True).encode() + b"\n"
            details = {
                "lock_path": str(self.skill_lock_path),
                "pre_hash": sha256_bytes(raw),
                "post_hash": sha256_bytes(after_bytes),
                "removed": list(removed),
            }
            journal = self._new_journal(
                "lock-migration", identifier, changes=list(changes), details=details
            )
            self._phase(transaction, journal, "prepared", fail_after)
            atomic_write_bytes(self.skill_lock_path, after_bytes)
            reparsed = load_json(self.skill_lock_path, "migrated skill lock")
            if reparsed != after:
                raise ValidationError("migrated skill lock did not reparse identically")
            self._phase(transaction, journal, "lock-replaced", fail_after)
            journal["status"] = "committed"
            self._phase(transaction, journal, "committed", None)
            return OperationResult(
                identifier, True, "lock-migrated", changes, removed=removed
            )

    def _rollback_lock(
        self, transaction: Path, journal: dict[str, Any]
    ) -> None:
        details = journal["details"]
        lock_path = Path(details["lock_path"])
        preimage = transaction / "lock-preimage.json"
        if not lock_path.is_file() or not preimage.is_file():
            raise ValidationError("lock migration rollback preimage or target is missing")
        # Decide from the lock's bytes, not the journaled phase, as install
        # rollback does.
        current = lock_path.read_bytes()
        if sha256_bytes(current) == details["pre_hash"]:
            return
        if sha256_bytes(current) != details["post_hash"]:
            raise CollisionError("skill lock changed after migration; refusing rollback")
        self._begin_rollback(transaction, journal)
        atomic_write_bytes(transaction / "rollback-lock.json", current)
        atomic_write_bytes(lock_path, preimage.read_bytes())
        if sha256_bytes(lock_path.read_bytes()) != details["pre_hash"]:
            raise ValidationError("lock rollback did not restore exact preimage")
