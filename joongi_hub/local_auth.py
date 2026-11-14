"""Expiring, rotating credentials for local UI and scoped HTTP MCP clients."""

import json
import math
import re
import secrets
import time
from pathlib import Path

from joongi_hub.credential_lock import CredentialLock
from joongi_hub.errors import RpcError
from joongi_hub.storage import atomic_json

TOKEN_TTL = 3600
ROTATE_AFTER = 900
PREVIOUS_GRACE = 60
SESSION_TTL = 8 * 3600
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


def _name(scope, management):
    return "management" if management else "mcp:" + scope


def _new(now, previous=None, session_end=None):
    end = session_end or now + SESSION_TTL
    row = {
        "current": secrets.token_urlsafe(32),
        "issued_at": now,
        "expires_at": min(now + TOKEN_TTL, end),
        "session_end": end,
    }
    if previous and previous["expires_at"] > now:
        row["previous"] = previous["current"]
        row["previous_until"] = min(previous["expires_at"], now + PREVIOUS_GRACE)
    return row


def _load(path):
    if (
        path.is_symlink()
        or path.parent.is_symlink()
        or (path.exists() and path.stat().st_size > 65536)
    ):
        raise RpcError(-32040, "로컬 연결 자격증명 파일을 확인하세요.")
    try:
        data = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {"schema": 2, "tokens": {}}
        )
        # Legacy non-expiring bearer credentials are revoked on upgrade.
        if isinstance(data, dict) and "schema" not in data:
            if not all(isinstance(v, str) and TOKEN.fullmatch(v) for v in data.values()):
                raise ValueError
            now = time.time()
            data = {
                "schema": 2,
                "tokens": {
                    k if k == "management" or k.startswith("mcp:") else "mcp:" + k: _new(now)
                    for k in data
                },
            }
            atomic_json(path, data)
        if (
            not isinstance(data, dict)
            or set(data) != {"schema", "tokens"}
            or data["schema"] != 2
            or not isinstance(data["tokens"], dict)
        ):
            raise ValueError
        for key, row in data["tokens"].items():
            if (
                not isinstance(key, str)
                or not (key == "management" or key.startswith("mcp:"))
                or not isinstance(row, dict)
            ):
                raise ValueError
            if set(row) not in (
                {"current", "issued_at", "expires_at", "session_end"},
                {"current", "issued_at", "expires_at", "session_end", "previous", "previous_until"},
            ):
                raise ValueError
            if not isinstance(row["current"], str) or not TOKEN.fullmatch(row["current"]):
                raise ValueError
            for field in ("issued_at", "expires_at", "session_end", "previous_until"):
                if field in row and (
                    type(row[field]) not in (int, float) or not math.isfinite(row[field])
                ):
                    raise ValueError
            if (
                not row["issued_at"] < row["expires_at"] <= row["session_end"]
                or row["expires_at"] - row["issued_at"] > TOKEN_TTL
                or row["session_end"] - row["issued_at"] > SESSION_TTL
            ):
                raise ValueError
            if "previous" in row and (
                not isinstance(row["previous"], str)
                or not TOKEN.fullmatch(row["previous"])
                or row["previous_until"] > row["issued_at"] + PREVIOUS_GRACE
            ):
                raise ValueError
        return data
    except (ValueError, TypeError, OSError, KeyError) as exc:
        raise RpcError(-32040, "로컬 연결 자격증명을 읽을 수 없습니다.") from exc


def _locked(directory):
    return CredentialLock(Path(directory) / "http-auth.lock")


def local_token(directory, scope="global", create=True, *, management=False):
    """Owner-side broker: possession of the state directory permits renewal."""
    path = Path(directory) / "http-auth.json"
    key = _name(scope, management)
    with _locked(directory):
        data = _load(path)
        row, now = data["tokens"].get(key), time.time()
        if row is None and not create:
            return None
        if row is None or row["expires_at"] <= now or row["session_end"] <= now:
            row = _new(now)
        elif now - row["issued_at"] >= ROTATE_AFTER:
            row = _new(now, row, row["session_end"])
        else:
            return row["current"]
        data["tokens"][key] = row
        atomic_json(path, data)
        return row["current"]


def authenticate_local(directory, supplied, scope="global", *, management=False):
    """Network callers may rotate a valid session, never renew an expired one."""
    if not isinstance(supplied, str) or not TOKEN.fullmatch(supplied):
        return None
    path = Path(directory) / "http-auth.json"
    key = _name(scope, management)
    with _locked(directory):
        data = _load(path)
        row, now = data["tokens"].get(key), time.time()
        if not row or row["expires_at"] <= now or row["session_end"] <= now:
            return None
        current = secrets.compare_digest(supplied, row["current"])
        previous = row.get("previous_until", 0) > now and secrets.compare_digest(
            supplied, row.get("previous", "")
        )
        if not (current or previous):
            return None
        if now - row["issued_at"] >= ROTATE_AFTER:
            row = _new(now, row, row["session_end"])
            data["tokens"][key] = row
            atomic_json(path, data)
        return row["current"]


def rotate_local_tokens(directory):
    path = Path(directory) / "http-auth.json"
    with _locked(directory):
        data, now = _load(path), time.time()
        data["tokens"] = {key: _new(now) for key in data["tokens"]}
        atomic_json(path, data)
        from joongi_hub.security_events import record

        record(directory, "local_tokens_revoked", "owner")
        return {"rotated": len(data["tokens"]), "previous_tokens_revoked": True}


def token_status(directory, scope="global", *, management=False):
    path = Path(directory) / "http-auth.json"
    with _locked(directory):
        row = _load(path)["tokens"].get(_name(scope, management))
        return (
            {key: row[key] for key in ("issued_at", "expires_at", "session_end")} if row else None
        )


def ui_url(url, directory):
    return url.rstrip("/") + "/#session=" + local_token(directory, management=True)


class LocalAuth:
    def __init__(self, directory, profile):
        self.directory, self.profile = directory, profile

    def headers(self, config, **options):
        token = local_token(self.directory, self.profile, create=False)
        if not token:
            raise RpcError(-32040, "HTTP 연결 설정을 다시 생성하세요.")
        return {"Authorization": "Bearer " + token}

    def challenge(self, config, value):
        pass

    def secret_values(self, config):
        token = local_token(self.directory, self.profile, create=False)
        return [token] if token else []

    def refresh_rejected(self, config, rejected):
        return False
