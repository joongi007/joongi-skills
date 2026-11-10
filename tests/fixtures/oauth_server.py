"""Local OAuth provider emulator: independently checks PKCE, resource and grants."""

import base64
import hashlib
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

from tests.fixtures.mcp_server import Fixture


class OAuthProvider(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), OAuthHandler)
        self.base = f"http://127.0.0.1:{self.server_port}"
        self.issuer = self.base + "/issuer"
        self.resource = self.base + "/mcp"
        self.codes = {}
        self.access = set()
        self.refresh = set()
        self.clients = {"registered-client": {"token_endpoint_auth_method": "none"}}
        self.devices = {}
        self.refreshes = 0
        self.allow_refresh = True
        self.oidc_only = False
        self.wrong_issuer = False
        self.accept_header = None
        self.grants = []
        self.mcp = Fixture("2025-11-25")


class OAuthHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, value=None, headers=None):
        body = json.dumps(value).encode() if value is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        s = self.server
        p = urlsplit(self.path)
        if p.path == "/mcp":
            self.send(
                401,
                {},
                {
                    "WWW-Authenticate": (
                        f'Bearer resource_metadata="{s.base}/protected-metadata", scope="read"'
                    )
                },
            )
        elif p.path in {"/protected-metadata", "/.well-known/oauth-protected-resource/mcp"}:
            self.send(
                200,
                {
                    "resource": s.resource,
                    "authorization_servers": [s.issuer],
                    "scopes_supported": ["read", "write"],
                },
            )
        elif p.path in {
            "/.well-known/oauth-authorization-server/issuer",
            "/issuer/.well-known/openid-configuration",
        }:
            if s.oidc_only and p.path != "/issuer/.well-known/openid-configuration":
                self.send(404, {})
                return
            self.send(
                200,
                {
                    "issuer": s.base + "/wrong" if s.wrong_issuer else s.issuer,
                    "authorization_endpoint": s.base + "/authorize",
                    "token_endpoint": s.base + "/token",
                    "registration_endpoint": s.base + "/register",
                    "device_authorization_endpoint": s.base + "/device",
                    "revocation_endpoint": s.base + "/revoke",
                    "code_challenge_methods_supported": ["S256"],
                },
            )
        elif p.path == "/authorize":
            q = {k: v[0] for k, v in parse_qs(p.query).items()}
            if (
                q.get("client_id") not in s.clients
                or q.get("code_challenge_method") != "S256"
                or q.get("resource") != s.resource
            ):
                self.send(400, {"error": "invalid_request"})
                return
            code = secrets.token_urlsafe(20)
            s.codes[code] = q
            self.send(
                302,
                headers={
                    "Location": q["redirect_uri"]
                    + "?"
                    + urlencode({"code": code, "state": q["state"], "iss": s.issuer})
                },
            )
        else:
            self.send(404, {})

    def do_POST(self):
        s = self.server
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/register":
            body = json.loads(raw)
            client = "dynamic-" + str(len(s.clients))
            s.clients[client] = body
            self.send(201, {"client_id": client, "token_endpoint_auth_method": "none"})
            return
        if self.path == "/mcp":
            header = self.headers.get("Authorization") or self.headers.get("X-API-Key")
            valid = header in {"Bearer " + token for token in s.access} or (
                s.accept_header and header == s.accept_header
            )
            if not valid:
                self.send(
                    401,
                    {},
                    {
                        "WWW-Authenticate": (
                            f'Bearer resource_metadata="{s.base}/protected-metadata", scope="read"'
                        )
                    },
                )
                return
            result = s.mcp.handle(json.loads(raw))
            self.send(200 if result else 202, result)
            return
        q = {k: v[0] for k, v in parse_qs(raw.decode()).items()}
        if self.path == "/revoke":
            s.access.clear()
            s.refresh.discard(q.get("token"))
            self.send(200)
            return
        if self.path == "/device":
            code = secrets.token_urlsafe(16)
            s.devices[code] = False
            self.send(
                200,
                {
                    "device_code": code,
                    "user_code": "TEST-CODE",
                    "verification_uri": s.base + "/device-login",
                    "expires_in": 600,
                    "interval": 5,
                },
            )
            return
        if self.path != "/token":
            self.send(404, {})
            return
        client = q.get("client_id")
        if client not in s.clients or q.get("resource") != s.resource:
            self.send(400, {"error": "invalid_client"})
            return
        registration = s.clients[client]
        method = registration.get("token_endpoint_auth_method", "none")
        if method == "client_secret_basic":
            expected = (
                "Basic "
                + base64.b64encode((client + ":" + registration["client_secret"]).encode()).decode()
            )
            if self.headers.get("Authorization") != expected:
                self.send(401, {"error": "invalid_client"})
                return
        elif method == "client_secret_post" and q.get("client_secret") != registration.get(
            "client_secret"
        ):
            self.send(401, {"error": "invalid_client"})
            return
        grant = q.get("grant_type")
        s.grants.append(grant)
        if grant == "authorization_code":
            original = s.codes.pop(q.get("code"), None)
            challenge = (
                base64.urlsafe_b64encode(
                    hashlib.sha256(q.get("code_verifier", "").encode()).digest()
                )
                .decode()
                .rstrip("=")
            )
            if (
                not original
                or original["code_challenge"] != challenge
                or original["redirect_uri"] != q.get("redirect_uri")
            ):
                self.send(400, {"error": "invalid_grant"})
                return
        elif grant == "refresh_token":
            if not s.allow_refresh or q.get("refresh_token") not in s.refresh:
                self.send(400, {"error": "invalid_grant"})
                return
            s.refreshes += 1
            s.refresh.discard(q["refresh_token"])
        elif grant == "urn:ietf:params:oauth:grant-type:device_code":
            if not s.devices.get(q.get("device_code")):
                self.send(400, {"error": "authorization_pending"})
                return
        elif grant != "client_credentials":
            self.send(400, {"error": "unsupported_grant_type"})
            return
        access = "fixture-access-" + secrets.token_hex(12)
        refresh = "fixture-refresh-" + secrets.token_hex(12)
        s.access.add(access)
        s.refresh.add(refresh)
        self.send(
            200,
            {
                "access_token": access,
                "refresh_token": refresh,
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )
