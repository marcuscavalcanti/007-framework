# Evidence Confidence Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make controller-observed authority events non-self-assertable and make the dashboard answer whether 007 is meeting its reliability-per-dollar objective.

**Architecture:** Extend the existing `007 run` control path with one named action and no-replace controller event record; preserve manual receipts as declared evidence. Derive objective gates, prioritized actions, provenance coverage, and a 30-day raw-count trend in the current Python snapshot, then render them with the existing dependency-free HTML/CSS/JS dashboard.

**Tech Stack:** Python 3 standard library, vanilla JavaScript, native SVG, `unittest`, Git worktree.

**Spec:** `docs/superpowers/specs/2026-08-31-evidence-confidence-dashboard-design.md`

## Global Constraints

- No database, daemon, login, remote service, provider-specific runner, chart library, or new dependency.
- Existing `007 begin`, `007 record`, unbound `007 run`, receipts, registry, and dashboard URLs remain compatible.
- Missing data remains `N/D`; percentages are recomputed from aggregate numerators and denominators.
- Manual authority events are `declared`; only the current `007 run` invocation can produce `controlled` provenance through the supported API.
- The result does not claim resistance to a malicious process using Marcus's OS credentials.
- Diff budget: checkpoint above 400 net non-test lines; prefer modification of existing control paths over new modules.

---

### Task 1: Controller-observed authority events

**Files:**
- Modify: `scripts/framework_cli.py`
- Modify: `tests/test_dashboard.py`
- Modify: `references/receipt-schema.md`

**Interfaces:**
- Consumes: existing `begin_task`, `validate_authority`, `write_json_no_replace`, `bind_authority`, `record_receipt`, and `run_task`.
- Produces: `CONTROLLER_EVENT_SCHEMA`, `write_controller_event(root, task, action, outcome, exit_code=None, now=None) -> dict`, `blocked_receipt(task, action, now=None) -> dict`, and `run_task(..., authority_file=None, action=None)`.

- [ ] **Step 1: Write failing controller tests**

Add real CLI tests proving these breaks:

```python
def test_run_blocks_denied_action_before_subprocess(self):
    result = self.run_cli(
        "run", "--repo", str(repo), "--task-id", "deny-1",
        "--receipt", "blocked.json", "--authority-file", str(authority),
        "--action", "deploy", "--", sys.executable, "-c",
        "from pathlib import Path; Path('sentinel').write_text('ran')",
    )
    self.assertNotEqual(result.returncode, 0)
    self.assertFalse((repo / "sentinel").exists())
    stored = json.loads((repo / ".007/receipts/deny-1.receipt.json").read_text())
    self.assertEqual(stored["authority_evidence"], "controlled")
    self.assertEqual(stored["authority_summary"]["protected_blocks"], 1)

def test_run_records_allowed_action_as_controlled(self):
    # The child writes a normal receipt without authority_evidence.
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertTrue((repo / "sentinel").exists())
    self.assertEqual(stored["authority_evidence"], "controlled")
    self.assertEqual(stored["authority_summary"]["allowed_executions"], 1)

def test_record_rejects_caller_supplied_controlled_provenance(self):
    receipt["authority_evidence"] = "controlled"
    self.assertEqual(self.run_cli("record", "--repo", str(repo), "--file", str(source)).returncode, 2)

def test_manual_authority_receipt_is_declared(self):
    self.assertEqual(stored["authority_evidence"], "declared")
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_dashboard.DashboardTests.test_run_blocks_denied_action_before_subprocess \
  tests.test_dashboard.DashboardTests.test_run_records_allowed_action_as_controlled \
  tests.test_dashboard.DashboardTests.test_record_rejects_caller_supplied_controlled_provenance \
  tests.test_dashboard.DashboardTests.test_manual_authority_receipt_is_declared -v
```

Expected: failures because `--action`, controller events, and `authority_evidence` do not exist.

- [ ] **Step 3: Implement the minimum controller path**

Add the schema and reject computed provenance at the receipt boundary:

```python
CONTROLLER_EVENT_SCHEMA = "007-framework/controller-event/v1"

def validate_receipt(value):
    if "authority_summary" in value or "authority_evidence" in value:
        raise ValueError("authority provenance is computed by 007")
    # existing validation remains
```

Persist one no-replace event per task under `.007/events/<task-id>.event.json`.
Extend `bind_authority(receipt, task, controller_event=None)` so a controller
event supplies the action/outcome and sets `authority_evidence="controlled"`;
the existing receipt-event path sets `authority_evidence="declared"`.

Extend `run_task` and the parser with `--action`. Validate action/authority
pairing before `begin_task`. For denied or unclassified actions, do not call
`subprocess.run`; persist a blocked event and a valid blocked receipt using:

```python
{
    "schema": RECEIPT_SCHEMA,
    "task_id": task["task_id"],
    "status": "blocked",
    "proof_required": "authority",
    "proof_reached": "controller-blocked-before-execution",
    "checks": [{"command": f"007 authority {action}", "exit": 3}],
    "delta": {"files": 0, "added": 0, "deleted": 0, "dependencies": 0},
    "first_pass": "unmeasured",
    "repair_rounds": 0,
    "corrective_lines": "pending",
    "escape_7d": "pending",
    "requested_provider": "unmeasured",
    "requested_model": "unmeasured",
    "requested_effort": "unmeasured",
    "served_provider": "unmeasured",
    "served_model": "unmeasured",
    "served_effort": "unmeasured",
    "tokens": 0,
    "wall_s": 0,
    "cost_usd": 0,
    "cost_source": "local-compute",
    "cost_status": "final",
    "uncertainty": "subprocess not started",
}
```

For allowed actions, run the command once, persist the controller event with
its exit code, and pass that event to `record_receipt`. Preserve existing
non-zero and missing-receipt behavior without retry.

- [ ] **Step 4: Verify GREEN and full regression**

Run:

```bash
python3 -m unittest tests.test_dashboard -v
python3 -m unittest discover -s tests
```

Expected: all focused and existing tests pass.

- [ ] **Step 5: Document and commit the controller contract**

Document `--action`, declared versus controlled provenance, no-replace local
events, and the same-principal limitation in `references/receipt-schema.md`.

```bash
git add scripts/framework_cli.py tests/test_dashboard.py references/receipt-schema.md
git commit -m "feat: capture controller authority evidence"
```

---

### Task 2: Objective gates, actions, confidence, and trend

**Files:**
- Modify: `scripts/dashboard.py`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: sanitized receipts, task starts, current `metrics_from_receipts`, `metrics_from_observations`, `aggregate_projects`, and touch sensors.
- Produces: `objective_state(metrics, touch, **data_quality) -> dict`, `authority_confidence(metrics) -> dict`, and `outcome_trend(receipts, now=None, days=30) -> list[dict]`.

- [ ] **Step 1: Write literal table-driven objective tests**

Add tests whose expected values are hand-derived:

```python
def test_objective_state_prioritizes_measurement_before_performance(self):
    result = dashboard.objective_state(metrics, touch)
    self.assertEqual(result["status"], "not-measurable")
    self.assertEqual(result["primary_action"], "Record terminal cost for 2 outcomes.")
    self.assertEqual([gate["status"] for gate in result["gates"]],
                     ["pass", "pass", "pass", "pass", "pass", "wait", "pass"])

def test_objective_state_reports_off_target_only_when_all_gates_are_known(self):
    result = dashboard.objective_state(metrics, touch)
    self.assertEqual(result["status"], "off-target")
    self.assertIn("Reliable first-pass", result["primary_action"])

def test_authority_confidence_separates_controlled_and_declared(self):
    result = dashboard.metrics_from_receipts([controlled, declared, unbound])
    self.assertEqual(result["authority_controlled_tasks"], 1)
    self.assertEqual(result["authority_declared_tasks"], 1)

def test_outcome_trend_returns_daily_raw_counts(self):
    self.assertEqual(dashboard.outcome_trend(receipts, now=instant, days=3), [
        {"date": "2026-08-29", "reliable": 0, "accepted_other": 0, "not_accepted": 0},
        {"date": "2026-08-30", "reliable": 1, "accepted_other": 1, "not_accepted": 0},
        {"date": "2026-08-31", "reliable": 0, "accepted_other": 0, "not_accepted": 1},
    ])
```

- [ ] **Step 2: Run focused tests and verify RED**

Run the four exact test methods with `python3 -m unittest ... -v`.

Expected: missing functions/fields.

- [ ] **Step 3: Implement derived snapshot fields**

Reuse the thresholds already encoded by `evidence_state`; move them into one
literal gate definition inside `objective_state` and retain `evidence` as a
compatibility projection. Add raw provenance counters to `RAW_METRICS`, compute
`authority_confidence`, and derive the daily trend directly from
`completed_at`. Aggregate trends by summing daily raw counts, never project
percentages.

Attach `objective`, `authority_confidence`, and `trend_30d` to every project and
the aggregate. Primary-action ordering must match the spec and return one
sentence with an affected count or threshold.

- [ ] **Step 4: Verify reconciliation and regressions**

```bash
python3 -m unittest tests.test_dashboard -v
python3 -m unittest discover -s tests
```

Expected: project and aggregate fixtures pass with exact raw totals.

- [ ] **Step 5: Commit derived analytics**

```bash
git add scripts/dashboard.py tests/test_dashboard.py
git commit -m "feat: derive objective confidence metrics"
```

---

### Task 3: Actionable cockpit, evidence, and release verification

**Files:**
- Modify: `dashboard/index.html`
- Modify: `dashboard/app.js`
- Modify: `dashboard/styles.css`
- Modify: `tests/test_dashboard.py`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/evidence.md`
- Modify: `CHANGELOG.md`
- Create: `evidence/v1.3.0/controller-authority-protocol.json`
- Create: `evidence/v1.3.0/controller-authority-result.json`
- Create: `evidence/v1.3.0/release-evidence.md`

**Interfaces:**
- Consumes: snapshot `objective`, `authority_confidence`, and `trend_30d` from Task 2.
- Produces: decision hero, gate matrix, ordered action queue, provenance panel, native SVG trend, and frozen deterministic mechanism evidence.

- [ ] **Step 1: Write failing shell and rendering-contract tests**

Assert semantic IDs and safe rendering behavior:

```python
self.assertIn('id="primary-action"', html)
self.assertIn('id="gate-matrix-body"', html)
self.assertIn('id="outcome-trend"', html)
self.assertIn('id="authority-controlled"', html)
self.assertIn('createElementNS', app)
self.assertNotIn('.innerHTML =', app)
```

Add a snapshot fixture check that the UI-facing objective has three states only:
`on-target`, `off-target`, and `not-measurable`.

- [ ] **Step 2: Run the dashboard test and verify RED**

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_dashboard_shell_is_semantic_and_self_contained -v
```

Expected: missing IDs and SVG renderer.

- [ ] **Step 3: Implement the minimum UI**

Reuse existing panels and CSS variables. Replace the current verdict copy with
the three-state answer and `primary_action`. Insert one gate table below the
hero. Replace the self-reported authority cards with controlled/declared/not
observed counts and provenance-specific block totals. Render the 30-day stacked
raw-count SVG with `document.createElementNS`; show an explicit empty state when
all counts are zero. Convert diagnostics to the backend-ordered action queue.

Do not add filters, date pickers, animation libraries, tooltips, canvas, or a
second mobile layout. Preserve keyboard focus, reduced motion, and the existing
project selector.

- [ ] **Step 4: Run the deterministic OLD×NEW mechanism check**

Freeze protocol JSON before execution. Run three repetitions per arm for:

1. denied target command;
2. allowed control command;
3. manual provenance-upgrade attempt.

The hidden probe checks sentinel existence, exit status, and stored provenance.
Persist all 18 cell outcomes without retries. PASS requires NEW to block every
denied sentinel, allow every control, reject every upgrade, and OLD to retain
the pre-change contrast. Record exact input and result hashes in
`evidence/v1.3.0/release-evidence.md`.

- [ ] **Step 5: Verify code and live UI**

```bash
python3 -m unittest discover -s tests
python3 -m py_compile scripts/*.py
node --check dashboard/app.js
git diff --check
```

Start the worktree dashboard on a spare loopback port. Inspect aggregate and
one project at desktop and mobile widths. Verify the three-state answer, target
lines, action priority, trend empty/non-empty states, provenance labels, no
console errors, and exact aggregate/project reconciliation.

- [ ] **Step 6: Obtain adversarial review and close the candidate**

Create one sanitized, hash-addressed context containing the spec, plan, diff,
tests, causal protocol/result, and visual-check inventory, but no private
project receipts or secrets. Run Opus 5/xhigh read-only with tools disabled.
Accept only `approve` with highest severity `low`; fix agreed findings through
RED→GREEN and re-review the delta.

- [ ] **Step 7: Commit the candidate**

```bash
git add dashboard scripts tests README.md docs CHANGELOG.md evidence/v1.3.0
git commit -m "feat: add evidence confidence cockpit"
```

Do not merge, push, tag, or restart port 7007 until fresh verification succeeds
and the user authorizes that publication boundary.
