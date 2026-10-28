# ML Experiment Preflight

**Version 0.1.0 — pre-release.**

`ml-experiment-preflight` is a read-only, offline pre-training check for an **explicitly specified** ML project root, entry script, input paths, and output paths. It reports deterministic evidence about Git state, explicit input paths, and output/input conflicts before a training launch.

It is intentionally narrow. It does **not** inspect training-data contents, validate data quality, estimate GPU/VRAM use, resolve dependencies, score reproducibility, or run training.

## Why use it

Before launching a long or expensive run, a short static check can catch a few expensive-to-discover setup mistakes:

- the entry script is modified or untracked;
- the repository has no usable HEAD;
- a declared input does not exist or has the wrong file/directory type;
- an output already exists, is the wrong type, or collides with an input/entry/root.

The value is a fast, auditable snapshot—not a guarantee that training will succeed. The checker is independent of any Agent and can be run directly from a terminal. The Agent Skill only explains the CLI's structured result.

This project does not claim a unique market position. Related tools include MLflow, DVC, ReproZip, Gitleaks, and pre-training checkers such as `preflight-ml`, `trainproof`, and `preflight-data`. See [docs/COMPETITOR_ANALYSIS.md](docs/COMPETITOR_ANALYSIS.md).

## The six rules

The report always contains exactly six results in this order. `pass` means only that the rule found no predefined issue in its limited scope; it is not a general safety claim.

| Rule | What it checks | Finding | `unknown` examples |
| --- | --- | --- | --- |
| `GIT-001` | Root is a normal local `.git` repository with a resolvable HEAD and the repository top level equals `--root`. | warning `NO_REPOSITORY`, `NO_HEAD` | `GIT_UNAVAILABLE`, `GIT_ROOT_MISMATCH`, `UNSUPPORTED_GIT_LAYOUT`, `GIT_TIMEOUT`, `GIT_ERROR` |
| `GIT-002` | Only the explicitly named tracked entry has staged or worktree changes. | warning `ENTRY_CHANGED` | `ENTRY_UNAVAILABLE`, `ENTRY_NOT_TRACKED`, `GIT_ENTRY_FLAG_UNSUPPORTED`, `GIT_CONTEXT_UNKNOWN`, `GIT_TIMEOUT`, `GIT_ERROR`, `GIT_OUTPUT_LIMIT` |
| `GIT-003` | The explicitly named entry is tracked by the Git index. | warning `ENTRY_NOT_TRACKED` | `ENTRY_UNAVAILABLE`, `GIT_CONTEXT_UNKNOWN`, `GIT_TIMEOUT`, `GIT_ERROR` |
| `PATH-001` | Explicit entry and inputs exist with the declared file/directory type; the entry's physical target stays inside the root. | critical `ENTRY_MISSING`, `INPUT_MISSING`, `TYPE_MISMATCH`, `ENTRY_ESCAPES_ROOT` | `PERMISSION_DENIED`, `SYMLINK_UNRESOLVED`, `PATH_IO_ERROR`, `EVIDENCE_LIMIT` |
| `OUT-001` | Each output exists, matches the declared type, or has a resolvable parent. | warning `OUTPUT_EXISTS`; critical `OUTPUT_TYPE_MISMATCH` | `OUTPUT_PARENT_UNKNOWN`, `SYMLINK_UNRESOLVED`, `PERMISSION_DENIED`, `PATH_IO_ERROR` |
| `OUT-002` | Output equals an input/entry, contains an input/entry/root, or lies inside an input directory. Same-file identity uses `Path.samefile` for existing targets. | critical `OUTPUT_EQUALS_INPUT_OR_ENTRY`, `OUTPUT_DIR_CONTAINS_INPUT_OR_ROOT`; warning `OUTPUT_INSIDE_INPUT_DIR` | `PATH_COMPARISON_UNKNOWN`, `SYMLINK_UNRESOLVED`, `OUTPUT_PARENT_UNKNOWN`, `EVIDENCE_LIMIT` |

Git is optional. If Git is unavailable, Git rules become `unknown`; the path/output rules still run. If a rule cannot decide, it must not be reported as `pass`.

## Installation

Requires **Python 3.11+**. Git is optional for the CLI (needed for the Git examples and Git rules). There is no third-party runtime dependency. No PyPI release is published; install from this source checkout.

### Windows PowerShell (clean environment)

```powershell
cd F:\path\to\ml-experiment-preflight
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
$env:PATH = (Resolve-Path .\.venv\Scripts).Path + ";" + $env:PATH
ml-experiment-preflight --help
```

`pip install .` may use the network to obtain its declared build requirements (`setuptools>=61` and `wheel`) when build isolation is enabled. The installed tool itself runs offline.

### Linux Bash (clean environment)

```bash
cd /path/to/ml-experiment-preflight
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
ml-experiment-preflight --help
```

### Uninstall

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y ml-experiment-preflight
Remove-Item -Recurse -Force .venv
```

Linux Bash:

```bash
. .venv/bin/activate
python -m pip uninstall -y ml-experiment-preflight
deactivate
rm -rf .venv
```

For a detailed installation verification walkthrough, see [Installation verification](#installation-verification).

## CLI usage

The CLI requires an explicit root, entry, at least one explicit input, and at least one explicit output. Each input/output group is limited to 32 entries. Relative paths are interpreted relative to `--root`; the current shell directory is not used as the project root.

### Windows PowerShell

```powershell
ml-experiment-preflight check --root C:\work\demo --entry train.py --input-file data\input.bin --output-file runs\model.bin --format json
```

### Linux Bash

```bash
ml-experiment-preflight check --root /work/demo --entry train.py --input-file data/input.bin --output-file runs/model.bin --format json
```

Use `--input-dir` or `--output-dir` when the declared target is a directory. `--format` defaults to `text`; Agents must request `--format json`. There is no `--write`, `--fix`, `--upload`, `--scan-all`, or automatic directory discovery.

If the console script is not available but the package is installed/importable, use the module form:

```text
python -m ml_experiment_preflight check --root ROOT --entry ENTRY --input-file INPUT --output-file OUTPUT --format json
```

## JSON report

The CLI emits one UTF-8 JSON object on stdout for a valid check. It contains no absolute paths, file names, usernames, environment values, or Git file names. Targets are referred to as `root`, `entry`, `input:N`, and `output:N`.

Representative output for a normal run:

```json
{
  "schema_version": "1.0",
  "tool_version": "0.1.0",
  "scope": {
    "root_ref": "root",
    "entry_ref": "entry",
    "input_count": 1,
    "output_count": 1,
    "git_status_scope": "entry_only",
    "untracked_files_scanned": false
  },
  "overall": {
    "status": "clear",
    "finding_count": 0,
    "unknown_count": 0
  },
  "results": [
    {
      "rule_id": "GIT-001",
      "status": "pass",
      "severity": "none",
      "coverage_complete": true,
      "reason_code": null,
      "unknown_refs": [],
      "evidence": [{"code": "REPOSITORY_WITH_HEAD", "refs": ["root"]}]
    },
    {
      "rule_id": "GIT-002",
      "status": "pass",
      "severity": "none",
      "coverage_complete": true,
      "reason_code": null,
      "unknown_refs": [],
      "evidence": [{"code": "ENTRY_UNCHANGED", "refs": ["entry"]}]
    },
    {
      "rule_id": "GIT-003",
      "status": "pass",
      "severity": "none",
      "coverage_complete": true,
      "reason_code": null,
      "unknown_refs": [],
      "evidence": [{"code": "ENTRY_TRACKED", "refs": ["entry"]}]
    },
    {
      "rule_id": "PATH-001",
      "status": "pass",
      "severity": "none",
      "coverage_complete": true,
      "reason_code": null,
      "unknown_refs": [],
      "evidence": []
    },
    {
      "rule_id": "OUT-001",
      "status": "pass",
      "severity": "none",
      "coverage_complete": true,
      "reason_code": null,
      "unknown_refs": [],
      "evidence": []
    },
    {
      "rule_id": "OUT-002",
      "status": "pass",
      "severity": "none",
      "coverage_complete": true,
      "reason_code": null,
      "unknown_refs": [],
      "evidence": []
    }
  ]
}
```

`overall.status` priority is: critical finding → `blocked`; otherwise incomplete coverage → `incomplete`; otherwise warning finding → `review`; otherwise `clear`. `unknown` is not a pass, and `blocked` must not be hidden.

## Exit codes

| Exit | Meaning |
| --- | --- |
| `0` | `clear`: all six rules passed with complete coverage |
| `1` | At least one known finding and complete coverage (`review` or `blocked`) |
| `2` | Any incomplete coverage, usage error, or report-build failure |

Exit `2` can still carry a valid JSON report. Parse stdout first; do not base the project conclusion on the exit code alone. If stdout is not JSON, report a tool failure (`USAGE_ERROR` or `REPORT_ERROR`), not a project status.

## Agent Skill installation and invocation

The repository includes a project-level Skill at both supported discovery paths:

```text
.claude/skills/ml-experiment-preflight/SKILL.md   # Claude Code
.agents/skills/ml-experiment-preflight/SKILL.md   # Codex
```

The two files are identical (SHA-256 `a7cf67ff94fac04186530e1318b115c4d77504d8d87d52951baa42befa1f3a1c`) and target Skill version `0.1.0`. Install the CLI first; the Skill invokes it.

### Copy the Skill into your own project

Windows PowerShell:

```powershell
$dest = "C:\work\my-project\.claude\skills\ml-experiment-preflight"
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item -Recurse -Force .\.claude\skills\ml-experiment-preflight\* $dest
```

Linux Bash:

```bash
dest=/work/my-project/.claude/skills/ml-experiment-preflight
mkdir -p "$dest"
cp -R .claude/skills/ml-experiment-preflight/. "$dest/"
```

For Codex, copy to `.agents/skills/ml-experiment-preflight/` instead. Do not edit only one copy; keep both host copies identical.

### Invoke

- **Claude Code:** type `/ml-experiment-preflight ...` at the start of a message, or ask naturally with the preflight trigger words. The project-level Skill is discovered from `.claude/skills`.
- **Codex:** mention `$ml-experiment-preflight` (or `/skills` in the Codex IDE); Codex scans `.agents/skills` from the working directory up to the repository root.
- **AionUi:** there is no tested native AionUi Skill discovery. A member Agent can read `SKILL.md` and run the CLI manually; do not treat that as native AionUi compatibility.

The Skill instructs the Agent to ask for explicit paths, run only the read-only CLI, interpret JSON, and never run training, import project code, read data contents, write Git state, or execute fixes without user confirmation. See [SKILL.md](.claude/skills/ml-experiment-preflight/SKILL.md) and [docs/SKILL_INTEGRATION.md](docs/SKILL_INTEGRATION.md).

## Examples

Three fully synthetic, temporary projects are included under [`examples/`](examples/). They use local Git repositories, placeholder files, and no real research data. `train.py` is never executed.

| Example | Expected result | Exit |
| --- | --- | --- |
| `normal` | all six rules pass; `overall=clear` | `0` |
| `risk` | `ENTRY_CHANGED`, `INPUT_MISSING`, `OUTPUT_EXISTS`; `OUT-002` unknown; `overall=blocked` | `2` |
| `conflict` | `OUTPUT_EQUALS_INPUT_OR_ENTRY` critical; `overall=blocked` | `1` |

Run all examples and assert their expected outputs.

Windows PowerShell:

```powershell
cd F:\path\to\ml-experiment-preflight
python .\examples\verify_examples.py
```

Linux Bash:

```bash
cd /path/to/ml-experiment-preflight
python3 examples/verify_examples.py
```

Individual runners (each creates and removes a temporary project):

Windows PowerShell:

```powershell
powershell -NoProfile -File .\examples\normal\run.ps1
powershell -NoProfile -File .\examples\risk\run.ps1
powershell -NoProfile -File .\examples\conflict\run.ps1
```

Linux Bash:

```bash
bash examples/normal/run.sh
bash examples/risk/run.sh
bash examples/conflict/run.sh
```

The `risk` and `conflict` runners intentionally exit `2` and `1`; that is the expected result, not a script failure. See [examples/README.md](examples/README.md) for prerequisites and details.

## Privacy and limitations

- **Read-only:** the CLI reads filesystem metadata and limited local Git metadata. It does not execute training or user code, import project modules, read data contents, create files, or modify Git state.
- **Git executable trust:** Git is resolved from absolute PATH directories outside the checked root and current directory, never by implicit cwd lookup. A caller-controlled PATH outside those boundaries remains a trust assumption (see SECURITY.md).
- **Explicit paths only:** it does not scan a whole project or guess missing paths. Input/output contents are never read; input directories are not enumerated.
- **Offline intent:** the CLI has no upload, telemetry, or network API. Obvious UNC paths are rejected or marked unknown. Filesystem metadata on a user-supplied mapped/network volume may still cause operating-system network I/O; do not use such volumes when strict offline operation is required.
- **Redacted reports:** the JSON contains only rule/evidence codes and symbolic refs. It intentionally omits absolute paths, file names, environment values, and Git file names. The original shell command and Agent host logs may still contain paths; run locally for private projects and share only the redacted JSON.
- **Git is optional:** missing Git or an unsupported repository layout produces `unknown`, not `pass`.
- **Static snapshot:** TOCTOU, concurrent changes, symlinks, permissions, network paths, and cross-volume identity remain limitations. UNC roots/entries are rejected; UNC inputs/outputs are unknown. Mapped paths are not exhaustively detected. Windows process-tree termination is not guaranteed beyond the direct process.
- **Not a data/reproducibility audit:** no data quality, labels, schema, GPU/CUDA, dependency resolution, performance, or full reproducibility proof.
- **Skill permissions:** the Skill does not declare `allowed-tools`; the host's permission model still governs Bash/tool calls. Do not treat Skill instructions as a sandbox.

## Compatibility

Only the following have actually been exercised. Empty/“not run” rows are not claims of support.

| Environment | Status |
| --- | --- |
| Windows 10.0.19045; Python 3.11.0; Git 2.54.0.windows.1 | Local final-candidate run: 127 unittest tests, 0 failures, 5 skips, exit 0; all three synthetic examples verified. |
| Linux / Windows Python 3.12 (local) | Not run locally. |
| GitHub Actions (Ubuntu 24.04 and Windows; Python 3.11/3.12) | Workflow is provided. The public repository must run its own four-matrix CI on the final public commit before release; pre-publication results are not a public compatibility claim. |
| Claude Code / Codex project-level Skill | Both discovery paths are provided and the two SKILL.md copies are byte-identical. Host-native discovery, versions, permissions, and behavior vary and were not independently re-verified in the public tree. |
| AionUi | No native Skill discovery is claimed. A member Agent can read SKILL.md and run the CLI manually. |

The local Windows run had 5 skips (4 POSIX-only tests plus 1 Windows symlink-privilege test). The public source tree contains the source, tests, Skill, examples, and documentation needed to use and verify the project.

## Installation verification

A clean-environment check for a new user:

1. Install into a fresh virtual environment as shown above.
2. Run `ml-experiment-preflight --help` and confirm the `check` command is listed.
3. Run the normal example verifier:

   Windows PowerShell (with the venv Scripts directory on PATH from the install step):

   ```powershell
   .\.venv\Scripts\python.exe .\examples\verify_examples.py
   ```

   Linux Bash (with the venv activated):

   ```bash
   python examples/verify_examples.py
   ```

4. Confirm the printed results are `normal: overall=clear`, `risk: overall=blocked`, and `conflict: overall=blocked`, and that the verifier says it is using the installed `ml-experiment-preflight`.
5. Run the normal runner directly and confirm the JSON `overall.status` is `clear` and the exit code is `0`.
6. Uninstall as shown above; confirm `ml-experiment-preflight` is no longer available in that environment.

If the console script is blocked by a host permission or is absent, use the documented module fallback with the package installed. Do not install undeclared dependencies for the examples; they use only Python's standard library and Git.

## License

MIT. See [LICENSE](LICENSE). The project contains no vendored third-party source code. `setuptools>=61` and `wheel` are build-time requirements; Git and Python are external tools, not bundled components. External documentation links are references, not bundled content.

## Contributing and security

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [CHANGELOG.md](CHANGELOG.md)

Do not include API keys, credentials, private research data, absolute user paths, or proprietary project material in issues, tests, examples, or reports. The checker and examples are designed for synthetic fixtures only.
