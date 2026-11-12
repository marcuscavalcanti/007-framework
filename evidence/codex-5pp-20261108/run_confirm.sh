#!/bin/sh
# PREREG-CONFIRM: two looks of 4 replicates per arm on the confirmatory set, pinned v1.7.0 runner, cap US$400, then the analysis.
# Look 1 decides KILL / FUTILITY / CONTINUE; only CONTINUE dispatches replicates 5-8. Invalid cells never redone.
cd "$(dirname "$0")" || exit 1
PIN=../../qualified-releases/v1.7.0-21ba2ffba46a
python3 -I -B pinned.py || exit 1
shasum -a 256 -c SHA256SUMS > /dev/null || { echo "a hashed file changed" >&2; exit 1; }
[ -f confirm-build.json ] || { echo "build_confirm.py first" >&2; exit 1; }
SET=$(shasum -a 256 confirm-set.json | cut -d' ' -f1)
[ "$SET" = "$(python3 -I -c 'import json; print(json.load(open("confirm-build.json"))["confirm_set_sha256"])')" ] || { echo "confirm-set.json changed after the build" >&2; exit 1; }
T=$(python3 -I -c 'import json; print(len(json.load(open("confirm-set.json"))["tasks"]))') || exit 1
block() {  # $1 = replicates so far, $2 = look
  echo "{\"confirm\": \"look $2 start\", \"at\": \"$(date -u +%FT%TZ)\", \"confirm_set_sha256\": \"$SET\", \"sha256sums\": \"$(shasum -a 256 SHA256SUMS | cut -d' ' -f1)\"}" >> confirm.log
  caffeinate -i python3 -B "$PIN/scripts/effort_lab.py" run --set confirm-set.json --out confirm-results --replicates "$1" --jobs 4 \
    --max-calls $(( 2 * T * $1 )) --max-usd 400 --stop-usd 2 --max-invalid $(( (2 * T * $1 + 9) / 10 )) >> confirm.log 2>> confirm.err
  rc=$?
  echo "{\"confirm\": \"look $2 end\", \"exit\": $rc, \"at\": \"$(date -u +%FT%TZ)\"}" >> confirm.log
  [ "$rc" = 0 ] || exit "$rc"  # an early stop goes back to Marcus: NO-STOPPED
  python3 -I -B -W ignore analyze_confirm.py "$2" > "confirm-look$2.out" 2>> confirm.err || exit 1
}
block 4 1
D=$(python3 -I -c 'import json; print(json.load(open("confirm-results-look1.json"))["decision"])')
[ "$D" = CONTINUE ] || { echo "look 1: $D" >> confirm.log; exit 0; }
block 8 2
python3 -I -B -W ignore part3.py confirm-results > part3.out 2>> confirm.err
