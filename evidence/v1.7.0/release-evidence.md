# 1.7.0 candidate — capture, local operations and distribution

Prepared on 2026-11-09 from published 1.6.2. This minor release adds compatible
observational fields and packaging. The receipt and report schema identifiers,
existing commands and existing options remain supported.

## Changes under qualification

- Session capture streams complete logs with byte cursors, supports compressed
  Codex logs, joins child sessions to their parent and records model/effort
  segments. Worktrees join their Git repository. Passive collection reports its
  observed coverage and preserves incomplete or unavailable usage.
- The lab spend ledger reports retained attempt costs and their provenance.
  Missing receipts or unpriced attempts remain explicit. A mixed session is
  labelled mixed. Passive activity and attribution are observational.
- The stdlib runtime is installable as a wheel with the existing `007` CLI.
  Installed-package checks exercise project records and the HTTP dashboard.
  The version comes from `SKILL.md` for source and installed entry points.
- The dashboard validates HTTP authority before reading route data and starts
  without reverse DNS. Capture skips enumeration when its registered scope is
  empty. Explicit execution environments and wrappers are honored.
- Local argv and bounded diagnostics are retained by default. Diagnostic
  minimization is opt-in. Existing frozen inputs and historical results keep
  their bytes. Local retention and model egress have separate authorization.
- CI adds macOS, pinned actions, source-candidate provenance preparation,
  CodeQL artifacts and a Scorecard workflow. Account settings, required checks,
  package publication and operational installation have separate gates.

The existing provider-neutral core and explicit adapters remain the routing
boundary. These additions do not select a model or authorize an execution.

## Engineering evidence and limits

The versioned candidate `4cdca26bf9fd9a14e164ac446d7fbb94b192ccde` received
FIX FIRST from its single authorized independent review. That call is consumed.
Release is blocked. The local follow-up corrects ledger cost completeness,
project and route attribution, legacy Claude intervals, changed-log cursors,
usage completeness and output permissions. A reproduced concurrent-collection
race is corrected too. The follow-up passed 822 native Python tests without
skips and 51 JavaScript tests. Gitleaks found no secrets in its directory scan.
The corrected candidate still needs its current manifest, distribution, CI
and newly authorized independent review before release.

The follow-up candidate5dca544 received FIX FIRST in a subsequent single
authorized review. Its new fix pass covers dispatch-only and damaged-history
accounting, scoped ownership through attribution, observation supersession,
legacy-only uncertainty, empty native deltas and aggregate cache writes.
Connected controls cover duplicate controllers, ambiguous cell identities,
three-digit replicates, torn-history append and decoder recovery. These runtime
changes passed 839 integrated native Python tests without skips and 52 JavaScript
tests. Updated documentation and the source manifest are checked separately.
The corrected candidate still needs exact distribution/remote checks and a
newly authorized independent review before release.

Candidate `bdd702b5cbab6fd2ecfed36b894143275738a80a` received FIX FIRST in
its single authorized follow-up review. Its six original counterexamples were
recognized as corrected. A new local pass addresses connected recovery-cost,
lineage, artifact-namespace, standalone preflight, usage and dispatch-history
failures. Focused RED-to-GREEN checks passed. A connected recovery audit also
restores per-cell and invalid-count stops and rejects invalid numeric costs.
The final local pass passed 851 integrated native Python tests without skips
and 52 JavaScript tests. The final release-record paragraph and source manifest
are checked separately. Distribution, remote and newly authorized independent
review qualification of these changed bytes remain pending.

Candidate `55984a336123733815813758b8000e5b450982bb` received FIX FIRST in
its single authorized review. The next local pass covers project-local lineage,
cumulative continuity, cache allocation, filesystem naming, numeric control and
accounting boundaries, and the remaining report reader. The CI triggers and
README were updated under explicit operator instructions. Focused regression
matrices passed. The first integrated run passed 864 native Python tests
without skips. A subsequent compatibility audit reproduced and corrected an
explicit legacy main identity without log_id; 52 connected checks passed. The final integrated run passed 865 native Python tests without skips in
288.964 seconds and 52 JavaScript tests. The final release-record paragraph and
source manifest are checked separately. Exact-source distribution, remote checks
and a newly authorized independent review remain pending.

Candidate `222b24c586d0136721af7ca0c7a9ec063a64383d` received FIX FIRST
in its single authorized review. The next local pass covers timestamp rewinds
across the usage window, per-observation cache tier/allocation coherence, shared
monetary validity in native collection, telemetry, receipts and rate cards,
positive standalone timeouts and finite controller accounting during execution
and recovery. Decimal pricing avoids intermediate float overflow while retaining
representable estimates. Focused matrices passed 109 and 139 connected tests. The first integrated run
passed 873 native Python tests without skips in 172.216 seconds. An additional
cutoff-boundary audit reproduced and corrected cumulative undercounting at the
inclusive window edge. The final native run passed 873 tests without skips in226.652 seconds,
with 52 JavaScript tests. The final record and manifest are checked separately.
Exact-source distribution, remote checks and fresh independent review remain
pending.

Candidate `9af7c9e00c92ca8feb86c154f0aa196ff99b4b66` received FIX FIRST
in its single authorized review. The next local pass applies shared window
coherence to Claude and Codex, preserves duplicate-allocation anomalies without
double counting, and validates raw, derived and aggregated price allocations.
Overflow-safe totals cover activity, routes and lab reports. Portable timeout
limits are checked before execution, and reservation comparisons use checked
monetary arithmetic. Focused regressions reproduced the six findings before
correction. The integrated native run passed 880 tests without skips in
323.438 seconds. JavaScript, final record/manifest, distribution and remote
checks are recorded separately; fresh independent review remains required.

Candidate `ea561e2be4f8add1337fb0875b6403b50fd2c6e3` received FIX FIRST
in its single authorized review. Its four connected counterexamples were
reproduced before correction. Temporal evidence now survives counter
deduplication, and untimed Claude cost and usage retain window uncertainty.
Pricing validates required cumulative baselines, normalized cache tiers and
conflicting tier aliases. Known primary and aggregate usage remains available
when finite cache tiers contradict their allocation. The final integrated native
run passed 885 tests without skips in 223.664 seconds. Final record, manifest,
distribution, remote checks and fresh independent review are qualified separately.

Candidate `56e7d21b4eb8b7b547bf6fccc3a61e1d7d837563` received FIX FIRST
in its single authorized review. The three source counterexamples were reproduced
before correction. Invalid cache-only deltas now retain pricing uncertainty,
while coherent partial fallback remains priceable through cumulative counters,
and unidentified historical rows preserve their timestamp fallback during merging.
Shared native counter validation and checked subtotals keep unrepresentable
aggregates unavailable while preserving finite known subtotals and explicit zero.
The pricing, summary, route and dashboard readers enforce those boundaries.
The final native run passed 891 tests without skips in 175.764 seconds, and
54 JavaScript tests passed. Final record, manifest, distribution, remote checks
and fresh independent review are qualified separately.

Candidate `ebb6b5e309241f4d56a9e5e3f106f712623f4e2d` received FIX FIRST
in its single authorized review. Four source counterexamples were reproduced
before correction. Retained identified logs now preserve fallback activity when
other logs contribute intervals. Complete and partial repeated deltas share
cumulative bounds. Gemini checks primary composition and cache allocations
before aggregation. Recognized untimed native records retain window uncertainty.
Recognized usage events with missing or non-object counters also retain
uncertainty instead of allowing earlier observations to appear complete.
The final connected matrix passed 156 Python checks. After that boundary fix,
the integrated native run passed 898 tests without skips in 174.338 seconds.
JavaScript, final record, manifest, distribution, remote checks and fresh
independent review are qualified separately.

Candidate `3767a786c526263a19d7237dbe61ab8b0bd6db6e` received FIX FIRST
in its single authorized review. The four historical counterexamples were
recognized as corrected. Two new counterexamples were reproduced before a
shared native-reader correction. Present sparse reasoning counters now obey
available cumulative bounds before duplicate suppression. A reliably dated
event outside the reporting window is excluded before payload completeness
checks, while an unknown timestamp retains uncertainty. Coherent sparse records,
absent optional bounds, the inclusive cutoff and explicit zeros remain supported.
The final native integration passed 901 tests without skips in 172.583 seconds.
The final record and manifest are checked separately. Exact-source distribution,
remote checks and a newly authorized independent review remain required for
this changed tree.

Candidate `4e84c926c9f48264eff23ce820993fb43439bde2` received FIX FIRST
in its single authorized review. The preceding two findings were recognized
as corrected. A shared follow-up preserves optional reasoning-counter presence
beside normalized counters, checks available output bounds and reconciles
reported deltas with cumulative observations. Missing baselines remain unknown.
Known cumulative values remain visible with incomplete flags when observations
contradict them. Valid primary baselines remain usable when a dated optional
counter defect falls outside the window. Regressions cover numeric bounds,
gaps, absent optional fields, explicit zeros, duplicates and temporal scope.
The connected matrix passed 163 Python checks. Final native integration passed
905 tests without skips in 161.780 seconds. The final record and manifest are
checked separately. Exact-source distribution, remote checks and a newly
authorized independent review remain required for this changed tree.

Candidate `571728f6790dc986de65f7910cf737d70ded99ac` received FIX FIRST
in its single authorized review. Its preceding reasoning counterexamples were
recognized as corrected. The next pass bounds cumulative reasoning growth by
output growth across corresponding snapshots, preserving valid anchors through
absent optional fields. Invalid old anchors are discarded so valid current
usage remains readable. A repeated last-usage object validates its own
reasoning/output bound before duplicate suppression. Known diagnostic counters,
explicit zeros and coherent repeats remain supported. The original reproductions
had 20 assertion failures. A preservation regression in the initial correction
had one failure and was corrected. The local activity module passed 79 tests.
An arithmetic feasibility matrix matched all 642 synthetic cases. Final native
integration passed 909 tests without skips in 177.659 seconds and the frontend
passed 54 JavaScript tests. The final record and manifest are checked separately.
Exact-source distribution, remote checks and a newly authorized independent
review remain required for this changed tree. The frozen retrospective backtest
of 571728f remains scoped to its original inputs and does not qualify these bytes.

Candidate `d99285b63d5032214d7ef11c86b78d2ea272545f` received FIX FIRST
in its single authorized review. Its preceding counterexamples were recognized
as corrected. The next pass preserves feasible lower and upper reasoning bounds
through mixed cumulative and delta observations. Known deltas keep their exact
contribution. Unknown deltas retain only their corresponding output capacity.
Primary resets before the cutoff discard obsolete constraints, and a sparse
reasoning delta also obeys available output growth derived from primary totals.
The reproductions had 16 assertion failures before correction. A retained CI
regression evaluates 3,456 mixed histories against independently enumerated
integer values and reproduced 128 failures against the reviewed old runtime.
An additional independent check matched 78,750 cases in its declared finite
grid of full and sparse last-usage observations. The local-activity module
passed 83 test methods. Runtime changes add 16 lines and remove seven without
a dependency. Final native integration passed 913 tests without skips in
206.660 seconds and 54 JavaScript tests. The final record and manifest are
checked separately. Exact-source distribution, remote checks and a newly
authorized independent review remain required for the changed tree.

Candidate `e075ee2e0e71435c9d7b5f6ddb712c024f6692d6` received FIX FIRST
in its single authorized focused review. The interval transition was recognized
as correct on a trusted continuous chain. Four boundary counterexamples were
reproduced before correction. Reporting-window reconstruction now maintains
cumulative = baseline + window with feasible ranges for all three values.
Unknown optional baselines retain their known output bounds. Full deltas agree
with primary increments before establishing an exact reasoning transition.
Dated invalid transitions discard older constraints. Singleton window ranges
retain exact results from zero output growth and sparse reasoning deltas.
Reported diagnostic values remain separate from feasibility. Two older positive
fixtures implied reasoning beyond baseline output. Their exact inputs now stay
as negative controls beside feasible controls, with primary totals and reported
diagnostics retained. The capture module and a synthetic price/cache recovery
check passed 91 methods. The retained checks include 19,424 temporal/zero-growth
histories and 2,800 exact range-projection cases, alongside the prior 3,456-case
matrix. An independent reference matched 273,600 histories in its declared
variable-growth and reporting-window domain. Runtime changes add 77 lines and
remove 37 without a dependency. Final native integration passed 921 tests
without skips in 236.121 seconds and 54 JavaScript tests. Final documentation,
manifest, exact-source distribution, remote checks and a newly authorized
independent review remain separate qualification gates for the changed tree.

Candidate `f5c4941ad8e25a5a5bc544167f0e3aa94e955b1f` received FIX FIRST
in its single authorized review. The previous four corrections, three-range
arithmetic and cached-price invalidation were recognized within their supplied
scope. The two remaining counterexamples concerned availability across multiple
pre-window observations and primary aggregation across mixed full/sparse last
objects. Both reproduced before correction. Reasoning availability now follows
the trusted chain. Missing primary increments are reconstructed from continuous
cumulative snapshots while reported full deltas retain their validation. A first
unanchored last constrains its cumulative reasoning within output bounds. A
related sparse upper-bound defect found by the enlarged oracle also reproduced
before correction. Two earlier omitted-delta controls now assert their fully
reconstructible total360/reasoning40; contradictory full reports remain negative.
The 95 focal methods passed. Retained matrices include 38,848 reporting-window
histories, 6,240 multi-observation-prefix histories, 2,800 projection cases and
the preceding 3,456 mixed histories. Independent references matched 547,200
window histories and 118,560 valid-prefix histories. The first prefix-oracle
attempt remains diagnostic because it included malformed full deltas in a
valid-prefix domain. The revised domain excludes those deltas, which retain
their separate dated-reset controls. Runtime changes add 31 lines and remove
5 without a dependency. Native integration passed 925 tests without skips in
184.260 seconds and 54 JavaScript tests. Final documentation, manifest,
distribution, remote checks and newly authorized review remain separate gates.
The frozen functional backtest and earlier results retain their original bytes
and source identities.

Candidate `bee4188976b6e5745c5ec815cf88b58d4492900d` received FIX FIRST
in its single authorized consolidated review. Its two preceding fixes were
recognized. Six pre-existing defects were reproduced in six methods with
13 assertion failures. The current joint correction preserves primary triples
through optional scalar corruption, separates duplicate consumption from
physical evidence, validates reasoning subset complements and retains optional
enrichment. Per-observation aggregation preserves known subtotals across resets.
Unreported reasoning remains unavailable through summaries and snapshots;
complete Codex output pricing can proceed when that optional field was never
reported. The additive `reasoning_output_tokens_available` field preserves that
distinction through normalized usage validation. Empty observations remain
unavailable. A prior sparse-reasoning control implied only a range, rather than
an exact measurement. Its original inputs now retain incompleteness beside
full-context positive controls. Existing window matrices also assert reasoning
availability when no reasoning field was seen. Eight boundary methods include
a retained 546-case independent subset matrix. References matched 547,200
window histories, 118,560 prefixes and 99,930 representation-boundary histories,
including duplicate consumption and enriched prefixes. Runtime changes add
109 lines and remove 67 in one file, without a dependency. Native integration
passed 933 tests without skips in 202.837 seconds and 54 JavaScript tests.
SHA-256 identities for 116 code/test/workflow files matched before and after
the native run. Final documents, manifest, distribution, remote checks and a
newly authorized independent review remain separate gates. Earlier results
and their source identities are preserved. No new causal ROI claim follows.

The local candidate `1e81c7d9f98861091e223b9bd2d522769230a683` passed its
recorded checks before a compatibility audit found an introduced empty-window
regression. Histories containing only unusable old counters could appear as
complete zero consumption. Four cases reproduced in RED, with a readable
baseline retained as a positive control. The correction requires a readable
primary snapshot before an empty window can qualify. The new source passed
933 native tests without skips in 186.860 seconds. The 116 code/test/workflow
identities matched before and after execution. References were executed again
and matched all 765,690 cases in their declared domains. JavaScript 54 and
post-document contracts are checked separately. Relative to bee4188, runtime
changes add 110 lines and remove 67 in one file, within the 350-line budget.
The earlier source and its results remain preserved. Distribution, current-head
remote checks and a newly authorized independent review remain required.

The pre-version candidate `6aaff4456c47690260f296619ef6aa9defa1eb6f` passed
811 native Python tests without skips. Its exact push and pull-request CI each
passed five jobs, including installed-wheel checks. Hosted macOS skipped three
real Go tests because Go was absent there. The native macOS run exercised those
tests. Frontend bytes matched the earlier 50-test JavaScript qualification.

CodeQL completed Python and JavaScript analysis for that candidate with zero
reported alerts in its pull-request scope. This is the default query suite and
PR diff filtering. It is separate from the partial native Codex Security scan.
Scorecard execution awaits a supported event on the default branch. Its upstream
action uses a version-tagged Docker image as a transitive dependency.

The versioned candidate still requires its own exact checks. The source manifest
binds the complete tracked inventory. Main CI, annotated-tag CI, distribution
identity and independent review are recorded with the GitHub release under
`RELEASING.md` and the reviewer identity policy in `AGENTS.md`.

Independent review requires a fresh authorization bound to the sanitized context.
Previous single-use grants are consumed. A test or scan result does not grant
merge, publication, installation or account changes.

## Causal evidence

The engineering checks above do not measure causal ROI. No new causal result is
asserted by this candidate. The frozen experiment reports retain their original
scope, verdicts, model identities and economic coverage. The 5-point Codex pilot
depends on final mining and sensitivity controls, reconciled frozen inputs and
its separate conditional authorization. Confirmation needs its own grant.
