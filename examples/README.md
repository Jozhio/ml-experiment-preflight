# Synthetic examples

These examples use only synthetic files and temporary Git repositories. They never execute `train.py`, never read research data, and never modify this repository.

Requirements: Python 3.11+ and Git. The scripts use the installed `ml-experiment-preflight` command when available; otherwise they add `src/` to `PYTHONPATH` and use `python -m ml_experiment_preflight`.

For the full first-run walkthrough, see the [Quick start](../README.md#quick-start).

## Expected results

| Example | What it contains | Expected CLI result | Exit |
| --- | --- | --- | --- |
| `normal` | committed entry; existing input; absent output | all six rules pass; `overall=clear`; no unknown | `0` |
| `risk` | modified entry; missing input; existing output | `ENTRY_CHANGED`, `INPUT_MISSING`, `OUTPUT_EXISTS`; `OUT-002` is `unknown`; `overall=blocked`; 3 findings / 1 unknown | `2` |
| `conflict` | input and output are the same file | `OUTPUT_EQUALS_INPUT_OR_ENTRY` critical; `overall=blocked`; 2 findings / 0 unknown | `1` |

`clear` means all six rules passed with complete coverage. `blocked` means at least one critical finding. `unknown` means the tool could not decide; it is not a pass, and `risk` exits `2` because one comparison is incomplete.

## Run all three

Run these commands from the repository root after installing the CLI. The fixture paths are relative to this repository; the runners create their own temporary projects.

### Windows PowerShell

```powershell
.\.venv\Scripts\python.exe -B .\examples\verify_examples.py
```

If the venv is already activated, `python -B examples\verify_examples.py` is equivalent.

### Linux Bash

```bash
.venv/bin/python -B examples/verify_examples.py
```

If the venv is already activated, `python -B examples/verify_examples.py` is equivalent.

`verify_examples.py` creates isolated temporary projects, initializes local Git repositories, runs the CLI, asserts the expected statuses and exit codes, and prints a one-line summary per case.

## Run each example

Each runner copies its fixture into a fresh temporary directory, creates a local Git repository, runs the read-only CLI, prints the expected/actual exit code, and removes the temporary directory.

### Windows PowerShell

From the repository root:

```powershell
powershell -NoProfile -File .\examples\normal\run.ps1
powershell -NoProfile -File .\examples\risk\run.ps1
powershell -NoProfile -File .\examples\conflict\run.ps1
```

### Linux Bash

From the repository root:

```bash
bash examples/normal/run.sh
bash examples/risk/run.sh
bash examples/conflict/run.sh
```

`risk` and `conflict` intentionally exit `2` and `1`; that is the expected result, not a script failure. The PowerShell scripts use Windows PowerShell syntax; the Bash scripts use POSIX shell syntax. Do not mix the two continuation styles.

If Git is not installed, the Git-related examples cannot run; the CLI itself reports Git rules as `unknown`.

## Fixtures and paths

- `fixture/` files are placeholders; `train.py` is never executed.
- The runners create projects under the system temporary directory and remove them afterward.
- The commands above are relative to this repository. No user project path is required for the examples.
- No API keys, credentials, research data, or user paths are included in the fixtures.
