# Contributing

The rules for people and agents are in [AGENTS.md](AGENTS.md): proof by
contribution type, evidence integrity, privacy, licensing and review. Copilot
reads the same file as `.github/copilot-instructions.md`, and Claude Code reads
it through `CLAUDE.md`; a test fails if the copy drifts.

## Quick start

Python 3.11+ and Git; no other dependency.

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
```

CI runs the same commands on Python 3.11, 3.12 and 3.13, without secrets, so a
pull request from a fork gets the same checks.

Participation follows the [code of conduct](CODE_OF_CONDUCT.md). Report vulnerabilities privately
([SECURITY.md](SECURITY.md)), not in an issue.
Maintainers release by [RELEASING.md](RELEASING.md).
