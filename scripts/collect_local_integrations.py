#!/usr/bin/env python3
"""Inventory local MCP configuration and skill origins without copying secrets or executing them."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from scripts.install_manager import jsonc_data
else:
    from install_manager import jsonc_data

try:
    import tomllib
except ImportError:  # The Hub supports 3.10; TOML inventory requires 3.11+.
    tomllib = None

EXCLUDED = {
    ".local-tools",
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "vendor",
    "_vendor",
    "__pycache__",
    "dist",
    "build",
    "target",
    "site-packages",
    "venv",
    ".venv",
    ".venv-windows",
    ".cache",
    ".local",
    ".validation-tmp",
    ".next",
    ".nuxt",
    ".tox",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    "coverage",
    ".turbo",
    ".gradle",
}
CONFIG_NAMES = {
    ".mcp.json",
    "mcp.json",
    "mcp_config.json",
    "claude_desktop_config.json",
    "settings.json",
    "settings.local.json",
    "config.toml",
    "opencode.json",
    "opencode.jsonc",
}
MAX_BYTES = 1024 * 1024
MAX_FILES = 100000
MAX_DEPTH = 12
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def configuration(path: Path, text: str) -> dict:
    if path.suffix == ".toml":
        if tomllib is None:
            raise ValueError("toml_requires_python_3_11")
        data = tomllib.loads(text)
    else:
        data = jsonc_data(text)
    return data if isinstance(data, dict) else {}


def server_entries(data: dict):
    for key in ("mcpServers", "mcp_servers", "mcp"):
        entries = data.get(key)
        if not isinstance(entries, dict):
            continue
        # VS Code uses mcp.servers, unlike OpenCode's mcp.<name>.
        if key == "mcp" and isinstance(entries.get("servers"), dict):
            entries = entries["servers"]
        for name, entry in entries.items():
            if not isinstance(name, str) or not isinstance(entry, dict):
                continue
            if not any(field in entry for field in ("command", "url", "httpUrl", "type")):
                continue
            yield name, entry
    # .vscode/mcp.json stores servers directly at the root.
    if isinstance(data.get("servers"), dict):
        yield from server_entries({"mcpServers": data["servers"]})


def collect(root: Path) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("root_must_be_directory")
    skills = []
    servers = []
    issues = []
    visited = 0
    truncated = False
    projects = set()

    def on_error(error):
        # Exception messages can contain local data; record a fixed category only.
        issues.append({"kind": "directory_unreadable"})

    for directory, folders, files in os.walk(root, followlinks=False, onerror=on_error):
        parent = Path(directory)
        relative = parent.relative_to(root)
        folders[:] = sorted(
            name
            for name in folders
            if name not in EXCLUDED
            and not name.startswith(".venv")
            and not (parent / name).is_symlink()
        )
        if len(relative.parts) >= MAX_DEPTH:
            if folders:
                issues.append({"source": relative.as_posix(), "kind": "depth_limit"})
            folders[:] = []
        for filename in sorted(files):
            visited += 1
            if visited > MAX_FILES:
                truncated = True
                break
            if filename != "SKILL.md" and filename not in CONFIG_NAMES:
                continue
            path = parent / filename
            if path.is_symlink() or not path.is_file():
                continue
            source = path.relative_to(root).as_posix()
            if not path.resolve().is_relative_to(root):
                continue
            try:
                if path.stat().st_size > MAX_BYTES:
                    issues.append({"source": source, "kind": "file_size_limit"})
                    continue
                with path.open("rb") as stream:
                    raw = stream.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    issues.append({"source": source, "kind": "file_size_limit"})
                    continue
                text = raw.decode("utf-8-sig")
                project = path.relative_to(root).parts[0]
                if filename == "SKILL.md":
                    # Descriptions and instruction bodies may contain private project data.
                    # Keep only a validated routing name and a fingerprint for deduplication.
                    match = re.search(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
                    field = re.search(r"^name:\s*([^\r\n]+)", match[1], re.M) if match else None
                    name = field[1].strip().strip("\"'") if field else ""
                    if not NAME.fullmatch(name) or len(name) > 64:
                        issues.append({"source": source, "kind": "invalid_skill_name"})
                        continue
                    skills.append(
                        {
                            "name": name,
                            "source": source,
                            "project": project,
                            "sha256": hashlib.sha256(raw).hexdigest(),
                        }
                    )
                    projects.add(project)
                    continue
                data = configuration(path, text)
                for name, entry in server_entries(data):
                    # Allowlist output fields. Never emit commands, args, URLs, credentials,
                    # headers, environment names/values, descriptions, or raw parse errors.
                    transport = (
                        "stdio"
                        if "command" in entry
                        else "http"
                        if "url" in entry or "httpUrl" in entry
                        else "unknown"
                    )
                    declared = entry.get("type")
                    if declared in {
                        "sse",
                        "http",
                        "streamable-http",
                        "stdio",
                        "local",
                        "remote",
                        "sdk",
                    }:
                        transport = declared
                    servers.append(
                        {
                            "name": name,
                            "source": source,
                            "project": project,
                            "transport": transport,
                            "enabled": entry.get("enabled") is not False
                            and entry.get("disabled") is not True,
                        }
                    )
                    projects.add(project)
            except (OSError, UnicodeError, ValueError, RecursionError):
                issues.append({"source": source, "kind": "unreadable_or_invalid_config"})
        if truncated:
            break
    groups = {}
    for entry in skills:
        groups.setdefault(entry["sha256"], []).append(entry["source"])
    return {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "scope": "configuration_and_skill_files_only",
        "summary": {
            "projects": len(projects),
            "skills": len(skills),
            "unique_skill_contents": len(groups),
            "mcp_entries": len(servers),
        },
        "skills": skills,
        "mcp": servers,
        "duplicate_skills": [sources for sources in groups.values() if len(sources) > 1],
        "issues": issues,
        "limits": {"files": MAX_FILES, "depth": MAX_DEPTH, "bytes_per_file": MAX_BYTES},
        "truncated": truncated,
    }


def markdown(report: dict) -> str:
    def cell(value):
        return str(value).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")

    summary = report["summary"]
    lines = [
        "# 로컬 MCP·스킬 목록",
        "",
        f"확인: {report['generated_at']}",
        "",
        f"프로젝트 {summary['projects']}개 · 스킬 {summary['skills']}개 "
        f"(내용 기준 {summary['unique_skill_contents']}개) · MCP 설정 {summary['mcp_entries']}개",
        "",
        "설정·SKILL.md에서 발견한 후보이며 연결 성공이나 실제 사용 여부는 확인하지 않았습니다.",
        "명령·인자·URL·환경변수·헤더·스킬 본문은 저장하지 않습니다.",
        "",
        "## 스킬",
        "",
        "| 이름 | 프로젝트 | 원본 |",
        "|---|---|---|",
    ]
    for entry in report["skills"]:
        lines.append(
            "| " + " | ".join(cell(entry[k]) for k in ("name", "project", "source")) + " |"
        )
    lines += ["", "## MCP 설정", "", "| 이름 | 전송 | 활성 설정 | 원본 |", "|---|---|---|---|"]
    for entry in report["mcp"]:
        lines.append(
            "| "
            + " | ".join(cell(entry[k]) for k in ("name", "transport", "enabled", "source"))
            + " |"
        )
    lines += [
        "",
        f"확인 제한·읽기 오류: {len(report['issues'])}개. "
        f"파일 수 제한 도달: {report['truncated']}. 세부 항목은 JSON을 확인하세요.",
        "",
        "재사용할 항목은 원본 지침·라이선스·프로젝트 의존성을 검토한 뒤 선별합니다.",
        "다른 프로젝트 설정을 변경하거나 MCP를 실행하지 않았습니다.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=Path(".local/integrations"))
    args = parser.parse_args()
    report = collect(args.root)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, content in (
        ("catalog.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
        ("catalog.md", markdown(report)),
    ):
        path = args.out / name
        if path.is_symlink():
            raise ValueError("output_must_not_be_symlink")
        path.write_text(content, encoding="utf-8")
        path.chmod(0o600)
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"Catalog: {args.out / 'catalog.md'}")
    if report["truncated"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
