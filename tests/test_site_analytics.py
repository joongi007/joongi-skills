"""Production tagging is isolated from previews, local Hub and Markdown content."""

import base64
import hashlib
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from scripts.build_pages import build, public_file
from scripts.build_site_docs import build_docs
from scripts.site_analytics import enabled


class Tags(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.scripts = []
        self.csp = ""
        self.current = None
        self.feed(page)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "script":
            self.current = {"attributes": attrs, "text": ""}
            self.scripts.append(self.current)
        if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy":
            self.csp = attrs["content"]

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "script":
            self.current = None


class SiteAnalytics(unittest.TestCase):
    def test_only_the_exact_public_site_enables_tracking(self):
        self.assertTrue(enabled("https://joongi007.github.io/joongi-skills/"))
        for value in (
            "https://example.invalid/joongi-skills",
            "http://localhost:8765",
            "https://joongi007.github.io/another-project",
            "https://joongi007.github.io.evil.example/joongi-skills",
            "https://joongi007.github.io/joongi-skills?preview=1",
        ):
            self.assertFalse(enabled(value), value)

    def test_public_document_allows_only_hashed_initialization_and_google_script(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            (root / "README.md").write_text(
                "# Safe\n<script>window.injected=1</script>\n", encoding="utf-8"
            )
            output = Path(directory) / "out"
            build_docs(root, output, public_file, analytics=True)
            page = Tags((output / "read/README.html").read_text(encoding="utf-8"))
            self.assertEqual(len(page.scripts), 2)
            self.assertEqual(
                page.scripts[0]["attributes"]["src"],
                "https://www.googletagmanager.com/gtm.js?id=GTM-MCHLMHRF",
            )
            self.assertIn("async", page.scripts[0]["attributes"])
            inline = page.scripts[1]["text"]
            self.assertNotIn("window.injected", inline)
            self.assertIn("gtag('js', new Date());", inline)
            expected = base64.b64encode(hashlib.sha256(inline.encode()).digest()).decode()
            self.assertIn("'sha256-" + expected + "'", page.csp)
            self.assertIn("default-src 'none'", page.csp)
            self.assertIn("script-src-attr 'none'", page.csp)
            self.assertNotIn("unsafe-inline", page.csp)
            self.assertNotIn("unsafe-eval", page.csp)

    def test_real_public_build_tags_home_and_every_document_but_not_local_hub(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pages"
            build(output, "https://joongi007.github.io/joongi-skills")
            home = Tags((output / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(
                sum("GTM-MCHLMHRF" in s["attributes"].get("src", "") for s in home.scripts), 1
            )
            guide = Tags((output / "guide.html").read_text(encoding="utf-8"))
            self.assertEqual(len(guide.scripts), 2)
            self.assertIn("script-src-attr 'none'", guide.csp)
            self.assertNotIn("unsafe-inline", guide.csp)
            documents = list((output / "read").rglob("*.html"))
            self.assertGreater(len(documents), 40)
            for document in documents:
                self.assertEqual(
                    len(Tags(document.read_text(encoding="utf-8")).scripts), 2, str(document)
                )
            root = Path(__file__).resolve().parents[1]
            for file in (root / "joongi_hub/static").rglob("*"):
                if file.is_file():
                    self.assertNotIn(b"GTM-MCHLMHRF", file.read_bytes(), str(file))
