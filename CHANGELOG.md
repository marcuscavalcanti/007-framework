# Changelog

All notable changes are documented here.

## [Unreleased]

### Thesis D: minimum sufficient effort

- Product thesis moved from "007 doctrine vs none" to the canonical minimum-intelligence thesis: the least reasoning effort that
  keeps accepted, durable changes, measured per repository. README states the bounded evidence (holdout: Codex `medium` matched
  `xhigh` with ~52% less time; Claude `medium` failed the zero margin; harder tasks at ceiling, Codex only, exploratory).
- Add `choice_observatory.py`: sessions attributed to commits by activity intervals (ambiguous commits are never guessed), line
  survival at 7/30 days, and an evidence level on every judgment; `touch_rate.survival` extracted for reuse.
- Add `effort_trial.py`/`effort_trial_analysis.py` for an opt-in randomized field trial of default effort (off by default;
  blinded outcomes) and `config_guard.py`, which refuses settings that would change the meaning of evidence levels.
- Native runner hardening found by adversarial review: whole pipe drained after exit, all served models kept, receipts reserved
  before spending, option allowlist with user configuration sources off, error classes (rate limit vs transient), acceptance run
  inside a sandbox with a minimal environment.
- Internal planning documents are no longer shipped in the public tree.
- Thesis restated by what can prove each part: a repository measures the savings and guards against a large loss (`KILL`
  when the whole interval is below -3 points); a 3-point bound needs more attempts per commit or a pooled public corpus, with
  one verdict per executor.
- Public pre-registered replay on go-json-experiment/json (Codex `medium` vs `high`, 62 commits): reasoning -67%, median agent
  time -32%, same change +1.3 pp (95% t interval -4.7 to +7.2), not proven. It did not reproduce the +9.4 pp post-hoc Codex gain.
- `007 lab mine` skips commits with more hidden tests than the acceptance reader takes; `report` counts unreadable test
  reports as no test passing and names them in `unreadable_outcomes`.
- README states what one repository can show: measured (time and tokens with intervals), guarded (`KILL` near the loss that
  erases the saving), bounded (the same change within 3 points stays open); "less reasoning" is the manipulation check.
- go-json top-up result (pre-registered, 656 attempts, US$173 list price): Codex `medium` vs `high` −0.9 pp, 95% CI −3.4 to
  +1.6, not proven; agent time −30%. Commits differ in effect beyond what 41 can absorb, so "one repository may be enough" is
  withdrawn; a 3-point bound needs several repositories.
- Pre-registration of a go-json top-up (41 commits × 8 fresh attempts per arm, two looks, critical-value floor fixed in
  advance): `evidence/go-json-topup-20261106/`.
- The time gate no longer compares raw accepted counts (equal arms failed it about half the time); acceptance enters through
  time per accepted change and the same-change verdict. `reach_rates`, `reachable_diffs` and `proven_critical` accept a frozen
  reach set (`reach=`), and `proven_critical` an attempt count (`attempts=`), so a pre-registered run fixes its denominator and a
  critical-value floor from earlier attempts.
- `007 lab run` takes `--max-invalid`; an invalid cell whose call reported no cost is charged its reserve instead of stopping the
  run at the first provider error, and a cell the runner refused before writing its receipt is reported invalid instead of
  breaking `report`. `line_trial` counts files a run created.
- Grading no longer lets the agent's own Go tests break a package: files matching a task's `reset_to_base` (`*_test.go` for
  the go adapter) go back to base before the hidden tests land.
- `same_change` (point estimate on tests that split cells, about one false `KILL` in three under no difference) is now only a
  diagnostic; `same_change_reachable` governs and its `KILL` kills the thesis. Its `PROVEN` must beat a critical value
  simulated from the run's own cells with a 3-point loss of whole failed attempts (`proven_critical`): the t interval proved
  such a loss up to 5.6% of the time on go-json, and bootstrap-t and Johnson's skew-corrected t did worse (up to 9.8%). The t
  interval now uses t at every task count. Report schema v6.
- Dashboard: "the same change" reads `same_change_reachable` and never shows a green state without a proving report; "less
  quota" is its own claim, `ESTIMATED`, because it comes from a price estimate.
- go-json evidence, without a model: re-graded with the fix, the per-attempt noise halves (6 of 231 attempts changed) and the
  verdict stays not proven (+1.5 pp, CI −3.2 to +6.2); the planted-defect check, which had been a stub, now ran and passes
  (79% of partial changes rejected). Under the calibrated rule, two attempts per arm almost never prove; about eight per arm on
  the same 41 commits would prove equal arms about three times in four if commits do not differ in effect.
  README and docs restate what one repository can show.

### Evidence and replay candidate

- Treat persisted acceptance/authority labels as declarations, not authenticated
  controller authorship. Original receipts and declared outcomes are preserved;
  the dashboard no longer turns locally writable evidence into verified authorship.
- Add experimental native JSON-stream adapters for fresh non-interactive Codex
  and Claude commands. Reject inherited/forked sessions, ambiguous identities,
  duplicate/truncated or over-budget streams; preserve unknown usage and cost.
  A real canary is still required for each advertised route and mode.
- Mark clipped Codex session-tail consumption as incomplete, preserving observed
  counters without submitting them for rate-card pricing. Show partial token
  coverage in the overview and affected project rows, not as a complete period.
- Retain explicitly declared pre-edit files, instructions, environment and
  acceptance recipes in a private vault, with byte/mode checks and no-replace
  publication. Restore inputs and candidates without the original checkout.
  This is a declared dependency closure, not automatic full-project capture.
- Preserve stable candidate outputs after supported incomplete outcomes,
  including telemetry publication collision, only after confirmed cleanup.
  Do not fabricate a terminal receipt, cost or successful shutdown.
- Use shared cohort economics across reports, dashboard and routing: include
  failed attempts, separate USD bases, account inclusive parent/child totals once,
  and keep incomplete cost or followup coverage unavailable for comparison.
- Add optional disjoint USD cost portions for executor, review, retries,
  verification, infrastructure and preparation. All six must reconcile to the
  declared total before full-scope economics qualifies routing or readiness;
  unknown overhead never becomes zero or upgrades historical receipts.
- Clear full-scope economic eligibility when route identity is incomplete or
  a project's source is unavailable, including an HTTP-successful stale read.
  Preserve historical data without current approval, and recover on a valid read.
- Add retained-case admission, contamination checks and explicit bounded oracle
  rechecks. Historical calibration never becomes holdout by changing a label.
  Qualified real comparisons are not yet admitted by the new dataset path.
- Add serial USD30 reservation/reconciliation accounting, checkpoint stops and
  unknown-cost/overrun handling. Accounting is not a provider spending cap;
  public retained-vault experiment execution remains disabled pending qualification.
- Add bounded dashboard event/case timelines, local-time dates, factual receipt
  contribution, stale last-good data and single-flight polling. Existing global
  historical comparisons do not represent new per-project causal experiments.
- Reuse the existing muted palette for secondary text that failed contrast checks;
  preserve keyboard focus, layout, metric values and evidence boundaries.
- Add idempotent read-only curation and sanitized checkpoint projection, with
  append-only hash/task/candidate-bound declared correction and escape links.
  Show source and affected-case counts by project without authenticating incidents.
  Accept hash/task/candidate-bound proposed hypotheses with one new routing and
  one new gate source per curation cycle; show sanitized kind/hash references
  and declared counts by project. Automatic generation, policy application and
  daily activation remain pending; proposals are not qualified improvements.
- Make historical tests reproducible from source archives using hash-bound MIT
  proof inputs. Add a synthetic integrated controller check for restoration,
  oracle controls, seeded order, complete cost arithmetic and repeated decisions.
- Add a licensed static synthetic replay corpus and full semantic regression
  digest for independent offline reproduction; keep native runtime mismatch
  rejection separate from portable fixture controls and economic ROI.

### Migration and proof boundaries

- Receipt v1 files are not rewritten. Keep the prior installation for rollback;
  this candidate has not been installed, integrated or released.
- Amount-only v1 receipts remain valid and descriptive but no longer qualify
  measured route ranking or readiness. Supply explicit reconciled cost portions
  prospectively; this is declaration coherence, not authenticated billing or ROI.
- Capture is explicit through a declared config and starts before task edits.
  Existing project use or old receipts do not imply replay retention.
- Native capture initially targets supported fresh non-interactive envelopes.
  Interactive/resumed tasks remain outside that promise until qualified.
- Same frozen bytes, versions and seed must yield the same controller decisions.
  Fresh LLM generations and newly captured local fixtures may differ.
- Costs in synthetic tests are literal fixture data, not charges or savings.
  No new real OLD×NEW benefit, reliable-result cost or net financial ROI is claimed.
- Final native canaries, prospective cases, financial bounds, independent review,
  installation/rollback, public content audit and release CI remain open.

## [1.5.2] — local candidate (2026-10-06)

- remove the inherited body minimum width that caused whole-page overflow at
  320px with a classic scrollbar; sampled wider layouts remain unchanged;
- add a stdlib browser-assisted selfcheck that rejects hidden/zero-sized causal
  values and verifies the actual dashboard at four widths; it is separate from
  unittest discovery and does not claim automatic browser CI coverage;
- keep the Headroom-inspired information hierarchy, honest unknown telemetry
  and historical/global causal scope unchanged; no new dependency or schema;
- preserve 1.5.1 and every historical causal artifact. Source commit `31c499ff`
  passed exact-commit Linux CI and a context-only independent package review;
  subsequent documentary bytes require separate qualification. This candidate
  is not publication, new ROI evidence or D7/D30 qualification. See
  [proof and remaining gates](evidence/v1.5.2/release-evidence.md).

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
