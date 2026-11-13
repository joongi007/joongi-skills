"""Fake OS keyring for isolated tests; never selected by production configuration."""

import base64
import os
from pathlib import Path

from joongi_hub.credential_store import CredentialStore


class FixtureVault:
    name = "linux-secret-service"

    def __init__(self, directory):
        self.directory = Path(directory)

    def entry(self, action, key, data=None):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / key
        if action == "write":
            path.write_bytes(base64.b64encode(data))
        elif action == "delete":
            path.unlink(missing_ok=True)
        elif path.exists():
            return base64.b64decode(path.read_bytes())


def test_store(path):
    return (
        CredentialStore(path)
        if os.name == "nt"
        else CredentialStore(path, FixtureVault(Path(path).parent / "fixture-vault"))
    )
