#!/usr/bin/env python3
"""Dependency-free, ownership-aware installation for Joongi Skills and Hub."""

from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

AGENTS = {
    "claude": (".claude", ".claude/skills"),
    "codex": (".codex", ".agents/skills"),
    "cursor": (".cursor", ".cursor/skills"),
    "copilot": (".copilot", ".copilot/skills"),
    "gemini": (".gemini", ".gemini/skills"),
    "opencode": (".config/opencode", ".config/opencode/skills"),
}
EXCLUDED = {"__pycache__", "node_modules", ".git", ".venv", ".DS_Store"}
MCP_NAME = "joongi-hub"
TOML_START = "# BEGIN joongi-skills managed MCP\n"
TOML_END = "# END joongi-skills managed MCP\n"


class InstallError(Exception):
    """A conflict that must be resolved without replacing user-owned content."""


def jsonc_clean(text: str, trailing_commas: bool = True) -> str:
    """Blank comments without moving offsets or changing quoted strings."""
    result = list(text)
    position = 0
    quoted = False
    escaped = False
    while position < len(text):
        char = text[position]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            position += 1
        elif char == '"':
            quoted = True
            position += 1
        elif text.startswith("//", position):
            end = text.find("\n", position)
            end = len(text) if end == -1 else end
            result[position:end] = " " * (end - position)
            position = end
        elif text.startswith("/*", position):
            end = text.find("*/", position + 2)
            if end == -1:
                raise InstallError("Unclosed JSONC comment")
            end += 2
            result[position:end] = ["\n" if value == "\n" else " " for value in text[position:end]]
            position = end
        else:
            position += 1
    cleaned = "".join(result)
    if trailing_commas:
        # String tokens are skipped, including strings containing ', }'.
        for match in re.finditer(r'"(?:\\.|[^"\\])*"|,(?=\s*[}\]])', cleaned):
            if match.group() == ",":
                result[match.start()] = " "
    return "".join(result)


def jsonc_data(text: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InstallError(f"Duplicate configuration key: {key}")
            result[key] = value
        return result

    data = json.loads(jsonc_clean(text), object_pairs_hook=unique)
    if not isinstance(data, dict):
        raise InstallError("Configuration root must be an object")
    return data


def jsonc_members(text: str, start: int):
    cleaned = jsonc_clean(text)
    decoder = json.JSONDecoder()
    position = start + 1
    members = []
    while True:
        while position < len(cleaned) and cleaned[position].isspace():
            position += 1
        if cleaned[position] == "}":
            return members, position
        key_start = position
        key, position = decoder.raw_decode(cleaned, position)
        while cleaned[position].isspace():
            position += 1
        if cleaned[position] != ":":
            raise InstallError("Invalid configuration member")
        position += 1
        while cleaned[position].isspace():
            position += 1
        value_start = position
        _, position = decoder.raw_decode(cleaned, position)
        members.append((key, key_start, value_start, position))
        while cleaned[position].isspace():
            position += 1
        if cleaned[position] == ",":
            position += 1
        elif cleaned[position] != "}":
            raise InstallError("Invalid configuration separator")


def jsonc_update(text: str, container: str, name: str, value) -> str:
    """Edit one nested property while keeping unrelated JSONC bytes and comments."""
    text = text or "{}\n"
    data = jsonc_data(text)
    if not isinstance(data.get(container, {}), dict):
        raise InstallError(f"Configuration {container} must be an object")
    cleaned = jsonc_clean(text)
    root = cleaned.index("{")
    root_members, root_end = jsonc_members(text, root)
    parent = next((member for member in root_members if member[0] == container), None)
    if parent is None:
        if value is None:
            return text
        members, end, key, replacement = root_members, root_end, container, {name: value}
    else:
        members, end = jsonc_members(text, parent[2])
        key, replacement = name, value
    member = next((item for item in members if item[0] == key), None)
    if member and replacement is not None:
        return text[: member[2]] + json.dumps(replacement, ensure_ascii=False) + text[member[3] :]
    if member:
        without_comments = jsonc_clean(text, trailing_commas=False)
        after = without_comments[member[3] : end]
        comma = after.find(",")
        if comma >= 0:
            stop = member[3] + comma + 1
            return text[: member[1]] + text[stop:]
        previous = next((item for item in reversed(members) if item[3] < member[1]), None)
        if previous:
            comma = without_comments.index(",", previous[3], member[1])
            return text[:comma] + text[comma + 1 : member[1]] + text[member[3] :]
        return text[: member[1]] + text[member[3] :]
    if replacement is None:
        return text
    extra = json.dumps(key) + ": " + json.dumps(replacement, ensure_ascii=False)
    if members:
        last_end = members[-1][3]
        has_comma = "," in jsonc_clean(text, trailing_commas=False)[last_end:end]
        if not has_comma:
            return text[:last_end] + "," + text[last_end:end] + "\n  " + extra + "\n" + text[end:]
    return text[:end] + "\n  " + extra + "\n" + text[end:]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_files(root: Path) -> dict[str, str]:
    if root.is_symlink():
        raise InstallError(f"Symlink is not managed: {root}")
    if not root.is_dir():
        raise InstallError(f"Expected a directory: {root}")
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise InstallError(f"Symlink is not managed: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    return result


def copy_tree(source: Path, target: Path) -> None:
    """Exclude runtime junk while refusing symlinks from an install source."""
    if source.is_symlink():
        raise InstallError(f"Source contains a symlink: {source}")
    target.mkdir(parents=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part in EXCLUDED for part in relative.parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise InstallError(f"Source contains a symlink: {path}")
        destination = target / relative
        if path.is_dir():
            destination.mkdir(exist_ok=True)
        elif path.is_file():
            shutil.copy2(path, destination)


def download_bundle(base: str, target: Path) -> Path:
    """Fetch a Pages bundle with bounded extraction and same-origin integrity data."""
    if not base.startswith("https://"):
        raise InstallError("Download base must use HTTPS")
    base = base.rstrip("/") + "/"
    with urllib.request.urlopen(base + "bundle-manifest.json", timeout=30) as response:
        manifest = json.loads(response.read(64 * 1024))
    expected = manifest.get("sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise InstallError("Invalid bundle SHA256 metadata")
    # A fixed basename prevents a manifest redirecting downloads to another host.
    with urllib.request.urlopen(base + "joongi-skills.tar.gz", timeout=60) as response:
        data = response.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024 or digest(data) != expected:
        raise InstallError("Bundle size or SHA256 check failed")
    from scripts.verify_release import VerificationError, verify_download

    try:
        with urllib.request.urlopen(base + "joongi-skills.sigstore.jsonl", timeout=30) as response:
            attestation = response.read(2 * 1024**2 + 1)
        verified = verify_download(data, attestation)
    except (VerificationError, OSError) as exc:
        raise InstallError("Signed release verification failed; installation was stopped") from exc
    if manifest.get("revision") != verified["revision"]:
        raise InstallError("Bundle metadata does not match verified source revision")
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
        unpacked = compressed.read(144 * 1024**2 + 1)
    if len(unpacked) > 144 * 1024**2:
        raise InstallError("Bundle decompression limit exceeded")
    with tarfile.open(fileobj=io.BytesIO(unpacked), mode="r:") as archive:
        members = []
        total_size = 0
        for member in archive:
            members.append(member)
            total_size += member.size
            if len(members) > 10000 or total_size > 128 * 1024**2:
                raise InstallError("Bundle extraction limits exceeded")
        for member in members:
            output = target / member.name
            if (
                member.issym()
                or member.islnk()
                or not (member.isfile() or member.isdir())
                or not output.resolve().is_relative_to(target.resolve())
            ):
                raise InstallError("Unsafe archive member")
        for member in members:
            output = target / member.name
            if member.isdir():
                output.mkdir(parents=True, exist_ok=True)
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source:
                    output.write_bytes(source.read())
    source = target / "joongi-skills"
    if not (source / "skills").is_dir():
        raise InstallError("Bundle has no skills directory")
    return source


def validate_wsl_backend(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"distribution", "launcher"}
        or not isinstance(value["distribution"], str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value["distribution"])
        or not isinstance(value["launcher"], str)
        or not value["launcher"].startswith("/home/")
        or any(c in value["launcher"] for c in "\x00\r\n")
    ):
        raise InstallError("Invalid saved WSL backend")
    return value


def discover_wsl_backend(distribution):
    if os.name != "nt" or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", distribution):
        raise InstallError("--wsl-distribution requires Windows and an installed WSL distribution")
    script = (
        "from pathlib import Path;import json;p=Path.home()/'.local/bin/joongi-hub';"
        "print(json.dumps({'launcher':str(p),'exists':p.is_file()}))"
    )
    try:
        result = subprocess.run(
            ["wsl.exe", "-d", distribution, "--exec", "python3", "-I", "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
        value = json.loads(result.stdout)
        if value.get("exists") is not True:
            raise ValueError
        return validate_wsl_backend({"distribution": distribution, "launcher": value["launcher"]})
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise InstallError("Install Joongi Hub inside the selected WSL distribution first") from exc


class Installer:
    def __init__(self, home: Path, source: Path, dry_run: bool = False):
        self.home = home.expanduser().resolve()
        self.source = source.resolve()
        self.state = self.home / ".local/share/joongi-skills"
        self.manifest_path = self.state / "installation.json"
        self.runtime = self.state / "runtime"
        self.bin_dir = self.home / ".local/bin"
        self.dry_run = dry_run
        self.messages: list[str] = []
        self.operations: list[tuple[Path, bytes | Path | None, dict | None]] = []
        self.config_baselines: dict[Path, bytes | None] = {}
        self._check_path(self.manifest_path)
        self.original_manifest = (
            self.manifest_path.read_bytes() if self.manifest_path.exists() else None
        )
        self.manifest = self._read_manifest()

    def _read_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {"schema": 1, "entries": {}, "agents": []}
        self._check_path(self.manifest_path)
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if data.get("schema") != 1 or not isinstance(data.get("entries"), dict):
            raise InstallError("Unsupported installation manifest")
        return data

    def _check_path(self, path: Path) -> None:
        if not path.is_relative_to(self.home) or not path.resolve().is_relative_to(self.home):
            raise InstallError(f"Target escapes installation home: {path}")
        current = path
        while current != self.home:
            if current.is_symlink():
                raise InstallError(f"Target traverses a symlink: {current}")
            current = current.parent

    def _key(self, path: Path) -> str:
        self._check_path(path)
        return path.relative_to(self.home).as_posix()

    def _managed_matches(self, path: Path, entry: dict) -> bool:
        self._check_path(path)
        if entry["kind"] == "tree":
            return path.is_dir() and tree_files(path) == entry["files"]
        return path.is_file() and digest(path.read_bytes()) == entry["sha256"]

    def _stage(self, path: Path, value: bytes | Path, kind: str) -> None:
        key = self._key(path)
        previous = self.manifest["entries"].get(key)
        if path.exists() and (previous is None or not self._managed_matches(path, previous)):
            raise InstallError(f"Preserved unowned or locally changed path: {path}")
        if (
            previous
            and kind == "tree"
            and self.manifest.get("skill_pins", {}).get(key)
            and previous.get("files") != tree_files(value)
        ):
            raise InstallError(
                f"Pinned skill is protected; unpin explicitly before updating: {path}"
            )
        entry = (
            {"kind": kind, "files": tree_files(value)}
            if kind == "tree"
            else {"kind": kind, "sha256": digest(value)}
        )
        self.operations.append((path, value, entry))
        self.messages.append(f"{'Would install' if self.dry_run else 'Install'} {path}")

    def detect(self) -> list[str]:
        return [name for name, (directory, _) in AGENTS.items() if (self.home / directory).is_dir()]

    def _config(self, agent: str, launcher: Path) -> None:
        from joongi_hub.connections import agent_value

        connection = getattr(self, "connection", None) or {
            "command": str(launcher),
            "args": ["stdio"],
        }
        value = agent_value(agent, connection)
        project = getattr(self, "project_scope", False)
        if agent == "codex":
            path = self.home / ".codex/config.toml"
            self._key(path)
            self.config_baselines[path] = path.read_bytes() if path.exists() else None
            original = (self.config_baselines[path] or b"").decode("utf-8")
            old = self.manifest.get("configs", {}).get(agent)
            if old:
                if old["block"] not in original:
                    raise InstallError(f"Preserved modified MCP registration: {path}")
                original = original.replace(old["block"], "", 1)
            elif re.search(
                r"^\s*(?:mcp_servers\s*=|\[[^\n]*mcp_servers[^\n]*joongi-hub)", original, re.M
            ):
                raise InstallError(f"MCP name already exists: {path}")
            block = (
                TOML_START
                + '[mcp_servers."joongi-hub"]\n'
                + (
                    "url = " + json.dumps(value["url"]) + "\n"
                    if "url" in value
                    else "command = "
                    + json.dumps(value["command"])
                    + "\nargs = "
                    + json.dumps(value["args"])
                    + "\n"
                )
                + (
                    "http_headers = { "
                    + ", ".join(
                        json.dumps(k) + " = " + json.dumps(v)
                        for k, v in value["http_headers"].items()
                    )
                    + " }\n"
                    if value.get("http_headers")
                    else ""
                )
                + TOML_END
            )
            updated = original + ("\n" if original and not original.endswith("\n") else "") + block
            try:
                import tomllib
            except ImportError:
                pass  # Python 3.10: preserve original TOML and append an isolated table.
            else:
                tomllib.loads(updated)
            entry = {"path": path.relative_to(self.home).as_posix(), "block": block}
        elif agent in {"claude", "cursor", "gemini", "copilot", "opencode"}:
            location = {
                "claude": ".claude.json",
                "cursor": ".cursor/mcp.json",
                "gemini": ".gemini/settings.json",
                "copilot": ".copilot/mcp-config.json",
                "opencode": ".config/opencode/opencode.json",
            }[agent]
            if project:
                location = {
                    "claude": ".mcp.json",
                    "copilot": ".github/mcp.json",
                    "opencode": "opencode.json",
                }.get(agent, location)
            old = self.manifest.get("configs", {}).get(agent)
            container = "mcp" if agent == "opencode" else "mcpServers"
            if agent == "opencode":
                candidates = [
                    location,
                    "opencode.jsonc" if project else ".config/opencode/opencode.jsonc",
                ]
                if old:
                    location = old["path"]
                elif (self.home / candidates[1]).exists():
                    location = candidates[1]
                for other in candidates:
                    candidate = self.home / other
                    self._key(candidate)
                    if other != location and candidate.exists():
                        self.config_baselines[candidate] = candidate.read_bytes()
                        other_data = jsonc_data(self.config_baselines[candidate].decode("utf-8"))
                        if MCP_NAME in other_data.get(container, {}):
                            raise InstallError(f"MCP name already exists: {candidate}")
            path = self.home / location
            self._key(path)
            self.config_baselines[path] = path.read_bytes() if path.exists() else None
            original = (self.config_baselines[path] or b"{}\n").decode("utf-8")
            data = jsonc_data(original) if agent == "opencode" else json.loads(original)
            if not isinstance(data, dict) or not isinstance(data.get(container, {}), dict):
                raise InstallError(f"Invalid MCP configuration shape: {path}")
            servers = data.setdefault(container, {})
            if MCP_NAME in servers and (old is None or servers[MCP_NAME] != old["value"]):
                raise InstallError(f"Preserved existing or modified MCP registration: {path}")
            servers[MCP_NAME] = value
            updated = (
                jsonc_update(original, container, MCP_NAME, value)
                if agent == "opencode"
                else json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            )
            entry = {
                "path": location,
                "value": value,
                "container": container,
                "jsonc": agent == "opencode",
            }
        else:
            self.messages.append(
                f"{agent}: skills installed; add MCP manually using {launcher} stdio"
            )
            return
        self.operations.append((path, updated.encode(), None))
        self.manifest.setdefault("configs", {})[agent] = entry
        self.messages.append(f"Register MCP for {agent}: {path}")

    def install(self, agents: list[str] | None = None, all_agents: bool = False) -> None:
        selected = list(AGENTS) if all_agents else agents if agents else self.detect()
        if not (self.source / "skills").is_dir():
            raise InstallError(f"Source has no skills directory: {self.source}")
        # Keep staged files alive through apply; nothing is written to home during preflight.
        with tempfile.TemporaryDirectory(prefix="joongi-install-") as temporary:
            staging = Path(temporary)
            runtime = staging / "runtime"
            runtime.mkdir()
            for name in ("joongi_hub", "skills"):
                if (self.source / name).is_dir():
                    copy_tree(self.source / name, runtime / name)
            (runtime / "scripts").mkdir()
            manager_source = self.source / "scripts/install_manager.py"
            shutil.copy2(
                manager_source if manager_source.is_file() else Path(__file__),
                runtime / "scripts/install_manager.py",
            )
            verifier = self.source / "scripts/verify_release.py"
            if not verifier.is_file():
                verifier = Path(__file__).with_name("verify_release.py")
            shutil.copy2(verifier, runtime / "scripts/verify_release.py")
            backend = self.manifest.get("wsl_backend")
            if backend:
                validate_wsl_backend(backend)
                delegation = [
                    "wsl.exe",
                    "-d",
                    backend["distribution"],
                    "--exec",
                    backend["launcher"],
                ]
                launcher_code = (
                    "import subprocess,sys\n"
                    + f"raise SystemExit(subprocess.call({delegation!r} + sys.argv[1:]))\n"
                )
            else:
                launcher_code = (
                    "import os\nimport runpy\nimport sys\nfrom pathlib import Path\n"
                    "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
                    "os.environ['JOONGI_HUB_INSTALL_STATE_DIR'] = "
                    f"{str(self.home / '.local/share/joongi-hub')!r}\n"
                    'runpy.run_module("joongi_hub", run_name="__main__")\n'
                )
            (runtime / "scripts/hub_launcher.py").write_text(launcher_code, encoding="utf-8")
            for filename in ("VERSION", "LICENSE", "install.sh", "install.ps1"):
                if (self.source / filename).is_file():
                    shutil.copy2(self.source / filename, runtime / filename)
            self._stage(self.runtime, runtime, "tree")
            python = str(Path(sys.executable).resolve())
            # python -B keeps the read-only source snapshot free of bytecode changes.
            if os.name == "nt":
                hub = self.bin_dir / "joongi-hub.cmd"
                manager = self.bin_dir / "joongi-skills.cmd"
                prefix = "@echo off\n"

                def command_path(path):
                    try:
                        return "%~dp0" + os.path.relpath(path, self.bin_dir)
                    except ValueError:
                        return str(path)

                # cmd expands %~dp0 as Unicode even under a legacy console code page.
                interpreter = command_path(python)
                hub_target = command_path(self.runtime / "scripts/hub_launcher.py")
                manager_target = command_path(self.runtime / "scripts/install_manager.py")
                # End batch context first: Python may replace/delete this launcher.
                # Arguments expand before goto; the native command preserves its exit status.
                handoff = prefix + f'(goto) 2>nul & "{interpreter}" -I -B '
                hub_script = handoff + f'"{hub_target}" %*\n'
                manager_script = handoff + f'"{manager_target}" %*\n'
            else:
                hub = self.bin_dir / "joongi-hub"
                manager = self.bin_dir / "joongi-skills"
                prefix = "#!/bin/sh\n"
                hub_script = (
                    prefix
                    + f"exec {shlex.quote(python)} -I -B "
                    + shlex.quote(str(self.runtime / "scripts/hub_launcher.py"))
                    + ' "$@"\n'
                )
                manager_script = (
                    prefix
                    + f"exec {shlex.quote(python)} -I -B "
                    + shlex.quote(str(self.runtime / "scripts/install_manager.py"))
                    + ' "$@"\n'
                )
            self._stage(hub, hub_script.encode(), "file")
            self._stage(manager, manager_script.encode(), "file")
            for agent in selected:
                self._check_path(self.home / AGENTS[agent][0])
                target = self.home / AGENTS[agent][1]
                current_skills = set()
                for skill in sorted((runtime / "skills").iterdir()):
                    if skill.is_dir() and (skill / "SKILL.md").is_file():
                        self._stage(target / skill.name, skill, "tree")
                        current_skills.add(skill.name)
                prefix = AGENTS[agent][1] + "/"
                for key, entry in list(self.manifest["entries"].items()):
                    if key.startswith(prefix) and key[len(prefix) :] not in current_skills:
                        stale = self.home / key
                        if not stale.exists() or self._managed_matches(stale, entry):
                            self.operations.append((stale, None, None))
                            del self.manifest["entries"][key]
                            self.messages.append(f"Remove retired skill: {stale}")
                        else:
                            self.messages.append(f"Preserve locally changed retired skill: {stale}")
                self._config(agent, hub)
            self.manifest["agents"] = sorted(set(self.manifest.get("agents", [])) | set(selected))
            if not selected:
                self.messages.append(
                    "No existing agents detected. Hub installed; "
                    "rerun install after adding an agent."
                )
            self._apply()

    def uninstall(self) -> None:
        for key, entry in list(self.manifest["entries"].items()):
            path = self.home / key
            if not path.exists():
                del self.manifest["entries"][key]
            elif self._managed_matches(path, entry):
                self.operations.append((path, None, None))
                del self.manifest["entries"][key]
                self.messages.append(f"Remove {path}")
            else:
                self.messages.append(f"Preserve locally changed path: {path}")
        for agent, entry in list(self.manifest.get("configs", {}).items()):
            path = self.home / entry["path"]
            self._key(path)
            if not path.exists():
                del self.manifest["configs"][agent]
                continue
            self.config_baselines[path] = path.read_bytes()
            original = self.config_baselines[path].decode("utf-8")
            if "block" in entry:
                if entry["block"] not in original:
                    self.messages.append(f"Preserve modified MCP registration: {path}")
                    continue
                updated = original.replace(entry["block"], "", 1)
            else:
                data = jsonc_data(original) if entry.get("jsonc") else json.loads(original)
                container = entry.get("container", "mcpServers")
                if data.get(container, {}).get(MCP_NAME) != entry["value"]:
                    self.messages.append(f"Preserve modified MCP registration: {path}")
                    continue
                del data[container][MCP_NAME]
                updated = (
                    jsonc_update(original, container, MCP_NAME, None)
                    if entry.get("jsonc")
                    else json.dumps(data, ensure_ascii=False, indent=2) + "\n"
                )
            self.operations.append((path, updated.encode(), None))
            del self.manifest["configs"][agent]
            self.messages.append(f"Unregister MCP for {agent}: {path}")
        self.manifest["agents"] = [
            name
            for name in self.manifest.get("agents", [])
            if name in self.manifest.get("configs", {})
            or any(key.startswith(AGENTS[name][1] + "/") for key in self.manifest["entries"])
        ]
        self._apply()

    def _apply(self) -> None:
        if self.dry_run:
            return
        self._check_path(self.state)
        self.state.mkdir(parents=True, exist_ok=True)
        lock = self.state / "install.lock"
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise InstallError(f"Another installer is running; inspect {lock}") from error
        os.close(descriptor)
        applied: list[tuple[Path, Path | None]] = []
        try:
            current_manifest = (
                self.manifest_path.read_bytes() if self.manifest_path.exists() else None
            )
            if current_manifest != self.original_manifest:
                raise InstallError("Installation changed during planning; rerun the command")
            for path, expected in self.config_baselines.items():
                self._check_path(path)
                current = path.read_bytes() if path.exists() else None
                if current != expected:
                    raise InstallError(f"Agent settings changed during planning; rerun: {path}")
            for path, value, entry in self.operations:
                self._check_path(path)
                path.parent.mkdir(parents=True, exist_ok=True)
                backup = None
                if path.exists():
                    backup = (
                        Path(tempfile.mkdtemp(prefix=".joongi-backup-", dir=path.parent))
                        / "original"
                    )
                    path.rename(backup)
                applied.append((path, backup))
                if isinstance(value, Path):
                    shutil.copytree(value, path)
                elif isinstance(value, bytes):
                    path.write_bytes(value)
                    path.chmod(0o700 if path.parent == self.bin_dir else 0o600)
                if entry:
                    self.manifest["entries"][self._key(path)] = entry
            self.manifest["source"] = str(self.source)
            content = json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n"
            staged = self.state / "installation.json.tmp"
            staged.write_text(content, encoding="utf-8")
            staged.chmod(0o600)
            staged.replace(self.manifest_path)
        except BaseException:
            for path, backup in reversed(applied):
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.exists():
                    path.unlink()
                if backup:
                    backup.rename(path)
            raise
        finally:
            for _, backup in applied:
                if backup and backup.parent.exists():
                    shutil.rmtree(backup.parent)
            lock.unlink(missing_ok=True)

    def status(self) -> dict:
        return {
            "detected_agents": self.detect(),
            "installed_agents": self.manifest.get("agents", []),
            "managed_paths": len(self.manifest["entries"]),
            "runtime": str(self.runtime),
            "launcher": str(self.bin_dir / ("joongi-hub.cmd" if os.name == "nt" else "joongi-hub")),
        }


def main(argv: list[str] | None = None) -> int:
    from joongi_hub.errors import RpcError

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    if sys.version_info < (3, 10):  # noqa: UP036 - explain unsupported direct invocations
        print("Python 3.10+ is required", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["install", "update", "uninstall", "status"], nargs="?", default="install"
    )
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument(
        "--source", type=Path, help="Local source checkout; overrides saved remote update URL"
    )
    parser.add_argument("--agent", action="append", choices=AGENTS)
    parser.add_argument(
        "--all", action="store_true", help="Explicitly install to every supported agent"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--wsl-distribution",
        help="Windows: delegate Hub commands and state to an installed WSL Hub",
    )
    parser.add_argument("--download-base", help="Fetch latest bundle from an HTTPS Pages URL")
    parser.add_argument("--mode", choices=["stdio", "hybrid", "http"])
    parser.add_argument("--url", help="Local HTTP Hub base URL")
    parser.add_argument("--fallback", choices=["stdio", "error"])
    parser.add_argument(
        "--start", action="store_true", help="Start optional local HTTP Hub after installation"
    )
    parser.add_argument("--port", type=int, help="HTTP Hub port for --start")
    args = parser.parse_args(argv)
    try:
        with contextlib.ExitStack() as stack:
            source = args.source or Path(__file__).resolve().parents[1]
            previous = Installer(args.home, source, args.dry_run).manifest
            download_base = args.download_base
            if (
                args.action == "update"
                and args.source is None
                and not download_base
                and not os.environ.get("JOONGI_INSTALL_DOWNLOAD_BASE")
            ):
                download_base = previous.get("download_base")
                previous_source = Path(previous.get("source", ""))
                if not download_base and (previous_source / "skills").is_dir():
                    source = previous_source
            if download_base and args.action in {"install", "update"}:
                temporary = stack.enter_context(
                    tempfile.TemporaryDirectory(prefix="joongi-download-")
                )
                source = download_bundle(download_base, Path(temporary))
            installer = Installer(args.home, source, args.dry_run)
            if args.wsl_distribution:
                installer.manifest["wsl_backend"] = discover_wsl_backend(args.wsl_distribution)
            saved_base = download_base or os.environ.get("JOONGI_INSTALL_DOWNLOAD_BASE")
            if saved_base:
                installer.manifest["download_base"] = saved_base
            elif args.source:
                installer.manifest.pop("download_base", None)
            from joongi_hub.connections import ConnectionSettings

            hub_state = installer.home / ".local/share/joongi-hub"
            selected = ConnectionSettings(hub_state).get()
            for key in ("mode", "url", "fallback"):
                if getattr(args, key) is not None:
                    selected[key] = getattr(args, key)
            selected = ConnectionSettings.validate(selected)
            if selected["mode"] == "http":
                launcher = installer.bin_dir / (
                    "joongi-hub.cmd" if os.name == "nt" else "joongi-hub"
                )
                installer.connection = {
                    "command": str(launcher),
                    "args": ["stdio", "--mode", "http", "--url", selected["url"]],
                }
            elif selected["mode"] == "hybrid":
                launcher = installer.bin_dir / (
                    "joongi-hub.cmd" if os.name == "nt" else "joongi-hub"
                )
                installer.connection = {
                    "command": str(launcher),
                    "args": ["stdio", "--mode", "hybrid", "--fallback", selected["fallback"]],
                }
            if args.action == "status":
                print(json.dumps(installer.status(), ensure_ascii=False, indent=2))
            elif args.action == "uninstall":
                installer.uninstall()
            else:
                installer.install(args.agent, args.all)
                if not args.dry_run and any(
                    getattr(args, key) is not None for key in ("mode", "url", "fallback")
                ):
                    installer._check_path(hub_state / "connection.json")
                    ConnectionSettings(hub_state).put(selected)
                if args.start and not args.dry_run:
                    from joongi_hub.lifecycle import start

                    print(
                        json.dumps(
                            start(
                                hub_state,
                                installer.runtime / "skills",
                                args.port,
                                source_root=installer.runtime,
                            ),
                            ensure_ascii=False,
                        )
                    )
            for message in installer.messages:
                print(message)
        return 0
    except (InstallError, OSError, ValueError, tarfile.TarError, RpcError) as error:
        print(f"Installation stopped: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
