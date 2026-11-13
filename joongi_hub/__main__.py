"""CLI entry points for the local panel and MCP stdio server."""

import argparse
import json
import os
import sys
from pathlib import Path

from joongi_hub import __version__
from joongi_hub.connections import ConnectionSettings, running, select_bridge
from joongi_hub.errors import RpcError
from joongi_hub.lifecycle import manage
from joongi_hub.local_auth import LocalAuth
from joongi_hub.server import HubServer
from joongi_hub.service import Hub
from joongi_hub.state_store import (
    default_directory,
    describe,
    import_servers,
    restore_backup,
    temporary,
)
from joongi_hub.storage import atomic_json
from joongi_hub.upstream import MAX_MESSAGE, HttpTransport


def serve_stdio(hub, bridge=None, profile="global"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    context = {"owner": "stdio-" + str(os.getpid()), "profile": profile}
    while True:
        line = sys.stdin.buffer.readline(MAX_MESSAGE + 1)
        if not line:
            break
        if len(line) > MAX_MESSAGE:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Message exceeds 4 MiB"},
                    }
                ),
                flush=True,
            )
            break
        try:
            message = json.loads(line)
        except (ValueError, UnicodeError):
            result = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Invalid JSON"},
            }
        else:
            if not isinstance(message, dict):
                result = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Invalid JSON-RPC request"},
                }
            elif bridge:
                try:
                    params = message.setdefault("params", {})
                    if isinstance(params, dict):
                        meta = params.setdefault("_meta", {})
                        if isinstance(meta, dict):
                            if meta.get("joongi-hub/profile", profile) != profile:
                                raise RpcError(-32602, "이 연결의 프로젝트를 변경할 수 없습니다.")
                            meta["joongi-hub/profile"] = profile
                    params = message.get("params", {})
                    meta = params.get("_meta", {}) if isinstance(params, dict) else {}
                    if isinstance(meta, dict) and meta.get(
                        "io.modelcontextprotocol/protocolVersion"
                    ):
                        bridge.version = meta["io.modelcontextprotocol/protocolVersion"]
                    result = bridge.exchange(message)
                    if message.get("method") == "initialize" and result and "result" in result:
                        bridge.version = result["result"]["protocolVersion"]
                except RpcError as exc:
                    result = {"jsonrpc": "2.0", "id": message.get("id"), "error": exc.as_dict()}
            else:
                result = hub.rpc(message, context)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False), flush=True)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Local skills and MCP hub")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    for name in (
        "serve",
        "stdio",
        "start",
        "stop",
        "restart",
        "status",
        "open",
        "configure",
        "state",
        "credentials",
    ):
        command = subparsers.add_parser(name)
        command.add_argument(
            "--state-dir",
            type=Path,
            default=default_directory(),
        )
        command.add_argument(
            "--skills-dir",
            type=Path,
            default=Path(
                os.environ.get(
                    "JOONGI_HUB_SKILLS_DIR", Path(__file__).resolve().parent.parent / "skills"
                )
            ),
        )
        if name in {"stdio", "configure"}:
            command.add_argument("--mode", choices=["stdio", "hybrid", "http"])
            command.add_argument("--url", help="Local HTTP Hub base URL")
            command.add_argument("--fallback", choices=["stdio", "error"])
        if name in {"stdio", "configure"}:
            command.add_argument(
                "--profile", default="global", help="Registered project ID, or global"
            )
        if name == "serve":
            command.add_argument("--host", choices=["127.0.0.1", "localhost"], default="127.0.0.1")
        if name in {"serve", "start", "restart", "open"}:
            command.add_argument("--port", type=int, default=8765 if name == "serve" else None)
        if name == "state":
            operation = command.add_mutually_exclusive_group()
            operation.add_argument(
                "--import-from",
                type=Path,
                help="Merge server registrations from another state directory",
            )
            operation.add_argument(
                "--restore-backup",
                action="store_true",
                help="Restore a missing server registry from its last committed backup",
            )
        if name == "credentials":
            command.add_argument(
                "--migrate",
                action="store_true",
                help="Move legacy plaintext credentials into the OS-protected store",
            )
    args = parser.parse_args(argv or None)
    if not args.command:
        parser.print_help()
        return 0
    args.state_dir = args.state_dir.expanduser().resolve()
    args.skills_dir = args.skills_dir.expanduser().resolve()
    if args.command == "credentials":
        from joongi_hub.auth import AuthManager

        manager = AuthManager(args.state_dir)
        try:
            with manager.lock:
                if (
                    manager.path.is_symlink()
                    or manager.path.parent.is_symlink()
                    or (manager.path.exists() and manager.path.stat().st_size > 1024**2)
                ):
                    raise RpcError(-32045, "인증 저장소 경로·크기를 확인하세요.")
                value = (
                    manager.store.migrate()
                    if args.migrate
                    else {
                        "storage": manager.store.vault.name,
                        "exists": manager.path.exists(),
                        "requires_plaintext_migration": manager.path.exists()
                        and "protected" not in json.loads(manager.path.read_text(encoding="utf-8")),
                    }
                )
            print(json.dumps(value, ensure_ascii=False))
            return 0
        except (RpcError, OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1
    if args.command == "state":
        try:
            result = {}
            if args.import_from:
                result = import_servers(args.state_dir, args.import_from)
            elif args.restore_backup:
                result = restore_backup(args.state_dir)
            print(json.dumps({**result, **describe(args.state_dir)}, ensure_ascii=False))
            return 0
        except (RpcError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.command in {"serve", "stdio", "start", "open", "restart"}:
        print(f"Joongi Hub state: {args.state_dir}", file=sys.stderr)
        if temporary(args.state_dir):
            print(
                "WARNING: 임시 저장소입니다. 공용 사용에는 기본 영구 저장소를 사용하세요.",
                file=sys.stderr,
            )
    endpoint = args.state_dir / "endpoint.json"
    bridge = None
    if args.command in {"start", "stop", "restart", "status", "open"}:
        try:
            print(
                json.dumps(
                    manage(
                        args.command, args.state_dir, args.skills_dir, getattr(args, "port", None)
                    ),
                    ensure_ascii=False,
                )
            )
            return 0
        except (RpcError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.command == "configure":
        hub = Hub(args.skills_dir, args.state_dir)
        try:
            scoped = hub.scoped(args.profile)
            settings = scoped.connection_settings.get()
            for key in ("mode", "url", "fallback"):
                if getattr(args, key) is not None:
                    settings[key] = getattr(args, key)
            scoped.connection_settings.put(settings)
            print(
                json.dumps(
                    {"settings": settings, "connection": hub.profile_connection(args.profile)},
                    ensure_ascii=False,
                )
            )
            return 0
        except RpcError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        finally:
            hub.close()
    hub = None
    if args.command == "stdio":
        try:
            settings = ConnectionSettings(args.state_dir)
            if args.profile != "global":
                from joongi_hub.profiles import Projects

                projects = Projects(args.state_dir)
                settings = ConnectionSettings(
                    projects.state_directory(projects.get(args.profile)), settings
                )
            selected = settings.get()
            for key in ("mode", "url", "fallback"):
                if getattr(args, key) is not None:
                    selected[key] = getattr(args, key)
            selected = ConnectionSettings.validate(selected)
            url = select_bridge(args.state_dir, selected, explicit_url=args.url is not None)
            if url:
                from joongi_hub.connections import mcp_url
                from joongi_hub.local_auth import local_token

                local_token(args.state_dir, args.profile)
                bridge = HttpTransport(
                    {"url": mcp_url(url, args.profile)},
                    auth=LocalAuth(args.state_dir, args.profile),
                )
        except RpcError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    hub = None if bridge else Hub(args.skills_dir, args.state_dir)
    if os.name != "nt":
        import signal

        def terminate(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, terminate)
    try:
        if args.command == "serve":
            if running(args.state_dir):
                parser.error(
                    "A panel already uses this state directory; open its URL or choose --state-dir"
                )
            server = HubServer((args.host, args.port), hub)
            atomic_json(
                endpoint,
                {
                    "pid": os.getpid(),
                    "url": f"http://127.0.0.1:{server.server_address[1]}",
                    "instance": server.instance_id,
                },
            )
            print(f"Joongi Hub http://127.0.0.1:{server.server_address[1]}", file=sys.stderr)
            try:
                server.serve_forever(poll_interval=0.25)
            finally:
                server.server_close()
                endpoint.unlink(missing_ok=True)
        else:
            serve_stdio(hub.scoped(args.profile) if hub else None, bridge, args.profile)
    except KeyboardInterrupt:
        pass
    finally:
        if hub:
            hub.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
