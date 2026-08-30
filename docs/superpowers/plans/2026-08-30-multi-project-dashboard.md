# 007 Framework Multi-Project Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dependency-free `007 init` and localhost dashboard whose all-project metrics reconcile exactly with per-project metrics.

**Architecture:** A Python standard-library CLI registers Git projects, reuses receipt and Git sensors to produce one sanitized snapshot, and serves static HTML/CSS/JS over loopback. The browser polls one allowlisted JSON endpoint every two seconds; no database, daemon, frontend framework, or arbitrary-path API is added.

**Tech Stack:** Python 3.11+ standard library, HTML5, CSS, vanilla JavaScript, native SVG, `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-30-multi-project-dashboard-design.md`

## Global Constraints

- Bind to `127.0.0.1` by default.
- Add no runtime or development dependency.
- Keep DuckDB deferred until the adoption gate in the spec is measured.
- Never infer monetary cost from a model name and aggregate token count.
- The aggregate is calculated from raw project totals, never averaged project percentages.
- Missing attribution or telemetry remains `N/D`, `pending`, or `unmeasured`.
- Operational evidence and causal evidence remain visually and semantically separate.
- Existing CLI output and all 16 V1 tests remain compatible.
- HTTP requests cannot select filesystem paths.
- Every production behavior starts with a failing test.

---

### Task 1: Project registration and CLI entrypoint

**Files:**
- Create: `scripts/framework_cli.py`
- Create: `bin/007`
- Create: `tests/test_dashboard.py`
- Modify: `tests/test_scripts.py`

**Interfaces:**
- Produces: `init_project(repo: Path, registry_path: Path, now: datetime | None = None) -> dict`
- Produces: `registry_path(home: Path | None = None) -> Path`
- Produces: CLI commands `007 init [--repo PATH]` and `007 dashboard`

- [ ] **Step 1: Write the failing registration test**

```python
def test_init_registers_project_idempotently(self):
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp, "repo")
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        registry = Path(tmp, "home", "projects.json")
        first = framework_cli.init_project(repo, registry)
        second = framework_cli.init_project(repo, registry)
        self.assertEqual(first["project_id"], second["project_id"])
        self.assertEqual(json.loads(registry.read_text())["projects"], [{
            "project_id": first["project_id"],
            "name": "repo",
            "path": str(repo.resolve()),
            "registered_at": first["registered_at"],
        }])
        self.assertTrue((repo / ".007/receipts").is_dir())
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `python3 -m unittest tests.test_dashboard.DashboardTests.test_init_registers_project_idempotently -v`

Expected: import or attribute failure because `framework_cli.init_project` does not exist.

- [ ] **Step 3: Implement the minimum atomic registry flow**

Implement Git-root resolution, UUID creation, `.007/project.json`, receipt directory creation, registry replacement through a sibling temporary file, and idempotent updates. Reject non-Git roots and malformed existing markers.

- [ ] **Step 4: Add the executable wrapper and CLI help contract**

`bin/007` imports `scripts/framework_cli.py` from the checkout root and exits through `main()`. Extend `test_all_scripts_have_help` to include `framework_cli.py`; add one subprocess test that invokes `bin/007 init --repo <fixture> --registry <fixture-registry>`.

- [ ] **Step 5: Run focused and full tests**

Run: `python3 -m unittest tests.test_dashboard tests.test_scripts -v`

Expected: all registration and existing script tests pass.

- [ ] **Step 6: Commit**

```bash
git add bin/007 scripts/framework_cli.py tests/test_dashboard.py tests/test_scripts.py
git commit -m "feat: register 007 projects"
```

---

### Task 2: Structured project and aggregate metrics

**Files:**
- Create: `scripts/dashboard.py`
- Modify: `scripts/touch_rate.py`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_scripts.py`

**Interfaces:**
- Produces: `touch_rate.calculate(repo: Path, days: int, agent_regex: str, max_commits: int) -> dict`
- Produces: `dashboard.project_snapshot(entry: dict, now: datetime | None = None) -> dict`
- Produces: `dashboard.aggregate_projects(projects: list[dict]) -> dict`
- Produces: `dashboard.build_snapshot(registry: Path, now: datetime | None = None) -> dict`

- [ ] **Step 1: Write the failing missing-data and reconciliation tests**

```python
def test_aggregate_reconciles_raw_project_totals_and_preserves_unknowns(self):
    projects = [
        {"available": True, "metrics": {"tasks": 2, "accepted": 1,
         "first_pass_yes": 1, "first_pass_known": 1, "tokens_known_sum": 100,
         "tokens_known_tasks": 1, "repair_rounds_sum": 0, "repair_rounds_known": 1}},
        {"available": True, "metrics": {"tasks": 3, "accepted": 2,
         "first_pass_yes": 1, "first_pass_known": 2, "tokens_known_sum": 0,
         "tokens_known_tasks": 0, "repair_rounds_sum": 2, "repair_rounds_known": 2}},
    ]
    result = dashboard.aggregate_projects(projects)
    self.assertEqual(result["tasks"], 5)
    self.assertEqual(result["accepted"], 3)
    self.assertEqual(result["first_pass_rate"], 2 / 3)
    self.assertEqual(result["tokens_known_sum"], 100)
    self.assertEqual(result["tokens_missing_tasks"], 4)
```

Add a separate test asserting empty/missing telemetry serializes as `None` with a reason instead of numeric zero.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python3 -m unittest tests.test_dashboard -v`

Expected: import or attribute failure because the dashboard aggregator does not exist.

- [ ] **Step 3: Refactor touch-rate behind a structured function**

Move the existing calculation into `calculate(...)`. Keep `main()` as formatting only, preserving both current output lines and the `N/D` exit-zero behavior. Return raw `agent_lines_added`, `surviving_lines`, `agent_commits`, `human_commits`, `rate`, and `reason`.

- [ ] **Step 4: Implement receipt projection and raw aggregation**

Reuse `harness_report.load_receipts`. Project only safe receipt fields: task id, status, proof levels, first-pass, repairs, delta totals, telemetry numbers, uncertainty, and completion time. Never return check command output, prompts, agent tails, or arbitrary receipt keys.

Compute rates only from known denominators. Compute `collecting`, `on-target`, or `needs-attention` with the thresholds frozen in the spec and include every unmet or unknown reason.

- [ ] **Step 5: Run tests and verify CLI compatibility**

Run: `python3 -m unittest tests.test_dashboard tests.test_scripts -v`

Expected: all pass, including unchanged touch-rate text assertions.

- [ ] **Step 6: Commit**

```bash
git add scripts/dashboard.py scripts/touch_rate.py tests/test_dashboard.py tests/test_scripts.py
git commit -m "feat: aggregate 007 outcome metrics"
```

---

### Task 3: Loopback HTTP server

**Files:**
- Modify: `scripts/dashboard.py`
- Modify: `scripts/framework_cli.py`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Produces: `dashboard.create_server(host: str, port: int, registry: Path, static_dir: Path) -> ThreadingHTTPServer`
- Produces: allowlisted routes `/`, `/styles.css`, `/app.js`, `/api/snapshot`, and `/api/health`

- [ ] **Step 1: Write a failing live-server contract test**

```python
def test_server_exposes_only_allowlisted_routes(self):
    server = dashboard.create_server("127.0.0.1", 0, self.registry, self.static_dir)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        self.assertEqual(json.load(urlopen(base + "/api/health"))["status"], "ok")
        with self.assertRaises(HTTPError) as denied:
            urlopen(base + "/api/snapshot?path=/etc")
        self.assertEqual(denied.exception.code, 400)
        with self.assertRaises(HTTPError) as missing:
            urlopen(base + "/../SKILL.md")
        self.assertEqual(missing.exception.code, 404)
    finally:
        server.shutdown()
        server.server_close()
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `python3 -m unittest tests.test_dashboard.DashboardTests.test_server_exposes_only_allowlisted_routes -v`

Expected: `create_server` missing.

- [ ] **Step 3: Implement the allowlisted handler**

Use `ThreadingHTTPServer` and `BaseHTTPRequestHandler`. Emit fixed content types, `Cache-Control: no-store` for APIs, small static cache headers, JSON errors without tracebacks, and no directory serving. Reject every query parameter and every route outside the allowlist.

- [ ] **Step 4: Connect `007 dashboard`**

Support `--host`, `--port`, `--registry`, and `--no-open`. Default host is `127.0.0.1`, port is `7007`, and the browser opens only after bind succeeds.

- [ ] **Step 5: Run focused tests**

Run: `python3 -m unittest tests.test_dashboard -v`

Expected: all registration, aggregation, and HTTP tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/dashboard.py scripts/framework_cli.py tests/test_dashboard.py
git commit -m "feat: serve local 007 dashboard"
```

---

### Task 4: Polished multi-project interface

**Files:**
- Create: `dashboard/index.html`
- Create: `dashboard/styles.css`
- Create: `dashboard/app.js`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `/api/snapshot` every 2000 ms
- Produces: overview and project selection from the same snapshot without client-side filesystem access

- [ ] **Step 1: Write failing static-contract tests**

Assert that the page contains semantic `header`, `nav`, `main`, live status with `aria-live`, overview and evidence sections, project navigation, and no external `http://` or `https://` assets. Assert that JavaScript uses `textContent`, polls `/api/snapshot`, and does not assign `innerHTML` with project data.

- [ ] **Step 2: Run the static tests and confirm RED**

Run: `python3 -m unittest tests.test_dashboard -v`

Expected: missing asset files.

- [ ] **Step 3: Build the accessible application shell and visual system**

Create a dark engineering-console layout with sidebar, live header, metric cards, trend SVG, project comparison, recent task timeline, evidence boundary panel, diagnostics panel, empty/loading/error states, responsive breakpoints, visible focus, and reduced-motion support. Use system fonts and no external request.

- [ ] **Step 4: Implement safe rendering and exact reconciliation**

Render project data through DOM creation and `textContent`. The overview uses server aggregate values. The selected project uses its server record. Display raw numerators beside derived percentages and show `N/D` with its server-supplied reason. Pause polling when the page is hidden and refresh immediately when visible.

Group outcomes by open-string provider/model route, preferring served values;
label requested-only routes as unverified. Show monetary cost only when the
backend marks it measured with `cost_source`.

- [ ] **Step 5: Run static and server tests**

Run: `python3 -m unittest tests.test_dashboard -v`

Expected: all dashboard tests pass.

- [ ] **Step 6: Commit**

```bash
git add dashboard tests/test_dashboard.py
git commit -m "feat: add multi-project dashboard UI"
```

---

### Task 5: Framework integration and documentation

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `docs/product.md`
- Modify: `docs/architecture.md`
- Modify: `references/receipt-schema.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_package.py`

**Interfaces:**
- Consumes: `.007/project.json` as the opt-in signal
- Produces: one atomic `.007/receipts/*.receipt.json` after an initialized task reaches a terminal framework status

- [ ] **Step 1: Write failing package-contract tests**

Change the expected skill version to `1.1.0`. Assert the skill says initialized projects write a receipt automatically, missing telemetry remains unmeasured, and receipt filenames cannot contain path separators. Assert README installation exposes `007 init` and `007 dashboard`.

- [ ] **Step 2: Run package tests and confirm RED**

Run: `python3 -m unittest tests.test_package -v`

Expected: version and dashboard-contract assertions fail against V1.0.0 docs.

- [ ] **Step 3: Update the skill and public documentation**

Add only the opt-in receipt rule to the core workflow. Document CLI installation through a symlink to `bin/007`, initialization, dashboard launch, metric definitions, observational-versus-causal boundary, localhost trust boundary, and uninstallation. Add optional `completed_at`, requested/served provider-model-effort, token breakdown, `cost_usd`, and `cost_source` fields without making them required.

- [ ] **Step 4: Run package and full tests**

Run: `python3 -m unittest discover -s tests -v`

Expected: every legacy and dashboard test passes.

- [ ] **Step 5: Commit**

```bash
git add SKILL.md README.md CHANGELOG.md docs references/receipt-schema.md tests/test_package.py
git commit -m "docs: integrate dashboard workflow"
```

---

### Task 6: End-to-end and visual release-candidate verification

**Files:**
- Modify only if a failing verification exposes a defect; each defect first receives a regression test.

**Interfaces:**
- Produces: local v1.1.0 release candidate, browser screenshots, and an exact sanitized adversarial-review payload

- [ ] **Step 1: Run deterministic verification**

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
git diff --check
```

- [ ] **Step 2: Exercise a clean fixture installation**

Create two temporary Git projects, run `bin/007 init` in each against a temporary registry, add valid receipts with known and unknown fields, start `bin/007 dashboard --no-open --registry <path> --port 0`, and verify health plus snapshot reconciliation.

- [ ] **Step 3: Perform browser QA**

Inspect desktop and mobile widths. Verify overview, project filter, empty state, unavailable project, unknown telemetry, invalid receipt, keyboard focus, contrast, and no console/network errors. Capture screenshots as local evidence.

- [ ] **Step 4: Review the entire diff for scope and secrets**

```bash
git status --short --branch -uall
git diff v1.0.0...HEAD --stat
git diff v1.0.0...HEAD --check
rg -n '/Users/marcus|BEGIN .*PRIVATE KEY|sk-ant-' --glob '!docs/superpowers/**' .
```

- [ ] **Step 5: Prepare bounded adversarial review**

Create one sanitized, hash-addressed full-tree context containing the approved spec, implementation diff, tests, verification outputs, and screenshots inventory but no secrets or project receipts. Stop before external egress and present exact path, SHA-256, size, destination, model, effort, and zero-cell scope for authorization.

- [ ] **Step 6: Commit any verified final metadata**

Only after all checks remain green:

```bash
git add -A
git commit -m "chore: finalize dashboard release candidate"
```

Do not push, tag, or publish without a separate explicit release action.
