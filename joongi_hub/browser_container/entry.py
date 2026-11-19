"""Container-only relay and reduced official Playwright MCP tool surface."""

import glob
import json
import os
import select
import socket
import socketserver
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

TOOLS = {
    "browser_navigate",
    "browser_navigate_back",
    "browser_snapshot",
    "browser_take_screenshot",
    "browser_click",
    "browser_type",
    "browser_press_key",
    "browser_tabs",
    "browser_close",
    "browser_wait_for",
    "browser_mouse_click_xy",
    "browser_mouse_move_xy",
    "browser_mouse_wheel",
}
ORIGINS = set(json.loads(os.environ["JOONGI_BROWSER_ORIGINS"]))


def check(name, args):
    if name not in TOOLS or not isinstance(args, dict):
        raise ValueError("This browser tool is not enabled")
    if "filename" in args or args.get("fullPage"):
        raise ValueError("Only bounded viewport screenshots and inline snapshots are enabled")
    if name == "browser_navigate":
        url = args.get("url", "")
        parsed = urlsplit(url)
        if (
            len(url) > 4096
            or parsed.username is not None
            or parsed.password is not None
            or parsed.scheme != "https"
            or parsed.port not in (None, 443)
            or "https://" + (parsed.hostname or "") not in ORIGINS
        ):
            raise ValueError("Enable this HTTPS origin in the owner browser configuration first")
    if len(json.dumps(args)) > 16384:
        raise ValueError("Browser arguments exceed the limit")
    for key, maximum in (("x", 1279), ("y", 799)):
        if key in args and (type(args[key]) not in (int, float) or not 0 <= args[key] <= maximum):
            raise ValueError("Coordinates must stay inside the viewport")
    if name == "browser_wait_for" and args.get("time", 0) > 10:
        raise ValueError("Wait at most 10 seconds per request")


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as remote:
            remote.connect("/egress.sock")
            self.request.settimeout(5)
            remote.settimeout(5)
            try:
                while True:
                    readable, _, _ = select.select([self.request, remote], [], [], 5)
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        (remote if source is self.request else self.request).sendall(data)
            except OSError:
                pass


class RelayServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    request_queue_size = 16


def main():
    relay = RelayServer(("127.0.0.1", 3128), Relay)
    threading.Thread(target=relay.serve_forever, daemon=True).start()
    Path("/tmp/workspace").mkdir()
    executable = glob.glob("/ms-playwright/chromium-*/chrome-linux*/chrome")
    if len(executable) != 1:
        raise RuntimeError("Pinned browser executable not found")
    headed = os.environ.get("JOONGI_BROWSER_DISPLAY") == "wayland"
    config = {
        "browser": {
            "browserName": "chromium",
            "isolated": True,
            "launchOptions": {
                "executablePath": executable[0],
                "headless": not headed,
                "chromiumSandbox": True,
                "args": ["--proxy-bypass-list=<-loopback>"]
                + (["--ozone-platform=wayland"] if headed else []),
                "proxy": {"server": "http://127.0.0.1:3128", "bypass": "<-loopback>"},
            },
            "contextOptions": {
                "viewport": {"width": 1280, "height": 800},
                "acceptDownloads": False,
                "serviceWorkers": "block",
            },
        },
        "capabilities": ["core", "vision"],
        "webmcp": False,
        "outputDir": "/tmp/output",
        "outputMaxSize": 8 * 1024**2,
        "imageResponses": "allow",
        "timeouts": {"action": 8000, "navigation": 15000},
    }
    Path("/tmp/browser-config.json").write_text(json.dumps(config))
    process = subprocess.Popen(
        [
            "node",
            "/app/node_modules/@playwright/mcp/cli.js",
            "--config",
            "/tmp/browser-config.json",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        cwd="/tmp/workspace",
        env={
            key: os.environ[key]
            for key in (
                "PATH",
                "HOME",
                "TMPDIR",
                "LANG",
                "WAYLAND_DISPLAY",
                "XDG_RUNTIME_DIR",
            )
            if key in os.environ
        },
        text=True,
        bufsize=1,
    )
    output_lock = threading.Lock()
    listings = set()

    def send(value):
        with output_lock:
            print(json.dumps(value), flush=True)

    def output():
        for line in process.stdout:
            if len(line) > 4 * 1024**2:
                process.kill()
                return
            value = json.loads(line)
            if value.get("id") in listings:
                listings.discard(value["id"])
                if "result" in value:
                    value["result"]["tools"] = [
                        t for t in value["result"].get("tools", []) if t["name"] in TOOLS
                    ]
                    for tool in value["result"]["tools"]:
                        properties = tool["inputSchema"].get("properties", {})
                        properties.pop("filename", None)
                        if tool["name"] == "browser_take_screenshot":
                            properties.pop("fullPage", None)
                            properties["type"] = {"type": "string", "enum": ["jpeg"]}
                            properties["scale"] = {"type": "string", "enum": ["css"]}
            send(value)

    threading.Thread(target=output, daemon=True).start()
    try:
        for line in sys.stdin:
            if len(line) > 65536:
                break
            message = json.loads(line)
            try:
                if message.get("method") == "tools/call":
                    check(message["params"]["name"], message["params"].get("arguments", {}))
                    if message["params"]["name"] == "browser_take_screenshot":
                        message["params"].setdefault("arguments", {}).update(
                            type="jpeg", scale="css"
                        )
                elif message.get("method") == "tools/list":
                    listings.add(message["id"])
                elif (
                    message.get("method")
                    not in {
                        "initialize",
                        "notifications/initialized",
                        "ping",
                        "notifications/cancelled",
                        "notifications/roots/list_changed",
                        "server/discover",
                    }
                    and "method" in message
                ):
                    send(
                        {
                            "jsonrpc": "2.0",
                            "id": message.get("id"),
                            "error": {
                                "code": -32601,
                                "message": "Only browser tools are enabled",
                            },
                        }
                    )
                    continue
                process.stdin.write(json.dumps(message) + "\n")
                process.stdin.flush()
            except (ValueError, TypeError, KeyError) as exc:
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "error": {
                            "code": -32602,
                            "message": str(exc),
                        },
                    }
                )
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        relay.shutdown()


if __name__ == "__main__":
    main()
