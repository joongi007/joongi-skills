"""Isolated owner UI with synthetic pending calls, no external service access."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.service import Hub
from tests.fixtures.credential_store import test_store

root = Path(__file__).resolve().parents[2]
hub = Hub(root / "skills", Path(sys.argv[1]) / "state", credential_store_factory=test_store)
config = hub.register(
    {"id": "notion-fixture", "transport": "http", "url": "http://127.0.0.1:12999/mcp", "policy": {}}
)
settings = []
approvals = []
try:
    with (
        patch(
            "joongi_hub.agent_panel.open_browser",
            side_effect=lambda url: settings.append(url) or True,
        ),
        patch(
            "joongi_hub.agent_approval.open_browser",
            side_effect=lambda url: approvals.append(url) or True,
        ),
    ):
        for name in ["notion-fetch", "notion-search"]:
            try:
                hub.tool_policy.authorize(config, {"name": name}, {"page": "synthetic-only"})
            except RpcError as error:
                hub.agent_approvals.request(error.data["approval_id"])
        result = hub.agent_panels.open()
    print(
        json.dumps({"settings": settings[0], "approvals": approvals, "result": result}), flush=True
    )
    for line in sys.stdin:
        if line.strip() == "status":
            hub.invoke("hub_status", {})
            print(
                json.dumps(
                    {
                        "mcp_alive": True,
                        "temporary_running": bool(hub.agent_panels.server),
                        "grants": len(hub.tool_policy.grants()),
                    }
                ),
                flush=True,
            )
finally:
    hub.close()
