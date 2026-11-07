# Result: go-json top-up, Codex `medium` vs `high` (2026-11-07)

Pre-registration: [PREREG-TOPUP.md](PREREG-TOPUP.md), pushed before the first paid attempt. Analysis outputs: `look1.json`,
`look2.json` (from `analyze_topup.py`, unchanged); post-hoc descriptives: `post_hoc.json` (`post_hoc.py`, never deciding).

## Verdict: NOT-PROVEN (pre-registered rule, look 2)

**Codex gpt-6.1-sol `medium` vs `high`** on go-json-experiment/json's 41 commits that reach new behaviour, 8 fresh attempts per
arm: **−0.9 pp, 95% t interval −3.4 to +1.6**. The calibrated statistic is 1.72, against a critical value of 2.20–2.21
(readings P and B; the floor was 2.198). Losses above about 3.4 points are excluded; a loss of 3 points is not. Not KILL.

The sequence held at both looks:
- **Manipulation:** median reasoning tokens 921 vs 2,808.
- **Less waiting:** median agent-time saving 30.4% per attempt, task-bootstrap 95% CI 25.7% to 33.1%.

Pre-registered consequence: the between-commit spread exceeds the 41-commit budget. τ² point estimates are 0.0028 (moments)
and 0.0049 (replicate covariance); post-hoc bootstrap upper bounds are 0.0069 and 0.0093, against a budget of 0.0047. **So the
claim that one repository may be enough is withdrawn.** On this repository, 41 commits cannot reach a 3-point verdict at any
number of attempts.

## Run
| | Look 1 (replicates 1–4) | Look 2 (replicates 1–8) |
|---|---|---|
| Attempts dispatched / valid | 328 / 324 | 656 / 652 |
| Decision | CONTINUE | **NOT-PROVEN** |
| Primary, readings P = B | +0.66 pp [−2.0, +3.3] | **−0.91 pp [−3.4, +1.6]** |
| Spend (list price, estimate) | US$87.00 | US$172.98 |

- The run took 2026-11-06 15:17Z to 2026-11-07 02:16Z, at 4 jobs, in 8 blocks of 82 attempts with planned pauses.
- **Invalid attempts:** 4 of 656, all `high`, all provider errors (`native-error-transient`) after 5–6 minutes. None was redone.
- **Why P and B agree:** the 4 `medium` partners that reading B drops scored 1.0 in tasks where every `medium` attempt scored 1.0.
- **No deviations from the pre-registration.** The τ² upper bounds were not in the pre-registered script; they are post hoc,
  and the point estimate alone already exceeds the budget.

## Secondary readings (never deciding)
- **Reach set recomputed from this run's attempts** (what `007 lab report` shows): −1.1 pp [−3.5, +1.4], NOT-PROVEN.
- **Acceptance** (all hidden tests green) on the 25 commits where any attempt was accepted: −4.4 pp [−10.4, +1.7].
  - Overall: 181/328 (55.2%) at `medium` against 186/324 (57.4%) at `high`.
  - Full acceptance is the coarser and noisier scale. It cannot exclude a loss of about 10 points.
- **Halves** (post hoc): replicates 1–4 gave +0.7 pp, replicates 5–8 gave −2.5 pp [−6.6, +1.6]. Both arms are shuffled inside
  every block, and the gap is within chance (z ≈ 1.3).
- **Contamination check:** median line similarity of a patch to the real commit is 0.129 at `medium` and 0.122 at `high`.
  10 and 11 attempts are above 0.8.
- **Cost:** median per attempt US$0.203 vs US$0.296 (−31.5%); in total US$70.4 vs US$101.1.

## What this changes
- **Guard.** At 8 attempts per arm, one repository's 41 commits rule out a loss larger than about 3.4 points on the behaviour
  their tests can see, with 30% less agent time. That is the tightest same-change bound 007 has: the first replay's interval
  was −4.7 to +7.2.
- **Bound.** A 3-point bound needs more commits, not more attempts. At this noise and 8 attempts per arm, 80% power takes about
  55–70 reaching commits if the arms are equal, and 110–145 if the true difference is −0.9 points. That means pooling several
  repositories with one verdict per executor.

## Limits (as pre-registered)
- One repository, one language, one executor. The commits are public (2021–2025), so the model may have seen them; both arms
  are alike in that.
- Served effort is not reported; the reasoning-token drop is the manipulation check.
- 21% of partial changes pass all hidden tests.
- Costs are list-price estimates.
- Raw attempts are kept locally: they carry local paths, and they will be published separately.
