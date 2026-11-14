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
            or self.path != "/decision"
            or self.headers.get("Origin") != origin
            or self.headers.get("Sec-Fetch-Site") not in {None, "same-origin"}
            or self.headers.get("Content-Type") != "application/json"
        ):
            self.send(403, {"error": "Request rejected"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024 or self.headers.get("Transfer-Encoding"):
                raise ValueError
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict) or set(body) != {"approval_id", "action"}:
                raise ValueError
            result = self.server.controller.decision(
                body["approval_id"], self.headers.get("Authorization", ""), body["action"]
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

    def status(self, approval_id):
        result = self.hub.tool_policy.get(approval_id)
        # Status is deliberately not a review/approval capability.
        return {
            key: value
            for key, value in result.items()
            if key in {"approval_id", "status", "expires_at", "server", "tool"}
        }

    def request(self, approval_id):
        with self.lock:
            if self.closed:
                raise RpcError(-32043, "Hub가 종료 중입니다.")
            result = self.status(approval_id)
            if result["status"] != "pending":
                return result
            flow = self.flows.get(approval_id)
            if flow:
                return {**result, "browser_opened": flow["opened"]}
            if self.server is None:
                self.server = ApprovalServer(self)
                self.thread = threading.Thread(target=self.serve, args=(self.server,), daemon=True)
                self.thread.start()
            secret = secrets.token_urlsafe(32)
            flow = {"secret": secret, "expires": result["expires_at"], "opened": False}
            self.flows[approval_id] = flow
            url = (
                f"http://127.0.0.1:{self.server.server_port}/"
                f"#approval_id={approval_id}&session={secret}"
            )
        # Never return/log this URL, including in errors. Only the OS browser gets it.
        try:
            opened = open_browser(url)
        except Exception:
            opened = False
        with self.lock:
            flow["opened"] = opened
            if not opened:
                self.flows.pop(approval_id, None)
        return {
            **result,
            "browser_opened": opened,
            "next_tool": "hub_approval_status",
            "instructions": "사용자가 로컬 브라우저에서 이 호출을 검토하도록 안내하세요. "
            "승인 후 원래 요청을 그대로 재시도하세요. "
            "창이 열리지 않으면 로컬 터미널의 joongi-hub open으로 관리 화면을 여세요.",
        }

    def decision(self, approval_id, authorization, action):
        with self.lock:
            flow = self.flows.get(approval_id) if isinstance(approval_id, str) else None
            if (
                not flow
                or flow["expires"] <= time.time()
                or not secrets.compare_digest(authorization, "Bearer " + flow["secret"])
            ):
                raise RpcError(-32043, "유효하지 않은 승인 세션입니다.")
            row = self.hub.tool_policy.get(approval_id)
            if row["status"] != "pending":
                raise RpcError(-32043, "이미 처리됐거나 만료된 승인 요청입니다.")
            if action == "view":
                return {**row, "profile": self.hub.profile_id}
            if action not in {"approve", "deny"}:
                raise RpcError(-32602, "허용하지 않는 작업입니다.")
            self.hub.tool_policy.decide(approval_id, action == "approve")
            self.flows.pop(approval_id, None)
            return self.status(approval_id)

    def serve(self, server):
        try:
            while not server.stopping.is_set():
                server.handle_request()
                with self.lock:
                    for key, flow in list(self.flows.items()):
                        if (
                            flow["expires"] <= time.time()
                            or self.status(key)["status"] != "pending"
                        ):
                            self.flows.pop(key, None)
                    if not self.flows:
                        if self.server is server:
                            self.server = None
                        break
        finally:
            server.server_close()
            with self.lock:
                if self.server is server:
                    self.server = None

    def close(self):
        with self.lock:
            self.closed = True
            self.flows.clear()
            server, thread = self.server, self.thread
            if server:
                server.stopping.set()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=4)
