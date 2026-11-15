"""Two MCP groups and another OS process feed one synthetic approval inbox."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.service import Hub
from tests.fixtures.credential_store import test_store

root = Path(__file__).resolve().parents[2]
state = Path(sys.argv[1]) / "state"
hub = Hub(root / "skills", state, credential_store_factory=test_store)
urls = []
ids = []


def enqueue(index, server):
    try:
        hub.tool_policy.authorize(
            {"id": server, "policy": {}},
            {"name": "read"},
            {"index": index, "message": '<img src=x onerror="window.injected=true">'},
        )
    except RpcError as exc:
        return exc.data["approval_id"]


try:
    with patch(
        "joongi_hub.agent_approval.open_browser", side_effect=lambda url: urls.append(url) or True
    ):
        ids.extend([enqueue(1, "notion"), enqueue(2, "github")])
        hub.agent_approvals.request(ids[0])
        print(json.dumps({"url": urls[0], "ids": ids}), flush=True)
        for line in sys.stdin:
            if line.strip() == "enqueue":
                script = """import json,sys
from pathlib import Path
from unittest.mock import patch
from joongi_hub.service import Hub
from joongi_hub.errors import RpcError
from tests.fixtures.credential_store import test_store
h=Hub(Path(sys.argv[1])/'skills',Path(sys.argv[2]),credential_store_factory=test_store)
try:
 try:h.tool_policy.authorize({'id':'notion','policy':{}},{'name':'read'},{'index':3})
 except RpcError as e: identity=e.data['approval_id']
 with patch('joongi_hub.agent_approval.open_browser',
            side_effect=AssertionError('Duplicate window')):
  result=h.agent_approvals.request(identity)
 print(json.dumps({'id':identity,'reused':result['window_reused']}))
finally:h.close()
"""
                child = subprocess.run(
                    [sys.executable, "-B", "-c", script, str(root), str(state)],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=True,
                )
                row = json.loads(child.stdout)
                ids.append(row["id"])
                print(json.dumps({**row, "launches": len(urls)}), flush=True)
            elif line.strip() == "status":
                print(
                    json.dumps(
                        {
                            "statuses": [hub.tool_policy.get(i)["status"] for i in ids],
                            "launches": len(urls),
                        }
                    ),
                    flush=True,
                )
finally:
    hub.close()
