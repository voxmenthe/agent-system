from __future__ import annotations

import concurrent.futures
import hashlib
import tempfile
import unittest
from pathlib import Path

from hosts.antigravity.plugin.antigravity_state import (
    DEFAULT_DELIVERY_TTL_SECONDS,
    AntigravityDeliveryStore,
    DeliveryMetadata,
    DeliveryStateError,
)


def _identity(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _complete_claim(root: str, conversation: str) -> bool:
    store = AntigravityDeliveryStore(Path(root))
    target = _identity("target")
    command = _identity("command")
    claims = store.claim_tools(conversation, [(target, 1, command)])
    if claims[0].duplicate:
        return False
    store.complete_tool(
        conversation,
        target,
        1,
        command,
        _identity("next-snapshot"),
        DeliveryMetadata((_identity("repository"),), (_identity("event"),)),
        now=101,
    )
    return True


class AntigravityDeliveryStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name) / "delivery"
        self.store = AntigravityDeliveryStore(self.root)
        self.conversation = "ec33ebf9-0cba-4100-8142-c61503f6c587"
        self.target = _identity("target")
        self.snapshot = _identity("snapshot")
        self.command = _identity("command")

    def _ready(self) -> None:
        action = self.store.begin_invocation(
            self.conversation, 0, {self.target: self.snapshot}, now=100
        )
        self.store.mark_ready(self.conversation, 0, action.prepare)

    def test_claim_replay_is_atomic_and_records_one_delivery(self) -> None:
        self._ready()
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            results = list(
                pool.map(
                    _complete_claim,
                    [str(self.root)] * 8,
                    [self.conversation] * 8,
                )
            )

        self.assertEqual(1, sum(results))
        summary = self.store.summary(now=102)
        self.assertEqual(1, summary["pending"])
        self.assertEqual(1, summary["snapshots"]["ready"])
        action = self.store.begin_invocation(
            self.conversation,
            1,
            {self.target: _identity("invocation-1")},
            now=102,
        )
        self.assertEqual(1, len(action.deliveries))
        replay = self.store.begin_invocation(
            self.conversation,
            1,
            {self.target: _identity("invocation-1")},
            now=103,
        )
        self.assertEqual(action.deliveries, replay.deliveries)
        acknowledged = self.store.begin_invocation(
            self.conversation,
            2,
            {self.target: _identity("invocation-2")},
            now=104,
        )
        self.assertEqual((), acknowledged.deliveries)

    def test_claim_is_single_owner_and_failure_or_expiry_allows_retry(self) -> None:
        self._ready()
        owner = self.store.claim_tools(
            self.conversation,
            [(self.target, 1, self.command)],
            now=100,
        )[0]
        concurrent_replay = self.store.claim_tools(
            self.conversation,
            [(self.target, 1, self.command)],
            now=101,
        )[0]
        self.assertFalse(owner.duplicate)
        self.assertTrue(concurrent_replay.duplicate)

        self.store.abandon_tool(
            self.conversation,
            self.target,
            1,
            self.command,
            now=102,
        )
        retry = self.store.claim_tools(
            self.conversation,
            [(self.target, 1, self.command)],
            now=103,
        )[0]
        self.assertFalse(retry.duplicate)

        expired_retry = self.store.claim_tools(
            self.conversation,
            [(self.target, 1, self.command)],
            now=103 + DEFAULT_DELIVERY_TTL_SECONDS,
        )[0]
        self.assertFalse(expired_retry.duplicate)

    def test_stale_killed_claim_does_not_block_a_later_invocation(self) -> None:
        self._ready()
        self.store.claim_tools(
            self.conversation,
            [(self.target, 1, self.command)],
            now=100,
        )
        with self.assertRaisesRegex(DeliveryStateError, "processing"):
            self.store.begin_invocation(
                self.conversation,
                1,
                {self.target: _identity("too-early")},
                now=100 + DEFAULT_DELIVERY_TTL_SECONDS - 1,
            )

        recovered = self.store.begin_invocation(
            self.conversation,
            1,
            {self.target: _identity("recovered")},
            now=100 + DEFAULT_DELIVERY_TTL_SECONDS,
        )
        self.assertEqual((self.snapshot,), recovered.retire)
        self.assertEqual(1, len(recovered.prepare))

    def test_unclaimed_delivery_expires_without_cross_conversation_effect(self) -> None:
        self._ready()
        claim = self.store.claim_tools(
            self.conversation, [(self.target, 1, self.command)]
        )[0]
        self.store.complete_tool(
            self.conversation,
            self.target,
            1,
            self.command,
            _identity("next"),
            DeliveryMetadata((_identity("repository"),), (_identity("event"),)),
            now=100,
        )
        self.assertFalse(claim.duplicate)
        stale_time = 100 + DEFAULT_DELIVERY_TTL_SECONDS
        self.assertEqual(1, self.store.summary(now=stale_time)["stale"])
        action = self.store.begin_invocation(
            self.conversation,
            1,
            {self.target: _identity("fresh")},
            now=stale_time,
        )
        self.assertEqual((), action.deliveries)

        other = "4a7df45c-98fd-445e-a07e-5143fd2b5e85"
        other_action = self.store.begin_invocation(
            other, 0, {self.target: _identity("other")}, now=stale_time
        )
        self.assertEqual((), other_action.deliveries)
        self.assertEqual(2, self.store.summary(now=stale_time)["conversations"])

    def test_state_is_private_and_malformed_history_is_never_repaired(self) -> None:
        self._ready()
        payload = next(self.root.glob("*.json")).read_text(encoding="utf-8")
        self.assertNotIn(self.conversation, payload)
        self.assertNotIn(str(self.root), payload)
        self.assertNotIn("/fixture/workspace", payload)

        state_path = next(self.root.glob("*.json"))
        state_path.write_text('{"schema":"unknown"', encoding="utf-8")
        with self.assertRaisesRegex(DeliveryStateError, "malformed"):
            self.store.summary()
        self.assertEqual(
            '{"schema":"unknown"', state_path.read_text(encoding="utf-8")
        )


if __name__ == "__main__":
    unittest.main()
