# What each outcome leads to, fixed before the pilot (2026-11-12)

This file changes nothing in [PREREG-PILOT.md](PREREG-PILOT.md), [AMENDMENT-1.md](AMENDMENT-1.md) or [AMENDMENT-2.md](AMENDMENT-2.md).
It fixes, in advance, what each outcome leads to. It also fixes how the maintainer's question "is 007 viable?" is answered.

That question has four parts. No single result answers all of them, so each part has its own rule. The [revisions](#revisions)
section says when each version was pushed and what existed at that moment.

## 1. The instrument
The question: does the published study carry out a pre-registered study end to end without breaking its own rules? "The published
study" means the pinned 007 code and the scripts hashed in `SHA256SUMS`, operated by the maintainer.

- **Yes** if all of these hold:
  - the gate re-run's consistency check reproduces the recorded counts;
  - the dry run passes;
  - the pilot finishes without an early stop;
  - so does the confirmatory run, if there is one;
  - every step ran the hashed scripts on the pinned code;
  - no deviation from PREREG-PILOT, its amendments or the confirmatory pre-registration is found, either by the maintainer or by
    the review in part 5.
- **No** otherwise. The failed step is reported with its cause: the instrument, the provider or the budget.
- **A check that fails before any paid attempt** (consistency or dry run):
  - the fix goes into a new release and a new amendment, both pushed before the check is repeated;
  - part 1 is then judged on that release;
  - every failed check is reported with the answer.

  No arm outcome exists at that point, so repeating the check cannot favour either answer.
- **A failure after the first paid attempt is final.** No attempt is redone, the answer in part 5 is NO, and no later release reopens
  this question: this executor, this margin, these repositories.

**The corrected gate's denominator**, as the pinned code computes it (`effort_lab.sensitivity_summary` at v1.7.0, called by
`gate_rerun.py`):
- It counts only the mutants of tasks whose reference passed its first oracle in the parallel re-run.
- A task whose reference fails in the parallel run, or in its serial re-run, is reference-failed (Amendment 2, change 4).
- A repository whose corrected immediate sensitivity is below 30% leaves the pool before the set is built. The pooled task count
  and the expected cost are then recomputed from the remaining repositories.
- This paragraph was pushed before the re-run's output was read.

## 2. The thesis for this executor
The question: Codex `gpt-6.1-sol`, `medium` against `high`, margin 5 points on the reachable scale, on the pooled Go repositories.

- **NO-GO in the pilot:**
  - The reading is "not shown to be provable at 5 points with these repositories".
  - No confirmatory run follows.
  - No repository is mined for this question afterwards: it would be chosen after the yields were seen.
- **GO in the pilot:**
  - The confirmatory run follows the confirmatory pre-registration and analysis script. Both are hashed in `SHA256SUMS` before the
    first pilot attempt.
  - **Cost cap:** US$400 at list price.
    - At the top-up's mean cost the largest possible run is 86 tasks × 16 attempts × US$0.264 = US$363.
    - Before dispatch, the expected cost is recomputed as reaching tasks × 16 × the pilot's own mean cost per dispatched attempt.
      If that exceeds the cap, no confirmatory attempt is dispatched, and the answer is NO, with the budget as its cause.
    - The maintainer's standing authorization of 2026-11-12 covers spend up to this cap.
  - **Its end is reported as already agreed, whichever it is:** a failed sequence look, KILL, FUTILITY, NO-INFORMATION, PROVEN or
    NOT-PROVEN.
  - NOT-PROVEN never supports the thesis and never refutes it.
- **Early stop in the pilot:** nothing is frozen, and the next step goes back to the maintainer, as PREREG-PILOT says.

## 3. "In your own repository"
The question: can one repository, alone, reach a 5-point verdict, with 80% power if the arms are equal?

**The reading**, for each pooled repository, is done by `part3.py`, hashed in `SHA256SUMS` before the first pilot attempt. It
never enters GO / NO-GO.
- **Size:** the repository's reaching tasks in the primary freeze's `frozen-reach.json`.
  - Mined tasks are never used.
  - A repository with fewer than 8 reaching tasks cannot hold.
- **Noise:** `τ² + σ²/4`, with τ² the larger of the two estimates.
  - It comes from the confirmatory attempts, not from the pilot. The pilot's noise already decided GO, and two attempts per arm
    cannot tell τ² from zero.
  - It is computed both on every reaching task and on the repository's own tasks, and the larger value is used.
- **Critical value:** `max(2.198, c)`, with `c` simulated from the repository's own confirmatory cells. If it cannot be simulated,
  the repository does not hold.
- **It holds** if its size is at least `noise × ((critical value + 0.8416) / 0.05)²`.
- **Without a finished confirmatory run,** no repository holds. The pilot's `n80` is then compared with each size, as a description
  only.
- **Reported next to it, never deciding:**
  - a task-bootstrap 95% interval for each required size;
  - the required size if the true difference is −0.9 points, go-json's estimate;
  - each repository's own verdict;
  - the same reading at the break-even margin of [docs/lab.md](../../docs/lab.md), with its inputs taken from the pilot.

**The outcome:**
- **If no repository holds:**
  - the claim that one repository gives a 5-point verdict at this noise is withdrawn;
  - the documentation then says that one repository gives a bound (the guard reading), not a verdict;
  - any confirmatory claim is about the pooled set.
- **If at least one repository holds:**
  - the claim stands for repositories of that size, as "80% power if the arms are equal";
  - the size is stated in reaching commits, in mined tasks and in candidate commits;
  - next to it goes how many of the nine repositories mined so far have that size: these five, the three dropped for yield, and
    go-json.

**Candidate commits per repository,** from the mining log (`mine2/<repo>.out`), recorded before any pilot attempt:

| Repository | Logged | Kept | Too short | No red hidden test | Too many hidden tests |
|---|---|---|---|---|---|
| BurntSushi/toml | 78 | 25 | 40 | 13 | 0 |
| traefik/yaegi | 49 | 13 | 16 | 20 | 0 |
| pelletier/go-toml | 167 | 13 | 139 | 14 | 1 |
| pierrec/lz4 | 30 | 11 | 8 | 11 | 0 |
| klauspost/compress | 139 | 24 | 59 | 44 | 12 |

## 4. Adoption
No experiment answers this part.

- **Baseline on 2026-11-12:**
  - GitHub shows 0 stars, 0 forks and 0 watchers;
  - one unique visitor in the last 14 days;
  - 764 clones from 134 unique cloners in the same 14 days, against that one visitor. They are read as automation, and clones never
    count as adoption;
  - 007 has not been announced. That was deliberate: the announcement waits for a verdict.
- **The rule, counted from the announcement:**
  - **Viable as a way to adoption:** within 60 days, at least 3 people other than the maintainer open an issue or pull request,
    or publish a report, about running `007 lab` on their own repository.
  - **Not viable:** none do, and the repository had at least 500 unique visitors in those 60 days. With fewer visitors there is no
    verdict.
  - Between 1 and 2 is reported as such, with no verdict.

## 5. One answer: yes or no
The maintainer asked for a single answer, yes or no, to "is 007 viable?".

**What it is read as:** can `007 lab` settle what the README asks, with a pre-registered verdict that is decisive and robust? And is
one repository alone enough for that verdict? The README asks whether a lower reasoning effort pays for the chosen executor, against
a margin declared before spending.

**What it is not read as:** "the lower effort pays". A KILL answers YES here, and it kills that thesis for this executor.

**Scope, whatever the answer:**
- Codex `gpt-6.1-sol`, `medium` against `high`;
- 5 points on the reachable scale;
- five public Go repositories chosen by the maintainer;
- every run operated by the maintainer.

It says nothing about other executors, languages or margins, about private repositories, or about adoption. A NO reads "not shown",
never "shown not to be viable".

**YES** only if all three hold:
- **(a)** Part 1 is yes.
- **(b)** Part 2 is decisive and robust:
  - the confirmatory verdict is PROVEN or KILL, and the answer says which;
  - both robustness checks of Amendment 1 return the same category: the re-grade with the fixed evaluator, and the exclusion of
    repositories below 60%.

  Every other end counts as no:
  - NO-GO;
  - an early stop of the pilot or of the confirmatory run;
  - a failed sequence look (manipulation or time);
  - FUTILITY, NO-INFORMATION or NOT-PROVEN;
  - a robustness check that changes the category.
- **(c)** Part 3 holds for at least one repository. This is a projection from the confirmatory run's noise, not a verdict shown on
  one repository, and it is reported as such.

**NO** otherwise.

**The answer carries its reason**, one of:
- YES-PROVEN, YES-KILL;
- NO-INSTRUMENT, NO-STOPPED, NO-BUDGET, NO-GO, NO-SEQUENCE, NO-NOT-PROVEN, NO-ROBUSTNESS, NO-ONE-REPOSITORY.

**Adoption** (part 4) is outside the answer, because it cannot be observed before an announcement plus 60 days. So the answer is
about the evidence, not about the maintainer's goal.
- A YES reads "007 has a decisive, pre-registered verdict to announce".
- It never reads "007 is adopted" or "007 will be".
- Part 4 is reported next to the answer when its 60 days end.

**Expected answer, written before any outcome: NO**, most likely NO-ONE-REPOSITORY.
- At go-json's noise, the pooled `n80` at 5 points is 23 to 31 reaching tasks (32 in Amendment 1's smoke test).
- The largest pooled repository has 25 mined tasks, and on go-json 41 of 62 mined tasks reached.
- So part (c) is expected to fail, whatever part (b) shows.
- An adversarial review put YES at about 3% under this rule.

**Before the answer is given:**
- **Review:**
  - The answer and its evidence go to Claude Fable 5.2 at maximum effort, asked to refute it.
  - The evidence package holds:
    - this file;
    - the pre-registrations and amendments;
    - the hashed scripts;
    - the freeze and look outputs;
    - the per-cell tables;
    - the gate outputs.
  - The same model reviewed this rule and the plan. Its passes are not independent reviews, and the answer says so.
- **Error:**
  - An error counts as confirmed only when the hashed script, re-run on the same files, reproduces it.
  - A confirmed computation or rule-application error is corrected.
- **Disagreement:**
  - A disagreement about the rule itself does not change the answer.
  - It is reported next to the answer.
- **Fixed point:**
  - Before the first pilot attempt, this file may still be revised after an adversarial review of the rule.
  - Every revision is its own commit.
  - After the first pilot attempt, the file is fixed.

## Revisions
- **Version 0** (`e689040`, 2026-11-12T01:11Z) and **its yes-or-no rule** (`4eef568`, 01:13Z).
  - The corrected gate re-run was still running when they were pushed.
  - No pilot set existed, and no attempt had been dispatched.
- **Revision 1** (this commit): parts 1 to 5, after an adversarial review of the rule by Claude Fable 5.2 at maximum effort.
  - The review is `fable-rule-20261112` in the maintainer's records. Its result is summarised in Amendment 3.
  - When this revision was pushed, the corrected gate re-run had not finished: its output files did not exist.
  - No pilot set existed, and no attempt had been dispatched.
  - The fixed point moved from "the pilot set is built" to "the first pilot attempt". A set reveals no arm outcome, and the scripts
    this revision requires must be hashed before dispatch.
