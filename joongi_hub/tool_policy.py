"""Exact-call consent shared by independent stdio and management processes."""

import contextlib
import hashlib
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

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
            db.execute(
                "CREATE TABLE IF NOT EXISTS grants "
                "(id TEXT PRIMARY KEY, server TEXT, tool TEXT, binding TEXT, scope TEXT, "
                "expires REAL, created REAL, UNIQUE(server,tool,binding))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS approval_window "
                "(id INTEGER PRIMARY KEY CHECK(id=1), owner TEXT, expires REAL)"
            )
        os.chmod(self.path, 0o600)

    @contextlib.contextmanager
    def db(self):
        with contextlib.closing(sqlite3.connect(self.path, timeout=10)) as db:
            with db:
                yield db

    @staticmethod
    def binding(config, tool, auth_epoch=""):
        # Store only a digest of connection, definition and resolved env values.
        names = set(config.get("env", {}).values()) | set(config.get("headers", {}).values())
        names.update(
            v
            for k, v in config.get("auth", {}).items()
            if k.endswith("_env") and isinstance(v, str)
        )
        value = {
            "config": config,
            "auth_epoch": auth_epoch,
            "definition": tool,
            "environment": {name: os.environ.get(name) for name in sorted(names)},
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest()

    def authorize(self, config, tool, arguments, continuation=None, auth_epoch=""):
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
        binding = self.binding(config, tool, auth_epoch)
        payload = {
            "binding": binding,
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
            db.execute("DELETE FROM grants WHERE expires IS NOT NULL AND expires<=?", (now,))
            obsolete = {
                row[0]
                for row in db.execute(
                    "SELECT binding FROM grants WHERE server=? AND tool=? AND binding!=?",
                    (config["id"], name, binding),
                )
            }
            if obsolete:
                for request_id, encoded in db.execute(
                    "SELECT id,payload FROM approvals"
                ).fetchall():
                    if json.loads(encoded).get("binding") in obsolete:
                        db.execute("DELETE FROM approvals WHERE id=?", (request_id,))
            db.execute(
                "DELETE FROM grants WHERE server=? AND tool=? AND binding!=?",
                (config["id"], name, binding),
            )
            denied = db.execute(
                "SELECT id FROM approvals WHERE identity=? AND status='denied'", (identity,)
            ).fetchone()
            if denied:
                raise RpcError(-32043, "사용자가 이 호출을 거절했습니다.", {"status": "denied"})
            if db.execute(
                "SELECT id FROM grants WHERE server=? AND tool=? AND binding=?",
                (config["id"], name, binding),
            ).fetchone():
                db.execute("DELETE FROM approvals WHERE identity=?", (identity,))
                return
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
                stored = json.loads(
                    db.execute(
                        "SELECT payload FROM approvals WHERE id=?", (request_id,)
                    ).fetchone()[0]
                )
                if "binding" not in stored:
                    stored["binding"] = binding
                    db.execute(
                        "UPDATE approvals SET payload=? WHERE id=?",
                        (json.dumps(stored, ensure_ascii=False), request_id),
                    )
            else:
                if db.execute("SELECT count(*) FROM approvals").fetchone()[0] >= 32:
                    raise RpcError(
                        -32043, "보류 중인 승인이 너무 많습니다. 관리 화면에서 정리하세요."
                    )
                request_id = secrets.token_hex(20)
                # Display-only snapshot is outside the canonical identity above.
                # The binding is part of consent identity; only this display snapshot is not.
                address = urlsplit(config.get("url", ""))
                payload["binding"] = binding
                payload["review"] = {
                    "transport": config.get("transport", ""),
                    "endpoint": urlunsplit(
                        (address.scheme, address.netloc.rsplit("@", 1)[-1], address.path, "", "")
                    ),
                }
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
                    "SELECT id,payload,status,expires FROM approvals "
                    "WHERE status!='denied' ORDER BY expires"
                )
            ]

    def decide(self, identity, approve, scope="once"):
        if type(approve) is not bool or (
            not isinstance(scope, str) or scope not in {"once", "hour", "always"}
        ):
            raise RpcError(-32602, "승인 범위를 확인하세요.")
        if not approve and scope != "once":
            raise RpcError(-32602, "거절에는 허용 범위를 지정할 수 없습니다.")
        if not isinstance(identity, str) or len(identity) != 40:
            raise RpcError(-32602, "승인 요청 ID를 확인하세요.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status,expires,payload FROM approvals WHERE id=?", (identity,)
            ).fetchone()
            if not row or row[0] != "pending" or row[1] < time.time():
                raise RpcError(-32043, "승인 요청이 만료되었거나 이미 처리됐습니다.")
            if approve and scope != "once":
                payload = json.loads(row[2])
                binding = payload.get("binding")
                if not isinstance(binding, str) or len(binding) != 64:
                    raise RpcError(
                        -32043, "이전 요청은 반복 허용할 수 없습니다. 호출을 다시 요청하세요."
                    )
                db.execute(
                    "INSERT OR REPLACE INTO grants VALUES (?,?,?,?,?,?,?)",
                    (
                        secrets.token_hex(20),
                        payload["server"],
                        payload["tool"],
                        binding,
                        scope,
                        time.time() + 3600 if scope == "hour" else None,
                        time.time(),
                    ),
                )
                for request_id, encoded in db.execute(
                    "SELECT id,payload FROM approvals WHERE status='pending'"
                ).fetchall():
                    if json.loads(encoded).get("binding") == binding:
                        db.execute(
                            "UPDATE approvals SET status='approved' WHERE id=?", (request_id,)
                        )
            if approve:
                db.execute("UPDATE approvals SET status='approved' WHERE id=?", (identity,))
            else:
                db.execute("UPDATE approvals SET status='denied' WHERE id=?", (identity,))
        return {"id": identity, "approved": approve, "scope": scope}

    def get(self, request_id):
        if not isinstance(request_id, str) or len(request_id) != 40:
            raise RpcError(-32602, "승인 요청 ID를 확인하세요.")
        with self.db() as db:
            row = db.execute(
                "SELECT payload,status,expires FROM approvals WHERE id=?", (request_id,)
            ).fetchone()
        if not row or row[2] <= time.time():
            return {"approval_id": request_id, "status": "unavailable"}
        return {
            **json.loads(row[0]),
            "approval_id": request_id,
            "status": row[1],
            "expires_at": row[2],
        }

    def grants(self):
        with self.db() as db:
            db.execute(
                "DELETE FROM grants WHERE expires IS NOT NULL AND expires<=?", (time.time(),)
            )
            return [
                dict(
                    zip(
                        ("id", "server", "tool", "scope", "expires_at", "created_at"),
                        row,
                        strict=True,
                    )
                )
                for row in db.execute(
                    "SELECT id,server,tool,scope,expires,created FROM grants ORDER BY created DESC"
                )
            ]

    def revoke_grant(self, identity):
        if not isinstance(identity, str) or len(identity) != 40:
            raise RpcError(-32602, "허용 ID를 확인하세요.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT binding FROM grants WHERE id=?", (identity,)).fetchone()
            if row:
                for request_id, encoded in db.execute(
                    "SELECT id,payload FROM approvals"
                ).fetchall():
                    if json.loads(encoded).get("binding") == row[0]:
                        db.execute("DELETE FROM approvals WHERE id=?", (request_id,))
                db.execute("DELETE FROM grants WHERE id=?", (identity,))
        return {"revoked": bool(row)}

    def revoke_server(self, server):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM grants WHERE server=?", (server,))
            for request_id, encoded in db.execute("SELECT id,payload FROM approvals").fetchall():
                if json.loads(encoded)["server"] == server:
                    db.execute("DELETE FROM approvals WHERE id=?", (request_id,))

    def decide_many(self, identities, approve):
        if (
            type(approve) is not bool
            or not isinstance(identities, list)
            or not 1 <= len(identities) <= 32
            or any(not isinstance(i, str) or len(i) != 40 for i in identities)
            or len(set(identities)) != len(identities)
        ):
            raise RpcError(-32602, "선택한 승인 요청을 확인하세요.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for identity in identities:
                row = db.execute(
                    "SELECT status,expires FROM approvals WHERE id=?", (identity,)
                ).fetchone()
                if not row or row[0] != "pending" or row[1] <= time.time():
                    raise RpcError(-32043, "요청 상태가 바뀌었습니다. 새 목록을 확인하세요.")
            for identity in identities:
                db.execute(
                    "UPDATE approvals SET status=? WHERE id=?",
                    ("approved" if approve else "denied", identity),
                )
        return [
            {"approval_id": i, "status": "approved" if approve else "denied", "scope": "once"}
            for i in identities
        ]

    def window_claim(self, owner):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT owner,expires FROM approval_window WHERE id=1").fetchone()
            if row and row[1] > time.time():
                return row[0] == owner
            db.execute(
                "INSERT OR REPLACE INTO approval_window VALUES (1,?,?)", (owner, time.time() + 120)
            )
        return True

    def window_live(self, owner=None, renew=False):
        with self.db() as db:
            if renew:
                db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT owner,expires FROM approval_window WHERE id=1").fetchone()
            active = bool(row and row[1] > time.time() and (owner is None or row[0] == owner))
            if active and renew:
                db.execute("UPDATE approval_window SET expires=? WHERE id=1", (time.time() + 120,))
            return active

    def window_release(self, owner, only_if_empty=False):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                only_if_empty
                and db.execute(
                    "SELECT id FROM approvals WHERE status='pending' AND expires>?", (time.time(),)
                ).fetchone()
            ):
                return False
            db.execute("DELETE FROM approval_window WHERE id=1 AND owner=?", (owner,))
        return True
