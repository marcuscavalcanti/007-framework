# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html): the public interface is the `007` CLI, the receipt and report
schemas, and the dashboard snapshot.

## [Unreleased]

### Added

- `007 lab viability` runs before any paid run and costs nothing. It answers `VIABLE`, `NOT-VIABLE` with reasons, or
  `UNKNOWN` naming the missing inputs. Missing data never reads `VIABLE`, and any known failure decides. It combines eight
  inputs:
  - the mined task count;
  - the oracle's sensitivity (`sensitivity.json` `immediate`, plus `sensitivity-v2.json` read at floor 0.30);
  - a pilot's reach share and SD, as in `feasibility`;
  - the prompt-sufficient share, as in `sufficiency`;
  - the reference arm's acceptance;
  - the cost saving;
  - each arm's share of tasks with an accepted change;
  - the power of `PROVEN` at the break-even margin of PREREG-F.

  Each threshold is an existing gate or a recorded rule, documented with its source in the help text and in
  [the lab guide](docs/lab.md#before-spending-viability). From recorded numbers alone, it reproduces the three D-2
  outcomes: too few tasks, an oracle that rejects 0.2968 of planted defects (under 0.30), and a reference accepted in
  4.3% of cells, which also makes `PAYS` unreachable and leaves the study underpowered. Study F's go-json numbers read
  `VIABLE`. Exit codes: 0 `VIABLE`, 1 `NOT-VIABLE`, 3 `UNKNOWN`. `feasibility` and `sufficiency` now share their
  computation with it, and their output is unchanged.
- `007 lab run --aa ARM` runs ARM twice on the same tasks, at one more paid attempt per task and replicate, so the report can
  show the copies' discordance and an A/A equality check beside the verdict. The copy is a third arm,
  `ARM-aa`, with ARM's model, effort and doctrine. Its cells are dispatched, charged and stopped like ARM's, and
  they count toward every budget and stop rule. `run-manifest.json` records the copy, and a resume that turns it on, off or onto
  another arm stops with `manifest-mismatch`. `chain` skips the copies. `report` reads the copy from the manifest and keeps the
  verdict on the set's two arms, so the verdict is unchanged. Next to the verdict, the `aa` block gives:
  - the acceptance discordance per task and overall, with a Clopper-Pearson interval;
  - missing, refused, invalid or unreadable copies, counted and named but never as agreement, with a worst case that counts
    them discordant;
  - the verdict's own statistic computed A against A;
  - `rejects_equality` when its 95% interval excludes zero.

  The printed verdict gains `aa_status` and `aa_qualified`. `aa_qualified` is false whenever there are no A/A cells, and
  `report.md` then says the verdict carries no measured noise floor. Reports of runs without `--aa` keep every earlier field and
  value. See [the lab guide](docs/lab.md#the-aa-check-run---aa-arm).
- `007 lab status --set S --results R` shows the grader's health while a run is in flight. A 2026-11-15 study went 0/124 with no
  alarm because its grader crashed with exit 1 before writing a report. `status` takes no lock and reveals no verdict. It pools
  every cell, A/A copies included, and never shows an arm, task or cell. It gives:
  - the distribution of grader exit codes;
  - each cell's class: accepted, rejected, oracle error, timeout, invalid or unrecorded;
  - alarms: no acceptance after 17 graded cells, every cell accepted after 44, grader errors or timeouts (at least 3, and above
    the declared margin's share), and any exit outside `lab_accept`'s contract.

  The 17 and 44 thresholds are where an honest oracle at the verdict's own acceptance gates (25% and 90%) gives one outcome less
  than 1% of the time. `status` exits 1 while an alarm is open. `report` adds the same block, `oracle_health`, with a per-arm
  breakdown. An alarm never changes a verdict: it marks the run `oracle-suspect`. The printed verdict gains `oracle_status` and
  `oracle_suspect`, and `report.md` opens with a notice until a person runs `status --ack-oracle REASON`. That command writes
  `ORACLE-ACK.json`, bound to the counts it saw, so any new cell reopens the alarm. Runs whose cells record no grader exit read
  `unmeasured` and keep every verdict value. See [the lab guide](docs/lab.md#oracle-health-status-and-the-report).
- Read isolation and contamination detection for replay cells (`007 lab run` and `replay_eval run`). Each cell has a list of
  protected paths: `--out`, the set's directory (the set file for `replay_eval`), source repositories, hidden-test sources,
  the vault, installed plugin and skill copies under HOME, and other sessions' logs. A set opts in to prevention with
  placeholders in its agent command: `{read_isolation_claude_settings}` and `{read_isolation_claude_settings_sha256}` give
  Claude Code `permissions` deny rules and a required sandbox `filesystem.denyRead`, which `native_runner` admits;
  `{read_isolation_codex_profile}` gives Codex a permission profile that denies each path. Each cell records
  `read_isolation`, which is `unenforced` when the command asks nothing. Detection reads the retained stream
  (`--stream-copy {stream_copy}`): a tool call that names a protected path marks the cell `contaminated` and invalid, and it
  counts against `--max-invalid`. `report` and `status` (pooled) show the modes and the scan results; cells from before 1.11.0
  read `unrecorded` and are never rescanned. Prevention is only what each CLI enforces, detection sees only logged tool calls,
  and full isolation needs an OS sandbox, which 007 does not provide. See
  [the lab guide](docs/lab.md#read-isolation-and-contamination).

### Changed

- The README now presents 007 as a measurement layer for routing decisions: outcome receipts plus a pre-registered causal
  verdict with a declared error rate. That error rate is measured for one path and one shape only: `report
  --missing-data-guard` with `compare.critical_floor`, on Study F's shape (go-json, 41 tasks, two attempts per arm, a 20-point
  margin); a plain `report`, a run without a floor and any other shape are outside it, and the CLI has no command that runs
  the control. 007 measures; a host or a gateway routes. Standalone use is the only mode that exists; the gateway mode is a
  design that would reuse the same receipts and verdict code, and is not built. `007 route` and the host skill move out of
  the headline and are labelled experimental. The README, `docs/product.md`, `docs/architecture.md`, `CITATION.cff` and the
  package description carry the same wording. A "Why, for whom, status" section states that 007's incremental
  value over a well-informed user of the same native CLI is not demonstrated.
- README evidence table: adds Study F (`PAYS` at 20 points, whole-change acceptance 56/82 against 61/81, margin chosen after an
  exploratory reading) and the paired study of the skill (no detectable effect; after audit Claude 19/29 against 19/29, Codex
  20/29 against 18/29), names each row's model, mode and requested effort, and states that savings are per attempt and
  differences are on reachable hidden tests, not whole-change acceptance.
- README structure: install comes before first use, with pipx listed as a prerequisite and the Claude Code skill path
  (`~/.claude/skills/007-framework`) next to Codex's; the lab flow reads `mine → sensitivity → viability → feasibility → run →
  status → report`, with `sufficiency` and `chain` as optional steps and what to expect (NOT-PROVEN at 3 points, read
  isolation, `--jobs`); the routing selector's gates and its fallback-or-block behaviour are spelled out; new sections on
  privacy and security, versioning and citation. Paths that belong to the 007 checkout and those that belong to your project
  are now told apart.
- Maturity is stated per component, not by the version number: the README says that 1.x indicates interface stability, not
  demonstrated value, and the package metadata carries `Development Status :: 4 - Beta`.

### Fixed

- **Runs before 1.11.0, Study F included, exposed the arm label to the agent.** The agent's working directory was
  `007-<task>-<arm>-r01-<random>`, and the runner receipt path in its arguments was `<task>-r01-<arm>.runner.json`. A stage-2
  task id also carried its stage-1 arm. This was a visible difference between the arms of the main comparison, and its effect
  on any verdict was not measured. Since 1.11.0, `run` seals a random `blind_salt` in `run-manifest.json`. Each cell gets a token,
  sixteen digits of a salted SHA-256 of its id, and its agent sees only that token:
  - the workspace is `007-<token>-<random>`;
  - the receipt and stream copy are written under `--out/.blind/` and renamed to the cell's own names once the agent exits;
  - the grading directory is `007-acceptance-<token>-<random>`.

  The A/A copy and stage-2 cells get tokens like any other cell. Results, `report` and `chain` keep the real arm names
  (`status` pools every cell and names no arm), and each cell records its `blind_token`. The token is stable across resume, and a malformed salt stops a resume with
  `manifest-mismatch`. A run sealed before 1.11.0 resumes with its labelled paths, and its report and verdict are unchanged. The
  model and effort flags, and any doctrine that differs between arms, still reach the agent: they are the treatment. See
  [the lab guide](docs/lab.md#blind-arms-what-the-agent-sees).
- An agent receipt left in `--out/.blind/` by a controller that died is now counted. `report` lists it in
  `orphan_blind_files`, named by its cell when the salt and the ledger or plan trace it, and counts that cell as attempted
  without a result; `status` lists the file names, which are tokens. A resume stops with `uncertain-attempts` for such a file
  even when the ledger lost its dispatch.
- `replay_eval run`, outside `007 lab`, named each agent's workspace and receipt by its arm. It now uses the same salted tokens
  and seals the salt as `blind_salt` in its `summary.json`, written before the first cell. Outputs without a salt load as
  before.
- **`PROVEN` was too easy when a task's attempts fail together.** A calibrated positive control of Study F's rule (41 go-json
  tasks, two attempts per arm, a 20-point margin, 4,000 replicates per loss model) labelled it NOT-CALIBRATED. A true loss of
  the margin read `PROVEN` 3.50% of the time (Wilson 2.97–4.12%) when both `medium` attempts of a task failed together,
  against 2.03% when attempts failed alone and the 2.5% the rule promises. The missing-data guard was not the cause: L2 changed
  no verdict in either model. The cause was `proven_critical`, and the floor Study F built with it: both simulated the loss as
  attempts that fail independently. A clustered loss halves the number of independent loss units, so it doubles the loss's
  share of the variance and skews the per-task differences. The 97.5% point of the statistic rose from 2.18 to 2.44, while
  Study F's floor sat at 2.23. `proven_critical` (and
  `whole_loss_draws(..., clustered=True)`) now also simulates the clustered loss, with the same expected loss, and keeps the
  larger value. `proven_critical(..., loss=("independent",))` returns the earlier value draw for draw.

  The main verdict, the A/A statistic and `report --missing-data-guard` all use the new value. A run made before 1.11.0
  and read again by 1.11.0 can therefore move from `PROVEN` to `NOT-PROVEN` in any of the three, never the other way.
  `proven_critical(..., loss=("independent",))` and `guard_decision(..., loss=("independent",))` reproduce the earlier
  critical value and guard verdict; `report` has no switch for it. A new `guard_decision` returns the guard's verdict
  without the cost ratio. On the control's replicates, with the floor rebuilt the
  way Study F built it (2.4768 instead of 2.2315), `PROVEN` at the margin is 2.33% clustered and 1.43% independent, and power
  at a true loss of 10 points falls from 56.5% to 49.0%. With Study F's floor kept, the rates are 2.75% (2.29–3.30%) and 1.88%
  and power is 55.8%. A `compare.critical_floor` computed before 1.11.0 covers independent loss only: rebuild it. Study F's
  frozen analysis is unchanged; a second calibrated control of the corrected rule is reported in the errata below. See
  [the lab guide](docs/lab.md#proven-under-a-clustered-loss).
- **A Claude usage limit that cut a call after the agent had worked read as an invalid cell.** 1.9.0 covered only refusals with
  no usage, so with `--jobs 4` the cells in flight when the account's limit started could spend a `--max-invalid` of 3 and end
  the run for good (`STOP.json`). The runner receipt now records `usage_limit`: its source (the CLI's "usage limit reached"
  result or a rejected `rate_limit_event`) and the reset time the provider gave, in Unix seconds, or none; never the text. Such a
  call is refused whatever its usage (its cost is still charged), labelled `provider-rate-limit`, kept out of `--max-invalid`, and
  set aside and dispatched again with `--requeue-refused`. Any other rate limit after the agent worked is still an invalid cell.
- **A Claude usage limit now stops dispatch as a failed quota gate does.** A usage-limit refusal pauses the run with
  `quota-hold`, not `rate-limit`, so `--rate-limit-wait-s` no longer retries a five-hour or seven-day window every 10 minutes.
  The ledger row records `usage_limit` and `resets_at`, `run` returns `resets_at`, and while that reset lies ahead (and planned
  cells remain) a resume stops at once with `quota-hold`, `resets_at` and `retry_after_s`, dispatching nothing. A limit that
  named no reset falls back to the 10-minute cooldown. The quota probe (`--quota-gate`) now reads a probe whose own call hit the
  limit as `usage limit reached` instead of `no rate_limit_event`, and `quota.jsonl` records `resets_at`.
- A refused call whose stream touched a protected path stays `contaminated`: it counts against `--max-invalid`, is never
  relabelled `provider-rate-limit` and is never requeued. Before, a contaminated cell whose receipt also named a refusal was
  relabelled, kept out of `--max-invalid`, and with `--requeue-refused` moved to `refused/` and dispatched again.
- `007 lab report` raised `statistics.StatisticsError` when an arm of the comparison had no valid cell, and wrote no report. It
  now writes one: the verdict carries `arms_without_valid_cells` (empty when both arms have one), the same-change, time and
  durability verdicts read `NO-INFORMATION`, the thesis `UNPROVEN`, `rework_ok` is null instead of a vacuous true, the empty arm's
  median reasoning tokens are null, and `report.md` opens with a "No comparison" line naming the arm. With no valid cell in
  either arm, `report` still refuses with "no valid cells to report".

- **Documentation that contradicted the code or the schema.**
  - The README said a missing cost "stays an explicit accounting gap". `007 record` rejects a receipt without a numeric
    `cost_usd`, source and status; only the explicit `cost_unavailable_opt_in` accepts `cost_usd: null` with
    `cost_status: "unavailable"`, a `custom:<name>` source and a reason.
  - The README gave task coverage the wrong denominator. It is the share of observed starts (`007 begin`) that have a matching
    terminal receipt; an open start stays in the denominator.
  - `references/metrics.md` said Codex logs over a 4 MiB window kept only tail counters. Since 1.7.0 the collector reads Codex
    and Claude Code logs whole from a verified byte cursor (`local_activity.ActivityCollector._parse`, `read_log`,
    `unchanged_prefix`); usage is marked partial only when a session's own counters are incomplete.
  - The README put `feasibility` after `report` (it runs before spending), named a `replay-set.json` that does not ship (the
    example is `examples/replay-set.example.json`), and used the CLI before installing it.
  - The README's manual receipt flow began `pagination-regression` but pointed at an example receipt whose `task_id` is
    `pagination-fix-001`, which `007 record` would not match; it now says which ID to write and to run from the project.
  - The README said hidden tests are ones "the agent never sees" and called receipts records of each task. Hidden tests are
    kept outside the agent's workspace and stay readable on the host unless read isolation is configured; receipts are
    unauthenticated declarations for tasks started with `007 begin`.
- **Public errata for the published results, in [docs/evidence.md](docs/evidence.md#errata-and-limits-published-for-1110).**
  No frozen report is edited.
  - Blinding: every replay comparison run with 1.10.1 or earlier, Study F included, let the agent read its arm's label in its
    workspace path. The arms were not blind; the effect is unmeasured.
  - The first calibrated control of Study F's rule read NOT-CALIBRATED: `PROVEN` at the margin 81/4,000 (2.03%) under
    independent loss and 140/4,000 (3.50%, Wilson 2.97–4.12%) under clustered loss; power at a true −10 points 226/400
    (56.5%). Its first reading blamed the missing-data guard; the cause was the critical value and Study F's floor, both
    calibrated for independent loss only, and L2 changed no verdict.
  - A second pre-registered control of the corrected rule (floor 2.4768, `scripts/` tree `4fae7b3f8df4d2569f324fdcfbf23de5e79dd9c8`)
    read CALIBRATED-UNDERPOWERED. `PROVEN` at the margin, of 4,000 each: C1 independent 56 (1.40%), C1b clustered 91 (2.27%,
    1.86–2.78%), C1p partly clustered 78 (1.95%), H1 held-out independent 50 (1.25%), H1b held-out clustered 91 (2.27%), and
    `KILL` at the margin C4 78 (1.95%). The power gate PW1 failed: at a true loss of 10 points, inside the margin, the rule
    read `PROVEN` in 228/400 (57.0%); the first control's seeds gave 196/400 (49.0%) for the same rule and floor, so the power
    is between 49% and 57% (53% pooled, Wilson 95% 49.5–56.4%) against the 80% required. Detecting a loss beyond the margin is
    `KILL`'s gate: 94.42% at −40 points (passed). Equal counts across gates are coincidences of distinct seeds. It licenses
    error control only in `report --missing-data-guard` with `compare.critical_floor`, at Study F's shape (go-json, 41 tasks,
    two attempts per arm, 20-point margin, whole-attempt loss, floor 2.4768); under clustered loss the guarantee is
    "compatible with 2.5%", not "at most 2.5%". The held-out world is fresh attempts on the same tasks and arms as the floor's
    Codex pool: the favourable case, not a transfer. Not covered: a plain `report` and any run without a floor, partial-credit
    loss, clustered missing cells, any other study size. The controls' records stay private (one maintainer; models of one
    family wrote and reviewed them); their SHA-256 digests are published. Study F still reads `PROVEN`
    and `PAYS` under both rules (statistic 10.841).
  - Study F's published 95% interval covers the truth about 92% of the time in its own regime (1,838/2,000 and 1,832/2,000 in
    the two controls).
  - Version binding: the second control ran on `scripts/` tree `4fae7b3f…`. Three files differ from this release's tree
    (`effort_lab.py`, `cli_telemetry.py`, `native_runner.py`); 1.11.0's `effort_lab.py` is not byte-identical to that tree's (the usage-limit and empty-arm fixes above changed `refused`, `_run`, `quota_check`, `_report` and `summary`).
    The frozen control was rerun with this release's `scripts/` tree (`2f83d292…`) on the same inputs and seeds: the rebuilt
    floor, the coverage grid, the A/A check, the prescreen of all 29,200 replicates, the decision rule on all 979 replicates
    that reach it, the re-read of Study F and the end-to-end gate equal the validated run's output exactly. The control's
    sensitivity analysis was not rerun. A release with a different `scripts/` tree needs the comparison again.

## [1.10.1] - 2026-11-22

A patch release for `007 lab`'s grader. A replay cell now tells a grader failure from a rejection of the candidate, without
turning a candidate that hangs, floods its output or crashes its own suite into an invalid cell. Tasks mined by 1.10.1 carry
`acceptance_exit_contract: "lab-accept-v1"`; sets mined before keep their embedded grader and the 1.10.0 reading until they
are mined again. Release qualification is recorded in [the release record](evidence/v1.10.1/release-evidence.md).

### Changed

- The release reviewer for a Codex host is OpenAI `gpt-6.2-astra` at `xhigh` (maintainer's decision, `AGENTS.md` revision
  2026-11-22), in place of `gpt-6-astra`. A ChatGPT account refuses this model on Codex CLI 0.165, so the route needs a newer
  CLI; on an older one the review fails and stops, with no other model tried. The Claude route is unchanged.

### Fixed

- A task mined by 1.10.1 declares `acceptance_exit_contract: "lab-accept-v1"`. Under it a replay cell reads the grader's
  exit 0 as accepted, 1 and 3 as rejected, and any other exit as `acceptance-harness-error`, an invalid cell. In 1.10.0 a
  grader that crashed or could not start read as a rejection of the candidate. The contract also requires exactly one
  acceptance command, checked before any agent runs. Tasks without the field keep the 1.10.0 reading.
- `lab_accept.py` exits 3, with no report, when a suite command does not finish in time. In 1.10.0 that timeout surfaced
  as exit 2, which under the new contract would have made a hung candidate an invalid cell and dropped it from its arm's
  denominator. Each command still has 800 s, and the commands of one grade (`prepare` and the suite) now share one 860 s
  deadline, so the grader stops inside the cell's 900 s and exit 3 is observable whenever start-up and teardown take under
  40 s. A contract task whose `acceptance_timeout_s` is below 900 is refused before any agent runs. The wait keeps 1.10.0's
  end condition (every holder of the output pipes closes them, then the child exits), so a helper left holding the output
  is still waited for until the deadline. The deadline runs on a monotonic clock, re-read at least every second, so it
  holds when the grader itself is stopped and continued; a suite that exited meanwhile has its waiting output drained for
  up to a second instead of reading as hung. Exit 3 prints one line on standard error naming the command.
- The grader's memory is bounded. Output is dropped on arrival, except that the Go adapter keeps standard output in one
  buffer up to 64 MiB (peak memory a few times that); past the cap the run proves no pass. A repository whose
  `go test -json` stream exceeds 64 MiB can no longer be mined or graded, where 1.10.0 read it whole. A suite's own result
  file over 64 MiB is treated as unreadable.
- A suite's own result file that is cut short by a crash, malformed, of the wrong shape or over the cap (node's event
  stream, unittest's JSON, pytest's JUnit XML, a custom report) made the grader raise and exit 2, an invalid cell under the
  contract where 1.10.0 recorded a rejection. It now grades as no result: every hidden test "error", exit 1, one line on
  standard error. `--collect` still fails, so `mine` drops the commit rather than keep an empty baseline. The same holds
  for a `go test -json` stream past its cap, and for a command the candidate's tree made impossible to start (its
  directory or an in-tree runner gone, by `errno`); a missing toolchain, or a fork the host refused, stays a grader failure.
  A result file that is not a regular file or not valid UTF-8 is unreadable too, and `hidden.json` and `baseline.json` are
  read before the suite runs in the tree. A cell whose grader exits 3 reads its
  outcomes as unavailable without opening the report path. Node's records split on newlines only, since `JSON.stringify`
  leaves U+2028, U+2029 and U+0085 raw.
- `mine` reads a reference whose suite does not finish, or whose result file is unreadable, as
  `reference-fails-as-candidate`, not as a harness error.
- Known limits of the contract, not closed by it: the suite runs as the grader's user and in its process group (on purpose:
  `replay_eval` kills that whole session when the grader returns, descendants of `go test` and `node --test` included), so
  a suite that kills the grader leaves an exit outside 0, 1 and 3 and an invalid cell (the invalid budget surfaces it). A
  shared memory limit or a full disk can do the same when it hits the grader; when it hits the suite, the usual case, the
  cell reads as a rejection that the invalid budget never sees. Exit 1 is read as a rejection without proof of a grade, so
  an interpreter crash that exits 1 still reads as one. The grader needs a POSIX host (`select.poll`), as its suite
  environment already did.

## [1.10.0] - 2026-11-16

A minor release for `007 lab`, mostly corrections to the instrument. It adds a second sensitivity operator, off by default,
fixes what the first one counted, stops `mine` from keeping tasks no candidate can pass, and stops the grader from turning a
harness error into a rejection. `run` and `report` are unchanged: they still read the v1 `sensitivity.json`. A set mined before
1.10.0 keeps its embedded grader and its tasks until it is mined again. Release qualification is recorded in
[the release record](evidence/v1.10.0/release-evidence.md).

### Added

- `007 lab sensitivity --operator v2 [--floor F]` writes `sensitivity-v2.json` beside the v1 `sensitivity.json`, which `run` and
  `report` still read. A v2 mutant is the reference tree with one unit reverted to the base, built by line substitution rather
  than by applying a reduced patch. A unit is a hunk of a zero-context diff in a non-test text file; every unit is tried, and
  binary files stay as in the reference. A construction control checks, file by file, that the base plus every unit gives the
  reference and the reference minus every unit gives the base. Each mutant is classed trivial, equivalent (same tokens as the
  reference, touching only blank or comment lines), out-of-scope (the hidden tests pass without its file), invalid (breaks a
  test green at both the base and the reference with the hidden files at the base) or valid. A valid mutant ends
  `rejected-contract`, `rejected-assert` or `survived`. Tasks are measured only when the reference passes and the base fails. The
  file publishes sensitivity as a mean of per-task rates with a task-bootstrap interval, plus specificity on the equivalents,
  coverage and the whole funnel. Its decision has three states: `passes`, `fails` or `indeterminate`, plus `no-information`
  below 20 valid mutants in 8 tasks and `floor-unset` with no `--floor`; one equivalent mutant the oracle rejects reads `fails`
  before either, and `passes` needs at least one equivalent in a file the hidden tests load. The pooled binomial interval
  (Clopper-Pearson over all valid mutants, taken as independent) caps the task bootstrap, which has zero width when per-task
  rates are equal; with tasks as the unit the cap would be wider. The interval then spans two quantities, the mean of per-task
  rates and the pooled rate: where task sizes differ much they separate, and the decision drifts to `indeterminate`. A symbolic link or submodule has no unit; a comment that is a
  directive (a build tag, `go:embed`, `//export`, a shebang, a coding cookie) is not equivalent; the diff flags that set unit
  boundaries are pinned (algorithm, indent heuristic, inter-hunk context, textconv, external diff), while attributes and the
  git version are not, so the operator names the same units only on the same git. The file records `jobs`. Known limits are
  listed in `docs/lab.md`. Rows carry file indexes, never names; an `error` row or a failed control carries the exception type
  and a numeric exit code, never its message. `equivalents_loaded` counts the equivalents that can fail. Operator
  `revert-one-unit/1`.

### Fixed

- `sensitivity`: a mutant is the reference minus one sampled hunk, and every other block stays. In 1.9.0 every mutant also lost the
  reference's binary blocks and its blocks without a hunk (rename, mode change, empty file), which could fail a build and count as
  a caught defect. A diff is binary only on a `GIT binary patch` line, not on that phrase inside a text line (1.9.0 skipped such a
  text diff). A block whose only hunk is the sampled one still leaves whole, with a mode change or rename it carries. A reference
  with one hunk yields no mutant. `sensitivity.json` records
  `operator` (`minus-one-hunk/2`); a 1.9.0 file has none. Found by an exploratory audit (Codex gpt-6-astra) and confirmed in code;
  sensitivities measured with 1.9.0 stay as published. Both defects push them upward (a dropped block that fails a build counts
  as a caught defect); a case that pushes the other way is not excluded. `report` does not print the operator, and a comparison
  with a 1.10.0 one has to say so.
- `007 lab mine` kept tasks no candidate could pass: its controls graded the reference at its own tree, while a cell grades a
  patch on the base snapshot behind `reset_to_base`. A commit that renames or deletes a Go test file passed the first and failed
  the second. The reference patch is now also graded as a candidate, and such a commit is dropped
  (`reference-fails-as-candidate`, or `next-reference-fails-as-candidate` for the paired next change). The check runs once, under
  the mining load: a reference that fails once is dropped under that label, with no retry alone.
- `lab_accept.py` died on a `KeyError` when `ACCEPT_REPORT` was not set and left exit 1, which a caller reads as a rejection.
  Grading now works without it (the exit code is the verdict, the report is optional); `--collect` still requires it and says so.
  The grader exits 2, not 1, when it fails itself, and `mine` drops such a commit as `AcceptanceHarnessError`; a replay cell
  records any non-zero exit as not accepted, as before. Both fixes reach
  a set only when it is mined again: a mined task embeds its grader.

### Changed

- `docs/evidence.md` reports a paired study of the skill itself (invoked vs disabled, 31 public tasks, two agents): no
  detectable effect on acceptance by a rule written before the run. The study could only have detected a large effect, and
  host hooks ran in both arms.
- `docs/lab.md` states that a snapshot is not read isolation: an installed copy of a mined repository on the host can hold a
  task's answer.
- Amendment 2 to the Codex 5-point pilot pre-registration (`evidence/codex-5pp-20261108/AMENDMENT-2.md`), published before
  the corrected gate re-run and any pilot attempt. It pins the pilot to the v1.7.0 code, keeps the evaluator embedded in the mined
  tasks, re-runs the corrected planted-defect gate, fixes a blind rule for tasks whose reference fails, uses the floor as written
  and adds a dry run with no model. The original pre-registration, Amendment 1 and their scripts are unchanged.
- `evidence/codex-5pp-20261108/DECISIONS.md`, pushed before the gate re-run's result and any pilot attempt: what each pilot
  outcome leads to, the confirmatory cost cap (US$400), and the rules for whether one repository can reach a verdict and
  for adoption after the announcement.
- Amendment 3 (`evidence/codex-5pp-20261108/AMENDMENT-3.md`), pushed before the gate re-run's output and any pilot attempt, after an
  adversarial review of the viability rule: the confirmatory pre-registration and analysis at 5 points, a dry run on every pooled
  task with varied outcomes, a freeze that third parties can re-run with published per-cell tables, and the part-3 script.
- Amendment 4 (`evidence/codex-5pp-20261108/AMENDMENT-4.md`), after traefik/yaegi failed the gate re-run's consistency check
  and before any second re-run or pilot attempt: one quiet re-run, then an inconsistent repository leaves the pool.
- Amendment 5 and PREREG-B (`evidence/codex-5pp-20261108/`), before any pilot attempt, after an adversarial validation of the plan:
  four oracle controls (reference-failed union, a dry run that checks the reference, a serial re-grade with NO-INSTRUMENT above 2%
  discordance, one-job robustness re-grades), a load log, an A/A check, and a per-repository test of the thesis as written at the
  break-even margin. DECISIONS revision 2 makes that test the single answer.
- Amendment 6 (`evidence/codex-5pp-20261108/AMENDMENT-6.md`), after the dry run failed before any pilot attempt: pierrec/lz4's
  task bases hold a symlink the pinned snapshot refuses, so it leaves the pool; yaegi left under Amendment 4 (47/68 vs 46/68).
- Amendment 7 (`evidence/codex-5pp-20261108/AMENDMENT-7.md`), before any pilot attempt: every remaining run uses 2 jobs, after the
  dry run at 4 jobs drove the load to about 870 and the machine restarted.
- Amendment 8 (`evidence/codex-5pp-20261108/AMENDMENT-8.md`), before any pilot attempt: the serial re-grade reads patches as bytes;
  newline translation had made a CRLF patch unappliable and failed the dry run's serial check.
- Study F result (`evidence/go-json-claude-f-20261112/RESULT-F.md`): on go-json, Claude Opus 5.5 requested at `medium` against
  `xhigh` reads PAYS under PREREG-F and Amendment F-1 (reach difference +0.8 points, 95% interval −3.0 to +4.7, margin 20 points;
  cost per accepted change 0.26 of `xhigh`'s, worst case up to 0.32), with whole-change acceptance 56/82 against 61/81. DECISIONS
  part 6 reads YES for this executor on this repository; T1's third bullet was completed after the look by a demote-only step. The
  study was selected after an exploratory reading, and the result covers one public repository. Reviewed in two rounds by Claude
  Fable 5.2 at maximum effort.

### Documentation

- The lab guide states the scope of `proven_critical`'s 2.5%: it holds for attempts that fail independently. A failure shared by
  every attempt of a task is not in its loss model; an exact counter-example (24 tasks, 3 attempts per arm, 20-point margin) gives
  3.31%: one counter-example, not a bound. Study F's statistic (10.84) is far from its critical value (2.28), which was itself
  computed under that assumption.


## [1.9.0] - 2026-11-14

A minor release for `007 lab`: what Claude study F ran by script around 1.8.1 is now native, and most open items of the 1.8.0
and 1.8.1 qualification records are closed; the record lists the ones that stay open. Every new option is off by default: a run
or report without them behaves as in 1.8.1, except the fixes below. Release qualification is recorded in
[the release record](evidence/v1.9.0/release-evidence.md).

### Added

- `007 lab run` options for an unattended study: `--chunk` (dispatch, wait, gate, repeat), `--max-load` and `--load-wait-s` (a
  5-minute load gate before each chunk, `load.log`), `--quota-gate` (the set's `quota_probe`, judged on Claude's
  `rate_limit_event` rows, fails closed; `quota.jsonl`), `--cost-marker-at` and `--cost-marker-hold-usd` (one cost projection
  after the first cells; `HOLD.json` is terminal), `--requeue-refused` (a refused call is set aside under `refused/` and
  dispatched again after the pause), `--rate-limit-wait-s` (wait out the pause inside the run) and `--over-limit record` (a cell
  above `--stop-usd` is counted and the run goes on to `--max-usd`). New planned pauses: `machine-busy`, `quota-hold`. New stops:
  `cost-marker-hold` (terminal), `looked`, `load-sensitive-oracle`. `run` returns `refused_per_arm`, `requeued` and
  `over_limit_cells`, `quota_probe_usd` and `quota_probes_unmeasured`. A quota probe's cost joins the run's spend (one without a
  measured cost at the `--stop-usd` reserve), and a probe runs only with room under `--max-usd`.
- `007 lab report --single-look` takes the results' run lock and writes `LOOK.json`, after which `report` refuses to read the
  results and `run` refuses to add to them, also between chunks. `--missing-data-guard --reserve-usd X --replicates N` adds F-1's
  guard: readings P and B, L2 imputed from the plan of N replicates, the cost ratio with its interval and worst case, and an
  answer (PAYS, PROVEN-NOT-ECONOMIC, DOES-NOT-PAY). `--frozen-reach FILE` fixes the reach set and records its digest.
  `compare.critical_floor` sets a floor for the guard's critical value. On the published 2026-11-07 and study F results the guard
  reproduces every statistic, critical value and cost ratio that study F's hashed `analyze_f.py` gives.
- `native_runner --stream-copy FILE` (placeholder `{stream_copy}`) keeps the raw stream beside the cell, owner-only.
- The run manifest records the grading `toolchain`: path and version of each acceptance interpreter and of `go`, `node` or
  `pytest` when an adapter calls them. A change on resume is a `manifest-mismatch`.
- `sensitivity` grades each control again alone and lists `load_sensitive` tasks, whose grade moved with the load; they leave the
  measure, and `run` refuses a set that holds them.
- `--strict-jobs` on every `lab` command refuses a `--jobs` above a quarter of the cores (at least 2); without it, a warning.

### Changed

- The default `--jobs` is a quarter of the cores, at least 2 (was a third).
- `arm_accounting` gives `refused` per arm and `replicates`; `report.md` names refusals per arm and says when they hit the arms
  unequally, and the printed verdict carries `refused_unequal`.
- `run` no longer stops with `usd-budget` when the queue is already empty (1.8.1 checked the budget before the queue).
- A rate-limit cooldown applies only while planned cells remain.

### Fixed

- A Claude usage limit is a rate limit. The CLI's error result ("usage limit reached") and a rejected `rate_limit_event` read
  `native-error-rate-limit`, from the error text only, never from usage numbers. Before, they read `native-error` and spent the
  invalid budget, which study F had to guard with a quota gate.
- A refused call with a zero-filled `usage` counts as having no usage. The real Claude runner writes one, so in 1.8.1 the
  rate-limit pause never applied to Claude (the 1.8.1 review's open question, now pinned by a test on the runner's own receipt).
- A Claude session the CLI reopens for a background task that ended after the result (a second `init` with the same session id,
  after that task's notification) is one session: usage adds up, the cost is the last, cumulative one, and the receipt counts
  `continuations`. Before, it read `ambiguous-session`, the cause of F's only invalid cell (`GJ-F5A63B5F-r02-xhigh`, US$2.45),
  confirmed from its retained stream. Any other repeated `init` still reads `ambiguous-session`.
- The rate-limit cooldown reads the newest refusal anywhere in the ledger, after the orphan check (1.8.1 review N3).
- A snapshot's relative symbolic link whose target stays inside the snapshot is materialized as a copy instead of refusing the
  cell; absolute links, links that leave the snapshot or have no target are still refused.
- More forms of a file argument are sealed: `KEY=/file`, `--flag=key=/file`, `-f/file`, `@/file`, `--flag=@/file` (1.8.1 review
  item 6).
- A snapshot's directory link is copied only after the links inside its target are materialized.
- A controller error records `controller_error` (type, innermost frame, and the message when the set retains diagnostic text)
  in the cell and prints them to stderr.
- A manifest without `toolchain` is not compared on it (a 1.8.1 manifest still stops on the sealed 007 scripts).

### Not in this release

- Measuring the explicit-environment effect (a 2×2 on yaegi) is a paid Codex measurement, pending Codex quota and the
  maintainer's go.

## [1.8.1] - 2026-11-12

A patch release for `007 lab`, from defects the Codex 5-point pilot found. Release qualification is recorded in
[the release record](evidence/v1.8.1/release-evidence.md).

### Fixed

- `007 lab sensitivity` and `chain` read patches as bytes. Newline translation turned CRLF lines into LF, so a reference or
  candidate patch touching a CRLF file failed to apply: the task looked reference-failed, or its chain broke. Found by the
  Codex 5-point pilot's serial re-grade (its Amendment 8).
- One cell whose controller raises (a refused snapshot, a crash) becomes an invalid cell, `failure_class`
  `controller-error:<type>`, never retried. Before, the exception ended the whole `007 lab run`. The invalid budget still stops a
  run where every cell fails.
- A `--flag=/absolute/file` argument of the agent command is sealed like a bare absolute path. Before, it was silently unsealed.
- A provider rate limit no longer spends the invalid budget. A cell whose call the provider refused (receipt
  `native-error-rate-limit`, no usage reported) is labelled `provider-rate-limit` (the observed class is kept in
  `failure_class_observed`), is still charged its receipt cost or the `--stop-usd` reserve, does not count toward `--max-invalid`,
  is never retried, and pauses the run with stop `rate-limit` (no `STOP.json`). A resume within 10 minutes of the last refusal
  stops with `rate-limit-cooldown`, so a driver that resumes in a loop does not lose cells to the outage. `run` returns the
  `refused` count. Only refusals that report no usage are covered: cells already working when the limit starts can still fail
  as invalid, and a limit can hit one arm more than the other. In the Codex 5-point pilot (evidence commit `17d309e`), a rate
  limit refused every call for 7 minutes and 1.7.0 ended the paid study with `invalid-budget`.
- Patches are produced and applied losslessly: references and next changes are decoded with `surrogateescape`, references are
  written as bytes, and `git apply` runs with `--whitespace=nowarn`, so an `apply.whitespace=fix` setting no longer strips CR. A 1.8.0 `sensitivity.json`
  or chain set over CRLF or non-UTF-8 files should be rebuilt.
- `chain` skips cells with no candidate patch (controller errors, refused calls) and names them in `broken`.
- `unsealed_files` can name the file of a `--flag=/file` argument.
- A controller error prints the cell and the error to stderr. A truncated runner receipt reads as an unknown cost (charged its
  reserve) instead of ending the run.
- A run sealed by 1.8.0 does not resume under 1.8.1: the 007 scripts are sealed, so the upgrade reads as `manifest-mismatch`.
  Finish a sealed run on the version that started it.

### Notes

- Erratum to 1.8.0's list of new refusals, which omitted three:
  - `chain` on an `unbound` stage 1;
  - `report --next-results` on a stage 2 without a manifest whose ledger names one or cannot be read;
  - `run` with an `unsealed_files` that is not a list of strings.

  Over an unsealed (1.7.0) stage 1, stage 2's chain is not checked. The 1.8.0 release record also miscounts its earlier reviews (six
  reviews: five FIX FIRST, one stopped), as its release notes say.

## [1.8.0] - 2026-11-12

A minor release for `007 lab`: a resumed run is bound to what it started with, and the report accounts for every planned cell
per arm. Release qualification is recorded in [the release record](evidence/v1.8.0/release-evidence.md).

### Added

- `007 lab run` seals `run-manifest.json` before its first dispatch: the set (with its arm order), the agent command's program
  and absolute files (through symlinks), the 007 scripts and the Python version. Every dispatch records the manifest's digest. A
  start or resume that finds any of them changed stops with `manifest-mismatch` and dispatches nothing; an unreadable manifest, or
  one missing after a dispatch named it, stops with `manifest-unreadable` or `manifest-missing`; dispatches after the seal that
  do not name it stop with `manifest-mismatch` (`unbound-dispatches`). Files the attempts rewrite go in the set's
  `unsealed_files`. Limits can change at a planned pause. Before this, a resumed run re-read the set and could mix treatments
  under valid receipts. Results no sealed dispatch produced stop with `manifest-mismatch` (`unbound-cells`), and an unreadable named file with
  `executable-unreadable`. The binding state is one of `sealed`, `sealed-late`, `unbound` or `absent`, and the printed verdict
  carries it as `run_binding`. `run`, `report` and `chain` now refuse some inputs 1.7.0 accepted, as listed here.
- `007 lab report` and `chain` refuse results sealed with a different set or under another manifest; `report --next-results`
  requires stage 2 to be chained from this sealed run at the reference arm, with the same agent command, and bound to its
  own seal under the same rules, and publishes `next_run_manifest`; `chain` refuses a `compare` moved since stage 1 was sealed or a different chain set already in its
  directory. The printed verdict carries `compare_changed_after_seal`. The report gains `run_manifest` (`sealed`,
  `sealed-late`, `unbound` or `absent`, and whether the comparison or margin changed after the seal) and says it in plain words.
- `007 lab report` gains `arm_accounting`: per arm, planned cells (every task at the most replicates reached), never dispatched,
  attempted without a result (a dispatch or a receipt), invalid by failure class, valid and accepted, and whether the dispatch
  ledger was complete; also in plain words in `report.md`. Invalid cells and orphan receipts were named only as two flat lists.
  Reports written by 1.7.0 still render.

### Changed

- The README links the published 1.7.0 release and the dashboard's spend ledger (`709bbba`).
- Reviewer policy (Marcus, 2026-11-12): the reviewer follows the implementer, at `xhigh`. Codex implements: OpenAI
  `gpt-6-astra` reviews. Claude implements: Claude Fable 5.2 reviews (`AGENTS.md`, `scripts/review_route.py`). This replaces the
  cross-family rule; release notes state that reviewer and implementer share a model family.

### Fixed

- `docs/lab.md`: the miner's cap is 1,999 hidden tests (the reader's 2,000 outcomes include `__module__`), not 2,000.
- Release preparation keeps an annotated tag as such, and a failed tag-triggered preparation can be dispatched again on
  `main` with the existing tag and its exact tag object (`release.yml`, `RELEASING.md`).

## [1.7.0] - 2026-11-09

Candidate prepared for independent review. Release qualification is recorded in
[the release record](evidence/v1.7.0/release-evidence.md).

### Security

- The dashboard rejects foreign, missing, duplicate or malformed HTTP authorities and absolute request targets before
  reading route data; loopback aliases, the actual port and explicitly configured external binds remain supported.
- Activity skips session enumeration when no projects are registered; the observatory does the same when enrollment is
  empty and auto discovery is off. This does not promise preselection of every file while a project scope is active.
- Lab collection now honors an explicit acceptance environment without merging parent variables; retained-case rechecks
  honor the configured wrapper and environment too. Cells label the execution boundary without claiming sandbox proof.
- Local argv and bounded diagnostics remain available by default, with additional hashes for integrity/correlation.
  Explicit `retain_diagnostic_text: false` minimizes diagnostic text in new replay/lab runs and their copies; frozen
  inputs and historical results remain unchanged. New output directories are owner-only; existing permissions are preserved.
- Stale observatory enrollment with no matching registered project skips session enumeration. Security probes use synthetic
  or explicitly allowlisted environments and avoid assertions that can render credential values.

### Added

- CodeQL and Scorecard workflows retain bounded analysis reports as Actions artifacts, with pinned actions and read-only
  repository permissions. CodeQL SARIF/database uploads and Scorecard result publication are disabled.

- Tag-triggered source candidates with repeat-build and extracted-manifest checks, SHA256SUMS and GitHub build provenance,
  retained for maintainer publication after release qualification.
- A macOS Python 3.13 CI job alongside the existing Linux check names, portable tag-manifest verification and weekly
  Dependabot proposals restricted to GitHub Actions.
- An installable `007-framework` wheel with a `007` console entry point, versioned from `SKILL.md`, carrying the existing
  runtime layout, dashboard assets and default causal evidence. A synthetic installed-CLI check covers project records and
  the HTTP dashboard. CI builds the wheel at the minimum supported Python version and runs that check.
- A short README quickstart, `PRIVACY.md` for local collection and explicit egress, and software citation metadata.
- A persistent security review workflow in the shared agent instructions: native Codex Security when available, honest
  scope/coverage and completion gates, with the same criteria across hosts and separate authorization for paid/Cloud operations.
- `effort_segments` (`[start, model, effort]`) from Codex `turn_context` and Claude assistant rows, stored by `record`; each
  report row lists its attributed commits with the model and effort in force at commit time (`commit_efforts`).

- Dashboard snapshot field `lab_ledger`: the spend 007 itself caused, per experiment listed in the local config
  (`observatory.lab_ledger: [{"name": ..., "results": "dir" or ["dir", ...]}]`, paths relative to the config file), kept apart
  from the user's own agent usage. Per experiment: first and last attempt (from `dispatch.jsonl`), attempts, valid, invalid,
  orphan receipts, USD with its sources, USD on attempts without a valid result; plus a total. Sums of `007 lab run` runner
  receipts, a client estimate and not an invoice: an attempt without a cost is counted as unpriced (the total becomes a lower
  bound), never as zero, and a missing or unreadable directory is reported unavailable instead of failing the read.
- Dashboard panel "What each 007 experiment cost" shows that field under "Spend and cost", labelled as an estimate; with
  nothing configured it says only "No 007 experiments configured".

### Changed

- The README separates effort evaluation, local observation and host-skill use. It states log-decoding and served-identity
  limits, compressed-log requirements, stable installation/PATH and integration coverage, with detailed evidence linked.
- A session whose turns used more than one model or effort is labelled `mixed` instead of its last value, so a mixed-model
  session is no longer priced at one model's rate nor matched to one model's calibration. Claude's `<synthetic>` placeholder is
  not a model.

- Dashboard: "Full evidence and operations" now uses the verdict home's type scale, spacing, flat 6 px cards and colour tokens,
  and its summary reads as a section header. Its panels are grouped under Spend and cost, Activity and coverage, Outcomes and
  gates, and Data quality; route economics, authority counts, dataset counts and the case-evolution chart start collapsed.
  Groups are h2 and panels h3, so the page keeps one h1 and no skipped heading level. Table headers are sentence case
  everywhere, the live-session table included. No claim wording changed.

### Fixed

- Codex reasoning counters reconcile reported deltas, cumulative observations and available output bounds. Optional
  baselines retain uncertainty, known cumulative values stay visible, and dated errors outside the window preserve valid primary baselines.
  Cumulative reasoning growth fits output growth over the corresponding interval, including optional gaps. Repeated
  last-usage records validate their own reasoning/output relationship before consumption is deduplicated.
  Mixed known and unknown reasoning deltas retain their feasible lower and upper bounds. Pre-window primary resets
  discard obsolete constraints, and sparse reasoning deltas obey the output growth available from cumulative counters.
  Reporting-window results reconcile cumulative, baseline and window ranges together. Unknown baselines retain their
  output bounds, zero-capacity intervals infer exact reasoning, and dated inconsistent deltas discard older constraints.
  Continuous pre-window omissions retain earlier reasoning evidence. Unanchored last observations constrain their own
  cumulative reasoning within output bounds. Mixed full/sparse last objects retain every reconstructible primary increment,
  while contradictory reported deltas remain incomplete and preserve known diagnostic totals.
  Malformed optional scalars preserve readable primary counters. Unreported reasoning stays unavailable through summaries
  and snapshots, with an explicit availability flag; Codex output pricing can use complete primary usage without that optional
  measurement. Duplicate consumption is identified by primary counters while every physical observation retains validation
  and optional evidence. Subset constraints include non-reasoning capacity, and resets preserve known interval subtotals.
  An empty reporting window requires a readable primary snapshot before its counters can be complete.
- Codex cache subsets must fit the cumulative input categories and leave a feasible complement. Sparse allocation
  reports must agree with a known chronological increment. Contradictory allocation withholds pricing while primary
  diagnostics remain available. Omitted subset fields retain their feasible ranges.
- Full primary last-usage objects preserve optional allocation presence through aggregation. Known cumulative
  increments reconstruct omitted allocation fields, and explicit contradictory values still withhold pricing.
- Reasoning availability reflects the normalized diagnostic value, including aggregates outside the numeric envelope.
- Fresh-command Codex telemetry validates cache reads plus cache writes against inclusive input before accumulation
  and receipt enrichment. Claude retains its separate additive input/cache accounting.
- Primary subtotal availability is checked before composition, including across resets whose individually finite
  counters produce an unavailable aggregate. Finite diagnostic subtotals and explicit zero retain their values.
- Sparse Codex reasoning deltas obey reported cumulative bounds before deduplication, while absent optional bounds remain
  unavailable. Reliably dated Kimi/Gemini events outside the window cannot invalidate current usage because of missing counters.
- Retained identified logs preserve timestamp fallback beside other contributing logs; a fresh observation replaces only
  its own log. Full and partial repeated deltas share cumulative bounds before duplicate suppression.
- Gemini validates primary composition and cache allocations per observation, preserving known primary usage with unavailable
  allocation pricing. Untimed usage and missing counter objects retain uncertainty across the native readers.
- Invalid cache-only deltas retain allocation uncertainty before fallback and duplicate suppression. Coherent partial
  allocations remain priceable through validated cumulative counters.
  Unidentified historical activity keeps its timestamp fallback when merged with named logs.
- Shared native usage checks and checked token subtotals keep unrepresentable aggregates unavailable across pricing,
  summaries, routes and the dashboard. Known finite subtotals and explicit zero remain supported.
  Token-weighted quota rejects unrepresentable denominators, and invalid provided Kimi/Gemini counters stay incomplete.
- Counter timestamps survive duplicate suppression, and untimed Claude usage or cost retains window uncertainty.
  Required cumulative cache baselines and normalized Claude cache tiers are validated before pricing.
  Contradictory cache tiers preserve known primary and aggregate usage with tier pricing unavailable.
- Cumulative windows share temporal validation across native providers. Cache allocation is validated
  before duplicate suppression and after interval/window derivation, preserving primary usage.
- Native command telemetry validates Claude counter aliases by presence, type and agreement. Fatal accounting
  errors freeze the accepted prefix independently of read chunking, including aggregate limits and EOF.
  Oversized content retains its parsed identity envelope through bounded in-memory string compaction,
  with UTF-8 and escape validation throughout the discarded text.
- Compacted Codex identity messages invalidate native observation when their model evidence becomes unavailable.
  The replay runner requires confirmed output-stream closure, retains accepted prefix diagnostics, and concurrently
  counts stderr in memory. Its receipt adds `streams_closed` beside the existing stderr byte count.
- Activity, route and lab-report totals expose unavailable aggregates when they cannot be represented.
  Reservation comparisons handle large integer operands. Execution and acceptance timeout limits are
  checked before launch within the portable subprocess wait range.
- Native usage windows use an inclusive cutoff, reject temporal rewinds and reconcile cache pricing counters.
  Overflow-safe monetary validation is shared by collection, telemetry, task/replay receipts and rate cards.
  Rate-card arithmetic preserves representable estimates without intermediate float overflow.
- Standalone replay rejects nonpositive timeouts before output or launch. Controller accounting preserves
  unavailable aggregate spend when individually finite costs exceed representable totals, including recovery.
- Lineage prefers current project-local identities and uses cross-project parent information only when unambiguous.
  Cumulative usage requires continuity. Contradictory cache allocation keeps primary totals available and pricing unknown.
- Replay preflight checks the target filesystem's case rules, and the lab report reuses the shared receipt classifier.
  Numeric execution limits are validated before output/dispatch. Ledger readers and sums handle oversized values safely.
- CI runs on pull requests, `main` pushes and version tags, avoiding a second full run for each development-branch push.
- Recovery preserves unavailable-cost, per-cell and invalid-count stops before dispatch. Invalid numeric costs remain
  unavailable. Controllers and the ledger share timestamp and
  repeated-terminal validation. Replay and lab entry points preflight the full cell artifact namespace before execution.
- Artifact readers distinguish identified replay cells from runner receipts, including arms ending in `.runner`.
  Ambiguous legacy artifacts stay unavailable without rewriting historical bytes. Current log identities withdraw
  obsolete parent aliases. Native usage completeness is checked per observation, before deduplication, and against
  available cumulative counters.
- The spend ledger joins dispatch-only attempts and marks malformed or duplicate dispatch history incomplete. The dashboard
  shows lower bounds for affected counts and costs. Lab controllers sharing an output directory serialize before dispatch
  and refuse uncertain or damaged history. Task/arm identity collisions fail before execution. Three-digit replicates
  remain visible to result and budget readers.
- Commit ownership carries source, project and root session through attribution, including linked worktrees. Named-log
  observations supersede by recorded order, including same-timestamp repairs and restored native timestamps. Recording
  serializes read/dedup/append and preserves torn historical bytes while separating new JSON rows. Unresolved Claude
  legacy history stays uncertain even without a fresh companion log.
- Empty Codex per-turn usage falls back to cumulative observations. Incoherent totals remain incomplete. Claude aggregate
  cache writes survive missing tier detail, with tier-dependent prices unavailable when the breakdown is unknown.
  Successful decoder recovery clears the previous unreadable-log marker.
- Parent/child consolidation preserves project scope, including record deduplication. Per-commit model and effort come from
  the contributing logs, with mixed or unavailable identity retained explicitly. Fresh Claude main-log reads replace
  identifiable legacy clipped intervals. Unresolved historical intervals stay uncertain for attribution.
- Changed plain logs verify every consumed byte before resuming their parser, detecting equal-length, regrown and middle
  rewrites on the same inode. This adds prefix-read I/O with bounded memory. Concurrent reads serialize collector state.
- Missing Claude response usage and invalid Codex snapshots remain incomplete. Durable recording keeps completeness and
  same-timestamp counter repairs. Reports retain known subtotals, while incomplete and legacy totals remain unavailable
  for token-weighted quota comparisons.
- `lab chain` creates new output directories owner-only and preserves existing directory permissions.
- Dashboard startup uses the bound address for its server metadata, avoiding reverse-DNS stalls before announcing its URL.

- Project navigation wraps to its own row when the brand and controls cannot fit, avoiding page overflow on narrow screens.
- The lab spend ledger keeps missing receipts and amounts without cost provenance unpriced, including executed failures.
  A measured zero needs an explicit numeric receipt cost and provenance.
- Local session capture reads every Codex and Claude log whole, streaming row metadata with bounded memory, and reads a growing
  log on from a byte cursor. It read only the last 4 MiB of a Codex rollout (64 MiB for Claude) and counted the unread head as
  active: on the maintainer's machine one 541 MB rollout was a single 291 h activity interval instead of 35 (60 h), so it was
  credited with commits made while it was idle, with 4 M tokens instead of 2.6 bn. Each stored row names its log (`log_id`) and
  the store keeps a log's newest whole read, so the next `record` pass replaces a clipped interval.
- Compressed Codex rollouts (`*.jsonl.zst`, 2,819 of 2,879 on the maintainer's machine) are read: `compression.zstd` on
  Python 3.14+, else the `zstd` binary. Without either they are counted in `activity_errors` and in `record`'s output
  (`unreadable_logs`), never skipped silently.
- Codex subagent and auto-review (guardian) threads report their root session's id with `subagent: true`, as Claude subagent logs
  do, so they no longer compete with the thread that spawned them for its commits; rows stored under a child's own id join the
  root once `record` reads the child's log again. With this release's fixes, one `record` pass on the maintainer's machine took
  one repository from 8 attributed, 200 ambiguous and 43 unattributed commits to 198, 13 and 40.
- With `observatory.auto`, a Codex worktree (`~/.codex/worktrees/<name>/<repo>`) is the same project as its repository (git
  common dir) instead of a project of its own.
- A Claude session opened outside a repository maps to the first repository its rows move into (`cwds`), not only to its first
  row's directory.
- The activity panel no longer freezes a session's status and its 24 h window while the log is unchanged: both are recomputed at
  every read from the metadata kept per log.
- The passive Claude reader counts each response once (Claude Code repeats a response's usage on one row per content block: 52%
  of the maintainer's assistant rows), and a present but invalid token counter makes usage incomplete instead of zero.

## [1.6.2] - 2026-11-08

Patch release: the confirmed findings of an external audit of 1.6.1, the contribution rules, reviewer identity levels and
Amendment 1 to the Codex pilot. Additive only: no command,
flag or schema field is renamed or removed. See [the release record](evidence/v1.6.2/release-evidence.md).

### Added

- Contribution rules in `AGENTS.md`, copied to `.github/copilot-instructions.md` and read by Claude Code through `CLAUDE.md`
  (a test fails if the copy drifts); `RELEASING.md`; `.github/CODEOWNERS`, a pull request template, and bug and claim-challenge
  issue templates with security reports routed to private reporting; a short `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1 by
  reference). `CONTRIBUTING.md` now points to `AGENTS.md`.

### Changed

- Reviewer identity levels (`AGENTS.md`, `review_route.identity_level`): `verified`, `pinned-no-reroute` ("requested model
  pinned, no reroute observed, served identity unverified") and `failed`. A `pinned-no-reroute` review qualifies a release only
  as "qualified with unverified reviewer identity"; the levels never apply to experiments and never fill served identity from
  the request. Not retroactive.
- `RELEASING.md`: an announcement may report any verdict of a technically qualified release; NOT-PROVEN never states the thesis
  as proven, and a pilot's GO means only that a confirmation is feasible.
- Amendment 1 to the Codex 5-point pilot pre-registration (`evidence/codex-5pp-20261108/AMENDMENT-1.md`), published before any
  pilot attempt; the original pre-registration and its hash are unchanged.

### Fixed

- Follow-up to the independent review: reject unfinished or duplicate review
  completions and extra reported models; invalidate unexplained suite failure
  despite passing per-test reports; bind dashboard verdicts to both compared
  efforts. Existing partial report bindings remain readable but apply no verdict.
- Release manifest generation preserves whitespace in tracked filenames and
  refuses unsupported escapes and links before publishing a manifest.
- `007 lab` acceptance no longer passes a test whose suite failed around it (audit 2026-11-08, F01). A `unittest` class or module
  fixture error (`tearDownClass`, `tearDownModule`) and a `go` package that fails while none of its tests did (`TestMain`'s exit, a
  panic or fatal error outside a test) used to be dropped, so the tests read `pass` and the cell could be accepted. Those tests now
  read `error`, in mining and grading alike. Ordinary known-red test failures preserve partial grades, except that Go conservatively
  charges passes in a failed package with unattributed package output, even a harmless diagnostic. Missing Go package completion,
  unexpected process exits, failed preparation, and Node file/hook failures cannot leave affected tests green. The fixed unittest
  child normally exits zero even for red tests, so any nonzero exit invalidates its passes. Tasks mined earlier keep their
  hash-bound copy of `lab_accept.py`.
- Go acceptance also tracks each test's start and completion: a known-red test cannot explain away an unfinished test's
  timeout. Passes in that package become `error`; complete lifecycles and other packages keep their existing grades.
- A replay cell keeps the change of an agent that staged or committed it (audit 2026-11-08, F02). The retained candidate patch
  diffed the index against `HEAD`, so a commit left it without the change (and with a spurious deletion of the prompt file when
  the agent committed everything), and the change counts read the index, so `git add` alone zeroed them. Both now diff against the
  snapshot commit recorded before the agent starts. Acceptance always graded the work tree and is unchanged.
- `evidence/codex-5pp-20261108/gojson-floor-5pp.json` opens with two lines of simulation progress, so it is not valid JSON (audit
  2026-11-08, F11). It stays byte-identical because the pre-registration's `SHA256SUMS` bound it; an `ERRATUM.md` and the object
  alone (`gojson-floor-5pp.clean.json`) are added and hashed in `SHA256SUMS`. No figure changes: `freeze_pilot.py` uses the floor as
  a constant. A test now parses every `*.json` under `evidence/` and verifies every `evidence/*/SHA256SUMS` line.
- `interface_hints` cuts a signature at its top-level `:` with Python's tokenizer, so a one-line definition
  (`def f(x): return x`) or a multi-line header whose last line carries a body no longer copies the body (or, in the multi-line
  case, the following added lines) into a hint that promises signatures only (external audit F08). The one replay set built
  with hints (20 tasks of this repository, 62 hints) gets the same hints under the fix; no published result used the helper.
- The effort field trial's Kaplan-Meier curve stays at 0 to the horizon once every line at risk has died, instead of ending
  there: S(30) read "unknown" for an arm whose lines all died, and the bootstrap dropped every such draw as not estimable, which
  favoured the less durable arm. A curve still stops where censoring leaves nobody at risk with S > 0 (external audit F07).
  The trial is disabled and its outcomes were never unblinded, so no result changes.
- `007 run` with a denied `--action` and an acceptance contract (always the case under a capture config) persists its blocked
  terminal receipt again: recording demanded acceptance results that a blocked task never produces, so only the start and the
  event remained (external audit F04). The receipt now marks the contract as not run, an additive `receipt/v1` state:
  `acceptance_evidence: "not-executed"`, the contract hash, and `acceptance_summary.not_executed`. The blocked path also passes
  the caller's replay vault to `record`.
- `007 run --native-cli` no longer publishes a receipt whose declared `served_model` the native stream contradicts: telemetry
  only replaced usage, time and cost, so a Claude stream reporting one model could sit beside a receipt declaring another
  (external audit F03). When the stream names models (Claude `modelUsage`, a Codex reroute target), the declared model must be
  one of them; otherwise the run exits 2 with the telemetry kept and no terminal receipt. Declared and observed identity stay
  in separate fields. No published evidence holds a receipt with native telemetry.
- Dashboard: a `007 lab report` verdict no longer reads as evidence for whichever repository is selected (external audit F09).
  The report names no repository, so `observatory.lab_report` now takes `{"path", "project_id", "cli", "model", "effort", "against"}`,
  and the thesis panel applies the verdict only to that calibration and effort comparison. A bare path still loads but binds nothing, so
  its verdict is applied nowhere.
- Dashboard: a failed background rebuild no longer leaves the previous evidence looking current while the response clock moves
  (external audit F10). The preserved projects and aggregate are marked stale (gates WAIT, "STALE DATA"), the snapshot carries
  `rebuild_error`, and the top bar shows when the evidence was read (`evidence_read_at`) apart from the response time; Data
  quality names the failure.

## [1.6.1] - 2026-11-08

Patch release: fixes and documentation; no new command or schema.

### Fixed

- `007 lab sufficiency` measures only the behaviour the commit introduced (hidden tests minus the baseline), so an empty patch
  never qualifies; its docstring names the selection bias toward "equal".
- A dashboard layout test's 5-second subprocess timeout, which failed once on a loaded CI runner, is now 60 seconds.

### Changed

- The thesis, `docs/lab.md` and `report.md` state that a verdict holds for the specification form the set used (commit message
  plus pinned names) and that well-specified-task filters pull it toward "equal". `007 lab` is labelled beta. The dashboard
  says "less quota" is estimated as cost.
- The README opening says what 007 is: a toolkit that drives your agent CLIs (lab, skill, run/record/route/dashboard), not an
  agent and not only a skill.

## [1.6.0] - 2026-11-08

Minor release: new commands and schemas are additive, and v1 receipts stay valid. Behaviour changes are listed under
"Migration and proof boundaries".

### Release review fixes

- `007 lab sensitivity` counts a mutant only where the task's reference patch passes the oracle: an oracle that rejects
  everything no longer looks sensitive. (go-json's 62 reference patches all passed, so its published gate is unchanged.)
- `mine` and `collect` refuse a symlink anywhere on the path of a hidden test or of `.007-accept`, so a mined repository cannot
  redirect writes outside the temporary tree (`replay_eval.hidden_target`, reused).
- `report` names orphan receipts (an attempt with no result) and refuses to report when no valid cell remains.
- Codex runs record a server reroute (`model rerouted: A -> B`, the only served-model signal the Codex CLI emits) as the served
  model, so a rerouted run fails as `served-model-mismatch` instead of passing as unverified.
- Docs: `--max-usd` is a dispatch reservation, not a hard cap; planning sizes are normal approximations (lower bounds); the
  calibration's error rates are simulation results with the reach set taken as given; keep the set and its margin unchanged
  after the first attempt. "41 commits cannot reach a 3-point verdict" softened to a planning estimate, with errata in the
  go-json results.
- Dashboard: an equal accepted count reads "matched", never "enough" or "use"; the thesis line follows 1.6.0; less reasoning
  is a manipulation check; the one-task v1.4 comparison is labelled as such; effort-trial sessions are counted by arm in force
  (they share draws) and a disabled trial reads paused; blocked tasks no longer read as declared acceptances; worktrees with the
  same folder name are told apart; live sessions show age and N/A for incomplete usage.

### Thesis D: minimum sufficient effort

- Product thesis moved from "007 doctrine vs none" to the canonical minimum-intelligence thesis: the least reasoning effort that
  keeps accepted, durable changes, measured per repository. README states the bounded evidence (holdout: Codex `medium` matched
  `xhigh` with ~52% less time; Claude `medium` failed the zero margin; harder tasks at ceiling, Codex only, exploratory).
- Add `007 --version` (from `SKILL.md`, the single version source) and list `lab` in `007 -h`.
- Add `choice_observatory.py`: sessions attributed to commits by activity intervals (ambiguous commits are never guessed), line
  survival at 7/30 days, and an evidence level on every judgment; `touch_rate.survival` extracted for reuse.
- Add `effort_trial.py`/`effort_trial_analysis.py` for an opt-in randomized field trial of default effort (off by default;
  blinded outcomes) and `config_guard.py`, which refuses settings that would change the meaning of evidence levels.
- Native runner hardening found by adversarial review: whole pipe drained after exit, all served models kept, receipts reserved
  before spending, option allowlist with user configuration sources off, error classes (rate limit vs transient), acceptance run
  inside a sandbox with a minimal environment.
- Internal planning documents are no longer shipped in the public tree.
- Thesis restated by what can prove each part: a repository measures the savings and guards against a large loss (`KILL`
  when the whole interval is below -3 points); a 3-point bound probably needs more commits than one repository like go-json
  has (a pooled public corpus), with one verdict per executor.
- Public pre-registered replay on go-json-experiment/json (Codex `medium` vs `high`, 62 commits): reasoning -67%, median agent
  time -32%, same change +1.3 pp (95% t interval -4.7 to +7.2), not proven. It did not reproduce the +9.4 pp post-hoc Codex gain.
- `007 lab mine` skips commits with more hidden tests than the acceptance reader takes; `report` counts unreadable test
  reports as no test passing and names them in `unreadable_outcomes`.
- README states what one repository can show: measured (time and tokens with intervals), guarded (`KILL` near the loss that
  erases the saving), bounded (the same change within 3 points stays open); "less reasoning" is the manipulation check.
- Pre-registration of Claude Opus 5.5 `medium` vs `xhigh` on the same 41 go-json commits, margin 10 points (the decision
  margin), 2 fresh attempts per arm, critical-value floor fixed in advance: `evidence/go-json-claude-20261107/`.
- Claude result: −5.5 pp (95% t interval −11.8 to +0.7), not proven at the 10-point margin; agent time −67%, median cost −75%;
  acceptance on solved commits −11.1 pp (secondary). The between-commit spread was about five times Codex's, so README and
  `docs/lab.md` now give margin sizes per executor.
- `007 lab mine` no longer drops a commit that deletes a test or fixture file: hidden files are only those present at the
  commit (`git log --numstat` lists deleted files too). Found mining BurntSushi/toml, where it dropped 3 of 96 candidates.
- Pre-registration of a Codex `medium` vs `high` pilot on five pooled zero-dependency Go repositories, margin 5 points: it fixes
  the reach set, the noise and a go/no-go rule, and the confirmatory rules in advance: `evidence/codex-5pp-20261108/`.
- Thesis D restated as a decision: `007 lab` shows whether a lower effort pays, against a margin the set declares before any
  attempt (`compare.margin`, default 3 points, at most 20): break-even, "effectively the same" at 5, research precision at 3.
  `report` also writes `report.md`, the verdict in plain words. Durability leaves the claim until it is measured.
- go-json top-up result (pre-registered, 656 attempts, US$173 list price): Codex `medium` vs `high` −0.9 pp, 95% CI −3.4 to
  +1.6, not proven; agent time −30%. Commits differ in effect beyond what 41 can absorb, so "one repository may be enough" is
  withdrawn; a 3-point bound needs several repositories.
- Pre-registration of a go-json top-up (41 commits × 8 fresh attempts per arm, two looks, critical-value floor fixed in
  advance): `evidence/go-json-topup-20261106/`.
- The time gate no longer compares raw accepted counts (equal arms failed it about half the time); acceptance enters through
  time per accepted change and the same-change verdict. `reach_rates`, `reachable_diffs` and `proven_critical` accept a frozen
  reach set (`reach=`), and `proven_critical` an attempt count (`attempts=`), so a pre-registered run fixes its denominator and a
  critical-value floor from earlier attempts.
- `007 lab run` takes `--max-invalid`; an invalid cell whose call reported no cost is charged its reserve instead of stopping the
  run at the first provider error, and a cell the runner refused before writing its receipt is reported invalid instead of
  breaking `report`. `line_trial` counts files a run created.
- Grading no longer lets the agent's own Go tests break a package: files matching a task's `reset_to_base` (`*_test.go` for
  the go adapter) go back to base before the hidden tests land.
- `same_change` (point estimate on tests that split cells, about one false `KILL` in three under no difference) is now only a
  diagnostic; `same_change_reachable` governs and its `KILL` kills the thesis. Its `PROVEN` must beat a critical value
  simulated from the run's own cells with a 3-point loss of whole failed attempts (`proven_critical`): the t interval proved
  such a loss up to 5.6% of the time on go-json, and bootstrap-t and Johnson's skew-corrected t did worse (up to 9.8%). The t
  interval now uses t at every task count. Report schema v6.
- Dashboard: "the same change" reads `same_change_reachable` and never shows a green state without a proving report; "less
  quota" is its own claim, `ESTIMATED`, because it comes from a price estimate.
- go-json evidence, without a model: re-graded with the fix, the per-attempt noise halves (6 of 231 attempts changed) and the
  verdict stays not proven (+1.5 pp, CI −3.2 to +6.2); the planted-defect check, which had been a stub, now ran and passes
  (79% of partial changes rejected). Under the calibrated rule, two attempts per arm almost never prove; about eight per arm on
  the same 41 commits would prove equal arms about three times in four if commits do not differ in effect.
  README and docs restate what one repository can show.

### Evidence and replay

- Treat persisted acceptance/authority labels as declarations, not authenticated
  controller authorship. Original receipts and declared outcomes are preserved;
  the dashboard no longer turns locally writable evidence into verified authorship.
- Add experimental native JSON-stream adapters for fresh non-interactive Codex
  and Claude commands. Reject inherited/forked sessions, ambiguous identities,
  duplicate/truncated or over-budget streams; preserve unknown usage and cost.
  A real canary is still required for each advertised route and mode.
- Mark clipped Codex session-tail consumption as incomplete, preserving observed
  counters without submitting them for rate-card pricing. Show partial token
  coverage in the overview and affected project rows, not as a complete period.
- Retain explicitly declared pre-edit files, instructions, environment and
  acceptance recipes in a private vault, with byte/mode checks and no-replace
  publication. Restore inputs and candidates without the original checkout.
  This is a declared dependency closure, not automatic full-project capture.
- Preserve stable candidate outputs after supported incomplete outcomes,
  including telemetry publication collision, only after confirmed cleanup.
  Do not fabricate a terminal receipt, cost or successful shutdown.
- Use shared cohort economics across reports, dashboard and routing: include
  failed attempts, separate USD bases, account inclusive parent/child totals once,
  and keep incomplete cost or followup coverage unavailable for comparison.
- Add optional disjoint USD cost portions for executor, review, retries,
  verification, infrastructure and preparation. All six must reconcile to the
  declared total before full-scope economics qualifies routing or readiness;
  unknown overhead never becomes zero or upgrades historical receipts.
- Clear full-scope economic eligibility when route identity is incomplete or
  a project's source is unavailable, including an HTTP-successful stale read.
  Preserve historical data without current approval, and recover on a valid read.
- Add retained-case admission, contamination checks and explicit bounded oracle
  rechecks. Historical calibration never becomes holdout by changing a label.
  Qualified real comparisons are not yet admitted by the new dataset path.
- Add serial USD30 reservation/reconciliation accounting, checkpoint stops and
  unknown-cost/overrun handling. Accounting is not a provider spending cap;
  public retained-vault experiment execution remains disabled pending qualification.
- Add bounded dashboard event/case timelines, local-time dates, factual receipt
  contribution, stale last-good data and single-flight polling. Existing global
  historical comparisons do not represent new per-project causal experiments.
- Reuse the existing muted palette for secondary text that failed contrast checks;
  preserve keyboard focus, layout, metric values and evidence boundaries.
- Add idempotent read-only curation and sanitized checkpoint projection, with
  append-only hash/task/candidate-bound declared correction and escape links.
  Show source and affected-case counts by project without authenticating incidents.
  Accept hash/task/candidate-bound proposed hypotheses with one new routing and
  one new gate source per curation cycle; show sanitized kind/hash references
  and declared counts by project. Automatic generation, policy application and
  daily activation remain pending; proposals are not qualified improvements.
- Make historical tests reproducible from source archives using hash-bound MIT
  proof inputs. Add a synthetic integrated controller check for restoration,
  oracle controls, seeded order, complete cost arithmetic and repeated decisions.
- Add a licensed static synthetic replay corpus and full semantic regression
  digest for independent offline reproduction; keep native runtime mismatch
  rejection separate from portable fixture controls and economic ROI.

### Migration and proof boundaries

- Receipt v1 files are not rewritten. Keep the prior installation for rollback.
- Amount-only v1 receipts remain valid and descriptive but no longer qualify
  measured route ranking or readiness. Supply explicit reconciled cost portions
  prospectively; this is declaration coherence, not authenticated billing or ROI.
- Capture is explicit through a declared config and starts before task edits.
  Existing project use or old receipts do not imply replay retention.
- Native capture initially targets supported fresh non-interactive envelopes.
  Interactive/resumed tasks remain outside that promise until qualified.
- Same frozen bytes, versions and seed must yield the same controller decisions.
  Fresh LLM generations and newly captured local fixtures may differ.
- Costs in synthetic tests are literal fixture data, not charges or savings.
  No new real OLD×NEW benefit, reliable-result cost or net financial ROI is claimed.
- Still open: final native canaries, prospective cases, financial bounds and
  installation/rollback. Release CI passed; the independent review failed identity
  validation ([release record](evidence/v1.6.0/release-evidence.md)).

## [1.5.2] - 2026-10-06

- remove the inherited body minimum width that caused whole-page overflow at
  320px with a classic scrollbar; sampled wider layouts remain unchanged;
- add a stdlib browser-assisted selfcheck that rejects hidden/zero-sized causal
  values and verifies the actual dashboard at four widths; it is separate from
  unittest discovery and does not claim automatic browser CI coverage;
- keep the Headroom-inspired information hierarchy, honest unknown telemetry
  and historical/global causal scope unchanged; no new dependency or schema;
- preserve 1.5.1 and every historical causal artifact. Source commit `31c499ff`
  passed exact-commit Linux CI and a context-only independent package review;
  subsequent documentary bytes require separate qualification. This candidate
  is not publication, new ROI evidence or D7/D30 qualification. See
  [proof and remaining gates](evidence/v1.5.2/release-evidence.md).

## [1.5.1] - 2026-10-06

- prioritize accepted changes, measured repair rounds, terminal cost and open
  tasks in a Headroom-inspired dashboard; no assets or implementation copied;
- distinguish controller-observed acceptance from declarations, declared D7
  follow-up from verified durability, and provisional cost from final accounting;
- align per-route and aggregate accepted-follow-up denominators and expose
  cost provenance; open starts remain outside terminal cost;
- keep the historical effort comparison global and task-local; incomplete served
  identity is never presented as verified;
- preserve the v1.5.0 manifest and validate its historical Git blobs rather than
  requiring future versions to remain byte-identical to that release;
- add a deterministic admission-fence contrast on two sanitized defect-derived
  cases: 36 cells, zero invalid; NEW blocked all six defective candidates,
  accepted all six correct controls and left six unverifiable starts open.
  Two earlier inconclusive runs are preserved. These repetitions do not prove
  real-world ROI, model quality, general review replacement or D7/D30 durability;
- no new dependency, receipt contract, provider call, database or scheduler.
  The runtime/dashboard candidate has independent source review and exact-main
  Linux CI on Python 3.11/3.12/3.13: 155 tests per job, no test skips. The
  isolated install/rollback check covers symlinks and CLI startup only.
  Final documentation is a separate diff; exact-commit CI and tag/artifact
  verification remain distinct from source qualification. See
  [qualification](evidence/v1.5.1/release-evidence.md).

## [1.5.0] - 2026-10-06

- include stable version metadata, documentation and a separate public manifest;
- preserve the RC runtime, dependencies and historical causal artifacts byte-for-byte;
- record successful RC Linux CI with exact commit/job/attempt provenance;
- include the two RC and one prepared-stable reject verdicts with their
  hash-bound counterproofs; these preparation records do not establish
  independent approval or final-stable CI for a different commit;
- distinguish pre-test CI runner-allocation failures from observed test failures;
- require full Git history and the pinned v1.4 release tree before CI tests;
- publication requires explicit identity review, final-byte gates, a clean
  committed candidate, approval, authorization and tag/artifact read-back.

## [1.5.0-rc.2] - candidate, never tagged

### Added

- explicit opt-in for unavailable receipt cost, preserving unknown cost rather
  than manufacturing zero and excluding unpriced outcomes from economic claims;
- argv-only acceptance contracts frozen at task start; the controller records
  actual check results instead of trusting an executor's claimed checks;
- public first-shutdown-signal latch protocol and 12-cell local mutation/control
  result, exact reproducible mutant patch and observed assertion signatures,
  with a package manifest bound to the candidate source.

### Compatibility changes since 1.4.0

- malformed/non-finite receipt metrics are rejected, not silently normalized;
- after normal executor wait, unconfirmed cleanup returns exit `2`, writes no
  terminal receipt and leaves the task start open, even if the executor failed;
  wrappers must not interpret a missing receipt or exit `2` as acceptance;
- unavailable cost is accepted only with explicit project opt-in and the complete
  null-cost fields; it remains unaccounted and excluded from economic claims.
  Priced receipts retain their previous contract. See
  [receipt semantics](references/receipt-schema.md).

### Fixed

- preserve incomplete token usage and reject malformed/non-finite receipt metrics;
- confirm process-group cleanup after normal exit, failure or timeout before
  interpreting acceptance, receipts or replay diagnostics;
- preserve the first scoped shutdown signal, caller/ignored handlers and original
  unwind when cleanup diagnostics cannot be written; keep interrupted starts open.

### Evidence boundary

- runtime source is unchanged from the locally qualified a3012ee commit;
- the mutation contrast supports only the local first-signal latch mechanism;
- historical v1.4 economic results stay task-local; no new model or ROI claim;
- this is not a stable release: independent review, supported-version CI, clean
  committed release evidence and publication/read-back remain pending.

## [1.4.0] - 2026-08-31

### Added

- deterministic task-start routing across user-configured installed CLIs;
- fail-closed eligibility based on mature reliability, escapes, repairs, cost,
  and wall time before cost/latency optimization;
- aggregate and per-route reliable outcomes per USD and wall time per reliable
  outcome, counting failed attempts;
- a separately frozen causal ROI card based on one real paired-effort coding task;
- a public fail-closed record for the broader v16 bank that stopped inconclusive.

### Evidence boundary

- `medium` and `xhigh` passed deterministic acceptance 3/3 on the same real
  task; `medium` reduced estimated cost per accepted task by 42.6% and wall
  time per accepted task by 53.9%; per-cell ranges remain visible;
- this is a task-local mechanism result, not proof of task-class routing,
  provider portability, or D7/D30 durability;
- the v16 bank is inconclusive because protocol and grader precedence conflicted;
  its raw failed outputs do not support an economic or policy verdict.

### Fixed

- prevent a receipt author from promoting declared boundary events to
  controller-observed evidence;
- block denied and unclassified `007 run --action` commands before subprocess
  creation while preserving allowed controls;
- keep known performance failures visible while measurement gaps remain and
  exclude preventive controller blocks from the outcome-quality trend;
- require controlled provenance to match its persisted no-replace event and
  exclude pre-execution blocks from model-telemetry completeness;
- reject terminal receipts without a matching task-start record, closing a
  bypass that could silently remove authority binding;
- measure reported authority friction against allowed attempts instead of all
  blocked events;
- label boundary telemetry as self-reported and distinguish envelope presence
  from policy strictness;
- report deterministic causal evidence as distinct arm-scenario outcomes, each
  reproduced three times, rather than implying independent repeated cases.

### Added

- a three-state objective verdict, seven-gate decision matrix, primary next
  action, 30-day outcome trend, and aggregate/project provenance reconciliation;
- controller-observed, agent-declared, and unobserved authority tiers;
- an 18-cell deterministic OLD×NEW controller-authority flip-test with zero
  model calls and zero retries;
- optional SHA-256-bound authority envelopes with fail-closed terminal
  validation of reported boundary actions;
- aggregate and per-project fence telemetry for authority coverage, protective
  blocks, avoidable friction, and unclassified blocks;
- a preregistered OLD×NEW mechanism test with six distinct arm-scenario
  outcomes, each reproduced three times, and two negative controls.

- atomic, no-replace task-start records that expose missing terminal receipts;
- an Evidence Cockpit focused on reliable first-pass outcomes, observation
  coverage, cost per reliable outcome, and an explicit operational-versus-causal boundary.
- sanitized Codex/Claude/Kimi/Gemini activity per project with 24-hour token deltas;
- Headroom/LiteLLM-equivalent cost estimates with explicit lower bounds and
  unknown-model coverage;
- terminal-receipt cost as the KPI authority, with Headroom/RTK/rate-card values
  kept as optional diagnostics;
- corrected cache accounting that avoids charging cached input twice;
- provider-neutral `007 run` lifecycle wrapper for automatic starts and
  fail-closed terminal receipts.

## [1.1.0] - 2026-08-30

### Added

- automatic local registration for every Git project using the framework;
- explicit unregister command for stale or retired local project paths;
- atomic, no-replace terminal receipts with mandatory provider-neutral cost accounting;
- localhost multi-project dashboard with aggregate/project reconciliation and near-real-time polling;
- requested-versus-served provider/model/effort telemetry and cost coverage gates.

### Deliberately deferred

- provider-specific rate tables and model allowlists;
- DuckDB or another database before receipt volume or query latency demonstrates a need;
- login/authentication while the dashboard remains loopback-only.

## [1.0.0] - 2026-08-30

### Added

- provider-neutral routing, reuse-first implementation, proof gates, and outcome receipts;
- standard-library receipt, touch-rate, and causal replay tools;
- deterministic package tests and GitHub Actions CI;
- public controlled evidence with explicit claim limits.

### Excluded

- rejected external-provider credential doctrine;
- private probes, acceptance-test bodies, repository snapshots, and credentials;
- superseded laboratory implementations and provider-specific adapters.

[Unreleased]: https://github.com/marcuscavalcanti/007-framework/compare/v1.10.1...HEAD
[1.10.1]: https://github.com/marcuscavalcanti/007-framework/compare/v1.10.0...v1.10.1
[1.10.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.9.0...v1.10.0
[1.9.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.8.1...v1.9.0
[1.8.1]: https://github.com/marcuscavalcanti/007-framework/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.7.0...v1.8.0

[1.7.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.6.2...v1.7.0
[1.6.2]: https://github.com/marcuscavalcanti/007-framework/compare/v1.6.1...v1.6.2
[1.6.1]: https://github.com/marcuscavalcanti/007-framework/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.5.2...v1.6.0
[1.5.2]: https://github.com/marcuscavalcanti/007-framework/compare/v1.5.1...v1.5.2
[1.5.1]: https://github.com/marcuscavalcanti/007-framework/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.1.0...v1.4.0
[1.1.0]: https://github.com/marcuscavalcanti/007-framework/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/marcuscavalcanti/007-framework/releases/tag/v1.0.0
