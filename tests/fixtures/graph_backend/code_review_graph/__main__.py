"""Tiny subprocess backend: models per-repo graph provenance, never reads user trees."""

import json
import os
import sys
from pathlib import Path

root = Path(os.environ["CRG_REPO_ROOT"])
data = Path(os.environ["CRG_DATA_DIR"])
if sys.argv[1] == "build":
    data.mkdir(parents=True, exist_ok=True)
    (data / "graph.db").write_text(
        json.dumps({"repo_root": str(root), "files": sorted(p.name for p in root.glob("*.py"))})
    )
else:
    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message:
            continue
        method = message["method"]
        if method == "initialize":
            value = {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fixture", "version": "1"},
            }
        elif method == "tools/list":
            value = {"tools": []}
        elif method == "tools/call":
            args = message["params"]["arguments"]
            assert args["repo_root"] == str(root)
            value = {
                "content": [],
                "structuredContent": json.loads((data / "graph.db").read_text()),
            }
        else:
            value = {}
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": value}), flush=True)
