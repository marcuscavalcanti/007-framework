# Pre-registration: go-json top-up, Codex `medium` vs `high` (2026-11-06)

Written and hashed before any paid attempt of this run. The files next to this one are byte copies of the ones the run uses;
`SHA256SUMS` binds them.

## Question
Does Codex `gpt-6.1-sol` at `medium` effort make the same change as at `high` on the commits of go-json-experiment/json that
reach new behaviour, within 3 percentage points, while taking at least 25% less agent time? One repository, one executor.

## Why this run
The first pre-registered replay (62 commits, about two attempts per arm) gave +1.3 pp, 95% t interval −4.7 to +7.2 over the 41
commits that reach new behaviour: not proven. Since then, without any model call:
- a grading defect was fixed: an agent's own Go test could redeclare a hidden test's name and break the package;
- a re-grade halved the per-attempt noise;
- simulation showed that the plain t interval calls a true 3-point loss proven up to 5.6% of the time when the loss comes as
  rare attempts that fail outright, and that a critical value simulated from the attempts keeps it near 2.5%.
At about two attempts per arm no valid rule can prove anything on 41 commits. At eight per arm it can, if the arms are equal and
the commits do not differ much in effect (between-commit spread τ). This run tests that. None of the 231 earlier attempts enter
the primary analysis.

## Design
- **Commits:** the 41 commits that reached new behaviour in the first replay (`tasks.json`: id, base, commit, hashes of the
  hidden test files). They are the same 41 under the original grading and the corrected one. Hidden tests are each commit's own
  test files; the agent never sees them. Grading resets the agent's own `*_test.go` to base before the hidden tests land.
- **Arms:** `gpt-6.1-sol` at `medium` and at `high`, `codex exec --json --ephemeral` from Codex CLI 0.160.1 (pinned path), no
  user configuration, workspace sandbox, network proxy, Go module cache read-only, `GOPROXY=off`. Same prompt, no doctrine text.
- **Attempts:** 8 per arm per commit, 656 in all, fresh. `007 lab run` dispatches whole replicate blocks (82 attempts, both arms
  shuffled inside each block, seed 20261106), one block per invocation.
- **Planted-defect check:** the oracle rejected 255 of 321 reference patches with one hunk removed (79%; gate 30%).
- **Served effort** is not reported by the CLI. The manipulation check below is the evidence that the effort changed.

## Estimand (primary)
For each commit, the difference `medium − high` in the mean share of its **frozen reach set** passed per attempt.
- The frozen reach set (`frozen-reach.json`, 481 tests) is the hidden tests red at base that any of the 231 earlier,
  re-graded attempts passed, either arm. It is fixed now, so new attempts cannot move the denominator.
- Commits are weighted equally.
- Two readings: P (every valid attempt) and B (only replicate pairs where both arms are valid). The worse reading decides.

## Decision rules (fixed sequence, checked at both looks; a failed step stops the sequence)
1. **Manipulation:** median reasoning tokens are lower at `medium`.
2. **Less waiting:** median agent-time saving per attempt ≥ 25%, with a task-bootstrap 95% interval above 0.
3. **The same change (primary).**
   - **Look 1** (replicates 1–4, 328 attempts):
     - KILL if a reading's 95% t interval lies wholly below −3 pp;
     - FUTILITY (stop, not proven) if `(mean + 3 pp) / se < 0.5` in the worse reading;
     - otherwise continue.
     - Never PROVEN at look 1.
   - **Look 2** (replicates 1–8, 656 attempts):
     - KILL as at look 1;
     - PROVEN if, in both readings, `(mean + 3 pp) / se` exceeds `max(2.198, c)`. Here 2.198 is the floor in
       `critical-floor.json` (the 97.5% point of that statistic under a 3-pp loss of whole failed attempts, simulated from the
       earlier attempts at 8 per arm, 100,000 draws). `c` is the same quantity simulated from this run's own attempts
       (`effort_lab.proven_critical`, 100,000 draws).
     - Otherwise NOT-PROVEN.
4. **Durable:** not tested in this run.

**Simulated operating characteristics** (resampling the earlier attempts; independent adversarial review):
- PROVEN when the arms are equal: 82.5% at τ = 0, and 58 / 42 / 26% at τ = 0.03 / 0.05 / 0.08.
- PROVEN under a true 3-pp loss: ≤ 2.4%.
- KILL under a loss of 8 / 10 / 12 pp: 51 / 76 / 90%.
- Expected spend: about US$174 when the arms are equal, and about US$118 under a 3-pp loss.

## Secondary, never deciding
- The same rule on the reach set recomputed from this run's attempts (what `007 lab report` shows).
- Acceptance (all hidden tests green) on commits where any attempt was accepted.
- Timeouts scored as failed attempts.
- τ² bounds: method of moments, and the covariance of odd- and even-replicate differences. Eight attempts bound τ²; they do not
  identify it.
- Line similarity of patches to the real commit, per arm, as a contamination check.
- Invalid attempts per arm, failure classes, requested model and effort, and settings hashes.

## Operation
- **Command per block:** `effort_lab.py run --set topup-set.json --out results --replicates 8 --jobs 4 --max-calls 82 --max-usd 250 --stop-usd 2 --max-invalid 20`,
  under `caffeinate`.
- **Pauses:** a planned pause between blocks, where the Codex usage meter is noted (descriptive only).
- **Invalid attempts** are never redone. An invalid attempt without a cost is charged US$2 against the cap.
- **Resume:** at most one, after an invalid-budget stop. Wait ≥ 30 minutes, then rename `STOP.json`.
- **Orphans:** an orphan receipt (no result) counts as invalid.
- **Cap:** US$250 at list price, an estimate rather than an invoice.
- **Deviations:** any deviation is written down with its time and reason before any per-arm result is read.

## What will be said
- **PROVEN:** "On go-json-experiment/json's 41 commits that reach new behaviour, Codex gpt-6.1-sol `medium` lost no more than
  3 points against `high` on average over those commits, on the behaviour each commit's own tests can see (8 fresh attempts per
  arm, pre-registered, calibrated critical value). Per-commit effects are bounded, not shown equal (τ² ≤ X). About 21% of
  partial changes pass all hidden tests, so the oracle cannot see that part. Durability is not measured."
- **NOT-PROVEN:** the interval and the τ² bounds.
  - If the τ² upper bound exceeds 0.0047 (the spread at which 41 commits lose 80% power), the claim that one repository may be
    enough is withdrawn.
- **KILL:** thesis D fails for Codex on this repository.
- **FUTILITY or a failed earlier step:** reported as such. The same change is not proven.

## Limits stated in advance
- **Contamination:** these are public commits from 2021–2025. The model may have seen them; both arms alike.
- **Scope:**
  - one repository, one language, one executor;
  - costs are list-price estimates;
  - the 41 commits were chosen because some attempt in the first replay reached new behaviour, whichever arm;
  - Claude is out of scope.
