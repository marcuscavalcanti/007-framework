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
    def grade(self, events, hidden, baseline):
        proc = subprocess.CompletedProcess(["go"], 1, stdout="".join(json.dumps(e) + "\n" for e in events).encode(), stderr=b"")
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


if __name__ == "__main__":
    unittest.main()
