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

Economic eligibility uses the common cohort helper described in [metrics](metrics.md).
Matching starts must close at the cutoff, costs must have one explicit or
unambiguous USD basis, and accepted candidates need linked seven-day observations.
Unknown terminal route attribution cannot be discarded to make a route cheaper.
Measured selection additionally requires complete declared overhead scope on
the same USD basis. Scalar-only legacy records remain visible but no longer
qualify that economic gate; an explicitly configured fallback remains available.
The evidence scope remains supplied declarations; selection is not a causal
promotion of the route. Legacy frozen experiments keep their original evaluator
and do not qualify this changed selector automatically.

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

## Escalation economics (hypothesis, not proven)

A head-to-head comparison asks whether the cheaper effort is as good as the
expensive one. At a −5 pp non-inferiority margin and a 70% pass rate, that takes
about a thousand tasks per arm, more than one repository produces. A cascade
asks a smaller question: start low, and escalate only on a detected failure.

- If failures are detected and the escalated attempt starts fresh, the cascade
  succeeds at least as often as starting high:
  P(low ok) + P(low fails, high ok) ≥ P(high ok).
- It spends less agent time when p_low ≥ (ρ + q) / (1 + q), where ρ is the
  low/high time ratio and q is detection time over high time. That is a
  one-sample test against a threshold, feasible at one person's volume when
  p_low is high.

Both conditions break when detection breaks. In the exploratory holdout
simulation (13 tasks, 3 replicates each, the same data that suggested the
policy):

- Codex: the repository's suite caught every failure; `medium` then `xhigh`
  saved 22–39% of time with 39/39 accepted.
- Claude: the suite missed both `medium` failures (37/39; 9% saved, 95% CI −4
  to 21%). A stricter check caught them but raised 9 false alarms in 39 and was
  slower than `xhigh` (−26%, CI −52 to +2%).
- The 8 harder tasks cannot inform escalation: every effort solved every task.

Detection, not effort, is the binding constraint. A field reading with the
owner as the detector was pre-registered and then suspended before it started:
most sessions in the owner's history were launched by programs, not typed, and
the rest (about six in four weeks) could not reach a reading. Check who sends
the prompts before choosing the detector. When a program launches the session,
the cascade belongs in the launcher: start low, run the check, and relaunch one
tier higher on a detected failure. Treat the escalation rule above as practice,
not evidence.
