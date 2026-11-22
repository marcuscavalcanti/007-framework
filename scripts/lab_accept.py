"""Per-test acceptance for `007 lab`. Stdlib only: it is copied into each candidate tree and runs inside the acceptance sandbox.

Accepted = every hidden test passes and no baseline test regresses (key "__module__"). A test whose class, module or package
fails outside any test reads "error", not "pass". No test output is kept. Exit 0 accepted, 1 rejected, 2 the grader failed,
3 a suite command did not finish in time (a rejection: the candidate's code hung; no report is written). A suite's own result
file that cannot be read (cut short by a crash) grades as no result: a rejection, or exit 2 under --collect.
Usage: lab_accept.py --collect lab.json | lab_accept.py lab.json hidden.json baseline.json   (ACCEPT_REPORT names the report; optional when grading)
"""
import contextlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ElementTree

TIMEOUT_S = 800  # one suite command
GRADE_S = 860  # every command of one grade together: a cell allows 900 s, so start-up and teardown keep 40 s and exit 3 shows
GRACE_S = 1.0  # past a deadline, a suite that already exited has its waiting output drained this long, so it is not read as hung
MAX_STDOUT = 64 << 20  # only `go test -json` keeps stdout, in one buffer; past this the run proves no pass (peak RAM a few times this)
MAX_REPORT = 64 << 20  # a suite's own result file past this proves nothing, as a cut one
_grade_deadline = None  # set by _main for the whole grade; _run alone (tests) uses TIMEOUT_S only
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


class SuiteTimeout(Exception):
    """A suite command did not finish by TIMEOUT_S. The candidate's code hung: a rejection (exit 3), not a grader failure."""


class ReportUnreadable(Exception):
    """The suite's own result file (or `go test -json` stream) is cut or malformed: the run proves no outcome. Grading reads it as
    no result, a rejection; --collect fails (exit 2), so `mine` drops the commit instead of keeping an empty baseline. Also raised
    when the candidate's tree makes a command impossible to start (its directory or an in-tree executable gone)."""


def _spawn(argv, cwd, env):
    """Popen; a start failure the candidate's tree caused (cwd gone, an in-tree relative executable gone or not executable) is
    no result, a rejection. A missing toolchain on PATH or an absolute path stays a grader failure (exit 2): reading it as a
    rejection would reject every candidate, the 0/124 failure."""
    try:
        return subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        first = str(argv[0]) if argv else ""
        if not Path(cwd).is_dir() or ("/" in first and not first.startswith("/")):
            raise ReportUnreadable(f"start {Path(first).name}") from None
        raise


def _run(argv, cwd, env, *, keep_stdout=False):
    """`subprocess.run(capture_output=True, timeout=TIMEOUT_S)` with the same end: both pipes closed by every holder, then the
    child's exit, so a helper the suite leaves holding its output is waited for until the deadline, as in 1.10.0. Two changes:
    output is read and dropped on arrival, except stdout with `keep_stdout`, kept in one buffer up to MAX_STDOUT, so a suite
    that prints without end cannot exhaust memory; the deadline is wall time on a monotonic clock, polled in slices of at most
    one second, so it also expires while the grader itself is stopped and continued. A grade's commands also share
    `_grade_deadline`. The suite stays in the grader's process group on purpose: `replay_eval.run` kills that whole session
    when the grader returns, descendants of `go test` and `node --test` included. POSIX only (`select.poll`), as the suite
    environment already was."""
    process = _spawn(argv, cwd, env)
    deadline = time.monotonic() + TIMEOUT_S  # from the start of the child, as subprocess.run's timeout
    if _grade_deadline is not None:
        deadline = min(deadline, _grade_deadline)
    out_fd, kept, truncated = process.stdout.fileno(), bytearray(), False
    streams = {process.stdout.fileno(): process.stdout, process.stderr.fileno(): process.stderr}
    try:
        poller = select.poll()
        for fd in streams:
            poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
        drain_until = None
        while streams:
            now = time.monotonic()
            if now >= deadline and drain_until is None:
                if process.poll() is None:  # still running at its deadline: hung
                    raise SuiteTimeout(argv[0])
                drain_until = now + GRACE_S  # it finished (the grader was stopped or busy): read what is waiting, briefly
            if drain_until is not None and now >= drain_until:
                raise SuiteTimeout(argv[0])  # a helper still holds the output past the deadline, as in 1.10.0
            events = poller.poll(max(min((drain_until or deadline) - now, 1.0), 0) * 1000)
            for fd, _ in events:
                chunk = os.read(fd, 1 << 16)
                if not chunk:
                    poller.unregister(fd)
                    streams.pop(fd).close()
                elif fd == out_fd and keep_stdout and not truncated:
                    room = MAX_STDOUT - len(kept)
                    kept += chunk[:room]
                    truncated = len(chunk) > room
        try:
            returncode = process.wait(timeout=max(deadline - time.monotonic(), 0.05))
        except subprocess.TimeoutExpired:
            raise SuiteTimeout(argv[0]) from None
    except BaseException:
        process.kill()
        process.wait()
        raise
    finally:
        for stream in streams.values():
            stream.close()
    result = subprocess.CompletedProcess(argv, returncode, kept, b"")
    result.stdout_truncated = truncated
    return result


def _lines(data):
    """The lines of `data`, one at a time: a list of millions of short lines would cost far more than the bytes."""
    start = 0
    while start < len(data):
        end = data.find(b"\n", start)
        end = len(data) if end < 0 else end
        yield data[start:end]
        start = end + 1


def _read(path, adapter):
    """A suite's own result file as text, or None when absent. Past MAX_REPORT, or unreadable, it proves nothing; bytes cut
    inside a character decode with a replacement, so the cut shows up as malformed content, not as a grader crash."""
    try:
        if not path.exists():
            return None
        if path.stat().st_size > MAX_REPORT:
            raise ReportUnreadable(adapter)
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        raise ReportUnreadable(adapter) from None


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
    text = _read(events, "node") or ""
    clean = lambda value: value.replace(prefix, "").replace(str(root) + "/", "")
    for line in text.split("\n"):  # JSON.stringify leaves U+2028, U+2029 and U+0085 raw: only "\n" ends a record
        if not line:
            continue
        try:  # a cut stream (the runner died mid-write) or a record of the wrong shape proves nothing
            e = json.loads(line)
            _worst(final, f"{clean(e.get('f') or '?')} :: {e['d']} :: {clean(e['n'])}", e["o"])
            if e.get("b"):
                broken.add(f"{clean(e.get('f') or '?')} :: ")
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ReportUnreadable("node") from None
    return _process_status(_charge(final, broken), result)


def unittest_(root, cwd, config, env, scratch):
    report = scratch / "unittest.json"
    pattern = Path(config["tests"]).name
    result = _run([sys.executable, "-B", "-c", UNITTEST_RUNNER, str(report), str(root), str(Path(config["tests"]).parent), pattern], cwd, env)
    text = _read(report, "unittest")
    try:
        out, broken = json.loads(text) if text is not None else ({}, [])
        if not isinstance(out, dict) or not all(isinstance(b, str) for b in broken):
            raise TypeError
    except (ValueError, TypeError):
        raise ReportUnreadable("unittest") from None
    return _process_status(_charge(out, broken), result, failure_exit=None)  # this child normally exits 0 even for red tests


def pytest(root, cwd, config, env, scratch):
    report = scratch / "junit.xml"
    result = _run([sys.executable, "-m", "pytest", "-q", "-o", "junit_family=xunit1", f"--junitxml={report}", config["tests"]], cwd, env)
    final = {}
    text = _read(report, "pytest")
    try:
        cases = list(ElementTree.fromstring(text).iter("testcase")) if text is not None else []
    except ElementTree.ParseError:
        raise ReportUnreadable("pytest") from None
    for case in cases:
        bad = case.find("failure") is not None or case.find("error") is not None
        _worst(final, f"{case.get('file', '?')} :: 0 :: {case.get('classname')}.{case.get('name')}", "fail" if bad else "skip" if case.find("skipped") is not None else "pass")
    return _process_status(final, result)


def go(root, cwd, config, env, scratch):
    result = _run([shutil.which("go", path=env["PATH"]), "test", "-json", config["tests"]], cwd, env, keep_stdout=True)
    if getattr(result, "stdout_truncated", False):  # events past the cap are lost: no pass in this run is proven
        raise ReportUnreadable("go")
    final, failed, red, unexplained, seen, completed, active = {}, set(), set(), set(), set(), set(), set()
    for line in _lines(result.stdout):
        try:
            e = json.loads(line.decode(errors="replace"))
        except ValueError:
            continue
        if not isinstance(e, dict):
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
    text = _read(raw, "custom")
    try:
        final = json.loads(text) if text is not None else {}
    except ValueError:
        raise ReportUnreadable("custom") from None
    if not isinstance(final, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in final.items()):
        raise ReportUnreadable("custom")
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


def _main(argv, report):
    global _grade_deadline
    _grade_deadline = time.monotonic() + GRADE_S
    root, collect = Path.cwd(), argv[0] == "--collect"
    config = json.loads(Path(argv[1 if collect else 0]).read_text())
    try:
        final = suite(root, config, report.parent / "lab")
    except ReportUnreadable as unreadable:
        if collect:
            raise  # exit 2: a baseline is never collected from a run that proves nothing
        print(f"lab_accept: {unreadable} result unreadable, graded as no result", file=sys.stderr)
        hidden, _ = (json.loads(Path(p).read_text()) for p in argv[1:3])
        report.write_text(json.dumps({**{name: "error" for name in hidden}, "__module__": "fail"}, sort_keys=True))
        return 1  # a rejection even when nothing is hidden: no grade was made
    if collect:
        report.write_text(json.dumps(final))
        return 0
    hidden, baseline = (json.loads(Path(p).read_text()) for p in argv[1:3])
    result = {name: final.get(name, "error") for name in hidden}
    result["__module__"] = "fail" if any(final.get(name) != "pass" for name in baseline) else "pass"
    report.write_text(json.dumps(result, sort_keys=True))
    return 0 if all(v == "pass" for v in result.values()) else 1


def main(argv):
    """0 accepted, 1 rejected, 2 the grader itself failed, 3 a suite command did not finish (rejected, no report). Under the
    `lab-accept-v1` contract a replay cell reads 0, 1 and 3 as verdicts and any other exit as a harness error; without the
    contract it records any non-zero exit as not accepted, as before. `mine` reads 2 as a harness error."""
    try:
        return _grade(argv)
    except SuiteTimeout as timeout:  # the command's name only: its arguments can carry paths
        print(f"lab_accept: {Path(str(timeout)).name} did not finish within its deadline ({TIMEOUT_S} s per command,"
              f" {GRADE_S} s per grade)", file=sys.stderr)
        return 3


def _grade(argv):
    named = os.environ.get("ACCEPT_REPORT")
    if named:  # the lab's own path: no temporary directory, as in 1.9.0 (an exact environment may leave none writable)
        return _main(argv, Path(named))
    if argv[0] == "--collect":
        print("ACCEPT_REPORT is required with --collect: the report is its only output", file=sys.stderr)
        return 2
    # Grading without a report path still grades: the exit code alone is the verdict. A KeyError here left exit 1 on every
    # candidate, the reference included, and a caller read it as 124 rejections.
    with tempfile.TemporaryDirectory(prefix="lab-accept-") as spare:
        return _main(argv, Path(spare) / "report.json")


if __name__ == "__main__":
    try:
        code = main(sys.argv[1:])
    except Exception as error:  # the type and two frames only: a message can carry test output
        code = 2  # set first: a failure while describing the error must not turn into exit 1, which is a verdict
        with contextlib.suppress(Exception):
            frames = traceback.StackSummary.extract(traceback.walk_tb(error.__traceback__), lookup_lines=False)  # no source read
            mine = [f for f in frames if Path(f.filename).name == Path(__file__).name] or frames
            where = "; ".join(dict.fromkeys(f"{Path(f.filename).name}:{f.lineno} in {f.name}" for f in (mine[-1], frames[-1])))
            print(f"lab_accept: {type(error).__name__} at {where}", file=sys.stderr)
    raise SystemExit(code)
