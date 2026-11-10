"""Managed snapshots must preserve project edits, version pins and atomic rollback."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.service import Hub
from scripts.install_manager import Installer, InstallError
from tests.test_projects import skill


class SkillManagement(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        skill(self.source / "skills", "demo", "version one")
        (self.source / "VERSION").write_text("1.0.0")
        self.hub = Hub(self.source / "skills", self.root / "state")
        self.addCleanup(self.hub.close)
        self.home = self.root / "home"
        (self.home / ".codex").mkdir(parents=True)
        self.hub.skill_manager.home = self.home
        self.project_root = self.root / "project"
        self.project_root.mkdir()
        self.hub.projects.put(
            {"id": "project", "root": str(self.project_root), "common_skills": ["demo"]}
        )
        self.project = self.hub.scoped("project")
        self.project.skill_manager.home = self.home

    def install(self, manager):
        plan = manager.plan("install", ["demo"], ["codex"])
        self.assertFalse((self.home / ".agents/skills/demo").exists())
        return manager.apply(plan["id"])

    def test_project_copy_is_pinned_and_common_update_does_not_touch_it(self):
        manager = self.project.skill_manager
        self.install(manager)
        target = self.project_root / ".agents/skills/demo/SKILL.md"
        old = target.read_text()
        skill(self.source / "skills", "demo", "version two")
        plan = manager.plan("update", ["demo"], ["codex"])
        self.assertEqual(plan["actions"][0]["action"], "blocked")
        with self.assertRaises(RpcError):
            manager.apply(plan["id"])
        self.assertEqual(target.read_text(), old)
        lock = json.loads((self.project_root / "joongi-skills.lock.json").read_text())
        self.assertTrue(lock["skills"][0]["pinned"])
        unpin = manager.plan("unpin", ["demo"], ["codex"])
        manager.apply(unpin["id"])
        plan = manager.plan("update", ["demo"], ["codex"])
        manager.apply(plan["id"])
        self.assertIn("version two", target.read_text())

    def test_user_update_reuses_installer_ownership_and_preserves_local_edits(self):
        manager = self.hub.skill_manager
        self.install(manager)
        target = self.home / ".agents/skills/demo/SKILL.md"
        target.write_text(target.read_text() + "local edit")
        plan = manager.plan("update", ["demo"], ["codex"])
        self.assertEqual(plan["actions"][0]["action"], "blocked")
        with self.assertRaises(RpcError):
            manager.apply(plan["id"])
        self.assertIn("local edit", target.read_text())

    def test_target_or_snapshot_changes_and_replayed_plans_are_rejected(self):
        manager = self.hub.skill_manager
        plan = manager.plan("install", ["demo"], ["codex"])
        private = manager.directory / "plans" / plan["id"] / "source/skills/demo/SKILL.md"
        private.write_text("tampered")
        with self.assertRaises(RpcError):
            manager.apply(plan["id"])
        plan = manager.plan("install", ["demo"], ["codex"])
        manager.apply(plan["id"])
        with self.assertRaises(RpcError):
            manager.apply(plan["id"])

    def test_foreign_skills_and_unselected_common_skills_are_not_installable(self):
        skill(self.project_root / ".agents/skills", "demo", "project author")
        plan = self.project.skill_manager.plan("install", ["demo"], ["codex"])
        self.assertEqual(plan["actions"][0]["action"], "blocked")
        self.hub.projects.put({"id": "empty", "root": str(self.project_root)})
        with self.assertRaises(RpcError):
            self.hub.scoped("empty").skill_manager.plan("install", ["demo"], ["codex"])

    def test_installer_also_honors_pins_and_failed_apply_rolls_back(self):
        manager = self.hub.skill_manager
        self.install(manager)
        pin = manager.plan("pin", ["demo"], ["codex"])
        manager.apply(pin["id"])
        skill(self.source / "skills", "demo", "version two")
        installer = Installer(self.home, self.source)
        with self.assertRaises(InstallError):
            installer._stage(self.home / ".agents/skills/demo", self.source / "skills/demo", "tree")
        unpin = manager.plan("unpin", ["demo"], ["codex"])
        manager.apply(unpin["id"])
        plan = manager.plan("update", ["demo"], ["codex"])
        target = self.home / ".agents/skills/demo/SKILL.md"
        before = target.read_bytes()
        with patch("scripts.install_manager.shutil.copytree", side_effect=OSError("disk error")):
            with self.assertRaises(RpcError):
                manager.apply(plan["id"])
        self.assertEqual(target.read_bytes(), before)

    def test_retired_source_skill_can_be_removed_without_touching_lock_unrelated_entries(self):
        self.install(self.project.skill_manager)
        shutil.rmtree(self.source / "skills/demo")
        manager = self.project.skill_manager
        plan = manager.plan("remove", ["demo"], ["codex"])
        manager.apply(plan["id"])
        self.assertFalse((self.project_root / ".agents/skills/demo").exists())
        self.assertEqual(
            json.loads((self.project_root / "joongi-skills.lock.json").read_text())["skills"], []
        )

    def test_project_lockfile_failure_rolls_back_installed_tree(self):
        manager = self.project.skill_manager
        (self.project_root / "joongi-skills.lock.json").write_text("user-owned lock")
        plan = manager.plan("install", ["demo"], ["codex"])
        with self.assertRaises(RpcError):
            manager.apply(plan["id"])
        self.assertFalse((self.project_root / ".agents/skills/demo").exists())
        self.assertEqual(
            (self.project_root / "joongi-skills.lock.json").read_text(), "user-owned lock"
        )

    def test_scope_cannot_apply_other_project_plan(self):
        plan = self.project.skill_manager.plan("install", ["demo"], ["codex"])
        with self.assertRaises(RpcError):
            self.hub.skill_manager.apply(plan["id"])


if __name__ == "__main__":
    unittest.main()
