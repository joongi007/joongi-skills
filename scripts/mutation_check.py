#!/usr/bin/env python3
"""Generate and run independent AST mutants in disposable source copies.

The default campaign covers the persistence and ownership boundary. Operators
are systematic rather than five preselected text replacements. Reports retain
surviving, timed-out and invalid mutants separately; a score is evidence about
the selected target and regression suite, never global program correctness.
"""

import argparse
import ast
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPARISONS = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Lt: ast.GtE,
    ast.LtE: ast.Gt,
    ast.Gt: ast.LtE,
    ast.GtE: ast.Lt,
}


@dataclass(frozen=True)
class Mutation:
    node_index: int
    operator: str
    line: int
    column: int
    detail: str
    operand_index: int = 0


def inventory(tree):
    """Enumerate each applicable comparison, boolean, branch and numeric mutant."""
    result = []
    for index, node in enumerate(ast.walk(tree)):
        location = (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))

        def add(operator, detail, operand_index=0, current=index, position=location):
            result.append(Mutation(current, operator, *position, detail, operand_index))

        if isinstance(node, ast.Compare):
            for operand_index, operator in enumerate(node.ops):
                if type(operator) in COMPARISONS:
                    add("comparison", type(operator).__name__, operand_index)
        elif isinstance(node, ast.BoolOp):
            add("boolean", type(node.op).__name__)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            add("negation", "remove-not")
        elif isinstance(node, (ast.If, ast.IfExp)):
            add("branch", "always-true", 1)
            add("branch", "always-false", 0)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                add("constant", "invert-boolean")
            elif isinstance(node.value, int):
                add("constant", f"integer-plus-one:{node.value}")
    return result


def mutated_source(tree, mutation):
    changed = copy.deepcopy(tree)
    nodes = list(ast.walk(changed))
    node = nodes[mutation.node_index]
    if mutation.operator == "comparison":
        node.ops[mutation.operand_index] = COMPARISONS[type(node.ops[mutation.operand_index])]()
    elif mutation.operator == "boolean":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif mutation.operator == "negation":
        replacement = ast.copy_location(node.operand, node)
        for parent in nodes:
            for key, value in ast.iter_fields(parent):
                if value is node:
                    setattr(parent, key, replacement)
                elif isinstance(value, list):
                    setattr(parent, key, [replacement if item is node else item for item in value])
    elif mutation.operator == "branch":
        node.test = ast.copy_location(ast.Constant(bool(mutation.operand_index)), node.test)
    elif mutation.operator == "constant":
        node.value = not node.value if isinstance(node.value, bool) else node.value + 1
    else:
        raise ValueError("Unknown mutation operator")
    ast.fix_missing_locations(changed)
    # Invalid generated programs must never be counted as detected faults.
    compile(changed, "<mutant>", "exec")
    return ast.unparse(changed) + "\n"


def run_tests(directory, tests, timeout):
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(directory))
    started = time.monotonic()
    try:
        process = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", *tests, "-q"],
            cwd=directory,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "seconds": time.monotonic() - started}
    if process.returncode == 0:
        status = "survived"
    elif "FAILED (" in process.stderr:
        status = "killed"
    else:
        status = "invalid"
    return {
        "status": status,
        "seconds": round(time.monotonic() - started, 3),
        "returncode": process.returncode,
        "output": (process.stdout + process.stderr)[-10000:],
    }


def reviewed_survivors(report, policy):
    """A review is valid only for this exact target source and mutant location."""
    if (
        policy.get("schema") != 1
        or policy.get("target") != report["target"]
        or policy.get("sourceSha256") != report["sourceSha256"]
        or not isinstance(policy.get("equivalent"), list)
    ):
        raise ValueError("Mutation reviews do not match the current target source; review again")
    keys = ("line", "column", "operator", "detail", "operand_index")
    approved = {}
    for entry in policy["equivalent"]:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("reason"), str)
            or not entry["reason"].strip()
        ):
            raise ValueError("Equivalent mutation reviews need a reason")
        fingerprint = tuple(entry.get(key) for key in keys)
        if any(value is None for value in fingerprint) or fingerprint in approved:
            raise ValueError("Equivalent mutation reviews need unique, complete locations")
        approved[fingerprint] = entry["reason"]
    reviewed = []
    for item in report["results"]:
        fingerprint = tuple(item[key] for key in keys)
        if item["status"] == "survived" and fingerprint in approved:
            reviewed.append({"id": item["id"], "reason": approved[fingerprint]})
    return reviewed


def campaign(root, target, tests, timeout=10, max_mutants=0, operators=None):
    supported = {"comparison", "boolean", "negation", "branch", "constant"}
    if timeout <= 0 or max_mutants < 0 or (operators and not operators <= supported):
        raise ValueError("Use a positive timeout, nonnegative mutant limit and known operators")
    root = Path(root).resolve()
    relative = Path(target)
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix != ".py":
        raise ValueError("Mutation target must be a Python file inside the repository")
    original = path.read_text(encoding="utf-8")
    tree = ast.parse(original)
    mutations = inventory(tree)
    if operators:
        mutations = [mutation for mutation in mutations if mutation.operator in operators]
    if max_mutants:
        mutations = mutations[:max_mutants]
    if not mutations:
        raise ValueError("No applicable AST mutations for this target/operator selection")
    report = {
        "schema": 1,
        "target": relative.as_posix(),
        "sourceSha256": hashlib.sha256(original.encode()).hexdigest(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "tests": tests,
        "operators": sorted({mutation.operator for mutation in mutations}),
        "results": [],
    }
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="joongi-mutation-") as temporary:
        directory = Path(temporary)
        for folder in ("joongi_hub", "tests", "skills", "scripts"):
            if (root / folder).is_dir():
                shutil.copytree(
                    root / folder,
                    directory / folder,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
        for name in ("README.md", "VERSION"):
            if (root / name).is_file():
                shutil.copyfile(root / name, directory / name)
        destination = directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(original, encoding="utf-8")
        baseline = run_tests(directory, tests, timeout)
        report["baseline"] = baseline
        if baseline["status"] != "survived":
            report["error"] = "Baseline suite did not pass; mutation results are invalid"
            return report
        for number, mutation in enumerate(mutations, 1):
            try:
                source = mutated_source(tree, mutation)
            except (SyntaxError, ValueError) as error:
                result = {"status": "invalid", "output": str(error)}
            else:
                destination.write_text(source, encoding="utf-8")
                result = run_tests(directory, tests, timeout)
            record = {"id": number, **asdict(mutation), **result}
            report["results"].append(record)
            print(
                f"{number}/{len(mutations)} {result['status']}: "
                f"{relative}:{mutation.line} {mutation.operator} {mutation.detail}",
                flush=True,
            )
        destination.write_text(original, encoding="utf-8")
    report["seconds"] = round(time.monotonic() - started, 3)
    report["summary"] = dict(Counter(result["status"] for result in report["results"]))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--target", default="joongi_hub/storage.py")
    parser.add_argument("--tests", nargs="+", default=["tests.test_storage_contracts"])
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--max-mutants", type=int, default=0, help="0 enumerates every mutant")
    parser.add_argument("--operators", help="Comma-separated operator subset")
    parser.add_argument("--report", type=Path, default=ROOT / "dist/mutation-report.json")
    parser.add_argument("--fail-on-survivor", action="store_true")
    parser.add_argument("--reviewed-survivors", type=Path)
    args = parser.parse_args(argv)
    report = campaign(
        args.root,
        args.target,
        args.tests,
        args.timeout,
        args.max_mutants,
        set(args.operators.split(",")) if args.operators else None,
    )
    if args.reviewed_survivors and not report.get("error"):
        try:
            policy = json.loads(args.reviewed_survivors.read_text(encoding="utf-8"))
            report["reviewedEquivalent"] = reviewed_survivors(report, policy)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            report["error"] = str(exc)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "target": report["target"],
                "summary": report.get("summary"),
                "report": str(args.report),
            }
        )
    )
    if report.get("error"):
        print(report["error"], file=sys.stderr)
        return 1
    summary = report["summary"]
    return int(
        bool(
            summary.get("invalid")
            or summary.get("timeout")
            or (
                args.fail_on_survivor
                and summary.get("survived", 0) > len(report.get("reviewedEquivalent", []))
            )
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
