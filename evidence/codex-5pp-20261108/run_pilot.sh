#!/bin/sh
# PREREG-PILOT: one block of 2 attempts per arm on every pooled task, then the freeze. Cap US$150; invalid cells never redone.
cd "$(dirname "$0")" || exit 1
N=$(python3 -I -c 'import json; print(4 * len(json.load(open("pilot-set.json"))["tasks"]))') || exit 1
echo "{\"pilot\": \"start\", \"cells\": $N, \"at\": \"$(date -u +%FT%TZ)\"}" >> run.log
caffeinate -i python3 -B ../../repo/scripts/effort_lab.py run --set pilot-set.json --out results --replicates 2 --jobs 4 \
  --max-calls "$N" --max-usd 150 --stop-usd 2 --max-invalid $(( (N + 9) / 10 )) > block.out 2>> run.err
rc=$?
cat block.out >> run.log
echo "{\"pilot\": \"end\", \"exit\": $rc, \"at\": \"$(date -u +%FT%TZ)\"}" >> run.log
[ "$rc" = 0 ] && python3 -I -B -W ignore freeze_pilot.py > freeze.out 2>> run.err  # a stopped pilot goes back to Marcus
