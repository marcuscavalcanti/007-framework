"""PREREG-TOPUP: build the top-up set and fix, before any paid cell, the frozen reach set and the critical-value floor.
- Set: the 41 go-json tasks that reached new behaviour (same 41 under the run's grading and the 8fcec9c re-grade), each with
  `reset_to_base: ["*_test.go"]`, a new seed, and links to the task files and the real planted-defect gate (79% rejected).
- Frozen reach: per task, hidden tests red at base that some of the 231 re-graded old cells passed.
- Floor: effort_lab.proven_critical on those old cells, frozen reach, 8 attempts per arm, 100,000 draws, seed 20261106. At the
  product's 10,000 draws the floor moved 2.195-2.284 across seeds (seen before any fresh cell existed); 100,000 cuts that error.
No model. Usage: python3 -I -B build_topup.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EV = HERE.parent
sys.path.insert(0, str(EV.parents[1] / "repo" / "scripts"))
import effort_lab as lab  # noqa: E402

TASKS, SEED, DRAWS = EV / "lab-gojson" / "tasks", 20261106, 100_000


def old_cells(grading):
    rows = [{**r, "acceptance_outcomes": r["acceptance_outcomes"] if isinstance(r["acceptance_outcomes"], dict) else {}}
            for d in ("gojson-run", "gojson-ext") for r in lab.load_cells(EV / d / "results") if r["valid"] is True]
    if grading == "treatment":
        rows = [{**r, "acceptance_outcomes": (lambda v: v["outcomes"] if isinstance(v.get("outcomes"), dict) else {})(
            json.loads((EV / "gojson-regrade" / f"{r['cell']}.treatment.json").read_text()))} for r in rows]
    return rows


def main():
    treated = old_cells("treatment")
    reach = {t: sorted({k for c, _ in cells for k in json.loads((TASKS / t / "hidden.json").read_text())
                        if k != "__module__" and k not in set(json.loads((TASKS / t / "baseline.json").read_text()))
                        and any(x["acceptance_outcomes"].get(k) == "pass" for x, _ in cells)})
             for t, cells in lab.reach_rates(treated, TASKS).items()}
    assert set(reach) == set(lab.reach_rates(old_cells("as_run"), TASKS)) and len(reach) == 41
    full = json.loads((EV / "lab-gojson" / "gojson-set.json").read_text())
    tasks = [{**t, "reset_to_base": ["*_test.go"]} for t in full["tasks"] if t["id"] in reach]
    (HERE / "topup-set.json").write_text(json.dumps({**full, "seed": SEED, "tasks": tasks}, indent=1, ensure_ascii=False))
    for name, target in (("tasks", TASKS), ("sensitivity.json", EV / "lab-gojson-sens" / "sensitivity.json")):
        if not (HERE / name).exists():
            (HERE / name).symlink_to(target)
    (HERE / "frozen-reach.json").write_text(json.dumps(reach, indent=1, sort_keys=True))
    lab.GATES["draws"] = DRAWS
    floor = lab.proven_critical(treated, TASKS, "medium", "high", SEED, reach=reach, attempts=8)
    (HERE / "critical-floor.json").write_text(json.dumps({"critical_floor": floor, "attempts_per_arm": 8, "draws": lab.GATES["draws"], "seed": SEED,
                                                          "t975_df40": lab.t975(40)}, indent=1))
    print(json.dumps({"tasks": len(tasks), "reach_tests": sum(map(len, reach.values())), "critical_floor": floor,
                      "cells_at_8": len(lab.plan({**full, "seed": SEED, "tasks": tasks}, 8)),
                      "sensitivity_immediate": json.loads((HERE / "sensitivity.json").read_text())["immediate"]["passed"]}))


if __name__ == "__main__":
    main()
