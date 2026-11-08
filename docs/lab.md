# `007 lab`: what a lower effort saves and risks in your repository

`007 lab` replays your own commits at two efforts, without a screen, with any agent and any test runner. The source repository is only read.

```bash
007 lab mine --config lab.json --out lab
007 lab sensitivity --set lab/replay-set.json
007 lab feasibility --set lab/replay-set.json --sd 0.23
007 lab run --set lab/replay-set.json --out results --replicates 3 --max-calls 144 --max-usd 150 --jobs 6
007 lab report --set lab/replay-set.json --results results
```

Start from [`examples/lab.example.json`](../examples/lab.example.json). Only `run` calls a model. It stops before passing `--max-usd`, when a valid cell reports no cost, on a cell above `--stop-usd`, and once `--max-invalid` cells (default 3) are invalid; an invalid cell without a cost is charged its `--stop-usd` reserve. It resumes finished work and never retries a cell. `report` leaves invalid cells out and names them in `excluded_invalid`; a cell whose test report cannot be read counts as no test passing and is named in `unreadable_outcomes`. `mine` skips a commit with more hidden tests than the acceptance reader takes (2,000).

- **Agents** are an argv template (`agent_command`) that writes a runner receipt.
- **Tests** are an adapter: `node`, `pytest`, `unittest`, `go`, or `custom`, whose command writes `{test id: pass|fail|skip}` to `$LAB_RAW_REPORT`. With `go`, the agent's own `*_test.go` files go back to base before grading, so a test name it redeclares cannot break a package.
- **Parallelism** shortens the run; the budget reserves `--stop-usd` for each cell in flight.

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

Take the break-even inputs from a pilot or from published savings, never from the confirmatory attempts. Break-even is computed on acceptance while the verdict reads the reachable scale, so it is an approximation of the economic question, not the question itself. The sizes are normal
approximations; the calibrated `PROVEN` rule is stricter, so run `feasibility` on your own pilot. `report` writes `report.md`,
the verdict in plain words at the declared margin.

## Limits

Commit messages often under-specify what their tests pin. A generated contract states names and strings, never behaviour, but tests can stay out of reach. Tests that fail in every cell carry no signal and leave the metric.

Durability is harder than it looks. In the repository where this was built, five instruments failed their own sensitivity gates, so durability was not testable there. Proving a binary outcome non-inferior at -5 points needs 235 to 1039 changes per arm, depending on the base rate. Treat `durable` as unproven unless `report` says otherwise.
