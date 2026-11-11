#!/usr/bin/env python3
"""Stage a static Pages site and a verified, source-based installation bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path

if __package__:
    from scripts.build_site_docs import build_docs
else:
    from build_site_docs import build_docs

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    "__pycache__",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    ".DS_Store",
    ".local",
    ".aws",
    ".codex",
    ".agents",
    ".claude",
    ".cursor",
    ".copilot",
    ".gemini",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
}


def public_file(path: Path) -> bool:
    return not (
        any(part in EXCLUDED for part in path.parts)
        or (path.name.startswith(".env") and path.name != ".env.example")
        or path.suffix.lower() in {".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx"}
    )


def public_header(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Do not publish the build machine's account, group or file timestamps."""
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    info.pax_headers = {}
    return info


def build(output: Path, base_url: str) -> None:
    if not base_url.startswith("https://"):
        raise ValueError("Pages base URL must use HTTPS")
    output = output.resolve()
    if output == ROOT or ROOT.is_relative_to(output):
        raise ValueError("Output must not contain the source repository")
    if output.exists():
        raise ValueError("Output already exists; choose a new staging directory")
    output.mkdir(parents=True)
    site = ROOT / "site"
    if site.is_dir():
        for file in sorted(site.rglob("*")):
            relative = file.relative_to(site)
            if file.is_file() and not file.is_symlink() and public_file(relative):
                target = output / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, target)
    build_docs(ROOT, output, public_file)
    archive_path = output / "joongi-skills.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for name in (
            "skills",
            "joongi_hub",
            "scripts",
            "tests",
            "refs",
            "site",
            "frontend",
            "examples",
            "package.json",
            "package-lock.json",
            "requirements-docs.txt",
            ".github",
            ".gitignore",
            ".code-review-graphignore",
            "build.sh",
            "AGENTS.md",
            "PRODUCT.md",
            "DESIGN.md",
            "pyproject.toml",
            "install.sh",
            "install.ps1",
            "VERSION",
            "README.md",
            "docs",
            "LICENSE",
        ):
            path = ROOT / name
            if not path.exists():
                continue
            files = sorted(path.rglob("*")) if path.is_dir() else [path]
            for file in files:
                relative = file.relative_to(ROOT)
                if not file.is_file() or file.is_symlink() or not public_file(relative):
                    continue
                archive.add(
                    file,
                    arcname="joongi-skills/" + relative.as_posix(),
                    recursive=False,
                    filter=public_header,
                )
    sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    manifest = {
        "schema": 1,
        "archive": archive_path.name,
        "sha256": sha256,
        "version": (ROOT / "VERSION").read_text().strip()
        if (ROOT / "VERSION").exists()
        else "development",
    }
    (output / "bundle-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (output / "SHA256SUMS").write_text(f"{sha256}  {archive_path.name}\n", encoding="utf-8")
    for name in ("install.sh", "install.ps1"):
        text = (ROOT / name).read_text(encoding="utf-8")
        (output / name).write_text(
            text.replace("@DOWNLOAD_BASE@", base_url.rstrip("/")), encoding="utf-8"
        )
    (output / ".nojekyll").touch()
    print(f"Pages artifact ready: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    build(args.out, args.base_url)
