#!/bin/sh
# AMENDMENT-6: the gate files of prepare_pilot_v3.sh stand (gate-run1/, gate/); build_pilot_v4.py, dry_run_v3.py on the new set
# (the failed attempt kept as dryrun3-attempt1/), then the reference-failed union. No model, US$0. Stops at the first failure.
cd "$(dirname "$0")" || exit 1
log() { echo "{\"step\": \"$1\", \"event\": \"$2\", \"at\": \"$(date -u +%FT%TZ)\"$3}" >> prepare4.log; }
python3 -I -B pinned.py || exit 1
shasum -a 256 -c SHA256SUMS > /dev/null || { echo "a hashed file changed" >&2; exit 1; }
[ -d gate ] && [ -d gate-run1 ] || { echo "gate files missing" >&2; exit 1; }
[ ! -e dryrun3 ] || [ -e dryrun3-attempt1 ] || mv dryrun3 dryrun3-attempt1 || exit 1
python3 -I -B build_pilot_v4.py >> prepare4.log 2> build4.err; rc=$?
log build end ", \"exit\": $rc"; [ "$rc" = 0 ] || exit "$rc"
caffeinate -i python3 -I -B dry_run_v3.py >> prepare4.log 2> dryrun4.err; rc=$?
log dryrun3 end ", \"exit\": $rc"; [ "$rc" = 0 ] || exit "$rc"
python3 -I -B reference_union.py >> prepare4.log 2>> dryrun4.err; rc=$?
log union end ", \"exit\": $rc"
tail -c 3000 prepare4.log
exit "$rc"
