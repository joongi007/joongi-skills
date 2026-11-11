"""Static documentation must remain navigable and inert without JavaScript."""

import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from scripts.build_pages import ROOT, public_file
from scripts.build_site_docs import build_docs


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = set()
        self.links = []
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        self.tags.append(tag)
        if "id" in attrs:
            if attrs["id"] in self.ids:
                raise AssertionError("Duplicate heading id: " + attrs["id"])
            self.ids.add(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])


class SiteDocsTests(unittest.TestCase):
    def test_render_links_tables_code_and_unsafe_markup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            docs = root / "docs"
            docs.mkdir(parents=True)
            (root / "README.md").write_text(
                "# 시작\n[문서](docs/00-index.md#한글-제목)\n", encoding="utf-8"
            )
            (docs / "00-index.md").write_text(
                "# 안내\n<!-- contract: hidden -->\n## 한글 제목\n## 한글 제목\n"
                "| 열 | 값 |\n| --- | --- |\n| a | b |\n"
                "```html\n<script>example</script>\n```\n"
                "<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n"
                "[처음](../README.md)\n[파일](../LICENSE)\n",
                encoding="utf-8",
            )
            output = Path(directory) / "output"
            self.assertEqual(build_docs(root, output, public_file), 2)
            page = (output / "read/docs/00-index.html").read_text(encoding="utf-8")
            parsed = Links(page)
            self.assertNotIn("script", parsed.tags)
            self.assertNotIn('href="javascript:', page)
            self.assertNotIn("contract: hidden", page)
            self.assertIn("&lt;script&gt;example&lt;/script&gt;", page)
            self.assertIn("table", parsed.tags)
            self.assertIn("section-한글-제목", parsed.ids)
            self.assertIn("section-한글-제목-1", parsed.ids)
            self.assertIn("../README.html", parsed.links)
            self.assertIn(
                "https://github.com/joongi007/joongi-skills/blob/main/LICENSE", parsed.links
            )
            readme = (output / "read/README.html").read_text(encoding="utf-8")
            self.assertIn("docs/00-index.html#section-한글-제목", readme)

    def test_real_document_links_and_fragments_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            count = build_docs(ROOT, output, public_file)
            self.assertGreater(count, 40)
            pages = {
                p.resolve(): Links(p.read_text(encoding="utf-8")) for p in output.rglob("*.html")
            }
            for path, parsed in pages.items():
                for href in parsed.links:
                    url = urlsplit(href)
                    if url.scheme or url.netloc:
                        continue
                    target = (path.parent / unquote(url.path)).resolve() if url.path else path
                    if target in pages:
                        if url.fragment:
                            self.assertIn(unquote(url.fragment), pages[target].ids, (path, href))
                    else:
                        self.assertEqual(target, (output / "index.html").resolve(), (path, href))

    def test_private_markdown_and_symlinks_are_not_rendered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            for name in ["docs/00-index.md", "docs/.local/private.md", "docs/.aws/private.md"]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# " + name, encoding="utf-8")
            try:
                (root / "docs/alias").symlink_to(root / "docs/.local", target_is_directory=True)
            except OSError:
                pass
            output = Path(directory) / "out"
            self.assertEqual(build_docs(root, output, public_file), 1)
            self.assertEqual(len(list(output.rglob("*.html"))), 1)
