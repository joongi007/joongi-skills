"""Read-only Python AST code graph exposed as an independent MCP server.

The source tree is parsed, never imported or executed. Calls are static candidate
relationships, not a claim about runtime dispatch or reflection.
"""

import argparse
import ast
import hashlib
import json
import os
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from joongi_hub import __version__
from joongi_hub.errors import RpcError
from joongi_hub.upstream import MAX_MESSAGE, MODERN, VERSIONS

EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".tox",
    "vendor",
    "_vendor",
}
MAX_FILES = 10000
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


def module_name(path):
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or "__root__"


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


class SourceVisitor(ast.NodeVisitor):
    def __init__(self, path, tree, text):
        self.path = path.as_posix()
        self.module = module_name(path)
        self.symbols = []
        self.calls = []
        self.imports = []
        self.aliases = [{}]
        self.scopes = []
        self.classes = []
        self.source = "module:" + self.module
        self.symbols.append(
            {
                "id": self.source,
                "name": self.module,
                "qualified": self.module,
                "kind": "module",
                "path": self.path,
                "line": 1,
                "end_line": len(text.splitlines()),
                "doc": (ast.get_docstring(tree) or "")[:500],
            }
        )
        self.visit(tree)

    def _definition(self, node, kind):
        for decorator in node.decorator_list:
            self.visit(decorator)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in [*node.args.defaults, *node.args.kw_defaults]:
                if default:
                    self.visit(default)
        previous = self.source
        self.scopes.append(node.name)
        qualified = ".".join([self.module, *self.scopes])
        self.source = qualified + ":" + str(node.lineno)
        self.symbols.append(
            {
                "id": self.source,
                "name": node.name,
                "qualified": qualified,
                "kind": kind,
                "path": self.path,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "doc": (ast.get_docstring(node) or "")[:500],
            }
        )
        self.aliases.append({})
        if kind == "class":
            for base in node.bases:
                self.visit(base)
            self.classes.append(qualified)
        for statement in node.body:
            self.visit(statement)
        if kind == "class":
            self.classes.pop()
        self.aliases.pop()
        self.scopes.pop()
        self.source = previous

    def visit_FunctionDef(self, node):
        self._definition(node, "function")

    def visit_AsyncFunctionDef(self, node):
        self._definition(node, "async_function")

    def visit_ClassDef(self, node):
        self._definition(node, "class")

    def visit_Import(self, node):
        for item in node.names:
            self.aliases[-1][item.asname or item.name.split(".")[0]] = (
                item.name if item.asname else item.name.split(".")[0]
            )
            self.imports.append({"source": self.source, "module": item.name, "line": node.lineno})

    def visit_ImportFrom(self, node):
        package = self.module.split(".")
        if not self.path.endswith("/__init__.py") and self.path != "__init__.py":
            package = package[:-1]
        if node.level:
            package = package[: max(0, len(package) - node.level + 1)]
            base = ".".join([*package, *([node.module] if node.module else [])])
        else:
            base = node.module or ""
        self.imports.append({"source": self.source, "module": base, "line": node.lineno})
        for item in node.names:
            if item.name != "*":
                self.aliases[-1][item.asname or item.name] = ".".join(
                    filter(None, [base, item.name])
                )

    def visit_Call(self, node):
        name = dotted(node.func)
        if name:
            head, *tail = name.split(".")
            resolved = None
            if head in {"self", "cls"} and tail and self.classes:
                resolved = ".".join([self.classes[-1], *tail])
            else:
                for aliases in reversed(self.aliases):
                    if head in aliases:
                        resolved = ".".join([aliases[head], *tail])
                        break
            candidates = []
            if resolved:
                candidates.append(resolved)
            else:
                for depth in range(len(self.scopes), -1, -1):
                    candidates.append(".".join([self.module, *self.scopes[:depth], name]))
            self.calls.append(
                {
                    "source": self.source,
                    "expression": name,
                    "line": node.lineno,
                    "candidates": candidates,
                }
            )
        self.generic_visit(node)


class CodeGraph:
    def __init__(self, project):
        self.project = Path(project).expanduser().resolve()
        if not self.project.is_dir():
            raise RpcError(-32602, "Project directory does not exist")
        self.files = {}
        self.symbols = []
        self.edges = []
        self.errors = []
        self.indexed_at = None
        self.fingerprint = None
        self.index()

    def scan(self):
        files = {}
        size = 0
        for folder, directories, names in os.walk(self.project, followlinks=False):
            directory = Path(folder)
            directories[:] = sorted(
                name
                for name in directories
                if name not in EXCLUDED
                and not name.startswith(".")
                and not (directory / name).is_symlink()
            )
            for name in sorted(names):
                if not name.endswith(".py") or name.startswith("."):
                    continue
                path = directory / name
                relative = path.relative_to(self.project)
                if path.is_symlink() or not path.resolve().is_relative_to(self.project):
                    continue
                try:
                    with path.open("rb") as stream:
                        data = stream.read(MAX_FILE_BYTES + 1)
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise RpcError(
                        -32000, "Cannot read Python source: " + relative.as_posix()
                    ) from exc
                if len(data) > MAX_FILE_BYTES:
                    raise RpcError(
                        -32602, "Python source file exceeds 2 MiB: " + relative.as_posix()
                    )
                size += len(data)
                if len(files) >= MAX_FILES or size > MAX_TOTAL_BYTES:
                    raise RpcError(-32602, "Project exceeds 10000 files or 32 MiB of Python source")
                files[relative.as_posix()] = {
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "data": data,
                }
        return files

    def index(self):
        sources = self.scan()
        symbols, calls, imports, errors = [], [], [], []
        for path, source in sources.items():
            try:
                tree = ast.parse(source["data"], filename=path)
                visitor = SourceVisitor(Path(path), tree, source["data"].decode("utf-8-sig"))
            except (SyntaxError, UnicodeError) as exc:
                errors.append(
                    {
                        "path": path,
                        "line": getattr(exc, "lineno", None),
                        "error": "Source cannot be parsed by Python " + sys.version.split()[0],
                    }
                )
                continue
            symbols.extend(visitor.symbols)
            calls.extend(visitor.calls)
            imports.extend(visitor.imports)
        lookup = defaultdict(list)
        symbol_ids = {symbol["id"] for symbol in symbols}
        for symbol in symbols:
            lookup[symbol["qualified"]].append(symbol["id"])
        edges = []
        for call in calls:
            targets = []
            for candidate in call.pop("candidates"):
                targets = lookup.get(candidate, [])
                if targets:
                    break
            if targets:
                edges.extend(
                    {
                        **call,
                        "target": target,
                        "kind": "calls",
                        "resolution": "static_candidate" if len(targets) == 1 else "ambiguous",
                    }
                    for target in targets
                )
            else:
                edges.append({**call, "target": None, "kind": "calls", "resolution": "unresolved"})
        for item in imports:
            target = "module:" + item["module"]
            edges.append(
                {
                    "source": item["source"],
                    "target": target if target in symbol_ids else None,
                    "kind": "imports",
                    "expression": item["module"],
                    "line": item["line"],
                    "resolution": "static_candidate",
                }
            )
        self.files = {path: value["sha256"] for path, value in sources.items()}
        self.symbols, self.edges, self.errors = symbols, edges, errors
        self.indexed_at = datetime.now(timezone.utc).isoformat()
        self.fingerprint = hashlib.sha256(
            json.dumps(self.files, sort_keys=True).encode()
        ).hexdigest()
        return self.status()

    def status(self):
        actual = {path: value["sha256"] for path, value in self.scan().items()}
        changed = sorted(
            path
            for path in set(actual) | set(self.files)
            if actual.get(path) != self.files.get(path)
        )
        return {
            "project": str(self.project),
            "language": "python",
            "parser": "stdlib ast",
            "python": sys.version.split()[0],
            "indexed_at": self.indexed_at,
            "fingerprint": self.fingerprint,
            "fresh": not changed,
            "changed_files": changed,
            "files": len(self.files),
            "symbols": len(self.symbols),
            "resolved_calls": sum(
                edge["kind"] == "calls" and edge["target"] is not None for edge in self.edges
            ),
            "unresolved_calls": sum(
                edge["kind"] == "calls" and edge["target"] is None for edge in self.edges
            ),
            "parse_errors": self.errors,
        }

    def ensure_fresh(self):
        status = self.status()
        if not status["fresh"]:
            raise RpcError(
                -32000,
                "Code graph is stale; call graph_index before querying",
                {"changed_files": status["changed_files"]},
            )

    def matches(self, query):
        if not isinstance(query, str) or len(query) > 500:
            raise RpcError(-32602, "Symbol query must be text (up to 500 characters)")
        exact = [
            symbol
            for symbol in self.symbols
            if query in {symbol["id"], symbol["qualified"], symbol["name"]}
        ]
        return exact or [
            symbol for symbol in self.symbols if query.lower() in symbol["qualified"].lower()
        ]

    @staticmethod
    def limit(arguments, default=50):
        value = arguments.get("limit", default)
        if type(value) is not int or not 1 <= value <= 200:
            raise RpcError(-32602, "limit must be an integer between 1 and 200")
        return value

    def query(self, name, arguments):
        if not isinstance(arguments, dict):
            raise RpcError(-32602, "Tool arguments must be an object")
        if name not in {item["name"] for item in tool_definitions()}:
            raise RpcError(-32602, "Unknown code graph tool")
        if name == "graph_status":
            return self.status()
        if name == "graph_index":
            return self.index()
        self.ensure_fresh()
        limit = self.limit(arguments)
        query = arguments.get("symbol", arguments.get("query", ""))
        matches = self.matches(query)
        if name == "graph_symbols":
            return {
                "symbols": matches[:limit],
                "total": len(matches),
                "fingerprint": self.fingerprint,
            }
        if len(matches) != 1:
            return {
                "matches": matches[:limit],
                "ambiguous": len(matches) > 1,
                "hint": "Use an exact qualified name or symbol id",
            }
        symbol = matches[0]
        if name == "graph_context":
            path = self.project / symbol["path"]
            if path.is_symlink() or not path.resolve().is_relative_to(self.project):
                raise RpcError(-32000, "Indexed source path changed; reindex the project")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != self.files[symbol["path"]]:
                raise RpcError(-32000, "Source changed during query; reindex the project")
            source = data.decode("utf-8-sig").splitlines()
            start = max(1, symbol["line"] - 2)
            end = min(len(source), symbol["end_line"], start + 79)
            return {
                "symbol": symbol,
                "start_line": start,
                "end_line": end,
                "source": "\n".join(source[start - 1 : end]),
                "fingerprint": self.fingerprint,
            }
        if name in {"graph_callers", "graph_callees"}:
            field = "target" if name == "graph_callers" else "source"
            edges = [edge for edge in self.edges if edge[field] == symbol["id"]]
            return {"symbol": symbol, "edges": edges[:limit], "total": len(edges)}
        if name == "graph_impact":
            depth = arguments.get("depth", 3)
            if type(depth) is not int or not 1 <= depth <= 10:
                raise RpcError(-32602, "depth must be an integer between 1 and 10")
            reverse = defaultdict(set)
            for edge in self.edges:
                if edge["target"]:
                    reverse[edge["target"]].add(edge["source"])
            queue = deque([(symbol["id"], 0)])
            seen = {symbol["id"]}
            affected = []
            by_id = {item["id"]: item for item in self.symbols}
            while queue and len(affected) < limit:
                current, distance = queue.popleft()
                if distance >= depth:
                    continue
                for caller in sorted(reverse[current]):
                    if caller not in seen:
                        seen.add(caller)
                        affected.append({"symbol": by_id[caller], "distance": distance + 1})
                        queue.append((caller, distance + 1))
            return {
                "symbol": symbol,
                "affected": affected,
                "truncated": bool(queue),
                "depth": depth,
                "fingerprint": self.fingerprint,
            }
        raise RpcError(-32602, "Unknown code graph tool")


def tool_definitions():
    result = []
    descriptions = {
        "graph_status": "Check Python code graph freshness, source fingerprint and parse errors.",
        "graph_index": "Rebuild the read-only Python AST graph after source changes.",
        "graph_symbols": "Search functions, classes and modules by name or qualified symbol.",
        "graph_context": "Read one symbol's bounded source context. "
        "Use exact symbol id if ambiguous.",
        "graph_callers": "Find static callers and importers of an exact symbol.",
        "graph_callees": "Find static callees/imports, "
        "including unresolved dynamic/external calls.",
        "graph_impact": "Traverse reverse static dependencies for change impact analysis.",
    }
    for name, description in descriptions.items():
        properties = {}
        if name not in {"graph_status", "graph_index"}:
            properties = {
                "symbol": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            }
        if name == "graph_impact":
            properties["depth"] = {"type": "integer", "minimum": 1, "maximum": 10}
        result.append(
            {
                "name": name,
                "description": description,
                "annotations": {"readOnlyHint": True, "destructiveHint": False},
                "inputSchema": {
                    "type": "object",
                    "properties": properties,
                    "additionalProperties": False,
                },
            }
        )
    return result


def server_config(project, server_id="code-graph"):
    """Produce a cwd-independent registration for a source or installed runtime."""
    target = Path(project).expanduser().resolve()
    if not target.is_dir():
        raise RpcError(-32602, "Project directory does not exist")
    bootstrap = (
        "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));"
        "runpy.run_module('joongi_hub.code_graph',run_name='__main__')"
    )
    return {
        "id": server_id,
        "name": "Python code graph · " + target.name,
        "transport": "stdio",
        "command": sys.executable,
        "args": [
            "-I",
            "-B",
            "-c",
            bootstrap,
            str(Path(__file__).resolve().parents[1]),
            "--project",
            str(target),
        ],
        "enabled": True,
        "protocol_version": "auto",
        "sandbox": {"read": [str(target)]},
    }


def rpc(graph, message, context):
    request_id = message.get("id") if isinstance(message, dict) else None
    try:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise RpcError(-32600, "Invalid JSON-RPC request")
        method = message.get("method")
        params = message.get("params", {})
        if not isinstance(params, dict):
            raise RpcError(-32602, "params must be an object")
        if "id" not in message:
            return None
        meta = params.get("_meta", {})
        version = meta.get("io.modelcontextprotocol/protocolVersion", context.get("version"))
        info = {"name": "joongi-code-graph", "version": __version__}
        if method == "initialize":
            version = params.get("protocolVersion", "2025-11-25")
            version = version if version in VERSIONS[1:] else "2025-11-25"
            context["version"] = version
            result = {"protocolVersion": version, "capabilities": {"tools": {}}, "serverInfo": info}
        elif version not in VERSIONS:
            raise RpcError(-32022, "Unsupported protocol version", {"supported": VERSIONS})
        elif method == "server/discover":
            result = {
                "supportedVersions": VERSIONS,
                "capabilities": {"tools": {}},
                "ttlMs": 0,
                "cacheScope": "private",
            }
        elif method == "tools/list":
            result = {"tools": tool_definitions()}
        elif method == "tools/call":
            value = graph.query(params.get("name"), params.get("arguments", {}))
            encoded = json.dumps(value, ensure_ascii=False)
            if len(encoded.encode("utf-8")) > MAX_MESSAGE // 3:
                raise RpcError(
                    -32602, "Code graph result exceeds response budget; narrow the query"
                )
            result = {
                "content": [{"type": "text", "text": encoded}],
                "structuredContent": value,
            }
        elif method == "ping":
            result = {}
        else:
            raise RpcError(-32601, "Unknown method")
        if version == MODERN:
            result["resultType"] = "complete"
            result["_meta"] = {"io.modelcontextprotocol/serverInfo": info}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except RpcError as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": exc.as_dict()}
    except (TypeError, AttributeError, ValueError):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": "Invalid code graph parameters"},
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--summary", action="store_true", help="Print graph statistics instead of MCP"
    )
    args = parser.parse_args(argv)
    graph = CodeGraph(args.project)
    if args.summary:
        print(json.dumps(graph.status(), ensure_ascii=False, indent=2))
        return 0
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    context = {}
    while True:
        line = sys.stdin.buffer.readline(MAX_MESSAGE + 1)
        if not line:
            break
        if len(line) > MAX_MESSAGE:
            break
        try:
            response = rpc(graph, json.loads(line), context)
        except (ValueError, UnicodeError):
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Invalid JSON"},
            }
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
