"""Per-test acceptance for `007 lab`. Stdlib only: it is copied into each candidate tree and runs inside the acceptance sandbox.

Accepted = every hidden test passes and no baseline test regresses (key "__module__"). A test whose class, module or package
fails outside any test reads "error", not "pass". No test output is kept.
Usage: lab_accept.py --collect lab.json | lab_accept.py lab.json hidden.json baseline.json   (ACCEPT_REPORT names the report)
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ElementTree

TIMEOUT_S = 800
NODE_REPORTER = """export default async function* (source) {
  for await (const e of source) {
    if (e.type !== 'test:pass' && e.type !== 'test:fail') continue;
    const d = e.data;
    const outcome = e.type === 'test:fail' ? 'fail' : d.skip !== undefined || d.todo !== undefined ? 'skip' : 'pass';
    const error = d.details?.error;
    const broken = error && (error.exitCode !== undefined || error.signal !== undefined || error.failureType === 'hookFailed');
    yield JSON.stringify({ o: outcome, f: d.file, n: d.name, d: d.nesting, b: !!broken }) + '\\n';
  }
}
"""
UNITTEST_RUNNER = """import json, os, sys, unittest
out, broken = {}, []
def where(module):
    return os.path.relpath(getattr(module, "__file__", "?") or "?", sys.argv[2])
def key(test):
    return f"{where(sys.modules.get(type(test).__module__))} :: 0 :: {type(test).__name__}.{getattr(test, '_testMethodName', str(test))}"
def scope(holder):  # "tearDownClass (pkg.mod.Case)" or "setUpModule (pkg.mod)" -> the key prefix of the tests it covers; "" = all
    names = holder.description.rpartition(" (")[2].rstrip(")").split(".")
    for i in range(len(names), 0, -1):
        module = sys.modules.get(".".join(names[:i]))
        if module is not None:
            return f"{where(module)} :: 0 :: " + (names[-1] + "." if i < len(names) else "")
    return ""
class Result(unittest.TestResult):
    def addSuccess(self, test): out[key(test)] = "pass"
    def addFailure(self, test, err): out[key(test)] = "fail"
    def addError(self, test, err):
        if isinstance(test, unittest.TestCase): out[key(test)] = "fail"
        else: broken.append(scope(test))  # a class or module fixture failed outside any test
    def addSkip(self, test, reason): out[key(test)] = "skip"
    def addSubTest(self, test, subtest, err):
        if err is not None: out[key(test)] = "fail"
suite = unittest.defaultTestLoader.discover(sys.argv[3], pattern=sys.argv[4], top_level_dir=".")
suite.run(Result())
json.dump([out, broken], open(sys.argv[1], "w"))
"""


def _run(argv, cwd, env):
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=TIMEOUT_S)


def _worst(final, key, outcome):
    final[key] = "fail" if outcome == "fail" or final.get(key) == "fail" else outcome


def _charge(final, broken):
    """A pass inside a class, module or package that failed outside any of its tests is no pass. It reads "error", apart from a
    test's own "fail", so a test already red at base stays outside the grade. `broken` holds key prefixes; "" covers every test."""
    broken = tuple(broken)
    return {k: "error" if v == "pass" and k.startswith(broken) else v for k, v in final.items()}


def _process_status(final, result, *, failure_exit=1, explained=None):
    """A retained report cannot explain a crash. Only the adapter's normal test-failure exit may preserve partial grades."""
    if explained is None:
        explained = any(outcome in ("fail", "error") for outcome in final.values())
    if result.returncode and (result.returncode != failure_exit or not explained):
        return _charge(final, [""])
    return final


def node(root, cwd, config, env, scratch):
    reporter, events = scratch / "reporter.mjs", scratch / "events.jsonl"
    reporter.write_text(NODE_REPORTER)
    tests = sorted(str(p) for p in root.glob(config["tests"]))
    result = _run([shutil.which("node", path=env["PATH"]), "--test", "--test-concurrency=4", "--test-timeout=120000", f"--test-reporter={reporter}",
          f"--test-reporter-destination={events}", *tests], cwd, env)
    final, broken, prefix = {}, set(), str(root.resolve()) + "/"
    for line in events.read_text().splitlines() if events.exists() else []:
        e = json.loads(line)
        clean = lambda text: text.replace(prefix, "").replace(str(root) + "/", "")
        _worst(final, f"{clean(e.get('f') or '?')} :: {e['d']} :: {clean(e['n'])}", e["o"])
        if e.get("b"):
            broken.add(f"{clean(e.get('f') or '?')} :: ")
    return _process_status(_charge(final, broken), result)


def unittest_(root, cwd, config, env, scratch):
    report = scratch / "unittest.json"
    pattern = Path(config["tests"]).name
    result = _run([sys.executable, "-B", "-c", UNITTEST_RUNNER, str(report), str(root), str(Path(config["tests"]).parent), pattern], cwd, env)
    out, broken = json.loads(report.read_text()) if report.exists() else ({}, [])
    return _process_status(_charge(out, broken), result, failure_exit=None)  # this child normally exits 0 even for red tests


def pytest(root, cwd, config, env, scratch):
    report = scratch / "junit.xml"
    result = _run([sys.executable, "-m", "pytest", "-q", "-o", "junit_family=xunit1", f"--junitxml={report}", config["tests"]], cwd, env)
    final = {}
    if report.exists():
        for case in ElementTree.parse(report).getroot().iter("testcase"):
            bad = case.find("failure") is not None or case.find("error") is not None
            _worst(final, f"{case.get('file', '?')} :: 0 :: {case.get('classname')}.{case.get('name')}", "fail" if bad else "skip" if case.find("skipped") is not None else "pass")
    return _process_status(final, result)


def go(root, cwd, config, env, scratch):
    result = _run([shutil.which("go", path=env["PATH"]), "test", "-json", config["tests"]], cwd, env)
    final, failed, red, unexplained, seen, completed, active = {}, set(), set(), set(), set(), set(), set()
    for line in result.stdout.decode(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("Action") == "run" and e.get("Test"):
            seen.add(e["Package"])
            active.add((e["Package"], e["Test"]))
        if e.get("Action") == "output" and not e.get("Test"):
            text = e.get("Output", "").strip()
            if text not in ("", "FAIL", "PASS") and not text.startswith(("FAIL\t", "ok\t")):
                unexplained.add(e.get("Package"))
        if e.get("Action") not in ("pass", "fail", "skip"):
            continue
        if e.get("Test"):
            seen.add(e["Package"])
            active.discard((e["Package"], e["Test"]))
            _worst(final, f"{e['Package']} :: 0 :: {e['Test']}", e["Action"])
            if e["Action"] == "fail":
                red.add(e["Package"])
        else:
            completed.add(e["Package"])
            if e["Action"] == "fail":
                failed.add(e["Package"])
    # A package that failed while none of its tests did (TestMain's exit, a panic or fatal error outside a test, the timeout)
    # leaves its passes unproven; a test that never finished cannot be explained by another test already red at base.
    broken = (seen - completed) | (failed - red) | (failed & unexplained) | {package for package, _ in active}
    return _process_status(_charge(final, (f"{package} :: " for package in broken)), result,
                           explained=bool(failed))


def custom(root, cwd, config, env, scratch):
    """config["command"] writes {test id: pass|fail|skip} to $LAB_RAW_REPORT."""
    raw = scratch / "raw.json"
    result = _run(config["command"], cwd, {**env, "LAB_RAW_REPORT": str(raw)})
    final = json.loads(raw.read_text()) if raw.exists() else {}
    return _process_status(final, result)


ADAPTERS = {"node": node, "unittest": unittest_, "pytest": pytest, "go": go, "custom": custom}


def suite(root, config, scratch):
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "home").mkdir(exist_ok=True)
    (scratch / "tmp").mkdir(exist_ok=True)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(scratch / "home"), "TMPDIR": str(scratch / "tmp"), "LANG": "C", "CI": "1", "NODE_ENV": "test", **config.get("env", {})}
    for command in config.get("prepare", []):
        if _run(command, root, env).returncode:
            return {}  # no test result is admissible after failed preparation
    return ADAPTERS[config["adapter"]](root, root / config.get("cwd", "."), config, env, scratch)


def main(argv):
    root, report = Path.cwd(), Path(os.environ["ACCEPT_REPORT"])
    collect = argv[0] == "--collect"
    config = json.loads(Path(argv[1 if collect else 0]).read_text())
    final = suite(root, config, report.parent / "lab")
    if collect:
        report.write_text(json.dumps(final))
        return 0
    hidden, baseline = (json.loads(Path(p).read_text()) for p in argv[1:3])
    result = {name: final.get(name, "error") for name in hidden}
    result["__module__"] = "fail" if any(final.get(name) != "pass" for name in baseline) else "pass"
    report.write_text(json.dumps(result, sort_keys=True))
    return 0 if all(v == "pass" for v in result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
