"""PREREG-TOPUP analysis, fixed before any paid cell. Fresh cells only, from `results/`.
Usage: python3 -I -B analyze_topup.py 1|2      (look 1 = replicates 1-4, look 2 = replicates 1-8)
Fixed sequence, checked at both looks: (i) manipulation: median reasoning tokens lower in medium; (ii) time: median agent-time
saving >= 25 % with a task-bootstrap 95 % interval above 0; (iii) same change, primary: per-task medium - high pass share on the
frozen reach set (frozen-reach.json), readings P (valid cells) and B (task-replicate pairs with both arms valid), the worse
decides. Look 1: KILL if a reading's 95 % t interval is wholly below -3 pp; FUTILITY if (mean + 3 pp)/se < 0.5 in the worse
reading; else CONTINUE; never PROVEN. Look 2: PROVEN if (mean + 3 pp)/se beats max(critical floor, the fresh cells' own
proven_critical at 100,000 draws) in both readings; KILL as at look 1; else NOT-PROVEN. Secondary readings never decide.
"""
import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "repo" / "scripts"))
import effort_lab as lab  # noqa: E402

TASKS, LOW, REF, M, SEED = HERE / "tasks", "medium", "high", .03, 20261106
REACH = json.loads((HERE / "frozen-reach.json").read_text())
FLOOR = json.loads((HERE / "critical-floor.json").read_text())["critical_floor"]
ORDER = ["KILL", "NO-INFORMATION", "FUTILITY", "NOT-PROVEN", "CONTINUE", "PROVEN"]  # worst first
lab.GATES["draws"] = 100_000


def paired(rows):
    arms = {}
    for r in rows:
        arms.setdefault((r["task"], r["replicate"]), set()).add(r["arm"])
    return [r for r in rows if arms[(r["task"], r["replicate"])] == {LOW, REF}]


def median_saving(rows, key, tasks):
    by = {t: [r for r in rows if r["task"] == t] for t in tasks}
    values = lambda arm: [r[key] for t in tasks for r in by[t] if r["arm"] == arm and isinstance(r.get(key), (int, float))]
    return 1 - statistics.median(values(LOW)) / statistics.median(values(REF))


def time_gate(rows):
    tasks = sorted({r["task"] for r in rows})
    rng = random.Random(SEED)
    boot = sorted(median_saving(rows, "agent_wall_s", [rng.choice(tasks) for _ in tasks]) for _ in range(10_000))
    point, ci = median_saving(rows, "agent_wall_s", tasks), [boot[249], boot[9749]]
    return {"saving": point, "ci95": ci, "passed": point >= lab.GATES["min_reduction"] and ci[0] > 0}


def reasoning(rows):
    med = {a: statistics.median((r.get("usage") or {}).get("reasoning_output_tokens", 0) for r in rows if r["arm"] == a) for a in (LOW, REF)}
    return {**med, "passed": med[LOW] < med[REF]}


def same_change(rows, look, reach=REACH):
    diffs = lab.reachable_diffs(rows, TASKS, LOW, REF, reach=reach)
    s = lab.paired_interval(diffs)
    out = {"tasks": s["tasks"], "mean": s["mean"], "ci95": s["ci95"], "statistic": lab.studentized(diffs, M) if s["tasks"] > 1 else None}
    if s["tasks"] < lab.GATES["min_signal_tasks"] or s["ci95"] is None:
        return {**out, "verdict": "NO-INFORMATION"}
    if s["ci95"][1] < -M:
        return {**out, "verdict": "KILL"}
    if look == 1:
        return {**out, "verdict": "FUTILITY" if out["statistic"] < .5 else "CONTINUE"}
    fresh = lab.proven_critical(rows, TASKS, LOW, REF, SEED, reach=reach)
    critical = max(FLOOR, math.inf if fresh is None else fresh)
    return {**out, "critical_fresh": fresh, "critical_floor": FLOOR, "critical": critical, "verdict": "PROVEN" if out["statistic"] > critical else "NOT-PROVEN"}


def tau2(rows):
    """Heterogeneity bound on the frozen scale: moments (between-task variance minus noise) and odd-even replicate covariance."""
    rates = lab.reach_rates(rows, TASKS, REACH)
    per = {t: {a: [(c["replicate"], v) for c, v in cells if c["arm"] == a] for a in (LOW, REF)} for t, cells in rates.items()}
    per = {t: p for t, p in per.items() if p[LOW] and p[REF]}
    d = [statistics.fmean(v for _, v in p[LOW]) - statistics.fmean(v for _, v in p[REF]) for p in per.values()]
    groups = [[v for _, v in p[a]] for p in per.values() for a in (LOW, REF) if len(p[a]) > 1]
    s2 = sum(statistics.variance(g) * (len(g) - 1) for g in groups) / sum(len(g) - 1 for g in groups)
    moments = statistics.variance(d) - statistics.fmean(s2 / len(p[LOW]) + s2 / len(p[REF]) for p in per.values())
    half = lambda p, odd: statistics.fmean(v for r, v in p[LOW] if r % 2 == odd) - statistics.fmean(v for r, v in p[REF] if r % 2 == odd)
    both = [p for p in per.values() if all(any(r % 2 == o for r, _ in p[a]) for a in (LOW, REF) for o in (0, 1))]
    cov = statistics.covariance([half(p, 1) for p in both], [half(p, 0) for p in both]) if len(both) > 2 else None
    return {"sigma2": s2, "tau2_moments": moments, "tau2_covariance": cov, "covariance_tasks": len(both), "budget_41_tasks": .0047}


def main():
    look = int(sys.argv[1])
    every = lab.load_cells(HERE / "results")
    rows = [r for r in every if r["valid"] is True and r["replicate"] <= 4 * look]
    sequence = {"manipulation": reasoning(rows), "time": time_gate(rows)}
    readings = {"P": rows, "B": paired(rows)}
    if all(g["passed"] for g in sequence.values()):
        primary = {name: same_change(r, look) for name, r in readings.items()}
        decision = min((p["verdict"] for p in primary.values()), key=ORDER.index)
    else:
        primary, decision = None, "STOP-SEQUENCE"  # an earlier claim failed: the same change is not tested
    timeouts = [{**r, "valid": True} for r in every if r.get("failure_class") == "timeout" and r["replicate"] <= 4 * look]
    secondary = {
        "product_reach": {name: same_change(r, look, reach=None) for name, r in readings.items()},
        "solvable_acceptance": lab.paired_interval({t: statistics.fmean(r["accepted"] for r in rows if r["task"] == t and r["arm"] == LOW)
                                                     - statistics.fmean(r["accepted"] for r in rows if r["task"] == t and r["arm"] == REF)
                                                     for t in {r["task"] for r in rows if r["accepted"]}
                                                     if {r["arm"] for r in rows if r["task"] == t} == {LOW, REF}}),
        "timeouts_as_failures": same_change(rows + timeouts, look) if timeouts else None,
        "tau2": tau2(rows),
        "similarity_to_reference": {a: {"median": statistics.median(v), "over_0_8": sum(x > .8 for x in v)} for a in (LOW, REF)
                                    for v in [[r["line_similarity_diagnostic"] for r in rows if r["arm"] == a and isinstance(r.get("line_similarity_diagnostic"), (int, float))]] if v},
        "invalid_per_arm": {a: sum(r["arm"] == a and r["valid"] is not True for r in every if r["replicate"] <= 4 * look) for a in (LOW, REF)},
        "failure_classes": sorted({r.get("failure_class") for r in every}),
        "requested": sorted({(r.get("requested_model"), r.get("requested_effort"), r["arm"]) for r in every}),
        "settings_sha256": sorted({json.loads((HERE / "results" / f"{r['cell']}.runner.json").read_text()).get("settings_sha256") for r in every
                                   if (HERE / "results" / f"{r['cell']}.runner.json").is_file()}),
    }
    print(json.dumps({"look": look, "cells_valid": len(rows), "decision": decision, "sequence": sequence, "primary": primary, "secondary": secondary},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
