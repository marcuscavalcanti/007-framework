# Contributing

Contributions should reduce rework without expanding the framework by default.

## Before opening a change

1. Describe the observed failure or user outcome.
2. Search for an existing rule, script, or platform feature.
3. Keep one behavior per change and state the proof level.
4. Add the smallest regression check that would fail without the change.

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
```

Doctrine changes need stronger evidence than prose: a real failure, frozen
OLD×NEW task, pre-registered acceptance rule, and results that preserve
non-target behavior. New provider instructions require verified runtime
receipts and must remain outside the provider-neutral core when possible.

Do not submit secrets, customer data, hidden acceptance tests, private repository
snapshots, raw model transcripts, or generated benchmark outputs containing
private code.
