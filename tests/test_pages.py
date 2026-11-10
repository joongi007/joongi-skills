"""The downloadable bundle must contain the actual runtime and a usable bootstrap."""

import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.build_pages import build
from scripts.install_manager import download_bundle


class PagesTests(unittest.TestCase):
    def test_build_bakes_url_and_download_extracts_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "pages"
            build(output, "https://example.invalid/project")
            self.assertTrue((output / "index.html").is_file())
            self.assertNotIn("@DOWNLOAD_BASE@", (output / "install.sh").read_text())
            self.assertIn("https://example.invalid/project", (output / "install.sh").read_text())
            manifest = (output / "bundle-manifest.json").read_bytes()
            archive = (output / "joongi-skills.tar.gz").read_bytes()
            with patch(
                "urllib.request.urlopen", side_effect=[io.BytesIO(manifest), io.BytesIO(archive)]
            ):
                source = download_bundle("https://example.invalid/project", root / "download")
            self.assertTrue((source / "scripts/install_manager.py").is_file())
            self.assertTrue((source / "scripts/check_docs.py").is_file())
            self.assertTrue((source / "tests/fixtures/mcp_server.py").is_file())
            self.assertTrue((source / "build.sh").is_file())
            self.assertTrue((source / "skills/engineering-playbook/SKILL.md").is_file())
            self.assertTrue((source / "skills/usual-korean/SKILL.md").is_file())
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
                self.assertFalse(any("__pycache__" in name for name in bundle.getnames()))
                self.assertFalse(any(".local" in Path(name).parts for name in bundle.getnames()))
            self.assertEqual(json.loads(manifest)["archive"], "joongi-skills.tar.gz")

    def test_build_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                build(Path(temporary), "https://example.invalid/project")


if __name__ == "__main__":
    unittest.main()
