#!/bin/sh
# AMENDMENT-5: prepare_pilot_v2.sh with dry_run_v3.py, then the reference-failed union. No model, US$0. Stops at the first failure.
cd "$(dirname "$0")" || exit 1
log() { echo "{\"step\": \"$1\", \"event\": \"$2\", \"at\": \"$(date -u +%FT%TZ)\"$3}" >> prepare3.log; }
python3 -I -B pinned.py || exit 1
shasum -a 256 -c SHA256SUMS > /dev/null || { echo "a hashed file changed" >&2; exit 1; }
[ -d gate-run1 ] || mv gate gate-run1 || exit 1
mkdir -p gate
AGAIN=$(python3 -I -c 'import json, pathlib; print(" ".join(p.stem for p in sorted(pathlib.Path("gate-run1").glob("*.json")) if not json.loads(p.read_text())["consistent"]))')
for f in gate-run1/*.json; do n=$(basename "$f" .json); case " $AGAIN " in *" $n "*) ;; *) cp "$f" "gate/$n.json";; esac; done
log gate2 start ", \"repositories\": \"$AGAIN\""
if [ -n "$AGAIN" ]; then caffeinate -i python3 -I -B gate_rerun.py $AGAIN >> prepare3.log 2> gate2.err; rc=$?; else rc=0; fi
log gate2 end ", \"exit\": $rc"; [ "$rc" = 0 ] || exit "$rc"
python3 -I -B build_pilot_v3.py >> prepare3.log 2> build3.err; rc=$?
log build end ", \"exit\": $rc"; [ "$rc" = 0 ] || exit "$rc"
caffeinate -i python3 -I -B dry_run_v3.py >> prepare3.log 2> dryrun3.err; rc=$?
log dryrun3 end ", \"exit\": $rc"; [ "$rc" = 0 ] || exit "$rc"
python3 -I -B reference_union.py >> prepare3.log 2>> dryrun3.err; rc=$?
log union end ", \"exit\": $rc"
tail -c 3000 prepare3.log
exit "$rc"
