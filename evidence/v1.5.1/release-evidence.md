# 1.5.1 candidate evidence

Owner: Codex coordinator. Status: local working candidate, not published.
Base: `36dc86576af0cdf2c49d740a1f6be201c1cf52b1`.
Scope: backward-compatible dashboard reporting, tests and sanitized evidence.
No new dependency, receipt schema, model call, database or scheduler.

## Deterministic causal mechanism

Question: does a controller-bound executable acceptance contract prevent false
approval while retaining correct controls and abstaining when verification is
unavailable? OLD and NEW use the same candidate, deterministic executor, receipt,
runtime and independent post-run grader. Only NEW binds the acceptance contract.
The grader is independent of the executor's claimed success, not an external
reviewer or a separate institutional author.

Two fixtures derive from inspected historical engineering corrections:

- MoneyMouse `95b92926d6019392f31670f5deee20eabfa7411d`: required-field
  presence in eligible early-return rows, not financial correctness.
- Coliseum `e4b6dea61f3d3b7307abc6f19b3ea53d22852e5b`: duplicate-key
  rejection, not the complete evidence schema.

These are sanitized structural subsets, not private-project replays. Raw
financial/customer data, credentials and session transcripts are not packaged.
The final [protocol](protocol-r3.json) freezes seed 5151, three reproductions,
zero retries, and a stop rule that any invalid required cell is inconclusive.
The [observed result](result-r3.json) has 36 cells, zero invalid and no observed
source drift; local runtime is Darwin/Python 3.14.7.

| Frozen condition | OLD | NEW |
| --- | --- | --- |
| Defective candidate | 6 accepted, exit 0 | 6 blocked, exit 4 |
| Correct positive control | 6 accepted, exit 0 | 6 accepted, exit 0 |
| Verifier unavailable | 6 accepted, exit 0 | 6 persisted open starts, exit 2 |

There are **two independent cases**, not 36 independent tasks. Deterministic
repetitions establish classification reproducibility. No model was called; USD,
model generation quality, longitudinal rework and D7/D30 are not measured.
The supported conclusion is the admission fence's behavior in these frozen
cases, not universal review accuracy or resistance to same-user file tampering.

## Preserved failed preparation

The first [protocol/result](result.json) and the second [protocol/result](result-r2.json)
are inconclusive, not deleted or relabeled as successful. The deterministic
executor first emitted unavailable-cost fields outside the existing contract,
then used null telemetry where the contract requires `unmeasured`. Their runner
revisions remain beside the results. Revision 3 repairs the synthetic executor
and validates the verdict matrix independently of the protocol, persisted
starts, acceptance-contract binding and pre/post source hashes.

## Reproduce without a provider

From a full Git checkout, choose a new output pathname (no replacement):

```bash
python3 evidence/v1.5.1/run_acceptance_experiment.py --out /absolute/new-result.json
python3 -m unittest discover -s tests -v
node --test tests/dashboard_reporting.test.cjs
```

The experiment creates isolated temporary repositories and a temporary registry;
it does not register or alter the user's projects. Process timing and output
digests may differ; the frozen classifications, candidate pins and validity are
the reproducibility criteria. The local result binds these source hashes:

- runner: `28eec06cd4f335b7d0b16bd36645b9ea2c078158efb2f62be6eedb6a2a65d943`;
- CLI: `4ef2e3dacc60e17eac911a31a9e2e209a4f242535a6b04c6b10c82ff1e17d7d7`;
- receipt example: `cc5217d9a57f2cab2a1bf6823aa7935a76a6ed2735d1b86c2f8572ac9c5295b3`.

## Dashboard verification and boundaries

The first view emphasizes delivery, measured repairs, terminal USD and unresolved
starts. It distinguishes declared acceptance from controller-observed checks,
declared D7 follow-up from durability, and provisional/final cost provenance.
The historical global effort comparison is explicitly not “with/without 007”
and not the selected project's gain. Incomplete identity stays incomplete.

Local DOM and screenshots were inspected on desktop and 390×844 mobile; mobile
had no horizontal page overflow. Project navigation retained the historical
scope warning. Preview uses only local assets and remains loopback-only.
Headroom inspired the hierarchy of cards/comparisons; no assets/code copied.

For the layout regression, test browser viewport widths 390, 620, 621, 640, 760,
900, 901, 1024, 1259, 1260, 1261, 1280 and 1440 at height 844, load the
populated historical comparison, and run this read-only check in DevTools. It
checks the inner grid and panel, not only the page scrollbar:

```javascript
(() => {
  const grid = document.querySelector(".causal-grid");
  if (!grid) throw new Error("Load the dashboard comparison");
  const values = [...grid.querySelectorAll("strong")].map(node => node.textContent);
  if (values.length !== 4 || values.some(value => value.includes("N/D"))) {
    throw new Error("Load the populated historical comparison");
  }
  const widths = [grid, grid.closest("section"), document.documentElement].map(node => ({
    client: node.clientWidth, scroll: node.scrollWidth,
  }));
  const valueWidths = [...grid.querySelectorAll("strong")].map(node => ({
    client: node.clientWidth, scroll: node.scrollWidth,
  }));
  if ([...widths, ...valueWidths].some(({client, scroll}) => scroll > client)) {
    throw new Error(`Horizontal overflow: ${JSON.stringify(widths)}`);
  }
  return {viewport: window.innerWidth, values, widths};
})();
```

This check failed before the mobile fix: grid client/scroll was 240/277 px and
panel client/scroll 349/363 px, despite a page width of 375/375 px. A one-line
mobile CSS correction uses one column; the same populated check then returned
240/240, 349/349 and 375/375 px. The temporary viewport was reset. The earlier
page-scrollbar inspection alone had missed the internal overflow. The prior
frozen source and manifest are preserved separately; that review's approval
does not cover this new CSS/report delta.

The subsequent bounded review correction removes the unconditional overview
claim: the static and runtime title now describe delivery, rework and cost as
questions for the evidence. A no-outcome renderer regression failed on the
previous promise and passes on the descriptive title. The renderer now has six
passing checks.

The same populated DOM check exposed an intermediate breakpoint gap at 640px:
grid 474/503 px and panel 583/589 px, although the page was 625/625 px.
One rule in the existing 900px breakpoint uses two columns; the 620px
single-column rule remains. After the change, all observed client/scroll pairs
match:

| Viewport width | Grid | Panel | Page |
| --- | --- | --- | --- |
| 390 px | 240/240 | 349/349 | 375/375 |
| 640 px | 474/474 | 583/583 | 625/625 |
| 760 px | 594/594 | 703/703 | 745/745 |
| 1280 px | 819/819 | 928/928 | 1265/1265 |

The next focal counterproof reproduced an overflow immediately above the 900px
breakpoint: at 901px the 238px sidebar returns, leaving a 491px grid whose four
min-content tracks plus gaps need 503px. The page itself was 886/886px. The
same actual-DOM assertion failed before the correction and passed afterward.
The only product change moves the existing two-column rule from the 900px
block to the existing 1260px block. At <=620px the grid still has one column;
at 621–1260px it has two; above 1260px it has four. No new rule/dependency.

With all four historical values populated, the grid, panel and numeric value
contents passed at 320,390,620,621,640,760,900,901,1024,1259,1260,1261,1280,1440px.
The whole-page assertion passed at 13 of those 14 widths. At 901px the corrected
grid is 491/491px, panel600/600px and page886/886px. Temporary viewport reset.

The 320px whole-page result is explicitly not PASS: client305px/scroll320px
with a classic 15px scrollbar. The unchanged, base-present body min-width320px
sets the layout's content floor. At the 335px positive control the client,
scroll and body widths all equal320px. This inherited minimum-width limit was
not changed by this bounded correction; the 320px grid and values themselves
fit. These observations do not establish every viewport, zoom or browser.

The existing 36 causal cells remain immutable: no replay, added sample or model
call. NEW acceptance and the post-run grader share grade(); independence is
from executor declarations, not an independently implemented oracle.

After the one-rule boundary correction the host suite passed155 tests in
25.668s, zero skips; all six existing renderer checks passed. No Python or
JavaScript product source changed. Exact-copy checks and Linux CI remain
separate gates; these local results do not establish publication.

Assertions require populated values, not a still-loading N/D panel; the viewport
was reset. After these two corrections, 155 host tests passed in 21.974 s and
155 tests in a fresh full-history source copy passed in 22.294 s, with zero
skips. Python compilation, JavaScript syntax and whitespace checks passed.
The three recorded causal source pins and protocol still match; no causal cell
was rerun or added. Prior exact freezes remain preserved. Previous external
approvals do not cover the corrected bytes; CI/publication gates remain open.

Earlier local checks (before the six-check headline regression):

- integrated suite after review fixes: 155 tests passed, 22.389 s;
- full-history clean-source copy including the actual modified/new files:
  155 tests passed, 22.059 s, with no skipped historical-release checks;
- renderer: 5 tests passed, including a failing-then-passing follow-up label
  regression; Python compilation, JavaScript syntax and diff whitespace passed;
- after the mobile correction: 155 tests passed in 22.051 s on the host;
  the sandbox run had one `PermissionError` in
  `test_server_exposes_only_allowlisted_routes` at the loopback bind;
  5 renderer checks passed with zero skips. This permission failure was not
  hidden or attributed to the CSS change;
- Gitleaks scanned the public-file copy with redacted output:
  no leaks found. This is a bounded scanner result, not a privacy guarantee;
- the final mobile DOM had no horizontal page overflow and the temporary
  viewport override was reset. Assets are local; project navigation preserved
  the global historical-comparison warning.

The tests ran locally on Darwin/Python 3.14.7; they do not establish compatibility
on the supported Linux CI matrix. Older manifests remain byte-identical,
including v1.5.0 SHA-256
`7e5d9f009939c252a5cfe6ab667931bacda7618f7e81e16cd73e970497367951`.

## Internal review reconciliation

The internal read-only reviewer identified two material reporting defects:
zero passing/failing checks could be called controller-observed in the ledger,
and per-route USD lacked the source/state shown in the aggregate. Both were
reproduced with failing regressions and corrected before the final 155-test
suite. The sanitizer now requires nonempty observed checks and successful
acceptance for accepted receipts, while preserving observed failed checks on
blocked outcomes. Route/project aggregation and the renderer retain accounting
origin and provisional/final state, including mixed-source routes.
Internal review is not external approval or publication authority.

## Release gates still open

The [local candidate manifest](manifest.sha256) excludes only itself. It binds
working candidate bytes, not an approved commit/tag. Authorized independent review,
exact-commit CI on Python 3.11/3.12/3.13, clean
commit, explicit publication authority, tag/artifact read-back and local install
rollback must be recorded before calling this a published stable 1.5.1.
Older manifests and evidence remain immutable. Local proof is not remote CI.
