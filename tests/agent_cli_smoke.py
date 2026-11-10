"""Check real installed agent CLIs without authentication or model calls.

Run: python3 tests/agent_cli_smoke.py --codex /path/codex --claude /path/claude
All configuration, caches and Hub state use a disposable home. This verifies
Codex configuration recognition and Claude's own MCP connection health check.
"""

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.install_manager import Installer  # noqa: E402


def run(command, environment, directory):
    result = subprocess.run(
        command, cwd=directory, env=environment, timeout=45, capture_output=True, text=True
    )
    if result.returncode:
        raise RuntimeError(f"{Path(command[0]).name} failed: {result.stderr.strip()}")
    return result.stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default=shutil.which("codex"))
    parser.add_argument("--claude", default=shutil.which("claude"))
    parser.add_argument("--mode", choices=["stdio", "hybrid", "http"], default="stdio")
    args = parser.parse_args(argv)
    if not args.codex or not args.claude:
        parser.error("Both real Codex and Claude CLI executables are required")
    with (
        tempfile.TemporaryDirectory(prefix="joongi-real-agent-") as temporary,
        contextlib.ExitStack() as cleanup,
    ):
        directory = Path(temporary)
        installer = Installer(directory, ROOT)
        state = directory / ".local/share/joongi-hub"
        server = None
        if args.mode != "stdio":
            from joongi_hub.lifecycle import manage

            server = manage("start", state, ROOT / "skills", 0)
            cleanup.callback(manage, "stop", state, ROOT / "skills")
            if args.mode == "http":
                installer.connection = {"url": server["url"] + "/mcp"}
            else:
                installer.connection = {
                    "command": str(directory / ".local/bin/joongi-hub"),
                    "args": ["stdio", "--mode", "hybrid"],
                }
        installer.install(["claude", "codex"])
        environment = {
            key: os.environ[key]
            for key in ("PATH", "LANG", "LC_ALL", "TERM", "TMPDIR")
            if key in os.environ
        }
        environment.update(
            HOME=str(directory),
            CODEX_HOME=str(directory / ".codex"),
            XDG_CONFIG_HOME=str(directory / ".config"),
            XDG_DATA_HOME=str(directory / ".local/share"),
            XDG_CACHE_HOME=str(directory / ".cache"),
            # Claude's user-scoped .claude.json lives inside this overridden dir.
            CLAUDE_CONFIG_DIR=str(directory),
            CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
            DISABLE_TELEMETRY="1",
            JOONGI_HUB_STATE_DIR=str(directory / "hub-state"),
        )
        codex_version = run([args.codex, "--version"], environment, directory).strip()
        claude_version = run([args.claude, "--version"], environment, directory).strip()
        servers = json.loads(run([args.codex, "mcp", "list", "--json"], environment, directory))
        selected = next((item for item in servers if item["name"] == "joongi-hub"), None)
        if not selected or not selected["enabled"]:
            raise RuntimeError("Codex did not recognize the installed MCP registration")
        detail = json.loads(
            run([args.codex, "mcp", "get", "joongi-hub", "--json"], environment, directory)
        )
        expected = str(directory / ".local/bin/joongi-hub")
        if args.mode == "http":
            if detail["transport"].get("url") != server["url"] + "/mcp":
                raise RuntimeError("Codex resolved an unexpected HTTP URL")
        elif detail["transport"].get("command") != expected or detail["transport"]["args"] != (
            ["stdio", "--mode", "hybrid"] if args.mode == "hybrid" else ["stdio"]
        ):
            raise RuntimeError("Codex resolved an unexpected MCP command")
        claude = run([args.claude, "mcp", "get", "joongi-hub"], environment, directory)
        if "Connected" not in claude or "User config" not in claude:
            raise RuntimeError("Claude did not connect to the installed user-scoped Hub")
        print(f"{codex_version}: installed {args.mode} MCP configuration recognized")
        print(f"{claude_version}: real MCP connection health check passed")
        print("No credentials or model API calls were used; temporary home cleaned on exit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
