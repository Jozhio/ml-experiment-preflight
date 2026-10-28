# Changelog

All notable changes to this project are documented here.

## [0.1.0] - 2026-10-28

### Added

- Read-only Python CLI for six deterministic preflight rules:
  `GIT-001`, `GIT-002`, `GIT-003`, `PATH-001`, `OUT-001`, `OUT-002`.
- Stable JSON report with fixed rule order, pass/finding/unknown states, severity, coverage, evidence codes, and symbolic refs.
- Text output and exit codes `0`/`1`/`2`.
- Explicit-path validation, component-level output/input comparison, symlink/hardlink identity checks, and conservative unknown handling.
- Safe Git adapter with fixed argv, no shell, `--no-optional-locks`, `--no-lazy-fetch`, `--literal-pathspecs`, `--no-pager`, bounded output capture, timeout, environment isolation, and FSMonitor/ignoreStat/untrackedCache overrides.
- Project-level Agent Skill for Claude Code (`.claude/skills/ml-experiment-preflight/SKILL.md`) and Codex (`.agents/skills/ml-experiment-preflight/SKILL.md`), version `0.1.0`.
- Three synthetic examples (`normal`, `risk`, `conflict`) with PowerShell and Bash runners and a cross-platform verifier.
- Windows/Linux GitHub Actions workflow for the standard-library unittest suite.

### Security

- Bounded Git output capture with process termination and no pass on overflow/timeout.
- External helper marker regressions for filters, external diff, textconv, FSMonitor, and hooks.
- Synthetic-only tests, no private research data, no credentials.
- Git executable lookup is restricted to absolute PATH directories outside the checked root and current directory; UNC roots are rejected and non-alias absolute entry paths are not resolved.

### Documentation

- English and Chinese READMEs, installation/verification guidance, Skill integration guidance, contributing/security/changelog documents.
- Compatibility evidence includes a local Windows/Python 3.11 final-candidate run. The public repository must run the four-matrix GitHub Actions workflow on the final public commit; pre-publication CI is not a public compatibility claim.

### Known limitations

- Local Linux and local Windows Python 3.12 runs were not performed; the public repository must run its own four-matrix CI before release.
- Native automatic Skill selection and AionUi native Skill discovery are not verified.
- Windows terminates only the direct Git process; full process-tree isolation is not guaranteed.
- This is a source-only release; no PyPI package is published for this version.
