# 1.8.1 candidate: fixes from the Codex 5-point pilot

Prepared on 2026-11-12 from published 1.8.0.
- **Kind:** a patch release. No command, option or field is removed or renamed.
- **New stop reason:** `rate-limit`. It is a planned pause, like `call-budget`.
- **New failure classes:** `controller-error:<type>` and `provider-rate-limit`.

## Changes under qualification
- **Patches are read as bytes** in `sensitivity` and `chain` (`read_patch`). Newline translation turned CRLF into LF, so a patch
  touching CRLF lines failed to apply. In the pilot this made one klauspost/compress task look reference-failed.
- **One cell's controller error is an invalid cell**, `controller-error:<type>`, never retried. Before, it ended the whole run: in
  the pilot's first dry run, one symlinked snapshot did that.
- **A provider rate limit pauses the run.** It no longer spends the invalid budget.
  - **What the controller does:** a call refused with `native-error-rate-limit` and no usage costs nothing, is labelled
    `provider-rate-limit`, is not counted invalid and is never retried. The run stops with `rate-limit`, writes no `STOP.json`,
    and a later run resumes.
  - **Why:** in the pilot, the provider refused every call for 7 minutes, and 1.7.0 ended the paid study with `invalid-budget`.
- **`--flag=/absolute/file` arguments are sealed** like bare absolute paths.
- **Documentation:**
  - an erratum to 1.8.0's list of new refusals;
  - a stage 2 over an unsealed stage 1 is not chain-checked.

## Engineering evidence
- **Local suite on the candidate:** 977 native Python tests passed and 54 JavaScript tests passed (2026-11-12).
- **New tests:**
  - a CRLF patch applies intact, and fails under the old read;
  - a raising cell leaves the run going and is not an orphan on resume;
  - a rate limit pauses the run, with no cost and no invalid count, and is not retried on resume;
  - a flag file is sealed and its change is detected.
- **Independent review** (Claude Fable 5.2, `xhigh` requested, same family as the implementer by the maintainer's policy):
  - on `bcb1a77`: identity `verified`, FIX FIRST with two blockers. A refused cell was charged 0 on receipt evidence alone, and a
    resume re-derived the exemption from the receipt. Both are fixed with tests: the cell is charged as any invalid cell, and only
    the live label exempts it. The should-fix items are fixed too: cooldown, refused counts, `chain` skip, lossless patches,
    `unsealed_files` by file, stderr diagnosis, truncated receipts.
  - The qualifying review of the final head and CI are recorded in the GitHub release notes.

- **Upgrade note:** a run sealed by 1.8.0 cannot be resumed by 1.8.1 (the 007 scripts are sealed). The tag's README still
  installs v1.8.0; a follow-up documentation change updates it.
- **Pilot evidence** cited here is at commit `17d309e` of branch `claude/pilot-amendment-2`.

## Not in this release
- **Detecting a load-sensitive oracle:** 1.9.0.
- **Materializing safe symlinks in snapshots:** 1.9.0.
- **A guard against `--jobs` oversubscription:** 1.9.0.
- **Measuring the explicit-environment effect (a 2×2 on yaegi):** pending.

## Causal evidence
None is asserted. The Codex 5-point pilot stopped early, NO-STOPPED with the provider as cause, and reported nothing about arms
(`evidence/codex-5pp-20261108/PILOT-REPORT.md` on branch `claude/pilot-amendment-2`).
