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

- first-pass accepted rate;
- corrective touch rate at 7 and 30 days;
- repair rounds and escaped regressions;
- cost and wall time per accepted task;
- percentage of outcomes with complete, non-invented telemetry.

## Non-goals for V1

- autonomous production deployment or credential management;
- a workflow server, model gateway, IDE, or agent runtime;
- guaranteed support for every provider;
- automatic doctrine self-modification;
- claims of universal quality or productivity superiority.

## Adoption path

Install the skill, use it on scoped work, keep the outcome block, and add
machine-readable receipts only where the repository already has a receipt
location. After enough attributable history exists, run the included reports.
Adopt causal replay only for a concrete mechanism whose failure matters.
