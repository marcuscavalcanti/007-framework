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
