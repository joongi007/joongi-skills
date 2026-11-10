"""Registered project boundaries and a read-only common/project skill overlay."""

import hashlib
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

from joongi_hub.errors import RpcError
from joongi_hub.skills import NAME_PATTERN, Skills
from joongi_hub.storage import Registry, atomic_json

PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
PROJECT_SKILL_PATHS = [
    ".agents/skills",
    ".claude/skills",
    ".cursor/skills",
    ".github/skills",
    ".gemini/skills",
    ".opencode/skills",
]


def confined(root, relative):
    root = Path(root).resolve()
    path = root / relative
    if (
        Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or not path.resolve().is_relative_to(root)
    ):
        raise RpcError(-32602, "프로젝트 범위를 벗어난 경로입니다.")
    if any(p.is_symlink() for p in [path, *path.parents] if p.is_relative_to(root)):
        raise RpcError(-32602, "프로젝트 스킬 경로의 symlink는 지원하지 않습니다.")
    return path


class Projects:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "projects.json"
        self.lock = threading.RLock()

    def list(self):
        if not self.path.exists():
            return []
        if self.path.is_symlink():
            raise RpcError(-32602, "프로젝트 설정의 symlink는 지원하지 않습니다.")
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, identity):
        project = next((p for p in self.list() if p["id"] == identity), None)
        if project is None:
            raise RpcError(-32602, "등록되지 않은 프로젝트입니다.")
        return project

    def put(self, value):
        allowed = {"id", "name", "root", "common_skills", "common_servers", "skill_paths"}
        if not isinstance(value, dict) or set(value) - allowed:
            raise RpcError(-32602, "프로젝트 설정 필드를 확인하세요.")
        identity = value.get("id")
        if (
            not isinstance(identity, str)
            or not PROFILE_ID.fullmatch(identity)
            or identity == "global"
        ):
            raise RpcError(-32602, "프로젝트 ID는 영문 소문자·숫자·하이픈으로 지정하세요.")
        if not isinstance(value.get("root"), str) or not Path(value["root"]).is_absolute():
            raise RpcError(-32602, "프로젝트의 절대 경로를 지정하세요.")
        root = Path(value["root"]).resolve()
        if not root.is_dir():
            raise RpcError(-32602, "존재하는 프로젝트 폴더를 선택하세요.")
        skills = value.get("common_skills", [])
        servers = value.get("common_servers", [])
        paths = value.get("skill_paths", PROJECT_SKILL_PATHS)
        for items, pattern in ((skills, NAME_PATTERN), (servers, PROFILE_ID)):
            if (
                not isinstance(items, list)
                or len(items) > 100
                or not all(isinstance(item, str) and pattern.fullmatch(item) for item in items)
                or len(items) != len(set(items))
            ):
                raise RpcError(-32602, "공용 스킬·서버는 중복 없는 ID 배열로 지정하세요.")
        if (
            not isinstance(paths, list)
            or not paths
            or len(paths) > 12
            or not all(isinstance(path, str) and path in PROJECT_SKILL_PATHS for path in paths)
            or len(paths) != len(set(paths))
        ):
            raise RpcError(-32602, "지원하는 프로젝트 스킬 경로를 순서대로 지정하세요.")
        for path in paths:
            confined(root, path)
        name = value.get("name", identity)
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise RpcError(-32602, "프로젝트 표시 이름을 확인하세요.")
        result = {
            "id": identity,
            "name": name,
            "root": str(root),
            "common_skills": skills,
            "common_servers": servers,
            "skill_paths": paths,
        }
        with self.lock:
            projects = [p for p in self.list() if p["id"] != identity]
            atomic_json(self.path, [*projects, result])
        return result

    def state_directory(self, project):
        root_hash = hashlib.sha256(project["root"].encode()).hexdigest()[:16]
        return self.directory / "projects" / (project["id"] + "-" + root_hash)

    def delete(self, identity):
        with self.lock:
            self.get(identity)
            atomic_json(self.path, [p for p in self.list() if p["id"] != identity])


class ProjectRegistry(Registry):
    def __init__(self, directory, common, selected):
        super().__init__(directory)
        self.common = common
        self.selected = set(selected)

    def list(self):
        inherited = {
            c["id"]: {**c, "inherited": True}
            for c in self.common.list()
            if c["id"] in self.selected
        }
        local = super().list()
        inherited.update({c["id"]: c for c in local})
        return list(inherited.values())

    def put(self, server):
        with self.lock:
            # Registry.put calls list dynamically, so write only local entries here.
            local = Registry.list(self)
            atomic_json(self.path, [c for c in local if c["id"] != server["id"]] + [server])

    def delete(self, identity):
        with self.lock:
            local = Registry.list(self)
            if not any(c["id"] == identity for c in local):
                raise RpcError(-32602, "공용 연결은 프로젝트의 공용 서버 선택에서 제외하세요.")
            atomic_json(self.path, [c for c in local if c["id"] != identity])


class ProjectSkills:
    def __init__(self, common, project):
        self.common = common
        self.project = project
        self.directory = common.directory

    def _sources(self):
        selected = set(self.project["common_skills"])
        result = {
            s["name"]: (self.common, "common") for s in self.common.list() if s["name"] in selected
        }
        # Earlier explicit skill_paths win among project sources. Every project
        # source wins over the common catalog; no file is overwritten to do this.
        local = {}
        for relative in self.project["skill_paths"]:
            directory = confined(self.project["root"], relative)
            source = Skills(directory)
            for item in source.list():
                local.setdefault(item["name"], (source, "project"))
        result.update(local)
        return result

    def _source(self, name):
        item = self._sources().get(name)
        if item is None:
            raise RpcError(-32602, "이 프로젝트에 노출되지 않은 스킬입니다.")
        return item[0]

    def list(self):
        return [
            {**next(s for s in source.list() if s["name"] == name), "scope": scope}
            for name, (source, scope) in sorted(self._sources().items())
        ]

    def read(self, name, path="SKILL.md"):
        return self._source(name).read(name, path)

    def read_bytes(self, name, path="SKILL.md"):
        return self._source(name).read_bytes(name, path)

    def read_uri(self, uri):
        return self._source(urlparse(uri).netloc).read_uri(uri)

    def read_directory(self, uri):
        return self._source(urlparse(uri).netloc).read_directory(uri)

    def entry(self, name):
        return self._source(name).entry(name)

    def entries(self):
        return [self.entry(item["name"]) for item in self.list()]
