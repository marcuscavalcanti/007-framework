# Architecture

007 Framework is a stateless instruction package. The coding-agent host executes
models and tools; the repository remains the source of truth.

```text
task + repo rules
       │
       ▼
scope and route ──► controlled execution ──► repository-native gates
       │                                         │
       └──────── declared proof ─────────────────┘
                                                 ▼
                                      receipt + rework sensors
                                                 │
                                                 ▼
                                      bounded doctrine experiment
```

## Components

- `SKILL.md`: compact operating contract loaded for coding work.
- `references/`: details loaded only when the task needs them.
- `scripts/harness_report.py`: aggregates existing task receipts.
- `scripts/touch_rate.py`: approximates attributable code survival from Git.
- `scripts/replay_eval.py`: runs frozen OLD×NEW policies against reconstructed
  historical source and task-specific acceptance commands.
- `bin/007` and `scripts/framework_cli.py`: initialize projects, atomically
  persist task starts, controller-observed action events, and terminal receipts,
  select a task-start route, and launch the local dashboard.
- `scripts/dashboard.py` and `dashboard/`: aggregate registered projects and
  serve a loopback-only, dependency-free control room.
- `scripts/local_activity.py`: normalize sanitized Codex, Claude, Kimi, and
  Gemini metadata/token deltas, reconcile Git worktrees, and cache unchanged logs.
- `scripts/headroom_pricing.py`: optional local worker using Headroom's LiteLLM
  model resolution and per-token pricing; it receives no transcript content.
- `tests/`: protects package identity, public boundaries, and script behavior.

## State model

The framework owns only local measurement state: a project marker, task starts,
controller events, and receipts under `.007/`, plus the user-level project registry at
`~/.007-framework/projects.json`. `007 init` excludes `.007/` through the local
Git exclude file, so telemetry does not dirty or alter repository history.
Durable engineering authority remains in Git, repository instructions, tests,
and task handoffs. Conversations and raw transcripts are temporary context, not
operational authority.

The browser polls a read-only aggregate snapshot every two seconds. The snapshot
derives one three-state objective verdict, seven literal gates, evidence
provenance, and a 30-day raw-count trend from the same project totals. The HTTP
server binds to `127.0.0.1` by default and exposes only allowlisted static and
JSON routes. Aggregate metrics are recomputed from raw project totals; project
percentages are never averaged. JSON receipts remain the source of truth. A
database is intentionally deferred until measured volume or query latency makes
the standard-library scan insufficient.

Known gate failures take precedence in the verdict even while a measurement
gate is incomplete; the primary action still prioritizes closing that data gap.
An invalid or unavailable source keeps the overall verdict not measurable
because the missing record can change the denominator; any failure among valid
records remains visible in its individual gate.
Controller blocks that prevent execution are authority events, not software
outcomes, and are excluded from the quality trend and model-telemetry
denominator.

The snapshot publishes `telemetry_fields` alongside the completeness numerator
and denominator so consumers can see that V1.1 measures provider, model, effort,
tokens, and wall time.

The experimental route recommender reads normalized receipts from the current
repository only. It filters by task class and exact served binding and returns one
deterministic recommendation before execution. It is observational, not a
certified runtime selector, and never starts the recommended command. There is
no daemon, gateway, database, background agent, or mid-attempt rerouting.

## Trust boundaries

1. **Host boundary:** authentication, model binding, permissions, and sandboxing
   belong to the agent host.
2. **Repository boundary:** native tests and policies outrank framework prose.
3. **Acceptance boundary:** hidden tests are applied after an experimental agent
   exits and are never placed in its workspace.
4. **Review boundary:** an external reviewer receives sanitized frozen bytes and
   cannot replace executable proof or human release authority.
5. **Evidence boundary:** receipts record measured values and explicit unknowns;
   they do not reconstruct missing telemetry.
6. **Cost boundary:** every new terminal receipt needs numeric cost, accounting
   source, and final/provisional state. Prices are supplied by the host or a
   provider adapter; the core contains no provider-specific price table.
   The host captures cost at the terminal execution boundary and normalizes it
   into the receipt. Headroom, RTK, provider CLIs, rate cards, subscriptions,
   and local compute are replaceable sources. Observed runtime activity may show
   a diagnostic estimate, but it never substitutes for the terminal receipt.
7. **Observation boundary:** local logs establish activity only. `007 begin`
   establishes the outcome denominator and
   `007 record` closes it. Work that bypasses `begin` remains explicitly outside
   what the dependency-free core can observe.
8. **Execution boundary:** `007 run --action` validates the bound authority
   before starting a CLI and is the only supported writer of `controlled`
   provenance. The adapter at the last execution boundary remains responsible
   for the normalized outcome and cost receipt. Exit code alone never proves
   quality or accounting. Local records are not a security boundary against a
   process with the same OS identity.

## Verified guarantees

Each guarantee below is an obligation with a scope, an existing mechanism, an
evidence artifact, and a residual limit. "Valid case" means a public test shows
the permitted path passes; "counter-proof" means a test or frozen protocol shows
the mechanism rejects the specific violation, or that removing the mechanism
makes the test fail. Where a column says *not demonstrated*, the state is
undemonstrated, not presumed green. Everything here is local synthetic
conformance on macOS with Python 3.14; it does not qualify a real provider,
another OS, or causal value.

A valid functional failure is evidence that the candidate does not meet the
exercised requirement; an invalid execution is not a functional verdict on the
candidate. Missing required proof prevents the claim that depends on it;
missing telemetry limits the claims that depend on it. These
distinctions describe evidence, not new receipt states. Exit status does not
establish verifier sufficiency, and a byte hash is a content fingerprint, not
authenticated attestation.

The valid case and counter-proof columns address acceptance and rejection,
respectively: rejection alone does not rule out over-rejection. Neither column
establishes that the verifier covers every relevant requirement.

| Guarantee | Scope and hypotheses | Mechanism | Valid case | Counter-proof | Residual limit |
|---|---|---|---|---|---|
| No execution without authority | `007 run --authority-file --action`; same OS principal is trusted | `run_task` checks the bound envelope before executor spawn; only writer of `controlled` provenance | `test_run_records_allowed_action_as_controlled` | `test_run_blocks_denied_action_before_subprocess`; frozen OLD×NEW protocol `evidence/v1.3.0/controller-authority-result.json` (reported 18/18): feature-level conformance of the new `run --action` lifecycle with one positive control, not a focal mutation of a single guard | Manual `begin`+`record` is `declared`; records forgeable by the same principal |
| Receipt bound to its task start | `007 record`; local files trusted | matching `.007/tasks/<id>.task.json` required, ids must agree | `test_record_requires_cost_and_writes_no_replace_receipt` | `test_record_rejects_receipt_without_matching_task_start`, `..._mismatched_task_id`; protocol `evidence/v1.2.0/task-start-binding-result-r2.json` (reported 24/24): historical comparison compatible with focal isolation (the public diff `fabc8f4`→`be83a3f` changes two guards), but the result binds no NEW bytes, so attribution is limited | No commit/tree hash inside the receipt yet |
| Receipt integrity and completeness | every terminal receipt | `validate_receipt`: required fields, finite non-negative numbers, cost accounted or explicitly unavailable under opt-in, computed provenance not caller-supplied; `write_json_no_replace` | `test_receipt_cost_unavailable_requires_opt_in_and_all_four_fields`, priced regression tests | `test_receipt_rejects_non_finite_tokens_and_wall_s` (focal mutation RED with `10**400`), `test_record_rejects_caller_supplied_controlled_provenance`, `test_record_rejects_unaccounted_cost` | No-replace is creation without replacement, not immutability |
| Served identity and usage structure | replay cells with `require_served_identity: true` | `validate_served_identity` fail-closed; `validate_usage` structural | `test_replay_cell_binds_standard_runner_identity_and_cost` | `test_replay_requires_exact_served_identity_when_policy_is_causal`, `test_replay_run_stops_on_invalid_usage_before_next_executor` | Structure only: no completeness, truth, or cross-provider meaning of counts; skipped without the flag |
| Workspace is a fresh snapshot; hidden acceptance stays out of it | replay workspace; no OS sandbox assumed; not read isolation | `git archive` export, regular files only; hidden acceptance copied into a separate workspace after the agent exits | `test_replay_extracts_regular_files_and_rejects_links` | `test_hidden_acceptance_rejects_workspace_escape`, `test_hidden_acceptance_is_hash_bound_and_restores_agent_bytes` | No read or network isolation: the agent process can read any path the OS user can |
| Executor, replay, and acceptance groups are cleaned before interpretation | wrapped coding command, replay agent, replay Git helpers, replay and controller acceptance commands; POSIX sessions | child in its own session; `killpg(SIGKILL)` when a command returns (exit or failure; timeouts for replay/acceptance); nonignored SIGTERM/SIGHUP/SIGQUIT during the wrapped executor wait latch the first signal and unwind through cleanup; subsequent scoped signals do not interrupt the cleanup body; inherited `SIG_IGN` is preserved; group observed gone within bounded waits before interpretation; otherwise `cleanup-child-unconfirmed` / `cleanup-group-observable` invalidates the cell (acceptance and Git diagnostics skipped; diagnostics recorded as `unmeasured`) or fails `007 run` with exit 2 after normal wait return; shutdown unwind instead reports the state to stderr and retains `128 + signal`, with no receipt | `test_run_replaces_claimed_checks_with_controller_observed_acceptance`; ignored-signal control: `test_run_executor_preserves_inherited_ignored_shutdown_signals` (exit 0/7); compatibility: `test_run_executor_remains_usable_off_main_thread` | timeout: `test_replay_timeout_kills_agent_descendants`, `test_run_acceptance_timeout_kills_descendants_and_blocks`; executor orphan: `test_run_executor_kills_descendants_before_interpretation` (base RED for exit 0 and 7); signal shutdown: `test_run_executor_signal_shutdown_kills_group_without_terminal_progression` (SIGINT is a control), `test_run_executor_restores_callers_signal_handlers_on_exit_or_exception`; repeated signal/non-gone: `test_run_executor_shutdown_cleanup_keeps_first_signal_and_reports_non_gone` (real groups; injected cleanup-entry signals and reported states); exit-0 orphan: `test_replay_run_kills_descendants_after_normal_exit`, `test_run_acceptance_kills_descendants_after_normal_exit` (base RED on the timeout-only implementation); states and no-advance: `test_run_executor_cleanup_failure_leaves_start_open` (authority event retained; CLI exit 2 after executor 0/7; gone controls), `test_cleanup_states_are_derived_from_bounded_waits`, `test_replay_cell_is_invalid_and_skips_acceptance_when_cleanup_unconfirmed`, `test_replay_helper_cleanup_failure_stops_before_agent`, `test_run_acceptance_cleanup_failure_exits_without_terminal_receipt` | A descendant that leaves the original process group (e.g. via `setpgid` or a new session) escapes cleanup; the wrapped coding command has no execution timeout; handler installation is main-thread scoped (other threads keep normal execution/cleanup); unknown C-installed dispositions are unchanged; SIGKILL of the controller cannot run cleanup; overlapping delivery before the latch is set, signals during spawn/restoration, a first shutdown signal during cleanup and interactive/TTY use are unqualified; replay/acceptance have no shutdown-signal forwarding; group IDs are not pinned against reuse; waits are bounded but the OS may keep a group observable; not general process termination |
| Public command is what the cell runs | replay sets | `agent_command` and arms come only from the frozen set; `summary.json` binds `replay_set_sha256`, seed, replicates | `test_replay_summary_binds_exact_set_and_replicate_count` | `test_replay_rejects_replicate_override_against_frozen_set`, `test_replay_requires_a_preregistered_seed` | The executor binary itself is not hash-bound |
| Acceptance is controller-observed | `007 run --acceptance-file` | argv-only contract hashed at task start; controller replaces agent-claimed `checks` | `test_run_replaces_claimed_checks_with_controller_observed_acceptance` | `test_run_persists_blocked_receipt_when_controller_acceptance_fails` | Proves the declared commands ran, not that they are sufficient; oracle dependencies unqualified |
| Route selection excludes unknown cost | `007 route` | `select_route` rejects routes without full cost coverage; fallback only when explicit | `test_router_selects_lowest_cost_eligible_route_and_rejects_quality_loss` | `test_router_excludes_unavailable_cost_route_without_implicit_fallback`, `test_router_blocks_when_no_measured_or_explicit_fallback_exists`; protocol `evidence/v1.4.0/route-selector-result.json` (18/18) | Observational recommender; no model-quality claim |

Focal mutation (removing the mechanism and watching the test fail) has been
demonstrated for the finite-number, timeout, and wrapped-executor cleanup
guarantees. The other
counter-proofs show rejection of a violation but were not re-run against a
mutated implementation; that remains a documented gap, not a failure.

The frozen OLD×NEW protocols cited above compare a mechanism absent with a
mechanism present; their N/N counts are results reported by the artifacts,
not executions repeated for this document. `evidence/v1.2.0/authority-envelope-result-r2.json`
(reported 18/18) is feature-level conformance with two negative controls; the
patch matching its recorded `new_patch_sha256` was not located in the bounded
analysis. The controller-authority protocol is feature-level conformance with
one control. The task-start v2 comparison is compatible with focal isolation
but its NEW bytes are unbound in the artifact. None of them is a mutation of
the present implementation, and none bears on product value.

## Extension points

Provider adapters and repository-specific harness commands live outside the
core. Extend routing only after verifying the runtime binding. Add sensors before
automation, and add automation only after the manual contract is stable.
