# 1.8.0 candidate: `007 lab` run binding and per-arm accounting

Prepared on 2026-11-12 from published 1.7.0. This is a minor release:
- it adds compatible fields and stop reasons;
- it removes or renames no command, option or field;
- the report schema identifier stays `007-lab/report/v6`.

## Changes under qualification
- **`007 lab run` seals `run-manifest.json` before its first dispatch.** The manifest records:
  - the set, without its `compare` block;
  - the agent command's program and the absolute files it names, through symlinks;
  - a hash of the 007 scripts;
  - the Python version.
- **A resume refuses if any of these changed.** It stops with `manifest-mismatch`, names what changed and dispatches nothing. It
  writes no `STOP.json`, so restoring the changed input makes the run resumable.
  - Limits stay adjustable: replicates, calls, money, jobs and the invalid budget. So does `compare`.
  - An output directory from before 1.8 is sealed on its next resume and reported as `sealed-late`.
- **`report` and `chain` refuse results sealed with another set.**
- **`report` gains two fields**, each with a plain-words line in `report.md`:
  - `run_manifest`: the seal state, and whether the comparison or margin changed after the seal;
  - `arm_accounting`: per arm, planned cells, never dispatched, dispatched without a result, invalid by failure class, valid and
    accepted.
- **Release preparation keeps annotated tags.** This change was already on `main` after 1.7.0 (`cf3b556`).

## Engineering evidence and limits
- **New negative tests**, one per sealed input: arm, task prompt, agent binary bytes, retargeted symlink, Python version and 007
  scripts. Each asserts that:
  - nothing is dispatched;
  - the dispatch ledger is unchanged;
  - no STOP is written.
- **Other new tests:**
  - a resume after the input is restored, with more replicates;
  - set refusal at report time;
  - a legacy directory reported as `sealed-late`;
  - the per-arm sums, including a dispatch with no result.
- **Limit, marked in the code:** the compilers and test runners that an oracle calls are not sealed. Only the agent command's files
  are.
- **Local suite on the candidate:** 966 native Python tests passed with no skips, and 54 JavaScript tests passed (2026-11-12).
- **CI and the independent review** of the exact commit are recorded in the GitHub release notes.
- **Reviewer:** Claude Fable 5.2 at `xhigh`, because Claude implemented this release (AGENTS.md revision 2026-11-12). It shares
  the implementer's model family, by the maintainer's decision.
- **Earlier reviews, recorded and not qualifying this release:**
  - an OpenAI `gpt-6-astra` review, dispatched on the earlier candidate `57b0a08` before that decision;
  - a Fable review of candidate `8a7a29b`, stopped when the policy changed again.

## Causal evidence
- This release asserts no new causal result. The frozen experiment reports keep their scope and verdicts.
- The Codex 5-point pilot and its confirmatory run are pre-registered on the pinned 1.7.0 code. Their Amendments 2 and 3 are
  published on their own branch, `claude/pilot-amendment-2`. This release does not change them.
