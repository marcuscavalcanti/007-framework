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

Receipts contain declarations, paths and telemetry. Human-authored task fields
can contain sensitive text; a receipt is not automatically sanitized merely
because it conforms to a schema. Local records are not authenticated against
another process using the same filesystem account.

No default retention period is enforced. `007 unregister` removes a registry
entry without deleting project files. Disabling future collection does not
erase previously retained evidence. Removing evidence can make a replay or
historical claim unverifiable.

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

## Publication

Publication is a separate review gate. Credentials, private prompts, customer
data, hidden tests and private repository snapshots must stay out of the public
repository and its artifacts. Report exposure privately through
[SECURITY.md](SECURITY.md). No local test, scan or reviewer opinion proves that
all possible sensitive content has been removed.
