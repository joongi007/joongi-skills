"""Synthetic owner browser fixture. No real credentials or external calls."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.service import Hub
from tests.fixtures.credential_store import test_store

root = Path(__file__).resolve().parents[2]
hub = Hub(root / "skills", Path(sys.argv[1]) / "state", credential_store_factory=test_store)
urls = []
try:
    with patch(
        "joongi_hub.agent_approval.open_browser", side_effect=lambda url: urls.append(url) or True
    ):
        for action in ("approve", "deny"):
            try:
                hub.tool_policy.authorize(
                    {
                        "id": "synthetic-notion",
                        "transport": "http",
                        "url": "https://example.invalid/mcp",
                        "policy": {},
                    },
                    {"name": "notion-fetch"},
                    {"page": '<img src=x onerror="window.injected=true">', "test": action},
                )
            except RpcError as exc:
                hub.agent_approvals.request(exc.data["approval_id"])
    print(json.dumps({"urls": urls}), flush=True)
    sys.stdin.read()
finally:
    hub.close()
