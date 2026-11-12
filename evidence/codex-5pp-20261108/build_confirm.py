"""PREREG-CONFIRM: the confirmatory set, built only after a GO, from the pilot set and the primary freeze. No model.
- Tasks: the pilot set's tasks in frozen-reach.json, nothing else; arms, agent command, sandbox and grading unchanged; seed 20261113.
- Cost: reaching tasks x 16 attempts x the pilot's mean cost per dispatched attempt (cells.csv) must fit US$400 (DECISIONS part 2).
Usage: python3 -I -B build_confirm.py"""
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script directory out
import pinned  # noqa: E402

HERE = Path(__file__).resolve().parent
SEED, CAP, ATTEMPTS = 20261113, 400, 16


def main():
    pinned.verify()
    summary = json.loads((HERE / "pilot-summary.json").read_text())
    if summary["decision"] != "GO":
        raise SystemExit("the pilot did not GO: no confirmatory set")
    reach = json.loads((HERE / "frozen-reach.json").read_text())
    pilot = json.loads((HERE / "pilot-set.json").read_text())
    with (HERE / "cells.csv").open() as handle:
        costs = [float(r["cost_usd"]) for r in csv.DictReader(handle) if r["cost_usd"] not in ("", "None", "unmeasured")]
    per_attempt = sum(costs) / len(costs)
    tasks = [t for t in pilot["tasks"] if t["id"] in reach]
    expected = len(tasks) * ATTEMPTS * per_attempt
    if expected > CAP:
        raise SystemExit(f"expected cost US${expected:.2f} exceeds US${CAP}: no confirmatory attempt, NO-BUDGET")
    data = json.dumps({**pilot, "tasks": tasks, "seed": SEED}, indent=1, ensure_ascii=False)
    (HERE / "confirm-set.json").write_text(data)
    build = {"tasks": len(tasks), "pilot_mean_cost_per_attempt": per_attempt, "expected_usd": round(expected, 2), "cap_usd": CAP,
             "confirm_set_sha256": hashlib.sha256(data.encode()).hexdigest()}
    (HERE / "confirm-build.json").write_text(json.dumps(build, indent=1))
    print(json.dumps(build))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
