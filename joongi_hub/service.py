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
from joongi_hub.connections import ConnectionSettings, configuration
from joongi_hub.errors import RpcError
from joongi_hub.profiles import ProjectRegistry, Projects, ProjectSkills
from joongi_hub.resources import resource_uri, unwrap_resource
from joongi_hub.search import Document, parameter_text, rank
from joongi_hub.skill_management import SkillManager
from joongi_hub.skills import Skills
from joongi_hub.state_store import describe
from joongi_hub.storage import Registry, TaskStore
from joongi_hub.tool_policy import ToolPolicy
from joongi_hub.upstream import MODERN, VERSIONS, Upstream, validate_server

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
        self.skills = ProjectSkills(self.common_skills, project) if project else self.common_skills
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
        self.clients = {}
        self.health = {}
        self.lock = threading.RLock()
        self.task_slots = threading.BoundedSemaphore(8)
        self.cancelled = {}
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
        for child in self.profile_hubs.values():
            child.close()
        for event in self.cancelled.values():
            event.set()
        for client in list(self.clients.values()):
            client.close()

    def register(self, data):
        config = validate_server(data)
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
        limit=100,
        detail="full",
        kind="all",
        server=None,
    ):
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
            client = self.clients.get(config["id"])
            if not config["enabled"] or not client:
                continue
            for entry in client.skill_entries:
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
        return rank(
            documents,
            query,
            mode=mode,
            match=match,
            limit=limit,
            detail=detail,
            kind=kind,
            server=server,
        )

    def tools(self):
        tools = [
            {
                "name": "hub_search",
                "annotations": {"readOnlyHint": True},
                "description": (
                    "Search skill and connected MCP tool names, descriptions and arguments. "
                    "Lexical, not semantic or filesystem search. Use short keywords/identifiers. "
                    "Try limit=5, detail=summary; get detail=full by exact name before calling. "
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
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 100},
                        "detail": {
                            "type": "string",
                            "enum": ["summary", "full"],
                            "default": "full",
                        },
                        "kind": {
                            "type": "string",
                            "enum": ["all", "skill", "tool"],
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
                "description": "현재 저장 경로·등록 수·임시 저장소 경고·백업 위치를 확인합니다.",
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
                    "description": "연결된 MCP의 인증 상태를 비밀값 없이 조회합니다.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"server": {"type": "string"}},
                        "additionalProperties": False,
                    },
                },
            ]
        )
        # Native discovery preserves each upstream's schema, Apps metadata and
        # task execution contract. Search/call remain optional convenience tools.
        for server_id, client in list(self.clients.items()):
            if client.version:
                for tool in client.tools:
                    tools.append(
                        rewrite_resources(
                            {**tool, "name": server_id + "__" + tool["name"]}, server_id
                        )
                    )
        # App SDK calls use their original server tool names. App-only aliases
        # preserve that contract when the name identifies exactly one upstream.
        for server_id, client in list(self.clients.items()):
            has_app = any(app_resource_uri(tool) for tool in client.tools)
            if not client.version or not has_app:
                continue
            for tool in client.tools:
                matches = self.alias_matches(tool["name"])
                namespaced = server_id + "__" + tool["name"]
                if not any(candidate["name"] == namespaced for candidate in tools):
                    scoped = rewrite_resources({**tool, "name": namespaced}, server_id)
                    scoped.setdefault("_meta", {}).setdefault("ui", {})["visibility"] = ["app"]
                    tools.append(scoped)
                if len(matches) == 1 and not tool["name"].startswith("hub_"):
                    alias = rewrite_resources(tool, server_id)
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
    ):
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise RpcError(-32602, "Tool name and arguments must be a string and object")
        if name == "hub_skills_status":
            return text_result(self.skill_manager.status())
        if name == "hub_skills_plan":
            if set(arguments) - {"operation", "names", "agents", "refresh"}:
                raise RpcError(-32602, "지원하지 않는 스킬 계획 필드입니다.")
            return text_result(self.skill_manager.plan(**arguments))
        if name == "hub_skills_apply":
            return text_result(self.skill_manager.apply(arguments.get("plan_id")))
        if name == "hub_auth_status":
            configs = self.registry.list()
            if arguments.get("server"):
                configs = [c for c in configs if c["id"] == arguments["server"]]
                if not configs:
                    raise RpcError(-32602, "등록되지 않은 서버입니다.")
            return text_result([{"server": c["id"], **self.auth.status(c)} for c in configs])
        if name == "hub_search":
            if set(arguments) - {"query", "mode", "match", "limit", "detail", "kind", "server"}:
                raise RpcError(-32602, "Unknown search options")
            return text_result(self.search(**{"query": "", **arguments}))
        if name == "hub_read_skill":
            return text_result(
                self.skills.read(arguments.get("name"), arguments.get("path", "SKILL.md"))
            )
        if name == "hub_list_servers":
            return text_result(self.state()["servers"])
        if name == "hub_status":
            return text_result(
                {**describe(self.state_dir, len(self.registry.list())), "profile": self.profile_id}
            )
        if name == "hub_read_resource":
            return text_result(self.read_resource(arguments.get("uri", "")))
        if name == "hub_connect":
            return text_result(self.probe(arguments.get("server")))
        if name == "hub_call":
            return self.invoke(
                arguments.get("name"),
                arguments.get("arguments", {}),
                cancel_event,
                local_task_id,
                input_responses,
                request_state,
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
            )
        server_id, tool_name = name.split("__", 1)
        client = self.client(server_id)
        client.connect()
        tool = next((tool for tool in client.tools if tool.get("name") == tool_name), None)
        if tool is None:
            raise RpcError(-32602, "Tool not found on the selected server")
        self.tool_policy.authorize(
            client.config,
            tool,
            arguments,
            {"inputResponses": input_responses, "requestState": request_state},
        )
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
        result = client.request("tools/call", params)
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
        return rewrite_resources(result, server_id)

    def start_task(self, name, arguments, owner):
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
                result = self.invoke(name, arguments, event, task["taskId"])
                self.tasks.update(task["taskId"], status="completed", result=result)
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

        threading.Thread(target=work, daemon=True).start()
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
            if client.version and "resources" in client.capabilities:
                items.extend(
                    rewrite_resources(client.list_items("resources/list", "resources"), server_id)
                )
        return items

    def read_resource(self, uri):
        if uri.startswith("skill://"):
            file = self.skills.read_uri(uri)
            content = {"uri": uri, "mimeType": file["mimeType"]}
            content.update(
                {"text": file["content"]} if "content" in file else {"blob": file["blob"]}
            )
            return {"contents": [content]}
        server_id, original = unwrap_resource(uri)
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
                    "instructions": "Search skills with hub_search and read selected "
                    "instructions with hub_read_skill. Connect registered servers with "
                    "hub_connect; call discovered tools with hub_call.",
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
                                    rewrite_resources(client.skill_entries, server_id)
                                )
                    else:
                        uri = params.get("uri", "")
                        if uri.startswith("skill://"):
                            file = self.skills.read_uri(uri)
                            if file["path"] != "SKILL.md":
                                raise RpcError(-32602, "Use the skill's SKILL.md URI")
                            result["skill"] = self.skills.entry(file["name"])
                        else:
                            server_id, original = unwrap_resource(uri)
                            client = self.client(server_id)
                            entry = client.request("skills/get", {"uri": original})["skill"]
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
                        task = self.start_task(name, arguments, owner)
                        result = (
                            public_task(task, modern, include_result=False)
                            if modern
                            else {"task": public_task(task, False, include_result=False)}
                        )
                        if modern:
                            result["resultType"] = "task"
                    else:
                        result = self.invoke(
                            name,
                            arguments,
                            input_responses=params.get("inputResponses"),
                            request_state=params.get("requestState"),
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
