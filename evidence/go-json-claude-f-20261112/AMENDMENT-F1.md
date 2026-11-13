# Amendment F-1: the failed probe, a missing-data guard, quota and load gates, and stream retention (2026-11-13, before any F attempt)

Written after the probe failed. It is pushed with hashes before any attempt of study F. No F attempt has been dispatched.

## What happened
- **Probe.** The probe ran 3 real cells on go-json commits outside the 41, which do not count as evidence.
  - It failed: `GJ-1D040119-r01-xhigh` came back invalid (`runner-invalid`, problem `ambiguous-session`), after 3143 s and
    US$7.71. The other two cells were valid.
  - The cost projection fixed before the result was mean probe cost × 164. It gave US$492, above the US$400 cap.
- **The maintainer's go was conditional on both checks. It did not hold, and nothing was dispatched.**
- **The probe stays failed.** This amendment does not redefine what "passed" means for the probe or for the projection.

## Where the defect comes from
`ambiguous-session` is raised by the 1.8.1 telemetry parser. It fires on a second `system/init` in the Claude stream, or on an
`init` without a valid `session_id`, even when the `session_id` repeats. The cause is inferred, not observed, because the runner
does not keep the stream.

It has appeared in every Claude run:
- a private replay on 2026-11-04: 3 of 144 cells;
- go-json on 2026-11-07, the same 41 tasks: 1 of 164 cells, the longest `medium` cell;
- this probe: 1 of 3 cells.

Free forensics on the 311 receipts:
- no receipt field separates the 5 invalid cells from the 306 valid ones (wall time, cost, output, reasoning, cache reads and
  writes, each as a ratio to its arm's median);
- there was no rate-limit pause in the probe;
- no local transcript exists, because sessions run with `--no-session-persistence`.

## The decision
- **Second opinion.** An adversarial reviewer (Claude Fable 5.2, `xhigh`, no tools) recommended a hybrid:
  1. free forensics;
  2. a paid diagnostic that keeps the stream;
  3. this amendment, as a declared deviation;
  4. a new written go.
- **Maintainer's choice.** The maintainer chose the hybrid (`GO-2`).
- **Quota.** The account's seven-day usage window stood at 69% to 79% and overage was out of credits, while the study needs about
  half a window. The maintainer will pay a reset of the window when everything else is ready, instead of adding overage credit.
- **Conditional go.** The maintainer pre-authorised automatic dispatch (`GO-3-conditional.json`). It covers only the version of this
  amendment that passes its dry run, gets SHIP from the reviewer with no correction pending, and passes the quota and load gates.

## Diagnostic, not evidence
- **Run:** 2 cells of `GJ-1D040119` at `xhigh`, on the unchanged 1.8.1 distribution. The CLI was wrapped by a shim that copies
  its stdout to a file.
- **Retention marker: passed, 2 of 2.** Each copied stream has the same sha256 as the `source_sha256` of its receipt.
- **Classification, fixed before the data:**

  | Class | Definition | Consequence |
  |---|---|---|
  | D1 | Same `session_id` and one `result` | Proceed to this amendment |
  | D2 | Another `session_id`, an `init` without one, or more than one `result` | Proceed to this amendment |
  | D3 | Not reproduced | Proceed to this amendment |

  `GO-2` diverts to a product fix first only in two cases:
  - the rate-limit pause is the trigger;
  - the captured cause, applied to the 2026-11-07 receipts, marks 6 or more of 164 cells.
- **Result: D3.**
  - Both cells were valid, with one `init` and one `result` each.
  - Durations 1816 s and 1908 s; costs US$6.74 and US$7.40.
- **What the streams show.** Every Bash call emits `system/task_started` and `task_notification`. None was backgrounded, and all
  closed before the `result`.
- **Open hypothesis.** A background task that ends after the `result` may open a new turn, and with it a second `init`. It is
  untested.
- **Usage windows.** Every `rate_limit_event` seen on this account names one window, `seven_day`. That covers the diagnostic's
  Opus `xhigh` streams, the reviewer's streams and gate probes on Opus and Haiku.

## Two facts found while preparing this amendment
1. **A Claude usage limit is not a rate limit in 1.8.1.**
   - Rate-limit classification (`native_error_class`) applies only to Codex error rows.
   - For Claude, an errored `result` is always `native-error`, and `rate_limit_event` rows are ignored.
   - If the account's quota runs out inside a chunk, each later cell comes back invalid at once, charged its reserve, until the
     17-invalid cap stops the run (NO-STOPPED).
   - The pre-registered rate-limit pause therefore never fires for this study. Only the quota gate before each chunk protects it.
2. **One expensive cell stops the whole run.** In 1.8.1, a single cell that costs more than `--stop-usd` triggers
   `cell-over-limit`, which reads NO-STOPPED.
   - Observed `xhigh` cells on go-json reach US$8.08 (2026-11-07), US$7.71 (probe) and US$7.40 (diagnostic).
   - The pre-registered US$10 leaves little room.

## Reviews of this amendment
Each draft went to Claude Fable 5.2 at `xhigh`.

**Round 1: FIX FIRST** (one blocker, six majors). Checked against the pinned code:
- **Confirmed, B1:** a refused cell is recorded as done, never re-dispatched, and charged its reserve. Polling inside an outage
  loses 2 planned cells per retry.
- **Confirmed, M4 exit code:** the shim returned tee's failure instead of the CLI's code.
- **Refuted, M4 timeout:** the runner starts each cell in its own session and kills the whole process group (`os.killpg`). The
  reviewer withdrew this finding in round 2.

**Round 2: FIX FIRST** (one blocker, four majors).
- **Blocker:** the quota gate's open paths.
- **Majors:** resume never exercised; load gated only at a few instants; the `xhigh` half of L2 not asserted; the production shim
  never compared with the tested template.
- No finding biased the reading toward PROVEN or PAYS.

**Round 3: SHIP**, with no correction pending. All twelve round-2 findings are fixed, and no path to PROVEN, PAYS or DOES-NOT-PAY
was found that the run would not have earned.

Four launch checks are required and are recorded in `GO-3.json`:
- **L1:** the shim is executable.
- **L2:** the run is launched detached from the implementer's session, after a rehearsal before the window reset, on mains power.
- **L3:** the quota gate's CLI equals the one in `f1.json`.
- **L4:** the production directory is clean.

Accepted as-is: minors a to j of the round-3 review (`evidence/revisao-f1-r3-20261113/result-full.md` in the private record).

A free check the reviewer asked for: real `ambiguous-session` cells carry a measured cost from their receipt (US$1.96 on
2026-11-07, US$7.71 in the probe). They are not charged the US$20 reserve. So the "two cells hold the run" rule bites only cells
that fail with no cost, such as `CleanupIncomplete` or a usage limit.

## Changes, all before any F attempt

### 1. Missing-data guard (`analyze_f.py`)
Cells without a valid result are not missing at random: the longest sessions are the ones that die.

| Reading | What it does | Role |
|---|---|---|
| **L0** | The pre-registered reading, unchanged: cells without a valid result are left out. | Decides, with L2 |
| **L2** | Built from the plan (41 tasks × 2 replicates × 2 arms). Every planned cell without a usable valid result is imputed as the worst case for `medium`'s mean. | Decides, with L0 |
| **L1** | Invalid cells with readable outcomes, graded as observed. | Reported only |

Which cells L2 imputes:
- invalid cells of any class;
- cells refused by the provider;
- cells never dispatched;
- valid cells whose test outcomes are unreadable.

How L2 imputes:
- a `medium` cell fails every reachable test;
- an `xhigh` cell passes every reachable test;
- this restores the B pairs;
- its own critical value is simulated again, and the floor still applies.

L2 is the worst case for the mean, not necessarily for the statistic.

How the verdict is read:
- **PROVEN** needs PROVEN in both L0 and L2, in readings P and B. L0 PROVEN with L2 short of it reads NOT-PROVEN, labelled
  "not decisive by missing data".
- **KILL** follows L0 alone, because the guard can only demote.
- **PAYS** also needs the worst-case R to have its upper bound below 1. In that R:
  - an invalid `xhigh` cell counts as accepted;
  - a cell with no measured cost counts at US$20 at `medium` and at zero at `xhigh`.

**Tolerance.** On the 2026-11-07 data, one imputed `medium` cell moved the statistic from 4.67 to 4.04, against a critical value
near 2.23. By extrapolation, about five such cells would read NOT-PROVEN by missing data at that effect size.

### 2. Stops are read before any analysis
A `STOP.json` in the results reads NO-STOPPED. A `HOLD.json` from the cost marker reads NO-BUDGET. Neither is analysed further,
and `run_f.sh` refuses to start while either exists.

### 3. Per-cell brake from US$10 to US$20
The cap stays at US$400. Dispatch reserves US$20 per cell in flight, so it stops at a spend of about US$360. At the highest
observed burn (US$7.40 in 1908 s), a cell that runs to the 3600 s timeout costs about US$14.

**Tolerance.** A cell that fails with no measured cost, for example a `CleanupIncomplete` under load, is charged the US$20
reserve. Against an expected US$275, about four such cells bring a complete run to the US$360 stop.

### 4. Chunks and gates (`run_f.sh`)
Cells go out in chunks of at most 20, in the seeded plan's order: replicate 1 whole, then replicate 2. Every runner call uses
`--replicates 2`. The first 40 cells therefore stay replicate 1, and no call ever covers fewer replicates than the results on disk.

Before each chunk that has cells to dispatch, two gates run:
- the load gate (§6);
- the quota gate (§5).

A failed gate pauses the run for the maintainer. Running `run_f.sh` again resumes it:
- it skips what is on disk;
- it opens no grade;
- it never re-runs the cost marker;
- `run.lock` refuses a second concurrent start;
- an existing `f-result.json` refuses any start, so there is a single look.

### 5. Quota gate (`quota_f.py`)
Before each chunk, one minimal CLI call on the study's model (`claude-opus-5-5`, no tools; not evidence) reads every
`rate_limit_event` of the account.

**Overage never passes the gate**, because the study runs on a reset window.

The gate passes only if all of these hold:
- every event's top-level status is `allowed` or `allowed_warning`;
- the seven-day utilization is identified, from `unifiedWindows.seven_day` or from a top-level figure whose `rateLimitType` is
  `seven_day`;
- no other window appears (an unknown window fails closed, for the maintainer to judge);
- the window has room for the cells still to run: used + 0.60 × (cells left / 164) ≤ 0.95.

0.60 is the whole study's worst measured draw on the window: about US$4.7 per point on 2026-11-12, against a US$275 study. That
figure includes the implementer's own interactive session on the same account.

If the call returns no event, the gate fails closed.

### 6. Load gate and load log
- `load.log` records the load average every minute.
- Before each chunk and before the serial re-grade, the 5-minute load must be under 8. The study runs 2 jobs on 18 cores.
- The run waits up to 60 minutes for that, then pauses for the maintainer.

Other processes on this machine, including the maintainer's own, change grades and process cleanup: see the dry run below. The
maintainer's go records that the machine and the account are reserved for the study until `f-result.json` exists.

### 7. In-flight cost marker (`costcheck_f.py`)
After the first 40 cells, the run projects its cost by arm, once: mean `medium` cost × 82 + mean `xhigh` cost × 82. It reads costs
only, never grades. A pass writes `MARKER.json`.

**A hold is terminal: NO-BUDGET, and nothing is redone.** The run is held in either case:
- the projection is above US$360, where dispatch would stop;
- an arm has no cell yet.

With the 2026-11-07 costs of the same tasks and arms, in F's seeded order, the projection for the first 40 cells is about US$256.
Over 20,000 resamples of those costs it never passed US$270, and with costs 30% higher it stays near US$333.

A cell with no measured cost counts at the US$20 reserve. So any two such cells among the first 40 hold the run, at about
US$256 + US$164.

### 8. Stream retention (`bin/claude`, from `shim.template`)
- **What the shim does:**
  - runs the same CLI with the same arguments;
  - copies its stdout to `streams/`;
  - writes a sidecar with the workspace and start time;
  - exits with the CLI's own code (`PIPESTATUS`), even when the copy cannot be written.
- **What changes in the set:** the agent command's CLI path points to the shim, and nothing else.
  - Before: `edb3943f677d655360500e92e4fa676386c690f9d17b8cad3d7ec8d4563a3ad5`.
  - After: `2402907a97fed0fc46ccd429097328e175686a647820b0872356db71aaf1020e`.
  - `f1.json` is the source; `F1-SET.sha256` mirrors it.
- **Checks before the run:**
  - `bin/claude` must be byte-equal to `shim.template` filled with this directory's `streams/` and the CLI named in `f1.json`;
  - that CLI must be executable;
  - its `--version` is logged at each start.
- **The CLI wrapper's own bytes are neither hashed nor read.** That is a standing rule of the maintainer, because the wrapper
  handles credentials. The runner's seal covers the shim.
- **Publication:** the shim and `f1.json` are published by hash only, because they hold local paths.

### 9. Rate-limit pause
A recognised rate-limit stop (Codex only in 1.8.1) waits 30 minutes, at most 48 hours across the whole run.

### 10. Preconditions (`run_f.sh`)
Before the run starts:
- pins and hashes match;
- the PREREG dry run passed;
- the F-1 dry run passed, on this set and on the sha256 of every file it copied;
- the probe result is the recorded failure;
- the maintainer's `GO-3.json` names this `SHA256SUMS`;
- dry-run overrides (`F_REGRADE_ARGS`, `F_QUOTA_CLI`, `F_MAX_LOAD`) are refused unless `GO-3.json` is a sandbox stub, and they are
  logged;
- the shim checks of §8 pass;
- `streams/` is writable;
- no `HOLD.json` exists.

The run uses `LC_ALL=C`, and stays awake (`caffeinate`), pauses included.

The PREREG dry run checked references, sign and the serial re-grade on the set before F-1 (`edb3943f…`). It carries over, because
F-1 changes no task, oracle, reach or prompt.

## F-1 dry run (`dry_run_f1.py`, no model)
The dry run uses the real `run_f.sh`, `shim.template` and analysis, in sibling sandboxes, with a fake CLI.

| Scenario | What it exercises |
|---|---|
| **A, whole run** | Chunks of 20; one marker; one quota gate per chunk; `ambiguous-session` in one cell of each arm; one Claude usage-limit error after the marker; serial re-grade on a sample of 2; A/A; analysis. |
| **B, forced hold** | The marker holds after 40 cells, the analysis reads NO-BUDGET, and a restart is refused. |
| **C, quota gate fails** | Nothing is dispatched. |
| **D, resume** | The quota gate fails at its 3rd call, then the serial re-grade fails once, then the run completes. The result must equal A's, with one marker line; a 4th start is refused. |
| **E, quota gate on crafted events** | A blocked top-level status, events without `unifiedWindows`, an extra window, no event, the headroom rule, and a blocked later event. |

It also asserts that L2, with every planned cell missing, gives a mean of exactly −1.0 over the 41 tasks. The 60-minute load wait
is not exercised. The result is in `dryrun-f1/dry-run.json`.

**Result, on a quiet machine (5-minute load 7.10 at start, 2026-11-13T05:10Z, 1985 s): passed, 24 of 24 checks.**
- **A:** 9 chunks (8 × 20 + 4), one marker after 40 cells, one quota gate per chunk.
  - The only invalid cells are the 3 provoked ones.
  - Every valid cell's receipt hash is found among the 164 streams.
  - L2 imputed 3 cells.
- **B:** held after 40 cells; NO-BUDGET; the restart was refused.
- **C:** exit 4 and no results.
- **D:** exits 4, 1, 0 and 1. The result is equal to A's, with one marker line.
- **E:** every quota case behaved as fixed.
- **L2 with every cell missing:** mean -1.0 over 41 tasks.

**Earlier dry runs, preserved, not counted:**
- **Under heavy load.** The 5-minute load was 15 to 31. 4 of the first 40 cells came back invalid with `CleanupIncomplete`: the
  runner's 2-second check that a command's process group is gone failed. 3 of the 4 were in controller steps the shim does not
  touch. In isolation, the same check passed 60 of 60 times with the shim, with the fake CLI alone, and with `/usr/bin/true`, at
  the same load.
- **On a quiet machine,** with the round-1 code: 17 of 17 checks passed.

## What does not change
- the margin (0.20), the 41 tasks, the arms, the seed, the frozen reach and the critical floor;
- reading L0, T1 and the pre-registered R and its bootstrap;
- the US$400 cap and the cap of 17 invalid cells, which counts `ambiguous-session` like any other invalid class;
- the single look after the serial re-grade.

## Validation
The new `analyze_f.py` was run on the published 2026-11-07 results:
- **L0 reproduces the published reading exactly:** statistic 4.666643, critical values 2.2315 and 2.2367, PROVEN, R 0.300
  [0.267, 0.344].
- **L2:** 164 cells planned, 163 usable and 1 imputed (invalid). Mean −6.75 points, statistic 4.04, still PROVEN.
- **L1 equals L0.** The invalid cell passed its task's single reachable test, like the other three cells of that task.

## Hashes
- **Pinned distribution:** 007 1.8.1
  - commit `f05ebcbc47496bcd39c272fe2d0dd82d9a336879`;
  - manifest `e064bdeaeda8ebf046711f1ff82e1025c21169b3f91e32fef13db75b4b7d9615`;
  - archive `834d2ee9e9b18741f678ba4fff4f62eaa19a25dc86a04546795d2ac4bb31a877`.
- **Set:** before F-1 `edb3943f677d655360500e92e4fa676386c690f9d17b8cad3d7ec8d4563a3ad5`; after F-1
  `2402907a97fed0fc46ccd429097328e175686a647820b0872356db71aaf1020e`.
- **Every script, set, gate file and this amendment:** in `SHA256SUMS`. Its own sha256 is in the commit message and in the
  maintainer's `GO-3.json`.
