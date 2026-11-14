"""Expiry and rotation must work across processes without accepting stale credentials."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.local_auth import (
    PREVIOUS_GRACE,
    ROTATE_AFTER,
    SESSION_TTL,
    TOKEN_TTL,
    LocalAuth,
    authenticate_local,
    local_token,
    rotate_local_tokens,
)


class LocalTokenRotation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = patch("joongi_hub.local_auth.time.time", return_value=10000)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_rotation_has_bounded_previous_token_grace_and_scope_isolation(self):
        initial = local_token(self.root)
        self.now.return_value += ROTATE_AFTER
        replacement = authenticate_local(self.root, initial)
        self.assertNotEqual(initial, replacement)
        self.assertEqual(authenticate_local(self.root, initial), replacement)
        self.assertIsNone(authenticate_local(self.root, initial, "another"))
        self.now.return_value += PREVIOUS_GRACE + 1
        self.assertIsNone(authenticate_local(self.root, initial))
        self.assertEqual(authenticate_local(self.root, replacement), replacement)

    def test_expired_token_requires_owner_broker_not_a_network_refresh(self):
        initial = local_token(self.root)
        self.now.return_value += TOKEN_TTL + 1
        self.assertIsNone(authenticate_local(self.root, initial))
        replacement = LocalAuth(self.root, "global").headers({})["Authorization"][7:]
        self.assertNotEqual(initial, replacement)
        self.assertEqual(authenticate_local(self.root, replacement), replacement)
        self.assertIsNone(authenticate_local(self.root, initial))

    def test_continuous_network_refresh_cannot_extend_absolute_session(self):
        token = local_token(self.root, management=True)
        end = self.now.return_value + SESSION_TTL
        while self.now.return_value + ROTATE_AFTER < end:
            self.now.return_value += ROTATE_AFTER
            token = authenticate_local(self.root, token, management=True)
            self.assertIsNotNone(token)
        self.now.return_value = end
        self.assertIsNone(authenticate_local(self.root, token, management=True))
        self.assertNotEqual(local_token(self.root, management=True), token)

    def test_legacy_credentials_and_manual_revocation_are_immediate(self):
        legacy = "a" * 43
        (self.root / "http-auth.json").write_text(json.dumps({"management": legacy}))
        self.assertIsNone(authenticate_local(self.root, legacy, management=True))
        current = local_token(self.root, management=True)
        result = rotate_local_tokens(self.root)
        self.assertTrue(result["previous_tokens_revoked"])
        self.assertIsNone(authenticate_local(self.root, current, management=True))
        self.assertNotEqual(local_token(self.root, management=True), current)

    def test_broker_reads_new_credentials_without_restarting(self):
        bridge = LocalAuth(self.root, "global")
        initial = local_token(self.root)
        self.assertEqual(bridge.headers({})["Authorization"], "Bearer " + initial)
        rotate_local_tokens(self.root)
        replacement = bridge.headers({})["Authorization"][7:]
        self.assertNotEqual(initial, replacement)
        self.assertIsNone(authenticate_local(self.root, initial))
        self.assertIsNotNone(authenticate_local(self.root, replacement))
