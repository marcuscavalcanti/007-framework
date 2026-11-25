"""`007 lab`: headless effort replay for any Git repository and any coding agent.

mine        commit pairs A -> B (the next real change to A's sources) with hidden tests and a generated contract. No model.
sensitivity does a latent defect in A show up when B lands? Reference patches minus one hunk (--operator v2: one unit of the
            reference tree reverted, graded on A's hidden tests, three-state decision). No model.
run         every arm × task × replicate in parallel, under a call and money budget. Calls the configured agent.
chain       each candidate of A becomes the base of B, in a private mirror of the repository. No model.
report      frozen gates. A verdict is only as strong as the instrument: an insensitive one yields NO-INFORMATION, never PASS.
            "Same change" is read on reachable behaviours, paired by task, with a symmetric interval rule and a pseudo A/A.
feasibility before spending: how many tasks a verdict needs, from a pilot's noise or a stated SD. No model.
sufficiency drop tasks whose prompt alone cannot reach their hidden tests (calibration cells from a cheap arm). No model.
viability   before spending: VIABLE, NOT-VIABLE (why) or UNKNOWN (what is missing), from tasks, oracle sensitivity, a pilot's
            reach, sufficiency, reference acceptance and power at the break-even margin. No model.

Durable means the change survives the next change. Agents are an argv template (`agent_command`) and tests are an adapter in
lab_accept.py; nothing here knows a vendor or a language.
"""
import argparse
import contextlib
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
import fcntl
import glob
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import tokenize
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli_telemetry  # noqa: E402
import commit_replay  # noqa: E402
import harness_report  # noqa: E402
import replay_eval  # noqa: E402

HERE = Path(__file__).resolve().parent
ACCEPT = ".007-accept"
LITERAL = re.compile(r'"((?:[^"\\\n]|\\.){4,})"|\'((?:[^\'\\\n]|\\.){4,})\'|`((?:[^`\\\n$]|\\.){4,})`|/((?:[^/\\\n]|\\.){4,})/[a-z]*[,) ]')
IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b")
NOISE = {"const", "await", "async", "assert", "equal", "deepEqual", "strictEqual", "match", "test", "true", "false", "null", "None", "True", "False",
         "return", "function", "undefined", "length", "import", "from", "self", "assertEqual", "assertTrue", "assertFalse"}
MARKS = {"node": r'^\s*(test|it|describe)\(\s*(["\'`])(.+?)\2', "unittest": r"^\s*(def)( )(test\w+)", "pytest": r"^\s*(?:async\s+)?(def)( )(test\w+)",
         "go": r"^(func)( )(Test\w+)\(", "custom": r"^\s*(test|it|def|func)( )(\w+)"}
DOCUMENT = re.compile(r"\.(md|json|ya?ml|toml|txt)$")
# Frozen gates. Changing one is a protocol change, never a tuning step.
GATES = {"floor": .25, "ceiling": .90, "min_reduction": .25, "durability_margin": -.05, "min_cells": 40, "min_tasks": 5,
         "min_sensitivity": .30, "min_survivors": 10, "min_mutants": 20, "min_discriminating": 20, "min_signal_tasks": 8, "draws": 10000,
         "reachable_margin": .03, "false_proven": .025}
# Two-sided 95 % Student t quantiles, df 1-30; t975 extends them past 30.
T975 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131,
        2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]
Z80 = 0.8416


def t975(df):
    """Past df 30, the Cornish-Fisher expansion of t around the normal quantile: within 1e-4 of t (the normal 1.96 was 0.06 short at df 40)."""
    if df <= len(T975):
        return T975[df - 1]
    z = 1.959964
    return z + (z ** 3 + z) / (4 * df) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96 * df ** 2) + (3 * z ** 7 + 19 * z ** 5 + 17 * z ** 3 - 15 * z) / (384 * df ** 3)


def _git(repo, *args):
    return commit_replay._git(repo, *args)


def _text(repo, rev, path):
    return _git(repo, "show", f"{rev}:{path}").decode("utf-8", "replace")


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---- contract and reachability: which literals does a test pin that the task never states?

def blocks(text, adapter):
    """Leaf test name -> its source, up to the next test or group."""
    marks = list(re.finditer(MARKS[adapter], text, re.M))
    return {m[3]: text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)] for i, m in enumerate(marks) if m[1] != "describe"}


def tokens(block):
    found = {next(g for g in m.groups() if g) for m in LITERAL.finditer(block)}
    return {t.strip() for t in found if len(t.strip()) >= 4} | (set(IDENTIFIER.findall(block)) - NOISE)


def known_text(tree):
    parts = []
    for path in tree.rglob("*"):
        rel = str(path.relative_to(tree))
        if path.is_file() and (commit_replay.SOURCE.search(rel) or DOCUMENT.search(rel)) and not commit_replay.TEST.search(rel) and path.stat().st_size < 2_000_000:
            parts.append(path.read_text(errors="ignore"))
    return "\n".join(parts)


def added_source(patch_text):
    keep, out = False, []
    for line in patch_text.splitlines():
        if line.startswith("+++ "):
            keep = not commit_replay.TEST.search(line[4:])
        elif keep and line.startswith("+"):
            out.append(line[1:])
    return "\n".join(out)


def pinned(block, reference, known):
    return {x for x in tokens(block) if x in reference and x not in known}


# ---- trees

def extract(repo, rev, dest):
    dest.mkdir(parents=True)
    archive = subprocess.Popen(["git", "-C", str(repo), "archive", rev], stdout=subprocess.PIPE)
    subprocess.run(["tar", "-x", "-C", str(dest)], stdin=archive.stdout, check=True)
    archive.stdout.close()
    if archive.wait():
        raise RuntimeError("git archive failed")


def overlay(repo, tree, rev, files):
    for name in files:  # hidden_target refuses a symlink anywhere on the path: a mined repository cannot redirect host writes
        replay_eval.hidden_target(tree, name).write_bytes(_git(repo, "show", f"{rev}:{name}"))


def collect(tree, spec, sandbox, env):
    """Every test -> outcome in `tree`, through the configured command prefix and environment."""
    sandbox, env = replay_eval.acceptance_policy(sandbox, env)
    shutil.copy(HERE / "lab_accept.py", replay_eval.hidden_target(tree, f"{ACCEPT}/lab_accept.py"))
    replay_eval.hidden_target(tree, f"{ACCEPT}/lab.json").write_text(json.dumps(spec))
    with tempfile.TemporaryDirectory(prefix="lab-report-") as scratch:
        report = Path(scratch) / "report.json"
        argv = [p.replace("{cwd}", str(tree)) for p in sandbox or []] + [sys.executable, "-I", "-B", f"{ACCEPT}/lab_accept.py", "--collect", f"{ACCEPT}/lab.json"]
        subprocess.run(argv, cwd=tree, env={**env, "ACCEPT_REPORT": str(report)}, capture_output=True, timeout=900, check=True)
        return json.loads(report.read_text())


def passing(outcomes):
    return {k for k, v in outcomes.items() if v == "pass"}


# ---- mine

def failure_summary(error, retain_diagnostic_text=False):
    """Exception messages can contain private argv/output; keep a safe class and numeric exit only."""
    label = type(error).__name__
    if retain_diagnostic_text:
        return f"{label}: {error}"[:200]
    if isinstance(error, subprocess.CalledProcessError) and type(error.returncode) is int:
        label += f" (exit {error.returncode})"
    return label

def spec_for(config, test_file):
    packages = config.get("packages") or {"": {}}
    prefix = max((p for p in packages if test_file.startswith(p)), key=len, default=None)
    if prefix is None:
        return None, None
    return prefix, {"adapter": config["adapter"], "prepare": config.get("prepare", []), "env": config.get("test_env", {}), **{k: v for k, v in config.items() if k in ("tests", "cwd", "command")}, **packages[prefix]}


def _commits(raw):
    for block in raw.split("\0")[1:]:
        head, *lines = [l for l in block.split("\n") if l]
        yield head.split(), [l.split("\t", 2) for l in lines if l.count("\t") == 2]


def pool(config):
    repo, today = config["repo"], datetime.fromisoformat(config.get("as_of", _now()))
    since, until = today - timedelta(config.get("since_days", 180)), today - timedelta(config.get("future_days", 30))
    raw = _git(repo, "log", config.get("branch", "main"), "--no-merges", f"--since={since.date()}", f"--until={until.date()}", "--format=%x00%H %P", "--numstat", "--no-renames").decode("utf-8", "replace")
    found = []
    for ids, rows in _commits(raw):
        tests = [f for _, _, f in rows if commit_replay.TEST.search(f) and spec_for(config, f)[0] is not None]
        code = [(a, f) for a, _, f in rows if commit_replay.SOURCE.search(f) and not commit_replay.TEST.search(f)]
        added = sum(int(a) for a, _, _ in rows if a.isdigit())
        changed = sum(int(a) for a, _ in code if a.isdigit())
        if len(ids) == 2 and tests and code and config.get("min_added", 20) <= added <= config.get("max_added", 1500) and changed >= config.get("min_source_lines", 25):
            found.append({"sha": ids[0], "parent": ids[1], "tests": tests, "sources": [f for _, f in code]})
    found.sort(key=lambda c: c["sha"])
    excluded = tuple(config.get("exclude", []))
    return [c for c in found if not c["sha"].startswith(excluded or ("\0",))]


def next_change(config, candidate):
    """The first later commit touching A's sources. It must bring tests: anything else breaks the chain, so A's sources stay frozen until B."""
    repo, sha, branch = config["repo"], candidate["sha"], config.get("branch", "main")
    day = datetime.fromisoformat(_git(repo, "log", "-1", "--format=%cI", sha).decode().strip())
    raw = _git(repo, "log", "--reverse", "--first-parent", f"--before={(day + timedelta(config.get('future_days', 30))).isoformat()}", "--format=%x00%H %P", "--numstat", "--no-renames", f"{sha}..{branch}").decode("utf-8", "replace")
    for ids, rows in _commits(raw):
        files = [f for _, _, f in rows]
        if set(files) & set(candidate["sources"]):
            tests = [f for f in files if commit_replay.TEST.search(f) and spec_for(config, f)[0] is not None]
            return {"sha": ids[0], "parent": ids[1], "tests": tests} if len(ids) == 2 and tests else None
    return None


def prompt_for(config, message, contract):
    trailers = re.compile(r"^(Co-Authored-By|Signed-off-by|Generated-by):", re.I)
    body = "\n".join(l for l in message.splitlines() if not trailers.match(l)).strip()
    text = config.get("prompt_prefix", "Implement the change described below in this repository. Do not commit.") + "\n\n" + body
    if contract:
        text += "\n\nContract. Where the change introduces these names or strings, spell them exactly:\n" + "\n".join(f"- `{c}`" for c in contract)
    return text


def leaf(key, adapter):
    """Test key -> the name its source block carries: go's top-level Test func, unittest's or pytest's method, node's title."""
    name = key.split(" :: ")[-1]
    return name.split("/")[0] if adapter == "go" else name.split(".")[-1].split("[")[0] if adapter in ("unittest", "pytest") else name


def unedited_tests(repo, parent, sha, files, adapter):
    """Leaf test names in `files` whose source the commit left as it was. A name no block carries is never in here."""
    def found(rev):
        out = {}
        for name in files:
            try:
                out.update(blocks(_text(repo, rev, name), adapter))
            except subprocess.CalledProcessError:  # the commit added the file
                pass
        return out
    before = found(parent)
    return {n for n, b in found(sha).items() if before.get(n) == b}


def oracle(config, commit):
    """Hidden tests, baseline and contract of one commit, or a drop reason. A test counts only if it passes twice."""
    repo, sha, parent = config["repo"], commit["sha"], commit["parent"]
    prefix, spec = spec_for(config, commit["tests"][0])
    present = set(_git(repo, "--literal-pathspecs", "ls-tree", "-r", "--name-only", sha, "--", *commit["tests"]).decode("utf-8", "replace").splitlines())
    hidden_files = [f for f in commit["tests"] if f.startswith(prefix) and f in present]  # numstat also lists files the commit deleted
    sandbox, env = config.get("acceptance_sandbox"), config.get("acceptance_env")
    message = _git(repo, "log", "-1", "--format=%B", sha).decode("utf-8", "replace")
    with tempfile.TemporaryDirectory(prefix="lab-mine-") as scratch:
        head_tree, base_tree = Path(scratch) / "head", Path(scratch) / "base"
        extract(repo, sha, head_tree)
        extract(repo, parent, base_tree)
        overlay(repo, base_tree, sha, hidden_files)
        head, base = collect(head_tree, spec, sandbox, env), collect(base_tree, spec, sandbox, env)
        if spec["adapter"] == "go":  # `go test -json` names the package, not the file: match the Test functions the hidden files declare
            declared = {m.group(3) for f in hidden_files for m in re.finditer(MARKS["go"], (head_tree / f).read_text(errors="replace"), re.M)}
            in_hidden = lambda k: k.split(" :: ")[-1].split("/")[0] in declared
        else:
            in_hidden = lambda k: any(k.split(" :: ")[0] == f or f.endswith("/" + k.split(" :: ")[0]) for f in hidden_files)
        unedited = unedited_tests(repo, parent, sha, hidden_files, spec["adapter"])
        hidden = sorted(k for k in passing(head) if in_hidden(k))
        native = set()
        if any(k not in base for k in hidden):  # some hidden test never ran at base (its file does not build there): ask the base's own tests
            extract(repo, parent, Path(scratch) / "native")
            native = passing(collect(Path(scratch) / "native", spec, sandbox, env))
        old = {k for k in hidden if leaf(k, spec["adapter"]) in unedited or (k not in base and k in native)}
        if len(hidden) < config.get("min_hidden", 5) or not [k for k in hidden if k not in passing(base) and k not in old]:
            return "no-red-hidden-tests"
        stable = passing(head) & passing(collect(head_tree, spec, sandbox, env))
        known = known_text(base_tree) + "\n" + message
    hidden = [k for k in hidden if k in stable]
    if len(hidden) + 1 > replay_eval.MAX_ACCEPT_OUTCOMES:  # the report adds "__module__"; past the cap every cell's outcomes read "unavailable"
        return "too-many-hidden-tests"
    reference = _git(repo, "diff", "--binary", parent, sha, "--", ".", *[f":(exclude){f}" for f in hidden_files]).decode("utf-8", "surrogateescape")
    added = added_source(reference)
    contract = set()
    for name in hidden_files:
        for block in blocks(_text(repo, sha, name), spec["adapter"]).values():
            contract |= pinned(block, added, known)
    if len(contract) > config.get("max_contract", 60):
        return "contract-too-large"
    # baseline = old behaviour: green at base; or a hidden test whose source the commit left untouched; or, when the hidden files do
    # not build at base, a test the base's own suite already passed under the same name. Hidden minus baseline is what the change
    # introduces: the reachable scale counts only that.
    baseline = (stable & passing(base)) | {k for k in hidden if k in old}
    return {"spec": spec, "hidden_files": hidden_files, "hidden": hidden, "baseline": sorted(baseline), "reference": reference,
            "contract": sorted(contract), "message": message}


def write_task(config, out, tid, commit, built):
    directory = out / "tasks" / tid
    (directory / "hidden").mkdir(parents=True, exist_ok=True)
    entries = []
    for i, name in enumerate(built["hidden_files"]):
        source = directory / "hidden" / f"{i:02d}-{Path(name).name}"
        source.write_bytes(_git(config["repo"], "show", f"{commit['sha']}:{name}"))
        entries.append((source, name))
    for name, payload in (("hidden.json", json.dumps(built["hidden"])), ("baseline.json", json.dumps(built["baseline"])), ("lab.json", json.dumps(built["spec"])), ("lab_accept.py", (HERE / "lab_accept.py").read_text())):
        (directory / name).write_text(payload)
        entries.append((directory / name, f"{ACCEPT}/{name}"))
    (directory / "reference.patch").write_bytes(built["reference"].encode("utf-8", "surrogateescape"))
    # ponytail: Go only, where a redeclared test name breaks the package; other adapters keep the agent's tests until one collides
    reset = {"reset_to_base": ["*_test.go"]} if built["spec"]["adapter"] == "go" else {}
    return {"id": tid, "repo": config.get("repo_key", "source"), "base": commit["parent"], "accepted": commit["sha"], "prompt": prompt_for(config, built["message"], built["contract"]), "acceptance_timeout_s": 900, **reset,
            "hidden_acceptance": [{"source": str(s), "sha256": hashlib.sha256(s.read_bytes()).hexdigest(), "target": t} for s, t in entries],
            "acceptance_exit_contract": replay_eval.LAB_ACCEPT_EXIT_CONTRACT,
            "acceptance": [[sys.executable, "-I", "-B", f"{ACCEPT}/lab_accept.py", f"{ACCEPT}/lab.json", f"{ACCEPT}/hidden.json", f"{ACCEPT}/baseline.json"]]}


class AcceptanceHarnessError(RuntimeError):
    """The grader or its wrapper failed: the commit is dropped under this name, not as a reference that fails."""


def reference_passes_as_candidate(config, out, task):
    """The reference graded the way `replay_eval` grades a candidate: base snapshot, patch applied, hidden_acceptance (with its
    reset_to_base), acceptance. `oracle` grades the reference at its own tree; a commit that renames or deletes a Go test file
    passes there and fails here, since the reset brings the old test back, and then no candidate can pass."""
    sandbox, env = replay_eval.acceptance_policy(config.get("acceptance_sandbox"), config.get("acceptance_env"))
    with tempfile.TemporaryDirectory(prefix="lab-refcheck-") as scratch:
        workspace = Path(scratch).resolve() / "candidate"
        workspace.mkdir()
        replay_eval.export_snapshot(config["repo"], task["base"], workspace)
        if not apply_patch(workspace, read_patch(out / "tasks" / task["id"] / "reference.patch")):
            return False
        with replay_eval.hidden_acceptance(task, workspace):
            results, passed = replay_eval.acceptance(task, workspace, sandbox, {**env, "ACCEPT_REPORT": str(Path(scratch) / "report.json")})
        if any(r["exit"] not in (0, 1, 3) for r in results):  # lab_accept: 2 is the grader failing (3, a hung suite, is a rejection)
            raise AcceptanceHarnessError("acceptance did not grade")
        return passed


def build(config, candidate, out):
    """One commit -> (task, meta) or a drop reason. Each step is cheaper than the one it guards."""
    repo, sha, parent = config["repo"], candidate["sha"], candidate["parent"]
    if len(_git(repo, "log", "-1", "--format=%B", sha).strip()) < config.get("min_message", 200):
        return None, "message-too-short"
    following = next_change(config, candidate) if config.get("require_next", True) else None
    if config.get("require_next", True) and following is None:
        return None, "no-next-change"
    if following and len(_git(repo, "log", "-1", "--format=%B", following["sha"]).strip()) < config.get("min_next_message", 40):
        return None, "next-message-too-short"
    first = oracle(config, candidate)
    if isinstance(first, str):
        return None, first
    second = oracle(config, following) if following else None
    if isinstance(second, str):
        return None, "next-" + second
    tid = config.get("task_prefix", "LAB-") + sha[:8].upper()
    task = write_task(config, out, tid, candidate, first)
    next_task = write_task(config, out, tid + "-next", following, second) if following else None
    # ponytail: an unreachable task is dropped; keeping it means teaching the oracle which test files the reference removed
    failed = "error"
    try:
        failed = next((prefix for prefix, t in (("", task), ("next-", next_task)) if t and not reference_passes_as_candidate(config, out, t)), None)
    finally:
        if failed is not None:  # dropped or errored: neither leaves a task directory behind
            for name in (tid, tid + "-next"):
                shutil.rmtree(out / "tasks" / name, ignore_errors=True)
    if failed is not None:
        return None, failed + "reference-fails-as-candidate"
    if not following:
        return task, {"id": tid, "spec": first["spec"], "contract": first["contract"], "hidden": len(first["hidden"])}
    changed = [l.split("\t") for l in _git(repo, "diff-tree", "--no-commit-id", "--name-status", "--no-renames", "-r", sha).decode().splitlines()]
    rewind = [[status, name] for status, name in changed if name not in first["hidden_files"]]
    return task, {"id": tid, "spec": first["spec"], "next": next_task, "next_spec": second["spec"], "rewind": rewind, "contract": first["contract"], "next_contract": second["contract"],
                  "hidden": len(first["hidden"]), "next_hidden": len(second["hidden"])}


def mine(config, out, jobs):
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    retain_text = replay_eval._diagnostic_retention(config, out)
    log = out / "mine.jsonl"
    seen = {json.loads(l)["sha"]: json.loads(l) for l in log.read_text().splitlines()} if log.exists() else {}
    candidates = pool(config)
    random.Random(config.get("seed", 1)).shuffle(candidates)
    want, futures = config.get("want", 12), set()
    kept = sum(1 for row in seen.values() if row.get("kept"))
    queue = iter(c for c in candidates if c["sha"] not in seen)

    def work(candidate):
        try:
            task, meta = build(config, candidate, out)
        except Exception as error:  # one unbuildable commit must not end the scan
            task, meta = None, failure_summary(error, retain_text)
        return candidate, task, meta
    with ThreadPoolExecutor(jobs) as pool_:
        while True:
            while len(futures) < jobs and kept + len(futures) < want:
                candidate = next(queue, None)
                if candidate is None:
                    break
                futures.add(pool_.submit(work, candidate))
            if not futures:
                break
            finished, futures = wait(futures, return_when=FIRST_COMPLETED)
            for future in finished:
                candidate, task, meta = future.result()
                row = {"sha": candidate["sha"], "kept": bool(task)}
                if task:
                    kept += 1
                    (out / "tasks" / task["id"] / "task.json").write_text(json.dumps({"task": task, "meta": meta}, indent=1, ensure_ascii=False))
                else:
                    row["drop"] = meta
                with log.open("a") as handle:
                    handle.write(json.dumps(row) + "\n")
                print(candidate["sha"][:8], "kept" if task else "dropped (private diagnostic)" if retain_text else row["drop"], flush=True)
    return write_set(config, out)


def write_set(config, out):
    loaded = [json.loads(p.read_text()) for p in sorted((out / "tasks").glob("*/task.json"))]
    replay = {k: config[k] for k in ("seed", "agent_command", "arms", "served_identity", "acceptance_sandbox", "acceptance_env", "compare", "retain_diagnostic_text") if k in config}
    replay.update(repos={config.get("repo_key", "source"): config["repo"]}, retain_candidate_patch=True, tasks=[x["task"] for x in loaded], gates=GATES)
    (out / "replay-set.json").write_text(json.dumps(replay, indent=1, ensure_ascii=False))
    (out / "pairs.json").write_text(json.dumps({x["meta"]["id"]: x["meta"] for x in loaded}, indent=1, ensure_ascii=False))
    return len(loaded)


# ---- the chain: a candidate of A in the place of the real A, right before B

def rewound(repo, task, meta, dest):
    """B's parent with A's non-test files back at A's parent: the tree a candidate of A applies to."""
    extract(repo, meta["next"]["base"], dest)
    for status, name in meta["rewind"]:
        if status == "A":
            (dest / name).unlink(missing_ok=True)
        else:
            overlay(repo, dest, task["base"], [name])


def read_patch(path):
    """A patch as text with its bytes intact: read_text() turns CRLF into LF, and a patch touching CRLF lines then fails to apply."""
    return Path(path).read_bytes().decode("utf-8", "surrogateescape")


def apply_patch(tree, patch_text):
    if not patch_text.strip():
        return True
    if not (tree / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=tree, check=True, capture_output=True)
    # --whitespace=nowarn overrides apply.whitespace=fix (which strips CR); the rest of the operator's config stays, since the
    # snapshot was checked out under it too (core.autocrlf)
    return subprocess.run(["git", "apply", "--recount", "--binary", "--whitespace=nowarn", "-"], cwd=tree,
                          input=patch_text.encode(errors="surrogateescape"), capture_output=True).returncode == 0


def oracle_passes(directory, tree, spec, sandbox, env):
    ok = passing(collect(tree, spec, sandbox, env))
    return set(json.loads((directory / "hidden.json").read_text())) <= ok and set(json.loads((directory / "baseline.json").read_text())) <= ok


def commit_tree(mirror, tree, parent):
    """A commit in the private mirror holding `tree`. The source repository is never written."""
    env = {**commit_replay.GIT_ENV, "GIT_DIR": str(mirror), "GIT_WORK_TREE": str(tree), "GIT_INDEX_FILE": str(tree.parent / "index"),
           "GIT_AUTHOR_NAME": "007 lab", "GIT_AUTHOR_EMAIL": "lab@007.invalid", "GIT_COMMITTER_NAME": "007 lab", "GIT_COMMITTER_EMAIL": "lab@007.invalid"}
    run_ = lambda *a: subprocess.run(["git", *a], env=env, capture_output=True, check=True).stdout.decode().strip()
    shutil.rmtree(tree / ".git", ignore_errors=True)
    run_("add", "-A", "-f", ":/", ":(exclude).007-accept")
    return run_("commit-tree", run_("write-tree"), "-p", parent, "-m", "lab candidate")


def chain(config_path, results, out):
    """Stage 2: one task per stage-1 cell, B on top of that cell's candidate, always at the reference arm's effort."""
    config = json.loads(config_path.read_text())
    pairs = json.loads((config_path.parent / "pairs.json").read_text())
    tasks = {t["id"]: t for t in config["tasks"]}
    parent_state = sealed_state(config, results)
    if parent_state["state"] == "unbound":
        raise ValueError("stage 1 is unbound from its seal: chain refuses to build on it")
    if parent_state["compare_changed"]:  # compare.reference picks stage 2's arm: it must be the one sealed with stage 1
        raise ValueError("the comparison changed after stage 1 was sealed: chain refuses to pick stage 2's arm from it")
    parent = parent_state["sha256"]
    repo = next(iter(config["repos"].values()))
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    mirror = out / "mirror.git"
    if not mirror.exists():
        subprocess.run(["git", "clone", "-q", "--bare", "--no-hardlinks", str(repo), str(mirror)], check=True, capture_output=True)
    next_tasks, broken, aa, copies = [], [], parent_state.get("aa"), 0
    for row in load_cells(results):
        if aa and row.get("arm") == aa["label"]:  # an A/A copy is no part of the contrast stage 2 serves
            copies += 1
            continue
        meta, task = pairs[row["task"]], tasks[row["task"]]
        if not isinstance(row.get("candidate_patch"), dict) or row.get("failure_class") == "provider-rate-limit" or contaminated(row):
            broken.append(row["cell"])  # no candidate to chain from: a controller error, a refused call, or one that read the answer
            continue
        with tempfile.TemporaryDirectory(prefix="lab-chain-") as scratch:
            tree = Path(scratch) / "tree"
            rewound(repo, task, meta, tree)
            if not apply_patch(tree, read_patch(results / row["candidate_patch"]["path"])):
                broken.append(row["cell"])
                continue
            base = commit_tree(mirror, tree, meta["next"]["base"])
        next_tasks.append({**meta["next"], "id": row["cell"] + "-next", "base": base})
    arm = config["arms"][config["compare"]["reference"]]
    replay = {**config, "repos": {next(iter(config["repos"])): str(mirror)}, "arms": {"next": arm}, "tasks": next_tasks, "broken_chains": broken,
              "parent_manifest_sha256": parent}
    data = json.dumps(replay, indent=1, ensure_ascii=False)
    existing = out / "replay-set.json"
    if existing.is_file() and json.loads(existing.read_text()) != replay:  # a stage 2 sealed on it would no longer resume
        raise ValueError(f"a different chain set already exists in {out}: chain into a new directory")
    existing.write_text(data)
    (out / "pairs.json").write_text("{}")
    return {"tasks": len(next_tasks), "broken": broken, **({"aa_not_chained": copies} if aa else {})}


# ---- sensitivity

MUTATION_OPERATOR = "minus-one-hunk/2"  # 2: every unsampled block kept whole; no mutant of a one-hunk reference


def hunks(patch_text):
    """(file header, [hunks]) per `diff --git` block, in order. A binary block (a `GIT binary patch` line, not the phrase inside a
    text line) or a block with no `@@` (rename, mode change, empty file) is kept whole as its header, with no hunks."""
    out = []
    for chunk in re.split(r"(?m)^(?=diff --git )", patch_text):
        if chunk.startswith("diff --git "):
            parts = [] if re.search(r"(?m)^GIT binary patch$", chunk) else re.split(r"(?m)^(?=@@ )", chunk)
            out.append((parts[0], parts[1:]) if len(parts) > 1 else (chunk, []))
    return out


def mutants(patch_text, limit, rng):
    """The reference minus one hunk, sampled: a change partly done, as a weaker agent might leave it. Every other block, binary and
    hunk-less ones included, stays as in the reference. A block whose only hunk is the sampled one leaves whole, header included,
    so a mode change or rename carried by that block goes with it. A reference with one hunk has no mutant."""
    files = hunks(patch_text)
    index = [(i, j) for i, (_, parts) in enumerate(files) for j in range(len(parts))]
    rng.shuffle(index)
    if len(index) < 2:
        return
    for i, j in index[:limit]:
        yield "".join(head + "".join(p for n, p in enumerate(parts) if not (k == i and n == j)) for k, (head, parts) in enumerate(files) if not (k == i and len(parts) == 1))


def probe(config, out, tid, patch_text, real_next):
    """(passes A's oracle, passes B's oracle once the real B lands on it), or None when the patch cannot be applied."""
    pairs = json.loads((out / "pairs.json").read_text())
    meta, repo = pairs[tid], next(iter(config["repos"].values()))
    task = next(t for t in config["tasks"] if t["id"] == tid)
    sandbox, env = config.get("acceptance_sandbox"), config.get("acceptance_env")
    with tempfile.TemporaryDirectory(prefix="lab-probe-") as scratch:
        now = Path(scratch) / "now"
        extract(repo, task["base"], now)
        if not apply_patch(now, patch_text):
            return None
        overlay(repo, now, task["accepted"], [e["target"] for e in task["hidden_acceptance"] if not e["target"].startswith(ACCEPT)])
        first = oracle_passes(out / "tasks" / tid, now, meta["spec"], sandbox, env)
        if "next" not in meta:
            return first, None
        later = Path(scratch) / "later"
        rewound(repo, task, meta, later)
        if not apply_patch(later, patch_text) or not apply_patch(later, real_next):
            return first, None  # a textual conflict says nothing about behaviour: neither caught nor missed
        return first, oracle_passes(out / "tasks" / f"{tid}-next", later, meta["next_spec"], sandbox, env)


def sensitivity(config_path, jobs, per_task=6):
    config = json.loads(config_path.read_text())
    out = config_path.parent
    pairs = json.loads((out / "pairs.json").read_text())
    repo, rng, work = next(iter(config["repos"].values())), random.Random(config.get("seed", 1)), []
    for task in config["tasks"]:
        meta = pairs[task["id"]]
        real_next = _git(repo, "diff", "--binary", meta["next"]["base"], meta["next"]["accepted"]).decode("utf-8", "surrogateescape") if "next" in meta else ""
        reference = read_patch(out / "tasks" / task["id"] / "reference.patch")
        work.append((task["id"], True, reference, real_next))
        work += [(task["id"], False, m, real_next) for m in mutants(reference, per_task, rng)]

    def one(item):
        tid, control, patch_text, real_next = item
        try:
            return tid, control, probe(config, out, tid, patch_text, real_next)
        except Exception as error:
            return tid, control, failure_summary(error)
    with ThreadPoolExecutor(jobs) as pool_:
        rows = list(pool_.map(one, work))
    # each control again, one at a time: an oracle whose grade moves with the machine's load (yaegi) is not an instrument
    serial = {tid: value for tid, _, value in map(one, [item for item in work if item[1]])}
    unstable = sorted(tid for tid, control, value in rows if control and serial[tid] != value)
    result = {**sensitivity_summary(rows, unstable), "operator": MUTATION_OPERATOR}
    (out / "sensitivity.json").write_text(json.dumps(result, indent=1))
    return result


def sensitivity_summary(rows, load_sensitive=()):
    """`load_sensitive`: tasks whose control graded differently in the parallel pass and the serial repeat. They leave the
    measure, and `run` refuses a set that still holds them."""
    rows = [r for r in rows if r[0] not in set(load_sensitive)]
    controls = [r for r in rows if r[1]]
    survivors = [r for r in rows if not r[1] and isinstance(r[2], tuple) and r[2][0] and r[2][1] is not None]
    conflicts = sum(not r[1] and isinstance(r[2], tuple) and r[2][0] and r[2][1] is None for r in rows)
    caught = sum(not r[2][1] for r in survivors)
    per = {}
    for tid, _, value in survivors:
        per.setdefault(tid, [0, 0])
        per[tid][0] += 1
        per[tid][1] += not value[1]
    conformant = [r[0] for r in controls if isinstance(r[2], tuple) and r[2][0] and r[2][1] is not False]
    # a rejected mutant means something only where the reference patch passes: an oracle that rejects everything is not sensitive
    reference_ok = {r[0] for r in controls if isinstance(r[2], tuple) and r[2][0]}
    tried = [r for r in rows if not r[1] and isinstance(r[2], tuple) and r[0] in reference_ok]
    rejected = sum(not r[2][0] for r in tried)
    return {"immediate": {"mutants": len(tried), "rejected": rejected, "sensitivity": rejected / len(tried) if tried else None,
                          "passed": len(tried) >= GATES["min_mutants"] and rejected / len(tried) >= GATES["min_sensitivity"]},
            "mutants": len(rows) - len(controls), "survive_first_oracle": len(survivors), "caught_by_next_change": caught, "sensitivity": caught / len(survivors) if survivors else None,
            "conformant": conformant, "tasks": len(controls), "per_task": per, "errors": sum(isinstance(r[2], str) for r in rows), "unapplied": sum(r[2] is None for r in rows), "conflicts": conflicts,
            "load_sensitive": sorted(load_sensitive),
            "passed": bool(survivors) and len(survivors) >= GATES["min_survivors"] and caught / len(survivors) >= GATES["min_sensitivity"]}


# ---- sensitivity v2: the reference tree with one unit reverted, built line by line (no reduced patch to misapply)

OPERATOR_V2 = "revert-one-unit/1"
U0 = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", re.M)
CODE_TOKEN = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`[^`]*`|\n|\w+|[^\s\w]', re.S)
C_LIKE = re.compile(r"\.(go|(c|m)?(j|t)sx?|java|kt|c|cc|cpp|h|hpp|cs|swift|rs|scala|php)$")
# a directive written as a comment is code: build tags, go:embed/generate, cgo exports, a shebang, a coding cookie
DIRECTIVE = r"//go:|//\s*\+build|//export\s|#!|#.*coding[:=]"
COMMENT_LINE = re.compile(rf"^\s*(?!{DIRECTIVE})($|//|/\*|\*|#)")


def _lines(data):
    """Lines as git counts them: cut at \\n only, bytes intact."""
    return re.findall(r"[^\n]*\n|[^\n]+\Z", data.decode("utf-8", "surrogateescape"))


def _blob(repo, rev, path):
    try:
        return _lines(_git(repo, "show", f"{rev}:{path}"))
    except subprocess.CalledProcessError:
        return None


def units(repo, base, head, skip=()):
    """([path, lines at base | None, lines at head | None, [(base start, base n, head start, head n)]] per non-test text file,
    files without units): the hunks of a zero-context diff. A binary file, a symbolic link and a submodule have no unit and stay
    as at head; `skip` names the task's hidden files, whatever the test pattern says of them."""
    files, binaries = [], 0
    raw = _git(repo, "diff", "--raw", "-z", "--no-renames", "--no-abbrev", base, head).decode("utf-8", "surrogateescape").split("\0")
    irregular = {path for meta, path in zip(raw[::2], raw[1::2]) if {meta.split()[0].lstrip(":"), meta.split()[1]} - {"100644", "100755", "000000"}}
    for row in filter(None, _git(repo, "diff", "--numstat", "-z", "--no-renames", base, head).decode("utf-8", "surrogateescape").split("\0")):
        added, _, path = row.split("\t", 2)
        if commit_replay.TEST.search(path) or path in skip:
            continue
        if added == "-" or path in irregular:  # a link's "lines" are its target: never a unit, and _put would write through it
            binaries += 1
            continue
        # the operator's unit boundaries must not follow the host's git configuration
        diff = _git(repo, "diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames", "--diff-algorithm=myers", "--no-indent-heuristic", "--inter-hunk-context=0",
                    base, head, "--", f":(literal){path}").decode("utf-8", "surrogateescape")
        hunks = [(int(a) - (b != "0"), int(b or 1), int(c) - (d != "0"), int(d or 1)) for a, b, c, d in U0.findall(diff)]
        if hunks:
            files.append([path, _blob(repo, base, path), _blob(repo, head, path), hunks])
    return files, binaries


def revert(base_lines, head_lines, hunk):
    b0, bn, h0, hn = hunk
    return (head_lines or [])[:h0] + (base_lines or [])[b0:b0 + bn] + (head_lines or [])[h0 + hn:]


def rebuilds(base_lines, head_lines, hunks):
    """base + every unit = head and head - every unit = base: the parse is the change."""
    base_lines, head_lines = base_lines or [], head_lines or []
    forward, backward = list(base_lines), list(head_lines)
    for b0, bn, h0, hn in reversed(hunks):
        forward[b0:b0 + bn] = head_lines[h0:h0 + hn]
        backward[h0:h0 + hn] = base_lines[b0:b0 + bn]
    return forward == head_lines and backward == base_lines


def _code(lines, path):
    """What a compiler reads: comments out, runs of line breaks as one. None when it cannot be read (never equivalent then)."""
    text = "".join(lines or [])
    if path.endswith(".py"):
        try:
            return [(t.type, t.string) for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type not in (tokenize.COMMENT, tokenize.NL)]
        except (tokenize.TokenError, SyntaxError, ValueError):  # ValueError: bytes that are not UTF-8, kept as surrogates
            return None
    if not C_LIKE.search(path):
        return [line.rstrip() for line in text.split("\n")]  # ponytail: other files equivalent only up to trailing spaces
    out = []
    for token in CODE_TOKEN.findall(text):
        if not token.startswith(("//", "/*")) and not (token == "\n" and out and out[-1] == "\n"):
            out.append(token)
    return out


def equivalent(path, base_lines, head_lines, hunk):
    """Same tokens as the reference, and every line the unit touches is blank or a comment: a regex literal holding `//` cannot pass."""
    b0, bn, h0, hn = hunk
    touched = (base_lines or [])[b0:b0 + bn] + (head_lines or [])[h0:h0 + hn]
    if not all(COMMENT_LINE.match(line) for line in touched):
        return False
    mine = _code(revert(base_lines, head_lines, hunk), path)
    return mine is not None and mine == _code(head_lines, path)


def _put(tree, path, lines):
    target = replay_eval.hidden_target(tree, path)
    if lines is None:
        target.unlink(missing_ok=True)
    else:
        target.write_bytes("".join(lines).encode("utf-8", "surrogateescape"))


def _grade(directory, tree, spec, sandbox, env):
    """pass, contract (a hidden or baseline test absent or `error`: it did not build or load) or assert (all ran, one failed)."""
    outcomes = collect(tree, spec, sandbox, env)
    need = json.loads((directory / "hidden.json").read_text()) + json.loads((directory / "baseline.json").read_text())
    if all(outcomes.get(k) == "pass" for k in need):
        return "pass"
    return "contract" if any(outcomes.get(k) in (None, "error") for k in need) else "assert"


def sensitivity_v2(config_path, jobs, floor=None):
    """Every unit of every task: trivial, equivalent, out-of-scope, invalid, or valid and then rejected or survived. No model."""
    config = json.loads(config_path.read_text())
    out = config_path.parent
    pairs = json.loads((out / "pairs.json").read_text())
    repo = next(iter(config["repos"].values()))
    sandbox, env = config.get("acceptance_sandbox"), config.get("acceptance_env")
    hidden_of = lambda task: [e["target"] for e in task["hidden_acceptance"] if not e["target"].startswith(ACCEPT)]
    work, tasks = {}, {}
    for task in config["tasks"]:
        files, binaries = units(repo, task["base"], task["accepted"], hidden_of(task))
        tasks[task["id"]] = {"files": len(files), "units": sum(len(f[3]) for f in files), "binaries": binaries,
                             "construction": all(rebuilds(f[1], f[2], f[3]) for f in files)}
        work[task["id"]] = (task, files)

    def tree_run(tid, kind, index=None, unit=None):
        task, files = work[tid]
        spec, directory = pairs[tid]["spec"], out / "tasks" / tid
        try:
            with tempfile.TemporaryDirectory(prefix="lab-v2-") as scratch:
                tree = Path(scratch) / "tree"
                extract(repo, task["base"] if kind in ("base", "visible-base") else task["accepted"], tree)
                if kind == "base":
                    overlay(repo, tree, task["accepted"], hidden_of(task))
                elif kind == "deleted":
                    _put(tree, files[index][0], None)
                elif kind == "mutant":
                    path, base_lines, head_lines, hunks = files[index]
                    reverted = revert(base_lines, head_lines, hunks[unit])
                    _put(tree, path, None if base_lines is None and reverted == [] else reverted)
                grade = None if kind.startswith("visible") else _grade(directory, tree, spec, sandbox, env)
                if kind in ("visible-base", "visible-reference", "mutant"):
                    for name in hidden_of(task) if kind != "visible-base" else []:
                        _put(tree, name, _blob(repo, task["base"], name))
                    return grade, passing(collect(tree, spec, sandbox, env))
                return grade, None
        except Exception as error:
            return failure_summary(error), None

    first = [(tid, kind, None) for tid in work if tasks[tid]["construction"] for kind in ("reference", "base", "visible-base", "visible-reference")]
    first += [(tid, "deleted", i) for tid, (_, files) in work.items() if tasks[tid]["construction"] for i, f in enumerate(files) if f[2] is not None]
    with ThreadPoolExecutor(jobs) as pool_:
        done = dict(zip(first, pool_.map(lambda item: tree_run(*item), first)))
    rows, second = [], []
    for tid, (task, files) in work.items():
        meta = tasks[tid]
        if meta["construction"]:
            meta.update(reference=done[(tid, "reference", None)][0], base=done[(tid, "base", None)][0])
            seen_base, seen_reference = done[(tid, "visible-base", None)][1], done[(tid, "visible-reference", None)][1]
            visible = (seen_base or set()) & (seen_reference or set())
            # a visible run that errored would leave no test to break: every build-breaking revert would count as a rejection
            meta.update(visible_tests=len(visible), visible_control=seen_base is not None and seen_reference is not None)
        meta["control"] = ("operator-invalid" if not meta["construction"]
                           else "ok" if meta["reference"] == "pass" and meta["base"] in ("contract", "assert") and meta["visible_control"]
                           else "control-failed")
        if meta["control"] != "ok":
            continue
        trivial = meta["units"] == 1 and not meta["binaries"]
        for i, (path, base_lines, head_lines, hunks) in enumerate(files):
            loaded = head_lines is None or done[(tid, "deleted", i)][0] != "pass"
            for k, hunk in enumerate(hunks):
                row = {"task": tid, "file": i, "unit": k}
                row["class"] = ("trivial" if trivial else "equivalent" if equivalent(path, base_lines, head_lines, hunk)
                                else "out-of-scope" if not loaded else None)
                if row["class"] == "equivalent":
                    row["loaded"] = loaded
                rows.append(row)
                if row["class"] in (None, "equivalent"):
                    second.append((row, visible))
    with ThreadPoolExecutor(jobs) as pool_:
        graded = list(pool_.map(lambda item: tree_run(item[0]["task"], "mutant", item[0]["file"], item[0]["unit"]), second))
    for (row, visible), (grade, seen) in zip(second, graded):
        if grade not in ("pass", "contract", "assert"):
            row.update({"class": "error", "outcome": grade})
        elif row["class"] == "equivalent":
            row["outcome"] = grade
        elif not visible <= (seen or set()):
            row["class"] = "invalid"
        else:
            row.update({"class": "valid", "outcome": {"pass": "survived", "contract": "rejected-contract", "assert": "rejected-assert"}[grade]})
    result = {"operator": OPERATOR_V2, "seed": config.get("seed", 1), "floor": floor, "jobs": jobs,
              **sensitivity_v2_summary(rows, tasks, floor, config.get("seed", 1)), "tasks": tasks, "rows": rows}
    (out / "sensitivity-v2.json").write_text(json.dumps(result, indent=1))
    return {k: v for k, v in result.items() if k not in ("tasks", "rows")}


def _interval(values, seed, draws):
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(draws))
    return [means[int(.025 * draws)], means[int(.975 * draws) - 1]]


def _binomial_bounds(k, n, alpha=.025):
    """Clopper-Pearson limits for k of n, by bisection on the binomial tail (no beta quantile in the standard library)."""
    def tail(p, lo, hi):
        return sum(math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * math.log(p) + (n - i) * math.log1p(-p)) for i in range(lo, hi + 1))
    def solve(f):  # f is increasing in p on (0, 1)
        a, b = 0.0, 1.0
        for _ in range(60):
            m = (a + b) / 2
            a, b = (m, b) if f(m) < alpha else (a, m)
        return (a + b) / 2
    low = 0.0 if k == 0 else solve(lambda p: tail(p, k, n))            # P(X >= k) reaches alpha
    high = 1.0 if k == n else 1 - solve(lambda q: tail(1 - q, 0, k))    # P(X <= k) reaches alpha, in q = 1 - p
    return low, high


def sensitivity_v2_summary(rows, tasks, floor=None, seed=1, draws=GATES["draws"]):
    """Per-task means with a task bootstrap, and the three-state decision. Only tasks whose controls passed are measured."""
    ok = {tid for tid, meta in tasks.items() if meta["control"] == "ok"}
    rows = [r for r in rows if r["task"] in ok]
    funnel = {c: sum(r["class"] == c for r in rows) for c in ("trivial", "invalid", "equivalent", "out-of-scope", "valid", "error")}
    valid = [r for r in rows if r["class"] == "valid"]
    parts = {o: sum(r["outcome"] == o for r in valid) for o in ("rejected-contract", "rejected-assert", "survived")}
    per_task, coverage = {}, []
    for tid in sorted(ok):
        mine = [r for r in rows if r["task"] == tid]
        hits = [r["outcome"] != "survived" for r in mine if r["class"] == "valid"]
        if hits:
            per_task[tid] = sum(hits) / len(hits)
        if sum(r["class"] != "trivial" for r in mine):
            coverage.append(len(hits) / sum(r["class"] != "trivial" for r in mine))
    equivalents = [r for r in rows if r["class"] == "equivalent"]
    specificity = sum(r["outcome"] == "pass" for r in equivalents) / len(equivalents) if equivalents else None
    sensitivity = statistics.fmean(per_task.values()) if per_task else None
    interval = _interval(list(per_task.values()), seed, draws) if per_task else None
    if interval:
        # Equal per-task rates give the task bootstrap zero width: 20 of 20 rejected would read [1, 1] and pass any floor. The
        # pooled binomial interval caps it in every case, so no result reads better than a perfect one of the same size.
        # ponytail: the cap takes mutants as independent; with tasks as the unit it would be wider still
        low, high = _binomial_bounds(len(valid) - parts["survived"], len(valid))
        interval = [min(interval[0], low), max(interval[1], high)]
    if specificity is not None and specificity < 1:
        decision = "fails"
    elif len(valid) < 20 or len(per_task) < GATES["min_signal_tasks"]:
        decision = "no-information"
    elif floor is None:
        decision = "floor-unset"
    elif interval[1] < floor:
        decision = "fails"
    elif interval[0] >= floor and specificity == 1 and any(r.get("loaded") for r in equivalents):
        decision = "passes"  # an equivalent in a file no hidden test loads passes whatever the oracle is: it cannot carry specificity
    else:
        decision = "indeterminate"
    return {"decision": decision, "sensitivity": sensitivity, "interval": interval, "specificity": specificity, "equivalents": len(equivalents),
            "equivalents_loaded": sum(bool(r.get("loaded")) for r in equivalents),  # only these can fail: `passes` needs one
            "coverage": statistics.fmean(coverage) if coverage else None, "funnel": funnel, "valid_outcomes": parts, "per_task": per_task,
            "tasks_measured": len(ok), "tasks_with_valid": len(per_task),
            "controls": {c: sum(m["control"] == c for m in tasks.values()) for c in ("ok", "control-failed", "operator-invalid")}}


# ---- run

AA_SUFFIX = "-aa"


def aa_arms(config, arm):
    """The set's arms plus the A/A copy of `arm` (`run --aa`): a third label, `<arm>-aa`, with the arm's own model, effort and
    doctrine, so its cells are planned, shuffled into each replicate, dispatched, charged and stopped like the arm's. Its agent sees a
    token like any other cell's (`blind_salt`); in a run sealed before 1.11.0 its workspace takes the arm's name (`aa_of`)."""
    arms = config.get("arms", {})
    if arm not in arms:
        raise ValueError(f"--aa names no arm of the set: {arm}")
    if arm + AA_SUFFIX in arms:
        raise ValueError(f"the set already has an arm named {arm + AA_SUFFIX}: --aa cannot add its copy")
    return {**arms, arm + AA_SUFFIX: {**arms[arm], "aa_of": arm}}


def plan(config, replicates):
    """Whole replicates first, so a pilot of replicate 1 is a prefix of the full run and nothing is wasted."""
    cells, rng = [], random.Random(config["seed"])
    for rep in range(1, replicates + 1):
        block = [(t, rep, a) for t in config["tasks"] for a in config["arms"]]
        rng.shuffle(block)
        cells += block
    replay_eval.validate_cell_artifacts(config["tasks"], config["arms"], replicates)
    return cells


def _error_detail(error, retain=True):
    """Type, message (first 300 characters; None unless the set retains diagnostic text, as replay cells do) and the innermost
    traceback frame of a controller error."""
    frames = traceback.extract_tb(error.__traceback__)
    where = f"{Path(frames[-1].filename).name}:{frames[-1].lineno} in {frames[-1].name}" if frames else None
    return {"type": type(error).__name__, "message": str(error)[:300] if retain else None, "where": where}


def _controller_failure(out, task, arm, rep, error, retain=True):
    """The result of a cell whose controller raised: invalid, never retried, its receipt (if the agent ran) kept and bound."""
    cid = replay_eval.cell_id(task, arm, rep)
    path, receipt = out / f"{cid}.json", out / f"{cid}.runner.json"
    if path.exists():  # the cell finished before the error: its own result stands
        return json.loads(path.read_text())
    row = {"schema": "007-framework/replay-cell/v1", "task": task["id"], "arm": arm, "replicate": rep, "valid": False, "accepted": False,
           "failure_class": f"controller-error:{type(error).__name__}", "cost_usd": "unmeasured", "acceptance_outcomes": "unavailable",
           "runner_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest() if receipt.is_file() else "unmeasured",
           "controller_error": _error_detail(error, retain)}
    path.write_text(json.dumps(row))
    return row


RATE_LIMIT_COOLDOWN_S = 600


def _receipt(out, cid):
    """The cell's runner receipt as an object, or {} when it is absent, unreadable or not an object (it names no refusal)."""
    receipt = out / f"{cid}.runner.json"
    try:
        value = json.loads(receipt.read_text()) if receipt.is_file() else {}
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def usage_limit(out, cid):
    """{"source", "resets_at"} when the Claude account's usage limit stopped the call, else None. native_runner writes the
    receipt's `usage_limit` from the stream only: the CLI's "usage limit reached" result or a rejected rate_limit_event, with the
    reset time the provider gave (Unix seconds) or None."""
    value = _receipt(out, cid)
    limit = value.get("usage_limit")
    if value.get("problem") != "native-error-rate-limit" or not isinstance(limit, dict) or limit.get("source") not in ("result", "rate-limit-event"):
        return None
    return {"source": limit["source"], "resets_at": cli_telemetry.reset_epoch(limit.get("resets_at"))}


def refused(out, cid):
    """The provider refused the call: its receipt names a rate limit and reports no usage, or names the Claude account's usage
    limit (`usage_limit`), which also covers a call the limit cut after the agent had worked. It is still charged as any invalid
    cell (its receipt cost, else the --stop-usd reserve), but it does not count toward --max-invalid and it pauses the run. A limit
    can be per model, so it can hit one arm more than the other: the report counts refused cells per arm."""
    value = _receipt(out, cid)
    usage = value.get("usage")
    # no usage: absent, or every count zero (the real Claude runner writes a zero-filled one for a refused call)
    unused = not usage or isinstance(usage, dict) and all(type(n) is int and n == 0 for n in usage.values())
    return value.get("problem") == "native-error-rate-limit" and (unused or usage_limit(out, cid) is not None)


def contaminated(row):
    """The cell's stream touched a protected path (replay_eval.scan_stream). It stays invalid as `contaminated` even when the
    provider also refused the call: the label that excludes a cell for what the agent read wins over the one that requeues it."""
    scan = row.get("contamination")
    return row.get("failure_class") == "contaminated" or isinstance(scan, dict) and scan.get("status") == "contaminated"


def cost_of(out, cid, row):
    if harness_report._valid_money(row.get("cost_usd")):
        return row["cost_usd"]
    receipt = out / f"{cid}.runner.json"
    try:
        value = json.loads(receipt.read_text()).get("cost_usd") if receipt.is_file() and receipt.stat().st_size else None
    except (OSError, ValueError, AttributeError):  # a truncated receipt: unknown cost, charged its reserve
        value = None
    return value if harness_report._valid_money(value) else None


RUN_MANIFEST = "run-manifest.json"
LOOK = "LOOK.json"  # the single look: report --single-look writes it, and nothing runs or reads again


def _version():
    match = re.search(r"(?m)^  version: (\S+)$", (HERE.parent / "SKILL.md").read_text()) if (HERE.parent / "SKILL.md").is_file() else None
    return match[1] if match else None


def _sha256(path):
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def set_sha256(config):
    """The set as parsed: arms (and their order, which seeds the dispatch order), agent command, tasks with their prompts, bases and
    oracle hashes. Whitespace does not count, nor `compare` (which arms a report contrasts, at what margin): it changes no attempt in
    this run, and the report says if it moved after the seal. A chain's set names its parent manifest, so it is bound to it."""
    treatment = {k: v for k, v in config.items() if k != "compare"}
    treatment["__arm_order__"] = list(config.get("arms", {}))
    return hashlib.sha256(json.dumps(treatment, sort_keys=True).encode()).hexdigest()


def _read_manifest(path):
    """The sealed manifest, None if there is none. Anything else at that path, or bytes that are not one, is refused."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("run manifest is not a regular file")
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError("run manifest is unreadable") from error
    if (not isinstance(value, dict) or value.get("schema") != "007-framework/lab-run-manifest/v1" or not isinstance(value.get("set_sha256"), str)
            or not isinstance(value.get("executables", {}), dict)):
        raise ValueError("run manifest is malformed")
    return value


def _ledger(results):
    """The dispatch ledger's rows, [] when there is none, None when it cannot be read."""
    if not (results / "dispatch.jsonl").exists():
        return []
    try:
        history, _, _ = replay_eval.load_dispatch_history(results)
    except (OSError, ValueError):
        return None
    return history


def _bound_digests(history):
    """Manifest digests the dispatch ledger recorded: once a dispatch names one, that manifest is the only one the run accepts."""
    return {row["manifest_sha256"] for row in history if isinstance(row.get("manifest_sha256"), str)}


def _unbound(history, digest):
    """Dispatches that do not name this manifest: before the seal, or by a controller that does not seal (1.7.0)."""
    return sum("dispatched_at" in row and row.get("manifest_sha256") != digest for row in history)


def _named_files(part):
    """Absolute paths an argument may name: itself, after `=` (`--flag=/f`, `KEY=/f`, `--flag=key=/f`), after a short option
    (`-f/f`) or after `@` (`@/f`)."""
    names = {part}
    if "=" in part:
        names |= {part.split("=", 1)[1], part.rsplit("=", 1)[1]}
    if len(part) > 2 and part[0] == "-" and part[1] != "-":
        names.add(part[2:])
    names |= {name[1:] for name in names if name.startswith("@")}  # `@/f`, `--flag=@/f`
    return sorted(name for name in names if os.path.isabs(name))


TOOL_VERSION = {"go": ["version"], "node": ["--version"], "python": ["--version"], "pytest": ["-m", "pytest", "--version"]}


def toolchain(config, root):
    """Path and version of what grades the attempts: the interpreter each acceptance command starts, and the compiler or test runner
    its adapter calls (go, node, pytest), found on the acceptance PATH. Recorded at the seal; a change on resume is a mismatch."""
    adapters = set()
    for lab_json in sorted((root / "tasks").glob("*/lab.json")) if root else []:
        try:
            adapters.add(json.loads(lab_json.read_text()).get("adapter"))
        except (OSError, ValueError):
            adapters.add("unreadable")
    path = (config.get("acceptance_env") or {}).get("PATH", os.environ.get("PATH", ""))
    found = {name: shutil.which(name, path=path) for name in ("go", "node") if name in adapters}
    interpreters = {command[0] for task in config.get("tasks", []) for command in task.get("acceptance", [])[:1]
                    if command and os.path.isabs(command[0])}
    for index, program in enumerate(sorted(interpreters)):
        found["python" if index == 0 else f"python{index + 1}"] = program
        if "pytest" in adapters and index == 0:
            found["pytest"] = program
    out = {}
    for name, program in sorted(found.items()):
        version = None
        if program and Path(program).is_file():
            try:
                done = subprocess.run([program, *TOOL_VERSION[name.rstrip("0123456789")]], capture_output=True, text=True, timeout=60,
                                      env={**os.environ, "PATH": path}, stdin=subprocess.DEVNULL)
                version = (done.stdout or done.stderr).strip().splitlines()[0][:200] if (done.stdout or done.stderr).strip() else None
            except (OSError, subprocess.TimeoutExpired):
                version = None
        out[name] = {"path": str(Path(program).resolve()) if program else None, "version": version}
    return out


def seal(config, root=None):
    """What a resumed run must find unchanged, checked each time the run starts or resumes. Limits (replicates, calls, money, jobs,
    invalid budget) stay adjustable at a planned pause. Executables are the agent command's program (a PATH lookup for the first
    word) and every absolute file it names, through symlinks. A relative path resolves inside the task's workspace, which the set's
    base commit fixes; a later PATH lookup (`env agent`), anything the program launches, environment variables and the CLI's own
    configuration are not sealed, nor the parts the set lists in `unsealed_files` (a log the attempts rewrite). Given the set's
    directory (`root`), the grading toolchain is recorded too (`toolchain`). The manifest guards against accidents, not tampering:
    whoever can write the output directory can rewrite it."""
    listed = config.get("unsealed_files", [])
    if not isinstance(listed, list) or not all(isinstance(part, str) for part in listed):
        raise ValueError("unsealed_files must be a list of strings")
    tools, skip = {}, set(listed)
    for index, part in enumerate(config.get("agent_command", [])):
        names = _named_files(part)
        if part in skip or skip & set(names):
            continue
        found = [shutil.which(part)] if index == 0 and "/" not in part else names
        found = [name for name in found if name and Path(name).is_file()]
        if found:
            real = Path(found[0]).resolve()
            tools[part] = {"path": str(real), "sha256": _sha256(real)}
    return {"toolchain": toolchain(config, root), "schema": "007-framework/lab-run-manifest/v1", "set_sha256": set_sha256(config), "executables": tools,
            "framework_sha256": hashlib.sha256("".join(_sha256(p) for p in sorted(HERE.glob("*.py"))).encode()).hexdigest(),
            "python": sys.version.split()[0], "arms": config.get("arms"), "parent_manifest_sha256": config.get("parent_manifest_sha256"),
            "program_sealed": bool(config.get("agent_command")) and config["agent_command"][0] in tools, "sealed_parts": sorted(tools),
            "unsealed_files": sorted(skip),
            "agent_command_sha256": hashlib.sha256(json.dumps(config.get("agent_command"), sort_keys=True).encode()).hexdigest()}


def sealed_state(config, results):
    """state: sealed, sealed-late (a run older than the manifest), unbound (see _binding) or absent; compare_changed: the comparison or margin differs from
    the one in the set when the run was sealed; sha256: the manifest's digest. Results of a different set, a manifest the dispatches
    do not name, or a missing one they do name, are refused, not read."""
    recorded, history = _read_manifest(results / RUN_MANIFEST), _ledger(results)
    if recorded is not None and history is None:
        raise ValueError(f"the dispatch ledger of a sealed run cannot be read: {results}")
    bound = _bound_digests(history or [])
    if recorded is None:
        if bound:
            raise ValueError(f"run manifest missing for sealed dispatches: {results}")
        return {"state": "absent", "compare_changed": None, "sha256": None, "program_sealed": None, "sealed_parts": None,
                "unbound_dispatches": None, "unbound_cells": None, "aa": None}
    digest = _sha256(results / RUN_MANIFEST)
    if bound and bound != {digest}:
        raise ValueError(f"run manifest changed after dispatch: {results}")
    if recorded.get("set_sha256") != set_sha256(config):
        raise ValueError(f"results were run with a different set: {results}")
    state, unbound, unbound_cells = _binding(results, recorded, digest, history)
    return {"state": state, "compare_changed": recorded.get("compare") != config.get("compare"), "sha256": digest,
            "program_sealed": recorded.get("program_sealed"), "sealed_parts": recorded.get("sealed_parts"),
            "unsealed_files": recorded.get("unsealed_files"), "unbound_dispatches": unbound, "unbound_cells": unbound_cells,
            "aa": recorded.get("aa") if isinstance(recorded.get("aa"), dict) else None}


def _binding(results, recorded, digest, history):
    """(state, unbound dispatches, unbound results) of a sealed directory. unbound: dispatches after the seal that do not name it
    (another controller), or results no sealed dispatch produced (cells copied in), beyond what existed when it was sealed. Restoring
    inputs cannot rebind them: an unbound run stays unbound."""
    unbound = _unbound(history, digest)
    bound_cells = {row["cell"] for row in history if row.get("manifest_sha256") == digest}
    unbound_cells = len(set(replay_eval.read_cell_artifacts(results)[0]) - bound_cells)
    late = recorded.get("cells_before_seal", 0)
    if unbound > recorded.get("dispatches_before_seal", 0) or unbound_cells > late:
        return "unbound", unbound, unbound_cells
    return ("sealed-late" if unbound or late else "sealed"), unbound, unbound_cells


def jobs_limit():
    """Parallel cells this machine takes without loading itself: a quarter of its cores, at least 2. Amendment 7 saw a load of
    about 870 and a restart from oversubscription; external load also moves grades (yaegi)."""
    return max(2, (os.cpu_count() or 4) // 4)


LOAD_POLL_S, LOAD_LOG_S, QUOTA_TIMEOUT_S = 300, 60, 300
PLANNED_PAUSES = ("call-budget", "rate-limit", "machine-busy", "quota-hold", "looked")  # no STOP.json; a later run resumes all but `looked`


def _log_load(out, step=None):
    """Append the load averages to load.log; return the 5-minute one."""
    one, five, fifteen = os.getloadavg()
    with (out / "load.log").open("a") as handle:
        handle.write(json.dumps({"at": _now(), "load": [round(one, 2), round(five, 2), round(fifteen, 2)], **({"step": step} if step else {})}) + "\n")
    return five


def quiet(out, max_load, wait_s, step):
    """True once the 5-minute load is under max_load, polling every LOAD_POLL_S; False if it is not within wait_s."""
    waited = 0
    while _log_load(out, step) >= max_load:
        if waited >= wait_s:
            return False
        time.sleep(LOAD_POLL_S)
        waited += LOAD_POLL_S
    return True


def _load_logger(out, done):
    while not done.wait(LOAD_LOG_S):
        _log_load(out)


QUOTA_PASSING = ("allowed", "allowed_warning")


def quota_judge(events, left, windows=("seven_day",), need=.60, ceiling=.95):
    """(passes, reason, utilization by window) from a probe's rate_limit_event rows (Claude's rate_limit_info). It passes only if
    every event's status is allowed or allowed_warning, every window it reports is one of `windows` and allowed, each of those
    windows' utilization is identified, and each has room: used + need x left <= ceiling, where `left` is the share of the planned
    cells not yet done and `need` the share of the window the whole run takes. No event, an unknown window or a blocked one fails
    closed: the run pauses for the operator (F-1's quota_f.py, made native)."""
    if not events:
        return False, "no rate_limit_event", {}
    used, others = {}, set()
    for info in events:
        if info.get("status") not in QUOTA_PASSING:
            return False, f"status {info.get('status')!r}", used
        unified = info.get("unifiedWindows")
        if isinstance(unified, dict):
            for name, window in unified.items():
                if name not in windows:
                    others.add(name)
                elif not isinstance(window, dict) or window.get("status") not in QUOTA_PASSING:
                    return False, f"{name} status {window.get('status') if isinstance(window, dict) else None!r}", used
                elif harness_report._valid_money(window.get("utilization")):
                    used[name] = window["utilization"]
        elif info.get("rateLimitType") in windows and harness_report._valid_money(info.get("utilization")):
            used[info["rateLimitType"]] = info["utilization"]
        elif info.get("rateLimitType") is not None and info.get("rateLimitType") not in windows:
            others.add(info["rateLimitType"])
    if others:
        return False, f"unknown windows {sorted(map(str, others))}", used
    missing = [w for w in windows if w not in used]
    if missing:
        return False, f"utilization not identified: {missing}", used
    for window in windows:
        if used[window] + need * left > ceiling:
            return False, f"{window} at {used[window]} with {left:.0%} of cells left", used
    return True, "headroom", used


def quota_check(config, out, left):
    """Run the set's quota probe (one minimal call on the study's model, never a cell) and judge its rate_limit_event rows.
    Appends the decision to quota.jsonl."""
    validate_quota_probe(config)
    probe = config["quota_probe"]
    events, exit_code, cost, limited, resets = [], None, None, False, []
    try:
        with tempfile.TemporaryDirectory(prefix="007-quota-") as scratch:
            done = subprocess.run(probe["command"], cwd=scratch, capture_output=True, text=True, timeout=QUOTA_TIMEOUT_S, stdin=subprocess.DEVNULL)
        exit_code = done.returncode
        for line in done.stdout.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("type") == "rate_limit_event" and isinstance(row.get("rate_limit_info"), dict):
                events.append(row["rate_limit_info"])
                if row["rate_limit_info"].get("status") == "rejected":
                    resets.append(cli_telemetry.reset_epoch(row["rate_limit_info"].get("resetsAt")))
            if isinstance(row, dict) and row.get("type") == "result" and row.get("is_error") is not False and isinstance(row.get("result"), str):
                found = cli_telemetry.CLAUDE_USAGE_LIMIT.search(row["result"])  # the probe's own call hit the account's limit
                if found:
                    limited = True
                    resets.append(cli_telemetry.reset_field(found[1]))
            if isinstance(row, dict) and row.get("type") == "result" and harness_report._valid_money(row.get("total_cost_usd")):
                cost = row["total_cost_usd"]  # the probe is a real call: its cost joins the run's spend
    except (OSError, subprocess.TimeoutExpired) as error:
        exit_code = type(error).__name__
    ok, reason, used = quota_judge(events, left, tuple(probe.get("windows", ("seven_day",))), probe.get("need", .60), probe.get("ceiling", .95))
    if limited:  # the reading that names the limit, never "no rate_limit_event"; and a probe the limit stopped never passes
        ok, reason = False, "usage limit reached"
    known = [r for r in resets if r is not None]
    with (out / "quota.jsonl").open("a") as handle:
        handle.write(json.dumps({"at": _now(), "ok": ok, "reason": reason, "utilization": used, "cells_left_share": left,
                                 "probe_exit": exit_code, "probe_cost_usd": cost, "events": events,
                                 "resets_at": max(known) if known else None}) + "\n")
    return ok, reason, cost


def _probe_rows(out):
    try:
        lines = (out / "quota.jsonl").read_text().splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("ok") is False:
            rows.append(row)
    return rows


def probe_holds(out):
    """The resets (Unix seconds) that failed quota probes of this run logged in quota.jsonl: the account stays held until then."""
    return [row["resets_at"] for row in _probe_rows(out) if cli_telemetry.reset_epoch(row.get("resets_at"))]


def probe_limits_without_reset(out):
    """When failed probes saw the usage limit with no reset (their `at`): the fallback cooldown runs from the newest."""
    found = []
    for row in _probe_rows(out):
        if row.get("reason") == "usage limit reached" and not cli_telemetry.reset_epoch(row.get("resets_at")):
            try:
                found.append(harness_report._instant(row["at"]))
            except (KeyError, TypeError, ValueError):
                continue
    return found


def validate_quota_probe(config):
    probe = config.get("quota_probe")
    if not isinstance(probe, dict) or not isinstance(probe.get("command"), list) or not probe["command"] or not all(isinstance(p, str) for p in probe["command"]):
        raise ValueError("--quota-gate needs quota_probe.command (an argv list) in the set")
    windows = probe.get("windows", ["seven_day"])
    if not isinstance(windows, list) or not windows or not all(isinstance(w, str) for w in windows):
        raise ValueError("quota_probe.windows must be a nonempty list of names")
    for key, default in (("need", .60), ("ceiling", .95)):
        value = probe.get(key, default)
        if not harness_report._valid_money(value) or value > 1:
            raise ValueError(f"quota_probe.{key} must be a share between 0 and 1")


def probe_costs(out):
    """(measured cost, probes without a measured cost) of every quota probe this run recorded."""
    measured, unmeasured = 0.0, 0
    try:
        lines = (out / "quota.jsonl").read_text().splitlines()
    except FileNotFoundError:
        return measured, unmeasured
    except OSError as error:
        raise ValueError(f"quota.jsonl cannot be read: {out}") from error
    for line in lines:
        try:
            value = json.loads(line).get("probe_cost_usd")
        except (ValueError, AttributeError):
            unmeasured += 1
            continue
        if harness_report._valid_money(value):
            measured += value
        else:
            unmeasured += 1
    return measured, unmeasured


def cost_marker(out, cells, arm_of, stop_usd, hold_usd):
    """Once, after the first cells: project the run's cost by arm (mean cost per cell x planned cells of the arm) from costs only,
    never grades. A cell with no measured cost counts at the --stop-usd reserve; refused cells are left out. Above hold_usd, or
    with an arm that has no cell yet, it writes HOLD.json and the run stops for good (a terminal STOP); else MARKER.json."""
    results, _ = replay_eval.read_cell_artifacts(out)
    planned = {}
    for cell in cells:
        planned[cell[2]] = planned.get(cell[2], 0) + 1
    costs = {arm: [] for arm in planned}
    for name, row in results.items():
        if row.get("failure_class") == "provider-rate-limit" or name not in arm_of:
            continue
        value = cost_of(out, name, row)
        costs[arm_of[name]].append(value if harness_report._valid_money(value) else stop_usd)
    projection = sum(sum(v) / len(v) * planned[a] for a, v in costs.items()) if all(costs.values()) else None
    value = {"at": _now(), "cells": {a: len(v) for a, v in costs.items()}, "spent": sum(map(sum, costs.values())),
             "projection_usd": projection, "hold_above_usd": hold_usd}
    held = projection is None or projection > hold_usd
    (out / ("HOLD.json" if held else "MARKER.json")).write_text(json.dumps(value, indent=1) + "\n")
    return not held


def _set_aside(out, cid):
    """Move a refused attempt's files to refused/, numbered, so the cell can be dispatched again; nothing is deleted."""
    store = out / "refused"
    store.mkdir(mode=0o700, exist_ok=True)
    attempt = 1
    while any(store.glob(f"{glob.escape(cid)}.{attempt}.*")):  # a task id may hold dots
        attempt += 1
    for suffix in replay_eval.CELL_ARTIFACT_SUFFIXES:
        source = out / (cid + suffix)
        if source.exists() or source.is_symlink():
            os.replace(source, store / f"{cid}.{attempt}{suffix}")


def run(config_path, out, *, replicates, jobs, max_calls, max_usd, stop_usd, timeout_s=3600, execute=None, max_invalid=3,
        requeue_refused=False, over_limit="stop", chunk=None, max_load=None, load_wait_s=3600, quota_gate=False,
        cost_marker_at=None, cost_marker_hold_usd=None, rate_limit_wait_s=0, strict_jobs=False, aa=None):
    """Serialize controllers sharing an output directory before checking or publishing dispatch history. The options after
    max_invalid are off by default, so a run without them behaves as in 1.8.1. `aa` (an arm of the set) adds its A/A copy."""
    if aa is not None and not isinstance(aa, str):
        raise ValueError("aa must name an arm of the set")
    if not all(harness_report._valid_money(value) for value in (max_usd, stop_usd)):
        raise ValueError("budget values must be finite nonnegative numbers")
    for name, value, minimum in (("replicates", replicates, 1), ("jobs", jobs, 1), ("max_calls", max_calls, 0), ("max_invalid", max_invalid, 1),
                                  ("chunk", 1 if chunk is None else chunk, 1), ("load_wait_s", load_wait_s, 0),
                                  ("rate_limit_wait_s", rate_limit_wait_s, 0), ("cost_marker_at", 1 if cost_marker_at is None else cost_marker_at, 1)):
        if type(value) is not int or value < minimum:
            raise ValueError(f"{name} limit must be an integer >= {minimum}")
    if rate_limit_wait_s and not requeue_refused:  # waiting without requeue would lose every refused cell of the outage
        raise ValueError("rate_limit_wait_s limit needs requeue_refused")
    if over_limit not in ("stop", "record"):
        raise ValueError("over_limit limit must be stop or record")
    if max_load is not None and not (harness_report._valid_money(max_load) and max_load > 0):
        raise ValueError("max_load limit must be a positive number")
    if (cost_marker_at is None) != (cost_marker_hold_usd is None) or cost_marker_hold_usd is not None and not harness_report._valid_money(cost_marker_hold_usd):
        raise ValueError("cost marker limit needs both a cell count and a finite hold amount")
    if jobs > jobs_limit():
        message = f"--jobs {jobs} is above {jobs_limit()} (a quarter of this machine's cores, at least 2): load can move grades"
        if strict_jobs:
            raise ValueError(f"jobs limit: {message}")
        print(f"007 lab: warning: {message}", file=sys.stderr)
    timeout_s = replay_eval.validate_timeout(timeout_s)
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (out / ".run.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"stop": "run-already-active", "calls": 0}
        options = {"requeue_refused": requeue_refused, "over_limit": over_limit, "chunk": chunk, "max_load": max_load,
                   "load_wait_s": load_wait_s, "quota_gate": quota_gate, "cost_marker_at": cost_marker_at,
                   "cost_marker_hold_usd": cost_marker_hold_usd, "rate_limit_wait_s": rate_limit_wait_s, "aa": aa}
        return _run(config_path, out, replicates=replicates, jobs=jobs, max_calls=max_calls, max_usd=max_usd,
                    stop_usd=stop_usd, timeout_s=timeout_s, execute=execute, max_invalid=max_invalid, options=options)


def _run(config_path, out, *, replicates, jobs, max_calls, max_usd, stop_usd, timeout_s, execute, max_invalid, options):
    """Spend rule: a cell is dispatched only if the spend so far plus stop_usd for it and for each cell in flight stays under max_usd.
    A failed call that reports no cost is charged stop_usd (its reserve), never zero; only a valid cell without a cost stops the run."""
    config = written = json.loads(config_path.read_text())
    aa = {"arm": options["aa"], "label": options["aa"] + AA_SUFFIX} if options["aa"] is not None else None
    if aa:  # the copy is a third arm of this run only; the seal binds the set as written, and records the copy
        config = {**config, "arms": aa_arms(config, aa["arm"])}
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    execute = execute or replay_eval.execute_cell
    ledger = out / "dispatch.jsonl"
    cells = plan(config, replicates)
    replay_eval.validate_cell_artifacts(config["tasks"], config["arms"], replicates, directory=out)
    if (out / LOOK).exists():  # the single look was taken: no attempt may follow it
        return {"stop": "looked", "calls": 0}
    if options["quota_gate"]:
        validate_quota_probe(config)  # before the seal, not at the first gate
    try:
        flagged = set(json.loads((config_path.parent / "sensitivity.json").read_text()).get("load_sensitive", []))
    except (OSError, ValueError, AttributeError):
        flagged = set()
    if flagged & {t["id"] for t in config["tasks"]}:  # its grade moved with the load: drop it from the set before any attempt
        return {"stop": "load-sensitive-oracle", "tasks": sorted(flagged & {t["id"] for t in config["tasks"]}), "calls": 0}
    cell_name = lambda cell: replay_eval.cell_id(cell[0], cell[2], cell[1])
    results, receipts = replay_eval.read_cell_artifacts(out)
    done = set(results)
    orphans = set(receipts) - done
    try:
        history, invalid_history, ambiguous_history = replay_eval.load_dispatch_history(out)
        if invalid_history:
            return {"stop": "unreadable-dispatch-history", "calls": 0}
        if ambiguous_history:
            return {"stop": "ambiguous-dispatch-history", "calls": 0}
        last = {row["cell"]: row for row in history}
        for row in history:  # a refused attempt set aside for redispatch is not an orphan
            if row["cell"] not in done and not (last[row["cell"]].get("requeued") is True and "finished_at" in last[row["cell"]]):
                orphans.add(row["cell"])
    except (OSError, ValueError):
        return {"stop": "unreadable-dispatch-history", "calls": 0}
    try:  # an agent's receipt left under its token: its controller died while it ran (the ledger, if intact, says so too)
        salt_seen = (_read_manifest(out / RUN_MANIFEST) or {}).get("blind_salt")
    except ValueError:
        salt_seen = None
    named = {cell_name(c) for c in cells} | {row["cell"] for row in history}
    for name in replay_eval.blind_files(out):
        orphans.add(replay_eval.blind_cell(salt_seen, name, named) or f"{replay_eval.BLIND_DIR}/{name}")
    if orphans or (out / "STOP.json").exists():
        return {"stop": "uncertain-attempts" if orphans else "stopped-before", "orphans": sorted(orphans)}
    refusals = [row for row in history if "finished_at" in row and row.get("refused") is True]
    remaining = any(replay_eval.cell_id(t, a, r) not in done for t, r, a in cells)
    # a Claude usage limit lasts until the reset its refusal (or a failed quota probe) named, not 10 minutes: hold until then
    known = lambda row: row.get("usage_limit") is True and cli_telemetry.reset_epoch(row.get("resets_at"))
    # every finished attempt the account's limit cut holds the run, a contaminated one (never refused or requeued) included
    resets = [row["resets_at"] for row in history if "finished_at" in row and known(row)] + probe_holds(out)
    if resets and remaining and max(resets) > datetime.now(timezone.utc).timestamp():
        return {"stop": "quota-hold", "calls": 0, "resets_at": max(resets),
                "retry_after_s": math.ceil(max(resets) - datetime.now(timezone.utc).timestamp())}
    # a refusal whose reset is known and past needs no cooldown; one with no reset does, and so does a contaminated cell the
    # account's limit cut (never a refusal) and a failed probe that named the limit, both with no reset
    unknown = [harness_report._instant(row["finished_at"]) for row in history if "finished_at" in row and not known(row)
               and (row.get("refused") is True or row.get("usage_limit") is True)] + probe_limits_without_reset(out)
    if unknown and remaining:  # resuming inside the outage would only lose cells to it (the newest counts); a finished run has none to lose
        age = (datetime.now(timezone.utc) - max(unknown)).total_seconds()
        if age < RATE_LIMIT_COOLDOWN_S:
            return {"stop": "rate-limit-cooldown", "calls": 0, "retry_after_s": round(RATE_LIMIT_COOLDOWN_S - age)}
    try:
        sealed = seal(written, config_path.parent)
    except OSError:
        return {"stop": "executable-unreadable", "calls": 0}
    manifest = out / RUN_MANIFEST
    bound = _bound_digests(history)
    try:
        recorded = _read_manifest(manifest)
    except ValueError:
        return {"stop": "manifest-unreadable", "calls": 0}
    if recorded is None:
        if bound:  # dispatches named a manifest that is gone: never re-seal over them
            return {"stop": "manifest-missing", "calls": 0}
        # the agent's names come from this salt (replay_eval.blind_token); a directory with cells already run keeps their labelled paths
        salt = None if done else replay_eval.unique_salt([cell_name(c) for c in cells])
        # a directory from before 1.8 is sealed now and reported as sealed-late; written whole, then renamed
        with tempfile.NamedTemporaryFile("w", dir=out, prefix="." + RUN_MANIFEST + ".", delete=False) as handle:
            handle.write(json.dumps({**sealed, "compare": config.get("compare"), "aa": aa, "blind_salt": salt, "sealed_at": _now(), "cells_before_seal": len(done),
                                     "dispatches_before_seal": sum("dispatched_at" in row for row in history),
                                     "version": _version(), "set_file_sha256": _sha256(config_path)}, indent=1) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, manifest)
    else:
        # keys a later 007 adds to the seal are compared only once a manifest records them
        changed = sorted(key for key in sealed if key not in ("executables", "sealed_parts", "program_sealed", "unsealed_files") and key in recorded
                         and recorded[key] != sealed[key])
        old, new = recorded.get("executables") or {}, sealed["executables"]
        parts = sorted(part for part in set(old) | set(new) if old.get(part) != new.get(part))
        changed += [f"executables:{part}" for part in parts]
        if recorded.get("aa") != aa:  # A/A on or off, or another arm, against what was sealed (none, before 1.11)
            changed.append("aa")
        salt = recorded.get("blind_salt")  # none before 1.11.0: that run resumes with the labelled paths it began with
        if salt is not None and not (isinstance(salt, str) and re.fullmatch(r"[0-9a-f]{32}", salt)):
            changed.append("blind_salt")
        details = {part: {"sealed": old.get(part), "found": new.get(part)} for part in parts}
        if "toolchain" in changed:
            details["toolchain"] = {"sealed": recorded.get("toolchain"), "found": sealed["toolchain"]}
        if bound and bound != {_sha256(manifest)}:
            changed.append("manifest")
        binding = _binding(out, recorded, _sha256(manifest), history)
        if binding[1] > recorded.get("dispatches_before_seal", 0):
            changed.append("unbound-dispatches")  # a controller that does not seal dispatched after the seal
        if binding[2] > recorded.get("cells_before_seal", 0):
            changed.append("unbound-cells")  # results no sealed dispatch produced: copied in, or a lost ledger
        if changed:  # not a STOP: restoring what was sealed makes the run resumable again, except an unbound one
            return {"stop": "manifest-mismatch", "changed": changed, "details": details, "calls": 0}
    sealed_digest = _sha256(manifest)
    if salt and replay_eval.blind_collisions(salt, [cell_name(c) for c in cells]):  # two cells would share staging names
        return {"stop": "blind-token-collision", "cells": replay_eval.blind_collisions(salt, [cell_name(c) for c in cells]), "calls": 0}
    if salt:  # the executor names the agent's workspace and receipt from it; the set as written, and its seal, never hold it
        config = {**config, "blind_salt": salt}
    # the set's directory holds every task's hidden tests: no agent may read it (replay_eval.protected_paths adds the rest)
    config = {**config, "read_protect": [("set-directory", str(config_path.parent.resolve()))]}
    arm_of = {cell_name(c): c[2] for c in cells}
    spent, invalid, stop, lock = 0.0, 0, None, threading.Lock()
    refused_per_arm = {arm: 0 for arm in config["arms"]}
    over, requeued, limit_resets = 0, 0, None

    def charge(cost):
        nonlocal spent, stop
        if spent is not None:
            try:
                spent = float(harness_report._money_sum((spent, stop_usd if cost is None else cost)))
            except ValueError:
                spent = None
                stop = stop or "cost-total-unavailable"

    def over_limit(cost, live=False):
        nonlocal stop, over
        if cost is not None and cost > stop_usd:
            if options["over_limit"] == "stop":  # live, as in 1.8.1, it replaces any stop set earlier in the same pass
                stop = "cell-over-limit" if live else stop or "cell-over-limit"
            else:
                over += 1  # recorded; only the total cap stops the run

    probe_usd, probe_unmeasured = probe_costs(out)
    if probe_usd or probe_unmeasured:
        charge(probe_usd)  # quota probes this run already made; one without a measured cost at the --stop-usd reserve
        for _ in range(probe_unmeasured):
            charge(None)
    for row in refusals:  # the live decision, recorded in the ledger once per refused attempt
        if row["cell"] in arm_of:
            refused_per_arm[arm_of[row["cell"]]] += 1
        if row.get("requeued") is True:  # its files were set aside: the ledger keeps what it was charged
            requeued += 1
            charge(row["cost_usd"] if harness_report._valid_money(row.get("cost_usd")) else None)
    for name in done:
        row = json.loads((out / f"{name}.json").read_text())
        rate_limited = row.get("failure_class") == "provider-rate-limit"  # the live decision, never the receipt alone
        cost = cost_of(out, name, row)
        if cost is None and row.get("valid") is True:
            stop = "cost-unavailable"
        else:
            charge(cost)
            over_limit(cost)
        invalid += row.get("valid") is not True and not rate_limited
    if invalid >= max_invalid:
        stop = stop or "invalid-budget"
    calls, waited = 0, 0
    marker = options["cost_marker_at"] is not None and not (out / "MARKER.json").exists()
    logging = threading.Event()
    if options["max_load"] is not None:
        threading.Thread(target=_load_logger, args=(out, logging), daemon=True).start()

    def one(cell):
        task, rep, arm = cell
        try:
            return cell, execute(config, task, arm, rep, out, timeout_s)
        except Exception as error:  # one cell's failure (a refused snapshot, a crash) is an invalid cell, never the whole run
            row = _controller_failure(out, task, arm, rep, error, config.get("retain_diagnostic_text", True) is True)
            detail = row.get("controller_error") or _error_detail(error)
            text = f": {detail['message']}" if detail["message"] is not None else ""
            print(f"007 lab: {replay_eval.cell_id(task, arm, rep)}: {detail['type']}{text} (at {detail['where']})", file=sys.stderr)
            return cell, row
    try:
        with ThreadPoolExecutor(jobs) as pool_:
            while not stop:
                if marker and len(done) >= options["cost_marker_at"]:  # also on a resume that starts past it
                    marker = False
                    if not cost_marker(out, cells, arm_of, stop_usd, options["cost_marker_hold_usd"]):
                        stop = "cost-marker-hold"
                        break
                if (out / LOOK).exists():  # a look taken while this run was paused between chunks
                    stop = "looked"
                    break
                todo = [c for c in cells if cell_name(c) not in done]
                if not todo:
                    break
                if calls >= max_calls:
                    stop = "call-budget"
                    break
                size = len(todo) if options["chunk"] is None else options["chunk"]
                if marker and len(done) < options["cost_marker_at"]:
                    size = min(size, options["cost_marker_at"] - len(done))  # the marker reads exactly its first cells
                if options["max_load"] is not None and not quiet(out, options["max_load"], options["load_wait_s"], f"chunk at {len(done)}"):
                    stop = "machine-busy"
                    break
                if options["quota_gate"]:
                    try:  # the probe is a paid call: it needs room for its reserve, like a cell
                        room = spent is not None and harness_report._money_sum((spent, stop_usd)) <= harness_report._money_sum((max_usd,))
                    except ValueError:
                        room = False
                    if not room:
                        stop = "usd-budget"
                        break
                    ok, _, cost = quota_check(config, out, len(todo) / len(cells))
                    if cost is None:
                        probe_unmeasured += 1  # charged its reserve, as a cell without a cost
                    else:
                        probe_usd += cost
                    charge(cost)
                    if not ok:
                        stop = "quota-hold"
                        held = [r for r in probe_holds(out) if r > datetime.now(timezone.utc).timestamp()]
                        if held:
                            limit_resets = max(limit_resets or 0, *held)
                        break
                pending, active, sent = list(todo[:size]), set(), 0
                while True:
                    while not stop and len(active) < jobs and pending:
                        if calls >= max_calls:
                            stop = "call-budget"
                            break
                        try:
                            reserved = harness_report._money_sum((spent, stop_usd * (len(active) + 1)))
                        except ValueError:
                            reserved = None
                        if reserved is None or reserved > harness_report._money_sum((max_usd,)):
                            stop = "usd-budget"
                            break
                        cell = pending.pop(0)
                        calls += 1
                        sent += 1
                        with ledger.open("a") as handle:
                            handle.write(json.dumps({"cell": cell_name(cell), "dispatched_at": _now(), "manifest_sha256": sealed_digest}) + "\n")
                        active.add(pool_.submit(one, cell))
                    if not active:
                        break
                    finished, active = wait(active, return_when=FIRST_COMPLETED)
                    for future in finished:
                        cell, row = future.result()
                        cid = cell_name(cell)
                        rate_limited = row.get("valid") is not True and not contaminated(row) and refused(out, cid)
                        # the account's limit holds the run whatever else the cell is: contamination keeps it from being
                        # requeued or relabelled, never from pausing dispatch
                        limit = usage_limit(out, cid) if row.get("valid") is not True else None
                        if limit and not rate_limited:
                            stop = "quota-hold" if stop in (None, "call-budget", "rate-limit") else stop
                            if limit["resets_at"]:
                                limit_resets = max(limit_resets or 0, limit["resets_at"])
                        if rate_limited:
                            row = {**row, "failure_class": "provider-rate-limit", "failure_class_observed": row.get("failure_class")}
                            with tempfile.NamedTemporaryFile("w", dir=out, prefix=f".{cid}.", delete=False) as handle:
                                handle.write(json.dumps(row))
                                handle.flush()
                                os.fsync(handle.fileno())
                            os.replace(handle.name, out / f"{cid}.json")
                            refused_per_arm[cell[2]] += 1
                            if limit:  # the account's limit: no cell is dispatched again before its reset, as on a failed quota gate
                                stop = "quota-hold" if stop in (None, "call-budget", "rate-limit") else stop
                                if limit["resets_at"]:
                                    limit_resets = max(limit_resets or 0, limit["resets_at"])
                            else:
                                stop = "rate-limit" if stop in (None, "call-budget") else stop  # a pause outranks a planned call budget
                        cost = cost_of(out, cid, row)
                        again = rate_limited and options["requeue_refused"]
                        if again:  # dispatched again after the pause; its files kept under refused/
                            _set_aside(out, cid)
                            requeued += 1
                        else:
                            done.add(cid)
                        with lock, ledger.open("a") as handle:
                            handle.write(json.dumps({"cell": cid, "finished_at": _now(), "cost_usd": cost, "valid": row.get("valid"),
                                                     **({"refused": True} if rate_limited else {}), **({"requeued": True} if again else {}),
                                                     **({"usage_limit": True, "resets_at": limit["resets_at"]} if limit else {})}) + "\n")
                        invalid += row.get("valid") is not True and not rate_limited
                        if cost is None and row.get("valid") is True:
                            stop = "cost-unavailable"
                        else:
                            charge(cost)  # A failed call with no receipt cost is charged its reserve.
                            over_limit(cost, live=True)
                        if invalid >= max_invalid:
                            stop = "invalid-budget"
                if stop == "rate-limit" and options["rate_limit_wait_s"] and waited + RATE_LIMIT_COOLDOWN_S <= options["rate_limit_wait_s"]:
                    time.sleep(RATE_LIMIT_COOLDOWN_S)  # wait out the outage inside the run, within the allowance
                    waited += RATE_LIMIT_COOLDOWN_S
                    stop = None
                    continue
                if not sent and not stop:
                    break
    finally:
        logging.set()
    if stop and stop not in PLANNED_PAUSES:
        (out / "STOP.json").write_text(json.dumps({"stop": stop, "at": _now(), "spent": spent, "calls": calls}))
    return {"stop": stop, "calls": calls, "spent": spent, "invalid": invalid, "refused": sum(refused_per_arm.values()),
            "refused_per_arm": refused_per_arm, "requeued": requeued, "over_limit_cells": over, "cells": len(cells),
            "quota_probe_usd": probe_usd, "quota_probes_unmeasured": probe_unmeasured, **({"resets_at": limit_resets} if limit_resets else {})}


# ---- score and report

def load_cells(out):
    rows = []
    try:
        results, _ = replay_eval.read_cell_artifacts(out)
    except FileNotFoundError:
        return rows
    for identifier, row in sorted(results.items()):
        path = out / (identifier + ".json")
        row["cell"] = identifier
        if not isinstance(row.get("acceptance_outcomes"), dict):  # unreadable report (a hung suite, the cap): no test seen passing; report() names it
            row["acceptance_outcomes"], row["outcomes_unreadable"] = {}, True
        receipt = out / f"{path.stem}.runner.json"
        if row.get("runner_receipt_sha256") == "unmeasured" and not receipt.is_file():
            row["valid"] = False  # the runner refused before reserving a receipt: an invalid cell report() names, never a broken directory
        elif not receipt.is_file() or hashlib.sha256(receipt.read_bytes()).hexdigest() != row["runner_receipt_sha256"]:
            raise ValueError(f"receipt mismatch: {path.name}")
        patch = row.get("candidate_patch")
        if isinstance(patch, dict) and hashlib.sha256((out / patch["path"]).read_bytes()).hexdigest() != patch["sha256"]:
            raise ValueError(f"patch mismatch: {path.name}")
        rows.append(row)
    return rows


def arm_stats(rows, durable, next_rows):
    accepted = sum(r["accepted"] for r in rows)
    wall = sum(r["agent_wall_s"] for r in rows)
    cost = harness_report._money_total(r["cost_usd"] for r in rows)
    following = [next_rows[r["cell"]] for r in rows if r["cell"] in next_rows]
    good = sum(durable.get(r["cell"], False) for r in rows)
    return {"units": len(rows), "accepted": accepted, "agent_wall_s": wall, "cost_usd": cost, "wall_per_accepted_s": wall / accepted if accepted else None,
            "cost_per_accepted_usd": cost / accepted if accepted and cost is not None else None, "durable": good, "durable_rate": good / len(rows) if rows else None,
            "next_accepted": sum(r["accepted"] for r in following), "total_wall_s": wall + sum(r["agent_wall_s"] for r in following),
            "total_cost_usd": harness_report._money_total(r["cost_usd"] for group in (rows, following) for r in group)}


def contrast(rows, durable, next_rows, low, ref):
    s = {a: arm_stats([r for r in rows if r["arm"] == a], durable, next_rows) for a in (low, ref)}
    a, b, x, y = s[low]["wall_per_accepted_s"], s[ref]["wall_per_accepted_s"], s[low]["durable_rate"], s[ref]["durable_rate"]
    return {**s, "reduction": 1 - a / b if a and b else None, "durable_diff": x - y if x is not None and y is not None else None}


def bootstrap(rows, durable, next_rows, low, ref, tasks, seed):
    by = {t: [r for r in rows if r["task"] == t] for t in tasks}
    rng, reduction, diff = random.Random(seed), [], []
    for _ in range(GATES["draws"]):
        c = contrast([r for t in rng.choices(tasks, k=len(tasks)) for r in by[t]], durable, next_rows, low, ref)
        if c["reduction"] is not None:
            reduction.append(c["reduction"])
        if c["durable_diff"] is not None:
            diff.append(c["durable_diff"])
    ci = lambda v: [sorted(v)[int(.025 * len(v))], sorted(v)[min(len(v) - 1, int(.975 * len(v)))]] if v else None
    return {"reduction_ci95": ci(reduction), "durable_diff_ci95": ci(diff), "draws": GATES["draws"], "estimable_reduction": len(reduction), "estimable_diff": len(diff)}


def unseen(rows, hidden, low, ref):
    """Tests the agent never saw that split a task's cells, whichever arm passed them: floor and ceiling tests carry no signal."""
    tests = {}
    for task in {r["task"] for r in rows}:
        cells = [r for r in rows if r["task"] == task]
        tests[task] = [k for k in hidden[task] if len({r["acceptance_outcomes"].get(k) == "pass" for r in cells}) == 2]
    return tests


def unseen_diff(rows, tests, low, ref, sample=None):
    tally = {low: [0, 0], ref: [0, 0]}
    by_task = {}
    for r in rows:
        by_task.setdefault(r["task"], []).append(r)
    for task in sample if sample is not None else by_task:
        for r in by_task[task]:
            for k in tests[task]:
                tally[r["arm"]][1] += 1
                tally[r["arm"]][0] += r["acceptance_outcomes"].get(k) == "pass"
    a, b = tally[low], tally[ref]
    return (a[0] / a[1] - b[0] / b[1], a[0] / a[1], b[0] / b[1]) if a[1] and b[1] else (None, None, None)


def same_change(diff, ci, tests_count, signal_tasks, sensitive):
    if not sensitive or diff is None or tests_count < GATES["min_discriminating"] or signal_tasks < GATES["min_signal_tasks"]:
        return "NO-INFORMATION"
    if diff < GATES["durability_margin"]:
        return "KILL"
    return "PROVEN" if ci and ci[0] >= GATES["durability_margin"] else "NOT-PROVEN"


def reach_rates(rows, task_dir, reach=None):
    """{task: [(cell, pass share)]} on reachable behaviours: hidden tests red at base (absent from baseline.json) that some valid
    cell of the task passes, whichever arm. Tasks with none are left out. `reach` ({task: [test ids]}) freezes the set instead,
    as a pre-registration fixed from earlier attempts does: more attempts no longer move the denominator, and tasks outside it
    are left out."""
    out = {}
    for task in sorted({r["task"] for r in rows}):
        cells = [r for r in rows if r["task"] == task]
        if reach is not None:
            tests = reach.get(task, [])
        else:
            hidden = [k for k in json.loads((task_dir / task / "hidden.json").read_text()) if k != "__module__"]
            base = set(json.loads((task_dir / task / "baseline.json").read_text()))
            tests = [k for k in hidden if k not in base and any(c["acceptance_outcomes"].get(k) == "pass" for c in cells)]
        if tests:
            out[task] = [(c, sum(c["acceptance_outcomes"].get(k) == "pass" for k in tests) / len(tests)) for c in cells]
    return out


def reachable_diffs(rows, task_dir, low, ref, split=None, reach=None):
    """{task: pass rate of `low` - pass rate of `ref`} on reachable behaviours. Unlike `unseen`, tests both arms agree on stay in:
    they are the evidence of sameness. split=arm compares replicate 1 against the later replicates inside that arm instead (pseudo
    A/A: the instrument's own noise, which a real difference has to exceed)."""
    out = {}
    for task, cells in reach_rates(rows, task_dir, reach).items():
        if split is None:
            x, y = [v for c, v in cells if c["arm"] == low], [v for c, v in cells if c["arm"] == ref]
        else:
            x = [v for c, v in cells if c["arm"] == split and c["replicate"] == 1]
            y = [v for c, v in cells if c["arm"] == split and c["replicate"] > 1]
        if x and y:
            out[task] = sum(x) / len(x) - sum(y) / len(y)
    return out


def whole_loss_draws(rows, task_dir, low, ref, seed, margin, reach=None, attempts=None, clustered=False):
    """GATES["draws"] sets of per-task differences in which `low` truly loses `margin` as whole failed attempts. Each task's cells of
    both arms are pooled (no difference), each arm is redrawn at its observed cell count, and a drawn `low` cell fails every
    reachable test with the probability that makes the expected loss exactly `margin`. None when there are too few tasks or too
    little passing to take `margin` away. `attempts` redraws every task at that many attempts per arm instead, to fix a critical
    value for a planned run from earlier attempts. `clustered` loses every `low` attempt of a task together, with the same
    probability and so the same expected loss: one cause that fails the task, not each attempt on its own."""
    pools = {}
    for task, cells in reach_rates(rows, task_dir, reach).items():
        nx, ny = sum(c["arm"] == low for c, _ in cells), sum(c["arm"] == ref for c, _ in cells)
        if nx and ny:
            pools[task] = ([v for c, v in cells if c["arm"] in (low, ref)], attempts or nx, attempts or ny)
    level = statistics.mean(sum(p) / len(p) for p, _, _ in pools.values()) if pools else 0.0
    if len(pools) < GATES["min_signal_tasks"] or margin > level:
        return None
    q, rng = margin / level, random.Random(seed)
    if clustered:
        return ({task: (0.0 if rng.random() < q else sum(rng.choice(pool) for _ in range(nx)) / nx) - sum(rng.choice(pool) for _ in range(ny)) / ny
                 for task, (pool, nx, ny) in pools.items()} for _ in range(GATES["draws"]))
    return ({task: sum(0.0 if rng.random() < q else rng.choice(pool) for _ in range(nx)) / nx - sum(rng.choice(pool) for _ in range(ny)) / ny
             for task, (pool, nx, ny) in pools.items()} for _ in range(GATES["draws"]))


def studentized(diffs, margin):
    """(mean + margin) / standard error of per-task differences: how far the mean sits above -margin."""
    values = list(diffs.values())
    mean, sd = statistics.fmean(values), statistics.stdev(values)
    return (mean + margin) / (sd / math.sqrt(len(values))) if sd else math.inf if mean + margin > 0 else -math.inf


def false_proven(rows, task_dir, low, ref, seed, margin=None, reach=None, attempts=None):
    """How often the plain t rule says PROVEN when `low` truly loses `margin` in whole failed attempts: 3.7-5.6 % on go-json at -3
    points, against the 2.5 % it promises. The reason `proven_critical` exists; reported, never a gate."""
    margin = GATES["reachable_margin"] if margin is None else margin
    draws = whole_loss_draws(rows, task_dir, low, ref, seed, margin, reach, attempts)
    return None if draws is None else sum(behaviour_verdict(paired_interval(d), True, margin) == "PROVEN" for d in draws) / GATES["draws"]


LOSS_MODELS = ("independent", "clustered")


def proven_critical(rows, task_dir, low, ref, seed, margin=None, reach=None, attempts=None, loss=LOSS_MODELS):
    """The critical value PROVEN must beat: the upper GATES["false_proven"] point of `studentized` when `low` truly loses `margin` in
    whole failed attempts, simulated from the run's own cells, taken as the largest over the loss models in `loss`. "independent"
    fails each attempt on its own; "clustered" fails all of a task's `low` attempts together. Under independent loss alone, go-json
    simulations at 3 points kept that loss under 1 % PROVEN at two attempts per arm and at 2.6-2.8 % with about eight, where the t
    interval reached 5.6 % and 3.4 %: the loss it guards against puts failures into the pooled cells and lowers the value. That
    value was too low when the loss is clustered: the calibrated control of Study F's rule (41 tasks, two attempts per arm, 20
    points) called a clustered loss of the margin PROVEN 3.50 % of the time against 2.03 % for an independent one. A clustered loss
    has half as many independent loss units: it doubles the variance of the per-task differences and skews them, and the 97.5 %
    point of `studentized` rose from 2.18 to 2.44 there. With both models, and the floor rebuilt the same way, the control's
    replicates read 2.33 % and 1.43 %. `loss=("independent",)` gives the value before 1.11.0, draw for draw. Those rates
    hold for the scenarios simulated, with the reach set taken as given: a confirmatory run should freeze `reach` beforehand. A
    planned run can take the larger of this and a value fixed beforehand from earlier attempts (`attempts`)."""
    margin = GATES["reachable_margin"] if margin is None else margin
    if not loss or set(loss) - set(LOSS_MODELS):
        raise ValueError(f"loss must name some of {LOSS_MODELS}")
    values = []
    for model in loss:
        draws = whole_loss_draws(rows, task_dir, low, ref, seed, margin, reach, attempts, clustered=model == "clustered")
        if draws is None:
            return None
        ranked = sorted(studentized(d, margin) for d in draws)
        values.append(ranked[min(len(ranked) - 1, int((1 - GATES["false_proven"]) * len(ranked)))])
    return max(values)


def paired_interval(diffs):
    """Mean of per-task differences (equal weight per task) with a two-sided 95 % t interval: tasks, not tests, are the unit."""
    values = list(diffs.values())
    if len(values) < 2:
        return {"tasks": len(values), "mean": statistics.mean(values) if values else None, "sd": None, "ci95": None}
    mean, sd = statistics.mean(values), statistics.stdev(values)
    half = t975(len(values) - 1) * sd / math.sqrt(len(values))
    return {"tasks": len(values), "mean": mean, "sd": sd, "ci95": [mean - half, mean + half]}


def behaviour_verdict(interval, sensitive, margin=None, critical=None):
    """Non-inferiority on the t interval: KILL needs it all below -margin, so a point estimate alone never kills (the
    discriminating-scale rule did, about one false KILL in three under no difference). PROVEN needs the whole interval above
    -margin or, given `critical` (proven_critical), the studentized mean above it."""
    margin = GATES["reachable_margin"] if margin is None else margin
    if not sensitive or interval["ci95"] is None or interval["tasks"] < GATES["min_signal_tasks"]:
        return "NO-INFORMATION"
    low, high = interval["ci95"]
    if high < -margin:
        return "KILL"
    if critical is None:
        return "PROVEN" if low >= -margin else "NOT-PROVEN"
    se = interval["sd"] / math.sqrt(interval["tasks"])
    statistic = (interval["mean"] + margin) / se if se else math.inf if interval["mean"] + margin > 0 else -math.inf
    return "PROVEN" if statistic > critical else "NOT-PROVEN"


def tasks_needed(sd, margin, delta=0.0, power_z=Z80):
    """Tasks for a 95 % interval to clear -margin with the given power when the true difference is `delta` (normal approximation)."""
    if margin + delta <= 0:
        return None
    return math.ceil(((1.96 + power_z) * sd / (margin + delta)) ** 2)


def declared_margin(config):
    """The non-inferiority margin the set declares before any attempt (`compare.margin`), 3 points unless stated: a set can
    declare the loss that would cancel the saving instead of near-sameness. Bounded so a margin cannot swallow any loss."""
    margin = config.get("compare", {}).get("margin", GATES["reachable_margin"])
    if not isinstance(margin, (int, float)) or not 0 < margin <= .2:
        raise ValueError("compare.margin must be a share between 0 and 0.2")
    return margin


def _pilot_reach(config_path, rows, low, ref):
    """The pilot's paired reach interval and the share of tasks both arms attempted that reach new behaviour."""
    observed = paired_interval(reachable_diffs(rows, config_path.parent / "tasks", low, ref))
    both = {r["task"] for r in rows if r["arm"] == low} & {r["task"] for r in rows if r["arm"] == ref}
    # only tasks that reach new behaviour enter the verdict (41 of 62 on go-json); ponytail: measured at the pilot's
    # replicates, more attempts can reach more tasks
    return observed, observed["tasks"] / len(both) if both else None


def _power(sd, margin, counted):
    """95 % half-width and normal-approximation power of PROVEN at `margin` when the arms are equal, over `counted` tasks."""
    if not counted:
        return None, 0.0
    return 1.96 * sd / math.sqrt(counted), statistics.NormalDist().cdf(margin / (sd / math.sqrt(counted)) - 1.96)


def feasibility(config_path, results, margin=None, sd=None):
    """Before spending: with the noise of a pilot (or a stated per-task SD), how many tasks does a verdict need, and what does the
    current number of tasks buy? A run that cannot reach a verdict should not be paid for."""
    config = json.loads(config_path.read_text())
    margin = declared_margin(config) if margin is None else margin
    low, ref = config["compare"]["candidate"], config["compare"]["reference"]
    observed = reach = None
    if results is not None:
        rows = [r for r in load_cells(results) if r["valid"] is True]
        observed, reach = _pilot_reach(config_path, rows, low, ref)
        sd = observed["sd"] if sd is None else sd
    if not sd:  # a pilot whose tasks all agree has no spread to plan with
        raise ValueError("feasibility needs a positive SD from pilot results or --sd")
    planned = len(config["tasks"])
    counted = planned * reach if reach is not None else planned  # without a pilot, every planned task is assumed to reach
    half, power = _power(sd, margin, counted)
    needed = tasks_needed(sd, margin)
    return {"margin": margin, "sd": sd, "planned_tasks": planned, "reach_share": reach, "planned_reaching": counted,
            "planned_halfwidth": half, "power_proven_if_equal": power, "tasks_needed_if_equal": needed,
            "tasks_to_mine_if_equal": math.ceil(needed / reach) if reach and needed is not None else None, "pilot": observed,
            "tasks_needed_at_pilot_mean": tasks_needed(sd, margin, observed["mean"]) if observed and observed["mean"] is not None else None}


def _task_dir(set_dir, tid):
    """The task's directory under the set's `tasks/`, its id a plain name and its resolved path still inside: never a link out."""
    root = (set_dir / "tasks").resolve()
    directory = set_dir / "tasks" / replay_eval.validate_task_id(tid)
    if directory.exists() and not directory.resolve().is_relative_to(root):
        raise ValueError(f"task directory resolves outside the set: {tid}")
    return directory


def _sufficiency_shares(config, set_dir, rows):
    """[(task, the largest share of the behaviour its commit introduced that one valid cell passes)], None without cell or new test."""
    shares = []
    for task in config["tasks"]:
        directory = _task_dir(set_dir, task.get("id"))
        baseline = set(json.loads((directory / "baseline.json").read_text()))
        hidden = [k for k in json.loads((directory / "hidden.json").read_text()) if k != "__module__" and k not in baseline]
        cells = [r for r in rows if r["task"] == task["id"]]
        shares.append((task["id"], max((sum(c["acceptance_outcomes"].get(k) == "pass" for k in hidden) / len(hidden) for c in cells if hidden), default=None)))
    return shares


def sufficiency(config_path, results, threshold, out):
    """Specification floor filter: keep a task only if a calibration cell built from the prompt alone (cheap model, other family)
    passes at least `threshold` of the behaviour the commit introduced (hidden tests minus the baseline green at base, so an empty
    patch never qualifies). It keeps tasks a cheap executor can already reach, which pulls a later verdict toward "equal": a
    sizing aid for pilots, not for confirmatory sets."""
    config = json.loads(config_path.read_text())
    rows = [r for r in load_cells(results) if r["valid"] is True]
    kept, dropped = [], []
    for tid, share in _sufficiency_shares(config, config_path.parent, rows):
        (kept if share is not None and share >= threshold else dropped).append((tid, share))
    keep = {t for t, _ in kept}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**config, "tasks": [t for t in config["tasks"] if t["id"] in keep]}, indent=1, ensure_ascii=False))
    if out.parent != config_path.parent:  # report() reads tasks/ and sensitivity.json next to the set
        for name in ("tasks", "sensitivity.json"):
            if not (out.parent / name).exists() and (config_path.parent / name).exists():
                (out.parent / name).symlink_to(config_path.parent / name)
    return {"threshold": threshold, "kept": kept, "dropped": dropped}


# ---- viability: before any paid run, can this repository give a decisive verdict, and if not, why? No model.

# Every threshold is a gate the lab already applies or a recorded rule; none is tuned here.
VIABILITY = {
    "min_tasks": GATES["min_signal_tasks"],      # behaviour_verdict(): NO-INFORMATION under 8 tasks that reach new behaviour
    "min_mutants": GATES["min_mutants"],          # sensitivity.json `immediate.passed`, the `sensitive` that report() reads
    "min_sensitivity": GATES["min_sensitivity"],  # the same gate; also the floor the v2 decision is read at
    "min_reference_acceptance": GATES["floor"],   # verdict(): acceptance under the floor is not informative
    "sufficiency_threshold": .8,                  # `sufficiency`'s default
    "max_margin": .20,                            # the break-even margin's cap: PREREG-F and declared_margin()
    "min_power": .50,                             # the D-2 study's power rule (private record): P(PROVEN | equal arms) under 0.50 is ineligible
    "max_bootstrap_miss": .025,                   # study F reads R's task bootstrap at its 97.5 % point
}
VIABILITY_INPUTS = ("tasks", "sensitivity", "reach_share", "sd", "sufficient_share", "reference_acceptance", "saving", "accepted_task_share")
VIABILITY_OPTIONAL = ("load_sensitive", "sensitivity_v2", "declared_margin")
VIABILITY_ROLES = ("candidate", "reference")  # accepted_task_share's keys: the set's compare roles, never arm names
V2_DECISIONS = ("passes", "fails", "indeterminate", "no-information", "floor-unset")  # sensitivity_v2_summary's decisions
VIABILITY_HELP = """\
Verdict: VIABLE (every input known, no reason to fail), NOT-VIABLE (reasons below; any known failure decides, whatever is
missing) or UNKNOWN (the inputs it lacks; missing data never reads VIABLE). Exit 0, 1 and 3 respectively.
Reasons, in the order of the D-2 measurability ladder (tasks, instrument, reference, power):
  too-few-tasks              mined tasks < 8 (GATES min_signal_tasks: report reads NO-INFORMATION under 8 reaching tasks)
  load-sensitive-oracle      sensitivity.json lists tasks of the set in load_sensitive (run refuses such a set)
  oracle-blind               sensitivity.json immediate: rejected / mutants < 0.30, or mutants < 20 (GATES min_sensitivity and
                             min_mutants, the `sensitive` gate report reads; the point estimate decides, the interval is shown)
  oracle-blind-v2            sensitivity-v2.json, read at floor 0.30, decides `fails`
  too-few-reaching-tasks     tasks x the pilot's reach share < 8 (feasibility's planned_reaching)
  prompt-insufficient        tasks x the share of attempted tasks where one cell passes >= 0.8 of the new behaviour < 8
                             (sufficiency's default threshold)
  reference-does-not-deliver reference arm acceptance < 0.25 (GATES floor: acceptance under it is not informative)
  pays-unreachable           a task resample has no accepted change in some arm > 2.5 % of the time (the union of the arms'
                             misses, exact with `either`, else bounded by the marginals; across the gate it is missing): the
                             cost ratio's 97.5 % bootstrap point (study F) is then infinite and PAYS cannot be read
  underpowered               normal power of PROVEN at the break-even margin m = min(0.20, reference acceptance x saving)
                             (PREREG-F) < 0.50 (the D-2 study's power rule); also when m is known to be 0 (no saving),
                             whatever else is missing
Inputs come from the set's directory (tasks, sensitivity.json, sensitivity-v2.json), from pilot cells of this set
(--results: reach share and SD as in feasibility, sufficiency, reference acceptance, median cost saving, tasks with an
accepted cell per arm) and from --inputs, a JSON object of recorded numbers that wins over both: tasks, sensitivity
{mutants, rejected}, reach_share, sd, sufficient_share, reference_acceptance [accepted, cells], saving, accepted_task_share
{candidate: share, reference: share, either: share (optional: tasks accepted in either arm)}, and optionally load_sensitive, sensitivity_v2 {decision, sensitivity, interval}, declared_margin.
VIABLE is no known reason to fail, not a promised verdict: the power ignores the calibrated critical value."""


def _viability_check(inputs):
    """Refuse unknown or malformed inputs: a typo must not turn into a missing input, nor a string into a number."""
    number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    count = lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 0
    share = lambda v: number(v) and 0 <= v <= 1
    checks = {"tasks": count, "reach_share": share, "sufficient_share": share, "sd": lambda v: number(v) and v > 0,
              "saving": lambda v: number(v) and v <= 1, "declared_margin": lambda v: number(v) and 0 < v <= VIABILITY["max_margin"],
              "reference_acceptance": lambda v: isinstance(v, list) and len(v) == 2 and all(map(count, v)) and 0 < v[1] and v[0] <= v[1],
              "sensitivity": lambda v: isinstance(v, dict) and count(v.get("mutants")) and count(v.get("rejected")) and v["rejected"] <= v["mutants"],
              # both comparison arms, by role: one favourable arm, or a misspelled one, is not the input
              # `either`, optional: tasks with an accepted change in either arm, between the larger share and the sum of both
              "accepted_task_share": lambda v: (isinstance(v, dict) and set(VIABILITY_ROLES) <= set(v) <= {*VIABILITY_ROLES, "either"}
                                                and all(map(share, v.values())) and ("either" not in v or max(v["candidate"], v["reference"])
                                                <= v["either"] <= min(1, v["candidate"] + v["reference"]) + 1e-12)),
              "load_sensitive": lambda v: isinstance(v, list), "sensitivity_v2": lambda v: isinstance(v, dict) and v.get("decision") in V2_DECISIONS}
    for key, value in inputs.items():
        if key not in checks:
            raise ValueError(f"unknown viability input: {key}")
        if value is not None and not checks[key](value):
            raise ValueError(f"malformed viability input: {key}")


def viability_verdict(inputs):
    """VIABLE, NOT-VIABLE with reasons, or UNKNOWN naming the missing inputs. A known failure reads NOT-VIABLE whatever is
    missing; VIABLE needs every input in VIABILITY_INPUTS. Recorded numbers only: no file, no model."""
    _viability_check(inputs)
    g, get, reasons, derived, notes = VIABILITY, inputs.get, [], {}, []
    fail = lambda code, detail: reasons.append({"reason": code, "detail": detail})
    tasks = get("tasks")
    few = tasks is not None and tasks < g["min_tasks"]
    if few:
        fail("too-few-tasks", f"{tasks} mined tasks; a verdict needs {g['min_tasks']} that reach new behaviour")
    if get("load_sensitive"):
        fail("load-sensitive-oracle", f"{len(get('load_sensitive'))} task(s) graded differently when their control ran alone; run refuses the set")
    sense = get("sensitivity")
    if sense is not None:
        k, n = sense["rejected"], sense["mutants"]
        derived["sensitivity"] = {"rate": k / n if n else None, "clopper_pearson95": list(_binomial_bounds(k, n)) if n else None}
        if n < g["min_mutants"] or k / n < g["min_sensitivity"]:
            fail("oracle-blind", f"the hidden tests rejected {k} of {n} planted defects; report needs at least {g['min_mutants']} at a rate of "
                                 f"{g['min_sensitivity']:g} or more, otherwise every verdict reads NO-INFORMATION")
    v2 = get("sensitivity_v2")
    if v2 is not None and v2["decision"] == "fails":
        fail("oracle-blind-v2", f"sensitivity v2 at floor {g['min_sensitivity']:g} fails: sensitivity {v2.get('sensitivity')}, interval {v2.get('interval')}")
    reach, sufficient = get("reach_share"), get("sufficient_share")
    reaching = tasks * reach if tasks is not None and reach is not None else None
    derived["reaching_tasks"] = reaching
    if reaching is not None and reaching < g["min_tasks"] and not few:
        fail("too-few-reaching-tasks", f"{tasks} tasks x reach share {reach:.3g} = {reaching:.1f} that reach new behaviour, under {g['min_tasks']}")
    if tasks is not None and sufficient is not None and tasks * sufficient < g["min_tasks"] and not few:
        fail("prompt-insufficient", f"{tasks} tasks x {sufficient:.3g} whose prompt alone let one cell pass {g['sufficiency_threshold']:g} of the new "
                                    f"behaviour = {tasks * sufficient:.1f}, under {g['min_tasks']}")
    acceptance, rate = get("reference_acceptance"), None
    if acceptance is not None:
        rate = derived["reference_acceptance_rate"] = acceptance[0] / acceptance[1]
        if rate < g["min_reference_acceptance"]:
            fail("reference-does-not-deliver", f"the reference arm was accepted in {acceptance[0]} of {acceptance[1]} cells ({rate:.1%}), "
                                               f"under {g['min_reference_acceptance']:.0%}")
    shares, unsure = get("accepted_task_share"), False
    if shares is not None and tasks:
        # R = cost per accepted change, candidate over reference, bootstrapped over tasks: a resample without one accepted change
        # in either arm makes R infinite (_cost_ratio), and once more than 2.5 % do, the upper bound PAYS reads is infinite. The
        # share of such resamples is P(miss candidate or miss reference) = m_c + m_r - (1 - either)^tasks; with the marginals
        # alone it lies between max(m_c, m_r) and m_c + m_r
        miss = derived["bootstrap_miss"] = {role: (1 - shares[role]) ** tasks for role in VIABILITY_ROLES}
        low_m, high_m = max(miss.values()), sum(miss.values())
        if "either" in shares:
            low_m = high_m = miss["either"] = max(0.0, high_m - (1 - shares["either"]) ** tasks)
        else:
            derived["bootstrap_miss_bounds"] = [low_m, high_m]
        if low_m > g["max_bootstrap_miss"]:
            fail("pays-unreachable", f"a resample of {tasks} tasks has no accepted change in some arm {low_m:.1%} of the time"
                                     + ("" if "either" in shares else " at least") + f" (candidate in {shares['candidate']:.1%} of tasks, "
                                     f"reference in {shares['reference']:.1%}), above {g['max_bootstrap_miss']:.1%}, so the cost ratio's upper bound is infinite")
        unsure = high_m > g["max_bootstrap_miss"] >= low_m  # across the gate: the arms' overlap decides, and it is not known
    saving, sd = get("saving"), get("sd")
    # m = min(0.20, rate x saving) is 0 as soon as either factor is known to be 0 or less: no other input can change that
    margin = (0.0 if (saving is not None and saving <= 0) or rate == 0 else
              min(g["max_margin"], rate * saving) if rate is not None and saving is not None else None)
    if margin is not None:
        derived["break_even_margin"] = margin
        declared = get("declared_margin")
        if declared is not None and abs(declared - margin) > 1e-9:
            notes.append(f"the set declares compare.margin {declared:g}; this reading uses the break-even margin {margin:.4g} (study F's rule). "
                         "report tests the declared one: declare the break-even margin before the first attempt for a PAYS reading")
        if margin == 0:
            fail("underpowered", "the break-even margin is 0: nothing saved, nothing to prove")
        elif sd is not None and reaching is not None:
            _, power = _power(sd, margin, reaching)
            needed = tasks_needed(sd, margin)
            derived.update(power_proven_if_equal=power, tasks_needed_if_equal=needed,
                           tasks_to_mine_if_equal=math.ceil(needed / reach) if reach else None)
            if power < g["min_power"]:
                fail("underpowered", f"power of PROVEN at the break-even margin {margin:.4g} with {reaching:.1f} reaching tasks is {power:.2f}, "
                                     f"under {g['min_power']:g}; about {needed} reaching tasks needed")
    missing = [key for key in VIABILITY_INPUTS if get(key) is None] + (["accepted_task_share.either"] if unsure else [])
    return {"verdict": "NOT-VIABLE" if reasons else "UNKNOWN" if missing else "VIABLE", "reasons": reasons, "missing": missing,
            "derived": derived, "notes": notes, "thresholds": dict(VIABILITY)}


def viability(config_path=None, results=None, stated=None):
    """Collect the inputs from the set's directory (task count, sensitivity.json, sensitivity-v2.json), pilot cells of this
    set (`results`) and recorded numbers (`stated`, which win), then judge them. Reads files only: no model, no test run."""
    found, sources, pilot = {}, {}, None
    _viability_check(stated or {})

    def put(key, value, source):
        if value is not None:
            found[key], sources[key] = value, source
    if config_path is not None:
        config = json.loads(config_path.read_text())
        set_dir = config_path.parent
        ids = {_task_dir(set_dir, t.get("id")).name for t in config["tasks"]}  # joined into paths below: plain names, inside the set
        put("tasks", len(ids), "set")
        put("declared_margin", declared_margin(config), "set")
        if (set_dir / "sensitivity.json").is_file():
            sense = json.loads((set_dir / "sensitivity.json").read_text())
            immediate = sense.get("immediate") or {}
            if all(type(immediate.get(k)) is int for k in ("mutants", "rejected")):  # a `passed` asserted without counts is no measure
                put("sensitivity", {"mutants": immediate["mutants"], "rejected": immediate["rejected"]}, "sensitivity.json immediate")
            put("load_sensitive", sorted(set(sense.get("load_sensitive") or []) & ids), "sensitivity.json")
        if (set_dir / "sensitivity-v2.json").is_file():
            v2 = json.loads((set_dir / "sensitivity-v2.json").read_text())
            summary = sensitivity_v2_summary(v2["rows"], v2["tasks"], VIABILITY["min_sensitivity"], v2.get("seed", 1))
            put("sensitivity_v2", {k: summary[k] for k in ("decision", "sensitivity", "interval")}, f"sensitivity-v2.json at floor {VIABILITY['min_sensitivity']:g}")
        if results is not None:
            low, ref = config["compare"]["candidate"], config["compare"]["reference"]
            binding = sealed_state(config, results)["state"]  # a pilot sealed with another set is refused, not matched by task ids
            every = load_cells(results)
            if {r.get("task") for r in every} - ids:
                raise ValueError("--results holds cells of tasks outside this set; give numbers from other runs in --inputs")
            rows = [r for r in every if r["valid"] is True and r.get("arm") in (low, ref)]  # an A/A copy or another arm never counts
            # attempted: every task with a cell of either arm, invalid or refused included, as the cost ratio's bootstrap counts them,
            # and every task known only from an archived refusal or a dispatch the ledger records
            known = [(r.get("task"), r.get("arm")) for r in every] + [(r["task"], r["arm"]) for r in refused_attempts(results, (low, ref))]
            for row in _ledger(results) or []:
                decoded = _decode_cell(row.get("cell", ""), ids, (low, ref)) if "dispatched_at" in row else None
                known += [decoded[:2]] if decoded else []
            attempted = {task for task, arm in known if arm in (low, ref) and task in ids}
            tried = {arm: {task for task, a in known if a == arm and task in ids} for arm in (low, ref)}
            costs = {arm: [cost_of(results, r["cell"], r) for r in rows if r["arm"] == arm] for arm in (low, ref)}
            pilot = {"binding": binding, "attempted_tasks": len(attempted), "valid_cells": {role: sum(r["arm"] == arm for r in rows)
                     for role, arm in zip(VIABILITY_ROLES, (low, ref))},
                     "costs_missing": {role: sum(c is None for c in costs[arm]) for role, arm in zip(VIABILITY_ROLES, (low, ref))}}
            try:
                if rows:
                    observed, reach = _pilot_reach(config_path, rows, low, ref)
                    put("reach_share", reach, "results (as feasibility)")
                    put("sd", observed["sd"] or None, "results (as feasibility)")  # a pilot whose tasks all agree has no spread to plan with
                if attempted:
                    put("sufficient_share", sum(t in attempted and s is not None and s >= VIABILITY["sufficiency_threshold"]
                                                for t, s in _sufficiency_shares(config, set_dir, rows)) / len(attempted), "results (as sufficiency)")
            except OSError as error:
                raise ValueError(f"cannot read the set's task files for the pilot: {error.filename or error}") from None
            refs = [r for r in rows if r["arm"] == ref]
            put("reference_acceptance", [sum(bool(r.get("accepted")) for r in refs), len(refs)] if refs else None, "results")
            # a cell with no measured cost is not left out of the median: no saving is read until every valid cell has one
            if all(costs[arm] and None not in costs[arm] for arm in (low, ref)) and statistics.median(costs[ref]) > 0:
                put("saving", 1 - statistics.median(costs[low]) / statistics.median(costs[ref]), "results (median cost per valid cell, as PREREG-F)")
            if attempted and all(tried.values()):  # an arm with no attempt is unobserved, never a measured zero
                put("accepted_task_share", {**{role: len({r["task"] for r in rows if r["arm"] == arm and r.get("accepted")}) / len(attempted)
                                               for role, arm in zip(VIABILITY_ROLES, (low, ref))},
                                            "either": len({r["task"] for r in rows if r["arm"] in (low, ref) and r.get("accepted")}) / len(attempted)},
                    "results (over every attempted task)")
    elif results is not None:
        raise ValueError("--results needs --set: the cells are read against the set's tasks")
    for key, value in (stated or {}).items():
        put(key, value, "stated")
    result = viability_verdict(found)
    if pilot is not None and pilot["binding"] == "unbound":  # cells no sealed dispatch produced cannot be attributed: never VIABLE
        result["missing"].append("pilot-binding")
        result["verdict"] = "NOT-VIABLE" if result["reasons"] else "UNKNOWN"
    return {**result, "inputs": found, "sources": sources, **({"pilot": pilot} if pilot is not None else {})}


def viability_text(result):
    lines = [f"007 lab viability: {result['verdict']}"]
    lines += [f"- {r['reason']}: {r['detail']}" for r in result["reasons"]]
    if result["missing"]:
        lines.append("Missing, so the verdict cannot be VIABLE: " + ", ".join(result["missing"]))
    lines += ["Inputs:"] + [f"  {key} = {json.dumps(value)} ({result['sources'][key]})" for key, value in result["inputs"].items()]
    lines += ["Derived:"] + [f"  {key} = {json.dumps(value)}" for key, value in result["derived"].items()]
    lines += [f"Note: {note}" for note in result["notes"]]
    if result.get("pilot"):
        lines.append("Pilot: " + json.dumps(result["pilot"], sort_keys=True))
    return "\n".join(lines)


def verdict(c, ci, *, valid, tasks, split_tasks, sensitive, accepted_share, next_share):
    """The thesis holds only if time survives, durability is shown non-inferior by an instrument that can see a defect, and rework does not eat the saving."""
    in_range = lambda share: GATES["floor"] <= share <= GATES["ceiling"]
    informative = in_range(accepted_share) and in_range(next_share)
    low, ref = [k for k in c if k not in ("reduction", "durable_diff")]
    # acceptance is already in `reduction` (time per accepted change) and is judged by the same-change verdict; a raw count
    # comparison here failed equal arms about half the time
    survives = c["reduction"] is not None and c["reduction"] >= GATES["min_reduction"]
    computable = valid >= GATES["min_cells"] and tasks >= GATES["min_tasks"] and c["durable_diff"] is not None
    if not computable or not sensitive or not split_tasks or not informative:
        durability = "NO-INFORMATION"
    elif c["durable_diff"] < GATES["durability_margin"]:
        durability = "KILL"
    else:
        durability = "PROVEN" if ci and ci[0] >= GATES["durability_margin"] else "NOT-PROVEN"
    rework = c[low]["total_wall_s"] <= c[ref]["total_wall_s"]
    thesis = ("KILLED" if durability == "KILL" else "NOT-SURVIVES" if informative and not survives else
              "HOLDS" if informative and survives and durability == "PROVEN" and rework else "UNPROVEN")
    return {"thesis": thesis, "informative_acceptance": informative, "time": "SURVIVES" if survives else "NOT-SURVIVES", "durability": durability, "rework_ok": rework}


def _decode_cell(cell, task_ids, arms):
    """(task, arm, replicate) of a cell id, read against the set's own task ids and arm names; None when no reading or several fit."""
    found = set()
    for arm in arms:
        if cell.endswith("-" + arm):
            match = re.fullmatch(r"(.+)-r([0-9]{2,3})", cell[:-len(arm) - 1])  # a replicate past 999 is unread, not planned
            if match and match[1] in task_ids:
                found.add((match[1], arm, int(match[2])))
    return found.pop() if len(found) == 1 else None


def arm_accounting(config, results, rows, receipts):
    """Per arm, the fate of every planned cell: never dispatched, attempted with no result (a dispatch or a receipt without a result:
    an orphan or a cell in flight), invalid by failure class, valid, accepted. Planned counts every task at the most replicates any
    attempted or finished cell of this run reached. `history` says whether the dispatch ledger was complete, absent, damaged or
    unreadable; without a complete one, a dispatch that left no receipt counts as never dispatched."""
    bad = ambiguous = None
    if not (results / "dispatch.jsonl").exists():
        history, status = [], "absent"
    else:
        try:
            history, bad, ambiguous = replay_eval.load_dispatch_history(results)
            dispatched_cells = {row["cell"] for row in history if "dispatched_at" in row}
            status = "damaged" if bad or ambiguous else "partial" if set(r["cell"] for r in rows) - dispatched_cells else "complete"
        except (OSError, ValueError):
            history, status = [], "unreadable"
    attempted = {row["cell"] for row in history if "dispatched_at" in row} | set(receipts)
    by_cell = {r["cell"]: r for r in rows}
    task_ids, arms = {t["id"] for t in config.get("tasks", [])}, list(config.get("arms", {}))
    decoded = [_decode_cell(cell, task_ids, arms) for cell in attempted | set(by_cell)]
    replicates = max((d[2] for d in decoded if d), default=0)
    refusals = [row["cell"] for row in history if "finished_at" in row and row.get("refused") is True]
    table = {}
    for arm in arms:
        planned = {replay_eval.cell_id(task, arm, k) for task in config.get("tasks", []) for k in range(1, replicates + 1)}
        done = [by_cell[c] for c in planned if c in by_cell]
        invalid = {}
        for row in done:
            if row.get("valid") is not True:
                kind = row.get("failure_class") if isinstance(row.get("failure_class"), str) else "unknown"
                invalid[kind] = invalid.get(kind, 0) + 1
        table[arm] = {"planned": len(planned), "not_dispatched": len(planned - attempted - set(by_cell)),
                      "no_result": len((planned & attempted) - set(by_cell)), "valid": sum(r.get("valid") is True for r in done),
                      "accepted": sum(r.get("valid") is True and bool(r.get("accepted")) for r in done), "invalid": dict(sorted(invalid.items())),
                      # attempts the provider refused, each one counted (a requeued cell's set-aside attempts are in the ledger only)
                      "refused": max(sum(c in planned for c in refusals), invalid.get("provider-rate-limit", 0))}
    return {"history": status, "ledger_invalid_lines": bad, "ledger_ambiguous_cells": ambiguous, "unread_cells": sum(d is None for d in decoded),
            "replicates": replicates, "arms": table}


VERDICT_ORDER = ["KILL", "NO-INFORMATION", "NOT-PROVEN", "PROVEN"]


def _paired(rows, low, ref):
    """Reading B: only (task, replicate) pairs with a cell of both arms."""
    arms = {}
    for r in rows:
        arms.setdefault((r["task"], r["replicate"]), set()).add(r["arm"])
    return [r for r in rows if arms[(r["task"], r["replicate"])] >= {low, ref}]


def _usable(row):
    return row is not None and row.get("valid") is True and not row.get("outcomes_unreadable")


def _unusable(row):
    return "absent" if row is None else "refused" if row.get("failure_class") == "provider-rate-limit" else "unreadable" if row.get("valid") is True else "invalid"


def _reading(cells, task_dir, low, ref, margin, seed, reach, floor, critical=True, loss=LOSS_MODELS):
    diffs = reachable_diffs(cells, task_dir, low, ref, reach=reach)
    s = paired_interval(diffs)
    e = {"tasks": s["tasks"], "mean": s["mean"], "ci95": s["ci95"], "statistic": studentized(diffs, margin) if s["tasks"] > 1 else None}
    if s["tasks"] < GATES["min_signal_tasks"] or s["ci95"] is None:
        e["verdict"] = "NO-INFORMATION"
    elif s["ci95"][1] < -margin:
        e["verdict"] = "KILL"
    elif critical:
        own = proven_critical(cells, task_dir, low, ref, seed, margin=margin, reach=reach, loss=loss)
        e.update(critical_own=own, critical=max(floor or -math.inf, math.inf if own is None else own))
        e["verdict"] = "PROVEN" if e["statistic"] > e["critical"] else "NOT-PROVEN"
    else:
        e["verdict"] = "not-computed"  # simulated only where it can change the answer
    return e


def _cost_ratio(cells, results, low, ref, reserve, worst=False):
    """Cost per accepted change at `low` over the same at `ref`. A cell with no measured cost counts at `reserve`; in the worst
    case at `reserve` for `low` and zero for `ref`, and an invalid `ref` cell counts as accepted. A refused attempt adds its
    cost and never an accepted change; in the worst case a `ref` refusal costs zero, so it cannot lower the bound."""
    def cost(r):
        if worst and r["arm"] == ref and r.get("failure_class") == REFUSED:
            return 0.0
        value = cost_of(results, r["cell"], r)
        return value if harness_report._valid_money(value) else (reserve if r["arm"] == low else 0.0) if worst else reserve

    def per(arm):
        mine = [r for r in cells if r["arm"] == arm]
        accepted = sum(False if r.get("failure_class") == REFUSED else bool(r.get("accepted")) if r.get("valid") is True else worst and arm == ref
                       for r in mine)  # a refusal is never an accepted change, whatever else its row says
        return sum(map(cost, mine)) / accepted if accepted else math.inf
    a, b = per(low), per(ref)
    return a / b if math.isfinite(a) and math.isfinite(b) and b > 0 else math.inf


REFUSED = "provider-rate-limit"  # the failure class of an attempt the provider refused (refused())


def _archive(results, arms):
    """(rows of `arms`, unresolved names): each refused attempt set aside under refused/ (`_set_aside`) once, by its archived row,
    its cost read from that row or its archived receipt. Files are grouped by canonical cell and attempt number (an int: `.1` and
    `.01` are one attempt). Unresolved, whatever arm it may be: a duplicate attempt, an attempt with a receipt and no row, a row
    that cannot be read or whose task, arm and replicate are not its file name's cell, and, when the ledger exists (even empty), a
    cell whose attempts are not exactly 1 to the number of requeued refusals the ledger records for it; every archive when the
    ledger exists but cannot be read. Without a ledger (a directory not written by `run`) each cell's attempts must run 1 to n."""
    suffixes = sorted(replay_eval.CELL_ARTIFACT_SUFFIXES, key=len, reverse=True)
    attempts, unresolved = {}, []
    for path in sorted((results / "refused").iterdir()) if (results / "refused").is_dir() else ():
        suffix = next((s for s in suffixes if path.name.endswith(s)), None)
        match = re.fullmatch(r"(.+)\.([0-9]{1,9})", path.name[:-len(suffix)]) if suffix else None
        if not match:
            continue
        files = attempts.setdefault((match[1], int(match[2])), {})
        if suffix in files:
            unresolved.append(f"refused/{path.name}")  # the same attempt twice
            continue
        files[suffix] = path
    found, per_cell = [], {}
    for (cid, number), files in sorted(attempts.items()):
        per_cell.setdefault(cid, set()).add(number)
        path = files.get(".json")
        if path is None:
            unresolved.append(f"refused/{cid}.{number}: no row")  # a receipt or other file with no archived row
            continue
        try:
            row = json.loads(path.read_text()) if path.is_file() and not path.is_symlink() else None
        except (OSError, ValueError):
            row = None
        own = isinstance(row, dict) and isinstance(row.get("task"), str) and isinstance(row.get("arm"), str) and type(row.get("replicate")) is int
        if not own or replay_eval.cell_id({"id": row["task"]}, row["arm"], row["replicate"]) != cid:
            unresolved.append(f"refused/{path.name}")
            continue
        if row["arm"] in arms:
            found.append({**row, "cell": f"refused/{path.name[:-len('.json')]}", "attempt_of": cid, "valid": False, "accepted": False,
                          "failure_class": REFUSED})
    history = _ledger(results) if (results / "dispatch.jsonl").exists() else None
    if (results / "dispatch.jsonl").exists() and history is None:
        if attempts:
            unresolved.append("dispatch.jsonl")
    else:
        expected = {}
        for row in history or []:
            if "finished_at" in row and row.get("refused") is True and row.get("requeued") is True:
                expected[row["cell"]] = expected.get(row["cell"], 0) + 1
        for cid in sorted(set(per_cell) | set(expected)):
            want = set(range(1, (expected.get(cid, 0) if history is not None else max(per_cell[cid])) + 1))
            if per_cell.get(cid, set()) != want:
                unresolved.append(f"refused/{cid}: attempts {sorted(per_cell.get(cid, set()))}, expected {sorted(want)}")
    return found, unresolved


def refused_attempts(results, arms):
    """The archived refused attempts of `arms` that _archive resolves."""
    return _archive(results, arms)[0]


def _ratio_interval(cells, results, low, ref, reserve, seed, worst):
    tasks = sorted({r["task"] for r in cells})
    by, rng, draws = {t: [r for r in cells if r["task"] == t] for t in tasks}, random.Random(seed), []
    for _ in range(GATES["draws"]):
        draws.append(_cost_ratio([r for t in (rng.choice(tasks) for _ in tasks) for r in by[t]], results, low, ref, reserve, worst))
    draws.sort()
    return [draws[int(.025 * len(draws))], draws[int(.975 * len(draws)) - 1]]


def guard_decision(every, planned, task_dir, low, ref, margin, seed, reach, floor, loss=LOSS_MODELS):
    """The verdict of `missing_data_guard` without the cost ratio: (verdict, readings, missing_data). L0 reads the valid cells of
    `every` in readings P and B, the worse deciding; L2 imputes each planned cell without a usable result as `low`'s worst case and
    reads again, with its own critical value, only when L0 is PROVEN. The critical value is the larger of `floor` and
    `proven_critical` over the loss models in `loss`. Reach must be given: imputed cells must not move the denominator."""
    rows = [r for r in every if r.get("valid") is True]
    readings = {name: _reading(cells, task_dir, low, ref, margin, seed, reach, floor, loss=loss)
                for name, cells in (("P", rows), ("B", _paired(rows, low, ref)))}
    verdict = min((e["verdict"] for e in readings.values()), key=VERDICT_ORDER.index)
    by = {(r["task"], r["replicate"], r["arm"]): r for r in every}
    imputed, reasons = [], {}
    for task, rep, arm in planned:
        r = by.get((task, rep, arm))
        if _usable(r):
            imputed.append(r)
            continue
        why = _unusable(r)
        reasons[why] = reasons.get(why, 0) + 1
        imputed.append({"task": task, "replicate": rep, "arm": arm, "cell": replay_eval.cell_id({"id": task}, arm, rep), "valid": True,
                        "imputed": why, "acceptance_outcomes": {k: "fail" if arm == low else "pass" for k in reach.get(task, [])}})
    guard = {"planned": len(planned), "usable": len(planned) - sum(reasons.values()), "imputed_in_L2": reasons, "label": None,
             "unusable_cells": sorted(r["cell"] for r in every if not _usable(r))}
    if reasons:
        guard["L2"] = {name: _reading(cells, task_dir, low, ref, margin, seed, reach, floor, critical=verdict == "PROVEN", loss=loss)
                       for name, cells in (("P", imputed), ("B", _paired(imputed, low, ref)))}
        if verdict == "PROVEN" and any(e["verdict"] != "PROVEN" for e in guard["L2"].values()):
            verdict, guard["label"] = "NOT-PROVEN", "not decisive by missing data"
    return verdict, readings, guard


def missing_data_guard(config, results, task_dir, every, planned, low, ref, margin, reserve, reach=None):
    """F-1's missing-data guard, made native (`report --missing-data-guard`). L0 reads the valid cells, in readings P (all) and B
    (pairs with both arms); the worse decides. L2 takes the plan and imputes every planned cell without a usable valid result
    (invalid of any class, refused, never dispatched, or valid with unreadable outcomes) as the worst case for `low`: `low` fails
    every reachable test, `ref` passes every one; its critical value is simulated again. PROVEN needs PROVEN in L0 and L2, in P and
    B; L0 PROVEN with L2 short of it reads NOT-PROVEN, "not decisive by missing data". KILL follows L0. R is the cost per accepted
    change at `low` over `ref`, with a task bootstrap, and a worst case; every refused attempt, in place or set aside under
    refused/, adds its cost to its arm and task once and no accepted change. Answer: PAYS (PROVEN and both R upper
    bounds below 1), PROVEN-NOT-ECONOMIC, DOES-NOT-PAY (KILL), else the verdict. The instrument checks (serial re-grade, A/A) are
    not part of it."""
    seed, floor, frozen = config["seed"], (config.get("compare") or {}).get("critical_floor"), reach is not None
    # a refusal is never a grade: a row the controller labelled refused reads invalid before reach or any reading is taken
    every = [{**r, "valid": False, "accepted": False} if r.get("failure_class") == REFUSED else r for r in every]
    rows = [r for r in every if r.get("valid") is True]
    if reach is None:  # the run's own reach, fixed from the valid cells, so imputed cells cannot move the denominator
        reach = {}
        for task in sorted({r["task"] for r in rows}):
            hidden = [k for k in json.loads((task_dir / task / "hidden.json").read_text()) if k != "__module__"]
            base = set(json.loads((task_dir / task / "baseline.json").read_text()))
            reach[task] = [k for k in hidden if k not in base and any(c["acceptance_outcomes"].get(k) == "pass" for c in rows if c["task"] == task)]
    verdict, readings, guard = guard_decision(every, planned, task_dir, low, ref, margin, seed, reach, floor)
    archived, unresolved = _archive(results, (low, ref))
    charged = every + archived  # what was paid, refusals included (decision R2-1, 1.11.0)
    ratio, ratio_worst = (_cost_ratio(charged, results, low, ref, reserve, w) for w in (False, True))
    ci, ci_worst = (_ratio_interval(charged, results, low, ref, reserve, seed, w) for w in (False, True))
    # an archive the guard cannot reconcile leaves the charged cost unknown: no PAYS, and no NOT-ECONOMIC either
    answer = (("ACCOUNTING-UNRESOLVED" if unresolved else "PAYS" if max(ci[1], ci_worst[1]) < 1 else "PROVEN-NOT-ECONOMIC") if verdict == "PROVEN"
              else "DOES-NOT-PAY" if verdict == "KILL" else verdict)
    return {"verdict": verdict, "answer": answer, "margin": margin, "critical_floor": floor, "reserve_usd": reserve, "readings": readings,
            "missing_data": guard, "cost_ratio": ratio, "cost_ratio_ci95": ci, "cost_ratio_worst": ratio_worst, "cost_ratio_worst_ci95": ci_worst,
            "reach_frozen": frozen, "refused": sum(r.get("failure_class") == REFUSED and r["arm"] in (low, ref) for r in charged),
            "accounting_unresolved": unresolved}


def _reach_tests(rows, task_dir):
    """{task: reachable tests} as reach_rates finds them from `rows`: hidden tests red at base that some cell passes."""
    out = {}
    for task in sorted({r["task"] for r in rows}):
        hidden = [k for k in json.loads((task_dir / task / "hidden.json").read_text()) if k != "__module__"]
        base = set(json.loads((task_dir / task / "baseline.json").read_text()))
        out[task] = [k for k in hidden if k not in base and any(c["acceptance_outcomes"].get(k) == "pass" for c in rows if c["task"] == task)]
    return out


def aa_check(cells, task_dir, aa, margin, seed, sensitive, task_ids, replicates, reach=None, planned=True, archived=()):
    """`run --aa`: the arm against its copy, on the same tasks and plan. Discordance: whole-change acceptance differs within a
    (task, replicate) pair, over pairs whose two cells are usable, with a Clopper-Pearson interval (pairs pooled, taken as
    independent). A pair with an absent, refused, invalid or unreadable cell is counted and its cells named, never as agreement;
    the worst case counts it discordant. `replicates` is the plan when `planned`, else only the replicates cells reached, so
    trailing undispatched pairs are not seen; a cell set aside under refused/ (`archived`, cell ids) reads refused. The
    same-change statistic is the verdict's own (reachable_diffs on valid cells, the t interval, proven_critical), A against A. It
    rejects equality when its 95% interval, the verdict's level, excludes zero. Qualification reads its own interval
    (`qualifying_behaviour`) from usable matched pairs on reaching tasks only: it needs A/A cells, at least min_signal_tasks such
    tasks, no rejection by either interval, and the planned replicates."""
    arm, label = aa["arm"], aa["label"]
    by = {(r["task"], r["replicate"], r["arm"]): r for r in cells}
    per_task, missing, matched_rows = {}, {}, []
    for task in task_ids:
        entry = per_task[task] = {"pairs": 0, "discordant": 0, "missing": 0}
        for rep in range(1, replicates + 1):
            a, b = by.get((task, rep, arm)), by.get((task, rep, label))
            if _usable(a) and _usable(b):
                entry["pairs"] += 1
                matched_rows += [a, b]
                entry["discordant"] += bool(a.get("accepted")) != bool(b.get("accepted"))
                continue
            entry["missing"] += 1
            for side, r in ((arm, a), (label, b)):
                if not _usable(r):
                    cid = replay_eval.cell_id({"id": task}, side, rep)
                    missing.setdefault("refused" if r is None and cid in archived else _unusable(r), []).append(cid)
    n, k, m = (sum(e[key] for e in per_task.values()) for key in ("pairs", "discordant", "missing"))
    matched = sum(e["pairs"] > 0 for e in per_task.values())
    valid = [r for r in cells if r.get("valid") is True]
    diffs = reachable_diffs(valid, task_dir, arm, label, reach=reach)
    interval = paired_interval(diffs)
    critical = proven_critical(valid, task_dir, arm, label, seed, margin, reach=reach)
    ci = interval["ci95"]
    rejects = ci is not None and (ci[0] > 0 or ci[1] < 0)
    # what qualifies: usable matched pairs only, on tasks that reach new behaviour (the reach of every valid cell, or the frozen
    # one); the pooled statistic above is reported as before, and a rejection by either one disqualifies
    qualifying = paired_interval(reachable_diffs(matched_rows, task_dir, arm, label, reach=_reach_tests(valid, task_dir) if reach is None else reach))
    q_ci = qualifying["ci95"]
    q_rejects = q_ci is not None and (q_ci[0] > 0 or q_ci[1] < 0)
    enough = lambda i: i["ci95"] is not None and i["tasks"] >= GATES["min_signal_tasks"]
    copies = any(r["arm"] == label for r in cells) or any(c.endswith("-" + label) for c in archived)  # set aside under refused/ too
    status = ("absent" if not copies
              else "rejects-equality" if rejects and enough(interval) or q_rejects and enough(qualifying)
              else "too-few-tasks" if not enough(qualifying) else "qualified" if planned else "plan-unknown")
    return {"arm": arm, "label": label, "status": status, "rejects_equality": rejects, "planned_replicates": replicates if planned else None,
            "tasks_with_matched_pairs": matched, "qualifying_behaviour": qualifying, "qualifying_rejects_equality": q_rejects,
            "discordance": {"pairs": n, "discordant": k, "rate": k / n if n else None, "ci95": list(_binomial_bounds(k, n)) if n else None,
                            "ci95_assumes": "pairs pooled over tasks and replicates, taken as independent",
                            "missing_pairs": m, "worst_case_rate": (k + m) / (n + m) if n + m else None},
            "missing_cells": {why: sorted(v) for why, v in sorted(missing.items())}, "per_task": per_task, "reachable_behaviour": interval,
            "statistic": studentized(diffs, margin) if len(diffs) > 1 else None, "critical": critical,
            "same_change_reachable": behaviour_verdict(interval, sensitive, margin, critical=math.inf if critical is None else critical)}


ORACLE_CLASSES = ("accepted", "rejected", "oracle-error", "timeout", "invalid", "unrecorded")
ORACLE_ALPHA = .01


def _one_outcome_after(share):
    """Graded cells after which an oracle accepting `share` of them gives a single outcome with chance under ORACLE_ALPHA."""
    return math.ceil(math.log(ORACLE_ALPHA) / math.log(share))


# the verdict reads acceptance as informative between GATES floor and ceiling: an honest oracle at either edge rings under 1%
ORACLE_THRESHOLDS = {"zero_accepted_after": _one_outcome_after(1 - GATES["floor"]), "all_accepted_after": _one_outcome_after(GATES["ceiling"]),
                     "min_count": 3, "alpha": ORACLE_ALPHA}  # min_count: the run's own --max-invalid default


def _exits(row):
    checks = row.get("acceptance")
    return [c.get("exit") for c in checks if isinstance(c, dict)] if isinstance(checks, list) else []


LAB_ACCEPT_ARGS = ["-I", "-B", f"{ACCEPT}/lab_accept.py", f"{ACCEPT}/lab.json", f"{ACCEPT}/hidden.json", f"{ACCEPT}/baseline.json"]


def grader_contracts(config):
    """{task: contract} of the set's tasks: `lab-accept-v1` when declared, or when the task's only acceptance command is
    lab_accept's exact invocation as `mine` writes it (any interpreter, these arguments); `custom` for any other grader; `unknown`
    for a declared contract 007 does not know. A cell of a task the set does not list reads `unknown` too."""
    out = {}
    for task in config.get("tasks", []):
        if not isinstance(task, dict) or "id" not in task:
            continue
        declared, commands = task.get("acceptance_exit_contract"), task.get("acceptance")
        exact = isinstance(commands, list) and len(commands) == 1 and isinstance(commands[0], list) and commands[0][1:] == LAB_ACCEPT_ARGS
        out[task["id"]] = (replay_eval.LAB_ACCEPT_EXIT_CONTRACT if declared == replay_eval.LAB_ACCEPT_EXIT_CONTRACT or declared is None and exact
                           else "custom" if declared is None else "unknown")
    return out


def oracle_class(row, custom=False):
    """One cell as the grader's health reads it, never a verdict. A grader failure comes first, even on a cell the run counted
    valid: a set mined before 1.10.1 reads exit 2 as a rejection, and lab_accept writes its report before every exit 1, so a
    single exit 1 with no readable report is a grader that crashed (the 0/124 failure). Exit 3 is a rejection by timeout. A
    `custom` grader (not lab_accept) fails only as the controller saw it fail; any exit but 0 rejects. A cell with no grader exit
    (no acceptance, or an empty one) is unrecorded."""
    failure, exits = str(row.get("failure_class") or ""), _exits(row)
    unreported = row.get("outcomes_unreadable") or not isinstance(row.get("acceptance_outcomes"), dict)
    if (failure == "acceptance-harness-error" or failure.startswith("hidden-acceptance-")
            or not custom and (any(e not in (0, 1, 3) for e in exits) or (exits == [1] and unreported))):
        return "oracle-error"
    if failure == "acceptance-timeout" or not custom and 3 in exits:
        return "timeout"
    if row.get("valid") is not True:
        return "invalid"
    if not exits:
        return "unrecorded"
    return "accepted" if all(e == 0 for e in exits) else "rejected"


def _off_contract(row, custom=False):
    """An exit lab_accept never gives (a signal, a missing interpreter), or a cell whose acceptance disagrees with its exits."""
    exits = _exits(row)
    return not custom and any(e not in (0, 1, 2, 3) for e in exits) or bool(
        exits and row.get("valid") is True and bool(row.get("accepted")) != all(e == 0 for e in exits))


def _contract(row, contracts):
    return replay_eval.LAB_ACCEPT_EXIT_CONTRACT if contracts is None else contracts.get(row.get("task"), "unknown")


def _oracle_counts(rows, contracts=None):
    """`contracts` ({task: contract}, grader_contracts): only `lab-accept-v1` tasks are read under lab_accept's exit contract;
    `custom` and `unknown` ones are not, and the counts say how many cells each contract had. None: every cell is lab_accept's."""
    classes, exits, kinds = dict.fromkeys(ORACLE_CLASSES, 0), {}, {}
    for row in rows:
        kind = _contract(row, contracts)
        kinds[kind] = kinds.get(kind, 0) + 1
        classes[oracle_class(row, kind != replay_eval.LAB_ACCEPT_EXIT_CONTRACT)] += 1
        for code in _exits(row):  # a number, or one bucket: an exit written as text could name anything
            key = str(code) if type(code) is int else "non-integer"
            exits[key] = exits.get(key, 0) + 1
    return {"cells": len(rows), "classes": classes, "exit_codes": dict(sorted(exits.items())), "contracts": dict(sorted(kinds.items())),
            "contract_violations": sum(_off_contract(r, _contract(r, contracts) != replay_eval.LAB_ACCEPT_EXIT_CONTRACT) for r in rows)}


def oracle_health(rows, margin, controls=None, contracts=None):
    """The grader's health pooled over `rows`: counts only, no arm, task or cell. Alarms (ORACLE_THRESHOLDS): no acceptance
    after `zero_accepted_after` graded cells, every graded cell accepted after `all_accepted_after`, grader errors or timeouts at
    `min_count` or more and above the declared margin's share (alone they could move one arm by more than the margin), and any
    exit outside the contract (lab_accept's tasks only; `contracts` maps each task, see _oracle_counts). An alarm never changes a verdict. `controls`:
    the set's tasks whose reference control passed. The 1% thresholds take graded cells as independent; repeated attempts on one
    task are not."""
    counts = _oracle_counts(rows, contracts)
    c, t = counts["classes"], ORACLE_THRESHOLDS
    graded = c["accepted"] + c["rejected"] + c["timeout"]
    alarms = [name for name, ringing in (
        ("rejects-everything", graded >= t["zero_accepted_after"] and not c["accepted"]),
        ("accepts-everything", graded >= t["all_accepted_after"] and c["accepted"] == graded),
        ("oracle-errors", c["oracle-error"] >= t["min_count"] and c["oracle-error"] > margin * (graded + c["oracle-error"])),
        ("oracle-timeouts", c["timeout"] >= t["min_count"] and c["timeout"] > margin * graded),
        ("exit-contract", counts["contract_violations"] > 0)) if ringing]
    status = "oracle-suspect" if alarms else "no-alarm" if graded + c["oracle-error"] else "unmeasured"
    return {**counts, "graded": graded, "reference_controls_passed": controls, "margin": margin, "thresholds": t, "alarms": alarms,
            "status": status, "sha256": hashlib.sha256(json.dumps(counts, sort_keys=True).encode()).hexdigest()}


def _oracle_state(config_path, rows, margin):
    """oracle_health with the set's reference controls and its graders' contracts. No acknowledgement in 1.11.0 (decision R3-2):
    an open alarm marks the report until the counts stop ringing."""
    try:
        config = json.loads(config_path.read_text())
    except (OSError, ValueError):
        config = {}
    ids = {t.get("id") for t in config.get("tasks", []) if isinstance(t, dict)}
    try:
        conformant = json.loads((config_path.parent / "sensitivity.json").read_text()).get("conformant")
        controls = len({c for c in conformant if isinstance(c, str)} & ids) if isinstance(conformant, list) else None
    except (OSError, ValueError, AttributeError):
        controls = None
    return oracle_health(rows, margin, controls, grader_contracts(config))


def blind_orphans(config, results, rows, planned_replicates=None):
    """Files left in `.blind/` (an agent whose controller died, or one still running), each named by its cell when the sealed
    salt and the ledger or the plan identify it, else None. Counted beside orphan receipts, never dropped. The candidates are the
    cells with a result or a dispatch and the declared plan (`planned_replicates`, the run's --replicates); without it, the plan is
    guessed up to one replicate past the highest cell."""
    names = replay_eval.blind_files(results)
    if not names:
        return []
    try:
        manifest = _read_manifest(results / RUN_MANIFEST) or {}
    except ValueError:
        manifest = {}
    salt, aa, arms = manifest.get("blind_salt"), manifest.get("aa"), config.get("arms", {})
    if isinstance(aa, dict) and aa.get("label") not in arms:
        arms = {**arms, aa.get("label"): None}
    # the cells a token can belong to: those with a result or a dispatch, and every planned one up to one replicate past the last
    # the declared plan exactly; without it, a guess up to one replicate past the last cell
    reps = planned_replicates if planned_replicates is not None else max([r["replicate"] for r in rows if type(r.get("replicate")) is int] + [1]) + 1
    candidates = {r["cell"] for r in rows} | {row["cell"] for row in (_ledger(results) or [])}
    candidates |= {replay_eval.cell_id(t, a, k) for t in config.get("tasks", []) for a in arms for k in range(1, reps + 1)}
    return [{"file": name, "cell": replay_eval.blind_cell(salt, name, candidates)} for name in names]


def read_isolation(rows):
    """What each cell asked its CLI to enforce and what its stream showed. `unrecorded`: cells written before 1.11.0."""
    modes, found = {}, {"clean": 0, "contaminated": 0, "incomplete": 0, "unscanned": 0, "unrecorded": 0}
    for row in rows:
        mode = row.get("read_isolation") if isinstance(row.get("read_isolation"), str) else "unrecorded"
        modes[mode] = modes.get(mode, 0) + 1
        scan = row.get("contamination")
        state = scan.get("status") if isinstance(scan, dict) and scan.get("status") in found else "unrecorded"
        found[state] += 1
    return {"cells": len(rows), "modes": dict(sorted(modes.items())), "contamination": found,
            "contaminated_cells": sorted(str(r.get("cell")) for r in rows if isinstance(r.get("contamination"), dict)
                                         and r["contamination"].get("status") == "contaminated")}


STATUS_TRIES = 3
# read_isolation_mode()'s values: anything else in a cell is counted as `other` by status
STATUS_ISOLATION_MODES = ("unenforced", "claude-settings", "codex-profile", "claude-settings+codex-profile", "unrecorded")


def _generation(results):
    """Every cell artifact and `.blind/` file by name, inode, size and modification time: equal before and after a read means
    nothing the read depends on was added, removed, renamed or rewritten in between."""
    entries = []
    for directory in (results, results / replay_eval.BLIND_DIR):
        try:
            names = sorted(os.listdir(directory))
        except (FileNotFoundError, NotADirectoryError):
            continue
        for name in names:
            if directory == results and not (name.endswith(".json") and replay_eval.is_cell_id(name.split(".", 1)[0])):
                continue
            try:
                info = os.lstat(directory / name)
            except FileNotFoundError:
                entries.append((str(directory), name, None))
                continue
            entries.append((str(directory), name, info.st_ino, info.st_size, info.st_mtime_ns))
    return entries


def _snapshot(results):
    """One reading of a results directory a run may be writing: the cells, receipts and `.blind/` names read between two equal
    generations of every artifact they depend on; read again, up to STATUS_TRIES times, when anything moved or was rewritten.
    (cells, receipts, blind names, stable); the last reading comes back unstable."""
    found, receipts, names = {}, {}, []
    if not results.is_dir():  # nothing written yet
        return {}, {}, [], True
    for _ in range(STATUS_TRIES):
        before = _generation(results)
        try:
            names = replay_eval.blind_files(results)
            found, receipts = replay_eval.read_cell_artifacts(results)
        except (FileNotFoundError, ValueError):  # a file that vanished, or was caught half written
            continue
        if _generation(results) == before and replay_eval.blind_files(results) == names:
            return found, receipts, names, True
    return found, receipts, names, False


def status(config_path, results):
    """Read only and advisory: the grader's health pooled over every cell written so far, A/A copies included, with no arm, task,
    cell, verdict, time or free text. Takes no lock, writes nothing and checks no receipt; `snapshot` says whether it read a stable
    directory (the CLI exits 3 when it did not)."""
    config = json.loads(config_path.read_text())
    found, receipts, names, stable = _snapshot(results)
    rows = [{**row, "cell": cid} for cid, row in found.items()]
    health = _oracle_state(config_path, rows, declared_margin(config))
    # counts only: labelled receipts carry the arm in their names, and a `.blind/` name is whatever was written there
    tokens = sum(bool(re.fullmatch(r"[0-9]{16}\.(runner\.json|stream\.jsonl)", name)) for name in names)
    orphans = {"receipts": len(set(receipts) - set(found)), "blind_files": {"tokens": tokens, "other": len(names) - tokens},
               "note": "in flight while a run is active, else orphaned"}
    isolation = read_isolation(rows)
    del isolation["contaminated_cells"]  # pooled: names no cell
    modes = {}
    for mode, count in isolation["modes"].items():  # a mode the runner never writes is counted, not printed
        key = mode if mode in STATUS_ISOLATION_MODES else "other"
        modes[key] = modes.get(key, 0) + count
    isolation["modes"] = dict(sorted(modes.items()))
    return {"schema": "007-lab/status/v1", "snapshot": "stable" if stable else "unstable", "oracle_health": health, "orphans": orphans,
            "read_isolation": isolation}


def report(config_path, results, next_results, *, single_look=False, missing_data_guard_reserve=None, frozen_reach=None, planned_replicates=None):
    """`single_look`: the report may be read once, with no run active on the results; it writes LOOK.json, after which neither
    `report` nor `run` works on them. `missing_data_guard_reserve` (US$ for a cell with no measured cost, normally the run's
    --stop-usd) adds the guard, which needs `planned_replicates` (the run's --replicates: the plan is not recorded); the A/A
    check needs it too to qualify. `frozen_reach`
    ({task: [tests]}, fixed before the attempts) replaces the reach the run's own cells would give; its digest is reported."""
    if (results / LOOK).exists():
        raise ValueError(f"the single look has been taken ({LOOK} exists): these results are not read again: {results}")
    if missing_data_guard_reserve is not None and planned_replicates is None:
        raise ValueError("the missing-data guard needs the run's planned replicates")
    if planned_replicates is not None and (type(planned_replicates) is not int or planned_replicates < 1):
        raise ValueError("planned replicates must be the run's --replicates, an integer >= 1")
    if not single_look:
        return _report(config_path, results, next_results, False, missing_data_guard_reserve, frozen_reach, planned_replicates)
    with contextlib.ExitStack() as locks:  # no run may add cells, to stage 1 or stage 2, while the single look is taken
        for directory in [results] + ([next_results] if next_results else []):
            handle = locks.enter_context((directory / ".run.lock").open("a"))
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError(f"a run is active on these results: the single look waits for it: {directory}") from None
        if (results / LOOK).exists():  # checked again under the lock: two looks cannot both pass
            raise ValueError(f"the single look has been taken ({LOOK} exists): these results are not read again: {results}")
        return _report(config_path, results, next_results, True, missing_data_guard_reserve, frozen_reach, planned_replicates)


def _report(config_path, results, next_results, single_look, missing_data_guard_reserve, frozen_reach, planned_replicates):
    config = json.loads(config_path.read_text())
    low, ref = config["compare"]["candidate"], config["compare"]["reference"]
    manifest = sealed_state(config, results)
    aa = manifest["aa"]
    rows = cells = load_cells(results)
    # an orphan receipt (an attempt with no result) may have spent: named in the report, never silently dropped
    _, receipts = replay_eval.read_cell_artifacts(results)
    blind = blind_orphans(config, results, rows, planned_replicates)
    receipts = {**receipts, **{entry["cell"]: {} for entry in blind if entry["cell"] and entry["cell"] not in receipts}}
    accounting = arm_accounting({**config, "arms": {**config["arms"], aa["label"]: None}} if aa else config, results, rows, receipts)
    orphans = sorted(set(receipts) - {r["cell"] for r in rows})
    twins = [r for r in rows if aa and r.get("arm") in (aa["arm"], aa["label"])]
    rows = [r for r in rows if not aa or r.get("arm") != aa["label"]]  # the verdict reads the set's arms only, as without --aa
    every = rows
    excluded = sorted(r["cell"] for r in rows if r["valid"] is not True)
    rows = [r for r in rows if r["valid"] is True]
    if not rows:
        raise ValueError(f"no valid cells to report ({len(excluded)} invalid, {len(orphans)} orphan receipts, "
                         f"{sum(e['cell'] is None for e in blind)} unnamed files in {replay_eval.BLIND_DIR}/)")
    stage2 = None
    if next_results:  # stage 2 must be chained from this sealed run, at the reference arm, and bound to its own seal
        upstream = _read_manifest(next_results / RUN_MANIFEST)
        if upstream is None and manifest["sha256"]:
            raise ValueError(f"next results predate the seal of these results: chain again into a new directory, or report without them")
        if upstream is None:
            ledger = _ledger(next_results)
            if ledger is None or _bound_digests(ledger):
                raise ValueError(f"next results lost the manifest their dispatches name, or their ledger cannot be read: {next_results}")
            stage2 = {"state": "absent", "sha256": None, "unbound_dispatches": None, "unbound_cells": None}
        if upstream is not None and (upstream.get("parent_manifest_sha256") != manifest["sha256"] or upstream.get("arms") != {"next": config["arms"][ref]}):
            raise ValueError(f"next results are not chained from these results at the reference arm: {next_results}")
        if upstream is not None:
            ledger, digest = _ledger(next_results), _sha256(next_results / RUN_MANIFEST)
            if ledger is None or (_bound_digests(ledger) and _bound_digests(ledger) != {digest}):
                raise ValueError(f"next results do not match their own seal: {next_results}")
            command = hashlib.sha256(json.dumps(config.get("agent_command"), sort_keys=True).encode()).hexdigest()
            if "agent_command_sha256" in upstream and upstream["agent_command_sha256"] != command:
                raise ValueError(f"next results ran another agent command than these results: {next_results}")
            state, unbound, unbound_cells = _binding(next_results, upstream, digest, ledger)
            if state == "unbound":
                raise ValueError(f"next results are unbound from their own seal (another controller, or cells copied in): {next_results}")
            stage2 = {"state": state, "sha256": digest, "unbound_dispatches": unbound, "unbound_cells": unbound_cells}
    following = [r for r in load_cells(next_results) if r["valid"] is True] if next_results else []
    next_rows = {r["task"][:-len("-next")]: r for r in following}
    durable = {r["cell"]: bool(r["accepted"] and r["cell"] in next_rows and next_rows[r["cell"]]["accepted"]) for r in rows}
    tasks = sorted({r["task"] for r in rows})
    per_task = {t: {a: arm_stats([r for r in rows if r["task"] == t and r["arm"] == a], durable, next_rows) for a in (low, ref)} for t in tasks}
    split = [t for t, v in per_task.items() if v[low]["durable"] != v[ref]["durable"]]
    c = contrast(rows, durable, next_rows, low, ref)
    ci = bootstrap(rows, durable, next_rows, low, ref, tasks, config["seed"])
    sense = json.loads((config_path.parent / "sensitivity.json").read_text())
    valid = sum(r["valid"] is True for r in rows) + sum(r["valid"] is True for r in following)
    tier = verdict(c, ci["durable_diff_ci95"], valid=valid, tasks=len(tasks), split_tasks=split, sensitive=sense["passed"],
                   accepted_share=sum(r["accepted"] for r in rows) / len(rows), next_share=sum(r["accepted"] for r in following) / max(1, len(following)))
    tokens = {a: [r["usage"]["reasoning_output_tokens"] for r in rows if r["arm"] == a] for a in (low, ref)}
    reasoning = {a: statistics.median(v) if v else None for a, v in tokens.items()}  # an arm with no valid cell has no median
    faster = sum(per_task[t][low]["agent_wall_s"] < per_task[t][ref]["agent_wall_s"] for t in tasks)
    hidden = {t: [k for k in json.loads((config_path.parent / "tasks" / t / "hidden.json").read_text()) if k != "__module__"] for t in tasks}
    tests = unseen(rows, hidden, low, ref)
    diff, low_rate, ref_rate = unseen_diff(rows, tests, low, ref)
    rng, draws = random.Random(config["seed"]), []
    for _ in range(GATES["draws"]):
        value = unseen_diff(rows, tests, low, ref, rng.choices(tasks, k=len(tasks)))[0]
        if value is not None:
            draws.append(value)
    draws.sort()
    unseen_ci = [draws[int(.025 * len(draws))], draws[min(len(draws) - 1, int(.975 * len(draws)))]] if draws else None
    signal = [t for t in tasks if tests[t]]
    sensitive = sense.get("immediate", {}).get("passed", False)
    # diagnostic only: this point-estimate rule called about one null run in three a KILL, so no verdict reads it
    behaviour = {"tests": sum(map(len, tests.values())), "signal_tasks": len(signal), low: low_rate, ref: ref_rate, "diff": diff, "ci95": unseen_ci, "estimable": len(draws),
                 "superseded_verdict": same_change(diff, unseen_ci, sum(map(len, tests.values())), len(signal), sensitive)}
    task_dir = config_path.parent / "tasks"
    margin = declared_margin(config)
    diffs = reachable_diffs(rows, task_dir, low, ref, reach=frozen_reach)
    reachable = paired_interval(diffs)
    critical = proven_critical(rows, task_dir, low, ref, config["seed"], margin, reach=frozen_reach)
    tier["margin"] = margin
    tier["compare_changed_after_seal"] = manifest["compare_changed"]
    tier["run_binding"] = manifest["state"]
    # a limit can be per model: unequal refusals mean the compared arms' valid cells may cover different commits; the A/A copy's
    # refusals are counted on their own (aa_refused), never as an inequality between the compared arms
    tier["refused_unequal"] = accounting["arms"].get(low, {}).get("refused", 0) != accounting["arms"].get(ref, {}).get("refused", 0)
    tier["aa_refused"] = accounting["arms"].get(aa["label"], {}).get("refused", 0) if aa else None
    tier["next_run_binding"] = stage2["state"] if stage2 else None
    tier["same_change_reachable"] = behaviour_verdict(reachable, sensitive, margin, critical=math.inf if critical is None else critical)
    # an arm with no valid cell pairs no task: the verdict is NO-INFORMATION, and the report says why instead of a bare default
    tier["arms_without_valid_cells"] = [a for a in (low, ref) if not tokens[a]]
    if tier["arms_without_valid_cells"]:  # nor time, durability or rework: an empty arm's zero wall time would read as no rework
        tier.update(thesis="UNPROVEN", same_change_reachable="NO-INFORMATION", time="NO-INFORMATION", durability="NO-INFORMATION", rework_ok=None)
    proof = {"critical": critical, "statistic": studentized(diffs, margin) if len(diffs) > 1 else None,
             "t975": t975(len(diffs) - 1) if len(diffs) > 1 else None, "t_false_proven": false_proven(rows, task_dir, low, ref, config["seed"], margin, reach=frozen_reach)}
    if tier["same_change_reachable"] == "KILL":
        tier["thesis"] = "KILLED"
    elif tier["thesis"] == "HOLDS" and tier["same_change_reachable"] != "PROVEN":
        tier["thesis"] = "UNPROVEN"
    pseudo = {a: paired_interval(reachable_diffs(rows, task_dir, low, ref, split=a, reach=frozen_reach)) for a in (low, ref)}
    if planned_replicates is not None and planned_replicates < accounting["replicates"]:
        raise ValueError(f"cells reach replicate {accounting['replicates']}, beyond the {planned_replicates} planned")
    twin = aa_check(twins, task_dir, aa, margin, config["seed"], sensitive, [t["id"] for t in config["tasks"]],
                    accounting["replicates"] if planned_replicates is None else planned_replicates, frozen_reach,
                    planned=planned_replicates is not None,
                    archived={r["attempt_of"] for r in refused_attempts(results, (aa["arm"], aa["label"]))}) if aa else None
    tier["aa_status"] = twin["status"] if twin else "absent"
    tier["aa_qualified"] = tier["aa_status"] == "qualified"  # never without A/A cells
    # pooled over every cell, copies included; per arm only here, where the report already shows each arm's acceptance
    oracle = _oracle_state(config_path, cells, margin)
    contracts = grader_contracts(config)
    oracle["per_arm"] = {arm: _oracle_counts([r for r in cells if r.get("arm") == arm], contracts) for arm in sorted({r.get("arm") for r in cells})}
    tier["oracle_status"] = oracle["status"]
    tier["oracle_suspect"] = oracle["status"] == "oracle-suspect"  # the verdict's values stand; its label is not clean
    guard = None
    if missing_data_guard_reserve is not None:
        planned = [(t["id"], rep, arm) for t, rep, arm in plan(config, planned_replicates)]
        guard = missing_data_guard(config, results, task_dir, every, planned, low, ref, margin, missing_data_guard_reserve, frozen_reach)
    if stage2 is not None:
        stage2["stage1_cells_chained"] = sum(r["cell"] in next_rows for r in rows)
        stage2["stage1_cells"] = len(rows)
    result = {"schema": "007-lab/report/v6", "at": _now(), "run_manifest": manifest, "next_run_manifest": stage2, "arm_accounting": accounting, "verdict": tier, "excluded_invalid": excluded, "orphan_receipts": orphans,
              "orphan_blind_files": blind, "read_isolation": read_isolation(cells),
              "unreadable_outcomes": sorted(r["cell"] for r in rows if r.get("outcomes_unreadable")), "unseen_behaviour": behaviour,
              "reachable_behaviour": reachable, "proven_critical": proof, "pseudo_aa": pseudo, "aa": twin, "oracle_health": oracle, "contrast": c, "bootstrap": ci, "split_tasks": split, "per_task": per_task,
              "sensitivity": sense, "median_reasoning_tokens": reasoning, "tasks_faster": [faster, len(tasks)], "gates": GATES,
              "missing_data_guard": guard, "reach_frozen": frozen_reach is not None,
              "frozen_reach_sha256": hashlib.sha256(json.dumps(frozen_reach, sort_keys=True).encode()).hexdigest() if frozen_reach is not None else None}
    (results / "report.json").write_text(json.dumps(result, indent=1) + "\n")
    (results / "report.md").write_text(summary(result, low, ref, len(rows)))
    if single_look:
        (results / LOOK).write_text(json.dumps({"at": _now(), "report_sha256": _sha256(results / "report.json")}, indent=1) + "\n")
    return result


def aa_line(aa, margin):
    """The A/A line of report.md: the noise floor the verdict carries, or that it carries none."""
    if not aa or aa["status"] == "absent":
        return "- **A/A:** no A/A cells, so this verdict carries no measured noise floor and is not A/A-qualified (`run --aa ARM` adds them)."
    pct = lambda x: f"{100 * x:.1f}%"
    d, r = aa["discordance"], aa["reachable_behaviour"]
    status = {"qualified": "A/A-qualified: the copy does not reject equality with its arm",
              "rejects-equality": "**the A/A rejects equality at the verdict's 95% level: the instrument alone produces differences of this size; "
                                  "the verdict is not A/A-qualified**",
              "too-few-tasks": f"not A/A-qualified: fewer than {GATES['min_signal_tasks']} tasks that reach new behaviour have a usable "
                               "matched pair",
              "plan-unknown": "not A/A-qualified: without the run's planned replicates (`report --replicates N`) undispatched trailing "
                              "pairs cannot be counted"}[aa["status"]]
    discord = (f"acceptance differs in {d['discordant']} of {d['pairs']} pairs ({pct(d['rate'])}, 95% {pct(d['ci95'][0])} to {pct(d['ci95'][1])}, "
               "pairs taken as independent)"
               if d["pairs"] else "no complete pair")
    lost = (f"; {d['missing_pairs']} pairs have an absent or unusable cell, never counted as agreement (worst case {pct(d['worst_case_rate'])})"
            if d["missing_pairs"] else "")
    reach = (f"; reach difference {100 * r['mean']:+.1f} points (95% {100 * r['ci95'][0]:+.1f} to {100 * r['ci95'][1]:+.1f}, {r['tasks']} tasks), "
             f"same change at margin {100 * margin:g} points {aa['same_change_reachable']}" if r.get("ci95") else "")
    return f"- **A/A, `{aa['arm']}` twice:** {status}; {discord}{lost}{reach}."


ORACLE_ALARM_TEXT = {"rejects-everything": "no graded cell accepted", "accepts-everything": "every graded cell accepted",
                     "oracle-errors": "grader errors above the margin's share", "oracle-timeouts": "grader timeouts above the margin's share",
                     "exit-contract": "grader exits outside its contract"}


def oracle_line(health):
    """The oracle-health line of report.md: pooled counts and the alarms."""
    if not health:
        return None
    alarms = "; ".join(ORACLE_ALARM_TEXT[a] for a in health["alarms"])
    state = {"no-alarm": "no alarm", "unmeasured": "unmeasured: no cell records a grade",
             "oracle-suspect": f"**oracle-suspect** ({alarms})"}[health["status"]]
    classes = ", ".join(f"{k} {v}" for k, v in health["classes"].items() if v) or "none"
    exits = ", ".join(f"{k}: {v}" for k, v in health["exit_codes"].items()) or "none"
    return f"- **Oracle health:** {state}; {health['cells']} cells ({classes}); grader exits {exits}."


def isolation_line(isolation):
    """The read-isolation line of report.md: what the cells asked their CLI to enforce, and what the streams showed."""
    if not isolation or not isolation["cells"]:
        return None
    modes = ", ".join(f"{mode} {n}" for mode, n in isolation["modes"].items())
    found = ", ".join(f"{k} {v}" for k, v in isolation["contamination"].items() if v)
    bad = isolation["contamination"]["contaminated"]
    return (f"- **Read isolation:** asked of the CLI: {modes}; streams: {found}"
            + (f"; **{bad} contaminated cells read a protected path and are invalid**" if bad else "")
            + ". The check sees only tool calls the stream logs; `unenforced` means nothing stopped a read, and only an OS sandbox isolates fully.")


def summary(result, low, ref, attempts):
    """The report in plain words: what was measured, what the same-change verdict means at the declared margin, what is not shown."""
    tier, c, r = result["verdict"], result["contrast"], result["reachable_behaviour"]
    points = lambda x: f"{100 * x:+.1f}"
    margin = 100 * tier["margin"]
    meaning = {"PROVEN": f"`{low}` lost no more than {margin:g} points against `{ref}` on average over these commits, on what their own tests check.",
               "KILL": f"`{low}` lost more than {margin:g} points: keep `{ref}`.",
               "NOT-PROVEN": f"Neither a loss beyond {margin:g} points nor its absence is shown.",
               "NO-INFORMATION": "Too few commits reach new behaviour, or the oracle failed its planted-defect check."}[tier["same_change_reachable"]]
    interval = f" (mean {points(r['mean'])} points, 95% interval {points(r['ci95'][0])} to {points(r['ci95'][1])}, {r['tasks']} commits)" if r.get("ci95") else ""
    saving = f"{100 * c['reduction']:.0f}% less agent time per accepted change" if c["reduction"] is not None else "agent time not comparable"
    reasoning = result["median_reasoning_tokens"]
    tokens = lambda value: "none (no valid cell)" if value is None else f"{value:.0f}"
    sealed = result.get("run_manifest")  # absent from reports written before 1.8
    binding = {"sealed": "the set, the agent command's sealed files, 007 and Python matched the seal, made before the first dispatch, each time the run started or resumed",
               "sealed-late": "sealed only after some attempts had run: those earlier attempts are not bound to it",
               "unbound": "some attempts after the seal do not name it (another controller, or cells copied in): the seal binds none of them",
               "absent": "no run manifest: nothing binds the attempts to one set"}[sealed["state"]] if sealed else None
    if binding and sealed.get("sealed_parts") is not None:
        binding += f"; sealed files: {', '.join(sealed['sealed_parts']) or 'none'}"
    if binding and sealed.get("unsealed_files"):
        binding += f"; left out by the set: {', '.join(sealed['unsealed_files'])}"
    if binding and sealed.get("program_sealed") is False:
        binding += "; the agent command's program itself was not sealed (a relative or unresolved path)"
    if binding and sealed["compare_changed"]:
        binding += "; the comparison or margin changed after the seal, so the margin was not declared before these attempts"
    accounting = result.get("arm_accounting")
    return "\n".join([
        f"# `{low}` vs `{ref}`: {attempts} valid attempts",
        "",
        *(["**Oracle-suspect:** an oracle alarm is open. The verdict below is computed as usual but is not a clean verdict while the alarm "
           "is open; whoever reads it decides whether the run stands, and records why with the study.", ""]
          if result.get("verdict", {}).get("oracle_suspect") else []),
        *([f"- **No comparison:** {' and '.join(f'`{a}`' for a in empty)} {'has' if len(empty) == 1 else 'have'} no valid cell, so no task "
           "pairs the arms and every verdict below reads NO-INFORMATION or UNPROVEN for that reason, not for the arms' behaviour."]
          if (empty := tier.get("arms_without_valid_cells")) else []),
        f"- **Waiting:** {saving} ({tier['time']}); median reasoning tokens {tokens(reasoning[low])} vs {tokens(reasoning[ref])}.",
        f"- **The same change, margin {margin:g} points:** {tier['same_change_reachable']}. {meaning}{interval}",
        f"- **Durable:** {tier['durability']}.",
        *([f"- **Run binding:** {binding}."] if binding else []),
        *[f"- **Cells, `{arm}`:** {a['planned']} planned, {a['not_dispatched']} never dispatched, {a['no_result']} attempted without a result, "
          f"{sum(a['invalid'].values())} invalid" + (f" ({', '.join(f'{k} {v}' for k, v in a['invalid'].items())})" if a['invalid'] else "")
          + f", {a['valid']} valid, {a['accepted']} accepted" + (f"; {a['refused']} attempts refused by the provider" if a.get('refused') else "")
          + "." for arm, a in (accounting or {}).get("arms", {}).items()],
        *(["- **Refusals hit the arms unequally:** a provider limit can be per model, so the arms' valid cells may cover different commits."]
          if result["verdict"].get("refused_unequal") else []),
        *([f"- **Missing-data guard:** {g['verdict']}" + (f" ({g['missing_data']['label']})" if g["missing_data"]["label"] else "")
           + f", answer {g['answer']}; {g['missing_data']['usable']} of {g['missing_data']['planned']} planned cells usable; cost per accepted change "
           f"{g['cost_ratio']:.3f} of `{ref}`'s (95% {g['cost_ratio_ci95'][0]:.3f} to {g['cost_ratio_ci95'][1]:.3f}; worst case "
           f"{g['cost_ratio_worst']:.3f}, {g['cost_ratio_worst_ci95'][0]:.3f} to {g['cost_ratio_worst_ci95'][1]:.3f}). The instrument checks are not part of it."]
          if (g := result.get("missing_data_guard")) else []),
        aa_line(result.get("aa"), tier["margin"]),
        *([line] if (line := oracle_line(result.get("oracle_health"))) else []),
        *([f"- **Dispatch ledger:** {accounting['history']}; the counts above may be incomplete."] if accounting and accounting["history"] != "complete" else []),
        *([f"- **Stage 2:** {result['next_run_manifest']['state']}; {result['next_run_manifest']['stage1_cells_chained']} of "
           f"{result['next_run_manifest']['stage1_cells']} valid stage-1 attempts have a valid stage-2 attempt; the others count as not durable."]
          if result.get("next_run_manifest") else []),
        "- **Not shown by this report:** served effort (the CLIs do not report it), invoiced cost (costs are estimates), commits, models or specification forms other than these.",
        *([line] if (line := isolation_line(result.get("read_isolation"))) else []),
        f"- **Excluded:** {len(result['excluded_invalid'])} invalid attempts and {len(result.get('orphan_receipts', []))} orphan receipts, never retried"
        + (f"; {len(blind)} files an agent left under its token in `.blind/` ({sum(e['cell'] is None for e in blind)} not traced to a cell)"
           if (blind := result.get("orphan_blind_files")) else "") + ".",
        "",
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(prog="007 lab", description="Headless effort replay for any repository and any agent")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, target in (("mine", "--config"), ("sensitivity", "--set"), ("run", "--set"), ("chain", "--set"), ("report", "--set"), ("status", "--set")):
        sub = commands.add_parser(name)
        sub.add_argument(target, type=Path, required=True, dest="path")
        sub.add_argument("--out", type=Path, required=name in ("mine", "run", "chain"))
        sub.add_argument("--jobs", type=int, default=jobs_limit(), help="parallel cells; above a quarter of the cores (at least 2) it warns")
        sub.add_argument("--strict-jobs", action="store_true", help="refuse --jobs above that limit instead of warning")
        if name == "run":
            sub.add_argument("--replicates", type=int, required=True)
            sub.add_argument("--max-calls", type=int, required=True)
            sub.add_argument("--max-usd", type=float, required=True)
            sub.add_argument("--stop-usd", type=float, default=5.0)
            sub.add_argument("--max-invalid", type=int, default=3, help="stop once this many cells are invalid (never retried)")
            sub.add_argument("--requeue-refused", action="store_true",
                             help="a cell the provider refused is set aside under refused/ and dispatched again after the pause")
            sub.add_argument("--over-limit", choices=("stop", "record"), default="stop",
                             help="a cell costing more than --stop-usd: stop the run (default) or record it and go on to the --max-usd cap")
            sub.add_argument("--chunk", type=int, help="dispatch at most this many cells, wait for them, run the gates, then the next chunk")
            sub.add_argument("--max-load", type=float, help="before each chunk, wait for the 5-minute load to fall under this; logs load.log")
            sub.add_argument("--load-wait-s", type=int, default=3600, help="how long to wait for --max-load before pausing (machine-busy)")
            sub.add_argument("--quota-gate", action="store_true", help="before each chunk, run the set's quota_probe and pause (quota-hold) unless it has room")
            sub.add_argument("--cost-marker-at", type=int, help="after this many cells, project the cost once (needs --cost-marker-hold-usd)")
            sub.add_argument("--cost-marker-hold-usd", type=float, help="a projection above this holds the run for good (HOLD.json)")
            sub.add_argument("--rate-limit-wait-s", type=int, default=0, help="wait out rate-limit pauses inside the run, up to this long in all")
            sub.add_argument("--aa", metavar="ARM", help="also run ARM's A/A copy (label ARM-aa) on every task and replicate; report reads it")
        if name == "sensitivity":
            sub.add_argument("--operator", choices=("v1", "v2"), default="v1", help="v2: one unit reverted in the reference tree (sensitivity-v2.json)")
            sub.add_argument("--floor", type=float, help="v2: the floor its three-state decision reads; without it the decision is floor-unset")
        if name in ("chain", "report", "status"):
            sub.add_argument("--results", type=Path, required=True)
        if name == "report":
            sub.add_argument("--next-results", type=Path)
            sub.add_argument("--single-look", action="store_true", help="write LOOK.json: these results are never read or run again")
            sub.add_argument("--missing-data-guard", action="store_true", help="add L0/L2 from the plan and the worst-case cost ratio")
            sub.add_argument("--reserve-usd", type=float, help="with --missing-data-guard: a cell with no measured cost counts at this (the run's --stop-usd)")
            sub.add_argument("--frozen-reach", type=Path, help="JSON {task: [tests]} fixed before the attempts, instead of the run's own reach")
            sub.add_argument("--replicates", type=int, help="the run's --replicates, which fixes the plan: needed by --missing-data-guard "
                                                            "and for an A/A check to qualify")
    plan_ = commands.add_parser("feasibility", help="before spending: tasks a verdict needs, from a pilot or a stated per-task SD")
    plan_.add_argument("--set", type=Path, required=True, dest="path")
    plan_.add_argument("--results", type=Path)
    plan_.add_argument("--sd", type=float)
    plan_.add_argument("--margin", type=float)
    floor = commands.add_parser("sufficiency", help="drop tasks whose prompt alone cannot reach their hidden tests")
    floor.add_argument("--set", type=Path, required=True, dest="path")
    floor.add_argument("--results", type=Path, required=True)
    floor.add_argument("--threshold", type=float, default=.8)
    floor.add_argument("--out", type=Path, required=True)
    viable = commands.add_parser("viability", help="before spending: can this repository give a decisive verdict, and if not, why",
                                 epilog=VIABILITY_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    viable.add_argument("--set", type=Path, dest="path", help="the mined set (replay-set.json), with sensitivity.json beside it")
    viable.add_argument("--results", type=Path, help="pilot cells of this set")
    viable.add_argument("--inputs", type=Path, help="JSON object of recorded numbers; they win over the set and the results")
    viable.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)
    if args.command == "viability":
        if args.path is None and args.inputs is None:
            parser.error("viability needs --set, --inputs or both")
        try:
            stated = json.loads(args.inputs.expanduser().read_text()) if args.inputs else None
            if stated is not None and not isinstance(stated, dict):
                raise ValueError("--inputs must hold a JSON object")
            result = viability(args.path.expanduser().resolve() if args.path else None,
                               args.results.expanduser().resolve() if args.results else None, stated)
        except ValueError as error:
            parser.error(str(error))
        print(viability_text(result) if args.format == "text" else json.dumps(result))
        return {"VIABLE": 0, "NOT-VIABLE": 1}.get(result["verdict"], 3)
    if args.command == "feasibility":
        results = args.results.expanduser().resolve() if args.results else None
        print(json.dumps(feasibility(args.path.expanduser().resolve(), results, args.margin, args.sd)))
        return 0
    if args.command == "sufficiency":
        print(json.dumps(sufficiency(args.path.expanduser().resolve(), args.results.expanduser().resolve(), args.threshold, args.out.expanduser().resolve())))
        return 0
    path = args.path.expanduser().resolve()
    out = args.out.expanduser().resolve() if args.out else None
    if args.command == "run" and args.strict_jobs and args.jobs > jobs_limit():
        parser.error(f"--jobs {args.jobs} is above {jobs_limit()} (a quarter of this machine's cores, at least 2)")
    if args.command in ("mine", "sensitivity", "chain") and args.jobs > jobs_limit():  # run checks its own
        message = f"--jobs {args.jobs} is above {jobs_limit()} (a quarter of this machine's cores, at least 2): load can move grades"
        if args.strict_jobs:
            parser.error(message)
        print(f"007 lab: warning: {message}", file=sys.stderr)
    if args.command == "sensitivity" and args.floor is not None and (args.operator != "v2" or not 0 < args.floor <= 1):
        parser.error("--floor is a rate in (0, 1] and only the v2 operator reads it")
    if args.command == "mine":
        print(json.dumps({"tasks": mine(json.loads(path.read_text()), out, args.jobs)}))
    elif args.command == "sensitivity":
        print(json.dumps(sensitivity_v2(path, args.jobs, args.floor) if args.operator == "v2" else sensitivity(path, args.jobs)))
    elif args.command == "run":
        try:
            result = run(path, out, replicates=args.replicates, jobs=args.jobs, max_calls=args.max_calls, max_usd=args.max_usd, stop_usd=args.stop_usd,
                         max_invalid=args.max_invalid, requeue_refused=args.requeue_refused, over_limit=args.over_limit, chunk=args.chunk,
                         max_load=args.max_load, load_wait_s=args.load_wait_s, quota_gate=args.quota_gate, cost_marker_at=args.cost_marker_at,
                         cost_marker_hold_usd=args.cost_marker_hold_usd, rate_limit_wait_s=args.rate_limit_wait_s, strict_jobs=args.strict_jobs,
                         aa=args.aa)
        except ValueError as error:  # a refusal by the run (its options, set or artifacts) prints as a usage error, exit 2
            parser.error(str(error))
        print(json.dumps(result))
        return 2 if result.get("stop") else 0
    elif args.command == "chain":
        print(json.dumps(chain(path, args.results.expanduser().resolve(), out)))
    elif args.command == "status":
        try:
            result = status(path, args.results.expanduser().resolve())
        except ValueError as error:
            parser.error(str(error))
        print(json.dumps(result))
        return 3 if result["snapshot"] != "stable" else 1 if result["oracle_health"]["status"] == "oracle-suspect" else 0
    else:
        if args.missing_data_guard and (args.reserve_usd is None or args.replicates is None):
            parser.error("--missing-data-guard needs --reserve-usd (the run's --stop-usd) and --replicates (the run's)")
        reach = json.loads(args.frozen_reach.expanduser().read_text()) if args.frozen_reach else None
        result = report(path, args.results.expanduser().resolve(), args.next_results.expanduser().resolve() if args.next_results else None,
                        single_look=args.single_look, missing_data_guard_reserve=args.reserve_usd if args.missing_data_guard else None,
                        frozen_reach=reach, planned_replicates=args.replicates)
        print(json.dumps({**result["verdict"], **({"missing_data_guard": {k: result["missing_data_guard"][k] for k in ("verdict", "answer")}}
                                                  if result["missing_data_guard"] else {})}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
