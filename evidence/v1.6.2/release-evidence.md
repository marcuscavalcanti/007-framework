# 1.6.2: fixes from an external audit of 1.6.1

Base: published 1.6.1, commit `84abe04d5b92db13c29609e3ff064f0b17fc9811`. An external audit of that snapshot (report SHA-256
`337488b320b1a7e2ad9288925f0a61801cb8f05efe760f60e489fc0f41f2fd77`, 2026-11-08) reported eleven findings. Each was reproduced
on the current code and classified. Confirmed findings are fixed here with a test that fails before the fix and controls that pass
before and after. The audit was read as evidence to check, not as a specification.

## Reconciliation

The historical checks in the last column are maintainer-reported checks from
the external-audit reconciliation, not an independently hash-bound audit of all
published attempts. Their quantitative coverage was not supplied to the release
reviewer. They do not establish absence of historical impact; a full re-grade
of retained patches remains required before strengthening that claim.

| Finding | State on 1.6.1 | Fix in 1.6.2 | Historical impact |
|---|---|---|---|
| F01: acceptance passes a test whose suite failed around it | Confirmed (unittest teardown; Go package failure with every test passing, reproduced with real Go) | A test in a failed fixture or package scope reads `error` | None found. A targeted re-grade of 165 published go-json cells changed 0 outcomes and 0 acceptances, and no published task has a `TestMain`. A residual route (a fatal runtime error in an ungraded test after the last graded one) is invisible in stored data; a full re-grade with no model would close it. |
| F02: candidate patch empty after the agent commits | Confirmed, and worse: committing everything also produced a spurious prompt-file deletion | Diff against the snapshot commit recorded before the agent starts | None: no valid published cell has an empty patch or the spurious deletion |
| F03: declared served model can contradict the native stream | Confirmed | A declared model must be one the stream names, otherwise exit 2 with telemetry kept and no receipt | None: no published receipt carries native telemetry |
| F04: denied action with acceptance loses its terminal receipt | Confirmed, and systematic under a capture config | Additive `receipt/v1` state: acceptance `not-executed` | None |
| F05: passive activity frozen by a size/mtime cache | Confirmed (a cached read stayed `active` with 132 tokens; a fresh read gave `idle` with 12) | Fixed in the 1.7.0 capture rework, which it depends on; not in this patch | Passive observation only; no published result |
| F06: passive Claude usage aggregation | Confirmed (duplicated message ids counted twice; invalid counters read as zero) | Fixed in the 1.7.0 capture rework, which it depends on; not in this patch | Passive observation only; no published result |
| F07: Kaplan-Meier curve that reaches zero turns unknown | Confirmed | Extinction stays 0; censoring still stops a curve | None: the field trial is off and its outcomes were never unblinded |
| F08: signature hint can copy a function body | Confirmed, and worse: multi-line headers also copied following lines | Cut at the top-level `:` with the tokenizer | None: the only lab use, a private replay set, gets identical hints under the fix |
| F09: a lab verdict reads as evidence for any selected repository | Confirmed | A report applies only to the repository, CLI and model it is bound to | None: the published verdicts are NOT-PROVEN |
| F10: after a failed refresh, old evidence reads as current | Confirmed | Preserved data is marked stale, with the evidence read time separate from the response time | None |
| F11: the 5-point floor file is not valid JSON | Confirmed | `ERRATUM.md` and a clean sibling; the original stays byte-identical because the pre-registration hashed it | None: `freeze_pilot.py` uses the floor as a constant |

The published conclusions stand: Codex and Claude on go-json remain NOT-PROVEN at their declared margins.

Also in this release, from the maintainer's decisions after the audit:
- **Reviewer identity levels** (`AGENTS.md`, `review_route.identity_level`): `verified`, `pinned-no-reroute` and `failed`.
  `pinned-no-reroute` qualifies a release only as "qualified with unverified reviewer identity". The levels never apply to
  experiments.
- **Announcement rule:** any verdict of a technically qualified release may be announced (`RELEASING.md`).
- **Amendment 1 to the Codex 5-point pilot:** published before any pilot attempt; the original and its hash are unchanged.

## Qualification
- **Exact-commit and exact-tag CI:** recorded on the GitHub release.
- **Independent review:** per `AGENTS.md` reviewer identity levels, recorded on the GitHub release; not run if Marcus does not
  authorize it.

## Follow-up to the independent review

The review of candidate 4fbc2dd returned FIX FIRST at identity level
`pinned-no-reroute`: requested model pinned, no reroute observed, served identity
unverified. Its four blocking paths were reproduced before local correction:
later/extra review events, Go package failure hidden by a known-red test, custom
report-then-fail, and a verdict applied to the wrong effort pair. The new binding
requires `effort` and `against` in addition to project, CLI and model; partial
bindings still load but apply no verdict. Go output outside tests in a failed
package stays unproven when attribution is ambiguous. Custom exit 1 preserves
partial grades only when the report explains it with a failed/error test.

These corrections have local regression coverage; they have not received a new
independent approval. The original FIX FIRST verdict is not rewritten as SHIP.
CI and distribution checks for the revised commit are recorded separately.
