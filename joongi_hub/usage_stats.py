"""Opt-in local aggregate counters; never record queries, arguments or content."""

import math
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from joongi_hub.catalog_preferences import safe_path
from joongi_hub.credential_lock import CredentialLock
from joongi_hub.errors import RpcError

MAX_KEYS = 1000
RETENTION_DAYS = 30
MAX_DATABASE_BYTES = 2 * 1024**2
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
KINDS = {"search", "detail", "skill", "tool", "server", "call"}
OUTCOMES = {"success", "error", "empty", "approval_required", "cancelled", "denied", "ok", "miss"}


def today():
    return datetime.now(timezone.utc).date()


class UsageStats:
    def __init__(self, directory, enabled=False):
        self.directory = Path(directory).expanduser().absolute()
        self.path = self.directory / "usage-stats.sqlite3"
        self.lock = CredentialLock(self.directory / "usage-stats.lock")
        self.enabled = False
        self.set_enabled(enabled)

    def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise RpcError(-32602, "사용 통계 설정은 boolean이어야 합니다.")
        self.enabled = enabled

    @contextmanager
    def _connect(self):
        safe_path(self.path)
        if self.path.exists() and (
            not self.path.is_file() or self.path.stat().st_size > MAX_DATABASE_BYTES
        ):
            raise RpcError(-32045, "사용 통계 파일을 읽을 수 없습니다.")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(self.path, timeout=10)
        try:
            os.chmod(self.path, 0o600)
            db.execute("PRAGMA secure_delete=ON")
            db.execute(
                "CREATE TABLE IF NOT EXISTS usage ("
                "day TEXT NOT NULL,kind TEXT NOT NULL,name TEXT NOT NULL,outcome TEXT NOT NULL,"
                "count INTEGER NOT NULL,total_duration_ms INTEGER NOT NULL,"
                "max_duration_ms INTEGER NOT NULL,PRIMARY KEY(day,kind,name,outcome))"
            )
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _prune(db):
        cutoff = (today() - timedelta(days=RETENTION_DAYS - 1)).isoformat()
        db.execute("DELETE FROM usage WHERE day < ?", (cutoff,))
        db.execute(
            "DELETE FROM usage WHERE rowid IN ("
            "SELECT rowid FROM usage ORDER BY day DESC,rowid DESC LIMIT -1 OFFSET ?)",
            (MAX_KEYS,),
        )

    def record(self, kind, name, outcome, duration_ms=0, *, enabled=None):
        allowed = self.enabled if enabled is None else enabled is True
        if not allowed:
            return False
        # Invalid payloads are discarded rather than persisting untrusted content.
        if (
            not isinstance(kind, str)
            or kind not in KINDS
            or not isinstance(name, str)
            or not IDENTIFIER.fullmatch(name)
            or not isinstance(outcome, str)
            or outcome not in OUTCOMES
            or type(duration_ms) not in (int, float)
            or (type(duration_ms) is float and not math.isfinite(duration_ms))
            or duration_ms < 0
        ):
            return False
        duration = min(round(duration_ms), 3_600_000)
        safe_path(self.path)
        try:
            with self.lock, self._connect() as db:
                db.execute(
                    "INSERT INTO usage VALUES (?,?,?,?,1,?,?) "
                    "ON CONFLICT(day,kind,name,outcome) DO UPDATE SET "
                    "count=MIN(count+1,1000000000),"
                    "total_duration_ms=MIN(total_duration_ms+excluded.total_duration_ms,"
                    "1000000000000000),max_duration_ms=MAX(max_duration_ms,excluded.max_duration_ms)",
                    (today().isoformat(), kind, name, outcome, duration, duration),
                )
                self._prune(db)
            return True
        except sqlite3.Error as exc:
            raise RpcError(-32045, "사용 통계를 기록할 수 없습니다.") from exc

    def snapshot(self, *, enabled=None):
        allowed = self.enabled if enabled is None else enabled is True
        result = {
            "enabled": allowed,
            "retention_days": RETENTION_DAYS,
            "max_keys": MAX_KEYS,
            "total_count": 0,
            "entries": [],
        }
        safe_path(self.path)
        if not self.path.exists():
            return result
        try:
            with self.lock, self._connect() as db:
                self._prune(db)
                rows = db.execute(
                    "SELECT day,kind,name,outcome,count,total_duration_ms,max_duration_ms "
                    "FROM usage ORDER BY day DESC,kind,name,outcome LIMIT ?",
                    (MAX_KEYS,),
                ).fetchall()
            keys = (
                "day",
                "kind",
                "name",
                "outcome",
                "count",
                "total_duration_ms",
                "max_duration_ms",
            )
            result["entries"] = [dict(zip(keys, row, strict=True)) for row in rows]
            result["total_count"] = sum(row[4] for row in rows)
            return result
        except sqlite3.Error as exc:
            raise RpcError(-32045, "사용 통계를 읽을 수 없습니다.") from exc

    def reset(self):
        safe_path(self.path)
        if self.path.exists():
            try:
                with self.lock, self._connect() as db:
                    db.execute("DELETE FROM usage")
            except sqlite3.Error as exc:
                raise RpcError(-32045, "사용 통계를 초기화할 수 없습니다.") from exc
        return self.snapshot()
