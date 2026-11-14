# 1.9.0 candidate: study F's scripts made native, and the open qualification items closed

Prepared on 2026-11-14 from published 1.8.1, after Claude study F (evidence on branch `claude/pilot-amendment-2`, commit
`ffe304c4e209c4e30bb9feaebf55956eb243855f`).
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
  amendment F-1 recorded for `analyze_f.py`. L2's own simulated critical value is 2.2014, the value the hashed `analyze_f.py`
  gives on the same results (run again on 2026-11-14 to check); the 2.1793 in the first F-1 review's prompt came from a
  superseded draft of that script. The floor, 2.2315, decides either way.
- **Study F:** statistic 10.841 against 2.2788 (P) and 2.2866 (B); L2 critical 2.2702; R 0.2633 (0.2244 to 0.3130) and worst case
  0.2676 (0.2290 to 0.3169) at 10,000 bootstrap draws: equal to `f-result.json` in every digit printed.

The validation script is `validate_guard.py` beside this record. Its inputs (the cells of both runs) are in the maintainer's
records, not in this repository; study F's published `f-result.json` is on branch `claude/pilot-amendment-2`.

## Engineering evidence

- **Local suite:** after the round-1 fixes, 1,014 Python tests and 54 JavaScript tests passed on a tree left unchanged during the
  run (macOS, Python 3.14.7). A first full run failed one version test because the tree was edited while it ran; it was run
  again on a frozen tree.
- **CI:** to be filled.
- **Independent review** (Claude Fable 5.2, `high` requested, no tools, same family as the implementer by the maintainer's
  policy), round 1 on `cd2d2b2`, US$4.02: FIX FIRST with three blockers and one check.
  - **C1** (`reach=` passed to functions the diff does not show): their 1.8.1 definitions already take `reach`, and the suite
    ran (1,009 tests) before the review.
  - **B1** (a cell above `--stop-usd` lost its final stop when a pause was set first in the same pass, a regression with the
    options off): the stop now outranks planned pauses; tested with a refusal followed by a US$25 cell, with and without
    `--rate-limit-wait-s`.
  - **B2** (the guard inferred the plan from the replicates reached): `--replicates` is required with the guard, and fewer than
    the cells reached is refused; tested through `report()`.
  - **B3** (quota probes spent outside `spent`): the probe's cost is read from its result row, logged in `quota.jsonl` and
    charged, on resume too; a probe without a cost is counted.
  - **Should-fix done:** S1 (a directory link copied before the links inside it), S2 (the single look takes the run lock, and a
    run checks `LOOK.json` before each chunk), S3 (`--rate-limit-wait-s` needs `--requeue-refused`), S4 (a manifest without
    `toolchain`), S5 (documented: the floor applies to the guard only; the reach file's digest is recorded; tasks with no valid
    cell), S6 (the error message follows `retain_diagnostic_text`), S7 (the fake agent's delay no longer patched away; tests
    through `report()`, the `LOOK.json` writer, `--frozen-reach`, `critical_floor`, and a requeue through the real
    `execute_cell` and runner), S8 (this record and the changelog).
  - **1.8.1 review items also closed here:** item 3's printed flag (`refused_unequal`), item 5 (`chain` over a refused row,
    `report` over one), item 6's `--flag=@/file`, item 7/N2 (a CRLF patch under an operator's `core.autocrlf=true` and
    `apply.whitespace=fix`), the stream copy left empty when the receipt cannot be reserved, a quota probe validated before the
    seal, `--strict-jobs` on `run` as a usage error.
  - **Erratum to the 1.8.1 record (N1):** its line saying a refused call "costs nothing" is wrong: a refused cell is charged its
    receipt cost or the `--stop-usd` reserve. The 1.8.1 record is hashed in its tag and stays as published.

## Still open

- 1.8.1 review item 10: `except Exception` around one cell still catches every error a controller raises (a `KeyboardInterrupt`
  is not caught).
- A file argument naming two files seals only the first.
- `sensitivity.json` is not sealed, and the toolchain's `--version` runs outside the acceptance sandbox.

## Not in this release

- Item 16, the 2×2 on yaegi: a paid measurement, not code.
- The serial re-grade and the A/A check stay study scripts; the guard says they are not part of it.
