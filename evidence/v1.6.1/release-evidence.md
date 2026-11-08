# 1.6.1: fixes after 1.6.0

Base: published 1.6.0, commit `0c3b5cb78feb4a0817bda468d5bb452d04ced44b`. Patch release; the changes are listed in the
[changelog](../../CHANGELOG.md).

- **Fixed:** `007 lab sufficiency` counted old behaviour (hidden tests already green at base), so an empty patch could pass the
  filter. A test now fails on the 1.6.0 code and passes on this one. A 5-second subprocess timeout that flaked once on CI is now
  60 seconds.
- **Changed (documentation and labels):** a verdict holds for the specification form the set used; `007 lab` is beta; the
  dashboard says "less quota" is estimated as cost; the README opening describes 007 as a toolkit that drives agent CLIs.
- **Qualification:** exact-commit and exact-tag CI as recorded on the GitHub release. No independent review was run for this
  patch.
- **Not changed:** no command, flag, schema or published evidence.
