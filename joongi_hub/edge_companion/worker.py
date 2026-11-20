"""Prepared Windows-only stdio gate for the official Playwright extension.

This is trusted Windows user code, NOT an OS sandbox. Never kills Edge.
"""

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit

MAX_LINE = 4 * 1024**2
TOOLS = {
    "browser_navigate",
    "browser_snapshot",
    "browser_take_screenshot",
    "browser_click",
    "browser_type",
    "browser_press_key",
    "browser_tabs",
    "browser_wait_for",
}
CONNECT = "browser_extension_connect"
STATUS = "browser_extension_status"
DISCONNECT = "browser_extension_disconnect"
URL_PROBE = "async page => page.context().pages().map(p => p.url())"


def text_result(state, **extra):
    return {"content": [{"type": "text", "text": json.dumps({"state": state, **extra})}]}


def tab_urls(result):
    """Read trusted JSON from the fixed internal probe, never markdown tab titles."""
    texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
    if not texts or not texts[0].startswith("### Result\n"):
        return []
    try:
        value, _ = json.JSONDecoder().raw_decode(texts[0][len("### Result\n") :])
        return value if isinstance(value, list) and all(isinstance(u, str) for u in value) else []
    except ValueError:
        return []


def allowed_url(url, origins):
    try:
        p = urlsplit(url)
        return (
            isinstance(url, str)
            and len(url) <= 4096
            and p.scheme == "https"
            and p.username is None
            and p.password is None
            and p.port in (None, 443)
            and "https://" + (p.hostname or "") in origins
        )
    except (ValueError, TypeError):
        return False


def check(name, args, origins):
    if name not in TOOLS or not isinstance(args, dict) or len(json.dumps(args)) > 16384:
        raise ValueError("Tool or arguments not enabled")
    if "filename" in args or args.get("fullPage"):
        raise ValueError("Only inline viewport output is enabled")
    if name == "browser_navigate" and not allowed_url(args.get("url"), origins):
        raise ValueError("Owner must enable this exact HTTPS origin first")
    if name == "browser_wait_for" and (
        type(args.get("time", 0)) not in (int, float) or not 0 <= args.get("time", 0) <= 5
    ):
        raise ValueError("Wait at most five seconds")
    if name == "browser_tabs" and args.get("action") not in {"list", "new", "close", "select"}:
        raise ValueError("Unknown tab operation")
    if name == "browser_tabs":
        if "isolatedContext" in args:
            raise ValueError("Only the extension-owned default context is enabled")
        if "url" in args and not allowed_url(args["url"], origins):
            raise ValueError("Owner must enable this exact HTTPS origin first")
    if name == "browser_take_screenshot":
        args.update(type="jpeg", scale="css")


class Companion:
    def __init__(self, root):
        self.root = root
        self.settings = json.loads((root / "settings.json").read_text(encoding="utf-8"))
        self.state = "disconnected"
        self.detail = "not_connected"
        self.process = None
        self.pending = {}
        self.counter = 0
        self.closed = False
        self.temporary = None

    def stop(self):
        process, self.process = self.process, None
        if process and process.poll() is None:
            # No process-tree termination: Edge may be the user's existing browser.
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if self.temporary:
            self.temporary.cleanup()
            self.temporary = None

    def start(self):
        if not extension_ready(self.settings["profile"]):
            self.detail = "extension_setup_required"
            raise ValueError(
                "Install or update official Playwright extension (0.5+) in this profile"
            )
        if not edge_running():
            self.detail = "open_edge_first"
            raise ValueError("Open Edge yourself before connecting")
        self.temporary = tempfile.TemporaryDirectory(prefix="joongi-edge-session-")
        directory = Path(self.temporary.name)
        executable = next(
            (
                Path(os.environ[k]) / "Microsoft/Edge/Application/msedge.exe"
                for k in ("ProgramFiles(x86)", "ProgramFiles")
                if k in os.environ
                and (Path(os.environ[k]) / "Microsoft/Edge/Application/msedge.exe").is_file()
            ),
            None,
        )
        if executable is None:
            raise ValueError("Microsoft Edge is not installed")
        config = {
            "extension": True,
            "background": True,
            "tabGroup": True,
            "sessionName": "Joongi Hub",
            "codegen": "none",
            "webmcp": False,
            "ignoreRoots": True,
            "browser": {
                "browserName": "chromium",
                "launchOptions": {"executablePath": str(executable)},
            },
            "capabilities": ["core"],
            "outputDir": str(directory),
            "outputMaxSize": 1048576,
            "imageResponses": "allow",
            "timeouts": {"action": 4000, "navigation": 10000},
            "redactUrlParams": [
                "access_token",
                "id_token",
                "refresh_token",
                "code",
                "token",
                "key",
            ],
        }
        config_path = directory / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        env = {
            k: os.environ[k]
            for k in (
                "SystemRoot",
                "WINDIR",
                "USERPROFILE",
                "LOCALAPPDATA",
                "APPDATA",
                "ProgramFiles",
                "ProgramFiles(x86)",
            )
            if k in os.environ
        }
        env.update(
            TEMP=str(directory),
            TMP=str(directory),
            HOME=str(directory),
            PATH=str(self.root) + ";" + os.environ["SystemRoot"] + "\\System32",
        )
        self.process = subprocess.Popen(
            [
                str(self.root / "node.exe"),
                "--max-old-space-size=256",
                str(self.root / "node_modules/@playwright/mcp/cli.js"),
                "--config",
                str(config_path),
                "--browser",
                "msedge",
                "--profile-dir-name",
                self.settings["profile"],
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=directory,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self.reader, args=(self.process,), daemon=True).start()
        result = self.exchange(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "Joongi Hub", "version": "0.1.0"},
            },
            8,
        )
        if not result:
            raise ValueError("Official MCP initialization failed")
        self.process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        self.process.stdin.flush()

    def reader(self, process):
        try:
            while True:
                line = process.stdout.readline(MAX_LINE + 1)
                if not line or len(line) > MAX_LINE:
                    return
                value = json.loads(line)
                waiter = self.pending.get(value.get("id"))
                if waiter:
                    waiter.put_nowait(value)
        except (OSError, ValueError, queue.Full):
            return

    def exchange(self, method, params, timeout=15):
        self.counter += 1
        ident = self.counter
        waiter = queue.Queue(maxsize=1)
        self.pending[ident] = waiter
        try:
            self.process.stdin.write(
                (
                    json.dumps({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
                    + "\n"
                ).encode()
            )
            self.process.stdin.flush()
            reply = waiter.get(timeout=timeout)
            if "error" in reply or reply.get("result", {}).get("isError"):
                raise ValueError("Browser operation failed; inspect the owned tab before retrying")
            return reply["result"]
        except (queue.Empty, OSError, AttributeError) as exc:
            raise ValueError(
                "Browser disconnected or timed out; do not blindly repeat an action"
            ) from exc
        finally:
            self.pending.pop(ident, None)

    def pair(self):
        try:
            self.start()
            if self.closed:
                self.stop()
                return
            result = self.probe(120)
            if tab_urls(result) != ["about:blank"]:
                self.detail = "select_no_existing_tabs"
                raise ValueError("Select no existing tabs; reconnect with a new blank tab")
            if self.closed:
                self.stop()
            else:
                self.state = "ready"
                self.detail = "new_tab_ready"
        except (ValueError, OSError, KeyError):
            self.stop()
            self.state = "connection_failed"

    def call(self, name, args):
        if name in {CONNECT, STATUS, DISCONNECT}:
            if args:
                raise ValueError("This tool takes no arguments")
            if name == DISCONNECT:
                if self.state == "awaiting_browser_approval":
                    # The pair thread owns startup/shutdown during this bounded operation.
                    raise ValueError("Wait for pairing to finish or disconnect the Hub server")
                self.stop()
                self.state = "disconnected"
            if name == CONNECT and self.state in {"disconnected", "connection_failed"}:
                self.state = "awaiting_browser_approval"
                self.detail = "approve_without_selecting_tabs"
                threading.Thread(target=self.pair, daemon=True).start()
            return text_result(
                self.state,
                detail=self.detail,
                executed=False,
                instructions=(
                    "Approve in Edge, select NO existing tabs. Poll browser_extension_status. "
                    "When ready, issue the desired action once. "
                    "Failed actions may have side effects; inspect before retrying."
                ),
            )
        check(name, args, self.settings["origins"])
        if self.state != "ready":
            return text_result(
                self.state,
                executed=False,
                instructions="Call browser_extension_connect, then poll status. "
                "Original action was not executed.",
            )
        try:
            # Defense in depth, not atomic navigation enforcement or a subresource firewall.
            tabs = self.probe()
            urls = tab_urls(tabs)
            if not urls or any(
                u != "about:blank" and not allowed_url(u, self.settings["origins"]) for u in urls
            ):
                raise ValueError("An owned tab left the enabled sites. Disconnect and reconnect.")
            return self.exchange("tools/call", {"name": name, "arguments": args})
        except ValueError:
            self.state = "connection_failed"
            self.stop()
            raise

    def probe(self, timeout=8):
        # Fixed first-party source only. Never exposed as a tool, interpolated or accepted
        # from an agent. Read trusted Playwright page URLs without interpreting page titles.
        return self.exchange(
            "tools/call",
            {"name": "browser_run_code_unsafe", "arguments": {"code": URL_PROBE}},
            timeout,
        )


def edge_running():
    # Only process name, no browser command lines, profile contents or account data.
    result = subprocess.run(
        [
            os.environ["SystemRoot"] + "\\System32\\tasklist.exe",
            "/FI",
            "IMAGENAME eq msedge.exe",
            "/FO",
            "CSV",
            "/NH",
        ],
        capture_output=True,
        timeout=5,
    )
    return b'"msedge.exe"' in result.stdout.lower()


def extension_ready(profile):
    # Only the public extension manifest version; never browser state or cookies.
    root = Path(os.environ["LOCALAPPDATA"]) / "Microsoft/Edge/User Data" / profile / "Extensions"
    root /= "mmlmfjhmonkocbjadbfplnigmagldckm"
    for manifest in root.glob("*/manifest.json"):
        try:
            if manifest.stat().st_size > 65536:
                continue
            version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
            if tuple(int(p) for p in version.split(".")) >= (0, 5, 0):
                return True
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return False


def main():
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    companion = Companion(Path(sys.argv[1]))
    # Schema discovery must not open Edge or need an extension approval.
    schemas = json.loads((companion.root / "tools.json").read_text(encoding="utf-8"))
    for name in (CONNECT, STATUS, DISCONNECT):
        schemas.append(
            {
                "name": name,
                "description": (
                    "Start manual Edge pairing; select no existing tabs. "
                    "Returns immediately; poll status."
                    if name == CONNECT
                    else (
                        "Poll connection state; no account or page data."
                        if name == STATUS
                        else "Disconnect agent session. Does not terminate Edge."
                    )
                ),
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            }
        )
    try:
        while True:
            line = sys.stdin.buffer.readline(65537)
            if not line or len(line) > 65536:
                break
            request = json.loads(line)
            if "id" not in request:
                continue
            ident = request["id"]
            try:
                method = request["method"]
                if method == "initialize":
                    result = {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "joongi-personal-edge", "version": "0.1.0"},
                    }
                elif method == "tools/list":
                    result = {"tools": schemas}
                elif method == "ping":
                    result = {}
                elif method == "tools/call":
                    params = request["params"]
                    result = companion.call(params["name"], params.get("arguments", {}))
                else:
                    raise ValueError("Only the reduced browser tools are enabled")
                reply = {"jsonrpc": "2.0", "id": ident, "result": result}
            except (ValueError, KeyError, TypeError, OSError):
                reply = {
                    "jsonrpc": "2.0",
                    "id": ident,
                    "error": {
                        "code": -32000,
                        "message": "Personal Edge request refused or connection lost. "
                        "Check owned tabs before repeating side effects.",
                    },
                }
            print(json.dumps(reply), flush=True)
    finally:
        companion.closed = True
        companion.stop()


if __name__ == "__main__":
    main()
