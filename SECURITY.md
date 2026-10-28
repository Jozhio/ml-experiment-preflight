# Security Policy

## Supported versions

The `0.1.x` line is a pre-publication source release. This project has no supported production release yet. Security fixes are provided for the current `0.1.x` line.

## Reporting a vulnerability

Do not open a public issue, discussion, example, or report containing a vulnerability, credentials, private path, research data, or exploit details.

This source candidate is currently distributed privately; use the private maintainer/team channel through which this pre-release build was provided. If that channel is unavailable, report only a minimal, non-sensitive description and ask for a safe contact route.

Before any public release, the public repository must enable GitHub private vulnerability reporting (Security tab → Advisories → Report a vulnerability) and verify that the flow works. Until that channel is enabled and verified, this candidate is not approved for public release. The documentation will list the public reporting route only after it is actually available.

Include, where safe:

- affected version (`0.1.0`), platform, Python and Git versions;
- the smallest synthetic reproduction;
- the rule ID, evidence code, and observed versus expected behavior;
- whether the issue can expose a path, read outside the explicit metadata boundary, execute a command, or cause a write.

## Verified scope for v0.1.0

- Local Windows 10.0.19045 / Python 3.11.0 / Git 2.54.0.windows.1: unit/E2E tests, installation, and the three synthetic examples were exercised on the final candidate.
- A four-matrix GitHub Actions workflow (Ubuntu 24.04 and Windows; Python 3.11/3.12) is provided. Pre-publication runs are not public evidence; the public repository must run the workflow on the final public commit before release.
- Not fully verified: real Windows ACL denial, mapped or UNC network-volume behavior, full Windows process-tree termination, local Linux, local Windows Python 3.12, and older Git versions.

## Security model and boundaries

- The CLI is intended to be **read-only and offline**. It reads filesystem metadata and limited local Git metadata; it does not run training, import user modules, read data contents, or write project files. An explicitly supplied mapped/network volume can still cause operating-system network I/O during metadata access; avoid such volumes when strict offline behavior is required.
- Git commands use fixed argv, no shell, optional-lock avoidance, bounded output, and a timeout. The executable is selected from absolute PATH directories outside the checked root and current directory, never by implicit cwd lookup. A caller-controlled PATH outside those boundaries is still a trust assumption. Git is optional; unsupported layouts or unsafe conditions must become `unknown`, not `pass`.
- The CLI report is redacted: no absolute paths, file names, environment values, or Git file names are emitted. The original shell command and Agent host logs can still contain paths; run private projects locally and share only the redacted JSON.
- The Agent Skill is instructions plus the existing CLI. It does not declare `allowed-tools`; host permission rules still govern tool use. Skill text is not a sandbox.
- On Windows, process termination covers the direct Git process only. It is **not** a full process-tree isolation guarantee. External helper execution is mitigated by fixed commands, disabled FSMonitor/pager, cleared `GIT_*` environment, and marker tests, but is not a formal sandbox.
- Real ACL denial is not exercised by the public test suite. Synthetic permission-denial tests are not an ACL compatibility proof. Linux/POSIX process-group behavior, real POSIX permissions, real Windows symlinks/junctions beyond the tested synthetic cases, UNC/mapped network paths, and old Git versions are not fully verified.

## Known limitations that are not vulnerabilities by themselves

- Static metadata cannot prove data quality, reproducibility, GPU/CUDA compatibility, dependency completeness, or training success.
- `unknown`, `incomplete`, `PERMISSION_DENIED`, `SYMLINK_UNRESOLVED`, and similar outcomes are deliberate uncertainty, not a pass.
- TOCTOU and concurrent filesystem changes remain possible.
- A Git repository's local configuration can affect Git behavior; the checker applies defensive overrides, but this is not a formal sandbox proof.
- Windows process-tree termination, mapped/network volumes, and real ACL behavior remain environment-dependent limitations.

## Dependencies and licensing

The runtime has no third-party Python dependencies. Python and Git are external tools. `setuptools>=61` and `wheel` are build-time requirements. The project is MIT-licensed; no vendored third-party source is included. If you believe a contributed file has an incompatible license or copied material, report it through the private channel with the file path and source.
