# Routing

## Decision table

| Route | Default effort | Use | Do not use for |
|---|---:|---|---|
| inspect | low | read-only discovery, status, narrow docs | non-trivial implementation |
| implement | medium | scoped coding with explicit acceptance | unresolved architecture or security |
| deep | high | architecture, subtle debugging, security, concurrency, recovery | routine work “just in case” |
| design | medium/high | UI, UX, responsive and visual work | a model that cannot inspect visuals |

Model names are adapter configuration. A route is valid only when the runtime
confirms the executor, model, effort, and required capabilities. Record actual
served values; otherwise use `unmeasured`.

## Parallelism

Use one coordinator and the minimum workers. Parallel work is valid only for:

- independent read-only discovery; or
- disjoint edits in isolated worktrees with explicit owners.

Shared files, state, generated manifests, and lockfiles are serialized. Only the
coordinator integrates and runs the final harness.

## Handoff

Keep handoffs under 40 lines:

```markdown
# HANDOFF: <task> — <outcome>
## Constraints
- diff budget: <n>
- allowed paths: <paths>
- forbidden: <actions>
## Context
- <path:line and why>
## Checks
- <exact command>
## Done
- <observable criterion>
## Attempts not to repeat
- <approach and evidence>
```

Handoffs point to files; they do not paste the repository or conversation.

## Escalation

1. First failure: same route, fresh evidence only.
2. Second failure: one tier higher, fresh session and handoff.
3. No third equivalent attempt.

Provider switching repays context and changes the experiment. Keep one executor
per task unless the handoff explicitly starts a new attempt.
