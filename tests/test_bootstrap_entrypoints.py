"""Downloaded bootstraps must not select an installer from ambient caller paths."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.build_release import bootstrap_text

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://example.invalid/reviewed-release"


@unittest.skipIf(os.name == "nt", "Bash entrypoints run on POSIX")
class BashBootstrapEntrypoints(unittest.TestCase):
    def test_pipe_and_file_select_remote_but_clone_selects_adjacent_manager(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            caller = folder / "unrelated-project"
            (caller / "scripts").mkdir(parents=True)
            (caller / "scripts/install_manager.py").write_text("untrusted cwd installer")
            capture = folder / "invocation.json"
            python = folder / "capture-python"
            python.write_text(
                "#!/usr/bin/env python3\n"
                "import json,os,sys\n"
                "if '-c' not in sys.argv:\n"
                " data={'args':sys.argv[1:],'stdin':sys.stdin.read() if '-' in sys.argv else ''}\n"
                " open(os.environ['CAPTURE'], 'w').write(json.dumps(data))\n"
            )
            python.chmod(0o700)
            env = dict(os.environ, JOONGI_PYTHON=str(python), CAPTURE=str(capture))
            env.pop("JOONGI_DOWNLOAD_BASE", None)
            source = bootstrap_text(ROOT, "install.sh", BASE)
            script = folder / "install.sh"
            script.write_text(source)
            for mode in ("pipe", "file"):
                command = ["bash", "-s", "--"] if mode == "pipe" else ["bash", str(script)]
                result = subprocess.run(
                    command + ["install", "--dry-run"],
                    input=source if mode == "pipe" else None,
                    cwd=caller,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                invocation = json.loads(capture.read_text())
                self.assertEqual(
                    invocation["args"], ["-I", "-B", "-", BASE, "install", "--dry-run"]
                )
                self.assertIn("verified = verify_download(data, attestation)", invocation["stdin"])
            (folder / "scripts").mkdir()
            manager = folder / "scripts/install_manager.py"
            manager.write_text("reviewed local installer")
            result = subprocess.run(
                ["bash", str(script), "install", "--dry-run"],
                cwd=caller,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(capture.read_text())["args"],
                ["-I", "-B", str(manager), "install", "--dry-run"],
            )


@unittest.skipUnless(os.name == "nt", "Native PowerShell entrypoints run on Windows")
class PowerShellBootstrapEntrypoints(unittest.TestCase):
    def test_inline_scriptblock_does_not_inherit_outer_script_root(self):
        powershell = shutil.which("powershell.exe")
        if not powershell:
            self.skipTest("Windows PowerShell is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "scripts").mkdir()
            (folder / "scripts/install_manager.py").write_text("untrusted outer script installer")
            script = folder / "downloaded.ps1"
            script.write_text(bootstrap_text(ROOT, "install.ps1", BASE), encoding="utf-8")
            capture = folder / "invocation.json"
            runner = folder / "caller.ps1"
            runner.write_text(
                "function Capture-Python {\n"
                " if ($args -contains '-c') { $global:LASTEXITCODE=0; return }\n"
                " $payload=$input | Out-String\n"
                " @{ arguments=@($args); payload=$payload } | ConvertTo-Json -Depth 4 |\n"
                " Set-Content -LiteralPath $env:CAPTURE -Encoding UTF8\n"
                " $global:LASTEXITCODE=if ($env:SIMULATE_INSTALL_FAILURE) { 17 } else { 0 }\n"
                "}\n"
                "$env:JOONGI_PYTHON='Capture-Python'\n"
                "$source=Get-Content -Raw -LiteralPath $env:BOOTSTRAP_SCRIPT\n"
                "& ([scriptblock]::Create($source)) install --dry-run\n"
                "Set-Content -LiteralPath $env:RETURNED -Value continued\n"
                "exit $LASTEXITCODE\n",
                encoding="utf-8",
            )
            returned = folder / "returned.txt"
            env = dict(
                os.environ,
                CAPTURE=str(capture),
                BOOTSTRAP_SCRIPT=str(script),
                RETURNED=str(returned),
            )
            env.pop("JOONGI_DOWNLOAD_BASE", None)
            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(runner),
                ],
                cwd=folder,
                env=env,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            self.assertTrue(returned.exists(), "Inline installation exited the caller PowerShell")
            invocation = json.loads(capture.read_text(encoding="utf-8-sig"))
            self.assertEqual(invocation["arguments"][:4], ["-I", "-B", "-", BASE])
            self.assertEqual(invocation["arguments"][-2:], ["install", "--dry-run"])
            self.assertIn("verified = verify_download(data, attestation)", invocation["payload"])
            returned.unlink()
            env["SIMULATE_INSTALL_FAILURE"] = "1"
            failed = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(runner),
                ],
                cwd=folder,
                env=env,
                capture_output=True,
                timeout=30,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse(returned.exists(), "Failed inline installation continued as success")
