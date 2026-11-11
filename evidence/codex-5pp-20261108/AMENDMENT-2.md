# Amendment 2 to PREREG-PILOT (2026-11-11)

This amends [PREREG-PILOT.md](PREREG-PILOT.md) (SHA-256 `a55526f3…a4f5b2`) and [AMENDMENT-1.md](AMENDMENT-1.md) (SHA-256
`163d74a6…789b21`). Neither file is edited; their hashes in `SHA256SUMS` are unchanged. Where this amendment differs from them, it
applies.

It was written and pushed before three things: the corrected planted-defect gate below was re-run, any pilot set was built, and
any pilot attempt was dispatched.

Causes:
- an adversarial validation of the post-1.7.0 plan by Claude Fable 5.2 at `xhigh` effort, which found that the published pilot
  scripts cannot carry out Amendment 1 as written;
- the maintainer's decision to follow its recommendations.

## What had been executed and observed before this amendment
- **Mining round 2 and the planted-defect checks:**
  - they finished on 2026-11-10 at 16:27:54Z, every step exit 0, with no model;
  - the repository code was the maintainer's local commit `46dd81f`. It contains the miner fix `7129082`, but not the corrected gate
    of 1.6.0 (a rejected mutant counts only where its task's reference passes) nor the 1.6.2 fixes F01/F02.

  Observed per repository:

  | Repository | Tasks | Controls conformant | Recorded immediate sensitivity (old gate) |
  |---|---|---|---|
  | BurntSushi/toml | 25 | 25 | 78/119 = 65.5% |
  | traefik/yaegi | 13 | 7 | 46/68 = 67.6% |
  | pelletier/go-toml | 13 | 13 | 33/48 = 68.8% |
  | pierrec/lz4 | 11 | 11 | 50/58 = 86.2% |
  | klauspost/compress | 24 | 23 | 69/103 = 67.0% |

  "Conformant" means the reference passed its own oracle and was not contradicted by the next change's oracle. The recorded check
  keeps no rows, so which controls failed their first oracle (what the corrected gate uses) was not observed.
- Every mined task embeds the same evaluator, `lab_accept.py` SHA-256 `362f40c7…83c6be`. It is byte-identical to the evaluator of
  the go-json top-up tasks.
- **Not executed:**
  - no corrected gate;
  - no pilot set;
  - no pilot attempt;
  - no paid call for this study;
  - no arm outcome observed.

## Changes

**1. Code pinned to v1.7.0.**
- Before: `run_pilot.sh` ran `../../repo` (commit `46dd81f`), and the agent command's native runner came from the same checkout.
- After: the pilot uses the 1.7.0 distribution (commit `21ba2ff`, archive SHA-256 `3e9b82bb…d271`) for every step:
  - the runner;
  - grading;
  - the native runner inside the agent command;
  - the gate re-run;
  - the freeze.

  `pinned.py` checks every file of that distribution against its `evidence/v1.7.0/manifest.sha256` before each step, and refuses to
  run if a 007 module was loaded from anywhere else.
- Unchanged: the Codex CLI (0.160.1, pinned path), the model, the efforts, the CLI flags, the sandbox and the price table.
- The run log records first: the code commit, the pilot set's SHA-256, the Codex CLI version and the Python version.

This carries out Amendment 1 change 3: F02 is merged, so it is used.

**2. Evaluator.**
- The gate re-run and pilot grading use the evaluator embedded in each task (`362f40c7…`), keeping the top-up's grading logic as
  Amendment 1 change 3 requires.
- The 1.7.0 evaluator (with F01) is used only in the confirmatory robustness re-grade that Amendment 1 already requires.

**3. Corrected gate re-run (Amendment 1 change 1).**
- **Which repositories:** traefik/yaegi and klauspost/compress, the two whose recorded check had a non-conformant control. In the
  other three every control was conformant, so the corrected gate equals the recorded one.
- **How:** `gate_rerun.py`, with:
  - the pinned code and the embedded evaluator;
  - the recorded check's seed and mutant sampling;
  - 3 parallel jobs;
  - no model;
  - every row retained in `gate/<repo>.json`.
- **Consistency check before use:** the old rule, recomputed from the new rows, must reproduce the recorded counts (yaegi 46/68,
  compress 69/103). If it does not, nothing is built and the next step goes back to the maintainer.
- **Serial re-run:** every control whose reference failed its first oracle, or did not apply, is re-run once, alone.
- **Pooling:** a repository is pooled at a corrected immediate sensitivity of at least 30%, as before. Its rate is recorded for the
  Amendment 1 60% check.

**4. Tasks whose reference fails.** The rule is fixed now, at task level and blind to arms.
- **Definition:** a task is *reference-failed* if its reference patch does not apply, or fails its first oracle, in either the
  parallel or the serial re-run of change 3.
- **Attempts:** reference-failed tasks stay in the pilot and get attempts, keeping PREREG's "every pooled task".
- **Primary freeze:** frozen reach, noise, floor, `n80` and GO / NO-GO use only the other tasks. If GO, the confirmatory reach set
  comes from this primary freeze.
- **Secondary freeze:** on every pooled task. It is reported and never decides.
- **Next-change oracle:** a failure there does not count, because the pilot does not measure durability.

**5. The floor as written.**
- Before: `freeze_pilot.py` used the unrounded go-json value, 2.197566…, while PREREG writes `max(2.198, c_pilot)`.
- After: `freeze_pilot_v2.py` uses 2.198 as written. It is the larger value, so `n80` can only rise.

**6. Cost.**
- Expected cost: 4 × pooled tasks × US$0.264. With at most 86 tasks that is US$90.82, under the US$150 cap.
- Amendment 1's subset therefore does not apply. The build refuses to proceed if the expected cost exceeds the cap.

**7. A cell over the per-cell limit.**
- `--stop-usd 2` is unchanged. A cell reporting more than US$2 stops the run, as do the US$150 cap, the invalid budget and an
  unavailable cost.
- Any such stop is PREREG's early stop: the pilot is reported, nothing is frozen, and the next step goes back to the maintainer.

**8. Dry run before dispatch, with no model.**
- **What:** `dry_run.py` runs the built set on the pinned runner, with a fake Codex CLI that applies each task's reference patch.
  It covers 2 tasks per pooled repository and 2 attempts per arm. It then runs `freeze_pilot_v2.py` on those cells.
- **Pass condition:** the pilot is dispatched only if every dry-run cell is valid and the freeze completes.
- **Outputs:** they stay under `dryrun/` and never enter the pilot.

**9. Scripts.**
- New: `pinned.py`, `gate_rerun.py`, `build_pilot_v2.py`, `dry_run.py`, `run_pilot_v2.sh` and `freeze_pilot_v2.py`. Like the
  originals, they are byte copies of the ones used, and are hashed in `SHA256SUMS`.
- The original scripts stay as published.

## What does not change
- The arms, attempts per arm, seed and margin.
- The primary outcome, the two looks, and the KILL / FUTILITY / PROVEN rules.
- The `n80` formula and the GO / NO-GO rule.
- The US$150 cap and the invalid stop at 10% of cells.
- Pilot attempts never enter the confirmatory analysis.
- The confirmatory run still needs its own approval with its cost.
- No repository is added and none is mined again: re-mining after the yields were seen would redraw the task set.
