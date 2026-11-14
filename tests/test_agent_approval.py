"""An agent requests consent, but only the independent owner browser can decide."""

import http.client
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from joongi_hub.__main__ import serve_stdio
from joongi_hub.errors import RpcError
from joongi_hub.local_auth import LocalAuth
from joongi_hub.server import HubServer
from joongi_hub.service import Hub
from joongi_hub.upstream import HttpTransport
from tests.fixtures.credential_store import test_store
from tests.fixtures.oauth_server import OAuthProvider

ROOT = Path(__file__).resolve().parents[1]


class AgentApproval(unittest.TestCase):
    def enter_context(self, manager):
        value = manager.__enter__()
        self.addCleanup(manager.__exit__, None, None, None)
        return value

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hub = Hub(ROOT / "skills", self.root / "state", credential_store_factory=test_store)
        self.addCleanup(self.hub.close)
        self.provider = OAuthProvider()
        self.addCleanup(self.provider.server_close)
        self.addCleanup(self.provider.shutdown)
        threading.Thread(target=self.provider.serve_forever, daemon=True).start()
        config = self.hub.register(
            {
                "id": "protected",
                "transport": "http",
                "url": self.provider.resource,
                "auth": {"type": "bearer"},
            }
        )
        self.provider.access.add("fake-credential")
        self.hub.auth.set_manual(config, {"token": "fake-credential"})
        self.browser = self.enter_context(
            patch("joongi_hub.agent_approval.open_browser", return_value=True)
        )
        self.calls = self.enter_context(
            patch.object(self.provider.mcp, "handle", wraps=self.provider.mcp.handle)
        )
        self.args = {"message": "owner-selected page"}

    def call(self, name="protected__echo", arguments=None, local=True, meta=None):
        return self.hub.rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": name,
                    "arguments": self.args if arguments is None else arguments,
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                        **(meta or {}),
                    },
                },
            },
            {"owner": "test", "local_owner": local},
        )

    def start(self):
        result = self.call()
        data = result["error"]["data"]
        self.assertTrue(data["browser_opened"])
        url = self.browser.call_args.args[0]
        secret = parse_qs(urlsplit(url).fragment)["session"][0]
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(url, json.dumps(result))
        self.assertEqual(self.calls.call_args_list[-1].args[0]["method"], "tools/list")
        return data["approval_id"], url, secret

    def request(
        self,
        url,
        method="POST",
        action="view",
        secret=None,
        approval_id=None,
        headers=None,
        path=None,
    ):
        parsed = urlsplit(url)
        fragment = parse_qs(parsed.fragment)
        client = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        client.request(
            method,
            path or ("/decision" if method == "POST" else "/"),
            json.dumps({"approval_id": approval_id or fragment["approval_id"][0], "action": action})
            if method == "POST"
            else None,
            {
                "Content-Type": "application/json",
                "Authorization": "Bearer "
                + (secret if secret is not None else fragment["session"][0]),
                "Origin": f"http://127.0.0.1:{parsed.port}",
                **(headers or {}),
            },
        )
        response = client.getresponse()
        status, body, csp = (
            response.status,
            response.read(),
            response.getheader("Content-Security-Policy"),
        )
        client.close()
        return status, body, csp

    def test_owner_review_then_exactly_one_call_and_no_capability_in_mcp(self):
        identity, url, secret = self.start()
        self.assertEqual(self.request(url, method="GET")[0], 200)
        self.assertEqual(self.hub.tool_policy.get(identity)["status"], "pending")
        status, body, csp = self.request(url)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["arguments"], self.args)
        self.assertIn("frame-ancestors 'none'", csp)
        # MCP retry deduplicates the human popup; no upstream call yet.
        self.call()
        self.assertEqual(self.browser.call_count, 1)
        self.assertFalse(
            any(c.args[0]["method"] == "tools/call" for c in self.calls.call_args_list)
        )
        self.assertEqual(self.request(url, action="approve")[0], 200)
        status = self.call("hub_approval_status", {"approval_id": identity})
        self.assertNotIn(secret, json.dumps(status))
        self.assertIn("approved", json.dumps(status))
        self.assertNotIn("error", self.call())
        self.assertEqual(
            sum(c.args[0]["method"] == "tools/call" for c in self.calls.call_args_list), 1
        )
        self.assertIn("error", self.call())

    def test_mcp_cannot_decide_or_forge_local_owner(self):
        blocked = self.call(local=False, meta={"local_owner": True})
        identity = blocked["error"]["data"]["approval_id"]
        self.browser.assert_not_called()
        result = self.call(
            "hub_approval_request",
            {"approval_id": identity},
            local=False,
            meta={"local_owner": True, "owner": "stdio-1"},
        )
        self.assertIn("error", result)
        self.assertIn("error", self.call("hub_approval_decide", {"approval_id": identity}))
        self.assertEqual(self.hub.tool_policy.get(identity)["status"], "pending")

    def test_csrf_wrong_capability_other_request_and_get_cannot_approve(self):
        identity, url, _ = self.start()
        for kwargs in (
            {"secret": "wrong"},
            {"headers": {"Origin": "https://attacker.invalid"}},
            {"headers": {"Host": "attacker.invalid"}},
            {"headers": {"Sec-Fetch-Site": "cross-site"}},
            {"approval_id": "a" * 40},
        ):
            self.assertEqual(self.request(url, action="approve", **kwargs)[0], 403)
        self.assertEqual(self.request(url, method="GET", path="/decision?action=approve")[0], 404)
        self.assertEqual(self.hub.tool_policy.get(identity)["status"], "pending")
        self.assertEqual(self.request(url, action="deny")[0], 200)
        self.assertEqual(self.hub.tool_policy.get(identity)["status"], "denied")
        for _ in range(2):
            result = self.call()
            self.assertEqual(result["error"]["data"]["status"], "denied")
        self.assertEqual(self.browser.call_count, 1)
        self.assertFalse(
            any(c.args[0]["method"] == "tools/call" for c in self.calls.call_args_list)
        )

    def test_explicit_request_tool_reuses_pending_review_without_self_approval(self):
        blocked = self.call(local=False)
        identity = blocked["error"]["data"]["approval_id"]
        result = self.call("hub_approval_request", {"approval_id": identity})
        data = json.loads(result["result"]["content"][0]["text"])
        self.assertTrue(data["browser_opened"])
        self.assertEqual(data["status"], "pending")
        self.assertEqual(self.hub.tool_policy.get(identity)["status"], "pending")
        url = self.browser.call_args.args[0]
        secret = parse_qs(urlsplit(url).fragment)["session"][0]
        self.assertNotIn(secret, json.dumps(result))
        self.call("hub_approval_request", {"approval_id": identity})
        self.assertEqual(self.browser.call_count, 1)

    def test_changed_arguments_settings_definition_and_project_do_not_inherit_approval(self):
        identity, url, _ = self.start()
        self.assertEqual(self.request(url, action="approve")[0], 200)
        self.assertIn("error", self.call(arguments={"message": "other page"}))
        policy = self.hub.tool_policy
        config = self.hub.registry.list()[0]
        tool = self.hub.client("protected").tools[0]
        for changed_config, changed_tool in (
            ({**config, "url": config["url"] + "/changed"}, tool),
            (config, {**tool, "description": "changed"}),
        ):
            with self.assertRaises(RpcError):
                policy.authorize(
                    changed_config,
                    changed_tool,
                    self.args,
                    {"inputResponses": None, "requestState": None},
                )
        self.hub.projects.put({"id": "p", "root": str(self.root), "common_skills": []})
        other = self.hub.scoped("p")
        self.assertEqual(other.agent_approvals.status(identity)["status"], "unavailable")

    def test_expired_listener_and_failed_browser_leave_no_grant(self):
        identity, url, _ = self.start()
        port = urlsplit(url).port
        with self.hub.tool_policy.db() as db:
            db.execute("UPDATE approvals SET expires=? WHERE id=?", (time.time() - 1, identity))
        deadline = time.monotonic() + 3
        while self.hub.agent_approvals.server is not None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertIsNone(self.hub.agent_approvals.server)
        with self.assertRaises(OSError):
            http.client.HTTPConnection("127.0.0.1", port, timeout=1).connect()
        self.browser.return_value = False
        result = self.call()
        self.assertFalse(result["error"]["data"]["browser_opened"])
        self.assertEqual(
            self.hub.tool_policy.get(result["error"]["data"]["approval_id"])["status"], "pending"
        )

    def test_saved_decision_receipt_survives_consumption_without_granting_again(self):
        identity, url, _ = self.start()
        self.assertEqual(self.request(url, action="approve")[0], 200)
        self.assertNotIn("error", self.call())
        self.assertEqual(self.hub.agent_approvals.status(identity)["status"], "unavailable")
        status, body, _ = self.request(url, action="status")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "approved")
        self.assertEqual(self.request(url, action="approve")[0], 403)
        self.assertEqual(self.request(url, action="deny")[0], 403)
        self.assertEqual(self.request(url, action="view")[0], 403)
        self.assertEqual(self.request(url, action="status", secret="wrong")[0], 403)
        with self.hub.agent_approvals.lock:
            self.hub.agent_approvals.flows[identity]["expires"] = time.time() - 1
        deadline = time.monotonic() + 2
        while self.hub.agent_approvals.server and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertIsNone(self.hub.agent_approvals.server)

    def test_status_wait_returns_on_human_decision_without_model_poll_loop(self):
        identity, url, _ = self.start()
        outcome = []
        waiting = threading.Thread(
            target=lambda: outcome.append(
                self.call("hub_approval_status", {"approval_id": identity, "wait_seconds": 2})
            )
        )
        waiting.start()
        time.sleep(0.1)
        self.assertTrue(waiting.is_alive())
        start = time.monotonic()
        self.assertEqual(self.request(url, action="approve")[0], 200)
        waiting.join(timeout=1)
        self.assertFalse(waiting.is_alive())
        self.assertLess(time.monotonic() - start, 1)
        self.assertEqual(
            json.loads(outcome[0]["result"]["content"][0]["text"])["status"], "approved"
        )
        for invalid in (-1, 21, True, "2"):
            self.assertIn(
                "error",
                self.call(
                    "hub_approval_status", {"approval_id": identity, "wait_seconds": invalid}
                ),
            )

    def test_wait_has_a_deadline_and_detects_another_owner_process_decision(self):
        identity, _, _ = self.start()
        start = time.monotonic()
        self.assertEqual(self.hub.agent_approvals.wait_status(identity, 0.05)["status"], "pending")
        self.assertLess(time.monotonic() - start, 1)
        self.assertGreaterEqual(time.monotonic() - start, 0.04)
        outcome = []
        waiting = threading.Thread(
            target=lambda: outcome.append(self.hub.agent_approvals.wait_status(identity, 2))
        )
        waiting.start()
        time.sleep(0.05)
        # Independent DB writer, without this controller's event notification.
        self.hub.tool_policy.decide(identity, False)
        waiting.join(timeout=1)
        self.assertFalse(waiting.is_alive())
        self.assertEqual(outcome[0]["status"], "denied")

    def test_legacy_task_failure_preserves_request_id_for_human_approval(self):
        context = {"owner": "legacy-task", "local_owner": True}

        def rpc(identity, method, params):
            return self.hub.rpc(
                {"jsonrpc": "2.0", "id": identity, "method": method, "params": params}, context
            )

        rpc(
            1,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        self.hub.rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, context)
        task = rpc(
            2, "tools/call", {"name": "protected__echo", "arguments": self.args, "task": {}}
        )["result"]["task"]
        result = rpc(3, "tasks/result", {"taskId": task["taskId"]})
        self.assertEqual(result["error"]["code"], -32043)
        self.assertTrue(result["error"]["data"]["browser_opened"])
        identity = result["error"]["data"]["approval_id"]
        self.assertEqual(self.hub.agent_approvals.status(identity)["status"], "pending")

    def test_stdio_wire_and_managed_http_bridge_open_owner_review(self):
        for bridged in (False, True):
            with self.subTest(bridged=bridged):
                panel = None
                bridge = None
                if bridged:
                    panel = HubServer(("127.0.0.1", 0), self.hub)
                    threading.Thread(target=panel.serve_forever, daemon=True).start()
                    bridge = HttpTransport(
                        {"url": f"http://127.0.0.1:{panel.server_port}/mcp"},
                        auth=LocalAuth(self.hub.state_dir, "global"),
                    )
                args = {"message": f"wire-{bridged}"}
                messages = [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-11-25",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1"},
                        },
                    },
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "protected__echo", "arguments": args},
                    },
                ]
                messages.insert(1, {"jsonrpc": "2.0", "method": "notifications/initialized"})
                incoming = io.TextIOWrapper(
                    io.BytesIO("".join(json.dumps(m) + "\n" for m in messages).encode())
                )
                output = io.StringIO()
                try:
                    with patch("sys.stdin", incoming), patch("sys.stdout", output):
                        serve_stdio(self.hub, bridge)
                    result = json.loads(output.getvalue().splitlines()[-1])
                    self.assertTrue(
                        result.get("error", {}).get("data", {}).get("browser_opened"), result
                    )
                    identity = result["error"]["data"]["approval_id"]
                    url = self.browser.call_args.args[0]
                    secret = parse_qs(urlsplit(url).fragment)["session"][0]
                    self.assertNotIn(secret, output.getvalue())
                    self.assertEqual(self.request(url, action="approve")[0], 200)
                    self.assertNotIn("error", self.call(arguments=args))
                    self.assertEqual(self.hub.tool_policy.get(identity)["status"], "unavailable")
                finally:
                    if panel:
                        panel.shutdown()
                        panel.server_close()


if __name__ == "__main__":
    unittest.main()
