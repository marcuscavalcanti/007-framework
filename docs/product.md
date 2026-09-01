# Product

## Problem

Coding agents optimize for producing an answer. Engineering teams need a
different outcome: a correct, reviewable change that survives use without
repeated correction. Larger models, longer prompts, and more agents can increase
cost and coordination while leaving proof and rework invisible.

## Product thesis

Reliability improves when the workflow treats context, routing, implementation,
verification, and learning as one measured loop:

- choose the cheapest verified route likely to pass;
- minimize changed surface and reuse existing control paths;
- declare proof before implementation;
- gate on executable outcomes;
- preserve missing evidence as uncertainty;
- change doctrine only when a controlled test supports it.

## Users

- individual developers using terminal or IDE coding agents;
- tech leads standardizing AI-assisted delivery across repositories;
- platform teams comparing models or policies without binding to one provider;
- researchers running task-level causal evaluations on real code history.

## Jobs to be done

1. Route routine work cheaply without sending risky work to an incapable model.
2. Prevent speculative code and unrelated refactors.
3. Know exactly what was tested and what remains unknown.
4. Measure correction pressure instead of celebrating generated lines.
5. Test one workflow hypothesis without exposing hidden acceptance criteria.

## Success metrics

- reliable first-pass rate: accepted on the first pass and without a known
  seven-day escape;
- corrective touch rate at 7 and 30 days;
- repair rounds and escaped regressions;
- cost per reliable outcome, including failed and blocked attempts;
- observation coverage from task start to terminal receipt;
- percentage of outcomes with complete, non-invented telemetry and cost.
- reliable outcomes per USD and wall time per reliable outcome, counting every
  failed attempt in the cost and time paid.

## Non-goals for V1

- autonomous production deployment or credential management;
- a workflow server, model gateway, IDE, or agent runtime;
- guaranteed support for every provider;
- automatic doctrine self-modification;
- claims of universal quality or productivity superiority.

## Adoption path

Install the skill and `007` command, run `007 init` once in each Git project,
then run `007 begin --repo .` before scoped work and `007 record` at its terminal
outcome. Starts live under `.007/tasks`; receipts live under `.007/receipts` and
require explicit cost accounting. The
global local registry lets `007 dashboard` reconcile all projects with the
aggregate view. Adopt causal replay only for a concrete mechanism whose failure
matters.

Hosts may replace the two manual lifecycle calls with `007 run`, which wraps an
arbitrary command and requires its adapter to emit the same normalized receipt.
The wrapper is provider-neutral and does not store raw model output.

The dashboard is observational: it measures accepted outcomes, repair pressure,
touch-rate, escapes, telemetry, and cost. It does not turn those operational
signals into causal proof. Release-level causal evidence remains a separate,
frozen OLD×NEW experiment.

Routing is also deliberately small: v1.4 offers a deterministic experimental
repository-local recommendation over user-configured CLIs and mature receipts. It is not a
certified policy engine, does not serve automatically, and does not establish
cross-project transfer. 007 is not a model gateway and does not switch executors
inside an attempt.

Before receipts exist, a separate local-activity lane can already show Codex,
Claude, Kimi, and Gemini sessions, served routes, and 24-hour token deltas.
Provider-reported terminal cost is shown when available; external rate-card
estimates remain optional diagnostics. This is operational visibility only; it
never creates an accepted or reliable outcome.

The start/receipt pair makes missing terminal outcomes visible. Work performed
without `007 begin` remains outside the observable denominator and is shown as
legacy/unstarted data rather than silently treated as complete.
