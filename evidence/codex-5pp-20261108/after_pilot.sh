#!/bin/sh
# AMENDMENT-5: what the pilot's decision leads to, fixed before the pilot. GO: the confirmatory run (its block 1 also serves PREREG-B;
# if block 1 does not complete, block B runs instead). NO-GO: block B. NO-INSTRUMENT: nothing is dispatched. Then the robustness
# re-grades of the confirmatory cells (serial with the embedded evaluator, and with the v1.7.0 evaluator), each at one job.
cd "$(dirname "$0")" || exit 1
D=$(python3 -I -c 'import json; print(json.load(open("pilot-decision.json"))["decision"])') || exit 1
echo "{\"after_pilot\": \"$D\", \"at\": \"$(date -u +%FT%TZ)\"}" >> after.log
case "$D" in
  NO-INSTRUMENT) exit 0 ;;
  NO-GO) python3 -I -B build_b.py >> after.log 2>&1 && sh ./run_b.sh >> after.log 2>&1; exit $? ;;
  GO)
    python3 -I -B build_confirm.py >> after.log 2>&1 || exit 1
    sh ./run_confirm.sh >> after.log 2>&1; rc=$?
    if [ -f confirm-results-look1.json ] && [ "$rc" = 0 ]; then
      python3 -I -B -W ignore analyze_b.py confirm-results > b.out 2>> after.log
    else
      python3 -I -B build_b.py >> after.log 2>&1 && sh ./run_b.sh >> after.log 2>&1
    fi
    if [ -f confirm-results-look2.json ]; then
      caffeinate -i python3 -I -B regrade_serial.py confirm-set.json confirm-results confirm-serial frozen-reach.json >> after.log 2>&1
      caffeinate -i python3 -I -B regrade_serial.py confirm-set.json confirm-results confirm-pinned frozen-reach.json --evaluator pinned >> after.log 2>&1
      for d in confirm-serial confirm-pinned; do python3 -I -B -W ignore analyze_confirm.py 2 "$d" > "$d.out" 2>> after.log; done
    fi ;;
esac
