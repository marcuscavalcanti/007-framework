# Native capture — offline increments A, B1, B2 and prospective unit

Status: **offline implementation; not installed, enrolled or runtime-qualified**.
Owner: Codex. The approved local scope includes A1–A3 and the diagnostic-read follow-up of
the native-capture plan (internal design record, not published).
No private finance-project files, active sessions, model settings, hooks, trust state or
OTel exporters are changed. No network, model invocation or transcript reader is
part of the metadata commands.

## Prospective unit: offline calibration only

The approved local plan (internal design record, not published)
adds `prospective_unit.py` and `codex_prospective.py`, with no launcher, CLI entrypoint,
native connection, dependency, installation or change to existing admission guards.
The adapter identifies App Server0.160.1 as `codex-app-server`/terminal, not a hook
or Desktop producer. No tool type is qualified. Fixtures are synthetic and new;
historical receipts, costs and identities are not reused as evidence.

Preparation verifies source/restore inventories, modes, checkout identity and Git
base against the retained manifest. Prompt/context/acceptance/environment/authority
cannot be candidate outputs. The driver arms B2, revalidates input, publishes an
exclusive durable dispatch intent, revalidates again and calls one fake transport.
Exact request response plus start notification are required before consumption;
early starts are buffered, conflicting/unsupported messages refuse, and uncertainty
preserves the claim and refuses retry at the same root. Review reconciliation
confirmed a blocker: another dispatch root can resend for the same binding after
uncertainty. Both new/existing reservations return reserved, so checking that
return value alone does not fix it. Stable atomic dispatch ownership and sanitized
git subprocess errors are the proposed local corrective scope; no fix is installed.
These checks are not exactly-once delivery or
authenticated runtime evidence. Event refs hash the bytes actually published.

The parser drops content, reasoning and error/stderr text before persistence.
Limits are1MiB per frame,32MiB total,2000 projected frames including discarded
ones, and16KiB per projection/event (individual allowed fields have smaller bounds).
Distinct session/thread identity is mandatory; terminal is not acceptance.

Offline retention requires a coherent closed synthetic binding, unchanged protected
inputs/modes and an external oracle hash frozen in the existing environment object.
Source, prior restore, journal, vault and new restore cannot overlap. An explicitly
synthetic observation uses `checks=[]` and nine null telemetry fields; it is never
registered as a model receipt. Existing finalize/qualify/restore functions retain
and restore the candidate. Tests compare literal3 against focal4 without executing
candidate code; the known public case is instrument calibration, not holdout.

`qualification_report` is an observational projection, not a validator for arbitrary
caller-supplied protocol/candidate/oracle assertions. It cannot grant authority:
`runtime_qualified`, `replay_ready`, `causal_eligible`, `economic_eligible` are always
false and `cost_usd` is null. The writer-boundary and oracle-origin gaps remain.
Controlled child-process tests do not qualify detached native writers, effective
instructions or external isolation. The authorized independent review returned
reject/medium and local counterproofs confirmed the resend/error-boundary gaps;
the earlier B2 approval does not transfer. Runtime design/grant and D measurement
remain separate gates. No production session is read or interrupted.

## B1: explicit offline input capture and restore

B1 adds byte retention, not native session enrollment. The core accepts declared
execution variants without choosing a provider/model or inventing argv. Only
explicitly allowlisted task artifacts are read; a declared `binding_id` is not
proof that a session has been armed. Capture does not execute the declared argv
or acceptance commands, initialize `.007`, or read host transcripts/settings.
It runs local Git only to record the committed base identity.

Minimal native-host configuration (all named files must already exist):

```json
{
  "schema": "007-framework/capture-config/v2",
  "files": ["task.txt", "context.txt", "acceptance.json", "environment.json", "solution.py"],
  "prompt_file": "task.txt",
  "context_files": ["context.txt"],
  "acceptance_file": "acceptance.json",
  "environment_file": "environment.json",
  "output_files": ["solution.py"],
  "execution": {
    "kind": "native-host", "adapter": "fixture-hooks",
    "surface": "desktop", "binding_id": "example-binding"
  },
  "requested": null,
  "executor_timeout_s": null,
  "exclusions": [".git", ".007"],
  "external_inputs": []
}
```

`acceptance.json` uses the existing `007-framework/acceptance/v1` contract;
`environment.json` is an explicit JSON object. A native route may be null or a
complete declared `{provider, model, effort}`; it is not served-route evidence.
Native timeout must be null because the capturer does not control the host.
Surface is exactly `terminal` or `desktop`; adapter and binding use safe IDs.

For the command variant, keep the common fields above and replace exactly these
three fields (argv must name the actual intended command, never a placeholder
invented to impersonate a native session):

```json
{
  "execution": {"kind": "command", "argv": ["python3", "solution.py"]},
  "requested": {"provider": "fixture", "model": "fixture", "effort": "medium"},
  "executor_timeout_s": 30
}
```

The route here labels synthetic test data only. Command timeout is an integer
1–3600; native-host rejects argv. Both variants require exact keys, including
explicit nulls where applicable. Missing fields do not acquire defaults.

Example for an already prepared, committed synthetic checkout:

```sh
python3 scripts/replay_capture.py capture \
  --repo /absolute/synthetic-repo --project-id example --task-id solve-one \
  --config /absolute/capture-v2.json --vault-root /absolute/private-vault \
  --attempt-id attempt-one
python3 scripts/replay_capture.py restore \
  --project-id example --task-id solve-one --attempt-id attempt-one \
  --vault-root /absolute/private-vault --manifest example/attempt-one/input.json \
  --sha256 DIGEST_RETURNED_BY_CAPTURE --out /absolute/new-restore-directory
```

Capture stdout is only `{manifest, sha256}`. Restore retains its v1 summary
fields. Invalid flags and operational errors return 2 without echoing private
arguments or payloads. Capture requires an explicit vault; only restore retains
the legacy default vault. Existing directories/files must be owner-only
(directories 0700; vault artifacts 0600). Symlinks and replacements are refused.
Budgets remain 8 MiB/file, 64 MiB/aggregate, 5000 entries, 1 MiB/manifest.

v1 still uses `<project>/<task>/input.json`; v2 uses
`<project>/<attempt>/input.json` with both identities in the manifest. An attempt
is unique per project, not a new dataset sample. Collisions with any v1, v2 or
partially published case refuse without overwrite, migration or automatic retry.
Restore optionally requires the exact attempt; v1 rejects an attempt argument.
Input/result/followup links bind exact hashes and the validated case directory.

**B1 v2 is not executable replay.** begin/run/record refuse it before lifecycle
publication; generation refuses before workspace creation or budget reservation;
recheck runs no oracle and reports `v2-execution-unqualified`. Intact candidates
may be curated observationally, never made replay-ready or causal/economic
evidence. v2 dashboard discovery is not integrated. B2's offline lifecycle is
described below; real Terminal/Desktop qualification and authorized private-project
capture remain pending. B1 received one independent pre-fix approval; the two
review corrections have local regression/integrated proof, not re-review approval.

## Capability and evidence matrix

Official source: [Codex hooks](https://learn.chatgpt.com/docs/hooks), fetched
2026-10-16. `codex --version` returned `codex-cli 0.160.1`; this identifies the
installed terminal binary, not the Desktop build or a live hook producer.

| Field / boundary | Source | Evidence in A | Remaining gap |
|---|---|---|---|
| Session, turn, tool-call IDs | Hook `session_id`, `turn_id`, `tool_use_id` | Documented shapes + synthetic fixture tests | Runtime identity/binding unqualified |
| Event kind | Seven lifecycle hook names | Projection and malformed/unknown event rejection | Other hooks and specialized paths unsupported |
| Model | Hook `model` | Retained as `model_reported`; absent is null | Not served-provider proof; no effort/usage inferred |
| Host version | Explicit trusted caller metadata | `normalize_hook` accepts it; offline CLI uses null | No host discovery/auto-attestation |
| Surface | Caller argument `terminal` / `desktop` | Enum validated | A fixture label is not Desktop qualification |
| Observation time | Observer UTC clock | RFC3339 validation | Not native event time or causal ordering |
| Prompt/context/tool output | No permitted source in A | Excluded, even from hashes | Context and generation replay unqualified |
| Children | Subagent events / exposed child ID | Rejected with fixed gap code | No child accounting or parent attribution |
| Usage/cost | No source in A | No fields or numeric defaults emitted | OTel/request join/privacy not established |

Terminal fresh/resumed, Desktop fresh/resumed and child sessions each remain
`runtime-unqualified`. Hook/trust/exporter configuration was not inventoried or
changed. Hosted tools such as WebSearch do not have local tool hooks; `write_stdin`
does not repeat PreToolUse for an existing process. Hook completion does not prove
process cleanup or absence of external writers. Before D, establish an exact
request/turn join and privacy-safe source; no speculative collector or watcher.

## Interfaces

`scripts/codex_capture.py` reads at most 1 MiB + one overflow-detection byte from
stdin, projects the allowed metadata and calls `scripts/native_capture.py`.
Success: stdout `{}`, exit 0, no instructions to the model. Failure: exit 1 and a
fixed error code on stderr. It never returns a permission decision, rewrite,
additional context or Stop continuation. Failure is **not** enforcement against
the host's primary work.

Offline example, synthetic input only; this does not configure Codex hooks:

```sh
capture_example="$(mktemp -d /private/tmp/007-native-example.XXXXXX)"
printf '%s\n' '{"hook_event_name":"UserPromptSubmit","session_id":"synthetic-1","turn_id":"turn-1","model":"fixture"}' |
  python3 scripts/codex_capture.py --surface terminal --state-dir "$capture_example/state" --binding-id example
python3 scripts/native_capture.py --state-dir "$capture_example/state" --binding-id example
```

`binding-id` is currently a caller-declared **journal partition**, not proof of a
reserved task or execution authority. B must establish the prospective binding.
Do not use this script as an automatically enrolled global hook yet.

The diagnostic returns only `schema`, `coverage`, `event_count`, `gaps`. Exit 0
means the journal could be inspected, not that the work passed. Coverage is
`partial` or `invalid`, never `complete`. Missing/unsafe/unreadable journals return
nonzero with no fabricated zero-work report. A complete set of observed hook
events still has unobserved context/usage and unqualified runtime gaps.

## Custody and failure rules

- Envelope: `007-framework/native-event/v1`; summary: `007-framework/native-summary/v1`.
- Existing replay manifests, receipts and fresh-command CLI telemetry are unchanged.
- Identity key: SHA-256 of the compact JSON array of adapter, kind, session, turn,
  tool-call and agent IDs. Observation time is excluded from duplicate comparison.
- Same key and same normalized content is an idempotent duplicate. Different
  content preserves the first event and records a conflict. No random retry key.
- Match tool starts/finishes by IDs, not arrival order or time proximity. An
  unmatched tool event remains a gap. Stop is not acceptance or a task boundary.
- Paths: `<root>/<binding>/events/<key>.json` and `gaps/<fixed-code>.json`.
  Directories require 0700/current owner; files require 0600/current owner.
  Symlink paths, traversal, special files and invalid shapes are rejected.
  The root's parent must already exist; missing ancestors are never recursively
  created outside the directory-publication synchronization boundary.
- Bounds: 16 KiB/normalized event, 2000 events/partition, closed finite gap codes.
  No silent truncation, eviction or TTL. Reads are bounded too.
- Atomic publication reuses `replay_capture.write_bytes_no_replace`, including
  file/directory fsync and no replacement. Directory publication is synchronized
  before event writes. Published-but-uncertain failure is reported as failure.
- A per-partition atomic directory lock serializes writers, not diagnostic reads.
  A busy lock returns immediately; it is never removed by a competing caller.
  Controlled exit releases only its own unchanged lock. Crash leftovers require
  human recovery after confirming no owner remains; no age/PID-based auto-delete.
- Diagnostics check for an existing lock before/after reading, without claiming it.
  They inspect a bounded listing of immutable published entries, not a transactional
  snapshot. A completed concurrent append can be absent from this observation;
  `partial` never means complete or ready for admission. Temporary/unknown names,
  disappearance, corruption and a still-active writer cause a sanitized failure,
  not a skipped entry or retry loop. The 2000-event write/read bound is unchanged.
- Gap-write failure is not recursively logged or called delivered. If the storage
  cannot record an error, the command still returns failure. Invisible host events
  cannot be counted. Same-UID tampering/producer authenticity is not solved by hashes.

The state directory should be on a supported local filesystem. This increment is
qualified offline on macOS/Python 3.12; no Windows, remote filesystem, power-loss
hardware or adversarial same-user isolation claim is made. Runtime overhead and
retention policy must be qualified before enrollment. No installation rollback is
needed for A because nothing was activated; preserve evidence and old locks.

## Verification

```sh
python3 -m unittest discover -s tests -p test_native_capture.py -v
python3 -m unittest discover -s tests -p test_codex_capture.py -v
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
```

Tests use disposable synthetic directories and subprocesses, not model sessions.
They exercise actual persistence/CLI output, sensitive sentinels, malformed JSON,
byte/count limits, duplicate/conflicting events, reorder, orphan calls, path
denial, locks and injected fsync failure. Independent review and live enrollment
remain separate gates. Local checks do not establish economic ROI.

## Next calibration questions: algorithms and system design

Marcus clarified **system design**, not design-system/UI work. The existing public
fixture archive is a tiny value-change oracle; it does not already provide these
benchmarks. The following are authored specifications for a later isolated
calibration stage, **not implemented solvers or completed experiments**:

| Case | Frozen behavior to test | Focal negative |
|---|---|---|
| LRU cache, capacity 2 | `put(a,1), put(b,2), get(a), put(c,3)` returns 1 for the first read; b is evicted, a/c retained; update preserves capacity | FIFO eviction or cache size exceeds 2 |
| Idempotent queue consumer | Duplicate deliveries with the same operation ID produce one committed effect; crash between commit and acknowledgement is retried without a second effect; poison item does not block unrelated work | Mark-before-commit loses work; commit-before-dedupe duplicates effects |
| Atomic sliding-window limiter | Limit 2, window 1000 ms, interval `(now-1000, now]`: calls at 0/0 allowed, third denied; at 1000 capacity renews; concurrent admission never exceeds 2; tenants remain isolated | Fixed-window burst, non-atomic check/increment or cross-tenant leakage |

Use virtual clocks, deterministic failure schedules, positive controls and seeded
faults to evaluate these contracts. Architecture claims need executable invariants
and explicit assumptions (e.g. atomic storage), not a subjective diagram score.
Public GitHub cases require pinned source/license, isolation and separation from
holdout; familiar interview questions may be contaminated by prior model exposure.
Do not fetch/run arbitrary benchmark code or launch model sessions automatically.
Such calibration can validate the mechanism without interrupting the user's private project, but
cannot replace prospective real-task evidence or prove monetary ROI by itself.

## Ponytail v5.3.0 source assessment — 2026-10-16

Pinned source: `DietrichGebert/ponytail`, tag `v5.3.0`, full commit
`742e0abae1501e12d1254a81d05f16bba10d08c1`, resolved with `git ls-remote`
and checked against the isolated source clone. This is a source assessment, not
an installation, a signed-release attestation or live-host qualification.

**Decision:** reuse architectural lessons and negative cases, not the band ledger
as a replay/accounting authority. No upstream code or dependency was copied into 007.

### What is portable, and what is not

The rules are portable across agents. The new band imports `claude-code` and uses
its `atom/read/update`, `session.*`, `turn.complete`, `tool.call` and UI APIs.
It does not choose a model, but this does not make that telemetry host/provider
agnostic. The README limits the band UI to Claude Code 2.1.290+ terminal/Desktop,
excluding VS Code chat, cloud and `claude -p`. Codex support for the rules is not
proof of Codex support for this module: the pinned
[Codex manifest](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/.codex-plugin/plugin.json)
loads only the common lifecycle hook JSON, whereas the Claude manifest additionally
loads `claude-band.json` and its `register.tsx` module.

A host-specific adapter is compatible with 007 agnosticism: keep identities,
evidence rules and admission in the common core, and qualify each adapter's
capabilities explicitly. There is no need for a universal proxy to achieve this.

### Source-grounded findings

All links below use the verified commit, not the moving main branch.

| Mechanism | Source | Consequence for 007 |
|---|---|---|
| Session cost/turn totals from the host; per-turn usage and duration from events; child cost not added again | [register.tsx:256–309](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/hooks/band/register.tsx#L256-L309) | Prefer native observations over token-price guesses. Still prove event dedupe, counter scope, resets, parent inclusion and cost basis. No per-attempt model/effort provenance is exported. |
| One task equals one session segment; key uses only first eight session characters plus startedAt | [metrics.ts:184–244](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/hooks/band/metrics.ts#L184-L244) | Keep task, attempt, session and turn distinct. Need explicit prospective binding, not a title or /clear. Constructed same-prefix/same-time sessions collide. |
| Resume stores only total/output; remainder becomes input and cache buckets become zero | [metrics.ts:207–222](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/hooks/band/metrics.ts#L207-L222) | Preserve native categories and unknowns. In a synthetic case, input 10/cache 100+30 becomes input 140/cache 0+0 while total 160 survives. |
| Whole-project CSV read/modify/write; mutable rows; board rebuilt from all ledgers | [register.tsx:119–160](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/hooks/band/register.tsx#L119-L160), [metrics.ts:268–283](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/hooks/band/metrics.ts#L268-L283) | Not an immutable event store. No application-level transaction/lock or retention bound in this path. Stale concurrent reads can produce lost updates; actual host filesystem scheduling remains untested. Project basename/sanitization is not checkout identity. |
| Missing/malformed numbers become zero; CSV cost rounded to cents | [board.ts:64–80](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/hooks/band/board.ts#L64-L80), [metrics.ts:268–283](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/hooks/band/metrics.ts#L268-L283) | Useful display projection, unsuitable as authoritative economics. Preserve raw precision, source/basis and null; absence is not free work. |
| Tests recognized by command regex and tool error; stale set only for recognized Edit/Write code files; reuse is name/regex matching | [register.tsx:216–254](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/hooks/band/register.tsx#L216-L254), [metrics.ts:63–105](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/hooks/band/metrics.ts#L63-L105) | Reuse percentage is a heuristic, not semantic reuse or ROI. Test badge is not a frozen oracle. Synthetic echo is recognized as a test; unittest is not; a comment can count as a call. Shell/config edits need separate invalidation. |
| First prompt names task; transcript is scanned for renamed title; webhook optional, names enabled by default when configured | [register.tsx:108–151](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/hooks/band/register.tsx#L108-L151), [register.tsx:200–214](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/hooks/band/register.tsx#L200-L214), [plugin.json](https://github.com/DietrichGebert/ponytail/blob/742e0abae1501e12d1254a81d05f16bba10d08c1/.claude-plugin/plugin.json#L14-L38) | Do not adopt transcript/title capture under the current privacy contract. `sendNames=false` clears name, not project/session. Hiding the band only gates rendering; it is not disabling capture/export. |

The standalone board is a useful low-infrastructure pattern: generated local HTML,
no server, escaped embedded data and explicit cost-not-bill wording. 007 already
has reporting, so a second board is not the next increment. Failure notices and
fire-and-forget optional export protect responsiveness but do not prove durable
delivery. The source's catch/next behavior was not runtime-qualified here.

### Diagnostic evidence and its limits

Ten deterministic checks ran against the actual pinned `metrics.ts`/`board.ts`
helpers, with Node 26.7.0 built-in TypeScript stripping and VM modules. Synthetic
inputs only; no plugin registration, model call, HTTP dispatch or local transcript.
In addition to the table: a valid multiline CSV title fails to round-trip on
upsert; duplicate `addTokens` calls double the observation. The latter is a
missing helper-level dedupe guarantee, not proof that the host delivers duplicates.
The lost-update check is an interleaving model, not a real two-process host test.
Node emitted experimental-API warnings; these checks are diagnostics, not a new
supported runtime dependency of 007.

`tests/band.test.tsx` uses `claude-code/testing`. It was inspected, not executed.
The checked default `npm test`/CI runs `tests/*.test.js` and pi tests, not that TSX
file; this does not prove the author did not run it separately. No full Ponytail
suite or live terminal/Desktop rendering qualification was performed.

### Priority changes to the existing plan

1. **A follow-up, low effort/high impact:** remove diagnostic-induced writer
   contention, preserving immutable publication and hard bounds. This does not
   fix writer-versus-writer contention or guarantee persistence of every refusal.
2. **B, medium/high effort/critical:** freeze full project/task/attempt/session/turn
   binding and pre-state/oracle references. Add same-name-project, same-prefix-ID,
   resume and /clear counterexamples; no automatic session-to-task conversion.
3. **C/D, conditional:** qualify native metadata/usage per host without transcript
   access. Require dedupe, loss visibility, null preservation, category retention
   across resume, exact scope/child inclusion and cost basis. No source means N/A.
4. **E/F, gated:** restore/oracle and prospective real task, then causal experiment.
   Hooks, a board and reduced tokens cannot establish replay readiness or positive ROI.

## CodeHealth study: evidence and implications for 007 (2026-10-16)

Sources: [arXiv v1, full paper](https://arxiv.org/html/2610.21914v1),
[canonical replication record](https://doi.org/10.5281/zenodo.22127920),
[inspected versioned archive](https://doi.org/10.5281/zenodo.23392202).
The article is distributed under CC BY 4.0. Assessment is a paraphrase with
attribution, not a reproduction. Public-source research was delegated separately;
the coordinator checked the primary tables, source excerpts and retained CSV
aggregates. This is not independent review of the 007 candidate.

### What the study establishes

The observational sample contains 465 merged, agent-authored PRs from 246 public
repositories with at least 100 stars, in five languages. A frozen pipeline uses
four review roles and one batch-fix role, separately with DeepSeek v4 Flash,
Qwen3.6-35B-A3B-NVFP4 and Claude Sonnet 5. CodeHealth is scored at the PR head,
before review, over changed files weighted by changed lines. It is not the
quality of the entire repository or strictly its pre-PR state (§§3.2–3.8).

The primary mixed model is `log(tokens) ~ CH + log(changed lines) + language +
(1|repo)`, fitted separately per model. It is an adjusted association, not a
randomized refactoring experiment or an out-of-sample budget predictor.

| Model | Analyzed PRs | Associated token reduction per CH point, 95% CI | CH coefficient after adding file size, 95% CI |
|---|---:|---|---|
| DeepSeek | 453 | 6.1% [3.4%, 8.6%] | -0.009 [-0.044, 0.026] |
| Qwen | 461 | 4.8% [1.4%, 8.1%] | -0.023 [-0.071, 0.025] |
| Sonnet | 453 | 3.5% [0.1%, 6.8%] | +0.018 [-0.027, 0.064] |

Sources: Tables 8 and 15. The registered criterion (all coefficients negative,
at least two intervals excluding zero) passes. After the exploratory file-size
adjustment, none of the intervals excludes zero. The median scored file has
2,146 lines in the unhealthy group versus 128 in the healthy group. CH and file
size strongly overlap: their association cannot be separated by this sample.
The authors interpret mediation; confounding, overlapping metric components and
collinearity remain compatible explanations. Attenuation is not causal proof.

Review represents a median 84.7%, 86.2% and 85.8% of tokens, respectively (Table
12). Lower CH accompanies more review iterations and uncached input, without a
significant relationship with comment count (Table 13). That does not establish
equally useful findings: comments and fixes were not independently graded for
correctness. Complex Method and Complex Conditional correlate with fix cost;
Code Duplication does not pass the registered test (Table 10). Median post-fix
CH change is zero; this does not prove unchanged correctness or maintainability.

### Strengths to reuse, limits not to inherit

1. **Sampling before spending.** Crossed CH/footprint strata, per-repository caps
   and excluded pilot PRs correct earlier misleading pilot results. Preserve
   logical-task/family grouping in 007; attempts and models on the same task are
   not independent samples. The sample's deliberate balance also means that its
   null CH/PR-size relationship is not proof of population independence.
2. **Separate instruments.** Different tokenizers, providers, quantization,
   cache regimes and guards preclude a naive model leaderboard. An agnostic
   interface must retain these differences, not erase them. Repeated runs can
   estimate variability within each declared route; cross-route comparisons
   need their own matched protocol and accounting basis.
3. **Instrument defects can look like expensive tasks.** The authors found an
   11.3-million-character tool result, added bounds/pagination, archived and
   recollected 67 affected PRs (§3.12). Freeze tool/parser versions as well as
   prompts; an amended instrument creates a new epoch. In 007, retention rejects
   budget overflow instead of silently truncating. A later bounded presentation
   layer must make omissions explicit and preserve recoverable allowed source.
4. **Pre-registration is not automatically prospective.** Reviews for 241
   DeepSeek and 84 Qwen PRs had already completed when registration was filed;
   authors report no peeking and later corrected the chronology. That is useful
   transparency, but weaker than inputs/protocol frozen before any outcome.
   007 must keep retrospective calibration and prospective proof distinct.
5. **Count failures in economics.** Review guard stops are retained, while 28
   fix-stopped PR/model runs are excluded (§3.10). Qwen's individual slope loses
   significance when 103 guard-affected PRs are removed. These rules define a
   scientific estimand, not a complete operational cost ledger. 007 must retain
   all launch/attempt/retry costs and explicitly mark unmeasured spend; failures
   cannot disappear from cost per accepted outcome.
6. **Do not equate cached tokens with extra tokens.** Here cached input is a
   subset of input. Input + output is volume, not billed money. Cache creation,
   cache reads, uncached input and output can have distinct prices; local compute
   has a different cost basis. Reasoning must not be double-counted inside output.
7. **Replicate selectively, without outcome-based cherry-picking.** A 27-PR
   subsample, three runs each, estimates single-run reliability of .948/.695/.962
   (Table 16). This supports measuring repeatability; it does not prescribe three
   runs as sufficient for every 007 mechanism or justify copying those numbers
   to another runtime. Nominal temperature zero is not determinism.
8. **Score is diagnostic, not approval.** CodeHealth is proprietary and the
   vendor affiliation is declared (§6.3/conflict statement). Independent metrics
   and correctness oracles matter. Do not gate 007 on a vendor score, equate more
   comments with value, or assume five agents outperform one: there is no such
   ablation in the study.

### Replication-code checks and reproducibility boundary

The inspected archive is `agentic-review-codehealth-20261015T100248Z.tar.gz`,
100,459,710 bytes. Its MD5 matches the Zenodo record:
`41586c3c51ddd4a5b378d2806bc3b28b`. This verifies the downloaded archive against
that record, not the provenance of each historical execution. No downloaded
code, model pipeline or analyzer was executed.

- `src/lib/agent_session.py:382–386` omits temperature for Claude although the
  article says all calls use temperature zero. The current code alone cannot
  establish which effective parameters every historical request received.
- Its `_accumulate` ignores absent usage and uses zero defaults for missing
  token fields. That behavior is not an acceptable missing-data policy for 007.
  It is not evidence that the study's retained rows actually lost usage.
- Independent arithmetic on the shipped retained CSV gives 453/461/453 rows and
  cached/input shares of 92.808%/81.912%/89.560%, versus 93.2%/81.9%/89.7% in
  Table 4. The paper describes a full-collection denominator; the researcher
  also reported small differences using all structured run records. The exact
  published aggregation is not reconciled here. Do not silently replace the
  table or infer that the primary regression is wrong.
- The archive's source/data supports re-analysis without new model calls, but
  exact hosted weights, CodeScene availability and external commits are separate
  dependencies. The README warns of alias drift. OSF version history could not
  be independently fetched in this review; the chronology above is the authors'
  disclosed account, not a verified registration audit.
- Review tool outputs are recorded by size and reconstructed from deterministic
  tools/commit/arguments, not retained as full responses. Intermediate fix-edit
  payloads are omitted (§3.13). Consequently, artifact restoration, reconstruction
  of tool responses, oracle replay and rerunning generation are different proof
  levels. The package does not provide byte-exact intermediate edit replay.

### Prioritized application, without widening B1

These are recommendations for the existing next gates, not implemented features
or authority to install, collect private content or spend.

| Priority / existing gate | Smallest useful change | Effort / impact / waste risk | Verifiable acceptance |
|---|---|---|---|
| P0 / B1 | Exact task-versus-attempt identity; retained bytes must not become execution proof | Low incremental / critical / low | Wrong refs, collisions, budget use and false replay-ready claims refused; v1 unchanged |
| P0 / B2 + C | Bind one explicit task/attempt to checkout, session and turn after durable input | Medium / critical / low if capability-first | Ambiguous/missing ID stays unavailable; no time/title heuristic; separate Terminal/Desktop proof |
| P0 / D | Qualify usage semantics and full cost coverage before building collection | Medium / critical / high if source is guessed | Missing usage stays null; replayed events idempotent; cache/reasoning/parent-child totals not doubled; retries retained |
| P1 / E | Deterministic algorithm/system-design cases plus focal mutants and independent acceptance | Medium / high / low | Positive and negative controls; no repeated task crosses calibration/holdout; restore without original checkout |
| P1 / F | One paired OLD×NEW navigation/context intervention | Medium / high / bounded | Same task/route/oracle; quality non-inferiority, all-attempt cost and overhead, controlled order and frozen epoch |
| P2 / after F | Targeted structural refactor or extra specialist, only for measured hotspots | Medium/high / uncertain / high if global | Net benefit covers implementation, added review/context, regressions and follow-up; otherwise reject |

For the first future context experiment, compare existing competent navigation
against one bounded, loss-visible retrieval mechanism, without simultaneously
changing model, prompts, reviewer count or file structure. Record bytes exposed,
repeated reads and token coverage only from permitted metadata; do not introduce
transcript capture. Smaller context is beneficial only if independent acceptance
and escaped-defect checks do not deteriorate. Use calibration variance to size
the subsequent experiment, not the paper's effect size as a promised benefit.

Economic decision rule: quality gates first; then whole-cohort cost per accepted
outcome and rework follow-up. Monetary ROI additionally requires measured benefit,
initial investment and recurring operating cost. Token reduction, restored bytes,
hashes and agreement between reviewers cannot fill those missing fields.

## P0 capability findings and B2 design brief — 2026-10-16

Historical discovery status: **no native runtime qualification**. The subsequent
B2 spec/plan were approved and implemented offline (see the B2 section below);
no live capture, collector, enrollment or new execution authority follows here.
The goal is auditable replay inputs and refutable economics across hosts/models,
not automatic evidence promotion or a promise of positive ROI.

### Evidence reached, and its limits

Official documentation was searched and opened. Separately, the installed
`codex-cli 0.160.1` generated its app-server JSON schemas successfully without
starting a server, conversation or model. Local evidence and exact schema hashes
are retained in the private P0 evidence directory recorded in the work ledger.
This proves a CLI protocol
shape, not runtime delivery, installed Desktop capability or producer authenticity.
The generator emitted a PATH-alias permission warning but exited 0.

- [Hooks](https://learn.chatgpt.com/docs/hooks): common metadata includes
  `session_id` and `cwd`; `UserPromptSubmit` adds `turn_id`. Child hooks can use
  the parent's session ID. Matching hooks may start concurrently. Background
  hooks cannot enforce a barrier; tool coverage excludes hosted paths and does
  not re-run PreToolUse for `write_stdin`. A callback failure is not necessarily
  a tool denial. No documented application task/attempt token links a prompt
  hook to an approved 007 contract.
- [App Server](https://learn.chatgpt.com/docs/app-server): `thread.sessionId`
  denotes the live session-tree root and is not interchangeable with thread ID.
  `turn/steer` can add input without changing turn ID. `turn/start` returns the
  server's turn identity; its response alone is not a documented pre-mutation
  barrier. Usage notifications exist, but the opened page does not settle their
  complete aggregation/deduplication semantics. Notification opt-out names are
  exact matches, not an allowlist of permitted future event types.
- [Advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced):
  OTel logs include request/stream events and common conversation metadata;
  export is asynchronous. `turn.token_usage` is a histogram with token-type
  labels, not a task ledger. The documented tags do not establish an exact
  per-request/per-turn join suitable for this contract.
- [Telemetry privacy](https://learn.chatgpt.com/docs/agent-approvals-security):
  disabling prompt logging does not suppress every content-bearing event;
  tool-result events can contain output snippets. Do not enable an exporter
  until filtering before prohibited persistence/egress is demonstrated.
- [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode):
  the documented JSON sample has a thread ID and terminal usage, but its
  `turn.started` example has no turn ID. The stream can also carry reasoning,
  messages and command output. It is not an approved raw collection source.
- [Execution surfaces](https://learn.chatgpt.com/docs/enterprise/agent-security):
  local-only orchestration and cloud orchestration with local execution have
  different hook support. A local execution directory does not prove a local
  orchestrator. Terminal and Desktop require separate runtime qualification.

### Concrete local protocol findings

| Generated schema | Observed shape | Required 007 consequence |
|---|---|---|
| `ThreadStartResponse` | Thread has distinct `id` and `sessionId`; session ID is shared within a session tree | Keep namespaces and explicit thread-to-session evidence; never join by assumed equality or title |
| `TurnStartParams` / `TurnStartResponse` | Start requires `threadId` and `input`, offers `clientUserMessageId`, and has no caller-selected `turnId`; returned Turn has a generated `id` | The optional client field is not proof of idempotency or hook correlation; no blind retry or first-event selection |
| `ThreadTokenUsageUpdatedNotification` | Required `threadId`, `turnId`, `tokenUsage`; usage contains `last` and `total` | Exact turn correlation is promising; meanings, ordering, completeness and retries still need proof |
| `TokenUsageBreakdown` | Required input/cached-input/output/reasoning-output/total integers; optional `cacheWriteInputTokens` with schema default 0 | Preserve presence before any default application; omission remains unknown, not measured zero; validate nonnegative integers separately |

The usage notification has no declared request ID, sequence number, billed cost
or served-route identity. A schema default describes decoding, not measurement.
Neither the names `last`/`total` nor a cache counter prove whether children,
automatic review, compaction, failures and retries are included. Do not add these
sources together, subtract snapshots or calculate API-equivalent cost yet.

### Existing integration gap (source inspection, no business data)

`codex_capture.normalize_hook` deliberately drops `cwd` and payload content.
Its CLI's `binding-id` selects storage; `native_capture.append_event` validates
event structure and integrity, not a task/checkout/session contract. Thus an
otherwise valid event is not evidence that the selected binding was authorized.
Do not weaken this honest observational contract or reinterpret historical v1
events as verified bindings.

`replay_capture.capture_input` already retains checkout/configuration and v2
attempt identity, while `validate_replay_ref` checks the manifest/reference.
`framework_cli.begin_task` deliberately rejects v2 before publishing task-start;
`replay_eval` also refuses execution. B2 must not remove either guard merely to
make a binding test pass. A task-start record would add a separate lifecycle
contract and needs an atomicity/recovery design with the binding publication.

### Smallest proposed B2 boundary (for approval, not a frozen API)

Reuse the private journal and vault; add no daemon, database, provider policy or
transcript watcher. Keep capture, attribution, replay admission and execution
authorization as separate decisions. Proposed operations:

1. **Arm:** validate the durable v2 input/reference against project/task/attempt,
   enrolled checkout and declared scope/authority. Record the exact producer,
   surface and available native identities. A reservation without a known turn
   is not a consumed binding. A local claim coordinates cooperating writers;
   it does not prove exclusive checkout ownership or authorize business work.
2. **Consume:** bind only an explicitly correlated producer start to that
   reservation, once, with the exact native turn and thread/session namespace.
   Replaying the same binding is idempotent; different identity/content conflicts
   preserve the original. Hooks alone currently lack a demonstrated correlation
   bridge. If exact correlation or pre-mutation ordering is unavailable, retain
   observation only; never consume the next/first/last turn by inference.
3. **Close:** record the exact bound terminal outcome independently of acceptance
   and cleanup. Missing/late/conflicting events or uncertain publication keep the
   result incomplete. Stop does not release a checkout for reuse or certify that
   detached processes have ended. Preserve claims/evidence; no automatic stale
   lock deletion or rearming after an uncertain write.

One turn per attempt is a limit, not proof of one immutable request: steering,
scope/route changes, fork/resume and children require explicit treatment. New
scope needs a new attempt; if changed work already ran, preserve its events and
cost gaps rather than retroactively label it prospective. No prompt hashes or
content are added to the metadata-only observer to work around missing identity.

| Approach | Effort / impact / waste | Decision proposed |
|---|---|---|
| Explicit one-turn binding using existing storage, followed by a qualified producer bridge | Medium / critical / bounded | Recommended; freeze the correlation and task-start recovery contract before implementation |
| Install hooks/OTel now and infer assignments afterwards | Low initial / misleading / high | Reject: missing correlation, failure-boundary and privacy proofs |
| Replace Desktop/terminal with a new controlled executor now | High / potentially strong / high | Defer; broader product/authority change, not necessary for offline contract work |

### Usage-source qualification before collection (P0 / D)

| Source | Permitted conclusion now | Missing gate |
|---|---|---|
| Existing hook projection | Observed lifecycle metadata | Usage and full requested/served route are absent |
| Generated app-server usage schema | Named counters and exact thread/turn fields exist in CLI protocol | Native semantics, reset/order/dedupe, terminal completeness, child/retry coverage and privacy |
| CLI JSON terminal usage | Candidate terminal summary shape | Exact turn binding, failures/interrupt coverage and pre-persistence projection |
| OTel logs | Candidate request/stream metadata | Exact join, delivery loss, duplicate identity and content filtering |
| OTel histograms | Aggregate instrumentation diagnostics | Not attributable accounting evidence; do not promote to per-task costs |
| Billing or explicit allocation | Potential billed or allocated amount | No source admitted here; API-equivalent, billed and subscription-allocated values stay distinct |

For every admitted source, preserve original field presence, scope, units,
delta/cumulative semantics, producer/adapter version, epoch and inclusion rules.
Unknown remains `null`. Do not sum reasoning twice, add cached input to an
already inclusive input count, double-count inclusive parents plus children, or
drop failed requests. Incomplete known components may be reported as a labeled
subtotal, never as the full task cost or a qualified ROI denominator.

### Counterproofs and next decision

Before B2 code, agree on the producer-to-reservation bridge and task-start
transaction. Required synthetic counterproofs: two threads sharing a session;
same turn label in different namespaces; wrong checkout/task/attempt/reference;
duplicate and conflicting consumes; unrelated prompt during an armed reservation;
steering without a new turn; route change; fork/child attribution; missing terminal;
writer collision; crash between journal/binding/task-start publications; fsync
failure after publication; v1 compatibility and v2 execution still refused.

For usage, require absent cache-write versus explicit zero; negative/bool counters;
duplicate/late/out-of-order updates; cumulative reset; failure without usage;
inclusive parent versus child usage; unknown served route; and sensitive sentinels
absent from disk/stdout/stderr. These are test requirements, not tests executed.

P1 corpus and OLD×NEW remain after these P0 gates; P2 refactoring/specialists remain
after measured benefit. The design/plan approvals and B1 review described as future
steps in this historical discovery were subsequently resolved for local B2 only.
Independent B2 review and live installation are separate gates. After the first
attempt failed on external quota, one newly authorized review returned reject.
Its concrete defects received a local correction pass; the frozen review did
not cover those corrections or the omitted baseline/consumer bodies. A later
separately authorized final review included those sources and corrected bytes but
timed out after 340 seconds without stdout, stderr or a verdict. Its single-call
grant is consumed; no further review or live installation is authorized.

## B2: explicit offline reservation, consumption and closure

Contract: B2 specification (internal design record, not published).
Execution record: B2 plan (internal design record, not published).
This is a local consistency/custody implementation, not a native producer bridge,
execution authorization or evidence of prospective capture. It requires an
already captured native-host v2 input and an authority artifact included in that
capture. A live authority path is never consulted. Only `synthetic` and `declared`
sources are accepted; there is no `qualified` mode or automatic task discovery.

The journal retains A's `events/` and `gaps/` unchanged. B2 adds
`<binding-id>/binding/reservation.json`, `consumption.json`, `closure.json` and
separate fixed-code `binding/gaps/` markers. Records are immutable 0600 files in
0700 directories; checkout permissions are not changed. Limits: 16 KiB/record,
1 KiB/marker, at most 128 binding directories per root including A-only directories.
Symlinks, extra fields, duplicate JSON keys and nonfinite numbers refuse.

| Operation | Required declaration | Local result |
|---|---|---|
| `arm` | Exact project/task/attempt/binding, v2 ref, checkout path/device/inode, captured authority file, producer, dispatch, source, observation time | `reserved` |
| `consume` | Published reservation-byte hash, identical producer/dispatch/source, exact turn and already-published start-event ref | `bound` |
| `close` | Reservation and consumption byte hashes, explicit matching terminal event and outcome | `closed`, never accepted/approved |
| `close` before consume | Reservation hash, `cancelled-before-consume`, null consumption hash and null terminal ref | `closed`, not proof that no external work ran |
| `inspect` | Explicit binding, journal root and vault root | Observational summary only |

Producer fields are exactly `namespace`, `adapter`, `surface`, `host_version`,
`session_id`, `thread_id`. Session is not inferred to be a thread. Event refs are
exactly `{event_key, sha256}` and can only address the selected binding's published
event files. `turn_start` is required for consumption; `turn_stop`/`interrupt`
map to `stop-observed`/`interrupt-observed`. Agent-child events do not qualify.
There is no next/first/last event selection, prompt hash or content heuristic.

Example commands below assume explicit synthetic record files prepared from a
synthetic capture; they do not manufacture hashes or install any host integration:

```sh
python3 scripts/native_capture.py arm --state-dir /absolute/private-journal --binding-id example-binding --vault-root /absolute/private-vault < reservation.json
python3 scripts/native_capture.py consume --state-dir /absolute/private-journal --binding-id example-binding --vault-root /absolute/private-vault < consumption.json
python3 scripts/native_capture.py close --state-dir /absolute/private-journal --binding-id example-binding --vault-root /absolute/private-vault < closure.json
python3 scripts/native_capture.py inspect --state-dir /absolute/private-journal --binding-id example-binding --vault-root /absolute/private-vault
```

Flags may precede the verb. The original no-verb A inspection remains compatible.
Mutation stdin is one complete record; at most 16385 bytes are read to enforce the
16384-byte bound. Inspect does not read stdin. Successful mutations print only
`{"binding_state":"reserved"}`, `bound`, or `closed` in the same shape, exit 0.
Idempotent repeats ignore only the new `observed_at`; they validate existing
references, preserve original bytes/inode/mtime and return the current state.
Repeating arm or consume after a valid close returns `closed`, never reopens it.

Generate hashes from exact published bytes, not reserialized dictionaries. The
synthetic `BindingFixture` in `tests/test_native_binding.py` constructs all three
records from real fixture files and computes these hashes with SHA-256; those
test records are not operational receipts or replay proof.

Handled mutation/argument failures exit 1, with empty stdout and one fixed stderr code:
`binding-integrity`, `binding-unavailable`, `binding-conflict`, `binding-lock-busy`
or `binding-publication-uncertain`. Those handlers do not print private exceptions
or arguments; B2 stdin I/O failure is unavailable, not an integrity violation.
An interrupt before B2 publication, after safe identity-checked lock cleanup when
needed, exits 130 with `binding-unavailable`; an unavailable import exits 1 with
that same fixed code. Legacy A still propagates those exceptions unchanged.
Legacy calls with an unknown positional retain the `identity-invalid` error.
Inspect prints exactly the specification's summary, exit 0 for partial coverage
and 1 for invalid coverage. Every summary has `execution_authorized=false`,
`replay_admissible=false`, `economic_admissible=false` and
`binding-correlation-unqualified`. Unknown identities/source are null. A's gaps
are preserved; no path, authority content, prompt or output appears in the summary.

The atomic root `.bindings.lock` serializes participating B2 mutations only;
B2 never acquires A's writer lock. An unclosed reservation excludes the same
checkout path **or** device/inode, or the same session within its namespace.
Different namespaces do not by themselves permit the same checkout. No other
root, host, editor or process is covered. Even close does not certify process
termination or permit checkout reuse outside this local protocol.

A competing new reservation or a new consumption after closure is refused
without publishing a binding or conflict marker. A never-published loser may
inspect as absent; that is not proof no external request occurred. Divergence
from an existing immutable record still publishes a conflict marker. Any known
persisted marker blocks mutations across this root, even if its records remain
readable; inspection does not erase the marker or authorize recovery.

Visible publication followed by fsync/cleanup failure is uncertain, not success.
Keep record and owned lock when possible; failed unlock may leave no lock, and
the code does not recreate one or claim otherwise. Conflict preserves original
bytes; failed marker publication does not claim a durable marker. No retry under
a new key, force-unlock, cleanup, reset or GC is provided. Human review is required
before recovery. Inspect never repairs state, creates directories or acquires a
writer lock. It checks locks before/after but is not a transactional snapshot and
cannot detect every complete intervening transition or external modification.

For B2 interrupt/import failures, publication starts before the first binding or
marker directory mutation. Once started, preserve the lock and existing bytes and
report `binding-publication-uncertain` (exit 1), even when no record is visible yet
or the publisher has returned. The same conservative result applies to interrupted
lock acquisition before owner verification and interrupted cleanup; a removed lock
is never recreated. Before publication, release only the verified unchanged owned
lock. Lazy authority-import failure makes inspection invalid/unavailable. This is
not forced-process-death handling, automatic partial-directory repair or a change
to the shared publisher/legacy A exception policy.

Consumption is the sole observed-start attribution publication. B2 writes no
legacy task-start, receipt or accounting entry. Closed-binding counterproofs keep
begin/run/record and both replay executors blocked by `v2-execution-unqualified`
before publication, budget, restore, workspace, generator or oracle. Unknown cost
stays unknown; no ROI claim follows from custody, a test pass or a close event.

Local tests cover contracts, concurrency, injected syscall failures, observation,
CLI compatibility/privacy and consumer guards. They do not prove hardware crash
durability, global exclusion, authenticated producers, Desktop/terminal capture,
prospective private-project evidence or economic benefit. The independent pre-correction
B2 verdict on 2026-10-16 was reject; four corrections were locally tested. That
frozen bundle omitted the pre-B2 source and full legacy consumers; coordinator
checks do not retroactively expand its review. A new complete context's first
authorized attempt ended at a 340-second nonstream timeout (exit 143), without
stdout/stderr or verdict. Identity/usage/cost of that attempt remain unmeasured.

A separately and explicitly authorized streaming recovery of the complete context
finished in 565.216 seconds, exit 0, reported model claude-fable-5-1, verdict
approve/highestSeverity medium. The reconciled approval covers offline consistency,
custody and compatibility only; the reviewer did not execute tests or verify hashes.
Requested high effort is CLI evidence, not served-effort attestation; reported
list-price cost is not billing proof. Both grants are consumed; no retry/fallback.

Before C activation, resolve the reviewed operational gaps: the reviewed bytes let
non-listed exceptions bypass lock cleanup/sanitization; A can grow a shared root beyond B2's transition
limit and prevent close; an empty or partially published binding directory makes
root mutations fail closed. Lesser issues are checkout-before-closure error
precedence and owner-stripping umask. No automatic unlock, cap removal, directory
deletion or reinterpretation of uncertain state as absent has been adopted.
The review's ancillary assertion that inspect holds the root lock and scans all
neighbors is incorrect: inspection remains selected-binding and lock-free.
The 450-line checkpoint is a planned limit, not the actual +411/-2 = +409 net delta.
Historical whole-WIP preservation gaps remain; new edits do not inherit this
approval. No hook/OTel/settings, native replay or economic admission is authorized.

Subsequent synthetic diagnostics reproduced nine operational cases. A normal
prepublication writer error alone can leave an empty binding directory that blocks
later arm operations; a physical crash is not required. At 128 total directories
close succeeds; after A adds a 129th it is refused, while selected-binding inspect
can still show reserved/partial. Late consumption with a removed checkout returns
binding-unavailable, not the reviewer's predicted integrity code. Two private
acceptance tests initially remained RED for uncaught ImportError/KeyboardInterrupt.
The subsequent authorized correction adds phase-aware handling in the existing
module and 12 regression methods in `BindingBoundaryTests`. The first ten methods
reproduced 30 failing subcases before the fix; focused native/binding/adapter/reader
validation then passed 101 tests on Python 3.14.7. These tests include real file
publication with injected failures; they are not native operational qualification.
The master plan/ledger records the integrated outcome. Root saturation, ordinary
writer errors leaving partial directories, restrictive umask and new-byte review
remain unresolved; no inherited independent approval or economic claim follows.

### B2 capacity/partial-state amendment — approved local correction

Analysis before this amendment separated three obligations:
finishing an existing reservation, admitting another one, and retaining evidence
over repeated use. They must not be reported as one solved problem.

- `_binding_chains` counts all root directories before inspecting closure state;
  closed bindings still consume the 128-directory capacity. `close` publishes a
  record but retires no directory. Therefore even a healthy, fully closed history
  eventually refuses a new ID. This is a source-derived consequence, not a newly
  executed 129-cycle benchmark or authority to rotate roots.
- Previously both `arm_binding` and `_transition_binding` called that root scan. A-created
  directories can exceed its bound because A's `_case` does not use the B2 root
  lock/admission bound. The earlier 128/129 synthetic probe remains the execution
  evidence; it was not repeated on unchanged relevant code.
- Root-wide taint was intentional: the prior neighbor-marker test required an
  unrelated marker to prevent close. Marcus's new direct “sim” explicitly approves
  changing that contract only for close. The amended regression still requires
  global arm/consume rejection and byte preservation of neighbor markers.
- `_binding_publish` creates directories before the no-replace file publisher.
  A known ordinary prepublication write error can leave empty `binding/`; the
  reader correctly refuses it without a reservation. Making the reader silently
  treat existing partial directories as absent is not an accepted repair.

| Approach | Consequence | Recommendation |
|---|---|---|
| Increase the cap, skip partial neighbors or silently start another root | Postpones saturation or weakens exclusion/evidence; no sustainable lifecycle proof | Reject |
| Add a registry/index plus rotation/retirement now | Could support sustained intake, but introduces multi-record consistency, migration and rollback obligations | Defer until the operational lifecycle contract is approved; not this local repair |
| Separate selected-chain closure from admission; narrowly roll back this call's own empty prepublication directories | Repairs stuck closure and prevents a proven ordinary-failure residue using existing lock/storage; does not create new intake capacity | Approved and implemented locally; independent review/activation remain separate |

Approved local scope: existing native module, binding/readers tests and existing
documentation. Keep schemas, CLI, A behavior and shared publisher unchanged; no new
dependency, process, storage namespace, root rotation or generic recovery command.

1. `close` holds the same B2 root lock, validates the complete selected chain,
   vault, hashes, events, owner/modes and its own gaps, then publish only its closure.
   Neighbor corruption/capacity no longer prevent that closure; they still
   prevent `arm`/`consume`. A selected gap or uncertain/foreign root lock still
   refuses. `closed` explicitly certifies neither root health nor renewed
   capacity, process termination or permission. Three admission flags remain false.
2. On a known ordinary I/O failure before any reservation is visible, the lock
   owner removes only empty directories proven newly created by this call, in
   reverse order, under the existing cooperative lock and identity checks. No
   pre-existing directory, any file, partial history, unknown owner or interrupt/import
   uncertainty would be removed. Any uncertainty in publication, ownership,
   removal or directory synchronization preserves evidence and reports uncertainty;
   no recursive deletion or lock recreation. External non-cooperating process races
   remain outside the current exclusion guarantee. Successful mkdir and verified
   ownership are required; FileExistsError never claims creation. Root/lock and
   directory identities are checked before cleanup, root/lock again before unlock.
3. Required counterproofs: saturated/tainted neighbor allows only a valid selected
   close while new arm/consume still refuse; selected corruption/gaps and lock
   uncertainty still refuse; no-replace/idempotency and v2 consumers stay guarded;
   ordinary write failure leaves no newly owned blocking empty directory, whereas
   pre-existing, replaced, nonempty, concurrent-A and post-link/interrupt states
   are preserved. Fsync/remove failures remain uncertain. RED reproduced 14 failed
   assertions and 12 expected-operation refusals across eight methods. A further
   lock-replacement regression failed before the post-cleanup owner recheck. Final
   focused proof: 109 tests, exit 0; integrated results live in the master/ledger.

This approved amendment intentionally changes the all-mutations root-taint policy only for
closure and permits a narrowly defined cleanup that the previous correction did
not authorize. Independent review of these new bytes remains a separate gate. Existing
partial artifacts and lifetime capacity still require an explicit recovery/retention
policy before C activation; the local repair cannot be presented as that policy.

### Next B2 lifecycle decision — finite qualification versus continuous operation

Marcus's subsequent direct `siga com o plano mais atualizado` accepted the
recommended finite-cohort scope and bounded corrections below. They are now
implemented locally; neither this amendment nor the earlier close/cleanup is
awaiting design approval again. This does not establish C readiness or continuous
capture. Independent review of new bytes remains a separate gate.

The r9 source investigation separated three concerns (the last is now corrected):

- Capacity is historical occupancy, not active concurrency: `_binding_chains`
  counts A-only and closed directories. Archive/move/skip of an old directory
  would affect identity lookup, idempotency, evidence custody and exclusion, not
  merely free space. A's `_case` can independently add directories to that root.
- Partial state predates the current call. Neither missing bytes, elapsed time
  nor absent process proves there was no publication or external execution.
  Existing lock/partial evidence cannot be deleted or treated as absent safely.
- Setup permission failure occurs before lock cleanup starts: `_binding_lock`
  creates the lock, then `_binding_dir` rejects its mode. The recorded 0177-umask
  probe produced mode 0600 and left that lock. The new empty-directory cleanup
  is for known reservation publication failure, not unverified setup. Similarly,
  `_transition_binding` validates a live checkout before checking a cancellation
  when no consumption exists; this explains the historical late-consume result.

| Choice | Benefit | Cost / limit | Recommendation |
|---|---|---|---|
| Finite first qualification cohort with explicit stop | Reuses bounded storage to qualify native capture before investing in retention | Cap 128 remains; tainted/saturated root blocks intake; not continuous operation | Accepted next scope; not an activation grant |
| Permanent admission/history lifecycle now | Could support continued capture without discarding old evidence | Needs authoritative admission, stable historical lookup, crash/recovery consistency, A coexistence, migration and rollback | Separate architectural design, not a small cleanup patch |
| Raise cap, ignore partials, auto-switch root or move closed directories without a custody design | Superficially restores intake | Breaks bounds or cannot prove identity/exclusion/recovery; postpones the same problem | Reject |

Accepted finite policy: preserve all historical state, refuse arm/consume on
taint/capacity and retain selected close when its own chain/lock is valid. Do not
automatically rotate, retry, delete, reset, or infer cross-root exclusion. Any
future C qualification must explicitly enumerate a finite cohort/root and stop
when its admission fails; enrollment/real execution remains separately gated.
This is not resolution of the full product's sustained-capture requirement.

Implemented bounded corrections in the existing native module and binding tests:

1. Honor the caller's umask. Do not chmod paths or temporarily change process-wide
   umask. A newly created root/lock/directory with owner bits stripped should fail
   cleanly (`binding-unavailable`) only when this call's creation, type, uid,
   identity and emptiness can be proved; otherwise preserve it and report
   uncertainty. Preexisting paths retain strict integrity checks. Parent fsync,
   root/lock replacement and interruption/import uncertainty retain their gates.
   Cleanup cannot descend into or remove files or historical partials.
2. For a new consume after valid cancellation, validate stored chain, vault and
   authority first, then return `binding-conflict` without inspecting the live
   checkout. Fresh admissible consume must still revalidate checkout identity.
   Do not publish a marker, reopen a reservation or weaken corrupt-history refusal.
3. Counterproofs must cover new and preexisting roots, accepted and owner-stripping
   masks, replaced/unknown owner, nonempty paths, failed cleanup/fsync, KI/import,
   closed checkout removed/replaced, invalid manifest/authority/event and unchanged
   v2 reader guards. Inspect remains read-only; no new schema, CLI, A behavior or
   shared-publisher changes. Real umask tests run only in disposable children.

Current local evidence: six regression methods produced 24 failing assertions
before implementation. First focused run passed 115 tests; self-review then added
a failing two-case owner-replacement counterproof. Final focused run passed 116
tests (18.269 s, exit0). The final recheck validates the parent and removed path
after fsync; empty-directory inspection reads at most one entry. Production delta
is +29/-8 = +21 lines; cumulative B2 +472, below checkpoint500. Integrated and
document-check outcomes are tracked by the master checkpoint and private ledger.
Seven methods added; existing tests unchanged except a child-process helper guard
against chmod/umask changes. This is author verification, not independent review.

The design-acceptance gate is resolved. Permanent lifecycle still requires its
own architectural spec/plan. A new exact-byte independent review requires a new
grant; old grants cannot authorize it. No permanent lifecycle or automatic
recovery is included merely because this continuation was authorized.

## Ponytail v5.3.2 source assessment — 2026-10-16

Decision: adopt focused counterexamples and metadata contracts in existing
C/D/P4–P6 work; do not transplant the importer, CSV ledger or board. Importing
history is not prospective capture, restore, independent acceptance or causal ROI.
The inspected release remains Claude-specific telemetry despite portable rules.

### Source identity and verification boundary

Public checkout: [v5.3.2, 16352ac229eb08a9598dcae48fe9f2b342567d86](https://github.com/DietrichGebert/ponytail/tree/16352ac229eb08a9598dcae48fe9f2b342567d86).
Baseline [v5.3.1, 6f1c2bfff0c837d268929a7c4e490918eb4fab29](https://github.com/DietrichGebert/ponytail/tree/6f1c2bfff0c837d268929a7c4e490918eb4fab29);
[PR #1152 commit ca88b4f377fd94f780ac9035808dc4dc54e7a9cf](https://github.com/DietrichGebert/ponytail/commit/ca88b4f377fd94f780ac9035808dc4dc54e7a9cf).
Delta: 24 files, +473/-22. Lightweight tags resolve to commits; this is not
signature, published-package or remote-CI verification. The session's installed
skill is 5.2.0, not an installation of the inspected 5.3.2 code.

The delegated reviewer executed the upstream import test and 25 synthetic checks
on Node 26.7.0. The coordinator independently confirmed source and six groups of
pure counterexamples, without discovery, filesystem fixtures or environment
overrides: unknown-cost projection, partial/final ordering, mixed-model labeling,
31-minute duration, duplicate/colliding identities, and unanswered/zero-cost cases.
Those checks assert the defects below, not product correctness. No personal
session, native host, browser rendering, physical crash or real race was tested.
The TSX host suite and Node 22/Windows matrix were not executed. Pricing constants
were inspected as source claims, not independently verified current prices.

### Findings and exact sources

| Finding | Pinned source | Consequence for 007 |
|---|---|---|
| Unknown model/fast usage returns null; CSV is empty; board converts it to 0. Explicit observed zero can conversely become null. | [import:44–55,152–184](https://github.com/DietrichGebert/ponytail/blob/16352ac229eb08a9598dcae48fe9f2b342567d86/hooks/ponytail-band-import.js#L44-L184), [board:65–82](https://github.com/DietrichGebert/ponytail/blob/16352ac229eb08a9598dcae48fe9f2b342567d86/hooks/band/board.ts#L65-L82) | Presence and precision must survive parsing, persistence, projection, UI and totals; missing is not zero. |
| Import computes estimates; board footer says “Nothing here is estimated.” `max(own, estimate)` mixes potentially different scopes. | [import:152–160](https://github.com/DietrichGebert/ponytail/blob/16352ac229eb08a9598dcae48fe9f2b342567d86/hooks/ponytail-band-import.js#L152-L160), [board:555](https://github.com/DietrichGebert/ponytail/blob/16352ac229eb08a9598dcae48fe9f2b342567d86/hooks/band/board.ts#L555) | Preserve source, basis, pricing epoch/version and coverage; known subtotal cannot become a complete economic denominator. |
| Parent record majority before dedupe supplies one model label; children contribute usage but not that label. First message ID wins globally. | [import:105–175](https://github.com/DietrichGebert/ponytail/blob/16352ac229eb08a9598dcae48fe9f2b342567d86/hooks/ponytail-band-import.js#L105-L175) | Attribute at qualified request/attempt scope with producer namespace; no first/last/majority rule in the core. |
| No-human/no-reply sessions disappear; >30-minute intervals count as no agent time. | [import:105–150](https://github.com/DietrichGebert/ponytail/blob/16352ac229eb08a9598dcae48fe9f2b342567d86/hooks/ponytail-band-import.js#L105-L150) | Include failed/headless/reviewer/coordination attempts in coverage; distinguish wall time, host duration and heuristic activity. |
| Eight-character session prefix collides; duplicates in one batch survive; reimport skips corrections. | [import:181–195](https://github.com/DietrichGebert/ponytail/blob/16352ac229eb08a9598dcae48fe9f2b342567d86/hooks/ponytail-band-import.js#L181-L195) | Complete identity, explicit idempotency/conflict and revision semantics; history cannot be repaired into prospective evidence. |
| Global project scan, prompt/title retention, symlinks followed, silent parse/child failures and unbounded retained projections. | [import:68–100](https://github.com/DietrichGebert/ponytail/blob/16352ac229eb08a9598dcae48fe9f2b342567d86/hooks/ponytail-band-import.js#L68-L100), [216–265](https://github.com/DietrichGebert/ponytail/blob/16352ac229eb08a9598dcae48fe9f2b342567d86/hooks/ponytail-band-import.js#L216-L265) | Explicit enrollment and metadata-only selection, resource bounds before work, safe no-op and durable sanitized gaps. |
| CSV read-modify-write has no atomic publication or coordination; injected partial write truncated synthetic ledger. | [import:251–265](https://github.com/DietrichGebert/ponytail/blob/16352ac229eb08a9598dcae48fe9f2b342567d86/hooks/ponytail-band-import.js#L251-L265) | Reuse journal/vault; do not create a second mutable accounting authority. Lost updates are an inferred race risk, not a reproduced real race. |

Concrete synthetic observations: updated same-ID usage yields 11 or 110 tokens
depending on order; repeated parent records label 1,221 mixed tokens as Haiku;
same ID in parent/child loses the child; two distinct sessions sharing a prefix
collide. A hypothetical inclusive parent plus exclusive child double-counts
without a scope contract; this does not assert that the real host uses that
semantics. Nested cache-only usage can be priced but absent from token totals.
Numerical strings, booleans and negatives are not rejected at the importer boundary.

Positive, bounded properties remain: imported tests show unavailable instead of
passed; board JSON escapes script delimiters and UI uses textContent; the board
is a local self-contained HTML file. Those do not anonymize embedded rows or
certify acceptance. The live path has an optional webhook, and hiding the band
does not disable collection. No webhook was exercised in this review.

### Reuse and prioritized acceptance additions

These are pending obligations, not newly implemented tests or another roadmap:

1. **D/P4/P6, low effort / critical impact:** null versus zero, missing versus
   malformed, sub-cent precision, partial coverage and known subtotal through
   JSON/CSV-equivalent projections, UI and economic aggregates. Distinct estimated,
   provider-reported, billed and subscription-allocated bases; incomplete final
   ratios remain N/A. Display method/source per field, not just a disclaimer.
2. **D, medium / critical:** identical and conflicting duplicates, partial→final,
   reordering, epochs/resets, resumed sessions, producer/parent/child namespace,
   inclusive/exclusive usage and mixed models. Typed finite counters preserve
   presence; adapter version proves cache/reasoning semantics. Separate requested
   route from reported/served identity and unavailable effort.
3. **D/P4, medium / critical:** failures without final replies, retries, reviewers,
   coordination and missing children remain in coverage. Known spend survives
   refusal of a formal terminal receipt; an accepted-looking receipt is not the
   fallback for incomplete telemetry. Pricing epochs and tool charges are explicit.
4. **C, low/medium / high:** no-op outside exact enrollment, coexistence, bounded
   reads, symlink rejection, failure-before/after-publication and sanitized gap
   visibility without disrupting the primary work. No global transcript importer.
5. **Existing P4–P6 integration, low/medium / high:** mixed-model composition only
   where attribution is qualified; independent test status distinct from absent
   or not-executed; wall/host/heuristic durations separate. Use current dashboard,
   not a parallel board or a second ledger.

The candidate already has useful bounded `cli_telemetry.py` validation, optional
versioned pricing, `local_activity.py` coverage, journal/vault and accounting.
Reuse does not certify these as D-complete. Source inspection found Claude
`parse_claude_session` summing assistant records without message-ID dedupe,
retaining the last model for a whole session, and `safe_number` mapping invalid or
absent counters to zero. Aggregate-only cache writes also need a contract test.
These are concrete regression targets for D; no product fix or real data scan
was performed during research. Do not replace “last” with Ponytail's “majority”.

Historical backfill stays deferred as optional activity-only functionality, not
the critical path. No CSV migration, new board, transcript watcher, host settings
or hook installation follows from this assessment. Source is MIT; substantial
literal reuse requires notices and provenance. Prefer independently authored
contracts/tests on existing components, without vendoring code/assets/prices.
