# Receipt schema

A receipt records an outcome at gate time. It is not a transcript.

```json
{
  "schema": "007-framework/receipt/v1",
  "task_id": "example-123",
  "task_class": "implement",
  "status": "accepted",
  "proof_required": "integrated",
  "proof_reached": "integrated",
  "checks": [{"command": "python3 -m unittest", "exit": 0}],
  "delta": {"files": 3, "added": 42, "deleted": 9, "dependencies": 0},
  "first_pass": "yes",
  "repair_rounds": 0,
  "corrective_lines": "pending",
  "escape_7d": "pending",
  "requested_provider": "openai",
  "requested_model": "gpt-5.6-sol",
  "requested_effort": "xhigh",
  "served_provider": "openai",
  "served_model": "gpt-5.6-sol-2026-08-01",
  "served_effort": "xhigh",
  "tokens": 18420,
  "wall_s": 93.4,
  "cost_usd": 0.84,
  "cost_source": "provider-reported",
  "cost_status": "final",
  "uncertainty": "runtime not exercised"
}
```

Required semantic fields are status, proof, checks, delta, first-pass outcome,
rework state, requested and served route, telemetry state, cost, and uncertainty.
Provider, model, and effort are open strings: the framework does not maintain a
provider allowlist.

`task_class` is optional for backward compatibility and, when present, is one
of `inspect`, `implement`, `deep`, or `design`. It lets the selector compare like
with like; receipts without it stay visible but do not train route selection.

`cost_usd` is mandatory, finite, and numeric for every recorded terminal
outcome. `cost_source`
names how it was obtained, for example `provider-reported`,
`rate-card-estimate`, `subscription-allocated`, or `local-compute`.
Custom adapters use the explicit `custom:<name>` namespace; other free-form
labels are rejected so spelling mistakes do not silently split the KPI.
`cost_status` is `final` or `provisional`. A provider adapter may calculate cost
from token classes and the exact served model, but the core never guesses a
price table. Missing cost is not zero: `007 record` rejects it, and legacy or
foreign receipts remain visible as unaccounted in the dashboard. Observation
coverage uses task starts from `007 begin` as its denominator; work that never
calls `begin` remains explicitly outside the dependency-free observer.

Capture cost at the last execution boundary: the host or provider adapter reads
the terminal response, records the actually served route, and writes the
normalized receipt. Prefer provider-reported USD; otherwise use an explicit
rate-card, subscription-allocation, or local-compute source. Headroom, RTK, and
provider CLIs are replaceable adapters, not framework dependencies. An optional
activity estimate never substitutes for the terminal receipt.

Use `unmeasured`, `pending`, or `N/D` explicitly for telemetry the host cannot
expose. Never infer model, effort, token usage, cost, or human rework from a
conversation summary. Persist a receipt atomically with:

```bash
007 record --repo . --file task.receipt.json
```

Or wrap an arbitrary provider CLI without coupling the core to that provider:

```bash
007 run --repo . --task-id task-123 --receipt task.receipt.json -- <command>
```

The command reads `FRAMEWORK_007_TASK_ID`, `FRAMEWORK_007_RECEIPT_PATH`, and
`FRAMEWORK_007_REPO`, then writes the normalized receipt. `007 run` preserves
the command's non-zero exit status and leaves a start open when no valid,
task-matched terminal receipt exists. Raw transcripts are not retained.

To make hard-gate evidence controller-observed, pass an argv-only acceptance
contract:

```json
{
  "schema": "007-framework/acceptance/v1",
  "timeout_s": 900,
  "commands": [["python3", "-m", "unittest", "discover", "-s", "tests"]]
}
```

```bash
007 run --repo . --task-id task-123 --receipt task.receipt.json \
  --acceptance-file acceptance.json -- <command>
```

The task start stores the contract and its raw SHA-256 before the coding command
runs. After that command exits successfully, the controller executes each argv
without a shell and replaces agent-claimed `checks` with command, working
directory, exit code, duration, timeout state, and stdout/stderr digests. Any
non-zero hard gate forces a persisted `blocked` receipt and CLI exit `4`.
`acceptance_evidence: "controlled"` is computed by 007 and cannot be supplied
through manual `record`. This proves only the declared commands ran on that
working tree; it does not prove that the command set is sufficient.

## Optional authority envelope

For a task that crosses meaningful boundaries, bind a small action envelope at
start time:

```bash
007 begin --repo . --task-id task-123 --authority-file examples/authority.example.json
```

To make enforcement controller-observed instead of agent-declared, execute one
classified action through the supported controller path:

```bash
007 run --repo . --task-id task-123 --receipt task.receipt.json \
  --authority-file examples/authority.example.json --action test -- <command>
```

`--authority-file` and `--action` are required together. An allowed action runs;
a denied or unclassified action is blocked before the subprocess starts. The
controller writes one no-replace `.007/events/<task-id>.event.json` and stamps
the terminal receipt with `authority_evidence: "controlled"`. A caller cannot
set that provenance through `007 record`. Manual `begin` + `record` remains
supported, but its receipt is explicitly marked
`authority_evidence: "declared"`.
The controlled stamp is accepted only when the matching persisted controller
event exists and equals the event being bound to the receipt.

Every terminal receipt requires its matching task-start record. The start stores
the envelope and its raw-file SHA-256. The terminal receipt
must repeat `authority_sha256` and include `boundary_events`, whose entries are
`{"action":"test","outcome":"executed"}` or
`{"action":"deploy","outcome":"blocked"}`. `007 record` rejects a hash
mismatch and any reported executed action not listed in `allow`. It summarizes
protective, friction, and unclassified blocks for the dashboard.

This is an auditable terminal fence, not a security sandbox. The controlled path
prevents an agent using the supported command from omitting or relabeling the
classified event. The local event and task-start files remain unauthenticated:
a process running as the same OS principal can forge or remove them. Protecting
against the machine owner or a compromised local account requires host-level
isolation or a remote append-only ledger and is outside this version's threat
model.
Envelope coverage measures presence, not policy strictness. Secrets, production,
network egress, and destructive actions still require technical isolation and
host-level approval.
