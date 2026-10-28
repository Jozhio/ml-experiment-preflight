# Contributing

Thanks for considering a contribution. This project is a small, read-only preflight checker; keeping its scope and evidence boundaries stable matters more than adding features.

## Ground rules

- Use synthetic files and temporary local Git repositories only. Never commit or attach private research data, credentials, API keys, absolute user paths, or proprietary project material.
- Do not change the six public rules, JSON contract, or exit-code semantics without a design discussion, contract update, and tests. The current rules are `GIT-001/002/003` and `PATH-001/OUT-001/OUT-002`.
- Do not run training, import user project modules, read data contents, or add write-capable behavior to the checker.
- The CLI must remain usable with the Python standard library and an optional local Git executable. Do not add a runtime third-party dependency without an explicit design decision.
- Do not claim Linux, Windows 3.12, GitHub Actions, or host compatibility that has not actually been run.
- Contributions are accepted under the MIT license in [LICENSE](LICENSE). Do not contribute code copied from a project with an incompatible license.

## Development setup

### Windows PowerShell

```powershell
cd F:\path\to\ml-experiment-preflight
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
```

### Linux Bash

```bash
cd /path/to/ml-experiment-preflight
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

## Tests and examples

Run the complete synthetic unit suite:

```text
python -B -m unittest discover -s tests
```

Run the three synthetic examples and assert their expected results:

```text
python examples/verify_examples.py
```

Run the individual host-specific runners only when you need to verify the command shapes:

- Windows PowerShell: `powershell -NoProfile -File .\examples\normal\run.ps1`
- Linux Bash: `bash examples/normal/run.sh`

The `risk` and `conflict` examples intentionally exit `2` and `1`. They are expected results, not test failures.

## Skill changes

`SKILL.md` exists in both discovery locations and must remain byte-identical:

```text
.claude/skills/ml-experiment-preflight/SKILL.md
.agents/skills/ml-experiment-preflight/SKILL.md
```

After editing either file, copy it to the other path and run:

```text
python -B -m unittest discover -s tests -p "test_skill_contract.py"
```

Keep the frontmatter `name` equal to the parent directory, keep `description` within the Agent Skills specification limits, and keep the Skill version aligned with the package version (`0.1.0` for this release).

## Pull requests

A useful pull request includes:

- the problem and the smallest change that fixes it;
- tests or a reproducible synthetic fixture;
- the exact commands and results you ran, including platform and Python/Git versions;
- any remaining uncertainty or unverified platform;
- confirmation that no private data, credentials, absolute paths, or build artifacts were added.

Do not include a Release or publish a public repository as part of a normal contribution.

## Security

Do not open a public issue containing a vulnerability, private path, secret, or research data. Follow [SECURITY.md](SECURITY.md).
