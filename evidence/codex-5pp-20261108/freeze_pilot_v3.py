"""AMENDMENT-3: freeze_pilot_v2.py with the same decision logic, plus what a third party needs to check it.
- `analyze_topup` is imported from the published go-json top-up directory when present (else the maintainer's copy), and its bytes
  must match the hash published there.
- Writes cells.csv (one row per cell, no local paths) and cells.sha256 (SHA-256 of every raw cell and runner file).
- Adds reaching tasks per repository to the summary (DECISIONS part 3 compares them with n80, as a description).
No model. Usage: python3 -I -B freeze_pilot_v3.py [results_dir out_dir]   (defaults: results/ and this directory)"""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script directory out
import pinned  # noqa: E402

lab = pinned.load()
HERE = Path(__file__).resolve().parent
ANALYZE_SHA256 = "6b7ad6812fd6adc87834250fc358a69fbca8f2144804789ce4883c2c6dda21be"  # evidence/go-json-topup-20261106/SHA256SUMS
TOPUP = next(d for d in (HERE.parent / "go-json-topup-20261106", HERE.parent / "public-replay-20261105" / "gojson-topup")
             if (d / "analyze_topup.py").is_file())
if hashlib.sha256((TOPUP / "analyze_topup.py").read_bytes()).hexdigest() != ANALYZE_SHA256:
    raise SystemExit(f"analyze_topup.py differs from the published one: {TOPUP}")
sys.path.insert(0, str(TOPUP))
import analyze_topup as A  # noqa: E402  its own `import effort_lab` finds the pinned module already loaded

pinned.check_loaded()
RESULTS, OUT = (Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()) if len(sys.argv) == 3 else (HERE / "results", HERE)
TASKS = HERE / "tasks"
SEED, MARGIN, ATTEMPTS, FLOOR_DECLARED = 20261110, .05, 8, 2.198
CELL_FIELDS = ("cell", "repo", "task", "arm", "replicate", "valid", "failure_class", "accepted", "reasoning_output_tokens",
               "agent_wall_s", "cost_usd")


def frozen_reach(rows):
    """build_topup's rule: hidden tests not in the baseline that some valid attempt passed."""
    def tests(task, name):
        return json.loads((TASKS / task / name).read_text())
    return {t: sorted({k for c, _ in cells for k in tests(t, "hidden.json") if k != "__module__" and k not in set(tests(t, "baseline.json"))
                       and any(x["acceptance_outcomes"].get(k) == "pass" for x, _ in cells)})
            for t, cells in lab.reach_rates(rows, TASKS).items()}


def freeze(rows, repo_of):
    reach = {t: v for t, v in frozen_reach(rows).items() if v}
    A.TASKS, A.REACH = TASKS, reach
    noise = A.tau2(rows)
    lab.GATES["draws"] = 100_000
    pilot_floor = lab.proven_critical(rows, TASKS, A.LOW, A.REF, SEED, margin=MARGIN, reach=reach, attempts=ATTEMPTS)
    floor = max(FLOOR_DECLARED, math.inf if pilot_floor is None else pilot_floor)
    tau2 = max([0.0] + [v for v in (noise["tau2_moments"], noise["tau2_covariance"]) if v is not None])
    n80 = math.ceil((tau2 + noise["sigma2"] * 2 / ATTEMPTS) * ((floor + 0.8416) / MARGIN) ** 2) if math.isfinite(floor) else None
    pilot = lab.paired_interval(lab.reachable_diffs(rows, TASKS, A.LOW, A.REF, reach=reach))
    per_repo = {}
    for task in reach:
        per_repo[repo_of[task]] = per_repo.get(repo_of[task], 0) + 1
    return reach, {"decision": "GO" if n80 is not None and len(reach) >= n80 else "NO-GO", "reaching_tasks": len(reach),
                   "n80_if_equal": n80, "tau2_used": tau2, "noise": noise, "critical_floor": floor, "pilot_floor": pilot_floor,
                   "cells_valid": len(rows), "reaching_tasks_per_repo_never_deciding": dict(sorted(per_repo.items())),
                   "pilot_mean_never_deciding": {k: pilot[k] for k in ("tasks", "mean", "ci95")}}


def publish_cells(every, repo_of):
    with (OUT / "cells.csv").open("w", newline="") as handle:
        out = csv.writer(handle)
        out.writerow(CELL_FIELDS)
        for r in every:
            usage = r.get("usage") if isinstance(r.get("usage"), dict) else {}
            out.writerow([r["cell"], repo_of.get(r["task"]), r["task"], r["arm"], r["replicate"], r["valid"], r.get("failure_class"),
                          r.get("accepted"), usage.get("reasoning_output_tokens"), r.get("agent_wall_s"), r.get("cost_usd")])
    raw = sorted(p for p in RESULTS.iterdir() if p.suffix == ".json" and lab.replay_eval.is_cell_id(p.name.split(".")[0]))
    (OUT / "cells.sha256").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in raw))


def main():
    failed = set(json.loads((HERE / "reference-failed.json").read_text()))
    repo_of = {t["id"]: t["repo"] for t in json.loads((HERE / "pilot-set.json").read_text())["tasks"]}
    every = lab.load_cells(RESULTS)
    publish_cells(every, repo_of)
    valid = [r for r in every if r["valid"] is True]
    reach, primary = freeze([r for r in valid if r["task"] not in failed], repo_of)
    _, secondary = freeze(valid, repo_of)
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
