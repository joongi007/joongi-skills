#!/usr/bin/env python3
"""Check maintained Markdown links, skill routes and document identifiers.

This verifies deterministic structure. It does not claim semantic consistency
between prose and runtime behavior; contract and acceptance tests cover that.
"""

import argparse
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

if __package__:
    from scripts.check_contracts import check as check_contracts
else:
    from check_contracts import check as check_contracts

LINK = re.compile(r"\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)")
ROUTE = re.compile(r"`(references/[^`]+|PLAYBOOK\.md)`")
DOC_ID = re.compile(r"^문서 ID:\s*([A-Z][A-Z0-9-]+)", re.MULTILINE)
REQ_ID = re.compile(r"\bREQ-[A-Z][A-Z0-9-]*\b")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def prose(text):
    """Drop fenced examples so sample paths are not treated as real links."""
    lines = []
    fence_character = None
    fence_length = 0
    for line in text.splitlines():
        match = FENCE.match(line)
        if match:
            marker = match[1]
            if fence_character is None:
                fence_character, fence_length = marker[0], len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
            continue
        if fence_character is None:
            lines.append(line)
    return "\n".join(lines)


def check(root):
    root = Path(root).resolve()
    errors = []
    documents = [
        path
        for directory in ("docs", "skills", "refs")
        for path in (root / directory).rglob("*.md")
    ]
    if (root / "README.md").is_file():
        documents.append(root / "README.md")
    ids = {}
    scope = root / "docs/02-scope.md"
    requirements = set()
    if scope.is_file():
        requirements = set(
            re.findall(
                r"^\|\s*(REQ-[A-Z0-9-]+)\s*\|", scope.read_text(encoding="utf-8"), re.MULTILINE
            )
        )
    for path in sorted(documents):
        relative = path.relative_to(root)
        text = prose(path.read_text(encoding="utf-8"))
        for match in LINK.finditer(text):
            target = match[1].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            # Absolute web links belong to site routing, not source filesystem.
            if parsed.path.startswith("/"):
                continue
            resolved = (path.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to(root):
                errors.append(f"{relative}: local link escapes repository: {target}")
            elif not resolved.exists():
                errors.append(f"{relative}: broken local link: {target}")
        if path.is_relative_to(root / "docs"):
            for identifier in DOC_ID.findall(text):
                if identifier in ids:
                    errors.append(
                        f"{relative}: duplicate document ID {identifier} (also {ids[identifier]})"
                    )
                else:
                    ids[identifier] = str(relative)
            if scope.is_file():
                for identifier in sorted(set(REQ_ID.findall(text)) - requirements):
                    errors.append(f"{relative}: unknown requirement {identifier}")
        if path.name == "SKILL.md" and path.is_relative_to(root / "skills"):
            original = path.read_text(encoding="utf-8")
            match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", original, re.DOTALL)
            if not match:
                errors.append(f"{relative}: missing frontmatter")
                continue
            fields = dict(re.findall(r"^(name|description):\s*(.+)$", match[1], re.MULTILINE))
            if fields.get("name") != path.parent.name:
                errors.append(f"{relative}: name must match directory")
            description = fields.get("description", "").strip("\"'")
            if not description or len(description) > 1024:
                errors.append(f"{relative}: description must be 1..1024 characters")
            if len(original[match.end() :].splitlines()) >= 500:
                errors.append(f"{relative}: body must stay below 500 lines")
            for route in sorted(set(ROUTE.findall(text))):
                if not (path.parent / route).is_file():
                    errors.append(f"{relative}: missing routed reference: {route}")
            for reference in sorted((path.parent / "references").glob("*.md")):
                route = "references/" + reference.name
                if route not in ROUTE.findall(text):
                    errors.append(f"{relative}: unrouted reference: {route}")
    if (root / "docs/contracts.json").is_file():
        errors.extend(check_contracts(root))
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    errors = check(args.root)
    for error in errors:
        print(error)
    if errors:
        print(f"{len(errors)} documentation error(s)")
        return 1
    print(
        "Documentation links, routes, requirement traces and executable claims passed. "
        "Unstructured prose still requires review."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
