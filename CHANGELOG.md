# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html): the public interface is the `007` CLI, the receipt and report
schemas, and the dashboard snapshot.

## [Unreleased]

## [1.7.0] - 2026-11-09

Candidate prepared for independent review. Release qualification is recorded in
[the release record](evidence/v1.7.0/release-evidence.md).

### Security

- The dashboard rejects foreign, missing, duplicate or malformed HTTP authorities and absolute request targets before
  reading route data; loopback aliases, the actual port and explicitly configured external binds remain supported.
- Activity skips session enumeration when no projects are registered; the observatory does the same when enrollment is
  empty and auto discovery is off. This does not promise preselection of every file while a project scope is active.
- Lab collection now honors an explicit acceptance environment without merging parent variables; retained-case rechecks
  honor the configured wrapper and environment too. Cells label the execution boundary without claiming sandbox proof.
- Local argv and bounded diagnostics remain available by default, with additional hashes for integrity/correlation.
  Explicit `retain_diagnostic_text: false` minimizes diagnostic text in new replay/lab runs and their copies; frozen
  inputs and historical results remain unchanged. New output directories are owner-only; existing permissions are preserved.
- Stale observatory enrollment with no matching registered project skips session enumeration. Security probes use synthetic
  or explicitly allowlisted environments and avoid assertions that can render credential values.

### Added

- CodeQL and Scorecard workflows retain bounded analysis reports as Actions artifacts, with pinned actions and read-only
  repository permissions. CodeQL SARIF/database uploads and Scorecard result publication are disabled.

- Tag-triggered source candidates with repeat-build and extracted-manifest checks, SHA256SUMS and GitHub build provenance,
  retained for maintainer publication after release qualification.
- A macOS Python 3.13 CI job alongside the existing Linux check names, portable tag-manifest verification and weekly
  Dependabot proposals restricted to GitHub Actions.
- An installable `007-framework` wheel with a `007` console entry point, versioned from `SKILL.md`, carrying the existing
  runtime layout, dashboard assets and default causal evidence. A synthetic installed-CLI check covers project records and
  the HTTP dashboard. CI builds the wheel at the minimum supported Python version and runs that check.
- A short README quickstart, `PRIVACY.md` for local collection and explicit egress, and software citation metadata.
- A persistent security review workflow in the shared agent instructions: native Codex Security when available, honest
  scope/coverage and completion gates, with the same criteria across hosts and separate authorization for paid/Cloud operations.
- `effort_segments` (`[start, model, effort]`) from Codex `turn_context` and Claude assistant rows, stored by `record`; each
  report row lists its attributed commits with the model and effort in force at commit time (`commit_efforts`).

- Dashboard snapshot field `lab_ledger`: the spend 007 itself caused, per experiment listed in the local config
  (`observatory.lab_ledger: [{"name": ..., "results": "dir" or ["dir", ...]}]`, paths relative to the config file), kept apart
  from the user's own agent usage. Per experiment: first and last attempt (from `dispatch.jsonl`), attempts, valid, invalid,
  orphan receipts, USD with its sources, USD on attempts without a valid result; plus a total. Sums of `007 lab run` runner
  receipts, a client estimate and not an invoice: an attempt without a cost is counted as unpriced (the total becomes a lower
  bound), never as zero, and a missing or unreadable directory is reported unavailable instead of failing the read.
- Dashboard panel "What each 007 experiment cost" shows that field under "Spend and cost", labelled as an estimate; with
  nothing configured it says only "No 007 experiments configured".

### Changed

- The README separates effort evaluation, local observation and host-skill use. It states log-decoding and served-identity
  limits, compressed-log requirements, stable installation/PATH and integration coverage, with detailed evidence linked.
- A session whose turns used more than one model or effort is labelled `mixed` instead of its last value, so a mixed-model
  session is no longer priced at one model's rate nor matched to one model's calibration. Claude's `<synthetic>` placeholder is
  not a model.

- Dashboard: "Full evidence and operations" now uses the verdict home's type scale, spacing, flat 6 px cards and colour tokens,
  and its summary reads as a section header. Its panels are grouped under Spend and cost, Activity and coverage, Outcomes and
  gates, and Data quality; route economics, authority counts, dataset counts and the case-evolution chart start collapsed.
  Groups are h2 and panels h3, so the page keeps one h1 and no skipped heading level. Table headers are sentence case
  everywhere, the live-session table included. No claim wording changed.

### Fixed

- Codex reasoning counters reconcile reported deltas, cumulative observations and available output bounds. Optional
  baselines retain uncertainty, known cumulative values stay visible, and dated errors outside the window preserve valid primary baselines.
  Cumulative reasoning growth fits output growth over the corresponding interval, including optional gaps. Repeated
  last-usage records validate their own reasoning/output relationship before consumption is deduplicated.
  Mixed known and unknown reasoning deltas retain their feasible lower and upper bounds. Pre-window primary resets
  discard obsolete constraints, and sparse reasoning deltas obey the output growth available from cumulative counters.
  Reporting-window results reconcile cumulative, baseline and window ranges together. Unknown baselines retain their
  output bounds, zero-capacity intervals infer exact reasoning, and dated inconsistent deltas discard older constraints.
  Continuous pre-window omissions retain earlier reasoning evidence. Unanchored last observations constrain their own
  cumulative reasoning within output bounds. Mixed full/sparse last objects retain every reconstructible primary increment,
  while contradictory reported deltas remain incomplete and preserve known diagnostic totals.
- Sparse Codex reasoning deltas obey reported cumulative bounds before deduplication, while absent optional bounds remain
  unavailable. Reliably dated Kimi/Gemini events outside the window cannot invalidate current usage because of missing counters.
- Retained identified logs preserve timestamp fallback beside other contributing logs; a fresh observation replaces only
  its own log. Full and partial repeated deltas share cumulative bounds before duplicate suppression.
- Gemini validates primary composition and cache allocations per observation, preserving known primary usage with unavailable
  allocation pricing. Untimed usage and missing counter objects retain uncertainty across the native readers.
- Invalid cache-only deltas retain allocation uncertainty before fallback and duplicate suppression. Coherent partial
  allocations remain priceable through validated cumulative counters.
  Unidentified historical activity keeps its timestamp fallback when merged with named logs.
- Shared native usage checks and checked token subtotals keep unrepresentable aggregates unavailable across pricing,
  summaries, routes and the dashboard. Known finite subtotals and explicit zero remain supported.
  Token-weighted quota rejects unrepresentable denominators, and invalid provided Kimi/Gemini counters stay incomplete.
- Counter timestamps survive duplicate suppression, and untimed Claude usage or cost retains window uncertainty.
  Required cumulative cache baselines and normalized Claude cache tiers are validated before pricing.
  Contradictory cache tiers preserve known primary and aggregate usage with tier pricing unavailable.
- Cumulative windows share temporal validation across native providers. Cache allocation is validated
  before duplicate suppression and after interval/window derivation, preserving primary usage.
- Activity, route and lab-report totals expose unavailable aggregates when they cannot be represented.
  Reservation comparisons handle large integer operands. Execution and acceptance timeout limits are
  checked before launch within the portable subprocess wait range.
- Native usage windows use an inclusive cutoff, reject temporal rewinds and reconcile cache pricing counters.
  Overflow-safe monetary validation is shared by collection, telemetry, task/replay receipts and rate cards.
  Rate-card arithmetic preserves representable estimates without intermediate float overflow.
- Standalone replay rejects nonpositive timeouts before output or launch. Controller accounting preserves
  unavailable aggregate spend when individually finite costs exceed representable totals, including recovery.
- Lineage prefers current project-local identities and uses cross-project parent information only when unambiguous.
  Cumulative usage requires continuity. Contradictory cache allocation keeps primary totals available and pricing unknown.
- Replay preflight checks the target filesystem's case rules, and the lab report reuses the shared receipt classifier.
  Numeric execution limits are validated before output/dispatch. Ledger readers and sums handle oversized values safely.
- CI runs on pull requests, `main` pushes and version tags, avoiding a second full run for each development-branch push.
- Recovery preserves unavailable-cost, per-cell and invalid-count stops before dispatch. Invalid numeric costs remain
  unavailable. Controllers and the ledger share timestamp and
  repeated-terminal validation. Replay and lab entry points preflight the full cell artifact namespace before execution.
- Artifact readers distinguish identified replay cells from runner receipts, including arms ending in `.runner`.
  Ambiguous legacy artifacts stay unavailable without rewriting historical bytes. Current log identities withdraw
  obsolete parent aliases. Native usage completeness is checked per observation, before deduplication, and against
  available cumulative counters.
- The spend ledger joins dispatch-only attempts and marks malformed or duplicate dispatch history incomplete. The dashboard
  shows lower bounds for affected counts and costs. Lab controllers sharing an output directory serialize before dispatch
  and refuse uncertain or damaged history. Task/arm identity collisions fail before execution. Three-digit replicates
  remain visible to result and budget readers.
- Commit ownership carries source, project and root session through attribution, including linked worktrees. Named-log
  observations supersede by recorded order, including same-timestamp repairs and restored native timestamps. Recording
  serializes read/dedup/append and preserves torn historical bytes while separating new JSON rows. Unresolved Claude
  legacy history stays uncertain even without a fresh companion log.
- Empty Codex per-turn usage falls back to cumulative observations. Incoherent totals remain incomplete. Claude aggregate
  cache writes survive missing tier detail, with tier-dependent prices unavailable when the breakdown is unknown.
  Successful decoder recovery clears the previous unreadable-log marker.
- Parent/child consolidation preserves project scope, including record deduplication. Per-commit model and effort come from
  the contributing logs, with mixed or unavailable identity retained explicitly. Fresh Claude main-log reads replace
  identifiable legacy clipped intervals. Unresolved historical intervals stay uncertain for attribution.
- Changed plain logs verify every consumed byte before resuming their parser, detecting equal-length, regrown and middle
  rewrites on the same inode. This adds prefix-read I/O with bounded memory. Concurrent reads serialize collector state.
- Missing Claude response usage and invalid Codex snapshots remain incomplete. Durable recording keeps completeness and
  same-timestamp counter repairs. Reports retain known subtotals, while incomplete and legacy totals remain unavailable
  for token-weighted quota comparisons.
- `lab chain` creates new output directories owner-only and preserves existing directory permissions.
- Dashboard startup uses the bound address for its server metadata, avoiding reverse-DNS stalls before announcing its URL.

- Project navigation wraps to its own row when the brand and controls cannot fit, avoiding page overflow on narrow screens.
- The lab spend ledger keeps missing receipts and amounts without cost provenance unpriced, including executed failures.
  A measured zero needs an explicit numeric receipt cost and provenance.
- Local session capture reads every Codex and Claude log whole, streaming row metadata with bounded memory, and reads a growing
  log on from a byte cursor. It read only the last 4 MiB of a Codex rollout (64 MiB for Claude) and counted the unread head as
  active: on the maintainer's machine one 541 MB rollout was a single 291 h activity interval instead of 35 (60 h), so it was
  credited with commits made while it was idle, with 4 M tokens instead of 2.6 bn. Each stored row names its log (`log_id`) and
  the store keeps a log's newest whole read, so the next `record` pass replaces a clipped interval.
- Compressed Codex rollouts (`*.jsonl.zst`, 2,819 of 2,879 on the maintainer's machine) are read: `compression.zstd` on
  Python 3.14+, else the `zstd` binary. Without either they are counted in `activity_errors` and in `record`'s output
  (`unreadable_logs`), never skipped silently.
- Codex subagent and auto-review (guardian) threads report their root session's id with `subagent: true`, as Claude subagent logs
  do, so they no longer compete with the thread that spawned them for its commits; rows stored under a child's own id join the
  root once `record` reads the child's log again. With this release's fixes, one `record` pass on the maintainer's machine took
  one repository from 8 attributed, 200 ambiguous and 43 unattributed commits to 198, 13 and 40.
- With `observatory.auto`, a Codex worktree (`~/.codex/worktrees/<name>/<repo>`) is the same project as its repository (git
  common dir) instead of a project of its own.
- A Claude session opened outside a repository maps to the first repository its rows move into (`cwds`), not only to its first
  row's directory.
- The activity panel no longer freezes a session's status and its 24 h window while the log is unchanged: both are recomputed at
  every read from the metadata kept per log.
- The passive Claude reader counts each response once (Claude Code repeats a response's usage on one row per content block: 52%
  of the maintainer's assistant rows), and a present but invalid token counter makes usage incomplete instead of zero.

## [1.6.2] - 2026-11-08

Patch release: the confirmed findings of an external audit of 1.6.1, the contribution rules, reviewer identity levels and
Amendment 1 to the Codex pilot. Additive only: no command,
flag or schema field is renamed or removed. See [the release record](evidence/v1.6.2/release-evidence.md).

### Added

- Contribution rules in `AGENTS.md`, copied to `.github/copilot-instructions.md` and read by Claude Code through `CLAUDE.md`
  (a test fails if the copy drifts); `RELEASING.md`; `.github/CODEOWNERS`, a pull request template, and bug and claim-challenge
  issue templates with security reports routed to private reporting; a short `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1 by
  reference). `CONTRIBUTING.md` now points to `AGENTS.md`.

### Changed

- Reviewer identity levels (`AGENTS.md`, `review_route.identity_level`): `verified`, `pinned-no-reroute` ("requested model
  pinned, no reroute observed, served identity unverified") and `failed`. A `pinned-no-reroute` review qualifies a release only
  as "qualified with unverified reviewer identity"; the levels never apply to experiments and never fill served identity from
  the request. Not retroactive.
- `RELEASING.md`: an announcement may report any verdict of a technically qualified release; NOT-PROVEN never states the thesis
  as proven, and a pilot's GO means only that a confirmation is feasible.
- Amendment 1 to the Codex 5-point pilot pre-registration (`evidence/codex-5pp-20261108/AMENDMENT-1.md`), published before any
  pilot attempt; the original pre-registration and its hash are unchanged.

### Fixed

- Follow-up to the independent review: reject unfinished or duplicate review
  completions and extra reported models; invalidate unexplained suite failure
  despite passing per-test reports; bind dashboard verdicts to both compared
  efforts. Existing partial report bindings remain readable but apply no verdict.
- Release manifest generation preserves whitespace in tracked filenames and
  refuses unsupported escapes and links before publishing a manifest.
- `007 lab` acceptance no longer passes a test whose suite failed around it (audit 2026-11-08, F01). A `unittest` class or module
  fixture error (`tearDownClass`, `tearDownModule`) and a `go` package that fails while none of its tests did (`TestMain`'s exit, a
  panic or fatal error outside a test) used to be dropped, so the tests read `pass` and the cell could be accepted. Those tests now
  read `error`, in mining and grading alike. Ordinary known-red test failures preserve partial grades, except that Go conservatively
  charges passes in a failed package with unattributed package output, even a harmless diagnostic. Missing Go package completion,
  unexpected process exits, failed preparation, and Node file/hook failures cannot leave affected tests green. The fixed unittest
  child normally exits zero even for red tests, so any nonzero exit invalidates its passes. Tasks mined earlier keep their
  hash-bound copy of `lab_accept.py`.
- Go acceptance also tracks each test's start and completion: a known-red test cannot explain away an unfinished test's
  timeout. Passes in that package become `error`; complete lifecycles and other packages keep their existing grades.
- A replay cell keeps the change of an agent that staged or committed it (audit 2026-11-08, F02). The retained candidate patch
  diffed the index against `HEAD`, so a commit left it without the change (and with a spurious deletion of the prompt file when
  the agent committed everything), and the change counts read the index, so `git add` alone zeroed them. Both now diff against the
  snapshot commit recorded before the agent starts. Acceptance always graded the work tree and is unchanged.
- `evidence/codex-5pp-20261108/gojson-floor-5pp.json` opens with two lines of simulation progress, so it is not valid JSON (audit
  2026-11-08, F11). It stays byte-identical because the pre-registration's `SHA256SUMS` bound it; an `ERRATUM.md` and the object
  alone (`gojson-floor-5pp.clean.json`) are added and hashed in `SHA256SUMS`. No figure changes: `freeze_pilot.py` uses the floor as
  a constant. A test now parses every `*.json` under `evidence/` and verifies every `evidence/*/SHA256SUMS` line.
- `interface_hints` cuts a signature at its top-level `:` with Python's tokenizer, so a one-line definition
  (`def f(x): return x`) or a multi-line header whose last line carries a body no longer copies the body (or, in the multi-line
  case, the following added lines) into a hint that promises signatures only (external audit F08). The one replay set built
  with hints (20 tasks of this repository, 62 hints) gets the same hints under the fix; no published result used the helper.
- The effort field trial's Kaplan-Meier curve stays at 0 to the horizon once every line at risk has died, instead of ending
  there: S(30) read "unknown" for an arm whose lines all died, and the bootstrap dropped every such draw as not estimable, which
  favoured the less durable arm. A curve still stops where censoring leaves nobody at risk with S > 0 (external audit F07).
  The trial is disabled and its outcomes were never unblinded, so no result changes.
- `007 run` with a denied `--action` and an acceptance contract (always the case under a capture config) persists its blocked
  terminal receipt again: recording demanded acceptance results that a blocked task never produces, so only the start and the
  event remained (external audit F04). The receipt now marks the contract as not run, an additive `receipt/v1` state:
  `acceptance_evidence: "not-executed"`, the contract hash, and `acceptance_summary.not_executed`. The blocked path also passes
  the caller's replay vault to `record`.
- `007 run --native-cli` no longer publishes a receipt whose declared `served_model` the native stream contradicts: telemetry
  only replaced usage, time and cost, so a Claude stream reporting one model could sit beside a receipt declaring another
  (external audit F03). When the stream names models (Claude `modelUsage`, a Codex reroute target), the declared model must be
  one of them; otherwise the run exits 2 with the telemetry kept and no terminal receipt. Declared and observed identity stay
  in separate fields. No published evidence holds a receipt with native telemetry.
- Dashboard: a `007 lab report` verdict no longer reads as evidence for whichever repository is selected (external audit F09).
  The report names no repository, so `observatory.lab_report` now takes `{"path", "project_id", "cli", "model", "effort", "against"}`,
  and the thesis panel applies the verdict only to that calibration and effort comparison. A bare path still loads but binds nothing, so
  its verdict is applied nowhere.
- Dashboard: a failed background rebuild no longer leaves the previous evidence looking current while the response clock moves
  (external audit F10). The preserved projects and aggregate are marked stale (gates WAIT, "STALE DATA"), the snapshot carries
  `rebuild_error`, and the top bar shows when the evidence was read (`evidence_read_at`) apart from the response time; Data
  quality names the failure.

## [1.6.1] - 2026-11-08

Patch release: fixes and documentation; no new command or schema.

### Fixed

- `007 lab sufficiency` measures only the behaviour the commit introduced (hidden tests minus the baseline), so an empty patch
  never qualifies; its docstring names the selection bias toward "equal".
- A dashboard layout test's 5-second subprocess timeout, which failed once on a loaded CI runner, is now 60 seconds.

### Changed

- The thesis, `docs/lab.md` and `report.md` state that a verdict holds for the specification form the set used (commit message
  plus pinned names) and that well-specified-task filters pull it toward "equal". `007 lab` is labelled beta. The dashboard
  says "less quota" is estimated as cost.
- The README opening says what 007 is: a toolkit that drives your agent CLIs (lab, skill, run/record/route/dashboard), not an
  agent and not only a skill.

## [1.6.0] - 2026-11-08

Minor release: new commands and schemas are additive, and v1 receipts stay valid. Behaviour changes are listed under
"Migration and proof boundaries".

### Release review fixes

- `007 lab sensitivity` counts a mutant only where the task's reference patch passes the oracle: an oracle that rejects
  everything no longer looks sensitive. (go-json's 62 reference patches all passed, so its published gate is unchanged.)
- `mine` and `collect` refuse a symlink anywhere on the path of a hidden test or of `.007-accept`, so a mined repository cannot
  redirect writes outside the temporary tree (`replay_eval.hidden_target`, reused).
- `report` names orphan receipts (an attempt with no result) and refuses to report when no valid cell remains.
- Codex runs record a server reroute (`model rerouted: A -> B`, the only served-model signal the Codex CLI emits) as the served
  model, so a rerouted run fails as `served-model-mismatch` instead of passing as unverified.
- Docs: `--max-usd` is a dispatch reservation, not a hard cap; planning sizes are normal approximations (lower bounds); the
  calibration's error rates are simulation results with the reach set taken as given; keep the set and its margin unchanged
  after the first attempt. "41 commits cannot reach a 3-point verdict" softened to a planning estimate, with errata in the
  go-json results.
- Dashboard: an equal accepted count reads "matched", never "enough" or "use"; the thesis line follows 1.6.0; less reasoning
  is a manipulation check; the one-task v1.4 comparison is labelled as such; effort-trial sessions are counted by arm in force
  (they share draws) and a disabled trial reads paused; blocked tasks no longer read as declared acceptances; worktrees with the
  same folder name are told apart; live sessions show age and N/A for incomplete usage.

### Thesis D: minimum sufficient effort

- Product thesis moved from "007 doctrine vs none" to the canonical minimum-intelligence thesis: the least reasoning effort that
  keeps accepted, durable changes, measured per repository. README states the bounded evidence (holdout: Codex `medium` matched
  `xhigh` with ~52% less time; Claude `medium` failed the zero margin; harder tasks at ceiling, Codex only, exploratory).
- Add `007 --version` (from `SKILL.md`, the single version source) and list `lab` in `007 -h`.
- Add `choice_observatory.py`: sessions attributed to commits by activity intervals (ambiguous commits are never guessed), line
  survival at 7/30 days, and an evidence level on every judgment; `touch_rate.survival` extracted for reuse.
- Add `effort_trial.py`/`effort_trial_analysis.py` for an opt-in randomized field trial of default effort (off by default;
  blinded outcomes) and `config_guard.py`, which refuses settings that would change the meaning of evidence levels.
- Native runner hardening found by adversarial review: whole pipe drained after exit, all served models kept, receipts reserved
  before spending, option allowlist with user configuration sources off, error classes (rate limit vs transient), acceptance run
  inside a sandbox with a minimal environment.
- Internal planning documents are no longer shipped in the public tree.
- Thesis restated by what can prove each part: a repository measures the savings and guards against a large loss (`KILL`
  when the whole interval is below -3 points); a 3-point bound probably needs more commits than one repository like go-json
  has (a pooled public corpus), with one verdict per executor.
- Public pre-registered replay on go-json-experiment/json (Codex `medium` vs `high`, 62 commits): reasoning -67%, median agent
  time -32%, same change +1.3 pp (95% t interval -4.7 to +7.2), not proven. It did not reproduce the +9.4 pp post-hoc Codex gain.
- `007 lab mine` skips commits with more hidden tests than the acceptance reader takes; `report` counts unreadable test
  reports as no test passing and names them in `unreadable_outcomes`.
- README states what one repository can show: measured (time and tokens with intervals), guarded (`KILL` near the loss that
  erases the saving), bounded (the same change within 3 points stays open); "less reasoning" is the manipulation check.
- Pre-registration of Claude Opus 5.5 `medium` vs `xhigh` on the same 41 go-json commits, margin 10 points (the decision
  margin), 2 fresh attempts per arm, critical-value floor fixed in advance: `evidence/go-json-claude-20261107/`.
- Claude result: −5.5 pp (95% t interval −11.8 to +0.7), not proven at the 10-point margin; agent time −67%, median cost −75%;
  acceptance on solved commits −11.1 pp (secondary). The between-commit spread was about five times Codex's, so README and
  `docs/lab.md` now give margin sizes per executor.
- `007 lab mine` no longer drops a commit that deletes a test or fixture file: hidden files are only those present at the
  commit (`git log --numstat` lists deleted files too). Found mining BurntSushi/toml, where it dropped 3 of 96 candidates.
- Pre-registration of a Codex `medium` vs `high` pilot on five pooled zero-dependency Go repositories, margin 5 points: it fixes
  the reach set, the noise and a go/no-go rule, and the confirmatory rules in advance: `evidence/codex-5pp-20261108/`.
- Thesis D restated as a decision: `007 lab` shows whether a lower effort pays, against a margin the set declares before any
  attempt (`compare.margin`, default 3 points, at most 20): break-even, "effectively the same" at 5, research precision at 3.
  `report` also writes `report.md`, the verdict in plain words. Durability leaves the claim until it is measured.
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

### Evidence and replay

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

- Receipt v1 files are not rewritten. Keep the prior installation for rollback.
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
- Still open: final native canaries, prospective cases, financial bounds and
  installation/rollback. Release CI passed; the independent review failed identity
  validation ([release record](evidence/v1.6.0/release-evidence.md)).

## [1.5.2] - 2026-10-06

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

## [1.5.1] - 2026-10-06

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

## [1.5.0] - 2026-10-06

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

## [1.5.0-rc.2] - candidate, never tagged

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

[Unreleased]: https://github.com/marcuscavalcanti/007-framework/compare/v1.7.0...HEAD

[1.7.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.6.2...v1.7.0
[1.6.2]: https://github.com/marcuscavalcanti/007-framework/compare/v1.6.1...v1.6.2
[1.6.1]: https://github.com/marcuscavalcanti/007-framework/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.5.2...v1.6.0
[1.5.2]: https://github.com/marcuscavalcanti/007-framework/compare/v1.5.1...v1.5.2
[1.5.1]: https://github.com/marcuscavalcanti/007-framework/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.1.0...v1.4.0
[1.1.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/marcuscavalcanti/007-framework/releases/tag/v1.0.0
