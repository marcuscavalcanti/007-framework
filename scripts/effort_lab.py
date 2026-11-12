"""`007 lab`: headless effort replay for any Git repository and any coding agent.

mine        commit pairs A -> B (the next real change to A's sources) with hidden tests and a generated contract. No model.
sensitivity does a latent defect in A show up when B lands? Reference patches minus one hunk. No model.
run         every arm × task × replicate in parallel, under a call and money budget. Calls the configured agent.
chain       each candidate of A becomes the base of B, in a private mirror of the repository. No model.
report      frozen gates. A verdict is only as strong as the instrument: an insensitive one yields NO-INFORMATION, never PASS.
            "Same change" is read on reachable behaviours, paired by task, with a symmetric interval rule and a pseudo A/A.
feasibility before spending: how many tasks a verdict needs, from a pilot's noise or a stated SD. No model.
sufficiency drop tasks whose prompt alone cannot reach their hidden tests (calibration cells from a cheap arm). No model.

Durable means the change survives the next change. Agents are an argv template (`agent_command`) and tests are an adapter in
lab_accept.py; nothing here knows a vendor or a language.
"""
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    reference = _git(repo, "diff", "--binary", parent, sha, "--", ".", *[f":(exclude){f}" for f in hidden_files]).decode("utf-8", "replace")
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
    (directory / "reference.patch").write_text(built["reference"])
    # ponytail: Go only, where a redeclared test name breaks the package; other adapters keep the agent's tests until one collides
    reset = {"reset_to_base": ["*_test.go"]} if built["spec"]["adapter"] == "go" else {}
    return {"id": tid, "repo": config.get("repo_key", "source"), "base": commit["parent"], "accepted": commit["sha"], "prompt": prompt_for(config, built["message"], built["contract"]), "acceptance_timeout_s": 900, **reset,
            "hidden_acceptance": [{"source": str(s), "sha256": hashlib.sha256(s.read_bytes()).hexdigest(), "target": t} for s, t in entries],
            "acceptance": [[sys.executable, "-I", "-B", f"{ACCEPT}/lab_accept.py", f"{ACCEPT}/lab.json", f"{ACCEPT}/hidden.json", f"{ACCEPT}/baseline.json"]]}


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
    if not following:
        return task, {"id": tid, "spec": first["spec"], "contract": first["contract"], "hidden": len(first["hidden"])}
    next_task = write_task(config, out, tid + "-next", following, second)
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
    return subprocess.run(["git", "apply", "--recount", "--binary", "-"], cwd=tree, input=patch_text.encode(errors="surrogateescape"), capture_output=True).returncode == 0


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
    next_tasks, broken = [], []
    for row in load_cells(results):
        meta, task = pairs[row["task"]], tasks[row["task"]]
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
    return {"tasks": len(next_tasks), "broken": broken}


# ---- sensitivity

def hunks(patch_text):
    """(file header, [hunks]) per text file of a unified diff."""
    out = []
    for chunk in re.split(r"(?m)^(?=diff --git )", patch_text):
        if chunk.startswith("diff --git ") and "GIT binary patch" not in chunk:
            parts = re.split(r"(?m)^(?=@@ )", chunk)
            if len(parts) > 1:
                out.append((parts[0], parts[1:]))
    return out


def mutants(patch_text, limit, rng):
    """The reference minus one hunk, sampled: a change partly done, as a weaker agent might leave it."""
    files = hunks(patch_text)
    index = [(i, j) for i, (_, parts) in enumerate(files) for j in range(len(parts))]
    rng.shuffle(index)
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
        real_next = _git(repo, "diff", "--binary", meta["next"]["base"], meta["next"]["accepted"]).decode("utf-8", "replace") if "next" in meta else ""
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
    result = sensitivity_summary(rows)
    (out / "sensitivity.json").write_text(json.dumps(result, indent=1))
    return result


def sensitivity_summary(rows):
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
            "passed": bool(survivors) and len(survivors) >= GATES["min_survivors"] and caught / len(survivors) >= GATES["min_sensitivity"]}


# ---- run

def plan(config, replicates):
    """Whole replicates first, so a pilot of replicate 1 is a prefix of the full run and nothing is wasted."""
    cells, rng = [], random.Random(config["seed"])
    for rep in range(1, replicates + 1):
        block = [(t, rep, a) for t in config["tasks"] for a in config["arms"]]
        rng.shuffle(block)
        cells += block
    replay_eval.validate_cell_artifacts(config["tasks"], config["arms"], replicates)
    return cells


def _controller_failure(out, task, arm, rep, error):
    """The result of a cell whose controller raised: invalid, never retried, its receipt (if the agent ran) kept and bound."""
    cid = replay_eval.cell_id(task, arm, rep)
    path, receipt = out / f"{cid}.json", out / f"{cid}.runner.json"
    if path.exists():  # the cell finished before the error: its own result stands
        return json.loads(path.read_text())
    row = {"schema": "007-framework/replay-cell/v1", "task": task["id"], "arm": arm, "replicate": rep, "valid": False, "accepted": False,
           "failure_class": f"controller-error:{type(error).__name__}", "cost_usd": "unmeasured", "acceptance_outcomes": "unavailable",
           "runner_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest() if receipt.is_file() else "unmeasured"}
    path.write_text(json.dumps(row))
    return row


def cost_of(out, cid, row):
    if harness_report._valid_money(row.get("cost_usd")):
        return row["cost_usd"]
    receipt = out / f"{cid}.runner.json"
    value = json.loads(receipt.read_text()).get("cost_usd") if receipt.is_file() and receipt.stat().st_size else None
    return value if harness_report._valid_money(value) else None


RUN_MANIFEST = "run-manifest.json"


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


def seal(config):
    """What a resumed run must find unchanged, checked each time the run starts or resumes. Limits (replicates, calls, money, jobs,
    invalid budget) stay adjustable at a planned pause. Executables are the agent command's program (a PATH lookup for the first
    word) and every absolute file it names, through symlinks. A relative path resolves inside the task's workspace, which the set's
    base commit fixes; a later PATH lookup (`env agent`), anything the program launches, environment variables and the CLI's own
    configuration are not sealed, nor the parts the set lists in `unsealed_files` (a log the attempts rewrite). The manifest guards
    against accidents, not tampering: whoever can write the output directory can rewrite it."""
    listed = config.get("unsealed_files", [])
    if not isinstance(listed, list) or not all(isinstance(part, str) for part in listed):
        raise ValueError("unsealed_files must be a list of strings")
    tools, skip = {}, set(listed)
    for index, part in enumerate(config.get("agent_command", [])):
        if part in skip:
            continue
        value = part.split("=", 1)[1] if part.startswith("-") and "=" in part else part  # --config=/abs/file names a file too
        found = shutil.which(part) if index == 0 and "/" not in part else value if os.path.isabs(value) else None
        if found and Path(found).is_file():
            real = Path(found).resolve()
            tools[part] = {"path": str(real), "sha256": _sha256(real)}
    # ponytail: the agent command's files only; compilers and test runners the oracle calls are not sealed yet
    return {"schema": "007-framework/lab-run-manifest/v1", "set_sha256": set_sha256(config), "executables": tools,
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
                "unbound_dispatches": None, "unbound_cells": None}
    digest = _sha256(results / RUN_MANIFEST)
    if bound and bound != {digest}:
        raise ValueError(f"run manifest changed after dispatch: {results}")
    if recorded.get("set_sha256") != set_sha256(config):
        raise ValueError(f"results were run with a different set: {results}")
    state, unbound, unbound_cells = _binding(results, recorded, digest, history)
    return {"state": state, "compare_changed": recorded.get("compare") != config.get("compare"), "sha256": digest,
            "program_sealed": recorded.get("program_sealed"), "sealed_parts": recorded.get("sealed_parts"),
            "unsealed_files": recorded.get("unsealed_files"), "unbound_dispatches": unbound, "unbound_cells": unbound_cells}


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


def run(config_path, out, *, replicates, jobs, max_calls, max_usd, stop_usd, timeout_s=3600, execute=None, max_invalid=3):
    """Serialize controllers sharing an output directory before checking or publishing dispatch history."""
    if not all(harness_report._valid_money(value) for value in (max_usd, stop_usd)):
        raise ValueError("budget values must be finite nonnegative numbers")
    for name, value, minimum in (("replicates", replicates, 1), ("jobs", jobs, 1),
                                  ("max_calls", max_calls, 0), ("max_invalid", max_invalid, 1)):
        if type(value) is not int or value < minimum:
            raise ValueError(f"{name} limit must be an integer >= {minimum}")
    timeout_s = replay_eval.validate_timeout(timeout_s)
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (out / ".run.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"stop": "run-already-active", "calls": 0}
        return _run(config_path, out, replicates=replicates, jobs=jobs, max_calls=max_calls, max_usd=max_usd,
                    stop_usd=stop_usd, timeout_s=timeout_s, execute=execute, max_invalid=max_invalid)


def _run(config_path, out, *, replicates, jobs, max_calls, max_usd, stop_usd, timeout_s, execute, max_invalid):
    """Spend rule: a cell is dispatched only if the spend so far plus stop_usd for it and for each cell in flight stays under max_usd.
    A failed call that reports no cost is charged stop_usd (its reserve), never zero; only a valid cell without a cost stops the run."""
    config = json.loads(config_path.read_text())
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    execute = execute or replay_eval.execute_cell
    ledger = out / "dispatch.jsonl"
    cells = plan(config, replicates)
    replay_eval.validate_cell_artifacts(config["tasks"], config["arms"], replicates, directory=out)
    results, receipts = replay_eval.read_cell_artifacts(out)
    done = set(results)
    orphans = set(receipts) - done
    try:
        history, invalid_history, ambiguous_history = replay_eval.load_dispatch_history(out)
        if invalid_history:
            return {"stop": "unreadable-dispatch-history", "calls": 0}
        if ambiguous_history:
            return {"stop": "ambiguous-dispatch-history", "calls": 0}
        for row in history:
            if row["cell"] not in done:
                orphans.add(row["cell"])
    except (OSError, ValueError):
        return {"stop": "unreadable-dispatch-history", "calls": 0}
    if orphans or (out / "STOP.json").exists():
        return {"stop": "uncertain-attempts" if orphans else "stopped-before", "orphans": sorted(orphans)}
    try:
        sealed = seal(config)
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
        # a directory from before 1.8 is sealed now and reported as sealed-late; written whole, then renamed
        with tempfile.NamedTemporaryFile("w", dir=out, prefix="." + RUN_MANIFEST + ".", delete=False) as handle:
            handle.write(json.dumps({**sealed, "compare": config.get("compare"), "sealed_at": _now(), "cells_before_seal": len(done),
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
        details = {part: {"sealed": old.get(part), "found": new.get(part)} for part in parts}
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
    spent, invalid, stop, lock = 0.0, 0, None, threading.Lock()

    def charge(cost):
        nonlocal spent, stop
        if spent is not None:
            try:
                spent = float(harness_report._money_sum((spent, stop_usd if cost is None else cost)))
            except ValueError:
                spent = None
                stop = stop or "cost-total-unavailable"

    for name in done:
        row = json.loads((out / f"{name}.json").read_text())
        cost = cost_of(out, name, row)
        if cost is None and row.get("valid") is True:
            stop = "cost-unavailable"
        else:
            charge(cost)
            if cost is not None and cost > stop_usd:
                stop = stop or "cell-over-limit"
        invalid += row.get("valid") is not True
    if invalid >= max_invalid:
        stop = stop or "invalid-budget"
    cell_name = lambda cell: replay_eval.cell_id(cell[0], cell[2], cell[1])
    todo = [c for c in cells if cell_name(c) not in done]
    calls = 0

    def one(cell):
        task, rep, arm = cell
        try:
            return cell, execute(config, task, arm, rep, out, timeout_s)
        except Exception as error:  # one cell's failure (a refused snapshot, a crash) is an invalid cell, never the whole run
            return cell, _controller_failure(out, task, arm, rep, error)
    with ThreadPoolExecutor(jobs) as pool_:
        active, queue = set(), iter(todo)
        while True:
            while not stop and len(active) < jobs:
                if calls >= max_calls:
                    stop = stop or ("call-budget" if next(queue, None) else None)
                    break
                try:
                    reserved = harness_report._money_sum((spent, stop_usd * (len(active) + 1)))
                except ValueError:
                    reserved = None
                if reserved is None or reserved > harness_report._money_sum((max_usd,)):
                    stop = "usd-budget"
                    break
                cell = next(queue, None)
                if cell is None:
                    break
                calls += 1
                with ledger.open("a") as handle:
                    handle.write(json.dumps({"cell": cell_name(cell), "dispatched_at": _now(), "manifest_sha256": sealed_digest}) + "\n")
                active.add(pool_.submit(one, cell))
            if not active:
                break
            finished, active = wait(active, return_when=FIRST_COMPLETED)
            for future in finished:
                cell, row = future.result()
                cid = cell_name(cell)
                cost = cost_of(out, cid, row)
                with lock, ledger.open("a") as handle:
                    handle.write(json.dumps({"cell": cid, "finished_at": _now(), "cost_usd": cost, "valid": row.get("valid")}) + "\n")
                invalid += row.get("valid") is not True
                if cost is None and row.get("valid") is True:
                    stop = "cost-unavailable"
                else:
                    charge(cost)  # A failed call with no receipt cost is charged its reserve.
                    if cost is not None and cost > stop_usd:
                        stop = "cell-over-limit"
                if invalid >= max_invalid:
                    stop = "invalid-budget"
    if stop and stop != "call-budget":  # a call budget is a planned pause: the next stage resumes it
        (out / "STOP.json").write_text(json.dumps({"stop": stop, "at": _now(), "spent": spent, "calls": calls}))
    return {"stop": stop, "calls": calls, "spent": spent, "invalid": invalid, "cells": len(cells)}


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


def whole_loss_draws(rows, task_dir, low, ref, seed, margin, reach=None, attempts=None):
    """GATES["draws"] sets of per-task differences in which `low` truly loses `margin` as whole failed attempts. Each task's cells of
    both arms are pooled (no difference), each arm is redrawn at its observed cell count, and a drawn `low` cell fails every
    reachable test with the probability that makes the expected loss exactly `margin`. None when there are too few tasks or too
    little passing to take `margin` away. `attempts` redraws every task at that many attempts per arm instead, to fix a critical
    value for a planned run from earlier attempts."""
    pools = {}
    for task, cells in reach_rates(rows, task_dir, reach).items():
        nx, ny = sum(c["arm"] == low for c, _ in cells), sum(c["arm"] == ref for c, _ in cells)
        if nx and ny:
            pools[task] = ([v for c, v in cells if c["arm"] in (low, ref)], attempts or nx, attempts or ny)
    level = statistics.mean(sum(p) / len(p) for p, _, _ in pools.values()) if pools else 0.0
    if len(pools) < GATES["min_signal_tasks"] or margin > level:
        return None
    q, rng = margin / level, random.Random(seed)
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


def proven_critical(rows, task_dir, low, ref, seed, margin=None, reach=None, attempts=None):
    """The critical value PROVEN must beat: the upper GATES["false_proven"] point of `studentized` when `low` truly loses `margin` in
    whole failed attempts, simulated from the run's own cells. In go-json simulations at 3 points it kept that loss under 1 % PROVEN
    at two attempts per arm and at 2.6-2.8 % with about eight, where the t interval reached 5.6 % and 3.4 %: the loss it guards
    against puts failures into the pooled cells and lowers the value. Those rates hold for the scenarios simulated, with the reach
    set taken as given: a confirmatory run should freeze `reach` beforehand. A planned run can take the larger of this and a value
    fixed beforehand from earlier attempts (`attempts`), which held 2.4 % in simulation."""
    margin = GATES["reachable_margin"] if margin is None else margin
    draws = whole_loss_draws(rows, task_dir, low, ref, seed, margin, reach, attempts)
    if draws is None:
        return None
    values = sorted(studentized(d, margin) for d in draws)
    return values[min(len(values) - 1, int((1 - GATES["false_proven"]) * len(values)))]


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


def feasibility(config_path, results, margin=None, sd=None):
    """Before spending: with the noise of a pilot (or a stated per-task SD), how many tasks does a verdict need, and what does the
    current number of tasks buy? A run that cannot reach a verdict should not be paid for."""
    config = json.loads(config_path.read_text())
    margin = declared_margin(config) if margin is None else margin
    low, ref = config["compare"]["candidate"], config["compare"]["reference"]
    observed = reach = None
    if results is not None:
        rows = [r for r in load_cells(results) if r["valid"] is True]
        observed = paired_interval(reachable_diffs(rows, config_path.parent / "tasks", low, ref))
        both = {r["task"] for r in rows if r["arm"] == low} & {r["task"] for r in rows if r["arm"] == ref}
        # only tasks that reach new behaviour enter the verdict (41 of 62 on go-json); ponytail: measured at the pilot's
        # replicates, more attempts can reach more tasks
        reach = observed["tasks"] / len(both) if both else None
        sd = observed["sd"] if sd is None else sd
    if not sd:  # a pilot whose tasks all agree has no spread to plan with
        raise ValueError("feasibility needs a positive SD from pilot results or --sd")
    planned = len(config["tasks"])
    counted = planned * reach if reach is not None else planned  # without a pilot, every planned task is assumed to reach
    half = 1.96 * sd / math.sqrt(counted) if counted else None
    power = statistics.NormalDist().cdf(margin / (sd / math.sqrt(counted)) - 1.96) if counted else 0.0
    needed = tasks_needed(sd, margin)
    return {"margin": margin, "sd": sd, "planned_tasks": planned, "reach_share": reach, "planned_reaching": counted,
            "planned_halfwidth": half, "power_proven_if_equal": power, "tasks_needed_if_equal": needed,
            "tasks_to_mine_if_equal": math.ceil(needed / reach) if reach and needed is not None else None, "pilot": observed,
            "tasks_needed_at_pilot_mean": tasks_needed(sd, margin, observed["mean"]) if observed and observed["mean"] is not None else None}


def sufficiency(config_path, results, threshold, out):
    """Specification floor filter: keep a task only if a calibration cell built from the prompt alone (cheap model, other family)
    passes at least `threshold` of the behaviour the commit introduced (hidden tests minus the baseline green at base, so an empty
    patch never qualifies). It keeps tasks a cheap executor can already reach, which pulls a later verdict toward "equal": a
    sizing aid for pilots, not for confirmatory sets."""
    config = json.loads(config_path.read_text())
    rows = [r for r in load_cells(results) if r["valid"] is True]
    kept, dropped = [], []
    for task in config["tasks"]:
        directory = config_path.parent / "tasks" / task["id"]
        baseline = set(json.loads((directory / "baseline.json").read_text()))
        hidden = [k for k in json.loads((directory / "hidden.json").read_text()) if k != "__module__" and k not in baseline]
        cells = [r for r in rows if r["task"] == task["id"]]
        share = max((sum(c["acceptance_outcomes"].get(k) == "pass" for k in hidden) / len(hidden) for c in cells if hidden), default=None)
        (kept if share is not None and share >= threshold else dropped).append((task["id"], share))
    keep = {t for t, _ in kept}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**config, "tasks": [t for t in config["tasks"] if t["id"] in keep]}, indent=1, ensure_ascii=False))
    if out.parent != config_path.parent:  # report() reads tasks/ and sensitivity.json next to the set
        for name in ("tasks", "sensitivity.json"):
            if not (out.parent / name).exists() and (config_path.parent / name).exists():
                (out.parent / name).symlink_to(config_path.parent / name)
    return {"threshold": threshold, "kept": kept, "dropped": dropped}


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
                      "accepted": sum(r.get("valid") is True and bool(r.get("accepted")) for r in done), "invalid": dict(sorted(invalid.items()))}
    return {"history": status, "ledger_invalid_lines": bad, "ledger_ambiguous_cells": ambiguous, "unread_cells": sum(d is None for d in decoded),
            "arms": table}


def report(config_path, results, next_results):
    config = json.loads(config_path.read_text())
    low, ref = config["compare"]["candidate"], config["compare"]["reference"]
    manifest = sealed_state(config, results)
    rows = load_cells(results)
    # an orphan receipt (an attempt with no result) may have spent: named in the report, never silently dropped
    _, receipts = replay_eval.read_cell_artifacts(results)
    accounting = arm_accounting(config, results, rows, receipts)
    orphans = sorted(set(receipts) - {r["cell"] for r in rows})
    excluded = sorted(r["cell"] for r in rows if r["valid"] is not True)
    rows = [r for r in rows if r["valid"] is True]
    if not rows:
        raise ValueError(f"no valid cells to report ({len(excluded)} invalid, {len(orphans)} orphan receipts)")
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
    reasoning = {a: statistics.median(r["usage"]["reasoning_output_tokens"] for r in rows if r["arm"] == a) for a in (low, ref)}
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
    diffs = reachable_diffs(rows, task_dir, low, ref)
    reachable = paired_interval(diffs)
    critical = proven_critical(rows, task_dir, low, ref, config["seed"], margin)
    tier["margin"] = margin
    tier["compare_changed_after_seal"] = manifest["compare_changed"]
    tier["run_binding"] = manifest["state"]
    tier["next_run_binding"] = stage2["state"] if stage2 else None
    tier["same_change_reachable"] = behaviour_verdict(reachable, sensitive, margin, critical=math.inf if critical is None else critical)
    proof = {"critical": critical, "statistic": studentized(diffs, margin) if len(diffs) > 1 else None,
             "t975": t975(len(diffs) - 1) if len(diffs) > 1 else None, "t_false_proven": false_proven(rows, task_dir, low, ref, config["seed"], margin)}
    if tier["same_change_reachable"] == "KILL":
        tier["thesis"] = "KILLED"
    elif tier["thesis"] == "HOLDS" and tier["same_change_reachable"] != "PROVEN":
        tier["thesis"] = "UNPROVEN"
    aa = {a: paired_interval(reachable_diffs(rows, task_dir, low, ref, split=a)) for a in (low, ref)}
    if stage2 is not None:
        stage2["stage1_cells_chained"] = sum(r["cell"] in next_rows for r in rows)
        stage2["stage1_cells"] = len(rows)
    result = {"schema": "007-lab/report/v6", "at": _now(), "run_manifest": manifest, "next_run_manifest": stage2, "arm_accounting": accounting, "verdict": tier, "excluded_invalid": excluded, "orphan_receipts": orphans,
              "unreadable_outcomes": sorted(r["cell"] for r in rows if r.get("outcomes_unreadable")), "unseen_behaviour": behaviour,
              "reachable_behaviour": reachable, "proven_critical": proof, "pseudo_aa": aa, "contrast": c, "bootstrap": ci, "split_tasks": split, "per_task": per_task,
              "sensitivity": sense, "median_reasoning_tokens": reasoning, "tasks_faster": [faster, len(tasks)], "gates": GATES}
    (results / "report.json").write_text(json.dumps(result, indent=1) + "\n")
    (results / "report.md").write_text(summary(result, low, ref, len(rows)))
    return result


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
        f"- **Waiting:** {saving} ({tier['time']}); median reasoning tokens {reasoning[low]:.0f} vs {reasoning[ref]:.0f}.",
        f"- **The same change, margin {margin:g} points:** {tier['same_change_reachable']}. {meaning}{interval}",
        f"- **Durable:** {tier['durability']}.",
        *([f"- **Run binding:** {binding}."] if binding else []),
        *[f"- **Cells, `{arm}`:** {a['planned']} planned, {a['not_dispatched']} never dispatched, {a['no_result']} attempted without a result, "
          f"{sum(a['invalid'].values())} invalid" + (f" ({', '.join(f'{k} {v}' for k, v in a['invalid'].items())})" if a['invalid'] else "")
          + f", {a['valid']} valid, {a['accepted']} accepted." for arm, a in (accounting or {}).get("arms", {}).items()],
        *([f"- **Dispatch ledger:** {accounting['history']}; the counts above may be incomplete."] if accounting and accounting["history"] != "complete" else []),
        *([f"- **Stage 2:** {result['next_run_manifest']['state']}; {result['next_run_manifest']['stage1_cells_chained']} of "
           f"{result['next_run_manifest']['stage1_cells']} valid stage-1 attempts have a valid stage-2 attempt; the others count as not durable."]
          if result.get("next_run_manifest") else []),
        "- **Not shown by this report:** served effort (the CLIs do not report it), invoiced cost (costs are estimates), commits, models or specification forms other than these.",
        f"- **Excluded:** {len(result['excluded_invalid'])} invalid attempts and {len(result.get('orphan_receipts', []))} orphan receipts, never retried.",
        "",
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(prog="007 lab", description="Headless effort replay for any repository and any agent")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, target in (("mine", "--config"), ("sensitivity", "--set"), ("run", "--set"), ("chain", "--set"), ("report", "--set")):
        sub = commands.add_parser(name)
        sub.add_argument(target, type=Path, required=True, dest="path")
        sub.add_argument("--out", type=Path, required=name in ("mine", "run", "chain"))
        sub.add_argument("--jobs", type=int, default=max(2, (os.cpu_count() or 4) // 3))
        if name == "run":
            sub.add_argument("--replicates", type=int, required=True)
            sub.add_argument("--max-calls", type=int, required=True)
            sub.add_argument("--max-usd", type=float, required=True)
            sub.add_argument("--stop-usd", type=float, default=5.0)
            sub.add_argument("--max-invalid", type=int, default=3, help="stop once this many cells are invalid (never retried)")
        if name in ("chain", "report"):
            sub.add_argument("--results", type=Path, required=True)
        if name == "report":
            sub.add_argument("--next-results", type=Path)
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
    args = parser.parse_args(argv)
    if args.command == "feasibility":
        results = args.results.expanduser().resolve() if args.results else None
        print(json.dumps(feasibility(args.path.expanduser().resolve(), results, args.margin, args.sd)))
        return 0
    if args.command == "sufficiency":
        print(json.dumps(sufficiency(args.path.expanduser().resolve(), args.results.expanduser().resolve(), args.threshold, args.out.expanduser().resolve())))
        return 0
    path = args.path.expanduser().resolve()
    out = args.out.expanduser().resolve() if args.out else None
    if args.command == "mine":
        print(json.dumps({"tasks": mine(json.loads(path.read_text()), out, args.jobs)}))
    elif args.command == "sensitivity":
        print(json.dumps(sensitivity(path, args.jobs)))
    elif args.command == "run":
        result = run(path, out, replicates=args.replicates, jobs=args.jobs, max_calls=args.max_calls, max_usd=args.max_usd, stop_usd=args.stop_usd, max_invalid=args.max_invalid)
        print(json.dumps(result))
        return 2 if result.get("stop") else 0
    elif args.command == "chain":
        print(json.dumps(chain(path, args.results.expanduser().resolve(), out)))
    else:
        print(json.dumps(report(path, args.results.expanduser().resolve(), args.next_results.expanduser().resolve() if args.next_results else None)["verdict"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
