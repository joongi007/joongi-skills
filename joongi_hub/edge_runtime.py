"""Owner-prepared Windows Edge companion. Explicit personal-account trust boundary."""

import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import uuid
import zipfile
from pathlib import Path
from urllib.request import urlopen

from joongi_hub.browser_proxy import origins
from joongi_hub.errors import RpcError

FILES = Path(__file__).with_name("edge_companion")
NODE_URL = "https://nodejs.org/dist/v24.22.3/node-v24.22.3-win-x64.zip"
NODE_HASH = "e612af99f626ab415ea225af6bce5c971feb448cb5cae250bb1c3fa50c5f7d9f"
EXTENSION = (
    "https://chromewebstore.google.com/detail/playwright-extension/mmlmfjhmonkocbjadbfplnigmagldckm"
)


def powershell():
    path = (
        (
            Path(os.environ.get("SystemRoot", "C:\\Windows"))
            / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        if os.name == "nt"
        else Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    )
    if not path.is_file():
        raise RpcError(
            -32046, "개인 Edge 연결에는 Windows 또는 Windows 연동을 켠 WSL이 필요합니다."
        )
    return str(path)


def ps_command(script):
    return [
        powershell(),
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-EncodedCommand",
        base64.b64encode(script.encode("utf-16-le")).decode("ascii"),
    ]


def validate_edge(settings):
    if (
        set(settings) != {"backend", "edge_connection", "edge_fingerprint"}
        or not isinstance(settings.get("edge_connection"), str)
        or not re.fullmatch("[a-f0-9]{32}", settings["edge_connection"])
        or not isinstance(settings.get("edge_fingerprint"), str)
        or not re.fullmatch("[a-f0-9]{64}", settings["edge_fingerprint"])
    ):
        raise RpcError(
            -32602,
            "준비한 Edge 연결 ID와 fingerprint만 지정하세요. 임의 경로·명령은 받지 않습니다.",
        )


def command(settings):
    validate_edge(settings)
    script = (FILES / "gate.ps1").read_text(encoding="utf-8")
    script = script.replace("CONNECTION_ID", settings["edge_connection"]).replace(
        "PUBLIC_FINGERPRINT", settings["edge_fingerprint"]
    )
    return ps_command(script)


def download(url, limit=96 * 1024**2):
    # URLs come only from the pinned lock or the fixed Node release above.
    with urlopen(url, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Prepared package exceeds size limit")
    return data


def unpack_package(data, destination):
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive:
            parts = member.name.split("/")
            if (
                parts[0] != "package"
                or any(p in {"..", ""} for p in parts[1:])
                or any("\\" in p or ":" in p for p in parts)
                or member.issym()
                or member.islnk()
            ):
                raise ValueError("Unsafe package member")
            if member.isdir():
                continue
            if not member.isfile() or member.size > 64 * 1024**2:
                raise ValueError("Unsupported package member")
            total += member.size
            if total > 192 * 1024**2:
                raise ValueError("Expanded package too large")
            target = destination.joinpath(*parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("xb") as output:
                output.write(source.read())


def discover_tools(root):
    """Pinned official schema discovery only; never opens a browser."""
    from joongi_hub.edge_companion.worker import TOOLS
    from joongi_hub.sandbox import _helper_environment

    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "joongi-prepare", "version": "0.1.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    result = subprocess.run(
        [
            str(root / "node.exe"),
            str(root / "node_modules/@playwright/mcp/cli.js"),
            "--extension",
            "--background",
        ],
        input="".join(json.dumps(m) + "\n" for m in messages),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        cwd=root,
        env=_helper_environment(),
    )
    replies = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    tools = next(
        (r["result"]["tools"] for r in replies if r.get("id") == 2 and "result" in r), None
    )
    if tools is None:
        raise ValueError("Official tool schema discovery failed")
    selected = [t for t in tools if t["name"] in TOOLS]
    if {t["name"] for t in selected} != TOOLS:
        raise ValueError("Pinned official tools changed")
    for tool in selected:
        properties = tool["inputSchema"].get("properties", {})
        for key in ("filename", "fullPage", "isolatedContext"):
            properties.pop(key, None)
        if tool["name"] == "browser_take_screenshot":
            properties["type"] = {"type": "string", "enum": ["jpeg"]}
            properties["scale"] = {"type": "string", "enum": ["css"]}
        if tool["name"] == "browser_wait_for":
            properties["time"] = {"type": "number", "minimum": 0, "maximum": 5}
    return selected


def prepare(allowed, profile="Default"):
    """Must run on Windows as an explicit owner CLI operation."""
    if os.name != "nt":
        raise RpcError(
            -32046, "Windows Python에서 준비하거나 WSL에서 --windows-python을 지정하세요."
        )
    if not re.fullmatch(r"Default|Profile [1-9][0-9]{0,2}", profile):
        raise RpcError(-32602, "Edge 프로필은 Default 또는 Profile N 형식이어야 합니다.")
    allowed = origins(allowed)
    from joongi_hub.credential_store import dpapi

    # Known folder API, not an MCP-supplied path or an inherited LOCALAPPDATA override.
    known = subprocess.run(
        ps_command("[Console]::Write([Environment]::GetFolderPath('LocalApplicationData'))"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=True,
    ).stdout
    ident = uuid.uuid4().hex
    root = Path(known) / "joongi-hub/edge" / ident
    root.mkdir(parents=True)
    # Remove inherited ACEs and grant only the current owner. The prepared tree is private.
    acl = (
        "$p='"
        + str(root).replace("'", "''")
        + "';$s=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;"
        + (
            "& ($env:SystemRoot+'\\System32\\icacls.exe') $p /inheritance:r "
            "/grant:r ('*'+$s+':(OI)(CI)F') | Out-Null;"
            "if($LASTEXITCODE -ne 0){exit 1}"
        )
    )
    subprocess.run(ps_command(acl), check=True, capture_output=True, timeout=10)
    data = download(NODE_URL)
    if hashlib.sha256(data).hexdigest() != NODE_HASH:
        raise ValueError("Official Node archive hash mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        node = archive.read("node-v24.22.3-win-x64/node.exe")
    (root / "node.exe").write_bytes(node)
    lock = json.loads(
        Path(__file__).with_name("browser_container").joinpath("package-lock.json").read_text()
    )
    for relative, package in lock["packages"].items():
        if not relative:
            continue
        if not package["resolved"].startswith("https://registry.npmjs.org/"):
            raise ValueError("Unexpected package registry")
        data = download(package["resolved"])
        if (
            "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
            != package["integrity"]
        ):
            raise ValueError("Official package integrity mismatch")
        unpack_package(data, root / relative)
    (root / "worker.py").write_bytes((FILES / "worker.py").read_bytes())
    (root / "settings.json").write_text(
        json.dumps({"profile": profile, "origins": allowed}), encoding="utf-8"
    )
    (root / "tools.json").write_text(json.dumps(discover_tools(root)), encoding="utf-8")
    descriptor = {
        "version": 1,
        "python": sys.executable,
        "python_hash": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
        "files": {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file()
        },
    }
    plain = json.dumps(descriptor, sort_keys=True).encode()
    (root / "descriptor.dpapi").write_bytes(dpapi(plain))
    settings = {
        "backend": "first-party-edge",
        "edge_connection": ident,
        "edge_fingerprint": hashlib.sha256(plain).hexdigest(),
    }
    # Reuse runtime verification; fail preparation on untrusted Python or changed files.
    # No browser is started here: worker stdin is EOF.
    checked = subprocess.run(command(settings), input=b"", capture_output=True, timeout=30)
    if checked.returncode:
        raise ValueError("Prepared runtime verification failed (signed Python required)")
    return {
        "connection_id": ident,
        "fingerprint": settings["edge_fingerprint"],
        "prepared": True,
        "extension": EXTENSION,
        "profile": profile,
        "origins": allowed,
        "browser_started": False,
    }


def server_config(ident, fingerprint):
    from joongi_hub.upstream import validate_server

    settings = {
        "backend": "first-party-edge",
        "edge_connection": ident,
        "edge_fingerprint": fingerprint,
    }
    validate_edge(settings)
    return validate_server(
        {
            "id": "edge-browser",
            "name": "Personal Windows Edge · 기존 로그인 백그라운드 브라우저",
            "transport": "stdio",
            "command": "joongi-personal-edge",
            "args": [],
            "enabled": True,
            "protocol_version": "2025-11-25",
            "sandbox": settings,
            "policy": {"allowed_tools": ["browser_extension_status"], "denied_tools": []},
        }
    )


def cli(args):
    from joongi_hub.storage import Registry

    if not args.prepare and not args.register:
        raise RpcError(-32602, "edge-browser --prepare 또는 --register를 지정하세요.")
    result = None
    if args.prepare:
        if args.connection_id or args.fingerprint or args.replace:
            raise RpcError(-32602, "새 준비에는 기존 연결 값·--replace를 지정하지 마세요.")
        if args.windows_python and os.name != "nt":
            if not re.fullmatch(r'[A-Za-z]:\\[^\r\n"<>|]+\.exe', args.windows_python):
                raise RpcError(-32602, "Windows Python 실행 파일의 절대 경로를 지정하세요.")
            source = subprocess.check_output(
                ["wslpath", "-w", str(Path(__file__).parent.parent)], text=True
            ).strip()
            code = (
                "import sys;sys.path.insert(0,"
                + repr(source)
                + ");from joongi_hub.__main__ import main;sys.exit(main())"
            )
            argv = [
                args.windows_python,
                "-I",
                "-B",
                "-c",
                code,
                "edge-browser",
                "--prepare",
                "--profile",
                args.profile,
            ]
            for origin in args.origin:
                argv.extend(["--origin", origin])
            # Explicit owner installation action, never used by MCP execution or registry input.
            import base64 as b64

            script = (
                "$a=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"
                + b64.b64encode(json.dumps(argv).encode()).decode()
                + "'))|ConvertFrom-Json;$p=$a[0];& $p $a[1..($a.Length-1)];exit $LASTEXITCODE"
            )
            completed = subprocess.run(
                ps_command(script),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                check=True,
            )
            result = json.loads(completed.stdout)
        else:
            result = prepare(args.origin, args.profile)
        args.connection_id, args.fingerprint = result["connection_id"], result["fingerprint"]
    elif args.origin or args.windows_python or args.profile != "Default":
        raise RpcError(-32602, "사이트·프로필 변경은 새 준비가 필요합니다.")
    if args.register:
        config = server_config(args.connection_id or "", args.fingerprint or "")
        registry = Registry(args.state_dir)
        with registry.lock:
            old = next((s for s in registry.list() if s["id"] == "edge-browser"), None)
            if (
                old
                and old != config
                and (
                    not args.replace or old.get("sandbox", {}).get("backend") != "first-party-edge"
                )
            ):
                raise RpcError(
                    -32602, "기존 등록을 보존했습니다. 검토 후 --register --replace를 사용하세요."
                )
            registry.put(config)
        result = {**(result or {}), "server": "edge-browser", "registered": True, "started": False}
    return result
