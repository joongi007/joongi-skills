#!/usr/bin/env python3
"""Compare documented behavioral contracts with executable interfaces.

This checks explicit claims, not arbitrary natural-language equivalence. The
maintained facts document is reviewed like an API schema; source extraction,
CLI execution and capability calls independently detect implementation drift.
"""

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIM = re.compile(r"<!--\s*contract:\s*([\w.]+)\s*=\s*(.*?)\s*-->")


def tree(root, name):
    return ast.parse((root / name).read_text(encoding="utf-8"))


def literals(module):
    result = {}

    def resolve(node):
        if isinstance(node, ast.Name):
            return result[node.id]
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return [resolve(item) for item in node.elts]
        return ast.literal_eval(node)

    for node in module.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    result[target.id] = resolve(node.value)
                except (ValueError, TypeError, KeyError):
                    pass
    return result


def route_patterns(module):
    """Read path dispatch guards, preserving variable tails as {value}."""
    result = set()
    for function in ast.walk(module):
        if not isinstance(function, ast.FunctionDef) or not function.name.startswith("do_"):
            continue
        verb = function.name[3:]
        for node in ast.walk(function):
            if not isinstance(node, ast.If):
                continue
            prefixes, suffixes, exact = [], [], []
            for condition in ast.walk(node.test):
                if isinstance(condition, ast.Compare) and isinstance(
                    condition.left, (ast.Name, ast.Attribute)
                ):
                    name = getattr(condition.left, "id", getattr(condition.left, "attr", ""))
                    if (
                        name == "path"
                        and len(condition.ops) == 1
                        and isinstance(condition.ops[0], ast.Eq)
                    ):
                        for item in condition.comparators:
                            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                                exact.append(item.value)
                elif isinstance(condition, ast.Call) and isinstance(condition.func, ast.Attribute):
                    name = getattr(
                        condition.func.value, "id", getattr(condition.func.value, "attr", "")
                    )
                    if name != "path" or not condition.args:
                        continue
                    item = condition.args[0]
                    if isinstance(item, ast.Constant) and isinstance(item.value, str):
                        if condition.func.attr == "startswith":
                            prefixes.append(item.value)
                        elif condition.func.attr == "endswith":
                            suffixes.append(item.value)
            result.update(f"{verb} {path}" for path in exact)
            result.update(
                f"{verb} {prefix}{{value}}{suffixes[0] if suffixes else ''}" for prefix in prefixes
            )
    return sorted(result)


def method_branches(module):
    methods = set()
    for node in ast.walk(module):
        if not isinstance(node, ast.Compare) or not isinstance(node.left, ast.Name):
            continue
        if node.left.id != "method":
            continue
        for value in node.comparators:
            values = value.elts if isinstance(value, (ast.Tuple, ast.List, ast.Set)) else [value]
            methods.update(
                item.value
                for item in values
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            )
    return sorted(methods)


def runtime_snapshot(root):
    """Run read-only CLI and capability discovery in a fresh interpreter."""
    code = (
        "import json; from joongi_hub.service import Hub; "
        "print(json.dumps({'modern':Hub.capabilities(True),'legacy':Hub.capabilities(False)}))"
    )
    process = subprocess.run(
        [sys.executable, "-B", "-c", code], cwd=root, capture_output=True, text=True, timeout=10
    )
    if process.returncode:
        raise ValueError("Runtime capability inspection failed: " + process.stderr[-1000:])
    capabilities = json.loads(process.stdout)
    commands = {}
    for name in (
        "serve",
        "stdio",
        "configure",
        "start",
        "stop",
        "restart",
        "status",
        "open",
        "state",
        "credentials",
        "sandbox",
    ):
        command = subprocess.run(
            [sys.executable, "-B", "-m", "joongi_hub", name, "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if command.returncode:
            raise ValueError(f"CLI contract cannot execute {name} --help")
        commands[name] = sorted(set(re.findall(r"--[a-z][a-z-]*", command.stdout)))
    return capabilities, commands


def actual_facts(root, execute=True):
    root = Path(root).resolve()
    upstream = literals(tree(root, "joongi_hub/upstream.py"))
    version = literals(tree(root, "joongi_hub/__init__.py"))["__version__"]
    agents = literals(tree(root, "scripts/install_manager.py"))["AGENTS"]
    facts = {
        "runtime.version": version,
        "runtime.versionFile": (root / "VERSION").read_text().strip(),
        "protocol.versions": upstream["VERSIONS"],
        "protocol.methodBranches": method_branches(tree(root, "joongi_hub/service.py")),
        "http.routes": route_patterns(tree(root, "joongi_hub/server.py")),
        "agents.skills": {name: paths[1] for name, paths in agents.items()},
        "agents.detection": {name: paths[0] for name, paths in agents.items()},
    }
    if execute:
        capabilities, commands = runtime_snapshot(root)
        facts.update(
            {
                "cli.options": commands,
                "protocol.modernCapabilities": capabilities["modern"],
                "protocol.legacyCapabilities": capabilities["legacy"],
            }
        )
    return facts


def check(root=ROOT, facts=None):
    root = Path(root).resolve()
    path = root / "docs/contracts.json"
    if not path.is_file():
        return ["docs/contracts.json: missing executable documentation contracts"]
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
        actual = actual_facts(root) if facts is None else facts
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        return [f"Contract inspection failed: {error}"]
    errors = []
    if contract.get("schema") != 1 or not isinstance(contract.get("facts"), dict):
        return ["docs/contracts.json: invalid schema"]
    expected = contract["facts"]
    for key, value in expected.items():
        if key not in actual:
            errors.append(f"docs/contracts.json: unknown runtime contract {key}")
        elif value != actual[key]:
            errors.append(
                f"docs/contracts.json: {key} drift: documented={value!r}, actual={actual[key]!r}"
            )
    if expected.get("runtime.version") != expected.get("runtime.versionFile"):
        errors.append("Version claims disagree between package and VERSION file")
    observed = set()
    document_claims = {}
    for document in sorted((root / "docs").rglob("*.md")):
        for key, serialized in CLAIM.findall(document.read_text(encoding="utf-8")):
            observed.add(key)
            document_claims.setdefault(document.relative_to(root).as_posix(), set()).add(key)
            try:
                value = json.loads(serialized)
            except ValueError:
                errors.append(f"{document.relative_to(root)}: invalid JSON contract claim {key}")
                continue
            if key not in expected:
                errors.append(f"{document.relative_to(root)}: undefined contract claim {key}")
            elif value != expected[key]:
                errors.append(f"{document.relative_to(root)}: conflicting contract claim {key}")
    for key in contract.get("requiredClaims", []):
        if key not in observed:
            errors.append(f"docs: missing cross-document assertion for {key}")
    for document, keys in contract.get("documentClaims", {}).items():
        for key in keys:
            if key not in document_claims.get(document, set()):
                errors.append(f"{document}: missing required contract assertion {key}")
    requirements = (
        set(
            re.findall(
                r"^\|\s*(REQ-[A-Z0-9-]+)\s*\|",
                (root / "docs/02-scope.md").read_text(encoding="utf-8"),
                re.MULTILINE,
            )
        )
        if (root / "docs/02-scope.md").is_file()
        else set()
    )
    traces = contract.get("requirements", {})
    for requirement in sorted(requirements - set(traces)):
        errors.append(f"docs/contracts.json: requirement lacks acceptance trace {requirement}")
    for requirement, trace in traces.items():
        if requirement not in requirements:
            errors.append(f"docs/contracts.json: undefined requirement trace {requirement}")
        if not trace.get("documents") or not trace.get("tests"):
            errors.append(f"{requirement}: acceptance trace requires documents and tests")
        for name in trace.get("documents", []):
            document = (root / name).resolve()
            if not document.is_relative_to(root) or not document.is_file():
                errors.append(f"{requirement}: missing contract document {name}")
        for identifier in trace.get("tests", []):
            parts = identifier.split(".")
            if len(parts) < 3 or not all(
                re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in parts
            ):
                errors.append(f"{requirement}: malformed acceptance test {identifier}")
                continue
            module = root.joinpath(*parts[:-2]).with_suffix(".py").resolve()
            if not module.is_relative_to(root) or not module.is_file():
                errors.append(f"{requirement}: missing acceptance test {identifier}")
                continue
            classes = [item for item in tree(root, module).body if isinstance(item, ast.ClassDef)]
            found = any(
                item.name == parts[-2]
                and any(
                    isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and method.name == parts[-1]
                    for method in item.body
                )
                for item in classes
            )
            if not found:
                errors.append(f"{requirement}: missing acceptance test {identifier}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--snapshot", action="store_true", help="Inspect facts without changing contracts"
    )
    args = parser.parse_args(argv)
    if args.snapshot:
        print(json.dumps(actual_facts(args.root), ensure_ascii=False, indent=2))
        return 0
    errors = check(args.root)
    for error in errors:
        print(error)
    if errors:
        return 1
    print("Documented CLI, routes, capabilities, versions and agent paths match runtime contracts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
