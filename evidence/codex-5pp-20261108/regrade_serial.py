"""AMENDMENT-5 (c), (d): re-grade every valid cell of a results directory one at a time, on a quiet machine, with the evaluator
embedded in its task and the pinned v1.7.0 grading path (`replay_eval`: snapshot, candidate patch, hidden acceptance, acceptance).
No model. The original cells are never touched. Writes <out>/ with each cell's re-graded copy (receipt and patch copied, so the
freeze can read it) and <out>/regrade.json with the discordance: a cell disagrees when any test of its task's frozen reach (or,
without one, any hidden test) changes outcome.
With --evaluator pinned the v1.7.0 evaluator (lab_accept.py of the pinned distribution) replaces the embedded one: the
confirmatory robustness re-grade of PREREG-CONFIRM, at one job (AMENDMENT-5 (e)).
Usage: python3 -I -B regrade_serial.py <set.json> <results_dir> <out_dir> [reach.json] [--sample N] [--evaluator pinned]"""
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script directory out
import pinned  # noqa: E402

lab = pinned.load()
pinned.check_loaded()
RE = lab.replay_eval


def grade(config, task, patch_text):
    """Outcomes of `patch_text` on the task's base, graded as execute_cell grades a cell; None when the patch does not apply."""
    sandbox, env = config.get("acceptance_sandbox"), config.get("acceptance_env")
    with tempfile.TemporaryDirectory(prefix="007-regrade-") as scratch:
        workspace = Path(scratch) / "workspace"
        RE.export_snapshot(Path(config["repos"][task["repo"]]).expanduser().resolve(), task["base"], workspace)
        if not lab.apply_patch(workspace, patch_text):
            return None
        report = Path(scratch) / "accept-report.json"
        with RE.hidden_acceptance(task, workspace):
            checks, _ = RE.acceptance(task, workspace, sandbox, {**RE.acceptance_policy(sandbox, env)[1], "ACCEPT_REPORT": str(report)},
                                      retain_diagnostic_text=False)
        return RE.acceptance_outcomes(report) if len(checks) == 1 else "unavailable"


def main():
    argv, options = sys.argv[1:], {}
    for flag in ("--sample", "--evaluator"):
        if flag in argv:
            i = argv.index(flag)
            options[flag], argv = argv[i + 1], argv[:i] + argv[i + 2:]
    args, sample = argv, int(options["--sample"]) if "--sample" in options else None
    config = json.loads(Path(args[0]).read_text())
    results, out = Path(args[1]).resolve(), Path(args[2]).resolve()
    reach = json.loads(Path(args[3]).read_text()) if len(args) > 3 else {}
    tasks = {t["id"]: t for t in config["tasks"]}
    if options.get("--evaluator") == "pinned":
        source = pinned.PINNED / "scripts" / "lab_accept.py"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        tasks = {i: {**t, "hidden_acceptance": [{**e, "source": str(source), "sha256": digest} if e["target"] == ".007-accept/lab_accept.py" else e
                                               for e in t["hidden_acceptance"]]} for i, t in tasks.items()}
    elif "--evaluator" in options:
        raise SystemExit("--evaluator takes only: pinned")
    rows = [r for r in lab.load_cells(results) if r["valid"] is True and isinstance(r.get("candidate_patch"), dict)]
    if sample is not None:  # the dry run's check: the first `sample` cells per repository, in cell order
        seen, picked = {}, []
        for r in rows:
            repo = tasks[r["task"]]["repo"]
            if seen.get(repo, 0) < sample:
                seen[repo] = seen.get(repo, 0) + 1
                picked.append(r)
        rows = picked
    out.mkdir(parents=True, exist_ok=True)
    cells, disagree, unapplied = [], [], []
    for row in rows:  # one at a time: the point is a grade free of the run's own load
        patch_text = (results / row["candidate_patch"]["path"]).read_text(errors="surrogateescape")
        outcomes = grade(config, tasks[row["task"]], patch_text)
        tests = reach.get(row["task"]) or [k for k in (row["acceptance_outcomes"] or {}) if k != "__module__"]
        before = {k: row["acceptance_outcomes"].get(k) == "pass" for k in tests}
        after = {k: isinstance(outcomes, dict) and outcomes.get(k) == "pass" for k in tests}
        if outcomes is None:
            unapplied.append(row["cell"])
        if before != after:
            disagree.append({"cell": row["cell"], "changed": sorted(k for k in tests if before[k] != after[k])})
        raw = json.loads((results / f"{row['cell']}.json").read_text())
        raw["acceptance_outcomes"] = outcomes if isinstance(outcomes, dict) else raw["acceptance_outcomes"]
        raw["regraded_serial"] = outcomes is not None and isinstance(outcomes, dict)
        (out / f"{row['cell']}.json").write_text(json.dumps(raw))
        for suffix in (".runner.json",):
            shutil.copy2(results / f"{row['cell']}{suffix}", out / f"{row['cell']}{suffix}")
        shutil.copy2(results / row["candidate_patch"]["path"], out / row["candidate_patch"]["path"])
        cells.append(row["cell"])
    arms = sorted({r["arm"] for r in rows})
    summary = {"cells": len(cells), "disagree": len(disagree), "discordance": len(disagree) / len(cells) if cells else None,
               "per_arm": {a: {"cells": sum(r["arm"] == a for r in rows), "disagree": sum(d["cell"] in {r["cell"] for r in rows if r["arm"] == a} for d in disagree)} for a in arms},
               "unapplied": unapplied, "disagreements": disagree, "evaluator": options.get("--evaluator", "embedded"), "code_commit": pinned.COMMIT,
               "set_sha256": hashlib.sha256(Path(args[0]).read_bytes()).hexdigest()}
    (out / "regrade.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: summary[k] for k in ("cells", "disagree", "discordance", "per_arm", "unapplied")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
