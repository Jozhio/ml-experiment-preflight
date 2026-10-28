"""Installed-CLI end-to-end, safety and Windows path scenarios."""

import hashlib
import json
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

from ml_experiment_preflight.report import exit_code, validate_report


RULE_IDS = ["GIT-001", "GIT-002", "GIT-003", "PATH-001", "OUT-001", "OUT-002"]
GIT = shutil.which("git")


class AclSandboxError(RuntimeError):
    """ACL restoration or cleanup failed; the diagnostic path is retained."""


class AclSandbox:
    """Own a uniquely named temp ACL directory and clean it explicitly.

    The sandbox is deliberately outside any TemporaryDirectory.  close()
    restores the deny ACE, checks icacls' exit code, verifies access, then
    removes only this sandbox.  On failure it raises with diagnostics and
    leaves the directory for inspection; cleanup errors are never ignored.
    """

    PREFIX = "ml-experiment-preflight-m3a-acl-"
    # Deny read/execute so metadata access fails, but do not deny WRITE_DAC.
    # This lets restore remove the ACE without admin/bypass.
    DENY_RIGHTS = "(OI)(CI)(RX)"

    def __init__(self, principal):
        self.principal = principal
        self.path = Path(tempfile.mkdtemp(prefix=self.PREFIX))
        (self.path / "secret.bin").write_bytes(b"synthetic denied input")

    def _icacls(self, *args):
        return subprocess.run(
            ["icacls", *map(str, args)], capture_output=True, check=False
        )

    def _diag(self, action, result):
        return (
            f"icacls {action} failed rc={result.returncode} path={self.path} "
            f"stderr={result.stderr.decode('utf-8', 'replace')[:500]!r}"
        )

    def deny(self):
        result = self._icacls(
            self.path, "/deny", f"{self.principal}:{self.DENY_RIGHTS}"
        )
        if result.returncode != 0:
            raise AclSandboxError(self._diag("deny", result))

    def _verify_access(self):
        try:
            with os.scandir(self.path) as entries:
                list(entries)
            (self.path / "secret.bin").stat()
            self.path.resolve(strict=True)
        except OSError as error:
            raise AclSandboxError(
                f"ACL restore reported success but access still fails at "
                f"{self.path}: {error!r}"
            ) from error

    def restore(self):
        result = self._icacls(self.path, "/remove:d", self.principal)
        if result.returncode != 0:
            raise AclSandboxError(self._diag("remove", result))
        self._verify_access()

    def close(self):
        self.restore()
        try:
            shutil.rmtree(self.path)
        except OSError as error:
            raise AclSandboxError(
                f"ACL restored but sandbox cleanup failed at {self.path}: "
                f"{error!r}"
            ) from error
        if self.path.exists():
            raise AclSandboxError(
                f"cleanup reported success but sandbox remains: {self.path}"
            )


class AclSandboxCleanupTests(unittest.TestCase):
    def make_sandbox(self):
        # Exercise cleanup ordering without constructing an ACL sandbox or
        # changing permissions on the host.
        temp = tempfile.TemporaryDirectory(prefix="preflight-acl-mock-")
        self.addCleanup(temp.cleanup)
        sandbox = object.__new__(AclSandbox)
        sandbox.principal = "synthetic-principal"
        sandbox.path = Path(temp.name) / "sandbox"
        sandbox.path.mkdir()
        (sandbox.path / "secret.bin").write_bytes(b"synthetic")
        return sandbox

    def test_restore_runs_before_removal(self):
        sandbox = self.make_sandbox()
        calls = []
        original_rmtree = shutil.rmtree

        def fake_rmtree(path, *args, **kwargs):
            calls.append("rmtree")
            return original_rmtree(path, *args, **kwargs)

        with patch.object(sandbox, "restore",
                          side_effect=lambda: calls.append("restore")), \
             patch.object(shutil, "rmtree", fake_rmtree):
            sandbox.close()
        self.assertEqual(calls, ["restore", "rmtree"])
        self.assertFalse(sandbox.path.exists())

    def test_restore_failure_is_loud_and_keeps_sandbox(self):
        sandbox = self.make_sandbox()
        failed = subprocess.CompletedProcess(
            ["icacls"], 5, stdout=b"", stderr=b"denied"
        )
        with patch.object(sandbox, "_icacls", return_value=failed):
            with self.assertRaises(AclSandboxError) as raised:
                sandbox.close()
        self.assertIn("rc=5", str(raised.exception))
        self.assertIn(str(sandbox.path), str(raised.exception))
        self.assertTrue(sandbox.path.exists())

    def test_restore_verification_failure_is_loud_and_keeps_sandbox(self):
        sandbox = self.make_sandbox()
        ok = subprocess.CompletedProcess(["icacls"], 0, stdout=b"", stderr=b"")
        with patch.object(sandbox, "_icacls", return_value=ok), \
             patch.object(sandbox, "_verify_access",
                          side_effect=AclSandboxError("still denied")):
            with self.assertRaises(AclSandboxError):
                sandbox.close()
        self.assertTrue(sandbox.path.exists())


@unittest.skipUnless(GIT, "git executable is not available")
class InstalledCliM3ATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install_temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.install_temp.cleanup)
        base = Path(cls.install_temp.name)
        target = base / "packages"
        cls.target = target
        source = base / "source"
        source.mkdir()
        shutil.copy2(PROJECT / "pyproject.toml", source / "pyproject.toml")
        shutil.copy2(PROJECT / "README.md", source / "README.md")
        shutil.copytree(
            PROJECT / "src", source / "src",
            ignore=shutil.ignore_patterns("*.egg-info", "__pycache__", "*.pyc"),
        )
        install = subprocess.run(
            [sys.executable, "-B", "-m", "pip", "install", "--no-deps",
             "--no-build-isolation", "--no-cache-dir", "--target", str(target),
             str(source)],
            cwd=base, capture_output=True, text=True, encoding="utf-8", check=False,
        )
        if install.returncode != 0:
            raise unittest.SkipTest(f"pip --target install failed: {install.stderr[-500:]}")
        cls.command = target / "bin" / (
            "ml-experiment-preflight.exe" if os.name == "nt"
            else "ml-experiment-preflight"
        )
        if not cls.command.is_file():
            raise unittest.SkipTest("installed console script is missing")
        cls.env = os.environ.copy()
        cls.env["PYTHONPATH"] = str(target)
        cls.env["PYTHONDONTWRITEBYTECODE"] = "1"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.neutral = Path(self.temp.name) / "cwd"
        self.neutral.mkdir()
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

    def new_root(self, name="project"):
        root = Path(self.temp.name) / name
        root.mkdir(parents=True)
        return root

    def git(self, root, *args):
        result = subprocess.run(
            [GIT, *args], cwd=str(root), env=self.git_env,
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def write_files(self, root, entry="train.py", input_rel="data/input.bin",
                    output_rel="runs/model.bin", input_exists=True,
                    output_exists=False):
        entry_path = root / entry
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        entry_path.write_text("# synthetic entry\n", encoding="utf-8")
        input_path = root / input_rel
        input_path.parent.mkdir(parents=True, exist_ok=True)
        if input_exists:
            input_path.write_bytes(b"synthetic input")
        output_path = root / output_rel
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_exists:
            output_path.write_bytes(b"synthetic output")

    def init_repo(self, root, entry="train.py"):
        self.git(root, "init", "-q")
        self.git(root, "add", entry)
        self.git(root, "commit", "-qm", "init")

    def run_cli(self, root, args, output_format=None, env_extra=None, cwd=None):
        command = [str(self.command), "check", "--root", str(root), *args]
        if output_format:
            command.extend(("--format", output_format))
        env = self.env.copy()
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            command, cwd=str(cwd or self.neutral), env=env,
            capture_output=True, text=True, encoding="utf-8", check=False,
        )

    def run_json(self, root, args, env_extra=None):
        result = self.run_cli(root, args, "json", env_extra=env_extra)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        validate_report(report)
        self.assertEqual(result.returncode, exit_code(report))
        return report, result

    def run_both(self, root, args, names=()):
        report, json_result = self.run_json(root, args)
        text_result = self.run_cli(root, args)
        self.assertEqual(text_result.stderr, "")
        self.assertEqual(text_result.returncode, exit_code(report))
        self.assertEqual([row["rule_id"] for row in report["results"]], RULE_IDS)
        for row in report["results"]:
            self.assertRegex(
                text_result.stdout,
                rf"{row['rule_id']}: {row['status']}",
            )
        self.assertIn(report["overall"]["status"], text_result.stdout)
        combined = (
            json_result.stdout + json_result.stderr
            + text_result.stdout + text_result.stderr
        )
        self.assertNotIn(str(root), combined)
        for name in names:
            self.assertNotIn(name, combined)
        return report, json_result, text_result

    @staticmethod
    def snapshot(root):
        state = {}
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            digest = None
            if stat.S_ISREG(info.st_mode):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            state[rel] = (info.st_mode, info.st_size, info.st_mtime_ns, digest)
        return state

    @staticmethod
    def remove_junction(path):
        try:
            os.rmdir(path)
        except OSError:
            subprocess.run(["cmd", "/c", "rmdir", str(path)],
                           capture_output=True, text=True, check=False)

    def make_marker(self, name):
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

    # --- Three installed E2E scenarios ---------------------------------

    def test_installed_normal_project_all_six_pass(self):
        root = self.new_root("normal")
        self.write_files(root)
        self.init_repo(root)
        report, _, _ = self.run_both(
            root,
            ["--entry", "train.py", "--input-file", "data/input.bin",
             "--output-file", "runs/model.bin"],
            names=("train.py", "input.bin", "model.bin"),
        )
        for row in report["results"]:
            self.assertEqual(row["status"], "pass", row)
            self.assertTrue(row["coverage_complete"])
        self.assertEqual(report["scope"]["input_count"], 1)
        self.assertEqual(report["scope"]["output_count"], 1)
        self.assertEqual(report["overall"], {
            "status": "clear", "finding_count": 0, "unknown_count": 0,
        })
        self.assertEqual(exit_code(report), 0)

    def test_installed_risk_project_has_expected_findings(self):
        root = self.new_root("risk")
        self.write_files(root, input_rel="data/missing.bin",
                         output_rel="runs/model.bin", input_exists=False,
                         output_exists=True)
        self.init_repo(root)
        (root / "train.py").write_text("# uncommitted change\n", encoding="utf-8")
        report, _, _ = self.run_both(
            root,
            ["--entry", "train.py", "--input-file", "data/missing.bin",
             "--output-file", "runs/model.bin"],
            names=("train.py", "missing.bin", "model.bin"),
        )
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["GIT-002"]["status"], "finding")
        self.assertEqual(rows["GIT-002"]["severity"], "warning")
        self.assertEqual(rows["GIT-002"]["evidence"],
                         [{"code": "ENTRY_CHANGED", "refs": ["entry"]}])
        self.assertEqual(rows["PATH-001"]["status"], "finding")
        self.assertEqual(rows["PATH-001"]["severity"], "critical")
        self.assertEqual(rows["PATH-001"]["evidence"],
                         [{"code": "INPUT_MISSING", "refs": ["input:1"]}])
        self.assertEqual(rows["OUT-001"]["status"], "finding")
        self.assertEqual(rows["OUT-001"]["severity"], "warning")
        self.assertEqual(rows["OUT-001"]["evidence"],
                         [{"code": "OUTPUT_EXISTS", "refs": ["output:1"]}])
        self.assertEqual(rows["OUT-002"]["status"], "unknown")
        self.assertFalse(rows["OUT-002"]["coverage_complete"])
        self.assertEqual(report["overall"]["status"], "blocked")
        self.assertEqual(exit_code(report), 2)

    def test_installed_output_equals_input_is_critical(self):
        root = self.new_root("same-file")
        self.write_files(root, input_rel="data/input.bin",
                         output_rel="data/input.bin", output_exists=True)
        self.init_repo(root)
        report, _, _ = self.run_both(
            root,
            ["--entry", "train.py", "--input-file", "data/input.bin",
             "--output-file", "data/input.bin"],
            names=("train.py", "input.bin"),
        )
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["OUT-002"]["status"], "finding")
        self.assertEqual(rows["OUT-002"]["severity"], "critical")
        self.assertIn("OUTPUT_EQUALS_INPUT_OR_ENTRY",
                      [item["code"] for item in rows["OUT-002"]["evidence"]])
        self.assertEqual(report["overall"]["status"], "blocked")
        self.assertEqual(exit_code(report), 1)

    def test_installed_hardlink_alias_is_critical(self):
        root = self.new_root("hardlink")
        self.write_files(root)
        alias = root / "data" / "alias.bin"
        try:
            os.link(root / "data" / "input.bin", alias)
        except OSError as error:
            self.skipTest(f"hardlink unavailable: {error}")
        self.init_repo(root)
        report, _, _ = self.run_both(
            root,
            ["--entry", "train.py", "--input-file", "data/input.bin",
             "--output-file", "data/alias.bin"],
            names=("train.py", "input.bin", "alias.bin"),
        )
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["OUT-002"]["severity"], "critical")
        self.assertIn("OUTPUT_EQUALS_INPUT_OR_ENTRY",
                      [item["code"] for item in rows["OUT-002"]["evidence"]])
        self.assertEqual(exit_code(report), 1)

    # --- Windows path scenarios ----------------------------------------

    def test_installed_chinese_and_space_paths(self):
        root = self.new_root("项目 space")
        entry = "训练 脚本.py"
        input_rel = "数据 输入.bin"
        output_rel = "结果 输出.bin"
        self.write_files(root, entry=entry, input_rel=input_rel,
                         output_rel=output_rel)
        self.init_repo(root, entry=entry)
        report, _, _ = self.run_both(
            root,
            ["--entry", entry, "--input-file", input_rel,
             "--output-file", output_rel],
            names=(entry, input_rel, output_rel),
        )
        for row in report["results"]:
            self.assertEqual(row["status"], "pass", row)
        self.assertEqual(exit_code(report), 0)

    def test_installed_junction_entry_escape_is_critical(self):
        if os.name != "nt":
            self.skipTest("junction test is Windows-only")
        root = self.new_root("junction-root")
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "outside_entry.py").write_text("# outside\n", encoding="utf-8")
        self.write_files(root, entry="tracked.py")
        self.init_repo(root, entry="tracked.py")
        link = root / "linked"
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True, check=False,
        )
        if result.returncode != 0:
            self.skipTest(
                "junction creation failed: "
                + result.stderr.decode("utf-8", "replace").strip()
            )
        self.addCleanup(self.remove_junction, link)
        report, _, _ = self.run_both(
            root,
            ["--entry", "linked/outside_entry.py",
             "--input-file", "input.bin", "--output-file", "runs/model.bin"],
            names=("outside_entry.py", "input.bin", "model.bin"),
        )
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["PATH-001"]["status"], "finding")
        self.assertIn("ENTRY_ESCAPES_ROOT",
                      [item["code"] for item in rows["PATH-001"]["evidence"]])
        for rule in ("GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["status"], "unknown")
            self.assertEqual(rows[rule]["reason_code"], "ENTRY_UNAVAILABLE")
        self.assertEqual(report["overall"]["status"], "blocked")
        self.assertEqual(exit_code(report), 2)

    def test_installed_symlink_entry_escape_or_skip(self):
        root = self.new_root("symlink-root")
        outside = Path(self.temp.name) / "symlink-outside"
        outside.mkdir()
        (outside / "outside_entry.py").write_text("# outside\n", encoding="utf-8")
        self.write_files(root, entry="tracked.py")
        self.init_repo(root, entry="tracked.py")
        link = root / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            if os.name == "nt":
                self.skipTest(f"symlink creation unavailable: {error}")
            raise
        self.addCleanup(link.unlink, missing_ok=True)
        report, _, _ = self.run_both(
            root,
            ["--entry", "linked/outside_entry.py",
             "--input-file", "input.bin", "--output-file", "runs/model.bin"],
            names=("outside_entry.py", "input.bin", "model.bin"),
        )
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["PATH-001"]["status"], "finding")
        self.assertIn("ENTRY_ESCAPES_ROOT",
                      [item["code"] for item in rows["PATH-001"]["evidence"]])

    def test_installed_cross_drive_input_is_unknown_not_pass(self):
        if os.name != "nt":
            self.skipTest("Windows drive boundary scenario")
        other_temp = None
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            root_drive = Path(f"{letter}:\\")
            if not root_drive.exists():
                continue
            try:
                other_temp = tempfile.TemporaryDirectory(dir=str(root_drive))
                break
            except OSError:
                continue
        if other_temp is None:
            self.skipTest("no second drive available")
        self.addCleanup(other_temp.cleanup)
        external_input = Path(other_temp.name) / "input.bin"
        external_input.write_bytes(b"synthetic external input")
        root = self.new_root("cross-drive")
        self.write_files(root)
        self.init_repo(root)
        report, _, _ = self.run_both(
            root,
            ["--entry", "train.py", "--input-file", str(external_input),
             "--output-file", "runs/model.bin"],
            names=("train.py", "input.bin", "model.bin"),
        )
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["PATH-001"]["status"], "pass")
        self.assertEqual(rows["OUT-001"]["status"], "pass")
        self.assertEqual(rows["OUT-002"]["status"], "unknown")
        self.assertFalse(rows["OUT-002"]["coverage_complete"])
        self.assertEqual(exit_code(report), 2)

    @unittest.skipUnless(os.name == "nt", "Windows UNC path syntax")
    def test_installed_unc_input_and_output_are_unknown_not_pass(self):
        root = self.new_root("unc")
        self.write_files(root)
        private = "\\\\preflight-invalid-host\\private-share\\secret.bin"
        report, _, _ = self.run_both(
            root,
            ["--entry", "train.py", "--input-file", private,
             "--output-file", private],
            names=("train.py", "secret.bin"),
        )
        rows = {row["rule_id"]: row for row in report["results"]}
        for rule in ("PATH-001", "OUT-001", "OUT-002"):
            self.assertEqual(rows[rule]["status"], "unknown")
            self.assertFalse(rows[rule]["coverage_complete"])
        self.assertEqual(exit_code(report), 2)

    def test_installed_permission_error_injection_is_unknown_not_pass(self):
        root = self.new_root("permission")
        self.write_files(root)
        self.init_repo(root)
        input_path = root / "data" / "input.bin"
        script = (
            "import pathlib, sys\n"
            "from unittest.mock import patch\n"
            "import ml_experiment_preflight\n"
            "from ml_experiment_preflight.cli import main\n"
            "assert pathlib.Path(ml_experiment_preflight.__file__).is_relative_to(pathlib.Path(sys.argv[3]))\n"
            "target = pathlib.Path(sys.argv[2])\n"
            "original = pathlib.Path.resolve\n"
            "def resolving(path, *args, **kwargs):\n"
            "    if path == target:\n"
            "        raise PermissionError('synthetic private path')\n"
            "    return original(path, *args, **kwargs)\n"
            "with patch.object(pathlib.Path, 'resolve', resolving):\n"
            "    sys.exit(main(['check', '--root', sys.argv[1], "
            "'--entry', 'train.py', '--input-file', str(target), "
            "'--output-file', 'runs/model.bin', '--format', 'json']))\n"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", script, str(root), str(input_path),
             str(self.target)],
            cwd=self.neutral, env=self.env, capture_output=True, text=True,
            encoding="utf-8", check=False,
        )
        self.assertEqual(result.stderr, "")
        self.assertNotIn(str(root), result.stdout)
        self.assertNotIn(input_path.name, result.stdout)
        report = json.loads(result.stdout)
        validate_report(report)
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["PATH-001"]["status"], "unknown")
        self.assertEqual(rows["PATH-001"]["reason_code"], "PERMISSION_DENIED")
        self.assertEqual(rows["PATH-001"]["unknown_refs"], ["input:1"])
        self.assertEqual(result.returncode, 2)

    # --- Git safety through the installed CLI ---------------------------

    def test_installed_git_large_output_is_unknown_not_pass(self):
        # The fake Git must be a real executable on Windows: the final
        # _find_git_executable() only accepts git.exe, never git.cmd/bat.
        # It writes a marker before flooding stdout so this test proves the
        # installed CLI actually selected and ran the fake Git.
        root = self.new_root("large-git-output")
        self.write_files(root)
        (root / ".git").mkdir()
        fakebin = Path(self.temp.name) / "fakebin"
        fakebin.mkdir()
        marker = Path(self.temp.name) / "fake_git.marker"
        fake_git = Path(self.temp.name) / "fake_git.py"
        fake_git.write_text(
            "import os, pathlib, sys\n"
            "marker = os.environ.get('ML_PREFLIGHT_FAKE_GIT_MARKER')\n"
            "if marker:\n"
            "    pathlib.Path(marker).write_text('ran', encoding='utf-8')\n"
            "sys.stdout.write('x' * (2 * 1024 * 1024))\n"
            "sys.stdout.flush()\n",
            encoding="utf-8",
        )
        if os.name == "nt":
            powershell = shutil.which("powershell")
            if not powershell:
                self.skipTest("powershell is required to build the synthetic git.exe")
            ps1 = Path(self.temp.name) / "build_fake_git.ps1"
            ps1.write_text(
                """$src = @'
using System;
using System.IO;
public class FakeGit {
  public static int Main(string[] args) {
    var marker = Environment.GetEnvironmentVariable("ML_PREFLIGHT_FAKE_GIT_MARKER");
    if (!string.IsNullOrEmpty(marker)) { File.WriteAllText(marker, "ran"); }
    var data = new byte[2 * 1024 * 1024];
    for (int i = 0; i < data.Length; i++) { data[i] = (byte)'x'; }
    using (var stdout = Console.OpenStandardOutput()) {
      stdout.Write(data, 0, data.Length);
      stdout.Flush();
    }
    return 0;
  }
}
'@
Add-Type -TypeDefinition $src -OutputAssembly $env:FAKE_GIT_OUT -OutputType ConsoleApplication
""",
                encoding="utf-8",
            )
            wrapper = fakebin / "git.exe"
            build_env = os.environ.copy()
            build_env["FAKE_GIT_OUT"] = str(wrapper)
            built = subprocess.run(
                [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(ps1)],
                env=build_env, capture_output=True, text=True,
                encoding="utf-8", check=False,
            )
            if built.returncode != 0 or not wrapper.is_file():
                self.skipTest(
                    "cannot build synthetic Windows git.exe launcher: "
                    + (built.stderr or "")[-500:]
                )
        else:
            wrapper = fakebin / "git"
            wrapper.write_text(
                "#!/bin/sh\n"
                f'exec "{Path(sys.executable).as_posix()}" -B "{fake_git.as_posix()}"\n',
                encoding="utf-8",
            )
            os.chmod(wrapper, 0o755)
        path = str(fakebin) + os.pathsep + self.env.get("PATH", "")
        started = time.monotonic()
        report, _ = self.run_json(
            root,
            ["--entry", "train.py", "--input-file", "data/input.bin",
             "--output-file", "runs/model.bin"],
            env_extra={
                "PATH": path,
                "ML_PREFLIGHT_FAKE_GIT_MARKER": str(marker),
            },
        )
        elapsed = time.monotonic() - started
        self.assertTrue(marker.is_file(), "synthetic Git was not executed")
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["GIT-001"]["status"], "unknown")
        self.assertEqual(rows["GIT-001"]["reason_code"], "GIT_ERROR")
        for rule in ("GIT-002", "GIT-003"):
            self.assertEqual(rows[rule]["status"], "unknown")
            self.assertEqual(rows[rule]["reason_code"], "GIT_CONTEXT_UNKNOWN")
        self.assertEqual(exit_code(report), 2)
        self.assertLess(elapsed, 5.0)

    def test_installed_git_abnormal_layouts_are_unknown_not_pass(self):
        # .git file / external gitdir is unsupported.
        root = self.new_root("git-file-layout")
        self.write_files(root)
        (root / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
        report, _ = self.run_json(
            root,
            ["--entry", "train.py", "--input-file", "data/input.bin",
             "--output-file", "runs/model.bin"],
        )
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["GIT-001"]["status"], "unknown")
        self.assertEqual(rows["GIT-001"]["reason_code"], "UNSUPPORTED_GIT_LAYOUT")

        # assume-unchanged must not become a pass.
        root = self.new_root("git-assume-unchanged")
        self.write_files(root)
        self.init_repo(root)
        self.git(root, "update-index", "--assume-unchanged", "train.py")
        (root / "train.py").write_text("# changed\n", encoding="utf-8")
        report, _ = self.run_json(
            root,
            ["--entry", "train.py", "--input-file", "data/input.bin",
             "--output-file", "runs/model.bin"],
        )
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["GIT-002"]["status"], "unknown")
        self.assertEqual(rows["GIT-002"]["reason_code"], "GIT_ENTRY_FLAG_UNSUPPORTED")

        # Corrupt index must not become a pass.
        root = self.new_root("git-corrupt-index")
        self.write_files(root)
        self.init_repo(root)
        (root / ".git" / "index").write_bytes(b"garbage")
        report, _ = self.run_json(
            root,
            ["--entry", "train.py", "--input-file", "data/input.bin",
             "--output-file", "runs/model.bin"],
        )
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["GIT-001"]["status"], "pass")
        self.assertEqual(rows["GIT-002"]["reason_code"], "GIT_ERROR")
        self.assertEqual(rows["GIT-003"]["reason_code"], "GIT_ERROR")
        self.assertEqual(exit_code(report), 2)

    def test_installed_filter_marker_is_not_triggered(self):
        root = self.new_root("filter-marker")
        self.write_files(root)
        self.init_repo(root)
        script, marker = self.make_marker("filter")
        (root / ".gitattributes").write_text("*.py filter=marker\n", encoding="utf-8")
        self.git(root, "config", "filter.marker.clean",
                 self.marker_command(script, marker, "filter-clean"))
        (root / "train.py").write_text("# filter trigger\n", encoding="utf-8")
        self.git(root, "add", "--renormalize", "train.py")
        self.assertTrue(marker.exists(), "marker harness did not run")
        marker.unlink()
        (root / "train.py").write_text("# changed after trigger\n", encoding="utf-8")
        report, _ = self.run_json(
            root,
            ["--entry", "train.py", "--input-file", "data/input.bin",
             "--output-file", "runs/model.bin"],
        )
        self.assertFalse(marker.exists(), "installed CLI triggered a filter")
        rows = {row["rule_id"]: row for row in report["results"]}
        self.assertEqual(rows["GIT-002"]["status"], "finding")

    def test_installed_run_is_deterministic_and_read_only(self):
        root = self.new_root("deterministic")
        self.write_files(root)
        self.init_repo(root)
        before = self.snapshot(root)
        first, _ = self.run_json(
            root,
            ["--entry", "train.py", "--input-file", "data/input.bin",
             "--output-file", "runs/model.bin"],
        )
        second, _ = self.run_json(
            root,
            ["--entry", "train.py", "--input-file", "data/input.bin",
             "--output-file", "runs/model.bin"],
        )
        after = self.snapshot(root)
        self.assertEqual(first, second)
        self.assertEqual(before, after)
        self.assertEqual(exit_code(first), 0)


if __name__ == "__main__":
    unittest.main()
