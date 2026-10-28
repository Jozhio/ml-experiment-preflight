"""Synthetic POSIX regression cases; no real ACL or training data."""

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from ml_experiment_preflight import git_rules, path_rules


@unittest.skipUnless(os.name == "posix", "POSIX filesystem and process groups")
class PosixRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "train.py").write_text("# synthetic\n", encoding="utf-8")
        (self.root / "Input.bin").write_bytes(b"synthetic")

    def evaluate(self, input_name="Input.bin"):
        return path_rules.evaluate_path_rules(
            self.root, "train.py", [("file", input_name)],
            [("file", "out.bin")],
        )[0]

    def test_input_path_case_is_significant(self):
        self.assertEqual(self.evaluate("Input.bin")["status"], "pass")
        wrong_case = self.evaluate("input.bin")
        self.assertEqual(wrong_case["status"], "finding")
        self.assertIn("INPUT_MISSING", [item["code"] for item in wrong_case["evidence"]])

    def test_permission_error_from_metadata_is_unknown(self):
        original = Path.stat
        target = self.root / "Input.bin"

        def denying(path, *args, **kwargs):
            if path == target:
                raise PermissionError("synthetic metadata denial")
            return original(path, *args, **kwargs)

        with patch.object(Path, "stat", denying):
            row = self.evaluate()
        self.assertEqual(row["status"], "unknown")
        self.assertEqual(row["reason_code"], "PERMISSION_DENIED")
        self.assertEqual(row["unknown_refs"], ["input:1"])

    def test_double_slash_network_path_is_unknown(self):
        network_input = "//preflight-invalid-host/share/input.bin"
        path_row, output_row, conflict_row = path_rules.evaluate_path_rules(
            self.root, "train.py", [("file", network_input)],
            [("file", "out.bin")],
        )
        self.assertEqual(path_row["status"], "unknown")
        self.assertEqual(path_row["unknown_refs"], ["input:1"])
        self.assertEqual(path_row["reason_code"], "PATH_IO_ERROR")
        self.assertEqual(output_row["status"], "pass")
        self.assertEqual(conflict_row["status"], "unknown")

    def test_timeout_terminates_posix_process_group(self):
        marker = self.root / "child-survived.marker"
        child_pid_file = self.root / "child.pid"
        child_script = (
            "import pathlib,sys,time; "
            "time.sleep(3); pathlib.Path(sys.argv[1]).write_text('survived')"
        )
        parent_script = (
            "import pathlib,subprocess,sys,time; "
            "child=subprocess.Popen([sys.executable,'-B','-c',sys.argv[2],sys.argv[3]]); "
            "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(30)"
        )
        result = git_rules._run_process(
            [sys.executable, "-B", "-c", parent_script,
             str(child_pid_file), child_script, str(marker)],
            timeout=1.5, max_output=1024, env=os.environ.copy(),
        )
        self.assertEqual(result.failure, "timeout")
        self.assertTrue(child_pid_file.is_file(), "child did not start before timeout")
        # The synthetic child exits promptly even if a regression leaves it alive.
        time.sleep(3.2)
        self.assertFalse(marker.exists(), "child survived process-group termination")


if __name__ == "__main__":
    unittest.main()
