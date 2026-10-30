# Causal testing

## The question

Does one doctrine mechanism change the target behavior while everything else is
held constant?

## Minimal OLD×NEW flip test

1. Start from a real failure or costly correction.
2. Write a task that reproduces the decision, not the historical implementation.
3. Freeze the same repository snapshot, prompt, executor, model, effort,
   environment, timeout, and acceptance tests for both arms.
4. OLD receives the baseline doctrine; NEW differs by one declared mechanism.
5. Pre-register an integer seed, randomize arm order within each pair, record
   the realized order, and run at least three pairs for a mechanism probe.
6. Apply hidden acceptance tests only after the agent exits.
7. Pre-register pass, block, invalid-run, and early-stop rules.
8. Report every valid and invalid cell; no retry-to-pass.

A mechanism flip supports only that behavior in those conditions. It does not
prove general productivity, provider portability, production durability, or a
full framework bundle.

## Served identity

When provider, model, or effort is a causal variable, set
`require_served_identity: true`. The frozen adapter receives the
`{runner_receipt}` placeholder and must write a no-retry structured receipt:

```json
{
  "schema": "007-framework/runner-receipt/v1",
  "valid": true,
  "requested": {"provider": "openai", "model": "model-a", "effort": "medium"},
  "served": {"provider": "openai", "model": "model-a", "effort": "medium"},
  "identity_source": "provider-structured-response",
  "source_sha256": "<sha256>",
  "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
  "cost_usd": 0.01,
  "cost_source": "rate-card-estimate"
}
```

The adapter owns provider-specific parsing; the replay core only validates the
provider-neutral receipt against the pre-registered policy. Missing identity,
an adapter-invalid result, or requested/served mismatch invalidates the cell and
stops the run. A requested CLI flag is not served-identity evidence. The agent
command, the acceptance commands, and the replay's own Git helpers each run in
their own session; when a command returns, by exit, failure, or timeout, every
remaining member of that group is killed and observed gone before the result
is interpreted. The controlled waits total up to two seconds; the OS may keep
a group observable beyond that. If cleanup is not confirmed, the cell is
invalid with `cleanup-child-unconfirmed` or `cleanup-group-observable` as its
failure class, acceptance is skipped, no Git helper starts (the cell records
`d0_complete: false` and the seven diagnostic fields as `unmeasured`, never
zero), the run stops before the next executor, and a timeout diagnostic
(`agent_exit -9`, `TIMEOUT`) is preserved. The runner receipt, if present, is
still read and hashed as a diagnostic observation; while cleanup is
unconfirmed its bytes are not stable evidence and its identity is not
consolidated terminal evidence. Services
that must outlive a command are not supported in these groups. A descendant
that starts its own session escapes that cleanup. The workspace is a fresh
snapshot export, not read isolation: the agent process can still read any path
the OS user can.

`usage` is optional. When absent or `null`, the cell records `usage` and
`tokens` as `unmeasured`; the cell stays operationally valid, which does not
satisfy any protocol that requires token telemetry. When present it must be an
object, otherwise the cell fails with `usage-invalid` and the run stops before
the next executor. The public counters are `input_tokens`, `output_tokens`,
and `total_tokens`: each, when present, must be a non-negative, non-boolean
integer; an explicit `null` is invalid and nothing is coerced. Every other key,
including provider-specific `*_tokens` names, is preserved verbatim and not
interpreted. The core never sums components, derives `total_tokens`, or checks
relations between counters; the cell's `tokens` is the observed `total_tokens`
or `unmeasured`. This validates structure only, not completeness, truthfulness,
or the meaning of a count across providers.

## Controls

Include a non-target control when over-correction is plausible. A pass should
require the intended OLD→NEW improvement, no NEW target failure, and no loss on
the control. Invalid telemetry or contaminated inputs invalidate the pair; they
are not evidence against either arm.

## Diagnostics are not gates

File overlap, Jaccard, line similarity, and resemblance to an accepted patch are
**diagnostic only** and **never an acceptance, review, or release gate**. They can
explain divergence; only task-specific executable acceptance checks decide
correctness.

## From mechanism to release

Mechanism flip → broader paired tasks → real held-out tasks → longitudinal
receipts. Promotion claims must stop at the strongest completed layer.

## Retained-case integrity

`replay_capture.qualify_case(vault_root, project_id, task_id, replay_ref)` reads
the existing private manifests and validates retained input/candidate bytes.
Its projection contains only integrity states, fingerprints and fixed gap labels;
it does not run commands, expose artifact paths/content or rewrite receipts.
Missing or denied reads are `unavailable`, not a failed business outcome.
Corruption is `invalid`; absent capture is `observational`.

`inputs-retained` and `case-retained` are preservation states, not `replay-ready`.
Reconstruction, environment closure, independent oracle execution and generator
isolation remain required. A coherent candidate or receipt hash cannot admit a
holdout or establish causal/economic eligibility. The same records and bytes
produce the same projection; an input fingerprint ignores role-list order but
does not establish semantic equivalence between different tasks.
An older terminal without a separate project field can retain the exact validated
project/task `replay_ref` binding; an explicit conflicting project cannot.

## Dataset partitions and explicit recheck

Retained tasks in a replay-set can add `project_id`, `source_task_id` (defaults to
`id`), `replay_ref`, `family`, `class` and `split` (`discovery`, `calibration` or
`holdout`). An optional `result_sha256` freezes the candidate-result identity;
a mismatch excludes the case before execution. `accepted` identifies a known
historical solution, not a future holdout. Original records are never rewritten.

```bash
python3 scripts/replay_eval.py --set replay-set.json --vault /private/replay-vault admit
```

Admission is read-only by default: it verifies retained bytes, groups by project,
class and partition, and reports gaps/exclusions. It ignores file-supplied
`replay_ready`, `causal_eligible` and verification stamps. Cross-partition task,
family or exact input-fingerprint collisions exclude the affected cases; repeated
identities cannot inflate counts. The bounded manifest contains at most 100 cases;
do not split a contaminated manifest into separate batches to evade this check.
An admitted discovery/calibration entry is queue membership, not trial approval.

An explicit operator-authorized `admit --recheck` executes the captured acceptance
argv on two fresh reconstructed candidates, without using the original checkout.
It is limited to three cases per invocation and 300 seconds of command deadline
per case; file I/O also retains the capture limits. Excluded cases do not execute.
The profile checks the recorded Python version and refuses unresolved external
inputs. It does not install dependencies or prove cross-host environment closure.
No tails or commands are copied into the sanitized admission response. Timeout,
unconfirmed cleanup, unstable/nonzero oracle or unavailable bytes cannot establish
replay-ready; nonzero is not automatically blamed on an agent. This is a current-host
technical recheck, not an independent causal comparison or authenticated history.

`restore_candidate` overlays only the newly restored copy with declared retained
outputs/deletions and verifies bytes/modes. It refuses occupied destinations and
corrupted source. Neither admission nor recheck qualifies generator read isolation,
economic ROI or a public held-out result; these remain separate protocol gates.
The existing historical `list`/`run` path is unchanged and does not yet consume
retained-input tasks. Do not use it as a substitute for a dirty captured pre-state.

## Dashboard retention projection

The snapshot adds per-project `dataset` counts and sanitized case states using
the same retained-byte verifier. These cumulative stages overlap; do not sum
them as independent samples. This projection never executes an oracle or turns
file claims into replay-ready/causal/economic eligibility. It is not split
admission or a complete dependency snapshot. References without retained bytes
remain unavailable; conflicting starts/receipts and duplicates are explicit gaps.

The server caches the last integrity observation by project/task/reference and filesystem identity
(including size, mode, uid, inode, mtime and ctime). A relevant mutation triggers
verification with before/after identity checks, not a hash of every byte on every
poll. Metadata scanning remains proportional to retained entries and is bounded
to 100 cases per project and 10,010 retained entries (including directories) per
case; larger coverage is explicitly partial, not a failed business outcome.
Publishing a sibling case does not invalidate unrelated case bytes. This cache
is a local observation, not authentication or current byte integrity. Equal
metadata can conceal same-size byte changes. Each qualified observation keeps
its original `checked_at`; empty polling does not advance it. Dataset projections
use `last-checked-retention` with oldest/latest check dates (unknown if absent).
Admission, curation and replay re-read full hashes; they never trust this cache.

`latest_event_at` is a declared task event; `ingested_at` is this server's latest
changed projection; `generated_at`/`read_at` are reads. Empty polling changes only
read time. Ingestion clocks/cache restart with the server, not durable history.
Read errors retain the previous good project with `stale: true`, `available:
false` and no current approval; first failure has no invented good sample.
Path/project identity changes cannot inherit another acquisition's old values.
Denied directory listings are acquisition errors, not empty sources. A declining
start/receipt/matched-history count is held stale as possible loss; intentional
history removal requires review, not an automatic improvement claim.
The UI renders absolute local date, timezone/offset, relative age and factual
receipt contribution. Monetary gain still requires a qualified OLD×NEW result.

The event chart counts unique task/kind declarations in a frozen 30-day UTC
window; naive, invalid, future or duplicate entries are excluded explicitly.
Starts and terminals are events, not independent cases. No polling increment.
`dataset_history` holds the last 60 changed per-project observations in this
server session: first retained point is a baseline, absent verification is a
gap, and stale reads add no point. Stocks overlap; they are not training progress.
This is neither durable history nor a cross-project synchronized cohort.
The comparison plot identifies the existing historical experiment and its
API-equivalent rate-card USD; missing/incoherent costs or incomplete recorded
identity leave N/A. Rendering a historical artifact is not a new experiment,
provider billing, producer authentication or proof of ROI for the selected project.

The internal `execute_cell(..., vault_root=...)` path restores a hash-bound
retained input without consulting its original checkout or historical solution.
It uses the captured prompt and acceptance commands, rejects divergent overrides,
retains the effective prompt (captured instruction plus arm doctrine) with its
SHA-256, and preserves each stable candidate through the existing replay-input/result
formats before cleanup. Nonzero executors remain invalid but their declared
output bytes can be retained. Unconfirmed cleanup never captures a candidate;
preservation failure cannot publish a valid/accepted cell. Existing outputs are
not replaced or reexecuted. Historical similarity remains unmeasured.
Retention covers configured output paths, not all arbitrary new/ignored files.
The captured acceptance contract remains visible to the same-user generator;
this is calibration infrastructure, not qualified oracle isolation. Records
explicitly remain causally/economically ineligible. No CLI `run --vault` activation
or paid experiment is enabled here: isolation, budget enforcement and admission
must be qualified before that public path is connected.

`ReplayBudget` is the first experiment's serial USD30 accounting profile:
USD20 executor cells, USD5 independent review and USD5 contingency. Creation
requires an explicit same-basis prior cost for each category and source/protocol
hashes; unknown prior spend is not zero. SQLite transactions serialize reserve
decisions across controllers. Append-only events preserve reservations, costs,
unknowns and the reviewed checkpoint; a repeated reserve never grants another
launch. Restart preserves open obligations; no automatic refund on an exception.
Unknown cost, overrun or mixed basis blocks dispatch. The first checkpoint is
six priced cells or USD10 exposure, with a current-state-bound review before
continuation inside the unchanged category/total ceilings. Budget source hashes
bind declarations, not producer authentication or independent review quality.
`execute_reserved_cell` reserves before launch and reconciles all outcomes from
the exact persisted cell bytes. A paid failure remains in the total. Missing or
incompatible USD freezes the next call without discarding the candidate.
Reservation accounting does not enforce a provider's charge: a finite route
upper bound must be independently qualified before any real paid use. Overruns
are recorded and stop subsequent dispatch, not hidden or described as prevented.
The ledger holds at most128 events and refuses new launch grants before its
remaining space could prevent settling/reconciling an outstanding call.

`replay_eval.py --set cases.json --vault <vault> --checkpoint <private-path>
curate` reuses read-only admission and never runs generators or acceptance commands.
The owner-only checkpoint identifies the verifier, vault scope and sanitized
admission bytes; it is not producer authentication or a qualified comparison.
Repeated or reordered inputs leave its bytes and completion date unchanged and
emit no stdout. Additions/classification changes report only affected case IDs.
Unreadable/corrupt retention, unfinished candidate publication, history shrink or
source rebinding do not advance the checkpoint. A per-checkpoint atomic lock
rejects overlap; a crash can leave a lock requiring operator review, never automatic
removal. Existing valid checkpoint replacement is atomic, not a power-loss durability
guarantee. Sources remain unchanged; no hypothesis or policy is promoted by curating.
The command requires an explicit dataset manifest; it does not discover every
native session, configure active projects or activate the daily automation.

`007 dashboard --curation-checkpoint <private-path> --curation-vault <vault>`
consumes that checkpoint without curating or running an oracle. The shared reader
checks scope, hash and read-only admission semantics; sanitized totals are scoped
by project ID, not names. Polling reads only this bounded checkpoint (at most1MiB),
not the curation corpus. Failed reads preserve the last checkpoint as stale;
missing configuration or a project outside its manifest is N/A, not zero. Dates
are displayed in browser-local time. The shown completion is a declared persisted
checkpoint, not authenticated authorship, a new analysis each poll or proof of ROI.

Stable incomplete executions use the existing result format: outputs/receipt.json
may contain an execution-incomplete observation with no status and unknown USD,
not an official terminal receipt. Admission/curation can retain it as calibration
and an explicit recheck can reconstruct it without the original checkout. Passing
that oracle does not change historical exit/status/cost or causal/economic eligibility.
Five synthetic pipeline scenarios cover unpriced, missing/foreign receipt, failed
executor and incorrect candidate; corruption excludes before the oracle. This
does not qualify shutdown or every native-telemetry/publication failure path.

Native telemetry publication failure now preserves the stable candidate through
that same incomplete-observation path only after original-group cleanup is gone
and the stream is closed. The conflicting telemetry file is not overwritten;
the original failure still propagates and no official receipt is manufactured.
Parsed telemetry can remain inside the private observation, while USD/status stay
unknown. Unconfirmed cleanup/stream never publishes this fallback candidate.

### Declared correction and escape links

A curation task may append up to eight `followup_refs`, using the existing
relative-manifest/SHA-256 shape. Each file lives in the private vault at
`<project>/<source-task>/followup-<sha256>.json`, at most8192bytes and owner-only.
The JSON must match `project_id`, `task_id`, `input_sha256` and
`result_sha256` of the admitted retained case. The last digest identifies the
retained result manifest, not a Git commit or an inferred receipt candidate.
Include an aware, non-future `observed_at` and at least one of:
nonnegative integer `repair_rounds`/`corrective_lines`, or
`escape_7d` as a strict boolean or `"yes"`/`"no"`.

Curate verifies source bytes, scope and candidate binding; ambiguous/duplicate
trials, malformed counts, broken paths, changed/missing sources and duplicate
references fail without advancing the checkpoint. Removing a previously linked
observation leaves the old checkpoint incomplete, never improved. Append a new
immutable source instead of replacing an older observation. Reordering/repeating
the same sources is quiet. Private descriptions are not projected.

The existing checkpoint format gains only optional `declared_followups` on
admission rows; old checkpoints remain readable. These are traceable declarations,
not authenticated observations or seven-day maturity. They do not run an oracle,
train a model, enable causal/economic eligibility or change policy. Automatic
hypothesis generation and daily activation remain separate gates.

The dashboard counts linked sources separately from cases with any declared
correction or escape, globally and by project ID. Multiple sources for one case
do not become multiple incidents; a later zero/no declaration does not erase an
earlier signal. Polling projects only the validated checkpoint, without private
descriptions or source identities; failed reads keep the last values marked stale.

### Declared hypotheses, not policy decisions

A retained admitted task may append up to eight `hypothesis_refs` with the same
manifest/SHA shape, pointing to owner-only `<project>/<source-task>/hypothesis-<sha>.json`
sources <=8192bytes. Bind project/task/input/result as above; require `kind` as
`gate` or `routing`, `status: proposed`, and nonempty strings <=1024characters for
`mechanism`, `evidence`, `counterproof`, `positive_control` and `experiment`.
These are syntactically complete proposals, not verified mechanisms or results.
Private text stays in the vault; checkpoint rows project only kind/source hash.

At most one new gate and one new routing source may enter a successful cycle.
Prior references remain append-only; repeat/reordering is quiet, and ambiguous,
broken, changed or omitted sources cannot advance the checkpoint. Optional
`declared_hypotheses` on rows and `proposal_delta` in admission preserve the
existing checkpoint format and old-reader compatibility. The delta is hash-bound
to current rows; no label can claim approval, executed oracle or causal promotion.
The dashboard shows cumulative declared counts and the last cycle's kind/hash
references by project, preserving stale values explicitly. Polling reads only the
checkpoint. Source authorship, scientific merit and present source freshness
remain unverified; no automatic generation, training, route/gate application,
paid call or economic benefit is implied.

Input/candidate capture re-reads each bounded source and compares its digest to
the already copied artifact before publishing a manifest. Matching filesystem
stamps alone do not exclude same-size rewrites. Existing stat/mode/revision and
no-replace guards remain; this adds one bounded read, not an atomic filesystem
snapshot or proof of detecting a transient change restored between checks.
