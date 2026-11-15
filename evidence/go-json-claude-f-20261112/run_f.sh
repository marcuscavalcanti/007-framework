#!/bin/sh
# PREREG-F run as amended by F-1. Pinned 1.8.1, 2 jobs, cap US$400, per-cell brake US$20, at most 17 invalid cells of any class.
# Gates before any dispatch: one run at a time (run.lock); no f-result.json (one look); pins and hashes; the PREREG dry run (carried
# over) and the F-1 dry run on this set and these files; the recorded probe failure; the maintainer's GO-3 naming this SHA256SUMS;
# bin/claude equal to shim.template filled for this directory; writable streams/; no HOLD.json.
# Cells go out in chunks of at most 20, in the seeded plan's order (replicate 1 whole, then replicate 2). Before each chunk: the load
# gate (5-minute load under 8, waiting up to 60 minutes) and the quota gate (quota_f.py). A failed gate pauses the run for the
# maintainer; running this again resumes, and no grade is opened. After the first 40 cells the cost marker runs once
# (costcheck_f.py: MARKER.json on a pass; HOLD.json on a hold, which is terminal, NO-BUDGET). Then the serial re-grade (behind the
# load gate), A/A and analyze_f.py.
# In 1.8.1 a Claude usage limit is not recognised as a rate limit: inside a chunk it turns cells invalid, which count toward the 17.
# A recognised rate-limit stop (Codex only in 1.8.1) waits 30 minutes, 48 hours in all. Any other stop ends the run (NO-STOPPED).
# load.log records the load average every minute. F_REGRADE_ARGS, F_QUOTA_CLI and F_MAX_LOAD are dry-run overrides: refused unless
# GO-3.json is a sandbox stub.
export LC_ALL=C
[ -n "$F_CAFFEINATED" ] || exec env F_CAFFEINATED=1 caffeinate -i sh "$0" "$@"
cd "$(dirname "$0")" || exit 1
PIN=../../qualified-releases/v1.8.1-f05ebcbc4749
mkdir run.lock 2>/dev/null || { echo "another run_f.sh holds run.lock" >&2; exit 1; }
LOADLOG=""
trap 'rmdir run.lock 2>/dev/null; [ -n "$LOADLOG" ] && kill "$LOADLOG" 2>/dev/null' EXIT
[ ! -f f-result.json ] || { echo "the single look has been taken (f-result.json exists)" >&2; exit 1; }
python3 -I -B pinned_f.py || exit 1
shasum -a 256 -c SHA256SUMS > /dev/null || { echo "a hashed file changed" >&2; exit 1; }
SET=$(shasum -a 256 f-set.json | cut -d' ' -f1)
[ "$SET" = "$(python3 -I -c 'import json; print(json.load(open("f1.json"))["f_set_sha256"])')" ] || { echo "f-set.json changed" >&2; exit 1; }
python3 -I -c 'import json,sys; sys.exit(0 if json.load(open("dryrun/dry-run.json"))["passed"] else 1)' \
  || { echo "the PREREG dry run must have passed" >&2; exit 1; }
python3 -I -c '
import hashlib, json, sys
d = json.load(open("dryrun-f1/dry-run.json"))
same = all(hashlib.sha256(open(f, "rb").read()).hexdigest() == h for f, h in d["files"].items())
sys.exit(0 if d["passed"] and d["f_set_sha256"] == json.load(open("f1.json"))["f_set_sha256"] and same else 1)' \
  || { echo "the F-1 dry run must pass on this set and these files" >&2; exit 1; }
python3 -I -c 'import json,sys; sys.exit(0 if json.load(open("probe/probe.json"))["passed"] is False else 1)' \
  || { echo "the probe result must be the failure F-1 records" >&2; exit 1; }
SUMS=$(shasum -a 256 SHA256SUMS | cut -d' ' -f1)
[ "$SUMS" = "$(python3 -I -c 'import json; print(json.load(open("GO-3.json"))["sha256sums"])' 2>/dev/null)" ] \
  || { echo "the maintainer's go (GO-3.json) must name this SHA256SUMS" >&2; exit 1; }
STUB=$(python3 -I -c 'import json; print("stub" if json.load(open("GO-3.json")).get("stub") else "")')
[ -n "$STUB" ] || [ -z "$F_REGRADE_ARGS$F_QUOTA_CLI$F_MAX_LOAD" ] || { echo "dry-run overrides are refused in the real run" >&2; exit 1; }
CLI=$(python3 -I -c 'import json; print(json.load(open("f1.json"))["cli"])')
[ -x "$CLI" ] || { echo "the CLI named in f1.json is not executable" >&2; exit 1; }
sed -e "s#@STREAMS@#$PWD/streams#" -e "s#@CLI@#$CLI#" shim.template | cmp -s - bin/claude || { echo "bin/claude is not shim.template for this directory" >&2; exit 1; }
[ -d streams ] && [ -w streams ] || { echo "streams/ must be writable" >&2; exit 1; }
[ ! -f HOLD.json ] || { echo "held by the cost marker: NO-BUDGET" >&2; exit 1; }
done_cells() { find results -maxdepth 1 -name '*-r[0-9][0-9]-*.json' ! -name '*.runner.json' 2>/dev/null | wc -l | tr -d ' '; }
VER=$("$CLI" --version 2>/dev/null | head -1)
echo "{\"f\": \"start\", \"at\": \"$(date -u +%FT%TZ)\", \"cells_done\": $(done_cells), \"f_set_sha256\": \"$SET\", \"sha256sums\": \"$SUMS\", \"code_commit\": \"f05ebcbc47496bcd39c272fe2d0dd82d9a336879\", \"cli_version\": \"$VER\", \"overrides\": \"${F_REGRADE_ARGS:+regrade }${F_QUOTA_CLI:+quota }${F_MAX_LOAD:+load}\"}" >> run.log
( while :; do echo "$(date -u +%FT%TZ) $(sysctl -n vm.loadavg)" >> load.log; sleep 60; done ) &
LOADLOG=$!
quiet() {  # $1 names the step; waits up to 60 minutes for the 5-minute load to fall under F_MAX_LOAD (8)
  N=0
  while :; do
    L=$(sysctl -n vm.loadavg | awk '{print $3}')
    awk -v l="$L" -v m="${F_MAX_LOAD:-8}" 'BEGIN { exit !(l < m) }' && return 0
    [ "$N" -lt 12 ] || { echo "{\"f\": \"loaded\", \"step\": \"$1\", \"load5\": \"$L\", \"at\": \"$(date -u +%FT%TZ)\"}" >> run.log; echo "machine loaded before $1: paused for the maintainer" >&2; exit 5; }
    N=$((N + 1)); sleep 300
  done
}
WAITED_S=0
while :; do
  DONE=$(done_cells); LEFT=$((164 - DONE)); CALLS=20
  [ "$LEFT" -gt 0 ] || break
  [ "$CALLS" -le "$LEFT" ] || CALLS=$LEFT
  if [ ! -f MARKER.json ] && [ $((40 - DONE)) -lt "$CALLS" ]; then CALLS=$((40 - DONE)); fi
  if [ "$CALLS" -gt 0 ]; then
    quiet "chunk at $DONE"
    python3 -I -B quota_f.py ${F_QUOTA_CLI:+"$F_QUOTA_CLI"} >> run.log || { echo "quota gate failed at $DONE cells: paused for the maintainer" >&2; exit 4; }
    python3 -B "$PIN/scripts/effort_lab.py" run --set f-set.json --out results --replicates 2 --jobs 2 \
      --max-calls "$CALLS" --max-usd 400 --stop-usd 20 --max-invalid 17 > block.out 2>> run.err
    rc=$?; cat block.out >> run.log
    STOP=$(python3 -I -c 'import json; print(json.load(open("block.out")).get("stop") or "")' 2>/dev/null)
    echo "{\"f\": \"chunk end\", \"from\": $DONE, \"calls\": $CALLS, \"exit\": $rc, \"stop\": \"$STOP\", \"at\": \"$(date -u +%FT%TZ)\"}" >> run.log
    case "$STOP" in
      rate-limit|rate-limit-cooldown)
        [ "$WAITED_S" -lt 172800 ] || exit "$rc"
        echo "{\"f\": \"pause\", \"seconds\": 1800, \"at\": \"$(date -u +%FT%TZ)\"}" >> run.log
        sleep 1800; WAITED_S=$((WAITED_S + 1800)); continue;;
      call-budget|"") ;;
      *) exit "$rc";;
    esac
    [ "$(done_cells)" -gt "$DONE" ] || { echo "a chunk made no progress" >&2; exit 6; }
  fi
  if [ ! -f MARKER.json ] && [ "$(done_cells)" -ge 40 ]; then
    python3 -I -B costcheck_f.py >> run.log || exit 1
  fi
done
quiet "serial re-grade"
python3 -I -B regrade_f.py f-set.json results serial frozen-reach.json $F_REGRADE_ARGS > regrade.out 2>> run.err || exit 1
python3 -I -B -W ignore aa_f.py > aa.out 2>> run.err || exit 1
python3 -I -B -W ignore analyze_f.py > analyze.out 2>> run.err
