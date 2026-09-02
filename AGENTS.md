# 007 Framework repository instructions

## Adversarial review policy

All new external adversarial reviews for this project use:

- provider: Anthropic
- transport: Claude CLI
- model: `claude-fable-5-1`
- effort: `high`
- permission: read-only / plan mode
- tools: disabled
- session persistence: disabled

Reviews remain bound to the exact sanitized context path and SHA-256 authorized
by the user. If this route is unavailable or its served identity cannot be
verified, record a failed validation and stop; do not silently fall back to a
different model or effort.

This policy governs the independent reviewer only. It does not change causal
experiment arms, coding executors, historical receipts, or frozen evidence.
Historical review evidence is immutable and must retain the model and effort
that actually produced it.
