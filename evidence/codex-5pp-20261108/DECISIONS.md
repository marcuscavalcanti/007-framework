# What each outcome leads to, fixed before the pilot (2026-11-12)

This file was written and pushed before any of the following existed:
- the corrected gate re-run's result (the re-run was still running);
- any pilot set;
- any pilot attempt or outcome.

It changes nothing in [PREREG-PILOT.md](PREREG-PILOT.md), [AMENDMENT-1.md](AMENDMENT-1.md) or [AMENDMENT-2.md](AMENDMENT-2.md).
It fixes, in advance, what each outcome leads to. It also fixes how the maintainer's question "is 007 viable?" is answered.

That question has four parts. No single result answers all of them, so each part has its own rule.

## 1. The instrument
Does `007 lab` carry out a pre-registered study end to end without breaking its own rules?
- **Yes** if all three hold:
  - the gate re-run's consistency check reproduces the recorded counts;
  - the dry run passes;
  - the pilot finishes without an early stop.
- **No** for this release otherwise. The step that failed is reported and fixed before any other step.

## 2. The thesis for this executor
The question: Codex `gpt-6.1-sol`, `medium` against `high`, margin 5 points, on the pooled Go repositories.
- **NO-GO in the pilot:**
  - The reading is "not shown to be provable at 5 points with these repositories".
  - No confirmatory run follows.
  - No repository is mined for this question afterwards: it would be chosen after the yields were seen.
- **GO in the pilot:**
  - The confirmatory pre-registration is written, pinned to a published 007 release, and pushed before its first attempt.
  - **Cost cap:** US$400 at list price.
    - The largest possible run is 86 tasks × 16 attempts × US$0.264 = US$363, so the cap never blocks a GO.
    - The maintainer's standing authorization of 2026-11-12 covers spend up to this cap.
  - Its verdict is reported as already agreed: PROVEN, KILL or NOT-PROVEN, whichever it is. NOT-PROVEN never supports the thesis.
- **Early stop in the pilot:** nothing is frozen, and the next step goes back to the maintainer, as PREREG-PILOT says.

## 3. "In your own repository"
Can one repository, alone, reach a verdict?
- **The reading:** the primary freeze gives `n80` from the pooled noise. Each repository's own number of reaching tasks is
  compared with it. This comparison never enters GO / NO-GO.
- **If no repository reaches `n80` alone:**
  - the claim that one repository gives a 5-point verdict at this noise is withdrawn;
  - the documentation then says that one repository gives a bound (the guard reading), not a verdict;
  - any confirmatory claim is about the pooled set.
- **If at least one repository reaches it:** the claim stands for repositories of that size, and the number of reaching commits it
  takes is stated.

## 4. Adoption
No experiment answers this part.
- **Baseline on 2026-11-12:**
  - GitHub shows 0 stars, 0 forks and 0 watchers;
  - one unique visitor in the last 14 days;
  - 007 has not been announced. That was deliberate: the announcement waits for a verdict.
- **The rule, counted from the announcement:**
  - **Viable as a way to adoption:** within 60 days, at least 3 people other than the maintainer open an issue or pull request,
    or publish a report, about running `007 lab` on their own repository.
  - **Not viable:** none do.
  - Between 1 and 2 is reported as such, with no verdict.

## 5. One answer: yes or no
The maintainer asked for a single answer, yes or no, to "is 007 viable?". The question is read as the README's thesis: whether a
lower reasoning effort pays for the chosen executor on your repository's replay tasks, against a margin declared before spending.

**YES** only if all three hold:
- **(a)** Part 1 is yes.
- **(b)** Part 2 is decisive: the confirmatory verdict is PROVEN or KILL. Both count, because each shows whether the lower effort
  pays. NOT-PROVEN, NO-GO and an early stop count as no.
- **(c)** Part 3 holds: at least one repository reaches `n80` alone. This is a projection from the pilot's noise, not a verdict
  shown on one repository, and it is reported as such.

**NO** otherwise.

**Adoption** (part 4) is outside the answer. It cannot be observed before an announcement plus 60 days. It is reported on its own
and never changes the answer.

**Before the answer is given:**
- The answer and its evidence go to Claude Fable 5.2 at maximum effort, asked to refute it.
- A computation or rule-application error that the primary data confirm is corrected.
- A disagreement about the rule itself does not change the answer: the rule is fixed here, before any outcome. It is reported next
  to the answer.
- Before the pilot set is built, this file may still be revised after an adversarial review of the rule. Every revision is its own
  commit. After the set is built, it is fixed.
