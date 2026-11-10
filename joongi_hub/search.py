"""Bounded lexical catalog retrieval; optional ripgrep uses Rust's default engine."""

import math
import re
import shutil
import subprocess
import unicodedata
from collections import Counter
from dataclasses import dataclass

from joongi_hub.errors import RpcError

WEIGHTS = {"name": 5.0, "aliases": 4.0, "server": 2.0, "description": 1.0, "parameters": 0.75}
MAX_INDEX_BYTES = 8 * 1024**2
MAX_FIELD_CHARS = 8192


def clean(value):
    return " ".join(unicodedata.normalize("NFKC", value).replace("\0", " ").split())


def tokens(value):
    # Only these constant patterns run in Python re, never a user's pattern.
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return re.findall(r"[^\W_]+", value.casefold(), re.UNICODE)


def parameter_text(schema):
    """Index argument names/descriptions, not defaults, examples, auth or file contents."""
    found = []
    remaining = 1000

    def visit(node, depth=0):
        nonlocal remaining
        if remaining <= 0 or depth > 8 or not isinstance(node, dict):
            return
        remaining -= 1
        if isinstance(node.get("description"), str):
            found.append(node["description"][:MAX_FIELD_CHARS])
        for key in ("properties", "$defs", "definitions"):
            children = node.get(key, {})
            if isinstance(children, dict):
                for name, child in list(children.items())[:1000]:
                    if remaining <= 0:
                        break
                    found.append(name)
                    visit(child, depth + 1)
        for key in ("items", "additionalProperties"):
            visit(node.get(key), depth + 1)
        for key in ("anyOf", "allOf", "oneOf"):
            for child in node.get(key, [])[:100] if isinstance(node.get(key), list) else []:
                visit(child, depth + 1)

    visit(schema)
    return " ".join(found)[:MAX_FIELD_CHARS]


@dataclass
class Document:
    value: dict
    fields: dict


def validate(query, mode, match, limit, detail, kind, server):
    if not isinstance(query, str) or len(query) > 1000 or "\0" in query:
        raise RpcError(-32602, "Search query must be text (up to 1000 characters, no NUL)")
    if mode not in ("keyword", "literal", "regex") or match not in ("any", "all"):
        raise RpcError(-32602, "Use keyword/literal/regex mode and any/all keyword matching")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise RpcError(-32602, "Search limit must be an integer from 1 to 100")
    if detail not in ("summary", "full") or kind not in ("all", "skill", "tool"):
        raise RpcError(-32602, "Use summary/full detail and all/skill/tool kind")
    if server is not None and (not isinstance(server, str) or len(server) > 48):
        raise RpcError(-32602, "Server filter must be a server ID")


def regex_matches(documents, query):
    executable = shutil.which("rg")
    if not executable:
        raise RpcError(-32602, "Regex mode requires ripgrep (rg). Use keyword or literal mode.")
    lines, owners = [], []
    for index, document in enumerate(documents):
        for value in document.fields.values():
            if value:
                lines.append(value)
                owners.append(index)
    try:
        process = subprocess.run(
            [
                executable,
                "--no-config",
                "--engine",
                "default",
                "--text",
                "--line-number",
                "--no-filename",
                "--color",
                "never",
                "--ignore-case",
                "--regex-size-limit",
                "1M",
                "--dfa-size-limit",
                "1M",
                "--regexp",
                query,
                "-",
            ],
            input="\n".join(lines) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RpcError(-32602, "Regex search failed or timed out; narrow the pattern") from exc
    if process.returncode not in (0, 1):
        raise RpcError(
            -32602, "Invalid or unsupported Rust regex; lookaround/backreferences are unavailable"
        )
    return {
        owners[int(line.partition(":")[0]) - 1]
        for line in process.stdout.splitlines()
        if line.partition(":")[0].isdigit() and 1 <= int(line.partition(":")[0]) <= len(owners)
    }


def rank(
    documents,
    query,
    *,
    mode="keyword",
    match="any",
    limit=100,
    detail="full",
    kind="all",
    server=None,
):
    validate(query, mode, match, limit, detail, kind, server)
    selected = []
    size = 0
    for document in documents:
        value = document.value
        if kind != "all" and value["kind"] != kind:
            continue
        if server is not None and value.get("server") != server:
            continue
        fields = {key: clean(text[:MAX_FIELD_CHARS]) for key, text in document.fields.items()}
        size += sum(len(text.encode("utf-8", errors="replace")) for text in fields.values())
        if size > MAX_INDEX_BYTES or len(selected) >= 10000:
            raise RpcError(-32602, "Catalog metadata is too large; use kind/server filters")
        selected.append(Document(value, fields))
    if not selected:
        return []
    normalized = clean(query).casefold()
    term_list = sorted(set(tokens(clean(query))))
    counts = [{key: Counter(tokens(text)) for key, text in doc.fields.items()} for doc in selected]
    unions = [set().union(*(set(field) for field in item.values())) for item in counts]
    frequency = Counter(word for words in unions for word in words)
    averages = {
        key: sum(sum(item.get(key, {}).values()) for item in counts) / len(selected)
        for key in WEIGHTS
    }
    regex_hits = regex_matches(selected, query) if mode == "regex" and query else None
    ranked = []
    for index, doc in enumerate(selected):
        names = [doc.fields.get(key, "").casefold() for key in ("name", "aliases")]
        exact = normalized and normalized in names
        score = 1000.0 if exact else 0.0
        if not query:
            matched = True
        elif mode == "regex":
            matched = index in regex_hits
            score += 1.0
        elif mode == "literal" or not term_list:
            hits = [key for key, text in doc.fields.items() if normalized in text.casefold()]
            matched = bool(hits)
            score += sum(WEIGHTS[key] for key in hits)
        else:
            partial = [
                term
                for term in term_list
                if not frequency[term]
                and any(term in text.casefold() for text in doc.fields.values())
            ]
            hits = [term in unions[index] or term in partial for term in term_list]
            prefix = len(term_list) == 1 and any(normalized in name for name in names)
            matched = (all(hits) if match == "all" else any(hits)) or exact or prefix
            if prefix:
                score += 10.0
            score += 0.2 * len(partial)
            for term in term_list:
                inverse = math.log(
                    1 + (len(selected) - frequency[term] + 0.5) / (frequency[term] + 0.5)
                )
                for key, field in counts[index].items():
                    count = field[term]
                    if not count:
                        continue
                    length = sum(field.values())
                    norm = 1.2 * (0.25 + 0.75 * length / max(averages[key], 1))
                    score += WEIGHTS[key] * inverse * count * 2.2 / (count + norm)
        if matched:
            value = {**doc.value, "score": round(score, 6)}
            if detail == "summary":
                value = {
                    key: item
                    for key, item in value.items()
                    if key in {"kind", "name", "description", "server", "uri", "score"}
                }
                description = value.get("description", "")
                if len(description) > 300:
                    value["description"] = description[:300] + "…"
                    value["description_truncated"] = True
            ranked.append(value)
    return sorted(ranked, key=lambda item: (-item["score"], item["name"]))[:limit]
