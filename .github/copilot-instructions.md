# 007 Framework repository instructions

## Contributing to this repository

Contributions should reduce rework without expanding the framework by default.
A small pull request needs no issue first.

Every change:

1. Describe the observed failure or user outcome.
2. Search for an existing rule, script, or platform feature.
3. Keep one behavior per change and state the proof level.
4. Add the smallest regression check that would fail without the change.

| Type | Must bring |
| --- | --- |
| Bug fix | A test that fails before the fix. |
| Feature or instrument | A test, a `CHANGELOG.md` entry under `[Unreleased]`, and docs. |
| Evidence or claim | A pre-registration committed before any paid run, SHA-256 hashes of what the result depends on, and a source for any change to the README claims table. |
| Doctrine | A real failure, a frozen OLD×NEW task, a pre-registered acceptance rule, and results that preserve non-target behavior. |

New provider instructions require verified runtime receipts and stay outside the
provider-neutral core when possible.

Evidence integrity:

- The set, margin and acceptance rule are fixed before the first paid attempt
  and never changed after it.
- A published result is never edited. Append an erratum that says what changed
  and why.
- Maintainers run paid experiments, under a pre-registration. Propose one in an
  issue.

Project rules:

- Standard library only. A new runtime dependency needs an issue first.
- CI never calls a paid model or reads a secret, so pull requests from forks run
  the same CI. No test may need either.
- Privacy: 007 reads local session logs. No change may send them anywhere or
  store prompt text by default.
- Never commit secrets, customer data, hidden acceptance tests, private
  repository snapshots, raw model transcripts, or generated benchmark outputs
  containing private code.
- AI-assisted contributions are welcome. Name the agent and model in the pull
  request. The same proof standard applies, and the author answers for every
  line.
- Inbound = outbound: contributions are accepted under the MIT `LICENSE`. There
  is no CLA; a DCO sign-off (`git commit -s`) is welcome, not required.
- One maintainer approval merges a pull request once CI passes. The maintainer
  may merge small fixes directly.

Governance:

- A single maintainer, Marcus Cavalcanti (`@marcuscavalcanti`), decides.
- Routine changes go by lazy consensus on the issue or pull request.
- Thesis, doctrine and claims change only with the evidence above. A breaking
  change to the CLI, schemas or dashboard snapshot needs a major version
  (`RELEASING.md`).
- Not adopted yet, by design: a separate governance document (add one when a
  second maintainer or a sponsor joins), a required DCO sign-off (turn it on at
  the first non-trivial outside contribution or when an adopter asks for
  provenance), and a CLA (none while the project stays MIT with no plan to
  relicense).

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
  absent, there is no route. A launched review that fails, or whose identity
  level (below) is `failed`, also records a failed validation and stops: no
  second call and no substitute model or effort.
- Known limits, recorded rather than hidden: the Codex CLI has no USD budget
  flag; neither CLI stream reports served effort.
- Sending a business repository's content to any reviewer needs Marcus's
  per-repository authorization.

Reviews remain bound to the exact sanitized context path and SHA-256 authorized
by the user. If there is no route, record a failed validation and stop; do not
fall back to a different model or effort.

Reviewer identity levels (revision 2026-11-08, Marcus).
`review_route.identity_level` computes the level from the review's JSON stream:

- `verified`: the CLI reports the served model and every reported model is the
  routed one (Claude CLI `modelUsage`). Served effort stays unreported.
- `pinned-no-reroute`, recorded verbatim as "requested model pinned, no reroute
  observed, served identity unverified". All of these hold:
  - the routed model and effort are fixed in the review argv, with user config
    ignored;
  - the stream is from a CLI that reports a server-side model change (Codex
    `exec --json`: a `model rerouted: A -> B` item);
  - the stream completed (`turn.completed`, no `error` or `turn.failed` event);
  - no reroute appeared.
  
  The served model stays `null`; it is never copied from the request.
- `failed`: any other case, including a reroute, a different or missing reported
  model, or an incomplete stream. Record a failed validation; no second call.

A review qualifies a release as follows:

- `verified` qualifies it.
- `pinned-no-reroute` qualifies it only as "qualified with unverified reviewer
  identity". The release notes and release record state that level verbatim.
- `failed` does not qualify it.

These levels exist only for the release review. They never apply to experiment
arms, coding executors, lab receipts or `replay_eval` served-identity checks, and
they never fill served identity from the request. They are not retroactive: the
1.6.0 review keeps its recorded failed validation.

This policy governs the independent reviewer only. It does not change causal
experiment arms, coding executors, historical receipts, or frozen evidence.
Historical review evidence is immutable and must retain the model and effort
that actually produced it (previous policies: Claude CLI `claude-fable-5-1`, effort
`high`, no fallback; revision 2026-10-21 with a Kimi K3 fallback, never used).

(Yes, these rules also apply to agents working on this repository. Especially to them.)


## Security workflow for this project

Security review is active as a project workflow for every agent host. Read the
applicable root or nested `SECURITY.md` and `PRIVACY.md` before changing an
execution, filesystem, network, capture, credential or publication boundary.
Record the scope, attacker-controlled inputs and evidence for the affected
boundary; distinguish intended caller authority from a broken promised control.

Codex Security is the native scan adapter when available. Use the documented
Standard or diff workflow for the current host and authorized scope. Keep its
authoritative scan ID, target, source revision, coverage and artifacts; seal a
scan only after its real work and required documents exist. A started scan,
installed plugin, partial report or zero findings is not a security approval.
Schema or runtime failures remain explicit; do not invent fields or completion.

All hosts use the same security criteria. A host without the native adapter may
run authorized local checks, but must label the native result unavailable rather
than claiming an equivalent Codex Security scan. This workflow does not change
the independent reviewer policy or qualify an experiment, replay or ROI claim.

Keep scans inside their authorized repository and context. Never read provider
credentials, unrelated sessions, customer data or private prompts for a scan.
Paid inference, additional workers, Deep Scan, installs, hooks and Cloud
continuous monitoring require their applicable authorization; this instruction
does not renew consumed calls or change account settings. Persist findings and
unresolved gates, then continue independent authorized work.

Security probes and local verification must use an explicit environment allowlist
or a cleared synthetic environment, with a temporary HOME when native log reads
are not part of the check. Never print an environment mapping or use an assertion
that can render its values on failure. Report only the synthetic key's presence
or a safe error class; preserve diagnostics without copying credentials.
