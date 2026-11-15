#!/bin/sh
# AMENDMENT-2: run_pilot.sh on the pinned v1.7.0 runner. The log records the code commit, the set hash and the tool versions first.
# One block of 2 attempts per arm on every pooled task, then the freeze. Cap US$150; invalid cells never redone.
cd "$(dirname "$0")" || exit 1
PIN=../../qualified-releases/v1.7.0-21ba2ffba46a
python3 -I -B pinned.py || exit 1
[ -f pilot-build.json ] && [ -f reference-failed.json ] || { echo "build_pilot_v2.py first" >&2; exit 1; }
SET=$(shasum -a 256 pilot-set.json | cut -d' ' -f1)
[ "$SET" = "$(python3 -I -c 'import json; print(json.load(open("pilot-build.json"))["pilot_set_sha256"])')" ] || { echo "pilot-set.json changed after the build" >&2; exit 1; }
N=$(python3 -I -c 'import json; print(4 * len(json.load(open("pilot-set.json"))["tasks"]))') || exit 1
CODEX=$("$(python3 -I -c 'import json; c = json.load(open("pilot-set.json"))["agent_command"]; print(c[c.index("--") + 1])')" --version 2>&1)
echo "{\"pilot\": \"start\", \"cells\": $N, \"at\": \"$(date -u +%FT%TZ)\", \"code_commit\": \"21ba2ffba46a0e0cd6be0616a5582ffcffb24d88\", \"pilot_set_sha256\": \"$SET\", \"codex_cli\": \"$CODEX\", \"python\": \"$(python3 --version)\"}" >> run.log
caffeinate -i python3 -B "$PIN/scripts/effort_lab.py" run --set pilot-set.json --out results --replicates 2 --jobs 4 \
  --max-calls "$N" --max-usd 150 --stop-usd 2 --max-invalid $(( (N + 9) / 10 )) > block.out 2>> run.err
rc=$?
cat block.out >> run.log
echo "{\"pilot\": \"end\", \"exit\": $rc, \"at\": \"$(date -u +%FT%TZ)\"}" >> run.log
[ "$rc" = 0 ] && python3 -I -B -W ignore freeze_pilot_v2.py > freeze.out 2>> run.err  # a stopped pilot goes back to Marcus
