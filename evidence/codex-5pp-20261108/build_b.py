"""PREREG-B, branch without a confirmatory run: block B's set. No model.
Tasks: the pilot set's tasks in frozen-reach.json whose repository has at least 8 of them; arms, agent command and grading as in the
pilot; seed 20261114. Expected cost tasks x 8 x the pilot's mean cost per dispatched cell must fit US$150, else NO-BUDGET.
Usage: python3 -I -B build_b.py"""
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script directory out
import pinned  # noqa: E402

HERE = Path(__file__).resolve().parent
SEED, CAP, ATTEMPTS, MIN_TASKS = 20261114, 150, 8, 8


def main():
    pinned.verify()
    reach = json.loads((HERE / "frozen-reach.json").read_text())
    pilot = json.loads((HERE / "pilot-set.json").read_text())
    per_repo = {}
    for t in pilot["tasks"]:
        if t["id"] in reach:
            per_repo.setdefault(t["repo"], []).append(t)
    tasks = [t for repo, ts in sorted(per_repo.items()) if len(ts) >= MIN_TASKS for t in ts]
    with (HERE / "cells.csv").open() as handle:
        costs = [float(r["cost_usd"]) for r in csv.DictReader(handle) if r["cost_usd"] not in ("", "None", "unmeasured")]
    expected = len(tasks) * ATTEMPTS * (sum(costs) / len(costs))
    if not tasks:
        raise SystemExit("no repository has 8 reaching tasks: block B has nothing to test")
    if expected > CAP:
        raise SystemExit(f"expected cost US${expected:.2f} exceeds US${CAP}: NO-BUDGET")
    data = json.dumps({**pilot, "tasks": tasks, "seed": SEED}, indent=1, ensure_ascii=False)
    (HERE / "b-set.json").write_text(data)
    build = {"tasks": len(tasks), "repositories": sorted({t["repo"] for t in tasks}), "expected_usd": round(expected, 2), "cap_usd": CAP,
             "b_set_sha256": hashlib.sha256(data.encode()).hexdigest()}
    (HERE / "b-build.json").write_text(json.dumps(build, indent=1))
    print(json.dumps(build))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
