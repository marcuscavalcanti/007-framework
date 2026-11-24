# Evidence

## Errata and limits published for 1.11.0

Appended on 2026-11-24. No published result file is edited: each frozen report keeps its text and verdict, and these notes
say what changed and why. The controls below ran at zero model cost. Their records stay in the maintainer's files because
they hold host paths; the figures here are copied from them and were checked against their result files. They are the
records of one maintainer, and models of one family wrote and reviewed them; the digests below commit to their content
without making it checkable here.

| Record | SHA-256 |
|---|---|
| First control, `PREREG-CC.md` | `67cf3840cd197667e4ef8cf4992cdeac174850ed35fdc932837b873ab98daf5d` |
| First control, pre-registration ledger | `477504afc99d0399d6742d62b11155a12a8425291c78de1f848c4e6aba5c2cff` |
| First control, `RESULT-CC.md` | `06f356116e22dfa23abc46707770dfde9a7d62ba9f81f1e5e91e074b62c5afef` |
| First control, `cc-result.json` | `91124ab4b10adb073c4fdec18c5029f9965b97debc2cab24f56eaf44a0946167` |
| Second control, `PREREG-CC2.md` | `fdd81ed4cd05dbc1ba7e32593a79ee248f668cb6518d306af600f11feb36f445` |
| Second control, pre-registration ledger | `55e5e9ae94c71a144593191e261aca8bf5ed0d38c84f414780e376d5477a3ebf` |
| Second control, `RESULT-CC2.md` | `5ed2146313f68b313d6d34d3f8f4898aad256f6d4201d72e1ef3272a0da368be` |
| Second control, `cc2-result.json` | `bfa5b938eee70ae1fb60bd5415429bafb482a63ab777134fa2b2e95ce3383105` |
| Version-binding rerun, `equiv.json` | `479b24d762fa2f6e0ce6bcb06e54fedc0efe8fc19e2ce192a321db411fb9f0ad` |

### The arms were not blind through 1.10.1

Until 1.11.0, the agent's working directory was `007-<task>-<arm>-r01-<random>`, and the runner receipt path in its arguments
named the arm too. Study F's retained streams confirm it: their working directory reads, for example,
`007-GJ-8469AAC2-xhigh-r01-…`. So in every replay comparison run with 1.10.1 or earlier, the Codex top-up, the Claude 10-point
replay and Study F included, an agent could read `medium`, `high` or `xhigh` in its own path. That is a difference between
the arms beyond the requested effort the studies meant to compare. Its effect on the agents' behaviour was not measured;
there is no basis to say it changed a result or that it did not. Since 1.11.0 the agent sees a salted token instead of the
label ([blind arms](lab.md#blind-arms-what-the-agent-sees)). A replication of Study F, and any new study, should run blind.

### First calibrated control of Study F's rule: NOT-CALIBRATED

A pre-registered positive control (2026-11-23) took Study F's own grades (41 go-json tasks, two attempts per arm, Claude Opus
5.5 `medium` against `xhigh`) and planted a true loss by replacing `medium` attempts with the grade of an empty patch: one
attempt at a time (independent loss) or both attempts of a task together (clustered loss). Study F's rule, floor 2.2315, read
each of 4,000 bootstrap replicates per scenario (400 for power). Wilson 95% intervals:

| Item | Criterion | Measured | Passes |
|---|---|---|---|
| C1, `PROVEN` at the margin, independent loss | ≤ 132/4,000 | 81 = 2.03% (1.63–2.51%) | yes |
| C1b, `PROVEN` at the margin, clustered loss | ≤ 132/4,000 | 140 = 3.50% (2.97–4.12%) | **no** |
| C4, `KILL` at the margin | ≤ 132/4,000 | 78 = 1.95% | yes |
| PW1, `PROVEN` at a true loss of 10 points | ≥ 320/400 | 226 = 56.5% (51.6–61.3%) | **no** |
| PW2, `KILL` at a true loss of 40 points | ≥ 3,200/4,000 | 3,798 = 94.95% | yes |

The label was NOT-CALIBRATED: under a clustered loss the rule promised 2.5% and gave 3.50%.

**Corrected mechanism.** The control's first reading blamed the missing-data guard (L2). That was wrong. The control's "loss"
replaces a valid cell with another valid grade, so nothing is missing apart from Study F's one invalid cell, and L2 changed no
verdict in either loss model. The cause was the critical value (`proven_critical`) and Study F's floor, which was built with
it: both simulated a loss of the margin as attempts that fail independently. A clustered loss has half as many independent
loss units (41 tasks instead of 82 attempts). The standard deviation of the mean difference rose from 0.047 to 0.066, the
per-task differences became more skewed, and the 97.5% point of the statistic rose from 2.18 to 2.44. The floor, 2.23, sat
between the two and decided 128 of the 140 false `PROVEN`. 1.11.0 simulates both loss models and keeps the larger critical
value, and the floor rebuilt the same way is 2.4768 ([PROVEN under a clustered loss](lab.md#proven-under-a-clustered-loss)).

### Second calibrated control, of the corrected rule: CALIBRATED-UNDERPOWERED

A second pre-registered control (run 2026-11-24, one attempt, exit 0) tested the corrected rule with the rebuilt floor
2.4768209601363016, on the 1.11.0 candidate's `scripts/` tree `4fae7b3f8df4d2569f324fdcfbf23de5e79dd9c8`. It used new seeds
and two data worlds: F, Study F's grades as in the first control; and H, held out, a world built from the Codex go-json
top-up (`medium` against `high`, the same 41 tasks, two attempts drawn per arm), whose sessions and receipts share none with
the pools the floor came from. It added a partly clustered loss (ρ = 0.5). Gates at the margin, 4,000 replicates each, Wilson
95%, each read by its pre-registered band:

| Gate | Scenario | Count | Wilson 95% | Reading |
|---|---|---|---|---|
| C1 | F, independent loss | 56 = 1.40% | 1.08–1.81% | at or below the nominal 2.5% |
| C1b | F, clustered loss | 91 = 2.27% | 1.86–2.78% | compatible with 2.5% |
| C1p | F, partly clustered loss (ρ = 0.5) | 78 = 1.95% | 1.57–2.43% | at or below the nominal 2.5% |
| H1 | H, independent loss | 50 = 1.25% | 0.95–1.64% | at or below the nominal 2.5% |
| H1b | H, clustered loss | 91 = 2.27% | 1.86–2.78% | compatible with 2.5% |
| C4 | `KILL` at the margin, F | 78 = 1.95% | 1.57–2.43% | at or below the nominal 2.5% |

The control read the rule the way `report --missing-data-guard` reads it with `compare.critical_floor` set
(`guard_decision` with the floor); a plain `report` ignores the floor and was not tested. The CLI has no command that runs
the control.

Interval coverage over the band from −30 to −10 points passed (mean 94.84%, every point at least 94.00%), as did the code
checks (no `PROVEN` at −30 points in 4,000; A/A equality rejection 1.37% and 1.81%) and PW2 (`KILL` at −40 points in 3,777 of
4,000, 94.42%). **PW1, the power gate, failed:** at a true loss of 10 points, inside the 20-point margin, `PROVEN` is the right
answer, and the rule gave it in 228 of 400 replicates, 57.0% (52.1–61.8%), against the 80% required; the other replicates
read `NOT-PROVEN`, which is inconclusive, not a detected loss. Detecting a loss beyond the margin is `KILL`'s job: 94.42% at
−40 points (PW2, passed) and 1,737 of 4,000 = 43.4% at −30 points (reported, not a gate). A sensitivity reading that takes
Study F's archived grade for the one known flaky cell gave the same label.

The same corrected rule and floor read PW1's −10-point scenario twice, with different seeds, and the two runs differ by about
eight points. The difference follows the replicates' mean, which fell below the true −0.1000 in one run and above it in the
other, and it appears under the earlier rule too:

| | First control's seeds | Second control's seeds |
|---|---|---|
| Mean of the 400 replicates (truth −0.1000) | −0.1033 (SE 0.0020) | −0.0980 (SE 0.0019) |
| Rule before 1.11.0, `PROVEN` | 226 = 56.5% | at most 258 = 64.5% (statistic above Study F's floor) |
| Corrected rule, floor 2.4768, `PROVEN` | 196 = 49.0% (44.1–53.9%) | 228 = 57.0% (52.1–61.8%) |

So the power is between 49% and 57% in two runs of 400 replicates, 424 of 800 = 53.0% pooled (Wilson 95% 49.5–56.4%), against
the 80% required. PW1 fails on any reading.

Equal counts across gates (C1b and H1b both 91, C1p and C4 both 78, C4 78 in both controls) are coincidences: the seeds and
the statistic vectors of those gates are distinct.

What this licenses, and what it does not:

- **Error control, at Study F's shape only:** go-json, 41 tasks, two attempts per arm, a 20-point margin, loss of whole
  attempts, `report --missing-data-guard` with floor 2.4768. Under clustered loss the citable guarantee is "compatible with
  2.5%" (upper bound 2.78%), not "at most 2.5%".
- **Without the required power.** The power to read `PROVEN` at a true loss of 10 points is between 49% and 57%, not 80%.
  More tasks, not a lower floor, would raise it.
- **Not covered:** a plain `report` and any run without a floor (the floor decided every verdict; L2 demoted none), a loss of partial credit
  spread over a task's tests, missing cells that cluster, and any other number of tasks, repository, attempts per arm or
  margin. World H is fresh attempts of the same tasks and arms the floor's Codex pool came from: the favourable case for the
  floor, not a transfer. Monotonicity between the loss models is shown at one point (ρ = 0.5) only.

**Study F still reads `PROVEN` and `PAYS`.** Re-read deterministically from its 164 archived results, Study F's statistic is
10.841 in both readings. The corrected rule gives `PROVEN` against critical values of 2.512 and 2.482 (L2 also `PROVEN`, at
2.524); Study F's own rule, as published, gives `PROVEN` against 2.279 and 2.287.

### Study F's 95% interval covers about 92%

In Study F's regime (no planted loss), the published 95% interval of the reach difference covered the truth in 1,838 of
2,000 replicates in the first control (91.9%, 90.6–93.0%) and 1,832 of 2,000 in the second (91.6%, 90.3–92.7%). Read Study
F's interval, −3.0 to +4.7 points, as a roughly 92% interval.

### Version binding of the validated error control

The second control validated the decision code of the `scripts/` tree `4fae7b3f8df4d2569f324fdcfbf23de5e79dd9c8`. Three
files of `scripts/` differ between that tree and this release's: `effort_lab.py`, `cli_telemetry.py` and `native_runner.py`.
1.11.0 changed `effort_lab.py` again (how a Claude usage limit is refused and requeued, and how `report` reads an arm with no
valid cell), so the released file is not byte-identical to the validated one and the binding by identity does not hold. The
functions the control exercised (`proven_critical`, `whole_loss_draws`, `guard_decision`, `missing_data_guard`, `_reading`,
`_paired`, `studentized`, `false_proven`, `aa_check`) are unchanged, and no module constant changed.

The binding was therefore measured, not argued. The frozen control, changed only in the line that picks the scripts
directory, was rerun with the `scripts/` tree of this release (`2f83d292cdaf145017140eab87b661fbfdc24b09`) on the same inputs
and seeds, and compared with the validated run's stored result, value for value and bit for bit in floats:

| Part | Compared | Result |
|---|---|---|
| Rebuilt floor | all of it | identical (2.4768209601363016) |
| Coverage grid | 37 points × 2,000 replicates | identical |
| A/A check | 2 arms × 100,000 draws, twice | identical |
| Prescreen of the ten rule runs | all 29,200 replicates | identical; the same 979 reach the decision rule |
| Decision rule (critical values under both loss models, verdict, missing-data guard) | all 979 replicates | 979 of 979 identical |
| Re-read of Study F under both rules | all of it | identical |
| End-to-end gate on four realizations of Study F's results directory | all of it | identical |

A negative control, the same scripts with the clustered loss model removed, was caught in 10 of 10 replicates checked. Not
rerun: the control's sensitivity analysis (597 replicates of the same rule on inputs with one cell replaced).

What 1.11.0 changed sits upstream of the decision (which refused cells are set aside and requeued in a live run) and in a
report override that applies only when an arm has no valid cell, a case the control never produced; the control does not
exercise those paths. The comparison holds for that `scripts/` tree only: a release whose `scripts/` differs needs it again.

### Incremental value

007's incremental value over a well-informed user of the same native CLI is not demonstrated. The paired study below found no
detectable effect of invoking the skill, and no study yet compares the product as a whole with that baseline.

## Release claim of 1.5.1 (historical)

The 1.5.1 working candidate has a [local deterministic admission-fence
contrast](../evidence/v1.5.1/release-evidence.md): two sanitized structural cases,
36 cells, zero invalid. Only the controller acceptance-contract binding changes
between arms. NEW prevents the six observed false approvals, preserves six
correct controls and leaves six verifier-unavailable starts unresolved rather
than verified. Earlier inconclusive runs remain public. This is mechanism
evidence, not a new model, ROI, portability or durability claim. Stable release
qualification and publication are still pending.

V1.4 is a usable, dependency-free causal beta with one real-task causal ROI
contrast, one deterministic selector-mechanism contrast, and package checks.

It is not a claim that the complete bundle is generally superior or replaces
code review in full. Deterministic conformance alone does not establish causal
delivery-quality gains. Repeated runs of one task do not add project diversity.
Initial acceptance does not establish durability; missing observations remain
unknown.

## V1.5.0 local stable-candidate boundary

The [stable candidate](../evidence/v1.5.0/release-evidence.md) changes only
packaging metadata, documentation and package checks. Runtime and all historical
causal artifacts remain unchanged. The RC commit passed 148 tests and compile
on Linux Python 3.11/3.13 in CI attempt 2 and Python 3.12 in attempt 3.
That is RC compatibility evidence, not CI on the final stable bytes.
Two RC reviews and one prepared-stable review returned reject. The public
[review record](../evidence/v1.5.0/adversarial-review.json) preserves their final
answers and the hash-bound counterproofs of the key-absence/test-reporting claims;
no approval is inferred. The subsequent provenance-only overlay is not externally
reviewed. No stable commit, tag or publication is claimed. Local package checks
remain separate from historical causal results and establish no economic gain.

## V1.5.0-rc.2 candidate boundary at preparation time

The candidate packages acceptance/cleanup and explicit unavailable-cost support
already present in source a3012ee. It changes no execution code. The public
[candidate evidence](../evidence/v1.5.0-rc.2/release-evidence.md) preserves a
preregistered local mutation contrast for the first-shutdown-signal latch:
CURRENT passes the target 3/3, the one-line MUTANT fails it 3/3, and an allowed
control passes in both arms. All 12 cells match with zero retry or model calls.
The public artifact now includes the exact mutant patch and observed assertion
messages verified against original log digests. These additions make the narrow
mechanism reproducible; they are not a new economic experiment or independent
timestamp attestation of the historical preregistration.

This supports that mechanism in the observed host conditions, not economic
ROI, cross-platform cleanup, resistance to same-user tampering or universal
review accuracy. Repeated process-test verdicts are reproducible; scheduler
timing is not mathematically deterministic. The new candidate is not externally
reviewed or published, and supported-version CI is not yet observed.

## Causal ROI result for v1.4.0

The real historical `register-projects` task ran three times per arm from the
same source snapshot. The task, harness, served model alias, tools, timeout,
hidden acceptance, pricing and serial controller were held constant; reasoning
effort was the only changed policy variable. `xhigh` and `medium` both passed
3/3, with requested-versus-served identity verified in all six cells. `medium`
reduced estimated cost per accepted task by 42.6%, wall time per accepted task
by 53.9%, total tokens by 42.7%, and median changed lines by 24.2%. Per-cell
cost and wall-time arrays are public so three-replicate dispersion remains visible.

This supports the minimum-intelligence mechanism for one task and run window.
It does not establish task-class generalization, cross-provider portability,
dynamic routing, or D7/D30 durability. Cost uses the frozen rate-card estimate,
not provider billing. The sanitized result and source hashes are in
`evidence/v1.4.0/causal-roi-result.json`; the earlier weaker secondary result is
preserved in `causal-roi-secondary-result.json`.

A later seven-task bank stopped after the first task because both arms passed
0/3 and the frozen protocol conflicted with the grader's precedence. Its six raw
cells remain valid observations, but no quality, economic, or policy conclusion
is permitted. The remaining 36 cells were not run. Public disposition and
provenance are in `phase-zero-v16-inconclusive.json`.

The new task-start selector also passes an 18/18 deterministic OLD×NEW mechanism
test. It preserves a cheap eligible route and rejects that route when synthetic mature
receipts show a quality regression or incomplete cost telemetry. This proves the
selection branch only, with synthetic receipts and zero model calls. It does not
certify automatic serving or cross-project learning; protocol and
result are in `evidence/v1.4.0/`.

## Observed frozen result

In a frozen OLD×NEW mechanism test, both arms received the same coding task,
repository snapshot, executor class, effort, environment, and hidden acceptance
rule. The NEW arm added the target doctrine; the OLD arm did not.

| Arm | Accepted |
|---|---:|
| OLD | 0/3 |
| NEW | 3/3 |

This descriptive 3×3 contrast is consistent with the pre-registered mechanism
hypothesis. With one task and three runs per arm, it cannot establish causation,
an effect size, or generalization. The source record remains private because it
contains hidden test material. S1 verdict SHA-256:
`722142ebbd38a216f9f84c66520bd2a8dc38c2f6baf08888e808b4ba15264610`.
S1 summary SHA-256:
`6178e407a3cd482c618545538b21062700f29397e077035a2b7783a10f2a318c`.

## Compatibility result

A separate real-task compatibility case accepted both OLD and NEW in 3/3 runs.
Median patch size was 130 lines for OLD and 95 for NEW; median wall-time ratio
NEW/OLD was 1.034. Model, effort, and token telemetry were unmeasured, so this
does not isolate a causal quality or cost effect. Sanitized report SHA-256:
`a0378afa772c12a40fd86b62659a9e952048744a87f497f4db6abbd5127eece1`.

## Paired study of the skill

A later study compared the same task with the skill invoked and with the skill disabled, on 31 tasks mined from three public
repositories (ponytail 19, lz4 11, go-cmp 1), one pair per task for each of two agents (Claude Opus 5.5 at medium, Codex
gpt-6-astra at high). Commit-derived hidden tests graded every patch. The analysis and decision rule were written before the
first agent ran and hashed locally; that record is not independently timestamped and was not committed to this repository
before the run. Its SHA-256 is `310f98ed379f6852d6e7d3d2123d13f410f77ae94de2315d2640c3827d03e2fc`.

| Agent | Accepted with the skill | Accepted without | Pairs only with | Pairs only without | Exact p |
|---|---:|---:|---:|---:|---:|
| Claude | 20/31 | 19/31 | 1 | 0 | 1.0 |
| Codex | 21/31 | 19/31 | 2 | 0 | 0.5 |
| Both | 41/62 | 38/62 | 3 | 0 | 0.25 |

By the rule written before the run this is no detectable effect. That rule reads each agent on its own; the pooled row was
planned as a description. The study could only have detected a large effect: a verdict needed six discordant pairs on one
side for one agent, a difference of at least 19 points. The "Both" row pools the two agents' pairs on the same 31 tasks; its three
discordant pairs come from three different tasks. Upper limits of the difference, as exact binomial bounds on the favourable
pairs (97.5%, one-sided): about +13.5 points pooled, +17 for Claude and +21 for Codex (a bootstrap over pairs gives +11.3
pooled). The lower
limits are not informative because no pair went the other way.

A post-result audit left the verdict as it was and removed Claude's single favourable pair:

- 19 of the 31 tasks come from ponytail, which is also installed on the host as a plugin, and that copy already holds the
  commit 7 of those tasks ask for. The audit searched every arm's recorded tool calls for reads of that copy beyond the
  plugin's own skill file. It found two arms, one per agent and both with the skill: Claude's single favourable pair, and a
  Codex pair accepted in both arms. A read that left no trace in the recorded calls would not be found. The audit did not
  look for the two Go repositories in module caches, and did not examine network access.
- One lz4 task could not be passed by any patch. The reference-passes and base-fails controls run on all 31 tasks graded the
  reference at its own tree and did not see it; a control that applied the reference as a patch failed on that task.
- Without that task and those two pairs: Claude 19 vs 19 of 29, Codex 20 vs 18 of 29 (2 to 0, p 0.5). The same bounds are
  then about +12 for Claude (0 of 29) and +23 for Codex (2 of 29).
- Exploratory, with no interval and one run per pair: in that subset Claude's arms cost US$26.66 with the skill against
  US$23.42 without, for 19 accepted changes each. Codex reports tokens, not cost.

Limits: three repositories, one agent configuration each, effort held fixed (the lever the effort studies measure was off),
global host hooks active in both arms, no A/A run to size the noise, and no measured sensitivity for these 31 tasks' hidden
tests (by the lab's own rule an unmeasured oracle gives no information). The first grading pass was void (the grader was
called without its report variable and rejected everything); the saved patches were graded again, in series. The source
record stays private because it holds host paths. Result SHA-256:
`13b9532a4da3aae242ba41a8a04a841619d06d49761b3bde3dd68d342c293dd1`.

This does not contradict the 3×3 mechanism result above, which used one task built to exercise one rule. This study adds no
evidence that invoking the skill raises acceptance on ordinary tasks.

## Rejected mechanism

A proposed external-provider credential rule failed its target test and was not
included in V1. Terminal block SHA-256:
`5c57524d130d0f567f2cd5c10ba842be8f046557ddf8deb3a5dc50754e18d0e1`.
This is evidence that the
release gate rejected unsupported doctrine, not evidence that the framework is
provider-agnostic.

## Package verification

The installed causal beta was frozen with package SHA-256
`debc42fe6f3c7dbf75bc4ed86b3a8fe3d80f47e4b2ed98a4441723c7d806ee1d`
and externally reviewed read-only by Opus 5/xhigh. Review receipt SHA-256:
`7496e9ab818548afdb48f730642f5bd1ce2dd71e13868987ab6c2dfc3f830430`.
The public V1 is a generalized, security-hardened derivative and has its own
release manifest under `evidence/v1.0.0/`.

## Authority-envelope mechanism

A public deterministic OLD×NEW flip-test exercised one terminal fence with two
negative controls. All six distinct arm-scenario outcomes matched and each was
reproduced three times: OLD accepted a reported denied execution,
NEW rejected it, and both arms continued accepting an allowed execution and a
denied action that was correctly blocked. Protocol and complete cell results are
under `evidence/v1.2.0/`.

This proves the reported-event gate, not complete or authentic event capture,
real-world rework reduction, or security without a sandbox.

The unreleased v1.2.0 follow-up closes missing and mismatched task-start bypasses.
A second frozen OLD×NEW test observed all eight distinct arm-scenario outcomes
as preregistered, each reproduced three times; see `evidence/v1.2.0/`. No v1.2.0 tag exists, so
these corrections amend the candidate rather than a released compatibility contract.

## Controller-observed authority mechanism

The v1.3.0 candidate replaces self-asserted controller provenance with a
supported `007 run --action` path. A preregistered deterministic OLD×NEW test
used three scenarios, two arms, and three clean-repository replicates: denied
action, allowed control, and caller provenance forgery. All 18/18 cells matched
their frozen expectation with zero retry and zero model calls.

- protocol SHA-256: `1dca9ad2211796aaea6475fa11eaa0b2ef63e1cf24eaed944c346c5110cf974f`;
- result SHA-256: `ab4fe0002ecb0a6b02bc745307ba6a0b86514cad6307bfc6b0471aedf5ec657a`;
- OLD: `be83a3f0075f5503f29f1a22023238065bf30985`;
- NEW treatment: `126eca0`.

An external Opus 5/xhigh review rejected two intermediate revisions and approved
the final correction delta with highest severity low. The review ledger,
including all context and source-result hashes, is stored at
`evidence/v1.3.0/adversarial-review.json`.

The flip proves that the supported NEW controller stops a denied subprocess,
preserves an allowed control, and rejects caller-supplied controlled provenance.
It does not prove resistance to same-user file tampering or that the complete
framework improves longitudinal productivity.

## Not proved

- provider/model portability;
- general productivity or quality superiority;
- 7-day or 30-day durability;
- production runtime behavior;
- accuracy of touch-rate without agent commit attribution;
- causal benefit of the complete framework bundle.
- task-class or cross-project superiority of the experimental route recommendation.
- incremental value over a well-informed user of the same native CLI.

## Product and release history

The [changelog](../CHANGELOG.md) records version-level capabilities. Each version under [evidence](../evidence/) keeps its qualification record and original claim limits. The historical V1 mechanism and v1.4 cost/time observations above retain their narrow scopes.

The [public README checkpoint at 1e9f3c1](https://github.com/marcuscavalcanti/007-framework/blob/1e9f3c1a85e10e4508ccd94c9d44a74cbeec6a77/README.md) preserves the earlier release narratives and evidence table. Current laboratory methods and frozen replay result links are collected in the [laboratory guide](lab.md#published-replay-evidence).
