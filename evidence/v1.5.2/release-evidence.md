# 1.5.2 local candidate: bounded dashboard correction

Base: published 1.5.1 commit `2fa6868a6e88c6dce50e5f110ce7fc094abb7db2`.
The source delta has the exact-commit qualification recorded below. This
documentary finalization is not publication, a new ROI result or qualification
of later bytes by an earlier CI/review.
Only product behavior change: remove `body { min-width: 320px; }`.
Version metadata and documentation identify the separate patch; no dependency,
receipt schema, routing rule, causal mechanism or dashboard metric is added.
Headroom inspired the existing information hierarchy; no assets/code copied.

## Observed focal counterproof and positive controls

Original and corrected actual page, height 800 with a classic 15px scrollbar:

| Viewport | Original client/scroll/body | Corrected client/scroll/body |
| --- | --- | --- |
| 320 | 305/320/320 | 305/305/305 |
| 335 | 320/320/320 | 320/320/320 |
| 768 | 753/753/753 | 753/753/753 |
| 1280 | 1265/1265/1265 | 1265/1265/1265 |

The former verifier falsely accepted four `display:none` values (0<=0).
The revised verifier rejects that same mutation and accepts visible controls:
native `checkVisibility`, positive height/client/right and content-width bounds.
Any positive classic scrollbar reproduces the cause; exactly 15px is not required.
Missing browser/native capability or measurements fails, never skips to PASS.
Optimized Python (-O/-OO or PYTHONOPTIMIZE) is rejected before server creation.
The visibility fix required one corrective round; it is not a first-pass success.

`tests/dashboard_layout.py` uses the real page, renderer, CSS and security headers,
loopback-only stdlib receiver, empty registry and disabled personal-session hook.
It remains browser-assisted, outside unittest discovery/automatic browser CI.
Unittest checks normal `--help` (exit 0, usage, no server URL) alongside four
optimized-Python rejection cases. An always-reject mutation passes the old
negative-only check but fails the added positive control; this is not DOM CI.
The original helper invocation exited 1 with only output digests retained;
its cause remains unknown. A passing recheck does not diagnose that failure.
Browser engine/version, zoom and DPR were not recorded for these samples.
The loopback POST receiver is unauthenticated and last-write-wins: measurements
are diagnostics, not attestation against hostile local callers.
It does not prove ancestor clipping/occlusion, left-edge placement, sub-320 layouts,
other browsers, fonts, zoom or accessibility. `checkOpacity` is a documented
historic alias of `opacityProperty`, not evidence that opacity checks are absent:
<https://developer.mozilla.org/en-US/docs/Web/API/Element/checkVisibility>.

## Independent review and causal boundary

Earlier CSS/selfcheck bytes received a context-only external local approval:
Fable 5.1 observed, high requested/backend effort unmeasured, no tools, session
persistence or fallback. Authorized context SHA-256
`55f23d66badc007d2654cc602134b0ea928915b17efca44a9368d33b38eb40b8`;
original review text SHA-256
`5a55a9ff4d37e92efa298ff0ed2f142027591560ea9880b05de9b4edc22b12ad`.
That approval covers those earlier bytes only, not this follow-up guard/test or
current metadata/docs/manifest. It does not attest hashes independently and is
not approval to publish.

## Exact source CI and package review

Source commit: `31c499ff52642730252107870c2deee91cb9fb86`.
Source tree: `5fcb262279a5298223c9b0b8d6ac0c7753878176`.
Its parent is the published 1.5.1 base above. On 2026-10-06, the
[push CI run 37459455969](https://github.com/marcuscavalcanti/007-framework/actions/runs/37459455969)
completed successfully on that exact source commit:

| Python | Job ID | Tests | Test skips |
| --- | --- | --- | --- |
| 3.11 | 112255087867 | 156, OK | 0 |
| 3.12 | 112255088229 | 156, OK | 0 |
| 3.13 | 112255088209 | 156, OK | 0 |

Compilation and historical-tree checks also passed. The release-manifest step
was **skipped**, not passed, because it runs only on version tags. The source
manifest was verified locally: 97/97. This is not automated DOM coverage.

The exact source delta then received a context-only independent package review:
Claude CLI 2.1.285, `claude-fable-5-1` observed in CLI model-usage metadata,
`high` requested; backend effort and actual charged USD unmeasured. One
invocation/turn, exit 0, 133.687s, no tools, MCP, session persistence or fallback.
Authorized context SHA-256:
`c908858b585aaec5114a6f6bb91212a721f462656d87b46c92ff09a5285861a0`.
Original review text SHA-256:
`d61cbd2564e412786c9616755b8c88c1703a9d565fd9682a51f5763002afb3f3`.
Verdict: approve the supplied source delta; coordinator reconciliation found
no confirmed functional blocker. It is a text-based opinion, not independent
execution, hash attestation or publication authority. Timeout diagnostics,
the disclosed local receiver and hygiene-scan boundaries remain unchanged.

This documentation/manifest addendum changes bytes after that commit and review.
Neither prior CI nor approval is automatically transferred to the new bytes.
Final-commit CI/review and tag/artifact read-back remain distinct release gates;
record their observed identities in the release record without rewriting 1.5.1.

The [preserved admission experiment](../v1.5.1/release-evidence.md) still has
two structural cases, three repetitions, 36 cells. Reproductions add no independent
cases and establish neither general review replacement nor real-project ROI.
Actual charged USD, cross-platform DOM behavior and D7/D30 remain unmeasured.
Two byte-identical same-host archives do not prove cross-host reproducibility.

Local revalidation on 2026-10-06 reproduced the same frozen protocol on
Darwin/Python 3.14.7: 36 cells, zero invalid, zero source drift and zero model
calls. No historical protocol/result was overwritten. This checks deterministic
classification again; it adds no independent case or economic claim.

## Reproduce and remaining release gates

From a full-history checkout, run the Python suite, renderer and whitespace
checks as documented in the preserved 1.5.1 evidence. Then run
`python3 tests/dashboard_layout.py --port 7013` and open its printed loopback
URL at 320/335/768/1280 x 800 with classic scrollbars. Missing samples fail at 180s.
The [candidate manifest](manifest.sha256) binds the public files, excluding itself.
No project receipts, local sessions, registry or credential files are packaged.
Before publication: clean committed candidate, exact-commit supported-version
CI, separately authorized exact-context package review, explicit publication
authority and tag/artifact read-back. The 1.5.1 tag/install must not be rewritten.
