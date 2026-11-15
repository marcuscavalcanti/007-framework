# Amendment 4 to PREREG-PILOT (2026-11-12)

This amends PREREG-PILOT and Amendments 1 to 3. None of them is edited.

**When it was pushed:**
- the first corrected-gate re-run had finished for traefik/yaegi, and was still running for klauspost/compress;
- no pilot set had been built;
- no pilot attempt had been dispatched.

**Cause:** traefik/yaegi failed Amendment 2's consistency check. Amendment 2 sends that case to the maintainer, who had authorized
proceeding to the end (2026-11-12). This amendment fixes what happens next, before any re-run.

## What was observed
- **The yaegi re-run** (`gate-run1/traefik_yaegi.json`): pinned v1.7.0, embedded evaluator, 3 jobs.
  - Recomputed with the old rule, it gave **54/68** rejected mutants, against the recorded **46/68**: inconsistent.
  - **Reference-failed tasks:** 6 of the 13 failed their first oracle in the parallel run. All 6 passed when re-run alone. The
    recorded check had also counted 6 controls non-conformant.
  - **Corrected immediate sensitivity:** 25/32 = 78%, on the 7 tasks whose reference passed.
- **A deviation by the operator.** From about 02:30Z to 04:30Z, during this re-run, Claude ran this repository's full test suite
  several times on the same machine. That added CPU load the recorded check did not have.
- **A code difference on the grading path.** Since 1.7.0, `collect` gives the evaluator only the set's explicit `acceptance_env`.
  The recorded check's code (`46dd81f`) merged that environment over the parent process's environment. yaegi's set declares 11
  variables: `PATH`, `HOME`, `TMPDIR`, the Go cache and module settings.
- **What this means:** load, the environment change, or both can explain the extra rejections. One run cannot tell them apart.

## Changes
**1. No other heavy process.** From this amendment until the pilot's freeze, no test suite, build or other CPU-heavy process runs
on the machine during:
- a gate re-run;
- the dry run;
- the pilot.

**2. One quiet re-run, and then a fixed rule.**
- **What is re-run:** every repository whose first re-run is inconsistent is re-run once more, with the same code and parameters,
  under change 1 (`prepare_pilot_v2.sh`). The first re-run is kept in `gate-run1/`.
- **The check:** Amendment 2's consistency check applies, exactly as written.
- **If the second re-run is consistent:** the repository is pooled or not by its corrected sensitivity, as before.
- **If it is still inconsistent:**
  - the repository leaves the pool (`build_pilot_v3.py`), because its gate cannot be verified;
  - the pooled task count and the expected cost are recomputed;
  - no further diagnosis is run.
- **A repository consistent in its first re-run** keeps that result.

**3. Reference-failed tasks** are still the union over the parallel and serial runs of the re-run used (Amendment 2, change 4).
A task that fails only under load is reference-failed. It stays out of the primary freeze.

**4. Part 1 of DECISIONS.md.**
- **What this amendment counts as:** a consistency failure before any paid attempt, handled here.
  - This amendment is the fix.
  - Every failed check is reported with the answer.
  - A repository that leaves the pool under change 2 does not, by itself, make part 1 NO: the check did its job by keeping an
    unverifiable gate out of the pool.
- **Unchanged:** part 1's other conditions.

**5. Scripts.** `build_pilot_v3.py` is `build_pilot_v2.py` with only the change 2 rule. `prepare_pilot_v2.sh` carries out
changes 2 and 3, then the build and `dry_run_v2.py`. Both are hashed in `SHA256SUMS`.

## What does not change
- The arms, attempts, seed, margin and cap.
- The GO / NO-GO formula, the floor and the confirmatory rules.
- The 30% pooling gate and the 60% check.
- No repository is added, and none is mined again.
