"""Bounded stdio/Streamable HTTP clients and version negotiation."""

import http.client
import ipaddress
import json
import os
import queue
import re
import socket
import subprocess
import threading
import time
from urllib.parse import urlparse

from joongi_hub.errors import RpcError

MODERN = "2026-07-28"
VERSIONS = [MODERN, "2025-11-25", "2025-06-18"]
MAX_MESSAGE = 4 * 1024 * 1024
TIMEOUT = 20
SERVER_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
CLIENT_INFO = {"name": "joongi-hub", "version": "0.1.0"}


def validate_server(data):
    if not isinstance(data, dict):
        raise RpcError(-32602, "Server must be an object")
    allowed = {
        "id",
        "name",
        "transport",
        "url",
        "command",
        "args",
        "enabled",
        "protocol_version",
        "env",
        "headers",
        "auth",
        "policy",
    }
    if set(data) - allowed:
        raise RpcError(-32602, "Unknown server fields")
    if "auth" in data:
        from joongi_hub.auth import validate_auth

        validate_auth(data["auth"], data.get("transport"))
    if "policy" in data:
        from joongi_hub.tool_policy import validate_policy

        validate_policy(data["policy"])
    server_id = data.get("id", "")
    if not isinstance(server_id, str) or not SERVER_ID.fullmatch(server_id):
        raise RpcError(-32602, "Server id must be lowercase letters, digits and hyphens (1–48)")
    if data.get("transport") not in {"stdio", "http"}:
        raise RpcError(-32602, "Transport must be stdio or http")
    if data.get("protocol_version", "auto") not in ["auto", *VERSIONS]:
        raise RpcError(-32602, "Unsupported upstream protocol version")
    if type(data.get("enabled", True)) is not bool:
        raise RpcError(-32602, "enabled must be a boolean")
    if not isinstance(data.get("name", server_id), str):
        raise RpcError(-32602, "name must be text")
    for key in ("env", "headers"):
        mapping = data.get(key, {})
        if not isinstance(mapping, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v)
            for k, v in mapping.items()
        ):
            raise RpcError(-32602, key + " maps destination names to environment variable names")
        if any("\r" in key or "\n" in key for key in mapping):
            raise RpcError(-32602, "Invalid header/environment name")
    if data["transport"] == "stdio":
        if not isinstance(data.get("command"), str) or not data["command"].strip():
            raise RpcError(-32602, "A stdio command is required")
        args = data.get("args", [])
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise RpcError(-32602, "args must be an array of strings")
    else:
        validate_url(data.get("url", ""))
    return {
        **data,
        "name": data.get("name", server_id),
        "enabled": data.get("enabled", True),
        "protocol_version": data.get("protocol_version", "auto"),
    }


def validate_url(url, timeout=None):
    """Resolve and return only verified socket addresses for the actual connection."""
    if not isinstance(url, str):
        raise RpcError(-32602, "URL must be text")
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise RpcError(-32602, "Use an HTTP(S) URL without credentials or fragments")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise RpcError(-32602, "Invalid upstream port") from exc
    answers = queue.Queue(maxsize=1)

    def resolve():
        try:
            answers.put(socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM))
        except (OSError, ValueError) as exc:
            answers.put(exc)

    threading.Thread(target=resolve, daemon=True).start()
    try:
        addresses = answers.get(timeout=TIMEOUT if timeout is None else max(0.001, timeout))
    except queue.Empty as exc:
        raise RpcError(-32000, "Upstream hostname lookup timed out") from exc
    if isinstance(addresses, Exception) or not addresses:
        raise RpcError(-32602, "Upstream hostname cannot be resolved")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0].split("%")[0])
        ip = ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped else ip
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            raise RpcError(-32602, "Metadata/link-local and multicast destinations are blocked")
    return addresses


class StdioTransport:
    def __init__(self, config):
        environment = dict(os.environ)
        for key, variable in config.get("env", {}).items():
            if variable not in os.environ:
                raise RpcError(-32000, "Required upstream environment variable is missing")
            environment[key] = os.environ[variable]
        self.process = subprocess.Popen(
            [config["command"], *config.get("args", [])],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            shell=False,
        )
        self.messages = queue.Queue(maxsize=256)
        self.closed = False
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while not self.closed:
                line = self.process.stdout.readline(MAX_MESSAGE + 1)
                if not line or len(line) > MAX_MESSAGE:
                    break
                self.messages.put_nowait(json.loads(line))
        except (ValueError, OSError, queue.Full):
            pass
        finally:
            self.process.stdout.close()
            try:
                self.messages.put_nowait(None)
            except queue.Full:
                pass

    def exchange(self, message):
        if self.closed or self.process.poll() is not None:
            raise RpcError(-32000, "Upstream process has stopped")
        payload = (json.dumps(message) + "\n").encode()
        if len(payload) > MAX_MESSAGE:
            raise RpcError(-32602, "Upstream request exceeds 4 MiB")
        expired = threading.Event()

        def abort():
            expired.set()
            if self.process.poll() is None:
                try:
                    self.process.kill()
                except OSError:
                    pass
            try:
                self.messages.put_nowait(None)
            except queue.Full:
                pass

        deadline = time.monotonic() + TIMEOUT
        timer = threading.Timer(TIMEOUT, abort)
        timer.daemon = True
        timer.start()
        try:
            self.process.stdin.write(payload)
            self.process.stdin.flush()
            if "id" not in message:
                return None
            while True:
                response = self.messages.get(timeout=max(0.01, deadline - time.monotonic()))
                if response is None:
                    raise RpcError(
                        -32000,
                        "Upstream request timed out"
                        if expired.is_set()
                        else "Upstream closed its output",
                    )
                if not isinstance(response, dict):
                    raise RpcError(-32000, "Upstream response must be an object")
                if "method" in response:
                    if "id" in response:
                        rejected = {
                            "jsonrpc": "2.0",
                            "id": response["id"],
                            "error": {
                                "code": -32601,
                                "message": "Hub does not offer sampling or elicitation",
                            },
                        }
                        self.process.stdin.write((json.dumps(rejected) + "\n").encode())
                        self.process.stdin.flush()
                    continue
                if response.get("id") == message["id"]:
                    return response
                if time.monotonic() >= deadline:
                    raise queue.Empty
        except (queue.Empty, OSError, BrokenPipeError) as exc:
            self.close()
            raise RpcError(-32000, "Upstream request timed out or connection closed") from exc
        finally:
            timer.cancel()
            if expired.is_set():
                self.close()

    def close(self):
        if not self.closed:
            self.closed = True
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            self.process.stdin.close()
            # Closing a BufferedReader held by its readline thread can deadlock
            # if a descendant inherited stdout. The reader closes its own file.
            if not self.reader.is_alive():
                self.process.stdout.close()


class HttpTransport:
    def __init__(self, config, auth=None):
        self.config = config
        self.auth = auth
        self.session = None
        self.version = MODERN

    def exchange(self, message, raw=None, _retried=False):
        started = time.monotonic()
        deadline = started + TIMEOUT
        addresses = validate_url(self.config["url"], timeout=TIMEOUT)
        parsed = urlparse(self.config["url"])
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.version,
        }
        headers["Mcp-Method"] = message.get("method", "")
        if isinstance(message.get("params"), dict):
            identity = message["params"].get("taskId") or message["params"].get("name")
            if identity:
                headers["Mcp-Name"] = str(identity)
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        for header, variable in self.config.get("headers", {}).items():
            if variable not in os.environ:
                raise RpcError(-32000, "Required upstream environment variable is missing")
            headers[header] = os.environ[variable]
        if self.auth and raw is None:
            headers.update(
                self.auth.headers(
                    self.config,
                    allow_anonymous=message["method"] in {"initialize", "server/discover"},
                )
            )
        if raw is not None:
            headers = raw.get("headers", {"Accept": "application/json"})
        reflected_headers = [
            value
            for key, value in headers.items()
            if key.lower() == "authorization"
            or key in self.config.get("headers", {})
            or key == self.config.get("auth", {}).get("header")
        ]

        def check_response(value):
            from joongi_hub.redaction import reject_secret_reflection

            reject_secret_reflection(value, reflected_headers)
            return value

        payload = raw.get("body") if raw is not None else json.dumps(message).encode()
        if payload is not None and len(payload) > MAX_MESSAGE:
            raise RpcError(-32602, "Upstream request exceeds 4 MiB")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RpcError(-32000, "Upstream request timed out")
        factory = (
            http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        )
        # Keep the original hostname for Host, TLS SNI and certificate verification.
        connection = factory(parsed.hostname, parsed.port, timeout=remaining)
        sockets = []
        expired = threading.Event()

        def abort():
            expired.set()
            for sock in list(sockets):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

        def connect_verified(address, timeout, source_address=None):
            # HTTPConnection normally resolves again. Connect directly to the
            # exact checked sockaddr, preventing a DNS rebind between checks.
            last_error = None
            for family, kind, protocol, _, sockaddr in addresses:
                if expired.is_set() or time.monotonic() >= deadline:
                    raise TimeoutError("Upstream connect timed out")
                sock = socket.socket(family, kind, protocol)
                sockets.append(sock)
                try:
                    sock.settimeout(max(0.001, deadline - time.monotonic()))
                    if source_address:
                        sock.bind(source_address)
                    sock.connect(sockaddr)
                    if parsed.scheme == "https":
                        # TLS detaches the original socket object's fd. Keep a
                        # duplicate so deadline shutdown also interrupts the
                        # handshake and request body before connection.sock
                        # receives the wrapped socket.
                        sockets.append(sock.dup())
                    return sock
                except OSError as exc:
                    last_error = exc
                    sock.close()
            raise last_error or OSError("No verified upstream address")

        connection._create_connection = connect_verified
        timer = threading.Timer(remaining, abort)
        timer.daemon = True
        timer.start()
        response = None
        try:
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            connection.request(
                raw.get("method", "GET") if raw else "POST", path, body=payload, headers=headers
            )
            # HTTPS wraps the raw socket. Track the wrapper as well so deadline
            # shutdown interrupts buffered TLS response reads.
            if connection.sock is not None:
                sockets.append(connection.sock)
            response = connection.getresponse()
            self.session = response.headers.get("Mcp-Session-Id", self.session)
            if raw is None and response.status in {401, 403} and self.auth:
                self.auth.challenge(self.config, response.headers.get("WWW-Authenticate", ""))
                if (
                    response.status == 401
                    and not _retried
                    and self.auth.refresh_rejected(self.config, headers.get("Authorization"))
                ):
                    return self.exchange(message, _retried=True)
                raise RpcError(
                    -32040,
                    "MCP 인증이 필요합니다. 연결 설정에서 로그인하세요.",
                    {"server": self.config.get("id"), "status": response.status},
                )
            if 300 <= response.status < 400:
                raise RpcError(
                    -32000, "Upstream redirects are not followed", {"status": response.status}
                )
            if raw is None and (response.status == 202 or "id" not in message):
                if response.status >= 400:
                    raise RpcError(
                        -32000, "Upstream HTTP request failed", {"status": response.status}
                    )
                return None
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > MAX_MESSAGE:
                raise RpcError(-32000, "Upstream response exceeds 4 MiB")
            if (
                raw is None
                and "text/event-stream" in response.headers.get("Content-Type", "")
                and response.status < 400
            ):
                size = 0
                data = []
                while not expired.is_set():
                    line = response.readline(MAX_MESSAGE + 1)
                    size += len(line)
                    if not line or size > MAX_MESSAGE:
                        break
                    if line.startswith(b"data:"):
                        data.append(line[5:].strip())
                    elif not line.strip() and data:
                        value = json.loads(b"\n".join(data))
                        data = []
                        if isinstance(value, dict) and value.get("id") == message["id"]:
                            return check_response(value)
                raise RpcError(-32000, "Upstream stream ended without a response")
            body = response.read(MAX_MESSAGE + 1)
            if expired.is_set():
                raise RpcError(-32000, "Upstream request timed out")
            if len(body) > MAX_MESSAGE:
                raise RpcError(-32000, "Upstream response exceeds 4 MiB")
            if raw is not None:
                return {"status": response.status, "headers": dict(response.headers), "body": body}
            value = json.loads(body)
            if response.status >= 400 and not (isinstance(value, dict) and "error" in value):
                raise RpcError(-32000, "Upstream HTTP request failed", {"status": response.status})
            return check_response(value)
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise RpcError(
                -32000,
                "Upstream request timed out"
                if expired.is_set()
                else "Upstream connection failed or returned invalid JSON",
            ) from exc
        finally:
            timer.cancel()
            if response is not None:
                response.close()
            connection.close()
            for sock in sockets:
                sock.close()

    def close(self):
        pass


class Upstream:
    def __init__(self, config, auth=None):
        self.config = config
        self.auth = auth
        self.transport = None
        self.version = None
        self.capabilities = {}
        self.tools = []
        self.skill_entries = []
        self.lock = threading.RLock()
        self.sequence = 0

    def _send(self, method, params=None, notification=False):
        self.sequence += 1
        params = dict(params or {})
        if self.version == MODERN:
            params["_meta"] = {
                **params.get("_meta", {}),
                "io.modelcontextprotocol/protocolVersion": MODERN,
                "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
                "io.modelcontextprotocol/clientCapabilities": {
                    "elicitation": {"form": {}, "url": {}},
                    "extensions": {
                        "io.modelcontextprotocol/tasks": {},
                        "io.modelcontextprotocol/skills": {},
                        "io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]},
                    },
                },
            }
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            message["id"] = self.sequence
        before = (
            self.auth.secret_values(self.config)
            if self.auth and hasattr(self.auth, "secret_values")
            else []
        )
        response = self.transport.exchange(message)
        if notification:
            return {}
        if self.auth and hasattr(self.auth, "secret_values"):
            from joongi_hub.redaction import reject_secret_reflection

            reject_secret_reflection(response, before + self.auth.secret_values(self.config))
        if not isinstance(response, dict) or response.get("id") != message["id"]:
            raise RpcError(-32000, "Invalid upstream response id")
        if "error" in response:
            error = response["error"]
            raise RpcError(
                error.get("code", -32000), error.get("message", "Upstream error"), error.get("data")
            )
        if not isinstance(response.get("result"), dict):
            raise RpcError(-32000, "Upstream result must be an object")
        return response["result"]

    def connect(self):
        with self.lock:
            if self.transport and self.version:
                return
            factory = StdioTransport if self.config["transport"] == "stdio" else HttpTransport
            self.transport = (
                factory(self.config, auth=self.auth)
                if factory is HttpTransport
                else factory(self.config)
            )
            requested = self.config.get("protocol_version", "auto")
            self.version = MODERN if requested == "auto" else requested
            try:
                if self.version == MODERN:
                    try:
                        result = self._send("server/discover")
                    except RpcError as exc:
                        if exc.code == -32022:
                            supported = (exc.data or {}).get("supported", [])
                            common = next((v for v in VERSIONS if v in supported), None)
                            if not common:
                                raise
                            self.version = common
                            if common == MODERN:
                                result = self._send("server/discover")
                        elif requested == "auto" and exc.code in {-32601, -32600, -32000}:
                            self.version = "2025-11-25"
                        else:
                            raise
                    if self.version == MODERN:
                        self.capabilities = result.get("capabilities", {})
                if self.version != MODERN:
                    if isinstance(self.transport, HttpTransport):
                        self.transport.version = self.version
                    result = self._send(
                        "initialize",
                        {
                            "protocolVersion": self.version,
                            "clientInfo": CLIENT_INFO,
                            "capabilities": {
                                "extensions": {
                                    "io.modelcontextprotocol/ui": {
                                        "mimeTypes": ["text/html;profile=mcp-app"]
                                    }
                                },
                                "tasks": {"requests": {"tools": {"call": {}}}},
                            },
                        },
                    )
                    if result.get("protocolVersion") not in VERSIONS[1:]:
                        raise RpcError(-32000, "No compatible legacy version")
                    self.version = result["protocolVersion"]
                    if isinstance(self.transport, HttpTransport):
                        self.transport.version = self.version
                    self.capabilities = result.get("capabilities", {})
                    self._send("notifications/initialized", notification=True)
                self.tools = (
                    self._list("tools/list", "tools") if "tools" in self.capabilities else []
                )
                if "io.modelcontextprotocol/skills" in self.capabilities.get("extensions", {}):
                    self.skill_entries = self._list("skills/list", "skills")
            except Exception:
                self.close()
                raise

    def _list(self, method, key):
        items = []
        cursor = None
        seen = set()
        for _ in range(100):
            result = self._send(method, {"cursor": cursor} if cursor else {})
            items.extend(result.get(key, []))
            cursor = result.get("nextCursor")
            if not cursor:
                return items
            if cursor in seen:
                break
            seen.add(cursor)
        raise RpcError(-32000, "Upstream pagination exceeded limit")

    def request(self, method, params=None):
        with self.lock:
            self.connect()
            try:
                return self._send(method, params)
            except (OSError, ValueError) as exc:
                self.close()
                raise RpcError(-32000, "Upstream connection failed") from exc

    def list_items(self, method, key):
        with self.lock:
            self.connect()
            return self._list(method, key)

    def refresh(self):
        with self.lock:
            if (
                self.transport
                and hasattr(self.transport, "process")
                and self.transport.process.poll() is not None
            ):
                self.close()
            self.connect()
            if "tools" in self.capabilities:
                self.tools = self._list("tools/list", "tools")
            if "io.modelcontextprotocol/skills" in self.capabilities.get("extensions", {}):
                self.skill_entries = self._list("skills/list", "skills")

    def close(self):
        if self.transport:
            self.transport.close()
        self.transport = None
        self.version = None
