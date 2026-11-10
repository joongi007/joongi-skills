"""Documentation claims must fail on semantic interface drift, not only broken links."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_contracts import actual_facts, check, method_branches, route_patterns


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "docs").mkdir()
        self.facts = {
            "runtime.version": "1.0.0",
            "runtime.versionFile": "1.0.0",
            "http.routes": ["GET /api/v1/state"],
        }
        self.manifest = {"schema": 1, "facts": self.facts, "requiredClaims": ["runtime.version"]}
        self.save()
        (self.root / "docs/claim.md").write_text('<!-- contract: runtime.version = "1.0.0" -->\n')

    def save(self):
        (self.root / "docs/contracts.json").write_text(json.dumps(self.manifest))

    def test_matching_contracts_pass(self):
        self.assertEqual(check(self.root, self.facts), [])

    def test_runtime_drift_is_reported(self):
        actual = {**self.facts, "http.routes": ["GET /api/v2/state"]}
        self.assertTrue(any("http.routes drift" in error for error in check(self.root, actual)))

    def test_cross_document_disagreement_and_missing_claim_are_reported(self):
        (self.root / "docs/other.md").write_text('<!-- contract: runtime.version = "2.0.0" -->\n')
        self.assertTrue(
            any("conflicting contract" in error for error in check(self.root, self.facts))
        )
        (self.root / "docs/other.md").unlink()
        (self.root / "docs/claim.md").unlink()
        self.assertTrue(
            any("missing cross-document" in error for error in check(self.root, self.facts))
        )

    def test_requirement_must_resolve_to_existing_acceptance_test(self):
        (self.root / "docs/02-scope.md").write_text("| REQ-ONE | behavior |\n")
        self.assertTrue(
            any("lacks acceptance trace" in error for error in check(self.root, self.facts))
        )
        self.manifest["requirements"] = {
            "REQ-ONE": {"tests": ["tests.test_example.Checks.test_real"]}
        }
        self.save()
        self.assertTrue(
            any("missing acceptance test" in error for error in check(self.root, self.facts))
        )

    def test_extractors_distinguish_dispatch_from_business_strings(self):
        import ast

        module = ast.parse(
            "class Handler:\n    def do_POST(self):\n"
            "        if self.path.startswith('/api/v1/tasks/') and self.path.endswith('/cancel'):\n"
            "            response = {'path':'not-a-route'}\n"
            "def rpc(method):\n    if method in {'tasks/get', 'tasks/cancel'}:\n        pass\n"
        )
        self.assertEqual(route_patterns(module), ["POST /api/v1/tasks/{value}/cancel"])
        self.assertEqual(method_branches(module), ["tasks/cancel", "tasks/get"])

    def test_repository_contracts(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(check(root, actual_facts(root)), [])
