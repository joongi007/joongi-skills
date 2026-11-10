#!/usr/bin/env python3
"""Register and verify an isolated code-review-graph MCP with analysis tools only."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from joongi_hub.errors import RpcError  # noqa: E402
from joongi_hub.review_graph import server_config as project_server_config  # noqa: E402
from joongi_hub.service import Hub  # noqa: E402
from joongi_hub.state_store import default_directory  # noqa: E402
from joongi_hub.upstream import validate_server  # noqa: E402
from scripts.check_code_graph import register  # noqa: E402

TOOLS = (
    "list_graph_stats_tool",
    "query_graph_tool",
    "get_impact_radius_tool",
    "get_review_context_tool",
    "get_minimal_context_tool",
    "find_large_functions_tool",
    "get_docs_section_tool",
)
BOOTSTRAP = (
    "import os,runpy,sys;"
    "os.environ['CRG_HOME']=sys.argv.pop(1);"
    "os.environ['CRG_DATA_DIR']=sys.argv.pop(1);"
    "sys.argv=['code-review-graph',*sys.argv[1:]];"
    "runpy.run_module('code_review_graph',run_name='__main__')"
)


def server_config(interpreter, target, data_dir, server_id="code-review-graph"):
    # Resolving a venv interpreter symlink would select the base Python and lose
    # its installed packages. Keep its absolute lexical path instead.
    interpreter = Path(interpreter).expanduser().absolute()
    target = Path(target).resolve(strict=True)
    data_dir = Path(data_dir).resolve()
    if not interpreter.is_file() or not target.is_dir():
        raise ValueError("An installed Python interpreter and project directory are required")
    return validate_server(
        {
            "id": server_id,
            "name": "Code Review Graph · " + target.name,
            "transport": "stdio",
            "command": str(interpreter),
            "args": [
                "-c",
                BOOTSTRAP,
                str(data_dir / "home"),
                str(data_dir / "data"),
                "serve",
                "--repo",
                str(target),
                "--tools",
                ",".join(TOOLS),
            ],
            "protocol_version": "2025-11-25",
            "enabled": True,
        }
    )


def verify(config, state_dir, sample_file=None):
    hub = Hub(Path(__file__).resolve().parents[1] / "skills", state_dir)
    try:
        probe = hub.probe(config["id"])
        names = {tool["name"] for tool in probe["tools"]}
        if names != set(TOOLS):
            raise RpcError(-32000, "Unexpected analysis-tool surface", {"tools": sorted(names)})
        result = hub.invoke(config["id"] + "__list_graph_stats_tool", {})
        if result.get("isError"):
            raise RpcError(-32000, "Code Review Graph statistics failed")
        stats = result.get("structuredContent", {})
        if stats.get("status") != "ok" or not stats.get("files_count"):
            raise RpcError(-32000, "Build the project graph before registering it")
        query = None
        if sample_file:
            query = hub.invoke(
                config["id"] + "__query_graph_tool",
                {
                    "pattern": "file_summary",
                    "target": sample_file,
                    "max_results": 5,
                },
            )
            if query.get("isError"):
                raise RpcError(-32000, "Code Review Graph query failed")
            if query.get("structuredContent", {}).get("status") != "ok":
                raise RpcError(-32000, "Code Review Graph query did not succeed")
        return {
            "protocol": probe["protocol_version"],
            "tools": sorted(names),
            "stats": stats,
            "query": query,
        }
    finally:
        hub.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--data-dir", type=Path, default=default_directory() / "review-graphs")
    parser.add_argument(
        "--fixed-project", action="store_true", help="Explicitly bind this server to --target"
    )
    parser.add_argument("--id", default="code-review-graph")
    parser.add_argument("--print-config", action="store_true")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--state-dir", type=Path, default=default_directory())
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--sample-file", help="Optional project-relative file for a query check")
    args = parser.parse_args()
    if args.fixed_project and args.target is None:
        parser.error("--fixed-project requires --target")
    config = (
        server_config(args.python, args.target, args.data_dir, args.id)
        if args.fixed_project
        else project_server_config(args.python, args.data_dir, args.id)
    )
    if args.print_config:
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return
    if args.register:
        if args.state_dir is None:
            parser.error("--register requires --state-dir")
        # Check in temporary state before persisting a usable registration.
    with tempfile.TemporaryDirectory(prefix="joongi-review-graph-") as directory:
        state = Path(directory)
        register(config, state)
        if args.fixed_project:
            result = verify(config, state, args.sample_file)
        else:
            hub = Hub(Path(__file__).resolve().parents[1] / "skills", state)
            try:
                probe = hub.probe(config["id"])
                if len(probe["tools"]) != 9 or any(
                    "repo_root" not in tool["inputSchema"]["required"] for tool in probe["tools"]
                ):
                    raise RpcError(-32000, "Project-selecting graph tools were not discovered")
                result = {"protocol": probe["protocol_version"], "tools": probe["tools"]}
            finally:
                hub.close()
    if args.register:
        register(config, args.state_dir, args.replace)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
