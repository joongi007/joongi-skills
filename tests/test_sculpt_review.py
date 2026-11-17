"""External manifest contracts: skipped passes, invented coverage and budget failures."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from joongi_hub.errors import RpcError
from joongi_hub.sculpt_review import STAGES, validate
from joongi_hub.service import Hub

ROOT = Path(__file__).resolve().parents[1]


def manifest(stage="blockout"):
    return {
        "references": ["reference/front.png"],
        "components": [{"id": "body", "purpose": "main body"}],
        "details": [
            {
                "id": "rim",
                "component_id": "body",
                "evidence": ["reference/front.png"],
                "confidence": 0.8,
            }
        ],
        "passes": [
            {
                "stage": name,
                "evidence": ["review/" + name + ".png"],
                "accepted": True,
                "notes": "Compared fixed front view; actual reviewer report.",
            }
            for name in STAGES[: STAGES.index(stage) + 1]
        ],
        "limitations": ["Back not visible in reference"],
        "budget": {"draw_calls": 80, "triangles": 100000, "frame_ms": 20},
        "measurements": {"draw_calls": 32, "triangles": 24000, "frame_ms": 12},
    }


class SculptReview(unittest.TestCase):
    def test_complete_record_has_explicit_manifest_only_scope(self):
        result = validate("optimization", manifest("optimization"))
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["verification"], "manifest_only")

    def test_missing_reordered_or_unreviewed_pass_is_blocked(self):
        report = manifest("form")
        variants = []
        for edit in (
            lambda r: r["passes"].pop(0),
            lambda r: r["passes"].reverse(),
            lambda r: r["passes"][0].update(accepted=False),
            lambda r: r["passes"][0].update(evidence=[]),
        ):
            changed = copy.deepcopy(report)
            edit(changed)
            variants.append(changed)
        for changed in variants:
            self.assertEqual(validate("form", changed)["status"], "blocked")

    def test_missing_component_mapping_duplicate_or_boolean_confidence_is_blocked(self):
        for edit in (
            lambda r: r["details"][0].update(component_id="absent"),
            lambda r: r["components"].append(r["components"][0]),
            lambda r: r["details"][0].update(confidence=True),
            lambda r: r["details"][0].update(confidence=10**300),
        ):
            report = manifest()
            edit(report)
            self.assertEqual(validate("blockout", report)["status"], "blocked")

    def test_unmeasured_excessive_or_boolean_budget_is_blocked(self):
        for value in (None, 81, True, -1):
            report = manifest("optimization")
            report["measurements"]["draw_calls"] = value
            self.assertEqual(validate("optimization", report)["status"], "blocked")

    def test_invalid_or_oversized_json_is_rejected_without_execution(self):
        for report in ({"value": float("nan")}, {"value": "x" * 128001}, []):
            with self.assertRaises(RpcError):
                validate("blockout", report)

    def test_real_hub_discovers_skill_and_calls_gate(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        hub = Hub(ROOT / "skills", Path(temporary.name))
        self.addCleanup(hub.close)
        self.assertTrue(hub.search("building-procedural-3d", kind="skill"))
        tool = next(t for t in hub.tools() if t["name"] == "hub_3d_review")
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        result = hub.invoke("hub_3d_review", {"target_stage": "blockout", "report": manifest()})
        self.assertEqual(json.loads(result["content"][0]["text"])["status"], "passed")


if __name__ == "__main__":
    unittest.main()
