# 007 Framework repository instructions

## Adversarial review policy

Revision 2026-10-21b (Marcus): the independent reviewer comes from a different
model family than the host session running the routine. `scripts/review_route.py`
is the single implementation of this table; it selects, it never launches.
There is no fallback model: the route fails closed.

| Host session (detected) | Reviewer | Transport | Effort |
| --- | --- | --- | --- |
| Claude (`CLAUDECODE` set) | OpenAI `gpt-6-astra` | Codex CLI, `exec`, read-only sandbox, user config ignored | `xhigh` |
| Codex (`CODEX_THREAD_ID` set) | Anthropic `claude-opus-5-5` | Claude CLI, plan mode, tools disabled, no persistence, CLI budget cap | `xhigh` |

- Both host markers present means nested sessions: the caller must declare the
  host; never guess.
- Fail-closed: if the host is neither Claude nor Codex, or the reviewer's CLI is
  absent, there is no route. A launched review that fails, or whose served
  identity cannot be verified, also records a failed validation and stops: no
  second call and no substitute model or effort.
- Known limits, recorded rather than hidden: the Codex CLI has no USD budget
  flag; neither CLI stream reports served effort.
- Sending a business repository's content to any reviewer needs Marcus's
  per-repository authorization.

Reviews remain bound to the exact sanitized context path and SHA-256 authorized
by the user. If there is no route, or the served identity cannot be verified,
record a failed validation and stop; do not fall back to a different model or
effort.

This policy governs the independent reviewer only. It does not change causal
experiment arms, coding executors, historical receipts, or frozen evidence.
Historical review evidence is immutable and must retain the model and effort
that actually produced it (previous policies: Claude CLI `claude-fable-5-1`, effort
`high`, no fallback; revision 2026-10-21 with a Kimi K3 fallback, never used).
