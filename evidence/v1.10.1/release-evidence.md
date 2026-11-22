# 1.10.1 candidate: the lab grader's exit contract, and a reviewer route change

Prepared on 2026-11-22 from published 1.10.0. A public paired study (2026-11-15) had read 124 of 124 patches as rejected
because the grader failed; 1.10.0 made a grader failure exit 2, but a replay cell still recorded any non-zero exit as a
rejection. This release makes a cell tell a grader failure from a rejection, without turning a hung or crashing candidate
into an invalid cell.

- **Kind:** a patch release. No command, option or field is removed or renamed. Tasks mined by 1.10.1 carry a new field,
  `acceptance_exit_contract: "lab-accept-v1"`; tasks without it keep the 1.10.0 reading.
- **Behaviour that changes without an option:**
  - Under the contract a cell reads grader exit 0 as accepted, 1 and 3 as rejected, and any other exit as
    `acceptance-harness-error`, an invalid cell. The contract requires exactly one acceptance command and
    `acceptance_timeout_s` of at least 900, checked before any agent runs.
  - `lab_accept.py` exits 3, with no report, when a suite command does not finish (800 s per command, 860 s for one grade).
  - A suite result file that is cut, malformed, of the wrong shape or over 64 MiB, a `go test -json` stream past 64 MiB, or a
    command the candidate's tree made impossible to start, grades as no result (a rejection); `--collect` fails on them, so
    `mine` drops such a commit. A repository whose `go test -json` output exceeds 64 MiB can no longer be mined.
  - The grader's memory is bounded: output is dropped on arrival except the Go adapter's standard output.
  - The release reviewer for a Codex host is `gpt-6.2-astra` at `xhigh`; it needs a Codex CLI newer than 0.165.
  - Grading reads `hidden.json` and `baseline.json` before the suite runs, and only regular, UTF-8 result files.
- **Reach:** sets mined before 1.10.1 keep their embedded grader and the 1.10.0 reading until they are mined again.

## What each change answers

| Change | Observed failure | Test |
|---|---|---|
| Exit contract | a grader that crashed or could not start read as a rejection of the candidate (the 0/124 class) | `test_lab_oracle_error_is_invalid_but_candidate_rejection_is_valid`, `test_lab_contract_rejects_wrong_command_count_before_execution` |
| Exit 3 for a suite that does not finish | under the contract a hung candidate made the grader exit 2, an invalid cell that left its arm's denominator (review 2026-11-20, SHIP withdrawn by erratum) | `SuiteDeadline`, `test_a_real_exit_3_that_leaves_descendants_is_a_valid_rejection` |
| One 860 s deadline per grade | prepare plus suite could pass the cell's 900 s, so a hung candidate still ended invalid (review r2) | `test_one_grade_shares_one_deadline`, `test_a_prepare_that_hangs_exits_3` |
| Bounded output and result files | a suite that prints or writes without end exhausted the grader's memory | `test_output_that_never_stops_is_dropped_on_arrival`, `test_many_tiny_writes_are_kept_in_one_buffer`, `test_an_oversized_result_file_proves_nothing` |
| Cut or malformed result file is no result | the adapter raised, exit 2, an invalid cell where 1.10.0 rejected (review r1, r2) | `UnreadableReport` |
| Grader stopped past its deadline | round 4 of a lost branch: the wait did not count stopped time | `test_a_grader_stopped_past_its_deadline_exits_3_once_continued`, `test_no_wait_is_longer_than_one_second` |
| Reviewer route | the maintainer's decision; `gpt-6.2-astra` is refused on Codex CLI 0.165 | `tests/test_review_route.py` |

## Engineering evidence

- **Local suite:** 1,061 tests on macOS, Python 3.14.7, on a tree left unchanged during the run, after the last review fix
  and the version change. Three failed. Two are the real-Go tests: this Mac's Homebrew Go cannot build any package that
  imports `os`, and they fail the same way on 1.10.0. The third was a version pin left at 1.10.0 in `tests/test_package.py`;
  it was corrected after the run and that module re-run (25 tests pass).
- **CI:** pull request 27 passed its seven checks at `e3c0a2f`, the tree round 3 read plus its should-fix items and the
  version change (run 45043938278: 1,061 tests on Python 3.11, 3.12 and 3.13 on ubuntu and 3.13 on macOS, the three real-Go
  tests passing on ubuntu and skipped on macOS, which has no Go; CodeQL run 45043938291). The release notes carry the runs for the merge commit and the tag.
- **Independent review** (Claude Fable 5.2, `max` requested by the maintainer in place of the policy's `xhigh`, no tools, same
  family as the implementer by the maintainer's policy; identity level `verified` in every round):
  - **Round 1** on `daa051d`, US$11.17: FIX FIRST. Blocking: the output cap counted bytes, not memory (one object per read
    and per line, up to ~1.8 GiB under a 64 MiB cap); fixed with one buffer and stdout kept only for Go. Should-fix items
    closed: the stopped-grader test, exit 3 without reading a report, the tests placed after `unittest.main()`, exit 3 for
    every adapter, a stderr line, the deadline taken after spawn, a 60 s helper. One item was refuted in code (`outcomes`
    was already initialised). A cut result file raising in an adapter, an invalid cell where 1.10.0 rejected, was found by
    the implementer in the same area and fixed.
  - **Round 2** on `0ef5470`, US$10.60: FIX FIRST, "with B1 and the item-4 wording fixed, I would SHIP". B1, suite result
    files read whole with no cap and node's read outside the conversion; fixed with one bounded reader. Item 4, 800 s per
    command against the cell's 900 s; fixed with one 860 s deadline per grade and a refusal below 900 s. Should-fix items
    closed: a suite that finished while the grader was stopped, a start failure caused by the candidate's tree, wrong JSON
    shapes, the unreadable line and exit, the docs, a real exit 3 in a cell, a helper released in time, a hung `prepare`.
  - **Round 3** on `20bff78`, US$13.25: **SHIP**, about 80%, no blocker. Its should-fix items, taken before the tag and not
    reviewed again: the residual sentence (a memory limit or full disk that hits the suite reads as a rejection); start
    failures classified by `errno`, so a host refusing a fork stays a grader failure; "sets mined before 1.10.1"; result
    files read only when regular, from one non-blocking handle, bounded to 64 MiB + 1 byte and decoded strictly;
    `RecursionError` and non-string outcomes converted; the final wait re-reads the deadline every second; `hidden.json`
    and `baseline.json` read before the suite runs; the grade deadline cleared after each grade; the contract's timeout
    validated; test hygiene; and a kernel-independent test that no wait inside `_run` exceeds one second (the stopped-grader
    test discriminates on arm64 Linux, where three wait mutants fail, and not on macOS).
- The candidate was rebuilt on the maintainer's Mac after an earlier branch and its review texts were lost with a remote
  sandbox; the lost rounds' records were given to the reviewer, and one lost item ("report reading") was reconstructed, not
  recovered.

## Still open

- Exit 1 is read as a rejection without proof of a grade: an interpreter crash that exits 1 still reads as one (1.11).
- The suite shares the grader's user and process group: a suite that kills the grader, a shared memory limit or a full disk
  makes an invalid cell. The invalid budget surfaces it.
- The stopped-grader test discriminates only where `poll` restarts with the remaining time (seen on arm64 Linux); the
  one-second bound on every wait is tested on any kernel.
- The Go adapter's new read path ran here only against mocks and on CI's toolchain; this Mac's Go cannot build.
- Round 3's items were not reviewed again.

## What this release does not claim

- That the skill raises acceptance, or any value of 007; no study result changes.
- That sets mined before 1.10.1 grade under the contract.
