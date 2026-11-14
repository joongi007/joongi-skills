"""Only a local owner opens settings; tab leases stop the web without stopping stdio."""

import http.client
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from joongi_hub.__main__ import serve_stdio
from joongi_hub.local_auth import local_token
from joongi_hub.service import Hub
from tests.fixtures.credential_store import test_store

ROOT = Path(__file__).resolve().parents[1]


class AgentPanel(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.hub = Hub(ROOT / "skills", Path(self.temp.name), credential_store_factory=test_store)
        self.addCleanup(self.hub.close)
        self.browser = patch("joongi_hub.agent_panel.open_browser", return_value=True).start()
        self.addCleanup(patch.stopall)
        self.manager = self.hub.agent_panels
        self.manager.close_seconds = 0.1
        self.manager.idle_seconds = 2

    def call(self, local=True, meta=None, args=None):
        return self.hub.rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "hub_open_settings",
                    "arguments": args or {},
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                        **(meta or {}),
                    },
                },
            },
            {"owner": "test", "local_owner": local},
        )

    def open(self):
        result = self.call()
        self.assertNotIn("error", result)
        url = self.browser.call_args.args[0]
        self.assertNotIn(parse_qs(urlsplit(url).fragment)["session"][0], json.dumps(result))
        self.assertNotIn(url, json.dumps(result))
        return url

    def request(self, url, path="/api/v1/panel", body=None, headers=None):
        parsed = urlsplit(url)
        token = parse_qs(parsed.fragment)["session"][0]
        client = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
        client.request(
            "POST" if body is not None else "GET",
            path,
            json.dumps(body) if body is not None else None,
            {
                "X-Hub-Token": token,
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{parsed.port}",
                **(headers or {}),
            },
        )
        response = client.getresponse()
        status, data = response.status, response.read()
        client.close()
        return status, json.loads(data)

    def wait_closed(self):
        deadline = time.monotonic() + 3
        while self.manager.server and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertIsNone(self.manager.server)
        self.assertNotIn(
            "error",
            self.hub.rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "hub_status",
                        "arguments": {},
                        "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"},
                    },
                },
                {"owner": "test"},
            ),
        )

    def test_open_close_keeps_stdio_and_does_not_advertise_http_endpoint(self):
        url = self.open()
        self.assertEqual(self.request(url)[1]["mode"], "temporary")
        self.assertFalse((self.hub.state_dir / "endpoint.json").exists())
        page = parse_qs(urlsplit(url).fragment)["panel_page"][0]
        self.assertEqual(self.request(url, "/api/v1/panel/heartbeat", {"page": page})[0], 200)
        self.assertEqual(self.request(url, "/api/v1/panel/close", {"page": page})[0], 200)
        self.wait_closed()

    def test_remote_mcp_cannot_open_settings_even_with_forged_owner_metadata(self):
        self.assertIn("error", self.call(False, {"local_owner": True, "owner": "stdio-owner"}))
        self.browser.assert_not_called()

    def test_temporary_panel_rejects_mcp_and_persistent_management_credentials_and_csrf(self):
        url = self.open()
        for headers in (
            {"X-Hub-Token": ""},
            {"X-Hub-Token": local_token(self.hub.state_dir, management=True)},
            {"X-Hub-Token": local_token(self.hub.state_dir)},
            {"Origin": "https://attacker.invalid"},
            {"Host": "attacker.invalid"},
        ):
            self.assertEqual(self.request(url, headers=headers)[0], 403)
        self.assertEqual(
            self.request(url, "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "ping"})[0], 403
        )
        self.assertEqual(
            self.request(url, "/api/v1/panel/close", {"page": "unknown-page-id-123"})[0], 400
        )

    def test_closing_one_tab_does_not_stop_another_or_break_refresh(self):
        first, second = self.open(), self.open()
        p1 = parse_qs(urlsplit(first).fragment)["panel_page"][0]
        p2 = parse_qs(urlsplit(second).fragment)["panel_page"][0]
        self.request(first, "/api/v1/panel/close", {"page": p1})
        time.sleep(0.3)
        self.assertEqual(self.request(second)[0], 200)
        self.request(second, "/api/v1/panel/close", {"page": p2})
        # A refreshed document claims a fresh per-document lease before the close grace ends.
        self.assertEqual(
            self.request(second, "/api/v1/panel/heartbeat", {"page": "new-document-123456"})[0], 200
        )
        time.sleep(0.3)
        self.assertEqual(self.request(second)[0], 200)
        self.request(second, "/api/v1/panel/close", {"page": "new-document-123456"})
        self.wait_closed()

    def test_idle_fallback_and_stdio_shutdown_reap_listener(self):
        self.manager.idle_seconds = 0.3
        self.open()
        self.wait_closed()
        self.manager.idle_seconds = 2
        self.open()
        self.hub.close()
        self.assertIsNone(self.manager.server)

    def test_reopen_during_old_callback_cleanup_restores_the_original_callback(self):
        self.manager.idle_seconds = 0.2
        with self.hub.auth.lock:
            self.open()
            self.wait_closed()
            # Old listener cleanup is blocked on this credential lock while a
            # fresh settings request starts. It must not restore a dead port.
            self.manager.idle_seconds = 2
            self.open()
        self.manager.close()
        self.assertIsNone(self.hub.auth.callback_url)

    def test_local_http_broker_keeps_both_protocol_result_shapes_without_token_handoff(self):
        for version in ("2025-11-25", "2026-07-28"):
            bridge = SimpleNamespace(version=version)
            message = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "hub_open_settings",
                    "arguments": {},
                    "_meta": {"io.modelcontextprotocol/protocolVersion": version},
                },
            }
            incoming = io.TextIOWrapper(io.BytesIO((json.dumps(message) + "\n").encode()))
            output = io.StringIO()
            with patch("sys.stdin", incoming), patch("sys.stdout", output):
                serve_stdio(self.hub, bridge)
            response = json.loads(output.getvalue())
            self.assertNotIn("error", response)
            if version == "2026-07-28":
                self.assertEqual(response["result"]["resultType"], "complete")
            else:
                self.assertNotIn("resultType", response["result"])
            url = self.browser.call_args.args[0]
            secret = parse_qs(urlsplit(url).fragment)["session"][0]
            self.assertNotIn(secret, output.getvalue())

    def test_persistent_panel_is_reused_without_a_temporary_lifetime(self):
        with patch(
            "joongi_hub.agent_panel.running", return_value={"url": "http://127.0.0.1:12345"}
        ):
            value = self.call()
        data = json.loads(value["result"]["content"][0]["text"])
        self.assertEqual(data["mode"], "persistent")
        self.assertFalse(data["closes_with_window"])
        self.assertIsNone(self.manager.server)


if __name__ == "__main__":
    unittest.main()
