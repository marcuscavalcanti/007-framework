# Historical proof inputs

historical-sources.tar.gz contains only the exact files consumed by existing
historical checks, not a Git database, sessions, receipts or private project data.
The original sources are MIT licensed by Marcus Cavalcanti; their LICENSE bytes
are included. No historical file was edited or relabeled as a new v2 result.

| Source revision | Included bytes |
| --- | --- |
| 301b1aa30522e87a486088c79687a93d95d2aa4a | 69 paths listed in evidence/v1.4.0/manifest.sha256 |
| 460e98535752b18d1b4738babf8ad1f7d859d4a1 | 79 paths listed in evidence/v1.5.0/manifest.sha256 |
| a3012ee28f160d63a404c00c8bb4d372fe807279 | scripts/framework_cli.py, bound by the RC mutation protocol/result |

149 regular members, 1,370,106 source bytes. Archive SHA-256:
75405b32cf52569c299e7e5b5c53954289a7e31a6aa9110c551c4d319e65a906

The test reader validates that hash before decompression and reads members
without extracting paths. Existing manifest, mutation and routing checks still
verify their original assertions. Corruption or missing inputs fail; they do not
skip tests or substitute the current implementation.

Reproduction requires only a copy of this source package, supported Python,
Node and Git. It does not contact a provider, acquire credentials, regenerate
LLM output or establish economic ROI. Public release approval remains separate.

## Static synthetic replay corpus

semantic-replay.tar.gz contains26 regular members in existing replay input/result
formats, a two-case set, literal receipts/starts and this repository's MIT license.
The3,548-byte archive has SHA-256:
c15a598d5f09258aa8907d5725e446f19631af8b60f5a66a08954a775b89797c

All content is synthetic and authored for this repository, not extracted from a
private project or provider session. The declared original checkout is the inert
synthetic path /synthetic/007-public-fixture; no original checkout is needed.
One candidate changes value2 to3; the focal wrong candidate changes it to4.
Frozen portable commands expect3. Inputs include an ignored binary and an
untracked text file; file modes and all hashes remain in the native manifests.
Receipts are test declarations, with no producer authentication or billing claim.

The public test verifies the archive hash before decompression, materializes
owner-only disposable vaults without extracting archive paths, and repeats the
full read-only semantic decision three times. Expected SHA-256:
f68d412bf032303715aeda3f9b8a4713bc9ef2ba04357e19b38898b8eb2d8006
Literal independent checks also require correct/wrong oracle exits0/1, seed4007
order, failed8+accepted2=USD10, remaining20, blocked next reservation, unknown
reliable-result cost and byte-corruption rejection. The digest is a frozen
regression expectation, not an independent oracle of general correctness.

Input metadata retains the generator's Python3.11.15/source versions. Native
recheck retains its captured controller-version gate; other versions must report
runtime-version-mismatch without running that recheck. The separate portable
controls prove this tiny fixture's behavior, not runtime equivalence in general.
No model is run, trained or promoted; economic ROI remains unmeasured.
