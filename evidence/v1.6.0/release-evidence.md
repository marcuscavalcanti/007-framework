# 1.6.0 candidate: `007 lab` and thesis D

Base: published 1.5.2, commit `361ede0751b1d02b5488b940dd943c77f4a6b675`. The changes are listed in the
[changelog](../../CHANGELOG.md); this file records what qualifies the candidate and what it does not claim.

## What changes for a user
- **`007 lab`.** Subcommands: `mine`, `sensitivity`, `run`, `chain`, `report`, `feasibility`, `sufficiency`.
  - It replays a repository's own commits at two reasoning efforts, with each commit's own tests hidden from the agent.
  - It reports agent time, tokens and estimated cost.
  - It tests the behaviour the commits' tests check against a margin declared before spending.
  - `PROVEN` must beat a critical value simulated from the run's own attempts; `report.md` states the verdict in plain words.
- **Thesis D.** It is restated as a decision: for the model you chose, whether a lower effort pays in your repository.
- **New tools:**
  - native runner hardening;
  - `choice_observatory.py`;
  - `effort_trial.py` (off by default);
  - `config_guard.py`;
  - `line_trial.py`.
- **Dashboard:** the same-change claim reads the reachable scale, and quota is marked ESTIMATED.

## Evidence status (README's claims table)
- **Measured:** less waiting.
  - Codex −30% median agent time per attempt on public go-json, 95% CI 26–33%.
  - Claude Opus 5.5 −67% on public go-json, CI 60–73%.
- **Proxy only:** less quota.
  - Estimated cost per attempt: Codex −31.5%, Claude −75%.
- **Not proven:** the same change.
  - Codex `medium` vs `high` on public go-json: −0.9 pp (95% t interval −3.4 to +1.6) at a 3-point margin.
  - Claude `medium` vs `xhigh` on public go-json: −5.5 pp (−11.8 to +0.7) at a 10-point margin.
  - Both runs were pre-registered.
- **Withdrawn:** "one repository may be enough".
- **Not measured:** durability, subscription quota per arm, served effort.

## Qualification
Recorded before the tag. A later documentary commit is qualified separately, not by the CI or the review of an earlier commit.
- Exact-commit CI: pending.
- Independent review: pending (route per `AGENTS.md`: Codex `gpt-6-astra`, `xhigh`, read-only, context on stdin).
