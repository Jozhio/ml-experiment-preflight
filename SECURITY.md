# Security Policy

## Supported versions

The `0.1.x` development line is publicly available as source code. No production-ready release has been declared.

Security fixes are maintained for the current `0.1.x` line. Compatibility and security guarantees are limited to the verified scope documented below.

## Reporting a vulnerability

If you discover a potential security vulnerability, please report it privately through [GitHub Private Vulnerability Reporting](https://github.com/Jozhio/ml-experiment-preflight/security/advisories).

Private vulnerability reporting is enabled for this repository. The reporting entry point is available to external visitors.

Do not open a public issue or discussion containing unpatched vulnerabilities, credentials, private paths, research data, or exploit details.

When submitting a report, include the following information where safe:

- Affected version (`0.1.0` or later), operating system, Python version, and Git version.
- The smallest synthetic reproduction that demonstrates the issue.
- Relevant rule IDs, evidence codes, and observed versus expected behavior.
- Whether the issue may expose filesystem paths, access data outside the documented metadata boundary, execute unintended commands, or modify files.

Please avoid attaching real research data, credentials, or sensitive local files.

Reports will be reviewed by the repository maintainer. Confirmed vulnerabilities will be assessed and addressed according to their severity and impact.

## Verified scope for v0.1.0

- Local Windows 10.0.19045 / Python 3.11.0 / Git 2.54.0.windows.1: unit and end-to-end tests, package installation, and three synthetic examples were exercised on the release candidate.
- A public GitHub Actions workflow covers Ubuntu 24.04 and Windows with Python 3.11 and 3.12.
- The initial public source candidate passed all four CI jobs. Subsequent commits require their own CI verification; a successful earlier run does not establish the status of a later commit.
- Before creating a tagged release, all four CI jobs must pass on the exact release commit.
- Not fully verified: real Windows ACL denial, mapped or UNC network-volume behavior, full Windows process-tree termination, local Linux execution, local Windows Python 3.12 execution, and older Git versions.

Test coverage is not a formal security certification or a guarantee of correct behavior in every environment.

## Security model and boundaries

- The CLI is designed for **read-only, offline preflight checks**. It reads filesystem metadata and limited local Git metadata. It does not run model training, import user project modules, read dataset contents, or intentionally modify project files.
- An explicitly supplied mapped or network volume may cause operating-system network I/O during metadata access. Avoid such volumes when strict offline behavior is required.
- Git commands use fixed argument vectors, no shell, optional-lock avoidance, bounded output, and execution timeouts.
- The Git executable is selected from absolute PATH directories outside the checked project root and current working directory. Implicit current-directory executable lookup is not used.
- Executables available through caller-controlled PATH entries outside those boundaries remain a trust assumption. Use a trusted execution environment and PATH configuration.
- Git is optional. Unsupported repository layouts, unavailable Git executables, and unsafe or uncertain conditions must produce `unknown`, not `pass`.
- CLI reports are designed to avoid emitting absolute paths, filenames, environment values, or Git-tracked filenames. Shell command histories, terminal output, and execution-host logs may still contain sensitive information. Run checks against private projects locally and share only reviewed, redacted reports.
- The Agent Skill provides instructions for using the existing CLI. It does not override host permission policies or provide an execution sandbox.
- On Windows, process termination covers the directly launched Git process only. Full process-tree isolation is not guaranteed.
- External Git helper execution risks are mitigated through fixed commands, disabled FSMonitor and pager behavior, cleared `GIT_*` environment variables, and regression tests. These measures do not constitute a formal sandbox.
- Real Windows ACL denial is not exercised by the public test suite. Synthetic permission-denial tests do not establish full ACL compatibility.
- Linux/POSIX process-group behavior, real POSIX permissions, Windows symlinks and junctions beyond tested cases, UNC and mapped network paths, and older Git versions remain partially verified or environment-dependent.

## Known limitations

The following limitations are not vulnerabilities by themselves:

- Static metadata checks cannot establish dataset quality, scientific reproducibility, GPU/CUDA compatibility, dependency completeness, or successful model training.
- Results such as `unknown`, `incomplete`, `PERMISSION_DENIED`, and `SYMLINK_UNRESOLVED` indicate uncertainty or incomplete coverage. They must not be interpreted as successful validation.
- Time-of-check to time-of-use (TOCTOU) conditions and concurrent filesystem changes remain possible.
- Local Git configuration can influence Git behavior. Defensive overrides reduce selected risks but do not provide a formal isolation guarantee.
- Windows process-tree termination, mapped and network volumes, and real ACL behavior remain environment-dependent.
- A successful preflight result does not replace experiment execution, scientific validation, or a comprehensive security review.

## Dependencies and licensing

The runtime has no third-party Python dependencies. Python and Git are external tools.

`setuptools>=61` and `wheel` are build-time requirements.

The project is distributed under the MIT License. No vendored third-party source code is included.

If you identify potentially incompatible licensing, copied material, or a security concern involving dependencies, report it through the repository's private vulnerability reporting channel. Do not include sensitive information in public issues.
