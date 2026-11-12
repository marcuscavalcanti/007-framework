#!/bin/sh
# PREREG-B, branch without a confirmatory run: 4 fresh attempts per arm on block B's set, pinned v1.7.0 runner, cap US$150, then
# analyze_b.py. Invalid cells never redone; an early stop ends block B (NO-STOPPED).
cd "$(dirname "$0")" || exit 1
PIN=../../qualified-releases/v1.7.0-21ba2ffba46a
python3 -I -B pinned.py || exit 1
shasum -a 256 -c SHA256SUMS > /dev/null || { echo "a hashed file changed" >&2; exit 1; }
[ -f b-build.json ] || { echo "build_b.py first" >&2; exit 1; }
[ ! -e b-results ] || { echo "b-results/ exists: never redo block B" >&2; exit 1; }
SET=$(shasum -a 256 b-set.json | cut -d' ' -f1)
[ "$SET" = "$(python3 -I -c 'import json; print(json.load(open("b-build.json"))["b_set_sha256"])')" ] || { echo "b-set.json changed after the build" >&2; exit 1; }
N=$(python3 -I -c 'import json; print(8 * len(json.load(open("b-set.json"))["tasks"]))') || exit 1
echo "{\"b\": \"start\", \"cells\": $N, \"at\": \"$(date -u +%FT%TZ)\", \"b_set_sha256\": \"$SET\", \"sha256sums\": \"$(shasum -a 256 SHA256SUMS | cut -d' ' -f1)\"}" >> b.log
caffeinate -i python3 -B "$PIN/scripts/effort_lab.py" run --set b-set.json --out b-results --replicates 4 --jobs 4 \
  --max-calls "$N" --max-usd 150 --stop-usd 2 --max-invalid $(( (N + 9) / 10 )) >> b.log 2>> b.err
rc=$?
echo "{\"b\": \"end\", \"exit\": $rc, \"at\": \"$(date -u +%FT%TZ)\"}" >> b.log
[ "$rc" = 0 ] || exit "$rc"
python3 -I -B -W ignore analyze_b.py b-results > b.out 2>> b.err
