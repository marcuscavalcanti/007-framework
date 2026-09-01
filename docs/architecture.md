# Architecture

007 Framework is a stateless instruction package. The coding-agent host executes
models and tools; the repository remains the source of truth.

```text
task + repo rules
       │
       ▼
scope and route ──► controlled execution ──► repository-native gates
       │                                         │
       └──────── declared proof ─────────────────┘
                                                 ▼
                                      receipt + rework sensors
                                                 │
                                                 ▼
                                      bounded doctrine experiment
```

## Components

- `SKILL.md`: compact operating contract loaded for coding work.
- `references/`: details loaded only when the task needs them.
- `scripts/harness_report.py`: aggregates existing task receipts.
- `scripts/touch_rate.py`: approximates attributable code survival from Git.
- `scripts/replay_eval.py`: runs frozen OLD×NEW policies against reconstructed
  historical source and task-specific acceptance commands.
- `bin/007` and `scripts/framework_cli.py`: initialize projects, atomically
  persist task starts, controller-observed action events, and terminal receipts,
  select a task-start route, and launch the local dashboard.
- `scripts/dashboard.py` and `dashboard/`: aggregate registered projects and
  serve a loopback-only, dependency-free control room.
- `scripts/local_activity.py`: normalize sanitized Codex, Claude, Kimi, and
  Gemini metadata/token deltas, reconcile Git worktrees, and cache unchanged logs.
- `scripts/headroom_pricing.py`: optional local worker using Headroom's LiteLLM
  model resolution and per-token pricing; it receives no transcript content.
- `tests/`: protects package identity, public boundaries, and script behavior.

## State model

The framework owns only local measurement state: a project marker, task starts,
controller events, and receipts under `.007/`, plus the user-level project registry at
`~/.007-framework/projects.json`. `007 init` excludes `.007/` through the local
Git exclude file, so telemetry does not dirty or alter repository history.
Durable engineering authority remains in Git, repository instructions, tests,
and task handoffs. Conversations and raw transcripts are temporary context, not
operational authority.

The browser polls a read-only aggregate snapshot every two seconds. The snapshot
derives one three-state objective verdict, seven literal gates, evidence
provenance, and a 30-day raw-count trend from the same project totals. The HTTP
server binds to `127.0.0.1` by default and exposes only allowlisted static and
JSON routes. Aggregate metrics are recomputed from raw project totals; project
percentages are never averaged. JSON receipts remain the source of truth. A
database is intentionally deferred until measured volume or query latency makes
the standard-library scan insufficient.

Known gate failures take precedence in the verdict even while a measurement
gate is incomplete; the primary action still prioritizes closing that data gap.
An invalid or unavailable source keeps the overall verdict not measurable
because the missing record can change the denominator; any failure among valid
records remains visible in its individual gate.
Controller blocks that prevent execution are authority events, not software
outcomes, and are excluded from the quality trend and model-telemetry
denominator.

The snapshot publishes `telemetry_fields` alongside the completeness numerator
and denominator so consumers can see that V1.1 measures provider, model, effort,
tokens, and wall time.

The experimental route recommender reads normalized receipts from the current
repository only. It filters by task class and exact served binding and returns one
deterministic recommendation before execution. It is observational, not a
certified runtime selector, and never starts the recommended command. There is
no daemon, gateway, database, background agent, or mid-attempt rerouting.

## Trust boundaries

1. **Host boundary:** authentication, model binding, permissions, and sandboxing
   belong to the agent host.
2. **Repository boundary:** native tests and policies outrank framework prose.
3. **Acceptance boundary:** hidden tests are applied after an experimental agent
   exits and are never placed in its workspace.
4. **Review boundary:** an external reviewer receives sanitized frozen bytes and
   cannot replace executable proof or human release authority.
5. **Evidence boundary:** receipts record measured values and explicit unknowns;
   they do not reconstruct missing telemetry.
6. **Cost boundary:** every new terminal receipt needs numeric cost, accounting
   source, and final/provisional state. Prices are supplied by the host or a
   provider adapter; the core contains no provider-specific price table.
   The host captures cost at the terminal execution boundary and normalizes it
   into the receipt. Headroom, RTK, provider CLIs, rate cards, subscriptions,
   and local compute are replaceable sources. Observed runtime activity may show
   a diagnostic estimate, but it never substitutes for the terminal receipt.
7. **Observation boundary:** local logs establish activity only. `007 begin`
   establishes the outcome denominator and
   `007 record` closes it. Work that bypasses `begin` remains explicitly outside
   what the dependency-free core can observe.
8. **Execution boundary:** `007 run --action` validates the bound authority
   before starting a CLI and is the only supported writer of `controlled`
   provenance. The adapter at the last execution boundary remains responsible
   for the normalized outcome and cost receipt. Exit code alone never proves
   quality or accounting. Local records are not a security boundary against a
   process with the same OS identity.

## Extension points

Provider adapters and repository-specific harness commands live outside the
core. Extend routing only after verifying the runtime binding. Add sensors before
automation, and add automation only after the manual contract is stable.
