"""Actual SDK clients exercise a protected native tool with an output contract."""

import sys
import threading
from pathlib import Path
from unittest.mock import patch

from joongi_hub.__main__ import serve_stdio
from joongi_hub.service import Hub
from tests.fixtures.credential_store import test_store
from tests.fixtures.oauth_server import OAuthProvider

provider = OAuthProvider()
threading.Thread(target=provider.serve_forever, daemon=True).start()
handler = provider.mcp.handle


def typed(message):
    value = handler(message)
    if message.get("method") == "tools/list":
        for tool in value["result"]["tools"]:
            if tool["name"] == "echo":
                tool["outputSchema"] = {
                    "type": "object",
                    "properties": {"data": {"$ref": "#/$defs/value"}},
                    "required": ["data"],
                    "$defs": {"value": {"type": "string"}},
                }
    return value


provider.mcp.handle = typed
hub = Hub(
    Path(__file__).resolve().parents[2] / "skills",
    Path(sys.argv[1]),
    credential_store_factory=test_store,
)
config = hub.register(
    {
        "id": "protected",
        "transport": "http",
        "url": provider.resource,
        "protocol_version": "2025-11-25",
        "auth": {"type": "bearer"},
    }
)
provider.access.add("fake-sdk-credential")
hub.auth.set_manual(config, {"token": "fake-sdk-credential"})
hub.probe("protected")
try:
    with patch("joongi_hub.agent_approval.open_browser", return_value=True):
        serve_stdio(hub)
finally:
    hub.close()
    provider.shutdown()
    provider.server_close()
