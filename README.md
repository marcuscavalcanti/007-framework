# 007 Framework

**Evidence-bounded orchestration for reliable agentic coding.**

007 Framework is a small, provider-neutral skill that tells a coding agent how
to choose the cheapest executor likely to succeed, make the smallest safe
change, prove the outcome, and report uncertainty without inventing telemetry.

It is designed for the failure that matters most in AI-assisted development:
code that looks finished but must be rewritten, repaired, or explained again.

> **Status:** v1.1.0 is ready to test. A frozen mechanism test observed an
> OLD 0/3 vs NEW 3/3 contrast on one decision; the complete framework is not
> claimed to be universally superior or production-proven. See
> [Evidence](docs/evidence.md).

## What it gives you

- risk-based routing instead of “largest model by default”;
- reuse-first, minimal-diff implementation discipline;
- explicit proof levels and fail-closed quality gates;
- a compact outcome receipt with provider-neutral route telemetry and mandatory
  cost accounting;
- Git-based corrective touch-rate and receipt reporting;
- a polished localhost dashboard that reconciles all registered projects;
- an OLD×NEW replay runner for causal tests on real historical tasks.

No database, API key, package manager, or model-runtime dependency is added.
The included tools use Python's standard library. If Headroom is installed,
the dashboard reuses its LiteLLM pricing engine for local cost estimates.

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

## Use

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

Start the all-project control room:

```bash
007 dashboard
```

The loopback dashboard opens at `http://127.0.0.1:7007`, discovers all projects
registered by `007 init`, updates every two seconds, and keeps aggregate totals
mathematically reconcilable with the project views. It has no login because it
binds locally; do not expose it on a public interface.

The activity lane reads only sanitized session metadata and token counters from
local Codex and Claude logs. It maps Git worktrees back to their registered
project and shows sessions, active state, served route, 24-hour token deltas,
and Headroom/LiteLLM-equivalent USD. Partial pricing is shown as a lower bound;
unknown models are `N/D`, never free. This lane does not infer acceptance,
first-pass success, or reliability from a completed session.

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
