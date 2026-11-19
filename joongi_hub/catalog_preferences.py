"""Profile-local discovery choices; these preferences are not an authorization boundary."""

import copy
import json
import re
from pathlib import Path

from joongi_hub.credential_lock import CredentialLock
from joongi_hub.errors import RpcError
from joongi_hub.storage import atomic_json

CATEGORIES = ("development", "documentation", "design", "tools")
SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
SERVER_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
SKILL_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,199}$")
RESERVED_SOURCES = {"builtin", "project"}
MAX_SETTINGS_BYTES = 256 * 1024
DEFAULTS = {
    "schema": 1,
    "exposure": "search-first",
    "sources": [],
    "disabled": {"skill": [], "server": [], "source": [], "category": []},
    "category_overrides": {},
    "usage_enabled": False,
}
BUILTIN_CATEGORIES = {
    "engineering-playbook": ("development", "documentation"),
    "usual-korean": ("documentation",),
    "applying-design-systems": ("design",),
    "creating-diagrams": ("design", "documentation"),
    "building-procedural-3d": ("design", "development"),
}


def builtin_categories(name):
    """Categories for bundled identities, not guesses based on arbitrary descriptions."""
    return list(BUILTIN_CATEGORIES.get(name, ()))


def safe_path(path):
    """Reject symlinks, including missing targets and symlinked parent directories."""
    path = Path(path)
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise RpcError(-32045, "카탈로그 설정 경로의 symlink는 지원하지 않습니다.")


def _bad(message="카탈로그 설정 필드를 확인하세요."):
    raise RpcError(-32602, message)


def _items(values, pattern=None, choices=None, maximum=500):
    if not isinstance(values, list) or len(values) > maximum:
        _bad()
    if any(
        not isinstance(value, str)
        or (pattern is not None and not pattern.fullmatch(value))
        or (choices is not None and value not in choices)
        for value in values
    ):
        _bad()
    if len(set(values)) != len(values):
        _bad("카탈로그 선택에는 중복 항목을 넣을 수 없습니다.")
    return list(values)


def _source(value, check_exists=False):
    if not isinstance(value, dict) or set(value) - {"id", "name", "path", "enabled", "category"}:
        _bad("스킬 출처 설정 필드를 확인하세요.")
    identity = value.get("id")
    if (
        not isinstance(identity, str)
        or not SOURCE_ID.fullmatch(identity)
        or identity in RESERVED_SOURCES
    ):
        _bad("출처 ID는 소문자·숫자·하이픈으로 지정하고 builtin/project는 사용하지 마세요.")
    name = value.get("name", identity)
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        _bad("출처 이름은 비어 있지 않은 100자 이하 문자열이어야 합니다.")
    raw = value.get("path")
    if not isinstance(raw, str) or len(raw) > 4096 or "\0" in raw:
        _bad("출처 폴더의 절대 경로를 지정하세요.")
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        _bad("출처 폴더의 절대 경로를 지정하세요.")
    safe_path(path)
    enabled = value.get("enabled", True)
    if type(enabled) is not bool:
        _bad()
    if check_exists and enabled and not path.is_dir():
        _bad("사용할 스킬 출처 폴더가 존재하지 않습니다.")
    result = {"id": identity, "name": name, "path": str(path), "enabled": enabled}
    if "category" in value:
        if value["category"] not in CATEGORIES:
            _bad("지원하는 출처 분류를 선택하세요.")
        result["category"] = value["category"]
    return result


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate setting key")
        result[key] = value
    return result


def _categories(value, kind, name, source):
    override = value["category_overrides"].get(f"{kind}:{name}")
    if override is not None:
        return list(override)
    if kind in ("server", "tool"):
        return ["tools"]
    if source:
        registered = next((item for item in value["sources"] if item["id"] == source), None)
        if registered and registered.get("category"):
            return [registered["category"]]
    return builtin_categories(name) if source in (None, "builtin") else []


def validate(value, check_source_paths=False):
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        _bad()
    if type(value["schema"]) is not int or value["schema"] != 1:
        _bad("지원하지 않는 카탈로그 설정 버전입니다.")
    if value["exposure"] not in ("search-first", "all-native"):
        _bad("도구 노출은 search-first 또는 all-native로 지정하세요.")
    if type(value["usage_enabled"]) is not bool:
        _bad()
    sources = value["sources"]
    if not isinstance(sources, list) or len(sources) > 32:
        _bad("출처는 최대 32개까지 등록할 수 있습니다.")
    sources = [_source(source, check_exists=check_source_paths) for source in sources]
    if len({source["id"] for source in sources}) != len(sources):
        _bad("출처 ID는 중복할 수 없습니다.")
    disabled = value["disabled"]
    if not isinstance(disabled, dict) or set(disabled) != set(DEFAULTS["disabled"]):
        _bad()
    disabled = {
        "skill": _items(disabled["skill"], pattern=SKILL_ID),
        "server": _items(disabled["server"], pattern=SERVER_ID, maximum=100),
        "source": _items(disabled["source"], pattern=SOURCE_ID, maximum=64),
        "category": _items(disabled["category"], choices=CATEGORIES, maximum=len(CATEGORIES)),
    }
    overrides = value["category_overrides"]
    if not isinstance(overrides, dict) or len(overrides) > 500:
        _bad()
    normalized = {}
    for key, categories in overrides.items():
        if not isinstance(key, str):
            _bad()
        kind, separator, name = key.partition(":")
        pattern = SKILL_ID if kind == "skill" else SERVER_ID
        if kind not in ("skill", "server") or not separator or not pattern.fullmatch(name):
            _bad("분류 재정의 키는 skill:이름 또는 server:ID 형식이어야 합니다.")
        normalized[key] = _items(categories, choices=CATEGORIES, maximum=len(CATEGORIES))
    result = {
        "schema": 1,
        "exposure": value["exposure"],
        "sources": sources,
        "disabled": disabled,
        "category_overrides": normalized,
        "usage_enabled": value["usage_enabled"],
    }
    if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_SETTINGS_BYTES:
        _bad("카탈로그 설정 크기 제한을 초과했습니다.")
    return result


class CatalogPreferences:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().absolute()
        self.path = self.directory / "catalog-preferences.json"
        self.lock = CredentialLock(self.directory / "catalog-preferences.lock")

    def _read(self):
        safe_path(self.path)
        if not self.path.exists():
            return copy.deepcopy(DEFAULTS)
        try:
            if not self.path.is_file() or self.path.stat().st_size > MAX_SETTINGS_BYTES:
                raise ValueError
            text = self.path.read_text(encoding="utf-8")
            if len(text.encode()) > MAX_SETTINGS_BYTES:
                raise ValueError
            return validate(json.loads(text, object_pairs_hook=_json_object))
        except (ValueError, OSError, UnicodeError, RpcError) as exc:
            raise RpcError(-32045, "카탈로그 설정을 읽을 수 없습니다. 설정을 복구하세요.") from exc

    def get(self):
        safe_path(self.path)
        # Reading defaults should not create a state directory or lock file.
        if not self.path.exists():
            return copy.deepcopy(DEFAULTS)
        with self.lock:
            return self._read()

    def update(self, patch):
        if not isinstance(patch, dict) or set(patch) - set(DEFAULTS):
            _bad()
        safe_path(self.path)
        with self.lock:
            value = self._read()
            patch = copy.deepcopy(patch)
            if "disabled" in patch:
                disabled = patch.pop("disabled")
                if not isinstance(disabled, dict) or set(disabled) - set(DEFAULTS["disabled"]):
                    _bad()
                value["disabled"].update(disabled)
            value.update(patch)
            value = validate(value, check_source_paths="sources" in patch)
            atomic_json(self.path, value)
            return copy.deepcopy(value)

    def reset(self):
        """Explicit recovery also replaces a corrupt regular file, never a symlink."""
        safe_path(self.path)
        with self.lock:
            value = copy.deepcopy(DEFAULTS)
            atomic_json(self.path, value)
            return value

    def sources(self):
        return copy.deepcopy(self.get()["sources"])

    def categories(self, kind, name, source=None):
        return _categories(self.get(), kind, name, source)

    def allows(self, kind, name, server=None, source=None, categories=()):
        value = self.get()
        disabled = value["disabled"]
        if source in disabled["source"]:
            return False
        registered = next((item for item in value["sources"] if item["id"] == source), None)
        if registered and not registered["enabled"]:
            return False
        if kind == "server" and name in disabled["server"]:
            return False
        if server and server in disabled["server"]:
            return False
        if server and set(_categories(value, "server", server, None)).intersection(
            disabled["category"]
        ):
            return False
        if kind == "skill" and name in disabled["skill"]:
            return False
        selected = categories or _categories(value, kind, name, source)
        return not set(selected).intersection(disabled["category"])
