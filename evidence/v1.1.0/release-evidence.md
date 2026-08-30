# v1.1.0 release evidence

Release status: **ready to test**.

## Product checks

- installable skill and CLI identity: `007-framework` / `1.1.0`;
- runtime dependencies: Python standard library only;
- deterministic package and dashboard suite: 41 tests;
- clean-project E2E covers init, cost-accounted receipt, aggregation, and served route;
- loopback HTTP allowlist, CSP, safe browser projection, and responsive UI checked;
- aggregate metrics reconcile from raw project totals and fail closed on broken evidence;
- every recorded terminal outcome requires finite cost, accounting source, and status.

## Measurement boundary

- cost coverage uses recorded receipts as its denominator;
- a host that omits `007 record` is not observable by the dependency-free core;
- operational dashboard metrics are observational and do not prove causality;
- the narrow frozen mechanism result remains OLD 0/3 versus NEW 3/3 on one task.

## External review

Opus 5/xhigh reviewed the full candidate, rejected two earlier revisions, and
approved the bounded final delta with maximum severity `low`. Approval receipt
SHA-256:
`8f6991aeb4513ae3cd771dd57680f3cdbc840898bb1dceb86efd874fde1a418b`.

The rejected receipts are preserved outside the public package by content hash.
Reviewer judgment supplements, but does not replace, executable checks.

## Freeze contract

`manifest.sha256` covers every tracked release file except itself. It is an
integrity inventory for this tag, not an independent authenticity claim.
