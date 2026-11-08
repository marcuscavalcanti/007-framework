# 007 Framework

**Evidence-bounded orchestration for reliable agentic coding.**

007 Framework is a provider-neutral toolkit for agentic coding, not an agent. It
drives the agent CLIs you already use (Codex, Claude Code) and adds three things:

- **`007 lab`** replays your own commits at two reasoning efforts, headless, and
  tells you, against a margin you declare, whether the lower effort pays in your
  repository (beta).
- **A skill** (`SKILL.md`) gives your agents the doctrine: choose the cheapest
  executor likely to succeed, make the smallest safe change, prove the outcome,
  and report uncertainty without inventing telemetry.
- **`007 run`, `record`, `route` and `dashboard`** observe real tasks, require a
  terminal receipt, route to the cheapest measured executor, and report locally.

It is designed for the failure that matters most in AI-assisted development:
code that looks finished but must be rewritten, repaired, or explained again.

## Current thesis: minimum sufficient effort (November 2026)

**Thesis: for the model you chose, `007 lab` shows in your own repository whether a lower reasoning effort pays.** It measures
the agent time and tokens saved, and tests, against a margin you declare before spending, whether the lower effort loses more
of the behaviour your commits' own tests check, for tasks specified the way your commits are (the commit message plus the
names its tests pin). One verdict per executor, repository and specification form; durability is not part of the claim until
it is measured. `007 lab` is beta: two public pre-registered runs, Go only, no `PROVEN` yet. The earlier wording, "the same durable change", is what a 3-point margin tests, and that stays open:

- **Declare the margin by the decision you face.** The loss that would cancel the saving (about 10 points of acceptance at a 30%
  saving) is cheap to test for Codex: roughly 20 commits that reach new behaviour at 2 attempts per arm. Claude's commits
  differed about five times more on go-json, so the same test needs about 40. "Effectively the same" at 5 points takes about 40
  such commits at 8 attempts per arm. 3 points takes several repositories. Rough sizes at go-json's noise;
  [docs/lab.md](docs/lab.md#choosing-the-margin) has the rule. A margin is fixed before any attempt, never after.

- **Measured in your repository.** `007 lab` replays your own commits at two efforts. Agent time and tokens settle within a few
  dozen commits. Public go-json replay, Codex `medium` vs `high`, 8 attempts per arm on 41 commits: agent time −30% median per
  attempt (task-bootstrap 95% CI −33% to −26%), cost −31.5% median; full acceptance 55.2% vs 57.4%. In the first replay (about
  two attempts per arm), tokens fell 26% to 34% under any weighting of input, cached input and output.
- **Guarded in your repository.** `report` returns `KILL` when the whole 95% interval of the paired difference falls below minus
  the declared margin. At the default 3 points, with about 40 commits that reach new behaviour and go-json's noise, a loss spread across commits is caught four times
  in five from about 10–12 points, roughly where the lower effort stops paying (on go-json a 10.5-point drop in acceptance
  erases the 31% cost saving per accepted change). A loss concentrated in a few commits must be larger.
- **Bounded, not proven: the same change within 3 points.** With the attempts each run had (about two per arm for Codex, three
  for Claude), excluding a loss above 3 points takes roughly 190–360 commits that reach new behaviour for Codex (go-json, after a
  grading fix) and about 700 for Claude (estimated from 17 tasks, so anywhere from 400 to 1,700). go-json-experiment/json gave 41
  such commits out of 145 candidates. At 8 fresh attempts per arm (pre-registered) Codex `medium` vs `high` came out −0.9 pp,
  95% t interval −3.4 to +1.6: losses above about 3.4 points are excluded, 3 points are not
  ([result](evidence/go-json-topup-20261106/RESULT-TOPUP.md)). That run declared 3 points; it is not re-read at any other
  margin. When a loss comes as rare attempts that
  fail outright, the t interval calls a 3-point loss `PROVEN` up to 5.6% of the time instead of 2.5%, so `report` takes
  `PROVEN`'s critical value from that loss simulated on the run's own attempts. `007 lab feasibility` computes the task count
  for your history before you spend.
- **A 3-point bound probably needs more commits than one repository like go-json has.** The pre-registered test of "one
  repository may be enough" ([pre-registration](evidence/go-json-topup-20261106/PREREG-TOPUP.md)) came out not proven, and the
  spread between commits is about at or above what 41 of them can absorb (τ² 0.003–0.005 against a 0.0047 budget, bootstrap
  upper bounds 0.007–0.009), so that claim is withdrawn. Planning estimates at go-json's noise, not limits: at 8 attempts per arm
  a 3-point verdict takes about 55–70 reaching commits if the arms are equal and 110–145 if the true difference is −0.9 points,
  that is, several repositories, one verdict per executor.
- **Each executor gets its own verdict.** Claude Opus 5.5 `medium` vs `xhigh`, pre-registered on the same 41 go-json commits at
  a 10-point margin, 2 attempts per arm: −5.5 pp (95% t interval −11.8 to +0.7), not proven, with 67% less agent time and a 75%
  lower median cost ([result](evidence/go-json-claude-20261107/RESULT-CLAUDE.md)). Acceptance on the 36 commits any attempt
  solved fell 11.1 points (−21.1 to −1.1, secondary). On one owner's Node repository: −6.9 pp (CI −21.8 to +8.0) over 17
  commits. For Claude, `medium` is cheaper and faster, and not shown to keep the behaviour.
- **Not measured:** durability, subscription quota per arm, served effort.

Anthropic documents `medium` as the default effort of Claude Opus 5.5 and recommends running an effort sweep on your own evals;
`007 lab` runs that sweep from your Git history.

Where each claim stands (pre-registered replays; hidden tests are each commit's own tests; one owner's repositories plus the public go-json-experiment/json):

| Claim | Status | Evidence |
|---|---|---|
| Less reasoning | **manipulation check** | it shows the effort setting changed the work; it is not a benefit by itself. Median reasoning tokens, lower effort vs reference: Codex −72%, Claude Opus 5.5 −84%, Claude Sonnet 5.5 138 vs 1,780; public go-json replay, Codex `medium` vs `high` −67%; public go-json, Claude Opus 5.5 `medium` vs `xhigh` −89% |
| Less waiting | **supported** | agent time per attempt: Codex `medium` vs `high` −47.5% (95% CI 43–51%); Claude Opus 5.5 `medium` vs `xhigh` −60.0% (CI 57–63%), faster on 23 of 24 tasks; Claude Sonnet −50.6% per accepted change (holdout); public go-json replay, Codex `medium` vs `high` −32% median per attempt, same acceptance (37.9% vs 36.5%); public go-json, Claude Opus 5.5 `medium` vs `xhigh` −67% median per attempt (CI 60–73%), acceptance 67.9% vs 76.8% |
| Less quota | **proxy only** | estimated cost per attempt −40% (Codex), −67% (Opus), −31% median (Codex, public go-json replay), −75% median (Claude Opus 5.5, public go-json). On go-json any non-negative weighting of input, cached input and output tokens gives −26% to −34%, so the saving does not hang on how a plan counts cache; subscription quota itself is not measured per arm |
| Same change | **not proven** | behaviour the commit introduced (hidden tests red at base), paired by task. Public pre-registered replay (go-json-experiment/json, 62 Go commits, Codex `medium` vs `high`): +1.3 pp over the 41 commits where any attempt reached new behaviour (95% t interval −4.7 to +7.2; paired-replicate reading +0.05, −7.3 to +7.4). Its checks: an A/A not killed and a 30-point injected loss killed (gross errors only), 79% of planted partial changes rejected; at this size a plain t interval would call a true 3-point loss `PROVEN` 3.7–5.3% of the time. Re-graded without a model after fixing a grading defect (the agent's own Go tests could break a package): +1.5 pp (−3.2 to +6.2; paired +0.3, −6.1 to +6.7), still not proven. Pre-registered top-up, 8 fresh attempts per arm on the same 41 commits: −0.9 pp (−3.4 to +1.6), not proven; full acceptance on the 25 commits any attempt solved −4.4 pp (−10.4 to +1.7). Pre-registered Claude Opus 5.5 `medium` vs `xhigh` on the same 41 commits, margin 10 points, 2 attempts per arm: −5.5 pp (−11.8 to +0.7), not proven; acceptance on the 36 solved commits −11.1 pp (−21.1 to −1.1). One owner's Node repository: Claude Opus 5.5 −6.9 pp over 17 commits (CI −21.8 to +8.0, pre-registered metric, corrected in an erratum: the first scale also counted old behaviour, 83% of hidden tests); Codex +9.4 pp over 16 commits (CI +0.2 to +18.7, metric chosen after the data), a gain the go-json replay did not reproduce. Neither executor excludes a loss above 3 points; Claude does not exclude 10 |
| Durable | **not measured yet** | observational only: 30-day line survival of 332 Codex commits, 85% at `high` vs 89% at `xhigh` (−4.8 pp, CI −12.7 to +3.7, confounded by task). A randomized per-run instrument exists (`scripts/line_trial.py`); no trial has run |

The earlier holdout (one private Go repository, 13 tasks with independently validated requirements) found Codex `medium` 39/39
vs `xhigh` 39/39 with 51.8% less agent time per accepted change (CI 44.3–57.9%), and Claude Sonnet `medium` 37/39 vs 39/39. At that size a zero-margin count rule rejects two equal arms about
four times in ten, so the Sonnet result means *no power*, not *worse*. An exploratory run on 8 harder tasks (Codex only) found
every effort solved every task, so it says nothing about when to escalate.

What the instrument learned, and now does by default:

- **Say before spending whether a run can answer.** `007 lab feasibility` turns a pilot's noise into the number of tasks a
  verdict needs. On the Opus data, read on the corrected scale, a 3-point margin needs about 700 tasks that reach new
  behaviour; the run had 17.
- **Read "same change" where both arms can be compared.** Reports use reachable behaviours (hidden tests red at base that some
  attempt passes), paired by task, with a symmetric interval rule — a point estimate never kills — and a pseudo A/A per arm.
  `PROVEN` must beat a critical value simulated from the run's own attempts with a loss of the declared margin as whole failed
  attempts, so in go-json simulations such a loss comes out `PROVEN` about 2.5% of the time (reach set taken as given;
  confirmatory runs freeze it beforehand).
- **Filter weak specifications.** Commit messages make thin requirements: few tasks reach full acceptance. `007 lab sufficiency`
  drops tasks whose prompt alone cannot reach their tests.

Not proven: durability, a 3-point bound for any executor, other repositories or languages, any population claim. Served
effort is not reported by either CLI (a reasoning-token manipulation check is the only evidence the effort changed), and Codex reports the served model only when it reroutes a request, which fails the run. Costs are API-equivalent estimates, not invoices.
Raw records of the replays on private repositories stay private because they contain business code; the summaries above are
their full claim.

Tools for this thesis: `scripts/effort_lab.py` (`007 lab`: mine, sensitivity, run, chain, report, feasibility, sufficiency),
`scripts/line_trial.py` (per-run effort assignment and content-based line survival for a launcher),
`scripts/choice_observatory.py` (session → commit attribution, with the model and effort in force at each commit, and line
survival, with an explicit evidence level) and
`scripts/effort_trial.py` (opt-in randomized default effort; **off by default**).

> **1.6.0** (published 2026-11-08): adds `007 lab` and restates the thesis as a decision tested
> against a margin declared before spending. Public pre-registered evidence so far:
> Codex on go-json not proven at 3 points, Claude on go-json not proven at 10
> points. See its [qualification record](evidence/v1.6.0/release-evidence.md).

> **1.5.2** (published 2026-10-06): fixes the inherited 320px page overflow and adds
> a browser-assisted visibility selfcheck; see its
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
