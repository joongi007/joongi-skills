"""Bounded local security diagnostics containing fixed labels, never request data."""

import json
import os
import time
from pathlib import Path

from joongi_hub.credential_lock import CredentialLock
from joongi_hub.errors import RpcError

EVENTS = {"authentication_denied", "authentication_limited", "local_tokens_revoked"}
REASONS = {"mcp", "management", "owner"}
MAX_BYTES = 1024 * 1024


def record(directory, event, reason):
    if event not in EVENTS or reason not in REASONS:
        raise ValueError("Unknown security event label")
    directory = Path(directory)
    path = directory / "security-events.jsonl"
    previous = directory / "security-events.previous.jsonl"
    with CredentialLock(directory / "security-events.lock"):
        if path.is_symlink() or previous.is_symlink():
            raise RpcError(-32040, "보안 이벤트 파일의 symlink는 지원하지 않습니다.")
        if path.exists() and path.stat().st_size >= MAX_BYTES:
            os.replace(path, previous)
        fd = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            stream.write(
                json.dumps({"time": int(time.time()), "event": event, "reason": reason}) + "\n"
            )
