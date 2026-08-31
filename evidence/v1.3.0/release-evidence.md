# v1.3.0 controller-authority evidence

## Verdict

PASS for the narrow controller mechanism: 18/18 preregistered cells matched.

## What changed

`007 run --action` now owns controller provenance. It blocks denied or
unclassified actions before starting the subprocess, records allowed execution,
and rejects caller-supplied `authority_evidence`. Manual receipts remain usable
and are explicitly classified as declared.

## Frozen comparison

- OLD: `be83a3f0075f5503f29f1a22023238065bf30985`
- NEW treatment: `126eca0`
- scenarios: denied action, allowed control, provenance forgery
- replicates: 3 per arm and scenario
- retries: 0
- model calls: 0
- matched: 18/18

Protocol SHA-256:
`1dca9ad2211796aaea6475fa11eaa0b2ef63e1cf24eaed944c346c5110cf974f`

Result SHA-256:
`ab4fe0002ecb0a6b02bc745307ba6a0b86514cad6307bfc6b0471aedf5ec657a`

## Adversarial review

Opus 5/xhigh rejected two earlier revisions with medium findings. After focused
RED→GREEN corrections, the final delta was approved with highest severity low.
The no-replace ledger is `adversarial-review.json`; its final context SHA-256 is
`26c7ddc04f77b56c9ddeab44ee68f710635e9f1836fddb5f2153da27b34f4791` and
the ledger SHA-256 is
`ce1718190f2b965844ef149e117bb72063b3ca24dc8f2969b3c01c035948606f`.

## Claim boundary

This result supports only the local supported-controller mechanism. It does not
prove resistance to a malicious process with the same OS credentials, broader
productivity gains, seven-day durability, or provider portability. Dashboard
project metrics remain observational.
