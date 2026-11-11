"""Mutation generation and verdicts must be independent and reproducible."""

import ast
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.mutation_check import (
    campaign,
    inventory,
    main,
    mutated_source,
    reviewed_survivors,
    run_tests,
)


class MutationEngineTests(unittest.TestCase):
    def test_cli_fails_for_unreviewed_survivor_and_stale_review(self):
        location = {
            "line": 3,
            "column": 4,
            "operator": "constant",
            "detail": "invert-boolean",
            "operand_index": 0,
        }
        report = {
            "target": "joongi_hub/logic.py",
            "sourceSha256": "source-a",
            "summary": {"survived": 2},
            "results": [{"id": i, "status": "survived", **{**location, "line": i}} for i in (1, 2)],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = {"schema": 1, "target": report["target"], "sourceSha256": "source-a"}
            review_file = root / "reviews.json"
            args = [
                "--report",
                str(root / "report.json"),
                "--fail-on-survivor",
                "--reviewed-survivors",
                str(review_file),
            ]
            for reviewed_count, source_hash, expected in [
                (1, "source-a", 1),
                (2, "source-a", 0),
                (2, "changed-source", 1),
            ]:
                policy["sourceSha256"] = source_hash
                policy["equivalent"] = [
                    {**location, "line": i, "reason": "Reviewed fixture"}
                    for i in range(1, reviewed_count + 1)
                ]
                review_file.write_text(json.dumps(policy))
                with (
                    self.subTest(count=reviewed_count, source=source_hash),
                    patch("scripts.mutation_check.campaign", return_value=copy.deepcopy(report)),
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    self.assertEqual(main(args), expected)

    def test_equivalent_reviews_require_exact_source_and_do_not_hide_other_survivors(self):
        location = {
            "line": 3,
            "column": 4,
            "operator": "constant",
            "detail": "invert-boolean",
            "operand_index": 0,
        }
        report = {
            "target": "joongi_hub/logic.py",
            "sourceSha256": "source-a",
            "results": [
                {"id": 1, "status": "survived", **location},
                {"id": 2, "status": "survived", **{**location, "line": 8}},
            ],
        }
        policy = {
            "schema": 1,
            "target": report["target"],
            "sourceSha256": "source-a",
            "equivalent": [{**location, "reason": "Serialization only; parsed value unchanged"}],
        }
        self.assertEqual([r["id"] for r in reviewed_survivors(report, policy)], [1])
        for change in ({"sourceSha256": "source-b"}, {"target": "other.py"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                reviewed_survivors(report, {**policy, **change})
        with self.assertRaises(ValueError):
            reviewed_survivors(report, {**policy, "equivalent": [{**location, "reason": ""}]})

    def test_operators_are_enumerated_from_arbitrary_ast(self):
        source = "def choose(a, b):\n    if not a or b < 2:\n        return True\n    return 3\n"
        parsed = ast.parse(source)
        operators = {item.operator for item in inventory(parsed)}
        self.assertEqual(operators, {"branch", "negation", "boolean", "comparison", "constant"})
        for mutation in inventory(parsed):
            changed = mutated_source(parsed, mutation)
            compile(changed, "<mutant>", "exec")
            self.assertNotEqual(ast.dump(ast.parse(changed)), ast.dump(parsed))

    def test_comparison_mutation_changes_one_operand_and_preserves_source(self):
        parsed = ast.parse("result = a < b < c\n")
        before = ast.dump(parsed)
        mutants = inventory(parsed)
        self.assertEqual(len(mutants), 2)
        first = ast.parse(mutated_source(parsed, mutants[0]))
        self.assertIsInstance(first.body[0].value.ops[0], ast.GtE)
        self.assertIsInstance(first.body[0].value.ops[1], ast.Lt)
        self.assertEqual(ast.dump(parsed), before)

    def test_campaign_detects_faults_and_retains_survivors_without_editing_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "joongi_hub"
            package.mkdir()
            (package / "__init__.py").write_text("")
            source = "def choose(value):\n    if value < 2:\n        return 7\n    return 9\n"
            target = package / "logic.py"
            target.write_text(source)
            tests = root / "tests"
            tests.mkdir()
            (tests / "__init__.py").write_text("")
            (tests / "test_logic.py").write_text(
                "import unittest\nfrom joongi_hub.logic import choose\n"
                "class Checks(unittest.TestCase):\n"
                "    def test_one(self):\n        self.assertEqual(choose(1), 7)\n"
            )
            report = campaign(root, "joongi_hub/logic.py", ["tests.test_logic"], timeout=5)
            self.assertGreater(report["summary"].get("killed", 0), 0)
            self.assertGreater(report["summary"].get("survived", 0), 0)
            self.assertEqual(report["summary"].get("invalid", 0), 0)
            self.assertEqual(target.read_text(), source)

    def test_target_cannot_escape_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                campaign(Path(temporary), "../outside.py", ["tests.test_logic"])

    def test_timeout_and_infrastructure_error_are_not_counted_as_killed(self):
        import subprocess

        with patch(
            "scripts.mutation_check.subprocess.run",
            side_effect=subprocess.TimeoutExpired("test", 1),
        ):
            self.assertEqual(run_tests(Path("."), ["tests.test_logic"], 1)["status"], "timeout")
        result = subprocess.CompletedProcess("test", 1, "", "Interpreter could not start")
        with patch("scripts.mutation_check.subprocess.run", return_value=result):
            self.assertEqual(run_tests(Path("."), ["tests.test_logic"], 1)["status"], "invalid")
