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

## Task-start selector

Put the routes you intentionally support in `~/.007-framework/routes.json` and
run `007 route --task-class inspect|implement|deep|design`. The command does not
discover credentials or invent provider policy. It only considers configured
commands present on `PATH` and receipts from the current Git repository. Both
text and JSON output identify the evidence scope as `repository-local`.

A route becomes measured-eligible after at least five mature matching outcomes
with reliable first-pass rate at least 70%, escape rate at most 5%, mean repair
rounds at most 0.5, and complete terminal cost and wall time. Among eligible
routes, choose the lowest all-attempt cost per reliable outcome; use wall time
and then route ID as deterministic tie-breakers. If none qualifies, use the
explicit available fallback. The returned JSON includes every rejection reason.

Selection happens once at task start. Switching providers during one attempt
destroys attribution and repays context, so escalation starts a new attempt and
receipt.

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
