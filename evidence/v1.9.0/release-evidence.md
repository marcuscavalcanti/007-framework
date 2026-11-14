# 1.9.0 candidate: study F's scripts made native, and the open qualification items closed

Prepared on 2026-11-14 from published 1.8.1, after Claude study F (evidence on branch `claude/pilot-amendment-2`, commit
`ffe304c`).
- **Kind:** a minor release. Every new option is off by default, so a run or report without them behaves as in 1.8.1. No command,
  option or field is removed or renamed; `arm_accounting` gains `refused` and `replicates`, and the run manifest gains `toolchain`.
- **New stop reasons:** planned pauses `machine-busy` and `quota-hold`; `cost-marker-hold` (terminal), `looked` and
  `load-sensitive-oracle` (refusals before any dispatch).
- **Behaviour that changes without an option:** a Claude usage limit now pauses the run instead of spending the invalid budget; a
  Claude session reopened for a background task is valid instead of `ambiguous-session`; a snapshot's safe relative symbolic link
  is copied instead of refusing the cell; `sensitivity` repeats each control alone; more forms of a file argument and the grading
  toolchain are sealed, so a 1.8.1 run does not resume under 1.9.0 (as with every release since 1.8.0, the 007 scripts are sealed);
  the default `--jobs` is a quarter of the cores.

## Items under qualification

From `PLANO-1.9.0` (the maintainer's records), items 1 to 8 come from study F's amendment F-1, and items 9 to 16 from the 1.8.0
and 1.8.1 records ("Not in this release", "Limit, marked in the code", and the should-fix items the 1.8.1 review left open).

| # | Item | 1.9.0 | Test |
|---|---|---|---|
| 1 | A Claude usage limit read as `native-error` and spent the invalid budget | the error result's text and a rejected `rate_limit_event` read `native-error-rate-limit`; a zero-filled usage counts as none | the F-1 dry run's "usage limit reached" result, through the real runner, read by `refused()` |
| 2 | A refused cell was final and charged its reserve | `--requeue-refused`: set aside under `refused/`, dispatched again; charged its receipt cost (0.0 for Claude) | 4 refusals, `--jobs` 1 and 2, all 8 cells valid, ledger unambiguous |
| 3 | One cell above `--stop-usd` ended the run | `--over-limit record` | a US$25 cell with a US$20 brake and a US$400 cap |
| 4 | `ambiguous-session` of unknown cause | cause found in F's retained stream; a reopened session after a background task's notification is one session; `--stream-copy` | the F stream's shape; four shapes that stay ambiguous; stream copy hash equals `source_sha256` |
| 5 | The account's quota was not read before dispatch | `--quota-gate` with the set's `quota_probe` | the eight cases of F-1 dry-run scenario E; a real probe command |
| 6 | External load moved grades | `--max-load`, `load.log` | a loaded machine pauses, an idle one runs |
| 7 | Resume, lock and single look were scripts | `--chunk`, `--cost-marker-at`, `report --single-look` | chunks never overlap; the marker reads exactly its first cells, once; nothing runs or reads after `LOOK.json` |
| 8 | The missing-data guard was a script | `report --missing-data-guard`, `--frozen-reach`, `compare.critical_floor` | synthetic PAYS, not-decisive and KILL cases; validation below |
| 9 | Refused counts were not per arm | `refused_per_arm`, `arm_accounting.refused` | refusals on one arm only |
| 10 | Untested branches | the usage guard, `--jobs` > 1 with refusals, both `_controller_failure` branches, real receipts, cooldown anchor (N3), label-only exemption (N4) | one test each |
| 11 | Controller errors gave a message only | `controller_error` with type, message and innermost frame | a raising cell |
| 12 | A load-sensitive oracle (yaegi) | serial repeat of each control; `load_sensitive`; `run` refuses such a set | a control that passes in parallel and fails alone |
| 13 | Symlinked snapshots were refused (klauspost/compress) | safe relative links materialized as copies | internal, chained and directory links; absolute, escaping, self-containing, dangling and cyclic links refused |
| 14 | `--jobs` oversubscription (Amendment 7) | warning above a quarter of the cores, `--strict-jobs` refuses | an 8-core machine |
| 15 | The oracle's toolchain was not sealed | `toolchain` in the manifest | a version change between start and resume |
| 16 | The explicit-environment effect, a 2×2 on yaegi | not code: a paid Codex measurement | pending Codex quota and the maintainer's go |

Also closed from the 1.8.1 review: item 6's unsealed argument forms (`KEY=/f`, `--flag=key=/f`, `-f/f`, `@/f`).

## Validation of the missing-data guard on published results

`missing_data_guard` with study F's frozen reach, margin 0.20, floor 2.2315 and 100,000 simulation draws:
- **2026-11-07 Claude go-json run:** L0 statistic 4.666643 against 2.2315 (P) and 2.2367 (B), PROVEN; L2 (one invalid cell
  imputed) statistic 4.0385, mean −0.0675 (−0.1338 to −0.0012), PROVEN; R 0.300 (0.267 to 0.344). These are the numbers
  amendment F-1 recorded for `analyze_f.py`. L2's own simulated critical value is 2.2014 where one F-1 record gives 2.1793; the
  floor, 2.2315, decides either way.
- **Study F:** statistic 10.841 against 2.2788 (P) and 2.2866 (B); L2 critical 2.2702; R 0.2633 (0.2244 to 0.3130) and worst case
  0.2676 (0.2290 to 0.3169) at 10,000 bootstrap draws: equal to `f-result.json` in every digit printed.

## Engineering evidence

- **Local suite on the candidate:** to be filled from the final run.
- **CI:** to be filled.
- **Independent review:** to be filled (Claude Fable 5.2, `high` requested, same family as the implementer by the maintainer's
  policy).

## Not in this release

- Item 16, the 2×2 on yaegi: a paid measurement, not code.
- The serial re-grade and the A/A check stay study scripts; the guard says they are not part of it.
