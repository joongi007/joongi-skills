"""Disposable browser fixture: own home/project, independent OAuth HTTP provider."""

import json
import os
import sys
import threading
from pathlib import Path

from joongi_hub.server import HubServer
from joongi_hub.service import Hub
from tests.fixtures.oauth_server import OAuthProvider

root = Path(sys.argv[1])
os.environ["JOONGI_HUB_MANAGED_HOME"] = str(root / "home")
(root / "home/.codex").mkdir(parents=True)
(root / "project").mkdir()
provider = OAuthProvider()
threading.Thread(target=provider.serve_forever, daemon=True).start()
hub = Hub(Path.cwd() / "skills", root / "state")
hub.register(
    {
        "id": "protected",
        "name": "인증 검증 서버",
        "transport": "http",
        "url": provider.resource,
        "auth": {"type": "oauth", "client_id": "registered-client"},
    }
)
panel = HubServer(("127.0.0.1", 0), hub)
print(
    json.dumps({"url": f"http://127.0.0.1:{panel.server_port}", "project": str(root / "project")}),
    flush=True,
)
try:
    panel.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    panel.server_close()
    hub.close()
    provider.shutdown()
    provider.server_close()
