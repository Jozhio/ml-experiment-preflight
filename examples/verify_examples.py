"""Reproduce the three synthetic examples and assert their expected results.

Uses only the Python standard library, temporary directories, and synthetic
files. It never runs train.py or reads any real research data.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


PROJECT = Path(__file__).resolve().parents[1]
EXAMPLES = Path(__file__).resolve().parent
GIT = shutil.which("git")

GIT_ENV = os.environ.copy()
for key in tuple(GIT_ENV):
    if key.upper().startswith("GIT_"):
        GIT_ENV.pop(key, None)
GIT_ENV.update({
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_AUTHOR_NAME": "Synthetic",
    "GIT_AUTHOR_EMAIL": "synthetic@example.invalid",
    "GIT_COMMITTER_NAME": "Synthetic",
    "GIT_COMMITTER_EMAIL": "synthetic@example.invalid",
    "LC_ALL": "C",
})

CLI = shutil.which("ml-experiment-preflight")
CLI_ENV = os.environ.copy()
CLI_ENV["PYTHONDONTWRITEBYTECODE"] = "1"
if CLI:
    # Verify the installed entry point; do not let a source checkout shadow it.
    CLI_ENV.pop("PYTHONPATH", None)
else:
    CLI_ENV["PYTHONPATH"] = str(PROJECT / "src")


def git(root, *args):
    result = subprocess.run(
        [GIT, *args], cwd=str(root), env=GIT_ENV,
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args} failed: {result.stderr}")


def copy_fixture(case, destination):
    shutil.copytree(EXAMPLES / case / "fixture", destination, dirs_exist_ok=True)


def init_repo(root):
    git(root, "init", "-q")
    git(root, "add", "train.py")
    git(root, "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
        "commit", "-qm", "init")


def run_cli(root, input_path, output_path):
    command = [CLI, "check"] if CLI else [
        sys.executable, "-B", "-m", "ml_experiment_preflight", "check"
    ]
    command.extend([
        "--root", str(root), "--entry", "train.py",
        "--input-file", input_path, "--output-file", output_path,
        "--format", "json",
    ])
    result = subprocess.run(
        command, cwd=str(root), env=CLI_ENV,
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if result.stderr:
        raise AssertionError(f"unexpected stderr: {result.stderr}")
    report = json.loads(result.stdout)
    return result.returncode, report


def rows(report):
    return {row["rule_id"]: row for row in report["results"]}


def check_normal(temp):
    root = Path(temp) / "normal"
    copy_fixture("normal", root)
    (root / "runs").mkdir()
    init_repo(root)
    code, report = run_cli(root, "data/input.bin", "runs/model.bin")
    assert code == 0, code
    assert report["overall"] == {
        "status": "clear", "finding_count": 0, "unknown_count": 0,
    }, report["overall"]
    assert all(row["status"] == "pass" for row in report["results"])
    return report


def check_risk(temp):
    root = Path(temp) / "risk"
    copy_fixture("risk", root)
    (root / "runs").mkdir(exist_ok=True)
    shutil.copy2(EXAMPLES / "risk" / "fixture" / "train.baseline.py",
                 root / "train.py")
    init_repo(root)
    shutil.copy2(EXAMPLES / "risk" / "fixture" / "train.dirty.py",
                 root / "train.py")
    code, report = run_cli(root, "data/missing.bin", "runs/model.bin")
    assert code == 2, code
    result_rows = rows(report)
    assert report["overall"]["status"] == "blocked", report["overall"]
    assert result_rows["GIT-002"]["status"] == "finding"
    assert result_rows["PATH-001"]["status"] == "finding"
    assert "INPUT_MISSING" in [item["code"] for item in result_rows["PATH-001"]["evidence"]]
    assert result_rows["OUT-001"]["status"] == "finding"
    assert "OUTPUT_EXISTS" in [item["code"] for item in result_rows["OUT-001"]["evidence"]]
    assert result_rows["OUT-002"]["status"] == "unknown"
    return report


def check_conflict(temp):
    root = Path(temp) / "conflict"
    copy_fixture("conflict", root)
    init_repo(root)
    code, report = run_cli(root, "data/input.bin", "data/input.bin")
    assert code == 1, code
    result_rows = rows(report)
    assert report["overall"]["status"] == "blocked", report["overall"]
    assert result_rows["OUT-002"]["status"] == "finding"
    assert result_rows["OUT-002"]["severity"] == "critical"
    assert "OUTPUT_EQUALS_INPUT_OR_ENTRY" in [
        item["code"] for item in result_rows["OUT-002"]["evidence"]
    ]
    return report


def main():
    if not GIT:
        print("ERROR: git is required for the examples", file=sys.stderr)
        return 2
    print("using", "installed ml-experiment-preflight" if CLI else
          f"source module ({PROJECT / 'src'})")
    checks = (("normal", check_normal), ("risk", check_risk), ("conflict", check_conflict))
    for name, check in checks:
        with tempfile.TemporaryDirectory(prefix=f"ml-preflight-example-{name}-") as temp:
            report = check(temp)
            print(f"{name}: overall={report['overall']['status']} "
                  f"findings={report['overall']['finding_count']} "
                  f"unknowns={report['overall']['unknown_count']}")
    print("All synthetic examples matched their expected results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
