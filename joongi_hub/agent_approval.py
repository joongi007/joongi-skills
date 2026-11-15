"""Owner-browser consent; the MCP caller never receives the decision capability."""

import json
import os
import secrets
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

from joongi_hub.agent_login import CallbackHandler, CallbackServer
from joongi_hub.errors import RpcError

STATIC = Path(__file__).with_name("static")


def open_browser(url):
    # WSL's default webbrowser often has no Windows browser registered. Keep the
    # capability out of PowerShell's command line and discard all helper output.
    is_wsl = bool(os.environ.get("WSL_DISTRO_NAME"))
    if os.name != "nt" and not is_wsl:
        try:
            is_wsl = "microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower()
        except OSError:
            pass
    if is_wsl or os.name == "nt":
        try:
            executable = "powershell.exe"
            if os.name != "nt":
                executable = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
            result = subprocess.run(
                [
                    executable,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "$u=[Console]::In.ReadToEnd(); Start-Process -FilePath $u",
                ],
                input=url,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        return bool(webbrowser.open(url))
    except (OSError, webbrowser.Error):
        return False


class ApprovalHandler(CallbackHandler):
    def send(self, status, data, content_type="application/json; charset=utf-8"):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        for name, value in {
            "Content-Type": content_type,
            "Content-Length": str(len(data)),
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; "
            "style-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'none'",
            "Connection": "close",
        }.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def valid_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self.valid_host():
            self.send(403, {"error": "Host rejected"})
            return
        assets = {
            "/": ("approval.html", "text/html; charset=utf-8"),
            "/approval.js": ("approval.js", "text/javascript; charset=utf-8"),
            "/approval.css": ("approval.css", "text/css; charset=utf-8"),
            "/tokens.css": ("tokens.css", "text/css; charset=utf-8"),
            "/theme.css": ("theme.css", "text/css; charset=utf-8"),
        }
        asset = assets.get(self.path)
        if not asset:
            self.send(404, {"error": "Not found"})
            return
        self.send(200, (STATIC / asset[0]).read_bytes(), asset[1])

    def do_POST(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if (
            not self.valid_host()
            or self.path not in {"/decision", "/inbox"}
            or self.headers.get("Origin") != origin
            or self.headers.get("Sec-Fetch-Site") not in {None, "same-origin"}
            or self.headers.get("Content-Type") != "application/json"
        ):
            self.send(403, {"error": "Request rejected"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= (8192 if self.path == "/inbox" else 1024) or self.headers.get(
                "Transfer-Encoding"
            ):
                raise ValueError
            body = json.loads(self.rfile.read(size))
            if self.path == "/inbox":
                if (
                    not isinstance(body, dict)
                    or set(body) - {"action", "approval_ids"}
                    or "action" not in body
                ):
                    raise ValueError
                result = self.server.controller.inbox(
                    self.headers.get("Authorization", ""), body["action"], body.get("approval_ids")
                )
            else:
                if not isinstance(body, dict) or (
                    set(body) - {"approval_id", "action", "scope"}
                    or not {"approval_id", "action"} <= set(body)
                ):
                    raise ValueError
                result = self.server.controller.decision(
                    body["approval_id"],
                    self.headers.get("Authorization", ""),
                    body["action"],
                    body.get("scope", "once"),
                )
        except (ValueError, TypeError, RpcError):
            self.send(403, {"error": "요청이 만료되었거나 처리됐습니다. 에이전트에서 확인하세요."})
            return
        self.send(200, result)


class ApprovalServer(CallbackServer):
    def __init__(self, controller):
        super().__init__(controller)
        self.RequestHandlerClass = ApprovalHandler

    def handle_error(self, request, client_address):
        pass  # Never log capability headers or request data on malformed requests.


class AgentApprovals:
    def __init__(self, hub):
        self.hub = hub
        self.lock = threading.RLock()
        self.flows = {}
        self.server = None
        self.thread = None
        self.closed = False
        self.changed = threading.Event()
        self.window_owner = secrets.token_hex(20)
        self.window_secret = None
        self.browser_seen = False
        self.window_expires = 0
        self.opened = False

    def status(self, approval_id):
        result = self.hub.tool_policy.get(approval_id)
        # Status is deliberately not a review/approval capability.
        return {
            key: value
            for key, value in result.items()
            if key in {"approval_id", "status", "expires_at", "server", "tool"}
        }

    def wait_status(self, approval_id, wait_seconds=0):
        if (
            isinstance(wait_seconds, bool)
            or not isinstance(wait_seconds, (int, float))
            or not 0 <= wait_seconds <= 20
        ):
            raise RpcError(-32602, "wait_seconds는 0~20초로 지정하세요.")
        deadline = time.monotonic() + wait_seconds
        while True:
            result = self.status(approval_id)
            remaining = deadline - time.monotonic()
            if result["status"] != "pending" or remaining <= 0 or self.closed:
                if result["status"] == "pending":
                    result["window_open"] = self.hub.tool_policy.window_live()
                    result["instructions"] = (
                        "정상적인 사용자 승인 대기입니다. "
                        "원래 호출을 반복하지 마세요. "
                        "승인함이 닫혔다면 사용자가 다시 열어 달라고 할 때 "
                        "hub_approval_request를 사용하세요."
                    )
                return result
            # Wake immediately for this process, and detect decisions made by a
            # separate owner process within 250 ms. Never hold the controller lock.
            self.changed.wait(min(0.25, remaining))
            self.changed.clear()

    def request(self, approval_id):
        with self.lock:
            if self.closed:
                raise RpcError(-32043, "Hub가 종료 중입니다.")
            result = self.status(approval_id)
            if result["status"] != "pending":
                return result
            own = self.hub.tool_policy.window_live(self.window_owner)
            if self.server is not None and own:
                return self.delivery(result, self.opened, reused=True)
            owner = secrets.token_hex(20)
            if not self.hub.tool_policy.window_claim(owner):
                return self.delivery(result, True, reused=True)
            self.window_owner = owner
            self.flows.clear()
            self.window_secret = secrets.token_urlsafe(32)
            self.window_expires = time.time() + 8 * 3600
            self.browser_seen = False
            self.opened = True  # Owner launch is in progress; concurrent requests join it.
            self.server = ApprovalServer(self)
            self.server.window_owner = self.window_owner
            self.flows[approval_id] = {
                "secret": self.window_secret,
                "expires": result["expires_at"],
                "opened": True,
            }
            self.thread = threading.Thread(target=self.serve, args=(self.server,), daemon=True)
            self.thread.start()
            url = (
                f"http://127.0.0.1:{self.server.server_port}/"
                f"#approval_id={approval_id}&session={self.window_secret}"
            )
        try:
            opened = open_browser(url)
        except Exception:
            opened = False
        with self.lock:
            self.opened = bool(opened)
            if not opened:
                self.hub.tool_policy.window_release(self.window_owner)
                if self.server:
                    self.server.stopping.set()
                self.flows.clear()
        return self.delivery(result, bool(opened), reused=False)

    @staticmethod
    def delivery(result, opened, reused):
        return {
            **result,
            "browser_opened": opened,
            "window_reused": reused,
            "next_tool": "hub_approval_status" if opened else "hub_approval_request",
            "arguments": {
                "approval_id": result["approval_id"],
                **({"wait_seconds": 20} if opened else {}),
            },
            "instructions": "정상적인 사용자 승인 대기입니다. "
            "실패로 보고하거나 원래 호출을 반복하지 마세요. "
            "같은 범위의 기존 승인함에 MCP별 도구 요청을 모읍니다. "
            "서로 독립적인 요청은 계속 등록해 한 번에 검토할 수 있습니다. "
            "hub_approval_status(wait_seconds=20)로 기다리고 approved일 때만 재시도하세요. "
            "사용자가 거절하거나 창을 닫으면 자동으로 다시 열지 마세요.",
        }

    def authenticate_window(self, authorization):
        if (
            self.closed
            or not self.window_secret
            or self.window_expires <= time.time()
            or not isinstance(authorization, str)
            or not authorization.isascii()
            or not secrets.compare_digest(authorization, "Bearer " + self.window_secret)
            or not self.hub.tool_policy.window_live(self.window_owner, renew=True)
        ):
            raise RpcError(-32043, "승인함이 종료됐습니다. 새 요청에서 다시 여세요.")

    def remember(self, identity, result):
        if len(self.flows) >= 32 and identity not in self.flows:
            old = next(iter(self.flows))
            self.flows.pop(old, None)
        self.flows[identity] = {
            "secret": self.window_secret,
            "expires": time.time() + 30,
            "opened": True,
            "receipt": result,
        }

    def inbox(self, authorization, action, identities=None):
        with self.lock:
            self.authenticate_window(authorization)
            if action == "view" and identities is None:
                self.browser_seen = True
                rows = [row for row in self.hub.tool_policy.list() if row["status"] == "pending"]
                return {
                    "profile": self.hub.profile_id,
                    "requests": rows,
                    "receipts": [
                        flow["receipt"]
                        for flow in self.flows.values()
                        if flow.get("receipt") and flow["expires"] > time.time()
                    ],
                }
            if action in {"close", "close_if_empty"} and identities is None:
                closed = self.hub.tool_policy.window_release(
                    self.window_owner, only_if_empty=action == "close_if_empty"
                )
                if closed and self.server:
                    self.server.stopping.set()
                return {"closed": closed}
            if action not in {"approve", "deny"}:
                raise RpcError(-32602, "승인함 요청을 확인하세요.")
            decisions = self.hub.tool_policy.decide_many(identities, action == "approve")
            for row in decisions:
                self.remember(row["approval_id"], row)
            self.changed.set()
            return {"decisions": decisions}

    def decision(self, approval_id, authorization, action, scope="once"):
        if (not isinstance(scope, str) or scope not in {"once", "hour", "always"}) or (
            action != "approve" and scope != "once"
        ):
            raise RpcError(-32602, "승인 범위를 확인하세요.")
        with self.lock:
            self.authenticate_window(authorization)
            flow = self.flows.get(approval_id) if isinstance(approval_id, str) else None
            if flow and flow["expires"] <= time.time():
                self.flows.pop(approval_id, None)
                flow = None
            row = self.hub.tool_policy.get(approval_id)
            if not flow:
                if row["status"] != "pending":
                    raise RpcError(-32043, "이미 처리됐거나 만료된 승인 요청입니다.")
                flow = {"secret": self.window_secret, "expires": row["expires_at"], "opened": True}
                self.flows[approval_id] = flow
            if action == "status":
                return flow.get("receipt") or self.status(approval_id)
            if flow.get("receipt"):
                raise RpcError(-32043, "이미 처리된 승인 요청입니다.")
            row = self.hub.tool_policy.get(approval_id)
            if row["status"] != "pending":
                raise RpcError(-32043, "이미 처리됐거나 만료된 승인 요청입니다.")
            if action == "view":
                return {**row, "profile": self.hub.profile_id}
            if action not in {"approve", "deny"}:
                raise RpcError(-32602, "허용하지 않는 작업입니다.")
            self.hub.tool_policy.decide(approval_id, action == "approve", scope)
            # A short, read-only receipt lets a browser recover a lost response,
            # even when the agent already consumed the one-time grant. It grants
            # no further decisions and never asserts upstream execution success.
            receipt = {
                "approval_id": approval_id,
                "status": "approved" if action == "approve" else "denied",
                "scope": scope,
            }
            self.remember(approval_id, receipt)
            self.changed.set()
            return receipt

    def serve(self, server):
        try:
            while not server.stopping.is_set():
                server.handle_request()
                with self.lock:
                    if self.server is not server:
                        break
                    for key, flow in list(self.flows.items()):
                        if flow["expires"] <= time.time() or (
                            not flow.get("receipt") and self.status(key)["status"] != "pending"
                        ):
                            self.flows.pop(key, None)
                    pending = any(row["status"] == "pending" for row in self.hub.tool_policy.list())
                    alive = (
                        self.hub.tool_policy.window_live(self.window_owner)
                        and self.window_expires > time.time()
                    )
                    if not alive or (not self.browser_seen and not self.flows and not pending):
                        if self.server is server:
                            self.server = None
                        break
        finally:
            server.server_close()
            with self.lock:
                self.hub.tool_policy.window_release(server.window_owner)
                if self.server is server:
                    self.server = None

    def close(self):
        with self.lock:
            self.closed = True
            self.hub.tool_policy.window_release(self.window_owner)
            self.changed.set()
            self.flows.clear()
            server, thread = self.server, self.thread
            if server:
                server.stopping.set()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=4)
