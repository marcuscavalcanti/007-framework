# Amendment 5 to PREREG-PILOT (2026-11-12)

This amends PREREG-PILOT and Amendments 1 to 4. None of them is edited.

**When it was pushed:**
- the first gate re-run of klauspost/compress was still running;
- no second re-run had started;
- no pilot set had been built;
- no pilot attempt had been dispatched.

**Cause:**
- An adversarial validation of the post-gate plan, by Claude Fable 5.2 with `xhigh` effort requested. The served model was
  `claude-fable-5-2`, at US$1.97; the record is `plano-tese-20261112` in the maintainer's records. It found that the oracle needs
  four controls before any paid attempt.
- The maintainer's decision to follow that plan (2026-11-12): "siga o plano proposto até concluir".
- The reviewer shares the implementer's model family.

## Changes
**(a) Reference-failed is a union over every run.** A task is reference-failed if its reference fails in any run on the pinned
code:
- the first gate re-run (`gate-run1/`);
- the re-run used (`gate/`);
- the dry run.

`reference_union.py` only adds to `reference-failed.json`. This replaces Amendment 4, change 3, whose union covered only "the
re-run used".

**(b) The dry run checks the reference** (`dry_run_v3.py`, replacing `dry_run_v2.py`). Every cell that applied the reference, on
a task outside `reference-failed.json`, must be accepted.
- **Environment break:** a repository with 2 or more such failures, or 10% of its tasks, has a broken environment, and the dry
  run fails.
- **Fewer failures:** they join `reference-failed-dryrun.json`, and through (a) leave the primary freeze.
- **The plan's own rule, and why it was changed:** the plan asked for 100%. The threshold separates one unstable task, which (a)
  removes, from an environment that grades every task wrong. It is fixed here, before any dry run.
- **Sign check:** the primary freeze's `medium − high` mean must be negative. The design applies the reference to about 90% of
  `high` cells and about 80% of `medium` cells.
- **Serial check:** `regrade_serial.py` re-grades the first 2 valid cells of each repository. It must find no discordance.

**(c) Serial re-grade** (`regrade_serial.py`).
- **What it does:** after the pilot's freeze, it re-grades every valid pilot cell:
  - one cell at a time;
  - on a machine running nothing else the operator started;
  - with the evaluator embedded in its task;
  - through the same grading path (`replay_eval`: snapshot, candidate patch, hidden acceptance, acceptance).
- **Discordance:** a cell disagrees if any test of its task's frozen reach changes outcome.
- **Serial freeze:** the re-graded cells are frozen again, into `serial-freeze/`.

**(d) The decision** (`decide_pilot.py`).
- **NO-INSTRUMENT** if either holds:
  - discordance above 2% of the valid cells;
  - the primary freeze says GO and the serial freeze does not.

  Nothing paid follows.
- **Otherwise,** the primary freeze decides: GO or NO-GO.

**(e) The confirmatory robustness re-grade runs at one job.**
- PREREG-CONFIRM's re-grade with the v1.7.0 evaluator is `regrade_serial.py --evaluator pinned`.
- A serial re-grade with the embedded evaluator runs beside it. Each is analysed by `analyze_confirm.py`, and the category must
  stay the same in both.
- Together, they separate the evaluator from the load.

**(f) Load log.**
- Every minute, `load.log` records:
  - the time;
  - the load averages;
  - the three processes using the most CPU.
- Its SHA-256 is published with each result.
- At the start of the log the load averages were 76 to 150. The top processes were `fseventsd`, driven by the gate's temporary
  files, and a web browser. Background load that the operator did not start is recorded, not removed.

**(g) Order of the answer's reasons,** the first that applies:
1. NO-INSTRUMENT
2. NO-STOPPED
3. NO-BUDGET
4. NO-GO
5. NO-SEQUENCE
6. NO-NOT-PROVEN (with FUTILITY and NO-INFORMATION)
7. NO-ROBUSTNESS
8. NO-ONE-REPOSITORY

**(h) Erratum to Amendment 4.** Its "from about 02:30Z to 04:30Z" is wrong. The operator's test suites ran from about 02:15Z to
about 03:15Z: the yaegi re-run's result was read at about 03:15Z, and this amendment's context was written at 03:55Z.

**(i) What each decision leads to** (`after_pilot.sh`):
- **GO:**
  - the confirmatory run (PREREG-CONFIRM);
  - its block 1 (replicates 1 to 4) also serves PREREG-B. If block 1 does not complete, block B runs instead.
- **NO-GO:** block B (PREREG-B), capped at US$150.
- **NO-INSTRUMENT:** nothing is dispatched.

**(j) A/A** (`aa.py`), after the freeze:
- **Input:** the go-json top-up's `high` cells.
- **Method:** 2,000 random splits into pseudo-arms of 4.
- **Expected:** the 95% interval excludes zero in 3% to 8% of the splits. Outside that range, no verdict is announced as proof until
  the cause is found.

**(k) Scripts:**
- `regrade_serial.py`, `dry_run_v3.py`, `reference_union.py`, `decide_pilot.py`;
- `prepare_pilot_v3.sh`, `run_pilot_v4.sh`, `after_pilot.sh`;
- `build_b.py`, `run_b.sh`, `analyze_b.py`, `aa.py`.

`run_pilot_v4.sh` replaces `run_pilot_v3.sh`, and `prepare_pilot_v3.sh` replaces `prepare_pilot_v2.sh`. All of them are hashed
in `SHA256SUMS`.

## What does not change
- The arms, attempts, seed, margin and caps of the pilot and the confirmatory run.
- The GO / NO-GO formula, the floor and the confirmatory rules.
- Amendment 4's quiet re-run and its rule for an inconsistent repository.
- No repository is added, and none is mined again.
