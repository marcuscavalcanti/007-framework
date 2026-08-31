# Evidence Confidence and Decision Dashboard Design

**Status:** approved in chat on 2026-08-31; implementation not started

**Target:** 007 Framework v1.3.0 candidate

**Current baseline:** `main@be83a3f0075f5503f29f1a22023238065bf30985`

## Goal

Make the localhost dashboard answer, with inspectable evidence, whether the
framework is producing reliable agentic changes at acceptable rework and cost.
Replace self-reported authority metrics with provenance tiers so an ordinary
agent run cannot promote its own declaration to controller-observed evidence.

## Product question

The primary question is:

> Is 007 producing more reliable software changes per dollar?

The dashboard answers exactly one of:

- **YES — on target:** every decision gate is measured and passes.
- **NO — off target:** every decision gate is measurable and at least one fails.
- **NOT YET MEASURABLE:** sample maturity, coverage, or data quality is
  insufficient.

The answer is not a composite score. Each gate remains independently visible.

## Threat model and evidence boundary

This version protects the supported lifecycle against agent self-reporting:

- only `007 run --action <name>` may create a controller-observed authority
  event;
- receipt input cannot claim controller provenance;
- a denied or unclassified action is rejected before its subprocess starts;
- manual `007 begin` + `007 record` remains supported but its boundary events
  are classified as **declared**, never **controlled**;
- missing controlled evidence remains unknown and cannot be upgraded from
  prose or a receipt field.

This is not a security boundary against Marcus, an administrator, or a
malicious process with the same operating-system credentials and direct write
access to local state. Protecting that stronger threat model requires a
separate principal, hardware-backed signing, or an external append-only sink
and is explicitly outside v1.3.0.

## Rejected approaches

### Local HMAC

Rejected because a process with the same user permissions can access or invoke
the signing material. It would add complexity without changing the declared
threat boundary.

### Remote evidence ledger

Rejected for this version because it adds authentication, service operation,
network failure modes, and data egress. Reconsider only if hostile local-user
tampering becomes an explicit requirement.

## Controller-observed authority flow

The existing `007 run` path is extended; no second runner is introduced.

```text
007 run --authority-file policy.json --action test --receipt result.json -- command
       │
       ├─ validate task, policy, and action before creating the subprocess
       ├─ denied/unclassified ─► controller block; command never starts
       └─ allowed ─────────────► command starts
                                      │
                                      ▼
                              provider receipt
                                      │
                                      ▼
                         007 binds controller event
                                      │
                                      ▼
                           no-replace terminal record
```

### CLI contract

- `--action` is optional for unbound legacy `007 run` calls.
- `--action` is required when `--authority-file` is present.
- Supplying `--action` without `--authority-file` is rejected.
- One top-level action is observed per `007 run` invocation in v1.3.0.
- An allowed action records `executed` only after the subprocess is created.
- A denied or unclassified action records `blocked` and the subprocess is never
  created.
- A non-zero subprocess exit remains a failed execution attempt, not a
  protective block and not an accepted result.

### Receipt contract

The normalized receipt exposes an `authority_evidence` value computed by the
controller:

- `controlled` — action provenance came from the current `007 run` process;
- `declared` — valid events came from manual receipt input;
- absent — no authority envelope was bound.

Input receipts are forbidden from supplying `authority_summary` or
`authority_evidence`; both are controller-computed. Existing v1 receipts remain
readable and are classified as declared when they contain valid authority
events.

Controller observations are persisted atomically under `.007/events/` with the
task ID, action, outcome, authority hash, timestamp, and subprocess exit when
available. Callers cannot submit these records through `007 record`; the
supported writer is `007 run`. The records are no-replace audit evidence, not
cryptographically immutable evidence.

Controller-blocked commands must remain visible as terminal blocked attempts.
The controller writes the smallest valid blocked receipt itself with zero model
tokens and zero provider cost because no provider command was started. The
record identifies the accounting source as local control and does not claim
software correctness.

## Decision gates

The current formulas remain authoritative. The decision matrix shows actual
value, target, status, evidence denominator, and next action.

| Gate | Target | Why it matters |
|---|---:|---|
| Mature accepted results | at least 5 | avoids a verdict from a trivial sample |
| Reliable first-pass at 7 days | at least 70% | measures accepted work that survived without repair |
| Mean repair rounds | at most 0.5 | exposes repeated correction loops |
| Seven-day escape rate | at most 5% | exposes regressions after acceptance |
| Thirty-day corrective touch proxy | at most 15% | measures how much agent code required later edits |
| Terminal cost coverage | 100% | prevents cheap-looking results from omitted cost |
| Telemetry completeness | at least 80% | makes route comparisons interpretable |

Authority confidence is reported beside, not mixed into, the objective verdict:

- controlled coverage among authority-bound terminal outcomes;
- declared-only outcomes;
- unobserved authority outcomes;
- protective blocks, allowed executions, friction blocks, and unclassified
  blocks by provenance.

The dashboard never averages project percentages. Aggregate gates are
recomputed from aggregate numerators and denominators.

## Actionable dashboard hierarchy

### 1. Decision hero

The first viewport contains the three-state answer, sample size, confidence
label, and the single highest-priority action. Examples:

- “Run five tasks through `007 run`; only two outcomes are mature.”
- “Capture terminal cost for three receipts; cost coverage is 72%.”
- “Reliable first-pass is 58% against the 70% target; inspect four repaired
  outcomes.”

### 2. Gate matrix

One compact table presents every decision gate as pass, fail, or waiting. It
shows literal thresholds and denominators. Missing data is `N/D`, never zero.

### 3. Thirty-day outcome trend

A dependency-free native SVG chart groups terminal outcomes by completion day:

- reliable first-pass;
- accepted but repaired or not yet durable;
- blocked or not accepted.

A horizontal 70% reference line is shown only when the denominator exists.
The chart is descriptive operational evidence, not a causal claim.

### 4. Project comparison and drill-down

Every project row shows verdict, evidence confidence, reliable first-pass,
cost per reliable outcome, coverage, and its next action. Selecting a project
uses the same formulas and components as the aggregate view.

### 5. Evidence confidence

The existing authority panel becomes a provenance panel. Labels are
“controller-observed”, “agent-declared”, and “not observed”; it never uses
“secure” or “verified” without naming the controller boundary.

### 6. Diagnostics

Diagnostics become an ordered action queue. Ordering is deterministic:

1. invalid or unavailable data;
2. inactive or incomplete lifecycle capture;
3. missing cost or telemetry;
4. insufficient seven-day maturity;
5. failed quality gates;
6. authority friction and unclassified blocks.

Each item names the affected count and the command or investigation that closes
the gap. No automated mutation is added to the dashboard.

## Snapshot additions

The existing JSON snapshot gains only derived fields:

- `objective`: `{status, headline, primary_action, gates[]}`;
- `authority_confidence`: controlled, declared, and unobserved counts and
  coverage;
- `trend_30d`: daily raw counts used by the SVG;
- project rows expose the same three structures.

Receipts, task starts, and controller event records remain the source of truth.
No database, background worker, analytics service, or JavaScript chart
dependency is added.

## Error handling

- Invalid caller-supplied provenance fails closed before a receipt is written.
- Denied and unclassified actions fail before subprocess creation.
- If an allowed subprocess fails or omits its receipt, the start and
  controller event remain visible as incomplete; the framework does not retry.
- Invalid legacy receipts remain listed in data quality and excluded from KPIs.
- A project or Git sensor failure cannot erase other projects from the aggregate.
- Empty trends render an explicit “insufficient completed outcomes” state.

## Testing and causal proof

Implementation follows RED→GREEN checks against real subprocesses and temporary
Git projects.

### Focused mechanism tests

1. A denied action never creates the sentinel file produced by its command.
2. An allowed action creates the sentinel and is classified as controlled.
3. A manual receipt cannot set `authority_evidence=controlled`.
4. A valid legacy/manual authority receipt is classified as declared.
5. Aggregate objective gates reconcile exactly with project numerators and
   denominators.
6. Each fail/wait/pass gate maps to the expected primary action.

### Frozen OLD×NEW flip-test

The causal mechanism test freezes the same repository, task, action envelope,
command, and acceptance probe for both arms:

- **OLD:** a receipt can report a denied action as blocked or executed, but all
  accepted evidence remains self-reported.
- **NEW:** denied execution is stopped before the sentinel appears, and manual
  provenance cannot be upgraded to controlled.

The target effect is conjunctive: NEW blocks the denied command in every
replicate, accepts the allowed control in every replicate, and never labels a
manual event controlled. The result proves this mechanism only; it does not
prove general productivity, hostile-user security, or longitudinal durability.

### Integrated and visual gates

- full Python suite;
- Python and JavaScript syntax checks;
- aggregate/project reconciliation fixtures;
- live dashboard inspection at desktop and mobile widths;
- no console or network errors;
- read-only adversarial Opus review before integration.

## Compatibility and migration

- Existing `007 begin`, `007 record`, unbound `007 run`, registry, receipts,
  and dashboard URLs remain valid.
- Existing authority receipts are displayed as declared evidence.
- No historical record is rewritten or backfilled.
- No automatic project mutation is introduced.

## Scope limits

V1.3.0 does not add login, remote persistence, DuckDB, a daemon, provider price
tables, provider-specific runners, command interception outside `007 run`, or
protection against a malicious local administrator. Those additions require
separate evidence and explicit product demand.
