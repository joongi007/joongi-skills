"""State provenance and explicit, non-destructive registry migration."""

import json
import os
import tempfile
from pathlib import Path

from joongi_hub.errors import RpcError
from joongi_hub.storage import Registry
from joongi_hub.upstream import validate_server


def default_directory():
    # An installed launcher belongs to one home, independent of inherited env/cwd.
    return (
        Path(
            os.environ.get("JOONGI_HUB_INSTALL_STATE_DIR")
            or os.environ.get("JOONGI_HUB_STATE_DIR", Path.home() / ".local/share/joongi-hub")
        )
        .expanduser()
        .resolve()
    )


def temporary(directory):
    path = Path(directory).resolve()
    roots = [Path(tempfile.gettempdir()).resolve()]
    if os.name != "nt":
        roots += [Path("/tmp"), Path("/var/tmp")]
    return any(path == root or path.is_relative_to(root) for root in roots)


def describe(directory, server_count=None):
    directory = Path(directory).resolve()
    registry = Registry(directory)
    warnings = []
    if temporary(directory):
        warnings.append("임시 저장소입니다. 재부팅·정리 시 등록 정보가 사라질 수 있습니다.")
    try:
        count = len(registry.list()) if server_count is None else server_count
    except RpcError as exc:
        count = None
        warnings.append(str(exc))
    if count == 0:
        warnings.append("이 저장소에 등록된 MCP가 없습니다. 이전에 사용한 저장 경로를 확인하세요.")
    return {
        "state_dir": str(directory),
        "default_state_dir": str(default_directory()),
        "temporary": temporary(directory),
        "server_count": count,
        "registry_backup": str(registry.backup) if registry.backup.is_file() else None,
        "warnings": warnings,
    }


def read_servers(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024**2:
        raise RpcError(-32602, "가져올 MCP 등록 파일을 확인하세요.")
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError
        result = [validate_server(item) for item in entries]
        if len({item["id"] for item in result}) != len(result):
            raise ValueError
        return result
    except (ValueError, TypeError, KeyError) as exc:
        raise RpcError(-32602, "가져올 MCP 등록 형식이 올바르지 않습니다.") from exc


def import_servers(directory, source):
    """Merge configurations only; never copy credentials/tasks or execute commands."""
    source = Path(source).expanduser().resolve()
    if source == Path(directory).resolve():
        raise RpcError(-32602, "원본과 대상 저장소가 같습니다.")
    incoming = read_servers(source / "servers.json")
    for item in incoming:
        if item["transport"] == "stdio":
            command = Path(item["command"]).expanduser()
            paths = [
                command,
                *(Path(arg) for arg in item.get("args", []) if Path(arg).is_absolute()),
            ]
            if any(path.is_absolute() and temporary(path) for path in paths):
                raise RpcError(
                    -32602,
                    "임시 실행 경로를 포함한 MCP는 영구 경로로 바꾼 뒤 가져오세요.",
                    {"id": item["id"]},
                )
            if command.is_absolute() and not command.is_file():
                raise RpcError(
                    -32602,
                    "MCP 실행 파일이 없습니다. 실행 환경을 먼저 복구하세요.",
                    {"id": item["id"]},
                )
    registry = Registry(Path(directory))
    with registry.lock:
        current = registry.list()
        existing = {item["id"]: item for item in current}
        conflicts = [
            item["id"]
            for item in incoming
            if item["id"] in existing and existing[item["id"]] != item
        ]
        if conflicts:
            raise RpcError(
                -32602,
                "같은 ID의 다른 MCP 설정이 있어 가져오기를 중단했습니다.",
                {"ids": conflicts},
            )
        additions = [item for item in incoming if item["id"] not in existing]
        registry.save(current + additions)
    return {
        "imported": [item["id"] for item in additions],
        "source_preserved": True,
        "notice": "서버 설정만 가져왔습니다. 실행 경로·환경 변수와 인증을 확인하세요.",
    }


def restore_backup(directory):
    registry = Registry(Path(directory))
    with registry.lock:
        if registry.path.exists() or registry.path.is_symlink():
            raise RpcError(
                -32602, "기존 등록 파일을 덮어쓰지 않습니다. 별도로 보존한 뒤 복구하세요."
            )
        servers = read_servers(registry.backup)
        registry.save(servers)
    return {"restored": len(servers)}
