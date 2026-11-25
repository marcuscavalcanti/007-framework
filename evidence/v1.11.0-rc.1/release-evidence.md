# 1.11.0-rc.1 pre-release: the lab's error control corrected and measured, blind arms, checks before spending

Prepared on 2026-11-25 from published 1.10.1. Package version `1.11.0rc1`, tag `v1.11.0-rc.1`. This is a **pre-release, not a
qualified stable release**: four rounds of independent review each returned FIX FIRST, and the fixes made after the fourth
round were not reviewed again. It is not activated as the stable version; 1.10.1 stays stable.

- **Kind:** a minor release candidate. No command, option or receipt field of 1.10.1 is removed or renamed. A run sealed by
  1.10.1 resumes only under the 007 that sealed it (`docs/lab.md`).
- **What changes:** see [the changelog](../../CHANGELOG.md) section `[1.11.0-rc.1]`. In short: the `PROVEN` critical value also
  simulates task-clustered loss, and a study floor is rebuilt for its own shape; `007 lab viability`, `run --aa` and
  `007 lab status` (read-only oracle health) are added; agents see salted tokens instead of their arm's label; a Claude usage
  limit is a quota hold, not an invalid cell, and a charged refusal counts once in its arm's cost; the README presents 007 as
  a measurement layer and publishes the errata.

## The decision rule's error control

- A pre-registered calibrated control of the corrected rule (zero model cost) passed every error-rate gate and failed its
  power gate (CALIBRATED-UNDERPOWERED), for one study shape (go-json, 41 tasks, two attempts per arm, a 20-point margin,
  whole-attempt loss) and only for `report --missing-data-guard` with `compare.critical_floor` 2.4768. Figures, scope and the
  records' SHA-256 are in [`docs/evidence.md`](../../docs/evidence.md).
- The control ran on an earlier `scripts/` tree (`4fae7b3f…`). Rerun with this pre-release's `scripts/` tree
  (`0fe9a537d25d9fe7997aa393ecb9f1ec8ed7117b`) on the same inputs and seeds, it reproduced the stored result exactly: rebuilt
  floor, coverage grid, A/A, the prescreen of 29,200 replicates, all 979 decision-rule replicates, the Study F re-read and the
  end-to-end gate (1,026 comparisons, 0 differences). The sensitivity analysis was not rerun.

## Engineering evidence

- **Local suite:** 1,168 tests, 0 failures, 0 skipped, on macOS with Python 3.14.7 and a cleared environment, on the
  candidate tree left unchanged during the run (version change included; this record and the version-binding text came after, and the doc-only
  test module was re-run). CI runs the real-Go tests on ubuntu.
- **Independent review:** OpenAI `gpt-6.2-astra` at `xhigh`, by the maintainer's decision in place of the policy's
  same-family reviewer (the implementation is by Claude Opus 5.5). No tools; identity level `pinned-no-reroute` in every round
  (requested model pinned, no reroute observed, served identity unverified).
  - **Round 1** on the full candidate: FIX FIRST, 18 findings (6 blocking): viability accepted one arm's evidence; charged
    refusals left the cost ratio; A/A qualified with no matched pair; a stream could be replaced at promotion; a test wrote
    the host environment to disk; the version-binding claim preceded its evidence. All confirmed in code and fixed with
    failing-first tests, except blinding, which was narrowed in the text.
  - **Round 2** on the fixes: FIX FIRST, 2 blocking (evidence read by path after the identity check; A/A qualifying on tasks
    with no reach) and 10 major. The approach changed under the product's own escalation rule: the manual oracle
    acknowledgement was removed, `status` made read-only, and promises aligned with the stated threat model (007 runs with the
    user's authority and isolates nothing).
  - **Round 3** on that delta: FIX FIRST, one blocking code defect (archived attempts counted by file, so a duplicate could
    hide a missing paid attempt) and claims the code did not meet.
  - **Round 4** on that delta: FIX FIRST, one blocking economic defect (an archived cost was not compared with the ledger's)
    and claims. The decision functions were found untouched in every round.
  - **Fixed after round 4, not reviewed again:** archived costs reconciled with the ledger (a mismatch withholds the economic
    answer); attempt numbers normalized and bounded without materializing ranges; an unusable results path is no reading;
    preparation failures report what was published; both task input files checked before any read; the wording on the
    foreign-task check, the interpreter-name heuristic, non-blocking opens and unchanged verdicts.

## Still open

- No SHIP verdict: the candidate is unqualified until a later review says SHIP.
- No CLI command runs the calibrated control; a plain `report` prints a verdict no control covered.
- The oracle alarm has no acknowledgement; an open alarm marks the report until it stops ringing.
- Blind promotion guards against collisions and accidents, not against a process with the user's authority. Other channels
  that can show an arm (model and effort flags, doctrine, timing) stay open and are listed in `docs/lab.md`.
- Viability does not count an attempt that left only an orphan receipt; an unsealed pilot is matched by task ids.
- The A/A discordance interval and the oracle-alarm thresholds treat observations as independent.
- Implicit recognition of `lab_accept` reads the interpreter's name, not a verified identity.
- Served model and effort are not verified.

## What this release does not claim

It does not show that 007 gives better or cheaper outcomes than a well-informed user of the same native CLI. Study F, the
only `PAYS`, predates blind arms and has no blind replication.
