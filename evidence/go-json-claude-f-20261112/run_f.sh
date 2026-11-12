#!/bin/sh
# PREREG-F run: two blocks of 1 replicate per arm (82 cells each), pinned 1.8.1, 2 jobs, cap US$400, then the serial re-grade, A/A
# and analyze_f.py. A provider rate limit (stop "rate-limit") pauses: the same command resumes every 30 minutes, for at most 48 hours.
# Any other stop ends the run (NO-STOPPED) and nothing is redone.
cd "$(dirname "$0")" || exit 1
PIN=../../qualified-releases/v1.8.1-f05ebcbc4749
python3 -I -B pinned_f.py || exit 1
shasum -a 256 -c SHA256SUMS > /dev/null || { echo "a hashed file changed" >&2; exit 1; }
SET=$(shasum -a 256 f-set.json | cut -d' ' -f1)
[ "$SET" = "$(python3 -I -c 'import json; print(json.load(open("f-build.json"))["f_set_sha256"])')" ] || { echo "f-set.json changed" >&2; exit 1; }
python3 -I -c 'import json,sys; sys.exit(0 if json.load(open("dryrun/dry-run.json"))["passed"] and json.load(open("probe/probe.json"))["passed"] else 1)' \
  || { echo "dry run and probe must pass first" >&2; exit 1; }
[ -f GO ] || { echo "the maintainer's go (file GO) is missing" >&2; exit 1; }
echo "{\"f\": \"start\", \"at\": \"$(date -u +%FT%TZ)\", \"f_set_sha256\": \"$SET\", \"sha256sums\": \"$(shasum -a 256 SHA256SUMS | cut -d' ' -f1)\", \"code_commit\": \"f05ebcbc47496bcd39c272fe2d0dd82d9a336879\"}" >> run.log
for REPS in 1 2; do
  WAITED=0
  while :; do
    caffeinate -i python3 -B "$PIN/scripts/effort_lab.py" run --set f-set.json --out results --replicates $REPS --jobs 2 \
      --max-calls 164 --max-usd 400 --stop-usd 10 --max-invalid 17 > block.out 2>> run.err
    rc=$?; cat block.out >> run.log
    STOP=$(python3 -I -c 'import json; print(json.load(open("block.out")).get("stop") or "")' 2>/dev/null)
    [ "$STOP" = "rate-limit" ] && [ "$WAITED" -lt 96 ] && { WAITED=$((WAITED + 1)); sleep 1800; continue; }
    break
  done
  echo "{\"f\": \"block $REPS end\", \"exit\": $rc, \"stop\": \"$STOP\", \"at\": \"$(date -u +%FT%TZ)\"}" >> run.log
  [ "$rc" = 0 ] || exit "$rc"
done
caffeinate -i python3 -I -B regrade_f.py f-set.json results serial frozen-reach.json > regrade.out 2>> run.err || exit 1
python3 -I -B -W ignore aa_f.py > aa.out 2>> run.err || exit 1
python3 -I -B -W ignore analyze_f.py > analyze.out 2>> run.err
