# Pre-registration: confirmatory Codex `medium` vs `high` run at 5 points (written 2026-11-12, before the first pilot attempt)

It applies only if the pilot's primary freeze decides GO.

**When it was fixed:**
- It was written and hashed before any pilot attempt, so no pilot outcome could shape it.
- It keeps every rule in "Confirmatory rules, fixed now" of [PREREG-PILOT.md](PREREG-PILOT.md) and in change 4 of
  [AMENDMENT-1.md](AMENDMENT-1.md).
- It fixes what those leave open.

## Set and run
- **Tasks:**
  - the pooled pilot tasks in the primary freeze's `frozen-reach.json`, and no others;
  - built by `build_confirm.py` into `confirm-set.json`, whose SHA-256 is logged before dispatch.
- **Unchanged from the pilot:**
  - the arms, the agent command, the sandbox and the grading;
  - the evaluator embedded in each task (`362f40c7…`);
  - the pinned v1.7.0 runner (`21ba2ff`).
- **Seed:** 20261113.
- **Attempts:** fresh, 8 per arm, in two blocks.
  - Block 1 is replicates 1–4, then look 1.
  - Block 2 is replicates 5–8, dispatched only if look 1 says CONTINUE, then look 2.
- **Limits:**
  - 4 jobs;
  - `--stop-usd 2`;
  - invalid cells stop a block at 10% of its cumulative cells, and are never redone.
- **Cap:** US$400 at list price.
  - Before dispatch, the expected cost is reaching tasks × 16 × the pilot's mean cost per dispatched attempt.
  - If that is over the cap, nothing is dispatched (DECISIONS part 2).
- **Code:** `run_confirm.sh` runs it all. It refuses if a file hashed in `SHA256SUMS` changed, or if `confirm-set.json` differs
  from its build.

## Analysis (`analyze_confirm.py`)
- **Sequence**, checked at both looks:
  - manipulation: median reasoning tokens are lower at `medium`;
  - time: the median agent-time saving is at least 25%, and its task-bootstrap 95% interval lies above 0.

  If either fails, the run ends there with STOP-SEQUENCE.
- **Primary:** the per-task `medium − high` pass share on the frozen reach, in readings P and B. The worse reading decides.
- **Look 1:**
  - KILL if a reading's 95% t interval lies wholly below −5 points;
  - FUTILITY if `(mean + 5) / se < 0.5`;
  - otherwise CONTINUE.
- **Look 2:**
  - PROVEN if `(mean + 5) / se` exceeds `max(pilot critical floor, c)` in both readings, where `c` is simulated from the fresh
    cells at 5 points with 100,000 draws;
  - KILL as at look 1;
  - otherwise NOT-PROVEN.
- **Fewer than the minimum signal tasks:** NO-INFORMATION.
- **Difference from the top-up's script:** the 5-point margin is passed to the simulated critical value. The top-up's
  `analyze_topup.py` called it without a margin, which simulates at 3 points.

## Robustness (Amendment 1, required for any public claim and for a YES in DECISIONS part 5)
- **Exclusion check:** look 2 is recomputed without the repositories whose gate sensitivity is below 60% (`pilot-gate.json`).
  The category must stay the same.
- **Re-grade:**
  - **What it does:**
    - every valid confirmatory cell's retained candidate patch is applied to its task's base;
    - the patch is graded with the v1.7.0 evaluator (`lab_accept.py`, SHA-256 `85c452c1…`, from the pinned distribution), with no
      model;
    - its `acceptance_outcomes` are replaced;
    - look 2 is recomputed on the re-graded cells. The category must stay the same.
  - **Unrepeatable cells:** a cell whose patch cannot be applied, or whose grading errors, keeps its original grade and is listed.
  - **The script** (`regrade_confirm.py`):
    - it is written only after a GO and before the first confirmatory attempt, and hashed in `SHA256SUMS` then;
    - its behaviour is fixed here, and it has no other parameter.

## Part 3 and publication
- **Part 3:** `part3.py`, run on the confirmatory results ([DECISIONS.md](DECISIONS.md) part 3).
- **Published with the result:**
  - the per-cell table and the hashes of the raw cells (`confirm-published/`);
  - both look outputs;
  - `part3.json`.
- **Early stop:** an early stop of either block ends the run. The answer is then NO-STOPPED (DECISIONS part 5).
