"""lab_accept: a class, module or package that fails outside its tests must not grade as a pass (audit 2026-11-08, F01).

Before the fix, unittest's tearDownClass error and a `go test` package failure after every test passed were both accepted.
Controls: a clean suite, a test already red at base, and a failure in a scope no graded test lives in still grade as before.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lab_accept  # noqa: E402

CASES = """import unittest
class Kept(unittest.TestCase):
    def test_new(self): pass
    def test_old(self): pass
class KnownRed(unittest.TestCase):
    def test_red(self): self.fail("red at base too")
"""
NEW, OLD, RED = (f"test_fixture.py :: 0 :: {name}" for name in ("Kept.test_new", "Kept.test_old", "KnownRed.test_red"))


def accept(root, config, hidden, baseline):
    """lab_accept as the lab runs it, from `root`: (exit, report)."""
    for name, value in (("lab.json", config), ("hidden.json", hidden), ("baseline.json", baseline)):
        (root / name).write_text(json.dumps(value))
    report = root.parent / "report.json"
    proc = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts/lab_accept.py"), "lab.json", "hidden.json", "baseline.json"],
                          cwd=root, env={**os.environ, "ACCEPT_REPORT": str(report)}, capture_output=True, timeout=300)
    return proc.returncode, json.loads(report.read_text())


class Unittest(unittest.TestCase):
    def grade(self, source):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "tree"
            root.mkdir()
            (root / "test_fixture.py").write_text(source)
            return accept(root, {"adapter": "unittest", "tests": "test_*.py"}, [NEW], [OLD])

    def test_a_class_or_module_teardown_error_voids_the_passes_it_covers(self):
        class_error = CASES.replace("    def test_old(self): pass\n", "    def test_old(self): pass\n    @classmethod\n"
                                    "    def tearDownClass(cls): raise RuntimeError('class cleanup failed')\n")
        module_error = CASES + "def tearDownModule(): raise RuntimeError('module cleanup failed')\n"
        for name, source in (("class", class_error), ("module", module_error)):
            with self.subTest(scope=name):
                self.assertEqual(self.grade(source), (1, {NEW: "error", "__module__": "fail"}))

    def test_grading_without_a_report_path_still_grades(self):
        """Without ACCEPT_REPORT the grader died on a KeyError and left exit 1: a harness error read as a rejection of every
        candidate (public paired study, 2026-11-15: 0 of 124 accepted, the reference included)."""
        env = {k: v for k, v in os.environ.items() if k != "ACCEPT_REPORT"}
        for source, expected in ((CASES, 0), (CASES.replace("def test_new(self): pass", "def test_new(self): self.fail('red')"), 1)):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "test_fixture.py").write_text(source)
                for name, value in (("lab.json", {"adapter": "unittest", "tests": "test_*.py"}), ("hidden.json", [NEW]), ("baseline.json", [OLD])):
                    (root / name).write_text(json.dumps(value))
                proc = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts/lab_accept.py"), "lab.json", "hidden.json", "baseline.json"],
                                      cwd=root, env=env, capture_output=True, text=True, timeout=300)
                self.assertEqual((proc.returncode, "Traceback" in proc.stderr), (expected, False), proc.stderr[-300:])
        collect = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts/lab_accept.py"), "--collect", "lab.json"], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual((collect.returncode, "ACCEPT_REPORT is required" in collect.stderr), (2, True))

    def test_a_grader_failure_exits_2_and_is_not_a_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "lab.json").write_text("{not json")
            proc = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts/lab_accept.py"), "lab.json", "hidden.json", "baseline.json"],
                                  cwd=root, env={**os.environ, "ACCEPT_REPORT": str(root / "report.json")}, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        # the type, the deepest frame inside the grader and the innermost frame; never the message
        self.assertRegex(proc.stderr.strip(), r"^lab_accept: JSONDecodeError at lab_accept\.py:\d+ in _main; \w+\.py:\d+ in \w+$")

    def test_the_lab_path_needs_no_temporary_directory(self):
        """Review of 1.10.0, B1: with ACCEPT_REPORT set (every lab cell) the grader must not need a writable temp location."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "tree"
            root.mkdir()
            (root / "test_fixture.py").write_text(CASES)
            for name, value in (("lab.json", {"adapter": "unittest", "tests": "test_*.py"}), ("hidden.json", [NEW]), ("baseline.json", [OLD])):
                (root / name).write_text(json.dumps(value))
            cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.dict(os.environ, {"ACCEPT_REPORT": str(Path(temporary) / "report.json")}), \
                        mock.patch.object(lab_accept.tempfile, "TemporaryDirectory", side_effect=AssertionError("no temp dir on the lab path")):
                    self.assertEqual(lab_accept.main(["lab.json", "hidden.json", "baseline.json"]), 0)
            finally:
                os.chdir(cwd)

    def test_a_clean_suite_passes_and_a_test_red_at_base_stays_outside_the_grade(self):
        self.assertEqual(self.grade(CASES), (0, {NEW: "pass", "__module__": "pass"}))
        # The fixture of a class that holds no graded test fails: nothing graded depends on it.
        other = CASES + "    @classmethod\n    def tearDownClass(cls): raise RuntimeError('cleanup of a red class')\n"
        self.assertEqual(self.grade(other), (0, {NEW: "pass", "__module__": "pass"}))


class Go(unittest.TestCase):
    def grade(self, events, hidden, baseline, returncode=1):
        proc = subprocess.CompletedProcess(["go"], returncode, stdout="".join(json.dumps(e) + "\n" for e in events).encode(), stderr=b"")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, value in (("lab.json", {"adapter": "go", "tests": "./..."}), ("hidden.json", hidden), ("baseline.json", baseline)):
                (root / name).write_text(json.dumps(value))
            with mock.patch.object(lab_accept, "_run", return_value=proc), \
                    mock.patch.dict(os.environ, {"ACCEPT_REPORT": str(root / "report.json")}):
                status = lab_accept.main([str(root / n) for n in ("lab.json", "hidden.json", "baseline.json")])
            return status, json.loads((root / "report.json").read_text())

    def test_a_package_that_fails_while_every_test_passed_is_rejected(self):
        events = [{"Action": "pass", "Package": "ex", "Test": "TestNew"}, {"Action": "pass", "Package": "ex", "Test": "TestOld"},
                  {"Action": "fail", "Package": "ex"}]
        self.assertEqual(self.grade(events, ["ex :: 0 :: TestNew"], ["ex :: 0 :: TestOld"]),
                         (1, {"ex :: 0 :: TestNew": "error", "__module__": "fail"}))

    def test_a_red_test_owns_its_package_failure_and_other_packages_stay_apart(self):
        events = [{"Action": "pass", "Package": "ex", "Test": "TestNew"}, {"Action": "pass", "Package": "ex", "Test": "TestOld"},
                  {"Action": "fail", "Package": "ex", "Test": "TestRedAtBase"}, {"Action": "fail", "Package": "ex"},
                  {"Action": "pass", "Package": "ex/sub", "Test": "TestSub"}, {"Action": "pass", "Package": "ex/sub"},
                  {"Action": "fail", "Package": "e", "FailedBuild": "e"}]  # a package outside the grade that does not build
        self.assertEqual(self.grade(events, ["ex :: 0 :: TestNew", "ex/sub :: 0 :: TestSub"], ["ex :: 0 :: TestOld"]),
                         (0, {"ex :: 0 :: TestNew": "pass", "ex/sub :: 0 :: TestSub": "pass", "__module__": "pass"}))

    def test_a_known_red_does_not_hide_a_later_package_panic(self):
        events = [{"Action": "pass", "Package": "ex", "Test": "TestNew"},
                  {"Action": "fail", "Package": "ex", "Test": "TestRedAtBase"},
                  {"Action": "output", "Package": "ex", "Output": "panic: after tests\n"},
                  {"Action": "fail", "Package": "ex"}]
        self.assertEqual(self.grade(events, ["ex :: 0 :: TestNew"], []),
                         (1, {"ex :: 0 :: TestNew": "error", "__module__": "pass"}))

    def test_unattributed_package_diagnostic_is_conservatively_charged_even_with_known_red(self):
        events = [{"Action": "pass", "Package": "ex", "Test": "TestNew"},
                  {"Action": "fail", "Package": "ex", "Test": "TestRedAtBase"},
                  {"Action": "fail", "Package": "ex"}]
        self.assertEqual(self.grade(events, ["ex :: 0 :: TestNew"], []),
                         (0, {"ex :: 0 :: TestNew": "pass", "__module__": "pass"}))
        events.insert(-1, {"Action": "output", "Package": "ex", "Output": "ordinary diagnostic\n"})
        self.assertEqual(self.grade(events, ["ex :: 0 :: TestNew"], []),
                         (1, {"ex :: 0 :: TestNew": "error", "__module__": "pass"}))

    def test_unfinished_go_tests_invalidate_only_their_package_despite_known_red(self):
        events = [{"Action": "pass", "Package": "ex", "Test": "TestNew"},
                  {"Action": "fail", "Package": "ex", "Test": "TestRed"},
                  {"Action": "run", "Package": "ex", "Test": "TestHanging"},
                  {"Action": "pause", "Package": "ex", "Test": "TestHanging"},
                  {"Action": "cont", "Package": "ex", "Test": "TestHanging"},
                  {"Action": "output", "Package": "ex", "Test": "TestHanging", "Output": "panic: test timed out\n"},
                  {"Action": "fail", "Package": "ex"},
                  {"Action": "pass", "Package": "ex/sub", "Test": "TestOther"},
                  {"Action": "pass", "Package": "ex/sub"}]
        self.assertEqual(self.grade(events, ["ex :: 0 :: TestNew", "ex/sub :: 0 :: TestOther"], []),
                         (1, {"ex :: 0 :: TestNew": "error", "ex/sub :: 0 :: TestOther": "pass", "__module__": "pass"}))

    def test_completed_go_lifecycles_preserve_partial_grades(self):
        for terminal in ("pass", "fail", "skip"):
            with self.subTest(terminal=terminal):
                events = [{"Action": "run", "Package": "ex", "Test": "TestNew"},
                          {"Action": "pass", "Package": "ex", "Test": "TestNew"},
                          {"Action": "run", "Package": "ex", "Test": "TestRed"},
                          {"Action": "fail", "Package": "ex", "Test": "TestRed"},
                          {"Action": "run", "Package": "ex", "Test": "TestOther"},
                          {"Action": terminal, "Package": "ex", "Test": "TestOther"},
                          {"Action": "fail", "Package": "ex"}]
                self.assertEqual(self.grade(events, ["ex :: 0 :: TestNew"], []),
                                 (0, {"ex :: 0 :: TestNew": "pass", "__module__": "pass"}))

    def test_go_success_does_not_prove_an_unfinished_test_completed(self):
        events = [{"Action": "pass", "Package": "ex", "Test": "TestNew"},
                  {"Action": "run", "Package": "ex", "Test": "TestHanging"},
                  {"Action": "pass", "Package": "ex"}]
        self.assertEqual(self.grade(events, ["ex :: 0 :: TestNew"], [], returncode=0),
                         (1, {"ex :: 0 :: TestNew": "error", "__module__": "pass"}))

    def test_a_second_go_run_does_not_reuse_the_first_completion(self):
        events = [{"Action": "run", "Package": "ex", "Test": "TestNew"},
                  {"Action": "pass", "Package": "ex", "Test": "TestNew"},
                  {"Action": "fail", "Package": "ex", "Test": "TestRed"},
                  {"Action": "run", "Package": "ex", "Test": "TestNew"},
                  {"Action": "fail", "Package": "ex"}]
        self.assertEqual(self.grade(events, ["ex :: 0 :: TestNew"], []),
                         (1, {"ex :: 0 :: TestNew": "error", "__module__": "pass"}))

    @unittest.skipUnless(shutil.which("go"), "go is not installed")
    def test_real_go_known_red_and_hanging_test_cannot_accept_hidden_pass(self):
        cache = subprocess.run(["go", "env", "GOCACHE"], capture_output=True, text=True).stdout.strip()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "tree"; root.mkdir()
            (root / "go.mod").write_text("module ex\n\ngo 1.20\n")
            (root / "ex_test.go").write_text('package ex\nimport ("testing"; "time")\n'
                'func TestNew(t *testing.T) {}\nfunc TestRed(t *testing.T) { t.Fatal("known red") }\n'
                'func TestHanging(t *testing.T) { time.Sleep(time.Hour) }\n')
            status, report = accept(root, {"adapter": "go", "tests": "./...", "env": {
                "GOCACHE": cache, "GOFLAGS": "-count=1 -timeout=2s", "GOPROXY": "off", "GOTOOLCHAIN": "local"}},
                ["ex :: 0 :: TestNew"], [])
            self.assertEqual((status, report["ex :: 0 :: TestNew"]), (1, "error"))

    @unittest.skipUnless(shutil.which("go"), "go is not installed")
    def test_real_go_test_main_exit_after_passing_tests_is_rejected(self):
        cache = subprocess.run(["go", "env", "GOCACHE"], capture_output=True, text=True).stdout.strip()
        main = "func TestMain(m *testing.M) { m.Run(); os.Exit(1) }\n"
        for exit_after, expected in ((False, (0, "pass")), (True, (1, "error"))):
            with self.subTest(test_main=exit_after), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "tree"
                root.mkdir()
                (root / "go.mod").write_text("module ex\n\ngo 1.20\n")
                (root / "ex_test.go").write_text('package ex\n\nimport (\n\t"os"\n\t"testing"\n)\n\nvar _ = os.Exit\n\n'
                                                 "func TestNew(t *testing.T) {}\n" + (main if exit_after else ""))
                status, report = accept(root, {"adapter": "go", "tests": "./...", "env": {"GOCACHE": cache, "GOFLAGS": "-count=1"}},
                                        ["ex :: 0 :: TestNew"], [])
                self.assertEqual((status, report["ex :: 0 :: TestNew"]), expected)

    @unittest.skipUnless(shutil.which("go"), "go is not installed")
    def test_real_go_known_red_then_panic_does_not_leave_hidden_green(self):
        cache = subprocess.run(["go", "env", "GOCACHE"], capture_output=True, text=True).stdout.strip()
        for panic, expected in ((False, (0, "pass")), (True, (1, "error"))):
            with self.subTest(panic=panic), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "tree"
                root.mkdir()
                (root / "go.mod").write_text("module ex\n\ngo 1.20\n")
                tail = 'panic("after tests")' if panic else 'os.Exit(code)'
                (root / "ex_test.go").write_text('package ex\nimport ("testing"; "os")\nvar _ = os.Exit\n'
                    'func TestNew(t *testing.T) {}\nfunc TestRed(t *testing.T) { t.Fatal("known red") }\n'
                    'func TestMain(m *testing.M) { code := m.Run(); _ = code; ' + tail + ' }\n')
                status, report = accept(root, {"adapter": "go", "tests": "./...", "env": {"GOCACHE": cache, "GOFLAGS": "-count=1"}},
                                        ["ex :: 0 :: TestNew"], [])
                self.assertEqual((status, report["ex :: 0 :: TestNew"]), expected)


class ProcessExit(unittest.TestCase):
    def test_failed_preparation_does_not_reach_the_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(lab_accept, "_run", return_value=subprocess.CompletedProcess(["prepare"], 1)), \
                    mock.patch.dict(lab_accept.ADAPTERS, {"custom": mock.Mock(return_value={"new": "pass"})}):
                self.assertEqual(lab_accept.suite(root, {"adapter": "custom", "prepare": [["prepare"]]}, root / "scratch"), {})
                lab_accept.ADAPTERS["custom"].assert_not_called()

    def test_normal_failed_test_exit_preserves_partial_grades_but_crash_does_not(self):
        final = {"new": "pass", "known-red": "fail"}
        for code in (0, 1, 2, -9):
            with self.subTest(code=code):
                expected = "pass" if code in (0, 1) else "error"
                self.assertEqual(lab_accept._process_status(final, subprocess.CompletedProcess(["runner"], code)),
                                 {"new": expected, "known-red": "fail"})

    def test_each_adapter_rejects_passing_reports_after_unexplained_nonzero_exit(self):
        for adapter in ("node", "unittest", "pytest", "go"):
            with self.subTest(adapter=adapter), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); scratch = root / "scratch"; scratch.mkdir()
                def run(argv, cwd, env, **_):
                    stdout = b""
                    if adapter == "node":
                        (scratch / "events.jsonl").write_text(json.dumps({"f": "case.js", "d": 0, "n": "New", "o": "pass"}) + "\n")
                    elif adapter == "unittest":
                        (scratch / "unittest.json").write_text(json.dumps([{"case.py :: 0 :: New": "pass"}, []]))
                    elif adapter == "pytest":
                        (scratch / "junit.xml").write_text('<testsuite><testcase file="case.py" classname="Case" name="New"/></testsuite>')
                    else:
                        stdout = (json.dumps({"Action": "pass", "Package": "ex", "Test": "TestNew"}) + "\n").encode()
                    return subprocess.CompletedProcess(argv, 1, stdout=stdout, stderr=b"")
                with mock.patch.object(lab_accept, "_run", side_effect=run):
                    got = lab_accept.ADAPTERS[adapter](root, root, {"tests": "*"}, {"PATH": os.environ.get("PATH", "")}, scratch)
                self.assertTrue(got)
                self.assertEqual(set(got.values()), {"error"})

    def test_go_requires_a_completed_package_even_after_exit_zero(self):
        proc = subprocess.CompletedProcess(["go"], 0, stdout=(json.dumps(
            {"Action": "pass", "Package": "ex", "Test": "TestNew"}) + "\n").encode(), stderr=b"")
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(lab_accept, "_run", return_value=proc):
            root = Path(temporary)
            self.assertEqual(lab_accept.go(root, root, {"tests": "./..."}, {"PATH": os.environ.get("PATH", "")}, root),
                             {"ex :: 0 :: TestNew": "error"})

    def test_unittest_shutdown_failure_voids_a_report_that_contains_known_red(self):
        source = CASES + '\nimport atexit,os\natexit.register(lambda: os._exit(1))\n'
        self.assertEqual(Unittest().grade(source), (1, {NEW: "error", "__module__": "fail"}))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_node_file_exit_failure_cannot_leave_the_hidden_test_green(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "tree"; root.mkdir()
            (root / "case.test.cjs").write_text("const test=require('node:test'); test('New',()=>{}); process.on('exit',()=>{process.exitCode=1;});")
            status, report = accept(root, {"adapter": "node", "tests": "*.test.cjs"}, ["case.test.cjs :: 0 :: New"], [])
            self.assertEqual((status, report["case.test.cjs :: 0 :: New"]), (1, "error"))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_node_ordinary_known_red_preserves_other_test_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "tree"; root.mkdir()
            (root / "case.test.cjs").write_text("const test=require('node:test'); test('New',()=>{}); test('Red',()=>{throw Error('known red');});")
            status, report = accept(root, {"adapter": "node", "tests": "*.test.cjs"}, ["case.test.cjs :: 0 :: New"], [])
            self.assertEqual((status, report["case.test.cjs :: 0 :: New"]), (0, "pass"))


class Custom(unittest.TestCase):
    def test_report_then_fail_does_not_accept_unexplained_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = "import json,os,sys; json.dump({'new':'pass'},open(os.environ['LAB_RAW_REPORT'],'w')); sys.exit(1)"
            self.assertEqual(accept(root, {"adapter": "custom", "command": [sys.executable, "-c", source]}, ["new"], []),
                             (1, {"new": "error", "__module__": "pass"}))

    def test_an_explicit_red_test_preserves_partial_grades(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = "import json,os,sys; json.dump({'new':'pass','known-red':'fail'},open(os.environ['LAB_RAW_REPORT'],'w')); sys.exit(1)"
            self.assertEqual(accept(root, {"adapter": "custom", "command": [sys.executable, "-c", source]}, ["new"], []),
                             (0, {"new": "pass", "__module__": "pass"}))


class SuiteDeadline(unittest.TestCase):
    """1.10.1: a suite that does not finish is a rejection (exit 3), never a grader failure (exit 2), and never exhausts memory.
    `subprocess.run(capture_output=True, timeout=)` raised TimeoutExpired, which the grader turned into exit 2; under the
    `lab-accept-v1` contract exit 2 makes the cell invalid, so a candidate whose code hangs left the arm's denominator."""

    def run_child(self, source, timeout=1.5, cap=None, keep=False):
        patches = [mock.patch.object(lab_accept, "TIMEOUT_S", timeout)]
        if cap is not None:
            patches.append(mock.patch.object(lab_accept, "MAX_STDOUT", cap))
        with tempfile.TemporaryDirectory() as temporary, contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            started = time.monotonic()
            try:
                result = lab_accept._run([sys.executable, "-c", source], temporary, {"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                                         keep_stdout=keep)
            except lab_accept.SuiteTimeout:
                return "timeout", time.monotonic() - started
            return result, time.monotonic() - started

    def test_a_suite_that_never_returns_times_out(self):
        outcome, elapsed = self.run_child("import time\ntime.sleep(60)")
        self.assertEqual(outcome, "timeout")
        self.assertLess(elapsed, 10)

    def test_a_suite_that_stops_itself_still_times_out(self):
        """A stopped suite never ends on its own: the deadline still comes."""
        outcome, elapsed = self.run_child("import os, signal\nos.kill(os.getpid(), signal.SIGSTOP)")
        self.assertEqual(outcome, "timeout")
        self.assertLess(elapsed, 10)

    def test_a_helper_holding_the_output_is_waited_for_as_in_1_10_0(self):
        """1.10.0 read until every holder of the pipes closed them: a child that exits at once but leaves a helper with its
        output open was graded only when the deadline came. Accepting it at once changes when a suite counts as finished."""
        helper = "import subprocess, sys\nsubprocess.Popen([sys.executable, '-c', 'import time; time.sleep(4)'])\nprint('done')"
        outcome, elapsed = self.run_child(helper)
        self.assertEqual(outcome, "timeout")
        self.assertGreaterEqual(elapsed, 1.4)

    def test_output_that_never_stops_is_dropped_on_arrival(self):
        flood = "import sys\nchunk = b'x' * 65536\nwhile True:\n    sys.stdout.buffer.write(chunk); sys.stderr.buffer.write(chunk)"
        outcome, _ = self.run_child(flood, timeout=1.5, cap=1 << 20)
        self.assertEqual(outcome, "timeout")
        source = "import sys\nsys.stdout.write('y' * (3 << 20))\nsys.stderr.write('z' * (3 << 20))"
        short = self.run_child(source, cap=1 << 20, keep=True)[0]
        self.assertEqual((short.returncode, len(short.stdout), short.stdout_truncated, short.stderr), (0, 1 << 20, True, b""))
        dropped = self.run_child(source, cap=1 << 20)[0]  # only the Go adapter asks for stdout; the rest keep none
        self.assertEqual((dropped.returncode, len(dropped.stdout), dropped.stdout_truncated), (0, 0, False))

    def test_many_tiny_writes_are_kept_in_one_buffer(self):
        """Review 2026-11-22: a list of one bytes object per read cost ~50 bytes each, so 64 MiB in tiny reads took over 1 GiB."""
        result = self.run_child("import os\nfor _ in range(20000): os.write(1, b'{')", timeout=30, keep=True)[0]
        self.assertEqual((type(result.stdout), len(result.stdout)), (bytearray, 20000))
        self.assertEqual(list(lab_accept._lines(bytearray(b"a\n\nb"))), [b"a", b"", b"b"])

    def test_a_suite_that_finishes_keeps_its_output_and_code(self):
        result = self.run_child("import sys\nprint('ok')\nsys.exit(4)", keep=True)[0]
        self.assertEqual((result.returncode, result.stdout, result.stdout_truncated), (4, b"ok\n", False))

    @unittest.skipUnless(hasattr(__import__("signal"), "SIGSTOP"), "needs job-control signals")
    def test_a_grader_stopped_past_its_deadline_exits_3_once_continued(self):
        """Round 4 of the lost branch: the grader itself stopped across the deadline. A wait that slept the whole remaining time
        (select with the full timeout) could outlive the cell's own limit after SIGCONT; the deadline is re-read every second."""
        import signal
        # Review 2026-11-22 r2: deadline 5 s, stopped 6 s, prompt bound 1.5 s, so a wait that re-slept its whole original
        # timeout after SIGCONT (~5 s) fails; readiness comes from the suite itself, so the stop lands inside _run.
        with tempfile.TemporaryDirectory() as temporary:
            ready = Path(temporary) / "ready"
            suite = f"import pathlib, time; pathlib.Path({str(ready)!r}).write_text('1'); time.sleep(60)"
            source = ("import sys; sys.path.insert(0, sys.argv[1]); import lab_accept; lab_accept.TIMEOUT_S = 5\n"
                      "try: lab_accept._run([sys.executable, '-c', sys.argv[2]], '.', {})\n"
                      "except lab_accept.SuiteTimeout: raise SystemExit(3)\n")
            grader = subprocess.Popen([sys.executable, "-I", "-c", source, str(ROOT / "scripts"), suite],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            try:
                waited = time.monotonic()
                while not ready.exists():
                    self.assertLess(time.monotonic() - waited, 30, "the suite never started")
                    time.sleep(0.05)
                grader.send_signal(signal.SIGSTOP)
                time.sleep(6)  # stopped past its 5 s deadline
                grader.send_signal(signal.SIGCONT)
                continued = time.monotonic()
                self.assertEqual(grader.wait(timeout=15), 3)
                self.assertLess(time.monotonic() - continued, 1.5)
            finally:
                if grader.poll() is None:
                    grader.kill()
                    grader.wait()
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(grader.pid, signal.SIGKILL)  # the sleeping suite, left in the grader's group

    def test_a_helper_that_releases_the_pipes_in_time_grades_normally(self):
        helper = "import subprocess, sys\nsubprocess.Popen([sys.executable, '-c', 'import time; time.sleep(1)'])\nsys.exit(5)"
        result, elapsed = self.run_child(helper, timeout=10)
        self.assertEqual(result.returncode, 5)
        self.assertGreaterEqual(elapsed, 0.9)

    @unittest.skipUnless(hasattr(__import__("signal"), "SIGSTOP"), "needs job-control signals")
    def test_a_suite_that_finished_while_the_grader_was_stopped_is_not_hung(self):
        """r2 should-fix 3: the suite exits while the grader is stopped past its deadline; on SIGCONT its output is drained
        and its exit code kept, not read as a hung suite (exit 3)."""
        import signal
        with tempfile.TemporaryDirectory() as temporary:
            ready, go = Path(temporary) / "ready", Path(temporary) / "go"
            suite = (f"import pathlib, sys, time; pathlib.Path({str(ready)!r}).write_text('1')\n"
                     f"while not pathlib.Path({str(go)!r}).exists(): time.sleep(0.02)\n"
                     "print('done'); sys.exit(0)")
            source = ("import sys; sys.path.insert(0, sys.argv[1]); import lab_accept; lab_accept.TIMEOUT_S = 3\n"
                      "try: r = lab_accept._run([sys.executable, '-c', sys.argv[2]], '.', {}, keep_stdout=True)\n"
                      "except lab_accept.SuiteTimeout: raise SystemExit(3)\n"
                      "raise SystemExit(0 if (r.returncode, bytes(r.stdout)) == (0, b'done\\n') else 9)\n")
            grader = subprocess.Popen([sys.executable, "-I", "-c", source, str(ROOT / "scripts"), suite],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            try:
                waited = time.monotonic()
                while not ready.exists():
                    self.assertLess(time.monotonic() - waited, 30, "the suite never started")
                    time.sleep(0.05)
                grader.send_signal(signal.SIGSTOP)
                go.write_text("1")  # the suite finishes now, while the grader cannot read
                time.sleep(5)  # past the 3 s deadline
                grader.send_signal(signal.SIGCONT)
                self.assertEqual(grader.wait(timeout=15), 0)
            finally:
                if grader.poll() is None:
                    grader.kill()
                    grader.wait()

    def test_one_grade_shares_one_deadline(self):
        """r2 item 4: prepare and suite together stop at GRADE_S, so exit 3 is observable inside the cell's 900 s."""
        with mock.patch.object(lab_accept, "_grade_deadline", time.monotonic() + 1.0), \
                mock.patch.object(lab_accept, "TIMEOUT_S", 30), tempfile.TemporaryDirectory() as temporary:
            started = time.monotonic()
            with self.assertRaises(lab_accept.SuiteTimeout):
                lab_accept._run([sys.executable, "-c", "import time; time.sleep(30)"], temporary, {})
            self.assertLess(time.monotonic() - started, 5)

    def test_a_prepare_that_hangs_exits_3(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "tree"
            root.mkdir()
            config = {"adapter": "unittest", "tests": "test_*.py", "prepare": [[sys.executable, "-c", "import time; time.sleep(60)"]]}
            for name, value in (("lab.json", config), ("hidden.json", [NEW]), ("baseline.json", [])):
                (root / name).write_text(json.dumps(value))
            cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(lab_accept, "TIMEOUT_S", 1.5), \
                        mock.patch.dict(os.environ, {"ACCEPT_REPORT": str(Path(temporary) / "r.json")}), \
                        contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(lab_accept.main(["lab.json", "hidden.json", "baseline.json"]), 3)
            finally:
                os.chdir(cwd)

    def test_a_start_failure_from_the_candidate_tree_is_a_rejection_but_a_missing_toolchain_is_not(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(lab_accept.ReportUnreadable):  # the candidate deleted its own directory
                lab_accept._run([sys.executable, "-c", "pass"], Path(temporary) / "gone", {})
            with self.assertRaises(lab_accept.ReportUnreadable):  # an in-tree runner the candidate removed
                lab_accept._run(["./run_tests.sh"], temporary, {})
            with self.assertRaises(OSError) as raised:  # the host's toolchain is missing: a grader failure, exit 2
                lab_accept._run(["/nonexistent/toolchain/go"], temporary, {})
            self.assertNotIsInstance(raised.exception, lab_accept.ReportUnreadable)

    def test_a_timeout_exits_3_and_writes_no_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "tree"
            root.mkdir()
            (root / "test_fixture.py").write_text("import time, unittest\nclass Kept(unittest.TestCase):\n    def test_new(self): time.sleep(60)\n")
            for name, value in (("lab.json", {"adapter": "unittest", "tests": "test_*.py"}), ("hidden.json", [NEW]), ("baseline.json", [])):
                (root / name).write_text(json.dumps(value))
            report = Path(temporary) / "report.json"
            cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(lab_accept, "TIMEOUT_S", 1.5), mock.patch.dict(os.environ, {"ACCEPT_REPORT": str(report)}):
                    self.assertEqual(lab_accept.main(["lab.json", "hidden.json", "baseline.json"]), 3)
            finally:
                os.chdir(cwd)
            self.assertFalse(report.exists())  # no grade was observed: the caller reads outcomes as unavailable

    def test_every_adapter_and_the_unnamed_report_path_exit_3(self):
        for adapter, named in (("node", True), ("pytest", True), ("go", True), ("custom", True), ("unittest", False)):
            with self.subTest(adapter=adapter, named=named), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "tree"
                root.mkdir()
                config = {"adapter": adapter, "tests": "*", "command": ["true"]}
                for name, value in (("lab.json", config), ("hidden.json", [NEW]), ("baseline.json", [])):
                    (root / name).write_text(json.dumps(value))
                report = Path(temporary) / "report.json"
                env = {"ACCEPT_REPORT": str(report)} if named else {}
                cwd = os.getcwd()
                os.chdir(root)
                try:
                    with mock.patch.object(lab_accept, "_run", side_effect=lab_accept.SuiteTimeout("suite")), \
                            mock.patch.dict(os.environ, env), contextlib.redirect_stderr(io.StringIO()) as err:
                        if not named:
                            os.environ.pop("ACCEPT_REPORT", None)
                        self.assertEqual(lab_accept.main(["lab.json", "hidden.json", "baseline.json"]), 3)
                finally:
                    os.chdir(cwd)
                self.assertFalse(report.exists())
                self.assertTrue(err.getvalue().startswith("lab_accept: suite did not finish within its deadline"), err.getvalue())


class UnreadableReport(unittest.TestCase):
    """Review 2026-11-22: a result file cut short by a crash raised in the adapter, so the grader exited 2 and, under
    `lab-accept-v1`, the cell became invalid where 1.10.0 recorded a rejection. Grading now reads it as no result (exit 1);
    --collect still fails (exit 2), so `mine` never keeps a baseline from a run that proves nothing."""

    CUT = {"node": ("events.jsonl", '{"f": "case.js", "d": 0, "n": "New", "o": "pass"}\n{"f": "ca'),
           "unittest": ("unittest.json", '[{"case.py :: 0 :: New": "pa'),
           "pytest": ("junit.xml", '<testsuite><testcase file="case.py" classname="Case" name="New"/><testc'),
           "custom": ("raw.json", '{"New": "pa'),
           "custom-list": ("raw.json", '["New"]'),
           "node-cut-in-a-character": ("events.jsonl", b'{"f": "caso\xc3', ),
           "node-wrong-shape": ("events.jsonl", '[1, 2]\n'),
           "unittest-wrong-shape": ("unittest.json", '[["not", "a", "dict"], []]'),
           "custom-wrong-values": ("raw.json", '{"New": 1}')}

    def grade(self, adapter, collect):
        name, text = self.CUT[adapter]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "tree"
            root.mkdir()
            config = {"adapter": adapter.split("-")[0], "tests": "*", "command": ["true"]}
            write = (lambda path: path.write_bytes(text)) if isinstance(text, bytes) else (lambda path: path.write_text(text))
            for file, value in (("lab.json", config), ("hidden.json", ["case.py :: 0 :: New"]), ("baseline.json", [])):
                (root / file).write_text(json.dumps(value))
            report = Path(temporary) / "out" / "report.json"
            report.parent.mkdir()

            def run(argv, cwd, env, **_):
                write(report.parent / "lab" / name)
                return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
            cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(lab_accept, "_run", side_effect=run), mock.patch.dict(os.environ, {"ACCEPT_REPORT": str(report)}):
                    if collect:
                        with self.assertRaises(lab_accept.ReportUnreadable):
                            lab_accept.main(["--collect", "lab.json"])
                        return None
                    return lab_accept.main(["lab.json", "hidden.json", "baseline.json"]), json.loads(report.read_text())
            finally:
                os.chdir(cwd)

    def test_a_cut_result_file_is_a_rejection_when_grading(self):
        for adapter in self.CUT:
            with self.subTest(adapter=adapter):
                self.assertEqual(self.grade(adapter, collect=False), (1, {"case.py :: 0 :: New": "error", "__module__": "fail"}))

    def test_a_cut_result_file_fails_collection(self):
        for adapter in self.CUT:
            with self.subTest(adapter=adapter):
                self.grade(adapter, collect=True)

    def test_an_oversized_result_file_proves_nothing(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(lab_accept, "MAX_REPORT", 10):
            big = Path(temporary) / "raw.json"
            big.write_text(json.dumps({"New": "pass", "Other": "pass"}))
            with self.assertRaises(lab_accept.ReportUnreadable):
                lab_accept._read(big, "custom")

    def test_a_go_stream_past_the_cap_proves_nothing(self):
        events = ({"Action": "pass", "Package": "ex", "Test": "TestNew"}, {"Action": "pass", "Package": "ex"})
        proc = subprocess.CompletedProcess(["go"], 0, stdout="".join(json.dumps(e) + "\n" for e in events).encode())
        proc.stdout_truncated = True
        with mock.patch.object(lab_accept, "_run", return_value=proc), self.assertRaises(lab_accept.ReportUnreadable):
            lab_accept.go(Path("."), Path("."), {"tests": "./..."}, {"PATH": os.environ.get("PATH", "")}, Path("."))
        proc.stdout_truncated = False
        with mock.patch.object(lab_accept, "_run", return_value=proc):
            self.assertEqual(lab_accept.go(Path("."), Path("."), {"tests": "./..."}, {"PATH": os.environ.get("PATH", "")}, Path(".")),
                             {"ex :: 0 :: TestNew": "pass"})


if __name__ == "__main__":
    unittest.main()
