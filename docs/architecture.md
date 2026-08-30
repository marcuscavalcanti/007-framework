# Architecture

007 Framework is a stateless instruction package. The coding-agent host executes
models and tools; the repository remains the source of truth.

```text
task + repo rules
       │
       ▼
scope and route ──► isolated execution ──► repository-native gates
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
- `tests/`: protects package identity, public boundaries, and script behavior.

## State model

The framework owns no service state. Durable authority remains in Git, repository
instructions, tests, task handoffs, and optional receipts. Conversations and raw
transcripts are temporary context, not operational authority.

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

## Extension points

Provider adapters and repository-specific harness commands live outside the
core. Extend routing only after verifying the runtime binding. Add sensors before
automation, and add automation only after the manual contract is stable.
