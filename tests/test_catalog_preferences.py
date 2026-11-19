"""Discovery choices must be scoped, durable, explicit and recoverable."""

import json
import tempfile
import unittest
from pathlib import Path

from joongi_hub.catalog_preferences import CatalogPreferences, builtin_categories
from joongi_hub.errors import RpcError


class CatalogPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.preferences = CatalogPreferences(self.root / "state")
        self.company = self.root / "company-skills"
        self.company.mkdir()

    def source(self, **values):
        return {"id": "company", "name": "Company", "path": str(self.company), **values}

    def test_defaults_are_lazy_independent_and_copy_safe(self):
        initial = self.preferences.get()
        self.assertEqual(initial["exposure"], "search-first")
        self.assertFalse(initial["usage_enabled"])
        self.assertFalse((self.root / "state").exists())
        initial["disabled"]["skill"].append("usual-korean")
        self.assertTrue(self.preferences.allows("skill", "usual-korean"))

    def test_partial_updates_preserve_other_choices_and_new_instances_observe_them(self):
        self.preferences.update(self.preferences.get())
        first = self.preferences.update({"disabled": {"skill": ["usual-korean"]}})
        self.assertFalse(first["usage_enabled"])
        second = CatalogPreferences(self.root / "state")
        second.update({"disabled": {"server": ["notion"]}, "usage_enabled": True})
        self.assertFalse(self.preferences.allows("skill", "usual-korean"))
        self.assertFalse(self.preferences.allows("tool", "notion__fetch", server="notion"))
        self.assertTrue(self.preferences.get()["usage_enabled"])
        other = CatalogPreferences(self.root / "another-profile")
        self.assertTrue(other.allows("skill", "usual-korean"))

    def test_categories_sources_and_item_switches_compose_and_reset(self):
        self.preferences.update({"sources": [self.source(category="design")]})
        self.preferences.update({"disabled": {"category": ["design"]}})
        self.assertFalse(self.preferences.allows("skill", "applying-design-systems"))
        self.assertFalse(self.preferences.allows("skill", "company__identity", source="company"))
        self.assertTrue(self.preferences.allows("skill", "usual-korean"))
        self.preferences.update({"category_overrides": {"skill:applying-design-systems": []}})
        self.assertTrue(self.preferences.allows("skill", "applying-design-systems"))
        self.preferences.update({"disabled": {"source": ["company"]}})
        self.assertFalse(self.preferences.allows("skill", "company__identity", source="company"))
        self.preferences.update({"disabled": {"category": ["tools"]}})
        self.assertFalse(
            self.preferences.allows("skill", "remote__guide", server="remote", source="remote")
        )
        self.preferences.update({"category_overrides": {"server:remote": ["design"]}})
        self.assertTrue(
            self.preferences.allows("tool", "remote__fetch", server="remote", categories=["design"])
        )
        self.preferences.reset()
        self.assertTrue(self.preferences.allows("skill", "applying-design-systems"))
        self.assertEqual(self.preferences.sources(), [])
        self.assertEqual(self.preferences.get()["disabled"]["category"], [])

    def test_sources_are_namespaced_metadata_and_do_not_rewrite_their_files(self):
        instruction = self.company / "custom-skill/SKILL.md"
        instruction.parent.mkdir()
        instruction.write_text("company-owned instructions")
        self.preferences.update({"sources": [self.source(enabled=False)]})
        self.assertFalse(
            self.preferences.allows("skill", "company__custom-skill", source="company")
        )
        self.assertEqual(instruction.read_text(), "company-owned instructions")
        self.assertEqual(
            self.preferences.categories("skill", "company__custom-skill", "company"), []
        )
        self.preferences.update({"sources": [self.source(enabled=True)]})
        self.assertTrue(self.preferences.allows("skill", "company__custom-skill", source="company"))
        self.assertEqual(
            builtin_categories("engineering-playbook"), ["development", "documentation"]
        )
        self.assertEqual(self.preferences.categories("server", "notion"), ["tools"])

    def test_invalid_update_cannot_partly_enable_an_excluded_item(self):
        self.preferences.update({"disabled": {"skill": ["usual-korean"]}})
        before = self.preferences.path.read_bytes()
        invalid = [
            {"exposure": "surprise"},
            {"schema": 2},
            {"disabled": {"skill": []}, "usage_enabled": "true"},
            {"disabled": {"skill": ["../../secret"]}},
            {"disabled": {"category": ["design", "design"]}},
            {"category_overrides": {"path:/private/secret": ["design"]}},
            {"sources": [self.source(id="builtin")]},
            {"sources": [self.source(path="relative/path")]},
            {"sources": [self.source(path=str(self.root / "missing"))]},
            {"sources": [self.source(), self.source()]},
        ]
        for patch in invalid:
            with self.subTest(patch=patch), self.assertRaises(RpcError):
                self.preferences.update(patch)
            self.assertEqual(self.preferences.path.read_bytes(), before)

    def test_deleted_source_can_be_disabled_without_losing_settings(self):
        self.preferences.update({"sources": [self.source()]})
        self.company.rmdir()
        self.assertEqual(self.preferences.sources()[0]["id"], "company")
        self.preferences.update({"usage_enabled": True})
        self.preferences.update({"sources": [self.source(enabled=False)]})
        self.assertFalse(self.preferences.allows("skill", "company__item", source="company"))

    def test_corrupt_unknown_duplicate_and_oversized_settings_fail_closed(self):
        self.preferences.update({})
        for data in [b"{", b'{"schema":1,"schema":1}', b"x" * (256 * 1024 + 1)]:
            self.preferences.path.write_bytes(data)
            with self.assertRaises(RpcError):
                self.preferences.get()
            with self.assertRaises(RpcError):
                self.preferences.allows("skill", "usual-korean")
            self.preferences.reset()
            self.assertTrue(self.preferences.allows("skill", "usual-korean"))
        value = self.preferences.get()
        value["unreviewed_behavior"] = True
        self.preferences.path.write_text(json.dumps(value))
        with self.assertRaises(RpcError):
            self.preferences.get()

    def test_symlinked_settings_and_sources_are_never_followed(self):
        target = self.root / "keep.json"
        target.write_text("keep")
        self.preferences.directory.mkdir()
        try:
            self.preferences.path.symlink_to(target)
        except OSError:
            self.skipTest("Symlink creation is unavailable")
        for operation in (self.preferences.get, self.preferences.reset):
            with self.assertRaises(RpcError):
                operation()
        self.assertEqual(target.read_text(), "keep")
        self.preferences.path.unlink()
        alias = self.root / "alias"
        alias.symlink_to(self.company, target_is_directory=True)
        with self.assertRaises(RpcError):
            self.preferences.update({"sources": [self.source(path=str(alias))]})
