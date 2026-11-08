"""PREREG-CLAUDE analysis, fixed before any paid attempt. The Codex top-up's pre-registered functions (gojson-topup/
analyze_topup.py, unchanged) with this run's constants: arms medium vs xhigh, margin 10 points, this run's floor, one look over
replicates 1-2. Sequence: manipulation -> time (median saving >= 25%, task-bootstrap 95% interval above 0) -> same change:
KILL if a reading's 95% t interval lies wholly below -10 points; PROVEN if (mean + 10 points)/se beats max(floor, the run's own
proven_critical at a 10-point margin, 100,000 draws) in both readings P and B; else NOT-PROVEN. Usage: python3 -I -B analyze_claude.py"""
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gojson-topup"))
import analyze_topup as A  # noqa: E402

A.LOW, A.REF, A.M = "medium", "xhigh", .10
A.FLOOR = json.loads((HERE / "critical-floor.json").read_text())["critical_floor"]
lab = A.lab


def same_change(rows, reach=A.REACH):
    """analyze_topup.same_change at look 2, with the margin passed to proven_critical (that function leaves it at 3 points)."""
    import math
    diffs = lab.reachable_diffs(rows, A.TASKS, A.LOW, A.REF, reach=reach)
    s = lab.paired_interval(diffs)
    out = {"tasks": s["tasks"], "mean": s["mean"], "ci95": s["ci95"], "statistic": lab.studentized(diffs, A.M) if s["tasks"] > 1 else None}
    if s["tasks"] < lab.GATES["min_signal_tasks"] or s["ci95"] is None:
        return {**out, "verdict": "NO-INFORMATION"}
    if s["ci95"][1] < -A.M:
        return {**out, "verdict": "KILL"}
    fresh = lab.proven_critical(rows, A.TASKS, A.LOW, A.REF, A.SEED, A.M, reach=reach)
    critical = max(A.FLOOR, math.inf if fresh is None else fresh)
    return {**out, "critical_fresh": fresh, "critical_floor": A.FLOOR, "critical": critical, "verdict": "PROVEN" if out["statistic"] > critical else "NOT-PROVEN"}


def main():
    every = lab.load_cells(HERE / "results")
    rows = [r for r in every if r["valid"] is True]
    sequence = {"manipulation": A.reasoning(rows), "time": A.time_gate(rows)}
    readings = {"P": rows, "B": A.paired(rows)}
    if all(g["passed"] for g in sequence.values()):
        primary = {name: same_change(r) for name, r in readings.items()}
        decision = min((p["verdict"] for p in primary.values()), key=A.ORDER.index)
    else:
        primary, decision = None, "STOP-SEQUENCE"
    secondary = {
        "product_reach": {name: same_change(r, reach=None) for name, r in readings.items()},
        "solvable_acceptance": lab.paired_interval({t: statistics.fmean(r["accepted"] for r in rows if r["task"] == t and r["arm"] == A.LOW)
                                                     - statistics.fmean(r["accepted"] for r in rows if r["task"] == t and r["arm"] == A.REF)
                                                     for t in {r["task"] for r in rows if r["accepted"]}
                                                     if {r["arm"] for r in rows if r["task"] == t} == {A.LOW, A.REF}}),
        "tau2": A.tau2(rows),
        "invalid_per_arm": {a: sum(r["arm"] == a and r["valid"] is not True for r in every) for a in (A.LOW, A.REF)},
        "failure_classes": sorted({r.get("failure_class") for r in every}),
        "median_cost_usd": {a: statistics.median(r["cost_usd"] for r in rows if r["arm"] == a) for a in (A.LOW, A.REF)},
        "requested": sorted({(r.get("requested_model"), r.get("requested_effort"), r["arm"]) for r in every}),
    }
    print(json.dumps({"cells_valid": len(rows), "decision": decision, "sequence": sequence, "primary": primary, "secondary": secondary}, indent=1, default=str))


if __name__ == "__main__":
    main()
