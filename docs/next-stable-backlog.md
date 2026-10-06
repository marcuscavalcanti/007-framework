# Next stable backlog

Status: implemented locally; stable-release qualification pending.
Owner: Codex coordinator. Target: 1.5.1, subject to final scope and release gates.
Base: v1.5.0, commit `460e98535752b18d1b4738babf8ad1f7d859d4a1`.
Scope: the existing dashboard, its tests, sanitized evidence and release docs.
No new dependencies, provider calls, receipt-schema version or workflow server.

## Product promise

Make verified engineering outcomes, correction pressure, all-attempt cost and
evidence gaps visible. Operational history is not a causal comparison. Passing
a project test is not proof that adopting 007 improved that project.

The dashboard should answer, in order: what was accepted; what required repair;
what is actually measured; which controlled comparison supports a gain; and
what remains unknown. Fewer tokens alone are not success.

## Release backlog, in dependency order

| Priority | Increment | Acceptance | Status |
| --- | --- | --- | --- |
| P0 | Honest operational dashboard | Read existing starts and receipts; distinguish open starts, accepted/blocked outcomes, declared/controlled acceptance and unknown telemetry. Do not turn local sessions into accepted outcomes or missing cost into zero. | Implemented; local checks |
| P0 | Correct the audited claims | Do not call an escape declaration verified D7 survival. Expose cost provenance and provisional/final accounting. Make route and aggregate denominators explicit and consistent where they claim the same metric. Distinguish terminal cost coverage from unresolved attempts. Never print verified identity when the artifact does not establish it. | Implemented; regressions pass |
| P0 | Clear product-value presentation | Separate operational outcomes, historical controlled results and unknowns. Show before/after, task, route, sample, pricing status and boundary together. The historical effort experiment must not appear to measure the selected project's current gain. | Implemented; desktop/mobile observed |
| P0 | Regression and rendered-UI proof | Preserve positive controls and the audited counterexamples: a just-completed receipt, provisional cost, failed attempts, an open start, missing data and zero verified causal cells. Missing evidence must remain visible. No new economic or durability claim. | 155 local/clean-source tests; 5 renderer tests; desktop/mobile observed |
| P0 | Focused deterministic mechanism experiment | Freeze the protocol below before execution. Publish actual outcomes, invalid cells and a narrowly scoped conclusion; never an expected-result table presented as observed evidence. | 36/36 valid; two earlier inconclusive runs preserved |
| P0 | Stable-release qualification | Complete local suite and UI checks, clean-source checks, an authorized independent review and exact-candidate supported-version CI. Freeze final bytes and manifest, inspect license/privacy, document rollback and obtain separate publication authority. | Pending all preceding gates |

## Additional proof proposal: prevent false approval without over-rejection

Question: for the same replayed candidate and claimed checks, does requiring
controller-observed acceptance prevent an incorrect approval while preserving
correct approvals? Reuse the existing acceptance contract and `007 run`.

1. Select one engineering failure from MoneyMouse and one from Coliseum.
   Verify each historical snapshot, defect and executable oracle before inclusion.
   Use sanitized domain-derived fixtures where the original contains private
   data; label those fixtures as derived, not as a replay of the private project.
2. For each case freeze a defective candidate and a correct positive control.
   The deterministic executor replays those artifacts; it does not call a model.
   Freeze the common runtime, candidate hashes, claimed receipt, independent
   grader, timeouts and expected classifications.
3. OLD uses agent-declared checks without a controller acceptance contract.
   NEW changes only that contract binding. Run the same independent grader
   after both arms; its result determines ground truth, not the claimed receipt.
4. Include a verifier-unavailable scenario. Unavailable verification is not an
   observed candidate defect, but it must never become verified approval. Check
   the applicable blocked/inconclusive/open-start behavior explicitly.
5. Pre-register pair order, a fixed seed, three reproductions per condition,
   stop rules and no retries. Deterministic repetitions establish reproducibility,
   not additional independent tasks. Record every invocation and invalid result.
6. Success requires at least one false approval under OLD, no false approval
   under NEW in the frozen defect cases, no NEW rejection of correct controls,
   and no verified approval when verification is unavailable. An invalid required
   cell leaves the experiment inconclusive rather than shrinking the sample.

This proves only the incremental admission-fence behavior in the frozen cases.
It does not prove better model-generated code, lower real rework or cost,
complete code-review replacement, provider portability or D7/D30 durability.
Measure false approvals and false rejections separately; do not invent USD ROI.
Existing pass/fail tests are reusable prerequisites, not a completed cross-project
experiment. See [causal testing](../references/causal-testing.md) and
[receipt semantics](../references/receipt-schema.md).

## Subsequent minor candidate: prospective capture

Only a backward-compatible new capability would justify a 1.6.0 target; more
tests or a larger sample alone do not require a minor version.

- Integrate and qualify the smallest host boundary using existing `begin`,
  `run` and `record`, rather than a new scheduler or general adapter platform.
- Capture controller checks, the verified candidate identity and measured
  terminal telemetry when the host actually provides them. Unknowns stay unknown.
- Confirm end-to-end behavior with real scoped tasks before claiming host/model
  support. Paid calls and external reviewers require their own concrete authority.
- Follow prospective D7 outcomes with incident/correction evidence and explicit
  missing follow-up. Elapsed time alone is not proof that no escape occurred.

## Historical reuse and exclusions

MoneyMouse receipts can contribute operational history now. Coliseum engineering
history can supply defect cases even where normalized receipts are absent.
Neither source may be backfilled with inferred cost, served model, first-pass
acceptance or causal gains. Deduplicate copied receipts and identify dependent
increments rather than presenting them as independent replications.

Keep raw financial/customer data, credentials and session transcripts out of the
public package. Do not rewrite historical receipts or frozen evidence, fabricate
past starts, delete stale registry entries, or mutate the other projects as part
of the dashboard release. Registry repair and host integration are separate work.
Do not wait for unavailable D7 evidence to fix the dashboard; display the gap.

## Version and authority boundary

1.5.1 is appropriate only while this remains backward-compatible correction of
the existing reporting behavior. Reassess the version if the implementation adds
a public capability or changes a contract. This backlog does not itself bump the
package version, qualify a release or authorize commit, push, tag or publication.
