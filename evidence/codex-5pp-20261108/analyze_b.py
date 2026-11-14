"""PREREG-B: does the lower effort pay on this repository? One verdict per eligible repository, at its break-even margin, with the
economic reading. No model. Usage: python3 -I -B analyze_b.py <attempts_dir> [pilot_results_dir out.json]
- Eligible: a pooled repository with at least 8 tasks in the primary freeze's frozen-reach.json.
- Margin m = min(0.20, acceptance at `high` x median cost saving of `medium`), from that repository's valid pilot cells
  (docs/lab.md "Choosing the margin"). m < 0.01: NO-SAVING, reported, never decisive. Costs are read as the run reads them
  (`effort_lab.cost_of`: the cell, else its runner receipt).
- Attempts: fresh, replicates 1-4 per arm, from <attempts_dir> (the confirmatory block 1 after a GO, else block B).
- Verdict, readings P and B, the worse decides: KILL if the 95% t interval lies wholly below -m; PROVEN if (mean + m)/se beats
  max(floor_m, c), floor_m simulated from go-json's top-up cells (replicates 1-4) at m with 4 attempts, c from the repository's own
  cells; fewer than 8 signal tasks: NO-INFORMATION; else NOT-PROVEN.
- Economic reading R = (cost per accepted change at medium) / (same at high), over every dispatched cell; a cell without a cost
  counts at the US$2 reserve only when neither the cell nor its runner receipt has one. Task-bootstrap 95% interval, 10,000 draws, seed 20261114.
- Per repository: PAYS = PROVEN and R's upper bound < 1; DOES-NOT-PAY = KILL; PROVEN-NOT-ECONOMIC = PROVEN with R reaching 1."""
import json
import math
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script directory out
import pinned  # noqa: E402

lab = pinned.load()
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import freeze_pilot_v3 as F  # noqa: E402  imports the hash-checked analyze_topup as F.A

pinned.check_loaded()
A = F.A
LOW, REF, SEED, CAP_M, MIN_M, ATTEMPTS, RESERVE, DRAWS = "medium", "high", 20261114, .20, .01, 4, 2.0, 10_000
TOPUP = HERE.parent / "public-replay-20261105" / "gojson-topup"
lab.GATES["draws"] = 100_000


def cost(r):
    value = lab.cost_of(r["_dir"], r["cell"], r) if "_dir" in r else r.get("cost_usd")
    return value if isinstance(value, (int, float)) else RESERVE


def margin(pilot):
    high = [r for r in pilot if r["arm"] == REF]
    if not high:
        return None, {}
    accepted = statistics.fmean(bool(r.get("accepted")) for r in high)
    prices = {a: [cost(r) for r in pilot if r["arm"] == a and isinstance(lab.cost_of(r["_dir"], r["cell"], r), (int, float))] for a in (LOW, REF)}
    saving = 1 - statistics.median(prices[LOW]) / statistics.median(prices[REF]) if prices[LOW] and prices[REF] else None
    m = min(CAP_M, accepted * saving) if saving is not None else None
    return m, {"acceptance_high": accepted, "cost_saving": saving}


def ratio(cells, tasks):
    def per_accept(arm):
        c = sum(cost(r) for r in cells if r["arm"] == arm and r["task"] in tasks)
        a = sum(r.get("valid") is True and bool(r.get("accepted")) for r in cells if r["arm"] == arm and r["task"] in tasks)
        return c / a if a else math.inf
    low, ref = per_accept(LOW), per_accept(REF)
    return low / ref if math.isfinite(low) and math.isfinite(ref) and ref > 0 else math.inf


def ratio_interval(cells, tasks, rng):
    tasks = sorted(tasks)
    by = {t: [r for r in cells if r["task"] == t] for t in tasks}
    draws = []
    for _ in range(DRAWS):
        pick = [rng.choice(tasks) for _ in tasks]
        sample = [{**r, "task": f"{t}#{i}"} for i, t in enumerate(pick) for r in by[t]]
        draws.append(ratio(sample, {f"{t}#{i}" for i, t in enumerate(pick)}))
    draws.sort()
    return [draws[int(.025 * DRAWS)], draws[int(.975 * DRAWS) - 1]]


def floor_at(m):
    rows = [r for r in lab.load_cells(TOPUP / "results") if r["valid"] is True and r["replicate"] <= ATTEMPTS]
    reach = json.loads((TOPUP / "frozen-reach.json").read_text())
    value = lab.proven_critical(rows, TOPUP / "tasks", LOW, REF, SEED, margin=m, reach=reach, attempts=ATTEMPTS)
    return math.inf if value is None else value


def verdict(rows, reach, m, floor):
    out = {}
    for name, cells in (("P", rows), ("B", A.paired(rows))):
        diffs = lab.reachable_diffs(cells, F.TASKS, LOW, REF, reach=reach)
        s = lab.paired_interval(diffs)
        entry = {"tasks": s["tasks"], "mean": s["mean"], "ci95": s["ci95"], "statistic": lab.studentized(diffs, m) if s["tasks"] > 1 else None}
        if s["tasks"] < lab.GATES["min_signal_tasks"] or s["ci95"] is None:
            entry["verdict"] = "NO-INFORMATION"
        elif s["ci95"][1] < -m:
            entry["verdict"] = "KILL"
        else:
            c = lab.proven_critical(cells, F.TASKS, LOW, REF, SEED, margin=m, reach=reach)
            entry.update(critical_own=c, critical=max(floor, math.inf if c is None else c))
            entry["verdict"] = "PROVEN" if entry["statistic"] > entry["critical"] else "NOT-PROVEN"
        out[name] = entry
    order = ["KILL", "NO-INFORMATION", "NOT-PROVEN", "PROVEN"]
    return min((e["verdict"] for e in out.values()), key=order.index), out


def main():
    attempts = Path(sys.argv[1]).resolve()
    pilot_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else HERE / "results"
    out_path = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else HERE / "b-result.json"
    reach = json.loads((HERE / "frozen-reach.json").read_text())
    repo_of = {t["id"]: t["repo"] for t in json.loads((HERE / "pilot-set.json").read_text())["tasks"]}
    pilot = [{**r, "_dir": pilot_dir} for r in lab.load_cells(pilot_dir) if r["valid"] is True]
    every = [{**r, "_dir": attempts} for r in lab.load_cells(attempts) if r["replicate"] <= ATTEMPTS]
    rng, result = random.Random(SEED), {}
    for repo in sorted({repo_of[t] for t in reach}):
        tasks = {t for t in reach if repo_of[t] == repo}
        entry = {"reaching_tasks": len(tasks), "eligible": len(tasks) >= lab.GATES["min_signal_tasks"]}
        if entry["eligible"]:
            m, inputs = margin([r for r in pilot if repo_of.get(r["task"]) == repo])
            entry.update(margin=m, margin_inputs=inputs)
            if m is None or m < MIN_M:
                entry["answer"] = "NO-SAVING"
            else:
                own_reach = {t: reach[t] for t in tasks}
                rows = [r for r in every if r["valid"] is True and r["task"] in tasks]
                floor = floor_at(m)
                category, readings = verdict(rows, own_reach, m, floor)
                cells = [r for r in every if r["task"] in tasks]
                r_point, r_ci = ratio(cells, tasks), ratio_interval(cells, tasks, rng)
                answer = ("PAYS" if r_ci[1] < 1 else "PROVEN-NOT-ECONOMIC") if category == "PROVEN" else "DOES-NOT-PAY" if category == "KILL" else category
                entry.update(floor=floor, verdict=category, readings=readings, cost_ratio=r_point, cost_ratio_ci95=r_ci,
                             invalid_per_arm={a: sum(r["arm"] == a and r["valid"] is not True for r in cells) for a in (LOW, REF)},
                             cells=len(cells), answer=answer)
        result[repo] = entry
    decisive = sorted(repo for repo, e in result.items() if e.get("answer") in ("PAYS", "DOES-NOT-PAY"))
    summary = {"repositories": result, "decisive": decisive, "t2": bool(decisive), "attempts_dir": attempts.name}
    out_path.write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({"decisive": decisive, "answers": {k: v.get("answer") for k, v in result.items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
