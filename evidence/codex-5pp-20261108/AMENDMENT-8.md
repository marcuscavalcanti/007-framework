# Amendment 8 to PREREG-PILOT (2026-11-12)

This amends PREREG-PILOT and Amendments 1 to 7. None of them is edited.

**When it was pushed:** no pilot attempt had been dispatched (`results/` does not exist), and no arm outcome of this study existed.

## What was observed
`dry_run_v3.py` ran from 13:30Z to 16:07Z at 2 jobs, without trouble.

**Eight of its nine checks passed:**
- 248 of 248 cells were valid;
- run and freeze exited 0;
- σ² > 0, with `n80` = 189 on 61 reaching tasks of fake data;
- every reference cell was accepted, with no environment break;
- the sign came out negative.

**The serial re-grade check failed.** Two of its six sampled cells disagreed: both cells of `COMPRE-03DE960A`, whose candidate patch
did not apply in the re-grade.

**The cause:**
- The patch holds 8 carriage returns (CRLF lines).
- `regrade_serial.py` read it with `Path.read_text()`. Python's newline translation turns CRLF into LF, so the patch no longer
  matches the files.
- `git apply` of the same bytes succeeds on a fresh snapshot (checked by hand).
- `COMPRE-03DE960A` is the only pooled task whose reference patch holds a CR.

**The same reading sits in the pinned 007 code.** `effort_lab.sensitivity` and `effort_lab.chain` read patches with `read_text()`,
at v1.7.0 and at v1.8.0. That explains why the gate re-run marked `COMPRE-03DE960A` reference-failed ("patch does not apply"). The
pilot's grading (`execute_cell`) reads no patch file and is not affected.

## Changes
**1. `regrade_serial.py` reads patches as bytes.** It decodes them with UTF-8 and `surrogateescape`, with no newline translation.
Its new hash replaces the old one in `SHA256SUMS`.
- **Checked before this amendment was pushed:** the corrected script, run on the same six sampled cells of the failed dry run,
  found 0 disagreements and nothing unapplied.

**2. The dry run is repeated in full** with the corrected script, in a fresh `dryrun3/`. The failed attempt is kept as
`dryrun3-attempt3/`. Its pass condition is unchanged.

**3. `COMPRE-03DE960A` stays reference-failed.** The union rule (Amendment 5 (a)) is blind and was fixed before this cause was
known, so the task stays out of the primary freeze, as already decided.

**4. Part 1 of DECISIONS.md:** this is a dry-run failure before any paid attempt, fixed by this amendment. It is reported with the
answer.

## For the product
`effort_lab.sensitivity` and `chain` read patches with newline translation in 1.7.0 and 1.8.0. A task whose patch holds CRLF looks
as if its reference does not apply. The fix belongs in 1.8.1: read patches as bytes. This study does not depend on it.

## What does not change
Everything else in the pre-registrations and Amendments 1 to 7.
