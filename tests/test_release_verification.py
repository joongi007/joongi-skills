"""Trust checks happen before archive extraction or downloaded code execution."""

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.verify_release import VerificationError, verify_download, verify_release


class ReleaseVerification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "artifact"
        self.bundle = self.root / "attestation.jsonl"
        self.archive.write_bytes(b"reviewed-fake-artifact")
        self.bundle.write_text("{}")
        self.sha = "a" * 40
        self.verified = [
            {
                "verificationResult": {
                    "signature": {
                        "certificate": {
                            "sourceRepositoryIdentifier": "1452939341",
                            "sourceRepositoryOwnerIdentifier": "68692377",
                        }
                    },
                    "statement": {
                        "subject": [
                            {
                                "digest": {
                                    "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest()
                                }
                            }
                        ]
                    },
                }
            }
        ]

    def run_verifier(self, result=None):
        response = subprocess.CompletedProcess(
            [], 0, json.dumps(result or self.verified).encode(), b""
        )
        with (
            patch("scripts.verify_release.shutil.which", return_value="/trusted/gh"),
            patch("scripts.verify_release.subprocess.run", return_value=response) as command,
        ):
            verified = verify_release(self.archive, self.bundle, self.sha)
            args = command.call_args.args[0]
            for expected in [
                "--source-digest",
                self.sha,
                "--cert-identity",
                "--deny-self-hosted-runners",
                "--source-ref",
            ]:
                self.assertIn(expected, args)
            self.assertNotIn("--signer-workflow", args)
            self.assertNotIn("GH_TOKEN", command.call_args.kwargs["env"])
            return verified

    def test_verifier_pins_workflow_source_repository_identity_and_digest(self):
        self.assertEqual(self.run_verifier()["revision"], self.sha)
        self.verified[0]["verificationResult"]["signature"]["certificate"][
            "sourceRepositoryIdentifier"
        ] = "different-repository"
        with self.assertRaises(VerificationError):
            self.run_verifier()

    def test_modified_artifact_is_rejected_even_if_cli_output_is_otherwise_valid(self):
        self.archive.write_bytes(b"modified artifact")
        with self.assertRaises(VerificationError):
            self.run_verifier()

    def test_temporary_file_replacement_cannot_authorize_different_downloaded_bytes(self):
        with patch("scripts.verify_release.verify_release", return_value={"sha256": "0" * 64}):
            with self.assertRaises(VerificationError):
                verify_download(b"original-downloaded-bytes", b"fake-attestation", self.sha)

    def test_failed_or_missing_verifier_never_falls_back_to_checksums(self):
        with (
            patch("scripts.verify_release.shutil.which", return_value="/trusted/gh"),
            patch(
                "scripts.verify_release.subprocess.run",
                return_value=subprocess.CompletedProcess([], 1, b"", b"fake rejected bundle"),
            ),
        ):
            with self.assertRaises(VerificationError):
                verify_release(self.archive, self.bundle, self.sha)
        with (
            patch("scripts.verify_release.shutil.which", return_value=None),
            patch("scripts.verify_release.Path.home", return_value=self.root),
        ):
            with self.assertRaises(VerificationError):
                verify_release(self.archive, self.bundle, self.sha)
