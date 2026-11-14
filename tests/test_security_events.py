"""Security diagnostics stay bounded and reject caller-provided content."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.security_events import record


class SecurityEvents(unittest.TestCase):
    def test_fixed_labels_and_rotation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record(root, "authentication_denied", "mcp")
            path = root / "security-events.jsonl"
            first = path.read_text()
            with patch("joongi_hub.security_events.MAX_BYTES", 1):
                record(root, "local_tokens_revoked", "owner")
            self.assertEqual((root / "security-events.previous.jsonl").read_text(), first)
            self.assertEqual(set(json.loads(path.read_text())), {"time", "event", "reason"})
            with self.assertRaises(ValueError):
                record(root, "fake-secret-do-not-log", "mcp")
            with self.assertRaises(ValueError):
                record(root, "authentication_denied", "fake-secret-do-not-log")
            self.assertNotIn("fake-secret", path.read_text())
