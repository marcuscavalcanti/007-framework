"""PREREG-F analysis, one look. No model. Usage: python3 -I -B analyze_f.py [results_dir out.json]
Verdict at m = 0.20, readings P and B (the worse decides): KILL if a reading's 95% t interval lies wholly below -0.20; PROVEN if
(mean + 0.20)/se beats max(floor, c) in both readings (floor from critical-floor.json, c simulated from this run at 0.20 with 2
attempts per arm, 100,000 draws); NO-INFORMATION under 8 signal tasks; else NOT-PROVEN.
R = cost per accepted change at medium / at xhigh over every dispatched cell except provider refusals (failure_class
provider-rate-limit); costs as the run reads them; a cell with none counts at its US$10 reserve; task bootstrap, 10,000 draws.
T1: serial re-grade discordance <= 2% (serial/regrade.json) and A/A within 3-8% (aa.json).
Answer: PAYS (PROVEN, R upper < 1), DOES-NOT-PAY (KILL), PROVEN-NOT-ECONOMIC (PROVEN, R reaches 1), else not decisive."""
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
lab.GATES["draws"] = 100_000


def paired(rows):
    arms = {}
    for r in rows:
        arms.setdefault((r["task"], r["replicate"]), set()).add(r["arm"])
    return [r for r in rows if arms[(r["task"], r["replicate"])] == {LOW, REF}]


def cost(r):
    value = lab.cost_of(r["_dir"], r["cell"], r)
    return value if isinstance(value, (int, float)) else RESERVE


def ratio(cells):
    def per(arm):
        c = sum(cost(r) for r in cells if r["arm"] == arm)
        a = sum(r.get("valid") is True and bool(r.get("accepted")) for r in cells if r["arm"] == arm)
        return c / a if a else math.inf
    low, ref = per(LOW), per(REF)
    return low / ref if math.isfinite(low) and math.isfinite(ref) and ref > 0 else math.inf


def main():
    results = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "results"
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else HERE / "f-result.json"
    reach = json.loads((HERE / "frozen-reach.json").read_text())
    floor = json.loads((HERE / "critical-floor.json").read_text())["critical_floor"]
    every = [{**r, "_dir": results} for r in lab.load_cells(results)]
    dispatched = [r for r in every if r.get("failure_class") != "provider-rate-limit"]
    rows = [r for r in every if r["valid"] is True]
    readings = {}
    for name, cells in (("P", rows), ("B", paired(rows))):
        diffs = lab.reachable_diffs(cells, HERE / "tasks", LOW, REF, reach=reach)
        s = lab.paired_interval(diffs)
        e = {"tasks": s["tasks"], "mean": s["mean"], "ci95": s["ci95"], "statistic": lab.studentized(diffs, M) if s["tasks"] > 1 else None}
        if s["tasks"] < lab.GATES["min_signal_tasks"] or s["ci95"] is None:
            e["verdict"] = "NO-INFORMATION"
        elif s["ci95"][1] < -M:
            e["verdict"] = "KILL"
        else:
            c = lab.proven_critical(cells, HERE / "tasks", LOW, REF, SEED, margin=M, reach=reach)
            e.update(critical_own=c, critical=max(floor, math.inf if c is None else c))
            e["verdict"] = "PROVEN" if e["statistic"] > e["critical"] else "NOT-PROVEN"
        readings[name] = e
    verdict = min((e["verdict"] for e in readings.values()), key=["KILL", "NO-INFORMATION", "NOT-PROVEN", "PROVEN"].index)
    tasks = sorted({r["task"] for r in dispatched})
    by = {t: [r for r in dispatched if r["task"] == t] for t in tasks}
    rng, draws = random.Random(SEED), []
    for _ in range(DRAWS):
        draws.append(ratio([r for t in (rng.choice(tasks) for _ in tasks) for r in by[t]]))
    draws.sort()
    r_ci = [draws[int(.025 * DRAWS)], draws[int(.975 * DRAWS) - 1]]
    regrade = json.loads((HERE / "serial" / "regrade.json").read_text()) if (HERE / "serial" / "regrade.json").is_file() else {}
    aa = json.loads((HERE / "aa.json").read_text()) if (HERE / "aa.json").is_file() else {}
    t1 = regrade.get("discordance") is not None and regrade["discordance"] <= .02 and aa.get("within_range") is True
    answer = ("PAYS" if r_ci[1] < 1 else "PROVEN-NOT-ECONOMIC") if verdict == "PROVEN" else "DOES-NOT-PAY" if verdict == "KILL" else verdict
    result = {"verdict": verdict, "answer": answer if t1 else "NO-INSTRUMENT", "t1": {"discordance": regrade.get("discordance"),
              "aa_ci_excludes_zero": aa.get("ci_excludes_zero"), "passed": t1}, "margin": M, "floor": floor, "readings": readings,
              "cost_ratio": ratio(dispatched), "cost_ratio_ci95": r_ci, "cells": len(every), "valid": len(rows),
              "refused": len(every) - len(dispatched), "invalid_per_arm": {a: sum(r["arm"] == a and r["valid"] is not True for r in dispatched) for a in (LOW, REF)}}
    out.write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps({k: result[k] for k in ("verdict", "answer", "t1", "cost_ratio", "cost_ratio_ci95", "cells", "valid", "refused")}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
