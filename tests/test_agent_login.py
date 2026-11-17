"""Agents can initiate upstream login without a management panel or token handoff."""

import http.client
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from joongi_hub.errors import RpcError
from joongi_hub.service import Hub
from tests.fixtures.credential_store import test_store
from tests.fixtures.oauth_server import OAuthProvider

ROOT = Path(__file__).resolve().parents[1]


class AgentLogin(unittest.TestCase):
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
        self.config = self.hub.register(
            {
                "id": "protected",
                "transport": "http",
                "url": self.provider.resource,
                "auth": {"type": "oauth", "client_id": "registered-client"},
                "policy": {"allowed_tools": ["echo"]},
            }
        )

    def call(self, name, args, version="2025-11-25"):
        params = {"name": name, "arguments": args}
        if version == "2026-07-28":
            params["_meta"] = {"io.modelcontextprotocol/protocolVersion": version}
        result = self.hub.rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params},
            {"version": version, "ready": True, "owner": "stdio-test"},
        )
        self.assertNotIn("error", result, result)
        self.assertFalse(result["result"].get("isError"), result)
        return json.loads(result["result"]["content"][0]["text"])

    def request(self, url, host=None):
        parsed = urlsplit(url)
        client = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        client.request(
            "GET",
            parsed.path + ("?" + parsed.query if parsed.query else ""),
            headers={"Host": host} if host else {},
        )
        response = client.getresponse()
        value = response.status, response.getheader("Location"), response.read()
        client.close()
        return value

    def authorize(self, flow):
        status, callback, _ = self.request(flow["url"])
        self.assertEqual(status, 302)
        return self.request(callback)

    def test_agent_tool_catalog_exposes_start_and_poll(self):
        names = {t["name"] for t in self.hub.tools()}
        self.assertIn("hub_auth_start", names)
        self.assertIn("hub_auth_poll", names)

    def test_callback_login_then_connect_without_full_panel_for_both_protocol_eras(self):
        for version in ("2025-11-25", "2026-07-28"):
            with self.subTest(version=version):
                self.hub.auth.logout(self.config)
                flow = self.call("hub_auth_start", {"server": "protected"}, version)
                self.assertEqual(flow["status"], "awaiting_user")
                self.assertNotIn("#session=", flow["url"])
                callback = parse_qs(urlsplit(flow["url"]).query)["redirect_uri"][0]
                self.assertEqual(
                    self.request(callback.replace("/oauth/callback", "/api/v1/state"))[0], 404
                )
                status, _, body = self.authorize(flow)
                self.assertEqual(status, 200, body)
                value = self.call(
                    "hub_auth_poll", {"server": "protected", "login_id": flow["login_id"]}, version
                )
                self.assertEqual(value["status"], "authenticated")
                self.assertEqual(
                    self.call("hub_connect", {"server": "protected"}, version)["status"],
                    "connected",
                )
                self.assertFalse((self.root / "state/http-auth.json").exists())
                encoded = json.dumps({"flow": flow, "status": value}) + body.decode()
                for secret in self.provider.access:
                    self.assertNotIn(secret, encoded)

    def test_repeated_start_reuses_flow_and_rejects_wrong_host_and_state(self):
        flow = self.call("hub_auth_start", {"server": "protected"})
        self.assertEqual(flow, self.call("hub_auth_start", {"server": "protected"}))
        callback = parse_qs(urlsplit(flow["url"]).query)["redirect_uri"][0]
        self.assertEqual(self.request(callback + "?state=invalid&code=invalid")[0], 400)
        self.assertEqual(self.request(callback, host="attacker.invalid")[0], 403)
        self.assertEqual(self.authorize(flow)[0], 200)

    def test_listener_closes_on_expiry_and_hub_shutdown(self):
        flow = self.call("hub_auth_start", {"server": "protected"})
        callback = parse_qs(urlsplit(flow["url"]).query)["redirect_uri"][0]
        with patch("joongi_hub.agent_login.time.time", return_value=time.time() + 601):
            deadline = time.monotonic() + 3
            while self.hub.agent_logins.server and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertIsNone(self.hub.agent_logins.server)
        with self.assertRaises(OSError):
            self.request(callback)
        self.call("hub_auth_start", {"server": "protected"})
        self.hub.close()
        self.assertIsNone(self.hub.agent_logins.server)

    def test_device_login_polls_without_opening_callback_or_leaking_device_secret(self):
        config = {**self.config, "auth": {"type": "device_code", "client_id": "registered-client"}}
        self.hub.register(config)
        flow = self.call("hub_auth_start", {"server": "protected"})
        self.assertEqual(flow["user_code"], "TEST-CODE")
        self.assertIsNone(self.hub.agent_logins.server)
        for secret in self.provider.devices:
            self.assertNotIn(secret, json.dumps(flow))
        self.assertEqual(
            self.call("hub_auth_poll", {"server": "protected", "login_id": flow["login_id"]})[
                "status"
            ],
            "pending",
        )
        for device in self.provider.devices:
            self.provider.devices[device] = True
        self.hub.auth.pending[flow["login_id"]]["next_poll"] = 0
        self.assertEqual(
            self.call("hub_auth_poll", {"server": "protected", "login_id": flow["login_id"]})[
                "status"
            ],
            "authenticated",
        )
        self.assertEqual(
            self.call("hub_auth_poll", {"server": "protected"})["status"], "authenticated"
        )

    def test_callback_rejects_login_started_elsewhere_and_changed_registration(self):
        flow = self.call("hub_auth_start", {"server": "protected"})
        callback = parse_qs(urlsplit(flow["url"]).query)["redirect_uri"][0]
        other = self.hub.auth.begin(self.config, redirect=callback)
        self.assertEqual(self.authorize(other)[0], 400)
        self.assertIn(other["login_id"], self.hub.auth.pending)
        # Keep housekeeping from retiring the listener first so this assertion
        # specifically exercises complete()'s registration-fingerprint rejection.
        with patch.object(self.hub.agent_logins, "prune"):
            with self.hub.agent_logins.lock:
                self.hub.register(
                    {**self.config, "auth": {**self.config["auth"], "scopes": ["read"]}}
                )
            self.assertEqual(self.authorize(flow)[0], 400)
        self.assertFalse(self.hub.auth.status(self.hub.registry.list()[0])["configured"])

    def test_changed_registration_retires_callback_and_cannot_authenticate(self):
        flow = self.call("hub_auth_start", {"server": "protected"})
        listener = self.hub.agent_logins.server
        thread = self.hub.agent_logins.thread
        self.hub.register({**self.config, "auth": {**self.config["auth"], "scopes": ["read"]}})
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive(), "Invalidated callback listener must retire")
        self.assertIsNone(self.hub.agent_logins.server)
        self.assertNotIn(flow["login_id"], self.hub.auth.pending)
        with self.assertRaises(RpcError):
            self.hub.agent_logins.complete("state=" + flow["login_id"] + "&code=unused", listener)
        self.assertFalse(self.hub.auth.status(self.hub.registry.list()[0])["configured"])

    def test_project_login_cannot_complete_through_the_global_callback(self):
        project_root = self.root / "project"
        project_root.mkdir()
        self.hub.projects.put(
            {"id": "scoped", "root": str(project_root), "common_servers": ["protected"]}
        )
        project = self.hub.scoped("scoped")
        global_flow = self.call("hub_auth_start", {"server": "protected"})
        scoped_flow = project.agent_logins.start("protected")
        status, callback, _ = self.request(scoped_flow["url"])
        self.assertEqual(status, 302)
        global_callback = parse_qs(urlsplit(global_flow["url"]).query)["redirect_uri"][0]
        self.assertEqual(self.request(global_callback + "?" + urlsplit(callback).query)[0], 400)
        self.assertEqual(self.request(callback)[0], 200)
        self.assertTrue(project.auth.status(self.config)["configured"])
        self.assertFalse(self.hub.auth.status(self.config)["configured"])

    def test_real_stdio_process_can_start_login_and_observe_shared_credentials(self):
        bootstrap = (
            f"import sys;from pathlib import Path;sys.path.insert(0,{str(ROOT)!r});"
            "from joongi_hub.service import Hub;from joongi_hub.__main__ import serve_stdio;"
            "from tests.fixtures.credential_store import test_store;"
            f"hub=Hub(Path({str(ROOT / 'skills')!r}),Path(sys.argv[1]),"
            "credential_store_factory=test_store);"
            "\ntry: serve_stdio(hub)\nfinally: hub.close()"
        )
        child = subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", bootstrap, str(self.root / "state")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        output = queue.Queue()

        def read():
            for line in child.stdout:
                output.put(json.loads(line))

        threading.Thread(target=read, daemon=True).start()

        def exchange(identity, method, params):
            child.stdin.write(
                json.dumps({"jsonrpc": "2.0", "id": identity, "method": method, "params": params})
                + "\n"
            )
            child.stdin.flush()
            result = output.get(timeout=15)
            self.assertEqual(result["id"], identity)
            self.assertNotIn("error", result, result)
            return result["result"]

        try:
            exchange(
                1,
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "auth-test", "version": "1"},
                },
            )
            child.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            child.stdin.flush()
            flow = json.loads(
                exchange(
                    2,
                    "tools/call",
                    {"name": "hub_auth_start", "arguments": {"server": "protected"}},
                )["content"][0]["text"]
            )
            self.assertEqual(self.authorize(flow)[0], 200)
            status = json.loads(
                exchange(
                    3, "tools/call", {"name": "hub_auth_poll", "arguments": {"server": "protected"}}
                )["content"][0]["text"]
            )
            self.assertEqual(status["status"], "authenticated")
            self.assertTrue(self.hub.auth.status(self.config)["configured"])
            child.stdin.close()
            child.wait(timeout=10)
            self.assertEqual(child.returncode, 0)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            for stream in (child.stdin, child.stdout, child.stderr):
                if not stream.closed:
                    stream.close()

    def test_connect_failure_tells_agent_which_login_tool_to_call(self):
        response = self.hub.rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "hub_connect", "arguments": {"server": "protected"}},
            },
            {"version": "2025-11-25", "ready": True, "owner": "test"},
        )
        self.assertEqual(response["error"]["data"]["next_tool"], "hub_auth_start")
        self.assertEqual(response["error"]["data"]["arguments"], {"server": "protected"})
