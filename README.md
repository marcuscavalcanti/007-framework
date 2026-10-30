# 007 Framework

**Evidence-bounded orchestration for reliable agentic coding.**

007 Framework is a small, provider-neutral skill that tells a coding agent how
to choose the cheapest executor likely to succeed, make the smallest safe
change, prove the outcome, and report uncertainty without inventing telemetry.

It is designed for the failure that matters most in AI-assisted development:
code that looks finished but must be rewritten, repaired, or explained again.

## Current thesis: minimum sufficient effort (October 2026)

**The same durable change, with less reasoning, less waiting and less quota — proven in your repository, not in a benchmark.**
For the model you chose, 007 measures which reasoning effort is enough for the work in *your* repository, and says so only at the
level of evidence it actually has.

What the experiments so far support (pre-registered rules, zero non-inferiority margin on accepted changes):

- **Holdout, one private Go repository, 13 real tasks** whose requirements were written before implementation and whose hidden
  tests were validated by an implementer who only read the requirement; 3 replicates per effort.
  - **Codex (`gpt-6.1-sol`): `medium` matched `xhigh`** — 39/39 vs 39/39 accepted, with **51.8% less agent time per accepted change**
    (95% CI 44.3–57.9%) and ~43% less rate-card cost. `low` missed 2/39 (owner-invariant regressions) and fails the zero margin.
  - **Claude (`sonnet-5.5`): `medium` did not pass** — 37/39 vs 39/39 (−50.6% time); `low` 36/39. Fisher p≈0.49: no power to tell
    them apart; the verdict follows the pre-registered rule.
- **8 harder tasks, Codex only (exploratory, after two post-start amendments):** `low` and `medium` matched `xhigh` (24/24 vs 23/24;
  the single `xhigh` miss is an infrastructure-invalidated attempt that passed the oracle) with 68% and 52% less time. Every effort
  solved every task, so this says nothing about *when to escalate*. The Claude run stopped at the pre-registered USD cap (50/72,
  no verdict).
- A commit-replay corpus built from 007's own history proved inadequate to measure quality and was closed.

Not proven: durability over time, other repositories or languages, any population claim. Served effort is not reported by either
CLI (a reasoning-token manipulation check is the only evidence the effort changed). Costs are API-equivalent estimates, not
invoices. Raw experiment records stay private because they contain business code; the summaries above are their full claim.

Tools for this thesis: `scripts/choice_observatory.py` (session → commit attribution and line survival, with an explicit evidence
level), `scripts/effort_trial.py` (opt-in randomized default effort for a durability field trial; **off by default**) and
`scripts/effort_trial_analysis.py`. A blinded field trial of 30-day line survival by effort is in progress.

> **1.5.2 local candidate:** fixes the inherited 320px page overflow and adds a
> browser-assisted visibility selfcheck. The source delta has exact-commit CI
> and a context-only independent review; later documentation is qualified
> separately. Not a published release; see its
> [bounded proof and remaining gates](evidence/v1.5.2/release-evidence.md).

> **1.5.1 evidence:** the qualified runtime and dashboard passed Linux CI on
> Python 3.11/3.12/3.13: 155 tests per job, no test skips. The
> [qualification record](evidence/v1.5.1/release-evidence.md) binds those results
> to exact commits. Distribution verification is separate: use the
> [tag/Release reference](https://github.com/marcuscavalcanti/007-framework/releases/tag/v1.5.1)
> and manifest contract; this source record does not assert publication.
> The historical v1.4 real-task result remains narrow: both efforts passed 3/3,
> with `medium` using 42.6% less estimated USD and 53.9% less wall time.
> Neither result proves task-class superiority, complete code-review replacement
> or D7/D30 durability. See [Evidence](docs/evidence.md) and the
> [1.5.1 qualification and publication gates](evidence/v1.5.1/release-evidence.md).

**1.5.1** makes accepted delivery, repair pressure, terminal
cost and missing evidence the dashboard's first view. A new deterministic
comparison prevented false approvals in two sanitized defect-derived cases,
without rejecting correct controls: 36 cells, zero invalid. This is a narrow
admission-mechanism result, not model quality or measured financial ROI. See the
[evidence and publication verification](evidence/v1.5.1/release-evidence.md).

## What it gives you

- risk-based routing instead of “largest model by default”;
- reuse-first, minimal-diff implementation discipline;
- explicit proof levels and fail-closed quality gates;
- a compact outcome receipt with provider-neutral route telemetry and mandatory
  cost accounting;
- Git-based corrective touch-rate and receipt reporting;
- a polished localhost dashboard that reconciles all registered projects;
- an experimental route recommendation from mature receipts, never automatic serving;
- an OLD×NEW replay runner for causal tests on real historical tasks.

No database, API key, package manager, or model-runtime dependency is added.
The included tools require Python 3.11+ and use only its standard library. Outcome cost comes from the
terminal receipt. If Headroom is installed, the dashboard may additionally use
its LiteLLM pricing engine for a non-authoritative local estimate.

## Install

Clone the repository into the skills directory used by your coding-agent host:

```bash
git clone https://github.com/marcuscavalcanti/007-framework.git
mkdir -p ~/.codex/skills
ln -s "$PWD/007-framework" ~/.codex/skills/007-framework
mkdir -p ~/.local/bin
ln -s "$PWD/007-framework/bin/007" ~/.local/bin/007
```

For another skills-compatible host, use its documented skills directory. The
framework itself does not call a model provider; your host remains responsible
for authentication, model selection, sandboxing, and permissions.

Validate the checkout:

```bash
cd 007-framework
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
```

The same suite runs from an extracted source archive without Git history.
Historical checks use the hash-bound, MIT-licensed proof inputs documented in
[tests/fixtures/README.md](tests/fixtures/README.md); Git is still needed by tests
that create disposable repositories.

## Use

For the offline synthetic controller proof, run:

```bash
python3 -m unittest discover -s tests -p test_semantic_replay.py -v
```

It restores a retained candidate, accepts the correct fixture and rejects a
wrong one, repeats admission/budget/accounting/seeded order three times, and
rejects byte corruption. USD values are literal test data, not provider charges
or measured savings. Each invocation freezes a new local fixture; its identity
hashes may differ from another invocation or runtime. Within that fixture all
semantic values and identities must remain identical across the three repeats.

For the same public corpus bytes across independent processes and supported
Python versions, run:

```bash
python3 -m unittest discover -s tests -p test_public_replay_corpus.py -v
```

This licensed static fixture pins the full read-only admission, restored file
identities/modes, portable oracle controls, seeded order, budget and accounting
digest. It does not remove errors or identities to obtain equality. The native
`recheck` path separately retains its exact captured-runtime requirement; the
portable fixture controls do not waive that gate or qualify native generation.
See [corpus contents and limits](tests/fixtures/README.md).

Register each Git project once. Registration is idempotent, adds `.007/` only to
the repository's local Git exclude file, and updates the user-level project
registry automatically:

```bash
cd /path/to/project
007 init
```

Remove a stale or retired path without deleting any project files:

```bash
007 unregister --project /old/path/to/project
```

Ask your agent to use `007-framework` for a coding task. A normal run follows:

```text
task start → scope → route → minimal implementation → repository harness → outcome receipt
```

Example request:

```text
Use 007-framework to fix the pagination regression. Preserve unrelated work,
reuse the existing query path, and stop after integrated proof.
```

Expected final output:

```text
status: accepted
proof: integrated -> integrated; python3 -m unittest (42 passed)
delta: 2 files, +18/-4, dependencies=0
first_pass: yes; repair_rounds=0
rework: corrective_lines=pending; escape_7d=pending
telemetry: model=served-model; effort=medium; tokens=unmeasured; wall_s=31
cost: usd=0.42; source=provider-reported; status=final
uncertainty: runtime not exercised
```

For initialized projects, the operating contract requires the agent host to
observe the task before implementation and persist every terminal task through
the fail-closed receipt command:

```bash
007 begin --repo . --task-id pagination-regression
```

The returned task ID must match the terminal receipt. Start from
[`examples/task.receipt.example.json`](examples/task.receipt.example.json):

```bash
007 record --repo . --file task.receipt.json
```

The command rejects missing, non-finite, or explicitly unaccounted cost,
malformed task IDs, and duplicate receipts.
Provider/model/effort are open values, with requested and actually served routes
kept separately. Cost may be provider-reported, estimated by an external rate
card, allocated from a subscription, or derived from local compute; its source
and provisional/final state must be explicit.

Configure the CLIs you actually own once, using argv arrays rather than shell
strings:

```bash
mkdir -p ~/.007-framework
cp examples/routes.example.json ~/.007-framework/routes.json
007 route --task-class implement --format json
```

The experimental selector filters unavailable commands and routes that miss the reliability
gates, then minimizes **all-attempt cost per reliable outcome** with latency as
the tie-breaker. Until a route has five mature receipts, it uses only a
configured fallback. The decision is made once per task; 007 does not run a
gateway, silently change providers, or switch models mid-attempt.

This command is a repository-local observational recommendation, not a certified policy engine.
Its deterministic mechanism test does not prove model quality, cross-project
transfer, or causal ROI. Keep human control of the chosen executor.

To make the lifecycle automatic for any agent CLI, wrap it with `007 run`:

```bash
007 run --repo . --task-id pagination-regression \
  --receipt task.receipt.json -- your-agent-command
```

The wrapped command receives `FRAMEWORK_007_TASK_ID`,
`FRAMEWORK_007_RECEIPT_PATH`, and `FRAMEWORK_007_REPO`. Its provider adapter
writes the normalized receipt to that path. A failed command, missing receipt,
or mismatched task ID stays visibly open; the core never infers success or cost
from an exit code or transcript.

Bind explicit task authority when the work has meaningful boundaries:

```bash
007 run --repo . --task-id pagination-regression \
  --authority-file examples/authority.example.json \
  --action test --receipt task.receipt.json -- your-agent-command
```

An allowed action runs once; a denied or unclassified action is blocked before
the subprocess starts. `007 run` writes a no-replace controller event and marks
the receipt as `controlled`. Manual `007 begin` + `007 record` remains valid but
is marked `declared`, and caller-supplied controlled provenance is rejected.
Every receipt still requires its matching task start.

Controller events and task starts are unauthenticated local records. This
protects the supported lifecycle against agent omission; it does not protect
against tampering by a process using the same filesystem account.
This does not replace technical isolation for secrets, network, production, or
destructive actions.

Task starts are intentionally no-replace. If a command fails before producing a
valid terminal receipt, keep that start as evidence and retry with a new
`task-id`; do not delete or reuse the interrupted identity.

Start the all-project control room:

```bash
007 dashboard
```

The loopback dashboard opens at `http://127.0.0.1:7007`, discovers all projects
registered by `007 init`, updates every two seconds, and keeps aggregate totals
mathematically reconcilable with the project views. It has no login because it
binds locally; do not expose it on a public interface.

The first viewport shows accepted changes (controller-observed versus declared),
measured repair rounds, accounted terminal USD and unresolved starts. The
operational verdict remains **on target**, **off target**, or **not yet
measurable**; it is not a causal verdict. Independent gates show value, target, evidence
denominator, and next action. A 30-day trend and controlled/declared/unobserved
provenance panel explain the verdict without hiding missing data in a score.
Preventive controller blocks remain visible in the authority panel but are not
classified as failed engineering outcomes in the 30-day quality trend or as
model-telemetry opportunities when no model was invoked.

Declared D7 follow-up is not independently verified survival. Cost exposes its
source and provisional/final state; open attempts have no terminal cost yet.
The historical OLD×NEW panel compares `gpt-5.6-sol@xhigh` with `medium` on one
task, not “without 007” versus “with 007”, and stays global when a project is
selected. Unknown identity, cost and durability stay unknown.

The activity lane reads only sanitized session metadata and token counters from
local Codex, Claude, Kimi Code, and Gemini CLI logs. It maps Git worktrees back
to their registered project and shows sessions, active state, served route, and
24-hour token deltas. Provider-reported terminal USD is preserved when present.
Headroom/LiteLLM, RTK, or another rate card may supply a separate diagnostic
estimate, but never closes the cost gate. Unknown cost is `N/A`, never free.
This lane does not infer acceptance, first-pass success, or reliability from a
completed session.

The ROI cards use every measured attempt, including failures, in the numerator
and only reliable first-pass outcomes in the denominator. They remain `N/A`
unless terminal cost and wall-time coverage are complete. A separate frozen
OLD×NEW card reports release-level causal evidence, so live observational data
is never mislabeled as causation.

Observation coverage is the percentage of starts created by `007 begin` with a
matching terminal receipt. Cost coverage is the percentage of terminal receipts
with valid accounting. Work that bypasses `007 begin` remains outside the
dependency-free observer and appears as legacy/unstarted data rather than being
silently counted as complete.

## Measure

Summarize machine-readable receipts:

```bash
python3 scripts/harness_report.py --receipt-dir .007/receipts --format json
```

Receipt filenames end in `.receipt.json`; unrelated JSON files in the same tree
are ignored. A malformed matching receipt is reported alongside valid summaries
and makes the command exit non-zero.

Estimate whether attributable agent code was later rewritten:

```bash
python3 scripts/touch_rate.py --repo . --days 30
```

List or execute a frozen replay set:

```bash
python3 scripts/replay_eval.py --set replay-set.json list
python3 scripts/replay_eval.py --set replay-set.json run --replicates 3 --out replay-results
```

The replay runner accepts a JSON config containing repository paths, OLD/NEW
doctrine arms, an argv-style agent command, real tasks, and task-specific
acceptance commands. Historical solution similarity is reported only as a
diagnostic; it never decides correctness. Start from
[`examples/replay-set.example.json`](examples/replay-set.example.json). The
frozen prompt is also provided on stdin, which works with CLIs that accept `-`.
The replay set must contain a seed fixed before execution; `summary.json` records
that seed and the realized cell order.

## Architecture

The repository root is the installable skill:

```text
SKILL.md        operating contract
references/     detailed doctrine loaded on demand
scripts/        receipts, local activity/cost, touch-rate, and replay sensors
dashboard/      dependency-free localhost control room
bin/007         project registration, receipt, and dashboard CLI
tests/          deterministic package contract
docs/           product, architecture, evidence, and research history
evidence/       release-specific, sanitized proof
```

Read [Architecture](docs/architecture.md) for data flow and trust boundaries.

## Evidence and limits

The strongest V1 observed result is a narrow OLD×NEW decision test: OLD accepted
the intended behavior in 0/3 runs; NEW accepted it in 3/3 under frozen
conditions. A separate compatibility run passed 3/3 in both arms and showed a
smaller median patch for NEW, but it does not isolate causality.

This release does **not** claim provider-agnostic effectiveness, production
durability, or general productivity gains. Those require broader held-outs and
longitudinal receipts. Exact boundaries and hashes are in
[Evidence](docs/evidence.md).

## Documentation

- [Product](docs/product.md)
- [Architecture](docs/architecture.md)
- [Evidence](docs/evidence.md)
- [Research history](docs/research-history.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## License

[MIT](LICENSE) © 2026 Marcus Cavalcanti.
