"""Transport-independent hub services and feature-aware protocol adapter."""

import base64
import copy
import hashlib
import json
import threading
import time
from pathlib import Path

from joongi_hub import __version__
from joongi_hub.agent_connections import AgentConnections
from joongi_hub.apps import app_resource_uri, wrap_app_html
from joongi_hub.auth import AuthManager, fingerprint
from joongi_hub.catalog_preferences import CATEGORIES, CatalogPreferences
from joongi_hub.catalog_skills import CatalogSkills
from joongi_hub.connections import ConnectionSettings, configuration
from joongi_hub.consent_schema import proxy_output
from joongi_hub.errors import RpcError
from joongi_hub.profiles import ProjectRegistry, Projects, ProjectSkills
from joongi_hub.resources import resource_uri, unwrap_resource
from joongi_hub.sculpt_review import TOOL as SCULPT_TOOL
from joongi_hub.sculpt_review import validate as validate_sculpt
from joongi_hub.search import (
    DEFAULT_DETAIL,
    DEFAULT_LIMIT,
    Document,
    SearchCache,
    parameter_text,
    rank,
)
from joongi_hub.skill_management import SkillManager
from joongi_hub.skills import Skills
from joongi_hub.state_store import describe
from joongi_hub.storage import Registry, TaskStore
from joongi_hub.tool_policy import ToolPolicy
from joongi_hub.upstream import MODERN, VERSIONS, Upstream, validate_server
from joongi_hub.usage_stats import UsageStats

INFO = {"name": "joongi-hub", "version": __version__}
TASK_EXTENSION = "io.modelcontextprotocol/tasks"
UI_EXTENSION = "io.modelcontextprotocol/ui"
SKILLS_EXTENSION = "io.modelcontextprotocol/skills"


def text_result(value):
    return {
        "content": [
            {
                "type": "text",
                "text": value if isinstance(value, str) else json.dumps(value, ensure_ascii=False),
            }
        ]
    }


def public_task(task, modern=False, include_result=True):
    result = {
        key: value for key, value in task.items() if key not in {"owner", "name", "executorPid"}
    }
    if not include_result:
        result.pop("result", None)
        result.pop("error", None)
    if not modern:
        result["ttl"] = result.pop("ttlMs", None)
        if "pollIntervalMs" in result:
            result["pollInterval"] = result.pop("pollIntervalMs")
    return result


def rewrite_resources(value, server_id):
    """Namespace only protocol-defined resource fields, never application data.

    Callers pass a protocol result, a tool/skill definition, or a list of
    resource/skill definitions. structuredContent, JSON Schema, arbitrary _meta
    and text/HTML remain opaque even when they contain keys named uri.
    """

    def metadata(item):
        if not isinstance(item, dict):
            return item
        result = copy.deepcopy(item)
        meta = result.get("_meta")
        if isinstance(meta, dict) and isinstance(meta.get("ui/resourceUri"), str):
            legacy = meta["ui/resourceUri"]
            meta.setdefault("ui", {}).setdefault("resourceUri", legacy)
            meta["ui/resourceUri"] = resource_uri(server_id, legacy)
        if isinstance(meta, dict) and isinstance(meta.get("ui"), dict):
            uri = meta["ui"].get("resourceUri")
            if isinstance(uri, str):
                meta["ui"]["resourceUri"] = resource_uri(server_id, uri)
        return result

    def resource(item):
        if not isinstance(item, dict):
            return item
        result = metadata(item)
        if isinstance(result.get("uri"), str):
            result["uri"] = resource_uri(server_id, result["uri"])
        # Native skill entries contain a typed resource manifest.
        if "frontmatter" in result and isinstance(result.get("resources"), list):
            result["resources"] = [resource(entry) for entry in result["resources"]]
        return result

    def block(item):
        if not isinstance(item, dict):
            return item
        result = metadata(item)
        if result.get("type") == "resource_link":
            return resource(result)
        if result.get("type") == "resource" and isinstance(result.get("resource"), dict):
            result["resource"] = resource(result["resource"])
        return result

    if isinstance(value, list):
        # Direct list callers are resources/list or native skill entries.
        return [resource(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = metadata(value)
    if "frontmatter" in result and isinstance(result.get("uri"), str):
        return resource(result)
    for key in ("resources", "contents", "skills"):
        if isinstance(result.get(key), list):
            result[key] = [resource(item) for item in result[key]]
    if isinstance(result.get("skill"), dict):
        result["skill"] = resource(result["skill"])
    if isinstance(result.get("content"), list):
        result["content"] = [block(item) for item in result["content"]]
    if isinstance(result.get("messages"), list):
        messages = []
        for message in result["messages"]:
            message = copy.deepcopy(message)
            if isinstance(message, dict):
                if isinstance(message.get("content"), dict):
                    message["content"] = block(message["content"])
                elif isinstance(message.get("content"), list):
                    message["content"] = [block(item) for item in message["content"]]
            messages.append(message)
        result["messages"] = messages
    return result


class Hub:
    def __init__(
        self,
        skills_dir: Path,
        state_dir: Path,
        project=None,
        root_hub=None,
        credential_store_factory=None,
    ):
        state_dir = Path(state_dir).expanduser().resolve()
        self.state_dir = state_dir
        self.root_hub = root_hub or self
        self.project = project
        self.profile_id = project["id"] if project else "global"
        self.projects = self.root_hub.projects if root_hub else Projects(state_dir)
        self.profile_hubs = {}
        self.common_skills = self.root_hub.common_skills if root_hub else Skills(skills_dir)
        self.catalog_preferences = CatalogPreferences(state_dir)
        base_skills = ProjectSkills(root_hub.skills, project) if project else self.common_skills
        self.skills = CatalogSkills(base_skills, self.catalog_preferences)
        self.search_cache = SearchCache()
        self.usage_stats = UsageStats(state_dir)
        self.credential_store_factory = (
            root_hub.credential_store_factory if root_hub else credential_store_factory
        )
        self.auth = AuthManager(
            state_dir,
            store=self.credential_store_factory(state_dir / "auth/credentials.json")
            if self.credential_store_factory
            else None,
        )
        self.registry = (
            ProjectRegistry(state_dir, self.root_hub.registry, project["common_servers"])
            if project
            else Registry(state_dir)
        )
        self.tasks = TaskStore(state_dir)
        self.tool_policy = ToolPolicy(state_dir)
        self.auth.consent_reset = self.tool_policy.revoke_server
        from joongi_hub.agent_approval import AgentApprovals
        from joongi_hub.agent_login import AgentLogins

        self.agent_logins = AgentLogins(self)
        self.agent_approvals = AgentApprovals(self)
        from joongi_hub.agent_panel import AgentPanels

        self.agent_panels = root_hub.agent_panels if root_hub else AgentPanels(self)
        self.clients = {}
        self.health = {}
        self.lock = threading.RLock()
        self.task_slots = threading.BoundedSemaphore(8)
        self.cancelled = {}
        self.task_threads = set()
        self.remote_tasks = {}
        self.answered_inputs = {}
        self.input_calls = {}
        self.closing = False
        self.skill_manager = SkillManager(self)
        self.connection_settings = ConnectionSettings(
            state_dir, self.root_hub.connection_settings if project else None
        )
        self.agent_connections = AgentConnections(self)

    def profile_connection(self, identity, **options):
        return configuration(self.root_hub, identity, **options)

    def scoped(self, profile="global"):
        root = self.root_hub
        if profile == "global":
            return root
        project = root.projects.get(profile)
        with root.lock:
            child = root.profile_hubs.get(profile)
            if child and child.project != project:
                child.close()
                child = None
            if child is None:
                child = Hub(
                    root.common_skills.directory,
                    root.projects.state_directory(project),
                    project=project,
                    root_hub=root,
                )
                child.auth.callback_url = root.auth.callback_url
                root.profile_hubs[profile] = child
            return child

    def close(self):
        self.closing = True
        if self.root_hub is self:
            self.agent_panels.close()
        self.agent_logins.close()
        self.agent_approvals.close()
        for child in self.profile_hubs.values():
            child.close()
        for event in list(self.cancelled.values()):
            event.set()
        for client in list(self.clients.values()):
            client.close()
        with self.lock:
            workers = list(self.task_threads)
        deadline = time.monotonic() + 10
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(max(0, deadline - time.monotonic()))

    def register(self, data):
        config = validate_server(data)
        if any(source["id"] == config["id"] for source in self.catalog_preferences.sources()):
            raise RpcError(-32602, "MCP ID conflicts with a registered local skill source")
        with self.lock:
            previous = self.clients.pop(config["id"], None)
            if previous:
                previous.close()
            self.health.pop(config["id"], None)
            old_config = next((c for c in self.registry.list() if c["id"] == config["id"]), None)
            if old_config and fingerprint(old_config) != fingerprint(config):
                self.auth.logout(old_config, revoke=False)
            self.registry.put(config)
        if self.root_hub is self:
            for child in self.profile_hubs.values():
                child.close()
            self.profile_hubs.clear()
        return config

    def remove(self, server_id):
        with self.lock:
            config = next((c for c in self.registry.list() if c["id"] == server_id), None)
            self.registry.delete(server_id)
            if config:
                self.auth.logout(config)
            client = self.clients.pop(server_id, None)
            if client:
                client.close()
            self.health.pop(server_id, None)
        if self.root_hub is self:
            for child in self.profile_hubs.values():
                child.close()
            self.profile_hubs.clear()

    def client(self, server_id):
        with self.lock:
            config = next((s for s in self.registry.list() if s["id"] == server_id), None)
            if not config or not config["enabled"]:
                raise RpcError(-32602, "Unknown or disabled server")
            if server_id in self.clients and self.clients[server_id].config != config:
                self.clients.pop(server_id).close()
            if server_id not in self.clients:
                self.clients[server_id] = Upstream(config, auth=self.auth)
            return self.clients[server_id]

    def probe(self, server_id):
        try:
            client = self.client(server_id)
            client.refresh()
            self.health[server_id] = {"status": "connected", "error": None}
            return {
                "id": server_id,
                "status": "connected",
                "protocol_version": client.version,
                "tools": client.tools,
                "capabilities": client.capabilities,
            }
        except (RpcError, OSError) as exc:
            message = str(exc) if isinstance(exc, RpcError) else "Cannot start upstream process"
            self.health[server_id] = {"status": "error", "error": message}
            config = next((c for c in self.registry.list() if c["id"] == server_id), None)
            if config and config.get("auth", {}).get("type") in {"oauth", "device_code"}:
                status = self.auth.status(config)
                if status["login_required"]:
                    raise RpcError(
                        -32040,
                        (
                            "MCP 인증이 필요합니다. hub_auth_start로 로그인 링크를 만들고 "
                            "사용자 승인 후 다시 연결하세요."
                        ),
                        {
                            "server": server_id,
                            "next_tool": "hub_auth_start",
                            "arguments": {"server": server_id},
                        },
                    ) from exc
            raise RpcError(-32000, message) from exc

    @staticmethod
    def compatibility():
        return {
            "versions": VERSIONS,
            "transports": ["stdio", "http"],
            "tools": "supported",
            "resources": "supported",
            "prompts": "supported",
            "tasks": "2025 polling/result/cancel; 2026 polling/update/cancel with input requests",
            "apps": "local sandboxed AppBridge renderer and origin-scoped callbacks; "
            "external clients need their own Apps host",
            "skills": "native skills/list and skills/get with SHA-256 manifests, safe YAML "
            "and text/binary supporting resources",
            "limitations": [
                "No sampling, elicitation, subscriptions or legacy HTTP+SSE transport",
                "Local single-user trust boundary; not a multi-tenant server",
                "Cancellation cannot undo upstream side effects",
                "Running tasks become failed after hub restart",
            ],
        }

    def state(self):
        servers = []
        for config in self.registry.list():
            client = self.clients.get(config["id"])
            item = {
                **config,
                "status": "disconnected",
                "error": None,
                "tools": [],
                "capabilities": {},
                **self.health.get(config["id"], {}),
            }
            if client and client.version:
                item.update(
                    protocol_version=client.version,
                    tools=client.tools,
                    capabilities=client.capabilities,
                )
            item["auth_status"] = self.auth.status(config)
            servers.append(item)
        return {
            "version": __version__,
            "storage": describe(self.state_dir, len(servers)),
            "profile": self.profile_id,
            "project": self.project,
            "skills": self.skills.list(),
            "servers": servers,
            "tasks": self.tasks.list(),
            "compatibility": self.compatibility(),
        }

    def search(
        self,
        query,
        *,
        mode="keyword",
        match="any",
        limit=DEFAULT_LIMIT,
        detail=DEFAULT_DETAIL,
        kind="all",
        server=None,
    ):
        started = time.monotonic()
        outcome = "success"
        try:
            result = self._search(
                query, mode=mode, match=match, limit=limit, detail=detail, kind=kind, server=server
            )
            outcome = "success" if result else "empty"
            return result
        except Exception:
            outcome = "error"
            raise
        finally:
            self.record_usage("search", "hub_search", outcome, (time.monotonic() - started) * 1000)

    def _search(self, query, **options):
        return rank(self.catalog_documents(), query, cache=self.search_cache, **options)

    def catalog_documents(self):
        documents = []
        for skill in self.skills.list():
            documents.append(
                Document(
                    {"kind": "skill", **skill},
                    {
                        "name": skill["name"],
                        "aliases": skill["name"],
                        "description": skill["description"],
                        "server": "",
                        "parameters": "",
                    },
                )
            )
        for config in self.registry.list():
            if not self.catalog_server_enabled(config):
                continue
            client = self.clients.get(config["id"])
            status = self.health.get(config["id"], {}).get("status", "disconnected")
            value = {
                "kind": "server",
                "name": config["id"],
                "server": config["id"],
                "description": config["name"] + " · " + config["transport"],
                "status": status,
                "enabled": config["enabled"],
                "next_tool": "hub_connect" if config["enabled"] else None,
            }
            # Registration metadata only: do not expose env/headers/auth/URL
            # secrets, initialize a server, or discover its tools during search.
            documents.append(
                Document(
                    value,
                    {
                        "name": config["id"],
                        "aliases": config["name"],
                        "description": value["description"],
                        "server": config["id"],
                        "parameters": "",
                    },
                )
            )
            if not config["enabled"] or not client:
                continue
            for entry in client.skill_entries:
                if not self.remote_skill_enabled(config["id"], entry):
                    continue
                frontmatter = entry.get("frontmatter", {})
                name = frontmatter.get("name", "")
                description = frontmatter.get("description", "")
                value = {
                    "kind": "skill",
                    "name": config["id"] + "__" + name,
                    "description": description,
                    "server": config["id"],
                    "uri": resource_uri(config["id"], entry["uri"]),
                }
                documents.append(
                    Document(
                        value,
                        {
                            "name": value["name"],
                            "aliases": name,
                            "description": description,
                            "server": config["id"] + " " + config["name"],
                            "parameters": "",
                        },
                    )
                )
            for tool in client.tools:
                value = {
                    "kind": "tool",
                    "name": config["id"] + "__" + tool["name"],
                    "description": tool.get("description", ""),
                    "server": config["id"],
                    "inputSchema": tool.get("inputSchema", {}),
                }
                documents.append(
                    Document(
                        value,
                        {
                            "name": value["name"],
                            "aliases": tool["name"],
                            "description": value["description"],
                            "server": config["id"] + " " + config["name"],
                            "parameters": parameter_text(value["inputSchema"]),
                        },
                    )
                )
        return documents

    def catalog_server_enabled(self, config):
        identity = config["id"]
        categories = self.catalog_preferences.categories("server", identity)
        if not self.catalog_preferences.allows("server", identity, categories=categories):
            return False
        if config.get("inherited"):
            root = self.root_hub.catalog_preferences
            return root.allows("server", identity, categories=root.categories("server", identity))
        return True

    def remote_skill_enabled(self, server, entry):
        config = next((item for item in self.registry.list() if item["id"] == server), None)
        if config is None or not self.catalog_server_enabled(config):
            return False
        name = server + "__" + entry.get("frontmatter", {}).get("name", "")
        return self.catalog_preferences.allows(
            "skill",
            name,
            server=server,
            categories=self.catalog_preferences.categories("skill", name),
        )

    def catalog_settings(self, *, owner=True):
        settings = self.catalog_preferences.get()
        if not owner:
            settings = copy.deepcopy(settings)
            for source in settings["sources"]:
                source.pop("path", None)
        skills = self.skills.inventory()
        for server_id, client in list(self.clients.items()):
            for entry in client.skill_entries:
                identity = server_id + "__" + entry.get("frontmatter", {}).get("name", "")
                skills.append(
                    {
                        "name": identity,
                        "server": server_id,
                        "description": entry.get("frontmatter", {}).get("description", ""),
                        "source": "mcp:" + server_id,
                        "categories": self.catalog_preferences.categories("skill", identity),
                        "search_enabled": self.remote_skill_enabled(server_id, entry),
                    }
                )
        servers = [
            {
                "id": item["id"],
                "name": item["name"],
                "search_enabled": self.catalog_server_enabled(item),
            }
            for item in self.registry.list()
        ]
        if not owner:
            return {
                "settings": settings,
                "categories": list(CATEGORIES),
                "counts": {"skills": len(skills), "servers": len(servers)},
                "cache": self.search_cache.status(),
                "profile": self.profile_id,
                "native_installation": "Independent; use an installation plan",
            }
        return {
            "settings": settings,
            "categories": list(CATEGORIES),
            "inventory": {"skills": skills, "servers": servers},
            "cache": self.search_cache.status(),
            "profile": self.profile_id,
            "native_installation": "Independent of catalog selection; use an installation plan",
        }

    def configure_catalog(self, patch=None, *, reset=False):
        if not reset and isinstance(patch, dict) and isinstance(patch.get("sources"), list):
            server_ids = {item["id"] for item in self.registry.list()}
            if any(
                isinstance(source, dict) and source.get("id") in server_ids
                for source in patch["sources"]
            ):
                raise RpcError(-32602, "Local skill source ID conflicts with a registered MCP ID")
        value = (
            self.catalog_preferences.reset() if reset else self.catalog_preferences.update(patch)
        )
        self.search_cache.clear()
        return {
            "settings": value,
            "profile": self.profile_id,
            "reconnect_required_for_native_tools": True,
        }

    def catalog_item(self, kind, name):
        started = time.monotonic()
        identity, outcome = "unavailable", "error"
        try:
            result = self._catalog_item(kind, name)
            identity, outcome = result["name"], "success"
            return result
        finally:
            self.record_usage("detail", identity, outcome, (time.monotonic() - started) * 1000)

    def _catalog_item(self, kind, name):
        if (
            not isinstance(kind, str)
            or kind not in {"skill", "server", "tool"}
            or not isinstance(name, str)
        ):
            raise RpcError(-32602, "Choose an exact skill/server/tool name")
        candidates = [
            document.value
            for document in self.catalog_documents()
            if document.value["kind"] == kind and document.value["name"] == name
        ]
        if len(candidates) != 1:
            raise RpcError(-32602, "Catalog item is unavailable or ambiguous in this profile")
        item = candidates[0]
        if kind == "tool":
            server = item["server"]
            original_name = name[len(server) + 2 :]
            original = next(
                tool for tool in self.clients[server].tools if tool["name"] == original_name
            )
            return {
                "kind": kind,
                "server": server,
                **proxy_output(
                    rewrite_resources({**original, "name": name}, server),
                    self.clients[server].config,
                    original_name,
                ),
            }
        return copy.deepcopy(item)

    def record_usage(self, kind, name, outcome, duration_ms):
        try:
            self.usage_stats.record(
                kind,
                name,
                outcome,
                duration_ms,
                enabled=self.catalog_preferences.get()["usage_enabled"],
            )
        except (RpcError, OSError):
            # Optional diagnostics must never change the outcome of an actual call.
            pass

    def tools(self):
        tools = [
            {
                "name": "hub_search",
                "annotations": {"readOnlyHint": True},
                "description": (
                    "Unified search for skills, registered MCP servers and connected tools. "
                    "Server results include disconnected registrations; connect explicitly with "
                    "hub_connect before tool discovery. Search never starts a server. "
                    "Lexical, not semantic or filesystem search. Use short keywords/identifiers. "
                    "Defaults: limit=5, detail=summary. Select hub_get_item(kind,name) for the "
                    "exact original schema, then hub_call. "
                    "mode=literal uses fixed strings; mode=regex uses ripgrep (rg required), "
                    "e.g. markdown|convert. match=all narrows keywords. Retry alternate/English "
                    "terms on no results; rewrite Korean requests into short English keywords "
                    "when needed. Read selected skills before working."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "maxLength": 1000},
                        "mode": {
                            "type": "string",
                            "enum": ["keyword", "literal", "regex"],
                            "default": "keyword",
                        },
                        "match": {"type": "string", "enum": ["any", "all"], "default": "any"},
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "default": DEFAULT_LIMIT,
                        },
                        "detail": {
                            "type": "string",
                            "enum": ["summary", "full"],
                            "default": DEFAULT_DETAIL,
                        },
                        "kind": {
                            "type": "string",
                            "enum": ["all", "skill", "tool", "server"],
                            "default": "all",
                        },
                        "server": {"type": "string", "maxLength": 48},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "hub_read_skill",
                "description": "Read SKILL.md or one selected reference file of a skill.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "path": {"type": "string", "default": "SKILL.md"},
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "hub_status",
                "description": "등록 수·임시 저장소 경고·백업 유무를 확인합니다. "
                "절대 경로는 로컬 관리 화면에서 확인하세요.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "hub_list_servers",
                "description": "List registered MCP servers and connection status.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "hub_read_resource",
                "description": "Read a selected skill/resource URI returned by "
                "hub_search or resources/list, preserving its origin.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"uri": {"type": "string"}},
                    "required": ["uri"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "hub_connect",
                "description": "Connect a registered server and discover its tools. "
                "Registration is done in the local control panel.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"server": {"type": "string"}},
                    "required": ["server"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "hub_call",
                "description": "Call a discovered tool by its server__tool name and arguments.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "arguments": {"type": "object"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
        ]
        tools.extend(
            [
                {
                    "name": "hub_skills_status",
                    "description": "현재 범위의 스킬 설치·버전 고정·수정 상태를 조회합니다.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "hub_skills_plan",
                    "description": (
                        "스킬 설치·업데이트·제거·고정 계획을 만듭니다. "
                        "대상 파일은 아직 변경하지 않습니다."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["install", "update", "remove", "pin", "unpin"],
                            },
                            "names": {"type": "array", "items": {"type": "string"}},
                            "agents": {"type": "array", "items": {"type": "string"}},
                            "refresh": {"type": "boolean"},
                        },
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "hub_skills_apply",
                    "description": (
                        "검토한 스킬 계획을 현재 범위에 적용합니다. "
                        "충돌·수정·고정된 파일은 보호합니다."
                    ),
                    "annotations": {"readOnlyHint": False, "destructiveHint": True},
                    "inputSchema": {
                        "type": "object",
                        "properties": {"plan_id": {"type": "string"}},
                        "required": ["plan_id"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "hub_auth_status",
                    "description": (
                        "연결된 MCP의 인증 상태를 비밀값 없이 조회합니다. "
                        "login_required이면 hub_auth_start를 호출하세요."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {"server": {"type": "string"}},
                        "additionalProperties": False,
                    },
                },
            ]
        )
        tools.extend(
            [
                {
                    "name": "hub_auth_start",
                    "description": (
                        "Start upstream OAuth/device login without the control panel. "
                        "Show the returned url to the user for browser approval, "
                        "then hub_auth_poll and hub_connect. Never ask for tokens."
                    ),
                    "annotations": {
                        "readOnlyHint": False,
                        "destructiveHint": False,
                        "openWorldHint": True,
                    },
                    "inputSchema": {
                        "type": "object",
                        "properties": {"server": {"type": "string"}},
                        "required": ["server"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "hub_auth_poll",
                    "description": (
                        "Check agent-started OAuth login or poll device authorization. "
                        "Returns status, never access/refresh tokens. "
                        "Retry hub_connect after authenticated."
                    ),
                    "annotations": {"readOnlyHint": False, "destructiveHint": False},
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "server": {"type": "string"},
                            "login_id": {"type": "string"},
                        },
                        "required": ["server"],
                        "additionalProperties": False,
                    },
                },
            ]
        )
        for name, description in (
            (
                "hub_approval_request",
                "Open a local owner-browser review for a pending approval_id. "
                "Only a local stdio connection can open it. Never approves a call itself. "
                "Ask the user to review the browser, then hub_approval_status; "
                "retry the original exact call only after approved.",
            ),
            (
                "hub_approval_status",
                "Check pending/approved/denied/unavailable call consent. "
                "Use wait_seconds=20 to wait for the user decision without repeated polling. "
                "No approval capability is returned. Do not retry a denied call.",
            ),
        ):
            tools.append(
                {
                    "name": name,
                    "description": description,
                    "execution": {"taskSupport": "forbidden"},
                    "annotations": {
                        "readOnlyHint": name.endswith("status"),
                        "destructiveHint": False,
                        "openWorldHint": False,
                    },
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "approval_id": {"type": "string", "minLength": 40, "maxLength": 40},
                            **(
                                {
                                    "wait_seconds": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 20,
                                        "default": 0,
                                    }
                                }
                                if name == "hub_approval_status"
                                else {}
                            ),
                        },
                        "required": ["approval_id"],
                        "additionalProperties": False,
                    },
                }
            )
        tools.append(
            {
                "name": "hub_open_settings",
                "description": "Open Hub settings in the local owner's browser. "
                "Temporary by default: "
                "closing the browser stops only the settings web listener, not stdio. "
                "Use persistent only when the user explicitly wants an always-running panel. "
                "Reuses an existing persistent panel. Requires a local stdio connection; "
                "no management URL or token is returned to the agent.",
                "execution": {"taskSupport": "forbidden"},
                "annotations": {"readOnlyHint": False, "destructiveHint": False},
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["temporary", "persistent"],
                            "default": "temporary",
                        }
                    },
                    "additionalProperties": False,
                },
            }
        )
        tools.extend(
            [
                {
                    "name": "hub_get_item",
                    "description": "Stage 2: read one exact catalog item and its "
                    "original schema before invocation. Does not connect or execute a server.",
                    "annotations": {"readOnlyHint": True},
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string", "enum": ["skill", "server", "tool"]},
                            "name": {"type": "string"},
                        },
                        "required": ["kind", "name"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "hub_catalog_status",
                    "description": "Read catalog source/group selections "
                    "without private source paths. Catalog preferences are not OS access controls.",
                    "annotations": {"readOnlyHint": True},
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "hub_catalog_configure",
                    "description": "Change catalog search selection, "
                    "sources or optional local usage counters at the user's request. "
                    "Local stdio owner "
                    "only; HTTP MCP cannot change owner settings. "
                    "Native installed skills are separate.",
                    "execution": {"taskSupport": "forbidden"},
                    "inputSchema": {
                        "type": "object",
                        "properties": {"patch": {"type": "object"}},
                        "required": ["patch"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "hub_catalog_reset",
                    "description": "Reset this profile's catalog preferences "
                    "at the user's request. Does not delete skill files, "
                    "credentials or usage data. "
                    "Local stdio owner only.",
                    "execution": {"taskSupport": "forbidden"},
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "hub_catalog_usage",
                    "description": "Read local opt-in aggregate counters. "
                    "No query, arguments, payloads or tokens are stored.",
                    "annotations": {"readOnlyHint": True},
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "hub_catalog_usage_reset",
                    "description": "Delete local aggregate counters. "
                    "Local stdio owner only; does not change catalog preferences.",
                    "execution": {"taskSupport": "forbidden"},
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            ]
        )
        tools.append(copy.deepcopy(SCULPT_TOOL))
        # All transports share this original-metadata decision, before legacy task augmentation.
        expose_all = self.catalog_preferences.get()["exposure"] == "all-native"
        for server_id, client in list(self.clients.items()):
            if client.version and self.catalog_server_enabled(client.config):
                for tool in client.tools:
                    is_task = tool.get("execution", {}).get("taskSupport") in {
                        "optional",
                        "required",
                    }
                    if not (expose_all or app_resource_uri(tool) or is_task):
                        continue
                    tools.append(
                        proxy_output(
                            rewrite_resources(
                                {**tool, "name": server_id + "__" + tool["name"]}, server_id
                            ),
                            client.config,
                            tool["name"],
                        )
                    )
        # App SDK calls use their original server tool names. App-only aliases
        # preserve that contract when the name identifies exactly one upstream.
        for server_id, client in list(self.clients.items()):
            has_app = any(app_resource_uri(tool) for tool in client.tools)
            if not client.version or not has_app or not self.catalog_server_enabled(client.config):
                continue
            for tool in client.tools:
                matches = self.alias_matches(tool["name"])
                namespaced = server_id + "__" + tool["name"]
                if not any(candidate["name"] == namespaced for candidate in tools):
                    scoped = proxy_output(
                        rewrite_resources({**tool, "name": namespaced}, server_id),
                        client.config,
                        tool["name"],
                    )
                    scoped.setdefault("_meta", {}).setdefault("ui", {})["visibility"] = ["app"]
                    tools.append(scoped)
                if len(matches) == 1 and not tool["name"].startswith("hub_"):
                    alias = proxy_output(
                        rewrite_resources(tool, server_id), client.config, tool["name"]
                    )
                    alias.setdefault("_meta", {}).setdefault("ui", {})["visibility"] = ["app"]
                    tools.append(alias)
        return tools

    def alias_matches(self, name):
        return [
            (server_id, tool)
            for server_id, client in list(self.clients.items())
            if client.version
            for tool in client.tools
            if tool.get("name") == name
        ]

    def invoke(
        self,
        name,
        arguments,
        cancel_event=None,
        local_task_id=None,
        input_responses=None,
        request_state=None,
        local_owner=False,
    ):
        started = time.monotonic()
        outcome = "success"
        try:
            return self._invoke(
                name,
                arguments,
                cancel_event,
                local_task_id,
                input_responses,
                request_state,
                local_owner,
            )
        except Exception as exc:
            outcome = "approval_required" if getattr(exc, "consent_required", False) else "error"
            raise
        finally:
            if isinstance(name, str):
                if "__" in name:
                    server, original = name.split("__", 1)
                    client = self.clients.get(server)
                    known = client and any(tool.get("name") == original for tool in client.tools)
                    self.record_usage(
                        "tool",
                        name if known else "unavailable",
                        outcome,
                        (time.monotonic() - started) * 1000,
                    )

    def _invoke(
        self,
        name,
        arguments,
        cancel_event=None,
        local_task_id=None,
        input_responses=None,
        request_state=None,
        local_owner=False,
    ):
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise RpcError(-32602, "Tool name and arguments must be a string and object")
        if name == "hub_get_item":
            if set(arguments) != {"kind", "name"}:
                raise RpcError(-32602, "Choose kind and exact name")
            return text_result(self.catalog_item(**arguments))
        if name == "hub_catalog_status":
            if arguments:
                raise RpcError(-32602, "Catalog status takes no arguments")
            return text_result(self.catalog_settings(owner=False))
        if name in {"hub_catalog_configure", "hub_catalog_reset", "hub_catalog_usage_reset"}:
            if not local_owner:
                raise RpcError(
                    -32043, "Catalog changes require the local stdio owner or management UI"
                )
            if name == "hub_catalog_configure":
                if set(arguments) != {"patch"}:
                    raise RpcError(-32602, "Provide a catalog settings patch")
                self.configure_catalog(arguments["patch"])
                return text_result(self.catalog_settings(owner=False))
            if arguments:
                raise RpcError(-32602, "Reset takes no arguments")
            if name == "hub_catalog_reset":
                self.configure_catalog(reset=True)
                return text_result(self.catalog_settings(owner=False))
            self.usage_stats.reset()
            return text_result({"reset": True})
        if name == "hub_catalog_usage":
            if arguments:
                raise RpcError(-32602, "Usage status takes no arguments")
            return text_result(
                self.usage_stats.snapshot(enabled=self.catalog_preferences.get()["usage_enabled"])
            )
        if name == "hub_open_settings":
            if not local_owner:
                raise RpcError(-32043, "설정 창은 로컬 stdio 연결에서만 열 수 있습니다.")
            if set(arguments) - {"mode"}:
                raise RpcError(-32602, "설정 화면에는 mode만 지정하세요.")
            return text_result(self.agent_panels.open(self.profile_id, **arguments))
        if name in {"hub_approval_request", "hub_approval_status"}:
            allowed = (
                {"approval_id", "wait_seconds"} if name.endswith("status") else {"approval_id"}
            )
            if "approval_id" not in arguments or set(arguments) - allowed:
                raise RpcError(-32602, "승인 조회 필드를 확인하세요.")
            if name == "hub_approval_request":
                if not local_owner:
                    raise RpcError(
                        -32043,
                        "승인창은 로컬 stdio 연결에서만 열 수 있습니다. "
                        "로컬 터미널에서 joongi-hub open을 사용하세요.",
                    )
                return text_result(self.agent_approvals.request(arguments["approval_id"]))
            return text_result(self.agent_approvals.wait_status(**arguments))
        if name == "hub_skills_status":
            return text_result(self.skill_manager.status(include_paths=False))
        if name == "hub_skills_plan":
            if set(arguments) - {"operation", "names", "agents", "refresh"}:
                raise RpcError(-32602, "지원하지 않는 스킬 계획 필드입니다.")
            return text_result(self.skill_manager.plan(**arguments))
        if name == "hub_skills_apply":
            return text_result(self.skill_manager.apply(arguments.get("plan_id")))
        if name == "hub_auth_start":
            if set(arguments) != {"server"}:
                raise RpcError(-32602, "로그인 시작에는 server만 지정하세요.")
            return text_result(self.agent_logins.start(arguments["server"]))
        if name == "hub_auth_poll":
            if set(arguments) - {"server", "login_id"} or "server" not in arguments:
                raise RpcError(-32602, "인증 상태 조회 필드를 확인하세요.")
            return text_result(self.agent_logins.poll(**arguments))
        if name == "hub_auth_status":
            configs = self.registry.list()
            if arguments.get("server"):
                configs = [c for c in configs if c["id"] == arguments["server"]]
                if not configs:
                    raise RpcError(-32602, "등록되지 않은 서버입니다.")
            return text_result([{"server": c["id"], **self.auth.status(c)} for c in configs])
        if name == "hub_3d_review":
            if set(arguments) != {"target_stage", "report"}:
                raise RpcError(-32602, "target_stage와 report만 지정하세요.")
            return text_result(validate_sculpt(**arguments))
        if name == "hub_search":
            if set(arguments) - {"query", "mode", "match", "limit", "detail", "kind", "server"}:
                raise RpcError(-32602, "Unknown search options")
            return text_result(self.search(**{"query": "", **arguments}))
        if name == "hub_read_skill":
            return text_result(
                self.read_skill(arguments.get("name"), arguments.get("path", "SKILL.md"))
            )
        if name == "hub_list_servers":
            return text_result(
                [
                    {
                        "id": config["id"],
                        "name": config["name"],
                        "transport": config["transport"],
                        "enabled": config["enabled"],
                        "status": self.health.get(config["id"], {}).get("status", "disconnected"),
                        "search_enabled": self.catalog_server_enabled(config),
                        "tool_count": len(self.clients[config["id"]].tools)
                        if config["id"] in self.clients
                        else 0,
                    }
                    for config in self.registry.list()
                ]
            )
        if name == "hub_status":
            return text_result(
                {
                    **describe(self.state_dir, len(self.registry.list()), include_paths=False),
                    "profile": self.profile_id,
                }
            )
        if name == "hub_read_resource":
            return text_result(self.read_resource(arguments.get("uri", "")))
        if name == "hub_connect":
            connected = self.probe(arguments.get("server"))
            return text_result(
                {
                    "server": arguments.get("server"),
                    "status": connected["status"],
                    "protocol_version": connected["protocol_version"],
                    "tool_count": len(connected["tools"]),
                    "next_tool": "hub_search",
                    "refresh_native_tools": True,
                }
            )
        if name == "hub_call":
            return self.invoke(
                arguments.get("name"),
                arguments.get("arguments", {}),
                cancel_event,
                local_task_id,
                input_responses,
                request_state,
                local_owner,
            )
        if "__" not in name:
            matches = self.alias_matches(name)
            if len(matches) != 1:
                raise RpcError(-32602, "Unknown or ambiguous app tool name; use server__tool")
            return self.invoke(
                matches[0][0] + "__" + name,
                arguments,
                cancel_event,
                local_task_id,
                input_responses,
                request_state,
                local_owner,
            )
        server_id, tool_name = name.split("__", 1)
        client = self.client(server_id)
        client.connect()
        tool = next((tool for tool in client.tools if tool.get("name") == tool_name), None)
        if tool is None:
            raise RpcError(-32602, "Tool not found on the selected server")
        consent_epoch = self.auth.consent_epoch(client.config)
        try:
            self.tool_policy.authorize(
                client.config,
                tool,
                arguments,
                {"inputResponses": input_responses, "requestState": request_state},
                auth_epoch=consent_epoch,
            )
        except RpcError as exc:
            self.approval_error(exc, local_owner)
            raise
        params = {"name": tool_name, "arguments": arguments}
        if input_responses is not None:
            if not isinstance(input_responses, dict):
                raise RpcError(-32602, "inputResponses must be an object")
            params["inputResponses"] = input_responses
        if request_state is not None:
            if not isinstance(request_state, str):
                raise RpcError(-32602, "requestState must be text")
            params["requestState"] = request_state
        task_support = tool.get("execution", {}).get("taskSupport")
        if client.version != MODERN and task_support in {"required", "optional"}:
            task_requests = client.capabilities.get("tasks", {}).get("requests", {})
            supports_tasks = "call" in task_requests.get("tools", {})
            if task_support == "required" and not supports_tasks:
                raise RpcError(-32021, "Upstream requires Tasks but did not advertise support")
            if supports_tasks:
                params["task"] = {"ttl": 86400000}
        with self.auth.guard_consent(client.config, consent_epoch):
            result = client.request("tools/call", params)
        if isinstance(result.get("_meta"), dict):
            result["_meta"].pop("joongi-hub/approval", None)
        deadline = time.monotonic() + 3600
        while result.get("resultType") == "input_required":
            if not local_task_id:
                return result
            requests = result.get("inputRequests", {})
            if not isinstance(requests, dict):
                raise RpcError(-32000, "Invalid upstream inputRequests")
            continuation = {"event": threading.Event(), "responses": {}}
            self.input_calls[local_task_id] = continuation
            self.tasks.update(
                local_task_id,
                status="input_required" if requests else "working",
                inputRequests=requests,
            )
            try:
                while requests and not continuation["event"].wait(0.1):
                    if (
                        self.closing
                        or time.monotonic() >= deadline
                        or (cancel_event and cancel_event.is_set())
                    ):
                        raise RpcError(-32000, "Input wait was cancelled or timed out")
                if "requestState" in result:
                    params["requestState"] = result["requestState"]
                if continuation["responses"]:
                    params["inputResponses"] = continuation["responses"]
                if not requests:
                    if time.monotonic() >= deadline:
                        raise RpcError(-32000, "Input retry deadline exceeded")
                    time.sleep(0.1)
                self.tasks.update(local_task_id, status="working", inputRequests={})
                with self.auth.guard_consent(client.config, consent_epoch):
                    result = client.request("tools/call", params)
            finally:
                self.input_calls.pop(local_task_id, None)
        remote = result if result.get("resultType") == "task" else result.get("task")
        if remote:
            remote_id = remote["taskId"]
            if local_task_id:
                self.remote_tasks[local_task_id] = (client, remote_id)
                self.answered_inputs[local_task_id] = set()
            deadline = time.monotonic() + 3600
            try:
                while time.monotonic() < deadline and not self.closing:
                    if cancel_event and cancel_event.wait(0.5):
                        try:
                            client.request("tasks/cancel", {"taskId": remote_id})
                        finally:
                            raise RpcError(-32000, "Task cancelled")
                    if not cancel_event:
                        time.sleep(0.5)
                    task = client.request("tasks/get", {"taskId": remote_id})
                    if task["status"] == "completed":
                        result = (
                            task.get("result")
                            if client.version == MODERN
                            else client.request("tasks/result", {"taskId": remote_id})
                        )
                        break
                    if task["status"] == "input_required":
                        if not local_task_id:
                            raise RpcError(
                                -32021, "Run this tool as a task to provide interactive input"
                            )
                        pending = {
                            key: request
                            for key, request in task.get("inputRequests", {}).items()
                            if key not in self.answered_inputs.get(local_task_id, set())
                        }
                        self.tasks.update(
                            local_task_id,
                            status="input_required" if pending else "working",
                            inputRequests=pending,
                        )
                        continue
                    if (
                        local_task_id
                        and self.tasks.get(local_task_id)["status"] == "input_required"
                    ):
                        self.tasks.update(local_task_id, status="working", inputRequests={})
                    if task["status"] in {"failed", "cancelled"}:
                        raise RpcError(-32000, "Upstream task " + task["status"])
                else:
                    raise RpcError(-32000, "Task polling exceeded one hour or hub is stopping")
            finally:
                if local_task_id:
                    self.remote_tasks.pop(local_task_id, None)
                    self.answered_inputs.pop(local_task_id, None)
        if isinstance(result.get("_meta"), dict):
            result["_meta"].pop("joongi-hub/approval", None)
        return rewrite_resources(result, server_id)

    def approval_error(self, exc, local_owner):
        if exc.code != -32043 or not isinstance(exc.data, dict) or not exc.data.get("approval_id"):
            return
        data = {
            **exc.data,
            "next_tool": "hub_approval_request",
            "arguments": {"approval_id": exc.data["approval_id"]},
        }
        if local_owner:
            try:
                data.update(self.agent_approvals.request(exc.data["approval_id"]))
            except Exception:
                data["browser_opened"] = False
        if data.get("browser_opened"):
            data["next_tool"] = "hub_approval_status"
            data["arguments"] = {"approval_id": exc.data["approval_id"], "wait_seconds": 20}
        data["status"] = "approval_required"
        data["execution"] = "not_started"
        exc.consent_required = True
        exc.data = data
        exc.args = (
            "사용자가 로컬 브라우저에서 호출을 검토해야 합니다. "
            "hub_approval_status로 확인하고 approved일 때 원래 요청을 재시도하세요.",
        )

    @staticmethod
    def approval_result(data, modern=False):
        payload = {**data, "status": "approval_required", "execution": "not_started"}
        result = {
            **text_result(payload),
            "structuredContent": payload,
            "isError": False,
            "_meta": {"joongi-hub/approval": payload},
        }
        if modern:
            result["resultType"] = "complete"
            result["_meta"]["io.modelcontextprotocol/serverInfo"] = INFO
        return result

    def start_task(self, name, arguments, owner, local_owner=False):
        if self.closing:
            raise RpcError(-32000, "Hub is shutting down")
        if not self.task_slots.acquire(blocking=False):
            raise RpcError(-32000, "Eight tasks are already running; retry later")
        try:
            task = self.tasks.create(name, owner)
        except Exception:
            self.task_slots.release()
            raise
        event = threading.Event()
        self.cancelled[task["taskId"]] = event

        def work():
            try:
                while not event.is_set() and not self.closing:
                    try:
                        result = self.invoke(
                            name, arguments, event, task["taskId"], local_owner=local_owner
                        )
                        self.tasks.update(task["taskId"], status="completed", result=result)
                        return
                    except RpcError as exc:
                        if not getattr(exc, "consent_required", False):
                            raise
                        approval_id = exc.data["approval_id"]
                        self.tasks.update(
                            task["taskId"],
                            status="input_required",
                            statusMessage="사용자 승인 대기 · 승인함에서 요청을 검토하세요.",
                            _meta={"joongi-hub/approval-wait": exc.data},
                        )
                        while not event.is_set() and not self.closing:
                            state = self.agent_approvals.wait_status(approval_id, 0.25)
                            if state["status"] != "pending":
                                break
                        if event.is_set() or self.closing:
                            break
                        if state["status"] != "approved":
                            self.tasks.update(
                                task["taskId"],
                                status="cancelled",
                                statusMessage="사용자가 거절했거나 승인 요청이 만료됐습니다.",
                                _meta={},
                            )
                            return
                        self.tasks.update(
                            task["taskId"],
                            status="working",
                            _meta={},
                            statusMessage="승인 확인 · 원래 요청 실행 중",
                        )
                self.tasks.update(task["taskId"], status="cancelled", _meta={})
            except Exception as exc:
                error = (
                    exc.as_dict()
                    if isinstance(exc, RpcError)
                    else {"code": -32603, "message": "Task execution failed"}
                )
                self.tasks.update(task["taskId"], status="failed", error=error)
            finally:
                self.cancelled.pop(task["taskId"], None)
                self.task_slots.release()
                with self.lock:
                    self.task_threads.discard(threading.current_thread())

        with self.lock:
            if self.closing:
                self.cancelled.pop(task["taskId"], None)
                self.task_slots.release()
                self.tasks.update(
                    task["taskId"],
                    status="failed",
                    error={"code": -32000, "message": "Hub is shutting down"},
                )
                raise RpcError(-32000, "Hub is shutting down")
            worker = threading.Thread(target=work, daemon=True)
            self.task_threads.add(worker)
            worker.start()
        return task

    def cancel_task(self, task_id, owner=None):
        task = self.tasks.get(task_id, owner)
        if task["status"] not in {"working", "input_required"}:
            raise RpcError(-32602, "Task is already terminal")
        if task_id in self.cancelled:
            self.cancelled[task_id].set()
        return self.tasks.update(
            task_id,
            status="cancelled",
            statusMessage="Cancellation requested; completed upstream effects cannot be undone",
        )

    def respond_task(self, task_id, responses, owner=None):
        task = self.tasks.get(task_id, owner)
        if not isinstance(responses, dict):
            raise RpcError(-32602, "inputResponses must be an object")
        if task["status"] not in {"working", "input_required"}:
            raise RpcError(-32602, "Task is already terminal")
        pending = task.get("inputRequests", {})
        accepted = {key: value for key, value in responses.items() if key in pending}
        if not accepted:
            return {}
        continuation = self.input_calls.get(task_id)
        if continuation:
            continuation["responses"].update(accepted)
            remaining = {key: value for key, value in pending.items() if key not in accepted}
            self.tasks.update(task_id, inputRequests=remaining)
            continuation["event"].set()
            return {}
        remote = self.remote_tasks.get(task_id)
        if not remote:
            raise RpcError(-32000, "Task input connection is unavailable")
        client, remote_id = remote
        if client.version != MODERN:
            raise RpcError(-32602, "Interactive task input requires the 2026 protocol")
        client.request("tasks/update", {"taskId": remote_id, "inputResponses": accepted})
        self.answered_inputs.setdefault(task_id, set()).update(accepted)
        remaining = {key: value for key, value in pending.items() if key not in accepted}
        self.tasks.update(
            task_id, status="input_required" if remaining else "working", inputRequests=remaining
        )
        return {}

    def read_skill(self, name, path="SKILL.md"):
        started = time.monotonic()
        identity, outcome = "unavailable", "error"
        try:
            result = self.skills.read(name, path)
            identity, outcome = result["name"], "success"
            return result
        finally:
            self.record_usage("skill", identity, outcome, (time.monotonic() - started) * 1000)

    def read_skill_uri(self, uri):
        started = time.monotonic()
        identity, outcome = "unavailable", "error"
        try:
            result = self.skills.read_uri(uri)
            identity, outcome = result["name"], "success"
            return result
        finally:
            self.record_usage("skill", identity, outcome, (time.monotonic() - started) * 1000)

    def remote_resource_allowed(self, server_id, original, *, directory=False, skill=False):
        config = next((item for item in self.registry.list() if item["id"] == server_id), None)
        if config is None or not self.catalog_server_enabled(config):
            return False
        client = self.clients.get(server_id)
        if not client:
            return not skill
        matching = []
        for entry in client.skill_entries:
            manifest = entry.get("resources", [])
            manifest = manifest if isinstance(manifest, list) else []
            root_uri = entry.get("uri", "")
            uris = [root_uri, *[item.get("uri", "") for item in manifest if isinstance(item, dict)]]
            root = root_uri.rsplit("/", 1)[0] + "/" if root_uri.endswith("/SKILL.md") else ""
            in_root = bool(root and (original.startswith(root) or original == root.rstrip("/")))
            parent_of_root = bool(
                root and directory and root.startswith(original.rstrip("/") + "/")
            )
            if (
                in_root
                or parent_of_root
                or any(
                    uri == original or (directory and uri.startswith(original.rstrip("/") + "/"))
                    for uri in uris
                    if isinstance(uri, str)
                )
            ):
                matching.append(entry)
        if skill and not matching:
            return False
        return all(self.remote_skill_enabled(server_id, entry) for entry in matching)

    def require_remote_resource(self, server_id, original, *, directory=False, skill=False):
        if not self.remote_resource_allowed(server_id, original, directory=directory, skill=skill):
            raise RpcError(-32602, "Resource is disabled or unavailable in this catalog")

    def resources(self):
        items = [
            {
                "uri": item["uri"],
                "name": item["name"],
                "description": item["description"],
                "mimeType": "text/markdown",
            }
            for item in self.skills.list()
        ]
        for server_id, client in list(self.clients.items()):
            if (
                client.version
                and "resources" in client.capabilities
                and self.catalog_server_enabled(client.config)
            ):
                items.extend(
                    rewrite_resources(
                        [
                            item
                            for item in client.list_items("resources/list", "resources")
                            if self.remote_resource_allowed(server_id, item["uri"])
                        ],
                        server_id,
                    )
                )
        return items

    def read_resource(self, uri):
        if uri.startswith("skill://"):
            file = self.read_skill_uri(uri)
            content = {"uri": uri, "mimeType": file["mimeType"]}
            content.update(
                {"text": file["content"]} if "content" in file else {"blob": file["blob"]}
            )
            return {"contents": [content]}
        server_id, original = unwrap_resource(uri)
        self.require_remote_resource(server_id, original)
        client = self.client(server_id)
        result = client.request("resources/read", {"uri": original})
        # A proxy must not silently serve bytes that differ from its advertised skill manifest.
        protected_skill = False
        for entry in client.skill_entries:
            manifest = entry.get("resources", [])
            if not isinstance(manifest, list):
                continue
            file = next((file for file in manifest if file["uri"] == original), None)
            if file:
                protected_skill = True
                contents = result.get("contents", [])
                if len(contents) != 1:
                    raise RpcError(-32000, "Skill resource does not match its manifest")
                content = contents[0]
                raw = (
                    content["text"].encode("utf-8")
                    if "text" in content
                    else base64.b64decode(content.get("blob", ""), validate=True)
                )
                if (
                    len(raw) != file["size"]
                    or "sha256:" + hashlib.sha256(raw).hexdigest() != file["digest"]
                ):
                    raise RpcError(
                        -32000, "Skill content changed; reconnect to refresh its manifest"
                    )
        if original.startswith("ui://") and not protected_skill:
            result = copy.deepcopy(result)
            for content in result.get("contents", []):
                if content.get("uri") == original and isinstance(content.get("text"), str):
                    content["text"] = wrap_app_html(content["text"], server_id)
                    csp = content.setdefault("_meta", {}).setdefault("ui", {}).setdefault("csp", {})
                    csp["frameDomains"] = list(
                        dict.fromkeys([*csp.get("frameDomains", []), "about:"])
                    )
        return rewrite_resources(result, server_id)

    def prompts(self):
        items = []
        for server_id, client in list(self.clients.items()):
            if client.version and "prompts" in client.capabilities:
                for prompt in client.list_items("prompts/list", "prompts"):
                    items.append({**prompt, "name": server_id + "__" + prompt["name"]})
        return items

    def rpc(self, message, context):
        request_id = message.get("id") if isinstance(message, dict) else None
        try:
            if (
                not isinstance(message, dict)
                or message.get("jsonrpc") != "2.0"
                or not isinstance(message.get("method"), str)
            ):
                raise RpcError(-32600, "Invalid JSON-RPC request")
            method = message["method"]
            params = message.get("params", {})
            if not isinstance(params, dict):
                raise RpcError(-32602, "params must be an object")
            if "id" not in message:
                if method == "notifications/initialized":
                    context["ready"] = True
                return None
            if (
                request_id is None
                or isinstance(request_id, bool)
                or not isinstance(request_id, (int, str))
            ):
                raise RpcError(-32600, "Request id must be a string or integer")
            meta = params.get("_meta", {})
            if not isinstance(meta, dict):
                raise RpcError(-32602, "_meta must be an object")
            profile = context.get("profile") or meta.get("joongi-hub/profile", self.profile_id)
            if context.get("profile") and meta.get("joongi-hub/profile", profile) != profile:
                raise RpcError(-32602, "연결된 프로젝트와 요청의 범위가 다릅니다.")
            if profile != self.profile_id:
                context["profile"] = profile
                return self.scoped(profile).rpc(message, context)
            context.setdefault("profile", profile)
            version = meta.get("io.modelcontextprotocol/protocolVersion") or context.get("version")
            if method == "initialize":
                requested = params.get("protocolVersion", "2025-11-25")
                version = requested if requested in VERSIONS[1:] else "2025-11-25"
                context.update(
                    version=version, capabilities=params.get("capabilities", {}), ready=False
                )
                result = {
                    "protocolVersion": version,
                    "serverInfo": INFO,
                    "capabilities": self.capabilities(False),
                    "instructions": "Use hub_search(kind=all) for skills, registered MCP servers "
                    "and connected tools. Read selected skills with hub_read_skill. "
                    "Server results may be disconnected; connect explicitly with "
                    "hub_connect; call discovered tools with hub_call. "
                    "Open local owner settings with hub_open_settings when requested. "
                    "approval_required is normal user-consent waiting, not a failed call. "
                    "The upstream was not executed. Wait with hub_approval_status; "
                    "retry only after approved. Independent calls may queue in the same inbox; "
                    "dependent calls must wait for the actual upstream result.",
                }
            else:
                modern = version == MODERN
                if method == "server/discover" and version is None:
                    version = MODERN
                    modern = True
                if version not in VERSIONS:
                    raise RpcError(
                        -32022,
                        "Unsupported protocol version",
                        {"supported": VERSIONS, "requested": version},
                    )
                if not modern and not context.get("ready") and method != "ping":
                    raise RpcError(-32000, "Send initialize and notifications/initialized first")
                capabilities = (
                    meta.get("io.modelcontextprotocol/clientCapabilities", {})
                    if modern
                    else context.get("capabilities", {})
                )
                if not isinstance(capabilities, dict):
                    raise RpcError(-32602, "Client capabilities must be an object")
                extensions = capabilities.get("extensions", {})
                if not isinstance(extensions, dict):
                    raise RpcError(-32602, "Client extensions must be an object")
                owner = context.get("owner", "local")
                if method == "server/discover":
                    result = {
                        "supportedVersions": VERSIONS,
                        "capabilities": self.capabilities(True),
                        "ttlMs": 0,
                        "cacheScope": "private",
                    }
                elif method == "ping":
                    result = {}
                elif method == "tools/list":
                    result = {"tools": self.tools()}
                    for tool in result["tools"]:
                        if modern:
                            tool.pop("execution", None)
                        else:
                            tool.setdefault("execution", {"taskSupport": "optional"})
                    if UI_EXTENSION not in extensions:
                        result["tools"] = [
                            tool
                            for tool in result["tools"]
                            if tool.get("_meta", {}).get("ui", {}).get("visibility") != ["app"]
                        ]
                        for tool in result["tools"]:
                            if isinstance(tool.get("_meta"), dict):
                                tool["_meta"].pop("ui", None)
                                tool["_meta"].pop("ui/resourceUri", None)
                elif method in {"skills/list", "skills/get"} and modern:
                    if SKILLS_EXTENSION not in extensions:
                        raise RpcError(-32021, "Skills extension capability is required")
                    result = {"ttlMs": 0, "cacheScope": "private"}
                    if method == "skills/list":
                        result["skills"] = self.skills.entries()
                        for server_id, client in list(self.clients.items()):
                            if client.version:
                                result["skills"].extend(
                                    rewrite_resources(
                                        [
                                            entry
                                            for entry in client.skill_entries
                                            if self.remote_skill_enabled(server_id, entry)
                                        ],
                                        server_id,
                                    )
                                )
                    else:
                        uri = params.get("uri", "")
                        if uri.startswith("skill://"):
                            file = self.read_skill_uri(uri)
                            if file["path"] != "SKILL.md":
                                raise RpcError(-32602, "Use the skill's SKILL.md URI")
                            result["skill"] = self.skills.entry(file["name"])
                        else:
                            server_id, original = unwrap_resource(uri)
                            self.require_remote_resource(server_id, original, skill=True)
                            client = self.client(server_id)
                            entry = client.request("skills/get", {"uri": original})["skill"]
                            if not self.remote_skill_enabled(server_id, entry):
                                raise RpcError(-32602, "Skill is disabled in this catalog")
                            client.skill_entries = [
                                cached
                                for cached in client.skill_entries
                                if cached["uri"] != original
                            ] + [entry]
                            result["skill"] = rewrite_resources(entry, server_id)
                elif method == "tools/call":
                    name, arguments = params.get("name"), params.get("arguments", {})
                    if not isinstance(name, str) or not isinstance(arguments, dict):
                        raise RpcError(-32602, "Invalid tool name or arguments")
                    if not modern:
                        definition = next(
                            (tool for tool in self.tools() if tool["name"] == name), {}
                        )
                        support = definition.get("execution", {}).get("taskSupport", "optional")
                        if support == "required" and "task" not in params:
                            raise RpcError(-32602, "This tool requires a task-augmented request")
                        if support == "forbidden" and "task" in params:
                            raise RpcError(-32602, "This tool does not accept task augmentation")
                    as_task = (
                        modern
                        and TASK_EXTENSION in extensions
                        and (name == "hub_call" or "__" in name)
                    ) or (not modern and "task" in params)
                    if as_task:
                        task = self.start_task(
                            name, arguments, owner, local_owner=context.get("local_owner", False)
                        )
                        result = (
                            public_task(task, modern, include_result=False)
                            if modern
                            else {"task": public_task(task, False, include_result=False)}
                        )
                        if modern:
                            result["resultType"] = "task"
                    else:
                        owner_name = arguments.get("name") if name == "hub_call" else name
                        owner_action = owner_name in (
                            "hub_approval_request",
                            "hub_approval_status",
                            "hub_open_settings",
                            "hub_catalog_configure",
                            "hub_catalog_reset",
                            "hub_catalog_usage_reset",
                        )
                        result = self.invoke(
                            name,
                            arguments,
                            input_responses=params.get("inputResponses"),
                            request_state=params.get("requestState"),
                            local_owner=context.get("local_owner", False)
                            and (not context.get("consent_in_host", False) or owner_action),
                        )
                        if not modern and result.get("resultType") == "input_required":
                            raise RpcError(-32021, "Run as a task to provide interactive input")
                    if UI_EXTENSION not in extensions:
                        # Host can still consume the text result without a UI renderer.
                        result = self.without_ui(result)
                elif method == "resources/list":
                    result = {"resources": self.resources()}
                elif method == "resources/templates/list":
                    result = {
                        "resourceTemplates": [
                            {
                                "uriTemplate": "skill://{name}/{path}",
                                "name": "Skill files",
                                "mimeType": "text/markdown",
                            }
                        ]
                    }
                elif method == "resources/read":
                    result = self.read_resource(params.get("uri", ""))
                    if modern:
                        result.update(ttlMs=0, cacheScope="private")
                elif method == "resources/directory/read" and modern:
                    if SKILLS_EXTENSION not in extensions:
                        raise RpcError(-32021, "Skills extension capability is required")
                    uri = params.get("uri", "")
                    if uri.startswith("skill://"):
                        result = {
                            "resources": self.skills.read_directory(uri),
                            "ttlMs": 0,
                            "cacheScope": "private",
                        }
                    else:
                        server_id, original = unwrap_resource(uri)
                        self.require_remote_resource(server_id, original, directory=True)
                        result = rewrite_resources(
                            self.client(server_id).request(method, {"uri": original}), server_id
                        )
                elif method == "prompts/list":
                    result = {"prompts": self.prompts()}
                elif method == "prompts/get":
                    server_id, separator, name = params.get("name", "").partition("__")
                    if not separator:
                        raise RpcError(-32602, "Use a server__prompt name")
                    result = rewrite_resources(
                        self.client(server_id).request(
                            "prompts/get", {"name": name, "arguments": params.get("arguments", {})}
                        ),
                        server_id,
                    )
                elif method == "tasks/list" and not modern:
                    result = {
                        "tasks": [
                            public_task(task, False, False) for task in self.tasks.list(owner)
                        ]
                    }
                elif method in {"tasks/get", "tasks/cancel", "tasks/result", "tasks/update"}:
                    if modern and TASK_EXTENSION not in extensions:
                        raise RpcError(-32021, "Tasks extension capability is required")
                    task_id = params.get("taskId", "")
                    task = self.tasks.get(task_id, owner)
                    if method == "tasks/cancel":
                        task = self.cancel_task(task_id, owner)
                        if modern:
                            result = {}
                            result["resultType"] = "complete"
                            return {"jsonrpc": "2.0", "id": request_id, "result": result}
                    elif method == "tasks/update":
                        self.respond_task(task_id, params.get("inputResponses"), owner)
                        return {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {"resultType": "complete"},
                        }
                    elif method == "tasks/result":
                        if modern:
                            raise RpcError(-32601, "2026 tasks/get includes the result")
                        # Legacy tasks/result waits until terminal state.
                        deadline = time.monotonic() + 20
                        while (
                            task["status"] in {"working", "input_required"}
                            and time.monotonic() < deadline
                        ):
                            time.sleep(0.05)
                            task = self.tasks.get(task_id, owner)
                        if task["status"] == "completed":
                            return {"jsonrpc": "2.0", "id": request_id, "result": task["result"]}
                        if task["status"] == "failed":
                            raise RpcError(
                                **{
                                    "code": task["error"]["code"],
                                    "message": task["error"]["message"],
                                    "data": task["error"].get("data"),
                                }
                            )
                        raise RpcError(-32000, "Task is not completed; poll tasks/get")
                    result = public_task(task, modern, include_result=modern)
                else:
                    raise RpcError(-32601, "Method not supported", {"method": method})
                if modern:
                    if method in {
                        "tools/list",
                        "resources/list",
                        "resources/templates/list",
                        "prompts/list",
                    }:
                        result.update(ttlMs=0, cacheScope="private")
                    result.setdefault("resultType", "complete")
                    result.setdefault("_meta", {})["io.modelcontextprotocol/serverInfo"] = INFO
                else:
                    result.pop("resultType", None)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except RpcError as exc:
            if getattr(exc, "consent_required", False) and message.get("method") == "tools/call":
                modern = (
                    message.get("params", {})
                    .get("_meta", {})
                    .get("io.modelcontextprotocol/protocolVersion")
                    or context.get("version")
                ) == MODERN
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": self.approval_result(exc.data, modern),
                }
            return {"jsonrpc": "2.0", "id": request_id, "error": exc.as_dict()}
        except (ValueError, TypeError, AttributeError, KeyError):
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "Invalid request parameters"},
            }
        except Exception:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": "Hub request failed; inspect connection state",
                },
            }

    @staticmethod
    def capabilities(modern):
        result = {"tools": {}, "resources": {}, "prompts": {}}
        if modern:
            result["extensions"] = {
                TASK_EXTENSION: {},
                SKILLS_EXTENSION: {"directoryRead": True},
                UI_EXTENSION: {"mimeTypes": ["text/html;profile=mcp-app"]},
            }
        else:
            result["tasks"] = {"list": {}, "cancel": {}, "requests": {"tools": {"call": {}}}}
        return result

    @staticmethod
    def without_ui(result):
        result = copy.deepcopy(result)
        if isinstance(result.get("_meta"), dict):
            result["_meta"].pop("ui", None)
            result["_meta"].pop("ui/resourceUri", None)
        return result
