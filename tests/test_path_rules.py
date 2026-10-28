"""Synthetic path and output rule behavior."""

import contextlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from ml_experiment_preflight import cli
from ml_experiment_preflight.report import exit_code, validate_report


class PathRuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "train.py").write_text("# synthetic\n", encoding="utf-8")
        (self.root / "input.bin").write_bytes(b"synthetic")
        (self.root / "runs").mkdir()

    def report(self, *, entry="train.py", inputs=None, outputs=None):
        inputs = inputs if inputs is not None else [("file", "input.bin")]
        outputs = outputs if outputs is not None else [("file", "runs/result.bin")]
        args = ["check", "--root", str(self.root), "--entry", entry]
        for kind, raw in inputs:
            args.extend(("--input-" + kind, raw))
        for kind, raw in outputs:
            args.extend(("--output-" + kind, raw))
        report, _ = cli.run_check(args)
        validate_report(report)
        return report

    def rows(self, report):
        return {row["rule_id"]: row for row in report["results"]}

    def test_present_inputs_and_absent_output_have_three_real_passes(self):
        report = self.report()
        rows = self.rows(report)
        for rule in ("PATH-001", "OUT-001", "OUT-002"):
            self.assertEqual(rows[rule]["status"], "pass")
            self.assertTrue(rows[rule]["coverage_complete"])
        self.assertEqual(rows["GIT-001"]["status"], "finding")
        self.assertEqual(rows["GIT-001"]["severity"], "warning")
        for rule in ("GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["status"], "unknown")
            self.assertEqual(rows[rule]["reason_code"], "GIT_CONTEXT_UNKNOWN")
        self.assertEqual(report["overall"], {
            "status": "incomplete", "finding_count": 1, "unknown_count": 2,
        })
        self.assertEqual(exit_code(report), 2)

    def test_missing_input_and_wrong_input_type_are_critical_findings(self):
        report = self.report(inputs=[("file", "missing.bin"), ("dir", "input.bin")])
        path = self.rows(report)["PATH-001"]
        self.assertEqual(path["status"], "finding")
        self.assertEqual(path["severity"], "critical")
        self.assertTrue(path["coverage_complete"])
        self.assertEqual({item["code"] for item in path["evidence"]},
                         {"INPUT_MISSING", "TYPE_MISMATCH"})

    def test_missing_entry_is_finding_and_makes_overlap_unknown(self):
        report = self.report(entry="absent.py")
        rows = self.rows(report)
        self.assertEqual(rows["PATH-001"]["evidence"][0]["code"], "ENTRY_MISSING")
        self.assertEqual(rows["OUT-002"]["status"], "unknown")
        self.assertFalse(rows["OUT-002"]["coverage_complete"])
        self.assertIn("entry", rows["OUT-002"]["unknown_refs"])

    def test_permission_denial_keeps_known_finding_and_unknown_target(self):
        original = Path.resolve
        denied = (self.root / "input.bin").resolve()

        def resolving(path, *args, **kwargs):
            if path == denied:
                raise PermissionError("private path")
            return original(path, *args, **kwargs)

        with patch.object(Path, "resolve", resolving):
            report = self.report(inputs=[("file", "missing.bin"), ("file", "input.bin")])
        path = self.rows(report)["PATH-001"]
        self.assertEqual(path["status"], "finding")
        self.assertFalse(path["coverage_complete"])
        self.assertEqual(path["reason_code"], "PERMISSION_DENIED")
        self.assertEqual(path["unknown_refs"], ["input:2"])
        self.assertEqual(path["evidence"][0]["code"], "INPUT_MISSING")
        self.assertEqual(report["overall"]["status"], "blocked")
        self.assertEqual(exit_code(report), 2)

    def test_entry_symlink_escaping_root_is_critical(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "outside.py"
            outside.write_text("# synthetic\n", encoding="utf-8")
            link = self.root / "linked.py"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                original = Path.resolve

                def resolving(path, *args, **kwargs):
                    return outside if path == link else original(path, *args, **kwargs)

                with patch.object(Path, "resolve", resolving):
                    report = self.report(entry="linked.py")
            else:
                report = self.report(entry="linked.py")
        path = self.rows(report)["PATH-001"]
        self.assertEqual(path["status"], "finding")
        self.assertIn("ENTRY_ESCAPES_ROOT", [e["code"] for e in path["evidence"]])

    def test_broken_input_symlink_is_unknown_not_missing(self):
        link = self.root / "broken.bin"
        try:
            link.symlink_to(self.root / "never-created.bin")
        except (OSError, NotImplementedError):
            original_resolve, original_lstat = Path.resolve, Path.lstat

            def resolving(path, *args, **kwargs):
                if path == link:
                    raise FileNotFoundError("synthetic broken link")
                return original_resolve(path, *args, **kwargs)

            def lstating(path, *args, **kwargs):
                if path == link:
                    return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 1, 0, 0, 0, 0, 0, 0))
                return original_lstat(path, *args, **kwargs)

            with patch.object(Path, "resolve", resolving), patch.object(Path, "lstat", lstating):
                report = self.report(inputs=[("file", "broken.bin")])
        else:
            report = self.report(inputs=[("file", "broken.bin")])
        path = self.rows(report)["PATH-001"]
        self.assertEqual(path["status"], "unknown")
        self.assertEqual(path["reason_code"], "SYMLINK_UNRESOLVED")
        self.assertEqual(path["unknown_refs"], ["input:1"])

    def test_existing_output_warning_and_type_mismatch_critical(self):
        (self.root / "runs" / "existing.bin").write_bytes(b"synthetic")
        report = self.report(outputs=[("file", "runs/existing.bin")])
        out = self.rows(report)["OUT-001"]
        self.assertEqual((out["status"], out["severity"]), ("finding", "warning"))
        self.assertEqual(out["evidence"][0]["code"], "OUTPUT_EXISTS")
        report = self.report(outputs=[("dir", "runs/existing.bin")])
        out = self.rows(report)["OUT-001"]
        self.assertEqual((out["status"], out["severity"]), ("finding", "critical"))
        self.assertEqual(out["evidence"][0]["code"], "OUTPUT_TYPE_MISMATCH")

    def test_output_missing_parent_is_unknown_and_can_mix_with_finding(self):
        (self.root / "runs" / "existing.bin").write_bytes(b"synthetic")
        report = self.report(outputs=[("file", "runs/existing.bin"),
                                      ("file", "unmade/result.bin")])
        rows = self.rows(report)
        out = rows["OUT-001"]
        self.assertEqual(out["status"], "finding")
        self.assertFalse(out["coverage_complete"])
        self.assertEqual(out["reason_code"], "OUTPUT_PARENT_UNKNOWN")
        self.assertEqual(out["unknown_refs"], ["output:2"])
        self.assertEqual(out["evidence"][0]["code"], "OUTPUT_EXISTS")
        self.assertFalse(rows["OUT-002"]["coverage_complete"])

    def test_output_with_only_unresolved_parent_is_unknown(self):
        report = self.report(outputs=[("file", "unmade/result.bin")])
        rows = self.rows(report)
        self.assertEqual(rows["OUT-001"]["status"], "unknown")
        self.assertEqual(rows["OUT-001"]["reason_code"], "OUTPUT_PARENT_UNKNOWN")
        self.assertEqual(rows["OUT-002"]["status"], "unknown")
        self.assertEqual(rows["OUT-002"]["reason_code"], "OUTPUT_PARENT_UNKNOWN")

    def test_output_equal_input_is_critical_and_inside_input_dir_is_warning(self):
        equal = self.report(outputs=[("file", "input.bin")])
        conflict = self.rows(equal)["OUT-002"]
        self.assertEqual((conflict["status"], conflict["severity"]),
                         ("finding", "critical"))
        self.assertIn("OUTPUT_EQUALS_INPUT_OR_ENTRY",
                      [item["code"] for item in conflict["evidence"]])

        (self.root / "data").mkdir()
        nested = self.report(inputs=[("dir", "data")],
                             outputs=[("file", "data/result.bin")])
        conflict = self.rows(nested)["OUT-002"]
        self.assertEqual((conflict["status"], conflict["severity"]),
                         ("finding", "warning"))
        self.assertEqual(conflict["evidence"][0]["code"], "OUTPUT_INSIDE_INPUT_DIR")

    def test_output_directory_contains_input_or_root_is_critical(self):
        (self.root / "data").mkdir()
        (self.root / "data" / "sample.bin").write_bytes(b"synthetic")
        report = self.report(inputs=[("file", "data/sample.bin")],
                             outputs=[("dir", "data")])
        out = self.rows(report)["OUT-002"]
        self.assertEqual(out["severity"], "critical")
        self.assertIn("OUTPUT_DIR_CONTAINS_INPUT_OR_ROOT",
                      [item["code"] for item in out["evidence"]])
        report = self.report(outputs=[("dir", str(self.root))])
        out = self.rows(report)["OUT-002"]
        self.assertEqual(out["severity"], "critical")
        self.assertIn("OUTPUT_DIR_CONTAINS_INPUT_OR_ROOT",
                      [item["code"] for item in out["evidence"]])

    def test_similar_prefix_directories_do_not_overlap(self):
        (self.root / "data").mkdir()
        (self.root / "database").mkdir()
        (self.root / "data" / "sample.bin").write_bytes(b"synthetic")
        report = self.report(inputs=[("dir", "data")],
                             outputs=[("file", "database/result.bin")])
        self.assertEqual(self.rows(report)["OUT-002"]["status"], "pass")

    def test_symlink_alias_output_conflict_uses_physical_path(self):
        alias = self.root / "alias.bin"
        try:
            alias.symlink_to(self.root / "input.bin")
        except (OSError, NotImplementedError):
            original = Path.resolve

            def resolving(path, *args, **kwargs):
                return self.root / "input.bin" if path == alias else original(path, *args, **kwargs)

            with patch.object(Path, "resolve", resolving):
                report = self.report(outputs=[("file", "alias.bin")])
        else:
            report = self.report(outputs=[("file", "alias.bin")])
        out = self.rows(report)["OUT-002"]
        self.assertIn("OUTPUT_EQUALS_INPUT_OR_ENTRY",
                      [item["code"] for item in out["evidence"]])

    def test_hardlink_alias_output_conflict_uses_file_identity(self):
        alias = self.root / "alias.bin"
        try:
            os.link(self.root / "input.bin", alias)
        except OSError:
            alias.write_bytes(b"synthetic")
            original = Path.samefile

            def samefile(path, other):
                if path == alias and other == self.root / "input.bin":
                    return True
                return original(path, other)

            with patch.object(Path, "samefile", samefile):
                report = self.report(outputs=[("file", "alias.bin")])
        else:
            report = self.report(outputs=[("file", "alias.bin")])
        out = self.rows(report)["OUT-002"]
        self.assertEqual(out["severity"], "critical")
        self.assertIn("OUTPUT_EQUALS_INPUT_OR_ENTRY",
                      [item["code"] for item in out["evidence"]])

    def test_file_identity_comparison_denial_is_unknown_not_pass(self):
        alias = self.root / "alias.bin"
        alias.write_bytes(b"synthetic")
        alias = alias.resolve()
        input_path = (self.root / "input.bin").resolve()
        original = Path.samefile

        def samefile(path, other):
            if path == alias and other == input_path:
                raise PermissionError("private identity")
            return original(path, other)

        with patch.object(Path, "samefile", samefile):
            report = self.report(outputs=[("file", "alias.bin")])
        out = self.rows(report)["OUT-002"]
        self.assertEqual(out["status"], "unknown")
        self.assertEqual(out["reason_code"], "PATH_COMPARISON_UNKNOWN")

    def test_overlap_finding_and_unknown_target_coexist(self):
        report = self.report(inputs=[("file", "input.bin"), ("file", "missing.bin")],
                             outputs=[("file", "input.bin")])
        out = self.rows(report)["OUT-002"]
        self.assertEqual(out["status"], "finding")
        self.assertFalse(out["coverage_complete"])
        self.assertEqual(out["reason_code"], "PATH_COMPARISON_UNKNOWN")
        self.assertEqual(out["unknown_refs"], ["input:2"])
        self.assertEqual(out["severity"], "critical")

    def test_overlap_evidence_limit_keeps_finding_and_incomplete(self):
        (self.root / "data").mkdir()
        inputs = []
        for number in range(32):
            name = f"data/item-{number}.bin"
            (self.root / name).write_bytes(b"synthetic")
            inputs.append(("file", name))
        report = self.report(inputs=inputs,
                             outputs=[("dir", str(self.root)), ("dir", "data")])
        out = self.rows(report)["OUT-002"]
        self.assertEqual(out["status"], "finding")
        self.assertFalse(out["coverage_complete"])
        self.assertEqual(out["reason_code"], "EVIDENCE_LIMIT")
        self.assertEqual(len(out["evidence"]), 64)
        self.assertIn("output:2", out["unknown_refs"])

    def test_finding_json_does_not_expose_path_or_filename(self):
        secret = "private-subject-audio.bin"
        args = ["check", "--root", str(self.root), "--entry", "train.py",
                "--input-file", secret, "--output-file", "runs/result.bin",
                "--format", "json"]
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(args)
        self.assertEqual(code, 2)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(json.loads(stdout.getvalue())["results"][3]["status"], "finding")
        self.assertNotIn(str(self.root), stdout.getvalue())
        self.assertNotIn(secret, stdout.getvalue())

    def test_rules_do_not_modify_checked_project(self):
        before = {path.relative_to(self.root): (path.stat().st_size, path.stat().st_mtime_ns)
                  for path in self.root.rglob("*")}
        self.report()
        after = {path.relative_to(self.root): (path.stat().st_size, path.stat().st_mtime_ns)
                 for path in self.root.rglob("*")}
        self.assertEqual(before, after)

    def test_input_directory_is_not_enumerated(self):
        (self.root / "data").mkdir()
        with patch.object(Path, "iterdir", side_effect=AssertionError("directory enumerated")), \
             patch.object(Path, "glob", side_effect=AssertionError("directory globbed")), \
             patch.object(Path, "rglob", side_effect=AssertionError("directory scanned")):
            report = self.report(inputs=[("dir", "data")])
        self.assertEqual(self.rows(report)["PATH-001"]["status"], "pass")

    @unittest.skipUnless(os.name == "nt", "Windows UNC boundary")
    def test_unc_input_and_output_remain_unknown_without_network_probe(self):
        private = "\\\\preflight-invalid-host\\private-share\\secret.bin"
        report = self.report(inputs=[("file", private)], outputs=[("file", private)])
        rows = self.rows(report)
        for rule in ("PATH-001", "OUT-001", "OUT-002"):
            self.assertEqual(rows[rule]["status"], "unknown")
            self.assertFalse(rows[rule]["coverage_complete"])


if __name__ == "__main__":
    unittest.main()
