"""AMENDMENT-2, change 8: the pilot path end to end with no model, before dispatch. A fake `codex` applies each task's reference patch
and prints a minimal `exec --json` stream; everything else is the built pilot set on the pinned runner: native runner receipt,
grading by the embedded evaluator, then freeze_pilot_v2.py on those cells. Two tasks per pooled repository, 2 attempts per arm.
Writes only under dryrun/. Usage: python3 -I -B dry_run.py"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script directory out
import pinned  # noqa: E402

HERE = Path(__file__).resolve().parent
DRY = HERE / "dryrun"
FAKE = r'''#!{python}
import json, pathlib, re, subprocess, sys
sys.stdin.read()
cwd = pathlib.Path(sys.argv[sys.argv.index("-C") + 1])
task = re.match(r"007-(.+)-(medium|high)-r\d\d-", cwd.name).group(1)
patch = pathlib.Path({tasks!r}) / task / "reference.patch"
applied = subprocess.run(["git", "apply", "--recount", "--binary", str(patch)], cwd=cwd, capture_output=True).returncode == 0
rows = [{{"type": "thread.started", "thread_id": "dry-" + task}}, {{"type": "turn.started"}},
        {{"type": "item.completed", "item": {{"type": "agent_message", "text": "reference applied" if applied else "reference did not apply"}}}},
        {{"type": "turn.completed", "usage": {{"input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": 10, "reasoning_output_tokens": 5}}}}]
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
    DRY.mkdir(exist_ok=True)
    (DRY / "bin").mkdir(exist_ok=True)
    fake = DRY / "bin" / "codex"
    fake.write_text(FAKE.format(python=sys.executable, tasks=str(HERE / "tasks")))
    fake.chmod(0o755)
    picked, seen = [], {}
    for task in pilot["tasks"]:
        if seen.get(task["repo"], 0) < 2:
            seen[task["repo"]] = seen.get(task["repo"], 0) + 1
            picked.append(task)
    command = list(pilot["agent_command"])
    cli = command.index("--") + 1  # the native runner's CLI argument: the pinned Codex binary
    if not command[cli].endswith("/codex"):
        raise SystemExit("unexpected agent command")
    command[cli] = str(fake)
    (DRY / "dry-set.json").write_text(json.dumps({**pilot, "tasks": picked, "agent_command": command}, indent=1, ensure_ascii=False))
    run = subprocess.run([sys.executable, "-B", str(pinned.PINNED / "scripts" / "effort_lab.py"), "run", "--set", str(DRY / "dry-set.json"),
                          "--out", str(DRY / "results"), "--replicates", "2", "--jobs", "4", "--max-calls", str(4 * len(picked)),
                          "--max-usd", "150", "--stop-usd", "2", "--max-invalid", str(4 * len(picked))], capture_output=True, text=True)
    print(json.dumps({"tasks": [t["id"] for t in picked], "run_exit": run.returncode, "run": run.stdout.strip()[-800:], "stderr": run.stderr.strip()[-800:]}))
    (DRY / "freeze").mkdir(exist_ok=True)
    freeze = subprocess.run([sys.executable, "-I", "-B", "-W", "ignore", str(HERE / "freeze_pilot_v2.py"), str(DRY / "results"), str(DRY / "freeze")],
                            capture_output=True, text=True)
    print(freeze.stdout[-3000:], freeze.stderr[-1500:])
    return run.returncode or freeze.returncode


if __name__ == "__main__":
    raise SystemExit(main())
