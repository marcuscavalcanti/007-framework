"""AMENDMENT-2: freeze_pilot.py on the pinned v1.7.0 code, with the floor written in PREREG-PILOT (max(2.198, c_pilot)) and two
readings: the primary leaves out the tasks in reference-failed.json and decides go / no-go; the secondary keeps every pooled task
and never decides. Everything else is freeze_pilot.py. No model.
Usage: python3 -I -B freeze_pilot_v2.py [results_dir out_dir]   (defaults: results/ and this directory)"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script directory out
import pinned  # noqa: E402

lab = pinned.load()
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "public-replay-20261105" / "gojson-topup"))
import analyze_topup as A  # noqa: E402  its own `import effort_lab` finds the pinned module already loaded

pinned.check_loaded()
RESULTS, OUT = (Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()) if len(sys.argv) == 3 else (HERE / "results", HERE)
TASKS = HERE / "tasks"
SEED, MARGIN, ATTEMPTS, FLOOR_DECLARED = 20261110, .05, 8, 2.198


def frozen_reach(rows):
    """build_topup's rule: hidden tests not in the baseline that some valid attempt passed."""
    def tests(task, name):
        return json.loads((TASKS / task / name).read_text())
    return {t: sorted({k for c, _ in cells for k in tests(t, "hidden.json") if k != "__module__" and k not in set(tests(t, "baseline.json"))
                       and any(x["acceptance_outcomes"].get(k) == "pass" for x, _ in cells)})
            for t, cells in lab.reach_rates(rows, TASKS).items()}


def freeze(rows):
    reach = {t: v for t, v in frozen_reach(rows).items() if v}
    A.TASKS, A.REACH = TASKS, reach
    noise = A.tau2(rows)
    lab.GATES["draws"] = 100_000
    pilot_floor = lab.proven_critical(rows, TASKS, A.LOW, A.REF, SEED, margin=MARGIN, reach=reach, attempts=ATTEMPTS)
    floor = max(FLOOR_DECLARED, math.inf if pilot_floor is None else pilot_floor)
    tau2 = max([0.0] + [v for v in (noise["tau2_moments"], noise["tau2_covariance"]) if v is not None])
    n80 = math.ceil((tau2 + noise["sigma2"] * 2 / ATTEMPTS) * ((floor + 0.8416) / MARGIN) ** 2) if math.isfinite(floor) else None
    pilot = lab.paired_interval(lab.reachable_diffs(rows, TASKS, A.LOW, A.REF, reach=reach))
    return reach, {"decision": "GO" if n80 is not None and len(reach) >= n80 else "NO-GO", "reaching_tasks": len(reach),
                   "n80_if_equal": n80, "tau2_used": tau2, "noise": noise, "critical_floor": floor, "pilot_floor": pilot_floor,
                   "cells_valid": len(rows), "pilot_mean_never_deciding": {k: pilot[k] for k in ("tasks", "mean", "ci95")}}


def main():
    failed = set(json.loads((HERE / "reference-failed.json").read_text()))
    every = [r for r in lab.load_cells(RESULTS) if r["valid"] is True]
    reach, primary = freeze([r for r in every if r["task"] not in failed])
    _, secondary = freeze(every)
    (OUT / "frozen-reach.json").write_text(json.dumps(reach, indent=1, sort_keys=True))
    (OUT / "critical-floor.json").write_text(json.dumps({"critical_floor": primary["critical_floor"], "pilot_floor": primary["pilot_floor"],
                                                         "declared_floor": FLOOR_DECLARED, "margin": MARGIN, "attempts_per_arm": ATTEMPTS,
                                                         "draws": 100_000, "seed": SEED, "code_commit": pinned.COMMIT}, indent=1))
    summary = {"decision": primary["decision"], "primary": primary, "reference_failed_left_out": sorted(failed),
               "secondary_every_pooled_task_never_deciding": secondary}
    (OUT / "pilot-summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
