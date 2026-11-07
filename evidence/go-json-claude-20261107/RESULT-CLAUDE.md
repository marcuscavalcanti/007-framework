# Result: go-json, Claude Opus 5.5 `medium` vs `xhigh`, margin 10 points (2026-11-07)

Pre-registration: [PREREG-CLAUDE.md](PREREG-CLAUDE.md), pushed before the first paid attempt. Analysis output: `result.json`
(from `analyze_claude.py`, unchanged; the files the run used match the hashes in `SHA256SUMS`).

## Verdict: NOT-PROVEN (pre-registered rule)

**Claude Opus 5.5 `medium` vs `xhigh`** on go-json-experiment/json's 41 commits that reach new behaviour, 2 fresh attempts per
arm: **−5.5 pp, 95% t interval −11.8 to +0.7**. The calibrated statistic is 1.44, against a critical value of 2.42 (the floor;
the run's own values were 2.36–2.37, readings P and B). A loss of 10 points is not excluded. Not KILL: the interval does not lie
wholly below −10.

The sequence held:
- **Manipulation:** median reasoning tokens 2,806 vs 26,522 (−89%).
- **Less waiting:** median agent-time saving 66.9% per attempt, task-bootstrap 95% CI 60.0% to 72.7% (188 s vs 568 s).

## Run
- 164 attempts dispatched, 163 valid, 2026-11-07 16:29Z to 21:37Z, at 4 jobs, in two blocks of 82 with a planned pause.
- **Invalid attempts:** 1 of 164, `medium`. Its stream carried a second session start (`ambiguous-session`), so the runner could
  not tie its usage to one session. Not redone.
- **Why P and B agree:** reading B drops that attempt's `xhigh` partner. On that commit every remaining attempt scored 1.0, so
  its difference is 0 in both readings.
- **Spend:** US$275.05 client-estimated (cap US$400): US$57.15 at `medium`, US$217.90 at `xhigh`.
- **No deviations from the pre-registration.**

## Secondary readings (never deciding)
- **Acceptance** (all hidden tests green) on the 36 commits where any attempt was accepted: −11.1 pp [−21.1, −1.1].
  Overall 55/81 (67.9%) at `medium` against 63/82 (76.8%) at `xhigh`.
- **Reach set recomputed from this run's attempts** (what `007 lab report` shows): −8.9 pp [−15.7, −2.1], NOT-PROVEN. The frozen
  set came from Codex attempts; this one comes from Claude's own.
- **Between-commit spread:** τ² 0.0225 (moments) and 0.0237 (replicate covariance), about five times the Codex top-up's on the
  same commits (0.0028–0.0049).
- **Cost:** median per attempt US$0.57 vs US$2.27 (−75%); per accepted attempt US$1.04 vs US$3.46.

## What this changes
- **Claude, twice not shown.** On one owner's Node repository (17 commits) and now on go-json (41 commits), `medium` is not shown
  to stay within the margin of `xhigh`. Both point estimates are losses (−6.9, −5.5), and here two secondary readings exclude
  zero. For Claude, `medium` is much cheaper and faster, it likely loses some behaviour, and this run cannot exclude a loss of
  up to about 12 points.
- **More attempts on these commits would not settle it.** If the true loss is near −5.5 points, the between-commit spread alone
  puts the standard error near 2.3 points on 41 commits, so the statistic stays below 2.42 at any number of attempts. A
  10-point verdict for Claude needs more commits, or a smaller true loss than this run estimates.
- **Sizes are per executor.** The break-even size in the README (about 20 commits at 2 attempts per arm) was Codex's noise. At
  Claude's, equal arms need about 40 such commits for 80% power at 2 attempts per arm (normal approximation; about 44% at 20).
  `007 lab feasibility` on your own pilot gives the size to trust.

## Limits (as pre-registered)
- One repository, one language, one executor. The commits are public (2021–2025), so the model may have seen them; both arms
  are alike in that.
- Served effort is not reported; the reasoning-token drop is the manipulation check.
- Costs are client estimates.
- The frozen reach set came from another executor.
- 21% of partial changes pass all hidden tests.
- Raw attempts are kept locally: they carry local paths, and they will be published separately.
