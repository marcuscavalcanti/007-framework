# Amendment 7 to PREREG-PILOT (2026-11-12)

This amends PREREG-PILOT, PREREG-CONFIRM, PREREG-B and Amendments 1 to 6. None of them is edited.

**When it was pushed:** no pilot attempt had been dispatched (`results/` does not exist), and no arm outcome of this study existed.

## What was observed
- `prepare_pilot_v4.sh` built the 62-task set at 08:14Z and started `dry_run_v3.py`, which runs 4 jobs, each a full `go test ./...`.
- **The load log:** load averages rose to 666–869 (08:32Z–08:33Z, `load.log`).
- **The machine restarted** at about 08:34Z (uptime at 13:29Z: 4 h 55 min). The dry run had finished no cell. Its directory is kept as
  `dryrun3-attempt2/`.
- **The gate re-runs ran 3 jobs.** They held for hours at load averages of about 150 to 270 (machine: 18 CPUs, 64 GB).

A pilot at 4 jobs risked the same restart in the middle of paid attempts. Those attempts would be left without results, the run
would stop with `uncertain-attempts`, and that is an early stop.

## Change
**Every remaining run uses 2 jobs instead of 4:**
- the dry run (`dry_run_v3.py`);
- the pilot (`run_pilot_v4.sh`);
- the confirmatory blocks (`run_confirm.sh`);
- block B (`run_b.sh`).

The scripts are edited in place, and their new hashes replace the old ones in `SHA256SUMS`. The only change is `--jobs 4` →
`--jobs 2`.

**Why the design holds:** jobs set how many cells run at once. They change no arm, task, attempt count, seed, cap or rule.
- Both arms are shuffled within each block, so both run under the same concurrency.
- The confirmatory time look compares the arms with each other, never against a fixed duration.
- Serial re-grades stay at one job (Amendment 5 (c), (e)).

**Effect:** wall time roughly doubles. The pilot (248 cells) takes about 10 to 15 hours.

## What does not change
Everything else in the pre-registrations and Amendments 1 to 6.
