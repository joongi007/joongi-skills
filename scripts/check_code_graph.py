#!/usr/bin/env python3
"""Inspect, register and verify a real project's read-only code graph MCP."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from joongi_hub.code_graph import server_config  # noqa: E402
from joongi_hub.errors import RpcError  # noqa: E402
from joongi_hub.service import Hub  # noqa: E402
from joongi_hub.state_store import default_directory  # noqa: E402
from joongi_hub.storage import Registry  # noqa: E402


def register(config, state_dir, replace=False):
    registry = Registry(state_dir)
    existing = next((item for item in registry.list() if item["id"] == config["id"]), None)
    if existing and existing != config and not replace:
        raise RpcError(
            -32602, "Server id already belongs to another registration; choose --id or --replace"
        )
    registry.put(config)


def verify(config, state_dir):
    root = Path(__file__).resolve().parents[1]
    hub = Hub(root / "skills", state_dir)
    try:
        # Verification is isolated unless the caller explicitly registered first.
        existing = next((item for item in hub.registry.list() if item["id"] == config["id"]), None)
        if existing != config:
            raise RpcError(-32602, "Selected state does not contain the requested registration")
        probe = hub.probe(config["id"])
        status = hub.invoke(config["id"] + "__graph_status", {})["structuredContent"]
        symbols = hub.invoke(config["id"] + "__graph_symbols", {"query": "", "limit": 5})[
            "structuredContent"
        ]
        return {
            "protocol": probe["protocol_version"],
            "tools": [item["name"] for item in probe["tools"]],
            "status": status,
            "sample_symbols": symbols["symbols"],
        }
    finally:
        hub.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, default=default_directory())
    parser.add_argument("--id", default="code-graph")
    parser.add_argument(
        "--register", action="store_true", help="Save registration in explicit state directory"
    )
    parser.add_argument("--replace", action="store_true", help="Replace a conflicting registration")
    parser.add_argument("--print-config", action="store_true")
    args = parser.parse_args(argv)
    config = server_config(args.target, args.id)
    if args.print_config:
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return 0
    if args.register and args.state_dir is None:
        parser.error("--register requires an explicit --state-dir")
    if args.register:
        register(config, args.state_dir, args.replace)
        result = verify(config, args.state_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="joongi-graph-check-") as temporary:
            directory = Path(temporary)
            register(config, directory)
            result = verify(config, directory)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
