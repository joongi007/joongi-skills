"""Reproduce native Windows HTTPS bootstrap testing from WSL without a public deployment.

Requires Windows PowerShell/Python, WSL interop, and openssl. The self-signed TLS
certificate and installation home exist only in a temporary checkout directory.
The child process trusts that certificate via SSL_CERT_FILE; no trust store or
global PowerShell policy is changed.
"""

import functools
import http.server
import ssl
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_pages import build  # noqa: E402

POWERSHELL = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
WINDOWS_TEST = """
$ErrorActionPreference = 'Stop'
$env:SSL_CERT_FILE = '@@CERT@@'
$testHome = '@@ROOT@@\\home'
$bootstrap = '@@ROOT@@\\remote-install.ps1'
$installArgs = @('--home', $testHome, '--agent', 'copilot')
& $bootstrap -Action install -DownloadBase '@@URL@@' -InstallArgs $installArgs
if ($LASTEXITCODE -ne 0) { throw 'Remote bootstrap failed' }
if (-not (Test-Path (Join-Path $testHome '.copilot/mcp-config.json'))) {
    throw 'Remote MCP absent'
}
& $bootstrap -Action uninstall -DownloadBase '@@URL@@' -InstallArgs @('--home', $testHome)
if ($LASTEXITCODE -ne 0) { throw 'Remote uninstall failed' }
if (Test-Path (Join-Path $testHome '.local/bin/joongi-hub.cmd')) {
    throw 'Runtime survived uninstall'
}
Write-Output 'Windows HTTPS bootstrap passed: download, hash, extraction, install, uninstall.'
"""


def main():
    if not POWERSHELL.is_file():
        raise SystemExit("Run this integration check from WSL with Windows PowerShell installed.")
    with tempfile.TemporaryDirectory(prefix=".test-windows-remote-", dir=ROOT) as temporary:
        directory = Path(temporary)
        cert, key = directory / "cert.pem", directory / "key.pem"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=IP:127.0.0.1,DNS:localhost",
            ],
            check=True,
            capture_output=True,
        )
        output = directory / "pages"
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=output)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        url = f"https://127.0.0.1:{server.server_port}"
        build(output, url)
        (directory / "remote-install.ps1").write_bytes((output / "install.ps1").read_bytes())
        windows_root = subprocess.check_output(["wslpath", "-w", str(directory)], text=True).strip()
        runner = (
            WINDOWS_TEST.replace("@@CERT@@", windows_root + "\\cert.pem")
            .replace("@@ROOT@@", windows_root)
            .replace("@@URL@@", url)
        )
        (directory / "run.ps1").write_text(runner, encoding="utf-8")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    str(POWERSHELL),
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    windows_root + "\\run.ps1",
                ],
                timeout=60,
                capture_output=True,
            )
            print(result.stdout.decode("utf-8", errors="replace"))
            if result.stderr:
                print(result.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
            return result.returncode
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
