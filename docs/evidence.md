# Evidence

## Release claim

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
side for one agent, a difference of 19 points. The "Both" row pools the two agents' pairs on the same 31 tasks; its three
discordant pairs come from three different tasks. Upper limits of the difference, as exact binomial bounds on the favourable
pairs: about +13.5 points pooled, +17 for Claude and +21 for Codex (a bootstrap over pairs gives +11.3 pooled). The lower
limits are not informative because no pair went the other way.

A post-result audit left the verdict as it was and removed Claude's single favourable pair:

- 19 of the 31 tasks come from ponytail, which is also installed on the host as a plugin, and that copy already holds the
  commit 7 of those tasks ask for. The audit searched every arm's recorded tool calls for reads of that copy beyond the
  plugin's own skill file. It found two arms, one per agent and both with the skill: Claude's single favourable pair, and a
  Codex pair accepted in both arms. A read that left no trace in the recorded calls would not be found. The audit did not
  look for the two Go repositories in module caches, and did not examine network access.
- One lz4 task could not be passed by any patch. The reference-passes and base-fails controls run on all 31 tasks graded the
  reference at its own tree and did not see it; a control that applied the reference as a patch failed on that task.
- Without that task and those two pairs: Claude 19 vs 19 of 29, Codex 20 vs 18 of 29 (2 to 0, p 0.5).
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

## Product and release history

The [changelog](../CHANGELOG.md) records version-level capabilities. Each version under [evidence](../evidence/) keeps its qualification record and original claim limits. The historical V1 mechanism and v1.4 cost/time observations above retain their narrow scopes.

The [public README checkpoint at 1e9f3c1](https://github.com/marcuscavalcanti/007-framework/blob/1e9f3c1a85e10e4508ccd94c9d44a74cbeec6a77/README.md) preserves the earlier release narratives and evidence table. Current laboratory methods and frozen replay result links are collected in the [laboratory guide](lab.md#published-replay-evidence).
