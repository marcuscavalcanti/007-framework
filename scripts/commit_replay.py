"""Trilha A (master plan 3.2): commit-replay calibration tasks from git history. Calibration/pilot only, never holdout.

The source repository is only read. The hidden oracle is the commit's own bytes of its changed tests, validated per test:
fail_to_pass must be non-empty. Results keep test ids and outcomes only, never test output.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tarfile
import tempfile

TEST = re.compile(r"(^|/)(tests?|__tests__|spec|specs)/|(^|/)test_[^/]+\.py$|_test\.(py|go)$|\.(test|spec)\.(c|m)?(j|t)sx?$|Tests?\.(java|kt|cs|swift)$")
SOURCE = re.compile(r"\.(py|(c|m)?(j|t)sx?|go|rs|java|kt|rb|php|swift|cs|c|cc|cpp|h|hpp|scala|sql)$")
MAX_PATHS = 10
GIT_ENV = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_OPTIONAL_LOCKS": "0", "LANG": "C"}
OUTCOMES = ("pass", "fail", "error", "skip")
# Per-test stdlib runner: writes only {test id: outcome}; test output goes to /dev/null with the process.
RUNNER = """import json, sys, unittest
outcomes = {}
class Result(unittest.TestResult):
    def addSuccess(self, test): outcomes[test.id()] = "pass"
    def addFailure(self, test, err): outcomes[test.id()] = "fail"
    def addError(self, test, err): outcomes[test.id()] = "error"
    def addSkip(self, test, reason): outcomes[test.id()] = "skip"
    def addExpectedFailure(self, test, err): outcomes[test.id()] = "skip"  # review R1: not a pass, consistent with BOOT
    def addUnexpectedSuccess(self, test): outcomes[test.id()] = "fail"
    def addSubTest(self, test, subtest, err):
        if err is not None: outcomes[test.id()] = "fail"
unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:]).run(Result())
with open(sys.argv[1], "w") as handle: json.dump(outcomes, handle)
"""


def _expect(value):
    if not value:
        raise ValueError("replay-invalid")


def _git(repo, *args, data=None):
    return subprocess.run(["git", "-c", "core.quotepath=false", "-C", str(repo), *args], input=data, capture_output=True,
                          env=GIT_ENV, timeout=120, check=True).stdout


def candidates(repo: Path) -> list[dict]:
    raw = _git(repo, "log", "--all", "--no-merges", "--reverse", "--topo-order", "-M", "--name-status", "--format=%x00%H %P")
    found = []
    for block in raw.decode().split("\0")[1:]:
        header, *lines = [line for line in block.split("\n") if line]
        commit, *parents = header.split()
        changes = [line.split("\t") for line in lines]
        paths = [change[-1] for change in changes]
        if len(parents) != 1 or len(paths) > MAX_PATHS or any(p.startswith('"') for p in paths):  # ponytail: quoted paths skipped
            continue
        tests = sorted(c[-1] for c in changes if TEST.search(c[-1]) or TEST.search(c[1]))
        removed = [c for c in changes if c[0][0] in "DR" and (TEST.search(c[1]) or TEST.search(c[-1]))]
        sources = sorted(p for p in paths if SOURCE.search(p) and not TEST.search(p))
        if tests and sources and not removed:
            found.append({"commit": commit, "parent": parents[0], "tests": tests, "sources": sources})
    return found


def materialize(repo: Path, rev: str, dest: Path) -> dict:
    dest = Path(dest)
    try:
        _expect(not dest.exists() and not dest.is_symlink())
        archive = _git(repo, "archive", "--format=tar", rev)
        dest.mkdir(mode=0o700)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(dest, filter="data")
        # export-ignore/export-subst would silently change the tree: every blob must match byte for byte
        listing = [line.split(None, 3) for line in _git(repo, "ls-tree", "-r", rev).decode().splitlines()]
        _expect(all(kind == "blob" and mode in ("100644", "100755", "120000") for mode, kind, _, _ in listing))  # no gitlinks
        blobs = {path: sha for mode, kind, sha, path in listing if mode in ("100644", "100755")}
        links = {path: sha for mode, kind, sha, path in listing if mode == "120000"}
        files = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file() and not p.is_symlink())
        _expect(files == sorted(blobs))
        # review R4: every tracked symlink must exist with its exact target (a dropped one fails readlink)
        _expect(all(os.readlink(dest / path).encode() == _git(repo, "cat-file", "blob", sha) for path, sha in links.items()))
        hashes = _git(repo, "hash-object", "--no-filters", "--stdin-paths",
                      data="".join(str(dest / f) + "\n" for f in files).encode()).decode().split()
        _expect(hashes == [blobs[f] for f in files])
        return {"rev": rev, "tree": _git(repo, "rev-parse", rev + "^{tree}").decode().strip()}
    except (OSError, subprocess.SubprocessError, tarfile.TarError, ValueError):
        raise ValueError("replay-invalid") from None


def _run(argv, cwd, env, timeout):
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        return None


# Acceptance for scripts/replay_eval.py: isolated interpreter (-I ignores PYTHONPATH/PYTHON* and the cwd, so a candidate's
# sitecustomize.py cannot run first), explicit sys.path, HOME/TMPDIR in a fresh temp dir OUTSIDE the acceptance copy (replay_eval makes
# that copy a git repo; temps inside it would sit in a work tree), removed at the end; output discarded, exit code only.
# ponytail: in-process forgery by the candidate (L3, spec 5b) is not prevented; recorded as gap oracle-in-process.
# r45: with ACCEPT_REPORT set, also writes {test id: outcome} there (never output; the exit code alone stays the verdict).
# Subtest outcomes count for their test; a fixture error keeps its own id, e.g. "setUpClass (m.C)"; later kinds win.
BOOT = """import json, os, shutil, sys, tempfile, unittest
report = os.environ.pop("ACCEPT_REPORT", None)
root = os.getcwd()
sys.path[:0] = [os.path.join(root, p) for p in {paths!r}]
home = tempfile.mkdtemp(prefix="007-eval-")
os.environ.update(HOME=home, TMPDIR=home, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
tempfile.tempdir = home
sys.stdout = sys.stderr = open(os.devnull, "w")
ran = []
class Result(unittest.TextTestResult):
    def startTest(self, test):
        ran.append(test.id())
        super().startTest(test)
result = unittest.TextTestRunner(stream=sys.stderr, verbosity=0, resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:]))
shutil.rmtree(home, ignore_errors=True)
clean = not (result.errors or result.failures or result.skipped or result.expectedFailures or result.unexpectedSuccesses)
if report:
    outcomes = dict.fromkeys(ran, "pass")
    for outcome, items in (("skip", result.skipped), ("expected-failure", result.expectedFailures),
                           ("unexpected-success", [(t,) for t in result.unexpectedSuccesses]),
                           ("fail", result.failures), ("error", result.errors)):
        for test, *_ in items:
            outcomes[getattr(test, "test_case", test).id()] = outcome
    try:
        with open(report, "w") as handle:
            json.dump(outcomes, handle)
    except OSError:
        pass
os._exit(0 if clean and result.testsRun == len(sys.argv) - 1 else 1)  # review R1: skips and fixture errors are not passes
"""


def replay_tasks(repo: Path, rows: list[dict], *, repo_key: str, oracle_dir: Path, python: str, python_paths: list[str]) -> list[dict]:
    """Validated rows -> scripts/replay_eval.py tasks; oracle bytes written once under oracle_dir and bound by sha256."""
    oracle_dir = Path(oracle_dir)
    try:
        _expect(rows and all(row["status"] == "valid" for row in rows) and not oracle_dir.exists() and not oracle_dir.is_symlink())
        oracle_dir.mkdir(mode=0o700, parents=True)
        tasks = []
        for row in rows:
            task_id = f"{repo_key}-{row['commit'][:12]}"
            hidden = []
            for path in row["tests"]:
                _expect(not Path(path).is_absolute() and ".." not in Path(path).parts)
                data = _git(repo, "show", f"{row['commit']}:{path}")
                target = oracle_dir / task_id / path
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with open(target, "xb") as handle:
                    handle.write(data)
                hidden.append({"source": str(target.absolute()), "sha256": hashlib.sha256(data).hexdigest(), "target": path})
            tasks.append({"id": task_id, "repo": repo_key, "base": row["parent"], "accepted": row["commit"],
                          "prompt": row["statement"]["text"], "hidden_acceptance": hidden,
                          "acceptance": [[python, "-I", "-c", BOOT.format(paths=list(python_paths)),
                                          *sorted(row["fail_to_pass"] + row["pass_to_pass"])]]})
        return tasks
    except (OSError, KeyError, TypeError, subprocess.SubprocessError, ValueError):
        raise ValueError("replay-invalid") from None


def unittest_command(python):
    return lambda paths, report: [python, "-c", RUNNER, report, *(Path(p).stem for p in paths if p.endswith(".py"))]


def _report(path):
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    ok = isinstance(value, dict) and all(isinstance(k, str) and v in OUTCOMES for k, v in value.items())
    return value if ok else None


def validate(repo: Path, task: dict, *, command, env: dict, timeout: float) -> dict:
    """command(test_paths, report_path) -> argv that writes {test id: outcome} to report_path."""
    reports = []
    with tempfile.TemporaryDirectory() as scratch:
        parent, commit = Path(scratch, "parent"), Path(scratch, "commit")
        materialize(repo, task["parent"], parent)
        for path in task["tests"]:  # the hidden oracle, applied onto the parent
            _expect(not Path(path).is_absolute() and ".." not in Path(path).parts)
            (parent / path).parent.mkdir(parents=True, exist_ok=True)
            (parent / path).write_bytes(_git(repo, "show", f"{task['commit']}:{path}"))
        materialize(repo, task["commit"], commit)
        for tree in (parent, commit):
            report = Path(scratch, tree.name + ".json")
            home = Path(scratch, tree.name + "-home")  # review R3: historical tests never resolve the real account home
            home.mkdir()
            run_env = {**env, "HOME": str(home), "TMPDIR": str(home)}
            if _run(command(task["tests"], str(report)), tree, run_env, timeout) is None:
                return {"status": "timeout", "fail_to_pass": [], "pass_to_pass": [], "excluded": []}
            reports.append(_report(report))
    before, after = reports
    if before is None or after is None:
        return {"status": "report-missing", "fail_to_pass": [], "pass_to_pass": [], "excluded": []}
    if any(outcome != "pass" and " (" in t for t, outcome in after.items()):  # fixture error or skip, e.g. "tearDownClass (m.C)" (R1)
        return {"status": "fixture-error", "fail_to_pass": [], "pass_to_pass": [], "excluded": []}
    passing = sorted(t for t, outcome in after.items() if outcome == "pass")
    fail_to_pass = [t for t in passing if before.get(t) != "pass"]  # absent on the parent counts as not passing
    return {"status": "valid" if fail_to_pass else "no-fail-to-pass", "fail_to_pass": fail_to_pass,
            "pass_to_pass": [t for t in passing if before.get(t) == "pass"],
            "excluded": sorted(t for t, outcome in after.items() if outcome in ("fail", "error"))}


def statement(repo: Path, task: dict) -> dict:
    """Task text = the commit message; flags only, never rewritten (no model)."""
    text = _git(repo, "log", "-1", "--format=%B", task["commit"]).decode().strip()
    diff = _git(repo, "diff", "--no-color", "--no-ext-diff", "--no-textconv", task["parent"], task["commit"]).decode()
    added = {line[1:].strip() for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")}
    words = len(text.split())
    flags = (["underspecified"] if words < 8 else []) + (["leak"] if any(len(a) >= 20 and a in text for a in added) else [])
    return {"text": text, "words": words, "flags": flags}
