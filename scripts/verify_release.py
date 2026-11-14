"""Verify a release with GitHub CLI's Sigstore verifier before executing its files.

This module is also embedded verbatim in published bootstraps. Trust policy must
come from the reviewed bootstrap/installed verifier, never the downloaded bundle.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

TRUSTED_REPOSITORY = "joongi007/joongi-skills"
TRUSTED_REPOSITORY_ID = "1452939341"
TRUSTED_OWNER_ID = "68692377"
TRUSTED_WORKFLOW = "joongi007/joongi-skills/.github/workflows/pages.yml"
TRUSTED_REF = "refs/heads/main"


class VerificationError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def github_document(path):
    request = urllib.request.Request(
        "https://api.github.com/repos/" + TRUSTED_REPOSITORY + ("/" + path if path else ""),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "joongi-release-verifier",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=30) as response:
            content = response.read(1024**2 + 1)
        if len(content) > 1024**2:
            raise ValueError
        return json.loads(content)
    except (OSError, ValueError) as exc:
        raise VerificationError("GitHub release trust metadata could not be verified") from exc


def expected_revision():
    repository = github_document("")
    if (
        str(repository.get("id")) != TRUSTED_REPOSITORY_ID
        or str(repository.get("owner", {}).get("id")) != TRUSTED_OWNER_ID
    ):
        raise VerificationError("The trusted repository identity changed")
    return github_document("branches/main")["commit"]["sha"]


def _field(value, wanted):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if re.sub("[^a-z]", "", key.lower()) == wanted:
                found.append(str(item))
            else:
                found.extend(_field(item, wanted))
    elif isinstance(value, list):
        for item in value:
            found.extend(_field(item, wanted))
    return found


def verify_release(archive, bundle, revision=None):
    archive, bundle = Path(archive), Path(bundle)
    if archive.is_symlink() or bundle.is_symlink() or not archive.is_file() or not bundle.is_file():
        raise VerificationError("Release artifact and attestation must be regular files")
    if archive.stat().st_size > 32 * 1024**2 or bundle.stat().st_size > 2 * 1024**2:
        raise VerificationError("Release verification size limit exceeded")
    revision = revision or expected_revision()
    if not isinstance(revision, str) or not re.fullmatch("[a-f0-9]{40}", revision):
        raise VerificationError("Expected source revision must be a full commit SHA")
    gh = shutil.which("gh")
    if not gh:
        candidate = Path.home() / ".local/bin" / ("gh.exe" if os.name == "nt" else "gh")
        gh = str(candidate) if candidate.is_file() else None
    if not gh:
        raise VerificationError(
            "GitHub CLI with 'gh attestation verify' is required. "
            "Install it from https://cli.github.com/; unsigned installation is disabled."
        )
    command = [
        gh,
        "attestation",
        "verify",
        str(archive),
        "--bundle",
        str(bundle),
        "--repo",
        TRUSTED_REPOSITORY,
        "--signer-workflow",
        TRUSTED_WORKFLOW,
        "--cert-identity",
        "https://github.com/" + TRUSTED_WORKFLOW + "@" + TRUSTED_REF,
        "--cert-oidc-issuer",
        "https://token.actions.githubusercontent.com",
        "--source-ref",
        TRUSTED_REF,
        "--source-digest",
        revision,
        "--predicate-type",
        "https://slsa.dev/provenance/v1",
        "--deny-self-hosted-runners",
        "--hostname",
        "github.com",
        "--format",
        "json",
    ]
    # Do not expose provider credentials or accept alternate Sigstore trust roots
    # from the caller's environment. The official verifier supplies its roots.
    allowed = {
        "PATH",
        "HOME",
        "USERPROFILE",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "TMPDIR",
        "APPDATA",
        "LOCALAPPDATA",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "XDG_CACHE_HOME",
    }
    environment = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    environment.update(
        GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1", GH_NO_EXTENSION_UPDATE_NOTIFIER="1"
    )
    try:
        result = subprocess.run(command, capture_output=True, timeout=90, env=environment)
        if result.returncode or len(result.stdout) > 4 * 1024**2:
            raise VerificationError(
                "Release signature/provenance verification failed; no downloaded code was executed"
            )
        verified = json.loads(result.stdout)
        if not isinstance(verified, list) or not verified:
            raise ValueError
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        for record in verified:
            value = record["verificationResult"]
            certificate = value["signature"]["certificate"]
            if _field(certificate, "sourcerepositoryidentifier") != [
                TRUSTED_REPOSITORY_ID
            ] or _field(certificate, "sourcerepositoryowneridentifier") != [TRUSTED_OWNER_ID]:
                raise ValueError
            subjects = value["statement"]["subject"]
            if any(subject.get("digest", {}).get("sha256") == digest for subject in subjects):
                return {"revision": revision, "repository": TRUSTED_REPOSITORY, "sha256": digest}
        raise ValueError
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as exc:
        raise VerificationError(
            "Release verification did not provide the required trusted identity and digest"
        ) from exc


def verify_download(data, attestation, revision=None):
    with tempfile.TemporaryDirectory(
        prefix="joongi-release-verification-", dir=Path.home() if os.name == "nt" else None
    ) as directory:
        root = Path(directory)
        archive, bundle = root / "joongi-skills.tar.gz", root / "attestation.jsonl"
        archive.write_bytes(data)
        bundle.write_bytes(attestation)
        verified = verify_release(archive, bundle, revision)
        if verified["sha256"] != hashlib.sha256(data).hexdigest():
            raise VerificationError(
                "Verified artifact does not match the immutable downloaded bytes"
            )
        return verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument(
        "--revision",
        help="Explicitly reviewed full source commit SHA; default requires current main",
    )
    args = parser.parse_args()
    try:
        print(json.dumps(verify_release(args.archive, args.bundle, args.revision)))
        return 0
    except VerificationError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
