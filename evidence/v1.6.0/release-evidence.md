# 1.6.0: `007 lab` and thesis D

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
- **Exact-commit CI:** `e44e505` passed all 6 checks on GitHub Actions ([push](https://github.com/marcuscavalcanti/007-framework/actions/runs/42498557745),
  [pull request](https://github.com/marcuscavalcanti/007-framework/actions/runs/42498554629)); locally, 722 tests on a clean export. This
  record's own commit is qualified by its own CI run.
- **Independent review: failed validation.**
  - Route per `AGENTS.md`: Codex `gpt-6-astra`, `xhigh`, read-only, context on stdin.
  - One call on candidate `4326e56`, 586 s. The context was 152,204 bytes (SHA-256 `4b4a970d82c7203bdd32454f3c0dab5cf43765b9b29ad6645c01f14c1ee4b6bd`),
    authorized by the maintainer. It left out `replay_eval.py` and `dashboard/app.js` for size.
  - The Codex CLI stream does not report the served model, so the reviewer's identity is unverified. Under `AGENTS.md` that is a
    failed validation, with no second call and no substitute; this review does not qualify the release.
  - Its findings were read as unverified input and each was checked against the code and data:
    - **Fixed, with tests that fail on the old code:**
      - sensitivity counted mutants of tasks whose reference patch failed;
      - a mined repository's symlinks could redirect writes outside the temporary tree;
      - orphan receipts were not named, and a report with no valid cell divided by zero.
    - **Fixed in the docs:**
      - `--max-usd` was described as a hard cap;
      - "41 commits cannot reach a 3-point verdict" overstated (errata in the go-json results);
      - feasibility sizes are uncalibrated lower bounds;
      - calibration rates assume the reach set is given;
      - the margin is read at report time;
      - the US$1.48 gap in the top-up totals was the 4 invalid attempts (US$1.43, errata).
    - **Already resolved:** the pilot's 5-point floor has its own simulation output (`evidence/codex-5pp-20261108/gojson-floor-5pp.json`,
      2.1976); it is close to, but not the same as, the 3-point floor (2.1979).
    - **Known limit, not changed:** several first-replay and private-run figures have no primary source in the public tree.
- **The pilot runs on the pre-fix miner** (`7129082`), already under way. go-json's reference patches all passed, and the pilot's
  repositories are checked the same way before it starts.
