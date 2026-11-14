#!/usr/bin/env bash
# Joongi Skills bootstrap. Download, inspect, then run with bash install.sh install.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${JOONGI_PYTHON:-python3}"
DOWNLOAD_BASE="${JOONGI_DOWNLOAD_BASE:-@DOWNLOAD_BASE@}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  printf '%s\n' 'Python 3.10+ is required. Set JOONGI_PYTHON to its executable.' >&2
  exit 1
fi
if ! "$PYTHON" -I -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
  printf '%s\n' 'Python 3.10+ is required. Set JOONGI_PYTHON to a supported executable.' >&2
  exit 1
fi
if [[ -f "$SCRIPT_DIR/scripts/install_manager.py" ]]; then
  exec "$PYTHON" -I -B "$SCRIPT_DIR/scripts/install_manager.py" "$@"
fi
if [[ "$DOWNLOAD_BASE" == @* || -z "$DOWNLOAD_BASE" ]]; then
  printf '%s\n' 'Set JOONGI_DOWNLOAD_BASE=https://OWNER.github.io/REPOSITORY, or run install.sh from a clone.' >&2
  exit 1
fi
exec "$PYTHON" -I -B - "$DOWNLOAD_BASE" "$@" <<'PY'
import hashlib
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required")
base = sys.argv[1].rstrip("/") + "/"
if not base.startswith("https://"):
    raise SystemExit("Download base must use HTTPS")
with urllib.request.urlopen(base + "bundle-manifest.json", timeout=30) as response:
    manifest = json.loads(response.read(65536))
with urllib.request.urlopen(base + "joongi-skills.tar.gz", timeout=60) as response:
    data = response.read(32 * 1024**2 + 1)
if len(data) > 32 * 1024**2 or hashlib.sha256(data).hexdigest() != manifest.get("sha256"):
    raise SystemExit("Bundle size or SHA256 check failed")
# @ATTESTATION_VERIFIER@
with urllib.request.urlopen(base + "joongi-skills.sigstore.jsonl", timeout=30) as response:
    attestation = response.read(2 * 1024**2 + 1)
verified = verify_download(data, attestation)
if manifest.get("revision") != verified["revision"]:
    raise SystemExit("Bundle source revision does not match its signature")
with tempfile.TemporaryDirectory(prefix="joongi-bootstrap-") as temporary:
    target = Path(temporary).resolve()
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
        unpacked = compressed.read(144 * 1024**2 + 1)
    if len(unpacked) > 144 * 1024**2:
        raise SystemExit("Archive decompression limit exceeded")
    with tarfile.open(fileobj=io.BytesIO(unpacked), mode="r:") as archive:
        members, total_size = [], 0
        for member in archive:
            members.append(member)
            total_size += member.size
            if len(members) > 10000 or total_size > 128 * 1024**2:
                raise SystemExit("Archive extraction limit exceeded")
        for member in members:
            output = target / member.name
            if (not output.resolve().is_relative_to(target)
                    or not (member.isfile() or member.isdir())
                    or member.issym() or member.islnk()):
                raise SystemExit("Unsafe archive member")
        for member in members:
            output = target / member.name
            if member.isdir():
                output.mkdir(parents=True, exist_ok=True)
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source:
                    output.write_bytes(source.read())
    manager = target / "joongi-skills/scripts/install_manager.py"
    if not manager.is_file():
        raise SystemExit("Bundle has no installer")
    environment = dict(os.environ, JOONGI_INSTALL_DOWNLOAD_BASE=base.rstrip("/"))
    raise SystemExit(subprocess.call([sys.executable, "-I", "-B", str(manager), *sys.argv[2:]], env=environment))
PY
