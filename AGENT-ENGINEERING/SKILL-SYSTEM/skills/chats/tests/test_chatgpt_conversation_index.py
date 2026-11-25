from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import chatgpt_conversation_index as conversation_index  # noqa: E402
import list_chatgpt_conversations as list_cli  # noqa: E402


def _item(
    conversation_id: str,
    *,
    created: str,
    updated: str,
    archived: bool = False,
    title: str | None = None,
) -> dict[str, object]:
    return {
        "id": conversation_id,
        "title": title or f"Title for {conversation_id}",
        "create_time": created,
        "update_time": updated,
        "is_archived": archived,
    }


class FakePageFetcher:
    def __init__(
        self,
        pages: dict[tuple[bool, int], list[dict[str, object]]],
    ) -> None:
        self.pages = pages
        self.calls: list[tuple[int, int, bool]] = []

    def __call__(
        self,
        offset: int,
        limit: int,
        *,
        archived: bool,
    ) -> dict[str, object]:
        self.calls.append((offset, limit, archived))
        items = self.pages.get((archived, offset), [])
        # Deliberately make total a look-ahead value. The live endpoint does not
        # expose a stable full-history count here.
        return {
            "items": items,
            "offset": offset,
            "limit": limit,
            "total": offset + len(items) + (1 if len(items) == limit else 0),
        }


class ConversationIndexTests(unittest.TestCase):
    def test_recent_paginates_without_trusting_total_and_applies_limit(self) -> None:
        fetcher = FakePageFetcher(
            {
                (False, 0): [
                    _item(
                        "conv-0004",
                        created="2026-08-04T00:00:00Z",
                        updated="2026-08-08T04:00:00Z",
                    ),
                    _item(
                        "conv-0003",
                        created="2026-08-03T00:00:00Z",
                        updated="2026-08-08T03:00:00Z",
                    ),
                ],
                (False, 2): [
                    _item(
                        "conv-0002",
                        created="2026-08-02T00:00:00Z",
                        updated="2026-08-08T02:00:00Z",
                    ),
                    _item(
                        "conv-0001",
                        created="2026-08-01T00:00:00Z",
                        updated="2026-08-08T01:00:00Z",
                    ),
                ],
            }
        )

        result = conversation_index.list_recent(
            fetcher,
            limit=3,
            archive_scope="active",
            page_size=2,
        )

        self.assertEqual(
            ["conv-0004", "conv-0003", "conv-0002"],
            [item.conversation_id for item in result.conversations],
        )
        self.assertEqual(2, result.pages_fetched)
        self.assertEqual([(0, 2, False), (2, 2, False)], fetcher.calls)

    def test_created_date_range_scans_active_and_archived_histories(self) -> None:
        fetcher = FakePageFetcher(
            {
                (False, 0): [
                    _item(
                        "conv-new-update",
                        created="2025-01-01T00:00:00Z",
                        updated="2026-08-08T05:00:00Z",
                    ),
                    _item(
                        "conv-created-in-range",
                        created="2026-08-02T12:00:00Z",
                        updated="2026-08-08T04:00:00Z",
                    ),
                ],
                (False, 2): [
                    _item(
                        "conv-old",
                        created="2024-01-01T00:00:00Z",
                        updated="2024-01-01T01:00:00Z",
                    )
                ],
                (True, 0): [
                    _item(
                        "conv-archived-in-range",
                        created="2026-08-03T12:00:00Z",
                        updated="2026-08-04T00:00:00Z",
                        archived=True,
                    )
                ],
            }
        )

        result = conversation_index.list_date_range(
            fetcher,
            start=datetime(2026, 8, 1, tzinfo=timezone.utc),
            end=datetime(2026, 8, 5, tzinfo=timezone.utc),
            date_field="created",
            archive_scope="all",
            page_size=2,
        )

        self.assertEqual(
            ["conv-archived-in-range", "conv-created-in-range"],
            [item.conversation_id for item in result.conversations],
        )
        self.assertEqual(3, result.pages_fetched)
        self.assertEqual(
            [(0, 2, False), (2, 2, False), (0, 2, True)],
            fetcher.calls,
        )

    def test_created_range_stops_after_updates_cross_lower_bound(self) -> None:
        fetcher = FakePageFetcher(
            {
                (False, 0): [
                    _item(
                        "conv-recently-updated-old-chat",
                        created="2025-01-01T00:00:00Z",
                        updated="2026-08-08T05:00:00Z",
                    ),
                    _item(
                        "conv-created-in-range",
                        created="2026-08-02T12:00:00Z",
                        updated="2026-08-07T04:00:00Z",
                    ),
                ],
                (False, 2): [
                    _item(
                        "conv-before-range-1",
                        created="2026-07-01T00:00:00Z",
                        updated="2026-07-31T23:00:00Z",
                    ),
                    _item(
                        "conv-before-range-2",
                        created="2026-06-01T00:00:00Z",
                        updated="2026-07-30T23:00:00Z",
                    ),
                ],
                (False, 4): [
                    _item(
                        "conv-older-page-that-must-not-be-read",
                        created="2026-05-01T00:00:00Z",
                        updated="2026-07-01T00:00:00Z",
                    )
                ],
            }
        )

        result = conversation_index.list_date_range(
            fetcher,
            start=datetime(2026, 8, 1, tzinfo=timezone.utc),
            end=datetime(2026, 8, 5, tzinfo=timezone.utc),
            date_field="created",
            archive_scope="active",
            page_size=2,
        )

        self.assertEqual(
            ["conv-created-in-range"],
            [item.conversation_id for item in result.conversations],
        )
        self.assertEqual([(0, 2, False), (2, 2, False)], fetcher.calls)

    def test_conversation_cannot_be_updated_before_it_was_created(self) -> None:
        fetcher = FakePageFetcher(
            {
                (False, 0): [
                    _item(
                        "conv-invalid-timestamps",
                        created="2026-08-02T00:00:00Z",
                        updated="2026-08-01T00:00:00Z",
                    )
                ]
            }
        )

        with self.assertRaisesRegex(
            conversation_index.ConversationIndexError,
            "updated before it was created",
        ):
            conversation_index.list_date_range(
                fetcher,
                start=datetime(2026, 8, 1, tzinfo=timezone.utc),
                end=datetime(2026, 8, 5, tzinfo=timezone.utc),
                archive_scope="active",
                page_size=2,
            )

    def test_updated_date_range_stops_after_crossing_lower_bound(self) -> None:
        fetcher = FakePageFetcher(
            {
                (False, 0): [
                    _item(
                        "conv-too-new",
                        created="2026-08-01T00:00:00Z",
                        updated="2026-08-09T00:00:00Z",
                    ),
                    _item(
                        "conv-in-range",
                        created="2026-08-01T00:00:00Z",
                        updated="2026-08-07T00:00:00Z",
                    ),
                ],
                (False, 2): [
                    _item(
                        "conv-before-range",
                        created="2026-07-01T00:00:00Z",
                        updated="2026-07-31T23:59:59Z",
                    ),
                    _item(
                        "conv-even-older",
                        created="2026-06-01T00:00:00Z",
                        updated="2026-07-02T00:00:00Z",
                    ),
                ],
            }
        )

        result = conversation_index.list_date_range(
            fetcher,
            start=datetime(2026, 8, 1, tzinfo=timezone.utc),
            end=datetime(2026, 8, 8, tzinfo=timezone.utc),
            date_field="updated",
            archive_scope="active",
            page_size=2,
        )

        self.assertEqual(
            ["conv-in-range"],
            [item.conversation_id for item in result.conversations],
        )
        self.assertEqual([(0, 2, False), (2, 2, False)], fetcher.calls)

    def test_calendar_date_bounds_respect_named_timezone_and_dst(self) -> None:
        start, end = conversation_index.calendar_date_bounds(
            "2026-03-08",
            "2026-03-08",
            "America/Los_Angeles",
        )

        self.assertEqual("2026-03-08T08:00:00Z", conversation_index.format_utc(start))
        self.assertEqual("2026-03-09T07:00:00Z", conversation_index.format_utc(end))

    def test_duplicate_conversation_fails_loudly_instead_of_hiding_drift(self) -> None:
        duplicate = _item(
            "conv-duplicate",
            created="2026-08-01T00:00:00Z",
            updated="2026-08-08T00:00:00Z",
        )
        fetcher = FakePageFetcher(
            {
                (False, 0): [duplicate, duplicate],
            }
        )

        with self.assertRaisesRegex(
            conversation_index.ConversationIndexError,
            "duplicate",
        ):
            conversation_index.list_recent(
                fetcher,
                limit=2,
                archive_scope="active",
                page_size=2,
            )

    def test_page_limit_mismatch_fails_loudly(self) -> None:
        def fetch_page(
            offset: int,
            limit: int,
            *,
            archived: bool,
        ) -> dict[str, object]:
            return {
                "items": [
                    _item(
                        "conv-limit-mismatch",
                        created="2026-08-01T00:00:00Z",
                        updated="2026-08-08T00:00:00Z",
                        archived=archived,
                    )
                ],
                "offset": offset,
                "limit": limit - 1,
            }

        with self.assertRaisesRegex(
            conversation_index.ConversationIndexError,
            "limit mismatch",
        ):
            conversation_index.list_recent(fetch_page, limit=1)


class FakeBridge:
    class ChatGPTError(Exception):
        pass

    class NotLoggedInError(ChatGPTError):
        pass

    class JSExecBlockedError(ChatGPTError):
        pass

    class ChatGPTTimeoutError(ChatGPTError):
        pass

    class ChatGPTReadThrottledError(ChatGPTTimeoutError):
        pass

    def __init__(self) -> None:
        self.target = (31, 41)
        self.session_targets: list[tuple[int, int]] = []
        self.page_calls: list[tuple[int, int, bool, tuple[int, int]]] = []

    def ensure_chatgpt_available(self) -> tuple[int, int]:
        return self.target

    def get_session(self, *, target: tuple[int, int]) -> dict[str, str]:
        self.session_targets.append(target)
        return {"accessToken": "must-not-be-printed"}

    def fetch_conversations_page(
        self,
        offset: int,
        limit: int,
        *,
        archived: bool,
        target: tuple[int, int],
    ) -> dict[str, object]:
        self.page_calls.append((offset, limit, archived, target))
        return {
            "items": [
                _item(
                    "conv-cli-0001",
                    created="2026-08-08T01:00:00Z",
                    updated="2026-08-08T02:00:00Z",
                )
            ],
            "offset": offset,
            "limit": limit,
            "total": 1,
        }


class ListCliTests(unittest.TestCase):
    def test_recent_cli_uses_one_authenticated_target_and_prints_versioned_json(
        self,
    ) -> None:
        bridge = FakeBridge()
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = list_cli.main(
                ["recent", "--limit", "1"],
                bridge=bridge,
            )

        self.assertEqual(list_cli.EXIT_OK, exit_code)
        self.assertEqual([bridge.target], bridge.session_targets)
        self.assertEqual([(0, 20, False, bridge.target)], bridge.page_calls)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(1, payload["schema_version"])
        self.assertEqual("best_effort", payload["snapshot_consistency"])
        self.assertEqual("recent", payload["query"]["mode"])
        self.assertEqual(1, payload["count"])
        self.assertEqual(
            "https://chatgpt.com/c/conv-cli-0001",
            payload["conversations"][0]["url"],
        )
        self.assertNotIn("must-not-be-printed", stdout.getvalue())

    def test_cli_maps_invalid_date_range_to_usage_error(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = list_cli.main(
                [
                    "range",
                    "--from-date",
                    "2026-08-08",
                    "--to-date",
                    "2026-08-01",
                ],
                bridge=FakeBridge(),
            )

        self.assertEqual(list_cli.EXIT_USAGE, exit_code)
        self.assertIn("must not be after", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
