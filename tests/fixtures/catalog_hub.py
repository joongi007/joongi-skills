"""Isolated catalog with connected tools, an unstarted server and a second profile."""

import json
import sys
import threading
from pathlib import Path

from joongi_hub.local_auth import ui_url
from joongi_hub.server import HubServer
from joongi_hub.service import Hub
from tests.fixtures.credential_store import test_store
from tests.fixtures.oauth_server import OAuthProvider

root = Path(sys.argv[1])
provider = OAuthProvider()
threading.Thread(target=provider.serve_forever, daemon=True).start()
hub = Hub(Path.cwd() / "skills", root / "state", credential_store_factory=test_store)
config = hub.register(
    {
        "id": "catalog",
        "name": "Catalog fixture",
        "transport": "http",
        "url": provider.resource,
        "auth": {"type": "bearer"},
        "policy": {"allowed_tools": ["echo"]},
    }
)
provider.access.add("fake-catalog-credential")
hub.auth.set_manual(config, {"token": "fake-catalog-credential"})
hub.probe("catalog")
hub.register(
    {"id": "sleeping", "name": "Unstarted MCP", "transport": "stdio", "command": sys.executable}
)
(root / "project").mkdir(parents=True)
hub.projects.put(
    {
        "id": "isolated",
        "name": "Isolated project",
        "root": str(root / "project"),
        "common_servers": [],
        "common_skills": ["usual-korean"],
    }
)
panel = HubServer(("127.0.0.1", 0), hub)
print(
    json.dumps({"ui_url": ui_url(f"http://127.0.0.1:{panel.server_port}", root / "state")}),
    flush=True,
)
try:
    panel.serve_forever()
finally:
    panel.server_close()
    hub.close()
    provider.shutdown()
    provider.server_close()
