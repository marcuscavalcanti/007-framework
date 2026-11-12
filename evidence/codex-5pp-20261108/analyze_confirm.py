"""PREREG-CONFIRM analysis, fixed before the first pilot attempt (Amendment 3). Fresh confirmatory cells only.
Usage: python3 -I -B analyze_confirm.py 1|2 [results_dir]   (look 1 = replicates 1-4, look 2 = 1-8; default confirm-results/)
The top-up's sequence and readings (analyze_topup.py), at 5 points, with the pilot's frozen reach and critical floor:
(i) manipulation: median reasoning tokens lower at medium; (ii) time: median agent-time saving >= 25% with a task-bootstrap 95%
interval above 0; (iii) primary: per-task medium - high pass share on the frozen reach, readings P and B, the worse decides.
Look 1: KILL if a reading's 95% t interval lies wholly below -5 points; FUTILITY if (mean + 5)/se < 0.5; else CONTINUE.
Look 2: PROVEN if (mean + 5)/se beats max(pilot critical floor, the fresh cells' own critical value simulated at 5 points) in both
readings; KILL as at look 1; else NOT-PROVEN. Differences from analyze_topup: the margin (0.05) is passed to the simulated critical
value, and the 60% robustness reading (Amendment 1) is computed. Secondary readings never decide."""
import json
import math
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
LOOK = int(sys.argv[1])
RESULTS = Path(sys.argv[2]).resolve() if len(sys.argv) == 3 else HERE / "confirm-results"
M, SEED = .05, 20261113
A.TASKS, A.M, A.SEED = HERE / "tasks", M, SEED
A.REACH = json.loads((HERE / "frozen-reach.json").read_text())
A.FLOOR = json.loads((HERE / "critical-floor.json").read_text())["critical_floor"]
lab.GATES["draws"] = 100_000


def same_change(rows, look, reach):
    diffs = lab.reachable_diffs(rows, A.TASKS, A.LOW, A.REF, reach=reach)
    s = lab.paired_interval(diffs)
    out = {"tasks": s["tasks"], "mean": s["mean"], "ci95": s["ci95"], "statistic": lab.studentized(diffs, M) if s["tasks"] > 1 else None}
    if s["tasks"] < lab.GATES["min_signal_tasks"] or s["ci95"] is None:
        return {**out, "verdict": "NO-INFORMATION"}
    if s["ci95"][1] < -M:
        return {**out, "verdict": "KILL"}
    if look == 1:
        return {**out, "verdict": "FUTILITY" if out["statistic"] < .5 else "CONTINUE"}
    fresh = lab.proven_critical(rows, A.TASKS, A.LOW, A.REF, SEED, margin=M, reach=reach)
    critical = max(A.FLOOR, math.inf if fresh is None else fresh)
    return {**out, "critical_fresh": fresh, "critical_floor": A.FLOOR, "critical": critical,
            "verdict": "PROVEN" if out["statistic"] > critical else "NOT-PROVEN"}


def decide(rows, look, reach):
    sequence = {"manipulation": A.reasoning(rows), "time": A.time_gate(rows)}
    if not all(g["passed"] for g in sequence.values()):
        return "STOP-SEQUENCE", sequence, None
    primary = {name: same_change(r, look, reach) for name, r in {"P": rows, "B": A.paired(rows)}.items()}
    return min((p["verdict"] for p in primary.values()), key=A.ORDER.index), sequence, primary


def main():
    every = lab.load_cells(RESULTS)
    rows = [r for r in every if r["valid"] is True and r["replicate"] <= 4 * LOOK and r["task"] in A.REACH]
    decision, sequence, primary = decide(rows, LOOK, A.REACH)
    gate = json.loads((HERE / "pilot-gate.json").read_text())
    repo_of = {t["id"]: t["repo"] for t in json.loads((HERE / "pilot-set.json").read_text())["tasks"]}
    below = {name for name, g in gate.items() if g["below_60"] and g["pooled"]}
    excluded = {name.lower().replace("-", "") for name in below}  # mine2/<Owner_repo-name> -> repo_key, e.g. pelletier_go-toml -> pelletier_gotoml
    if not excluded <= set(repo_of.values()):
        raise SystemExit(f"repository keys not found in the pilot set: {sorted(excluded - set(repo_of.values()))}")
    reach60 = {t: v for t, v in A.REACH.items() if repo_of[t] not in excluded}
    robustness = {"repositories_below_60": sorted(below), "repo_keys_excluded": sorted(excluded),
                  "decision_without_them": decide([r for r in rows if r["task"] in reach60], LOOK, reach60)[0] if excluded else decision}
    out = {"look": LOOK, "cells_valid": len(rows), "decision": decision, "sequence": sequence, "primary": primary,
           "robustness_60": robustness, "secondary": {"tau2": A.tau2(rows),
                                                      "invalid_per_arm": {a: sum(r["arm"] == a and r["valid"] is not True for r in every
                                                                                  if r["replicate"] <= 4 * LOOK) for a in (A.LOW, A.REF)}}}
    F.RESULTS, F.OUT = RESULTS, HERE / "confirm-published"  # cells.csv and cells.sha256, no local paths
    F.OUT.mkdir(exist_ok=True)
    F.publish_cells(every, repo_of)
    (HERE / f"confirm-look{LOOK}.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
