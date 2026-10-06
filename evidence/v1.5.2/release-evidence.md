# 1.5.2 local candidate: bounded dashboard correction

Base: published 1.5.1 commit `2fa6868a6e88c6dce50e5f110ce7fc094abb7db2`.
This is local preparation, not a release, new ROI result or CI qualification.
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

The [preserved admission experiment](../v1.5.1/release-evidence.md) still has
two structural cases, three repetitions, 36 cells. Reproductions add no independent
cases and establish neither general review replacement nor real-project ROI.
Actual charged USD, cross-platform DOM behavior and D7/D30 remain unmeasured.
Two byte-identical same-host archives do not prove cross-host reproducibility.

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
