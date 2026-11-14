"""PREREG-F analysis, one look. No model. Usage: python3 -I -B analyze_f.py [results_dir out.json]
Verdict at m = 0.20, readings P and B (the worse decides): KILL if a reading's 95% t interval lies wholly below -0.20; PROVEN if
(mean + 0.20)/se beats max(floor, c) in both readings (floor from critical-floor.json, c simulated from this run at 0.20 with 2
attempts per arm, 100,000 draws); NO-INFORMATION under 8 signal tasks; else NOT-PROVEN.
R = cost per accepted change at medium / at xhigh over every dispatched cell except provider refusals (failure_class
provider-rate-limit); costs as the run reads them; a cell with none counts at its US$10 reserve; task bootstrap, 10,000 draws.
T1: serial re-grade discordance <= 2% (serial/regrade.json) and A/A within 3-8% (aa.json).
Answer: PAYS (PROVEN, R upper < 1), DOES-NOT-PAY (KILL), PROVEN-NOT-ECONOMIC (PROVEN, R reaches 1), else not decisive.
F-1, fixed before any F attempt:
- A STOP.json in the results reads NO-STOPPED; a HOLD.json (cost marker) reads NO-BUDGET. Neither is analysed further.
- Missing-data guard. L0 is the reading above (cells without a valid result are left out). L2 takes the plan (41 tasks x 2
  replicates x 2 arms) and imputes every planned cell without a usable valid result (invalid of any class, refused by the provider,
  never dispatched, or valid with unreadable test outcomes) as the worst case for medium's mean: medium fails every reachable test,
  xhigh passes every one. That restores the B pairs; L2's own critical value is simulated again (floor kept). PROVEN needs PROVEN in
  L0 and in L2, in P and B; L0 PROVEN with L2 short of it reads NOT-PROVEN, labelled "not decisive by missing data". KILL follows
  L0 alone. L1 (invalid cells with readable outcomes, graded as observed) is only reported.
- PAYS also needs the worst-case R's upper bound below 1: an invalid xhigh cell counts as accepted, and a cell with no measured cost
  counts at the runner's US$20 reserve at medium and at zero at xhigh."""
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinned_f  # noqa: E402

lab = pinned_f.load()
pinned_f.check_loaded()
HERE = Path(__file__).resolve().parent
LOW, REF, M, SEED, RESERVE, DRAWS = "medium", "xhigh", .20, 20261112, 10.0, 10_000
WORST_RESERVE = {LOW: 20.0, REF: 0.0}
ORDER = ["KILL", "NO-INFORMATION", "NOT-PROVEN", "PROVEN"]
lab.GATES["draws"] = 100_000


def paired(rows):
    arms = {}
    for r in rows:
        arms.setdefault((r["task"], r["replicate"]), set()).add(r["arm"])
    return [r for r in rows if arms[(r["task"], r["replicate"])] == {LOW, REF}]


def cost(r, worst=False):
    value = lab.cost_of(r["_dir"], r["cell"], r)
    return value if isinstance(value, (int, float)) else WORST_RESERVE[r["arm"]] if worst else RESERVE


def ratio(cells, worst=False):
    def accepted(r):
        if r.get("valid") is not True:
            return worst and r["arm"] == REF  # worst case: an invalid xhigh cell counts as accepted
        return bool(r.get("accepted"))

    def per(arm):
        c = sum(cost(r, worst) for r in cells if r["arm"] == arm)
        a = sum(accepted(r) for r in cells if r["arm"] == arm)
        return c / a if a else math.inf
    low, ref = per(LOW), per(REF)
    return low / ref if math.isfinite(low) and math.isfinite(ref) and ref > 0 else math.inf


def usable(r):
    return r is not None and r["valid"] is True and not r.get("outcomes_unreadable")


def planned_l2(every, planned, reach):
    """L2: each planned cell keeps its usable valid result, or is imputed as medium's worst case, with the reason recorded."""
    by = {(r["task"], r["replicate"], r["arm"]): r for r in every}
    out, reasons = [], {}
    for task, rep, arm in planned:
        r = by.get((task, rep, arm))
        if usable(r):
            out.append(r)
            continue
        why = "absent" if r is None else "refused" if r.get("failure_class") == "provider-rate-limit" else \
            "unreadable" if r["valid"] is True else "invalid"
        reasons[why] = reasons.get(why, 0) + 1
        tests = reach.get(task, [])
        out.append({"task": task, "replicate": rep, "arm": arm, "cell": f"{task}-r{rep:02d}-{arm}", "valid": True, "imputed": why,
                    "acceptance_outcomes": {k: "fail" if arm == LOW else "pass" for k in tests}})
    return out, reasons


def reading(cells, reach, floor, critical=True):
    diffs = lab.reachable_diffs(cells, HERE / "tasks", LOW, REF, reach=reach)
    s = lab.paired_interval(diffs)
    e = {"tasks": s["tasks"], "mean": s["mean"], "ci95": s["ci95"], "statistic": lab.studentized(diffs, M) if s["tasks"] > 1 else None}
    if s["tasks"] < lab.GATES["min_signal_tasks"] or s["ci95"] is None:
        e["verdict"] = "NO-INFORMATION"
    elif s["ci95"][1] < -M:
        e["verdict"] = "KILL"
    elif critical:
        c = lab.proven_critical(cells, HERE / "tasks", LOW, REF, SEED, margin=M, reach=reach)
        e.update(critical_own=c, critical=max(floor, math.inf if c is None else c))
        e["verdict"] = "PROVEN" if e["statistic"] > e["critical"] else "NOT-PROVEN"
    else:
        e["verdict"] = "not-computed"  # the critical value is simulated only where it can change the answer
    return e


def boot(by, tasks, worst):
    rng, draws = random.Random(SEED), []
    for _ in range(DRAWS):
        draws.append(ratio([r for t in (rng.choice(tasks) for _ in tasks) for r in by[t]], worst))
    draws.sort()
    return [draws[int(.025 * DRAWS)], draws[int(.975 * DRAWS) - 1]]


def main():
    results = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "results"
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else HERE / "f-result.json"
    for marker, answer in (((results / "STOP.json"), "NO-STOPPED"), ((HERE / "HOLD.json"), "NO-BUDGET")):
        if marker.is_file():
            out.write_text(json.dumps({"verdict": answer, "answer": answer, "marker": marker.name, "detail": json.loads(marker.read_text())}, indent=1))
            print(json.dumps({"verdict": answer, "answer": answer}))
            return 0
    reach = json.loads((HERE / "frozen-reach.json").read_text())
    floor = json.loads((HERE / "critical-floor.json").read_text())["critical_floor"]
    config = json.loads((HERE / "f-set.json").read_text())
    planned = [(t["id"], rep, arm) for t, rep, arm in lab.plan(config, 2)]
    every = [{**r, "_dir": results} for r in lab.load_cells(results)]
    dispatched = [r for r in every if r.get("failure_class") != "provider-rate-limit"]
    rows = [r for r in every if r["valid"] is True]
    readings = {name: reading(cells, reach, floor) for name, cells in (("P", rows), ("B", paired(rows)))}
    verdict = min((e["verdict"] for e in readings.values()), key=ORDER.index)
    l2, reasons = planned_l2(every, planned, reach)
    invalid = [r for r in every if not usable(r)]
    guard = {"planned": len(planned), "usable": len(planned) - sum(reasons.values()), "imputed_in_L2": reasons,
             "unusable_cells": [{"cell": r["cell"], "arm": r["arm"], "task": r["task"], "failure_class": r.get("failure_class"),
                                 "agent_wall_s": r.get("agent_wall_s")} for r in invalid],
             "watch_GJ-A9CFAE7F_medium": [r["cell"] for r in invalid if r["task"] == "GJ-A9CFAE7F" and r["arm"] == LOW]}
    if reasons:
        guard["L2"] = {name: reading(cells, reach, floor, critical=verdict == "PROVEN") for name, cells in (("P", l2), ("B", paired(l2)))}
        l1 = [r for r in every if r.get("failure_class") != "provider-rate-limit" and not r.get("outcomes_unreadable")]
        guard["L1_reported_only"] = {name: reading([{**r, "valid": True} for r in cells], reach, floor, critical=False)
                                     for name, cells in (("P", l1), ("B", paired(l1)))}
        if verdict == "PROVEN" and any(e["verdict"] != "PROVEN" for e in guard["L2"].values()):
            verdict, guard["label"] = "NOT-PROVEN", "not decisive by missing data"
    tasks = sorted({r["task"] for r in dispatched})
    by = {t: [r for r in dispatched if r["task"] == t] for t in tasks}
    r_ci, r_ci_worst = boot(by, tasks, False), boot(by, tasks, True)
    regrade = json.loads((HERE / "serial" / "regrade.json").read_text()) if (HERE / "serial" / "regrade.json").is_file() else {}
    aa = json.loads((HERE / "aa.json").read_text()) if (HERE / "aa.json").is_file() else {}
    t1 = regrade.get("discordance") is not None and regrade["discordance"] <= .02 and aa.get("within_range") is True
    answer = ("PAYS" if max(r_ci[1], r_ci_worst[1]) < 1 else "PROVEN-NOT-ECONOMIC") if verdict == "PROVEN" else "DOES-NOT-PAY" if verdict == "KILL" else verdict
    result = {"verdict": verdict, "answer": answer if t1 else "NO-INSTRUMENT", "t1": {"discordance": regrade.get("discordance"),
              "aa_ci_excludes_zero": aa.get("ci_excludes_zero"), "passed": t1}, "margin": M, "floor": floor, "readings": readings,
              "missing_data_guard": guard, "cost_ratio_worst": ratio(dispatched, True), "cost_ratio_worst_ci95": r_ci_worst,
              "cost_ratio": ratio(dispatched), "cost_ratio_ci95": r_ci, "cells": len(every), "valid": len(rows),
              "refused": len(every) - len(dispatched), "invalid_per_arm": {a: sum(r["arm"] == a and r["valid"] is not True for r in dispatched) for a in (LOW, REF)}}
    out.write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps({k: result[k] for k in ("verdict", "answer", "t1", "cost_ratio", "cost_ratio_ci95", "cells", "valid", "refused")}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
