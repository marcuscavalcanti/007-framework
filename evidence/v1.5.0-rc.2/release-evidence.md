# v1.5.0-rc.2 — candidate evidence, not release approval

Runtime base: a3012ee28f160d63a404c00c8bb4d372fe807279. All execution scripts
are byte-identical to that source. This amendment changes documentation,
version metadata, public observations and package tests; no dependency is added.

## Observed mechanism and provenance

mechanism-protocol.json sanitizes the original preregistered source protocol,
SHA
4c7f29fd0317be901596549f4e33075d047c63a273cb908246ca7094f1853a4d.
mechanism-result.json preserves every cell and original log digests from source
result b919d48ab9b263c9a5010f749483e9bd7fec79457c182d667a360452deb3eb66.
Private capture paths and interpreter argv are omitted. The exact
[mutant patch](mechanism-mutant.patch) and resulting mutant source SHA are now
bound in the public protocol. Their publication metadata was added after the
original run, not retroactively preregistered. No independent timestamp
attestation is claimed.

Same target/control tests, source and Python 3.14.7/macOS arm64 host; three paired
replicates, seed 4007, zero retries. MUTANT changes exactly one guard:
`if shutdown_signal is None:` to `if True:`. CURRENT passes the target 3/3;
MUTANT fails 3/3 with exactly one assertion failure and no error. The observed
message is `AssertionError: ProcessLookupError not raised : executor survived
shutdown cleanup`. Allowed control passes 3/3 in each arm. All 12 outcomes match.
The added per-cell signature, assertion message and failure/error counts were
read from original hash-verified logs, not inferred from exit code alone.
No model calls; cost is unmeasured, not zero. This is local mechanism evidence,
not a historical OLD comparison, economic ROI or a full-framework causal proof.
Verdicts reproduce in the observed conditions; scheduling and wall time are not
mathematically deterministic. A public log digest does not provide its raw log.

## Reproduce the focal contrast

Use two disposable copies of the manifest-verified source, CURRENT and MUTANT,
never a live project. Verify the source manifest in CURRENT first. The original
pair order is in `realized_pair_order` in mechanism-protocol.json; run the target
and then control in each listed arm. Record interpreter, OS, exit, assertion
message and log digests; do not retry mismatches or count unrelated errors as
expected failures.

Apply the public patch only to MUTANT:

```sh
git -C "$MUTANT" apply --check "$CURRENT/evidence/v1.5.0-rc.2/mechanism-mutant.patch"
git -C "$MUTANT" apply "$CURRENT/evidence/v1.5.0-rc.2/mechanism-mutant.patch"
```

From `tests/` in each arm, run:

```sh
python3 -B -m unittest test_dashboard.DashboardTests.test_run_executor_shutdown_cleanup_keeps_first_signal_and_reports_non_gone -v
python3 -B -m unittest test_dashboard.DashboardTests.test_run_records_allowed_action_as_controlled -v
```

Expected: target exit 0 in CURRENT, exit 1 with the exact assertion above and
`FAILED (failures=1)` in MUTANT; control exit 0 in both. Compare the resulting
mutant source SHA with `mutant_source_sha256`. MUTANT intentionally violates the
source manifest and must never be integrated or treated as a release candidate.

## Compatibility since 1.4.0

Malformed/non-finite receipt metrics are rejected. After normal executor wait,
unconfirmed cleanup returns exit `2`, persists no terminal receipt and leaves
the start open; successful checks or executor exit alone do not override this.
Unavailable cost needs explicit project opt-in and all null-cost fields; it is
not priced economic evidence. Priced receipt semantics remain unchanged. Full
[contract and signal limits](../../references/receipt-schema.md) remain in the
receipt reference; this RC adds no execution behavior.

## Qualification and release boundary

The runtime base passed 144/144 tests in three Python 3.14.7 runs and one local
Python 3.13.15 run, with compile and CLI help checks. Those observations qualify
the runtime source, not every RC packaging byte. New candidate native checks
and a public-patch-based focal rerun are captured separately by the release
coordinator, not substituted for the historical public result above.
manifest.sha256 binds these candidate bytes (excluding the manifest itself).
Stable promotion needs its own manifest.

The independent review accepted rc.1 for local integration with caveats; it does
not review or approve these rc.2 bytes. Independent hash-bound review is pending.
Python 3.11/3.12 and the
remote 3.11/3.12/3.13 CI matrix for the final SHA are unobserved. No stable tag,
push or publication is claimed. Historical release manifests/reviews remain
unchanged and do not substitute for approval of this candidate.
Python 3.14 local qualification does not imply observed 3.14 CI support.

## Release gates still required

Fresh native checks against the exact manifest; independent hash-bound review;
clean committed candidate and evidence; supported-version CI; explicit publication
authorization; exact tag/commit/artifact read-back. Passing local tests alone
does not establish those gates, portability, D7/D30 or code-review replacement.
SIGKILL, escaped groups, PID reuse, signal windows and same-user tamper-proofing
remain unqualified.
