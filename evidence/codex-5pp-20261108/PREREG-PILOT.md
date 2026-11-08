# Pre-registration: Codex `medium` vs `high` pilot on pooled Go repositories, margin 5 points (2026-11-08)

Written and hashed before any paid attempt of this pilot. `SHA256SUMS` binds the scripts next to this file, which are byte
copies of the ones the pilot uses.

## Why a pilot
The next confirmatory test asks whether Codex `gpt-6.1-sol` at `medium` stays within **5 points** of `high` on commits that
reach new behaviour, pooled over several public Go repositories that 007 has never replayed. One verdict for the executor. On
go-json, 41 such commits came from 145 candidates; no single other repository triaged so far yields enough. These repositories
have no earlier attempts, so nothing fixes their reach set or their noise yet. This pilot fixes both before the confirmatory
attempts. It decides nothing about the thesis.

## Repositories
BurntSushi/toml, traefik/yaegi, pelletier/go-toml, pierrec/lz4, klauspost/compress.
- **Chosen** by metadata triage before any mining: Go modules with no dependencies (so every commit builds offline), and many
  commits whose message has at least 200 characters.
- **Mined** with the go-json rules and the miner fixed in this change (a commit that deletes a test file is no longer dropped).
- **Gate:** a repository enters only if its planted-defect check rejects at least 30% of reference patches with one hunk removed
  (go-json: 79%).
- **Dropped before this pilot:** golang/sync, golang/time and google/go-cmp yielded 3, 1 and 2 tasks.

## Pilot design
- **Arms:** the Codex top-up's agent command, settings and grading ([../go-json-topup-20261106](../go-json-topup-20261106/)).
- **Attempts:** 2 per arm on every pooled task, one block, seed 20261110.
- **Cap:** US$150 at list price, an estimate rather than an invoice.
  - Invalid cells: a stop after 10% of cells.
  - Never redone.
- **Stops early** (cap or invalid budget): the pilot is reported, nothing is frozen, and the next step goes back to Marcus.

## What the pilot fixes (`freeze_pilot.py`)
- **Frozen reach:**
  - per task, the hidden tests red at base that some valid pilot attempt passed, in either arm;
  - **reaching tasks** are those with a non-empty set.
- **Noise on that reach:**
  - σ², within arm per attempt;
  - τ², by moments and by odd/even replicate covariance.
- **Critical floor:** `max(2.198, c_pilot)`.
  - 2.198 is the value simulated from go-json's Codex attempts at 5 points and 8 attempts per arm, 100,000 draws.
  - `c_pilot` is the same quantity from the pilot attempts.
- **Go / no-go:** `n80 = (τ² + σ²/4) × ((floor + 0.8416) / 0.05)²`, with τ² the larger estimate.
  - This is the number of reaching tasks for 80% power to prove 5 points at 8 attempts per arm when the arms are equal.
  - **GO** if the reaching tasks number at least `n80`. **NO-GO** otherwise: no confirmatory run is proposed, and the 5-point test
    needs more repositories.
- **Never deciding:**
  - The pilot's mean difference is reported, and it never enters go / no-go.
  - Pilot attempts never enter the confirmatory analysis.

## Confirmatory rules, fixed now
If GO, a confirmatory pre-registration is submitted for approval with its cost. It keeps these rules:
- **Attempts:** fresh, 8 per arm on the reaching tasks.
- **Sequence:** the top-up's two looks:
  - manipulation: median reasoning tokens lower at `medium`;
  - less waiting: median agent-time saving ≥ 25%, with a task-bootstrap interval above 0.
- **Primary:** per-task `medium − high` pass share on the frozen reach, readings P and B; the worse decides.
  - **Look 1** (replicates 1–4):
    - KILL if a reading's 95% t interval lies wholly below −5 points;
    - FUTILITY if `(mean + 5 points) / se < 0.5`;
    - never PROVEN.
  - **Look 2** (replicates 1–8):
    - PROVEN if, in both readings, `(mean + 5 points) / se` exceeds `max(floor, c)`, where `c` is the value simulated from the
      confirmatory attempts;
    - KILL as at look 1;
    - otherwise NOT-PROVEN.
- **Secondary, never deciding:**
  - each repository alone;
  - acceptance on the tasks any attempt solved;
  - τ² bounds;
  - invalid attempts per arm;
  - cost.

## Limits stated in advance
- **Contamination:** public commits, so the model may have seen them; both arms alike.
- **Scope:**
  - Go only;
  - one executor;
  - repositories chosen for offline builds and long commit messages, not at random.
- **Measurement:** served effort is not reported; costs are list-price estimates.
