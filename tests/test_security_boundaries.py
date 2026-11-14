"""Credentialed calls require independent consent; local HTTP is not anonymous."""

import concurrent.futures
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.connections import configuration
from joongi_hub.errors import RpcError
from joongi_hub.local_auth import local_token
from joongi_hub.redaction import reject_secret_reflection
from joongi_hub.server import HubServer
from joongi_hub.service import Hub
from joongi_hub.tool_policy import ToolPolicy
from tests.fixtures.credential_store import test_store
from tests.fixtures.oauth_server import OAuthProvider

ROOT = Path(__file__).resolve().parents[1]


class SecurityBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hub = Hub(ROOT / "skills", self.root / "state", credential_store_factory=test_store)
        self.addCleanup(self.hub.close)
        self.provider = OAuthProvider()
        self.panel = HubServer(("127.0.0.1", 0), self.hub)
        for server in (self.provider, self.panel):
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.config = self.hub.register(
            {
                "id": "protected",
                "transport": "http",
                "url": self.provider.resource,
                "protocol_version": "2025-11-25",
                "auth": {"type": "bearer"},
            }
        )
        self.fake = "fake-local-audit-credential-not-real"
        self.provider.access.add(self.fake)
        self.hub.auth.set_manual(self.config, {"token": self.fake})

    def request(self, method, path, body=None, headers=None):
        client = http.client.HTTPConnection("127.0.0.1", self.panel.server_port, timeout=5)
        client.request(
            method,
            path,
            None if body is None else json.dumps(body),
            {"Content-Type": "application/json", **(headers or {})},
        )
        response = client.getresponse()
        result = response.status, json.loads(response.read() or b"null")
        client.close()
        return result

    def test_bad_credentials_are_limited_without_locking_out_the_valid_owner(self):
        for index in range(23):
            status, _ = self.request(
                "GET", "/api/v1/session", headers={"X-Hub-Token": "fake-invalid-secret"}
            )
            self.assertEqual(status, 403 if index < 20 else 429)
        status, _ = self.request(
            "GET", "/api/v1/session", headers={"X-Hub-Token": self.panel.token}
        )
        self.assertEqual(status, 200)
        log = (self.hub.state_dir / "security-events.jsonl").read_text()
        self.assertEqual(len(log.splitlines()), 21)
        self.assertIn("authentication_limited", log)
        self.assertNotIn("fake-invalid-secret", log)
        self.assertNotIn(self.panel.token, log)

    def initialize(self):
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "clientInfo": {"name": "security-test", "version": "1"},
                "capabilities": {},
            },
        }

    def test_http_mcp_and_management_require_different_credentials(self):
        self.assertEqual(self.request("POST", "/mcp", self.initialize())[0], 401)
        self.assertEqual(self.request("GET", "/api/v1/session")[0], 403)
        self.assertEqual(self.request("GET", "/%61pi/v1/connection")[0], 403)
        self.assertEqual(self.request("GET", "/api/v1/%73ession")[0], 403)
        admin = {"X-Hub-Token": self.panel.token}
        self.assertEqual(self.request("GET", "/api/v1/session", headers=admin)[0], 200)
        self.assertEqual(self.request("POST", "/mcp", self.initialize(), admin)[0], 401)
        self.assertNotEqual(local_token(self.hub.state_dir, "management"), self.panel.token)
        bearer = {"Authorization": "Bearer " + local_token(self.hub.state_dir)}
        self.assertEqual(self.request("POST", "/mcp", self.initialize(), bearer)[0], 200)
        self.assertEqual(self.request("GET", "/api/v1/session", headers=bearer)[0], 403)

    def test_http_tokens_cannot_switch_project_by_path_header_or_metadata(self):
        self.hub.projects.put({"id": "p", "root": str(self.root), "common_skills": []})
        config = configuration(self.hub, "p", mode="http")
        headers = config["headers"]
        self.assertEqual(
            self.request("POST", "/mcp/projects/p", self.initialize(), headers)[0], 200
        )
        self.assertEqual(self.request("POST", "/mcp", self.initialize(), headers)[0], 401)
        global_headers = {"Authorization": "Bearer " + local_token(self.hub.state_dir)}
        self.assertEqual(
            self.request("POST", "/mcp/projects/p", self.initialize(), global_headers)[0], 401
        )
        self.assertEqual(
            self.request(
                "POST", "/mcp", self.initialize(), {**global_headers, "X-Hub-Profile": "p"}
            )[0],
            400,
        )
        request = self.initialize()
        request["params"]["_meta"] = {"joongi-hub/profile": "p"}
        self.assertEqual(self.request("POST", "/mcp", request, global_headers)[0], 400)

    def test_remote_readonly_hints_do_not_grant_authority_and_approval_is_exact_once(self):
        client = self.hub.client("protected")
        client.connect()
        with patch.object(client, "request", wraps=client.request) as send:
            with self.assertRaises(RpcError) as pending:
                self.hub.invoke("protected__echo", {"message": "approved-argument"})
            self.assertEqual(pending.exception.code, -32043)
            send.assert_not_called()
        request_id = pending.exception.data["approval_id"]
        self.assertEqual(
            self.request("POST", "/api/v1/approvals/" + request_id, {"approve": True})[0], 403
        )
        status, _ = self.request(
            "POST",
            "/api/v1/approvals/" + request_id,
            {"approve": True},
            {"X-Hub-Token": self.panel.token},
        )
        self.assertEqual(status, 200)
        with self.assertRaises(RpcError):
            self.hub.invoke("protected__echo", {"message": "different-argument"})
        self.hub.invoke("protected__echo", {"message": "approved-argument"})
        with self.assertRaises(RpcError):
            self.hub.invoke("protected__echo", {"message": "approved-argument"})

    def test_known_secrets_are_rejected_in_normal_and_error_responses(self):
        config = {**self.config, "policy": {"allowed_tools": ["echo"]}}
        self.hub.register(config)
        handler = self.provider.mcp.handle

        def reflected(message):
            if message.get("method") == "tools/call":
                return {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {"code": -32000, "message": self.fake},
                }
            return handler(message)

        self.provider.mcp.handle = reflected
        with self.assertRaises(RpcError) as rejected:
            self.hub.invoke("protected__echo", {})
        self.assertEqual(rejected.exception.code, -32044)
        self.assertNotIn(self.fake, str(rejected.exception))
        self.provider.mcp.handle = handler
        with self.assertRaises(RpcError) as rejected:
            self.hub.invoke("protected__echo", {"message": self.fake})
        self.assertEqual(rejected.exception.code, -32044)
        for secret in [
            'fake-password-with-"quotes"',
            "fake-password-with-\\backslash",
            "임시-인증-비밀",
        ]:
            with self.assertRaises(RpcError):
                reject_secret_reflection({"result": secret}, [secret])
        for value in [{"content": self.fake}, {"error": {"data": self.fake}}]:
            with self.assertRaises(RpcError):
                reject_secret_reflection(value, [self.fake])

    def test_mrtr_continuation_cannot_replace_local_security_approval(self):
        from tests.fixtures.mcp_server import Fixture

        self.provider.mcp = Fixture("2026-07-28")
        config = self.hub.register(
            {
                "id": "roundtrip",
                "transport": "http",
                "url": self.provider.resource,
                "auth": {"type": "bearer"},
                "protocol_version": "2026-07-28",
                "policy": {},
            }
        )
        self.hub.auth.set_manual(config, {"token": self.fake})
        with self.assertRaises(RpcError) as pending:
            self.hub.invoke("roundtrip__confirm", {})
        self.hub.tool_policy.decide(pending.exception.data["approval_id"], True)
        initial = self.hub.invoke("roundtrip__confirm", {})
        self.assertEqual(initial["resultType"], "input_required")
        response = {"consent": {"action": "accept", "content": {"confirmed": True}}}
        with self.assertRaises(RpcError) as continuation:
            self.hub.invoke(
                "roundtrip__confirm",
                {},
                input_responses=response,
                request_state=initial["requestState"],
            )
        self.assertEqual(continuation.exception.code, -32043)
        self.hub.tool_policy.decide(continuation.exception.data["approval_id"], True)
        final = self.hub.invoke(
            "roundtrip__confirm",
            {},
            input_responses=response,
            request_state=initial["requestState"],
        )
        self.assertEqual(final["content"][0]["text"], "Confirmed True")

    def test_policy_is_shared_between_processes_and_atomic_under_concurrent_consumption(self):
        tool = {"name": "echo", "annotations": {"readOnlyHint": True}}
        args = {"message": "once"}
        with self.assertRaises(RpcError) as pending:
            self.hub.tool_policy.authorize(self.config, tool, args)
        other = ToolPolicy(self.hub.state_dir)
        other.decide(pending.exception.data["approval_id"], True)

        def consume(_):
            try:
                ToolPolicy(self.hub.state_dir).authorize(self.config, tool, args)
                return True
            except RpcError:
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(consume, range(4))), 1)
        with self.assertRaises(RpcError):
            self.hub.tool_policy.authorize(
                {**self.config, "url": self.config["url"] + "/other"}, tool, args
            )
        with self.assertRaises(RpcError):
            self.hub.tool_policy.authorize(
                self.config, tool, args, {"inputResponses": {"approve": True}}
            )
