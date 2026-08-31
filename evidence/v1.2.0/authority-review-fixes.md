# Authority task-start binding evidence

Verdict: **PASS at mechanism level; 8/8 distinct arm-scenario outcomes matched, each reproduced 3/3.**

- OLD commit: `fabc8f4cdb8146ae8601da6be5721dc074fe0a8b`
- final protocol SHA-256: `c54d0bdac21aa89601dd6d66262c02fb57fecd5c48059b3bb8a5898ec0d39456`
- Opus rejection receipt SHA-256s: `a7f83ff15ee84cda421cf46db877a433f7a7729380ad03a66d32bcb34b67a4ed`, `1e74a4a1d2b70aab7f09729e67001615429b91742d8d6e4dc3c685b9015be5ad`;
- targets: a valid receipt without its task-start and one whose task-start embeds a different task ID were accepted by OLD and rejected by NEW;
- controls: matching unbound and matching authority-bound starts remained accepted in both arms;
- no retry-to-pass.

The correction also changes the reported friction denominator to
`friction_blocks / (allowed_executions + friction_blocks)` and labels envelope
coverage as presence rather than strictness.

This proves task-start binding for receipts processed by `007 record`. Boundary
events and task-start files remain unauthenticated local records, forgeable by
the same filesystem principal. It does not prove complete or authentic event
capture, sandbox security, or lower real-world rework.
