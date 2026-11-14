"""Item 8 validation: native missing_data_guard on the published 2026-11-07 go-json results, as AMENDMENT-F1 validated analyze_f.py."""
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import effort_lab as lab
F = Path(sys.argv[2]); results = Path(sys.argv[3])
lab.GATES["draws"] = 100_000
config = json.loads((F / "f-set.json").read_text())
config.setdefault("compare", {})["critical_floor"] = json.loads((F / "critical-floor.json").read_text())["critical_floor"]
reach = json.loads((F / "frozen-reach.json").read_text())
every = lab.load_cells(results)
planned = [(t["id"], r, a) for t, r, a in lab.plan(config, 2)]
g = lab.missing_data_guard(config, results, F / "tasks", every, planned, "medium", "xhigh", .20, 10.0, reach)
out = {"verdict": g["verdict"], "answer": g["answer"], "L0": {k: [v["statistic"], v.get("critical"), v["verdict"]] for k, v in g["readings"].items()},
       "L2": {k: [v["statistic"], v.get("critical"), v.get("critical_own"), v["mean"], v["ci95"], v["verdict"]] for k, v in g["missing_data"].get("L2", {}).items()},
       "imputed": g["missing_data"]["imputed_in_L2"], "R": [g["cost_ratio"], g["cost_ratio_ci95"]], "R_worst": [g["cost_ratio_worst"], g["cost_ratio_worst_ci95"]]}
print(json.dumps(out, indent=1))
