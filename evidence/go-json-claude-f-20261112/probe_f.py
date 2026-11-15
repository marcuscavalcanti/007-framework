"""PREREG-F provider probe: 3 real cells on go-json commits outside the 41 (declared non-evidence), on the F agent command and the
pinned 1.8.1 runner. Passes only if all 3 are valid with a receipt and a measured cost. Writes under probe/. Usage: python3 -I -B probe_f.py"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinned_f  # noqa: E402

lab = pinned_f.load()
HERE = Path(__file__).resolve().parent
PROBE = HERE / "probe"


def main():
    config = json.loads((HERE / "f-set.json").read_text())
    used = {t["id"] for t in config["tasks"]}
    mined = json.loads((HERE.parent / "public-replay-20261105" / "lab-gojson" / "replay-set.json").read_text())
    extra = [t for t in mined["tasks"] if t["id"] not in used][:3]
    if len(extra) < 3:
        raise SystemExit("fewer than 3 go-json commits outside the 41")
    PROBE.mkdir(exist_ok=True)
    (PROBE / "probe-set.json").write_text(json.dumps({**config, "tasks": extra, "seed": 20261199}, indent=1, ensure_ascii=False))
    run = subprocess.run([sys.executable, "-B", str(pinned_f.PINNED / "scripts" / "effort_lab.py"), "run", "--set", str(PROBE / "probe-set.json"),
                          "--out", str(PROBE / "results"), "--replicates", "1", "--jobs", "1", "--max-calls", "3", "--max-usd", "30",
                          "--stop-usd", "10", "--max-invalid", "3"], capture_output=True, text=True)
    rows = lab.load_cells(PROBE / "results")
    costs = [lab.cost_of(PROBE / "results", r["cell"], r) for r in rows]
    passed = len(rows) == 3 and all(r["valid"] is True for r in rows) and all(isinstance(c, (int, float)) for c in costs)
    result = {"passed": passed, "cells": [{"cell": r["cell"], "valid": r["valid"], "failure_class": r.get("failure_class"), "cost_usd": c}
                                          for r, c in zip(rows, costs)], "run_stdout": run.stdout[-400:], "run_stderr": run.stderr[-800:]}
    (PROBE / "probe.json").write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps({k: result[k] for k in ("passed", "cells")}, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
