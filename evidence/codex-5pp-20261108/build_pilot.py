"""PREREG-PILOT: pool the mined Go repositories that pass the planted-defect gate into one Codex `medium` vs `high` pilot set.
- Source: evidence/public-yield-20261107/mine2/<repo>/, one set per repository, mined with the fixed miner (7129082).
- Gate: a repository enters only if its planted-defect check rejected at least 30% of mutants (sensitivity.json, immediate).
- Agent command, arms and comparison come unchanged from the go-json top-up set (Codex CLI pinned, gpt-6.1-sol); sandbox and
  grading from the mined sets. Seed 20261110; declared margin 5 points. `tasks/` links every pooled task under one directory.
No model. Usage: python3 -I -B build_pilot.py"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MINED = HERE.parent / "public-yield-20261107" / "mine2"
TOPUP = HERE.parent / "public-replay-20261105" / "gojson-topup" / "topup-set.json"
REPOS = ("BurntSushi_toml", "traefik_yaegi", "pelletier_go-toml", "pierrec_lz4", "klauspost_compress")
GATE, SEED, MARGIN = .30, 20261110, .05


def main():
    topup = json.loads(TOPUP.read_text())
    pooled, gate = None, {}
    (HERE / "tasks").mkdir(exist_ok=True)
    for name in REPOS:
        d = MINED / name
        if not (d / "replay-set.json").is_file():
            gate[name] = {"tasks": 0, "sensitivity": None, "pooled": False}
            continue
        mined = json.loads((d / "replay-set.json").read_text())
        sens = json.loads((d / "sensitivity.json").read_text())["immediate"]["sensitivity"] if (d / "sensitivity.json").is_file() else None
        gate[name] = {"tasks": len(mined["tasks"]), "sensitivity": sens, "pooled": bool(mined["tasks"]) and sens is not None and sens >= GATE}
        if not gate[name]["pooled"]:
            continue
        pooled = pooled or {**mined, "repos": {}, "tasks": []}
        pooled["repos"].update(mined["repos"])
        pooled["tasks"] += mined["tasks"]
        for task in mined["tasks"]:
            if not (HERE / "tasks" / task["id"]).exists():
                (HERE / "tasks" / task["id"]).symlink_to(d / "tasks" / task["id"])
    (HERE / "pilot-gate.json").write_text(json.dumps(gate, indent=1))
    if pooled is None:
        print(json.dumps({"gate": gate, "tasks": 0}))
        return 1
    pooled.update({k: topup[k] for k in ("agent_command", "served_identity", "arms")}, seed=SEED, compare={**topup["compare"], "margin": MARGIN})
    (HERE / "pilot-set.json").write_text(json.dumps(pooled, indent=1, ensure_ascii=False))
    print(json.dumps({"gate": gate, "tasks": len(pooled["tasks"]), "cells_at_2": 4 * len(pooled["tasks"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
