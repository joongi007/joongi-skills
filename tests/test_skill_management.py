"""Managed snapshots must preserve project edits, version pins and atomic rollback."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.service import Hub
from scripts.install_manager import Installer, InstallError, tree_files
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

    def test_project_manifest_cannot_claim_company_skill_ownership(self):
        target = self.project_root / ".agents/skills/demo"
        skill(target.parent, "demo", "company-owned")
        legacy = self.project_root / ".joongi/private/installation.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "entries": {
                        ".agents/skills/demo": {"kind": "tree", "files": tree_files(target)}
                    },
                }
            )
        )
        # Even a malformed user-installer manifest inside the checkout must not
        # be loaded before the separate project ownership store is selected.
        decoy = self.project_root / ".local/share/joongi-skills/installation.json"
        decoy.parent.mkdir(parents=True)
        decoy.write_text("untrusted checkout metadata")
        before = tree_files(target)
        manager = self.project.skill_manager
        for operation in ("install", "update", "remove"):
            plan = manager.plan(operation, ["demo"], ["codex"])
            self.assertEqual(plan["actions"][0]["action"], "blocked")
            with self.assertRaises(RpcError):
                manager.apply(plan["id"])
            self.assertEqual(tree_files(target), before)
        self.assertFalse(manager._installer().state.is_relative_to(self.project_root))
        self.assertFalse(manager._installer().manifest["entries"])

    def test_trusted_project_ownership_survives_restart_and_ignores_checkout_metadata(self):
        manager = self.project.skill_manager
        self.install(manager)
        manifest = manager._installer().manifest_path
        self.assertTrue(manifest.is_relative_to(self.project.state_dir))
        self.assertFalse((self.project_root / ".joongi/private").exists())
        legacy = self.project_root / ".joongi/private/installation.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("not a trusted ownership record")
        from joongi_hub.skill_management import SkillManager

        restored = SkillManager(self.project, self.home)
        self.assertEqual(restored.status()["installed"][0]["name"], "demo")
        plan = restored.plan("remove", ["demo"], ["codex"])
        restored.apply(plan["id"])
        self.assertFalse((self.project_root / ".agents/skills/demo").exists())
        self.assertEqual(legacy.read_text(), "not a trusted ownership record")

    def test_upstream_cannot_be_granted_write_access_to_project_ownership(self):
        from joongi_hub.sandbox import _grant

        state = self.project.skill_manager._installer().state
        state.mkdir(parents=True)
        with self.assertRaises(RpcError):
            _grant(str(state), write=True, state=self.project.state_dir)

    def test_external_state_cannot_be_redirected_into_checkout_or_outside_state(self):
        with self.assertRaises(InstallError):
            Installer(self.project_root, self.source, state_dir=self.project_root / "private")
        installer = self.project.skill_manager._installer()
        with self.assertRaises(InstallError):
            installer._check_state_path(installer.state.parent / "foreign.json")
        with self.assertRaises(InstallError):
            installer._stage(self.root / "outside-project", b"no", "file")

    def test_mcp_skill_status_omits_paths_but_local_management_preserves_them(self):
        manager = self.project.skill_manager
        self.install(manager)
        for owner in (False, True):
            for name, args in (
                ("hub_skills_status", {}),
                ("hub_call", {"name": "hub_skills_status", "arguments": {}}),
            ):
                response = self.project.invoke(name, args, local_owner=owner)
                data = json.loads(response["content"][0]["text"])
                self.assertNotIn("source", data)
                self.assertNotIn("path", data["installed"][0])
                self.assertNotIn(str(self.root), json.dumps(data))
                self.assertEqual(data["installed"][0]["name"], "demo")
        self.assertIn("path", manager.status()["installed"][0])
        self.assertIn("source", manager.status())

    def test_scope_cannot_apply_other_project_plan(self):
        plan = self.project.skill_manager.plan("install", ["demo"], ["codex"])
        with self.assertRaises(RpcError):
            self.hub.skill_manager.apply(plan["id"])


if __name__ == "__main__":
    unittest.main()
