"""Reviewed MCP registration changes with installer ownership and rollback."""

import hashlib
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

from joongi_hub.connections import configuration
from joongi_hub.errors import RpcError
from joongi_hub.storage import atomic_json


class AgentConnections:
    def __init__(self, hub):
        self.hub = hub
        self.home = Path(os.environ.get("JOONGI_HUB_MANAGED_HOME") or Path.home()).resolve()
        self.directory = hub.state_dir / "connection-plans"

    def installer(self):
        from scripts.install_manager import Installer

        project = self.hub.project
        manager = Installer(
            Path(project["root"]) if project else self.home,
            self.hub.root_hub.common_skills.directory.parent,
        )
        if project:
            from joongi_hub.profiles import confined

            manager.state = confined(project["root"], ".joongi/private")
            manager.manifest_path = manager.state / "mcp-installation.json"
            manager.original_manifest = (
                manager.manifest_path.read_bytes() if manager.manifest_path.exists() else None
            )
            manager.manifest = manager._read_manifest()
            manager.project_scope = True
        manager.connection = configuration(self.hub.root_hub, self.hub.profile_id)
        return manager

    def plan(self, agents):
        from scripts.install_manager import AGENTS, InstallError

        if (
            not isinstance(agents, list)
            or not agents
            or not all(isinstance(a, str) and a in AGENTS for a in agents)
            or len(set(agents)) != len(agents)
        ):
            raise RpcError(-32602, "등록할 에이전트를 선택하세요.")
        manager = self.installer()
        try:
            for agent in agents:
                manager._config(agent, Path(sys.executable))
            identity = secrets.token_hex(20)
            plan = {
                "id": identity,
                "scope": self.hub.profile_id,
                "expires_at": time.time() + 900,
                "settings": self.hub.connection_settings.get(),
                "agents": agents,
                "manifest": hashlib.sha256(manager.original_manifest or b"").hexdigest(),
                "baselines": {
                    str(p): hashlib.sha256(v or b"").hexdigest()
                    for p, v in manager.config_baselines.items()
                },
                "paths": [str(p) for p, _, _ in manager.operations],
                "status": "planned",
            }
            atomic_json(self.directory / (identity + ".json"), plan)
            return self.public(plan)
        except (InstallError, OSError, ValueError) as exc:
            raise RpcError(
                -32602, "기존 또는 수정된 MCP 설정을 보호했습니다. 연결 설정을 확인하세요."
            ) from exc

    @staticmethod
    def public(plan):
        return {
            key: plan[key] for key in ("id", "scope", "expires_at", "agents", "status", "paths")
        }

    def apply(self, identity):
        from scripts.install_manager import InstallError

        if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{40}", identity):
            raise RpcError(-32602, "연결 계획 ID를 확인하세요.")
        path = self.directory / (identity + ".json")
        if path.is_symlink() or not path.is_file():
            raise RpcError(-32602, "연결 계획을 찾을 수 없습니다.")
        plan = json.loads(path.read_text(encoding="utf-8"))
        if (
            plan["status"] != "planned"
            or plan["scope"] != self.hub.profile_id
            or plan["expires_at"] < time.time()
            or plan["settings"] != self.hub.connection_settings.get()
        ):
            raise RpcError(-32602, "연결 계획이 만료되었거나 설정이 바뀌었습니다. 다시 확인하세요.")
        manager = self.installer()
        if hashlib.sha256(manager.original_manifest or b"").hexdigest() != plan["manifest"]:
            raise RpcError(-32602, "등록 상태가 바뀌었습니다. 계획을 다시 만드세요.")
        try:
            for agent in plan["agents"]:
                manager._config(agent, Path(sys.executable))
            current = {
                str(p): hashlib.sha256(v or b"").hexdigest()
                for p, v in manager.config_baselines.items()
            }
            if current != plan["baselines"]:
                raise RpcError(-32602, "에이전트 설정이 계획 이후 바뀌었습니다.")
            if self.hub.project:
                manager.state.mkdir(parents=True, exist_ok=True)
                (manager.state / ".gitignore").write_text("*\n", encoding="utf-8")
            manager.manifest["agents"] = sorted(
                set(manager.manifest.get("agents", [])) | set(plan["agents"])
            )
            manager._apply()
            plan["status"] = "applied"
            atomic_json(path, plan)
            return self.public(plan)
        except (InstallError, OSError, ValueError) as exc:
            raise RpcError(
                -32602, "연결 등록을 적용하지 못했습니다. 기존 설정은 보존합니다."
            ) from exc
