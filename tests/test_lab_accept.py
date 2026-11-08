"""lab_accept: a class, module or package that fails outside its tests must not grade as a pass (audit 2026-11-08, F01).

Before the fix, unittest's tearDownClass error and a `go test` package failure after every test passed were both accepted.
Controls: a clean suite, a test already red at base, and a failure in a scope no graded test lives in still grade as before.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
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
                def run(argv, cwd, env):
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


if __name__ == "__main__":
    unittest.main()
