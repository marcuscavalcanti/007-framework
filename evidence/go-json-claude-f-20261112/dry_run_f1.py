"""F-1 dry run, no model: the real run_f.sh, shim template and analysis in sibling sandboxes, with a fake CLI. Scenarios:
A. whole run: about 90% reference at xhigh and 80% at medium (a planted defect otherwise), US$0.60 per medium cell and US$2.40 per
   xhigh cell, ambiguous-session in one medium and one xhigh cell of replicate 2, one Claude usage-limit error in replicate 1 after
   the marker (1.8.1 reads it as an invalid cell). Chunks of 20, one marker, one quota gate per chunk.
B. forced hold: US$3 and US$8 per cell, so the marker holds after 40 cells and the analysis reads NO-BUDGET; a restart is refused.
C. quota gate fails before any dispatch (seven-day at 0.79): nothing is dispatched.
D. resume: as A, but the quota gate fails at its 3rd call (run 1 stops after the marker), then the serial re-grade fails once (run 2
   stops after 164 cells), then run 3 completes; the result must equal A's, with one marker line; a 4th start is refused.
E. quota gate on crafted events: blocked top-level status, no unifiedWindows (seven_day type, then another type), an extra window,
   no event, the headroom rule, and a later blocked event.
Also asserts that L2's imputation, with every planned cell missing, gives a mean of exactly -1.0 over the 41 tasks.
Writes dryrun-f1/dry-run.json with the production set hash and the sha256 of every file the sandboxes copied; run_f.sh requires it.
Usage: python3 -I -B dry_run_f1.py"""
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinned_f  # noqa: E402

lab = pinned_f.load()
import analyze_f  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "dryrun-f1"
COPY = ["pinned_f.py", "analyze_f.py", "costcheck_f.py", "quota_f.py", "regrade_f.py", "aa_f.py", "run_f.sh", "critical-floor.json",
        "frozen-reach.json", "shim.template"]
PROMPT = "Reply with the single word OK."
FAKE = r'''#!{python}
import hashlib, json, pathlib, re, subprocess, sys
box = pathlib.Path({box!r})
mode = json.loads((box / "fake-mode.json").read_text())
if {prompt!r} in sys.argv:
    counter = box / "quota-calls"
    calls = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(calls))
    if "events" in mode:
        events = mode["events"]
    else:
        seven = mode["seven_day"]
        status = "rejected" if calls in mode.get("quota_fail_calls", []) else "allowed_warning"
        events = [{{"status": status, "rateLimitType": "seven_day", "utilization": seven, "overageStatus": "rejected",
                   "unifiedWindows": {{"seven_day": {{"utilization": seven, "status": status}}}}}}]
    print(json.dumps({{"type": "system", "subtype": "init", "session_id": "quota"}}), flush=True)
    for info in events:
        print(json.dumps({{"type": "rate_limit_event", "rate_limit_info": info}}), flush=True)
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": False, "session_id": "quota", "usage": {{"input_tokens": 1, "output_tokens": 1}}}}), flush=True)
    sys.exit(0)
if "--version" in sys.argv:
    print("0.0.0 (fake)")
    sys.exit(0)
sys.stdin.read()
cwd = pathlib.Path.cwd()
task, arm, rep = re.match(r"007-(.+)-(medium|xhigh)-r(\d\d)-", cwd.name).groups()
key = f"{{task}}|{{arm}}|{{int(rep)}}"
session = "dry-" + hashlib.sha256(key.encode()).hexdigest()[:12]
init = {{"type": "system", "subtype": "init", "session_id": session, "model": "claude-opus-5-5"}}
cost = mode["cost"][arm]
if key in mode["usage_limit"]:
    for row in (init, {{"type": "result", "subtype": "success", "is_error": True, "session_id": session, "result": "Claude AI usage limit reached|1795039200",
                        "total_cost_usd": 0.0, "usage": {{"input_tokens": 0, "output_tokens": 0}}}}):
        print(json.dumps(row), flush=True)
    sys.exit(1)
reference = int(hashlib.sha256(f"{{task}}|{{arm}}|{{rep}}".encode()).hexdigest(), 16) % 100 < {{"xhigh": 90, "medium": 80}}[arm]
patch = (pathlib.Path({tasks!r}) / task / "reference.patch") if reference else (pathlib.Path({mutants!r}) / (task + ".patch"))
if patch.stat().st_size:
    subprocess.run(["git", "apply", "--recount", "--binary", str(patch)], cwd=cwd, capture_output=True)
result = {{"type": "result", "subtype": "success", "is_error": False, "session_id": session, "total_cost_usd": cost, "num_turns": 1,
          "usage": {{"input_tokens": 1000, "output_tokens": 10}}, "modelUsage": {{"claude-opus-5-5": {{"inputTokens": 1000, "outputTokens": 10, "costUSD": cost}}}}}}
for row in ([init, init, result] if key in mode["ambiguous"] else [init, result]):
    print(json.dumps(row), flush=True)
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make(name, mode, mutants):
    box = HERE.parent / f"claude-f-20261112-{name}"
    if box.exists():
        raise SystemExit(f"{box.name} exists: move it aside first")
    box.mkdir()
    for f in COPY:
        shutil.copy2(HERE / f, box / f)
    (box / "probe").mkdir()
    shutil.copy2(HERE / "probe" / "probe.json", box / "probe" / "probe.json")
    (box / "tasks").symlink_to((HERE / "tasks").resolve())
    (box / "streams").mkdir()
    (box / "fakebin").mkdir()
    (box / "fake-mode.json").write_text(json.dumps(mode))
    fake = box / "fakebin" / "claude"
    fake.write_text(FAKE.format(python=sys.executable, box=str(box), prompt=PROMPT, tasks=str(HERE / "tasks"), mutants=str(mutants)))
    fake.chmod(0o755)
    (box / "bin").mkdir()
    (box / "bin" / "claude").write_text((HERE / "shim.template").read_text().replace("@STREAMS@", str(box / "streams")).replace("@CLI@", str(fake)))
    (box / "bin" / "claude").chmod(0o755)
    config = json.loads((HERE / "f-set.json").read_text())
    command = list(config["agent_command"])
    cli = command.index("--") + 1
    if not command[cli].endswith("/bin/claude"):
        raise SystemExit("unexpected agent command")
    command[cli] = str(box / "bin" / "claude")
    (box / "f-set.json").write_text(json.dumps({**config, "agent_command": command}, indent=1, ensure_ascii=False))
    digest = sha(box / "f-set.json")
    (box / "f1.json").write_text(json.dumps({"f_set_sha256": digest, "cli": str(fake)}))
    for d in ("dryrun", "dryrun-f1"):
        (box / d).mkdir()
    (box / "dryrun" / "dry-run.json").write_text(json.dumps({"passed": True, "stub": "sandbox only"}))
    (box / "dryrun-f1" / "dry-run.json").write_text(json.dumps({"passed": True, "f_set_sha256": digest, "files": {f: sha(box / f) for f in COPY},
                                                                 "stub": "sandbox only"}))
    listed = COPY + ["f-set.json", "f1.json", "bin/claude"]
    sums = subprocess.run(["shasum", "-a", "256", *listed], cwd=box, capture_output=True, text=True, check=True).stdout
    (box / "SHA256SUMS").write_text(sums)
    (box / "GO-3.json").write_text(json.dumps({"sha256sums": hashlib.sha256(sums.encode()).hexdigest(), "stub": "sandbox only"}))
    return box, fake


def start(box, fake):
    env = {**os.environ, "F_QUOTA_CLI": str(fake), "F_REGRADE_ARGS": "--sample 2", "F_MAX_LOAD": "1000"}  # load waits not exercised
    env.pop("F_CAFFEINATED", None)
    return subprocess.run(["sh", str(box / "run_f.sh")], cwd=box, env=env, capture_output=True, text=True)


def log(box):
    rows = []
    for line in (box / "run.log").read_text().splitlines() if (box / "run.log").is_file() else []:
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def invalid(box, rows):
    out = {}
    for r in rows:
        if r["valid"] is not True:
            path = box / "results" / f"{r['cell']}.runner.json"
            receipt = json.loads(path.read_text()) if path.is_file() and path.stat().st_size else {}
            out[r["cell"]] = receipt.get("problem") or r.get("failure_class")
    return out


def main():
    pinned_f.verify()
    config = json.loads((HERE / "f-set.json").read_text())
    production = sha(HERE / "f-set.json")
    if production != json.loads((HERE / "f1.json").read_text())["f_set_sha256"]:
        raise SystemExit("f-set.json does not match f1.json")
    OUT.mkdir(exist_ok=True)
    mutants = OUT / "mutants"
    mutants.mkdir(exist_ok=True)
    for task in config["tasks"]:
        reference = lab.read_patch(HERE / "tasks" / task["id"] / "reference.patch")
        planted = list(lab.mutants(reference, 1, random.Random(f"20261112|{task['id']}")))
        (mutants / f"{task['id']}.patch").write_text(planted[0] if planted else "")
    plan = [(t["id"], rep, arm) for t, rep, arm in lab.plan(config, 2)]
    reach = json.loads((HERE / "frozen-reach.json").read_text())
    rep2 = [c for c in plan if c[1] == 2]
    ambiguous = [next(c for c in rep2 if c[2] == "medium"), next(c for c in rep2 if c[2] == "xhigh")]
    limited = [plan[50]]
    key = lambda c: f"{c[0]}|{c[2]}|{c[1]}"
    name = lambda c: f"{c[0]}-r{c[1]:02d}-{c[2]}"
    base = {"seven_day": 0.1, "cost": {"medium": 0.6, "xhigh": 2.4}, "ambiguous": [key(c) for c in ambiguous], "usage_limit": [key(c) for c in limited]}
    checks, detail = {}, {}

    l2, why = analyze_f.planned_l2([], plan, reach)
    s = lab.paired_interval(lab.reachable_diffs(l2, HERE / "tasks", "medium", "xhigh", reach=reach))
    checks["N4_all_imputed_mean_is_minus_1"] = s["tasks"] == 41 and abs(s["mean"] + 1.0) < 1e-12 and why == {"absent": 164}
    detail["N4"] = {"tasks": s["tasks"], "mean": s["mean"], "imputed": why}

    box, fake = make("dry1-A", base, mutants)
    run = start(box, fake)
    rows = lab.load_cells(box / "results")
    problems = invalid(box, rows)
    streams = list((box / "streams").glob("*.jsonl"))
    stream_hashes = {sha(p) for p in streams}
    valid_hashes = {json.loads((box / "results" / f"{r['cell']}.runner.json").read_text()).get("source_sha256") for r in rows if r["valid"] is True}
    result_a = json.loads((box / "f-result.json").read_text()) if (box / "f-result.json").is_file() else {}
    guard = result_a.get("missing_data_guard", {})
    events = log(box)
    chunks = [e for e in events if e.get("f") == "chunk end"]
    checks["A_run_exit_0"] = run.returncode == 0
    checks["A_164_cells"] = len(rows) == 164
    checks["A_chunks_of_at_most_20_then_40_marker"] = [c["calls"] for c in chunks] == [20, 20, 20, 20, 20, 20, 20, 20, 4] and \
        len(chunks) > 2 and chunks[1]["from"] == 20 and chunks[2]["from"] == 40
    checks["A_one_marker"] = sum("costcheck" in e for e in events) == 1 and (box / "MARKER.json").is_file() and not (box / "HOLD.json").exists()
    checks["A_quota_gate_per_chunk"] = sum("quota" in e for e in events) == len(chunks)
    checks["A_no_unexpected_invalid"] = set(problems) == {name(c) for c in ambiguous + limited}
    checks["A_ambiguous_in_each_arm"] = sorted(problems.get(name(c)) or "" for c in ambiguous) == ["ambiguous-session"] * 2
    checks["A_usage_limit_is_invalid_not_refused"] = all(name(c) in problems for c in limited) and result_a.get("refused") == 0
    checks["A_one_stream_and_sidecar_per_cell"] = len(streams) == 164 and len(list((box / "streams").glob("*.meta.json"))) == 164
    checks["A_valid_streams_match_receipts"] = bool(valid_hashes) and valid_hashes <= stream_hashes
    checks["A_guard_imputes_3"] = guard.get("planned") == 164 and guard.get("imputed_in_L2") == {"invalid": 3}
    checks["A_analysis_ran"] = result_a.get("verdict") in ("PROVEN", "NOT-PROVEN", "KILL", "NO-INFORMATION")
    checks["A_regrade_aa_loadlog"] = (box / "serial" / "regrade.json").is_file() and (box / "aa.json").is_file() and \
        (box / "load.log").is_file() and (box / "load.log").stat().st_size > 0
    checks["A_lock_released"] = not (box / "run.lock").exists()
    detail["A"] = {"exit": run.returncode, "stderr": run.stderr[-600:], "chunks": [(c["from"], c["calls"], c["stop"]) for c in chunks], "invalid": problems,
                   "verdict": result_a.get("verdict"), "L0": {k: [v.get("mean"), v.get("statistic"), v.get("verdict")] for k, v in result_a.get("readings", {}).items()},
                   "L2": {k: [v.get("mean"), v.get("statistic"), v.get("verdict")] for k, v in guard.get("L2", {}).items()},
                   "imputed": guard.get("imputed_in_L2"), "cost_ratio": result_a.get("cost_ratio"), "cost_ratio_worst": result_a.get("cost_ratio_worst")}

    box, fake = make("dry1-B", {**base, "cost": {"medium": 3.0, "xhigh": 8.0}, "ambiguous": [], "usage_limit": []}, mutants)
    run = start(box, fake)
    rows = lab.load_cells(box / "results")
    subprocess.run([sys.executable, "-I", "-B", "-W", "ignore", str(box / "analyze_f.py")], capture_output=True, text=True)
    held = json.loads((box / "f-result.json").read_text()) if (box / "f-result.json").is_file() else {}
    rerun = start(box, fake)
    checks["B_holds_after_40"] = (box / "HOLD.json").is_file() and len(rows) == 40 and run.returncode == 1
    checks["B_analysis_reads_NO_BUDGET"] = held.get("answer") == "NO-BUDGET"
    checks["B_restart_refused"] = rerun.returncode == 1 and len(lab.load_cells(box / "results")) == 40
    detail["B"] = {"exit": run.returncode, "cells": len(rows), "hold": json.loads((box / "HOLD.json").read_text()) if (box / "HOLD.json").is_file() else None,
                   "analysis": held.get("answer"), "restart_stderr": rerun.stderr[-200:]}

    box, fake = make("dry1-C", {**base, "seven_day": 0.79}, mutants)
    run = start(box, fake)
    checks["C_quota_gate_dispatches_nothing"] = run.returncode == 4 and not (box / "results").exists()
    detail["C"] = {"exit": run.returncode, "stderr": run.stderr[-300:]}

    box, fake = make("dry1-D", {**base, "quota_fail_calls": [3]}, mutants)
    run1 = start(box, fake)
    cells1 = len(lab.load_cells(box / "results"))
    (box / "serial").write_text("blocks the re-grade once")
    run2 = start(box, fake)
    cells2 = len(lab.load_cells(box / "results"))
    (box / "serial").unlink()
    run3 = start(box, fake)
    result_d = json.loads((box / "f-result.json").read_text()) if (box / "f-result.json").is_file() else {}
    run4 = start(box, fake)
    events = log(box)
    box_a = HERE.parent / "claude-f-20261112-dry1-A"
    same = result_d.get("verdict") == result_a.get("verdict") and all(
        abs((result_d.get("readings", {}).get(k, {}).get("statistic") or 0) - (v.get("statistic") or 0)) < 1e-9 for k, v in result_a.get("readings", {}).items())
    checks["D_pause_then_regrade_failure_then_completion"] = (run1.returncode, cells1, run2.returncode, cells2, run3.returncode) == (4, 40, 1, 164, 0)
    checks["D_result_equals_A"] = same and invalid(box, lab.load_cells(box / "results")) == invalid(box_a, lab.load_cells(box_a / "results"))
    checks["D_one_marker_line"] = sum("costcheck" in e for e in events) == 1
    checks["D_fourth_start_refused"] = run4.returncode == 1 and "single look" in run4.stderr
    detail["D"] = {"exits": [run1.returncode, run2.returncode, run3.returncode, run4.returncode], "cells": [cells1, cells2], "verdict": result_d.get("verdict"),
                   "L0": {k: v.get("statistic") for k, v in result_d.get("readings", {}).items()},
                   "stderr": [run1.stderr[-200:], run2.stderr[-200:], run4.stderr[-200:]]}

    box, fake = make("dry1-E", base, mutants)
    cases = {
        "blocked_top_level": ([{"status": "rejected", "rateLimitType": "seven_day", "utilization": 0.1, "unifiedWindows": {"seven_day": {"utilization": 0.1, "status": "allowed"}}}], 4),
        "no_windows_seven_day": ([{"status": "allowed", "rateLimitType": "seven_day", "utilization": 0.1}], 0),
        "no_windows_other_type": ([{"status": "allowed", "rateLimitType": "five_hour", "utilization": 0.1}], 4),
        "extra_window": ([{"status": "allowed", "unifiedWindows": {"seven_day": {"utilization": 0.1, "status": "allowed"}, "five_hour": {"utilization": 0.2, "status": "allowed"}}}], 4),
        "no_event": ([], 4),
        "headroom_short": ([{"status": "allowed_warning", "unifiedWindows": {"seven_day": {"utilization": 0.36, "status": "allowed_warning"}}}], 4),
        "headroom_enough": ([{"status": "allowed_warning", "unifiedWindows": {"seven_day": {"utilization": 0.30, "status": "allowed_warning"}}}], 0),
        "second_event_blocked": ([{"status": "allowed", "unifiedWindows": {"seven_day": {"utilization": 0.1, "status": "allowed"}}}, {"status": "rejected"}], 4),
    }
    got = {}
    for case, (events_, expected) in cases.items():
        (box / "fake-mode.json").write_text(json.dumps({**base, "events": events_}))
        got[case] = subprocess.run([sys.executable, "-I", "-B", str(box / "quota_f.py"), str(fake)], capture_output=True, text=True).returncode
    checks["E_quota_gate_cases"] = all(got[c] == e for c, (_, e) in cases.items())
    detail["E"] = got

    files = {f: sha(HERE / f) for f in COPY}
    out = {"passed": all(checks.values()), "checks": checks, "f_set_sha256": production, "files": files, "detail": detail}
    (OUT / "dry-run.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"passed": out["passed"], "checks": checks}, default=str))
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
