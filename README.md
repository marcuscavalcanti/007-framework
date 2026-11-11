# 007 Framework

**Measure reasoning-effort trade-offs and record coding outcomes locally.**

007 is a provider-neutral toolkit around your agent CLIs. It combines three capabilities.

-  **Evaluate effort.** The beta `007 lab` replays Git-history tasks at two reasoning efforts and
  evaluates a quality margin declared before spending.
-  **Observe work.** Local receipts, session metadata and the dashboard expose outcomes, costs,
  coverage and missing evidence.
-  **Guide execution.** The host skill supplies the doctrine. `007 route` prints a repository-local
  executor recommendation or a configured fallback. The host chooses and runs the executor.

Public Go replays support narrower time and estimated-cost observations. Their pre-registered
quality bounds are **NOT-PROVEN**. [Evidence and scope](#evidence-and-current-thesis)

## Choose a first use

From a source checkout with Python 3.11+ and Git, inspect the CLI.

```bash
python3 bin/007 --help
```

### Observe a project

```bash
python3 bin/007 init --repo /path/to/your/project
python3 bin/007 dashboard
```

Registration creates local project records and enrolls the path. Task receipts require the lifecycle
integration below. Opening the dashboard also allows local activity collection under the configured
project scope. [Privacy](PRIVACY.md)

### Evaluate reasoning effort

```bash
python3 bin/007 lab --help
```

The evaluation flow is `mine → sensitivity → run → report → feasibility`. Start from
`examples/lab.example.json` and follow the laboratory guide for commands, oracle controls and
decision rules. [Laboratory guide](docs/lab.md)

`run` launches the configured agent commands. Declare inputs, acceptance rules, a quality margin and
spend limits first. Its budget reserves an amount for in-flight attempts. An attempt above its
reserve can exceed the total cap before the observed cost triggers a stop. Costs retain their
accounting source.

### Use the host skill

Install the skill in your host's documented skills directory and ask it to use `007-framework` for a
task. The workflow is scope, executor choice, minimal implementation, repository harness and outcome
receipt.

```text
Use 007-framework to fix the pagination regression. Preserve unrelated work,
reuse the existing query path, and stop after integrated proof.
```

## Install

Install the stable CLI from a published tag. The example uses v1.7.0. The release page includes
the source archive, SHA-256 checksums and build provenance details.
[007 Framework 1.7.0](https://github.com/marcuscavalcanti/007-framework/releases/tag/v1.7.0)

```bash
release_tag=v1.7.0
git clone --branch "$release_tag" --depth 1 https://github.com/marcuscavalcanti/007-framework.git
cd 007-framework
pipx install .
pipx ensurepath
```

Open a new shell after the PATH update, then run `007 --version` and `007 --help`. From an existing checkout, `pipx
install .` installs that source version. Building the wheel uses setuptools. The installed runtime
uses the Python standard library and includes its scripts, dashboard assets and default public
evidence. Version metadata comes from `SKILL.md`.

For a host skill, use the directory documented by that host. For Codex's default skills directory,
run the following from the source checkout.

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD" ~/.codex/skills/007-framework
```

A manual CLI link is another source-checkout installation path.

```bash
mkdir -p ~/.local/bin
ln -s "$PWD/bin/007" ~/.local/bin/007
export PATH="$HOME/.local/bin:$PATH"
```

Persist that PATH entry in your shell profile for later shells. Existing links need to identify the
intended checkout before you replace them.

### Requirements by capability

CI qualifies Linux and macOS. The laboratory and observatory use POSIX file locks.

| Capability | Requirements |
|---|---|
| Core CLI, receipts and dashboard | Python 3.11+ and Git |
| Compressed Codex logs, `*.jsonl.zst` | Python 3.14+ with `compression.zstd`, or the `zstd` executable on PATH |
| Agent execution | Your configured CLI, its authentication and the context you authorize |
| Replay acceptance | The toolchain and acceptance commands declared by the task |
| Wheel build | Setuptools, with pipx for the documented isolated installation |
| Diagnostic pricing | Optional installed Headroom/LiteLLM integration |

A missing compressed-log decoder is reported as unavailable capture. The core exposes that coverage
gap. The host controls filesystem access, network access, authentication and executor isolation.
[Privacy](PRIVACY.md)

### Integration coverage

| Integration | Supplied support |
|---|---|
| Codex and Claude Code | Native CLI stream adapters and local activity readers |
| Kimi Code and Gemini CLI | Local activity readers |
| Another CLI | Explicit argv configuration and a normalized receipt adapter |
| Compatible coding-agent host | Install `SKILL.md` using the host's skills mechanism |

Provider-neutral interfaces allow additional executors. Measured effectiveness has the executor,
repository and specification scope stated in each result.

## Task lifecycle and routing

Register each Git project once with `007 init`. Registration is idempotent, adds `.007/` to the
repository's local Git exclude file and updates the local user registry. Remove a stale entry with
`007 unregister --project /old/path`.

Start a task before implementation and persist its terminal receipt.

```bash
007 begin --repo . --task-id pagination-regression
007 record --repo . --file task.receipt.json
```

The task ID must match. Start from the receipt example and its schema. The command validates
identity, accounting, finite values and uniqueness. Missing cost stays an explicit accounting gap.
[Receipt example](examples/task.receipt.example.json) · [Receipt
schema](references/receipt-schema.md)

Wrap a configured agent command to let the controller observe the lifecycle.

```bash
007 run --repo . --task-id pagination-regression --receipt task.receipt.json -- your-agent-command
```

The command receives `FRAMEWORK_007_TASK_ID`, `FRAMEWORK_007_RECEIPT_PATH` and `FRAMEWORK_007_REPO`.
Its adapter writes the normalized receipt. Native stream capture is available through `--native-cli
codex` or `--native-cli claude`. Failed commands and missing or mismatched receipts leave unresolved
starts. A retry uses a new task ID and preserves the prior attempt.

For explicit task authority, add `--authority-file` and `--action`. The controller records an
allowed execution or blocks the command before launch. Controlled and declared provenance remain
separate. Local records can be modified by another process with the same filesystem account.
Technical containment belongs to the host. [Authority example](examples/authority.example.json)

Configure the CLIs you own to obtain a route recommendation.

```bash
mkdir -p ~/.007-framework
cp examples/routes.example.json ~/.007-framework/routes.json
007 route --repo . --task-class implement --format json
```

The selector requires mature outcomes and reliability, escape, repair, cost and latency gates. With
fewer than five mature outcomes, it uses the configured fallback. It minimizes all-attempt cost per
reliable outcome among eligible, comparable routes. Its evidence scope is repository-local. Executor
selection and serving remain explicit host actions. [Routing details](references/routing.md)

## Local observation and diagnostics

The dashboard discovers registered projects and serves a loopback interface at
`http://127.0.0.1:7007`. The browser polls every two seconds. Background evidence has its own build
timestamp, and failed refreshes expose stale evidence.

Activity collection decodes native log rows locally and retains selected session metadata and token
counters. Those rows can contain message payloads before field selection. The activity view shows
session state and model/effort labels observed in native metadata, with served-identity limits kept
explicit. [Privacy](PRIVACY.md)

Collection reads complete supported logs with bounded-memory streaming and checks consumed prefixes
before resuming changed plain logs. Parent/child ownership preserves project scope. Per-commit
routes use contributing activity. Overlapping routes and unresolved historical observations retain
uncertainty. Attribution remains observational.

The dashboard separates terminal accounting, diagnostic price estimates and laboratory spend.
Open **Full evidence and operations → Spend and cost → What each 007 experiment cost** to see
the attempts and estimated spend for each experiment configured in `observatory.lab_ledger`.
Missing amounts and receipts are unpriced. Incomplete totals expose lower bounds. Task coverage
uses observed starts with matching receipts as its denominator.
Work outside that lifecycle remains outside complete receipt coverage.

Operational panels expose accepted outcomes, repairs, costs, authority events and data quality. The
causal verdict belongs to its frozen experiment. [Architecture and boundaries](docs/architecture.md)

Replay and lab records preserve local acceptance argv and bounded diagnostics by default, alongside
hashes, lengths, exit codes and test outcomes. Explicit `retain_diagnostic_text: false` minimizes
diagnostic text in new runs. Output hashes describe UTF-8 re-encoded subprocess text. New output
directories request owner-only permissions. Existing host permissions govern existing roots.

Recoverable evaluation or training examples also need authorized frozen inputs, contracts and
artifacts. Metadata and hashes provide correlation and integrity. [Privacy and
retention](PRIVACY.md)

## Evidence and current thesis

The current beta asks whether a lower reasoning effort pays for the chosen executor on your
repository's replay tasks, against a margin declared before spending. Each verdict names its
executor, repository and specification form.

| Frozen experiment | Observed time/cost | Quality verdict |
|---|---|---|
| Public go-json, Codex medium vs high, 8 fresh attempts per arm | About 30% lower median agent time and 31.5% lower median estimated cost per attempt | **NOT-PROVEN** at 3 pp. Difference −0.9 pp, 95% interval −3.4 to +1.6. [Result](evidence/go-json-topup-20261106/RESULT-TOPUP.md) |
| Public go-json, Claude Opus 5.5 medium vs xhigh, 2 attempts per arm | 67% lower median agent time and 75% lower median estimated cost per attempt | **NOT-PROVEN** at 10 pp. Difference −5.5 pp, 95% interval −11.8 to +0.7. [Result](evidence/go-json-claude-20261107/RESULT-CLAUDE.md) |
| Durability and subscription quota | Unmeasured for these causal comparisons | Separate measurements are required |

Costs are API-equivalent estimates. The reports preserve their original margins and decision rules.
Their acceptance measures come from commit-derived tests. Served effort is unreported by the
supported native CLIs. Codex's served-model limits and reroute controls remain explicit in the
frozen protocols.

The laboratory uses reference/oracle controls, sensitivity checks, paired task readings and a
calibrated quality decision. Feasibility estimates the sample a future verdict needs. These
pre-registered experiments leave broader quality, durability and general-productivity claims open.
[Laboratory methods](docs/lab.md) · [Evidence and historical scope](docs/evidence.md)

## Measurement and replay tools

```bash
python3 scripts/harness_report.py --receipt-dir .007/receipts --format json
python3 scripts/touch_rate.py --repo . --days 30
python3 scripts/replay_eval.py --set replay-set.json list
```

The lower-level replay runner accepts explicit repositories, arms, agent argv, seeded tasks and
acceptance commands. Its advanced `run` entry point executes those commands. The laboratory guide
covers the budgeted experiment workflow. [Replay example](examples/replay-set.example.json) ·
[Laboratory guide](docs/lab.md)

The offline semantic replay and portable corpus checks exercise controller mechanisms with synthetic
inputs and oracle controls. Their cost values are literal test data. Native captured-runtime and
candidate-retention gates have their own qualification requirements. [Corpus contents and
limits](tests/fixtures/README.md)

## Development and contribution

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
```

Tests use synthetic or licensed historical inputs. Git is required by tests that create disposable
repositories. Node and Go enable their respective runtime checks. CI runs for PRs, main and version
tags, with static analysis reported separately. [CI](.github/workflows/ci.yml) · [Security
analysis](.github/workflows/codeql.yml)

The source root is the host skill. `scripts/` holds the runtime, `dashboard/` the local UI,
`bin/007` the CLI wrapper and `evidence/` the versioned records. [Product](docs/product.md) ·
[Architecture](docs/architecture.md) · [Research](docs/research-history.md)

Contribution rules cover proof, privacy, minimal changes and release authority.
[Contributing](CONTRIBUTING.md) · [Agent instructions](AGENTS.md) · [Code of
conduct](CODE_OF_CONDUCT.md)

Report vulnerabilities through the documented private channel. [Security](SECURITY.md)

## License

[MIT](LICENSE) © 2026 Marcus Cavalcanti.
