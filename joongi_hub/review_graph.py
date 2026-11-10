"""Project-selecting MCP adapter for the optional Code Review Graph package.

Every analysis call names a repository. Each repository has its own database and
upstream process; no call can repoint a shared database to another source tree.
"""

import argparse
import copy
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path

from joongi_hub import __version__
from joongi_hub.credential_lock import CredentialLock
from joongi_hub.errors import RpcError
from joongi_hub.runtime import process_alive
from joongi_hub.storage import atomic_json
from joongi_hub.upstream import MAX_MESSAGE, Upstream, validate_server

SCHEMAS = Path(__file__).with_name("review_graph_tools.json")
PURPOSES = {
    "list_graph_stats_tool": "Inspect graph size, languages and index statistics. 그래프 통계.",
    "query_graph_tool": (
        "Query code symbols, callers, callees, dependencies and file summaries. 호출 관계, 의존성."
    ),
    "get_impact_radius_tool": (
        "Find code and tests affected by changes to selected files. 변경 영향, 영향 범위."
    ),
    "get_review_context_tool": (
        "Collect review context and source around changed files. 코드 리뷰, 변경 검토."
    ),
    "get_minimal_context_tool": (
        "Find minimal task-relevant code context and entry points. 최소 컨텍스트, 진입점."
    ),
    "find_large_functions_tool": (
        "Find large functions or classes by line count and file pattern. 긴 함수, 큰 클래스."
    ),
    "get_docs_section_tool": (
        "Read a built-in Code Review Graph usage documentation section. 사용법, 도움말."
    ),
}
BOOTSTRAP = (
    "import os,runpy,sys;"
    "os.environ['CRG_HOME']=sys.argv.pop(1);"
    "os.environ['CRG_DATA_DIR']=sys.argv.pop(1);"
    "os.environ['CRG_REPO_ROOT']=sys.argv.pop(1);"
    "os.environ['CRG_SERIAL_PARSE']='1';"
    "sys.argv=['code-review-graph',*sys.argv[1:]];"
    "runpy.run_module('code_review_graph',run_name='__main__')"
)


def tool_definitions():
    tools = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    for tool in tools:
        schema = tool["inputSchema"]
        schema["properties"]["repo_root"] = {
            "type": "string",
            "description": "Absolute project root. Required; never reuse another project root.",
        }
        schema["required"] = sorted(set(schema.get("required", [])) | {"repo_root"})
        tool["description"] = (
            PURPOSES[tool["name"]]
            + " Use the selected repo_root only; call graph_build first if not indexed."
        )
        tool["annotations"] = {"readOnlyHint": True}
    for name, description in [
        (
            "graph_project_status",
            "Check the selected project's index; poll this after graph_build. 색인 상태.",
        ),
        (
            "graph_build",
            "Build this graph in the background. Poll graph_project_status. 색인 생성, 재색인.",
        ),
    ]:
        properties = {
            "repo_root": {
                "type": "string",
                "description": "Absolute project root (WSL paths or Windows drive paths in WSL).",
            }
        }
        if name == "graph_build":
            properties.update(
                refresh={"type": "boolean", "default": False},
                initialize_project={
                    "type": "boolean",
                    "default": False,
                    "description": "Allow a .code-review-graph marker without Git/SVN.",
                },
            )
        tools.append(
            {
                "name": name,
                "description": description,
                "inputSchema": {
                    "type": "object",
                    "properties": properties,
                    "required": ["repo_root"],
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": name != "graph_build"},
            }
        )
    return tools


def module_command(*arguments):
    source = Path(__file__).resolve().parent.parent
    bootstrap = (
        f"import sys,runpy;sys.path.insert(0,{str(source)!r});"
        "runpy.run_module('joongi_hub.review_graph',run_name='__main__')"
    )
    return [sys.executable, "-B", "-c", bootstrap, *map(str, arguments)]


def server_config(interpreter, directory, server_id="code-review-graph"):
    command = module_command(
        "--python",
        Path(interpreter).expanduser().absolute(),
        "--data-dir",
        Path(directory).expanduser().resolve(),
    )
    return validate_server(
        {
            "id": server_id,
            "name": "Code Review Graph · project-aware",
            "transport": "stdio",
            "command": command[0],
            "args": command[1:],
            "protocol_version": "2025-11-25",
            "enabled": True,
        }
    )


def repository(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise RpcError(-32602, "repo_root에 분석할 프로젝트의 절대 경로를 지정하세요.")
    if os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", value):
        value = "/mnt/" + value[0].lower() + "/" + value[3:].replace("\\", "/")
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_dir() or path == Path(path.anchor):
        raise RpcError(-32602, "repo_root는 존재하는 프로젝트 폴더의 절대 경로여야 합니다.")
    return path.resolve()


def read_record(path):
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > 65536:
        raise RpcError(-32602, "그래프 상태 파일을 확인하세요.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError
        return value
    except ValueError as exc:
        raise RpcError(-32602, "그래프 상태 파일을 읽을 수 없습니다.") from exc


def result(value):
    return {
        "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
        "structuredContent": value,
    }


class Gateway:
    def __init__(self, interpreter, directory):
        self.interpreter = Path(interpreter).expanduser().absolute()
        if not self.interpreter.is_file():
            raise RpcError(-32602, "Code Review Graph Python 실행 환경을 찾지 못했습니다.")
        self.directory = Path(directory).expanduser().resolve()
        self.clients = OrderedDict()

    def select(self, value):
        root = repository(value)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Persistent paths survive remounts; samefile joins Windows case aliases.
        # Never persist device/inode as a cache key: mount IDs can change on reboot.
        with CredentialLock(self.directory / "projects.lock"):
            for path in self.directory.glob("*/project.json"):
                record = read_record(path)
                if record:
                    saved = Path(record["repo_root"])
                    if saved.is_dir() and saved.samefile(root):
                        return saved, path.parent
            folder = self.directory / hashlib.sha256(str(root).encode()).hexdigest()
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_json(folder / "project.json", {"repo_root": str(root)})
        return root, folder

    @staticmethod
    def status(root, folder):
        state = read_record(folder / "build.json") or {"status": "not_indexed"}
        if state["status"] == "building" and (
            not process_alive(state.get("pid")) or time.time() - state.get("started_at", 0) > 360
        ):
            state = {**state, "status": "interrupted"}
        if state["status"] == "ready" and not (folder / "data/graph.db").is_file():
            state = {"status": "not_indexed"}
        if state["status"] == "ready" and process_alive(state.get("pid")):
            # Completion is durable before process exit; Windows still holds worker.log.
            state = {**state, "status": "building"}
        return {
            **state,
            "repo_root": str(root),
            "data_dir": str(folder / "data"),
            "next_step": "graph_project_status"
            if state["status"] == "building"
            else "analysis tools"
            if state["status"] == "ready"
            else "graph_build",
        }

    def build(self, root, folder, arguments):
        with CredentialLock(self.directory / "builds.lock"), CredentialLock(folder / "build.lock"):
            state = self.status(root, folder)
            if state["status"] == "building" or (
                state["status"] == "ready" and not arguments.get("refresh", False)
            ):
                return result(state)
            active = 0
            for path in self.directory.glob("*/build.json"):
                record = read_record(path) or {}
                if (
                    record.get("status") == "building"
                    and process_alive(record.get("pid"))
                    and time.time() - record.get("started_at", 0) < 360
                ):
                    active += 1
            if active >= 2:
                raise RpcError(
                    -32602,
                    "동시에 최대 2개 프로젝트를 색인합니다. 완료 후 다시 요청하세요.",
                )
            if not any((root / name).exists() for name in (".git", ".svn", ".code-review-graph")):
                if arguments.get("initialize_project") is not True:
                    raise RpcError(
                        -32602,
                        "Git/SVN이 없습니다. initialize_project=true로 표지 생성을 허용하세요.",
                    )
                (root / ".code-review-graph").mkdir(exist_ok=True)
            old = self.clients.pop(str(root), None)
            if old:
                old.close()
            plan = {"repo_root": str(root), "python": str(self.interpreter)}
            atomic_json(folder / "build-plan.json", plan)
            with (folder / "worker.log").open("ab") as log:
                child = subprocess.Popen(
                    module_command("--worker", folder),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=os.name != "nt",
                    creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
                )
            atomic_json(
                folder / "build.json",
                {"status": "building", "pid": child.pid, "started_at": time.time()},
            )
            threading.Thread(target=child.wait, daemon=True).start()
            # Worker outlives the MCP connection; it writes completion itself.
            return result(self.status(root, folder))

    def query(self, name, arguments):
        if name not in {item["name"] for item in tool_definitions()} or not isinstance(
            arguments, dict
        ):
            raise RpcError(-32602, "알 수 없는 그래프 도구 또는 입력입니다.")
        root, folder = self.select(arguments.get("repo_root"))
        if name == "graph_build":
            if any(
                type(arguments.get(key, False)) is not bool
                for key in ("refresh", "initialize_project")
            ):
                raise RpcError(-32602, "refresh와 initialize_project는 boolean이어야 합니다.")
            return self.build(root, folder, arguments)
        with CredentialLock(folder / "build.lock"):
            state = self.status(root, folder)
            if name == "graph_project_status":
                return result(state)
            if state["status"] != "ready":
                raise RpcError(
                    -32602,
                    "그래프가 준비되지 않았습니다. "
                    "graph_build 후 graph_project_status를 확인하세요.",
                    state,
                )
            return self.analysis(name, arguments, root, folder)

    def analysis(self, name, arguments, root, folder):
        key = str(root)
        client = self.clients.pop(key, None)
        if client is None:
            config = {
                "id": "selected-graph",
                "transport": "stdio",
                "command": str(self.interpreter),
                "args": [
                    "-B",
                    "-c",
                    BOOTSTRAP,
                    str(folder / "home"),
                    str(folder / "data"),
                    str(root),
                    "serve",
                    "--repo",
                    str(root),
                    "--tools",
                    ",".join(t["name"] for t in json.loads(SCHEMAS.read_text())),
                ],
                "protocol_version": "2025-11-25",
            }
            client = Upstream(validate_server(config))
        self.clients[key] = client
        while len(self.clients) > 2:
            _, retired = self.clients.popitem(last=False)
            retired.close()
        params = copy.deepcopy(arguments)
        params["repo_root"] = str(root)
        return client.request("tools/call", {"name": name, "arguments": params})

    def close(self):
        for client in self.clients.values():
            client.close()
        self.clients.clear()


def worker(folder):
    folder = Path(folder)
    with CredentialLock(folder / "build.lock"):
        plan = read_record(folder / "build-plan.json")
        state = read_record(folder / "build.json")
        if not plan or not state or state.get("pid") != os.getpid():
            return 1
    root = repository(plan["repo_root"])
    command = [
        plan["python"],
        "-B",
        "-c",
        BOOTSTRAP,
        str(folder / "home"),
        str(folder / "data"),
        str(root),
        "build",
        "--repo",
        str(root),
        "--skip-flows",
    ]
    status = "error"
    try:
        with (folder / "build.log").open("wb") as log:
            completed = subprocess.run(
                command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, timeout=300
            )
        if completed.returncode == 0 and (folder / "data/graph.db").is_file():
            status = "ready"
    except (OSError, subprocess.TimeoutExpired):
        status = "error"
    with CredentialLock(folder / "build.lock"):
        atomic_json(
            folder / "build.json",
            {
                **state,
                "status": status,
                "finished_at": time.time(),
                "log": str(folder / "build.log"),
            },
        )
    return 0 if status == "ready" else 1


def rpc(gateway, message):
    request_id = message.get("id") if isinstance(message, dict) else None
    try:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise RpcError(-32600, "Invalid JSON-RPC request")
        if "id" not in message:
            return None
        method, params = message.get("method"), message.get("params", {})
        if not isinstance(params, dict):
            raise RpcError(-32602, "Invalid parameters")
        if method == "initialize":
            value = {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "joongi-project-review-graph", "version": __version__},
            }
        elif method == "tools/list":
            value = {"tools": tool_definitions()}
        elif method == "tools/call":
            value = gateway.query(params.get("name"), params.get("arguments", {}))
        elif method == "ping":
            value = {}
        else:
            raise RpcError(-32601, "Unknown method")
        return {"jsonrpc": "2.0", "id": request_id, "result": value}
    except RpcError as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": exc.as_dict()}
    except (OSError, ValueError, TypeError):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": "그래프 경로와 실행 환경을 확인하세요."},
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--worker", type=Path)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker)
    if not args.python or not args.data_dir:
        parser.error("--python and --data-dir are required")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    gateway = Gateway(args.python, args.data_dir)
    if os.name != "nt":

        def terminate(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, terminate)
    try:
        while line := sys.stdin.buffer.readline(MAX_MESSAGE + 1):
            if len(line) > MAX_MESSAGE:
                break
            try:
                response = rpc(gateway, json.loads(line))
            except ValueError:
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Invalid JSON"},
                }
            if response is not None:
                print(json.dumps(response, ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        gateway.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
