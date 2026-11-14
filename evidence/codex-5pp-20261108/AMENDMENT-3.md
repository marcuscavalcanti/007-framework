# Amendment 3 to PREREG-PILOT (2026-11-12)

This amends PREREG-PILOT and Amendments 1 and 2. None of them is edited, and their hashes in `SHA256SUMS` are unchanged.

**When it was pushed:**
- the corrected gate re-run was still running, and none of its output files existed;
- no pilot set had been built;
- no pilot attempt had been dispatched.

**Cause:** an adversarial review of [DECISIONS.md](DECISIONS.md) and of the pre-outcome plan.
- Claude Fable 5.2 at maximum effort; served model `claude-fable-5-2`, US$4.23.
- The review is kept in the maintainer's records as `fable-rule-20261112`.

## What the review found
- **The rule was not informative.** Under the first yes-or-no rule, NO was expected about 93% of the time. Most of that NO would have
  said nothing about 007: it would have come from pilot noise, small repositories or provider failures. DECISIONS revision 1
  (`5d7a585`) answers this, and adds the scripts below.
- **The confirmatory analysis was left until after a GO,** when pilot arm outcomes would already be visible. It is written now
  ([PREREG-CONFIRM.md](PREREG-CONFIRM.md)).
- **The top-up's analysis simulates its critical value at the default 3 points.** `analyze_topup.py` line 64 calls
  `proven_critical` without a margin. The confirmatory analysis passes 5 points.
- **Part 3 had no script.** It would have been computed by hand after the outcome. `part3.py` fixes it now.
- **The dry run covered 2 tasks per repository, and every cell applied the reference.** That gives zero variance, so the path from
  noise to `n80` to GO was never exercised.
- **Third parties could not re-run the freeze.** `freeze_pilot_v2.py` imports `analyze_topup` from a directory the published
  tree does not have, and raw cells are kept local.

## Changes
**1. Freeze (`freeze_pilot_v3.py`).**
- The decision logic is that of `freeze_pilot_v2.py`, unchanged.
- It imports `analyze_topup.py` from the published `evidence/go-json-topup-20261106/` when present. Wherever it imports it from,
  the bytes must match the SHA-256 published there (`6b7ad681…`).
- It writes `cells.csv`: one row per cell with repository, task, arm, replicate, validity, failure class, acceptance, reasoning
  tokens, agent time and cost. The table has no local paths.
- It writes `cells.sha256`, with the hash of every raw cell and runner file. Both files are published with the pilot result.
- It reports the reaching tasks per repository. This count never decides.

**2. Dry run (`dry_run_v2.py`).** It replaces the dry run of Amendment 2, change 8.
- Every pooled task, 2 attempts per arm.
- The fake CLI applies either the reference or a planted defect. The defect is the reference without one hunk, drawn with the
  pinned `mutants`. The choice is a hash of task, arm and replicate: about 90% reference at `high` and 80% at `medium`.
- **It passes only if:**
  - every cell is valid;
  - the run and the freeze exit 0;
  - σ² > 0;
  - `n80` is a number.
- This also checks every pooled task's reference under the pinned code, the three repositories accepted from the recorded check
  included.
- The early stops (`cell-over-limit`, `invalid-budget`, the money cap) are covered by the unit tests of the pinned distribution.
- **Cost of a cell:** a cell above `--stop-usd 2` is unlikely. The most expensive valid cell of the go-json top-up cost US$0.79,
  over 652 cells.

**3. Dispatch (`run_pilot_v3.sh`).** The pilot is dispatched only if all of these hold:
- the pinned distribution verifies;
- every file in `SHA256SUMS` matches;
- `dry_run_v2.py` passed;
- no `results/` directory exists;
- the set matches its build.

The log records the hash of `SHA256SUMS`. After the freeze, `part3.py` runs as a description only.

**4. Confirmatory rules.**
- [PREREG-CONFIRM.md](PREREG-CONFIRM.md), `build_confirm.py`, `run_confirm.sh` and `analyze_confirm.py` fix:
  - the confirmatory set, seed, blocks, limits and cap;
  - the analysis at 5 points;
  - the 60% exclusion reading.
- The re-grade with the v1.7.0 evaluator is fixed in behaviour now. Its script is written after a GO and hashed before the first
  confirmatory attempt.

**5. Part 3 (`part3.py`).** It carries out [DECISIONS.md](DECISIONS.md) part 3.

## What does not change
- The pilot's arms, attempts, seed, margin, cap, invalid budget, GO / NO-GO formula and floor.
- The primary outcome and the looks.
- The corrected gate and its consistency check.
- The reference-failed rule.
- No repository is added, and none is mined again.
