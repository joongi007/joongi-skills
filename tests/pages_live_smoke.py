"""Live deployment smoke: isolated install, stdio, remote update and self-uninstall."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def run(command, input=None):
    environment = dict(os.environ, JOONGI_PYTHON=sys.executable)
    for key in ("JOONGI_DOWNLOAD_BASE", "JOONGI_INSTALL_DOWNLOAD_BASE"):
        environment.pop(key, None)
    r = subprocess.run(
        [str(x) for x in command], input=input, capture_output=True, timeout=180, env=environment
    )
    if r.returncode:
        raise RuntimeError(
            "Command failed: "
            + str(command[0])
            + "\n"
            + r.stderr.decode("utf-8", errors="replace")[-3000:]
        )
    return r.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("PAGES_BASE_URL"))
    args = parser.parse_args()
    if not args.base_url:
        parser.error("Use --base-url or PAGES_BASE_URL")
    BASE = args.base_url.rstrip("/")
    parsed = urlsplit(BASE)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        parser.error("Use a trusted HTTPS deployment URL without credentials or query strings")
    with urllib.request.urlopen(BASE + "/read/docs/00-index.html", timeout=30) as response:
        document = response.read().decode("utf-8")
    assert '<article class="document-body">' in document and "문서 안내" in document
    assert "installation/00-index.html" in document
    architecture_url = BASE + "/read/docs/architecture/01-components.html"
    with urllib.request.urlopen(architecture_url, timeout=30) as response:
        architecture = response.read().decode("utf-8")
    image = re.search(r'<img src="([^"]+diagrams/[a-f0-9]{64}\.svg)"', architecture)
    assert image, "Published architecture page must contain a static Mermaid diagram"
    with urllib.request.urlopen(urljoin(architecture_url, image[1]), timeout=30) as response:
        svg = response.read(2 * 1024**2 + 1).decode("utf-8")
    assert svg.startswith("<svg") and "<script" not in svg.lower()
    assert "data-mermaid-slot" not in architecture
    with tempfile.TemporaryDirectory(prefix="joongi-live-bootstrap-") as directory:
        temp = Path(directory).resolve()
        home = temp / "home with spaces 한글"
        home.mkdir()
        (home / "keep.txt").write_text("user file")
        script_name = "install.ps1" if os.name == "nt" else "install.sh"
        with urllib.request.urlopen(BASE + "/" + script_name, timeout=30) as r:
            script = r.read()
        from scripts.build_pages import bootstrap_text

        expected = bootstrap_text(ROOT, script_name, BASE).encode()
        assert script == expected, "Published bootstrap differs from reviewed source"
        bootstrap = temp / script_name
        bootstrap.write_bytes(script)
        from scripts.verify_release import verify_download

        with urllib.request.urlopen(BASE + "/joongi-skills.sigstore.jsonl", timeout=30) as response:
            attestation = response.read(2 * 1024**2 + 1)
        verify_download(script, attestation)
        if os.name == "nt":
            ps = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            command = [
                ps,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                bootstrap,
            ]
        else:
            command = ["bash", bootstrap]
        run([*command, "install", "--home", home, "--agent", "codex"])
        launcher = home / ".local/bin" / ("joongi-hub.cmd" if os.name == "nt" else "joongi-hub")
        manager = (
            home / ".local/bin" / ("joongi-skills.cmd" if os.name == "nt" else "joongi-skills")
        )
        runtime = home / ".local/share/joongi-skills/runtime"
        assert (runtime / "LICENSE").read_text(encoding="utf-8") == (ROOT / "LICENSE").read_text(
            encoding="utf-8"
        )
        assert (runtime / "joongi_hub/runtime.py").read_text(encoding="utf-8") == (
            ROOT / "joongi_hub/runtime.py"
        ).read_text(encoding="utf-8")
        assert (runtime / "scripts/install_manager.py").read_text(encoding="utf-8") == (
            ROOT / "scripts/install_manager.py"
        ).read_text(encoding="utf-8")
        status = json.loads(run([launcher, "status"]))
        assert status["mode"] == "stdio" and not status["running"], status
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "live-pages-smoke", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "hub_search",
                    "arguments": {"query": "usual-korean", "kind": "skill"},
                },
            },
        ]
        responses = [
            json.loads(line)
            for line in run(
                [launcher, "stdio"], input="".join(json.dumps(x) + "\n" for x in messages).encode()
            ).splitlines()
        ]
        search = next(x for x in responses if x.get("id") == 2)["result"]
        assert not search.get("isError") and "usual-korean" in search["content"][0]["text"]
        manifest = home / ".local/share/joongi-skills/installation.json"
        assert json.loads(manifest.read_text(encoding="utf-8"))["download_base"] == BASE
        (home / ".copilot").mkdir()
        run([manager, "update", "--home", home])
        assert not Path(json.loads(manifest.read_text(encoding="utf-8"))["source"]).exists(), (
            "Update reused a local snapshot"
        )
        assert (home / ".copilot/mcp-config.json").is_file(), (
            "New agent was not registered during remote update"
        )
        assert (runtime / "LICENSE").read_text(encoding="utf-8") == (ROOT / "LICENSE").read_text(
            encoding="utf-8"
        )
        run([manager, "uninstall", "--home", home])
        assert not launcher.exists() and not manager.exists() and not runtime.exists()
        assert (home / "keep.txt").read_text() == "user file"
        assert (home / ".local/share/joongi-hub/tasks.sqlite3").exists(), (
            "Uninstall deleted Hub state"
        )
        record = {
            "os": os.name,
            "url": BASE,
            "bootstrap_sha256": hashlib.sha256(script).hexdigest(),
            "install": True,
            "stdio_search": True,
            "http_running": False,
            "remote_update_new_agent": True,
            "uninstall_preserves_state": True,
            "license_verified": True,
            "rendered_docs": True,
        }
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
