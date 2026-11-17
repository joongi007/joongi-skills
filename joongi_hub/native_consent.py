"""Owner-host form consent over the stdio response channel, never an MCP tool."""

import collections
import json
import os
import queue
import secrets
import threading
import time

from joongi_hub.errors import RpcError


def supports_form(context, message=None):
    capabilities = context.get("capabilities", {})
    elicitation = capabilities.get("elicitation") if isinstance(capabilities, dict) else None
    params = message.get("params", {}) if isinstance(message, dict) else {}
    meta = params.get("_meta", {}) if isinstance(params, dict) else {}
    version = (
        meta.get("io.modelcontextprotocol/protocolVersion") if isinstance(meta, dict) else None
    )
    return (
        (version or context.get("version")) == "2025-11-25"
        and isinstance(elicitation, dict)
        and (not elicitation or isinstance(elicitation.get("form"), dict))
    )


class StdioChannel:
    """One bounded input reader; preserve unrelated messages during a host prompt."""

    def __init__(self, source, send, max_message):
        self.send = send
        self.max_message = max_message
        self.messages = queue.Queue(maxsize=128)
        self.deferred = collections.deque()
        try:
            descriptor = source.fileno()
        except (OSError, ValueError, AttributeError):
            descriptor = None
        buffer = bytearray()

        def readline():
            if descriptor is None:
                return source.readline(max_message + 1)
            # Reading the raw descriptor avoids holding sys.stdin's buffered-I/O
            # lock in a daemon thread during SIGTERM/interpreter finalization.
            while True:
                newline = buffer.find(b"\n")
                count = newline + 1 if newline >= 0 else len(buffer)
                if newline >= 0 or len(buffer) > max_message:
                    line = bytes(buffer[:count])
                    del buffer[:count]
                    return line
                chunk = os.read(descriptor, min(65536, max_message + 1 - len(buffer)))
                if not chunk:
                    line = bytes(buffer)
                    buffer.clear()
                    return line
                buffer.extend(chunk)

        def read():
            while True:
                try:
                    line = readline()
                except (OSError, ValueError):
                    line = b""
                finished = not line or len(line) > max_message
                self.messages.put(line)
                line = None
                if finished:
                    return

        threading.Thread(target=read, daemon=True).start()

    def next(self):
        return self.deferred.popleft() if self.deferred else self.messages.get()

    def ask(self, params, timeout=45, parent_id=None):
        identity = "hub-consent-" + secrets.token_hex(20)
        self.send(
            {"jsonrpc": "2.0", "id": identity, "method": "elicitation/create", "params": params}
        )
        deadline = time.monotonic() + timeout

        def abandon():
            self.send(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {
                        "requestId": identity,
                        "reason": "Consent form ended without approval",
                    },
                }
            )
            return None

        while True:
            try:
                line = self.messages.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                return abandon()
            if not line:
                self.deferred.append(line)
                return None
            if len(line) > self.max_message:
                self.deferred.append(line)
                return abandon()
            try:
                value = json.loads(line)
            except (ValueError, UnicodeError):
                value = None
            if isinstance(value, dict) and value.get("id") == identity and "method" not in value:
                return (
                    value.get("result")
                    if value.get("jsonrpc") == "2.0" and "error" not in value
                    else None
                )
            self.deferred.append(line)
            if (
                isinstance(value, dict)
                and value.get("method") == "notifications/cancelled"
                and isinstance(value.get("params"), dict)
                and value["params"].get("requestId") in (identity, parent_id)
            ):
                return abandon()
            # Do not retain unlimited agent traffic while a user is away.
            if len(self.deferred) >= 128:
                return abandon()


def review(hub, approval_id, channel, parent_id=None):
    """Approve an explicit snapshot once; no credentials or browser keys in forms."""
    pending = [row for row in hub.tool_policy.list() if row["status"] == "pending"]
    current = next((row for row in pending if row["id"] == approval_id), None)
    if current is None:
        return False, "changed"
    rows = [current]
    rows.extend(row for row in pending if row["id"] != approval_id)
    rows = rows[:8]
    properties = {}
    for index, row in enumerate(rows):
        properties["request_" + str(index)] = {
            "type": "boolean",
            "title": row["server"] + " · " + row["tool"],
            "description": json.dumps(
                {key: row.get(key) for key in ("arguments", "continuation", "review")},
                ensure_ascii=False,
            ),
            "default": False,
        }
    params = {
        "mode": "form",
        "message": "Joongi Hub · "
        + hub.profile_id
        + " · 선택한 호출만 한 번 실행하도록 허용합니다. "
        "체크하지 않은 요청과 이후 도착한 요청은 승인하지 않습니다. "
        "이 폼에는 비밀번호·토큰을 입력하지 마세요.",
        "requestedSchema": {"type": "object", "properties": properties},
    }
    if len(json.dumps(params).encode()) > 24000:
        return False, "browser_required"
    result = channel.ask(params, parent_id=parent_id)
    if not isinstance(result, dict):
        return False, "unavailable"
    action = result.get("action")
    if isinstance(action, str) and action in {"decline", "cancel"}:
        # Declining this form denies only the triggering call, not every queued call.
        try:
            hub.tool_policy.decide_many([approval_id], False)
        except RpcError:
            pass
        return False, action
    content = result.get("content")
    if (
        action != "accept"
        or not isinstance(content, dict)
        or set(content) - set(properties)
        or any(not isinstance(value, bool) for value in content.values())
    ):
        return False, "invalid_response"
    selected = [row["id"] for index, row in enumerate(rows) if content.get("request_" + str(index))]
    if not selected:
        return False, "not_selected"
    try:
        hub.tool_policy.decide_many(selected, True)
    except RpcError:
        return False, "changed"
    return approval_id in selected, "approved"
