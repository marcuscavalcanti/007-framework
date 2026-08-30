# Changelog

All notable changes are documented here.

## [Unreleased]

### Added

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
