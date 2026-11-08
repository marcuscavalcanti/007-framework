# Amendment 1 to PREREG-PILOT (2026-11-08)

This amends [PREREG-PILOT.md](PREREG-PILOT.md) (SHA-256 `a55526f3…a4f5b2`, published in `7a6b44d` at 2026-11-08T11:40:26-03:00).
That file is not edited; its hash in `SHA256SUMS` is unchanged. Where this amendment and the original differ, this amendment
applies. It was written and published before any pilot attempt was dispatched and before any pilot outcome existed. Its
causes are an external audit of release 1.6.1, an independent critical review, and decisions by the maintainer.

## What had been executed and observed before this amendment
- **2026-11-07, yield probe round 1:** BurntSushi/toml 23 tasks, golang/sync 3, golang/time 1, google/go-cmp 2. It used the
  pre-fix miner and no model.
- **2026-11-08, before the pre-registration:**
  - The critical floor at 5 points was simulated from go-json's Codex attempts (2.1976). The published
    `gojson-floor-5pp.json` has diagnostic lines before its JSON object (audit finding F11); its numbers are unchanged.
  - `freeze_pilot.py` was smoke-tested on replicates 1–2 of the go-json top-up, an earlier experiment whose outcomes were already
    public. The result was GO, with 40 reaching tasks against n80 = 32. It used no pilot data.
- **2026-11-08 from 14:43Z, yield probe round 2 (fixed miner, no model; still running when this was written):**
  - BurntSushi/toml: 25 tasks;
  - traefik/yaegi: 11 tasks from its first 41 candidates;
  - pelletier/go-toml, pierrec/lz4 and klauspost/compress: not mined yet;
  - no planted-defect check run yet.
  
  What was observed is task counts and drop reasons. There are no arm outcomes.
- **Post-hoc analyses (exploratory error vs fail, the audit):** they read only the earlier go-json experiments' outcomes.
- **Not executed:**
  - no pilot set built;
  - no pilot attempt dispatched;
  - no paid call for this study;
  - no pilot outcome observed.

## Changes

**1. Repository gate.**
- Before (line 18): "a repository enters only if its planted-defect check rejects at least 30% of reference patches with one hunk
  removed".
- After:
  - The 30% entry gate stays.
  - A rejected mutant counts only where the task's reference patch passes its own oracle (the corrected gate of 1.6.0). If any
    reference patch of a repository fails, that repository's check is re-run with the corrected gate before pooling, with no
    model. Each repository's rejection rate and control pass rate are reported.
  - Pooling allows a repository down to 30%, but a public claim about the pooled confirmatory verdict also requires the same
    verdict category when repositories below 60% are excluded. go-json was 79%.

**2. Cost cap.**
- Before (line 25): "US$150 at list price, an estimate rather than an invoice".
- After:
  - The cap stays.
  - Before dispatch, the expected cost is 4 × pooled tasks × US$0.264, the top-up's mean cost per dispatched attempt
    (US$172.98 / 656).
  - If that exceeds US$150, the pilot uses a random subset of tasks drawn before dispatch:
    - seed 20261110;
    - without replacement;
    - proportional to each repository's share;
    - sized to fit.
  - The subset is recorded in the run log.

**3. Evaluator and patch capture.**
- Before (line 23): the arms use "the Codex top-up's agent command, settings and grading".
- After:
  - Grading keeps the top-up's evaluator logic, for coherence with the floor.
  - The exact code commit is recorded in the run log at dispatch.
  - If the audit's fix for capture against the immutable base commit (F02) is merged before dispatch, the run uses it.
  - Candidate patches are retained for re-grading.

**4. Confirmatory rules, added to "Confirmatory rules, fixed now".** Lines 48–69 are unchanged. Added:
- **Estimand:**
  - population: the reaching tasks of the pooled, gated repositories;
  - conditions: `medium` and `high` as specified;
  - outcome: pass share on the frozen reach;
  - intercurrent events:
    - provider error, timeout, ambiguous session and a run stopped by the cap make an attempt invalid; invalid attempts are
      excluded and reported per arm with their reason;
    - an agent commit is captured against the base commit, never as an empty patch;
  - summary measure: the mean of per-task `medium − high` differences.
- **Robustness, required for any public claim** (never changing the verdict itself):
  - re-grade the retained confirmatory patches with the evaluator after the audit's F01/F02 fixes, with no model; the verdict
    category must stay the same;
  - the 60% exclusion check of change 1.
- **Secondary, never deciding:**
  - a bootstrap by blocks of contiguous commits, and one by repository;
  - a reading that counts every dispatched attempt (invalid = failed);
  - full acceptance;
  - mean cost per dispatched attempt and per accepted attempt.

## What does not change
- The arms.
- Attempts per arm, and the seed.
- The critical floor (2.198) and the GO / NO-GO formula.
- The primary outcome, the two looks, the 5-point margin and the KILL / FUTILITY / PROVEN rules.
- Pilot attempts never enter the confirmatory analysis.
- The confirmatory run still needs its own approval with its cost.
