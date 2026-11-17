"""Actual SDK clients exercise a protected native tool with an output contract."""

import json
import sys
import threading
from pathlib import Path
from unittest.mock import patch

from joongi_hub.__main__ import serve_stdio
from joongi_hub.local_auth import LocalAuth
from joongi_hub.server import HubServer
from joongi_hub.service import Hub
from joongi_hub.upstream import HttpTransport
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
    if message.get("method") == "tools/call" and message.get("params", {}).get("name") == "echo":
        value["result"]["structuredContent"] = {"data": message["params"]["arguments"]["message"]}
        with (Path(sys.argv[1]) / "executed.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(message["params"]["arguments"]) + "\n")
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
panel = bridge = None
if "--bridge" in sys.argv:
    panel = HubServer(("127.0.0.1", 0), hub)
    threading.Thread(target=panel.serve_forever, daemon=True).start()
    bridge = HttpTransport(
        {"url": f"http://127.0.0.1:{panel.server_port}/mcp"},
        auth=LocalAuth(hub.state_dir, "global"),
    )
try:

    def browser(url):
        (Path(sys.argv[1]) / "browser-opened").touch()
        return True

    with patch("joongi_hub.agent_approval.open_browser", side_effect=browser):
        serve_stdio(hub, bridge)
finally:
    if bridge:
        bridge.close()
    if panel:
        panel.shutdown()
        panel.server_close()
    hub.close()
    provider.shutdown()
    provider.server_close()
