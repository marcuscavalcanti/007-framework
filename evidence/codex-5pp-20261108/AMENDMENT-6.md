# Amendment 6 to PREREG-PILOT (2026-11-12)

This amends PREREG-PILOT and Amendments 1 to 5. None of them is edited.

**When it was pushed:**
- the quiet gate re-run and the first `dry_run_v3.py` had run;
- no pilot attempt had been dispatched: `results/` does not exist;
- no arm outcome of this study existed.

**Cause:** the dry run failed before any paid attempt, as designed (Amendment 5 (b)).

## What was observed
- **Quiet gate re-run of traefik/yaegi** (`gate/traefik_yaegi.json`, 04:22Z–08:06Z):
  - the old rule recomputed **47/68**, against the recorded **46/68**: still inconsistent, so yaegi leaves the pool (Amendment 4);
  - the first re-run, under the operator's load, had given 54/68.
- **klauspost/compress:** consistent in its first re-run, **69/103**. Corrected sensitivity 67%; one reference-failed task.
- **Build:** 73 tasks, from toml, go-toml, lz4 and compress.
- **Dry run (`dryrun3-attempt1/`):**
  - after 9 cells, the pinned runner raised `archive entry is not a regular file: testdata/Mark.Twain-Tom.Sawyer_linked.txt.gz`;
  - v1.7.0 refuses snapshots holding a symlink, a safety rule;
  - the exception ended the whole run, so most tasks never ran.
- **Check of every pooled task's base** (`git ls-tree -r`): all 11 pierrec/lz4 bases hold that symlink; no toml, go-toml or compress
  base holds any entry other than a regular or executable file.
- **What this means:** no lz4 cell could ever run on the pinned code. The 9 dry-run cells that did run are fake-CLI cells with no arm
  information.

## Changes
**1. A repository whose task bases the pinned snapshot refuses leaves the pool** (`build_pilot_v4.py`).
- **Criterion:** any entry of `git ls-tree -r <base>` other than mode 100644 or 100755.
- **Why it is fair:** it is mechanical, checked before any attempt, and blind to outcomes.
- **Effect:** pierrec/lz4 leaves. The pool is BurntSushi/toml (25), pelletier/go-toml (13) and klauspost/compress (24): 62 tasks,
  expected US$65 (4 × 62 × 0.264).

**2. The check is repeated** with `prepare_pilot_v4.sh`. It keeps the gate files, builds with `build_pilot_v4.py`, re-runs
`dry_run_v3.py` (the failed attempt is kept in `dryrun3-attempt1/`), then runs the reference-failed union.

**3. Part 1 of DECISIONS.md.**
- **What it counts as:** a dry-run failure before any paid attempt. It is fixed by this amendment and the build that removes the
  unrunnable repository. No release is needed: the pinned code is unchanged.
- **Reporting:** the failure is reported with the answer.

## For the product, not this study
- One cell's exception ends the whole `007 lab run`.
- A repository with a symlink cannot be replayed at all.

Both belong to 1.9.0: a failing snapshot should make an invalid cell, and a safe symlink should be materialized. Neither changes
this study.

## What does not change
- Everything in Amendments 1 to 5 not named here.
- No repository is added, and none is mined again.
