# Authority-envelope mechanism evidence

Verdict: **PASS at mechanism level; 18/18 preregistered cells matched.**

- OLD commit: `c5a4cdbe991332e6d16a0f8949e5c08ec349d404`
- protocol SHA-256: `999b9f2d7aca0f1c27eb5aa6a6dae59d508bfa347cef0405f62866abc179bbeb`
- final result SHA-256: `e4361f30a2a55b0602b1af021af74944f567fa790293a1ee0dcd3df5d305d655`
- design: three scenarios, three repetitions, OLD and NEW on identical fixtures;
- target: an executed action outside bound authority was accepted by OLD and rejected by NEW;
- controls: an allowed execution and a denied-but-blocked action remained accepted in both arms.

This isolates the terminal gate mechanism. It does **not** prove that agents
report every event, that soft policy replaces sandboxing, or that authority
envelopes reduce real-world rework. Those claims require operational receipts
and later paired tasks.

`result-r2` reran the unchanged protocol after review hardened receipt
sanitization and rejected injected summaries; it is the release-facing result.
