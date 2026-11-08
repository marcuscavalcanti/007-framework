"""PREREG-PILOT: after the pilot and before any confirmatory attempt, fix what the confirmatory run needs. No model.
- Frozen reach: per task, hidden tests red at base that some valid pilot attempt passed, either arm. Reaching tasks: non-empty.
- Noise on that reach (analyze_topup.tau2): sigma2 within arm per attempt; tau2 by moments and by odd/even replicate covariance.
- Floor: max(2.198, the go-json value at 5 points and 8 attempts per arm, and effort_lab.proven_critical on the pilot attempts at
  5 points and 8 attempts per arm, 100,000 draws, seed 20261110).
- Go/no-go: tasks needed for 80% power to prove 5 points at 8 attempts per arm when the arms are equal,
  n80 = (tau2 + sigma2 / 4) * ((floor + 0.8416) / 0.05) ** 2, with tau2 the larger estimate (at least 0).
  GO when reaching tasks >= n80; otherwise NO-GO and no confirmatory run is proposed.
- The pilot's mean difference is reported and never used for go/no-go. Pilot attempts never enter the confirmatory analysis.
Usage: python3 -I -B freeze_pilot.py"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "public-replay-20261105" / "gojson-topup"))
import analyze_topup as A  # noqa: E402

lab = A.lab
RESULTS, TASKS, OUT = HERE / "results", HERE / "tasks", HERE
SEED, MARGIN, ATTEMPTS, GOJSON_FLOOR = 20261110, .05, 8, 2.197566414978024


def frozen_reach(rows):
    """build_topup's rule: hidden tests not in the baseline that some valid attempt passed."""
    def tests(task, name):
        return json.loads((TASKS / task / name).read_text())
    return {t: sorted({k for c, _ in cells for k in tests(t, "hidden.json") if k != "__module__" and k not in set(tests(t, "baseline.json"))
                       and any(x["acceptance_outcomes"].get(k) == "pass" for x, _ in cells)})
            for t, cells in lab.reach_rates(rows, TASKS).items()}


def main():
    rows = [r for r in lab.load_cells(RESULTS) if r["valid"] is True]
    reach = {t: v for t, v in frozen_reach(rows).items() if v}
    A.TASKS, A.REACH = TASKS, reach
    noise = A.tau2(rows)
    lab.GATES["draws"] = 100_000
    pilot_floor = lab.proven_critical(rows, TASKS, A.LOW, A.REF, SEED, margin=MARGIN, reach=reach, attempts=ATTEMPTS)
    floor = max(GOJSON_FLOOR, math.inf if pilot_floor is None else pilot_floor)
    tau2 = max([0.0] + [v for v in (noise["tau2_moments"], noise["tau2_covariance"]) if v is not None])
    n80 = math.ceil((tau2 + noise["sigma2"] * 2 / ATTEMPTS) * ((floor + 0.8416) / MARGIN) ** 2) if math.isfinite(floor) else None
    pilot = lab.paired_interval(lab.reachable_diffs(rows, TASKS, A.LOW, A.REF, reach=reach))
    decision = "GO" if n80 is not None and len(reach) >= n80 else "NO-GO"
    (OUT / "frozen-reach.json").write_text(json.dumps(reach, indent=1, sort_keys=True))
    (OUT / "critical-floor.json").write_text(json.dumps({"critical_floor": floor, "pilot_floor": pilot_floor, "gojson_floor": GOJSON_FLOOR,
                                                         "margin": MARGIN, "attempts_per_arm": ATTEMPTS, "draws": 100_000, "seed": SEED}, indent=1))
    summary = {"decision": decision, "reaching_tasks": len(reach), "n80_if_equal": n80, "tau2_used": tau2, "noise": noise,
               "cells_valid": len(rows), "pilot_mean_never_deciding": {k: pilot[k] for k in ("tasks", "mean", "ci95")}}
    (OUT / "pilot-summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
