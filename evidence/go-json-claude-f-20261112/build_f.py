"""PREREG-F: the Claude go-json set at the break-even margin, and the critical-value floor, before any attempt. No model.
- Set: the earlier Claude run's set (41 commits, frozen reach, grading, arms, agent command and pinned Claude settings), with seed
  20261112, compare.margin 0.20, and the native runner of the pinned 1.8.1 distribution.
- Floor: the larger of effort_lab.proven_critical at a 0.20 loss and 2 attempts per arm (100,000 draws) from (i) the 231 earlier
  re-graded Codex go-json attempts (treatment grading) and (ii) the earlier Claude run's valid attempts.
Writes f-set.json, critical-floor.json and f-build.json. Usage: python3 -I -B build_f.py"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinned_f  # noqa: E402

lab = pinned_f.load()
HERE = Path(__file__).resolve().parent
EV = HERE.parent / "public-replay-20261105"
SEED, MARGIN, DRAWS = 20261112, .20, 100_000
OLD_RUNNER = str(HERE.parents[1] / "repo" / "scripts" / "native_runner.py")


def codex_pool():
    rows = [r for d in ("gojson-run", "gojson-ext") for r in lab.load_cells(EV / d / "results") if r["valid"] is True]
    graded = []
    for r in rows:
        value = json.loads((EV / "gojson-regrade" / f"{r['cell']}.treatment.json").read_text())
        graded.append({**r, "acceptance_outcomes": value["outcomes"] if isinstance(value.get("outcomes"), dict) else {}})
    return graded


def main():
    old = json.loads((EV / "claude-go" / "claude-set.json").read_text())
    command = list(old["agent_command"])
    if command.count(OLD_RUNNER) != 1:
        raise SystemExit("the earlier Claude command does not name the expected native runner once")
    command[command.index(OLD_RUNNER)] = str(pinned_f.PINNED / "scripts" / "native_runner.py")
    config = {**old, "seed": SEED, "agent_command": command, "compare": {**old["compare"], "margin": MARGIN}}
    data = json.dumps(config, indent=1, ensure_ascii=False)
    (HERE / "f-set.json").write_text(data)
    if not (HERE / "tasks").exists():
        (HERE / "tasks").symlink_to(EV / "lab-gojson" / "tasks")
    reach = json.loads((EV / "gojson-topup" / "frozen-reach.json").read_text())
    (HERE / "frozen-reach.json").write_text(json.dumps(reach, indent=1, sort_keys=True))
    lab.GATES["draws"] = DRAWS
    tasks = EV / "lab-gojson" / "tasks"
    codex = lab.proven_critical(codex_pool(), tasks, "medium", "high", SEED, margin=MARGIN, reach=reach, attempts=2)
    claude_rows = [r for r in lab.load_cells(EV / "claude-go" / "results") if r["valid"] is True]
    claude = lab.proven_critical(claude_rows, tasks, "medium", "xhigh", SEED, margin=MARGIN, reach=reach, attempts=2)
    floor = max(v for v in (codex, claude) if v is not None)
    (HERE / "critical-floor.json").write_text(json.dumps({"critical_floor": floor, "from_codex_pool": codex, "from_claude_run": claude,
                                                         "margin": MARGIN, "attempts_per_arm": 2, "draws": DRAWS, "seed": SEED}, indent=1))
    build = {"tasks": len(config["tasks"]), "cells": len(lab.plan(config, 2)), "f_set_sha256": hashlib.sha256(data.encode()).hexdigest(),
             "critical_floor": floor, "code_commit": pinned_f.COMMIT}
    (HERE / "f-build.json").write_text(json.dumps(build, indent=1))
    print(json.dumps(build))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
