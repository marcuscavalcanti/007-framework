# Receipt schema

A receipt records an outcome at gate time. It is not a transcript.

```json
{
  "schema": "007-framework/receipt/v1",
  "task_id": "example-123",
  "status": "accepted",
  "proof_required": "integrated",
  "proof_reached": "integrated",
  "checks": [{"command": "python3 -m unittest", "exit": 0}],
  "delta": {"files": 3, "added": 42, "deleted": 9, "dependencies": 0},
  "first_pass": "yes",
  "repair_rounds": 0,
  "corrective_lines": "pending",
  "escape_7d": "pending",
  "model": "unmeasured",
  "effort": "unmeasured",
  "tokens": "unmeasured",
  "wall_s": "unmeasured",
  "uncertainty": "runtime not exercised"
}
```

Required semantic fields are status, proof, checks, delta, first-pass outcome,
rework state, telemetry state, and uncertainty. Use `unmeasured`, `pending`, or
`N/D` explicitly. Never infer model, effort, token usage, or human rework from a
conversation summary.
