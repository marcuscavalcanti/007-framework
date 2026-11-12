"""AMENDMENT-5, plan step 6: A/A by permutation on real data. No model. Run only after the pilot's freeze.
The go-json top-up's `high` cells (8 attempts per task): 2,000 random splits of each task's 8 attempts into two pseudo-arms of 4
(seed 20261115). For each split, the per-task difference on the top-up's frozen reach and its paired 95% t interval.
Reports how often the interval excludes zero (expected 3% to 8%: outside that range, no verdict is announced as proof until the cause
is found) and how often the 5-point statistic beats the floor 2.198. Usage: python3 -I -B aa.py"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script directory out
import pinned_f as pinned  # noqa: E402

lab = pinned.load()
pinned.check_loaded()
HERE = Path(__file__).resolve().parent
TOPUP = HERE.parent / "public-replay-20261105" / "gojson-topup"
SPLITS, SEED, MARGIN, FLOOR = 2000, 20261115, .05, 2.198


def main():
    reach = json.loads((TOPUP / "frozen-reach.json").read_text())
    rows = [r for r in lab.load_cells(TOPUP / "results") if r["valid"] is True and r["arm"] == "high"]
    rates = lab.reach_rates(rows, TOPUP / "tasks", reach)
    rng, excludes, proven, used = random.Random(SEED), 0, 0, 0
    for _ in range(SPLITS):
        diffs = {}
        for task, cells in rates.items():
            values = [v for _, v in cells]
            if len(values) < 2:
                continue
            rng.shuffle(values)
            half = len(values) // 2
            diffs[task] = sum(values[:half]) / half - sum(values[half:]) / (len(values) - half)
        s = lab.paired_interval(diffs)
        if s["ci95"] is None:
            continue
        used += 1
        excludes += s["ci95"][0] > 0 or s["ci95"][1] < 0
        proven += lab.studentized(diffs, MARGIN) > FLOOR
    out = {"splits": used, "tasks": len(rates), "ci_excludes_zero": excludes / used, "proven_at_5pp_floor": proven / used,
           "expected_range": [.03, .08], "within_range": .03 <= excludes / used <= .08}
    (HERE / "aa.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
