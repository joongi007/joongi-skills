"""The checker must catch real inconsistencies without rejecting code examples."""

import tempfile
import unittest
from pathlib import Path

from scripts.check_docs import check


class DocumentationChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "docs").mkdir()
        (self.root / "docs/02-scope.md").write_text("| REQ-ONE | behavior |\n", encoding="utf-8")

    def write(self, name, text):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def test_valid_links_and_code_examples(self):
        self.write(
            "docs/00-index.md",
            "[scope](02-scope.md)\n[remote](https://example.com/missing)\n```md\n[sample](not-a-file.md)\n```\n",
        )
        self.assertEqual(check(self.root), [])

    def test_detects_missing_target_and_escape(self):
        self.write("docs/00-index.md", "[missing](gone.md)\n[escape](../../outside.md)\n")
        errors = check(self.root)
        self.assertTrue(any("broken local link" in error for error in errors))
        self.assertTrue(any("escapes repository" in error for error in errors))

    def test_duplicate_ids_and_unknown_requirement(self):
        self.write("docs/one.md", "문서 ID: DOC-SAME · 요구사항: REQ-ONE\n")
        self.write("docs/two.md", "문서 ID: DOC-SAME · 요구사항: REQ-MISSING\n")
        errors = check(self.root)
        self.assertTrue(any("duplicate document ID" in error for error in errors))
        self.assertTrue(any("unknown requirement REQ-MISSING" in error for error in errors))

    def test_route_requires_both_existing_file_and_discovery(self):
        self.write(
            "skills/example/SKILL.md",
            "---\nname: example\ndescription: A specific skill description\n"
            "---\n`references/missing.md`\n",
        )
        self.write("skills/example/references/unrouted.md", "Useful guidance\n")
        errors = check(self.root)
        self.assertTrue(any("missing routed reference" in error for error in errors))
        self.assertTrue(any("unrouted reference" in error for error in errors))

    def test_repository_documents(self):
        self.assertEqual(check(Path(__file__).resolve().parent.parent), [])
