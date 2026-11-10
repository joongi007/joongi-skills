"""The public bundle must not include local state or builder account metadata."""

import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_pages


class PublicationTests(unittest.TestCase):
    def test_bundle_and_site_exclude_private_files_and_account_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            files = {
                "VERSION": "0.1.0",
                "install.sh": "@DOWNLOAD_BASE@",
                "install.ps1": "@DOWNLOAD_BASE@",
                "site/index.html": "public page",
                "skills/demo/SKILL.md": "public skill",
                "skills/demo/.env.example": "DEMO_TOKEN=replace-me",
                "skills/demo/.env": "private environment",
                "skills/demo/.local/credentials.json": "private credential state",
                "skills/demo/.aws/credentials": "private cloud state",
                "skills/demo/key.pem": "private key fixture",
                "site/.env.production": "private environment",
                "site/.codex/auth.json": "private agent state",
                ".local/servers.json": "private registry",
            }
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            output = Path(temp) / "pages"
            with patch.object(build_pages, "ROOT", root):
                build_pages.build(output, "https://example.invalid/hub")
            self.assertTrue((output / "index.html").is_file())
            self.assertFalse((output / ".env.production").exists())
            self.assertFalse((output / ".codex").exists())
            with tarfile.open(output / "joongi-skills.tar.gz") as archive:
                names = archive.getnames()
                self.assertIn("joongi-skills/skills/demo/SKILL.md", names)
                self.assertIn("joongi-skills/skills/demo/.env.example", names)
                self.assertFalse(
                    any("private" in archive.extractfile(n).read().decode() for n in names)
                )
                for info in archive.getmembers():
                    self.assertEqual((info.uid, info.gid, info.uname, info.gname), (0, 0, "", ""))
                    self.assertEqual(info.mtime, 0)
                    self.assertFalse(info.pax_headers)
