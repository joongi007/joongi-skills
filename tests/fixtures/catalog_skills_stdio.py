"""Temporary, account-free Hub exposing two independent same-name skill sources."""

import json
import sys
import tempfile
from pathlib import Path

from joongi_hub.service import Hub
from tests.fixtures.credential_store import test_store


def main():
    with tempfile.TemporaryDirectory(prefix="joongi-source-skills-") as directory:
        root = Path(directory).resolve()
        (root / "builtin").mkdir()
        sources = []
        for identity, category in (("company", "design"), ("personal", "documentation")):
            source = root / identity
            skill = source / "same-guide"
            (skill / "references").mkdir(parents=True)
            (skill / "assets").mkdir()
            text = (
                "---\nname: same-guide\ndescription: Same name, different source.\n"
                f"metadata:\n  owner: {identity}\n---\n\n# {identity} source guide\n"
            )
            (skill / "SKILL.md").write_text(text, encoding="utf-8")
            (skill / "references/check.md").write_text(
                f"# {identity} source reference\n", encoding="utf-8"
            )
            (skill / "assets/sample.bin").write_bytes(
                bytes([0, 255, 17]) + identity.encode("ascii")
            )
            sources.append(
                {"id": identity, "name": identity, "path": str(source), "category": category}
            )
        hub = Hub(root / "builtin", root / "state", credential_store_factory=test_store)
        hub.configure_catalog({"sources": sources})
        context = {"owner": "isolated-source-sdk", "local_owner": True}
        try:
            for line in sys.stdin:
                reply = hub.rpc(json.loads(line), context)
                if reply is not None:
                    print(json.dumps(reply, ensure_ascii=False), flush=True)
        finally:
            hub.close()


if __name__ == "__main__":
    main()
