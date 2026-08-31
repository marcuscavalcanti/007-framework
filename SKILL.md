---
name: 007-framework
description: >-
  Evidence-bounded orchestration for agentic software development. Use for
  planning, routing, implementing, fixing, refactoring, reviewing, or releasing
  code when minimal diffs, explicit proof, low rework, and auditable outcomes
  matter.
metadata:
  version: 1.2.0
---

# 007 Framework

Ship the smallest correct change, prove what happened, and learn only from
observable outcomes.

## Success order

Optimize in this order:

1. Correctness and no regression.
2. Low rework: code should remain useful without another human or agent rewrite.
3. Small context and smallest sufficient diff.
4. Cost and latency, measured for every terminal outcome.

Never trade a likely correction round for a cheaper first attempt.

## Before writing code

1. Read repository instructions and current handoff.
2. Inspect the exact call path and working-tree state.
3. Search for an existing implementation or native feature.
4. Declare the task class, proof level, diff budget, and escalation path.
5. Use a fresh, scoped session; persist state in files, not conversation history.
6. In an initialized project, run `007 begin --repo . --task-id <stable-id>`
   before implementation so an omitted terminal receipt remains visible.
   Hosts may use `007 run --receipt <file> -- <command>` to automate this
   lifecycle when the command emits the normalized receipt.

Reuse ladder: need at all → existing code → standard library → platform feature
→ installed dependency → one line → minimum new code.

## Route by risk

- **inspect**: read-only discovery, status, logs, narrow documentation lookup.
- **implement**: localized feature, bug fix, configuration, documentation, or
  mechanical refactor with clear acceptance criteria. This is the default.
- **deep**: architecture, security, concurrency, performance, subtle debugging,
  or recovery after two evidence-changing implementation attempts.
- **design**: visual or interaction work; the executor must be able to inspect
  rendered states.

Choose the cheapest verified executor likely to pass. Provider/model names are
runtime configuration, not doctrine. Verify the actual binding and served model;
record unavailable or unmeasured instead of guessing. See
[`references/routing.md`](references/routing.md).

## Execute with one writer

- Serial by default. Parallelize only independent reads or disjoint edits in
  isolated worktrees.
- One coordinator owns integration, staging, and the final harness.
- Fix root causes in the shared path, not symptoms in each caller.
- No drive-by refactor, speculative abstraction, or new dependency without a
  demonstrated need.
- Bug fixes leave one failing-then-passing regression check.

## Gate the outcome

Before claiming completion, run the repository's own tests, lint/type checks,
and any clean-source or runtime checks required by the declared proof level.
Tests written by the implementer are evidence, not independent judgment.
Classify failures as introduced, pre-existing, external, permission,
capability, or evidence-gap. Retry only when the hypothesis, input, capability,
or evidence changed.

Never claim above the evidence reached: a unit test is not integration; a clean
build is not production; a reviewer opinion is not runtime proof. Full gates:
[`references/quality-gates.md`](references/quality-gates.md).

## Return an observable outcome

Every coding task ends with:

```text
status: accepted | blocked | no-op
proof: <required> -> <reached>; <exact checks>
delta: <files, +lines/-lines, dependencies>
first_pass: yes | no | unmeasured; repair_rounds=<n|unmeasured>
rework: corrective_lines=<n|pending|unmeasured>; escape_7d=<yes|no|pending>
telemetry: model=<served|unmeasured>; effort=<served|unmeasured>; tokens=<n|unmeasured>; wall_s=<n|unmeasured>
cost: usd=<measured>; source=<provider-reported|rate-card-estimate|subscription-allocated|local-compute|custom:name>; status=<final|provisional>
uncertainty: <remaining evidence gap or none>
```

Missing telemetry stays `unmeasured` or `N/D`; never reconstruct it. Cost is a
hard KPI: use the exact served route and an explicit accounting source. Never
record missing cost as zero. In an initialized project, the operating contract
requires `007 begin` before implementation and `007 record` for every terminal
outcome. The commands reject unsafe or duplicate task IDs, and terminal receipts
reject unaccounted cost. The dependency-free core cannot detect a host that
omits both commands, so dashboard coverage is explicitly limited to observed
starts. Schema:
[`references/receipt-schema.md`](references/receipt-schema.md).

## Learn without Goodharting

Record manual rewrites as harness failures: what was wrong and which acceptance
criterion, context item, or test would have caught it. Measure first-pass rate,
corrective touch rate, repair rounds, and escapes. File overlap, line similarity,
and resemblance to a historical solution are diagnostic only.

Change at most one unvalidated doctrine mechanism per causal cycle. Compare OLD
and NEW on the same task, model, effort, environment, acceptance tests, and
replication count. Freeze inputs before execution. See
[`references/causal-testing.md`](references/causal-testing.md).

## Escalation

First failure: retry the same route only with new evidence. Second failure:
escalate one tier in a fresh session with a short file-based handoff. Never make
a third equivalent attempt. After recovery, classify whether routing or the
harness was wrong.

## Included tools

```bash
007 init --repo .
007 begin --repo . --task-id <stable-id>
007 record --repo . --file task.receipt.json
007 run --repo . --task-id <stable-id> --receipt task.receipt.json -- <command>
007 dashboard
python3 scripts/harness_report.py --receipt-dir .007/receipts --format json
python3 scripts/touch_rate.py --repo . --days 30
python3 scripts/replay_eval.py --set replay-set.json list
```

The scripts use only the Python standard library. They report unavailable data
honestly and do not replace repository-native tests.

## Read on demand

- [`references/routing.md`](references/routing.md) — routing, effort, isolation.
- [`references/quality-gates.md`](references/quality-gates.md) — proof and review.
- [`references/metrics.md`](references/metrics.md) — low-rework measurements.
- [`references/receipt-schema.md`](references/receipt-schema.md) — normalized output.
- [`references/causal-testing.md`](references/causal-testing.md) — OLD×NEW protocol.
