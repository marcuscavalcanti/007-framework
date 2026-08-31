# Phase Zero Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make controller acceptance and experimental served identity truthful enough to run the minimum real causal thesis test.

**Architecture:** Extend the existing standard-library controller and replay runner; do not add a daemon, database, gateway, DSL, or provider-specific core. Acceptance is a frozen argv-only contract executed after the coding harness exits. Experimental identity is a required controller-observed value; absent or mismatched identity invalidates the cell.

**Tech Stack:** Python standard library, `unittest`, JSON, Git.

**Spec:** `docs/target-definition.md`; immediate scope is `docs/phase-zero-diagnosis.md`.

## Global Constraints

- Preserve backward compatibility when no acceptance contract is supplied.
- Never execute acceptance through a shell string.
- Never convert a failed hard gate into accepted because cost or latency is favorable.
- Never infer requested identity as served identity.
- No new dependency or product subsystem.

---

### Task 1: Controller-observed acceptance

**Files:**
- Modify: `scripts/framework_cli.py`
- Test: `tests/test_dashboard.py`
- Modify: `references/receipt-schema.md`

**Interfaces:**
- Consumes: an optional JSON file `{ "schema": "007-framework/acceptance/v1", "commands": [["python3", "-m", "unittest"]] }` supplied to `007 run --acceptance-file`.
- Produces: a hash-bound task-start contract and terminal `checks` containing argv, cwd, exit, duration, and stdout/stderr SHA-256 values; any non-zero check forces `status=blocked` and a non-zero CLI exit.

- [x] **Step 1: Write failing tests** proving that a false adapter-declared PASS is replaced by controller-observed checks and that one failing gate forces a persisted blocked receipt.
- [x] **Step 2: Run the focused tests** and confirm failures are caused by the missing `--acceptance-file` behavior.
- [x] **Step 3: Implement the minimum parser, validation, execution, binding, and CLI option** in `framework_cli.py`.
- [x] **Step 4: Run focused and full tests** and confirm backward compatibility.
- [x] **Step 5: Document the controller-observed contract** without claiming the thesis is proved.

### Task 2: Fail-closed served identity in experiments

**Files:**
- Modify: `scripts/replay_eval.py`
- Test: `tests/test_scripts.py`
- Modify: `examples/replay-set.example.json`
- Modify: `references/causal-testing.md`

**Interfaces:**
- Consumes: a pre-registered identity binding appropriate to the chosen harness and an exact expected provider/model/effort per arm.
- Produces: `served_provider`, `served_model`, and `served_effort` in every cell; required absent or mismatched identity yields `valid=false` and stops the run.

- [ ] **Step 1: Write table-driven failing tests** for exact match, absent identity, and mismatch.
- [ ] **Step 2: Run the focused tests** and confirm the current `unmeasured` behavior fails them.
- [ ] **Step 3: Implement the smallest harness-neutral binding supported by the chosen CLI's structured output**; do not parse prose.
- [ ] **Step 4: Run focused and full tests** and capture exact results.
- [ ] **Step 5: Freeze the experiment protocol only after both tasks pass**; zero model calls occur during these tasks.
