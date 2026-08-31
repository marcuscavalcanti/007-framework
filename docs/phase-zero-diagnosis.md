# Phase Zero diagnosis

Date: 2026-08-31
Status: verified current-state diagnosis; no thesis experiment has been run under this contract

## Authority

- Target definition: `docs/target-definition.md`
- Target-definition SHA-256: `c695e687cb870b1a6482a52af808e791dced1b92a07be4f9ffc8da8efe9c5841`
- Current candidate commit: `ec614b17a6884a73dcc607397b8d859abbe369f0`
- Last public baseline in this branch ancestry: `0e6be2d3d04b9d17ad75fa84db0c06d276ef925c`

## Current verified state

The repository has a local task lifecycle, immutable terminal receipts, requested-versus-served fields, authority events, a multi-project observer dashboard, paired replay mechanics, and a quality-filtered route selector. It is not yet an end-to-end control plane: `007 run` invokes a command and requires that command to write a receipt; it does not execute the receipt's acceptance commands itself.

The replay runner does execute repository-native acceptance commands after the agent exits. However, its cell receipt currently records `served_model` and `served_effort` as `unmeasured`. Therefore it cannot support a causal claim whose treatment changes model or effort.

The selector reads receipts across every registered project and applies fixed thresholds without a release-bound certified policy envelope or repository-local learned-state boundary. That behavior is observational routing, not certified online learning. Version strings also exist independently in multiple surfaces.

## Current thesis evidence

The strongest current result covers one frozen real coding task with three OLD and three NEW executions. Both arms passed hidden acceptance 3/3. NEW used 24.9% less retrospectively estimated USD and 21.5% fewer median added lines, while median wall time was 3.4% higher. This supports a narrow mechanism observation only. It does not establish task-class generalization, served-policy causality, routing superiority, provider portability, or realized durability.

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
