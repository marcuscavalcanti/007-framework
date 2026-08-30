# Local Runtime Activity Design

**Status:** approved in chat by Marcus on 2026-08-30
**Target:** Evidence Cockpit candidate after v1.1.0

## Objective

Make already-running 007 projects show useful near-real-time activity without
turning host logs into fabricated delivery outcomes. The dashboard must show
which local coding runtimes are active, which model and effort were served,
token volume, and Headroom-equivalent cost while keeping accepted, first-pass,
escape, and reliable-outcome metrics bound to validated receipts.

## Evidence lanes

The dashboard has two non-interchangeable operational lanes:

1. **Observed runtime activity:** read-only metadata from local Codex and Claude
   JSONL logs. It may report sessions, active/idle state, served model, effort,
   token classes, elapsed time, and estimated cost. Attribution is by the
   session working directory or Git common directory and is labelled as such.
2. **Verified outcomes:** `007 begin` plus `007 record`. Only this lane may
   report accepted, first-pass, repair rounds, escapes, or reliable outcomes.

A completed or idle model session is never inferred to be accepted. Prompts,
responses, tool arguments, command output, and hidden reasoning are neither
returned by the collector nor exposed by the dashboard API.

## Scope and window

V1 observes sessions started or updated during the last 24 hours. Codex logs
are read from `~/.codex/sessions`; Claude logs are read from
`~/.claude/projects`. Direct project paths and Git worktrees reconcile through
their Git common directory. Sessions that cannot be mapped safely remain
unattributed and do not enter a project total.

Codex cumulative token counters are read from bounded session tails. Claude
usage is summed only for bounded recent files; oversized or malformed logs keep
the session visible with usage `N/D`. File parsing is cached by path, size, and
modification time so the existing two-second dashboard poll does not repeatedly
scan unchanged logs.

## Cost semantics

Cost is an explicitly labelled **Headroom/LiteLLM estimate**, not a subscription
invoice. When Headroom is installed, the collector invokes its isolated Python
environment with sanitized token counts only. The worker uses Headroom's
LiteLLM model-name candidates and `cost_per_token`, preserving provider aliases,
cache-read/cache-write prices, and long-context pricing. No local 007 rate card
or silent family alias competes with that authority.

The worker receives only model and token classes; no prompt, output, path, or
session identifier crosses the process boundary. Unknown models, incomplete
usage, unavailable Headroom, and unsupported one-hour cache pricing are
unpriced, never assigned zero.
The dashboard reports priced-token coverage and keeps aggregate USD `N/D` when
any observed usage is unpriced.

## Interface

The aggregate and each project expose an `activity` object with:

- `window_hours`, `sessions`, `active_sessions`, and `idle_sessions`;
- normalized input/cache-write/cache-read/output/reasoning tokens;
- `tokens_total`, `cost_usd_estimate`, `priced_sessions`,
  `unpriced_sessions`, and `pricing_coverage`;
- routes grouped by observed provider, model, effort, token volume, and cost;
- recent sanitized sessions with ID, source, project attribution, timestamps,
  status, model, effort, tokens, and estimated cost.

The UI presents this activity before the receipt-only reliability funnel and
states that live activity is not proof of a reliable outcome.

## Constraints

- Standard-library dashboard; optional local Headroom supplies pricing without
  becoming an agent runtime, daemon, database, provider API, or log mutator.
- No prompt or output content crosses the parser boundary.
- No retrospective acceptance, first-pass, or escape inference.
- No cost for an unknown model and no silent alias matching.
- Existing receipt calculations and causal evidence remain unchanged.

## Verification

- Literal Codex and Claude JSONL fixtures prove normalized token accounting.
- Pricing-request tests cover every token class; a live local check compares the
  worker result with the installed Headroom/LiteLLM engine.
- Worktree and main checkout fixtures reconcile to one project identity.
- Prompt and response fields in fixtures never appear in collector output.
- Unknown models remain unpriced and make aggregate USD `N/D`.
- Existing tests, API allowlist, desktop/narrow UI, and six-project
  reconciliation remain green.
