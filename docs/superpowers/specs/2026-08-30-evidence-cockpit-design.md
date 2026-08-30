# 007 Framework Evidence Cockpit Design

**Status:** approved in chat by Marcus on 2026-08-30
**Target:** next testable release after v1.1.0

## Objective

Show whether 007 produces correct changes that are accepted on the first pass,
remain useful without corrective work, and cost less per reliable outcome. The
priority order is correctness, low rework, small change surface, then cost and
latency. Operational use and causal experiments remain separate evidence lanes.

## Observable lifecycle

An initialized project stores append-only task starts under `.007/tasks/` and
terminal receipts under `.007/receipts/`.

```text
007 begin -> task observed -> 007 record -> accepted -> first pass -> intact at 7d
```

`007 begin` creates a no-replace start record with a task ID and UTC timestamp.
`007 record` keeps its existing fail-closed receipt contract. Matching IDs let
the dashboard report started, terminal, active, and unreported tasks. Runs that
never invoke `007 begin` remain outside the dependency-free observer and are
declared as an evidence boundary, never guessed or backfilled.

The installed skill calls `007 begin` before implementation and `007 record` at
the terminal gate. Other hosts receive the same provider-neutral CLI contract.
Provider adapters may supply model, token, and cost values, but the core keeps
mandatory numeric cost and never embeds a mutable price table.

## Decision metrics

- **Reliable first-pass:** accepted, first-pass `yes`, and `escape_7d=no`, over
  accepted tasks whose first-pass and seven-day outcome have matured.
- **Delivery funnel:** started -> terminal -> accepted -> first-pass accepted ->
  reliable at seven days. Raw counts reconcile across project and aggregate.
- **Cost per reliable outcome:** all accounted terminal cost divided by reliable
  outcomes, so failed attempts are not free. It is `N/D` if terminal cost
  coverage is incomplete or no reliable outcome exists.
- **Rework:** repair rounds, known escapes, and Git touch proxy at 7/30 days.
- **Observation coverage:** terminal receipts divided by started tasks. It is
  `N/D` when no task start exists, not 0%.

No composite score is introduced. Correctness, durability, cost, and evidence
quality stay independently visible.

## Interface

The first viewport answers one question: **"O 007 está produzindo mais mudanças
confiáveis por dólar, sem deslocar custo para retrabalho?"**

1. A plain-language verdict: instrumentation inactive, collecting, on target,
   or needs attention, with the decisive reason.
2. Four primary cards: reliable first-pass, regressions/escapes, repair rounds,
   and cost per reliable outcome.
3. A five-stage reliability funnel with raw counts and maturation labels.
4. A reconciled project table using the same definitions as the aggregate.
5. Separate operational and causal evidence panels. Causal evidence shows the
   frozen OLDxNEW result, sample, claim, and evidence ceiling.
6. A data-quality panel exposing starts, terminal receipts, active tasks,
   observation coverage, cost coverage, pending windows, and invalid receipts.
7. Task detail retains provider, served model, proof, result, cost, and rework.

With no starts, the page says that projects are connected but instrumentation
has not started and shows the exact `007 begin` and `007 record` path. Empty
charts do not occupy the primary viewport.

## Architecture and constraints

Reuse `framework_cli.py`, `dashboard.py`, JSON receipts, Git sensors, static
HTML/CSS/JS, and two-second polling. Add no database, daemon, frontend framework,
chart dependency, provider catalog, or historical reconstruction. All state is
local, ignored by Git, validated at the filesystem boundary, and written
atomically or no-replace.

## Verification

- RED-GREEN tests for task-start validation/no-replace behavior.
- RED-GREEN tests for lifecycle reconciliation and reliable/cost formulas.
- Aggregate raw totals equal project totals.
- Existing receipt, security, route allowlist, and package tests remain green.
- Browser checks at desktop and narrow widths confirm hierarchy, empty state,
  project drill-down, no console errors, and two-second refresh.

## Deferred

Automatic interception of every proprietary IDE session, provider billing
APIs, team hosting, authentication, DuckDB, and backfill remain deferred until
the local lifecycle produces evidence that they are needed.
