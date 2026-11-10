"""Deterministic real-process upstream for gateway contract tests."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

MODERN = "2026-07-28"
SKILL_TEXT = (
    "---\nname: remote-review\ndescription: Review remote source.\n---\nReview carefully.\n"
)
SKILL_URI = "skill://remote-review/SKILL.md"


class Fixture:
    def __init__(self, version):
        self.version = version
        self.initialized = False
        self.input_response = None

    def handle(self, message):
        method = message["method"]
        params = message.get("params", {})
        error = None
        result = {}
        if method == "server/discover":
            if self.version != MODERN:
                error = {"code": -32601, "message": "Unknown method"}
            else:
                result = {
                    "supportedVersions": [MODERN],
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {},
                        "extensions": {
                            "io.modelcontextprotocol/skills": {},
                            "io.modelcontextprotocol/ui": {},
                            "io.modelcontextprotocol/tasks": {},
                        },
                    },
                    "ttlMs": 0,
                    "cacheScope": "private",
                }
        elif method == "initialize":
            self.initialized = True
            result = {
                "protocolVersion": self.version,
                "serverInfo": {"name": "fixture", "version": "1"},
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {},
                    "tasks": {"requests": {"tools": {"call": {}}}},
                },
            }
        elif method.startswith("notifications/"):
            return None
        elif self.version != MODERN and not self.initialized:
            error = {"code": -32000, "message": "Not initialized"}
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Echo a message",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "delay",
                        "description": "Slow operation",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "error",
                        "description": "Tool failure",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "app",
                        "description": "An interactive app",
                        "inputSchema": {"type": "object"},
                        "_meta": {"ui": {"resourceUri": "ui://fixture/panel.html"}},
                    },
                    {
                        "name": "async",
                        "description": "Remote task",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "ask",
                        "description": "Interactive task",
                        "inputSchema": {"type": "object"},
                        "execution": {"taskSupport": "required"},
                    },
                    {
                        "name": "confirm",
                        "description": "Request input before task creation",
                        "inputSchema": {"type": "object"},
                    },
                ]
            }
        elif method == "tools/call":
            name = params["name"]
            if name == "delay":
                time.sleep(params.get("arguments", {}).get("seconds", 0.2))
            if name == "error":
                result = {"content": [{"type": "text", "text": "Domain error"}], "isError": True}
            elif name == "confirm":
                if "inputResponses" not in params:
                    result = {
                        "resultType": "input_required",
                        "requestState": "opaque+must-preserve==",
                        "inputRequests": {
                            "consent": {
                                "method": "elicitation/create",
                                "params": {
                                    "mode": "form",
                                    "message": "Confirm this operation",
                                    "requestedSchema": {
                                        "type": "object",
                                        "properties": {"confirmed": {"type": "boolean"}},
                                    },
                                },
                            }
                        },
                    }
                elif params.get("requestState") != "opaque+must-preserve==":
                    error = {"code": -32602, "message": "requestState was not preserved"}
                else:
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": "Confirmed "
                                + str(params["inputResponses"]["consent"]["content"]["confirmed"]),
                            }
                        ]
                    }
            elif name in {"async", "ask"}:
                task = {
                    "taskId": "ask-task" if name == "ask" else "remote-task",
                    "status": "working",
                    "createdAt": "2026-11-05T00:00:00Z",
                    "lastUpdatedAt": "2026-11-05T00:00:00Z",
                }
                result = (
                    {**task, "resultType": "task", "ttlMs": 60000}
                    if self.version == MODERN
                    else {"task": {**task, "ttl": 60000}}
                )
            else:
                result = {
                    "content": [{"type": "text", "text": json.dumps(params.get("arguments", {}))}]
                }
        elif method == "tasks/get":
            result = {
                "taskId": "remote-task",
                "status": "completed",
                "createdAt": "2026-11-05T00:00:00Z",
                "lastUpdatedAt": "2026-11-05T00:00:00Z",
                "ttlMs": 60000,
                "result": {"content": [{"type": "text", "text": "Async complete"}]},
            }
            if params["taskId"] == "ask-task":
                result["taskId"] = "ask-task"
                if self.input_response is None:
                    result.update(
                        status="input_required",
                        inputRequests={
                            "name": {
                                "method": "elicitation/create",
                                "params": {
                                    "mode": "form",
                                    "message": "Enter your name",
                                    "requestedSchema": {
                                        "type": "object",
                                        "properties": {"name": {"type": "string"}},
                                        "required": ["name"],
                                    },
                                },
                            }
                        },
                    )
                    result.pop("result", None)
                else:
                    result["result"] = {
                        "content": [{"type": "text", "text": json.dumps(self.input_response)}]
                    }
        elif method == "tasks/update":
            self.input_response = params["inputResponses"].get("name")
            result = {}
        elif method == "tasks/result":
            result = {"content": [{"type": "text", "text": "Async complete"}]}
        elif method == "resources/list":
            result = {
                "resources": [
                    {
                        "uri": "ui://fixture/panel.html",
                        "name": "Panel",
                        "mimeType": "text/html;profile=mcp-app",
                    }
                ]
            }
        elif method == "resources/read":
            text = (
                SKILL_TEXT
                if params["uri"] == SKILL_URI
                else '<!doctype html><html><body><p id="app-status">App 연결 중</p>'
                '<button id="app-echo">App에서 도구 호출</button>'
                '<pre id="app-result"></pre>'
                '<button id="app-task">App에서 Task 실행</button>'
                '<pre id="app-task-result"></pre><script>'
                + (Path(__file__).resolve().parents[2] / "examples/apps/demo-view.js")
                .read_text(encoding="utf-8")
                .replace("</script", "<\\/script")
                + "</script></body></html>"
            )
            if params["uri"] == "file:///fixture/notes.txt":
                text = "App resource content"
            result = {
                "contents": [
                    {
                        "uri": params["uri"],
                        "mimeType": "text/markdown"
                        if params["uri"] == SKILL_URI
                        else "text/plain"
                        if params["uri"] == "file:///fixture/notes.txt"
                        else "text/html;profile=mcp-app",
                        "text": text,
                    }
                ]
            }
        elif method in {"skills/list", "skills/get"}:
            skill = {
                "uri": SKILL_URI,
                "frontmatter": {"name": "remote-review", "description": "Review remote source."},
                "resources": [
                    {
                        "uri": SKILL_URI,
                        "size": len(SKILL_TEXT.encode()),
                        "digest": "sha256:" + hashlib.sha256(SKILL_TEXT.encode()).hexdigest(),
                    }
                ],
            }
            result = {"skills": [skill]} if method == "skills/list" else {"skill": skill}
            result.update(ttlMs=0, cacheScope="private")
        elif method == "prompts/list":
            result = {"prompts": [{"name": "review", "description": "Review code"}]}
        elif method == "prompts/get":
            result = {
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": "Review this code"}}
                ]
            }
        else:
            error = {"code": -32601, "message": "Unknown method"}
        if "id" not in message:
            return None
        if self.version == MODERN and not error:
            result.setdefault("resultType", "complete")
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            **({"error": error} if error else {"result": result}),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=MODERN)
    args = parser.parse_args()
    fixture = Fixture(args.version)
    for line in sys.stdin:
        response = fixture.handle(json.loads(line))
        if response:
            print(json.dumps(response), flush=True)
