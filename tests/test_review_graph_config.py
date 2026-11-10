"""External graph configuration must preserve isolation and venv identity."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_review_graph import BOOTSTRAP, TOOLS, server_config


class ReviewGraphConfiguration(unittest.TestCase):
    def test_bootstrap_keeps_paths_with_spaces_and_isolates_only_crg_state(self):
        with tempfile.TemporaryDirectory(prefix="review graph ") as temporary:
            root = Path(temporary)
            package = root / "code_review_graph"
            package.mkdir()
            (package / "__init__.py").write_text("")
            (package / "__main__.py").write_text(
                "import json,os,sys\n"
                "print(json.dumps({'args':sys.argv,'state':os.environ['CRG_HOME'],"
                "'data':os.environ['CRG_DATA_DIR']}))\n"
            )
            process = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    BOOTSTRAP,
                    str(root / "home"),
                    str(root / "data"),
                    "serve",
                    "--repo",
                    str(root),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            result = json.loads(process.stdout)
            self.assertEqual(result["args"], ["code-review-graph", "serve", "--repo", str(root)])
            self.assertEqual(result["state"], str(root / "home"))
            self.assertEqual(result["data"], str(root / "data"))

    def test_config_keeps_interpreter_symlink_and_restricts_tools(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            interpreter = root / "venv-python"
            try:
                interpreter.symlink_to(sys.executable)
            except OSError:
                self.skipTest("symlink creation is unavailable")
            config = server_config(interpreter, root, root / "state")
            self.assertEqual(config["command"], str(interpreter))
            self.assertEqual(config["args"][-1], ",".join(TOOLS))
            self.assertNotIn("apply_refactor_tool", config["args"][-1])


if __name__ == "__main__":
    unittest.main()
