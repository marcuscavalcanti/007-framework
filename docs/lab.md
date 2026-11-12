# `007 lab`: what a lower effort saves and risks in your repository

`007 lab` replays your own commits at two efforts, without a screen, with any agent and any test runner. The source repository is only read.

```bash
007 lab mine --config lab.json --out lab
007 lab sensitivity --set lab/replay-set.json
007 lab feasibility --set lab/replay-set.json --sd 0.23
007 lab run --set lab/replay-set.json --out results --replicates 3 --max-calls 144 --max-usd 150 --jobs 6
007 lab report --set lab/replay-set.json --results results
```

Start from [`examples/lab.example.json`](../examples/lab.example.json). Only `run` calls a model. It dispatches a cell only while the spend so far plus a `--stop-usd` reserve for each cell in flight stays under `--max-usd`; a cell that costs more than its reserve can push the total past `--max-usd`, so set `--stop-usd` at or above the costliest expected attempt. It stops when a valid cell reports no cost, on a cell above `--stop-usd`, and once `--max-invalid` cells (default 3) are invalid; an invalid cell without a cost is charged its `--stop-usd` reserve. It resumes finished work and never retries a cell. Before its first dispatch it seals `run-manifest.json` in `--out`: the set (arms and their order, agent command, tasks with their prompts, bases and oracle hashes), the agent command's program (its first word, through `PATH`) and the absolute files it names (through symlinks), this 007 and the Python version; every dispatch in `dispatch.jsonl` names that manifest's digest. Each time the run starts or resumes it checks them: anything changed stops it with `manifest-mismatch`, naming what changed; restoring it makes the run resumable. A manifest that is unreadable, or missing after a dispatch named it, stops it with `manifest-unreadable` or `manifest-missing`; only a directory whose dispatches name no manifest (one from before 1.8) is sealed late. A relative path in the agent command resolves inside the task's workspace, which the set's base commit fixes; a later `PATH` lookup (`env agent`) and anything the program launches, an absolute file the attempts themselves rewrite (a log), and the compilers and test runners the oracle calls are not sealed; `report` says when the program itself was not sealed. The manifest guards against accidents, not tampering, and it records absolute paths: check it before publishing a results directory. At a planned pause (`call-budget`), `--replicates`, `--max-calls`, `--max-usd`, `--jobs` and `--max-invalid` can change; any other stop is final. `--stop-usd` reprices the reserve charged to earlier invalid cells without a cost, and `timeout_s` (Python API) is not sealed. The set's `compare` block is not sealed: a change is reported in `run_manifest` and in the printed verdict (`compare_changed_after_seal`), and it breaks the declared-margin rule below, so it serves an exploratory reading only. `chain` refuses a `compare` moved since stage 1 was sealed (its reference picks stage 2's arm), and refuses to overwrite a different chain set in its directory. `report` and `chain` refuse results sealed with another set or under another manifest; `report` names the binding in `run_manifest` (`sealed`, `sealed-late`, or `absent`) and says if the comparison or margin changed after the seal. With `--next-results` it requires stage 2 to be the chain of these very results at the reference arm. Its `arm_accounting` gives, per arm, the fate of every planned cell (every task at the most replicates any attempted or finished cell reached): never dispatched, attempted without a result (a dispatch or receipt with no result), invalid by `failure_class`, valid and accepted, with `history` saying whether the dispatch ledger was complete. `report` leaves invalid cells out and names them in `excluded_invalid`; a cell whose test report cannot be read counts as no test passing and is named in `unreadable_outcomes`. `mine` skips a commit with more hidden tests than the acceptance reader takes: 1,999, since the reader's 2,000 outcomes include `__module__`.

- **Agents** are an argv template (`agent_command`) that writes a runner receipt.
- **Tests** are an adapter: `node`, `pytest`, `unittest`, `go`, or `custom`, whose command writes `{test id: pass|fail|skip}` to `$LAB_RAW_REPORT`. With `go`, the agent's own `*_test.go` files go back to base before grading, so a test name it redeclares cannot break a package. A test whose `unittest` class or module, or whose `go` package, fails outside any test (a teardown error, `TestMain`'s exit, a panic after the test returned) reads `error`, not `pass`; a test that fails on its own owns its package's failure, so a test already red at base stays outside the grade.
- **Parallelism** shortens the run; the budget reserves `--stop-usd` for each cell in flight.

Acceptance execution uses the same configured `acceptance_sandbox` argv prefix and `acceptance_env` across replay cells,
lab collection and `admit --recheck`. An explicit environment (including `{}`) is exact apart from the controller's
`ACCEPT_REPORT`; omitted or null retains host inheritance for compatibility. Command prefixes are configured wrappers,
not proof of an operating-system sandbox. Cells identify their boundary as `host-unqualified` or
`wrapper-configured-unverified` and their environment as inherited or explicit. Configure containment before executing
untrusted candidates; no provider-specific mechanism is required by this policy. Existing frozen experiments keep their
original configuration and embedded acceptance adapter.

## What the report can say

| Claim | Gate |
|---|---|
| Less time | At least 25% less agent time per accepted change; fewer accepted changes raise that time, and whether the changes are the same is the next row |
| The same change | `same_change_reachable`: per task, the difference between the arms' pass rates on reachable behaviours (hidden tests red at base that some cell of the task passes), with a 95% t interval over tasks. `KILL` if the whole interval is below minus the declared margin (`compare.margin`, 3 points by default). `PROVEN` if `(mean + margin) / standard error` beats `proven_critical`: the 97.5% point of that statistic when the run's own cells are redrawn with a loss of the margin injected as whole failed attempts, so such a loss is called `PROVEN` about 2.5% of the time (in go-json simulations at 3 points: under 1% at two attempts per arm and 2.6–2.8% at about eight, where the plain t interval reached 5.6% and 3.4%; the report shows the plain rate as `t_false_proven`). A planned run can also fix a floor for the critical value from earlier attempts (`proven_critical(..., attempts=)`) and a frozen reach set (`reach=`). Otherwise `NOT-PROVEN`; under 8 tasks, `NO-INFORMATION`. A `KILL` here kills the thesis. The older point-estimate rule (tests that split a task's cells, -5 points) is kept only as `unseen_behaviour.superseded_verdict` |
| Durable | The change survives the next real change to the same code; requires `require_next` and `chain` |

Gates are fixed in code. If the oracle cannot reject planted defects, the verdict is `NO-INFORMATION`, never a pass.

## What one repository can answer

The savings settle fast: reasoning tokens, agent time and estimated cost per attempt need a few dozen commits. The same change does not. With the attempts each run had (about two per arm for Codex, three for Claude), a 3-point verdict needs hundreds of commits that reach new behaviour: about 190–360 with the noise measured for Codex on go-json, about 700 for Claude. A repository rarely has that many; go-json-experiment/json gave 41 out of 145 candidates. At that size `KILL` is a guard against a large loss (a loss spread across commits is caught four times in five only from about 10–12 points on), and `NOT-PROVEN` is the expected answer, not a failure. When a loss comes as rare attempts that fail outright, the t interval calls a 3-point loss `PROVEN` about twice as often as it should, which is why `PROVEN` uses a critical value simulated from the run. With it, two attempts per arm almost never prove; on go-json's 41 commits about eight per arm would prove equal arms about three times in four, if commits do not differ in effect. One verdict per executor.

Only some mined tasks reach new behaviour (41 of 62 on go-json). Given pilot results (`--results`), `feasibility` reports that share as `reach_share` and the tasks to mine as `tasks_to_mine_if_equal`; with `--sd` alone it assumes every task reaches.

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

Durability is harder than it looks. In the repository where this was built, five instruments failed their own sensitivity gates, so durability was not testable there. Proving a binary outcome non-inferior at -5 points needs 235 to 1039 changes per arm, depending on the base rate. Treat `durable` as unproven unless `report` says otherwise.

## Published replay evidence

The Codex top-up and Claude public replay reports retain their pre-registered margins, invalid-attempt accounting, estimands and full statistical readings. The short result table in the README is an entry point to these frozen records.

- [Codex go-json top-up, margin 3 pp](../evidence/go-json-topup-20261106/RESULT-TOPUP.md).
- [Claude go-json replay, margin 10 pp](../evidence/go-json-claude-20261107/RESULT-CLAUDE.md).

The detailed planning assumptions and earlier README evidence table are preserved in the [immutable public README checkpoint](https://github.com/marcuscavalcanti/007-framework/blob/1e9f3c1a85e10e4508ccd94c9d44a74cbeec6a77/README.md#current-thesis-minimum-sufficient-effort-november-2026). Those estimates keep their original experiment scope. Choosing the margin and evaluating feasibility above define the decision for a new run.
