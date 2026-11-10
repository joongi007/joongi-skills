"""Mutation generation and verdicts must be independent and reproducible."""

import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.mutation_check import campaign, inventory, mutated_source, run_tests


class MutationEngineTests(unittest.TestCase):
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
