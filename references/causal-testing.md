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
