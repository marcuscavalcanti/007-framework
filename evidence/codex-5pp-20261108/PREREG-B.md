# Pre-registration B: does the lower effort pay on this repository? (written 2026-11-12, before the first pilot attempt)

**The question is the README's thesis, as written:** whether a lower reasoning effort pays for the chosen executor on your
repository's replay tasks, against a margin declared before spending.
- The 5-point pooled test (PREREG-PILOT, PREREG-CONFIRM) asks something stronger: "effectively the same change" (`docs/lab.md`).
- This test runs whatever the pilot decides, except NO-INSTRUMENT. It is analysed by `analyze_b.py`, hashed before any pilot
  attempt.

## Units and margin
- **Eligible repositories:** every pooled repository with at least 8 tasks in the primary freeze's `frozen-reach.json`. All of them
  are reported. go-json is not one of them.
- **Margin, per repository:** `m = min(0.20, acceptance at high × median cost saving of medium)`.
  - The inputs are that repository's valid pilot cells. This is the break-even margin of `docs/lab.md`, with its inputs taken from
    a pilot, never from the attempts judged.
  - If `m < 0.01`, the answer is NO-SAVING: reported, never decisive.

## Attempts
- **Fresh, replicates 1 to 4 per arm, on the eligible repositories' reaching tasks.**
  - **After a GO:** the confirmatory run's block 1.
  - **After a NO-GO, or if block 1 does not complete:** block B (`build_b.py`, `run_b.sh`).
- **Block B's limits:**
  - seed 20261114;
  - pinned v1.7.0 runner and the pilot's arms;
  - 4 jobs;
  - `--stop-usd 2`;
  - invalid stop at 10% of cells;
  - cap US$150.
- **Block B's expected cost:** tasks × 8 × the pilot's mean cost per dispatched cell. If that is over the cap: NO-BUDGET.
- Nothing is redone. An early stop ends block B: NO-STOPPED.

## Verdict per repository (readings P and B, the worse decides)
- **KILL:** a reading's 95% t interval lies wholly below `−m`.
- **PROVEN:** `(mean + m) / se` beats `max(floor_m, c)` in both readings.
  - `floor_m` is simulated from the go-json top-up's cells (replicates 1 to 4) at margin `m`, with 4 attempts.
  - `c` is simulated from the repository's own cells.
- **NO-INFORMATION:** fewer than 8 signal tasks.
- **NOT-PROVEN:** anything else.

## Economic reading
- `R` = cost per accepted change at `medium` ÷ the same at `high`.
- It counts every dispatched cell. A cell without a cost counts at the US$2 reserve.
- Its 95% interval comes from a task bootstrap: 10,000 draws, seed 20261114.

## Answer per repository
| Answer | When |
|---|---|
| **PAYS** | PROVEN, and R's upper bound is below 1 |
| **DOES-NOT-PAY** | KILL |
| **PROVEN-NOT-ECONOMIC** | PROVEN, and R reaches 1: the reachable-scale margin does not measure "pays" |
| Not decisive | NOT-PROVEN, NO-INFORMATION or NO-SAVING |

## Smoke test, before the hash
`analyze_b.py`, run on the go-json top-up, whose outcomes are already public. Recorded with the commit that hashes it.
- **Expected margin:** 0.574 × 0.315 ≈ 0.18.
- **Expected R over all 8 replicates:** 0.70 to 0.72.
- Values outside these would mean the script is wrong, and it is corrected before the hash.

## Limits stated in advance
- PROVEN at break-even is not "the same change".
- Four attempts per arm give lower power than eight.
- The scope:
  - this executor, Codex `gpt-6.1-sol` at `medium` against `high`;
  - these public Go repositories;
  - every run operated by the maintainer's machine.
