#!/bin/sh
# AMENDMENT-5: run_pilot_v3.sh, dispatched only after dry_run_v3.py passed; after the freeze, the serial re-grade of every valid cell,
# the freeze of the re-graded cells, the decision (decide_pilot.py) and part3.py. Cap US$150; invalid cells never redone.
cd "$(dirname "$0")" || exit 1
PIN=../../qualified-releases/v1.7.0-21ba2ffba46a
python3 -I -B pinned.py || exit 1
shasum -a 256 -c SHA256SUMS > /dev/null || { echo "a hashed file changed" >&2; exit 1; }
[ -f pilot-build.json ] && [ -f reference-failed.json ] || { echo "build_pilot_v2.py first" >&2; exit 1; }
python3 -I -c 'import json, sys; sys.exit(0 if json.load(open("dryrun3/dry-run.json"))["passed"] is True else 1)' 2>/dev/null \
  || { echo "dry_run_v3.py must pass first" >&2; exit 1; }
[ ! -e results ] || { echo "results/ exists: a pilot was already dispatched; never redo it" >&2; exit 1; }
SET=$(shasum -a 256 pilot-set.json | cut -d' ' -f1)
[ "$SET" = "$(python3 -I -c 'import json; print(json.load(open("pilot-build.json"))["pilot_set_sha256"])')" ] || { echo "pilot-set.json changed after the build" >&2; exit 1; }
N=$(python3 -I -c 'import json; print(4 * len(json.load(open("pilot-set.json"))["tasks"]))') || exit 1
CODEX=$("$(python3 -I -c 'import json; c = json.load(open("pilot-set.json"))["agent_command"]; print(c[c.index("--") + 1])')" --version 2>&1)
echo "{\"pilot\": \"start\", \"cells\": $N, \"at\": \"$(date -u +%FT%TZ)\", \"code_commit\": \"21ba2ffba46a0e0cd6be0616a5582ffcffb24d88\", \"pilot_set_sha256\": \"$SET\", \"sha256sums\": \"$(shasum -a 256 SHA256SUMS | cut -d' ' -f1)\", \"codex_cli\": \"$CODEX\", \"python\": \"$(python3 --version)\"}" >> run.log
caffeinate -i python3 -B "$PIN/scripts/effort_lab.py" run --set pilot-set.json --out results --replicates 2 --jobs 2 \
  --max-calls "$N" --max-usd 150 --stop-usd 2 --max-invalid $(( (N + 9) / 10 )) > block.out 2>> run.err
rc=$?
cat block.out >> run.log
echo "{\"pilot\": \"end\", \"exit\": $rc, \"at\": \"$(date -u +%FT%TZ)\"}" >> run.log
[ "$rc" = 0 ] || exit "$rc"  # a stopped pilot goes back to Marcus: nothing is frozen
python3 -I -B -W ignore freeze_pilot_v3.py > freeze.out 2>> run.err || exit 1
echo "{\"regrade\": \"start\", \"at\": \"$(date -u +%FT%TZ)\"}" >> run.log
caffeinate -i python3 -I -B regrade_serial.py pilot-set.json results serial frozen-reach.json > regrade.out 2>> run.err || exit 1
mkdir -p serial-freeze && python3 -I -B -W ignore freeze_pilot_v3.py serial serial-freeze > serial-freeze.out 2>> run.err || exit 1
python3 -I -B decide_pilot.py >> run.log 2>> run.err || exit 1
python3 -I -B -W ignore part3.py > part3.out 2>> run.err
