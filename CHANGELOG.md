# Changelog

All notable changes are documented here.

## [Unreleased]

## [1.5.1] — source changes (2026-10-06)

- prioritize accepted changes, measured repair rounds, terminal cost and open
  tasks in a Headroom-inspired dashboard; no assets or implementation copied;
- distinguish controller-observed acceptance from declarations, declared D7
  follow-up from verified durability, and provisional cost from final accounting;
- align per-route and aggregate accepted-follow-up denominators and expose
  cost provenance; open starts remain outside terminal cost;
- keep the historical effort comparison global and task-local; incomplete served
  identity is never presented as verified;
- preserve the v1.5.0 manifest and validate its historical Git blobs rather than
  requiring future versions to remain byte-identical to that release;
- add a deterministic admission-fence contrast on two sanitized defect-derived
  cases: 36 cells, zero invalid; NEW blocked all six defective candidates,
  accepted all six correct controls and left six unverifiable starts open.
  Two earlier inconclusive runs are preserved. These repetitions do not prove
  real-world ROI, model quality, general review replacement or D7/D30 durability;
- no new dependency, receipt contract, provider call, database or scheduler.
  The runtime/dashboard candidate has independent source review and exact-main
  Linux CI on Python 3.11/3.12/3.13: 155 tests per job, no test skips. The
  isolated install/rollback check covers symlinks and CLI startup only.
  Final documentation is a separate diff; exact-commit CI and tag/artifact
  verification remain distinct from source qualification. See
  [qualification](evidence/v1.5.1/release-evidence.md).

## [1.5.0]

- include stable version metadata, documentation and a separate public manifest;
- preserve the RC runtime, dependencies and historical causal artifacts byte-for-byte;
- record successful RC Linux CI with exact commit/job/attempt provenance;
- include the two RC and one prepared-stable reject verdicts with their
  hash-bound counterproofs; these preparation records do not establish
  independent approval or final-stable CI for a different commit;
- distinguish pre-test CI runner-allocation failures from observed test failures;
- require full Git history and the pinned v1.4 release tree before CI tests;
- publication requires explicit identity review, final-byte gates, a clean
  committed candidate, approval, authorization and tag/artifact read-back.

## [1.5.0-rc.2] - Unreleased candidate

### Added

- explicit opt-in for unavailable receipt cost, preserving unknown cost rather
  than manufacturing zero and excluding unpriced outcomes from economic claims;
- argv-only acceptance contracts frozen at task start; the controller records
  actual check results instead of trusting an executor's claimed checks;
- public first-shutdown-signal latch protocol and 12-cell local mutation/control
  result, exact reproducible mutant patch and observed assertion signatures,
  with a package manifest bound to the candidate source.

### Compatibility changes since 1.4.0

- malformed/non-finite receipt metrics are rejected, not silently normalized;
- after normal executor wait, unconfirmed cleanup returns exit `2`, writes no
  terminal receipt and leaves the task start open, even if the executor failed;
  wrappers must not interpret a missing receipt or exit `2` as acceptance;
- unavailable cost is accepted only with explicit project opt-in and the complete
  null-cost fields; it remains unaccounted and excluded from economic claims.
  Priced receipts retain their previous contract. See
  [receipt semantics](references/receipt-schema.md).

### Fixed

- preserve incomplete token usage and reject malformed/non-finite receipt metrics;
- confirm process-group cleanup after normal exit, failure or timeout before
  interpreting acceptance, receipts or replay diagnostics;
- preserve the first scoped shutdown signal, caller/ignored handlers and original
  unwind when cleanup diagnostics cannot be written; keep interrupted starts open.

### Evidence boundary

- runtime source is unchanged from the locally qualified a3012ee commit;
- the mutation contrast supports only the local first-signal latch mechanism;
- historical v1.4 economic results stay task-local; no new model or ROI claim;
- this is not a stable release: independent review, supported-version CI, clean
  committed release evidence and publication/read-back remain pending.

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
