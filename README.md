# ML Experiment Preflight

**Version 0.1.0 — pre-release.**

`ml-experiment-preflight` is a read-only, offline pre-training check for an explicitly named ML project. You give it a project root, an entry script, explicit input paths, and explicit output paths. Before you launch training, it reports deterministic evidence about Git state, missing or mistyped inputs, and output/input conflicts.

It does **not** inspect training-data contents, validate data quality, estimate GPU/VRAM use, resolve dependencies, score reproducibility, or run training.

## Quick start

Requirements: **Python 3.11+**. Git is optional for the CLI; the Git examples need it.

### 1. Clone or download

```bash
git clone https://github.com/Jozhio/ml-experiment-preflight.git
cd ml-experiment-preflight
```

If you downloaded a ZIP instead, `cd` into the extracted folder (the folder name may end in `-main`). Replace every placeholder path in this README with a real path on your machine.

### 2. Install the CLI in a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\ml-experiment-preflight.exe --help
```

Linux:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
ml-experiment-preflight --help
```

No PyPI package is published; install from this clone. `pip install .` may use the network to obtain its build requirements (`setuptools>=61` and `wheel`) when build isolation is enabled. The installed tool itself runs offline.

### 3. Run the bundled synthetic examples

The repository ships with three synthetic projects. They use placeholder files and local Git repositories; `train.py` is never executed and no research data is read.

Windows PowerShell (from the repository root):

```powershell
.\.venv\Scripts\python.exe -B .\examples\verify_examples.py
```

Linux (from the repository root):

```bash
.venv/bin/python -B examples/verify_examples.py
```

Expected result:

| Example | Overall | Exit | What to notice |
| --- | --- | --- | --- |
| `normal` | `clear` | `0` | all six rules pass with complete coverage |
| `risk` | `blocked` | `2` | `ENTRY_CHANGED`, `INPUT_MISSING`, `OUTPUT_EXISTS`; `OUT-002` is `unknown`; unknown is not a pass |
| `conflict` | `blocked` | `1` | `OUTPUT_EQUALS_INPUT_OR_ENTRY` critical; no unknown |

`risk` exits `2` even though it is `blocked` because one comparison is incomplete. Read the JSON first, then use the exit code as a secondary signal.

The verifier prefers an installed `ml-experiment-preflight` command when it is on PATH; with the explicit venv Python shown above it may fall back to the source in this clone. Both paths exercise the same code.

### 4. Try it on your own project

Replace the placeholder paths; relative paths are interpreted from `--root`, not from your shell's current directory.

Windows PowerShell:

```powershell
.\.venv\Scripts\ml-experiment-preflight.exe check `
  --root C:\path\to\your-project `
  --entry train.py `
  --input-file data\input.bin `
  --output-file runs\model.bin `
  --format json
```

Linux:

```bash
.venv/bin/ml-experiment-preflight check \
  --root "$HOME/projects/your-project" \
  --entry train.py \
  --input-file data/input.bin \
  --output-file runs/model.bin \
  --format json
```

The checker reads metadata and limited local Git metadata only. It does not run `train.py`, import project code, read input contents, write project files, or change Git state.

## What the result means

Each of the six rules returns one of three states:

- `pass`: the rule found no predefined issue in its limited scope. This is not a general safety claim.
- `finding`: the rule observed a specific risk. `warning` is a review item; `critical` is a high-priority conflict or missing target.
- `unknown`: the rule had insufficient evidence. **Never treat unknown as pass, clean, or verified.**

`overall` follows this priority: any critical finding → `blocked`; otherwise incomplete coverage → `incomplete`; otherwise warnings → `review`; otherwise `clear`.

| Exit | Meaning |
| --- | --- |
| `0` | `clear`: all six rules passed with complete coverage |
| `1` | known finding(s) with complete coverage (`review` or `blocked`) |
| `2` | incomplete coverage, usage error, or report-build failure |

Exit `2` can still contain a valid JSON report. Parse stdout first. If stdout is not JSON, treat it as a tool failure (`USAGE_ERROR` or `REPORT_ERROR`), not a project result.

## The six rules

The report always contains exactly six results in this order.

| Rule | What it checks | Finding | `unknown` examples |
| --- | --- | --- | --- |
| `GIT-001` | Root is a normal local `.git` repository with a resolvable HEAD and the repository top level equals `--root`. | warning `NO_REPOSITORY`, `NO_HEAD` | `GIT_UNAVAILABLE`, `GIT_ROOT_MISMATCH`, `UNSUPPORTED_GIT_LAYOUT`, `GIT_TIMEOUT`, `GIT_ERROR` |
| `GIT-002` | Only the explicitly named tracked entry has staged or worktree changes. | warning `ENTRY_CHANGED` | `ENTRY_UNAVAILABLE`, `ENTRY_NOT_TRACKED`, `GIT_ENTRY_FLAG_UNSUPPORTED`, `GIT_CONTEXT_UNKNOWN`, `GIT_TIMEOUT`, `GIT_ERROR`, `GIT_OUTPUT_LIMIT` |
| `GIT-003` | The explicitly named entry is tracked by the Git index. | warning `ENTRY_NOT_TRACKED` | `ENTRY_UNAVAILABLE`, `GIT_CONTEXT_UNKNOWN`, `GIT_TIMEOUT`, `GIT_ERROR` |
| `PATH-001` | Explicit entry and inputs exist with the declared file/directory type; the entry's physical target stays inside the root. | critical `ENTRY_MISSING`, `INPUT_MISSING`, `TYPE_MISMATCH`, `ENTRY_ESCAPES_ROOT` | `PERMISSION_DENIED`, `SYMLINK_UNRESOLVED`, `PATH_IO_ERROR`, `EVIDENCE_LIMIT` |
| `OUT-001` | Each output exists, matches the declared type, or has a resolvable parent. | warning `OUTPUT_EXISTS`; critical `OUTPUT_TYPE_MISMATCH` | `OUTPUT_PARENT_UNKNOWN`, `SYMLINK_UNRESOLVED`, `PERMISSION_DENIED`, `PATH_IO_ERROR` |
| `OUT-002` | Output equals an input/entry, contains an input/entry/root, or lies inside an input directory. Same-file identity uses `Path.samefile` for existing targets. | critical `OUTPUT_EQUALS_INPUT_OR_ENTRY`, `OUTPUT_DIR_CONTAINS_INPUT_OR_ROOT`; warning `OUTPUT_INSIDE_INPUT_DIR` | `PATH_COMPARISON_UNKNOWN`, `SYMLINK_UNRESOLVED`, `OUTPUT_PARENT_UNKNOWN`, `EVIDENCE_LIMIT` |

Git is optional. If Git is unavailable, the Git rules become `unknown`; the path/output rules still run. If a rule cannot decide, it must not be reported as `pass`.

## Paths and read-only behavior

| Option | Meaning | Relative to | Requirements |
| --- | --- | --- | --- |
| `--root` | the project directory used as the path base and Git root | your current directory | must exist and be a directory |
| `--entry` | the training entry script | `--root` | must exist as a file; its physical target must stay inside `--root`; it is never executed |
| `--input-file` / `--input-dir` | explicitly declared inputs | `--root` | may be outside the root; metadata only; file contents are not read and directories are not enumerated |
| `--output-file` / `--output-dir` | explicitly declared outputs | `--root` | may be outside the root; may be absent if the parent is resolvable; the checker never creates it |

Provide at least one input and one output. Each group accepts at most 32 entries. Wildcards, environment-variable expansion, `@file`, and automatic directory discovery are not supported. Paths are explicit: the checker does not scan the project or guess missing paths.

Path conventions in this README: `ml-experiment-preflight` is the clone directory; `train.py`, `data/input.bin`, and `runs/model.bin` are paths relative to `--root`; `C:\path\to\your-project` and `$HOME/projects/your-project` are placeholders you must replace. `.claude/...`, `.agents/...`, `examples/...`, and `docs/...` are paths inside this repository.

The check is a read-only snapshot: it does not run training, import project modules, read data contents, create files, or modify Git state. Text output is human-readable; Agents should request `--format json`. There is no `--write`, `--fix`, `--upload`, or `--scan-all`.

Representative JSON shape (six results are always present; full schema in [docs/CLI_CONTRACT.md](docs/CLI_CONTRACT.md)):

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
  "overall": {"status": "clear", "finding_count": 0, "unknown_count": 0},
  "results": [
    {"rule_id": "GIT-001", "status": "pass", "severity": "none", "coverage_complete": true, "reason_code": null, "unknown_refs": [], "evidence": [{"code": "REPOSITORY_WITH_HEAD", "refs": ["root"]}]},
    {"rule_id": "GIT-002", "status": "pass", "severity": "none", "coverage_complete": true, "reason_code": null, "unknown_refs": [], "evidence": [{"code": "ENTRY_UNCHANGED", "refs": ["entry"]}]},
    {"rule_id": "GIT-003", "status": "pass", "severity": "none", "coverage_complete": true, "reason_code": null, "unknown_refs": [], "evidence": [{"code": "ENTRY_TRACKED", "refs": ["entry"]}]},
    {"rule_id": "PATH-001", "status": "pass", "severity": "none", "coverage_complete": true, "reason_code": null, "unknown_refs": [], "evidence": []},
    {"rule_id": "OUT-001", "status": "pass", "severity": "none", "coverage_complete": true, "reason_code": null, "unknown_refs": [], "evidence": []},
    {"rule_id": "OUT-002", "status": "pass", "severity": "none", "coverage_complete": true, "reason_code": null, "unknown_refs": [], "evidence": []}
  ]
}
```

## Agent Skill installation and use

The CLI is the checker. The Agent Skill is optional instructions that tell Claude Code or Codex how to call the same CLI, interpret the JSON, and avoid unsafe actions. Install the CLI first; the Skill does not install it and is not a sandbox.

### Project-level Skill paths

| Host | Path in your project | How to invoke |
| --- | --- | --- |
| Claude Code | `.claude/skills/ml-experiment-preflight/SKILL.md` | `/ml-experiment-preflight ...` or a natural-language request |
| Codex | `.agents/skills/ml-experiment-preflight/SKILL.md` | `$ml-experiment-preflight ...` or `/skills` in the Codex IDE |

These paths follow the official conventions: [Claude Code Skills](https://code.claude.com/docs/en/skills), [Codex Build skills](https://learn.chatgpt.com/docs/build-skills), and the [Agent Skills specification](https://agentskills.io/specification). Host-native discovery, automatic selection, and permission behavior vary by host version and configuration; this project does not claim uniform behavior across hosts. AionUi native Skill discovery is not verified; you can read `SKILL.md` and run the CLI manually, but that is not native AionUi compatibility.

The two copies in this repository are byte-identical (SHA-256 `a7cf67ff94fac04186530e1318b115c4d77504d8d87d52951baa42befa1f3a1c`). If you install both hosts, keep your copies identical.

### Copy the Skill into your own project

Windows PowerShell — from the `ml-experiment-preflight` clone:

```powershell
$src = (Resolve-Path .\.claude\skills\ml-experiment-preflight).Path
cd C:\path\to\your-project
New-Item -ItemType Directory -Force .\.claude\skills\ml-experiment-preflight | Out-Null
Copy-Item -Recurse -Force "$src\*" .\.claude\skills\ml-experiment-preflight
```

For Codex, use `.agents\skills\ml-experiment-preflight` for both `$src` and the destination.

Linux — from the `ml-experiment-preflight` clone:

```bash
src="$(pwd)/.claude/skills/ml-experiment-preflight"
cd "$HOME/projects/your-project"
mkdir -p .claude/skills/ml-experiment-preflight
cp -R "$src/." .claude/skills/ml-experiment-preflight/
```

For Codex, use `.agents/skills/ml-experiment-preflight` for `src` and the destination. Replace `C:\path\to\your-project` / `$HOME/projects/your-project` with your own project directory.

The Skill asks for explicit `--root`, `--entry`, inputs, and outputs; it runs only the read-only CLI, interprets the JSON, and does not run training, import project code, read data contents, write Git state, or perform fixes without user confirmation. See [the Claude Code Skill](.claude/skills/ml-experiment-preflight/SKILL.md) and [docs/SKILL_INTEGRATION.md](docs/SKILL_INTEGRATION.md).

## Synthetic examples

Three synthetic projects live under [`examples/`](examples/): `normal`, `risk`, and `conflict`. Each runner copies its fixture to a temporary directory, creates a local Git repository, runs the CLI, and removes the temporary directory. No real data is read and `train.py` is never executed.

From the repository root:

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -B .\examples\verify_examples.py
```

Linux:

```bash
.venv/bin/python -B examples/verify_examples.py
```

To inspect one case at a time:

```powershell
powershell -NoProfile -File .\examples\normal\run.ps1
powershell -NoProfile -File .\examples\risk\run.ps1
powershell -NoProfile -File .\examples\conflict\run.ps1
```

```bash
bash examples/normal/run.sh
bash examples/risk/run.sh
bash examples/conflict/run.sh
```

`risk` and `conflict` intentionally exit `2` and `1`; that is the expected result, not a script failure. See [examples/README.md](examples/README.md) for details.

## Uninstall

Windows PowerShell (from the repository root):

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y ml-experiment-preflight
Remove-Item -Recurse -Force .venv
```

Linux (from the repository root):

```bash
. .venv/bin/activate
python -m pip uninstall -y ml-experiment-preflight
deactivate
rm -rf .venv
```

If the console script is unavailable but the package is installed/importable, use `python -m ml_experiment_preflight check ...` with the same arguments.

## Privacy and limitations

- **Read-only:** reads filesystem metadata and limited local Git metadata; does not execute training or user code, import project modules, read data contents, create files, or modify Git state.
- **Explicit paths only:** does not scan a project, enumerate input directories, or guess missing paths.
- **Offline intent:** no upload, telemetry, or network API. Obvious UNC paths are rejected or marked `unknown`; metadata access on a user-supplied mapped/network volume may still cause operating-system network I/O.
- **Redacted reports:** JSON contains rule/evidence codes and symbolic refs only. Absolute paths, file names, environment values, and Git file names are omitted. The original command and host/tool logs may still contain paths; run private projects locally and share only the redacted JSON.
- **Git is optional:** missing Git or an unsupported layout produces `unknown`, not `pass`. Git is resolved from absolute PATH directories outside the checked root and current directory; a caller-controlled PATH remains a trust assumption.
- **Static snapshot:** TOCTOU, concurrent changes, symlinks, permissions, network paths, and cross-volume identity remain limitations. UNC roots/entries are rejected; UNC inputs/outputs are `unknown`; mapped paths are not exhaustively detected. Windows process-tree termination is not guaranteed beyond the direct process.
- **Not a data or reproducibility audit:** no data quality, labels, schema, GPU/CUDA, dependency resolution, performance, or full reproducibility proof.
- **Skill permissions:** the Skill does not declare `allowed-tools`; host permission rules still govern tool calls. Skill text is not a sandbox.

For the security policy and private vulnerability reporting, see [SECURITY.md](SECURITY.md).

## Compatibility

Only the following environments have actually been exercised. `Not run` rows are not support claims.

| Environment | Status |
| --- | --- |
| Windows 10.0.19045; Python 3.11.0; Git 2.54.0.windows.1 | Local final-candidate run: 127 unittest tests, 0 failures, 5 skips, exit 0; all three synthetic examples verified. |
| Linux / Windows Python 3.12 (local) | Not run locally. |
| Public GitHub Actions | The [initial public candidate run](https://github.com/Jozhio/ml-experiment-preflight/actions/runs/40710712840) passed all four jobs (Ubuntu 24.04 and Windows; Python 3.11/3.12). Each new commit, including documentation changes, must pass its own CI run before merge. |
| Claude Code / Codex project-level Skill | Both discovery paths and byte-identical copies are provided. Native host discovery was not independently re-verified for this public tree; behavior varies by host and version. |
| AionUi | No native Skill discovery is claimed. |

The local Windows run had 5 skips: 4 POSIX-only tests and 1 Windows symlink-privilege test.

## License and contributing

MIT. See [LICENSE](LICENSE). No third-party runtime dependencies; `setuptools>=61` and `wheel` are build-time requirements. Git and Python are external tools, not bundled components.

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [CHANGELOG.md](CHANGELOG.md)
- [CLI contract](docs/CLI_CONTRACT.md)
- [Rule specification](docs/RULE_SPECIFICATION.md)
- [Synthetic examples](examples/README.md)
- [Competitor analysis](docs/COMPETITOR_ANALYSIS.md)

Do not include API keys, credentials, private research data, absolute user paths, or proprietary project material in issues, tests, examples, or reports. The checker and examples are designed for synthetic fixtures only.
