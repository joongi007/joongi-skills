"""Atomic local registry and durable asynchronous task records."""

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from joongi_hub.credential_lock import CredentialLock
from joongi_hub.errors import RpcError
from joongi_hub.runtime import process_alive


def timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Registry:
    def __init__(self, directory: Path):
        self.path = directory / "servers.json"
        self.lock = CredentialLock(directory / "registry.lock")
        self.backup = directory / "backups" / "servers.json"

    def list(self):
        with self.lock:
            if not self.path.exists():
                if self.backup.exists():
                    raise RpcError(
                        -32041, "MCP 등록 파일이 없습니다. state --restore-backup으로 복구하세요."
                    )
                return []
            try:
                if self.path.is_symlink() or self.path.stat().st_size > 4 * 1024**2:
                    raise ValueError
                value = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(value, list) or any(
                    not isinstance(s, dict) or not isinstance(s.get("id"), str) for s in value
                ):
                    raise ValueError
                return value
            except (ValueError, OSError) as exc:
                raise RpcError(
                    -32041, "MCP 등록 파일을 읽을 수 없습니다. 백업을 확인하세요."
                ) from exc

    def save(self, servers):
        """Caller holds the process lock; keep a committed recovery copy."""
        if self.backup.is_symlink() or self.backup.parent.is_symlink():
            raise RpcError(-32041, "등록 백업 경로의 symlink는 지원하지 않습니다.")
        atomic_json(self.path, servers)
        atomic_json(self.backup, servers)

    def put(self, server):
        with self.lock:
            servers = [item for item in self.list() if item["id"] != server["id"]]
            self.save(servers + [server])

    def delete(self, server_id):
        with self.lock:
            servers = self.list()
            if not any(item["id"] == server_id for item in servers):
                raise RpcError(-32602, "Unknown server")
            self.save([item for item in servers if item["id"] != server_id])


class TaskStore:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "tasks.sqlite3"
        self.lock = threading.RLock()
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        os.chmod(self.path, 0o600)
        # A restarted process must not leave locally executing jobs working forever.
        for task in self.list():
            if task["status"] in {"working", "input_required"} and not process_alive(
                task.get("executorPid")
            ):
                self.update(
                    task["taskId"],
                    status="failed",
                    error={"code": -32603, "message": "Hub restarted; execution was interrupted"},
                )

    @contextmanager
    def connection(self):
        database = sqlite3.connect(self.path, timeout=10)
        try:
            with database:
                yield database
        finally:
            database.close()

    def list(self, owner=None):
        with self.lock, self.connection() as db:
            tasks = [
                json.loads(row[0])
                for row in db.execute("SELECT body FROM tasks ORDER BY rowid DESC")
            ]
        return [task for task in tasks if owner is None or task.get("owner") == owner]

    def get(self, task_id, owner=None):
        with self.lock, self.connection() as db:
            row = db.execute("SELECT body FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise RpcError(-32602, "Unknown task")
        task = json.loads(row[0])
        if owner is not None and task.get("owner") != owner:
            raise RpcError(-32602, "Unknown task")
        return task

    def create(self, name, owner):
        now = timestamp()
        task = {
            "taskId": uuid.uuid4().hex,
            "name": name,
            "owner": owner,
            "executorPid": os.getpid(),
            "status": "working",
            "createdAt": now,
            "lastUpdatedAt": now,
            "ttlMs": 86400000,
            "pollIntervalMs": 500,
        }
        with self.lock, self.connection() as db:
            db.execute("INSERT INTO tasks VALUES (?, ?)", (task["taskId"], json.dumps(task)))
        return task

    def update(self, task_id, **changes):
        with self.lock:
            task = self.get(task_id)
            # Completion must never resurrect a cancelled job.
            if task["status"] in {"completed", "failed", "cancelled"}:
                return task
            task.update(changes, lastUpdatedAt=timestamp())
            with self.connection() as db:
                db.execute("UPDATE tasks SET body = ? WHERE id = ?", (json.dumps(task), task_id))
        return task
