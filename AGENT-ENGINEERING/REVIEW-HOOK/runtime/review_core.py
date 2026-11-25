"""Host-neutral Git/reflog cadence state machine.

The core observes exact commit actions, owns session cadence and deduplication,
and emits immutable ``ReviewRequest`` objects. It never reviews or mutates the
target repository; host adapters only deliver its requests.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

from .analysis.evidence_package import (
    ReviewScanConfig,
    ReviewScanError,
    ReviewScanResult,
    failed_scan_result,
    scan_range,
)
from .analysis.model import (
    AnalysisHealth,
    AnalysisStatus,
    CommitRange,
    PolicyIdentity,
    RepositoryIdentity,
    ReviewEvidence,
)
from .analysis.outcomes import (
    OutcomeStore,
    OutcomeStoreError,
    build_auto_outcome,
    default_outcome_root,
    delivery_identity,
    outcome_evidence,
)
from .operational_health import OperationalJournal, OperationalJournalError
from .operational_state import locked_session, write_state
from .review_request import (
    CapabilityRef,
    PromptIntent,
    ReviewKind,
    ReviewMode,
    ReviewRequest,
)

MAX_TARGETS = 4
GIT_PROBE_TIMEOUT_SECONDS = 1.5
SHELL_CONTROL = frozenset(";&|()")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
COMMIT_REFLOG_ACTION = re.compile(br"^commit(?: \([^)]*\))?:")
FOUND_GIT = shutil.which("git")
TRUSTED_GIT = str(Path(FOUND_GIT).resolve()) if FOUND_GIT else None

GIT_OPTIONS_WITH_VALUES = frozenset(
    {
        "-C",
        "-c",
        "--config-env",
        "--git-dir",
        "--namespace",
        "--super-prefix",
        "--work-tree",
    }
)
COMMIT_OPTIONS_WITH_VALUES = frozenset(
    {
        "-C",
        "-F",
        "-c",
        "-m",
        "-t",
        "--author",
        "--cleanup",
        "--date",
        "--file",
        "--fixup",
        "--message",
        "--pathspec-from-file",
        "--reedit-message",
        "--reuse-message",
        "--squash",
        "--template",
        "--trailer",
    }
)

_CADENCE_POLICY_SPEC = {
    "name": "cadence",
    "version": "v1",
    "branch_precedence": True,
    "multiple_commits_select_branch": True,
    "standard_and_branch_intervals_are_independent": True,
}
_CADENCE_POLICY_BYTES = json.dumps(
    _CADENCE_POLICY_SPEC, sort_keys=True, separators=(",", ":")
).encode("utf-8")
CADENCE_POLICY = PolicyIdentity(
    name="cadence",
    version="v1",
    digest="sha256:" + hashlib.sha256(_CADENCE_POLICY_BYTES).hexdigest(),
)
CADENCE_POLICIES = (CADENCE_POLICY,)
EXPECTED_DIFF_REVIEW = CapabilityRef(
    name="diff-review",
    revision="current",
    contract="diff-review",
    digest="sha256:a8d8e31f6bb1af642db81e91f345cd095c973a5b98c2b506264d8338fd8f4fd0",
)


@dataclass(frozen=True)
class ReviewDecision:
    """One cadence outcome, possibly carrying one request per repository."""

    kind: ReviewKind
    counts: Tuple[int, ...]
    requests: Tuple[ReviewRequest, ...]

    def __post_init__(self) -> None:
        if not self.counts or not self.requests:
            raise ValueError("a review decision requires counts and requests")
        if any(request.kind is not self.kind for request in self.requests):
            raise ValueError("all requests in a cadence decision must share its kind")


@dataclass(frozen=True)
class _CommitObservation:
    identity: str
    repository: str
    old_oid: str
    new_oid: str
    empty_tree: str
    analysis_root: Optional[str]


class ReviewAfterCommit:
    """Record commit candidates and select exact read-only review requests."""

    def __init__(
        self,
        state_dir: Path,
        branch_every: Optional[int],
        standard_every: int = 1,
        mode: ReviewMode = ReviewMode.CADENCE,
        outcome_store: Optional[OutcomeStore] = None,
        scan_config: Optional[ReviewScanConfig] = None,
    ) -> None:
        if branch_every is not None and (
            type(branch_every) is not int or branch_every < 1
        ):
            raise ValueError("branch review interval must be a positive integer")
        if type(standard_every) is not int or standard_every < 1:
            raise ValueError("standard review interval must be a positive integer")
        if mode is ReviewMode.CADENCE and (
            outcome_store is not None or scan_config is not None
        ):
            raise ValueError("cadence mode cannot accept automatic-review state or scan config")
        if not isinstance(mode, ReviewMode):
            raise ValueError("review mode must be typed")
        self._state_dir = state_dir
        self._branch_every = branch_every
        self._standard_every = standard_every
        self._mode = mode
        self._outcome_store = (
            outcome_store
            if outcome_store is not None
            else OutcomeStore(default_outcome_root())
            if mode is ReviewMode.AUTO
            else None
        )
        self._scan_config = scan_config or ReviewScanConfig()
        self._operational_journal = OperationalJournal(
            self._state_dir / "operational"
        )
        self._operational_notices: List[str] = []

    def take_operational_notices(self) -> Tuple[str, ...]:
        """Return and clear bounded notices produced by the latest hook action."""

        notices = tuple(self._operational_notices)
        self._operational_notices.clear()
        return notices

    def operational_summary(self) -> Dict[str, Any]:
        """Return private aggregate health facts for status reporting."""

        return self._operational_journal.summary()

    @classmethod
    def from_environment(
        cls,
        state_dir_variable: str,
        branch_every_variable: str,
        standard_every_variable: Optional[str] = None,
        mode_variable: Optional[str] = None,
    ) -> "ReviewAfterCommit":
        state_dir_raw = os.environ.get(state_dir_variable)
        if not state_dir_raw:
            raise ValueError("{} is required".format(state_dir_variable))
        branch_interval = _positive_interval(
            os.environ.get(branch_every_variable),
            "branch review interval",
            default=None,
        )
        standard_interval = _positive_interval(
            os.environ.get(standard_every_variable)
            if standard_every_variable is not None
            else None,
            "standard review interval",
            default=1,
        )
        raw_mode = os.environ.get(mode_variable) if mode_variable else None
        try:
            mode = ReviewMode(raw_mode or ReviewMode.CADENCE.value)
        except ValueError as error:
            raise ValueError("review mode must be cadence or auto") from error
        return cls(Path(state_dir_raw), branch_interval, standard_interval, mode)

    def record_delivery(
        self,
        decision: ReviewDecision,
        host: str,
        delivery_context: str,
    ) -> Dict[str, str]:
        """Record each automatic request immediately before a host emits it."""

        if decision.kind is not ReviewKind.SIGNALS:
            return {}
        if self._mode is not ReviewMode.AUTO or self._outcome_store is None:
            raise AssertionError("signal delivery has no automatic outcome store")
        recorded: Dict[str, str] = {}
        for request in decision.requests:
            identity = delivery_identity(request.event_id, host, delivery_context)
            try:
                self._outcome_store.record_delivery(
                    request.repository,
                    request.event_id,
                    identity,
                    host,
                )
            except (OutcomeStoreError, OSError):
                self._add_notice(
                    "review-after-commit outcome capture: outcome-store-error; "
                    "review delivery continues"
                )
                continue
            recorded[request.event_id] = identity
        return recorded

    def find_commit_targets(self, command: str, cwd: str) -> List[Dict[str, Any]]:
        return _git_commit_targets(command, cwd)

    def record_before(
        self,
        session_id: str,
        tool_event_id: str,
        targets: List[Dict[str, Any]],
    ) -> None:
        if not isinstance(tool_event_id, str) or not tool_event_id:
            raise ValueError("tool_event_id must be a non-empty string")
        snapshots = [_resolve_target(target) for target in targets]
        with locked_session(
            self._state_dir,
            session_id,
            self._branch_every,
            self._standard_every,
            _valid_target,
        ) as (state_path, state):
            if tool_event_id in state["events"] or tool_event_id in state["ignored"]:
                return
            previous = state["pending"].get(tool_event_id)
            if previous is not None:
                if previous != snapshots:
                    raise ValueError(
                        "PreToolUse snapshot changed for {!r}".format(tool_event_id)
                    )
                return
            state["pending"][tool_event_id] = snapshots
            write_state(state_path, state)

    def discard_pending(self, session_id: str, tool_event_id: str) -> None:
        """Retire one unused pre-snapshot without changing recorded cadence."""

        if not isinstance(tool_event_id, str) or not tool_event_id:
            raise ValueError("tool_event_id must be a non-empty string")
        with locked_session(
            self._state_dir,
            session_id,
            self._branch_every,
            self._standard_every,
            _valid_target,
        ) as (state_path, state):
            if tool_event_id in state["events"] or tool_event_id in state["ignored"]:
                return
            if state["pending"].pop(tool_event_id, None) is None:
                return
            state["ignored"].append(tool_event_id)
            write_state(state_path, state)

    def review_event(
        self, session_id: str, tool_event_id: str, *, replay_processed: bool = True
    ) -> Optional[ReviewDecision]:
        """Consume an observation, optionally replaying its recorded decision.

        Retry-driven hosts need replay; Codex's immediate PostToolUse delivery
        consumes only once. Both checks share the existing session lock and
        event record, including when two callbacks race. This is not an
        exactly-once guarantee across a crash between consumption and emission.
        """
        with locked_session(
            self._state_dir,
            session_id,
            self._branch_every,
            self._standard_every,
            _valid_target,
        ) as (_, state):
            previous = state["events"].get(tool_event_id)
            if previous is not None:
                return self._decision(previous["counts"], previous["ranges"]) if replay_processed else None
            if tool_event_id in state["ignored"]:
                return None
            snapshots = state["pending"].get(tool_event_id)
            if snapshots is None:
                raise ValueError(
                    "missing PreToolUse snapshot for {!r}".format(tool_event_id)
                )

        observed = _commit_observations_after(snapshots)
        scans = self._record_auto_outcomes(session_id, observed)

        with locked_session(
            self._state_dir,
            session_id,
            self._branch_every,
            self._standard_every,
            _valid_target,
        ) as (state_path, state):
            previous = state["events"].get(tool_event_id)
            if previous is not None:
                return self._decision(previous["counts"], previous["ranges"]) if replay_processed else None
            if tool_event_id in state["ignored"]:
                return None
            if state["pending"].get(tool_event_id) != snapshots:
                raise ValueError(
                    "PreToolUse snapshot changed for {!r}".format(tool_event_id)
                )
            records = _consume_observations(state, [(tool_event_id, observed)])
            write_state(state_path, state)
        if not records:
            return None
        record = records[0]
        return self._decision(record["counts"], record["ranges"], scans)

    def review_pending(self, session_id: str) -> Optional[ReviewDecision]:
        with locked_session(
            self._state_dir,
            session_id,
            self._branch_every,
            self._standard_every,
            _valid_target,
        ) as (_, state):
            pending = list(state["pending"].items())
        if not pending:
            return None

        observations = [
            (tool_event_id, snapshots, _commit_observations_after(snapshots))
            for tool_event_id, snapshots in pending
        ]
        scans: Dict[Tuple[str, str, str, int], ReviewScanResult] = {}
        for _, _, observed in observations:
            scans.update(self._record_auto_outcomes(session_id, observed))

        with locked_session(
            self._state_dir,
            session_id,
            self._branch_every,
            self._standard_every,
            _valid_target,
        ) as (state_path, state):
            current: List[Tuple[str, List[_CommitObservation]]] = []
            for tool_event_id, snapshots, observed in observations:
                if tool_event_id in state["events"] or tool_event_id in state["ignored"]:
                    continue
                current_snapshots = state["pending"].get(tool_event_id)
                if current_snapshots is None:
                    continue
                if current_snapshots != snapshots:
                    raise ValueError(
                        "PreToolUse snapshot changed for {!r}".format(tool_event_id)
                    )
                current.append((tool_event_id, observed))
            if not current:
                return None
            records = _consume_observations(state, current)
            write_state(state_path, state)
        if not records:
            return None
        counts = tuple(
            event_count for record in records for event_count in record["counts"]
        )
        ranges = [item for record in records for item in record["ranges"]]
        return self._decision(counts, ranges, scans)

    def _record_auto_outcomes(
        self, session_id: str, observations: Sequence[_CommitObservation]
    ) -> Dict[Tuple[str, str, str, int], ReviewScanResult]:
        results: Dict[Tuple[str, str, str, int], ReviewScanResult] = {}
        if self._mode is not ReviewMode.AUTO or not observations:
            return results
        if self._outcome_store is None:
            raise AssertionError("auto mode has no outcome store")
        for root, repository, commit_range, ordered in _analysis_ranges_from_observations(
            observations
        ):
            if root is None:
                result = failed_scan_result(
                    repository,
                    commit_range,
                    ordered,
                    issue="review-scan-repository-root-unavailable",
                    config=self._scan_config,
                )
            else:
                started = time.monotonic()
                try:
                    result = scan_range(
                        Path(root),
                        commit_range.before,
                        commit_range.after,
                        config=self._scan_config,
                    )
                except ReviewScanError:
                    result = failed_scan_result(
                        repository,
                        commit_range,
                        ordered,
                        config=self._scan_config,
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
            if result.repository != repository or result.evidence.commit_range != commit_range:
                raise ValueError("Review Scan returned evidence for a different exact range")
            store_failure = False
            try:
                event = build_auto_outcome(
                    result,
                    repository_path=Path(root) if root is not None else None,
                )
                self._outcome_store.append(repository, event)
            except (OutcomeStoreError, OSError):
                store_failure = True
            results[_scan_key(repository, commit_range)] = result
            try:
                notice = self._operational_journal.record(
                    session_id,
                    self._mode.value,
                    result,
                    status_override=(
                        AnalysisStatus.ERROR if store_failure else None
                    ),
                    issues_override=(
                        ("outcome-store-error",) if store_failure else None
                    ),
                )
            except (OperationalJournalError, OSError):
                notice = (
                    "review-after-commit analyzer health: operational-journal-error; "
                    "automatic selection continues"
                )
            if notice:
                self._add_notice(notice)
        return results

    def _add_notice(self, notice: str) -> None:
        if notice not in self._operational_notices:
            self._operational_notices.append(notice)

    def _decision(
        self,
        counts: Sequence[int],
        ranges: Sequence[Dict[str, Any]],
        scans: Optional[Mapping[Tuple[str, str, str, int], ReviewScanResult]] = None,
    ) -> Optional[ReviewDecision]:
        if self._mode is ReviewMode.AUTO:
            return self._auto_decision(counts, ranges, scans or {})
        if len(counts) > 1 or (
            self._branch_every is not None
            and any(count % self._branch_every == 0 for count in counts)
        ):
            kind = ReviewKind.BRANCH
        elif any(count % self._standard_every == 0 for count in counts):
            kind = ReviewKind.RECENT
        else:
            return None
        requests = tuple(self._request(item, kind) for item in ranges)
        return ReviewDecision(kind, tuple(counts), requests)

    def _auto_decision(
        self,
        counts: Sequence[int],
        ranges: Sequence[Dict[str, Any]],
        scans: Mapping[Tuple[str, str, str, int], ReviewScanResult],
    ) -> Optional[ReviewDecision]:
        if self._outcome_store is None:
            raise AssertionError("auto mode has no outcome store")
        requests: List[ReviewRequest] = []
        for exact_range in ranges:
            repository = RepositoryIdentity(exact_range["repository"])
            commit_range = CommitRange(
                exact_range["before"],
                exact_range["after"],
                exact_range["commits"],
            )
            result = scans.get(_scan_key(repository, commit_range))
            if result is not None:
                if result.auto_available and result.auto_candidate.matched:
                    requests.append(self._auto_request(repository, result.evidence))
                continue
            try:
                event = self._outcome_store.find(repository, commit_range)
                if event is not None and event["selected"]:
                    requests.append(
                        self._auto_request(
                            repository, outcome_evidence(event, repository)
                        )
                    )
            except (OutcomeStoreError, OSError):
                self._add_notice(
                    "review-after-commit outcome capture: outcome-store-error; "
                    "duplicate delivery was skipped"
                )
        if not requests:
            return None
        return ReviewDecision(ReviewKind.SIGNALS, tuple(counts), tuple(requests))

    def _auto_request(
        self, repository: RepositoryIdentity, evidence: ReviewEvidence
    ) -> ReviewRequest:
        return ReviewRequest(
            event_id=evidence.event_id,
            repository=repository,
            commit_range=evidence.commit_range,
            kind=ReviewKind.SIGNALS,
            mode=ReviewMode.AUTO,
            policies=evidence.policies,
            health=evidence.health,
            prompt_intent=PromptIntent.REVIEW_SIGNALS,
            expected_skill=EXPECTED_DIFF_REVIEW,
            evidence=evidence,
        )

    def _request(self, exact_range: Dict[str, Any], kind: ReviewKind) -> ReviewRequest:
        commit_range = CommitRange(
            exact_range["before"],
            exact_range["after"],
            exact_range["commits"],
        )
        repository = RepositoryIdentity(exact_range["repository"])
        event_payload = {
            "schema": "review-event/v1",
            "repository": repository.digest,
            "range": {
                "before": commit_range.before,
                "after": commit_range.after,
                "commits": commit_range.commits,
            },
            "policies": [
                {
                    "name": policy.name,
                    "version": policy.version,
                    "digest": policy.digest,
                }
                for policy in CADENCE_POLICIES
            ],
        }
        event_id = "sha256:" + hashlib.sha256(
            json.dumps(event_payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        prompt_intent = {
            ReviewKind.RECENT: PromptIntent.REVIEW_RECENT,
            ReviewKind.BRANCH: PromptIntent.REVIEW_BRANCH,
        }[kind]
        return ReviewRequest(
            event_id=event_id,
            repository=repository,
            commit_range=commit_range,
            kind=kind,
            mode=self._mode,
            policies=CADENCE_POLICIES,
            health=AnalysisHealth(AnalysisStatus.SKIPPED_MODE),
            prompt_intent=prompt_intent,
            expected_skill=EXPECTED_DIFF_REVIEW,
        )


def _positive_interval(
    value: Optional[str], name: str, default: Optional[int]
) -> Optional[int]:
    if value in (None, ""):
        return default
    if not isinstance(value, str) or not value.isdecimal() or int(value) < 1:
        raise ValueError("{} must be a positive integer".format(name))
    return int(value)


def _shell_segments(command: str) -> Iterator[List[str]]:
    if not isinstance(command, str):
        raise ValueError("command must be a string")
    lexer = shlex.shlex(
        command.replace("\n", ";"),
        posix=True,
        punctuation_chars=";&|()",
    )
    lexer.whitespace_split = True
    lexer.commenters = ""
    segment: List[str] = []
    for token in lexer:
        if token and all(character in SHELL_CONTROL for character in token):
            if segment:
                yield segment
                segment = []
        else:
            segment.append(token)
    if segment:
        yield segment


def _command_index(tokens: Sequence[str]) -> Optional[int]:
    index = 0
    while index < len(tokens) and ASSIGNMENT.match(tokens[index]):
        index += 1
    if index >= len(tokens):
        return None
    if Path(tokens[index]).name == "command":
        index += 1
        while index < len(tokens) and tokens[index].startswith("-"):
            index += 1
    return index if index < len(tokens) else None


def _git_subcommand_index(tokens: Sequence[str], git_index: int) -> Optional[int]:
    index = git_index + 1
    while index < len(tokens):
        token = tokens[index]
        option_name = token.split("=", 1)[0]
        if option_name in GIT_OPTIONS_WITH_VALUES and "=" not in token:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return index
    return None


def _changed_directory(tokens: Sequence[str], command_index: int, cwd: Path) -> Path:
    arguments = list(tokens[command_index + 1 :])
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if not arguments:
        return Path.home().resolve()
    if arguments[0] == "-":
        return cwd
    destination = Path(arguments[0]).expanduser()
    if not destination.is_absolute():
        destination = cwd / destination
    return destination.resolve()


def _commit_is_dry_run(arguments: Sequence[str]) -> bool:
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token == "--":
            return False
        if token == "--dry-run":
            return True
        option_name = token.split("=", 1)[0]
        short_value_option_is_last = False
        if token.startswith("-") and not token.startswith("--"):
            for option_index, option in enumerate(token[1:], start=1):
                if option in "CFcmt":
                    short_value_option_is_last = option_index == len(token) - 1
                    break
        if "=" not in token and (
            option_name in COMMIT_OPTIONS_WITH_VALUES or short_value_option_is_last
        ):
            index += 2
        else:
            index += 1
    return False


def _git_commit_targets(command: str, cwd: str) -> List[Dict[str, Any]]:
    if not isinstance(cwd, str) or not cwd:
        raise ValueError("cwd must be a non-empty string")
    working_directory = Path(cwd).expanduser().resolve()
    targets: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, Tuple[str, ...]]] = set()
    for segment in _shell_segments(command):
        command_index = _command_index(segment)
        if command_index is None:
            continue
        executable = Path(segment[command_index]).name
        if executable == "cd":
            working_directory = _changed_directory(
                segment, command_index, working_directory
            )
            continue
        if executable != "git":
            continue
        subcommand_index = _git_subcommand_index(segment, command_index)
        if subcommand_index is None or segment[subcommand_index] != "commit":
            continue
        if _commit_is_dry_run(segment[subcommand_index + 1 :]):
            continue
        if TRUSTED_GIT is None:
            raise ValueError("git is not available on PATH")
        argv = [TRUSTED_GIT, *segment[command_index + 1 : subcommand_index]]
        identity = (str(working_directory), tuple(argv))
        if identity in seen:
            continue
        seen.add(identity)
        targets.append(
            {
                "cwd": str(working_directory),
                "argv": argv,
                "git_dir": None,
                "head": None,
                "head_log": None,
                "head_log_size": 0,
            }
        )
        if len(targets) > MAX_TARGETS:
            raise ValueError(
                "a hook event may target at most {} repositories".format(MAX_TARGETS)
            )
    return targets


def _run_git(
    target: Dict[str, Any], *arguments: str, input_text: Optional[str] = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*target["argv"], *arguments],
        cwd=target["cwd"],
        text=True,
        input=input_text,
        capture_output=True,
        check=False,
        timeout=GIT_PROBE_TIMEOUT_SECONDS,
    )


def _resolve_target(target: Dict[str, Any]) -> Dict[str, Any]:
    resolved = {
        "cwd": target["cwd"],
        "argv": list(target["argv"]),
        "git_dir": None,
        "head": None,
        "head_log": None,
        "head_log_size": 0,
    }
    if not Path(resolved["cwd"]).is_dir():
        return resolved
    git_dir_result = _run_git(resolved, "rev-parse", "--absolute-git-dir")
    if git_dir_result.returncode != 0:
        return resolved
    git_dir = git_dir_result.stdout.strip()
    if not git_dir or not Path(git_dir).is_absolute():
        raise ValueError("git rev-parse returned an invalid Git directory")
    resolved["git_dir"] = git_dir

    log_result = _run_git(
        resolved,
        "rev-parse",
        "--path-format=absolute",
        "--git-path",
        "logs/HEAD",
    )
    if log_result.returncode != 0:
        raise ValueError(
            "git rev-parse could not resolve the HEAD reflog for {}".format(git_dir)
        )
    head_log = log_result.stdout.strip()
    if not head_log or not Path(head_log).is_absolute():
        raise ValueError(
            "git rev-parse returned an invalid HEAD reflog path: {!r}".format(head_log)
        )
    resolved["head_log"] = head_log
    log_path = Path(head_log)
    if log_path.exists():
        if not log_path.is_file():
            raise ValueError("Git HEAD reflog is not a file: {}".format(head_log))
        resolved["head_log_size"] = log_path.stat().st_size

    head_result = _run_git(resolved, "rev-parse", "--verify", "HEAD")
    if head_result.returncode == 0:
        head = head_result.stdout.strip()
        if OBJECT_ID.fullmatch(head) is None:
            raise ValueError(
                "git rev-parse returned an invalid object id: {!r}".format(head)
            )
        resolved["head"] = head
    return resolved


def _valid_git_argv(argv: Any) -> bool:
    if (
        TRUSTED_GIT is None
        or not isinstance(argv, list)
        or not argv
        or argv[0] != TRUSTED_GIT
        or not all(isinstance(argument, str) and argument for argument in argv)
    ):
        return False
    probe = [*argv, "commit"]
    return _git_subcommand_index(probe, 0) == len(argv)


def _valid_target(target: Any) -> bool:
    if not isinstance(target, dict) or set(target) != {
        "cwd",
        "argv",
        "git_dir",
        "head",
        "head_log",
        "head_log_size",
    }:
        return False
    cwd = target["cwd"]
    git_dir = target["git_dir"]
    head = target["head"]
    head_log = target["head_log"]
    head_log_size = target["head_log_size"]
    return (
        isinstance(cwd, str)
        and bool(cwd)
        and Path(cwd).is_absolute()
        and _valid_git_argv(target["argv"])
        and (
            git_dir is None
            or isinstance(git_dir, str)
            and Path(git_dir).is_absolute()
        )
        and (
            head is None
            or isinstance(head, str)
            and OBJECT_ID.fullmatch(head) is not None
        )
        and (
            head_log is None
            or isinstance(head_log, str)
            and Path(head_log).is_absolute()
        )
        and type(head_log_size) is int
        and head_log_size >= 0
        and (
            git_dir is not None
            and head_log is not None
            or git_dir is None
            and head is None
            and head_log is None
            and head_log_size == 0
        )
    )


def _repository_details(
    target: Dict[str, Any]
) -> Tuple[str, str, Optional[str]]:
    common_result = _run_git(
        target,
        "rev-parse",
        "--path-format=absolute",
        "--git-common-dir",
    )
    if common_result.returncode != 0:
        raise ValueError("git could not resolve the common repository directory")
    common_dir = common_result.stdout.strip()
    if not common_dir or not Path(common_dir).is_absolute():
        raise ValueError("git returned an invalid common repository directory")
    canonical_common_dir = str(Path(common_dir).resolve())
    repository = "sha256:" + hashlib.sha256(
        ("review-repository/v1\0" + canonical_common_dir).encode("utf-8")
    ).hexdigest()

    empty_result = _run_git(target, "hash-object", "-t", "tree", "--stdin", input_text="")
    if empty_result.returncode != 0:
        raise ValueError("git could not resolve the empty-tree object")
    empty_tree = empty_result.stdout.strip()
    if OBJECT_ID.fullmatch(empty_tree) is None:
        raise ValueError("git returned an invalid empty-tree object")
    root_result = _run_git(target, "rev-parse", "--show-toplevel")
    analysis_root: Optional[str] = None
    if root_result.returncode == 0:
        root = root_result.stdout.strip()
        if root and Path(root).is_absolute():
            analysis_root = str(Path(root).resolve())
    return repository, empty_tree, analysis_root


def _new_commit_observations(before: Dict[str, Any]) -> List[_CommitObservation]:
    after = _resolve_target(before)
    if after["git_dir"] is None or after["head_log"] is None:
        return []
    if before["git_dir"] is not None and before["git_dir"] != after["git_dir"]:
        return []
    if before["head_log"] is not None and before["head_log"] != after["head_log"]:
        return []

    offset = before["head_log_size"] if before["head_log"] is not None else 0
    if after["head_log_size"] < offset:
        raise ValueError(
            "Git HEAD reflog shrank during the tool call: {}".format(after["head_log"])
        )
    if after["head_log_size"] == offset:
        return []
    log_path = Path(after["head_log"])
    with log_path.open("rb") as stream:
        stream.seek(offset)
        expected_bytes = after["head_log_size"] - offset
        appended = stream.read(expected_bytes)
    if len(appended) != expected_bytes or log_path.stat().st_size != after["head_log_size"]:
        raise ValueError(
            "Git HEAD reflog changed while it was being read: {}".format(
                after["head_log"]
            )
        )

    repository, empty_tree, analysis_root = _repository_details(after)
    observations: List[_CommitObservation] = []
    line_offset = offset
    for line in appended.splitlines(keepends=True):
        stripped = line.rstrip(b"\r\n")
        metadata, separator, action = stripped.partition(b"\t")
        if separator and COMMIT_REFLOG_ACTION.match(action) is not None:
            fields = metadata.split(b" ", 2)
            if len(fields) < 2:
                raise ValueError(
                    "invalid Git HEAD reflog entry in {}".format(after["head_log"])
                )
            try:
                old_oid = fields[0].decode("ascii")
                new_oid = fields[1].decode("ascii")
            except UnicodeDecodeError as error:
                raise ValueError(
                    "invalid object id in {}".format(after["head_log"])
                ) from error
            if (
                (OBJECT_ID.fullmatch(old_oid) is None and set(old_oid) != {"0"})
                or OBJECT_ID.fullmatch(new_oid) is None
                or len(old_oid) != len(new_oid)
            ):
                raise ValueError(
                    "invalid object ids in {}: {!r} -> {!r}".format(
                        after["head_log"], old_oid, new_oid
                    )
                )
            identity_bytes = (
                "{}\0{}\0{}\0".format(
                    after["git_dir"], after["head_log"], line_offset
                ).encode("utf-8")
                + stripped
            )
            observations.append(
                _CommitObservation(
                    identity=hashlib.sha256(identity_bytes).hexdigest(),
                    repository=repository,
                    old_oid=old_oid,
                    new_oid=new_oid,
                    empty_tree=empty_tree,
                    analysis_root=analysis_root,
                )
            )
        line_offset += len(line)

    if observations:
        expected_before = before["head"]
        first = observations[0]
        if expected_before is None:
            if set(first.old_oid) != {"0"}:
                raise ValueError(
                    "commit attribution is ambiguous: the first commit did not start "
                    "from the observed unborn repository"
                )
        elif first.old_oid != expected_before:
            raise ValueError(
                "commit attribution is ambiguous: HEAD moved before the first commit"
            )
        for previous, current in zip(observations, observations[1:]):
            if current.old_oid != previous.new_oid:
                raise ValueError(
                    "commit attribution is ambiguous: commit actions are not contiguous"
                )
    return observations


def _commit_observations_after(
    snapshots: Sequence[Dict[str, Any]],
) -> List[_CommitObservation]:
    observed: List[_CommitObservation] = []
    seen: Set[str] = set()
    for before in snapshots:
        for item in _new_commit_observations(before):
            if item.identity not in seen:
                seen.add(item.identity)
                observed.append(item)
    return observed


def _ranges_from_observations(
    observations: Sequence[_CommitObservation],
) -> List[Dict[str, Any]]:
    repository_order: List[str] = []
    by_repository: Dict[str, List[_CommitObservation]] = {}
    for observation in observations:
        if observation.repository not in by_repository:
            repository_order.append(observation.repository)
            by_repository[observation.repository] = []
        by_repository[observation.repository].append(observation)

    ranges: List[Dict[str, Any]] = []
    for repository in repository_order:
        items = by_repository[repository]
        for previous, current in zip(items, items[1:]):
            if current.old_oid != previous.new_oid:
                raise ValueError(
                    "cannot represent a non-contiguous repository range exactly"
                )
        first = items[0]
        before = first.empty_tree if set(first.old_oid) == {"0"} else first.old_oid
        ranges.append(
            {
                "repository": repository,
                "before": before,
                "after": items[-1].new_oid,
                "commits": len(items),
            }
        )
    return ranges


def _analysis_ranges_from_observations(
    observations: Sequence[_CommitObservation],
) -> List[Tuple[Optional[str], RepositoryIdentity, CommitRange, Tuple[str, ...]]]:
    ranges = _ranges_from_observations(observations)
    by_repository: Dict[str, List[_CommitObservation]] = {}
    for observation in observations:
        by_repository.setdefault(observation.repository, []).append(observation)
    result = []
    for exact_range in ranges:
        items = by_repository[exact_range["repository"]]
        roots = {item.analysis_root for item in items}
        if len(roots) != 1:
            raise ValueError("repository root changed within one exact commit range")
        result.append(
            (
                next(iter(roots)),
                RepositoryIdentity(exact_range["repository"]),
                CommitRange(
                    exact_range["before"],
                    exact_range["after"],
                    exact_range["commits"],
                ),
                tuple(item.new_oid for item in items),
            )
        )
    return result


def _scan_key(
    repository: RepositoryIdentity, commit_range: CommitRange
) -> Tuple[str, str, str, int]:
    return (
        repository.digest,
        commit_range.before,
        commit_range.after,
        commit_range.commits,
    )


def _consume_observations(
    state: Dict[str, Any],
    observations: Sequence[Tuple[str, List[_CommitObservation]]],
) -> List[Dict[str, Any]]:
    recorded_commits = set(state["commits"])
    records: List[Dict[str, Any]] = []
    for tool_event_id, observed in observations:
        new_observations = [
            item for item in observed if item.identity not in recorded_commits
        ]
        del state["pending"][tool_event_id]
        if not new_observations:
            state["ignored"].append(tool_event_id)
            continue
        ranges = _ranges_from_observations(new_observations)
        first_count = state["count"] + 1
        identities = [item.identity for item in new_observations]
        state["commits"].extend(identities)
        recorded_commits.update(identities)
        state["count"] += len(identities)
        counts = list(range(first_count, state["count"] + 1))
        record = {"counts": counts, "ranges": ranges}
        state["events"][tool_event_id] = record
        records.append(record)
    return records
