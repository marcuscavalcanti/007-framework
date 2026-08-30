# Local Runtime Activity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add sanitized, Headroom-priced Codex and Claude activity to every registered project's Evidence Cockpit view.

**Architecture:** A standard-library collector parses only local session metadata and usage, maps worktrees through Git common directories, and caches unchanged files. `dashboard.py` attaches the resulting observation-only activity to existing project and aggregate snapshots; receipt-based reliability remains authoritative.

**Tech Stack:** Python 3 standard library, JSONL, Git CLI, HTML/CSS/browser JavaScript, `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-30-local-runtime-activity-design.md`

## Global Constraints

- Read local runtime logs only; never persist, mutate, or expose prompt/output content.
- Use Headroom's LiteLLM pricing path and label all USD as estimates.
- Unknown pricing makes USD `N/D`, never zero.
- Keep verified outcomes separate from observed activity.
- Add no dependency, database, daemon, provider API, or background service.

---

### Task 1: Normalize local session usage and cost

**Files:**
- Create: `scripts/local_activity.py`
- Create: `scripts/headroom_pricing.py`
- Create: `tests/test_local_activity.py`

**Interfaces:**
- Produces: `pricing_request(session: dict) -> dict | None`
- Produces: `HeadroomPricer.quote(sessions: list[dict]) -> list[dict]`
- Produces: `parse_codex_session(path: Path, now: datetime) -> dict | None`
- Produces: `parse_claude_session(path: Path, now: datetime) -> dict | None`

- [ ] Write literal JSONL fixture tests for Codex cumulative usage, Claude
  per-message usage, exact pricing requests, unknown model pricing, and content
  sanitization.
- [ ] Run `python3 -m unittest tests.test_local_activity -v`; confirm imports
  fail because `local_activity.py` does not exist.
- [ ] Implement bounded parsers and a batched Headroom/LiteLLM pricing worker.
- [ ] Rerun the focused suite until all literal expectations pass.

### Task 2: Attribute activity to registered projects

**Files:**
- Modify: `scripts/local_activity.py`
- Modify: `tests/test_local_activity.py`

**Interfaces:**
- Produces: `ActivityCollector.collect(entries: list[dict], now: datetime | None = None) -> dict`
- Returns: `{"aggregate": activity, "projects": {project_id: activity}, "errors": list}`

- [ ] Add failing tests proving a main checkout and linked worktree share one
  project identity, unrelated CWDs are excluded, unchanged files reuse cached
  parsing, and unpriced sessions make aggregate cost unknown.
- [ ] Run the focused tests and verify the expected missing collector failure.
- [ ] Implement 24-hour discovery, Git-common-dir mapping, stat-based cache,
  project aggregation, route aggregation, and sanitized recent-session output.
- [ ] Rerun the focused suite and mutate project matching and cost coverage to
  verify the tests fail for the intended reasons.

### Task 3: Integrate the dashboard snapshot and UI

**Files:**
- Modify: `scripts/dashboard.py`
- Modify: `dashboard/index.html`
- Modify: `dashboard/app.js`
- Modify: `dashboard/styles.css`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- `build_snapshot(..., activity_provider=collector.collect)` attaches activity
  to every project and the aggregate.
- UI renders sessions, active sessions, tokens, estimated USD, pricing coverage,
  observed routes, and recent sanitized sessions.

- [ ] Add failing snapshot and shell tests for the activity contract and the
  explicit "activity is not outcome" boundary.
- [ ] Run the focused dashboard tests and confirm the old snapshot/shell fails.
- [ ] Inject the collector into `build_snapshot`, render the activity panel and
  project columns, and retain receipt-only reliability metrics unchanged.
- [ ] Run all dashboard and activity tests, then the complete suite.

### Task 4: Install and validate against live local projects

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/product.md`
- Modify: `references/metrics.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Documents the 24-hour window, attribution boundary, cost estimate, and
  outcome separation.

- [ ] Update documentation without claiming subscription billing or causal
  proof from runtime activity.
- [ ] Run `python3 -m unittest discover -s tests -v`, Python compile, JavaScript
  syntax, and `git diff --check`.
- [ ] Restart the worktree dashboard, verify Coliseum and MoneyMouse display
  local sessions/tokens/routes, inspect desktop and narrow layouts, and confirm
  the browser console is clean.
- [ ] Present the exact local merge/push boundary; do not integrate or publish
  without the user's choice.
