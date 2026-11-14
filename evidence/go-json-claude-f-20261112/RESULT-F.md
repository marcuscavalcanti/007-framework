# Study F result: Claude Opus 5.5 `medium` against `xhigh` on go-json (2026-11-14)

Pre-registration: [PREREG-F.md](PREREG-F.md), commit `100aa36` (the pre-registration) and `6d73c0a` (the full settings hash and
the `xhigh` arm in R), both 2026-11-12T21:41Z, before F's first attempt at 2026-11-13T22:41:21Z. Amended by
[AMENDMENT-F1.md](AMENDMENT-F1.md) before any attempt. Code: the published 007 1.8.1 distribution, commit `f05ebcbc`, pinned by
manifest hash. One run, one look.

## Answer

**Study F: PAYS.**

On 41 commits of go-json-experiment/json, with 2 fresh attempts per commit and arm (163 of 164 cells valid), Claude Opus 5.5
requested at `medium` passed the frozen reachable tests within the pre-registered 20-point margin of `xhigh` (difference +0.8
points, 95% interval −3.0 to +4.7), and its client-estimated cost per accepted change was 0.26 of `xhigh`'s (0.22 to 0.31; worst
case 0.27, 0.23 to 0.32): pre-registration F, as amended by F-1, reads PAYS. Whole-change acceptance was 56 of 82 at `medium` and
61 of 81 at `xhigh`, so PAYS means a lower cost per accepted change, not the same changes. The question, its margin and the
repository were chosen after an exploratory run on the same commits whose pre-registered 10-point test read NOT-PROVEN (−5.5
points, −11.8 to +0.7), and the study ran after its provider probe failed. It covers one public repository the model may have
seen, one model, effort as requested, and costs estimated by the client on a subscription account.

**DECISIONS part 6 (revision 2): YES**, for this executor on this repository. T1 was read on F's own cells under
[PROGRAM.md](../PROGRAM.md), and its third bullet was completed after the look by a step that could only demote the result (see
Instrument). Answer A (part 5): NO-STOPPED, from the closed Codex 5-point pilot, whose cells are never read (PROGRAM.md). F does not
compute it, because F has no 5-point confirmatory look.

This result does not say that `medium` is as good as `xhigh`, loses nothing, or is the better choice; anything about other
repositories, private code, other models or other effort pairs; that 74% of the money was saved; that the margin was fixed blind;
that the result holds at 10 or 5 points; that the A/A or the instrument was validated on this run or on Claude attempts; or that it
was independently reproduced.

## Numbers

| Item | Value |
|---|---|
| Cells | 164 planned, 163 valid, 0 refused, 1 invalid (`xhigh`) |
| Spend (client estimate) | US$295.18 of a US$400 cap; the cost marker at 40 cells projected US$282 |
| Reach difference, `medium` − `xhigh` | +0.0085 (95% CI −0.030 to +0.047), readings P and B |
| Statistic against critical value | 10.84 against 2.279 (P) and 2.287 (B); floor 2.2315 |
| Missing-data guard (L2 from the plan) | PROVEN in P and B, critical value 2.270 |
| R, cost per accepted change | 0.263 (0.224 to 0.313); worst case 0.268 (0.229 to 0.317) |
| Acceptance | `medium` 56/82, `xhigh` 61/81 |
| Mean cost per cell | `medium` US$0.70, `xhigh` US$2.90 |

## Instrument (T1, DECISIONS part 6)

| Check | Result |
|---|---|
| Serial re-grade, evaluator embedded in the tasks (`362f40c7…`) | 1 of 163 cells disagrees (0.61%, limit 2%) |
| A/A | 3.55%, inside 3% to 8%. This is the standing check on the Codex top-up's `high` cells, known before the run (GO-3 L4); it says nothing about F's cells or Claude attempts |
| Serial freeze | F has no freeze. Its function, the same decision from serial grades, is read in the next row: PROVEN and PAYS at 10.62 |
| Robustness re-grade 1: F's analysis on the embedded serial re-grade | PROVEN in P, B and L2; PAYS (mean +0.0075, statistic 10.62) |
| Robustness re-grade 2: serial re-grade with the pinned evaluator (`lab_accept.py` `85c452c1…`, the hash PREREG-CONFIRM names), analysed | 1 of 163 disagrees, the same cell and test; PROVEN in P, B and L2; PAYS (statistic 10.62) |
| 60% exclusion check | go-json is flagged `below_60: false` in `pilot-gate.json`, so nothing is excluded and the look is unchanged. In a one-repository study this check cannot bite |

The independent review (Claude Fable 5.2, maximum effort, no tools) found T1's third bullet required and not decidable from the
record. T1 was then completed after the look, with the result known, by a step that could only demote it: no model, and the hashed
`regrade_f.py` and `analyze_f.py`, unchanged. It was declared only in the maintainer's session record, immediately before the step;
this file is its first public record. On 2026-11-14 between 10:14 and 10:29Z, F's analysis was run on the run's own embedded serial
re-grade, the pinned-evaluator re-grade (`--evaluator pinned`) was run and analysed, and the 60% check was read from
`pilot-gate.json`. The commands were:

```
python3 -I -B analyze_f.py serial robustness/embedded-serial-result.json
python3 -I -B regrade_f.py f-set.json results serial-pinned frozen-reach.json --evaluator pinned
python3 -I -B analyze_f.py serial-pinned robustness/pinned-serial-result.json
```

Neither serial re-grade ran on a quiet machine. During the run's own embedded re-grade (09:36:50 to 09:51:49Z), the 5-minute load
had a median of 13.0 and a maximum of 15.2 over 15 samples. During the pinned re-grade it rose from 2.3 to 14.3, and the 15-minute
load from 4.0 to 11.4, so it was near 15 for most of it. Both are above the dispatch gate's limit of 8, and both depart from the
quiet-machine condition of Amendment 5 (c). The cause is not recorded: `load.log` stopped with the run, and it records load
averages only. The outcome did not differ: each re-grade agrees with the original grading on 162 of 163 cells, and the two
analyses are identical.

The discordant cell is `GJ-540F0144-r02-medium`. The one test that changed,
`TestMarshal/Maps/String/Deterministic+AllowInvalidUTF8+AllowDuplicateNames`, passed in the run's grading and failed in both serial
re-grades. The cell was not accepted in any of the three, so acceptance and R are unchanged; the reach mean fell by 1/984.

## Run record

- **Dispatch.** F was parked at 21:37:30Z on 2026-11-13 after the maintainer's "Fable 5.2 para tudo" (Fable 5.2 for everything); the launcher logged "F (Opus) estacionado" (F parked). The go that lifted the stop was
  "Pago o reset agora: F hoje" (I pay the reset now: F today), at 21:56:25Z. The launcher polled again from 22:04Z and read the
  seven-day window at 0.98 up to 22:34:39Z. At 22:40:59Z the maintainer wrote "opus voltou a ter quota" (Opus has quota again). A
  poll 22 seconds later came from a new launcher instance started by the coordinating session after that message; it read 0.01,
  and F started at 22:41:21Z.
- **Load.** The gate (5-minute load under 8) is checked only between 20-cell chunks. It held chunk 2 for 20 minutes and chunk 3 for
  5. Over the whole of `run_f.sh`, 671 one-minute samples that include both gate waits and the final serial re-grade, the 5-minute
  load had a median of 5.35, a 90th percentile of 10.0 and a maximum of 23.7.
- **Account.** The seven-day window rose 23 points over the first US$145 and 7 over the next US$145. The record does not attribute
  the difference. Other use of the same account early in the run is the likely cause; the coordinating session is a candidate. This
  departs from the reservation recorded in GO-3.
- **Timeouts.** None. The longest agent session was 566 s at `medium` and 1,762 s at `xhigh`, against a 3,600 s limit.
- **The invalid cell.** `GJ-F5A63B5F-r02-xhigh`: the runner receipt's problem is `ambiguous-session` and `f-result.json` labels it
  `runner-invalid`; US$2.45; its stream is retained in the maintainer's records. The task's other three cells were accepted, so they
  pass every reach test: the worst-case imputation (`xhigh` passes every reach test) equals the observed `xhigh` value, and P and B
  coincide because both `medium` attempts score the same. L2 equals L0 in mean, interval and statistic; its critical value differs
  because the simulation pool changed.
- **Hashes.** The pre-registration ledger, published here as `SHA256SUMS.prereg` (byte-identical to the `SHA256SUMS` that
  AMENDMENT-F1 and GO-3 name), hashes to `12a77915…`, the value GO-3 records. Every file in it verified at 2026-11-14T10:43:59Z, after
  the robustness step.

## Errata (hashed files are not edited)

- `regrade_f.py` and `aa_f.py` docstrings name v1.7.0, `regrade_serial.py` and the pilot's 5-point constants; the code loads 1.8.1.
- `analyze_f.py` would label an A/A failure NO-INSTRUMENT where DECISIONS part 6 says NO-AA; it did not apply.
- `analyze_f.py`'s base R charges a cell with no cost US$10 while the runner reserves US$20; no such cell occurred.
- The two robustness outputs are computed on the re-graded directories, which hold only the 163 valid cells. They therefore report
  163 cells, no invalid cell, R = 0.266 without the invalid cell's US$2.45, and a `cost_ratio_worst` equal to `cost_ratio`. The
  worst case that stands is the original's: 0.268 (0.229 to 0.317).

## Review

Claude Fable 5.2 at maximum effort, as part 6 requires (same model family as the implementer, by the maintainer's policy). The
reviewer had no tools: it recomputed no hash, cell or simulation, and checked the excerpts it was given against each other. Round 1:
CONFIRMED WITH CORRECTIONS, PAYS standing as computed, part 6's YES undecidable until T1's third bullet was settled. Round 2, after
the completion: third bullet met by the letter of PREREG-CONFIRM and Amendment 5 (e); part 6 YES; SHIP with seven changes, made
here. Round 2 named four gaps: the 60% check cannot bite in a one-repository study, the pinned re-grade ran under load, the evidence
that the pinned evaluator ran is the output's label and the code path, and the completion came after the look. Both rounds are in
the maintainer's records (`revisao-f-resultado-20261114`, `revisao-f-resultado-r2-20261114`).

## Files

| File | Content |
|---|---|
| `f-result.json` | the single look |
| `aa.json` | the A/A check |
| `serial-regrade.json`, `serial-pinned-regrade.json` | the two serial re-grades, per-cell detail omitted |
| `robustness/embedded-serial-result.json`, `robustness/pinned-serial-result.json` | F's analysis on each re-grade |
| `robustness/log.jsonl` | start and exit times and load of the robustness step |
| `robustness/timeouts-and-f5a.txt` | agent time, exit codes and failure classes by arm; the four cells of `GJ-F5A63B5F` |
| `robustness/cells.csv` | per cell: validity, failure class, acceptance, client-estimated cost, agent time |
| `descriptive-after-look.json` | per arm, computed after the look with the pinned `load_cells` and `cost_of`: cells, valid, accepted, total, mean and median cost |
| `run.log` (`6c90ecc2…`), `load.log` (`9c4b59d2…`), `autolaunch.log` (`8177df99…`) | the run, its one-minute load averages and the launcher |
| `pilot-gate.json` | the 60% flag (copy of `smoke-a3-20261112/pilot-gate.json`) |
| `SHA256SUMS.prereg` | the pre-registration ledger. Four files it names hold local paths and stay in the maintainer's records (`f-set.json`, `f1.json`, `quota_f.py`, `bin/claude`); every other file it names is here and verifies |
| `frozen-reach.json`, `dryrun/dry-run.json` | the frozen reach set and the PREREG dry run, as the ledger hashes them |
