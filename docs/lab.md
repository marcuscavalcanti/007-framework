# `007 lab`: what a lower effort saves and risks in your repository

`007 lab` replays your own commits at two efforts, without a screen, with any agent and any test runner. The source repository is only read.

```bash
007 lab mine --config lab.json --out lab
007 lab sensitivity --set lab/replay-set.json
007 lab viability --set lab/replay-set.json --results pilot --format text
007 lab feasibility --set lab/replay-set.json --sd 0.23
007 lab run --set lab/replay-set.json --out results --replicates 3 --max-calls 144 --max-usd 150
007 lab status --set lab/replay-set.json --results results
007 lab report --set lab/replay-set.json --results results
```

Start from [`examples/lab.example.json`](../examples/lab.example.json). Only `run` calls a model. It dispatches a cell only while the spend so far plus a `--stop-usd` reserve for each cell in flight stays under `--max-usd`; a cell that costs more than its reserve can push the total past `--max-usd`, so set `--stop-usd` at or above the costliest expected attempt. It stops when a valid cell reports no cost, on a cell above `--stop-usd` (unless `--over-limit record`), and once `--max-invalid` cells (default 3) are invalid; an invalid cell without a cost is charged its `--stop-usd` reserve. It resumes finished work and never retries a cell (a call the provider refused is dispatched again only with `--requeue-refused`); a cell whose controller raises (a refused snapshot, a crash) is recorded invalid as `controller-error:<type>` instead of ending the run. Before its first dispatch it seals `run-manifest.json` in `--out`: the set (arms and their order, agent command, tasks with their prompts, bases and oracle hashes), the agent command's program (its first word, through `PATH`) and the absolute files it names, also as `--flag=/file`, `KEY=/file`, `--flag=key=/file`, `-f/file`, `@/file` or `--flag=@/file` (through symlinks), this 007, the Python version, and the grading toolchain (`toolchain`: path and version of the interpreter each acceptance command starts and of `go`, `node` or `pytest` when a task's adapter calls them, found on the acceptance `PATH`); every dispatch in `dispatch.jsonl` names that manifest's digest. Each time the run starts or resumes it checks them: anything changed stops it with `manifest-mismatch`, naming what changed; restoring it makes the run resumable. A manifest that is unreadable, or missing after a dispatch named it, stops it with `manifest-unreadable` or `manifest-missing`; only a directory whose dispatches name no manifest (one from before 1.8) is sealed late. A relative path in the agent command resolves inside the task's workspace, which the set's base commit fixes; a later `PATH` lookup (`env agent`) and anything the program launches, environment variables, the CLI's own configuration files, the parts the set lists in `unsealed_files` (name there, before the first dispatch, any absolute file the attempts themselves rewrite, such as a log: otherwise it is sealed and its change stops the run, and a sealed run cannot adopt the list later because it changes the set), and anything else the oracle calls are not sealed; `report` names the sealed files and says when the program itself was not. The manifest guards against accidents, not tampering, and it records absolute paths: check it before publishing a results directory. At a planned pause (`call-budget`, `rate-limit`, `machine-busy` or `quota-hold`), `--replicates`, `--max-calls`, `--max-usd`, `--jobs` and `--max-invalid` can change: raising `--max-usd`, `--max-calls`, `--replicates` or `--max-invalid` is safe; raising `--jobs` reserves more `--stop-usd` at once and can bring a final `usd-budget` sooner; lowering `--stop-usd` below an earlier cell's cost ends the run; limits are not recorded. A provider rate limit with no usage reported (Codex's error event; since 1.9.0 also Claude's "usage limit reached" result and a rejected `rate_limit_event`; a zero-filled usage counts as none) pauses the run (`rate-limit`): the refused cell is charged like any invalid cell (its receipt cost, else the reserve), does not count toward `--max-invalid` and is labelled `provider-rate-limit`; by default it is not retried, and with `--requeue-refused` its files move to `refused/` and it is dispatched again after the pause. A resume within 10 minutes of the newest refusal stops with `rate-limit-cooldown`. Since 1.11.0 a Claude usage limit is told apart from other rate limits: the runner's receipt records `usage_limit` (its source, the CLI's "usage limit reached" result or a rejected `rate_limit_event`, and the reset time the provider gave, in Unix seconds, or none), never the text. Such a call is refused even if the agent had worked before the limit cut it (its usage and cost are still charged), and the run pauses with `quota-hold`, the stop a failed `--quota-gate` gives, instead of `rate-limit`: `--rate-limit-wait-s` does not wait it out, and the ledger row carries `usage_limit` and `resets_at`. While a refusal's reset lies ahead and planned cells remain, a resume stops at once with `quota-hold`, `resets_at` and `retry_after_s`, dispatching nothing; a usage limit that named no reset falls back to the 10-minute cooldown. Any other rate limit after the agent worked is still an invalid cell. Refused calls consume `--max-calls`, and a limit can hit one arm more than the other: `run` returns `refused_per_arm`, and `arm_accounting` and `report.md` count refusals per arm. A budget or invalid stop (`STOP.json`) is final. A manifest stop is not, except `unbound-dispatches` and `unbound-cells`: restoring inputs cannot rebind attempts the seal never covered. An absolute file in the agent command that cannot be read stops the run with `executable-unreadable`; list it in `unsealed_files` before the first dispatch. `--stop-usd` reprices the reserve charged to earlier invalid cells without a cost, and `timeout_s` (Python API) is not sealed. The set's `compare` block is not sealed: a change is reported in `run_manifest` and in the printed verdict (`compare_changed_after_seal`), and it breaks the declared-margin rule below, so it serves an exploratory reading only. `chain` refuses a `compare` moved since stage 1 was sealed (its reference picks stage 2's arm), and refuses to overwrite a different chain set in its directory: its commits are not date-pinned, so `chain` runs once per directory, and a stage 1 topped up later needs a new chain directory and a new stage 2. Mining more tasks after a pilot changes the set, so a sealed pilot directory cannot be extended. `feasibility`, `sufficiency` and the task files `report` reads (`hidden.json`, `baseline.json`, `sensitivity.json`) are not checked against the seal. Dispatches after the seal that do not name it (a 1.7.0 controller), or results no sealed dispatch produced (cells copied in, a lost ledger), stop a resume and report the run as `unbound`. The four states are `sealed`, `sealed-late`, `unbound` and `absent`; the printed verdict carries `run_binding`, and `report.json` names the sealed files and the `unsealed_files` (absolute paths: check before publishing). `report` and `chain` refuse results sealed with another set or under another manifest, or a sealed run whose ledger cannot be read; `report` names the binding in `run_manifest` (`sealed`, `sealed-late`, `unbound` or `absent`) and says if the comparison or margin changed after the seal. With `--next-results` it requires stage 2 to be chained from this sealed run at the reference arm, with the same agent command, and bound to its own seal under the same rules (an `unbound` stage 2 is refused), publishes `next_run_manifest` with how many stage-1 attempts have a stage-2 attempt (a stage 1 topped up after `chain` leaves the new ones without), and refuses a stage 2 older than stage 1's seal, or one that lost the manifest its ledger names (over an unsealed stage 1 there is no seal to chain from, so stage 2's chain is not checked); the printed verdict carries `next_run_binding`. `chain` refuses an `unbound` stage 1. The report's `arm_accounting` gives, per arm, the fate of every planned cell (every task at the most replicates any attempted or finished cell reached): never dispatched, attempted without a result (a dispatch or receipt with no result), invalid by `failure_class`, valid and accepted, with `history` saying whether the dispatch ledger was complete, partial (some results have no dispatch row), absent, damaged or unreadable (without a complete one, a dispatch that left no receipt counts as never dispatched). `report` leaves invalid cells out and names them in `excluded_invalid`; a cell whose test report cannot be read counts as no test passing and is named in `unreadable_outcomes`. `mine` skips a commit with more hidden tests than the acceptance reader takes: 1,999, since the reader's 2,000 outcomes include `__module__`.

- **Agents** are an argv template (`agent_command`) that writes a runner receipt.
- **Tests** are an adapter: `node`, `pytest`, `unittest`, `go`, or `custom`, whose command writes `{test id: pass|fail|skip}` to `$LAB_RAW_REPORT`. With `go`, the agent's own `*_test.go` files go back to base before grading, so a test name it redeclares cannot break a package. A test whose `unittest` class or module, or whose `go` package, fails outside any test (a teardown error, `TestMain`'s exit, a panic after the test returned) reads `error`, not `pass`; a test that fails on its own owns its package's failure, so a test already red at base stays outside the grade.
- **Parallelism** shortens the run; the budget reserves `--stop-usd` for each cell in flight. The default `--jobs` is a quarter of the cores, at least 2; above it every command warns (load moves grades and once restarted a machine), and `--strict-jobs` refuses.

## Running a study unattended

Study F ran Claude Opus 5.5 through `007 lab` 1.8.1 wrapped in scripts. Since 1.9.0 `run` and `report` do that work; every option is off by default, so a run without them behaves as in 1.8.1.

| Option | What it does |
|---|---|
| `--chunk N` | dispatch at most N cells, wait for all of them, run the gates below, then the next chunk |
| `--max-load L`, `--load-wait-s S` | before each chunk, wait (up to S seconds, default 3,600) for the 5-minute load to fall under L, else pause with `machine-busy`; `load.log` records the load every minute and at each gate |
| `--quota-gate` | (the set's `quota_probe` is checked before the seal) before each chunk, run the set's `quota_probe` (`{"command": [argv], "windows": ["seven_day"], "need": 0.6, "ceiling": 0.95}`: one minimal call on the study's model that prints Claude's `rate_limit_event` rows) and pause with `quota-hold` unless every event and window is allowed, no unknown window appears, and each watched window has room: used + need × share of cells left ≤ ceiling. No event fails closed. A probe whose own call hit the usage limit reads `usage limit reached` (since 1.11.0), and `quota.jsonl` records the reset the provider gave as `resets_at`. `quota.jsonl` records each decision and the probe's own cost, which joins `spent` (on resume too); a probe without a measured cost is counted in `quota_probes_unmeasured` and charged the `--stop-usd` reserve, and no probe runs without room for that reserve under `--max-usd` |
| `--cost-marker-at N`, `--cost-marker-hold-usd X` | once, after exactly the first N cells, project the cost (mean per arm × planned cells of the arm; a cell without a cost at the reserve): above X, or with an arm that has no cell yet, `HOLD.json` stops the run for good; else `MARKER.json`, never read again |
| `--requeue-refused` | a refused call is set aside under `refused/` and dispatched again after the pause. A set-aside cell is dispatched again on any later resume, with or without the option; until then `arm_accounting` counts it as attempted without a result. A stream rejected before any result is labelled refused even if the agent had worked, and is charged its reserve |
| `--rate-limit-wait-s S` | wait out `rate-limit` pauses inside the run, 10 minutes at a time, up to S seconds in all (a Claude usage limit's `quota-hold` is not waited out); it needs `--requeue-refused`, since without it every refused cell of a long outage would be lost |
| `--over-limit record` | a cell above `--stop-usd` is counted (`over_limit_cells`) and the run goes on; only `--max-usd` stops it. Without it, such a cell ends the run even if a pause was set in the same pass |
| `report --single-look` | refuses while a run holds the results' lock, then writes `LOOK.json` with the report's digest: after it, `report` refuses to read these results again and `run` refuses to add to them (`looked`; a run also checks for `LOOK.json` between chunks, though a run holds the lock that `--single-look` needs, so that check only meets a `LOOK.json` written by other means). Plain `report` calls before it leave no trace, so `LOOK.json` shows the look was taken, not that it was the first |
| `report --missing-data-guard --reserve-usd X --replicates N` | adds `missing_data_guard`; N is the run's `--replicates`, which fixes the plan (the run does not record it; fewer than the cells reached is refused): readings P (valid cells) and B (pairs with both arms), the worse deciding; L2 imputes every planned cell without a usable result as the worst case for the candidate arm (it fails every reachable test, the reference passes every one), and PROVEN needs L0 and L2 both PROVEN in P and B (otherwise NOT-PROVEN, "not decisive by missing data"); the cost per accepted change at the candidate over the reference, with a task-bootstrap interval and a worst case (no cost at X for the candidate and 0 for the reference, an invalid reference cell counted accepted); answer PAYS, PROVEN-NOT-ECONOMIC, DOES-NOT-PAY or the verdict. `compare.critical_floor` in the set sets a floor for the guard's critical value only (the main verdict ignores it, so the two can differ). Since 1.11.0 the simulated critical value covers a clustered loss too ([PROVEN under a clustered loss](#proven-under-a-clustered-loss)); a floor built with `proven_critical(..., attempts=)` before 1.11.0 covers independent loss only and should be rebuilt; `guard_decision` gives the guard's verdict without the cost ratio. Without `--frozen-reach`, a task with no valid cell has no reach, so L2 imputes nothing for it. The serial re-grade and A/A are not part of it |
| `report --frozen-reach FILE` | `{task: [tests]}` fixed before the attempts replaces the reach the run's own cells give. The report records the digest of its canonical JSON (`frozen_reach_sha256`, sorted keys: not the file's own hash); it is not sealed |

Validated on published results: on the 2026-11-07 Claude go-json run the guard reproduces L0 4.666643 (critical values 2.2315 and 2.2367), L2 4.0385 and R 0.300 (0.267 to 0.344); its own simulated L2 critical value, 2.2014, equals the one study F's hashed analysis script gives. On study F it reproduces every statistic, critical value and cost ratio of `f-result.json`.

A rate-limit cooldown applies only while planned cells remain. A driver that re-runs `run` in a loop should still cap its own retries: a refused cell is never lost, but each pass costs a probe or a call. The printed verdict carries `refused_unequal`. A controller error's message is kept only when the set retains diagnostic text (the default for replay cells). `sensitivity.json` is not sealed: a later `sensitivity` that flags a task blocks a resume. The toolchain's `--version` call runs outside the acceptance sandbox, and a set directory without `tasks/` (a chain's) records only the interpreter.

Since 1.10.0 a mutant removes one sampled hunk and keeps every other block of the reference, binary and hunk-less ones included (a block whose only hunk is the sampled one leaves whole, with any mode change or rename it carries); a reference with one hunk has no mutant, and `sensitivity.json` names the `operator`. `sensitivity --operator v2` measures something else and writes `sensitivity-v2.json`: whether A's hidden tests reject the reference tree with one unit (a zero-context hunk outside the tests) reverted. It tries every unit, checks that the units rebuild the change, sets aside trivial, equivalent, out-of-scope and invalid mutants, and publishes per-task sensitivity with a bootstrap interval, specificity on the equivalents and coverage. Its decision against `--floor` is `passes` only when the interval's lower bound clears the floor, every equivalent passes and at least one equivalent sits in a file the hidden tests load; otherwise it is at most `indeterminate`. The interval is the task bootstrap widened to the pooled binomial interval, which takes mutants as independent. It does not feed `run` or `report`. Known limits of v2: no grade is repeated alone, so a failure under load reads as a rejection: on a valid mutant it pushes toward `passes`, on an equivalent it reads `fails`, and on a control the task leaves the measure (the file records `jobs`; use a low value); the reference control grades the reference at its own tree; a mutant's visible-test run reuses the tree its graded run used, while the controls use fresh trees; comment detection does not know multi-line strings, Rust doc tests, cgo preambles (`// #include`) or TypeScript `@ts-` and triple-slash comments, so such a unit can read `equivalent`; unit boundaries depend on the git version and on attributes; `trivial` ignores changes without a hunk (an added empty file, a mode change), and one unit beside an unrelated binary is graded as valid; the classes `invalid`, `error`, `control-failed`, `operator-invalid` and `rejected-contract` have no end-to-end test yet. Other 1.9.0 behaviour: `sensitivity` grades each control again alone after the parallel pass and lists in `load_sensitive` the tasks whose grade moved; they leave the measure, and `run` refuses a set that still holds them (`load-sensitive-oracle`). A Claude CLI that reopens a session for a background task finished after its result (one more `init` with the same session id, after that task's notification) is one session: usage adds up, the cost is the last (cumulative) one and the receipt counts `continuations`; any other repeated `init` is still `ambiguous-session`. `native_runner --stream-copy FILE` (in `agent_command`: `--stream-copy {stream_copy}`) keeps the raw stream beside the cell, owner-only, for diagnosis; it holds the session's content. A snapshot's relative symbolic link whose target stays inside the snapshot is materialized as a copy; an absolute link, one leaving the snapshot or one with no target is still refused. A controller error records its type and innermost frame in the cell (`controller_error`) and on stderr, with its message when the set retains diagnostic text.

Acceptance execution uses the same configured `acceptance_sandbox` argv prefix and `acceptance_env` across replay cells,
lab collection and `admit --recheck`. An explicit environment (including `{}`) is exact apart from the controller's
`ACCEPT_REPORT`; omitted or null retains host inheritance for compatibility. Command prefixes are configured wrappers,
not proof of an operating-system sandbox. Cells identify their boundary as `host-unqualified` or
`wrapper-configured-unverified` and their environment as inherited or explicit. Configure containment before executing
untrusted candidates; no provider-specific mechanism is required by this policy. Existing frozen experiments keep their
original configuration and embedded acceptance adapter.

## The A/A check: `run --aa ARM`

Without an A/A, a disagreement such as 3 pairs in 62 cannot be told apart from noise. `run --aa ARM` runs ARM twice on the same
tasks and replicates: its copy is a third arm, `ARM-aa`, with ARM's model, effort and doctrine and the same agent command. Its cells
are shuffled into each replicate with the others, dispatched, charged and stopped like ARM's: they take a `--stop-usd` reserve, count
toward `--max-calls`, `--max-usd`, `--max-invalid`, refusals and the cost marker, and `arm_accounting` lists `ARM-aa` as an arm.
Its agent sees a token like every other cell's (see [Blind arms](#blind-arms-what-the-agent-sees)), never ARM's name or the label.
`run-manifest.json` records `aa` (`{"arm", "label"}`, or `null`); a resume with A/A turned on or off, or on another arm,
stops with `manifest-mismatch` (`aa`), so the copy is either planned from the first dispatch or not at all. `chain` does not chain
the copies (`aa_not_chained`).

`report` reads `aa` from the manifest; there is no report option. The verdict reads the set's two arms only, so its value and
statistics are the ones the same cells give without the copy. Next to it, the report's `aa` block gives:

- **Discordance:** pairs (task, replicate) whose whole-change acceptance differs, per task and overall, with a Clopper-Pearson 95%
  interval, over pairs whose two cells are usable.
- **Missing cells:** a pair with an absent, refused, invalid or unreadable cell is counted (`missing_pairs`) and its cells named
  (`missing_cells`), never as agreement; `worst_case_rate` counts each such pair as discordant.
- **The verdict's statistic, A against A:** `reachable_diffs` on the valid cells of ARM and its copy, the 95% t interval, the
  studentized statistic, `proven_critical` and the same-change reading at the declared margin.
- **The flag:** `rejects_equality` when that 95% interval, the verdict's own level, excludes zero.

The printed verdict carries `aa_status` and `aa_qualified`. `aa_qualified` is true only for `qualified`: A/A cells exist, at least 8
tasks (the verdict's own minimum) reach new behaviour in ARM and its copy, and the A/A does not reject equality. Otherwise the status
is `absent` (no A/A cells: a run without `--aa`, or one whose copies never ran), `too-few-tasks` or `rejects-equality`, and
`report.md` says the verdict is not A/A-qualified. A copy costs one more attempt per task and replicate: half again what the two arms
cost alone.

`pseudo_aa`, which splits one arm's replicate 1 against its later replicates, stays in the report; it is not this check. Study F's
recorded A/A (3.55% of permutation splits whose interval excluded zero) was the standing check on the Codex top-up's `high` cells,
not on F's cells or on Claude attempts (`TESE-SCORECARD` erratum of 2026-11-14).

## Blind arms: what the agent sees

Since 1.11.0, no path, argument or file name a cell's agent sees names its arm. Before its first dispatch, `run` seals a random
salt, `blind_salt` (32 hex digits), in `run-manifest.json`. A cell's token is sixteen digits of SHA-256 over the salt and the cell
id (`replay_eval.blind_token`). The agent works in `007-<token>-<random>` under the temporary directory. Its runner receipt and
stream copy are written as `<token>.runner.json` and `<token>.stream.jsonl` in `--out/.blind/`, and the grader runs in
`007-acceptance-<token>-<random>`. When the agent exits, the controller renames both files to the cell's own names
(`<task>-r01-<arm>.runner.json`). Results, `dispatch.jsonl`, `status`, `report` and `chain` therefore keep the real arm names, and
each cell records its `blind_token`. The receipt is kept byte for byte, so its `stream_copy` field names
`<token>.stream.jsonl`. If the controller itself dies while an agent runs, that agent's receipt stays in `.blind/`
under its token. `report` lists every file there in `orphan_blind_files`, each named by its cell when the sealed salt and the
ledger or the plan identify it, counts that cell as attempted without a result, and adds it to `orphan_receipts`; `report.md`
says how many such files there are and how many it could not trace. `status` lists the file names, which are tokens, beside a
count of labelled orphan receipts. A resume stops with `uncertain-attempts` for any file in `.blind/`, even one whose dispatch
the ledger lost, as well as for the ledger's own unfinished dispatches. The A/A copy gets a token like any other cell. So does a stage-2 cell, whose task id names
its stage-1 cell and arm. The salt is not part of the set, so it never moves `set_sha256`. A resume reads it from the manifest, so a
cell's token is the same on every resume. A salt that is not 32 hex digits stops a resume with `manifest-mismatch` (`blind_salt`).

What still differs between arms is the treatment itself:

- the model and effort flags in the agent command (`{model}`, `{effort}`);
- the doctrine appended to the prompt, when the arms' doctrines differ;
- whatever the CLI does differently at another model or effort, such as speed or output length.

The token hides the arm from the agent's own paths. It does not hide it from anyone who reads `--out`, where the manifest's salt and
the cell files map tokens back to arms. An agent that can read `--out` from outside its workspace can read them too: deny that read,
as with a host copy of the repository (see [Limits](#limits)).

**Runs before 1.11.0, Study F included, exposed the arm label to the agent.** The workspace path, which is the agent's working
directory, carried the arm name (`007-<task>-<arm>-r01-<random>`). The runner receipt path in the agent command's arguments
carried it too (`<task>-r01-<arm>.runner.json`). A stage-2 workspace also carried the stage-1 arm, through its task id. This was a
visible difference between the arms of the main comparison, and its effect on any verdict was not measured. A run sealed before
1.11.0 has no salt. Resumed with 1.11.0, it keeps its labelled paths, so one run never mixes the two procedures; its report and
verdict are unchanged.

`replay_eval run`, the experiment runner outside `007 lab`, uses the same tokens since 1.11.0. It seals its salt as
`blind_salt` in its own `summary.json`, which it now writes before the first cell, so a run that dies keeps it. A summary
without `blind_salt` was run with labelled paths, and its cells load as before.

## Read isolation and contamination

A cell's agent must not read the run or the answer. Since 1.11.0 each cell has a list of protected paths, and it uses the list
twice: to ask the CLI to deny those reads, and to look for them in the agent's retained stream. The list holds the paths below
that exist:

- `--out`, which holds the manifest and its salt, the ledger, every other cell and `.blind/`;
- the set's directory, which holds every task's hidden tests (`replay_eval run` protects the set file);
- every source repository in the set, which holds the commit a task asks for;
- hidden-test sources and the vault, when the set uses them;
- installed plugin and skill copies under HOME (`.claude/plugins`, `.claude/skills`, `.codex/plugins`, `.codex/skills`,
  `.agents/skills`), where an earlier study's agents found an answer;
- other sessions' logs under HOME (`.claude/projects`, `.codex/sessions`).

A protected path that is HOME, one of its parents or the filesystem root is refused, and so is a cell whose workspace lies
inside a protected path (move `TMPDIR`): denying either would deny the agent its own tools or workspace.

**Prevention depends on what each CLI enforces, and the set opts in.** The agent command names the rules with placeholders:

- Claude Code: `--settings {read_isolation_claude_settings}` in the Claude argv and `--settings-sha256
  {read_isolation_claude_settings_sha256}` in `native_runner`'s. The settings carry only `permissions` and `sandbox`, as
  `native_runner` admits: `Read` and `Edit` deny rules for each path (which the file tools, Grep and Glob included, apply), and
  the sandbox's `filesystem.denyRead` for Bash, with `sandbox.enabled`, `failIfUnavailable` and `allowUnsandboxedCommands: false`.
  The sandbox also limits what Bash may reach on the network, the same in every arm; a set that needs network access in Bash
  must allow it. These settings replace any static `--settings` the set carried before.
- Codex: `-c {read_isolation_codex_profile} -c default_permissions="lab_read_isolation"`. The profile extends `:workspace` and
  denies each path; Codex enforces it in its own sandbox.

Each cell records `read_isolation`: `claude-settings`, `codex-profile`, or `unenforced` when its command carries no placeholder.
`unenforced` means nothing stopped a read. The mode says what was asked of the CLI, from the placeholders; it was not checked
against a running CLI: the Claude keys come from the settings schema text in the Claude Code 2.1.322 binary, and the Codex
profile form from the Codex 0.165 binary's strings and the `-c` keys `native_runner` already admits. No CLI was run to check
them.

**Detection sees only logged tool calls.** When the set keeps the stream (`native_runner --stream-copy {stream_copy}`), each
cell's stream is scanned once its agent exits. Every string a tool call carries is matched against each protected path: Claude
`tool_use` inputs (Read, Grep, Glob, Bash commands, written content) and Codex command, file-change and MCP items, without their
output. Matching ignores case, resolves `~` and `..` against the workspace, and accepts a path's resolved and `/private`-less
spellings. A hit marks the cell `contaminated`: `valid` false, `failure_class: "contaminated"`, counted against `--max-invalid`
like any invalid cell. A contaminated cell stays `contaminated` even when the provider also refused the call (a usage limit or a rate limit with no usage): it is never relabelled `provider-rate-limit` or requeued, so a read cannot be erased by redispatching the cell. Each cell records `contamination` with its status (`clean`, `contaminated` or `unscanned` when no stream
was kept), its tool-call count, its unparsed stream lines and, for a hit, the protected path's kind and the tools, never the
command. `report` adds `read_isolation`, with the modes, the scan statuses and the contaminated cells; per arm they appear among
the invalid cells. `status` pools the same counts and names no cell. Cells written before 1.11.0 read `unrecorded`; nothing
rescans them, so their verdicts are unchanged.

The scan cannot see a path built at run time (a variable, an encoded, globbed or concatenated name, a script that computes
it), a read made by a program the agent started, or a call the CLI does not log. It is conservative the other way too: a call
that only names a protected path, such as `ls` or a written file mentioning it, counts as a hit. Neither layer isolates the
agent. Full isolation needs an OS sandbox around the whole agent process (a container or a separate user with no access to
these paths), which 007 does not provide.

## Oracle health: `status` and the report

A broken grader rejects every candidate and looks like a result: a 2026-11-15 study went 0/124 with no alarm, because the grader
exited 1 before writing its report. `status` shows the grader's health while a run is in flight, and `report` shows it after:

```bash
007 lab status --set lab/replay-set.json --results results
007 lab status --set lab/replay-set.json --results results --ack-oracle "REASON"
```

`status` reads the cells written so far, A/A copies included, takes no lock and checks no receipt. It prints health pooled over
every cell and never an arm, task, cell or verdict, so it can be read during a run without peeking at the comparison. Its exit code
is 1 while an alarm is open and 0 otherwise, so a driver can stop on it. `report` adds the same block (`oracle_health`) with a
per-arm breakdown (`per_arm`). The report already shows each arm's acceptance, so it reveals nothing new.

Each cell falls in one class. Classes are read from the grader's exits and never change the cell's verdict:

| Class | Cell |
|---|---|
| `oracle-error` | the grader failed: `acceptance-harness-error`, a `hidden-acceptance-*` failure, any exit other than 0, 1 or 3, or a single exit 1 with no readable report. `lab_accept` writes its report before every exit 1, so that last case is a grader that crashed. A set mined before 1.10.1 reads exit 2 as a rejection; it still counts here |
| `timeout` | exit 3 (a suite that did not finish, a rejection) or `acceptance-timeout` |
| `invalid` | invalid for a reason outside the grader (the agent's exit or timeout, a refusal, identity, cleanup) |
| `accepted`, `rejected` | a valid cell graded 0, or 1 with its report |
| `unrecorded` | a valid cell that records no grader exit (cells from before the field) |

It also gives `exit_codes`, the distribution of every grader exit, and `contract_violations`: cells with an exit `lab_accept` never
gives (outside 0 to 3, such as a signal), or whose acceptance disagrees with their exits. `graded` counts accepted, rejected and
timeout cells. `reference_controls_passed` counts the set's tasks whose reference control passed in `sensitivity.json`
(`conformant`), or is null without one.

| Alarm | Rings when | Why this threshold |
|---|---|---|
| `rejects-everything` | no acceptance after 17 graded cells | The verdict reads acceptance as informative from `GATES["floor"]`, 25%. An honest oracle at 25% gives 17 rejections in a row less than 1% of the time (0.75^17 = 0.75%; 16 would be 1.002%). It rings whether or not reference controls are known to pass, since the 0/124 study had none; `reference_controls_passed` says which case applies |
| `accepts-everything` | every graded cell accepted, after 44 | The same rule at `GATES["ceiling"]`, 90%: 0.90^44 = 0.97% |
| `oracle-errors` | at least 3 `oracle-error` cells, and more than the declared margin's share of graded and error cells | 3 is `--max-invalid`'s default. Above the margin's share, errors counted as rejections on one arm could move it by more than the margin alone |
| `oracle-timeouts` | at least 3 `timeout` cells, and more than the margin's share of graded cells | The same rule. A timeout is a legitimate rejection, but one caused by load falls on whichever arm runs slower |
| `exit-contract` | any contract violation | `lab_accept` exits 0, 1, 2 or 3 only |

The 1% thresholds are fixed by this release, not taken from an earlier rule. A status read many times during a run can ring by
chance more often than once in a hundred runs. The alarm is a request to look, not a verdict.

**An alarm never changes a verdict.** It marks the run `oracle-suspect`. Every verdict value stays as the same cells give it
without the alarm. The printed verdict carries `oracle_status`, which is one of:

- `no-alarm`;
- `unmeasured`: no cell records a grade, as for runs from before this field;
- `oracle-suspect`;
- `acknowledged`.

The printed verdict also carries `oracle_suspect`. While it is true, `report.md` opens with an oracle-suspect notice and the verdict
is not a clean one. A person clears it with `status --ack-oracle REASON`, which is refused when no alarm is open. That command
writes `ORACLE-ACK.json` (time, reason, alarms and the SHA-256 of the pooled counts). `report` then reads `acknowledged`, still
naming the alarms and the reason. The acknowledgement holds only for the counts it was given: any new or changed cell reopens the
alarm. `run` does not read health and does not stop on it.

## What the report can say

| Claim | Gate |
|---|---|
| Less time | At least 25% less agent time per accepted change; fewer accepted changes raise that time, and whether the changes are the same is the next row |
| The same change | `same_change_reachable`: per task, the difference between the arms' pass rates on reachable behaviours (hidden tests red at base that some cell of the task passes), with a 95% t interval over tasks. `KILL` if the whole interval is below minus the declared margin (`compare.margin`, 3 points by default). `PROVEN` if `(mean + margin) / standard error` beats `proven_critical`: the 97.5% point of that statistic when the run's own cells are redrawn with a loss of the margin injected as whole failed attempts, so such a loss is called `PROVEN` about 2.5% of the time (in go-json simulations at 3 points: under 1% at two attempts per arm and 2.6–2.8% at about eight, where the plain t interval reached 5.6% and 3.4%; the report shows the plain rate as `t_false_proven`). Since 1.11.0 the critical value is the larger of two simulations: attempts failing independently, and all of a task's candidate attempts failing together (a clustered loss); before it only the first was simulated, which let a clustered loss through more often (see [PROVEN under a clustered loss](#proven-under-a-clustered-loss)). A planned run can also fix a floor for the critical value from earlier attempts (`proven_critical(..., attempts=)`) and a frozen reach set (`reach=`). Otherwise `NOT-PROVEN`; under 8 tasks, `NO-INFORMATION`. A `KILL` here kills the thesis. The older point-estimate rule (tests that split a task's cells, -5 points) is kept only as `unseen_behaviour.superseded_verdict` |
| Durable | The change survives the next real change to the same code; requires `require_next` and `chain` |

Gates are fixed in code. If the oracle cannot reject planted defects, the verdict is `NO-INFORMATION`, never a pass.

An arm of the comparison with no valid cell (every attempt invalid, refused or missing) pairs no task. Since 1.11.0 the report
says so instead of failing with `statistics.StatisticsError`: the verdict carries `arms_without_valid_cells` (empty otherwise),
reads `same_change_reachable`, `time` and `durability` `NO-INFORMATION`, `thesis` `UNPROVEN` and `rework_ok` null, the arm's
median reasoning tokens are null, and `report.md` opens its list with a "No comparison" line naming the arm. With no valid cell
in either arm, `report` still refuses with "no valid cells to report".

## PROVEN under a clustered loss

A calibrated positive control of Study F's rule (go-json, 41 tasks, two attempts per arm, Opus 5.5 `medium` against `xhigh`,
a 20-point margin; 2026-11-23) planted a true loss by replacing `medium` attempts with an empty patch, either one attempt at a
time (independent) or both attempts of a task together (clustered). At exactly the margin, the rule said `PROVEN` 81 times in
4,000 bootstrap replicates (2.03%, Wilson 1.63–2.51%) under independent loss and 140 times (3.50%, 2.97–4.12%) under clustered
loss. It promises 2.5%, so the control was labelled NOT-CALIBRATED.

The missing-data guard was not the cause. Apart from Study F's one invalid cell, no cell was missing, and L2 changed no verdict
at the margin. The cause was the critical value. `proven_critical` simulated a loss of the margin as attempts that fail
independently, and Study F's floor, 2.2315, came from the same simulation on earlier attempts. A clustered loss has half as many
independent loss units (41 tasks instead of 82 attempts). On the control's replicates the standard deviation of the mean
difference rose from 0.047 to 0.066 (about the square root of two), and the per-task differences became more skewed. The 97.5%
point of the studentized statistic therefore rose from 2.18 to 2.44. The floor sat between the two: it decided 128 of the 140
false `PROVEN`.

`proven_critical` now also simulates the clustered loss, with the same probability and so the same expected loss, and keeps the
larger value. `proven_critical(..., loss=("independent",))` returns the earlier value draw for draw. The main verdict
(`same_change_reachable`), the A/A statistic and `report --missing-data-guard` (L0 and L2) all use the new value.

`compare.critical_floor` is an input, not something `report` computes. Rebuilt the way Study F built it (the larger of
`proven_critical(..., attempts=2)` on its two earlier pools), it rises from 2.2315 to 2.4768. The same replicates, with PROVEN
counted per 4,000 at the margin and per 400 at a true loss of 10 points:

| Rule | Margin, independent | Margin, clustered | −10 points, independent | −10 points, clustered |
|---|---|---|---|---|
| before 1.11.0 | 81 = 2.03% (1.63–2.51) | 140 = 3.50% (2.97–4.12) | 226 = 56.5% (51.6–61.3) | 185 = 46.3% (41.4–51.2) |
| new critical value, Study F's floor | 75 = 1.88% (1.50–2.34) | 110 = 2.75% (2.29–3.30) | 223 = 55.8% (50.9–60.5) | 170 = 42.5% (37.8–47.4) |
| new critical value, rebuilt floor | 57 = 1.43% (1.10–1.84) | 93 = 2.33% (1.90–2.84) | 196 = 49.0% (44.1–53.9) | 164 = 41.0% (36.3–45.9) |

With the rebuilt floor, both loss models stay under 2.5%. Power at −10 points falls from 56.5% to 49.0%: 30 of the 400 replicates
lose `PROVEN` and none gain it. With Study F's floor kept, power hardly moves, but the clustered rate is 2.75%. That is within
Monte Carlo error of 2.5%, yet above it. Neither version reaches 80% power at 41 tasks: the answer to low power is more tasks,
not a lower floor.

### Rebuilding a floor

A study that sets `compare.critical_floor` builds it before its first paid attempt, with 1.11.0 or later, from earlier
attempts that are not part of the study. Study F's recipe (`build_f.py`):

```python
import effort_lab as lab

lab.GATES["draws"] = 100_000                       # the study's analysis draws
values = [lab.proven_critical(rows, task_dir, low, ref, seed, margin=margin, reach=reach, attempts=attempts)
          for rows, ref in pools]                  # each earlier pool: valid cells and its reference arm
floor = max(v for v in values if v is not None)    # compare.critical_floor
```

- `attempts` is the study's planned attempts per arm, `seed` and `margin` are the study's own, and `reach` is the frozen reach
  the study reads.
- The default `loss` takes the larger of the independent and clustered simulations. To record both values, call it once with
  `loss=("independent",)` and once with `loss=("clustered",)`; the floor is the largest value of all.
- Write the floor, each pool's values and the hashes of the pools into the pre-registration. Rebuilding Study F's floor this
  way gives 2.4768209601363016 (Codex pool: independent 2.2315, clustered 2.4768; Claude run: 2.2269 and 2.4636). That is the
  floor a reuse of Study F's rule at Study F's shape uses: 41 tasks, two attempts per arm, a 20-point margin, Study F's pools.
- The floor is specific to that shape. `proven_critical` simulates one draw per task of the pool it is given, so the floor
  holds for studies with that many tasks; a studentized statistic over fewer tasks has heavier tails. A study of a different
  size (a 12-task replication, say), with other attempts per arm or another margin rebuilds its own floor from earlier
  attempts on its own tasks, with its own `attempts` and margin, and needs its own calibrated control before its `PROVEN` is
  read. The product does not hard-code a floor.

Study F's analysis is frozen and unchanged. A second pre-registered control (2026-11-24) tested the corrected rule with the
rebuilt floor on Study F's shape and on a held-out world from the Codex top-up, and read CALIBRATED-UNDERPOWERED: `PROVEN` at
the margin 1.25–2.27% across six gates, clustered loss 2.27% (1.86–2.78%, compatible with 2.5%), and power at a true loss of 10
points 57.0% against 80%. The rule may be reused for error control at Study F's shape only, with no detection claim; Study F
still reads `PROVEN` under both rules. Counts and scope are in
[the evidence errata](evidence.md#second-calibrated-control-of-the-corrected-rule-calibrated-underpowered). Not covered:
- a partly clustered loss sits between the two models, and is covered only if the error moves monotonically between them,
  which was not tested;
- a loss spread over a task's tests, rather than over whole attempts, is outside both models;
- these numbers hold for one set of 41 tasks.

## What one repository can answer

The savings settle fast: reasoning tokens, agent time and estimated cost per attempt need a few dozen commits. The same change does not. With the attempts each run had (about two per arm for Codex, three for Claude), a 3-point verdict needs hundreds of commits that reach new behaviour: about 190–360 with the noise measured for Codex on go-json, about 700 for Claude. A repository rarely has that many; go-json-experiment/json gave 41 out of 145 candidates. At that size `KILL` is a guard against a large loss (a loss spread across commits is caught four times in five only from about 10–12 points on), and `NOT-PROVEN` is the expected answer, not a failure. When a loss comes as rare attempts that fail outright, the t interval calls a 3-point loss `PROVEN` about twice as often as it should, which is why `PROVEN` uses a critical value simulated from the run. With it, two attempts per arm almost never prove; on go-json's 41 commits about eight per arm would prove equal arms about three times in four, if commits do not differ in effect. One verdict per executor.

Only some mined tasks reach new behaviour (41 of 62 on go-json). Given pilot results (`--results`), `feasibility` reports that share as `reach_share` and the tasks to mine as `tasks_to_mine_if_equal`; with `--sd` alone it assumes every task reaches.

## Before spending: `viability`

`007 lab viability` says, at no model cost, whether a repository can give a decisive verdict, and why not. It reads files
only: the set (task count, declared margin), `sensitivity.json` and `sensitivity-v2.json` beside it, pilot cells of the
same set (`--results`), and `--inputs`, a JSON object of recorded numbers that wins over both (for numbers from an earlier
run of another set, or published ones). It prints JSON, or plain text with `--format text`, and exits 0 for `VIABLE`, 1
for `NOT-VIABLE` and 3 for `UNKNOWN`.

- `NOT-VIABLE` lists every reason it found. A known failure decides whatever is missing.
- `UNKNOWN` names the inputs it lacks. Missing data never reads `VIABLE`. A `sensitivity.json` that asserts `passed`
  without counting mutants is not a measure, so it counts as missing.
- `VIABLE` needs all eight inputs and no reason. It means no known reason to fail, not a promised verdict: the power is a
  normal approximation and ignores the calibrated critical value, which is stricter.

Every threshold is a gate the lab already applies or a recorded rule. The reasons follow the D-2 measurability ladder
(tasks, instrument, reference, power):

| Reason | Fires when | Source |
|---|---|---|
| `too-few-tasks` | mined tasks < 8 | `GATES["min_signal_tasks"]`: `report` reads `NO-INFORMATION` under 8 tasks that reach new behaviour |
| `load-sensitive-oracle` | `sensitivity.json` lists tasks of the set in `load_sensitive` | `run` refuses such a set |
| `oracle-blind` | `immediate`: rejected / mutants < 0.30, or fewer than 20 mutants | `GATES["min_sensitivity"]`, `GATES["min_mutants"]`: the `sensitive` gate `report` reads. The point estimate decides, as in `report`; a Clopper-Pearson interval is shown |
| `oracle-blind-v2` | `sensitivity-v2.json`, read at floor 0.30, decides `fails` | the same floor. v2 is not qualified as a gate, so only `fails` counts |
| `too-few-reaching-tasks` | tasks × the pilot's reach share < 8 | `feasibility`'s `planned_reaching`, against the same 8 |
| `prompt-insufficient` | tasks × the share of attempted tasks where one cell passed ≥ 0.8 of the new behaviour < 8 | `sufficiency`'s default threshold, against the same 8 |
| `reference-does-not-deliver` | reference-arm acceptance < 0.25 | `GATES["floor"]`: acceptance under it is not informative |
| `pays-unreachable` | for some arm, (1 − share of tasks with an accepted cell)^tasks > 0.025 | Study F reads the cost ratio R from a task bootstrap at its 97.5% point. A resample with no accepted change in an arm makes R infinite. When that happens more than 2.5% of the time, the upper bound is infinite and `PAYS` cannot be read |
| `underpowered` | power of `PROVEN` at the break-even margin < 0.50, or the margin is 0 | margin `m = min(0.20, reference acceptance × saving)` (PREREG-F; [Choosing the margin](#choosing-the-margin)); power as `feasibility` computes it, over tasks × reach share; 0.50 from the power rule of the D-2 study on the maintainer's repositories (an amendment kept in the private record) |

From pilot cells, the inputs are read as follows:

- The reach share and SD are computed as `feasibility` computes them.
- The sufficient share is computed as `sufficiency` computes it, over any valid cell.
- The saving is 1 − (median cost per valid cell at the candidate ÷ median at the reference), as PREREG-F computed it.
- The accepted-task shares are the distinct tasks with an accepted cell in each arm, over the tasks attempted.

When the set's `compare.margin` differs from the break-even margin, a note says so. `report` tests the declared margin, so a
`PAYS` reading needs the break-even margin declared before the first attempt. Cells of tasks outside the set are refused;
put those numbers in `--inputs`.

Checked against the record, from recorded numbers only:

| Case | Inputs | Verdict |
|---|---|---|
| D-2 repository A | 7 tasks; 17 of 42 planted defects rejected | `NOT-VIABLE`: `too-few-tasks` (its oracle passed) |
| D-2 repository B | 52 tasks; 92 of 310 rejected (0.2968, interval about 0.25–0.35) | `NOT-VIABLE`: `oracle-blind` |
| D-2 repository C | 24 tasks, 46 of 136 rejected. An earlier replay of the same repository: reference accepted 3 of 70, saving 0.68, SD 0.198 over 21 reaching tasks, accepted cells in 3 of 24 tasks | `NOT-VIABLE`: `reference-does-not-deliver`, `pays-unreachable`, `underpowered` (m 0.029, power 0.10) |
| Study F as planned, and on its own cells | 41 tasks, all reaching; 255 of 321 rejected; reference accepted 63 of 82 (61 of 81 in F); saving 0.75 | `VIABLE`, m 0.20, power > 0.99 |

## Choosing the margin

`compare.margin` in the set (a share, default 0.03, at most 0.2) is the loss `report` tests against; `feasibility` uses it too.
Declare it before any attempt, from the decision you face, never from the run that will be judged:

| Margin | What `PROVEN` means | Rough size at go-json's noise (Codex) |
|---|---|---|
| Break-even: reference acceptance × the saving share (about 0.10 at 36% acceptance and a 30% saving) | the lower effort does not lose what it saves | ~20 commits that reach new behaviour, 2 attempts per arm, ~US$25 |
| 0.05 | effectively the same change | ~40 such commits, 8 attempts per arm, ~US$165 |
| 0.03 | the same change within research precision | ~55–145 such commits, 8 attempts per arm: several repositories |

Sizes are per executor. Claude Opus 5.5 on the same go-json commits had about five times Codex's between-commit spread: break-even
at 2 attempts per arm needs about 40 commits for 80% power when the arms are equal
([result](../evidence/go-json-claude-20261107/RESULT-CLAUDE.md)).

Take the break-even inputs from a pilot or from published savings, never from the confirmatory attempts. Break-even is computed on acceptance while the verdict reads the reachable scale, so it is an approximation of the economic question, not the question itself. The sizes,
and those `feasibility` reports, are normal approximations: they ignore the calibrated critical value (stricter than 1.96) and the
8-task minimum, so read them as lower bounds. `report` reads the margin from the set each time it runs: keep the set unchanged
after the first attempt (hash it, as the pre-registrations here do). For a confirmatory run, freeze the reach set beforehand
(`reach=`); the calibration's error rates come from simulations that take the reach set as given. `report` writes `report.md`,
the verdict in plain words at the declared margin.

## Limits

Execution and acceptance timeouts must be positive and at most 2,147,483 seconds,
the portable subprocess wait range. The standalone CLI accepts whole minutes,
up to 35,791. Invalid limits are refused before execution.

A verdict holds for the specification form the set used (by default the commit message plus a contract of names its tests
pin) and is not a claim about other forms, such as written signatures or a skeleton. Filters that keep well-specified tasks
(`min_message`, the reach set, `sufficiency`) select tasks where the specification is already enough, which pulls a verdict
toward "equal". Commit messages often under-specify what their tests pin. A generated contract states names and strings, never behaviour, but tests can stay out of reach. Tests that fail in every cell carry no signal and leave the metric.

`mine` keeps a commit only if its reference patch also passes the way a candidate is graded: applied to the base snapshot,
behind the same reset of test files (`reference-fails-as-candidate` otherwise, or `next-reference-fails-as-candidate` for the
paired next change; the check runs once, under the mining load, with no retry alone). A commit that renames or deletes a Go test file
passed at its own tree while no patch could pass in a cell. `lab_accept.py` grades without `ACCEPT_REPORT` too: the exit code is
the verdict and the report is optional, so a caller that forgets the variable no longer reads a harness error as a rejection. It
exits 2, not 1, when the grader itself fails, and `mine` drops such a commit as `AcceptanceHarnessError`, not as a reference
that fails. It exits 3, with no report, when a suite command does not finish in time (800 s per command, 860 s for all the
commands of one grade): that is a rejection of the candidate. A suite result file that is cut, malformed or over 64 MiB, or a
command the candidate's tree made impossible to start, grades as no result (a rejection); under `--collect` it fails, and
`mine` drops the commit. The Go adapter keeps at most 64 MiB of `go test -json` output, so a repository whose stream is
larger cannot be mined. A task mined since 1.10.1 carries `acceptance_exit_contract: "lab-accept-v1"`, which requires
exactly one acceptance command and `acceptance_timeout_s` of at least 900, and under which a cell reads 0 as accepted, 1
and 3 as rejected, and any other exit as an invalid cell (`acceptance-harness-error`). The suite shares the grader's user
and process group, so a suite that kills the grader still makes an invalid cell; a shared memory limit or a full disk does
the same when it hits the grader, and reads as a rejection when it hits the suite. Exit 1 is not proof that a grade was
made. The grader needs a POSIX host. A mined task embeds its grader: sets mined before 1.10.1 keep the old one, and its
reading, until they are mined again.

A snapshot is not read isolation. A mined public repository may also sit on the host as an installed copy (a plugin cache, a
module cache, a vendored checkout) that already holds the commit a task asks for, and an agent that searches outside its
workspace can find the answer there. Before a study, deny the agent read access to such copies or mine a repository the host
does not carry; a cell that read one is contaminated, not a result. [Read isolation](#read-isolation-and-contamination) covers
the plugin and skill copies 007 knows of; a module cache, a vendored checkout or a clone elsewhere on the host is not on its list.

Durability is harder than it looks. In the repository where this was built, five instruments failed their own sensitivity gates, so durability was not testable there. Proving a binary outcome non-inferior at -5 points needs 235 to 1039 changes per arm, depending on the base rate. Treat `durable` as unproven unless `report` says otherwise.

## Published replay evidence

The Codex top-up and Claude public replay reports retain their pre-registered margins, invalid-attempt accounting, estimands and full statistical readings. The short result table in the README is an entry point to these frozen records.

- [Codex go-json top-up, margin 3 pp](../evidence/go-json-topup-20261106/RESULT-TOPUP.md).
- [Claude go-json replay, margin 10 pp](../evidence/go-json-claude-20261107/RESULT-CLAUDE.md).
- [Study F, Claude go-json, margin 20 pp](../evidence/go-json-claude-f-20261112/RESULT-F.md). Its arms were not blind and its
  interval covers about 92%: see [the errata](evidence.md#errata-and-limits-published-for-1110).

The detailed planning assumptions and earlier README evidence table are preserved in the [immutable public README checkpoint](https://github.com/marcuscavalcanti/007-framework/blob/1e9f3c1a85e10e4508ccd94c9d44a74cbeec6a77/README.md#current-thesis-minimum-sufficient-effort-november-2026). Those estimates keep their original experiment scope. Choosing the margin and evaluating feasibility above define the decision for a new run.
