---
name: ml-experiment-preflight
description: Run a read-only pre-training preflight for an explicitly named ML project root, entry script, input paths, and output paths, then interpret the deterministic JSON result. Use before launching training when the user asks to check Git/version-control state, missing or mistyped inputs, or output/input overwrite or ancestor conflicts. Also trigger for Chinese requests such as 训练前预检、启动前检查、Git 入口未提交、输入路径缺失、输出覆盖输入. Do not use for data-content quality, GPU/VRAM estimation, dependency resolution, reproducibility scoring, or running training.
compatibility: Requires Python 3.11+ and an importable ml_experiment_preflight package; Git is optional; no network or third-party runtime dependencies.
metadata:
  version: "0.1.0"
  project: ml-experiment-preflight
---

# ML Experiment Preflight

## Purpose

Use the existing `ml-experiment-preflight` Python CLI as the only checker. The CLI performs six deterministic, metadata-only rules: GIT-001/002/003 and PATH-001/OUT-001/OUT-002. Do not reimplement these rules, infer their results, or replace the CLI with an LLM judgment.

The result is a snapshot of explicit paths. It is not a data audit, a reproducibility proof, a GPU/CUDA validation, or a guarantee that training will succeed.

## Non-negotiable boundaries

- Never run training, evaluation, or any user script.
- Never import user Python modules and never execute project code.
- Never read the contents of training data, checkpoints, logs, or secrets.
- Never recursively scan the project or guess paths.
- Never create, edit, move, or delete user experiment files.
- Never run `git add`, `git commit`, `git checkout`, `git restore`, `git clean`, or any write-capable Git command.
- Never upload the report, paths, or project data to an external service.
- Do not infer missing paths from a directory listing. Ask the user for every explicit path.
- If the user has not supplied a required path, stop and ask. Do not run the CLI with guessed values.

## Required explicit inputs

Ask the user for:

1. `--root`: an existing project directory.
2. `--entry`: the training entry script.
3. At least one explicit input: `--input-file` or `--input-dir`.
4. At least one explicit output: `--output-file` or `--output-dir`.

Use the exact paths the user provides. Keep the file/directory flags the user chose. Do not add wildcards, environment-variable expansion, `@file`, or automatic discovery.

Before running anything, confirm that the user wants this read-only preflight. Running the CLI is a Bash/tool action and may require host approval; do not treat the skill invocation as permission to run unrelated commands.

## Run the deterministic CLI

Prefer the installed console script:

```text
ml-experiment-preflight check --root ROOT --entry ENTRY \
  --input-file INPUT --output-file OUTPUT --format json
```

If the console script is not available but the package is importable, use:

```text
python -m ml_experiment_preflight check --root ROOT --entry ENTRY \
  --input-file INPUT --output-file OUTPUT --format json
```

Use `--input-dir` and/or `--output-dir` when the user supplied directories. The CLI requires at least one input and one output and accepts at most 32 of each. Do not add any option that is not documented by the CLI (`--write`, `--fix`, `--upload`, `--scan-all`, etc. do not exist).

Run from a normal local shell with the user's environment. Capture stdout, stderr, and the exit code. Do not redirect the report into the checked project unless the user explicitly asks and approves a destination outside the project.

If the command is unavailable, fail with a clear setup message such as "The ml-experiment-preflight CLI is not installed or importable." Do not emulate the rules or invent output.

## Interpret JSON

The CLI's `--format json` output is one JSON object. Parse it; do not treat text-mode output or the exit code alone as the result.

Top-level fields:

- `schema_version`, `tool_version`, `scope`
- `overall`: `status` (`clear`, `review`, `blocked`, `incomplete`), `finding_count`, `unknown_count`
- `results`: exactly six rule results in fixed order:
  `GIT-001`, `GIT-002`, `GIT-003`, `PATH-001`, `OUT-001`, `OUT-002`

Each result has:

- `status`: `pass`, `finding`, or `unknown`
- `severity`: `none`, `warning`, or `critical`
- `coverage_complete`: true only when all relevant targets were decidable
- `reason_code`, `unknown_refs`, `evidence`
- `evidence` items contain `code` and `refs` such as `root`, `entry`, `input:1`, `output:1`

Interpretation rules:

- `pass` means only that the rule found no predefined issue in its limited scope. It is not a claim that the experiment is safe.
- `finding` with `warning` is a review item; `finding` with `critical` is a high-priority conflict or missing target.
- `unknown` means evidence was insufficient. **Never describe unknown as pass, clean, or verified.**
- `coverage_complete=false` means the comparison is incomplete even if another finding exists.
- `overall=blocked` means at least one critical finding. Always state `blocked` explicitly; never hide it behind a summary count.
- `overall=incomplete` means at least one rule could not be decided. Do not describe it as clear.
- `overall=review` means warnings without critical findings or incomplete coverage.
- `overall=clear` means all six rules passed with complete coverage.

Exit codes:

- `0`: clear
- `1`: known finding with complete coverage (review or blocked)
- `2`: incomplete coverage, usage error, or report failure
- Exit code `2` may still carry a valid JSON report. Parse stdout before concluding anything.
- If stdout is not a JSON object, report `USAGE_ERROR` or `REPORT_ERROR` as a tool failure. Do not infer a project pass or a rule result.

## Report to the user

Use a compact, evidence-driven summary:

1. **Overall**: `clear`, `review`, `blocked`, or `incomplete`; state that this is a static, explicit-path snapshot.
2. **Critical findings**: rule ID, evidence code, refs, and what the conflict means.
3. **Warnings**: rule ID, evidence code, refs, and the review question.
4. **Unknowns**: rule ID, reason code, unknown refs, and what could not be checked.
5. **Limits**: no data content, no runtime, no GPU/CUDA, no reproducibility proof; unknown is not pass.

For every critical, warning, or unknown result, give an actionable suggestion, but do not execute it:

- `ENTRY_MISSING` / `INPUT_MISSING`: ask the user to correct the explicit path; do not create or copy files.
- `TYPE_MISMATCH`: ask whether the path should be a file or directory; do not change it.
- `ENTRY_ESCAPES_ROOT`: ask the user to confirm the intended entry and root; do not move files.
- `ENTRY_CHANGED`: suggest reviewing, committing, or stashing the entry change; do not run Git write commands.
- `ENTRY_NOT_TRACKED`: suggest `git add` after user review; do not run it.
- `OUTPUT_EXISTS`: ask whether the run is a resume or whether a new output path is intended; do not delete or overwrite.
- `OUTPUT_TYPE_MISMATCH`: ask the user to choose a file or directory path; do not modify it.
- `OUTPUT_EQUALS_INPUT_OR_ENTRY` / `OUTPUT_DIR_CONTAINS_INPUT_OR_ROOT`: suggest choosing a different output path; do not move or delete existing data.
- `OUTPUT_INSIDE_INPUT_DIR`: warn that output placement may contaminate later input discovery; ask the user to confirm; do not reorganize directories.
- `NO_REPOSITORY` / `NO_HEAD`: suggest initializing or committing only after user decision; never do it automatically.
- `PERMISSION_DENIED`, `SYMLINK_UNRESOLVED`, `PATH_IO_ERROR`, `OUTPUT_PARENT_UNKNOWN`, `PATH_COMPARISON_UNKNOWN`: ask the user to inspect the target and permissions; do not bypass ACLs or create parent directories.
- `GIT_CONTEXT_UNKNOWN`, `GIT_ENTRY_FLAG_UNSUPPORTED`, `GIT_ERROR`, `GIT_TIMEOUT`, `GIT_OUTPUT_LIMIT`, `UNSUPPORTED_GIT_LAYOUT`, `GIT_ROOT_MISMATCH`: report the limitation; do not infer a Git pass.

When referring to targets, use only the report's refs (`root`, `entry`, `input:N`, `output:N`). Do not print guessed filenames or absolute paths that are not in the user's original request. The JSON deliberately contains no path mapping.

## Privacy and approval boundary

- The CLI is read-only and offline, but the host's tool log may still contain the original command-line paths. Do not upload or paste host logs.
- For private projects, recommend running the CLI locally and sharing only the redacted JSON.
- Ask before any command that could write, open a network connection, install packages, or change Git state.
- Do not expand the scope to "fix" the project. The skill reports and suggests; the user decides and executes.

## Limitations to state every time

- Metadata-only snapshot at check time; TOCTOU and concurrent changes remain.
- No training data content, labels, schemas, or quality checks.
- No runtime environment, GPU/CUDA, dependency resolution, or performance validation.
- Git rules cover only the explicitly named entry and the documented repository layouts.
- `unknown` and `incomplete` are real outcomes, not failures to be smoothed over.

## Minimal example

User: "Run the preflight for root `/tmp/demo`, entry `train.py`, input `data/input.bin`, output `runs/model.bin`."

Agent: run the CLI with `--format json`, then report:

- Overall: `clear` (if all six pass) — static snapshot only.
- Or Overall: `blocked` with `OUT-002/OUTPUT_EQUALS_INPUT_OR_ENTRY`; suggest a different output path, do not move anything.
- Or Overall: `incomplete` with `GIT-002/unknown`; state that the entry change state was not verified and do not call it clean.
