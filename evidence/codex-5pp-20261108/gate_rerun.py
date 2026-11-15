"""AMENDMENT-2, change 3: the corrected planted-defect gate for the repositories whose recorded check had a non-conformant control.
Pinned v1.7.0 code, the evaluator embedded in the mined tasks, the same seed and mutant sampling as the recorded check, no model.
Writes gate/<repo>.json with every row; the recorded sensitivity.json is never touched.
Usage: python3 -I -B gate_rerun.py traefik_yaegi klauspost_compress"""
import hashlib
import json
import random
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script directory out
import pinned  # noqa: E402

lab = pinned.load()
HERE = Path(__file__).resolve().parent
MINED = HERE.parent / "public-yield-20261107" / "mine2"
JOBS = 3


def rows_for(name):
    out = MINED / name
    config = json.loads((out / "replay-set.json").read_text())
    pairs = json.loads((out / "pairs.json").read_text())
    repo, rng, work = next(iter(config["repos"].values())), random.Random(config.get("seed", 1)), []
    for task in config["tasks"]:  # the work list of effort_lab.sensitivity, in its order, so the mutants are the recorded ones
        meta = pairs[task["id"]]
        real_next = lab._git(repo, "diff", "--binary", meta["next"]["base"], meta["next"]["accepted"]).decode("utf-8", "replace") if "next" in meta else ""
        reference = (out / "tasks" / task["id"] / "reference.patch").read_text()
        work.append((task["id"], True, reference, real_next))
        work += [(task["id"], False, m, real_next) for m in lab.mutants(reference, 6, rng)]

    def one(item):
        tid, control, patch_text, real_next = item
        try:
            return tid, control, lab.probe(config, out, tid, patch_text, real_next)
        except Exception as error:
            return tid, control, lab.failure_summary(error)
    with ThreadPoolExecutor(JOBS) as pool:
        rows = list(pool.map(one, work))
    serial = {}  # every control whose reference did not pass its first oracle, once more, alone
    for tid, control, value in rows:
        if control and not (isinstance(value, tuple) and value[0]):
            serial[tid] = one(next(w for w in work if w[0] == tid and w[1]))[2]
    return config, rows, serial


def old_rule(rows):
    tried = [r for r in rows if not r[1] and isinstance(r[2], tuple)]
    return {"mutants": len(tried), "rejected": sum(not r[2][0] for r in tried)}


def main(names):
    evaluator = Path(tempfile.mkdtemp(prefix="gate-evaluator-"))
    for name in names:  # every mined task embeds the same evaluator; collect() copies lab.HERE/lab_accept.py into each tree
        for task in (MINED / name / "tasks").iterdir():
            if hashlib.sha256((task / "lab_accept.py").read_bytes()).hexdigest() != pinned.EVALUATOR_SHA256:
                raise SystemExit(f"embedded evaluator differs: {task}")
    shutil.copy(next((MINED / names[0] / "tasks").iterdir()) / "lab_accept.py", evaluator / "lab_accept.py")
    lab.HERE = evaluator
    pinned.check_loaded()
    (HERE / "gate").mkdir(exist_ok=True)
    for name in names:
        config, rows, serial = rows_for(name)
        recorded = json.loads((MINED / name / "sensitivity.json").read_text())
        failed = sorted({t for t, c, v in rows if c and not (isinstance(v, tuple) and v[0])} | {t for t, v in serial.items() if not (isinstance(v, tuple) and v[0])})
        result = {"repo": name, "code_commit": pinned.COMMIT, "evaluator_sha256": pinned.EVALUATOR_SHA256, "jobs": JOBS,
                  "tasks": len(config["tasks"]), "corrected": lab.sensitivity_summary(rows), "old_rule_recomputed": old_rule(rows),
                  "old_rule_recorded": {k: recorded["immediate"][k] for k in ("mutants", "rejected")},
                  "reference_failed": failed, "serial_controls": {t: list(v) if isinstance(v, tuple) else v for t, v in serial.items()},
                  "rows": [[t, c, list(v) if isinstance(v, tuple) else v] for t, c, v in rows]}
        result["consistent"] = result["old_rule_recomputed"] == result["old_rule_recorded"]
        (HERE / "gate" / f"{name}.json").write_text(json.dumps(result, indent=1))
        print(json.dumps({k: result[k] for k in ("repo", "tasks", "consistent", "old_rule_recorded", "old_rule_recomputed", "reference_failed")}
                         | {"corrected_immediate": result["corrected"]["immediate"]}), flush=True)
    shutil.rmtree(evaluator)


if __name__ == "__main__":
    main(sys.argv[1:] or ["traefik_yaegi", "klauspost_compress"])
