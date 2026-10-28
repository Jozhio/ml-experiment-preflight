"""Contract tests using only synthetic paths and the Python standard library."""

import ctypes
import json
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


RULE_IDS = ["GIT-001", "GIT-002", "GIT-003", "PATH-001", "OUT-001", "OUT-002"]
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "train.py").write_text("# synthetic entry\n", encoding="utf-8")
        (self.root / "input.bin").write_bytes(b"synthetic")
        self.base_args = [
            "check", "--root", str(self.root), "--entry", "train.py",
            "--input-file", "input.bin", "--output-file", "output.bin",
        ]

    def run_cli(self, *args):
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = str(PROJECT / "src")
        return subprocess.run(
            [sys.executable, "-B", "-m", "ml_experiment_preflight", *args],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_json_skeleton_is_explicitly_incomplete_and_redacted(self):
        result = self.run_cli(*self.base_args, "--format", "json")
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["schema_version"], "1.0")
        self.assertEqual(report["overall"], {
            "status": "incomplete", "finding_count": 1, "unknown_count": 2,
        })
        self.assertEqual([row["rule_id"] for row in report["results"]], RULE_IDS)
        git001, git002, git003 = report["results"][:3]
        self.assertEqual(git001["status"], "finding")
        self.assertEqual(git001["severity"], "warning")
        self.assertTrue(git001["coverage_complete"])
        self.assertIsNone(git001["reason_code"])
        self.assertEqual(git001["unknown_refs"], [])
        self.assertEqual(git001["evidence"], [{"code": "NO_REPOSITORY", "refs": ["root"]}])
        for row in (git002, git003):
            self.assertEqual(row["status"], "unknown")
            self.assertEqual(row["severity"], "none")
            self.assertFalse(row["coverage_complete"])
            self.assertEqual(row["reason_code"], "GIT_CONTEXT_UNKNOWN")
            self.assertEqual(row["unknown_refs"], ["entry"])
            self.assertEqual(row["evidence"], [])
        for row in report["results"][3:]:
            self.assertEqual(row["status"], "pass")
            self.assertTrue(row["coverage_complete"])
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        for filename in ("train.py", "input.bin", "output.bin"):
            self.assertNotIn(filename, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")

    def test_missing_required_input_is_usage_error_without_path_leak(self):
        result = self.run_cli(
            "check", "--root", str(self.root), "--entry", "train.py",
            "--output-file", "output.bin", "--format", "json",
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("USAGE_ERROR", result.stderr)
        self.assertNotIn(str(self.root), result.stderr)
        self.assertNotIn("output.bin", result.stderr)

    def test_entry_outside_root_is_usage_error_without_echo(self):
        secret = str(self.root.parent / "private-entry.py")
        args = self.base_args.copy()
        args[args.index("--entry") + 1] = secret
        result = self.run_cli(*args, "--format", "json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("USAGE_ERROR\n"))
        self.assertIn("usage:", result.stderr)
        self.assertNotIn(secret, result.stderr)

    def test_absolute_entry_alias_is_accepted_when_physical_path_is_inside_root(self):
        from ml_experiment_preflight import cli

        entry = str(self.root / "train.py")
        args = self.base_args.copy()
        args[args.index("--entry") + 1] = entry
        original_lexical = cli._lexical_path

        def short_name_lexical_mismatch(root, raw):
            if raw == entry:
                return str(self.root.parent / "alternate-root-spelling" / "train.py")
            return original_lexical(root, raw)

        with patch.object(cli, "_lexical_path", short_name_lexical_mismatch), \
                patch.object(cli, "_short_alias_parent", return_value=True):
            report, _ = cli.run_check(args)
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["PATH-001"]["status"], "pass")

    @unittest.skipUnless(os.name == "nt", "Windows short-path alias semantics")
    def test_short_alias_parent_predicate_boundaries(self):
        from ml_experiment_preflight import cli

        drive = os.environ.get("SystemDrive", "C:")
        root = Path(drive + r"\preflight-clean-root")
        other_drive = "Z:" if root.drive.upper() != "Z:" else "Y:"
        self.assertTrue(cli._short_alias_parent(
            root, Path(drive + r"\Users\RUNNER~1\proj\train.py")))
        self.assertFalse(cli._short_alias_parent(
            root, Path(drive + r"\Users\runneradmin\proj\train.py")))
        self.assertFalse(cli._short_alias_parent(root, Path(r"SUB~1\train.py")))
        self.assertFalse(cli._short_alias_parent(
            root, Path(other_drive + r"\RUNNER~1\proj\train.py")))
        self.assertFalse(cli._short_alias_parent(
            root, Path(r"\\server\share\RUNNER~1\train.py")))
        self.assertFalse(cli._short_alias_parent(root, Path(str(root / "TRAIN~1.PY"))))

    @unittest.skipUnless(os.name == "nt", "Windows 8.3 alias")
    def test_real_8_3_parent_alias_is_accepted_when_inside_root(self):
        from ml_experiment_preflight import cli

        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetShortPathNameW(
            str(self.root), buffer, len(buffer))
        if not length:
            self.skipTest("GetShortPathNameW failed")
        short_root = buffer.value
        if os.path.normcase(short_root) == os.path.normcase(str(self.root)):
            self.skipTest("8.3 short names are unavailable on this volume")
        args = self.base_args.copy()
        args[args.index("--entry") + 1] = str(Path(short_root) / "train.py")
        report, _ = cli.run_check(args)
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["PATH-001"]["status"], "pass")

    @unittest.skipUnless(os.name == "nt", "Windows short-path alias semantics")
    def test_tilde_parent_outside_root_is_rejected_without_echo(self):
        from ml_experiment_preflight import cli

        temp = tempfile.TemporaryDirectory(
            prefix="outside~1.", dir=str(self.root.parent))
        self.addCleanup(temp.cleanup)
        outside = Path(temp.name)
        (outside / "train.py").write_text("# synthetic\n", encoding="utf-8")
        secret = str(outside / "train.py")
        args = self.base_args.copy()
        args[args.index("--entry") + 1] = secret
        with self.assertRaises(cli.UsageError):
            cli.run_check(args)
        result = self.run_cli(*args, "--format", "json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("USAGE_ERROR\n"))
        self.assertNotIn(secret, result.stderr)

    def test_duplicate_output_is_usage_error(self):
        result = self.run_cli(
            *self.base_args, "--output-file", os.path.join(".", "output.bin"), "--format", "json"
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("USAGE_ERROR", result.stderr)

    def test_repeated_root_or_entry_is_usage_error_instead_of_last_value_wins(self):
        for option, value in (("--root", str(self.root)), ("--entry", "train.py")):
            with self.subTest(option=option):
                result = self.run_cli(*self.base_args, option, value, "--format", "json")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("USAGE_ERROR", result.stderr)

    def test_empty_root_and_entry_and_wildcard_entry_are_usage_errors(self):
        for option, value in (("--root", ""), ("--entry", ""), ("--entry", "*.py")):
            with self.subTest(option=option, value=value):
                args = self.base_args.copy()
                args[args.index(option) + 1] = value
                result = self.run_cli(*args, "--format", "json")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("USAGE_ERROR", result.stderr)

    def test_pending_refs_cover_all_explicit_targets(self):
        result = self.run_cli(
            *self.base_args,
            "--input-file", "other.bin", "--output-file", "other.out",
            "--format", "json",
        )
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["GIT-001"]["status"], "finding")
        self.assertEqual(rows["GIT-001"]["unknown_refs"], [])
        self.assertEqual(rows["GIT-002"]["unknown_refs"], ["entry"])
        self.assertEqual(rows["GIT-003"]["unknown_refs"], ["entry"])
        self.assertEqual(rows["PATH-001"]["status"], "finding")
        self.assertEqual(rows["PATH-001"]["evidence"][0], {
            "code": "INPUT_MISSING", "refs": ["input:2"],
        })
        self.assertEqual(rows["OUT-001"]["status"], "pass")
        self.assertEqual(rows["OUT-002"]["status"], "unknown")
        self.assertEqual(rows["OUT-002"]["unknown_refs"], ["input:2"])

    def test_default_text_reports_incomplete_without_paths(self):
        result = self.run_cli(*self.base_args)
        self.assertEqual(result.returncode, 2)
        self.assertIn("incomplete", result.stdout)
        self.assertIn("GIT-001", result.stdout)
        self.assertNotIn(str(self.root), result.stdout + result.stderr)

    def test_internal_error_is_visible_to_direct_caller_but_redacted_at_cli(self):
        from ml_experiment_preflight import cli

        secret = str(self.root / "private-trace.txt")
        with patch.object(cli, "evaluate_git_rules", side_effect=RuntimeError(secret)):
            with self.assertRaisesRegex(RuntimeError, "private-trace"):
                cli.run_check(self.base_args)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli.main(self.base_args)
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "REPORT_ERROR\n")
        self.assertNotIn(secret, stderr.getvalue())

    def test_invalid_root_path_value_is_redacted_usage_error(self):
        from ml_experiment_preflight import cli

        args = self.base_args.copy()
        args[args.index("--root") + 1] = "invalid\x00root"
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(args)
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(stderr.getvalue().startswith("USAGE_ERROR\n"))
        self.assertIn("usage:", stderr.getvalue())
        self.assertNotIn("invalid", stderr.getvalue())

    def test_nul_in_each_user_path_is_usage_error_for_direct_caller(self):
        from ml_experiment_preflight import cli

        for option in ("--root", "--entry", "--input-file", "--input-dir",
                       "--output-file", "--output-dir"):
            with self.subTest(option=option):
                args = self.base_args.copy()
                if option in args:
                    args[args.index(option) + 1] = "private\x00value"
                else:
                    args.extend((option, "private\x00value"))
                with self.assertRaises(cli.UsageError):
                    cli.run_check(args)

    @unittest.skipUnless(os.name == "nt", "Windows drive-relative syntax")
    def test_drive_relative_and_rooted_without_drive_paths_are_usage_errors(self):
        from ml_experiment_preflight import cli

        for option in ("--root", "--entry", "--input-file", "--output-file"):
            for raw in ("C:private.bin", "\\private.bin"):
                with self.subTest(option=option, raw=raw):
                    args = self.base_args.copy()
                    args[args.index(option) + 1] = raw
                    with self.assertRaises(cli.UsageError):
                        cli.run_check(args)

    def test_root_resolution_os_error_is_redacted_usage_error(self):
        from ml_experiment_preflight import cli

        for failure in (OSError(123, "private path"), RuntimeError("private loop")):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(cli.Path, "resolve", side_effect=failure):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        code = cli.main(self.base_args)
                self.assertEqual(code, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertTrue(stderr.getvalue().startswith("USAGE_ERROR\n"))
                self.assertNotIn("private", stderr.getvalue())

    def test_unrelated_absolute_entry_is_rejected_without_resolving_it(self):
        from ml_experiment_preflight import cli

        private_entry = str(self.root.parent / "unrelated-place" / "entry.py")
        args = self.base_args.copy()
        args[args.index("--entry") + 1] = private_entry
        original = cli.Path.resolve
        resolved_entries = []

        def guarded_resolve(path, *positional, **keyword):
            if str(path) == private_entry:
                resolved_entries.append(str(path))
                raise AssertionError("external entry must not be resolved")
            return original(path, *positional, **keyword)

        with patch.object(cli.Path, "resolve", guarded_resolve):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli.main(args)
        self.assertEqual(code, 2)
        self.assertEqual(resolved_entries, [])
        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(stderr.getvalue().startswith("USAGE_ERROR\n"))
        self.assertNotIn(private_entry, stderr.getvalue())

    @unittest.skipUnless(os.name == "nt", "Windows UNC syntax")
    def test_unc_entry_is_rejected_without_resolving_it(self):
        from ml_experiment_preflight import cli

        private_entry = r"\\server\share\PRIVATE~1\entry.py"
        args = self.base_args.copy()
        args[args.index("--entry") + 1] = private_entry
        original = cli.Path.resolve
        resolved_entries = []

        def guarded_resolve(path, *positional, **keyword):
            if str(path) == private_entry:
                resolved_entries.append(str(path))
                raise AssertionError("UNC entry must not be resolved")
            return original(path, *positional, **keyword)

        with patch.object(cli.Path, "resolve", guarded_resolve):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli.main(args)
        self.assertEqual(code, 2)
        self.assertEqual(resolved_entries, [])
        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(stderr.getvalue().startswith("USAGE_ERROR\n"))
        self.assertNotIn(private_entry, stderr.getvalue())

    @unittest.skipUnless(os.name == "nt", "Windows UNC syntax")
    def test_unc_root_is_rejected_without_resolving_it(self):
        from ml_experiment_preflight import cli

        private_root = r"\\server\share\project"
        args = self.base_args.copy()
        args[args.index("--root") + 1] = private_root
        with patch.object(cli.Path, "resolve", side_effect=AssertionError("must not resolve")):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli.main(args)
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(stderr.getvalue().startswith("USAGE_ERROR\n"))
        self.assertNotIn(private_root, stderr.getvalue())

    @unittest.skipUnless(os.name == "nt", "Windows path syntax")
    def test_invalid_windows_root_syntax_is_redacted_usage_error(self):
        args = self.base_args.copy()
        private_root = "C:\\private<invalid"
        args[args.index("--root") + 1] = private_root
        result = self.run_cli(*args, "--format", "json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("USAGE_ERROR\n"))
        self.assertNotIn(private_root, result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows drive boundary")
    def test_entry_on_other_drive_is_usage_error_without_echo(self):
        other_drive = "Z:" if self.root.drive.upper() != "Z:" else "C:"
        private_entry = other_drive + "\\private-entry.py"
        args = self.base_args.copy()
        args[args.index("--entry") + 1] = private_entry
        result = self.run_cli(*args, "--format", "json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("USAGE_ERROR\n"))
        self.assertNotIn(private_entry, result.stderr)

    def test_internal_path_value_error_is_report_error_not_usage_error(self):
        from ml_experiment_preflight import cli

        with patch.object(cli, "_lexical_path", side_effect=ValueError("private internal defect")):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli.main(self.base_args)
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "REPORT_ERROR\n")


if __name__ == "__main__":
    unittest.main()
