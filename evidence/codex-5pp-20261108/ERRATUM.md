# Erratum (2026-11-08): `gojson-floor-5pp.json` is not plain JSON

- **What:** the file opens with two lines of simulation progress (`earlier_231 {...}` and `topup_652 {...}`) before the JSON
  object, so a JSON parser rejects it at line 1. The external audit of 2026-11-08 found it (F11).
- **Why:** the simulation's whole standard output was saved, progress lines included.
- **What does not change:** the two lines repeat the per-set floors the object already records. The object's `critical_floor`,
  2.197566414978024, is the constant `GOJSON_FLOOR` in `freeze_pilot.py`, which never reads this file. No number, rule or decision
  of the pre-registration moves.
- **What is added:** `gojson-floor-5pp.clean.json`, the object alone: lines 3 to 17 of the original, byte for byte
  (`tail -n +3 gojson-floor-5pp.json`).
- **What is kept:** the original stays byte-identical, because `SHA256SUMS` bound it before any paid attempt and the 1.6.0 and 1.6.1
  release manifests list it. `SHA256SUMS` keeps its first five lines and gains one line for each new file.
- **Check:** `tests/test_package.py` parses every `*.json` under `evidence/`, allows this file as the only exception, and verifies
  every line of every `evidence/*/SHA256SUMS`.
