# 007 Framework Multi-Project Dashboard Design

**Status:** approved by Marcus on 2026-08-30  
**Target release:** v1.1.0  
**Scope:** local, read-only observability plus explicit project registration

## Objective

Provide one polished localhost dashboard that shows whether 007 Framework work
is meeting its operational objective across every registered project: accepted
changes with less corrective rework, explicit proof, and honest telemetry.

The dashboard has two reconciled views:

1. an all-project overview, which is the primary view;
2. a per-project view using the same metric definitions and raw totals.

Aggregated values are computed from raw project observations. Percentages are
never averaged across projects. Missing values remain `N/D` or `unmeasured`.

## Product boundary

The dashboard is an optional local observer, not an agent runtime, model
gateway, workflow engine, or causal judge. It reports operational outcomes from
receipts and Git. It must visually separate:

- **operational evidence:** observational results from registered projects;
- **causal evidence:** frozen OLDxNEW experiments shipped with a release;
- **unknowns:** missing attribution, immature windows, or absent telemetry.

Near-real-time means the browser reflects receipt changes within about two
seconds. It does not stream model thoughts, tokens, or tool calls.

## User flow

Installation exposes one dependency-free command named `007`.

```bash
cd /path/to/project
007 init
007 dashboard
```

`007 init` detects the Git root, creates `.007/project.json` and
`.007/receipts/`, and registers the canonical path in
`~/.007-framework/projects.json`. Re-running it is safe. If a project moves,
running `007 init` from the new path updates the registry.

When `.007/project.json` exists, the skill writes its machine-readable outcome
receipts under `.007/receipts/`. Without initialization, existing framework
behavior remains unchanged and the project does not appear in the dashboard.

`007 dashboard` starts on `127.0.0.1` and opens a browser unless `--no-open` is
passed. It reads all currently registered projects. Missing paths remain visible
as unavailable instead of being silently removed.

## Architecture

```text
.007 receipts + project Git history
                 |
                 v
existing report and touch-rate sensors
                 |
                 v
Python stdlib snapshot + HTTP server
                 |
                 v
static HTML/CSS/JS dashboard (2 s polling)
```

There is no database, Node runtime, container, frontend framework, external CDN,
or background daemon. The server uses Python's standard library and binds to
`127.0.0.1` by default.

### Files

- `bin/007`: stable executable entrypoint.
- `scripts/framework_cli.py`: `init` and `dashboard` commands.
- `scripts/dashboard.py`: registry, snapshot aggregation, Git metric cache, and
  localhost HTTP routes.
- `dashboard/index.html`: accessible application shell.
- `dashboard/styles.css`: complete visual system.
- `dashboard/app.js`: polling, filtering, reconciliation, and native SVG charts.

Existing `scripts/harness_report.py` remains the receipt loader. Existing
`scripts/touch_rate.py` gains a structured calculation function while
preserving its current CLI output.

## Durable local state

`.007/project.json` contains:

```json
{
  "schema": "007-framework/project/v1",
  "project_id": "stable UUID",
  "name": "project-name",
  "receipt_dir": "receipts"
}
```

`~/.007-framework/projects.json` contains only project identity, canonical path,
display name, and registration timestamp. Writes are atomic. Paths accepted by
the HTTP API always come from this registry; requests cannot supply arbitrary
filesystem paths.

## Snapshot contract

`GET /api/snapshot` returns:

- framework version and update timestamp;
- aggregate raw counts and derived rates;
- one record per registered project;
- recent sanitized receipt summaries;
- invalid-receipt and unavailable-project diagnostics;
- operational evidence state and explicit missing-data reasons.

Receipt metrics refresh on each two-second poll. Git touch-rate calculations are
cached for 60 seconds per project and window to avoid repeatedly running blame.

## Metrics

The overview and project views expose the same definitions:

- accepted, blocked, and no-op tasks;
- first-pass accepted numerator, denominator, and rate;
- total and mean repair rounds when measured;
- attributable line touch proxy at 7 and 30 days;
- known 7-day escapes and pending/unknown escape windows;
- tokens, wall time, and optional cost per accepted task when measured;
- outcomes and measured cost grouped by provider/model route;
- telemetry completeness;
- invalid receipts and unavailable projects.

The Git touch metric is labelled an approximation, never synonymous with
corrective work. Tiny samples are labelled as such. An operational state may be
`collecting`, `on-target`, or `needs-attention`; it is not described as causal
proof.

Default transparent operating targets are first-pass accepted >= 70%, mean
repair rounds <= 0.5, known 7-day escape rate <= 5%, 30-day touch proxy <= 15%,
telemetry completeness >= 80%, and cost coverage = 100%. `on-target`
additionally requires at least five accepted tasks and all required metrics
known. Unknown required metrics yield `collecting`, not a pass; cost coverage
below 100% is a hard `needs-attention` signal once the minimum sample matures.

### Provider-neutral cost contract

Requested and served provider, model, and effort are distinct receipt fields.
The dashboard groups by the served route when measured and labels a requested
fallback as unverified. Provider and model values are open strings; there is no
closed provider catalog.

`cost_usd` is accepted only with `cost_source` and `cost_status` (`provisional`
or `final`). Examples include `provider-reported`, `subscription-allocated`,
and `local-compute`. Without an accounted source, the task is
`cost_unaccounted`; model name plus aggregate tokens is insufficient because
input, output, cache, reasoning, date, provider, and subscription terms differ.
Cost per accepted task appears only when every accepted task in the selected
slice has accounted cost. A slice containing provisional values is labelled
provisional until reconciled.

A user-owned rate card may later produce an explicitly labelled estimate, but
v1.1.0 ships no mutable provider price table and performs no network price
lookup.

## Interface

The visual language is a responsive, dark internal engineering system using
system fonts and native SVG. It includes:

- status header with live pulse, last refresh, sample, and evidence state;
- executive cards for the north-star metrics;
- timeline and trend chart;
- project comparison table;
- project navigation and per-project detail;
- data-quality panel showing every `N/D`, pending window, and invalid receipt;
- causal-evidence panel that states exactly what the release proves and does not
  prove;
- useful empty state with the exact `007 init` command.

Keyboard focus, contrast, reduced motion, semantic landmarks, and responsive
layouts are required. No external asset request is permitted.

## Security and failure behavior

- bind to loopback unless the user explicitly supplies another host;
- do not expose receipt bodies, prompts, command output, secrets, or arbitrary
  files through the API;
- reject malformed registry and project markers fail-closed while keeping other
  projects visible;
- preserve invalid receipts as diagnostics and never coerce them into zeroes;
- escape all browser-rendered data by assigning text content, not HTML;
- return explicit HTTP errors without stack traces.

## Verification

Implementation follows RED-GREEN TDD. Deterministic tests cover:

- idempotent registration and moved/unavailable projects;
- aggregate equals the sum of project raw totals;
- missing telemetry remains unknown;
- receipt validation and sanitized recent-task projection;
- touch-rate structure and cache behavior;
- route allowlist and arbitrary-path rejection;
- static asset availability and package boundaries.

The full existing test suite and Python compilation must remain green. The final
dashboard is exercised against fixture projects, inspected in a browser at
desktop and mobile widths, and reviewed adversarially before release.

## Deferred deliberately

- authentication and remote access;
- database-backed history;
- live agent event streaming;
- filesystem-wide project discovery;
- multi-user/team service;
- provider billing integrations;
- custom dashboard builders.

Add these only when observed use demonstrates that localhost receipts plus Git
are insufficient.

### DuckDB adoption gate

DuckDB is a conditional analytical accelerator, not part of v1.1.0. JSON
receipts remain the source of truth. Consider a read-only derived DuckDB layer
only after either condition is measured:

- more than 10,000 receipts across registered projects;
- `/api/snapshot` p95 exceeds 250 ms on the target machine;
- a concrete cohort, window, or ad-hoc SQL analysis cannot remain simple in the
  standard-library aggregator.

If adopted, use in-memory or disposable derived storage over JSON/Parquet. Do
not make a DuckDB file the receipt authority and do not require agents to write
to it.
