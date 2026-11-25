"""Render host-neutral review decisions as thin capability requests."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Mapping, Optional

from .review_core import ReviewDecision
from .review_request import ReviewKind

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
PROMPTS = {
    ReviewKind.RECENT: PROMPT_DIR / "review-most-recent-commit.txt",
    ReviewKind.BRANCH: PROMPT_DIR / "review-current-branch-diff.txt",
    ReviewKind.SIGNALS: PROMPT_DIR / "review-python-signals.txt",
}


def render_decision(
    decision: ReviewDecision,
    outcome_deliveries: Optional[Mapping[str, str]] = None,
) -> str:
    """Render a decision without introducing host-specific semantics."""

    prompt = PROMPTS[decision.kind].read_text(encoding="utf-8").strip()
    request_blocks = []
    for index, request in enumerate(decision.requests, start=1):
        request_blocks.append(
            '<review-request-json index="{}" count="{}">\n{}\n'
            "</review-request-json>".format(
                index,
                len(decision.requests),
                request.to_json(),
            )
        )
    sections = [prompt, "\n".join(request_blocks)]
    deliveries = outcome_deliveries or {}
    commands = []
    management = shlex.quote(
        str(Path(__file__).resolve().parents[1] / "scripts/review_hook.py")
    )
    for request in decision.requests:
        delivery_id = deliveries.get(request.event_id)
        if delivery_id is None:
            continue
        commands.append(
            "/usr/bin/python3 -B {} record-review-outcome "
            "--repository {} --event {} --delivery {} "
            "--finding-count FINDING_COUNT".format(
                management,
                request.repository.digest,
                request.event_id,
                delivery_id,
            )
        )
    if commands:
        sections.append(
            "Automatic outcome capture: before your final response, run each "
            "command below once after replacing FINDING_COUNT with the number "
            "of attributable findings you will report for that request (use 0 "
            "for an honest no-finding result). This command writes only private "
            "review-hook state outside the target repository; it is the one "
            "permitted state write in this read-only review. Do not ask the user "
            "to record, label, or hand off anything.\n\n{}".format(
                "\n".join(commands)
            )
        )
    return "\n\n".join(sections)
