"""On-demand owner settings: browser-only capabilities, independent of stdio."""

import secrets
import threading
import time
from urllib.parse import quote

from joongi_hub.agent_approval import open_browser
from joongi_hub.connections import running
from joongi_hub.errors import RpcError
from joongi_hub.local_auth import ui_url
from joongi_hub.server import HubServer


class AgentPanels:
    def __init__(self, hub):
        self.hub = hub
        self.lock = threading.RLock()
        self.server = None
        self.thread = None
        self.pages = {}
        self.closed = False
        self.idle_seconds = 120
        self.close_seconds = 5
        self.expires = 0
        self.base_callback = None
        self.last_callback = None

    def open(self, profile="global", mode="temporary"):
        if mode not in {"temporary", "persistent"}:
            raise RpcError(-32602, "설정 화면 모드를 확인하세요.")
        with self.lock:
            if self.closed:
                raise RpcError(-32043, "Hub가 종료 중입니다.")
        persistent = running(self.hub.state_dir)
        if mode == "persistent" and not persistent:
            from joongi_hub.lifecycle import manage

            persistent = manage("start", self.hub.state_dir, self.hub.common_skills.directory)
        if persistent:
            url = ui_url(persistent["url"], self.hub.state_dir)
            url += "&profile=" + quote(profile, safe="") + "&view=settings"
            try:
                opened = open_browser(url)
            except Exception:
                opened = False
            return {
                "mode": "persistent",
                "browser_opened": bool(opened),
                "closes_with_window": False,
                "instructions": "상시 웹 UI입니다. 창을 닫아도 유지됩니다. "
                "종료하려면 로컬 터미널에서 joongi-hub stop을 사용하세요.",
            }
        with self.lock:
            if len(self.pages) >= 32:
                raise RpcError(-32043, "설정 창이 너무 많습니다. 기존 창을 먼저 닫으세요.")
            if self.server is None:
                if self.hub.auth.callback_url != self.last_callback:
                    self.base_callback = self.hub.auth.callback_url
                previous = self.base_callback
                server = HubServer(("127.0.0.1", 0), self.hub, temporary=self)
                self.server = server
                self.last_callback = self.hub.auth.callback_url
                self.expires = time.monotonic() + 8 * 3600
                self.thread = threading.Thread(
                    target=self.serve, args=(server, previous), daemon=True
                )
                self.thread.start()
                threading.Thread(target=self.watch, args=(server,), daemon=True).start()
            server = self.server
            page = secrets.token_urlsafe(32)
            self.pages[page] = time.monotonic() + self.idle_seconds
            url = (
                f"http://127.0.0.1:{server.server_port}/#session={server.token}"
                f"&panel_page={page}&profile={quote(profile, safe='')}&view=settings"
            )
        try:
            opened = open_browser(url)
        except Exception:
            opened = False
        if not opened:
            with self.lock:
                self.pages.pop(page, None)
        return {
            "mode": "temporary",
            "browser_opened": bool(opened),
            "closes_with_window": True,
            "instructions": "로컬 브라우저에서 설정하세요. "
            "창을 닫으면 약 5초 뒤 임시 웹만 종료됩니다. stdio 연결은 유지됩니다. "
            "브라우저 종료 신호가 없으면 마지막 화면 연결 확인 후 120초 안에 정리됩니다.",
        }

    def touch(self, page, close=False):
        if (
            not isinstance(page, str)
            or not 16 <= len(page) <= 64
            or not all(c.isascii() and (c.isalnum() or c in "-_") for c in page)
        ):
            raise RpcError(-32602, "설정 창 식별자를 확인하세요.")
        with self.lock:
            now = time.monotonic()
            self.pages = {key: end for key, end in self.pages.items() if end > now}
            if self.closed or self.server is None or now >= self.expires:
                raise RpcError(-32043, "임시 설정 화면이 종료됐습니다. 다시 여세요.")
            if page not in self.pages and (close or len(self.pages) >= 32):
                raise RpcError(-32602, "설정 창을 다시 여세요.")
            self.pages[page] = now + (self.close_seconds if close else self.idle_seconds)

    def watch(self, server):
        while True:
            time.sleep(0.2)
            with self.lock:
                now = time.monotonic()
                self.pages = {key: end for key, end in self.pages.items() if end > now}
                if self.server is not server:
                    return
                if self.closed or not self.pages or now >= self.expires:
                    # Detach before shutdown so a new open cannot join a dying listener.
                    self.server = None
                    self.pages.clear()
                    break
        server.shutdown()

    def serve(self, server, previous):
        try:
            server.serve_forever(poll_interval=0.2)
        finally:
            server.server_close()
            callback = f"http://127.0.0.1:{server.server_port}/oauth/callback"
            # Cancel only this window's OAuth callbacks; agent-login listeners are separate.
            for hub in [self.hub, *list(self.hub.profile_hubs.values())]:
                with hub.auth.lock:
                    for key, row in list(hub.auth.pending.items()):
                        if row.get("redirect") == callback:
                            hub.auth.pending.pop(key, None)
                    if hub.auth.callback_url == callback:
                        hub.auth.callback_url = previous
            with self.lock:
                if self.server is server:
                    self.server = None
                    self.pages.clear()

    def close(self):
        with self.lock:
            self.closed = True
            server, thread = self.server, self.thread
            self.server = None
            self.pages.clear()
        if server:
            server.shutdown()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=3)
