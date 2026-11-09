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
