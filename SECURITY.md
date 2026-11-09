# Security policy

## Supported version

Security fixes target the latest tagged release only; older releases do not get
fixes.

## Report a vulnerability

Use GitHub's
[private vulnerability reporting](https://github.com/marcuscavalcanti/007-framework/security/advisories/new)
for this repository. Do not open a
public issue containing credentials, private prompts, customer data, hidden test
bodies, or an exploit against a live system.

## Trust boundaries

007 Framework is instruction and local tooling. It does not grant permissions,
store provider credentials, or sandbox executors. The host application controls
authentication and filesystem/network access. Review agent commands and replay
sets before execution; they can invoke local tools with the host user's authority.

`replay_eval.py` validates task identifiers, exports a declared Git revision into
a fresh system temporary directory, and removes only that generated directory.
Keep source repositories and acceptance fixtures read-only to the agent arm.

## Repository checks

The CodeQL workflow analyzes Python and JavaScript on pull requests and main.
It retains SARIF as Actions artifacts for 14 days, with code-scanning and
database uploads disabled. Scorecard runs on main pushes or manual dispatch,
retaining JSON for 14 days with public result publication disabled. The reports
have the repository's artifact visibility. Both workflows use read-only
repository permissions, pinned actions and bounded jobs.

These checks produce findings for review. They do not qualify a runtime,
release or causal claim. The Scorecard action's transitive Docker image uses
the upstream version tag. Account settings and required checks are managed
separately by the maintainer.
