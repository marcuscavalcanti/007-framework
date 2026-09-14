# Causal testing

## The question

Does one doctrine mechanism change the target behavior while everything else is
held constant?

## Minimal OLD×NEW flip test

1. Start from a real failure or costly correction.
2. Write a task that reproduces the decision, not the historical implementation.
3. Freeze the same repository snapshot, prompt, executor, model, effort,
   environment, timeout, and acceptance tests for both arms.
4. OLD receives the baseline doctrine; NEW differs by one declared mechanism.
5. Pre-register an integer seed, randomize arm order within each pair, record
   the realized order, and run at least three pairs for a mechanism probe.
6. Apply hidden acceptance tests only after the agent exits.
7. Pre-register pass, block, invalid-run, and early-stop rules.
8. Report every valid and invalid cell; no retry-to-pass.

A mechanism flip supports only that behavior in those conditions. It does not
prove general productivity, provider portability, production durability, or a
full framework bundle.

## Served identity

When provider, model, or effort is a causal variable, set
`require_served_identity: true`. The frozen adapter receives the
`{runner_receipt}` placeholder and must write a no-retry structured receipt:

```json
{
  "schema": "007-framework/runner-receipt/v1",
  "valid": true,
  "requested": {"provider": "openai", "model": "model-a", "effort": "medium"},
  "served": {"provider": "openai", "model": "model-a", "effort": "medium"},
  "identity_source": "provider-structured-response",
  "source_sha256": "<sha256>",
  "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
  "cost_usd": 0.01,
  "cost_source": "rate-card-estimate"
}
```

The adapter owns provider-specific parsing; the replay core only validates the
provider-neutral receipt against the pre-registered policy. Missing identity,
an adapter-invalid result, or requested/served mismatch invalidates the cell and
stops the run. A requested CLI flag is not served-identity evidence. The agent
command, the acceptance commands, and the replay's own Git helpers each run in
their own session; when a command returns, by exit, failure, or timeout, every
remaining member of that group is killed and observed gone before the result
is interpreted. The controlled waits total up to two seconds; the OS may keep
a group observable beyond that. If cleanup is not confirmed, the cell is
invalid with `cleanup-child-unconfirmed` or `cleanup-group-observable` as its
failure class, acceptance is skipped, no Git helper starts (the cell records
`d0_complete: false` and the seven diagnostic fields as `unmeasured`, never
zero), the run stops before the next executor, and a timeout diagnostic
(`agent_exit -9`, `TIMEOUT`) is preserved. The runner receipt, if present, is
still read and hashed as a diagnostic observation; while cleanup is
unconfirmed its bytes are not stable evidence and its identity is not
consolidated terminal evidence. Services
that must outlive a command are not supported in these groups. A descendant
that starts its own session escapes that cleanup. The workspace is a fresh
snapshot export, not read isolation: the agent process can still read any path
the OS user can.

`usage` is optional. When absent or `null`, the cell records `usage` and
`tokens` as `unmeasured`; the cell stays operationally valid, which does not
satisfy any protocol that requires token telemetry. When present it must be an
object, otherwise the cell fails with `usage-invalid` and the run stops before
the next executor. The public counters are `input_tokens`, `output_tokens`,
and `total_tokens`: each, when present, must be a non-negative, non-boolean
integer; an explicit `null` is invalid and nothing is coerced. Every other key,
including provider-specific `*_tokens` names, is preserved verbatim and not
interpreted. The core never sums components, derives `total_tokens`, or checks
relations between counters; the cell's `tokens` is the observed `total_tokens`
or `unmeasured`. This validates structure only, not completeness, truthfulness,
or the meaning of a count across providers.

## Controls

Include a non-target control when over-correction is plausible. A pass should
require the intended OLD→NEW improvement, no NEW target failure, and no loss on
the control. Invalid telemetry or contaminated inputs invalidate the pair; they
are not evidence against either arm.

## Diagnostics are not gates

File overlap, Jaccard, line similarity, and resemblance to an accepted patch are
**diagnostic only** and **never an acceptance, review, or release gate**. They can
explain divergence; only task-specific executable acceptance checks decide
correctness.

## From mechanism to release

Mechanism flip → broader paired tasks → real held-out tasks → longitudinal
receipts. Promotion claims must stop at the strongest completed layer.
