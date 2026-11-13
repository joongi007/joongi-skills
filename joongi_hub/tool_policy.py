"""Exact-call consent shared by independent stdio and management processes."""

import contextlib
import hashlib
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

from joongi_hub.errors import RpcError


def validate_policy(value):
    if not isinstance(value, dict) or set(value) - {"allowed_tools", "denied_tools"}:
        raise RpcError(-32602, "도구 정책에는 allowed_tools·denied_tools만 지정하세요.")
    for names in value.values():
        if (
            not isinstance(names, list)
            or len(names) > 512
            or not all(
                isinstance(n, str) and 0 < len(n) <= 200 and not any(ord(c) < 32 for c in n)
                for n in names
            )
        ):
            raise RpcError(-32602, "도구 정책은 도구 이름의 배열이어야 합니다.")


class ToolPolicy:
    def __init__(self, directory):
        self.path = Path(directory) / "approvals.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise RpcError(-32043, "승인 저장소의 symlink는 허용하지 않습니다.")
        with self.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS approvals "
                "(id TEXT PRIMARY KEY, identity TEXT, payload TEXT, status TEXT, expires REAL)"
            )
        os.chmod(self.path, 0o600)

    @contextlib.contextmanager
    def db(self):
        with contextlib.closing(sqlite3.connect(self.path, timeout=10)) as db:
            with db:
                yield db

    def authorize(self, config, tool, arguments, continuation=None):
        policy = config.get("policy", {})
        name = tool["name"]
        if name in policy.get("denied_tools", []) or "*" in policy.get("denied_tools", []):
            raise RpcError(-32043, "이 도구는 로컬 정책으로 차단되어 있습니다.")
        if name in policy.get("allowed_tools", []) or "*" in policy.get("allowed_tools", []):
            return
        # A local command without credentials already executes as this OS user.
        # Remote services and credentialed commands require explicit local consent.
        if (
            config.get("auth", {}).get("type", "none") == "none"
            and not config.get("env")
            and not config.get("headers")
            and "policy" not in config
        ):
            return
        payload = {
            "server": config["id"],
            "tool": name,
            "arguments": arguments,
            "continuation": continuation or {},
        }
        if len(json.dumps(payload, ensure_ascii=False).encode()) > 16384:
            raise RpcError(
                -32043,
                "일회성 승인에 담기에는 인수가 큽니다. 신뢰한 도구의 허용 목록을 검토하세요.",
            )
        identity = hashlib.sha256(
            json.dumps(
                {"config": config, "definition": tool, "call": payload},
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
        ).hexdigest()
        now = time.time()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM approvals WHERE expires < ?", (now,))
            approved = db.execute(
                "SELECT id FROM approvals WHERE identity=? AND status='approved'", (identity,)
            ).fetchone()
            if approved:
                db.execute("DELETE FROM approvals WHERE id=?", approved)
                return
            pending = db.execute(
                "SELECT id FROM approvals WHERE identity=? AND status='pending'", (identity,)
            ).fetchone()
            if pending:
                request_id = pending[0]
            else:
                if db.execute("SELECT count(*) FROM approvals").fetchone()[0] >= 32:
                    raise RpcError(
                        -32043, "보류 중인 승인이 너무 많습니다. 관리 화면에서 정리하세요."
                    )
                request_id = secrets.token_hex(20)
                db.execute(
                    "INSERT INTO approvals VALUES (?,?,?,?,?)",
                    (
                        request_id,
                        identity,
                        json.dumps(payload, ensure_ascii=False),
                        "pending",
                        now + 300,
                    ),
                )
        raise RpcError(
            -32043,
            "로컬 Hub 관리 화면에서 이 호출을 검토·승인한 뒤 같은 요청을 다시 실행하세요.",
            {"approval_id": request_id, "server": config["id"], "tool": name},
        )

    def list(self):
        with self.db() as db:
            db.execute("DELETE FROM approvals WHERE expires < ?", (time.time(),))
            return [
                {"id": row[0], **json.loads(row[1]), "status": row[2], "expires_at": row[3]}
                for row in db.execute(
                    "SELECT id,payload,status,expires FROM approvals ORDER BY expires"
                )
            ]

    def decide(self, identity, approve):
        if not isinstance(identity, str) or len(identity) != 40:
            raise RpcError(-32602, "승인 요청 ID를 확인하세요.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status,expires FROM approvals WHERE id=?", (identity,)
            ).fetchone()
            if not row or row[0] != "pending" or row[1] < time.time():
                raise RpcError(-32043, "승인 요청이 만료되었거나 이미 처리됐습니다.")
            if approve:
                db.execute("UPDATE approvals SET status='approved' WHERE id=?", (identity,))
            else:
                db.execute("DELETE FROM approvals WHERE id=?", (identity,))
        return {"id": identity, "approved": approve}
