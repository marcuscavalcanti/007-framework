# Privacy and local data

007 is local tooling around your agent CLIs. The host controls authentication,
filesystem permissions and network access; these documents do not provide an
operating-system sandbox. See [the security policy](SECURITY.md).

## What it reads

- Registered repositories: declared receipts and task starts, Git metadata,
  configured acceptance evidence and replay inputs.
- Local activity: native session logs to extract session/parent identifiers,
  timestamps, working directories, model/effort segments and usage counters.
  The parser may encounter message payloads while decoding a log; the retained
  activity rows contain selected metadata, not copies of those message bodies.
- The observatory: configured calibration reports and Git history for
  attribution and line survival. Attribution is heuristic, not causal proof.

Opening the dashboard can inspect local session metadata. Durable observatory
recording is limited to `observatory.projects`, unless you explicitly enable
`observatory.auto` in the local configuration. Auto mode is off by default.
It does not grant access beyond the host's permissions.

## What it keeps

Project records live under `.007/`; configuration and the registry are under
`~/.007-framework/`. Observatory stores, replay vaults and experiment output
use their configured local paths. Replays can retain source snapshots, prompts,
patches and acceptance artifacts when you request those operations.

Local replay cells preserve the existing bounded agent/test output tails and acceptance argv by default, with
additional hashes/lengths of UTF-8 re-encoded subprocess text. The strict boolean `retain_diagnostic_text: false`
intentionally removes diagnostic text from cells and their observation/summary/receipt copies. New output directories
are owner-only; existing host permissions and ACLs still govern access. This does not remove authorized frozen replay
inputs or modify historical results. Local retention does not authorize model egress, sharing or publication.

Receipts contain declarations, paths and telemetry. Human-authored task fields
can contain sensitive text; a receipt is not automatically sanitized merely
because it conforms to a schema. Local records are not authenticated against
another process using the same filesystem account.

Controller-generated `007 run` acceptance checks preserve local argv and add a command hash. The explicitly bound
acceptance contract remains an input. Mining keeps its bounded diagnostic text locally; explicit metadata-only mode
keeps safe exception classes and numeric exits instead. Detailed mining errors are not echoed when that minimization
mode is selected. Existing records are not rewritten. Review/export/publication must separately sanitize authorized data.

No default retention period is enforced. `007 unregister` removes a registry
entry without deleting project files. Disabling future collection does not
erase previously retained evidence. Removing evidence can make a replay or
historical claim unverifiable.

With no registered projects, activity collection does not enumerate session logs and clears its session cursors.
With no enrolled observatory projects and auto mode off, observatory recording does not enumerate sessions either.
An active project scope can still require decoding native log metadata to identify its sessions; these guards do not
promise that only enrolled log files are opened in every collector mode.

## What can leave the machine

Native agent commands send the context you authorize to their configured model
providers. 007 does not replace their authentication or privacy settings.
Review requests and security scans are separate explicit operations; they must
receive only their authorized context.

Optional Headroom/LiteLLM pricing runs in an installed Python process. The
pricing worker receives model names and token counts, not session bodies or
repository source. That installed dependency controls its pricing-data loading;
007 does not claim to enforce its network policy. Missing prices remain unknown.

The dashboard binds to loopback by default. Changing its bind address changes
who may reach its metadata; it is not an authenticated hosted service.
HTTP requests must name the configured host, a bound interface address or the loopback localhost alias, using the actual
listening port. Foreign/missing/duplicate Host headers and proxy-style request targets are rejected before route data is
read. This browser-origin defense is not authentication; explicitly exposing the bind address remains a host decision.

## Publication

Publication is a separate review gate. Credentials, private prompts, customer
data, hidden tests and private repository snapshots must stay out of the public
repository and its artifacts. Report exposure privately through
[SECURITY.md](SECURITY.md). No local test, scan or reviewer opinion proves that
all possible sensitive content has been removed.
