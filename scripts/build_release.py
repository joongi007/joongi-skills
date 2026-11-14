"""Build release subjects using only the Python standard library and reviewed source."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

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


def bootstrap_text(root, name, base_url):
    template = (root / name).read_text(encoding="utf-8")
    if "# @ATTESTATION_VERIFIER@" not in template:
        return template.replace("@DOWNLOAD_BASE@", base_url.rstrip("/"))
    verifier = (root / "scripts/verify_release.py").read_text(encoding="utf-8")
    verifier = verifier[: verifier.index('if __name__ == "__main__":')]
    return (
        (root / name)
        .read_text(encoding="utf-8")
        .replace("@DOWNLOAD_BASE@", base_url.rstrip("/"))
        .replace("# @ATTESTATION_VERIFIER@", verifier)
    )


def source_revision(root):
    revision = os.environ.get("GITHUB_SHA")
    if not revision:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
        )
        revision = result.stdout.strip() if result.returncode == 0 else None
    return revision if revision and re.fullmatch("[a-f0-9]{40}", revision) else None


def build_release(root, output, base_url):
    if not base_url.startswith("https://"):
        raise ValueError("Release base URL must use HTTPS")
    output.mkdir(parents=True, exist_ok=True)
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
            path = root / name
            if not path.exists():
                continue
            files = sorted(path.rglob("*")) if path.is_dir() else [path]
            for file in files:
                relative = file.relative_to(root)
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
        "revision": source_revision(root),
        "version": (root / "VERSION").read_text().strip()
        if (root / "VERSION").exists()
        else "development",
    }
    (output / "bundle-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (output / "SHA256SUMS").write_text(f"{sha256}  {archive_path.name}\n", encoding="utf-8")
    for name in ("install.sh", "install.ps1"):
        (output / name).write_text(bootstrap_text(root, name, base_url), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    build_release(Path(__file__).resolve().parents[1], args.out, args.base_url)
