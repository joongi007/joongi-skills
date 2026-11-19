"""Compare the current ranker with a pinned local Git baseline.

Run from a trusted checkout: the historical Python source is executed locally.
Only public bundled skills and synthetic metadata are used.
"""

import argparse
import hashlib
import json
import math
import os
import platform
import random
import re
import shutil
import statistics
import subprocess
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from joongi_hub import search as current  # noqa: E402
from scripts.benchmark_catalog_search import cases, corpus  # noqa: E402

BASELINE = "709cc5ada82b8abfb8ca20c9f71506d3eee80ef5"
parser = argparse.ArgumentParser(
    description="Offline rank comparison; no Hub state or network access"
)
parser.add_argument("--sizes", nargs="+", type=int)
parser.add_argument("--repeats", type=int, default=5)
parser.add_argument("--seed", type=int, default=20261119)
parser.add_argument("--baseline-revision", default=BASELINE)
parser.add_argument(
    "--followup",
    action="store_true",
    help="Compare only current no-cache/cache-object, default 5000 documents",
)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
if not re.fullmatch(r"[0-9a-f]{40}", args.baseline_revision):
    parser.error("--baseline-revision must be a full lowercase Git commit SHA")
if args.out.exists():
    parser.error("output already exists; choose a new path to preserve earlier measurements")
if args.repeats < 1 or any(n < 1 or n > 10000 for n in args.sizes or []):
    parser.error("repeats must be positive; corpus sizes must be between 1 and 10000")
try:
    baseline_bytes = subprocess.check_output(
        ["git", "show", f"{args.baseline_revision}:joongi_hub/search.py"],
        cwd=ROOT,
        stderr=subprocess.PIPE,
    )
except subprocess.CalledProcessError:
    parser.error(
        "baseline is not in the local Git history; use a checkout "
        "containing the pinned commit (no automatic fetch)"
    )
old = types.ModuleType("joongi_search_before")
old.__file__ = "git-baseline/joongi_hub/search.py"
sys.modules[old.__name__] = old
exec(compile(baseline_bytes, old.__file__, "exec"), old.__dict__)
REPEATS = args.repeats
SEED = args.seed
rng = random.Random(SEED)


def summary(values):
    ordered = sorted(values)
    return {
        "samples": len(values),
        "p50_ms": statistics.median(ordered),
        "p95_ms": ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)],
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
    }


def payload_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def cpu_name():
    path = Path("/proc/cpuinfo")
    if path.exists():
        for line in path.read_text().splitlines():
            if line.startswith("model name"):
                return line.partition(":")[2].strip()
    return platform.processor()


result = {
    "environment": {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "cpu": cpu_name(),
        "logical_cpus": os.cpu_count(),
        "timer": "time.perf_counter_ns",
        "seed": SEED,
        "repeats_per_keyword_query": REPEATS,
        "concurrent_workload": (
            "Other agents may run builds/tests on the same host; no CPU isolation/governor control"
        ),
    },
    "scope": (
        "Offline lexical rank() on current public skills and synthetic "
        "metadata; excludes Hub filesystem/catalog assembly, transport I/O, "
        "upstream connection and LLM success/token measurements"
    ),
    "method": {
        "keyword_queries": [q for q, _ in cases()] + ["project"],
        "fair_options": {"limit": 5, "detail": "full", "mode": "keyword"},
        "ranking_equality": (
            "Exact returned dictionaries, including scores and schemas, "
            "compared per query for all engines"
        ),
        "cache": (
            "Warm cache prefilled once, cold cache creates a new instance per "
            "call; selected metadata normalisation and hashing remain in "
            "measured rank()."
        ),
        "percentile": "p95 nearest-rank percentile; median p50",
        "output_bytes": (
            "Compact UTF-8 JSON payload only, excluding JSON-RPC/content "
            "envelope and actual schema consent wrapping. Chosen detail "
            "simulated with current Document.value; no LLM token estimator."
        ),
    },
    "corpora": [],
}
for size in args.sizes or ([5000] if args.followup else [100, 1000, 5000]):
    docs = corpus(size)
    assert len(docs) == size
    queries = [q for q, _ in cases()] + ["project"]
    expected = {q: old.rank(docs, q, limit=5, detail="full") for q in queries}
    cache = current.SearchCache()
    current.rank(docs, queries[0], limit=5, detail="full", cache=cache)
    engines = {
        "old_rank": lambda q, docs=docs: old.rank(docs, q, limit=5, detail="full"),
        "current_no_cache": lambda q, docs=docs: current.rank(docs, q, limit=5, detail="full"),
        "current_cold_cache": lambda q, docs=docs: current.rank(
            docs, q, limit=5, detail="full", cache=current.SearchCache()
        ),
        "current_warm_cache": lambda q, docs=docs, cache=cache: current.rank(
            docs, q, limit=5, detail="full", cache=cache
        ),
    }
    if args.followup:
        engines = {
            key: value
            for key, value in engines.items()
            if key in ("current_no_cache", "current_warm_cache")
        }
    timings = {name: [] for name in engines}
    per_query = {name: {q: [] for q in queries} for name in engines}
    for _repeat in range(REPEATS):
        ordered_queries = list(queries)
        rng.shuffle(ordered_queries)
        for query in ordered_queries:
            order = list(engines)
            rng.shuffle(order)
            for name in order:
                start = time.perf_counter_ns()
                actual = engines[name](query)
                elapsed = (time.perf_counter_ns() - start) / 1e6
                assert actual == expected[query], (size, query, name)
                timings[name].append(elapsed)
                per_query[name][query].append(elapsed)
    row = {
        "documents": size,
        "keyword": {name: summary(values) for name, values in timings.items()},
        "keyword_per_query": {
            name: {q: summary(values) for q, values in rows.items()}
            for name, rows in per_query.items()
        },
        "ranking_equal": True,
        "warm_cache_status": cache.status(),
    }
    mode_results = {}
    for mode, query in (
        [] if args.followup else [("literal", "project"), ("regex", "project|review")]
    ):
        if mode == "regex" and not shutil.which("rg"):
            mode_results[mode] = {"skipped": "ripgrep is unavailable"}
            continue
        expected_mode = old.rank(docs, query, mode=mode, limit=5, detail="full")
        samples = {name: [] for name in ("old_rank", "current_no_cache", "current_warm_cache")}
        for _repeat in range(9):
            names = list(samples)
            rng.shuffle(names)
            for name in names:
                function = old.rank if name == "old_rank" else current.rank
                options = {"cache": cache} if name == "current_warm_cache" else {}
                started = time.perf_counter_ns()
                actual = function(docs, query, mode=mode, limit=5, detail="full", **options)
                elapsed = (time.perf_counter_ns() - started) / 1e6
                assert actual == expected_mode, (size, mode, name)
                samples[name].append(elapsed)
        mode_results[mode] = {
            "query": query,
            "ranking_equal": True,
            "latency": {name: summary(values) for name, values in samples.items()},
        }
    row["other_modes"] = mode_results
    previous = old.rank(docs, "project")
    light = current.rank(docs, "project")
    chosen = light[0]["name"] if light else None
    full = next(d.value for d in docs if d.value["name"] == chosen) if chosen else None
    previous_bytes = payload_bytes(previous)
    search_bytes = payload_bytes(light)
    detail_bytes = payload_bytes(full)
    row["broad_response_bytes"] = {
        "query": "project",
        "old_default_results": len(previous),
        "current_default_results": len(light),
        "chosen_name": chosen,
        "old_100_full": previous_bytes,
        "new_5_summary": search_bytes,
        "chosen_full_detail": detail_bytes,
        "new_total": search_bytes + detail_bytes,
        "reduction_percent": 100 * (1 - (search_bytes + detail_bytes) / previous_bytes),
    }
    result["corpora"].append(row)
    print(
        json.dumps(
            {
                "documents": size,
                "keyword": row["keyword"],
                "warm_cache_status": row["warm_cache_status"],
                "bytes": row["broad_response_bytes"],
            }
        ),
        flush=True,
    )
result["environment"]["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
result["baseline_source"] = {
    "revision": args.baseline_revision,
    "path": "joongi_hub/search.py",
    "sha256": hashlib.sha256(baseline_bytes).hexdigest(),
}
result["current_source_sha256"] = hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest()
result["followup_mode"] = args.followup
result["environment"]["concurrent_workload"] = (
    "Uncontrolled shared host; other builds/tests may run concurrently. "
    "Record local conditions separately."
)
args.out.parent.mkdir(parents=True, exist_ok=True)
with args.out.open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
