"""Agent-initiated upstream login with a temporary, callback-only listener."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from joongi_hub.auth import fingerprint
from joongi_hub.errors import RpcError


class CallbackServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 4

    def __init__(self, controller):
        self.controller = controller
        self.slots = threading.BoundedSemaphore(4)
        self.stopping = threading.Event()
        super().__init__(("127.0.0.1", 0), CallbackHandler)
        self.timeout = 0.2

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


class CallbackHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def log_message(self, *args):
        pass  # Never log callback codes, state, query strings or tokens.

    def reply(self, status, message):
        data = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def do_GET(self):
        port = self.server.server_port
        if self.headers.get("Host") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            self.reply(403, "허용하지 않는 Host입니다.")
            return
        parsed = urlsplit(self.path)
        if parsed.path != "/oauth/callback":
            self.reply(404, "로그인 callback 전용 주소입니다.")
            return
        try:
            self.server.controller.complete(parsed.query, self.server)
        except RpcError:
            self.reply(400, "로그인을 완료하지 못했습니다. 에이전트에서 다시 시작하세요.")
            return
        self.reply(200, "로그인을 마쳤습니다. 이 창을 닫고 에이전트에서 연결을 다시 시도하세요.")


class AgentLogins:
    def __init__(self, hub):
        self.hub = hub
        self.lock = threading.RLock()
        self.flows = {}
        self.server = None
        self.thread = None
        self.closed = False

    def config(self, server):
        if not isinstance(server, str) or not server or len(server) > 48:
            raise RpcError(-32602, "등록된 서버 ID를 지정하세요.")
        config = next((c for c in self.hub.registry.list() if c["id"] == server), None)
        if not config or not config.get("enabled", True):
            raise RpcError(-32602, "등록되지 않았거나 비활성화된 서버입니다.")
        return config

    def prune(self):
        with self.hub.auth.lock:
            for server, row in list(self.flows.items()):
                pending = self.hub.auth.pending.get(row["result"]["login_id"])
                if not pending or pending["expires"] <= time.time():
                    self.hub.auth.pending.pop(row["result"]["login_id"], None)
                    self.flows.pop(server, None)

    def start(self, server):
        config = self.config(server)
        kind = config.get("auth", {}).get("type")
        if kind not in {"oauth", "device_code"}:
            raise RpcError(-32602, "OAuth·device code 연결에서만 로그인 링크를 만들 수 있습니다.")
        with self.lock:
            if self.closed:
                raise RpcError(-32040, "Hub가 종료 중입니다. 새 연결에서 다시 시작하세요.")
            self.prune()
            state = self.hub.auth.status(config)
            if state["storage_error"]:
                raise RpcError(-32040, state["storage_error"])
            if state["configured"] and not state["login_required"]:
                return {"server": server, "status": "authenticated", "next_tool": "hub_connect"}
            previous = self.flows.get(server)
            if previous and previous["fingerprint"] == fingerprint(config):
                return dict(previous["result"])
            if previous:
                with self.hub.auth.lock:
                    self.hub.auth.pending.pop(previous["result"]["login_id"], None)
                self.flows.pop(server, None)
            created = None
            if kind == "oauth" and self.server is None:
                created = self.server = CallbackServer(self)
            try:
                redirect = (
                    f"http://127.0.0.1:{self.server.server_port}/oauth/callback"
                    if kind == "oauth"
                    else None
                )
                flow = self.hub.auth.begin(config, redirect=redirect)
                result = {
                    **flow,
                    "server": server,
                    "interval": flow.get("interval", 2),
                    "status": "awaiting_user",
                    "expires_at": self.hub.auth.pending[flow["login_id"]]["expires"],
                    "next_tool": "hub_auth_poll",
                    "instructions": "사용자에게 url을 열어 로그인을 승인하도록 안내하세요. "
                    "토큰을 요청하지 마세요. 승인 후 hub_auth_poll, hub_connect 순서로 확인하세요.",
                }
                self.flows[server] = {"fingerprint": fingerprint(config), "result": result}
            except BaseException:
                if created:
                    created.server_close()
                    self.server = None
                raise
            if created:
                self.thread = threading.Thread(target=self.serve, args=(created,), daemon=True)
                self.thread.start()
            return dict(result)

    def serve(self, server):
        try:
            while not server.stopping.is_set():
                server.handle_request()
                with self.lock:
                    self.prune()
                    if not any(
                        row["result"]["flow"] == "authorization_code" for row in self.flows.values()
                    ):
                        if self.server is server:
                            self.server = None
                        break
        finally:
            server.server_close()
            with self.lock:
                if self.server is server:
                    self.server = None

    def complete(self, query, server):
        states = parse_qs(query).get("state", [])
        with self.lock:
            if self.server is not server or len(states) != 1 or len(query) > 16384:
                raise RpcError(-32040, "유효하지 않은 로그인 callback입니다.")
            matching = next(
                (
                    (key, row)
                    for key, row in self.flows.items()
                    if row["result"]["login_id"] == states[0]
                ),
                None,
            )
            if not matching:
                raise RpcError(-32040, "이 callback에서 시작한 로그인 요청이 아닙니다.")
            key, row = matching
            if fingerprint(self.config(key)) != row["fingerprint"]:
                with self.hub.auth.lock:
                    self.hub.auth.pending.pop(states[0], None)
                self.flows.pop(key, None)
                raise RpcError(-32040, "로그인 중 연결 설정이 변경됐습니다. 다시 시작하세요.")
            self.hub.auth.complete(query)
            self.prune()

    def poll(self, server, login_id=None):
        config = self.config(server)
        if login_id is not None and (not isinstance(login_id, str) or len(login_id) > 256):
            raise RpcError(-32602, "login_id 형식을 확인하세요.")
        state = self.hub.auth.status(config)
        if state["configured"] and not state["login_required"]:
            return {
                "server": server,
                "status": "authenticated",
                "next_tool": "hub_connect",
                **state,
            }
        if config.get("auth", {}).get("type") == "device_code":
            if not login_id:
                raise RpcError(-32602, "device code 상태 조회에는 login_id가 필요합니다.")
            result = self.hub.auth.poll(config, login_id)
            return {"server": server, **result}
        status = (
            "authenticated"
            if state["configured"] and not state["login_required"]
            else "pending"
            if state["pending"]
            else "login_required"
        )
        return {
            "server": server,
            "status": status,
            **state,
            "next_tool": "hub_connect"
            if status == "authenticated"
            else "hub_auth_poll"
            if status == "pending"
            else "hub_auth_start",
        }

    def close(self):
        with self.lock:
            self.closed = True
            with self.hub.auth.lock:
                for row in self.flows.values():
                    self.hub.auth.pending.pop(row["result"]["login_id"], None)
            self.flows.clear()
            server, thread = self.server, self.thread
            if server:
                server.stopping.set()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=4)
