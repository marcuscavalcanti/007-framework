# 007 Framework

**A measurement layer for routing decisions between coding-agent configurations.**

When you choose between models, efforts or agent CLIs for coding work, 007 measures what that choice does. It produces two
things:

- **Outcome receipts.** A local, schema-checked record of each task: what ran, whether its acceptance checks passed, what
  it cost and how long it took. Missing evidence stays visible as a gap, never a zero.
- **A pre-registered causal verdict with a declared error rate.** `007 lab` replays your repository's own commits under two
  configurations and tests a quality margin you fix before spending. Its decision rule is checked by a calibrated
  control: on the one study shape validated so far, a true loss of the margin read `PROVEN` in 1.25–2.27% of simulated
  replicates, compatible with the 2.5% it promises.

007 measures; something else routes. In standalone use, you or your agent host read the receipts and the verdict on one
machine. In gateway use, a gateway that assigns configurations to tasks feeds the same receipts to the same 007 code,
which labels and judges them; 007 never chooses a model or moves traffic. Standalone is the building block and the only
mode exercised so far.

What the evidence shows today, all on one public Go repository (go-json-experiment/json), one model per executor, efforts as
requested from the CLI:

- At 3- and 10-point margins the quality verdicts are **NOT-PROVEN**. One Claude study (Study F) reads **PAYS** at a 20-point
  margin, with whole-change acceptance 56/82 against 61/81.
- A paired study found no detectable effect of invoking the 007 skill on acceptance.
- Runs before 1.11.0, Study F included, were not blind: the agent could read its arm's label in its workspace path.
- **007's incremental value over a well-informed user of the same native CLI is not demonstrated.**

[Evidence and its limits](#evidence-and-current-thesis)

## Why, for whom, status

**Why.** Cheaper settings save money per attempt; the open question is whether they lose accepted work. Answering that
needs a margin fixed in advance, the same tasks on both arms, hidden tests the agent never sees, and a rule whose error rate
was measured rather than assumed. 007 packages that procedure, and records outcomes so the question can be asked again on
real work.

**For whom.** Developers and teams who already run Codex or Claude Code from a terminal, on Linux or macOS, and want local
receipts, cost accounting and a pre-registered test of a lower effort on their own history. Researchers who compare
configurations on Git history. 007 is not an agent, a sandbox, a model gateway or a hosted service.

**Status.**

| Part | Status |
|---|---|
| Receipts, `007 begin`/`record`/`run`, dashboard | Stable interface (see [versioning](#versioning-and-changelog)) |
| `007 lab` | Beta. Error control validated for one shape only (below); detection power not reached |
| Gateway mode | Not built or validated: 007 ships no gateway, no multi-user service and no authentication |
| `007 route` and the host skill | Experimental. No demonstrated benefit over the native CLI used directly |

The lab's decision rule as corrected in 1.11.0 passed a calibrated control (CALIBRATED-UNDERPOWERED) for one shape: go-json,
41 tasks, two attempts per arm, a 20-point margin, whole-attempt loss, floor 2.4768. There, a true loss of the margin read
`PROVEN` in 1.25–2.27% of replicates; under a clustered loss the rate (2.27%, upper bound 2.78%) is compatible with 2.5%, not
shown to be below it. A true loss of 10 points was detected 57% of the time, against the 80% a detection claim needs. Any
other shape needs its own floor and control. [Errata and controls](docs/evidence.md#errata-and-limits-published-for-1110)

## Install

Prerequisites: Python 3.11+, Git, and [pipx](https://pipx.pypa.io/) for the isolated install. CI qualifies Linux and macOS;
the laboratory and observatory use POSIX file locks.

Install the stable CLI from a published tag. The example uses v1.10.1, the latest release; the 1.11.0 commands below
(`viability`, `status`, `run --aa`) need a later tag or a source checkout. The release page includes the source archive,
SHA-256 checksums and build provenance details.
[007 Framework 1.10.1](https://github.com/marcuscavalcanti/007-framework/releases/tag/v1.10.1)

```bash
release_tag=v1.10.1
git clone --branch "$release_tag" --depth 1 https://github.com/marcuscavalcanti/007-framework.git
cd 007-framework
pipx install .
pipx ensurepath
```

Open a new shell after the PATH update, then run `007 --version` (expect `007 1.10.1`) and `007 --help`. From an existing
checkout, `pipx install .` installs that source version. Updating a checkout does not upgrade an installed CLI: reinstall
with `pipx install --force .` and check `007 --version`. Building the wheel uses setuptools. The installed runtime uses the
Python standard library and includes its scripts, dashboard assets and default public evidence. Version metadata comes from
`SKILL.md`.

Without pipx, link the checkout's CLI wrapper instead. Persist the PATH entry in your shell profile, and check what an
existing link points to before you replace it.

```bash
mkdir -p ~/.local/bin
ln -s "$PWD/bin/007" ~/.local/bin/007
export PATH="$HOME/.local/bin:$PATH"
```

### Host skill

The source root is the skill (`SKILL.md`). Link it into your host's skills directory, from the checkout:

```bash
# Codex
mkdir -p ~/.codex/skills
ln -s "$PWD" ~/.codex/skills/007-framework
# Claude Code (personal skills)
mkdir -p ~/.claude/skills
ln -s "$PWD" ~/.claude/skills/007-framework
```

For another host, use the directory that host documents for skills.

### Requirements by capability

| Capability | Requirements |
|---|---|
| Core CLI, receipts and dashboard | Python 3.11+ and Git |
| Compressed Codex logs, `*.jsonl.zst` | Python 3.14+ with `compression.zstd`, or the `zstd` executable on PATH |
| Agent execution | Your configured CLI, its authentication and the context you authorize |
| Replay acceptance | The toolchain and acceptance commands declared by the task |
| Wheel build and isolated install | Setuptools and pipx |
| Diagnostic pricing | Optional installed Headroom/LiteLLM integration |

A missing compressed-log decoder is reported as unavailable capture. The core exposes that coverage gap. The host controls
filesystem access, network access, authentication and executor isolation. [Privacy and security](#privacy-and-security)

### Integration coverage

| Integration | Supplied support |
|---|---|
| Codex and Claude Code | Native CLI stream adapters and local activity readers |
| Kimi Code and Gemini CLI | Local activity readers |
| Another CLI | Explicit argv configuration; your command writes the normalized receipt |
| Compatible coding-agent host | Install `SKILL.md` using the host's skills mechanism |

Provider-neutral interfaces allow additional executors. Measured effectiveness has the executor, repository and
specification scope stated in each result.

## First use

Paths under `examples/` and `scripts/` below are relative to the 007 checkout; `--repo` points at your project.

### Observe a project

```bash
007 init --repo /path/to/your/project
007 dashboard --host 127.0.0.1 --port 7007 --no-open
```

Then open `http://127.0.0.1:7007`. Registration creates local project records and enrolls the path. Task outcomes appear as
you record receipts (below). Once a project is registered, opening the dashboard reads local Codex, Claude Code, Kimi and
Gemini session logs to find its sessions, and may decode logs of other projects. It keeps selected metadata and token
counters, not message bodies. [Privacy](PRIVACY.md)

### Evaluate a lower effort

```bash
007 lab --help
```

The flow is `mine → sensitivity → viability → feasibility → run → status → report`. Only `run` calls a model.

- `mine` builds tasks from your commits, with hidden tests the agent never sees; `sensitivity` checks that those tests
  reject planted defects.
- `viability` (since 1.11.0) says at no model cost whether the repository can give a decisive verdict, and why not;
  `feasibility` estimates how many tasks a verdict needs. Both run before spending.
- `run` launches the configured agent commands within your spend limits. Add `--aa ARM` (since 1.11.0) to run one arm
  twice, so the verdict carries its own noise floor.
- `status` (since 1.11.0) shows the grader's health while a run is in flight, without revealing a verdict.
- `report` gives the verdict at the declared margin.
- `sufficiency` (drop tasks whose prompt alone cannot reach their tests) and `chain` (a next-change stage for durability)
  are optional steps.

Start from `examples/lab.example.json` and follow the [laboratory guide](docs/lab.md) for commands, oracle controls and
decision rules. Declare inputs, acceptance rules, a quality margin and spend limits before the first attempt. The budget
reserves an amount for in-flight attempts; an attempt above its reserve can exceed the total cap before the observed cost
triggers a stop. Costs retain their accounting source.

What to expect:

- At a 3-point margin expect NOT-PROVEN: a verdict needs hundreds of commits that reach new behaviour, more than most
  repositories have. A break-even margin needs about 20 such commits per executor at go-json's Codex noise, about 40 for
  Claude.
- A snapshot is not read isolation. If the host holds another copy of the mined repository (a plugin or module cache, a
  vendored checkout), deny the agent access to it or the cell is contaminated.
- Keep `--jobs` at its default; machine load changes grades.

### Record task outcomes

Register each Git project once with `007 init`. Registration is idempotent, adds `.007/` to the repository's local Git
exclude file and updates the local user registry. Remove a stale entry with `007 unregister --project /old/path`.

For a manual record, start the task before implementation, do the work, write its observed outcome to a receipt with the
same task ID, then record it:

```bash
007 begin --repo . --task-id pagination-regression
# ... implement, run the checks, write task.receipt.json from the example ...
007 record --repo . --file task.receipt.json
```

`007 record` validates identity, accounting, finite values and uniqueness. It rejects a receipt without a numeric
`cost_usd`, a cost source and a status. If the route cannot be priced, such as a flat subscription, set
`cost_unavailable_opt_in: true` in `.007/project.json` and record `cost_usd: null`, `cost_status: "unavailable"`, a
`custom:<name>` source and a reason. Never enter zero. [Receipt example](examples/task.receipt.example.json) ·
[Receipt schema](references/receipt-schema.md)

To let the controller observe the lifecycle, wrap the agent command instead, with a fresh task ID:

```bash
007 run --repo . --task-id pagination-regression-2 --receipt task.receipt.json -- your-agent-command
```

The command receives `FRAMEWORK_007_TASK_ID`, `FRAMEWORK_007_RECEIPT_PATH` and `FRAMEWORK_007_REPO`. 007 does not write the
receipt: the wrapped command, or the agent following the skill, must write one that matches the schema to
`$FRAMEWORK_007_RECEIPT_PATH`. With `--native-cli codex` or `--native-cli claude`, invoke `codex exec --json --ephemeral …`
or `claude --print --verbose --output-format stream-json --no-session-persistence …`; resumed sessions are refused. Add
`--acceptance-file acceptance.json` to have 007 run your checks itself: a failing check records `blocked` and exits 4. A
command that writes no receipt, or a mismatched one, leaves an unresolved start. A retry uses a new task ID and preserves
the prior attempt. `--capture-config FILE` opts into retaining the declared inputs before edits.

For explicit task authority, add `--authority-file` and `--action`. The controller records an allowed execution or blocks
the command before launch. Controlled and declared provenance remain separate. Local records can be modified by another
process with the same filesystem account. Technical containment belongs to the host.
[Authority example](examples/authority.example.json)

### Use the host skill

After installing the [host skill](#host-skill), ask your host to use `007-framework` for a task. Its order of priority is
correctness and no regression, low rework, the smallest sufficient diff, then cost and latency. It declares the task class,
proof level and diff budget before editing, keeps one writer, and leaves a failing-then-passing check for a bug fix. After a
second failure it escalates one tier in a fresh session and never makes a third equivalent attempt.

```text
Use 007-framework to fix the pagination regression. Preserve unrelated work,
reuse the existing query path, and stop after integrated proof.
```

The skill is doctrine, not a measured improvement: the paired study below found no detectable effect of invoking it.

## Routing recommendation (experimental)

Configure the CLIs you own to obtain a route recommendation:

```bash
mkdir -p ~/.007-framework
cp /path/to/007-framework/examples/routes.example.json ~/.007-framework/routes.json
007 route --repo /path/to/your/project --task-class implement --format json
```

The selector is experimental and observational. A route is measured-eligible only after five mature outcomes of its task
class (reliable first-pass rate at least 70%, escape rate at most 5%, mean repair rounds at most 0.5), with complete cost and
wall time, linked seven-day observations and all six declared cost components. Until then it returns your configured
fallback; with no available fallback, it blocks. Its inputs are unauthenticated local declarations, and its evidence scope is
the current repository; a selection is not evidence that the route is better. Executor selection and serving remain
explicit host actions. [Routing details](references/routing.md)

## Local observation and diagnostics

The dashboard discovers registered projects and serves a loopback interface, by default at `http://127.0.0.1:7007`. The
browser polls every two seconds. Background evidence has its own build timestamp, and failed refreshes expose stale evidence.

Activity collection decodes native log rows locally and retains selected session metadata and token counters. Those rows can
contain message payloads before field selection. The activity view shows session state and model/effort labels observed in
native metadata, with served-identity limits kept explicit. [Privacy](PRIVACY.md)

Codex and Claude Code logs are read whole, with bounded memory, from a per-log byte cursor; a changed plain log is resumed
only after its consumed prefix is verified, and a changed compressed archive is read again from the start. A session whose
token counters are incomplete or incoherent is marked partial and is not priced. Parent/child ownership preserves project
scope. Overlapping routes and unresolved historical observations retain uncertainty. Attribution remains observational.

The dashboard separates terminal accounting, diagnostic price estimates and laboratory spend. Open **Full evidence and
operations → Spend and cost → What each 007 experiment cost** to see the attempts and estimated spend for each experiment
configured in `observatory.lab_ledger`. Missing amounts and receipts are unpriced. Incomplete totals expose lower bounds.
Task coverage is the share of observed starts (`007 begin`) that have a matching terminal receipt; an open start stays in
the denominator, and work that never calls `begin` is outside this measure.

Operational panels expose accepted outcomes, repairs, costs, authority events and data quality. The causal verdict belongs
to its frozen experiment. [Architecture and boundaries](docs/architecture.md)

Replay and lab records preserve local acceptance argv and bounded diagnostics by default, alongside hashes, lengths, exit
codes and test outcomes. Explicit `retain_diagnostic_text: false` minimizes diagnostic text in new runs. New output
directories request owner-only permissions. Existing host permissions govern existing roots.
[Privacy and retention](PRIVACY.md)

## Privacy and security

- 007 runs with your user's authority and sandboxes nothing. Agent commands, replay sets and acceptance commands can run
  any local tool: review them first.
- Logs never leave the machine through 007, and prompt text is not stored by default. Agent commands send the context you
  authorize to their model providers. Optional Headroom/LiteLLM pricing receives model names and token counts and controls
  its own network use.
- The dashboard reads local agent session logs, has no authentication, and binds to loopback unless you change `--host`.
- Replays can retain prompts, source snapshots and patches when you request it. Nothing expires: `007 unregister` removes
  only the registry entry. Run manifests and results directories hold absolute paths; check them before publishing.
- Read isolation in the lab (since 1.11.0) is only what each CLI enforces, plus detection of logged tool calls. Full
  isolation needs an OS sandbox, which 007 does not provide.

Details: [PRIVACY.md](PRIVACY.md). Report vulnerabilities privately: [SECURITY.md](SECURITY.md).

## Evidence and current thesis

The current beta asks whether a lower reasoning effort pays for the chosen executor on your repository's replay tasks,
against a margin declared before spending. Each verdict names its executor, repository, specification form and mode.

| Frozen experiment (mode) | Observed time/cost | Quality verdict |
|---|---|---|
| Public go-json, Codex gpt-6.1-sol, requested medium vs high, 41 tasks, 8 attempts per arm (standalone) | About 30% lower median agent time and 31.5% lower median estimated cost, per attempt | **NOT-PROVEN** at 3 pp. Difference −0.9 pp, 95% interval −3.4 to +1.6. [Result](evidence/go-json-topup-20261106/RESULT-TOPUP.md) |
| Public go-json, Claude Opus 5.5, requested medium vs xhigh, 41 tasks, 2 attempts per arm (standalone) | 67% lower median agent time and 75% lower median estimated cost, per attempt | **NOT-PROVEN** at 10 pp. Difference −5.5 pp, 95% interval −11.8 to +0.7. [Result](evidence/go-json-claude-20261107/RESULT-CLAUDE.md) |
| Study F: public go-json, Claude Opus 5.5, requested medium vs xhigh, 41 tasks, 2 attempts per arm (standalone) | Estimated cost per accepted change 0.26 of xhigh's (0.22–0.31; worst case 0.27). Whole-change acceptance 56/82 vs 61/81 | **PAYS** at 20 pp. Difference +0.8 pp, 95% interval −3.0 to +4.7 (covers about 92%, see errata). Margin chosen after an exploratory reading. [Result](evidence/go-json-claude-f-20261112/RESULT-F.md) |
| Skill invoked vs disabled, 31 tasks from three public repositories, Claude Opus 5.5 medium and Codex gpt-6-astra high (standalone) | Exploratory: Claude US$26.66 with the skill vs US$23.42 without, 19 accepted each | **No detectable effect.** After audit, Claude 19/29 vs 19/29, Codex 20/29 vs 18/29 accepted. Only a difference of about 19 points or more was detectable. [Evidence](docs/evidence.md#paired-study-of-the-skill) |
| Durability and subscription quota | Unmeasured for these causal comparisons | Separate measurements are required |

Savings in the first two rows are per attempt, not per accepted change. Differences are in the pass rate on reachable hidden
tests, not in whole-change acceptance; Study F shows the two can diverge. NOT-PROVEN means the interval did not exclude a loss
of the margin; it is not a measured loss. Arms differ by requested effort only: the supported native CLIs do not report the
served effort. Costs are API-equivalent estimates. The reports preserve their original margins and decision rules, and their
acceptance measures come from commit-derived tests.

**Errata and known limits** ([details](docs/evidence.md#errata-and-limits-published-for-1110)): every replay above ran
before 1.11.0, when the agent's workspace path showed its arm label, so the arms were not blind and the effect is unmeasured.
The first calibrated control of Study F's rule read NOT-CALIBRATED (a false `PROVEN` 3.50% of the time under a clustered
loss), because the critical value and the floor were simulated for independent loss only. The rule corrected in 1.11.0
passed a second control for Study F's shape alone, without the power to support a detection claim, and Study F's `PROVEN`
holds under both rules. Study F's 95% interval covers about 92% in practice.

The laboratory uses reference/oracle controls, sensitivity checks, paired task readings and a calibrated quality decision.
These experiments leave broader quality, durability, general-productivity and incremental-value claims open: nothing here
shows that 007 beats using the same CLI directly. [Laboratory methods](docs/lab.md) ·
[Evidence and historical scope](docs/evidence.md)

## Measurement and replay tools

From the 007 checkout:

```bash
python3 scripts/harness_report.py --receipt-dir /path/to/your/project/.007/receipts --format json
python3 scripts/touch_rate.py --repo /path/to/your/project --days 30
python3 scripts/replay_eval.py --set examples/replay-set.example.json list
```

The lower-level replay runner accepts explicit repositories, arms, agent argv, seeded tasks and acceptance commands. Its
advanced `run` entry point executes those commands. The laboratory guide covers the budgeted experiment workflow.
[Replay example](examples/replay-set.example.json) · [Laboratory guide](docs/lab.md)

The offline semantic replay and portable corpus checks exercise controller mechanisms with synthetic inputs and oracle
controls. Their cost values are literal test data. Native captured-runtime and candidate-retention gates have their own
qualification requirements. [Corpus contents and limits](tests/fixtures/README.md)

## Development and contribution

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
```

Tests use synthetic or licensed historical inputs, and no test calls a paid model. Git is required by tests that create
disposable repositories. Node and Go enable their respective runtime checks. CI runs for PRs, main and version tags, with
static analysis reported separately. [CI](.github/workflows/ci.yml) · [Security analysis](.github/workflows/codeql.yml)

`scripts/` holds the runtime, `dashboard/` the local UI, `bin/007` the CLI wrapper and `evidence/` the versioned records.
[Product](docs/product.md) · [Architecture](docs/architecture.md) · [Research](docs/research-history.md)

Contribution rules cover proof, privacy, minimal changes and release authority. [Contributing](CONTRIBUTING.md) ·
[Agent instructions](AGENTS.md) · [Code of conduct](CODE_OF_CONDUCT.md)

## Versioning and changelog

Versions follow Semantic Versioning. The public interface is the `007` CLI, the receipt and report schemas, and the dashboard
snapshot; a breaking change to any of them needs a major version. Releases are tagged and listed in
[CHANGELOG.md](CHANGELOG.md), with each release's qualification record under `evidence/`. Only the latest tag receives
security fixes. A replay set mined before 1.10.1 keeps its embedded grader until it is mined again. A verdict re-read with
1.11.0 uses the corrected critical value and can move from `PROVEN` to `NOT-PROVEN`, never the reverse.
[Releasing](RELEASING.md)

## Citation

Cite a result by its frozen report, not this README: give the evidence directory, the release tag and the report's SHA-256.
Cite the software by version or commit, as [CITATION.cff](CITATION.cff) asks: Marcus Cavalcanti, *007 Framework*, version
1.10.1, 2026, https://github.com/marcuscavalcanti/007-framework.

## License

[MIT](LICENSE) © 2026 Marcus Cavalcanti.
