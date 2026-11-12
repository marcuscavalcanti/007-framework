# Pre-registration F: does Claude Opus `medium` pay against `xhigh` on go-json? (2026-11-12)

Written and pushed before any attempt of this study.

**Origin, stated up front.** This is a confirmatory replication chosen after an exploratory reading. In the earlier Claude run (PREREG-CLAUDE, 2026-11-07), the pre-registered margin was 10 points and the verdict was NOT-PROVEN: −5.5 points, 95% interval −11.8 to +0.7. Read post hoc at the break-even margin of `docs/lab.md`, the same data would pay. This study asks that question again, on fresh attempts. Choosing it because of that reading is a selection, and it is reported with any result.

## Question
On go-json-experiment/json's 41 commits that reach new behaviour, does Claude Opus 5.5 at `medium` lose less than it saves against `xhigh`?

## Margin, fixed now
- **Formula:** `m = min(0.20, acceptance at xhigh × median cost saving of medium)`, the break-even margin of `docs/lab.md` and PREREG-B.
- **Inputs:** the earlier Claude run, as published. Acceptance at `xhigh` is 0.768 (63/82), and the median cost saving is 0.75 (US$0.57 against US$2.27). That gives min(0.20, 0.576).
- **Result: m = 0.20.**

## Design
- **Unchanged from PREREG-CLAUDE:**
  - the 41 commits;
  - the frozen reach set (481 tests);
  - the grading;
  - the arms (`claude-opus-5-5` at `medium` and `xhigh`);
  - the agent command, with Claude settings pinned by hash `9ee69a3a8a4b3bf65e75b80133988b5d6bde59a87e9b265e913ca93ec94af8f0` and the Go cache in the workspace with `GOPROXY=off`.
- **Attempts:** 2 fresh attempts per arm per commit, 164 in all. Two blocks of 82, both arms shuffled inside each block.
- **Seed:** 20261112.
- **Code:** the published 007 1.8.1 distribution, pinned by its manifest hash, which carries the rate-limit pause. Its commit and hash are recorded in F-1 before dispatch.
- **Before dispatch:**
  - **Dry run:** the full set with a fake CLI, with the reference, sign and serial re-grade checks of the Codex pilot's Amendment 5 (b).
  - **Provider probe:** 3 real cells on go-json commits outside the 41, declared non-evidence, which must finish with valid receipts.
- **Limits:**
  - 2 jobs;
  - `--stop-usd 10`;
  - invalid stop at 10% of cells; provider rate limits pause instead and are not counted;
  - cap US$400, client-estimated;
  - a load log.

## Verdict (one look)
- **Readings:** P and B; the worse decides.
- **KILL:** a reading's 95% t interval lies wholly below −0.20.
- **PROVEN:** `(mean + 0.20) / se` beats `max(floor, c)` in both readings.
  - `floor` is the larger of the 97.5% points simulated at a 0.20 loss with 2 attempts per arm, with 100,000 draws, from (i) the 231 earlier re-graded Codex go-json attempts and (ii) the earlier Claude run's 163 valid attempts.
  - `c` is the same quantity simulated from this run's attempts.
- **NOT-PROVEN:** anything else.

## Economic reading
- `R` = cost per accepted change at `medium` ÷ the same at `xhigh`. It counts every dispatched cell except provider refusals. The 95% interval comes from a task bootstrap: 10,000 draws, seed 20261112.

## Answer
| Answer | When |
|---|---|
| **PAYS** | PROVEN, and R's upper bound is below 1 |
| **DOES-NOT-PAY** | KILL |
| **PROVEN-NOT-ECONOMIC** | PROVEN, and R reaches 1 |

**Instrument (T1), required for any answer:**
- serial re-grade discordance of at most 2%;
- the A/A check of the Codex pilot's Amendment 5 (j) within 3% to 8%.

## Limits
- **Scope:** one public repository, from 2021 to 2025; the model may have seen it, in both arms alike.
- **Measurement:** served effort is not reported, and costs are client estimates.
- **The reach set** came from Codex attempts.
- **What PROVEN means:** at break-even, PROVEN means the lower effort does not lose what it saves. It does not mean the same change.
