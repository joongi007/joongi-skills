"""Observable persistence, ownership and state-machine contracts for mutation analysis."""

import json
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.storage import Registry, TaskStore, atomic_json, timestamp


class StorageContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_missing_primary_with_backup_requires_explicit_recovery(self):
        registry = Registry(self.root)
        registry.put({"id": "one"})
        registry.path.unlink()
        before = registry.backup.read_bytes()
        with self.assertRaises(RpcError) as error:
            registry.list()
        self.assertEqual(error.exception.code, -32041)
        self.assertFalse(registry.path.exists())
        self.assertEqual(registry.backup.read_bytes(), before)

    def test_corrupt_registry_and_invalid_entry_shapes_are_rejected(self):
        registry = Registry(self.root)
        for text in ("bad json", "{}", "[null]", "[{}]", '[{"id": 3}]'):
            with self.subTest(text=text):
                registry.path.write_text(text, encoding="utf-8")
                with self.assertRaises(RpcError) as error:
                    registry.list()
                self.assertEqual(error.exception.code, -32041)

    def test_registry_accepts_size_boundary_and_rejects_one_byte_over(self):
        registry = Registry(self.root)
        limit = 4 * 1024**2
        registry.path.write_bytes(b"[]" + b" " * (limit - 2))
        self.assertEqual(registry.list(), [])
        registry.path.write_bytes(b"[]" + b" " * (limit - 1))
        with self.assertRaises(RpcError) as error:
            registry.list()
        self.assertEqual(error.exception.code, -32041)

    def test_large_ascii_and_korean_records_survive_save_and_reload(self):
        # The first record fits with four bytes to spare; escaping Korean doubles its bytes.
        for payload in ("x" * (4 * 1024**2 - 50), "한" * 800000):
            with self.subTest(language="ascii" if payload[0] == "x" else "korean"):
                registry = Registry(self.root)
                server = {"id": "one", "payload": payload}
                registry.put(server)
                self.assertLessEqual(registry.path.stat().st_size, 4 * 1024**2)
                self.assertEqual(Registry(self.root).list(), [server])

    @unittest.skipIf(os.name == "nt", "POSIX symlink permissions")
    def test_registry_rejects_primary_symlink_without_reading_target(self):
        registry = Registry(self.root)
        target = self.root / "external.json"
        target.write_text('[{"id":"external"}]')
        registry.path.symlink_to(target)
        with self.assertRaises(RpcError) as error:
            registry.list()
        self.assertEqual(error.exception.code, -32041)
        self.assertEqual(target.read_text(), '[{"id":"external"}]')

    @unittest.skipIf(os.name == "nt", "POSIX symlink permissions")
    def test_registry_rejects_backup_file_or_parent_symlink_without_writing_target(self):
        registry = Registry(self.root)
        external = self.root / "external"
        external.mkdir()
        target = external / "servers.json"
        target.write_text('[{"id":"external"}]')
        for parent_link in (False, True):
            with self.subTest(parent_link=parent_link):
                if parent_link:
                    registry.backup.parent.symlink_to(external, target_is_directory=True)
                else:
                    registry.backup.parent.mkdir()
                    registry.backup.symlink_to(target)
                with registry.lock, self.assertRaises(RpcError) as error:
                    registry.save([{"id": "replacement"}])
                self.assertEqual(error.exception.code, -32041)
                self.assertFalse(registry.path.exists())
                self.assertEqual(target.read_text(), '[{"id":"external"}]')
                if parent_link:
                    registry.backup.parent.unlink()
                else:
                    registry.backup.unlink()
                    registry.backup.parent.rmdir()

    def test_registry_replaces_only_matching_id_and_persists(self):
        registry = Registry(self.root)
        self.assertEqual(registry.list(), [])
        registry.put({"id": "one", "value": 1})
        registry.put({"id": "two", "value": 2})
        registry.put({"id": "one", "value": 3})
        self.assertEqual(
            Registry(self.root).list(), [{"id": "two", "value": 2}, {"id": "one", "value": 3}]
        )
        registry.delete("one")
        self.assertEqual(registry.list(), [{"id": "two", "value": 2}])
        with self.assertRaises(RpcError) as error:
            registry.delete("absent")
        self.assertEqual(error.exception.code, -32602)
        self.assertEqual(registry.list(), [{"id": "two", "value": 2}])

    def test_tasks_creation_owner_filter_lookup_and_unknown_owner(self):
        directory = self.root / "private/nested"
        store = TaskStore(directory)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(store.path.stat().st_mode), 0o600)
        with store.connection() as database:
            self.assertEqual(database.execute("PRAGMA busy_timeout").fetchone()[0], 10000)
        one = store.create("first", "alice")
        two = store.create("second", "bob")
        self.assertNotEqual(one["taskId"], two["taskId"])
        self.assertEqual(one["status"], "working")
        self.assertEqual(one["executorPid"], os.getpid())
        self.assertEqual(one["ttlMs"], 86400000)
        self.assertEqual(one["pollIntervalMs"], 500)
        self.assertTrue(one["createdAt"].endswith("Z"))
        self.assertEqual([item["taskId"] for item in store.list()], [two["taskId"], one["taskId"]])
        self.assertEqual(store.list("alice"), [one])
        self.assertEqual(store.list("bob"), [two])
        self.assertEqual(store.list("nobody"), [])
        self.assertEqual(store.get(one["taskId"]), one)
        self.assertEqual(store.get(one["taskId"], "alice"), one)
        for task_id, owner in [(one["taskId"], "bob"), ("absent", "alice")]:
            with self.subTest(task_id=task_id, owner=owner), self.assertRaises(RpcError) as error:
                store.get(task_id, owner)
            self.assertEqual(error.exception.code, -32602)

    def test_every_terminal_state_is_immutable_and_active_state_can_change(self):
        store = TaskStore(self.root)
        for terminal in ("completed", "failed", "cancelled"):
            with self.subTest(state=terminal):
                task = store.create("operation", "alice")
                updated = store.update(
                    task["taskId"], status="input_required", statusMessage="wait"
                )
                self.assertEqual(updated["status"], "input_required")
                self.assertEqual(updated["statusMessage"], "wait")
                completed = store.update(task["taskId"], status=terminal, result={"value": 7})
                self.assertEqual(completed["status"], terminal)
                self.assertEqual(completed["result"], {"value": 7})
                self.assertEqual(
                    store.update(task["taskId"], status="working", result={}), completed
                )
                self.assertEqual(store.get(task["taskId"]), completed)

    def test_database_context_closes_on_success_and_on_failure_and_rolls_back(self):
        store = TaskStore(self.root)
        with store.connection() as committed:
            committed.execute("CREATE TABLE events (name TEXT)")
            committed.execute("INSERT INTO events VALUES ('committed')")
        with self.assertRaises(sqlite3.ProgrammingError):
            committed.execute("SELECT 1")
        with self.assertRaisesRegex(RuntimeError, "abort transaction"):
            with store.connection() as aborted:
                aborted.execute("INSERT INTO events VALUES ('rolled_back')")
                raise RuntimeError("abort transaction")
        with self.assertRaises(sqlite3.ProgrammingError):
            aborted.execute("SELECT 1")
        with store.connection() as reopened:
            self.assertEqual(
                reopened.execute("SELECT name FROM events").fetchall(), [("committed",)]
            )
        # Windows refuses this unlink if any task connection still holds the DB open.
        store.path.unlink()
        self.assertFalse(store.path.exists())

    def test_recovery_checks_only_active_tasks_and_preserves_live_execution(self):
        store = TaskStore(self.root)
        interrupted = [store.create("interrupted", "alice") for _ in range(2)]
        store.update(interrupted[1]["taskId"], status="input_required")
        terminal = store.create("done", "alice")
        store.update(terminal["taskId"], status="completed")
        with patch("joongi_hub.storage.process_alive", return_value=True):
            live_store = TaskStore(self.root)
        self.assertEqual(live_store.get(interrupted[0]["taskId"])["status"], "working")
        self.assertEqual(live_store.get(interrupted[1]["taskId"])["status"], "input_required")
        with patch("joongi_hub.storage.process_alive", return_value=False):
            recovered = TaskStore(self.root)
        for task in interrupted:
            value = recovered.get(task["taskId"])
            self.assertEqual(value["status"], "failed")
            self.assertEqual(value["error"]["code"], -32603)
        self.assertEqual(recovered.get(terminal["taskId"])["status"], "completed")

    def test_atomic_json_replaces_unicode_and_restricts_permissions(self):
        path = self.root / "private/nested/config.json"
        atomic_json(path, {"name": "설정"})
        atomic_json(path, {"name": "새 설정"})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"name": "새 설정"})
        self.assertEqual(list(path.parent.glob("*.tmp")), [])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_failed_atomic_replace_keeps_original_and_cleans_temporary_file(self):
        path = self.root / "config.json"
        atomic_json(path, {"value": "original"})
        with patch("joongi_hub.storage.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                atomic_json(path, {"value": "new"})
        self.assertEqual(json.loads(path.read_text()), {"value": "original"})
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_timestamp_is_utc_iso_format(self):
        self.assertRegex(timestamp(), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
