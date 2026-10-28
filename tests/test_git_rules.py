"""Synthetic Git rule behavior; no private repositories are used."""

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from ml_experiment_preflight import cli, git_rules
from ml_experiment_preflight.report import exit_code, validate_report


GIT = shutil.which("git")

PATH_PASS = {
    "rule_id": "PATH-001", "status": "pass", "severity": "none",
    "coverage_complete": True, "reason_code": None,
    "unknown_refs": [], "evidence": [],
}


@unittest.skipUnless(GIT, "git executable is not available")
class GitRuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.git_env = os.environ.copy()
        for key in tuple(self.git_env):
            if key.upper().startswith("GIT_"):
                self.git_env.pop(key, None)
        self.git_env.update({
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Synthetic",
            "GIT_AUTHOR_EMAIL": "synthetic@example.invalid",
            "GIT_COMMITTER_NAME": "Synthetic",
            "GIT_COMMITTER_EMAIL": "synthetic@example.invalid",
            "LC_ALL": "C",
        })

    def git(self, *args, cwd=None):
        result = subprocess.run(
            [GIT, *args], cwd=str(cwd or self.root), env=self.git_env,
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def make_files(self, entry="train.py"):
        entry_path = self.root / entry
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        entry_path.write_text("# synthetic\n", encoding="utf-8")
        (self.root / "input.bin").write_bytes(b"synthetic")
        (self.root / "runs").mkdir(exist_ok=True)

    def init_repo(self, entry="train.py", commit=True, add=True):
        self.make_files(entry)
        self.git("init", "-q")
        if add:
            self.git("add", entry)
        if commit:
            self.git("commit", "-qm", "init")
        return entry

    def run_report(self, entry="train.py"):
        args = [
            "check", "--root", str(self.root), "--entry", entry,
            "--input-file", "input.bin", "--output-file", "runs/out.bin",
            "--format", "json",
        ]
        report, _ = cli.run_check(args)
        validate_report(report)
        return {row["rule_id"]: row for row in report["results"]}, report

    def direct_rows(self, entry="train.py", path_row=None):
        path_row = PATH_PASS if path_row is None else path_row
        rows = git_rules.evaluate_git_rules(self.root, entry, path_row)
        return {row["rule_id"]: row for row in rows}

    def test_git_lookup_ignores_project_path_and_uses_absolute_external_path(self):
        trusted = Path(self.temp.name) / "trusted-bin"
        trusted.mkdir()
        name = "git.exe" if os.name == "nt" else "git"
        project_git = self.root / name
        trusted_git = trusted / name
        for path in (project_git, trusted_git):
            path.write_bytes(b"synthetic executable placeholder")
            path.chmod(0o755)
        with patch.dict(os.environ, {"PATH": os.pathsep.join((str(self.root), str(trusted)))}):
            selected = git_rules._find_git_executable(self.root)
        self.assertIsNotNone(selected)
        self.assertTrue(Path(selected).is_absolute())
        self.assertTrue(Path(selected).samefile(trusted_git))
        self.assertFalse(Path(selected).samefile(project_git))

    def test_git_lookup_project_path_only_is_unavailable(self):
        name = "git.exe" if os.name == "nt" else "git"
        project_git = self.root / name
        project_git.write_bytes(b"synthetic executable placeholder")
        project_git.chmod(0o755)
        with patch.dict(os.environ, {"PATH": str(self.root)}):
            self.assertIsNone(git_rules._find_git_executable(self.root))

    @staticmethod
    def snapshot(root):
        state = {}
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                digest = None
            state[rel] = (info.st_mode, info.st_size, info.st_mtime_ns, digest)
        return state

    def marker_script(self, name):
        script = Path(self.temp.name) / f"{name}.py"
        marker = Path(self.temp.name) / f"{name}.marker"
        script.write_text(
            "import pathlib, sys\n"
            "pathlib.Path(sys.argv[1]).write_text('ran ' + sys.argv[2])\n"
            "if sys.argv[2].startswith('filter'):\n"
            "    sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
            encoding="utf-8",
        )
        return script, marker

    def marker_command(self, script, marker, kind):
        return (
            f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}" '
            f'"{marker.as_posix()}" {kind}'
        )

    def shell_hook(self, path, script, marker, kind):
        path.write_text(
            "#!/bin/sh\n"
            f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}" '
            f'"{marker.as_posix()}" {kind}\n',
            encoding="utf-8",
        )
        os.chmod(path, 0o755)

    def test_clean_repository_all_six_rules_pass_and_exit_zero(self):
        self.init_repo()
        rows, report = self.run_report()
        self.assertEqual(rows["GIT-001"]["status"], "pass")
        self.assertEqual(rows["GIT-001"]["evidence"],
                         [{"code": "REPOSITORY_WITH_HEAD", "refs": ["root"]}])
        self.assertEqual(rows["GIT-002"]["status"], "pass")
        self.assertEqual(rows["GIT-002"]["evidence"],
                         [{"code": "ENTRY_UNCHANGED", "refs": ["entry"]}])
        self.assertEqual(rows["GIT-003"]["status"], "pass")
        self.assertEqual(rows["GIT-003"]["evidence"],
                         [{"code": "ENTRY_TRACKED", "refs": ["entry"]}])
        self.assertEqual(report["overall"], {
            "status": "clear", "finding_count": 0, "unknown_count": 0,
        })
        self.assertEqual(exit_code(report), 0)

    def test_no_repository_is_warning_and_context_is_unknown(self):
        self.make_files()
        rows, report = self.run_report()
        self.assertEqual((rows["GIT-001"]["status"], rows["GIT-001"]["severity"]),
                         ("finding", "warning"))
        self.assertEqual(rows["GIT-001"]["evidence"],
                         [{"code": "NO_REPOSITORY", "refs": ["root"]}])
        for rule in ("GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["status"], "unknown")
            self.assertEqual(rows[rule]["reason_code"], "GIT_CONTEXT_UNKNOWN")
        self.assertEqual(report["overall"], {
            "status": "incomplete", "finding_count": 1, "unknown_count": 2,
        })
        self.assertEqual(exit_code(report), 2)

    def test_no_head_is_warning_and_context_is_unknown(self):
        self.init_repo(commit=False, add=False)
        rows, report = self.run_report()
        self.assertEqual(rows["GIT-001"]["status"], "finding")
        self.assertEqual(rows["GIT-001"]["evidence"],
                         [{"code": "NO_HEAD", "refs": ["root"]}])
        for rule in ("GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["reason_code"], "GIT_CONTEXT_UNKNOWN")
        self.assertEqual(report["overall"]["finding_count"], 1)
        self.assertEqual(report["overall"]["unknown_count"], 2)

    def test_untracked_entry_is_git003_warning_and_git002_unknown(self):
        self.init_repo(entry="base.py")
        (self.root / "train.py").write_text("# synthetic\n", encoding="utf-8")
        rows, report = self.run_report(entry="train.py")
        self.assertEqual(rows["GIT-001"]["status"], "pass")
        self.assertEqual(rows["GIT-002"]["status"], "unknown")
        self.assertEqual(rows["GIT-002"]["reason_code"], "ENTRY_NOT_TRACKED")
        self.assertEqual(rows["GIT-002"]["unknown_refs"], ["entry"])
        self.assertEqual(rows["GIT-003"]["status"], "finding")
        self.assertEqual(rows["GIT-003"]["evidence"],
                         [{"code": "ENTRY_NOT_TRACKED", "refs": ["entry"]}])
        self.assertEqual(report["overall"], {
            "status": "incomplete", "finding_count": 1, "unknown_count": 1,
        })
        self.assertEqual(exit_code(report), 2)

    def test_modified_tracked_entry_is_warning_and_review(self):
        self.init_repo()
        (self.root / "train.py").write_text("# changed\n", encoding="utf-8")
        rows, report = self.run_report()
        self.assertEqual(rows["GIT-001"]["status"], "pass")
        self.assertEqual(rows["GIT-002"]["status"], "finding")
        self.assertEqual(rows["GIT-002"]["severity"], "warning")
        self.assertEqual(rows["GIT-002"]["evidence"],
                         [{"code": "ENTRY_CHANGED", "refs": ["entry"]}])
        self.assertEqual(rows["GIT-003"]["status"], "pass")
        self.assertEqual(report["overall"], {
            "status": "review", "finding_count": 1, "unknown_count": 0,
        })
        self.assertEqual(exit_code(report), 1)

    def test_staged_entry_change_is_warning(self):
        self.init_repo()
        (self.root / "train.py").write_text("# staged\n", encoding="utf-8")
        self.git("add", "train.py")
        rows, _ = self.run_report()
        self.assertEqual(rows["GIT-002"]["status"], "finding")
        self.assertEqual(rows["GIT-002"]["evidence"],
                         [{"code": "ENTRY_CHANGED", "refs": ["entry"]}])

    def test_other_files_and_untracked_data_do_not_affect_git002(self):
        self.init_repo()
        (self.root / "other.py").write_text("# other\n", encoding="utf-8")
        self.git("add", "other.py")
        self.git("commit", "-qm", "other")
        (self.root / "other.py").write_text("# changed other\n", encoding="utf-8")
        (self.root / "data.bin").write_bytes(b"untracked")
        rows, report = self.run_report()
        self.assertEqual(rows["GIT-002"]["status"], "pass")
        self.assertEqual(rows["GIT-003"]["status"], "pass")
        self.assertEqual(report["overall"]["status"], "clear")
        self.assertEqual(exit_code(report), 0)

    def test_assume_unchanged_entry_is_unknown_not_pass(self):
        self.init_repo()
        self.git("update-index", "--assume-unchanged", "train.py")
        (self.root / "train.py").write_text("# changed\n", encoding="utf-8")
        rows, _ = self.run_report()
        self.assertEqual(rows["GIT-002"]["status"], "unknown")
        self.assertEqual(rows["GIT-002"]["reason_code"], "GIT_ENTRY_FLAG_UNSUPPORTED")
        self.assertEqual(rows["GIT-003"]["status"], "pass")

    def test_skip_worktree_entry_is_unknown_not_pass(self):
        self.init_repo()
        self.git("update-index", "--skip-worktree", "train.py")
        (self.root / "train.py").write_text("# changed\n", encoding="utf-8")
        rows, _ = self.run_report()
        self.assertEqual(rows["GIT-002"]["status"], "unknown")
        self.assertEqual(rows["GIT-002"]["reason_code"], "GIT_ENTRY_FLAG_UNSUPPORTED")
        self.assertEqual(rows["GIT-003"]["status"], "pass")

    def test_core_ignorestat_is_overridden_and_change_is_detected(self):
        self.init_repo()
        (self.root / "train.py").write_text("# changed with different size\n", encoding="utf-8")
        self.git("config", "core.ignoreStat", "true")
        commands = []
        original = git_rules._run_process

        def recording(command, **kwargs):
            commands.append(list(command))
            return original(command, **kwargs)

        with patch.object(git_rules, "_run_process", recording):
            rows, _ = self.run_report()
        self.assertEqual(rows["GIT-002"]["status"], "finding")
        self.assertTrue(any("core.ignoreStat=false" in command for command in commands))

    def test_fsmonitor_config_is_neutralized(self):
        self.init_repo()
        self.git("config", "core.fsmonitor", str(Path(self.temp.name) / "missing-hook"))
        rows, report = self.run_report()
        self.assertEqual(rows["GIT-001"]["status"], "pass")
        self.assertEqual(rows["GIT-002"]["status"], "pass")
        self.assertEqual(rows["GIT-003"]["status"], "pass")
        self.assertEqual(report["overall"]["status"], "clear")

    def test_entry_with_space_and_unicode_is_handled(self):
        entry = "train script 模型.py"
        self.init_repo(entry=entry)
        (self.root / entry).write_text("# changed\n", encoding="utf-8")
        rows, _ = self.run_report(entry=entry)
        self.assertEqual(rows["GIT-002"]["status"], "finding")
        self.assertEqual(rows["GIT-003"]["status"], "pass")

    def test_corrupt_index_is_unknown_not_pass(self):
        self.init_repo()
        (self.root / ".git" / "index").write_bytes(b"garbage")
        rows = self.direct_rows()
        self.assertEqual(rows["GIT-001"]["status"], "pass")
        self.assertEqual(rows["GIT-002"]["status"], "unknown")
        self.assertEqual(rows["GIT-002"]["reason_code"], "GIT_ERROR")
        self.assertEqual(rows["GIT-003"]["status"], "unknown")
        self.assertEqual(rows["GIT-003"]["reason_code"], "GIT_ERROR")

    def test_unsupported_git_layout_is_unknown(self):
        self.make_files()
        (self.root / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
        rows = self.direct_rows()
        self.assertEqual(rows["GIT-001"]["status"], "unknown")
        self.assertEqual(rows["GIT-001"]["reason_code"], "UNSUPPORTED_GIT_LAYOUT")
        for rule in ("GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["reason_code"], "GIT_CONTEXT_UNKNOWN")

    def test_root_mismatch_is_unknown(self):
        self.init_repo()
        other = Path(self.temp.name) / "other"
        other.mkdir()
        self.git("config", "core.worktree", str(other))
        rows = self.direct_rows()
        self.assertEqual(rows["GIT-001"]["status"], "unknown")
        self.assertEqual(rows["GIT-001"]["reason_code"], "GIT_ROOT_MISMATCH")
        for rule in ("GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["reason_code"], "GIT_CONTEXT_UNKNOWN")

    def test_repository_root_alias_uses_file_identity(self):
        self.init_repo()
        alias = self.root.parent / "alternate-root-spelling"
        original_single_path = git_rules._single_path
        original_samefile = Path.samefile

        def alias_top(run):
            value = original_single_path(run)
            return str(alias) if value is not None else value

        def samefile(path, other):
            if path == alias and other == self.root:
                return True
            return original_samefile(path, other)

        with patch.object(git_rules, "_single_path", alias_top), \
             patch.object(Path, "samefile", samefile):
            rows = self.direct_rows()
        self.assertEqual(rows["GIT-001"]["status"], "pass")

    def test_repository_root_identity_denial_is_unknown(self):
        self.init_repo()
        alias = self.root.parent / "alternate-root-spelling"
        original_single_path = git_rules._single_path
        original_samefile = Path.samefile

        def alias_top(run):
            value = original_single_path(run)
            return str(alias) if value is not None else value

        def samefile(path, other):
            if path == alias and other == self.root:
                raise PermissionError("synthetic identity denied")
            return original_samefile(path, other)

        with patch.object(git_rules, "_single_path", alias_top), \
             patch.object(Path, "samefile", samefile):
            rows = self.direct_rows()
        self.assertEqual(rows["GIT-001"]["status"], "unknown")
        self.assertEqual(rows["GIT-001"]["reason_code"], "GIT_ERROR")

    def test_absolute_entry_alias_uses_resolved_parent_for_pathspec(self):
        self.init_repo(entry="src/train.py")
        absolute = str(self.root / "src" / "train.py")
        original_relpath = git_rules.os.path.relpath
        calls = []

        def short_name_mismatch(path, start):
            calls.append((path, start))
            if len(calls) == 1:
                return os.path.join("..", "different-spelling", "src", "train.py")
            return original_relpath(path, start)

        with patch.object(git_rules.os.path, "relpath", short_name_mismatch):
            pathspec = git_rules._entry_pathspec(self.root, absolute)
        self.assertEqual(pathspec, "src/train.py")

    def test_subdirectory_root_does_not_search_parent_repository(self):
        self.init_repo()
        sub = self.root / "sub"
        sub.mkdir()
        rows = {row["rule_id"]: row for row in git_rules.evaluate_git_rules(
            sub, "train.py", PATH_PASS)}
        self.assertEqual(rows["GIT-001"]["status"], "finding")
        self.assertEqual(rows["GIT-001"]["evidence"],
                         [{"code": "NO_REPOSITORY", "refs": ["root"]}])

    def test_unavailable_entry_skips_entry_git_commands(self):
        self.init_repo()
        for code in ("ENTRY_MISSING", "TYPE_MISMATCH", "ENTRY_ESCAPES_ROOT"):
            with self.subTest(code=code):
                path_row = {
                    "rule_id": "PATH-001", "status": "finding", "severity": "critical",
                    "coverage_complete": True, "reason_code": None, "unknown_refs": [],
                    "evidence": [{"code": code, "refs": ["entry"]}],
                }
                rows = self.direct_rows(path_row=path_row)
                self.assertEqual(rows["GIT-001"]["status"], "pass")
                for rule in ("GIT-002", "GIT-003"):
                    self.assertEqual(rows[rule]["status"], "unknown")
                    self.assertEqual(rows[rule]["reason_code"], "ENTRY_UNAVAILABLE")

    def test_missing_git_executable_is_unknown_not_pass(self):
        self.init_repo()
        with patch.object(git_rules, "_find_git_executable", return_value=None):
            rows = self.direct_rows()
        self.assertEqual(rows["GIT-001"]["status"], "unknown")
        self.assertEqual(rows["GIT-001"]["reason_code"], "GIT_UNAVAILABLE")
        for rule in ("GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["reason_code"], "GIT_CONTEXT_UNKNOWN")

    def test_git_timeout_is_unknown_not_pass(self):
        self.init_repo()
        with patch.object(git_rules, "_run_process",
                          return_value=git_rules.GitRun(None, failure="timeout")):
            rows = self.direct_rows()
        self.assertEqual(rows["GIT-001"]["status"], "unknown")
        self.assertEqual(rows["GIT-001"]["reason_code"], "GIT_TIMEOUT")
        for rule in ("GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["reason_code"], "GIT_CONTEXT_UNKNOWN")

    def test_excessive_git_output_is_unknown_not_pass(self):
        self.init_repo()
        with patch.object(git_rules, "_run_process",
                          return_value=git_rules.GitRun(0, failure="output_limit")):
            rows = self.direct_rows()
        self.assertEqual(rows["GIT-001"]["status"], "unknown")
        self.assertEqual(rows["GIT-001"]["reason_code"], "GIT_ERROR")
        for rule in ("GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["reason_code"], "GIT_CONTEXT_UNKNOWN")

    def test_git_argv_is_fixed_and_shell_is_disabled(self):
        self.init_repo()
        calls = []
        original = subprocess.Popen

        def recording(command, **kwargs):
            calls.append((list(command), dict(kwargs)))
            return original(command, **kwargs)

        with patch.object(git_rules.subprocess, "Popen", recording):
            rows = self.direct_rows()
        self.assertEqual(rows["GIT-001"]["status"], "pass")
        self.assertTrue(calls)
        for command, kwargs in calls:
            self.assertIs(kwargs.get("shell"), False)
            self.assertIn("--no-optional-locks", command)
            self.assertIn("--no-lazy-fetch", command)
            self.assertIn("--literal-pathspecs", command)
            self.assertIn("--no-pager", command)
            self.assertIn("-C", command)
            self.assertIn(str(self.root), command)
            self.assertIn("core.fsmonitor=false", command)
            self.assertIn("core.ignoreStat=false", command)
            self.assertIn("core.untrackedCache=false", command)
            self.assertFalse({"fetch", "pull", "clone", "remote", "submodule"} & set(command))

    def test_inherited_git_dir_is_ignored(self):
        self.init_repo()
        other = Path(self.temp.name) / "other"
        other.mkdir()
        self.git("init", "-q", cwd=other)
        (other / "other.py").write_text("# other\n", encoding="utf-8")
        self.git("add", "other.py", cwd=other)
        self.git("commit", "-qm", "other", cwd=other)
        with patch.dict(os.environ, {"GIT_DIR": str(other / ".git")}):
            rows, report = self.run_report()
        for rule in ("GIT-001", "GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["status"], "pass")
        self.assertEqual(report["overall"]["status"], "clear")

    def test_nested_and_absolute_entry_paths_are_handled(self):
        entry = "src/train.py"
        self.init_repo(entry=entry)
        (self.root / entry).write_text("# changed\n", encoding="utf-8")
        for value in (entry, str(self.root / entry)):
            with self.subTest(value=value):
                rows, _ = self.run_report(entry=value)
                self.assertEqual(rows["GIT-002"]["status"], "finding")
                self.assertEqual(rows["GIT-003"]["status"], "pass")

    def test_git002_output_limit_is_unknown(self):
        self.init_repo()
        original = git_rules._run_process

        def fake(command, **kwargs):
            if "status" in command:
                return git_rules.GitRun(0, failure="output_limit")
            return original(command, **kwargs)

        with patch.object(git_rules, "_run_process", fake):
            rows = self.direct_rows()
        self.assertEqual(rows["GIT-002"]["status"], "unknown")
        self.assertEqual(rows["GIT-002"]["reason_code"], "GIT_OUTPUT_LIMIT")
        self.assertEqual(rows["GIT-003"]["status"], "pass")

    def test_git003_tracking_output_limit_is_unknown(self):
        self.init_repo()
        original = git_rules._run_process

        def fake(command, **kwargs):
            if "ls-files" in command and "--cached" in command:
                return git_rules.GitRun(0, failure="output_limit")
            return original(command, **kwargs)

        with patch.object(git_rules, "_run_process", fake):
            rows = self.direct_rows()
        self.assertEqual(rows["GIT-002"]["status"], "unknown")
        self.assertEqual(rows["GIT-002"]["reason_code"], "GIT_OUTPUT_LIMIT")
        self.assertEqual(rows["GIT-003"]["status"], "unknown")
        self.assertEqual(rows["GIT-003"]["reason_code"], "GIT_ERROR")

    def test_status_stderr_error_is_unknown_not_pass(self):
        self.init_repo()
        original = git_rules._run_process

        def fake(command, **kwargs):
            if "status" in command:
                return git_rules.GitRun(
                    0, stdout=b"", stderr=b"error: synthetic helper failure\n"
                )
            return original(command, **kwargs)

        with patch.object(git_rules, "_run_process", fake):
            rows = self.direct_rows()
        self.assertEqual(rows["GIT-002"]["status"], "unknown")
        self.assertEqual(rows["GIT-002"]["reason_code"], "GIT_ERROR")
        self.assertEqual(rows["GIT-003"]["status"], "pass")

    def test_unmerged_index_is_unknown_not_pass(self):
        self.init_repo()
        self.git("checkout", "-b", "other")
        (self.root / "train.py").write_text("# other\n", encoding="utf-8")
        self.git("add", "train.py")
        self.git("commit", "-qm", "other")
        self.git("checkout", "-")
        (self.root / "train.py").write_text("# main\n", encoding="utf-8")
        self.git("add", "train.py")
        self.git("commit", "-qm", "main")
        merge = subprocess.run(
            [GIT, "merge", "other"], cwd=str(self.root), env=self.git_env,
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        self.assertNotEqual(merge.returncode, 0)
        rows, _ = self.run_report()
        self.assertEqual(rows["GIT-002"]["status"], "unknown")
        self.assertEqual(rows["GIT-002"]["reason_code"], "GIT_ERROR")
        self.assertEqual(rows["GIT-003"]["status"], "pass")

    def test_repository_root_with_space_and_unicode(self):
        root = Path(self.temp.name) / "repo space 项目"
        root.mkdir()
        self.git("init", "-q", cwd=root)
        (root / "train.py").write_text("# synthetic\n", encoding="utf-8")
        self.git("add", "train.py", cwd=root)
        self.git("commit", "-qm", "init", cwd=root)
        rows = {row["rule_id"]: row for row in git_rules.evaluate_git_rules(
            root, "train.py", PATH_PASS)}
        for rule in ("GIT-001", "GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["status"], "pass")

    def test_git002_timeout_is_unknown_not_pass(self):
        self.init_repo()
        original = git_rules._run_process

        def fake(command, **kwargs):
            if "status" in command:
                return git_rules.GitRun(None, failure="timeout")
            return original(command, **kwargs)

        with patch.object(git_rules, "_run_process", fake):
            rows = self.direct_rows()
        self.assertEqual(rows["GIT-002"]["status"], "unknown")
        self.assertEqual(rows["GIT-002"]["reason_code"], "GIT_TIMEOUT")
        self.assertEqual(rows["GIT-003"]["status"], "pass")

    def test_bounded_capture_keeps_normal_output(self):
        result = git_rules._run_process(
            [sys.executable, "-B", "-c",
             "import sys; sys.stdout.write('hello'); sys.stderr.write('err')"],
            timeout=5, max_output=1024, env=os.environ.copy(),
        )
        self.assertIsNone(result.failure)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"hello")
        self.assertEqual(result.stderr, b"err")

    def test_bounded_capture_aborts_large_stdout(self):
        script = (
            "import sys,time; sys.stdout.write('x'*(2*1024*1024)); "
            "sys.stdout.flush(); time.sleep(10)"
        )
        started = time.monotonic()
        result = git_rules._run_process(
            [sys.executable, "-B", "-c", script],
            timeout=5, max_output=1024 * 1024, env=os.environ.copy(),
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result.failure, "output_limit")
        self.assertLess(elapsed, 4.0)

    def test_bounded_capture_aborts_large_stderr(self):
        script = (
            "import sys,time; sys.stderr.write('y'*(2*1024*1024)); "
            "sys.stderr.flush(); time.sleep(10)"
        )
        started = time.monotonic()
        result = git_rules._run_process(
            [sys.executable, "-B", "-c", script],
            timeout=5, max_output=1024 * 1024, env=os.environ.copy(),
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result.failure, "output_limit")
        self.assertLess(elapsed, 4.0)

    def test_bounded_capture_handles_both_streams_without_deadlock(self):
        script = (
            "import sys,time; "
            "sys.stdout.write('o'*600000); sys.stdout.flush(); "
            "sys.stderr.write('e'*600000); sys.stderr.flush(); time.sleep(10)"
        )
        started = time.monotonic()
        result = git_rules._run_process(
            [sys.executable, "-B", "-c", script],
            timeout=5, max_output=1000, env=os.environ.copy(),
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result.failure, "output_limit")
        self.assertLess(elapsed, 4.0)

    def test_bounded_capture_timeout_kills_process(self):
        started = time.monotonic()
        result = git_rules._run_process(
            [sys.executable, "-B", "-c", "import time; time.sleep(10)"],
            timeout=0.3, max_output=1024, env=os.environ.copy(),
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result.failure, "timeout")
        self.assertLess(elapsed, 3.0)

    def test_bounded_capture_kills_process_before_late_output(self):
        marker = Path(self.temp.name) / "late-output.marker"
        script = (
            "import pathlib, sys, time\n"
            "sys.stdout.write('x' * (2 * 1024 * 1024))\n"
            "sys.stdout.flush()\n"
            "time.sleep(1.0)\n"
            f"pathlib.Path({str(marker)!r}).write_text('late')\n"
        )
        result = git_rules._run_process(
            [sys.executable, "-B", "-c", script],
            timeout=5, max_output=1024 * 1024, env=os.environ.copy(),
        )
        time.sleep(1.2)
        self.assertEqual(result.failure, "output_limit")
        self.assertFalse(marker.exists(), "killed process continued running")

    def test_bounded_capture_buffer_never_exceeds_limit(self):
        capture = git_rules._BoundedCapture(10)
        capture.add("stdout", b"a" * 6)
        capture.add("stderr", b"b" * 6)
        self.assertTrue(capture.overflow.is_set())
        self.assertEqual(
            len(capture.bytes("stdout")) + len(capture.bytes("stderr")), 10
        )

    def test_filter_commands_are_not_triggered_by_checker(self):
        self.init_repo()
        script, marker = self.marker_script("filter")
        (self.root / ".gitattributes").write_text("*.py filter=marker\n", encoding="utf-8")
        self.git("config", "filter.marker.clean",
                 self.marker_command(script, marker, "filter-clean"))
        self.git("config", "filter.marker.smudge",
                 self.marker_command(script, marker, "filter-smudge"))
        (self.root / "train.py").write_text("# filter trigger\n", encoding="utf-8")
        self.git("add", "--renormalize", "train.py")
        self.assertTrue(marker.exists(), "marker harness did not run for filter clean")
        marker.unlink()
        (self.root / "train.py").unlink()
        self.git("checkout", "--", "train.py")
        self.assertTrue(marker.exists(), "marker harness did not run for filter smudge")
        marker.unlink()
        (self.root / "train.py").write_text("# changed after trigger\n", encoding="utf-8")
        rows, _ = self.run_report()
        self.assertFalse(marker.exists(), "checker triggered a filter command")
        self.assertEqual(rows["GIT-002"]["status"], "finding")

    def test_external_diff_commands_are_not_triggered_by_checker(self):
        self.init_repo()
        script, marker = self.marker_script("external")
        self.git("config", "diff.external",
                 self.marker_command(script, marker, "external"))
        (self.root / "train.py").write_text("# external trigger\n", encoding="utf-8")
        self.git("diff", "--", "train.py")
        self.assertTrue(marker.exists(), "marker harness did not run for external diff")
        marker.unlink()
        rows, _ = self.run_report()
        self.assertFalse(marker.exists(), "checker triggered external diff")
        self.assertEqual(rows["GIT-002"]["status"], "finding")

    def test_textconv_commands_are_not_triggered_by_checker(self):
        self.init_repo()
        script, marker = self.marker_script("textconv")
        (self.root / ".gitattributes").write_text("*.py diff=marker\n", encoding="utf-8")
        self.git("config", "diff.marker.textconv",
                 self.marker_command(script, marker, "textconv"))
        (self.root / "train.py").write_text("# textconv trigger\n", encoding="utf-8")
        self.git("diff", "--textconv", "--", "train.py")
        self.assertTrue(marker.exists(), "marker harness did not run for textconv")
        marker.unlink()
        rows, _ = self.run_report()
        self.assertFalse(marker.exists(), "checker triggered textconv")
        self.assertEqual(rows["GIT-002"]["status"], "finding")

    def test_fsmonitor_hook_is_not_triggered_by_checker(self):
        self.init_repo()
        script, marker = self.marker_script("fsmonitor")
        hook = Path(self.temp.name) / "fsmonitor.sh"
        self.shell_hook(hook, script, marker, "fsmonitor")
        self.git("config", "core.fsmonitor", hook.as_posix())
        self.git("status", "--porcelain")
        self.assertTrue(marker.exists(), "marker harness did not run for FSMonitor")
        marker.unlink()
        rows, report = self.run_report()
        self.assertFalse(marker.exists(), "checker triggered FSMonitor hook")
        for rule in ("GIT-001", "GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["status"], "pass")
        self.assertEqual(report["overall"]["status"], "clear")

    def test_hooks_are_not_triggered_by_checker(self):
        self.init_repo()
        script, marker = self.marker_script("hook")
        hooks = Path(self.temp.name) / "hooks"
        hooks.mkdir()
        self.shell_hook(hooks / "pre-commit", script, marker, "hook")
        self.git("config", "core.hooksPath", hooks.as_posix())
        self.git("commit", "--allow-empty", "-qm", "hook trigger")
        self.assertTrue(marker.exists(), "marker harness did not run for hooks")
        marker.unlink()
        rows, report = self.run_report()
        self.assertFalse(marker.exists(), "checker triggered a hook")
        for rule in ("GIT-001", "GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["status"], "pass")
        self.assertEqual(report["overall"]["status"], "clear")

    def test_rule_execution_does_not_modify_worktree_or_index(self):
        self.init_repo()
        before = self.snapshot(self.root)
        self.run_report()
        after = self.snapshot(self.root)
        self.assertEqual(before, after)

        (self.root / "train.py").write_text("# changed\n", encoding="utf-8")
        before = self.snapshot(self.root)
        self.run_report()
        after = self.snapshot(self.root)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
