"""Vault failures must never degrade to plaintext or lose committed credentials."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.credential_store import CredentialStore, SystemVault, wsl_dpapi
from joongi_hub.errors import RpcError
from tests.fixtures.credential_store import FixtureVault


class CredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "credentials.json"
        self.vault = FixtureVault(self.root / "vault")
        self.store = CredentialStore(self.path, self.vault)
        self.records = {
            "provider": {
                "access_token": "fake-access-only-for-tests",
                "refresh_token": "fake-refresh-only-for-tests",
            }
        }

    def test_restart_rotation_and_delete(self):
        self.store.save(self.records)
        marker = json.loads(self.path.read_bytes())
        self.assertNotIn(b"fake-access", self.path.read_bytes())
        self.assertEqual(CredentialStore(self.path, self.vault).load(), self.records)
        self.store.save({"provider": {"access_token": "replacement-fake-token"}})
        self.assertFalse((self.vault.directory / marker["key"]).exists())
        self.store.save({})
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.vault.directory.iterdir()), [])

    def test_locked_vault_never_returns_cached_tokens_or_overwrites_marker(self):
        self.store.save(self.records)
        self.store.load()
        before = self.path.read_bytes()
        with patch.object(self.vault, "entry", side_effect=RpcError(-32045, "locked")):
            with self.assertRaises(RpcError):
                self.store.load()
            with self.assertRaises(RpcError):
                self.store.save(self.records)
        self.assertEqual(self.path.read_bytes(), before)

    def test_atomic_publish_failure_keeps_previous_credential(self):
        self.store.save(self.records)
        before = self.path.read_bytes()
        with patch("joongi_hub.credential_store.atomic_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.store.save({"provider": {"access_token": "fake-replacement"}})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.load(), self.records)

    def test_plaintext_requires_explicit_migration_and_missing_vault_fails_closed(self):
        self.path.write_text(json.dumps(self.records))
        with self.assertRaises(RpcError):
            self.store.load()
        before = self.path.read_bytes()
        vault = SystemVault()
        vault.name = "unavailable"
        with self.assertRaises(RpcError):
            CredentialStore(self.path, vault).migrate()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(self.store.migrate()["migrated"])
        self.assertEqual(self.store.load(), self.records)
        self.assertFalse(self.store.migrate()["migrated"])

    def test_wsl_secrets_use_stdin_and_not_process_arguments(self):
        import base64

        with patch(
            "joongi_hub.credential_store.run", return_value=base64.b64encode(b"cipher")
        ) as command:
            self.assertEqual(wsl_dpapi(b"fake-private-credential"), b"cipher")
            args, data = command.call_args.args
            self.assertNotIn("fake-private-credential", repr(args))
            self.assertEqual(data, base64.b64encode(b"fake-private-credential"))


class NativeCredentialStoreTests(unittest.TestCase):
    @unittest.skipUnless(
        __import__("os").environ.get("JOONGI_TEST_NATIVE_VAULT") == "1",
        "requires an isolated unlocked native OS vault",
    )
    def test_native_vault_round_trip_rotation_and_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            store = CredentialStore(path)
            self.assertNotEqual(store.vault.name, "unavailable")
            try:
                first = {"fixture": {"access_token": "fake-native-token-for-ci-only"}}
                store.save(first)
                self.assertNotIn(b"fake-native-token", path.read_bytes())
                self.assertEqual(CredentialStore(path).load(), first)
                second = {"fixture": {"access_token": "fake-rotated-native-token"}}
                store.save(second)
                self.assertEqual(CredentialStore(path).load(), second)
            finally:
                store.save({})
            self.assertFalse(path.exists())
