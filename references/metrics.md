# Metrics

The north-star family measures whether agent output survives use:

- **reliable first-pass rate** — accepted without a corrective agent round and
  still without a known escape after seven days;
- **corrective touch rate** — attributable agent lines later changed to correct
  behavior, ideally measured over 7 and 30 days;
- **repair rounds** — attempts after the first implementation;
- **escape rate** — accepted changes that later produce a regression or incident;
- **cost per reliable outcome** — all measured terminal cost, including failed
  and blocked attempts, divided by reliable first-pass outcomes;
- **reliable outcomes per USD** — the reciprocal ROI view, available only when
  the complete start/terminal cohort has accounted cost on one USD basis;
- **wall time per reliable outcome** — all measured attempt time, including
  failed work, divided by reliable first-pass outcomes;
- **observation coverage** — task starts with a matching terminal receipt;
- **cost coverage** — terminal outcomes with numeric cost, source, and
  final/provisional accounting status.

Rules:

1. Missing attribution or telemetry is `N/A`, never zero.
2. Separate corrective edits from feature evolution when the data permits.
3. Report medians and distributions; tiny samples are not trends.
4. Tokens and wall time are costs, not quality proxies.
5. Similarity to a prior patch is not correctness.
6. Cost coverage is a hard gate: below 100%, the operational state cannot be
   `on-target`. Missing cost is unaccounted, never zero. Observation gaps remain
   visible as active or unclosed tasks, not automatic quality failures.
7. Group cost by the served provider/model/effort when measured; otherwise keep
   the requested route explicitly marked as unverified.
8. Operational dashboard metrics are observational. Causal claims require a
   separately frozen OLD×NEW experiment with identical tasks and acceptance.
9. Local-session USD may use Headroom/LiteLLM or another rate card as a
   diagnostic estimate. Only normalized terminal receipts close the operational
   cost gate; unresolved models remain `N/A`.

Codex logs larger than the 4 MiB read window retain observed tail counters as
partial usage, never a complete period or a pricing input. The dashboard marks
affected per-project and aggregate token counts as partial. Small complete
sessions keep the previous behavior; no cursor or full-session reread is added.

## Common cohort accounting

`harness_report.summarize_economics` is the shared report, dashboard and selector
calculation. Freeze the supplied receipts, matching starts, follow-ups and aware
`as_of` timestamp to reproduce it. The output is `supplied-declarations`, not
producer authentication, causal benefit or billed ROI. Historical descriptive
counters remain available; their `legacy_cost_metric_scope` is not an economic
eligibility signal. The accepted-only legacy mean does not include failed work.

USD bases are `api-equivalent`, `subscription-allocated`, `billed` and
`local-compute`. An unambiguous rate-card source maps to API-equivalent; a
provider-reported USD number alone does not establish billing. Retain the actual
model, rate-table/version and usage classes with an estimate when available;
unknown pricing provenance remains a qualification gap, never a fabricated table.
Do not combine these bases or different projects into one eligible ratio.

Open starts, unbound terminals, duplicate identities, missing timestamps/costs or
contradictory repair claims block comparable ratios. Child costs count once only
when the parent explicitly includes them on the same basis and does not understate
their subtotal. Wall-time inclusion is not inferred from inclusive USD scope.
Seven-day receipt age and a bare `escape_7d: no` do not establish follow-up.
A linked observation needs matching project/task/candidate, source hash, actual-use
timestamp and a complete observation interval at the cutoff. These remain supplied
claims until source validation outside this arithmetic boundary qualifies them.

The dashboard separates project economics and requires cohort, basis and linked
follow-ups for operational readiness. Route quality counts blocked roots as known
unsuccessful outcomes; legacy accepted-only follow-up rates remain descriptive.
No equivalent-cost ratio alone proves saved dollars, accuracy or population ROI.

The optional `cost_components_usd` scope in [receipts](receipt-schema.md#declared-cost-scope-optional-v1-compatible)
distinguishes an accounted amount from declared coverage of the harness overhead.
`cost_component_known_tasks` reports coverage per category on the selected USD
basis; `cost_scope_reasons` explains missing or inconsistent portions. Complete
scope also requires a complete priced cohort. Legacy scalar sums and ratios keep
their descriptive meaning. The new `*_with_overhead*` ratios are available only
when every root has all six disjoint portions reconciling to its total.
The dashboard's readiness and measured route selection require that scope;
old declarations are not retroactively upgraded. Full declared scope still does
not authenticate the source or prove causal savings. Shared/public corpus bytes
and the legacy semantic projection remain unchanged; scope is tested separately.

New starts and terminal records include marker project identity. Legacy files
without that field are scoped in memory to their validated containing project;
an explicit foreign identity rejects. Original bytes are never rewritten and
marker scoping is contract coherence, not producer authentication. Failed reads
block comparable ratios while preserving known declarations. Financial values
retain decision precision; presentation alone may round them. Decimal-inclusive
subtotals and rejected duplicate cohorts are independent of input ordering.

`scripts/touch_rate.py` is an approximation based on attributable Git commits.
Renames, deletion, formatting, and mixed-author commits can distort it; use the
trend with receipts and incident data.

Dashboard polling is single-flight every two seconds, with a ten-second browser
request deadline. Failed, malformed or regressing snapshots preserve the last
valid observations with stale labels, no current approval and no final economic
ratios; filters and keyboard focus survive recovery. The server rejects concurrent
snapshot collection with 503 while health/static routes remain available. Client
abort does not stop a slow collector; a legitimate source clock correction can
also cause conservative stale status until a non-regressing snapshot arrives.
