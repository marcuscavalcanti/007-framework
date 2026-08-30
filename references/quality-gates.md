# Quality gates

## Declare proof before editing

Choose the minimum sufficient level:

1. **focused** — the changed behavior and regression check.
2. **integrated** — repository harness, lint and type checks.
3. **clean-source** — same checks from a fresh checkout/install.
4. **remote** — CI or review system observed on the committed source.
5. **runtime** — deployed behavior or production-equivalent probe.

Completion requires the declared level, not the largest level convenient to
claim afterward.

## Implementation gate

- scope and diff match the task;
- no unrelated working-tree changes were overwritten;
- root cause is handled in the shared path;
- regression protection covers the changed behavior;
- failures are classified, not silently retried;
- rollback or reversibility is stated for risky changes;
- no secret, private fixture, or customer data enters receipts.

## Independent review

Use an independent reviewer for architecture, security, release, destructive,
or high-cost decisions. The reviewer receives a sanitized frozen context and
cannot mutate the source. Reviewer approval is necessary where policy requires
it, but never substitutes for executable proof or human release authority.

## Release gate

A release is valid only when its exact committed bytes pass the required checks,
the evidence report is committed, the worktree is clean, and the tag points to
that commit. Package existence is not release evidence.
