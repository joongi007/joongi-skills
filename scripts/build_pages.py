#!/usr/bin/env python3
"""Stage a static Pages site and a verified, source-based installation bundle."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

if __package__:
    from scripts.build_release import bootstrap_text, build_release, public_file  # noqa: F401
    from scripts.build_site_docs import build_docs
else:
    from build_release import bootstrap_text, build_release, public_file  # noqa: F401
    from build_site_docs import build_docs

ROOT = Path(__file__).resolve().parents[1]


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
    build_release(ROOT, output, base_url)
    (output / ".nojekyll").touch()
    print(f"Pages artifact ready: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    build(args.out, args.base_url)
