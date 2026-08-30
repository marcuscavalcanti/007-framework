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
- **observation coverage** — task starts with a matching terminal receipt;
- **cost coverage** — terminal outcomes with numeric cost, source, and
  final/provisional accounting status.

Rules:

1. Missing attribution or telemetry is `N/D`, never zero.
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
9. Local-session USD follows Headroom's LiteLLM pricing path. Full coverage may
   be shown as an estimate; partial coverage is a lower bound plus coverage;
   unresolved models remain `N/D`.

`scripts/touch_rate.py` is an approximation based on attributable Git commits.
Renames, deletion, formatting, and mixed-author commits can distort it; use the
trend with receipts and incident data.
