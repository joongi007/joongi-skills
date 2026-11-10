"""Optional local HTTP daemon; stdio never needs this process to exist."""

import http.client
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from joongi_hub.connections import ConnectionSettings, running
from joongi_hub.errors import RpcError
from joongi_hub.runtime import process_alive

_children = {}


def status(directory):
    from joongi_hub.state_store import describe

    record = running(directory)
    return {
        **describe(directory),
        "running": bool(record),
        "url": record["url"] if record else None,
        "mode": ConnectionSettings(directory).get()["mode"],
        "instance": record.get("instance") if record else None,
    }


def stop(directory):
    record = running(directory)
    if not record:
        return {"running": False, "stopped": False}
    p = urlsplit(record["url"])
    client = http.client.HTTPConnection(p.hostname, p.port, timeout=3)
    try:
        client.request("GET", "/api/v1/session")
        response = client.getresponse()
        token = json.loads(response.read(65536))["token"]
        client.request(
            "POST",
            "/api/v1/runtime/stop",
            json.dumps({"instance": record["instance"]}),
            {"Content-Type": "application/json", "X-Hub-Token": token},
        )
        response = client.getresponse()
        response.read(65536)
        if response.status != 200:
            raise RpcError(-32000, "Hub 종료 요청이 거절되었습니다.")
    finally:
        client.close()
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        if not running(directory):
            child = _children.pop(record.get("pid"), None)
            if child:
                child.wait(timeout=5)
            elif os.name == "nt":
                # HTTP can stop before Windows releases the daemon's log handle.
                while process_alive(record.get("pid")) and time.monotonic() < deadline:
                    time.sleep(0.05)
                if process_alive(record.get("pid")):
                    raise RpcError(-32000, "Hub가 아직 종료 중입니다. 잠시 후 다시 확인하세요.")
            return {"running": False, "stopped": True}
        time.sleep(0.05)
    raise RpcError(-32000, "Hub가 아직 종료 중입니다. 잠시 후 상태를 확인하세요.")


def start(directory, skills_dir, port=None, source_root=None):
    directory = Path(directory)
    record = running(directory)
    if record:
        return status(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = directory / "start.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RpcError(-32000, "다른 시작 요청이 진행 중입니다. 상태를 확인하세요.") from exc
    os.close(descriptor)
    child = None
    try:
        if running(directory):
            return status(directory)
        port = (
            port if port is not None else urlsplit(ConnectionSettings(directory).get()["url"]).port
        )
        source = str(
            Path(source_root).resolve() if source_root else Path(__file__).resolve().parent.parent
        )
        bootstrap = (
            f"import runpy,sys;sys.path.insert(0,{source!r});"
            "runpy.run_module('joongi_hub',run_name='__main__')"
        )
        command = [
            sys.executable,
            "-B",
            "-c",
            bootstrap,
            "serve",
            "--state-dir",
            str(directory),
            "--skills-dir",
            str(skills_dir),
            "--port",
            str(port),
        ]
        kwargs = (
            {"start_new_session": True}
            if os.name != "nt"
            else {
                "creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            }
        )
        log = directory / "runtime.log"
        descriptor = os.open(log, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "ab") as errors:
            child = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=errors,
                **kwargs,
            )
        _children[child.pid] = child
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if running(directory):
                return status(directory)
            if child.poll() is not None:
                raise RpcError(
                    -32000, "Hub를 시작하지 못했습니다. 포트와 runtime.log를 확인하세요."
                )
            time.sleep(0.05)
        raise RpcError(-32000, "Hub 시작 시간이 초과되었습니다.")
    except BaseException:
        if child and child.poll() is None:
            _children.pop(child.pid, None)
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
        raise
    finally:
        lock.unlink(missing_ok=True)


def manage(action, directory, skills_dir, port=None):
    if action == "status":
        return status(directory)
    if action == "stop":
        return stop(directory)
    if action == "restart":
        current = running(directory)
        if current and port is None:
            port = urlsplit(current["url"]).port
        stop(directory)
    result = start(directory, skills_dir, port)
    if action == "open":
        result["browser_opened"] = bool(webbrowser.open(result["url"]))
    return result
