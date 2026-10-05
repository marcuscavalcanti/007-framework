# v1.5.0 — local stable candidate, not release approval

Base RC: d2cd9da1b10f3f5a7c90dbafd7bac0a0718e70b8. Runtime is byte-identical
to that RC and a3012ee28f160d63a404c00c8bb4d372fe807279. Only version metadata,
documentation, a new manifest and package checks change; no dependency is added.
The [qualification record](qualification.json) binds observed RC CI provenance
and unfulfilled approval gates. manifest.sha256 covers these candidate bytes,
excluding itself. Historical manifests and causal artifacts remain unchanged.

## Observed proof and limits

RC run 37366568729 passed compile and 148 tests on Linux Python 3.11/3.13
in attempt 2, and Python 3.12 in attempt 3. The release-manifest CI step was
skipped on that branch run. This is not final-stable CI or tag verification.
Local final-candidate checks are captured separately, not invented here.
Two RC reviews and one prepared-stable review returned reject. Their original
final answers and counterproofs are in the [public review record](adversarial-review.json),
bound by the qualification record and this manifest. The missing-field and
unreported-local-test claims were refuted by exact context/source bytes and
executable checks; no approve verdict is inferred. The origin of the contradictory
model reading is unknown, and model-side receipt is not attested. This later
provenance-only overlay was not externally reviewed.

Earlier CI jobs were cancelled before tests: all versions in attempt 1 and
Python 3.12 in attempt 2 had runner_id=0 and zero steps. Native observations
reported hosted-runner acquisition failure, not a failing or flaky test. The
qualification record retains those attempts; provider root cause is unknown.

The preserved [causal contrast](../v1.5.0-rc.2/release-evidence.md) supports
the first-signal latch mechanism only: CURRENT target 3/3 passes, MUTANT target
3/3 fails with the recorded assertion, positive controls 6/6 pass, zero retries.
Historical ROI remains task-local. Neither proves universal review replacement,
cross-platform causality, D7/D30 durability or deterministic scheduler timing.

For manual reproduction, verify this stable manifest first. Use two disposable
copies; run `git init -q` inside MUTANT before the documented `git apply`
commands so an ancestor Git repository cannot capture patch resolution.
Never apply the mutant to a live project or count unrelated errors as RED.

## Remaining release gates

- Review explicit public Git author/committer identity before any new commit;
  the RC used inferred host identity, not a ratified public identity.
- Historical v1.4 manifest checks require Git commit
  301b1aa30522e87a486088c79687a93d95d2aa4a. The existing test returns early
  when it is absent; a Git-free archive cannot prove that historical gate.
- Obtain required independent approval; verify exact final committed bytes,
  supported-version CI and release manifest. Local tests are not those gates.
- Obtain publication authorization and verify tag/commit/artifact read-back.
  No commit, push, tag, installation or publication is performed by preparation.
- Any change to final publication wording or evidence changes the manifest;
  regenerate it and verify the final committed bytes before tagging.
