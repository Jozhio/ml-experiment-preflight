# Synthetic examples

These examples use only synthetic files and temporary Git repositories. They never execute `train.py`, never read training data, and never modify this repository.

Requirements: Python 3.11+ and Git. The scripts use the installed `ml-experiment-preflight` command when available; otherwise they add `src/` to `PYTHONPATH` and use `python -m ml_experiment_preflight`.

## Expected results

| Example | What it contains | Expected CLI result | Expected exit |
| --- | --- | --- | --- |
| `normal` | committed entry; existing input; absent output | all six rules pass; `overall=clear` | 0 |
| `risk` | modified entry; missing input; existing output | `ENTRY_CHANGED`, `INPUT_MISSING`, `OUTPUT_EXISTS`; `OUT-002` unknown; `overall=blocked` | 2 |
| `conflict` | input and output are the same file | `OUTPUT_EQUALS_INPUT_OR_ENTRY` critical; `overall=blocked` | 1 |

## Reproduce all three

### Windows PowerShell

```powershell
cd F:\path\to\ml-experiment-preflight\examples
python .\verify_examples.py
```

### Linux Bash

```bash
cd /path/to/ml-experiment-preflight/examples
python3 verify_examples.py
```

`verify_examples.py` creates isolated temporary projects, initializes local Git repositories, runs the CLI, asserts the expected statuses/exit codes, and prints a one-line summary per case.

## Run each example script

Each runner copies its fixture into a fresh temporary directory, creates a local Git repository, runs the read-only CLI, prints the expected/actual exit code, and removes the temporary directory.

### Windows PowerShell

Risk and conflict intentionally exit non-zero; that is the expected result, not a script failure.

```powershell
cd F:\path\to\ml-experiment-preflight\examples
powershell -NoProfile -File .\normal\run.ps1
powershell -NoProfile -File .\risk\run.ps1
powershell -NoProfile -File .\conflict\run.ps1
```

### Linux Bash

Risk and conflict intentionally exit non-zero; that is the expected result, not a script failure.

```bash
cd /path/to/ml-experiment-preflight/examples
bash normal/run.sh
bash risk/run.sh
bash conflict/run.sh
```

The PowerShell scripts use Windows PowerShell syntax; the Bash scripts use POSIX shell syntax. Do not mix the two continuation styles. If Git is not installed, the Git-related examples cannot run; the CLI itself reports Git rules as `unknown`.

## No real projects or data

The `fixture/` files are placeholders. The entry files are never executed. No API keys, credentials, research data, or user paths are included.
