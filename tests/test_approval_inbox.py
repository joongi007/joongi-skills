"""Shared owner inbox, exact batch snapshots and non-error consent waits."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from joongi_hub.errors import RpcError
from joongi_hub.service import Hub
from joongi_hub.tool_policy import ToolPolicy
from tests.fixtures.credential_store import test_store

ROOT = Path(__file__).resolve().parents[1]


class ApprovalInbox(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.hub = Hub(ROOT / "skills", self.state, credential_store_factory=test_store)
        self.other = Hub(ROOT / "skills", self.state, credential_store_factory=test_store)
        self.addCleanup(self.other.close)
        self.addCleanup(self.hub.close)
        self.browser = patch("joongi_hub.agent_approval.open_browser", return_value=True).start()
        self.addCleanup(patch.stopall)

    def pending(self, index, server="notion"):
        with self.assertRaises(RpcError) as caught:
            self.hub.tool_policy.authorize(
                {"id": server, "policy": {}}, {"name": "read"}, {"id": index}
            )
        return caught.exception.data["approval_id"]

    def open(self, identity):
        value = self.hub.agent_approvals.request(identity)
        url = self.browser.call_args.args[0]
        secret = parse_qs(urlsplit(url).fragment)["session"][0]
        self.assertNotIn(secret, json.dumps(value))
        return "Bearer " + secret

    def test_multiple_servers_and_independent_stdio_owners_share_one_window(self):
        first, second, third = self.pending(1), self.pending(2), self.pending(3, "github")
        auth = self.open(first)
        self.assertTrue(self.hub.agent_approvals.request(second)["window_reused"])
        self.assertTrue(self.other.agent_approvals.request(third)["window_reused"])
        self.assertEqual(self.browser.call_count, 1)
        rows = self.hub.agent_approvals.inbox(auth, "view")["requests"]
        self.assertEqual({row["id"] for row in rows}, {first, second, third})
        self.assertEqual({row["server"] for row in rows}, {"notion", "github"})
        self.hub.agent_approvals.decision(third, auth, "approve")
        self.assertEqual(self.other.agent_approvals.status(third)["status"], "approved")

    def test_batch_approves_only_snapshot_not_later_arrivals(self):
        first, second = self.pending(1), self.pending(2)
        auth = self.open(first)
        self.hub.agent_approvals.inbox(auth, "view")
        later = self.pending(3)
        value = self.hub.agent_approvals.inbox(auth, "approve", [first, second])
        self.assertEqual(len(value["decisions"]), 2)
        self.assertEqual(self.hub.tool_policy.get(later)["status"], "pending")
        self.assertEqual(self.hub.tool_policy.grants(), [])
        self.assertFalse(self.hub.agent_approvals.inbox(auth, "close_if_empty")["closed"])

    def test_batch_is_atomic_when_any_request_changed_and_recovery_is_read_only(self):
        first, second = self.pending(1), self.pending(2)
        auth = self.open(first)
        self.hub.tool_policy.decide(second, False)
        with self.assertRaises(RpcError):
            self.hub.agent_approvals.inbox(auth, "approve", [first, second])
        self.assertEqual(self.hub.tool_policy.get(first)["status"], "pending")
        result = self.hub.agent_approvals.inbox(auth, "approve", [first])
        view = self.hub.agent_approvals.inbox(auth, "view")
        self.assertIn(result["decisions"][0], view["receipts"])
        with self.assertRaises(RpcError):
            self.hub.agent_approvals.inbox(auth, "approve", [first])

    def test_unknown_ids_other_profile_and_forged_capability_cannot_batch_approve(self):
        first = self.pending(1)
        auth = self.open(first)
        foreign = ToolPolicy(self.state / "other-project")
        with self.assertRaises(RpcError) as caught:
            foreign.authorize({"id": "notion", "policy": {}}, {"name": "read"}, {"id": 5})
        for authorization, ids in [
            ("Bearer wrong", [first]),
            (auth, [caught.exception.data["approval_id"]]),
            (auth, [first, first]),
            (auth, []),
            (auth, ["x" * 40]),
        ]:
            with self.assertRaises(RpcError):
                self.hub.agent_approvals.inbox(authorization, "approve", ids)
        self.assertEqual(self.hub.tool_policy.get(first)["status"], "pending")

    def test_window_lease_claim_is_atomic_and_close_allows_another_owner(self):
        stores = [ToolPolicy(self.state) for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(lambda pair: pair[1].window_claim(str(pair[0])), enumerate(stores))
            )
        self.assertEqual(sum(results), 1)
        winner = results.index(True)
        self.assertTrue(stores[0].window_release("not-the-owner", only_if_empty=True))
        self.assertTrue(stores[0].window_live(str(winner)))
        stores[0].window_release(str(winner))
        self.assertTrue(stores[0].window_claim("new-owner"))

    def test_closed_owner_does_not_leave_a_permanent_orphan_window(self):
        first = self.pending(1)
        self.open(first)
        self.hub.agent_approvals.close()
        result = self.other.agent_approvals.request(first)
        self.assertTrue(result["browser_opened"])
        self.assertEqual(self.browser.call_count, 2)


if __name__ == "__main__":
    unittest.main()
