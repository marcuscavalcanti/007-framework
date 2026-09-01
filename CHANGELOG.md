# Changelog

All notable changes are documented here.

## [Unreleased]

## [1.4.0] - 2026-08-31

### Added

- deterministic task-start routing across user-configured installed CLIs;
- fail-closed eligibility based on mature reliability, escapes, repairs, cost,
  and wall time before cost/latency optimization;
- aggregate and per-route reliable outcomes per USD and wall time per reliable
  outcome, counting failed attempts;
- a separately frozen causal ROI card based on one real paired-effort coding task;
- a public fail-closed record for the broader v16 bank that stopped inconclusive.

### Evidence boundary

- `medium` and `xhigh` passed deterministic acceptance 3/3 on the same real
  task; `medium` reduced estimated cost per accepted task by 42.6% and wall
  time per accepted task by 53.9%; per-cell ranges remain visible;
- this is a task-local mechanism result, not proof of task-class routing,
  provider portability, or D7/D30 durability;
- the v16 bank is inconclusive because protocol and grader precedence conflicted;
  its raw failed outputs do not support an economic or policy verdict.

### Fixed

- prevent a receipt author from promoting declared boundary events to
  controller-observed evidence;
- block denied and unclassified `007 run --action` commands before subprocess
  creation while preserving allowed controls;
- keep known performance failures visible while measurement gaps remain and
  exclude preventive controller blocks from the outcome-quality trend;
- require controlled provenance to match its persisted no-replace event and
  exclude pre-execution blocks from model-telemetry completeness;
- reject terminal receipts without a matching task-start record, closing a
  bypass that could silently remove authority binding;
- measure reported authority friction against allowed attempts instead of all
  blocked events;
- label boundary telemetry as self-reported and distinguish envelope presence
  from policy strictness;
- report deterministic causal evidence as distinct arm-scenario outcomes, each
  reproduced three times, rather than implying independent repeated cases.

### Added

- a three-state objective verdict, seven-gate decision matrix, primary next
  action, 30-day outcome trend, and aggregate/project provenance reconciliation;
- controller-observed, agent-declared, and unobserved authority tiers;
- an 18-cell deterministic OLD×NEW controller-authority flip-test with zero
  model calls and zero retries;
- optional SHA-256-bound authority envelopes with fail-closed terminal
  validation of reported boundary actions;
- aggregate and per-project fence telemetry for authority coverage, protective
  blocks, avoidable friction, and unclassified blocks;
- a preregistered OLD×NEW mechanism test with six distinct arm-scenario
  outcomes, each reproduced three times, and two negative controls.

- atomic, no-replace task-start records that expose missing terminal receipts;
- an Evidence Cockpit focused on reliable first-pass outcomes, observation
  coverage, cost per reliable outcome, and an explicit operational-versus-causal boundary.
- sanitized Codex/Claude/Kimi/Gemini activity per project with 24-hour token deltas;
- Headroom/LiteLLM-equivalent cost estimates with explicit lower bounds and
  unknown-model coverage;
- terminal-receipt cost as the KPI authority, with Headroom/RTK/rate-card values
  kept as optional diagnostics;
- corrected cache accounting that avoids charging cached input twice;
- provider-neutral `007 run` lifecycle wrapper for automatic starts and
  fail-closed terminal receipts.

## [1.1.0] - 2026-08-30

### Added

- automatic local registration for every Git project using the framework;
- explicit unregister command for stale or retired local project paths;
- atomic, no-replace terminal receipts with mandatory provider-neutral cost accounting;
- localhost multi-project dashboard with aggregate/project reconciliation and near-real-time polling;
- requested-versus-served provider/model/effort telemetry and cost coverage gates.

### Deliberately deferred

- provider-specific rate tables and model allowlists;
- DuckDB or another database before receipt volume or query latency demonstrates a need;
- login/authentication while the dashboard remains loopback-only.

## [1.0.0] - 2026-08-30

### Added

- provider-neutral routing, reuse-first implementation, proof gates, and outcome receipts;
- standard-library receipt, touch-rate, and causal replay tools;
- deterministic package tests and GitHub Actions CI;
- public controlled evidence with explicit claim limits.

### Excluded

- rejected external-provider credential doctrine;
- private probes, acceptance-test bodies, repository snapshots, and credentials;
- superseded laboratory implementations and provider-specific adapters.
