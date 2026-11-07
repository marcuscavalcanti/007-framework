# Pre-registration: go-json, Claude Opus 5.5 `medium` vs `xhigh`, margin 10 points (2026-11-07)

Written and hashed before any paid attempt of this run. It is pushed before dispatch. `SHA256SUMS` binds the files next to this one.

## Question
On go-json-experiment/json's 41 commits that reach new behaviour, does Claude Opus 5.5 at `medium` save at least 25% agent time
against `xhigh` without losing more than 10 points of the behaviour the commits' own tests check? This is the decision a
Claude user faces: the declared margin is the loss that would make `medium` not worth its saving. The margin is not near-sameness.
One repository, one executor.

## Design
- **Commits, grading, reach set:** the 41 commits, the frozen reach set (481 tests) and the grading of the Codex top-up
  ([../go-json-topup-20261106](../go-json-topup-20261106/)). The reach set comes from earlier Codex attempts. It is a fixed
  estimand, the behaviours a model already reached on these commits.
- **Arms:** `claude-opus-5-5` at `medium` and at `xhigh`.
  - **CLI:** Claude CLI in print mode, stream JSON, no session persistence.
  - **Tools:** Bash, Read, Edit, Write, Glob, Grep. Web tools are denied.
  - **Sandbox:** Claude sandbox on. Settings pinned by hash `9ee69a3a8a4b3bf65e75b80133988b5d6bde59a87e9b265e913ca93ec94af8f0`, unchanged from an earlier run.
  - **Go:** cache inside the workspace, `GOPROXY=off`.
- **Attempts:** 2 per arm per commit, 164 in all, fresh. Two replicate blocks of 82, both arms shuffled inside each block,
  seed 20261108.
- **Cost probe** before this registration: 4 attempts on 2 commits, all valid, US$6.95 client-estimated, Go builds in the
  sandbox. The probe is not part of the analysis.

## Decision rule (one look, fixed sequence)
1. **Manipulation:** median reasoning tokens lower at `medium`.
2. **Less waiting:** median agent-time saving ≥ 25% per attempt, with a task-bootstrap 95% interval above 0.
3. **Within the margin** (primary: per-commit `medium − xhigh` pass share on the frozen reach set; readings P and B, the worse
   decides):
   - KILL if a reading's 95% t interval lies wholly below −10 points.
   - PROVEN if, in both readings, `(mean + 10 points) / se` exceeds `max(2.4168, c)`.
     - 2.4168 is the floor in `critical-floor.json`: the 97.5% point of that statistic under a 10-point loss of whole failed
       attempts at 2 attempts per arm, simulated from the earlier attempts with 100,000 draws.
     - `c` is the same quantity simulated from this run's attempts.
   - Otherwise NOT-PROVEN.

**Why a floor** (`margin10_check.json`, Codex go-json pools, 4,000 draws per cell):

| Rule | False PROVEN at −10 pp, whole failed attempts (P / B) | PROVEN with equal arms (P / B) |
|---|---|---|
| Plain t | 4.9 / 4.7% | 99 / 97% |
| Run-own critical value | 3.25 / 2.5% | 96 / 89% |

The floor protects reading P. Claude's noise is not known yet. At the noise Claude showed on another repository, power to prove
equal arms would fall to about one half.

## Secondary, never deciding
- Product reach (recomputed from this run's attempts).
- Acceptance on commits where any attempt was accepted.
- τ² bounds.
- Invalid attempts per arm, failure classes, median cost per arm.

## Operation
- **Command per block:** `effort_lab.py run --set claude-set.json --out results --replicates 2 --jobs 4 --max-calls 82 --max-usd 400 --stop-usd 10 --max-invalid 10`.
- **Cap:** US$400, client-estimated cost.
- **Never redone:** invalid attempts, which are reported per arm.
- **Deviations:** any deviation is written down with its time before any per-arm result is read.

## What will be said
- **PROVEN:** "On go-json-experiment/json's 41 commits that reach new behaviour, Claude Opus 5.5 `medium` lost no more than 10
  points against `xhigh` on average over those commits, on what their own tests check, with X% less agent time (2 fresh
  attempts per arm, pre-registered, calibrated). Not a claim of sameness: the margin is the decision margin."
- **KILL:** "`medium` loses more than 10 points here: keep `xhigh` for Claude on this kind of code."
- **NOT-PROVEN:** the interval as it stands.

## Limits
- **Contamination:** public commits from 2021–2025; the model may have seen them, in both arms alike.
- **Measurement:** served effort is not reported by the CLI; costs are client estimates.
- **Oracle:** 21% of partial changes pass all hidden tests.
- **Scope:** one repository, one language. The reach set came from another executor.
