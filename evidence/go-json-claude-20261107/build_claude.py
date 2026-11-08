"""PREREG-CLAUDE: build the Claude go-json set and fix its critical-value floor before any paid attempt.
- Set: the same 41 tasks, frozen reach set and grading as the Codex top-up; arms Claude Opus 5.5 `medium` vs `xhigh` with the
  command the cost probe used; 2 attempts per arm; seed 20261108; declared margin 10 points (`compare.margin`).
- Floor: effort_lab.proven_critical at a 10-point margin and 2 attempts per arm, from the 231 earlier re-graded Codex attempts
  (pooled, so arm labels do not matter), frozen reach, 100,000 draws. At 10 points the run-own value alone reached 3.25%
  false PROVEN in reading P (claude-go/margin10_check.json), above the 2.98% limit.
No model. Usage: python3 -I -B build_claude.py"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EV = HERE.parent
sys.path.insert(0, str(EV / "gojson-topup"))
import build_topup as B  # noqa: E402

lab, SEED = B.lab, 20261108


def main():
    topup = json.loads((EV / "gojson-topup" / "topup-set.json").read_text())
    probe = json.loads((EV / "claude-probe" / "probe-set.json").read_text())
    cfg = {**topup, "seed": SEED, "agent_command": probe["agent_command"], "arms": probe["arms"], "served_identity": "requested-only",
           "compare": {"candidate": "medium", "reference": "xhigh", "margin": .10}}
    (HERE / "claude-set.json").write_text(json.dumps(cfg, indent=1, ensure_ascii=False))
    for name, target in (("tasks", EV / "lab-gojson" / "tasks"), ("sensitivity.json", EV / "lab-gojson-sens" / "sensitivity.json")):
        if not (HERE / name).exists():
            (HERE / name).symlink_to(target)
    reach = json.loads((EV / "gojson-topup" / "frozen-reach.json").read_text())
    lab.GATES["draws"] = 100_000
    floor = lab.proven_critical(B.old_cells("treatment"), B.TASKS, "medium", "high", SEED, margin=.10, reach=reach, attempts=2)
    (HERE / "critical-floor.json").write_text(json.dumps({"critical_floor": floor, "margin": .10, "attempts_per_arm": 2, "draws": 100_000, "seed": SEED}, indent=1))
    print(json.dumps({"tasks": len(cfg["tasks"]), "cells": len(lab.plan(cfg, 2)), "critical_floor": floor, "arms": {k: v["effort"] for k, v in cfg["arms"].items()}}))


if __name__ == "__main__":
    main()
