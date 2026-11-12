"""AMENDMENT-3: the dry run on every pooled task, with outcomes that vary, before dispatch. No model.
A fake `codex` applies, per cell, either the task's reference patch or a planted defect (the reference without one hunk, drawn with
the pinned `mutants` at a fixed seed). The choice is a hash of task, arm and replicate: about 90% reference at `high` and 80% at
`medium`, so the freeze sees real spread. Everything else is the built pilot set on the pinned runner, 2 attempts per arm, then
freeze_pilot_v3.py on those cells.
Passes only if: every cell is valid, the run and the freeze exit 0, sigma2 > 0 and n80 is a number. Writes only under dryrun2/.
Usage: python3 -I -B dry_run_v2.py"""
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script directory out
import pinned  # noqa: E402

lab = pinned.load()
pinned.check_loaded()
HERE = Path(__file__).resolve().parent
DRY = HERE / "dryrun2"
SHARE = {"high": 90, "medium": 80}
FAKE = r'''#!{python}
import hashlib, json, pathlib, re, subprocess, sys
sys.stdin.read()
cwd = pathlib.Path(sys.argv[sys.argv.index("-C") + 1])
task, arm, rep = re.match(r"007-(.+)-(medium|high)-r(\d\d)-", cwd.name).groups()
reference = int(hashlib.sha256(f"{{task}}|{{arm}}|{{rep}}".encode()).hexdigest(), 16) % 100 < {share!r}[arm]
patch = (pathlib.Path({tasks!r}) / task / "reference.patch") if reference else (pathlib.Path({mutants!r}) / (task + ".patch"))
applied = patch.stat().st_size == 0 or subprocess.run(["git", "apply", "--recount", "--binary", str(patch)], cwd=cwd, capture_output=True).returncode == 0
rows = [{{"type": "thread.started", "thread_id": "dry-" + task}}, {{"type": "turn.started"}},
        {{"type": "item.completed", "item": {{"type": "agent_message", "text": ("reference" if reference else "planted defect") + (" applied" if applied else " did not apply")}}}},
        {{"type": "turn.completed", "usage": {{"input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": 10, "reasoning_output_tokens": 5 if arm == "medium" else 9}}}}]
for row in rows:
    print(json.dumps(row), flush=True)
'''


def main():
    pinned.verify()
    build = json.loads((HERE / "pilot-build.json").read_text())
    data = (HERE / "pilot-set.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != build["pilot_set_sha256"]:
        raise SystemExit("pilot-set.json changed after the build")
    pilot = json.loads(data)
    (DRY / "bin").mkdir(parents=True, exist_ok=True)
    (DRY / "mutants").mkdir(exist_ok=True)
    for task in pilot["tasks"]:
        reference = (HERE / "tasks" / task["id"] / "reference.patch").read_text()
        planted = list(lab.mutants(reference, 1, random.Random(f"20261112|{task['id']}")))  # a one-hunk patch leaves an empty one
        (DRY / "mutants" / f"{task['id']}.patch").write_text(planted[0] if planted else "")
    fake = DRY / "bin" / "codex"
    fake.write_text(FAKE.format(python=sys.executable, tasks=str(HERE / "tasks"), mutants=str(DRY / "mutants"), share=SHARE))
    fake.chmod(0o755)
    command = list(pilot["agent_command"])
    cli = command.index("--") + 1  # the native runner's CLI argument: the pinned Codex binary
    if not command[cli].endswith("/codex"):
        raise SystemExit("unexpected agent command")
    command[cli] = str(fake)
    (DRY / "dry-set.json").write_text(json.dumps({**pilot, "agent_command": command}, indent=1, ensure_ascii=False))
    cells = 4 * len(pilot["tasks"])
    run = subprocess.run([sys.executable, "-B", str(pinned.PINNED / "scripts" / "effort_lab.py"), "run", "--set", str(DRY / "dry-set.json"),
                          "--out", str(DRY / "results"), "--replicates", "2", "--jobs", "4", "--max-calls", str(cells),
                          "--max-usd", "150", "--stop-usd", "2", "--max-invalid", str(cells)], capture_output=True, text=True)
    (DRY / "freeze").mkdir(exist_ok=True)
    freeze = subprocess.run([sys.executable, "-I", "-B", "-W", "ignore", str(HERE / "freeze_pilot_v3.py"), str(DRY / "results"), str(DRY / "freeze")],
                            capture_output=True, text=True)
    rows = lab.load_cells(DRY / "results")
    summary = json.loads((DRY / "freeze" / "pilot-summary.json").read_text()) if (DRY / "freeze" / "pilot-summary.json").is_file() else None
    primary = summary["primary"] if summary else {}
    checks = {"run_exit_0": run.returncode == 0, "freeze_exit_0": freeze.returncode == 0, "cells": len(rows) == cells,
              "every_cell_valid": bool(rows) and all(r["valid"] is True for r in rows),
              "sigma2_positive": (primary.get("noise") or {}).get("sigma2", 0) > 0, "n80_is_a_number": isinstance(primary.get("n80_if_equal"), int)}
    result = {"passed": all(checks.values()), "checks": checks, "cells_expected": cells, "cells_found": len(rows),
              "invalid": sorted(r["cell"] for r in rows if r["valid"] is not True), "freeze_primary": primary,
              "run_stdout": run.stdout.strip()[-800:], "run_stderr": run.stderr.strip()[-800:], "freeze_stderr": freeze.stderr.strip()[-1500:]}
    (DRY / "dry-run.json").write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps({k: result[k] for k in ("passed", "checks", "cells_expected", "cells_found", "invalid")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
