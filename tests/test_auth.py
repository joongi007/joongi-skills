"""OAuth interoperability uses a real independent HTTP provider and Hub callback."""

import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit

from joongi_hub.auth import AuthManager
from joongi_hub.errors import RpcError
from joongi_hub.server import HubServer
from joongi_hub.service import Hub
from joongi_hub.upstream import validate_server
from tests.fixtures.oauth_server import OAuthProvider

ROOT = Path(__file__).resolve().parents[1]


class Authentication(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.hub = Hub(ROOT / "skills", Path(self.temp.name))
        self.addCleanup(self.hub.close)
        self.provider = OAuthProvider()
        self.panel = HubServer(("127.0.0.1", 0), self.hub)
        for server in (self.provider, self.panel):
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.config = {
            "id": "protected",
            "transport": "http",
            "url": self.provider.resource,
            "auth": {"type": "oauth", "client_id": "registered-client"},
        }
        self.hub.register(self.config)

    def authorize(self, config=None, callback=False):
        config = config or self.config
        begin = self.hub.auth.begin(config)
        parsed = urlsplit(begin["url"])
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        connection.request("GET", parsed.path + "?" + parsed.query)
        response = connection.getresponse()
        self.assertEqual(response.status, 302)
        redirect = urlsplit(response.getheader("Location"))
        response.read()
        connection.close()
        if callback:
            status, body = self.panel_request(
                "GET",
                redirect.path + "?" + redirect.query,
                headers={"Sec-Fetch-Site": "cross-site"},
            )
            self.assertEqual(status, 200, body)
        else:
            self.hub.auth.complete(redirect.query)
        return begin, redirect

    def panel_request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.panel.server_port, timeout=10)
        connection.request(
            method,
            path,
            body=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def test_browser_pkce_callback_and_real_mcp_call(self):
        self.authorize(callback=True)
        result = self.hub.invoke("protected__echo", {"message": "authenticated"})
        self.assertIn("authenticated", result["content"][0]["text"])
        state = json.dumps(self.hub.state())
        self.assertNotIn("fixture-access-", state)
        self.assertNotIn("fixture-refresh-", state)

    def test_discovery_uses_www_authenticate_and_oidc_fallback(self):
        self.provider.oidc_only = True
        with self.assertRaises(RpcError):
            self.hub.probe("protected")
        self.assertIn("resource_metadata", self.hub.auth.challenges["protected"])
        self.authorize()
        self.assertFalse(self.hub.auth.status(self.config)["login_required"])

    def test_issuer_mismatch_and_wrong_resource_are_rejected(self):
        self.provider.wrong_issuer = True
        with self.assertRaises(RpcError):
            self.hub.auth.begin(self.config)
        self.provider.wrong_issuer = False
        self.provider.resource += "/other"
        with self.assertRaises(RpcError):
            self.hub.auth.begin(self.config)

    def test_dynamic_native_client_registration(self):
        config = {**self.config, "auth": {"type": "oauth"}}
        self.authorize(config)
        registered = next(v for k, v in self.provider.clients.items() if k.startswith("dynamic-"))
        self.assertEqual(registered["application_type"], "native")
        self.assertEqual(registered["token_endpoint_auth_method"], "none")

    def test_invalid_state_duplicate_code_and_replay_are_rejected(self):
        with self.assertRaises(RpcError):
            self.hub.auth.complete("state=unknown&code=unknown")
        _, callback = self.authorize()
        with self.assertRaises(RpcError):
            self.hub.auth.complete(callback.query)
        begin = self.hub.auth.begin(self.config)
        with self.assertRaises(RpcError):
            self.hub.auth.complete(urlencode({"state": begin["login_id"], "code": "x"}) + "&code=y")

    def test_expiry_refresh_rotation_and_server_rejection_retry(self):
        self.authorize()
        before = self.hub.auth.headers(self.config)["Authorization"]
        with self.hub.auth.lock:
            row = self.hub.auth._record(self.config)
            row["token"]["expires_at"] = time.time() - 10
            self.hub.auth._save(self.config, row)
        after = self.hub.auth.headers(self.config)["Authorization"]
        self.assertNotEqual(before, after)
        self.assertEqual(self.provider.refreshes, 1)
        self.provider.access.clear()
        self.hub.invoke("protected__echo", {})
        self.assertEqual(self.provider.refreshes, 2)

    def test_invalid_refresh_discards_token_and_logout_revokes(self):
        self.authorize()
        self.assertTrue(self.hub.auth.logout(self.config)["revoked"])
        self.assertTrue(self.hub.auth.status(self.config)["login_required"])
        self.authorize()
        self.provider.allow_refresh = False
        row = self.hub.auth._record(self.config)
        row["token"]["expires_at"] = time.time() - 10
        self.hub.auth._save(self.config, row)
        with self.assertRaises(RpcError):
            self.hub.auth.headers(self.config)
        self.assertTrue(self.hub.auth.status(self.config)["login_required"])

    def test_device_code_respects_poll_interval_and_stores_token(self):
        config = {**self.config, "auth": {"type": "device_code", "client_id": "registered-client"}}
        begin = self.hub.auth.begin(config)
        self.assertEqual(begin["user_code"], "TEST-CODE")
        self.assertEqual(self.hub.auth.poll(config, begin["login_id"])["status"], "pending")
        for device in self.provider.devices:
            self.provider.devices[device] = True
        self.hub.auth.pending[begin["login_id"]]["next_poll"] = 0
        self.assertEqual(self.hub.auth.poll(config, begin["login_id"])["status"], "authenticated")
        self.assertIn("Authorization", self.hub.auth.headers(config))

    def test_client_credentials_and_confidential_client_auth_methods(self):
        for method in ("client_secret_basic", "client_secret_post"):
            with (
                self.subTest(method=method),
                patch.dict(os.environ, {"TEST_CLIENT_SECRET": "secret"}),
            ):
                self.provider.clients["registered-client"] = {
                    "token_endpoint_auth_method": method,
                    "client_secret": "secret",
                }
                config = {
                    **self.config,
                    "auth": {
                        "type": "client_credentials",
                        "client_id": "registered-client",
                        "client_secret_env": "TEST_CLIENT_SECRET",
                        "client_auth_method": method,
                    },
                }
                self.assertIn("Authorization", self.hub.auth.headers(config))
                self.hub.auth.logout(config)

    def test_manual_credentials_and_environment_modes_do_not_leak(self):
        for auth, values in (
            ({"type": "bearer"}, {"token": "SECRET"}),
            ({"type": "api_key", "header": "X-API-Key"}, {"token": "SECRET"}),
            ({"type": "basic"}, {"username": "user", "password": "SECRET"}),
        ):
            config = {**self.config, "auth": auth}
            self.hub.auth.set_manual(config, values)
            self.assertTrue(self.hub.auth.headers(config))
            self.assertNotIn("SECRET", json.dumps(self.hub.auth.status(config)))
        if os.name != "nt":
            self.assertEqual(self.hub.auth.path.stat().st_mode & 0o777, 0o600)

    def test_changed_server_cannot_reuse_credentials_or_other_profile_tokens(self):
        self.authorize()
        changed = {**self.config, "url": self.config["url"] + "/different"}
        with self.assertRaises(RpcError):
            self.hub.auth.headers(changed)
        project = Path(self.temp.name) / "project"
        project.mkdir()
        self.hub.projects.put(
            {"id": "isolated", "root": str(project), "common_servers": ["protected"]}
        )
        with self.assertRaises(RpcError):
            self.hub.scoped("isolated").auth.headers(self.config)

    def test_auth_endpoints_require_local_management_token_and_hide_secrets(self):
        config = {**self.config, "auth": {"type": "bearer"}}
        self.hub.register(config)
        path = "/api/v1/auth/protected/credentials"
        self.assertEqual(self.panel_request("POST", path, {"token": "SECRET"})[0], 403)
        status, body = self.panel_request(
            "POST", path, {"token": "SECRET"}, {"X-Hub-Token": self.panel.token}
        )
        self.assertEqual(status, 200, body)
        self.assertNotIn(b"SECRET", body)

    def test_pkce_support_and_callback_issuer_are_required(self):
        original = self.hub.auth._metadata

        def metadata(config):
            value, resource, scopes = original(config)
            return {**value, "code_challenge_methods_supported": []}, resource, scopes

        with patch.object(self.hub.auth, "_metadata", side_effect=metadata):
            with self.assertRaises(RpcError):
                self.hub.auth.begin(self.config)
        begin = self.hub.auth.begin(self.config)
        pending = self.hub.auth.pending[begin["login_id"]]
        pending["row"]["metadata"]["authorization_response_iss_parameter_supported"] = True
        with self.assertRaises(RpcError):
            self.hub.auth.complete(urlencode({"state": begin["login_id"], "code": "test"}))

    def test_cimd_document_binding_and_pkce_token_exchange(self):
        from joongi_hub.auth import document

        url = "https://client.example.com/joongi.json"
        self.provider.clients[url] = {"token_endpoint_auth_method": "none"}
        config = {**self.config, "auth": {"type": "oauth", "client_metadata_url": url}}
        original = self.hub.auth._metadata

        def metadata(config):
            value, resource, scopes = original(config)
            return {**value, "client_id_metadata_document_supported": True}, resource, scopes

        def fetch(target, *args, **kwargs):
            if target == url:
                return {
                    "client_id": url,
                    "client_name": "Test Hub",
                    "redirect_uris": [self.hub.auth.callback_url],
                }
            return document(target, *args, **kwargs)

        with (
            patch.object(self.hub.auth, "_metadata", side_effect=metadata),
            patch("joongi_hub.auth.document", side_effect=fetch),
        ):
            self.authorize(config)
        self.assertTrue(self.hub.auth.status(config)["configured"])
        with (
            patch.object(self.hub.auth, "_metadata", side_effect=metadata),
            patch(
                "joongi_hub.auth.document",
                return_value={"client_id": url, "client_name": "Bad", "redirect_uris": []},
            ),
        ):
            with self.assertRaises(RpcError):
                self.hub.auth.begin(config)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI requires native Windows")
    def test_windows_dpapi_roundtrip_hides_plaintext(self):
        manager = AuthManager(Path(self.temp.name) / "dpapi")
        config = {**self.config, "auth": {"type": "bearer"}}
        manager.set_manual(config, {"token": "fake-windows-private-token"})
        self.assertNotIn("fake-windows-private-token", manager.path.read_text())
        self.assertEqual(
            AuthManager(manager.path.parent.parent).headers(config),
            {"Authorization": "Bearer fake-windows-private-token"},
        )

    def test_unsafe_auth_config_and_transport_rejected(self):
        for auth in (
            {"type": "oauth", "issuer": "http://example.com"},
            {"type": "bearer", "token": "literal-secret"},
            {"type": "api_key", "header": "X-Key\r\nInjected"},
        ):
            with self.subTest(auth=auth), self.assertRaises(RpcError):
                validate_server({**self.config, "auth": auth})
        with self.assertRaises(RpcError):
            validate_server(
                {"id": "stdio", "transport": "stdio", "command": "x", "auth": {"type": "oauth"}}
            )


if __name__ == "__main__":
    unittest.main()
