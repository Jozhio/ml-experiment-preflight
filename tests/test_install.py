"""Installation smoke test from an unrelated working directory."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def test_installed_cli_runs_outside_repository_without_repo_on_pythonpath(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            target = temp / "packages"
            source = temp / "source"
            source.mkdir()
            shutil.copy2(PROJECT / "pyproject.toml", source / "pyproject.toml")
            shutil.copy2(PROJECT / "README.md", source / "README.md")
            shutil.copytree(PROJECT / "src", source / "src",
                            ignore=shutil.ignore_patterns("*.egg-info", "__pycache__", "*.pyc"))
            install = subprocess.run(
                [sys.executable, "-B", "-m", "pip", "install", "--no-deps",
                 "--no-build-isolation", "--no-cache-dir", "--target", str(target),
                 str(source)],
                cwd=temp, capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertEqual(install.returncode, 0, install.stderr[-1200:])
            (temp / "train.py").write_text("# synthetic\n", encoding="utf-8")
            (temp / "input.bin").write_bytes(b"synthetic")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(target)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            run = subprocess.run(
                [sys.executable, "-B", "-m", "ml_experiment_preflight", "check",
                 "--root", str(temp), "--entry", "train.py", "--input-file",
                 "input.bin", "--output-file", "out.bin", "--format", "json"],
                cwd=temp, env=env, capture_output=True, text=True, encoding="utf-8",
                check=False,
            )
            self.assertEqual(run.returncode, 2, run.stderr)
            self.assertEqual(json.loads(run.stdout)["overall"]["status"], "incomplete")
            self.assertNotIn(str(PROJECT), run.stdout + run.stderr)
            command = target / "bin" / (
                "ml-experiment-preflight.exe" if os.name == "nt" else "ml-experiment-preflight"
            )
            self.assertTrue(command.is_file(), str(command))
            entrypoint = subprocess.run(
                [str(command), "--help"], cwd=temp, env=env,
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertEqual(entrypoint.returncode, 0, entrypoint.stderr)
            self.assertIn("check", entrypoint.stdout)


if __name__ == "__main__":
    unittest.main()
