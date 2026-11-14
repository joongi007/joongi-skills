"""Loopback HTTP control panel, same-origin API, and MCP transport."""

import json
import mimetypes
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from joongi_hub.apps import AppSessions
from joongi_hub.connections import agent_value, configuration, state_id
from joongi_hub.errors import RpcError
from joongi_hub.local_auth import authenticate_local, local_token
from joongi_hub.security_events import record
from joongi_hub.upstream import MAX_MESSAGE, MODERN, VERSIONS

STATIC = Path(__file__).parent / "static"


class HubServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, hub):
        self.hub = hub
        self.apps = AppSessions(hub)
        local_token(hub.state_dir, management=True)
        local_token(hub.state_dir)
        self.instance_id = secrets.token_urlsafe(24)
        self.sessions = {}
        self.session_lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(32)
        self.auth_failures = {}
        super().__init__(address, Handler)
        self.hub.auth.callback_url = f"http://127.0.0.1:{self.server_address[1]}/oauth/callback"
        self.profile_apps = {"global": self.apps}

    @property
    def token(self):
        return local_token(self.hub.state_dir, management=True)

    def apps_for(self, hub):
        session = self.profile_apps.get(hub.profile_id)
        if session is None or session.hub is not hub:
            session = AppSessions(hub)
            self.profile_apps[hub.profile_id] = session
        return session

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "JoongiHub"
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(25)

    def log_message(self, format, *args):
        # Request bodies, resource paths, tokens and tool arguments are never logged.
        pass

    def send_data(
        self, status, data=None, content_type="application/json; charset=utf-8", headers=None
    ):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        if status == 204:
            body = b""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'",
        )
        if getattr(self, "next_local_token", None):
            self.send_header("X-Hub-Next-Token", self.next_local_token)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def reject_authentication(self, scope, status, message, headers=None):
        now = time.monotonic()
        with self.server.session_lock:
            start, count = self.server.auth_failures.get(scope, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            count += 1
            self.server.auth_failures[scope] = (start, count)
        # Valid credentials are checked first and can never be locked out by bad callers.
        if count <= 21:
            record(
                self.server.hub.state_dir,
                "authentication_limited" if count == 21 else "authentication_denied",
                scope,
            )
        self.close_connection = True
        if count > 20:
            self.send_data(
                429,
                {"error": "인증 실패가 반복됐습니다. 잠시 후 다시 시도하세요."},
                headers={"Retry-After": "60", "Connection": "close"},
            )
        else:
            self.send_data(
                status, {"error": message}, headers={**(headers or {}), "Connection": "close"}
            )
        return False

    def guard(self):
        self.next_local_token = None
        host = self.headers.get("Host", "")
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if host not in allowed:
            self.send_data(403, {"error": "Untrusted Host header"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + value for value in allowed}:
            self.send_data(403, {"error": "Cross-origin requests are not allowed"})
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.send_data(403, {"error": "Cross-site requests are not allowed"})
            return False
        path = unquote(urlparse(self.path).path)
        if path == "/mcp" or path.startswith("/mcp/projects/"):
            profile = (
                path.removeprefix("/mcp/projects/")
                if path.startswith("/mcp/projects/")
                else "global"
            )
            supplied = self.headers.get("Authorization", "")
            renewed = authenticate_local(
                self.server.hub.state_dir,
                supplied[7:] if supplied.startswith("Bearer ") else "",
                profile,
            )
            if not renewed:
                return self.reject_authentication(
                    "mcp",
                    401,
                    "HTTP MCP 연결 자격증명이 필요합니다.",
                    {"WWW-Authenticate": 'Bearer realm="joongi-hub"'},
                )
            if self.headers.get("X-Hub-Profile", profile) != profile:
                self.send_data(400, {"error": "이 연결의 프로젝트를 변경할 수 없습니다."})
                return False
        elif path.startswith("/api/v1/"):
            self.next_local_token = authenticate_local(
                self.server.hub.state_dir, self.headers.get("X-Hub-Token", ""), management=True
            )
            if not self.next_local_token:
                return self.reject_authentication(
                    "management", 403, "Open the local panel to obtain an API session"
                )
        return True

    def mcp_path(self):
        return self.path == "/mcp" or self.path.startswith("/mcp/projects/")

    def path_profile(self):
        if not self.path.startswith("/mcp/projects/"):
            return None
        identity = self.path.removeprefix("/mcp/projects/")
        self.server.hub.projects.get(identity)
        return identity

    def read_json(self):
        if self.headers.get("Transfer-Encoding"):
            raise RpcError(-32600, "Transfer-Encoding is not supported")
        if self.headers.get_content_type() != "application/json":
            raise RpcError(-32600, "Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise RpcError(-32600, "Invalid Content-Length") from exc
        if length <= 0 or length > MAX_MESSAGE:
            raise RpcError(-32600, "Body must contain JSON and be at most 4 MiB")
        try:
            return json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError) as exc:
            raise RpcError(-32700, "Invalid JSON") from exc

    def active_hub(self):
        return self.server.hub.scoped(self.headers.get("X-Hub-Profile", "global"))

    def server_config(self, hub, identity):
        value = next((c for c in hub.registry.list() if c["id"] == identity), None)
        if value is None:
            raise RpcError(-32602, "등록되지 않은 MCP입니다.")
        return value

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.next_local_token = None
        parsed = urlparse(self.path)
        if parsed.path == "/oauth/callback":
            port = self.server.server_address[1]
            if self.headers.get("Host") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
                self.send_data(403, {"error": "Untrusted Host header"})
                return
            try:
                states = parse_qs(parsed.query).get("state", [])
                managers = [
                    self.server.hub.auth,
                    *[h.auth for h in self.server.hub.profile_hubs.values()],
                ]
                manager = next(
                    (m for m in managers if len(states) == 1 and states[0] in m.pending), None
                )
                if manager is None:
                    raise RpcError(-32040, "로그인 요청이 만료되었거나 state를 확인할 수 없습니다.")
                manager.complete(parsed.query)
                self.send_data(
                    200,
                    "로그인을 마쳤습니다. 이 창을 닫고 Hub에서 연결 확인을 누르세요.".encode(),
                    "text/plain; charset=utf-8",
                )
            except RpcError:
                self.send_data(
                    400,
                    "로그인을 완료하지 못했습니다. Hub에서 다시 시작하세요.".encode(),
                    "text/plain; charset=utf-8",
                )
            return
        if not self.guard():
            return
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            hub = self.active_hub()
            if path == "/api/v1/approvals":
                self.send_data(200, hub.tool_policy.list())
            elif path == "/api/v1/projects":
                self.send_data(
                    200,
                    {
                        "projects": [
                            {**p, "connection": self.server.hub.profile_connection(p["id"])}
                            for p in self.server.hub.projects.list()
                        ],
                        "active": hub.profile_id,
                    },
                )
            elif path == "/api/v1/skill-management/status":
                self.send_data(200, hub.skill_manager.status())
            elif path == "/api/v1/connection":
                settings = hub.connection_settings.get()
                connection = configuration(
                    self.server.hub, hub.profile_id, wsl_distribution=query.get("wsl", [None])[0]
                )
                self.send_data(
                    200,
                    {
                        "settings": settings,
                        "inherited": bool(hub.project and hub.connection_settings.local() is None),
                        "state_dir": str(hub.state_dir),
                        "connection": connection,
                        "configured": bool(
                            hub.connection_settings.local()
                            or self.server.hub.connection_settings.local()
                        ),
                        "runtime": {
                            "running": True,
                            "url": f"http://127.0.0.1:{self.server.server_port}",
                            "instance": self.server.instance_id,
                        },
                        "wsl_distribution": os.environ.get("WSL_DISTRO_NAME", ""),
                        "agents": {
                            name: agent_value(name, connection)
                            for name in (
                                "claude",
                                "codex",
                                "cursor",
                                "copilot",
                                "gemini",
                                "opencode",
                            )
                        },
                    },
                )
            elif path == "/healthz":
                self.send_data(
                    200,
                    {
                        "status": "ok",
                        "instance": self.server.instance_id,
                        "state_id": state_id(self.server.hub.state_dir),
                    },
                )
            elif path.startswith("/apps/"):
                profile = query.get("profile", [hub.profile_id])[0]
                app = self.server.apps_for(self.server.hub.scoped(profile)).get(
                    path.removeprefix("/apps/")
                )
                body = app["html"].encode("utf-8")
                self.send_response(200)
                for key, value in {
                    "Content-Type": "text/html; charset=utf-8",
                    "Content-Length": str(len(body)),
                    "Cache-Control": "no-store",
                    "Content-Security-Policy": app["policy"],
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "no-referrer",
                }.items():
                    self.send_header(key, value)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
            elif path == "/api/v1/session":
                self.send_data(200, {"token": self.server.token})
            elif path == "/api/v1/state":
                self.send_data(200, hub.state())
            elif path == "/api/v1/search":
                self.send_data(200, hub.search(query.get("q", [""])[0]))
            elif path.startswith("/api/v1/skills/"):
                name = path.removeprefix("/api/v1/skills/")
                self.send_data(200, hub.skills.read(name, query.get("path", ["SKILL.md"])[0]))
            elif path == "/api/v1/tasks":
                self.send_data(200, hub.tasks.list())
            elif path == "/mcp" or path.startswith("/mcp/projects/"):
                self.send_data(
                    405,
                    {"error": "Use POST for MCP; subscriptions are not offered"},
                    headers={"Allow": "POST"},
                )
            elif path == "/" or path.startswith("/static/"):
                relative = "index.html" if path == "/" else path.removeprefix("/static/")
                target = (STATIC / relative).resolve()
                if not target.is_relative_to(STATIC.resolve()) or not target.is_file():
                    self.send_data(404, {"error": "Not found"})
                    return
                mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                self.send_data(200, target.read_bytes(), mime + "; charset=utf-8")
            else:
                self.send_data(404, {"error": "Not found"})
        except RpcError as exc:
            self.send_data(400, {"error": str(exc), "code": exc.code})
        except Exception:
            self.send_data(500, {"error": "Local request failed"})

    def do_POST(self):
        if not self.guard():
            self.close_connection = True
            return
        try:
            hub = self.active_hub()
            body = self.read_json()
            if self.path == "/mcp" or self.path.startswith("/mcp/projects/"):
                self.handle_mcp(body)
                return
            if not isinstance(body, dict):
                raise RpcError(-32602, "Request body must be an object")
            if self.path.startswith("/api/v1/approvals/"):
                if set(body) != {"approve"} or type(body["approve"]) is not bool:
                    raise RpcError(-32602, "승인 여부를 지정하세요.")
                self.send_data(
                    200,
                    hub.tool_policy.decide(
                        self.path.removeprefix("/api/v1/approvals/"), body["approve"]
                    ),
                )
            elif self.path == "/api/v1/connection":
                self.send_data(200, hub.connection_settings.put(body))
            elif self.path == "/api/v1/connection/plan":
                if set(body) != {"agents"}:
                    raise RpcError(-32602, "에이전트 선택을 확인하세요.")
                self.send_data(200, hub.agent_connections.plan(body["agents"]))
            elif self.path == "/api/v1/connection/apply":
                if set(body) != {"plan_id"}:
                    raise RpcError(-32602, "연결 계획을 확인하세요.")
                self.send_data(200, hub.agent_connections.apply(body["plan_id"]))
            elif self.path == "/api/v1/runtime/stop":
                if body != {"instance": self.server.instance_id}:
                    raise RpcError(-32602, "실행 중인 Hub를 다시 확인하세요.")
                self.send_data(200, {"stopping": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            elif self.path == "/api/v1/projects":
                self.send_data(200, self.server.hub.projects.put(body))
            elif self.path == "/api/v1/skill-management/plan":
                if set(body) - {"operation", "names", "agents", "refresh"}:
                    raise RpcError(-32602, "계획 필드를 확인하세요.")
                self.send_data(200, hub.skill_manager.plan(**body))
            elif self.path == "/api/v1/skill-management/apply":
                self.send_data(200, hub.skill_manager.apply(body.get("plan_id")))
            elif self.path.startswith("/api/v1/auth/"):
                parts = self.path.split("/")
                if len(parts) != 6:
                    raise RpcError(-32602, "인증 경로를 확인하세요.")
                config = self.server_config(hub, parts[4])
                action = parts[5]
                if action == "login":
                    self.send_data(200, hub.auth.begin(config))
                elif action == "credentials":
                    self.send_data(200, hub.auth.set_manual(config, body))
                elif action == "poll":
                    self.send_data(200, hub.auth.poll(config, body.get("login_id")))
                elif action == "logout":
                    self.send_data(200, hub.auth.logout(config))
                else:
                    raise RpcError(-32602, "지원하지 않는 인증 동작입니다.")
            elif self.path == "/api/v1/servers":
                self.send_data(200, hub.register(body))
            elif self.path == "/api/v1/apps":
                self.send_data(
                    200, self.server.apps_for(hub).prepare(body.get("server"), body.get("tool"))
                )
            elif self.path.startswith("/api/v1/apps/") and self.path.endswith("/rpc"):
                self.send_data(
                    200,
                    self.server.apps_for(hub).request(
                        self.path.split("/")[-2], body.get("method"), body.get("params", {})
                    ),
                )
            elif self.path.startswith("/api/v1/servers/") and self.path.endswith("/probe"):
                self.send_data(200, hub.probe(self.path.split("/")[-2]))
            elif self.path == "/api/v1/call":
                name, arguments = body.get("name"), body.get("arguments", {})
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    raise RpcError(-32602, "Tool name and arguments are required")
                result = (
                    hub.start_task(name, arguments, "ui")
                    if body.get("task")
                    else hub.invoke(name, arguments)
                )
                self.send_data(200, result)
            elif self.path.startswith("/api/v1/tasks/") and self.path.endswith("/cancel"):
                self.send_data(200, hub.cancel_task(self.path.split("/")[-2]))
            elif self.path.startswith("/api/v1/tasks/") and self.path.endswith("/input"):
                self.send_data(
                    200, hub.respond_task(self.path.split("/")[-2], body.get("inputResponses"))
                )
            else:
                self.send_data(404, {"error": "Not found"})
        except RpcError as exc:
            self.close_connection = True
            status = 400 if exc.code in {-32600, -32602, -32700} else 502
            if self.path == "/mcp":
                self.send_data(status, {"jsonrpc": "2.0", "id": None, "error": exc.as_dict()})
            else:
                self.send_data(status, {"error": str(exc), "code": exc.code, "data": exc.data})
        except Exception:
            self.close_connection = True
            self.send_data(500, {"error": "Local request failed"})

    def handle_mcp(self, body):
        if not isinstance(body, dict):
            raise RpcError(-32600, "JSON-RPC batching is not supported")
        params = body.get("params", {})
        if not isinstance(params, dict):
            raise RpcError(-32602, "params must be an object")
        meta = params.get("_meta", {})
        if not isinstance(meta, dict):
            raise RpcError(-32602, "_meta must be an object")
        profile = self.path_profile() or "global"
        if meta.get("joongi-hub/profile", profile) != profile:
            raise RpcError(-32602, "이 연결의 프로젝트를 변경할 수 없습니다.")
        metadata_version = meta.get("io.modelcontextprotocol/protocolVersion")
        header_version = self.headers.get("MCP-Protocol-Version")
        if metadata_version and header_version and metadata_version != header_version:
            raise RpcError(-32600, "Protocol header and request metadata disagree")
        headers = {}
        if body.get("method") == "initialize":
            session_id = secrets.token_urlsafe(24)
            context = {
                "owner": session_id,
                "profile": self.path_profile()
                or self.headers.get("X-Hub-Profile")
                or meta.get("joongi-hub/profile", "global"),
            }
            with self.server.session_lock:
                if len(self.server.sessions) >= 256:
                    raise RpcError(-32000, "Session limit reached; restart hub to clear sessions")
                self.server.sessions[session_id] = context
            headers["Mcp-Session-Id"] = session_id
        elif metadata_version == MODERN or body.get("method") == "server/discover":
            context = {
                "owner": "http-local",
                "version": metadata_version or MODERN,
                "profile": self.path_profile()
                or self.headers.get("X-Hub-Profile")
                or meta.get("joongi-hub/profile", "global"),
            }
        else:
            session_id = self.headers.get("Mcp-Session-Id", "")
            context = self.server.sessions.get(session_id)
            if context is None:
                self.send_data(
                    404,
                    {
                        "jsonrpc": "2.0",
                        "id": body.get("id"),
                        "error": {
                            "code": -32000,
                            "message": "Initialize a legacy session or send modern metadata",
                        },
                    },
                )
                return
            if header_version and header_version not in VERSIONS:
                raise RpcError(
                    -32022,
                    "Unsupported protocol version",
                    {"supported": VERSIONS, "requested": header_version},
                )
        path_profile = self.path_profile()
        header_profile = self.headers.get("X-Hub-Profile")
        metadata_profile = meta.get("joongi-hub/profile")
        if path_profile and any(
            p and p != path_profile for p in (header_profile, metadata_profile)
        ):
            raise RpcError(-32602, "프로젝트 URL과 요청 범위가 다릅니다.")
        explicit_profile = path_profile or header_profile or metadata_profile
        if explicit_profile and explicit_profile != context.get("profile", "global"):
            raise RpcError(-32602, "MCP 세션과 요청의 프로젝트가 다릅니다.")
        result = self.server.hub.rpc(body, context)
        self.send_data(200 if result is not None else 202, result or {}, headers=headers)

    def do_DELETE(self):
        if not self.guard():
            return
        # DELETE bodies are unused. Close rather than leave unread bytes on keep-alive.
        if self.headers.get("Content-Length", "0") != "0" or self.headers.get("Transfer-Encoding"):
            self.close_connection = True
        if self.path.startswith("/api/v1/projects/"):
            identity = self.path.split("/")[-1]
            try:
                self.server.hub.projects.delete(identity)
                child = self.server.hub.profile_hubs.pop(identity, None)
                if child:
                    child.close()
                self.send_data(204)
            except RpcError as exc:
                self.send_data(400, {"error": str(exc)})
        elif self.path == "/mcp" or self.path.startswith("/mcp/projects/"):
            session_id = self.headers.get("Mcp-Session-Id", "")
            with self.server.session_lock:
                context = self.server.sessions.get(session_id)
                try:
                    profile = self.path_profile() or self.headers.get("X-Hub-Profile", "global")
                    if context and context.get("profile", "global") != profile:
                        raise RpcError(-32602, "MCP 세션과 종료 요청의 범위가 다릅니다.")
                except RpcError as exc:
                    self.send_data(400, {"error": str(exc)})
                    return
                self.server.sessions.pop(session_id, None)
            self.send_data(204)
        elif self.path.startswith("/api/v1/servers/"):
            try:
                self.active_hub().remove(self.path.removeprefix("/api/v1/servers/"))
                self.send_data(204)
            except RpcError as exc:
                self.send_data(400, {"error": str(exc)})
        else:
            self.send_data(404, {"error": "Not found"})

    def do_OPTIONS(self):
        self.send_data(405, {"error": "Cross-origin access is not enabled"})
