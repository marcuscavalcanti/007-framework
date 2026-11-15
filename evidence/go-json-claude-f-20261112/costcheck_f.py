"""F-1 in-flight cost marker: after the first 40 cells, project the run's cost by arm (mean medium cost x 82 + mean xhigh cost x 82)
from costs only, never grades. Above US$360 (the US$400 cap less the US$20 reserve of each of the 2 cells in flight, where the
runner stops dispatching), or with an arm that has no cell yet, it writes HOLD.json and exits 3. A hold is terminal: the study reads
NO-BUDGET and nothing is redone. A pass writes MARKER.json, and run_f.sh never runs the marker again. A cell with no measured cost
counts at the runner's US$20 reserve, so two such cells among the first 40 hold the run (about US$256 + 2 x 82 x 20 / 20).
Usage: python3 -I -B costcheck_f.py"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinned_f  # noqa: E402

lab = pinned_f.load()
HERE = Path(__file__).resolve().parent
HOLD_ABOVE, PER_ARM, RESERVE = 360.0, 82, 20.0


def main():
    results = HERE / "results"
    costs = {"medium": [], "xhigh": []}
    for r in lab.load_cells(results):
        if r.get("failure_class") == "provider-rate-limit":
            continue
        value = lab.cost_of(results, r["cell"], r)
        costs[r["arm"]].append(value if isinstance(value, (int, float)) else RESERVE)
    projection = sum(sum(v) / len(v) * PER_ARM for v in costs.values()) if all(costs.values()) else None
    report = {"at": datetime.now(timezone.utc).isoformat(), "cells": {a: len(v) for a, v in costs.items()},
              "spent": round(sum(map(sum, costs.values())), 2), "projection_usd": projection, "hold_above_usd": HOLD_ABOVE}
    print(json.dumps({"costcheck": report}))
    if projection is None or projection > HOLD_ABOVE:
        (HERE / "HOLD.json").write_text(json.dumps(report, indent=1))
        return 3
    (HERE / "MARKER.json").write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
