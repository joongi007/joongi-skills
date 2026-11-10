#!/usr/bin/env python3
"""Offline retrieval smoke benchmark; synthetic metadata, not an LLM quality test."""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from joongi_hub.review_graph import tool_definitions  # noqa: E402
from joongi_hub.search import Document, parameter_text, rank  # noqa: E402
from joongi_hub.skills import Skills  # noqa: E402


def corpus(size):
    documents = []
    for skill in Skills(ROOT / "skills").list():
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
    extra = [
        ("docs", "convert_to_markdown", "Convert documents to Markdown.", "source_uri"),
        ("docs", "getVersion", "Read the library version.", "library_id"),
        ("browser", "takeScreenshot", "Capture a screenshot of a browser page.", "viewport_size"),
        ("finance", "get_price", "Get the authoritative unit price of a product.", "sku"),
        ("finance", "get_exchange_rate", "Look up a currency exchange rate.", "base_currency"),
        ("infra", "rollout", "Inspect a Kubernetes deployment rollout.", "deployment_name"),
        (
            "docs",
            "a_tutorial",
            "Examples mentioning convert_to_markdown and engineering-playbook.",
            "example_id",
        ),
    ]
    specs = [("graph", t["name"], t["description"], t["inputSchema"]) for t in tool_definitions()]
    specs += [
        (server, name, desc, {"properties": {arg: {"type": "string"}}})
        for server, name, desc, arg in extra
    ]
    for i in range(max(0, size - len(specs) - len(documents))):
        specs.append(
            (
                "misc",
                f"record_{i:04d}",
                "Read project data and reference examples for a generic application.",
                {"properties": {"record_id": {"type": "string"}}},
            )
        )
    for server, name, description, schema in specs:
        value = {
            "kind": "tool",
            "name": server + "__" + name,
            "description": description,
            "server": server,
            "inputSchema": schema,
        }
        documents.append(
            Document(
                value,
                {
                    "name": value["name"],
                    "aliases": name,
                    "description": description,
                    "server": server,
                    "parameters": parameter_text(schema),
                },
            )
        )
    return documents


def cases():
    graph_names = {"graph__" + t["name"] for t in tool_definitions()}
    return [
        ("convert_to_markdown", {"docs__convert_to_markdown"}),
        ("docs__convert_to_markdown", {"docs__convert_to_markdown"}),
        ("source_uri", {"docs__convert_to_markdown"}),
        ("get version", {"docs__getVersion"}),
        ("library_id", {"docs__getVersion"}),
        ("repo_root", graph_names),
        ("max_lines_per_file", {"graph__get_review_context_tool"}),
        ("file_path_pattern", {"graph__find_large_functions_tool"}),
        (
            "changed_files",
            {
                "graph__get_review_context_tool",
                "graph__get_minimal_context_tool",
                "graph__get_impact_radius_tool",
            },
        ),
        ("section_name", {"graph__get_docs_section_tool"}),
        ("viewport_size", {"browser__takeScreenshot"}),
        ("screenshot", {"browser__takeScreenshot"}),
        ("unit price", {"finance__get_price"}),
        ("base_currency", {"finance__get_exchange_rate"}),
        ("deployment_name", {"infra__rollout"}),
        ("Kubernetes", {"infra__rollout"}),
        ("engineering-playbook", {"engineering-playbook"}),
        ("한국어", {"usual-korean"}),
        ("문서 변환", {"docs__convert_to_markdown"}),
        ("convert markdown", {"docs__convert_to_markdown"}),
        ("정규식 취약점", {"engineering-playbook"}),
        ("ReDoS", {"engineering-playbook"}),
    ]


def old_search(documents, query):
    terms = query.lower().split()
    result = []
    for document in documents:
        item = document.value
        text = (item["name"] + " " + item.get("description", "")).lower()
        score = sum(term in text for term in terms)
        if score:
            result.append({**item, "score": score})
    return sorted(result, key=lambda item: (-item["score"], item["name"]))[:5]


def benchmark(size, repeats):
    documents = corpus(size)
    result = {
        "documents": len(documents),
        "queries": len(cases()),
        "repeats": repeats,
        "scope": "Curated synthetic retrieval smoke set, not held-out LLM task performance",
        "engines": {},
    }
    for name, search in [
        ("previous_substring_count", old_search),
        ("weighted_lexical", lambda docs, q: rank(docs, q, limit=5)),
    ]:
        durations, rows = [], []
        for query, expected in cases():
            for _ in range(repeats):
                start = time.perf_counter()
                items = search(documents, query)
                durations.append((time.perf_counter() - start) * 1000)
            names = [item["name"] for item in items]
            position = next((i + 1 for i, value in enumerate(names) if value in expected), None)
            rows.append(
                {
                    "query": query,
                    "top1": bool(position == 1),
                    "hit5": position is not None,
                    "rr5": 1 / position if position else 0,
                    "returned": names,
                }
            )
        result["engines"][name] = {
            "top1": sum(row["top1"] for row in rows),
            "hit5": sum(row["hit5"] for row in rows),
            "mrr5": round(statistics.mean(row["rr5"] for row in rows), 4),
            "query_p50_ms": round(statistics.median(durations), 3),
            "cases": rows,
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 50 <= args.size <= 5000 or not 1 <= args.repeats <= 10:
        parser.error("size: 50..5000, repeats: 1..10")
    result = benchmark(args.size, args.repeats)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(
        json.dumps(
            {
                **result,
                "engines": {
                    key: {k: v for k, v in value.items() if k != "cases"}
                    for key, value in result["engines"].items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
