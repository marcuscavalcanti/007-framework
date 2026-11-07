#!/bin/sh
# PREREG-TOPUP: one look = 4 replicate blocks of 82 attempts, a planned pause between blocks; then the look's analysis.
# Usage: sh run_look.sh 1|2
cd "$(dirname "$0")" || exit 1
LOOK=$1
for block in 1 2 3 4; do
  echo "{\"look\": $LOOK, \"block\": $block, \"start\": \"$(date -u +%FT%TZ)\", \"meter\": $(python3 -I meter_now.py)}" >> run.log
  caffeinate -i python3 -B ../../../repo/scripts/effort_lab.py run --set topup-set.json --out results --replicates 8 --jobs 4 \
    --max-calls 82 --max-usd 250 --stop-usd 2 --max-invalid 20 > block.out 2>> run.err
  cat block.out >> run.log
  grep -q '"stop": "call-budget"' block.out || { echo "{\"halt\": \"not a planned pause\", \"at\": \"$(date -u +%FT%TZ)\"}" >> run.log; break; }
done
echo "{\"look\": $LOOK, \"end\": \"$(date -u +%FT%TZ)\", \"meter\": $(python3 -I meter_now.py)}" >> run.log
python3 -I -B analyze_topup.py "$LOOK" > "look$LOOK.json" 2>> run.err
