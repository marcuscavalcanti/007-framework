# Phase Zero diagnosis

Date: 2026-08-31
Status: superseded by the completed v12 task-local experiment and v16 inconclusive bank

## Authority

- Target definition: `docs/target-definition.md`
- Target-definition SHA-256: `c695e687cb870b1a6482a52af808e791dced1b92a07be4f9ffc8da8efe9c5841`
- Source controller commit used by both experiments: `08f9bf65ad62374d5e2170c438c199ee17a208be`
- Last public baseline in this branch ancestry: `0e6be2d3d04b9d17ad75fa84db0c06d276ef925c`

## Current verified state

The repository has a local task lifecycle, immutable terminal receipts, requested-versus-served fields, authority events, a multi-project observer dashboard, paired replay mechanics, and a quality-filtered route selector. It is not yet an end-to-end control plane: `007 run` invokes a command and requires that command to write a receipt; it does not execute the receipt's acceptance commands itself.

The replay runner does execute repository-native acceptance commands after the agent exits. However, its cell receipt currently records `served_model` and `served_effort` as `unmeasured`. Therefore it cannot support a causal claim whose treatment changes model or effort.

The original selector read receipts across every registered project. The v1.4
candidate correction scopes its experimental recommendation to the current
repository and labels that scope in machine output. It remains observational,
not certified online learning. Version strings still exist independently in
multiple surfaces.

## Current thesis evidence

The v12 experiment verified requested-versus-served identity in six cells and
isolated reasoning effort on one real task. Both arms passed 3/3; `medium`
reduced estimated cost per accepted task by 42.6% and wall time per accepted
task by 53.9% versus `xhigh`. This supports a task-local minimum-intelligence
mechanism only. The broader v16 bank is inconclusive after an instrument
precedence conflict and does not add a policy or economic claim.

## Existing primitives to preserve

- atomic and no-replace writes;
- `begin` / `run` / `record` lifecycle;
- authority block before subprocess execution;
- requested-versus-served distinction and honest `N/D`;
- explicit cost provenance;
- isolated git replay, seeded paired order, and stop-on-invalid-cell;
- repository-native acceptance commands;
- similarity diagnostics kept outside acceptance;
- standard-library-only core and SHA-256 manifests.

## Smallest useful experiment

Use one real repository and one narrow task class. Reconstruct multiple accepted historical tasks from their base commits, hide acceptance tests from the executor, and compare two frozen execution policies under the same harness, tools, context contract, timeout, and repository snapshots. Randomize within pairs, run independent replicas, include every attempt in cost and latency, and verify the identity actually served for every cell.

The experiment asks only whether the cheaper/faster policy is non-inferior on deterministic acceptance and measurable D0 for this repository and task class. It does not claim a universal best model, agent, provider, language, or architecture.

## Smallest patch sequence

1. Make the controller execute declared acceptance commands and derive the terminal gate result from observed exit codes.
2. Make experiment cells fail closed when the hypothesis requires served identity and that identity is absent or mismatched.
3. Freeze a minimal multi-task protocol, task snapshots, policies, margins, kill rule, schedule, and manifest.
4. Run the real cells without retry-to-pass and issue a deterministic kill/continue result.
5. Only after a positive thesis result, implement the smallest certified envelope and repository-local learned-state path needed for an actual beta.

## Explicit non-goals before a positive thesis result

No database, daemon, scheduler, event bus, generic DAG, model gateway, universal AST framework, shadow infrastructure, plugin platform, ML classifier, bandit, circuit breaker, or broad online-learning subsystem.

## Kill criteria

- A cell is invalid if a causal variable's served identity is unverified or mismatched.
- A failed required acceptance command cannot be overridden by cost or latency.
- Any treatment regression beyond the pre-registered non-inferiority margin blocks the claim.
- If the lower-intelligence policy does not reduce cost and/or latency among quality-qualified outcomes, stop governance expansion and report that the thesis was not supported.
- Invalid cells are reported and stop the run; they are never retried to pass.
