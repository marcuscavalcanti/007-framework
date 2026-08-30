# v1.0.0 release evidence

Release status: **ready to test**.

## Product checks

- installable skill identity: `007-framework` / `1.0.0`;
- runtime dependencies: none beyond Python standard library for optional tools;
- package contract: 16 deterministic unit tests;
- compatibility checked with Python 3.9 and 3.14 locally; CI covers 3.11–3.13;
- private paths, common private-key markers, and rejected credential doctrine
  excluded by tests;
- replay workspaces and archives use system-generated unique paths; extraction
  accepts only regular files/directories inside the workspace.

## Controlled-result boundary

- target mechanism: OLD 0/3, NEW 3/3;
- compatibility case: OLD 3/3, NEW 3/3;
- rejected provider mechanism: blocked and absent from V1;
- general superiority, production durability, and provider portability: not
  claimed.

Full historical hashes and interpretation are in
[`../../docs/evidence.md`](../../docs/evidence.md).

## Freeze contract

`manifest.sha256` covers every release file except itself and the post-freeze
`opus-review.json` attestation. The review context is built from those exact
covered bytes. It is an integrity inventory, not an independent authenticity
claim. Adding the attestation does not change product logic or doctrine.
