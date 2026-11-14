"""PREREG-F dry run, no model: the whole set on the pinned 1.8.1 runner with a fake CLI that applies, per cell, the reference or a
planted defect (the reference without one hunk); about 90% reference at xhigh and 80% at medium, by a hash of task, arm, replicate.
Passes only if: every cell valid; every reference cell accepted, except isolated failures (a task, 1 cell); the medium - xhigh mean on
the frozen reach is negative; regrade_f.py on 2 valid cells finds no discordance. Writes under dryrun/. Usage: python3 -I -B dry_run_f.py"""
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinned_f  # noqa: E402

lab = pinned_f.load()
HERE = Path(__file__).resolve().parent
DRY = HERE / "dryrun"
SHARE = {"xhigh": 90, "medium": 80}
FAKE = r'''#!{python}
import hashlib, json, pathlib, re, subprocess, sys
sys.stdin.read()
cwd = pathlib.Path(sys.argv[sys.argv.index("-C") + 1]) if "-C" in sys.argv else pathlib.Path.cwd()
task, arm, rep = re.match(r"007-(.+)-(medium|xhigh)-r(\d\d)-", cwd.name).groups()
reference = int(hashlib.sha256(f"{{task}}|{{arm}}|{{rep}}".encode()).hexdigest(), 16) % 100 < {share!r}[arm]
patch = (pathlib.Path({tasks!r}) / task / "reference.patch") if reference else (pathlib.Path({mutants!r}) / (task + ".patch"))
if patch.stat().st_size:
    subprocess.run(["git", "apply", "--recount", "--binary", str(patch)], cwd=cwd, capture_output=True)
rows = [{{"type": "system", "subtype": "init", "session_id": "dry-" + task, "model": "claude-opus-5-5"}},
        {{"type": "result", "subtype": "success", "is_error": False, "session_id": "dry-" + task, "total_cost_usd": 0.0,
          "usage": {{"input_tokens": 1000, "output_tokens": 10}}, "modelUsage": {{"claude-opus-5-5": {{"inputTokens": 1000, "outputTokens": 10, "costUSD": 0.0}}}}}}]
for row in rows:
    print(json.dumps(row), flush=True)
'''


def main():
    pinned_f.verify()
    build = json.loads((HERE / "f-build.json").read_text())
    data = (HERE / "f-set.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != build["f_set_sha256"]:
        raise SystemExit("f-set.json changed after the build")
    config = json.loads(data)
    (DRY / "bin").mkdir(parents=True, exist_ok=True)
    (DRY / "mutants").mkdir(exist_ok=True)
    for task in config["tasks"]:
        reference = lab.read_patch(HERE / "tasks" / task["id"] / "reference.patch")
        planted = list(lab.mutants(reference, 1, random.Random(f"20261112|{task['id']}")))
        (DRY / "mutants" / f"{task['id']}.patch").write_text(planted[0] if planted else "")
    fake = DRY / "bin" / "claude"
    fake.write_text(FAKE.format(python=sys.executable, tasks=str(HERE / "tasks"), mutants=str(DRY / "mutants"), share=SHARE))
    fake.chmod(0o755)
    command = list(config["agent_command"])
    cli = command.index("--") + 1
    if not command[cli].endswith("/claude"):
        raise SystemExit("unexpected agent command")
    command[cli] = str(fake)
    (DRY / "dry-set.json").write_text(json.dumps({**config, "agent_command": command}, indent=1, ensure_ascii=False))
    cells = len(lab.plan(config, 2))
    run = subprocess.run([sys.executable, "-B", str(pinned_f.PINNED / "scripts" / "effort_lab.py"), "run", "--set", str(DRY / "dry-set.json"),
                          "--out", str(DRY / "results"), "--replicates", "2", "--jobs", "2", "--max-calls", str(cells), "--max-usd", "400",
                          "--stop-usd", "10", "--max-invalid", str(cells)], capture_output=True, text=True)
    rows = lab.load_cells(DRY / "results")
    reach = json.loads((HERE / "frozen-reach.json").read_text())
    applied = lambda r: int(hashlib.sha256(f"{r['task']}|{r['arm']}|{r['replicate']:02d}".encode()).hexdigest(), 16) % 100 < SHARE[r["arm"]]
    broken = sorted({r["task"] for r in rows if r["valid"] is True and applied(r) and not r.get("accepted")})
    diffs = lab.reachable_diffs([r for r in rows if r["valid"] is True], HERE / "tasks", "medium", "xhigh", reach=reach)
    mean = lab.paired_interval(diffs)["mean"]
    regrade = subprocess.run([sys.executable, "-I", "-B", str(HERE / "regrade_f.py"), str(DRY / "dry-set.json"), str(DRY / "results"),
                              str(DRY / "regrade"), str(HERE / "frozen-reach.json"), "--sample", "2"], capture_output=True, text=True)
    serial = json.loads((DRY / "regrade" / "regrade.json").read_text()) if (DRY / "regrade" / "regrade.json").is_file() else {}
    checks = {"run_exit_0": run.returncode == 0, "cells": len(rows) == cells, "every_cell_valid": bool(rows) and all(r["valid"] is True for r in rows),
              "references_accepted": len(broken) < 2, "sign_negative": mean is not None and mean < 0,
              "serial_regrade_agrees": regrade.returncode == 0 and serial.get("cells", 0) > 0 and serial.get("disagree") == 0}
    result = {"passed": all(checks.values()), "checks": checks, "cells": len(rows), "reference_failures": broken, "mean": mean,
              "serial": {k: serial.get(k) for k in ("cells", "disagree", "unapplied")}, "run_stderr": run.stderr[-800:], "regrade_stderr": regrade.stderr[-800:]}
    (DRY / "dry-run.json").write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps({k: result[k] for k in ("passed", "checks", "cells", "reference_failures", "mean")}, default=str))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
