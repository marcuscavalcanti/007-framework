"""After look 2, not pre-registered, never deciding: tau^2 bootstrap upper bounds, the look-1/look-2 split, per-arm descriptives,
and what a 3-point verdict would need at the observed noise. Usage: python3 -I -B post_hoc.py"""
import json, math, random, statistics, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_topup as A  # noqa: E402
lab = A.lab
every = lab.load_cells(HERE / "results")
rows = [r for r in every if r["valid"] is True]
tasks = sorted(lab.reach_rates(rows, A.TASKS, A.REACH))
rng = random.Random(A.SEED)
boot = []
for _ in range(2000):
    pick = [rng.choice(tasks) for _ in tasks]
    sample = [dict(r, task=f"{r['task']}#{i}") for i, t in enumerate(pick) for r in rows if r["task"] == t]
    reach = {f"{t}#{i}": A.REACH[t] for i, t in enumerate(pick)}
    old = A.REACH
    A.REACH = reach
    try:
        tt = A.tau2([dict(r) for r in sample])
    finally:
        A.REACH = old
    boot.append((tt["tau2_moments"], tt["tau2_covariance"]))
boot.sort(key=lambda b: b[0]); up_m = boot[int(.95 * len(boot))][0]
cov = sorted(b[1] for b in boot if b[1] is not None); up_c = cov[int(.95 * len(cov))]
half = {f"replicates {a}-{b}": lab.paired_interval(lab.reachable_diffs([r for r in rows if a <= r["replicate"] <= b], A.TASKS, A.LOW, A.REF, reach=A.REACH)) for a, b in ((1, 4), (5, 8))}
arm = {a: {"cells": sum(r["arm"] == a for r in rows), "accepted": sum(r["accepted"] for r in rows if r["arm"] == a),
           "median_agent_wall_s": statistics.median(r["agent_wall_s"] for r in rows if r["arm"] == a),
           "median_cost_usd": statistics.median(r["cost_usd"] for r in rows if r["arm"] == a),
           "total_cost_usd": sum(r["cost_usd"] for r in rows if r["arm"] == a)} for a in (A.LOW, A.REF)}
t = A.tau2(rows)
need = lambda tau2, delta: math.ceil(((1.96 + lab.Z80) * math.sqrt(max(tau2, 0) + 2 * t["sigma2"] / 8) / (.03 + delta)) ** 2)
print(json.dumps({"tau2_point": {"moments": t["tau2_moments"], "covariance": t["tau2_covariance"]}, "tau2_upper95_bootstrap": {"moments": up_m, "covariance": up_c},
                  "halves": {k: {"mean": v["mean"], "ci95": v["ci95"]} for k, v in half.items()}, "arms": arm,
                  "tasks_for_80pct_at_8_per_arm": {f"tau2={x:.4f}, true diff {d:+.3f}": need(x, d) for x in (t["tau2_moments"], t["tau2_covariance"]) for d in (0.0, -0.009)}}, indent=1))
