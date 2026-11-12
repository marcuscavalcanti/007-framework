# 1.8.0 candidate: `007 lab` run binding and per-arm accounting

Prepared on 2026-11-12 from published 1.7.0. This is a minor release:
- it adds compatible fields and stop reasons, and `run`, `report` and `chain` refuse some inputs 1.7.0 accepted (CHANGELOG);
- it removes or renames no command, option or field;
- the report schema identifier stays `007-lab/report/v6`.

## Changes under qualification
- **`007 lab run` seals `run-manifest.json` before its first dispatch.** The manifest records:
  - the set, without its `compare` block;
  - the agent command's program and the absolute files it names, through symlinks;
  - a hash of the 007 scripts;
  - the Python version.
- **Each start or resume checks the seal.** Any change stops the run with `manifest-mismatch`, names what changed and dispatches
  nothing. It writes no `STOP.json`, so restoring the changed input makes the run resumable.
  - Every dispatch records the manifest's digest.
  - A manifest that is unreadable stops the run with `manifest-unreadable`. One missing after a dispatch named it stops the run
    with `manifest-missing`. Neither is ever re-sealed.
  - Only a directory whose dispatches name no manifest (one from before 1.8) is sealed late, and reported as `sealed-late`.
  - Limits can change at a planned pause. `compare` can change for an exploratory reading only.
- **`report` and `chain` refuse results sealed with another set or under another manifest.** `report --next-results` requires
  stage 2 to be chained from this sealed run at the reference arm, with the same agent command, bound to its own seal.
- **`report` gains `run_manifest`, `next_run_manifest`, `arm_accounting` and `verdict.run_binding` / `verdict.compare_changed_after_seal`**, each with a plain-words line in `report.md`:
  - `run_manifest`: the seal state, and whether the comparison or margin changed after the seal;
  - `arm_accounting`: per arm, planned cells, never dispatched, dispatched without a result, invalid by failure class, valid and
    accepted.
- **Release preparation keeps annotated tags.** This change was already on `main` after 1.7.0 (`cf3b556`).
- **Review fixes before release.** Of five reviews of earlier candidates, four returned FIX FIRST and one was stopped. None qualifies
  this release.
  - **OpenAI `gpt-6-astra`, `xhigh` requested, candidate `57b0a08`** (before the reviewer decision):
    - the stream completed with an `error` event ("model at capacity, reconnecting"), so its identity level is `failed`;
    - its findings were still checked in the code.
  - **Claude Fable 5.2, `xhigh` requested, candidate `2afe370`:**
    - identity `verified`, US$2.40;
    - its findings overlap Astra's and add:
      - `chain` taking stage 2's arm from an unsealed `compare`;
      - the executable seal saying more than it covered;
      - `chain` overwriting its set;
      - the printed verdict hiding a moved margin;
      - the review route still stating the cross-family rule.
  - **Claude Fable 5.2, `xhigh` requested, candidate `3273cf4`:**
    - identity `verified`, US$2.71;
    - it confirmed most earlier fixes, and returned FIX FIRST on:
      - a log the attempts rewrite being sealed (now `unsealed_files`);
      - `sealed` reported over dispatches that do not name the seal (now `unbound`, refused on resume);
      - stage 2's own seal;
      - an absent ledger reported as complete;
      - and smaller items.
  - **A first Fable review of `8a7a29b`** was stopped when the policy changed again. That makes it an incomplete stream, level
    `failed`, with no findings read.

  - **Claude Fable 5.2, `xhigh` requested, candidate `5e9bbbe`:** identity `verified`, US$3.17. FIX FIRST on stage 2 not held to the
    `unbound` rule. Fixed, with a test, along with its should-fix items (unbound results on resume, `run_binding` in the verdict,
    the limits sentence, `unsealed_files` recorded and named, agent-command lineage for stage 2, the four states documented).

  - **Claude Fable 5.2, `xhigh` requested, candidate `6a3abc2`:** identity `verified`, US$2.47. FIX FIRST on one regression the
    previous round introduced. The stage-2 agent-command check compared with stage 1's manifest, so it refused every stage 2 over an
    unsealed (1.7.0) stage 1. It now compares with the set in hand, with tests in both directions. Its should-fix items were fixed too:
    - a stage 2 without a manifest, refused if its ledger names one;
    - `next_run_binding` in the verdict;
    - a `partial` ledger;
    - the Stage 2 label;
    - the four states listed everywhere;
    - `chain` refusing an `unbound` stage 1;
    - `unsealed_files` validated;
    - the root test skip.

  **What the reviews' findings led to:**
  - **Fixed:**
    - stage 2's arm, now bound;
    - `chain` refusals;
    - the moved-margin flag in the verdict;
    - unsealed-program reporting;
    - per-part mismatch names;
    - streamed hashing;
    - the version and the raw set digest in the manifest;
    - the route table enforced for argv and identity;
    - re-sealing over a deleted or edited manifest;
    - unreadable manifests;
    - a non-atomic manifest write;
    - the arm order missing from the hash;
    - unbound `--next-results`;
    - receipt-only orphans and replicate numbers embedded in chain task ids, in the per-arm accounting;
    - crashes on rows that 1.7.0 accepted;
    - 1.7.0 reports that no longer rendered.
  - **Narrowed in the docs instead:**
    - relative and `env` paths in the agent command;
    - which limits can change;
    - `timeout_s`;
    - the meaning of a changed `compare`;
    - the seal being checked at each start or resume, not before each attempt.

## Engineering evidence and limits
- **New negative tests**, one per sealed input: arm, task prompt, agent binary bytes, retargeted symlink, Python version and 007
  scripts. Each asserts that:
  - nothing is dispatched;
  - the dispatch ledger is unchanged;
  - no STOP is written.
- **Other new tests:**
  - a resume after the input is restored, with more replicates;
  - set and manifest refusal through `sealed_state`, the function `report` and `chain` call;
  - a deleted, edited, truncated or non-file manifest;
  - a stage-2 manifest edited to another effort or another parent;
  - a 1.7.0 report rendered by `summary`;
  - a legacy directory reported as `sealed-late`;
  - the per-arm sums, including a dispatch with no result.
- **Limit, marked in the code:** the compilers and test runners that an oracle calls are not sealed. Only the agent command's files
  are.
- **Test suite:** from `3273cf4` on, the suite runs in CI, not locally. The pilot's Amendment 4 (on branch `claude/pilot-amendment-2`) forbids heavy local processes during
  its gate re-run. The exact-commit CI is recorded in the release notes.
- **CI and the independent review** of the exact commit are recorded in the GitHub release notes.
- **Reviewer route:** Claude Fable 5.2 at `xhigh`, requested, because Claude implemented this release (AGENTS.md revision
  2026-11-12). It shares the implementer's model family, by the maintainer's decision. Its identity level and verdict are recorded
  in the release notes.

- **Boundary record (AGENTS.md security workflow):**
  - `run` now reads every absolute file named in `agent_command`, except the `unsealed_files`;
  - it writes those files' absolute paths and digests into `run-manifest.json` in the output directory;
  - `report.json` and `report.md` also name those paths (`sealed_parts`, `unsealed_files`);
  - no file content leaves the machine;
  - the docs say to check the manifest before publishing a results directory.

## Causal evidence
- This release asserts no new causal result. The frozen experiment reports keep their scope and verdicts.
- The Codex 5-point pilot and its confirmatory run are pre-registered on the pinned 1.7.0 code. Their Amendments 2 and 3 are
  published on their own branch, `claude/pilot-amendment-2` (Amendments 2 to 5 and PREREG-B, latest `3dcb155`). This release does not change them.
