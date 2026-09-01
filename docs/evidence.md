# Evidence

## Release claim

V1.4 is a usable, dependency-free causal beta with one real-task causal ROI
contrast, one deterministic selector-mechanism contrast, and package checks.

It is not a claim that the complete bundle is generally superior.

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
