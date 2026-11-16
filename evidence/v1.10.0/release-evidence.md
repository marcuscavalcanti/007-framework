# 1.10.0 candidate: a second sensitivity operator, and three corrections to the lab's instrument

Prepared on 2026-11-16 from published 1.9.0, after a public paired study of the skill (2026-11-15) exposed two defects in the
miner and the grader, and an exploratory audit (Codex gpt-6-astra) exposed one in the sensitivity operator.

- **Kind:** a minor release. The one new option, `sensitivity --operator v2`, is off by default; `run` and `report` do not read
  its file. No command, option or field is removed or renamed.
- **Behaviour that changes without an option:**
  - `sensitivity` (v1) keeps the reference's binary and hunk-less blocks in every mutant, and makes no mutant from a one-hunk
    reference. `sensitivity.json` gains `operator`. A v1 number from 1.10.0 is not comparable with a 1.9.0 one without saying so.
  - `mine` also grades the reference patch the way a candidate is graded and drops a commit that fails
    (`reference-fails-as-candidate`, `next-reference-fails-as-candidate`, `AcceptanceHarnessError`). A mined set can be smaller.
  - `lab_accept.py` grades without `ACCEPT_REPORT`, and exits 2 (not 1) when the grader itself fails. A replay cell records
    any non-zero exit as not accepted, as before; only `mine` reads 2 as a harness error.
- **Reach:** a mined task embeds its grader and its hidden tests. Sets mined before 1.10.0 keep the old grader and may hold a
  task no candidate can pass until they are mined again.

## What each change answers

| Change | Observed failure | Test |
|---|---|---|
| v1 mutant keeps binary and hunk-less blocks | every 1.9.0 mutant lost them, which could fail a build and count as a caught defect | `tests/test_effort_lab.py`, the v1 mutant tests |
| `--operator v2` | a reduced patch can misapply; v2 reverts one unit in the reference tree by line substitution, with a construction control | `OperatorV2`, `OperatorV2Review` |
| `mine` grades the reference as a candidate | one of 31 mined public tasks (lz4) could not be passed by any patch: the commit renamed a Go test file and the reset brought the old one back | `test_the_reference_is_graded_the_way_a_candidate_is`, and the real task: rejected, with a passable task of the same repository kept |
| `lab_accept.py` without `ACCEPT_REPORT` | a study harness omitted the variable; the grader died on a `KeyError`, left exit 1, and 124 of 124 patches read as rejected | `test_grading_without_a_report_path_still_grades` |
| Grader exit 2 | the same class: a harness error read as a verdict | `test_a_grader_failure_exits_2_and_is_not_a_rejection` |

## Engineering evidence

- **Local suite:** 1,034 Python tests passed on a tree left unchanged during the run (macOS, Python 3.14.7), after the last
  review fix and the version change.
- **CI:** pull request 26 passed its seven checks at `758a3a0`, the tree round 3 read. The release notes carry the runs for the
  merge commit and the tag.
- **Independent review** (Claude Fable 5.2, `xhigh` requested, no tools, same family as the implementer by the maintainer's
  policy; identity level `verified` in all three rounds: the CLI reported `claude-fable-5-2` as the only served model).
  - **Round 1** on `dd77650`, US$4.19: FIX FIRST. B1, the grader created a temporary directory on every call, a regression
    under an exact environment; fixed. B2, "and nothing else" said more than the v1 code does; wording fixed. B3, a write
    through a symbolic link in v2; `hidden_target` already refused it, a test now shows it and links are never units.
  - **Round 2** on `cc62604`, US$3.55: FIX FIRST, B1 to B3 closed. N1, the interval cap added after round 1 applied only at
    all-or-none, so 19 of 20 rejected could pass a floor that 20 of 20 did not; the task bootstrap is now widened to the pooled
    Clopper-Pearson interval in every case. N2 to N6, changelog sentences the code contradicted; fixed. `passes` now needs an
    equivalent in a file the hidden tests load.
  - **Round 3** on `758a3a0`, restricted to the change since round 2, US$2.03: **SHIP**, no blocker. Its items, taken before
    the tag and not reviewed again: `equivalents_loaded` in the summary; the grader sets exit 2 before describing the error and
    prints its own deepest frame; tests for the `next-` drop label, `jobs` and a shebang; wording in the changelog,
    `docs/lab.md` and `docs/evidence.md`.

## Still open

- **v2 has no positive end-to-end test** for the classes `invalid`, `error`, `control-failed`, `operator-invalid` and
  `rejected-contract`. The mined-task drop is tested with a synthetic reset and a mock, and checked by hand on one real task;
  no fixture renames a test file.
- **v2 limits, listed in `docs/lab.md`:** no grade is repeated alone; the reference control grades at the reference's own tree;
  a mutant's visible run reuses its graded tree; comment detection does not know multi-line strings, Rust doc tests, cgo
  preambles or TypeScript directive comments; unit boundaries depend on the git version and on attributes; `trivial` ignores
  hunk-less changes, and one unit beside an unrelated binary is graded as valid.
- **v2's interval spans two quantities,** the mean of per-task rates and the pooled rate. Where task sizes differ much, the
  decision drifts to `indeterminate`, and `fails` can be out of reach.
- **`--no-indent-heuristic` was pinned late.** A `sensitivity-v2.json` written from this branch before `758a3a0` names other
  units under the same operator label; none was published.
- **`mine`'s new check runs once, under the mining load.** A reference that fails once is dropped with no retry alone.
- **`report` does not print the sensitivity operator,** and nothing reads grader exit 2 in `run`.
- **The 3.31% counter-example** in `docs/lab.md` has no public derivation.
- From 1.9.0, unchanged: the items under "Still open" in `evidence/v1.9.0/release-evidence.md`.

## What this release does not claim

- That v2 has been calibrated. No floor is fixed and no v2 number has been published.
- That the skill raises acceptance. `docs/evidence.md` reports a paired study that found no detectable effect, with its limits:
  a rule hashed locally and not committed here before the run, one void grading pass, and a post-result audit.
- That the tasks of sets mined before 1.10.0 are all passable.

## Not in this release

- A/A runs, read isolation for cells and an oracle-health line in the status: planned, not built.
- A README claims-table row for study F or for the paired study.
