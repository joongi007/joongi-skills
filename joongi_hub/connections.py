"""Explicit client transports, scoped settings and shared agent configuration."""

import hashlib
import http.client
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from joongi_hub.errors import RpcError
from joongi_hub.storage import atomic_json

MODES = {"stdio", "hybrid", "http"}
DEFAULT = {"mode": "stdio", "url": "http://127.0.0.1:8765", "fallback": "stdio"}


def base_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise RpcError(-32602, "Hub 주소를 확인하세요.")
    try:
        p = urlsplit(value)
        if (
            p.scheme != "http"
            or p.hostname not in {"127.0.0.1", "localhost"}
            or not p.port
            or p.username
            or p.password
            or p.query
            or p.fragment
            or p.path not in {"", "/"}
            or any(c in value for c in "\r\n")
        ):
            raise ValueError
    except ValueError as exc:
        raise RpcError(-32602, "Hub 주소는 http://127.0.0.1:포트 형식이어야 합니다.") from exc
    return f"http://127.0.0.1:{p.port}"


def state_id(directory):
    path = Path(directory).resolve()
    try:
        info = path.stat()
        identity = f"{info.st_dev}:{info.st_ino}" if info.st_ino else os.path.normcase(str(path))
    except OSError:
        identity = os.path.normcase(str(path))
    return hashlib.sha256(identity.encode()).hexdigest()


class ConnectionSettings:
    def __init__(self, directory, parent=None):
        self.path = Path(directory) / "connection.json"
        self.parent = parent

    def local(self):
        if not self.path.exists():
            return None
        if self.path.is_symlink() or self.path.stat().st_size > 65536:
            raise RpcError(-32602, "연결 설정 파일을 확인하세요.")
        try:
            return self.validate(json.loads(self.path.read_text(encoding="utf-8")))
        except (ValueError, OSError) as exc:
            raise RpcError(-32602, "연결 설정을 읽을 수 없습니다.") from exc

    def get(self):
        return self.local() or (self.parent.get() if self.parent else dict(DEFAULT))

    @staticmethod
    def validate(value):
        if not isinstance(value, dict) or set(value) != set(DEFAULT):
            raise RpcError(-32602, "연결 설정에는 mode·url·fallback만 지정하세요.")
        if (
            not isinstance(value["mode"], str)
            or value["mode"] not in MODES
            or value["fallback"] not in ("stdio", "error")
        ):
            raise RpcError(-32602, "연결 방식 또는 연결 실패 시 동작을 확인하세요.")
        return {**value, "url": base_url(value["url"])}

    def put(self, value):
        if value == {"inherit": True} and self.parent:
            self.path.unlink(missing_ok=True)
            return self.get()
        value = self.validate(value)
        atomic_json(self.path, value)
        return value


def health(url, directory, instance=None):
    """Startup probe only; dispatched tool calls are never replayed."""
    p = urlsplit(base_url(url))
    connection = http.client.HTTPConnection(p.hostname, p.port, timeout=1)
    try:
        connection.request("GET", "/healthz", headers={"Connection": "close"})
        response = connection.getresponse()
        body = response.read(65537)
        if response.status != 200 or len(body) > 65536:
            return None
        result = json.loads(body)
        if (
            not isinstance(result, dict)
            or result.get("state_id") != state_id(directory)
            or not result.get("instance")
            or (instance and result["instance"] != instance)
        ):
            return None
        return result
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        connection.close()


def running(directory):
    path = Path(directory) / "endpoint.json"
    try:
        if path.is_symlink() or path.stat().st_size > 65536:
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        url = base_url(record["url"])
        if health(url, directory, record.get("instance")):
            return {**record, "url": url}
    except (OSError, ValueError, KeyError, RpcError, TypeError):
        pass
    return None


def select_bridge(directory, settings, explicit_url=False):
    if settings["mode"] == "stdio":
        return None
    record = running(directory) if settings["mode"] == "hybrid" and not explicit_url else None
    url = record["url"] if record else settings["url"]
    if record or health(url, directory):
        return url
    if settings["mode"] == "hybrid" and settings["fallback"] == "stdio":
        return None
    raise RpcError(-32000, "HTTP Hub에 연결할 수 없습니다. 같은 저장소로 Hub를 시작하세요.")


def mcp_url(url, profile="global"):
    return base_url(url) + ("/mcp" if profile == "global" else "/mcp/projects/" + profile)


def agent_value(agent, connection):
    if "url" in connection:
        url = connection["url"]
        if agent == "gemini":
            return {"httpUrl": url}
        if agent == "opencode":
            return {"type": "remote", "url": url, "enabled": True}
        if agent == "copilot":
            return {"type": "http", "url": url, "tools": ["*"]}
        return {"type": "http", "url": url} if agent == "claude" else {"url": url}
    command, args = connection["command"], connection.get("args", [])
    if agent == "opencode":
        return {"type": "local", "command": [command, *args], "enabled": True}
    value = {"command": command, "args": args}
    if agent == "copilot":
        value.update(type="local", tools=["*"])
    return value


def configuration(hub, profile="global", mode=None, wsl_distribution=None):
    settings = hub.scoped(profile).connection_settings.get()
    if mode is not None:
        if mode not in MODES:
            raise RpcError(-32602, "연결 방식을 확인하세요.")
        settings = {**settings, "mode": mode}
    if settings["mode"] == "http":
        return {"url": mcp_url(settings["url"], profile)}
    source = Path(__file__).resolve().parent.parent
    bootstrap = (
        f"import runpy,sys;sys.path.insert(0,{str(source)!r});"
        "runpy.run_module('joongi_hub',run_name='__main__')"
    )
    args = [
        "-c",
        bootstrap,
        "stdio",
        "--state-dir",
        str(hub.root_hub.state_dir),
        "--skills-dir",
        str(hub.root_hub.common_skills.directory),
        "--profile",
        profile,
        "--mode",
        settings["mode"],
    ]
    if settings["mode"] == "hybrid":
        args += ["--fallback", settings["fallback"]]
    connection = {"command": sys.executable, "args": args}
    if wsl_distribution:
        if (
            not isinstance(wsl_distribution, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", wsl_distribution)
            or os.name == "nt"
        ):
            raise RpcError(-32602, "WSL 안에서 배포판 이름을 지정해 Windows용 연결을 생성하세요.")
        connection = {
            "command": "wsl.exe",
            "args": ["-d", wsl_distribution, "--exec", connection["command"], *args],
        }
    return connection
