"""Human grants bind a concrete tool/connection, expire and revoke across processes."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.service import Hub
from joongi_hub.tool_policy import ToolPolicy
from tests.fixtures.credential_store import test_store

ROOT = Path(__file__).resolve().parents[1]


class ScopedConsent(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = ToolPolicy(self.root)
        self.config = {
            "id": "notion",
            "transport": "http",
            "url": "https://example.invalid/mcp",
            "auth": {"type": "bearer"},
        }
        self.tool = {"name": "notion-fetch", "inputSchema": {"type": "object"}}

    def pending(self, args=None, config=None, tool=None):
        with self.assertRaises(RpcError) as error:
            self.policy.authorize(config or self.config, tool or self.tool, args or {"page": "one"})
        self.assertEqual(error.exception.code, -32043)
        return error.exception.data["approval_id"]

    def grant(self, scope="hour"):
        identity = self.pending()
        self.policy.decide(identity, True, scope)
        return identity

    def test_hour_grant_covers_different_args_in_an_independent_process_store(self):
        identity = self.grant()
        other = ToolPolicy(self.root)
        other.authorize(self.config, self.tool, {"page": "two"})
        other.authorize(self.config, self.tool, {"page": "three"})
        self.assertEqual(other.get(identity)["status"], "approved")
        self.assertEqual(other.grants()[0]["scope"], "hour")
        other.authorize(self.config, self.tool, {"page": "one"})
        self.assertEqual(other.get(identity)["status"], "unavailable")

    def test_hour_expiry_requires_new_consent(self):
        self.grant()
        self.policy.authorize(self.config, self.tool, {"page": "one"})
        with self.policy.db() as db:
            db.execute("UPDATE grants SET expires=?", (time.time() - 1,))
        self.pending(args={"page": "two"})
        self.assertEqual(self.policy.grants(), [])

    def test_permanent_grant_survives_reload_but_revocation_removes_unused_approvals(self):
        identity = self.grant("always")
        grant = ToolPolicy(self.root).grants()[0]
        self.assertIsNone(grant["expires_at"])
        self.assertTrue(self.policy.revoke_grant(grant["id"])["revoked"])
        self.assertEqual(self.policy.get(identity)["status"], "unavailable")
        self.pending()

    def test_address_or_definition_change_invalidates_grant_without_resurrection(self):
        for target in ("address", "definition"):
            with self.subTest(target=target):
                self.grant("always")
                self.pending(
                    config={**self.config, "url": self.config["url"] + "/changed"}
                    if target == "address"
                    else None,
                    tool={**self.tool, "description": "changed"}
                    if target == "definition"
                    else None,
                )
                self.assertEqual(self.policy.grants(), [])
                self.pending()

    def test_environment_value_change_requires_consent_without_storing_secret(self):
        self.config["headers"] = {"Authorization": "FAKE_CONSENT_TOKEN"}
        with patch.dict("os.environ", {"FAKE_CONSENT_TOKEN": "fake-first-secret"}):
            self.grant("always")
        with patch.dict("os.environ", {"FAKE_CONSENT_TOKEN": "fake-second-secret"}):
            self.pending()
        self.assertNotIn(b"fake-first-secret", self.policy.path.read_bytes())
        self.assertNotIn(b"fake-second-secret", self.policy.path.read_bytes())

    def test_explicit_tool_denial_and_exact_call_denial_win_over_broad_grant(self):
        rejected = self.pending(args={"page": "private"})
        self.policy.decide(rejected, False)
        self.grant("always")
        with self.assertRaises(RpcError) as error:
            self.policy.authorize(self.config, self.tool, {"page": "private"})
        self.assertEqual(error.exception.data["status"], "denied")
        with self.assertRaises(RpcError):
            self.policy.authorize(
                {**self.config, "policy": {"denied_tools": ["notion-fetch"]}},
                self.tool,
                {"page": "other"},
            )

    def test_another_project_cannot_use_or_revoke_this_grant(self):
        self.grant("always")
        other = ToolPolicy(self.root / "project")
        self.assertFalse(other.revoke_grant(self.policy.grants()[0]["id"])["revoked"])
        with self.assertRaises(RpcError):
            other.authorize(self.config, self.tool, {"page": "one"})
        self.assertEqual(len(self.policy.grants()), 1)

    def test_invalid_scopes_and_denial_cannot_create_grants(self):
        identity = self.pending()
        for scope in ("server", "*", None, [], {}):
            with self.assertRaises(RpcError):
                self.policy.decide(identity, True, scope)
        with self.assertRaises(RpcError):
            self.policy.decide(identity, False, "always")
        self.assertEqual(self.policy.grants(), [])
        self.assertEqual(self.policy.get(identity)["status"], "pending")

    def test_new_manual_login_and_logout_revoke_grants(self):
        hub = Hub(ROOT / "skills", self.root, credential_store_factory=test_store)
        self.addCleanup(hub.close)
        config = hub.register({**self.config, "url": "http://127.0.0.1:12999/mcp"})
        for action in ("login", "logout"):
            self.grant("always")
            if action == "login":
                hub.auth.set_manual(config, {"token": "fake-owned-token"})
            else:
                hub.auth.logout(config, revoke=False)
            self.assertEqual(self.policy.grants(), [])
            self.pending()

    def test_untrusted_read_only_hint_does_not_create_auto_consent(self):
        self.pending(tool={**self.tool, "annotations": {"readOnlyHint": True}})
        self.assertEqual(self.policy.grants(), [])


if __name__ == "__main__":
    unittest.main()
