# Evidence Cockpit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture observable task starts and make the localhost dashboard explain reliability, rework, cost, and causal evidence clearly.

**Architecture:** Extend the existing append-only `.007` state with task-start records, derive lifecycle and reliable-outcome metrics in the current Python snapshot, and render them in the existing dependency-free static dashboard. JSON and Git remain authoritative; no new service or dependency is introduced.

**Tech Stack:** Python 3 standard library, HTML, CSS, browser-native JavaScript/SVG, `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-30-evidence-cockpit-design.md`

## Global Constraints

- Preserve receipt schema v1 and existing initialized projects.
- Cost stays mandatory, numeric, and explicitly sourced.
- Missing or omitted evidence remains `N/D`; no backfill or inferred telemetry.
- Aggregate totals are sums of raw project totals, never averages of rates.
- No database, daemon, provider SDK, frontend framework, or new dependency.

---

### Task 1: Observable task starts

**Files:**
- Modify: `tests/test_dashboard.py`
- Modify: `scripts/framework_cli.py`
- Modify: `SKILL.md`
- Modify: `README.md`

**Interfaces:**
- Produces: `begin_task(repo, task_id=None, now=None) -> dict`
- Produces: CLI `007 begin --repo PATH [--task-id ID]`
- Persists: `.007/tasks/<task_id>.task.json` with schema, task ID, and UTC start.

- [ ] Add tests proving an initialized project creates a valid no-replace start,
  rejects an unsafe/duplicate task ID, and exposes the generated ID on stdout.
- [ ] Run the focused tests and confirm they fail because `begin_task` and the
  `begin` command do not exist.
- [ ] Implement task-ID validation by reusing the receipt ID rule, create the
  tasks directory, and persist one start atomically with no replacement.
- [ ] Run the focused tests and the CLI help contract until green.
- [ ] Update the skill and README so initialized tasks begin before code work and
  retain the existing terminal `007 record` contract.

### Task 2: Reliability and coverage calculations

**Files:**
- Modify: `tests/test_dashboard.py`
- Modify: `scripts/dashboard.py`

**Interfaces:**
- Consumes: `.007/tasks/*.task.json` and `.007/receipts/*.receipt.json`
- Produces metrics: `started_tasks`, `terminal_tasks`, `active_tasks`,
  `observation_coverage`, `reliable_first_pass_yes`,
  `reliable_first_pass_known`, `reliable_first_pass_rate`, and
  `cost_usd_per_reliable`.

- [ ] Add literal-fixture tests for start/receipt matching, unknown coverage with
  no starts, reliable maturation, and all-terminal-cost-per-reliable formula.
- [ ] Run focused tests and confirm expected missing-field failures.
- [ ] Add a strict safe task-start loader, project lifecycle derivation, and raw
  aggregate summation; invalid starts remain diagnostics.
- [ ] Run focused tests and mutation-check each formula by changing one term.
- [ ] Run the full Python suite to protect existing dashboard contracts.

### Task 3: Didactic Evidence Cockpit

**Files:**
- Modify: `dashboard/index.html`
- Modify: `dashboard/app.js`
- Modify: `dashboard/styles.css`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: existing `/api/snapshot` plus Task 2 lifecycle metrics.
- Produces: verdict, four KPI cards, lifecycle funnel, project reconciliation,
  separate causal evidence, data quality, and actionable empty state.

- [ ] Add a shell contract test for the objective question, funnel semantics,
  causal/operational separation, and instrumentation empty-state action.
- [ ] Run it and confirm the old shell fails the new behavior contract.
- [ ] Replace empty-first charts with the verdict and funnel in the first
  viewport; retain project/activity/route details below.
- [ ] Render all dynamic values with `textContent`, label `N/D` and pending
  states plainly, and keep aggregate/project metrics identical.
- [ ] Refine existing CSS for desktop and narrow side-panel widths without adding
  assets, dependencies, animation requirements, or a second visual system.
- [ ] Run static and full suite checks.

### Task 4: Integrated proof and documentation

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/product.md`
- Modify: `references/metrics.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Documents the lifecycle, formulas, evidence boundary, and adoption commands.

- [ ] Update technical and product docs with exact metric formulas and the
  begin/record lifecycle; explicitly preserve the provider-adapter boundary.
- [ ] Run `python3 -m unittest discover -s tests -v` and
  `python3 -m py_compile scripts/*.py` outside sandbox for loopback coverage.
- [ ] Start the worktree dashboard on an alternate localhost port and inspect
  desktop and narrow widths, project navigation, API reconciliation, and console.
- [ ] Inspect `git diff --check`, changed files/lines, and unintended WIP before
  presenting the local integration boundary.
