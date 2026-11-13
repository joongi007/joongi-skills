"""Separate, owner-only credentials for local UI and scoped HTTP MCP clients."""

import json
import re
import secrets
from pathlib import Path

from joongi_hub.credential_lock import CredentialLock
from joongi_hub.errors import RpcError
from joongi_hub.storage import atomic_json


def local_token(directory, scope="global", create=True, *, management=False):
    scope = "management" if management else "mcp:" + scope
    path = Path(directory) / "http-auth.json"
    with CredentialLock(Path(directory) / "http-auth.lock"):
        if path.is_symlink() or (path.exists() and path.stat().st_size > 65536):
            raise RpcError(-32040, "로컬 연결 자격증명 파일을 확인하세요.")
        try:
            values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (ValueError, OSError) as exc:
            raise RpcError(-32040, "로컬 연결 자격증명을 읽을 수 없습니다.") from exc
        if not isinstance(values, dict) or any(
            not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", v)
            for v in values.values()
        ):
            raise RpcError(-32040, "로컬 연결 자격증명이 올바르지 않습니다.")
        token = values.get(scope)
        if token is None and create:
            token = secrets.token_urlsafe(32)
            atomic_json(path, {**values, scope: token})
        return token


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
