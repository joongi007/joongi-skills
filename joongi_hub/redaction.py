"""Reject known credential reflection; this is not a general-purpose DLP system."""

import base64
import json
from urllib.parse import quote, quote_plus

from joongi_hub.errors import RpcError


def reject_secret_reflection(value, values):
    text = json.dumps(value, ensure_ascii=False)
    for value in set(values):
        if not isinstance(value, str) or not value:
            continue
        encoded = value.encode()
        variants = {
            value,
            json.dumps(value, ensure_ascii=False)[1:-1],
            quote(value, safe=""),
            quote_plus(value),
            base64.b64encode(encoded).decode(),
            base64.urlsafe_b64encode(encoded).decode(),
        }
        for pattern in variants:
            if len(pattern) >= 6 and pattern in text:
                raise RpcError(
                    -32044, "MCP 응답에서 인증 비밀값 반사를 차단했습니다. 서버 상태를 확인하세요."
                )
