"""Reviewed skill plans with scoped ownership, frozen sources and version pins."""

import hashlib
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from joongi_hub.errors import RpcError
from joongi_hub.profiles import confined
from joongi_hub.skills import NAME_PATTERN, Skills
from joongi_hub.storage import atomic_json
from scripts.install_manager import AGENTS, Installer, InstallError, copy_tree, tree_files

PROJECT_DESTINATIONS = {
    "claude": ".claude/skills",
    "codex": ".agents/skills",
    "cursor": ".cursor/skills",
    "copilot": ".github/skills",
    "gemini": ".gemini/skills",
    "opencode": ".opencode/skills",
}


def digest(value):
    return hashlib.sha256(value or b"").hexdigest()


class SkillManager:
    def __init__(self, hub, home=None):
        self.hub = hub
        self.home = Path(home or os.environ.get("JOONGI_HUB_MANAGED_HOME") or Path.home()).resolve()
        self.directory = hub.state_dir / "skill-management"
        self.lock = threading.RLock()

    def _installer(self, source=None):
        root = Path(self.hub.project["root"]) if self.hub.project else self.home
        installer = Installer(root, source or self.hub.common_skills.directory.parent)
        if self.hub.project:
            installer.state = confined(root, ".joongi/private")
            installer.manifest_path = installer.state / "installation.json"
            installer._check_path(installer.manifest_path)
            installer.original_manifest = (
                installer.manifest_path.read_bytes() if installer.manifest_path.exists() else None
            )
            installer.manifest = installer._read_manifest()
        return installer

    def _destinations(self, installer):
        return (
            PROJECT_DESTINATIONS
            if self.hub.project
            else {name: paths[1] for name, paths in AGENTS.items()}
        )

    def _available(self):
        # Only the approved common source is installable. Project-authored skills
        # remain where they are and are never promoted or copied to user scope.
        available = {s["name"] for s in self.hub.common_skills.list()}
        return available & set(self.hub.project["common_skills"]) if self.hub.project else available

    def _source(self, installer, refresh=False):
        source = self.hub.common_skills.directory.parent
        manifest = installer.manifest
        saved = manifest.get("source")
        if saved and (Path(saved) / "skills").is_dir():
            source = Path(saved)
        if refresh and manifest.get("download_base"):
            from scripts.install_manager import download_bundle

            self.directory.mkdir(parents=True, exist_ok=True)
            source = download_bundle(
                manifest["download_base"], self.directory / ("download-" + secrets.token_hex(12))
            )
        if not (source / "skills").is_dir():
            raise RpcError(-32602, "등록된 스킬 출처를 찾을 수 없습니다.")
        return source

    def status(self):
        try:
            installer = self._installer()
            destinations = self._destinations(installer)
            result = []
            for agent, relative in destinations.items():
                prefix = relative + "/"
                for key, entry in installer.manifest["entries"].items():
                    if key.startswith(prefix) and entry.get("kind") == "tree":
                        path = installer.home / key
                        result.append(
                            {
                                "agent": agent,
                                "name": key[len(prefix) :],
                                "path": str(path),
                                "modified": not installer._managed_matches(path, entry),
                                "pinned": installer.manifest.get("skill_pins", {}).get(key, False),
                                "version": installer.manifest.get("skill_versions", {}).get(key),
                            }
                        )
            return {
                "scope": self.hub.profile_id,
                "installed": result,
                "available": sorted(self._available()),
                "source": str(self._source(installer)),
                "agents": list(destinations),
            }
        except (InstallError, OSError, ValueError) as exc:
            raise RpcError(-32602, "스킬 설치 상태를 읽을 수 없습니다.") from exc

    def plan(self, operation="install", names=None, agents=None, refresh=False):
        if (
            operation not in {"install", "update", "remove", "pin", "unpin"}
            or type(refresh) is not bool
        ):
            raise RpcError(-32602, "지원하지 않는 스킬 작업입니다.")
        with self.lock:
            try:
                installer = self._installer()
                source = self._source(installer, refresh)
                catalog = Skills(source / "skills")
                available = self._available() & {s["name"] for s in catalog.list()}
                if operation in {"remove", "pin", "unpin"}:
                    for relative in self._destinations(installer).values():
                        prefix = relative + "/"
                        available.update(
                            key[len(prefix) :]
                            for key, entry in installer.manifest["entries"].items()
                            if key.startswith(prefix) and entry.get("kind") == "tree"
                        )
                names = sorted(available) if names is None else names
                if (
                    not isinstance(names, list)
                    or len(names) > 100
                    or not all(
                        isinstance(n, str) and NAME_PATTERN.fullmatch(n) and n in available
                        for n in names
                    )
                    or len(set(names)) != len(names)
                ):
                    raise RpcError(-32602, "현재 범위에서 사용할 스킬 이름을 선택하세요.")
                destinations = self._destinations(installer)
                if agents is None:
                    agents = [a for a in destinations if (self.home / AGENTS[a][0]).is_dir()]
                    if self.hub.project and not agents:
                        agents = ["codex"]
                if (
                    not isinstance(agents, list)
                    or not agents
                    or not all(a in destinations for a in agents)
                    or len(agents) != len(set(agents))
                ):
                    raise RpcError(-32602, "설치할 에이전트를 선택하세요.")
                identity = secrets.token_hex(20)
                directory = self.directory / "plans" / identity
                snapshot = directory / "source"
                (snapshot / "skills").mkdir(parents=True, mode=0o700)
                version = (
                    (source / "VERSION").read_text(encoding="utf-8").strip()
                    if (source / "VERSION").is_file()
                    else "local"
                )
                actions = []
                for name in names:
                    if operation in {"install", "update"}:
                        catalog.entry(name)  # Validate manifest and reject symlinks.
                        copy_tree(source / "skills" / name, snapshot / "skills" / name)
                for agent in agents:
                    for name in names:
                        target = installer.home / destinations[agent] / name
                        installer._check_path(target)
                        key = installer._key(target)
                        previous = installer.manifest["entries"].get(key)
                        pinned = installer.manifest.get("skill_pins", {}).get(key, False)
                        current = tree_files(target) if target.is_dir() else None
                        incoming = (
                            tree_files(snapshot / "skills" / name)
                            if operation in {"install", "update"}
                            else None
                        )
                        reason = None
                        if target.exists() and previous is None:
                            reason = "다른 도구 또는 프로젝트가 소유한 스킬"
                        elif previous and current != previous.get("files"):
                            reason = "직접 수정되었거나 파일이 누락된 스킬"
                        elif operation == "update" and previous is None:
                            reason = "아직 설치되지 않은 스킬"
                        elif operation in {"remove", "pin", "unpin"} and previous is None:
                            reason = "관리 중인 설치가 없음"
                        elif operation in {"install", "update"} and pinned and current != incoming:
                            reason = "프로젝트 또는 사용자가 버전을 고정한 스킬"
                        action = (
                            "blocked"
                            if reason
                            else "unchanged"
                            if operation in {"install", "update"} and current == incoming
                            else operation
                        )
                        actions.append(
                            {
                                "agent": agent,
                                "name": name,
                                "path": str(target),
                                "key": key,
                                "action": action,
                                "reason": reason,
                                "pinned": pinned,
                                "incoming": incoming,
                                "current": current,
                                "source_digest": digest(
                                    json.dumps(incoming, sort_keys=True).encode()
                                ),
                            }
                        )
                plan = {
                    "id": identity,
                    "scope": self.hub.profile_id,
                    "expires_at": time.time() + 900,
                    "operation": operation,
                    "source": str(source),
                    "snapshot": str(snapshot),
                    "manifest_digest": digest(installer.original_manifest),
                    "version": version,
                    "actions": actions,
                    "status": "planned",
                }
                atomic_json(directory / "plan.json", plan)
                return self.public(plan)
            except (InstallError, OSError, ValueError) as exc:
                raise RpcError(
                    -32602, "스킬 계획을 만들 수 없습니다. 출처·경로·소유권을 확인하세요."
                ) from exc

    @staticmethod
    def public(plan):
        return {k: v for k, v in plan.items() if k not in {"snapshot", "manifest_digest"}} | {
            "actions": [
                {k: v for k, v in action.items() if k not in {"incoming", "current", "key"}}
                for action in plan["actions"]
            ]
        }

    def apply(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{40}", identity):
            raise RpcError(-32602, "설치 계획 ID가 올바르지 않습니다.")
        with self.lock:
            directory = self.directory / "plans" / identity
            path = directory / "plan.json"
            if path.is_symlink() or directory.is_symlink() or not path.is_file():
                raise RpcError(-32602, "설치 계획을 찾을 수 없습니다.")
            plan = json.loads(path.read_text(encoding="utf-8"))
            if (
                plan["scope"] != self.hub.profile_id
                or plan["expires_at"] < time.time()
                or plan["status"] != "planned"
            ):
                raise RpcError(-32602, "설치 계획의 범위·유효 기간·상태를 확인하세요.")
            if any(a["action"] == "blocked" for a in plan["actions"]):
                raise RpcError(
                    -32602, "보호할 파일이 있어 적용하지 않았습니다. 대상과 충돌을 확인하세요."
                )
            try:
                installer = self._installer(Path(plan["snapshot"]))
                if digest(installer.original_manifest) != plan["manifest_digest"]:
                    raise RpcError(-32602, "설치 상태가 바뀌었습니다. 계획을 다시 만드세요.")
                pins = installer.manifest.setdefault("skill_pins", {})
                versions = installer.manifest.setdefault("skill_versions", {})
                for action in plan["actions"]:
                    target = Path(action["path"])
                    installer._check_path(target)
                    current = tree_files(target) if target.is_dir() else None
                    if current != action["current"]:
                        raise RpcError(-32602, "대상 파일이 계획 이후 변경되었습니다.")
                    source = Path(plan["snapshot"]) / "skills" / action["name"]
                    if action["incoming"] is not None and tree_files(source) != action["incoming"]:
                        raise RpcError(-32602, "출처 스냅샷이 계획 이후 변경되었습니다.")
                    key = action["key"]
                    if action["action"] in {"install", "update"}:
                        installer._stage(target, source, "tree")
                        pins[key] = pins.get(key, bool(self.hub.project))
                        versions[key] = {
                            "version": plan["version"],
                            "digest": action["source_digest"],
                        }
                    elif action["action"] == "remove":
                        installer.operations.append((target, None, None))
                        installer.manifest["entries"].pop(key, None)
                        pins.pop(key, None)
                        versions.pop(key, None)
                    elif action["action"] in {"pin", "unpin"}:
                        pins[key] = action["action"] == "pin"
                # _apply owns the existing installer lock, backup and rollback.
                # Remember the trusted origin rather than the temporary snapshot.
                installer.source = Path(plan["source"])
                if self.hub.project:
                    installer.state.mkdir(parents=True, exist_ok=True)
                    (installer.state / ".gitignore").write_text("*\n", encoding="utf-8")
                if self.hub.project:
                    keys = {
                        key
                        for key, entry in installer.manifest["entries"].items()
                        if entry["kind"] == "tree"
                    }
                    for action in plan["actions"]:
                        if action["action"] in {"install", "update"}:
                            keys.add(action["key"])
                        elif action["action"] == "remove":
                            keys.discard(action["key"])
                    lock = {
                        "schema": 1,
                        "skills": [
                            {"path": key, **versions.get(key, {}), "pinned": pins.get(key, False)}
                            for key in sorted(keys)
                        ],
                    }
                    installer._stage(
                        Path(self.hub.project["root"]) / "joongi-skills.lock.json",
                        (json.dumps(lock, ensure_ascii=False, indent=2) + "\n").encode(),
                        "file",
                    )
                installer._apply()
                plan["status"] = "applied"
                atomic_json(path, plan)
                return self.public(plan)
            except (InstallError, OSError, ValueError) as exc:
                raise RpcError(
                    -32602, "설치를 완료하지 못했습니다. 수정한 파일은 보존합니다."
                ) from exc
