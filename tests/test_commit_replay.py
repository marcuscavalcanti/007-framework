"""Trilha A step 2 (master 3.2): commit-replay calibration tasks from a synthetic git repository; no model, no network."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

GIT_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
RUN_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": "tests:.", "PYTHONDONTWRITEBYTECODE": "1"}
CALC = "def add(a, b):\n    return a + b\n"
TEST = "import unittest\nimport calc\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(calc.add(1, 2), 3)\n"


class ReplayFixture(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.repo = self.root / "source"
        (self.repo / "tests").mkdir(parents=True)
        self.git("init", "-q", "-b", "main")
        self.commit("init", {"calc.py": CALC, "tests/test_calc.py": TEST})
        self.ids = {}
        self.ids["valid"] = self.commit("add sub", {
            "calc.py": CALC + "\n\ndef sub(a, b):\n    return a - b\n",
            "tests/test_sub.py": "import unittest\nimport calc\nprint('PRIVATE-SENTINEL')\n\n\nclass T(unittest.TestCase):\n"
                                 "    def test_sub(self):\n        self.assertEqual(calc.sub(3, 1), 2)\n"})
        self.ids["already-passing"] = self.commit("comment", {
            "calc.py": "# comment\n" + CALC + "\n\ndef sub(a, b):\n    return a - b\n",
            "tests/test_more.py": TEST.replace("test_add", "test_add_again")})
        self.ids["broken"] = self.commit("broken", {
            "calc.py": "# broken\n" + CALC + "\n\ndef sub(a, b):\n    return a - b\n",
            "tests/test_broken.py": "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail()\n"})
        self.ids["slow"] = self.commit("slow", {
            "calc.py": "# slow\n" + CALC + "\n\ndef sub(a, b):\n    return a - b\n",
            "tests/test_slow.py": "import time\nimport unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n"
                                  "        time.sleep(30)\n"})
        self.ids["mixed"] = self.commit("mixed", {
            "calc.py": "# mixed\n" + CALC + "\n\ndef sub(a, b):\n    return a - b\n\n\ndef mul(a, b):\n    return a * b\n",
            "tests/test_mul.py": "import unittest\nimport calc\n\n\nclass T(unittest.TestCase):\n"
                                 "    def test_mul(self):\n        self.assertEqual(calc.mul(2, 3), 6)\n\n"
                                 "    def test_add_still(self):\n        self.assertEqual(calc.add(2, 3), 5)\n\n"
                                 "    def test_broken_on_commit(self):\n        self.fail()\n"})
        self.commit("delete test", {"calc.py": "# deleted\n" + CALC + "\n\ndef sub(a, b):\n    return a - b\n"},
                    remove=["tests/test_broken.py"])
        self.commit("too big", {f"mod{i}.py": f"X = {i}\n" for i in range(10)} | {"tests/test_big.py": TEST})
        self.commit("docs", {"README.md": "docs\n"})
        self.commit("tests only", {"tests/test_only.py": TEST})
        self.git("checkout", "-q", "-b", "side")
        side = self.commit("side", {"side.py": "S = 1\n", "tests/test_side.py": TEST})
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-ff", "-m", "merge", "side")
        self.ids["side"] = side

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=GIT_ENV, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, message, files, remove=()):
        for name, text in files.items():
            (self.repo / name).write_text(text)
        for name in remove:
            self.git("rm", "-q", name)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def module(self):
        try:
            return importlib.import_module("commit_replay")
        except ModuleNotFoundError:
            self.fail("commit-replay factory is missing")

    def snapshot(self):
        return self.git("status", "--porcelain=v1"), self.git("for-each-ref"), self.git("rev-parse", "HEAD")


class CommitReplayTests(ReplayFixture):
    def test_candidates_follow_the_preregistered_rule_in_commit_order(self):
        before = self.snapshot()
        found = self.module().candidates(self.repo)
        self.assertEqual([c["commit"] for c in found],
                         [self.ids[k] for k in ("valid", "already-passing", "broken", "slow", "mixed", "side")])
        first = found[0]
        self.assertEqual((first["parent"], first["tests"], first["sources"]),
                         (self.git("rev-parse", self.ids["valid"] + "^"), ["tests/test_sub.py"], ["calc.py"]))
        self.assertEqual(self.snapshot(), before)

    def test_materialize_is_exact_without_git_and_refuses_reuse_or_dropped_files(self):
        module = self.module()
        dest = self.root / "tree"
        result = module.materialize(self.repo, self.ids["valid"], dest)
        self.assertEqual(result["tree"], self.git("rev-parse", self.ids["valid"] + "^{tree}"))
        self.assertEqual(sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()),
                         ["calc.py", "tests/test_calc.py", "tests/test_sub.py"])
        self.assertFalse((dest / ".git").exists())
        with self.assertRaisesRegex(ValueError, "^replay-invalid$"):
            module.materialize(self.repo, self.ids["valid"], dest)
        dropped = self.commit("attributes", {".gitattributes": "calc.py export-ignore\n", "calc.py": "# attr\n" + CALC})
        with self.assertRaisesRegex(ValueError, "^replay-invalid$"):
            module.materialize(self.repo, dropped, self.root / "dropped")

    def test_validation_is_per_test_and_keeps_only_test_ids(self):
        # Step 2b: fail_to_pass = passes on the commit and not on parent + oracle; pass_to_pass = passes on both;
        # tests failing on the commit leave the oracle; only ids and outcomes are kept, never test output.
        module = self.module()
        # Added after GREEN (counterproof log 78): a test module that cannot even import on the parent has no ids there.
        self.ids["new-module"] = self.commit("new module", {
            "newmod.py": "VALUE = 7\n",
            "tests/test_newmod.py": "import unittest\nimport newmod\n\n\nclass T(unittest.TestCase):\n"
                                    "    def test_value(self):\n        self.assertEqual(newmod.VALUE, 7)\n"})
        before = self.snapshot()
        command = module.unittest_command(sys.executable)
        found = {c["commit"]: c for c in module.candidates(self.repo)}
        def check(key, timeout=20):
            return module.validate(self.repo, found[self.ids[key]], command=command, env=RUN_ENV, timeout=timeout)
        mixed = check("mixed")
        self.assertEqual((mixed["status"], mixed["fail_to_pass"], mixed["pass_to_pass"], mixed["excluded"]),
                         ("valid", ["test_mul.T.test_mul"], ["test_mul.T.test_add_still"], ["test_mul.T.test_broken_on_commit"]))
        self.assertEqual(set(mixed), {"status", "fail_to_pass", "pass_to_pass", "excluded"})
        valid = check("valid")
        self.assertEqual((valid["status"], valid["fail_to_pass"]), ("valid", ["test_sub.T.test_sub"]))
        self.assertNotIn("PRIVATE", repr(valid))
        self.assertEqual(check("already-passing")["status"], "no-fail-to-pass")
        self.assertEqual(check("already-passing")["pass_to_pass"], ["test_more.T.test_add_again"])
        self.assertEqual(check("broken")["status"], "no-fail-to-pass")
        self.assertEqual(check("slow", timeout=1)["status"], "timeout")
        absent = check("new-module")
        self.assertEqual((absent["status"], absent["fail_to_pass"]), ("valid", ["test_newmod.T.test_value"]))
        silent = module.validate(self.repo, found[self.ids["valid"]], command=lambda paths, report: [sys.executable, "-c", "pass"],
                                 env=RUN_ENV, timeout=20)
        self.assertEqual(silent["status"], "report-missing")
        self.assertEqual(self.snapshot(), before)

    def test_validation_isolates_home_and_refuses_fixture_errors(self):
        # Review r25-r32 R3: validation runs historical tests and must never resolve the real account home.
        # R1: a class-level fixture error on the commit would reject even the reference in acceptance, so the task is not valid.
        module = self.module()
        self.ids["home-check"] = self.commit("home check", {
            "homecheck.py": "OK = True\n",
            "tests/test_homecheck.py": "import os, pathlib, pwd, unittest\nimport homecheck\n\n\nclass T(unittest.TestCase):\n"
                                       "    def test_isolated(self):\n"
                                       "        self.assertNotEqual(str(pathlib.Path.home()), pwd.getpwuid(os.getuid()).pw_dir)\n"
                                       "        self.assertTrue(homecheck.OK)\n"})
        self.ids["fixture-error"] = self.commit("fixture error", {
            "fx.py": "VALUE = 1\n",
            "tests/test_fx.py": "import unittest\nimport fx\n\n\nclass T(unittest.TestCase):\n"
                                "    @classmethod\n    def tearDownClass(cls):\n        raise RuntimeError('fixture')\n\n"
                                "    def test_value(self):\n        self.assertEqual(fx.VALUE, 1)\n"})
        self.ids["fixture-skip"] = self.commit("fixture skip", {  # re-review r35 R1: a fixture skip also rejects the reference
            "fy.py": "VALUE = 1\n",
            "tests/test_fy.py": "import unittest\nimport fy\n\n\nclass T(unittest.TestCase):\n"
                                "    @classmethod\n    def tearDownClass(cls):\n        raise unittest.SkipTest('fixture')\n\n"
                                "    def test_value(self):\n        self.assertEqual(fy.VALUE, 1)\n"})
        command = module.unittest_command(sys.executable)
        found = {c["commit"]: c for c in module.candidates(self.repo)}
        check = lambda key: module.validate(self.repo, found[self.ids[key]], command=command, env=RUN_ENV, timeout=20)
        self.assertEqual(check("home-check")["status"], "valid")
        self.assertEqual(check("fixture-error")["status"], "fixture-error")
        self.assertEqual(check("fixture-skip")["status"], "fixture-error")

    def test_materialize_verifies_symlinks_and_refuses_dropped_ones(self):
        # Review r25-r32 R4: symlink entries are part of the exact tree.
        module = self.module()
        (self.repo / "alias").symlink_to("calc.py")
        kept = self.commit("symlink", {"calc.py": "# link\n" + CALC})
        dest = self.root / "linked"
        module.materialize(self.repo, kept, dest)
        self.assertEqual(((dest / "alias").is_symlink(), os.readlink(dest / "alias")), (True, "calc.py"))
        dropped = self.commit("drop symlink", {".gitattributes": "alias export-ignore\n", "calc.py": "# drop\n" + CALC})
        with self.assertRaisesRegex(ValueError, "^replay-invalid$"):
            module.materialize(self.repo, dropped, self.root / "dropped-link")

    def test_statement_is_the_commit_message_with_leak_and_size_flags(self):
        module = self.module()
        found = {c["commit"]: c for c in module.candidates(self.repo)}
        self.assertEqual(module.statement(self.repo, found[self.ids["valid"]]),
                         {"text": "add sub", "words": 2, "flags": ["underspecified"]})
        line = "TOTAL_LIMIT_VALUE = 12345  # hard cap"
        message = "Add a hard cap for totals so callers never exceed the limit\n\n" + line
        leaky = self.commit(message, {"limits.py": line + "\n", "tests/test_limits.py": TEST})
        clean = self.commit("Expose a subtraction helper so reports can compute balance deltas",
                            {"calc.py": "# clean\n" + CALC, "tests/test_clean.py": TEST})
        found = {c["commit"]: c for c in module.candidates(self.repo)}
        self.assertEqual(module.statement(self.repo, found[leaky])["flags"], ["leak"])
        self.assertEqual(module.statement(self.repo, found[clean])["flags"], [])


class AcceptReportTests(unittest.TestCase):
    def test_boot_writes_per_test_outcomes_only_when_asked_and_keeps_the_exit_code(self):
        # r45: a failed cell must be told apart (wrong code / other interface / environment): test id -> outcome, never output.
        boot = importlib.import_module("commit_replay").BOOT.format(paths=["."])
        with tempfile.TemporaryDirectory() as work, tempfile.TemporaryDirectory() as out:
            Path(work, "test_pair.py").write_text("import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n"
                                                  "        pass\n\n    def test_bad(self):\n        self.fail('PRIVATE-OUTPUT')\n")
            ok, bad = "test_pair.T.test_ok", "test_pair.T.test_bad"
            report = Path(out, "accept-report.json")
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "TMPDIR": tempfile.gettempdir()}
            def boot_exit(*ids, **extra):
                return subprocess.run([sys.executable, "-I", "-c", boot, *ids], cwd=work, env={**env, **extra},
                                      capture_output=True, timeout=60).returncode
            self.assertEqual(boot_exit(ok, bad, ACCEPT_REPORT=str(report)), 1)
            self.assertEqual(json.loads(report.read_text()), {ok: "pass", bad: "fail"})
            report.unlink()
            self.assertEqual(boot_exit(ok, bad), 1)
            self.assertEqual(os.listdir(out), [])
            self.assertEqual(boot_exit(ok, ACCEPT_REPORT=str(report)), 0)
            self.assertEqual(json.loads(report.read_text()), {ok: "pass"})



AGENT = r"""import pathlib, shutil, sys
mode, cwd, solution, *oracle = sys.argv[1:]
cwd = pathlib.Path(cwd)
assert not any((cwd / path).exists() for path in oracle)  # the hidden oracle is absent while the agent runs
if mode == "solve":
    shutil.copytree(solution, cwd, dirs_exist_ok=True)
elif mode == "edit-oracle":
    for path in oracle:
        (cwd / path).write_text("import unittest\n\n\nclass T(unittest.TestCase):\n    def test_sub(self):\n        pass\n")
elif mode == "startup-hook":
    (cwd / "tests" / "sitecustomize.py").write_text("import os\nos._exit(0)\n")
elif mode == "skip":  # review r25-r32 R1: a candidate whose attributes raise SkipTest when the oracle calls them is not a pass
    for path in pathlib.Path(solution).rglob("*.py"):
        (cwd / path.relative_to(solution)).write_text("import unittest\n\n\ndef __getattr__(name):\n    raise unittest.SkipTest(name)\n")
"""
MODES = ("solve", "noop", "edit-oracle", "startup-hook", "skip")


class ReplaySetTests(ReplayFixture):
    # Step 2c (master 3.2): commit-replay tasks feed the existing replay_eval runner; only the real solution is accepted.
    def setUp(self):
        super().setUp()
        self.ids["home"] = self.commit("home tool", {
            "home_tool.py": "VALUE = 1\n",
            "tests/test_home.py": "import pathlib\nimport subprocess\nimport tempfile\nimport unittest\nimport home_tool\n\n\n"
                                  "class T(unittest.TestCase):\n"
                                  "    def test_home(self):\n        (pathlib.Path.home() / 'probe').write_text('x')\n"
                                  "        self.assertEqual(home_tool.VALUE, 1)\n\n"
                                  "    def test_temp_is_not_inside_a_git_work_tree(self):  # 2d: replay_eval turns the workspace into a repo\n"
                                  "        inside = subprocess.run(['git', '-C', tempfile.mkdtemp(), 'rev-parse', '--is-inside-work-tree'],\n"
                                  "                                capture_output=True).returncode == 0\n"
                                  "        self.assertEqual((home_tool.VALUE, inside), (1, False))\n"})

    def rows(self):
        module = self.module()
        command = module.unittest_command(sys.executable)
        # The home fixture writes Path.home()/probe: never let a test run resolve the real account home (incident R3).
        env = {**RUN_ENV, "HOME": str(self.root / "test-home")}
        return [{**task, **module.validate(self.repo, task, command=command, env=env, timeout=20),
                 "statement": module.statement(self.repo, task)}
                for task in module.candidates(self.repo) if task["commit"] in (self.ids["valid"], self.ids["home"], self.ids["mixed"])]

    def replay_tasks(self, rows, oracle_dir):
        self.assertTrue(hasattr(self.module(), "replay_tasks"), "commit-replay to replay_eval bridge is missing")
        return self.module().replay_tasks(self.repo, rows, repo_key="fixture", oracle_dir=oracle_dir,
                                          python=sys.executable, python_paths=["tests", "."])

    def test_tasks_carry_a_hash_bound_hidden_oracle_and_refuse_invalid_rows(self):
        rows = self.rows()
        tasks = {t["accepted"]: t for t in self.replay_tasks(rows, self.root / "oracle")}
        task = tasks[self.ids["valid"]]
        self.assertEqual((task["id"], task["repo"], task["base"], task["prompt"]),
                         ("fixture-" + self.ids["valid"][:12], "fixture", self.git("rev-parse", self.ids["valid"] + "^"), "add sub"))
        [hidden] = task["hidden_acceptance"]
        oracle = subprocess.run(["git", "-C", str(self.repo), "show", self.ids["valid"] + ":tests/test_sub.py"],
                                env=GIT_ENV, check=True, capture_output=True).stdout
        self.assertEqual((hidden["target"], Path(hidden["source"]).read_bytes(), hidden["sha256"]),
                         ("tests/test_sub.py", oracle, hashlib.sha256(oracle).hexdigest()))
        [argv] = task["acceptance"]
        self.assertEqual((argv[:3], argv[4:]), ([sys.executable, "-I", "-c"], ["test_sub.T.test_sub"]))
        for bad, oracle_dir in (([{**rows[0], "status": "no-fail-to-pass"}], self.root / "oracle-2"), (rows, self.root / "oracle")):
            with self.subTest(oracle_dir=oracle_dir.name), self.assertRaisesRegex(ValueError, "^replay-invalid$"):
                self.replay_tasks(bad, oracle_dir)

    def test_replay_eval_accepts_only_the_real_solution_without_touching_home(self):
        replay_eval = importlib.import_module("replay_eval")
        sources = {row["commit"]: row["sources"] for row in self.rows()}
        tasks = {t["accepted"]: t for t in self.replay_tasks(self.rows(), self.root / "oracle")}
        real_home, output = self.root / "real-home", self.root / "cells"
        real_home.mkdir()
        output.mkdir()
        accepted = {}
        with patch.dict(os.environ, {"HOME": str(real_home), "PYTHONPATH": "tests"}):
            for key in ("valid", "home"):
                commit = self.ids[key]
                solution = self.root / f"solution-{key}"
                for path in sources[commit]:
                    (solution / path).parent.mkdir(parents=True, exist_ok=True)
                    (solution / path).write_bytes(subprocess.run(["git", "-C", str(self.repo), "show", f"{commit}:{path}"],
                                                                 env=GIT_ENV, check=True, capture_output=True).stdout)
                for mode in MODES:
                    task = tasks[commit]
                    config = {"repos": {"fixture": str(self.repo)}, "arms": {mode: {"model": "fake", "effort": "none", "doctrine": ""}},
                              "agent_command": [sys.executable, "-c", AGENT, mode, "{cwd}", str(solution),
                                                *(h["target"] for h in task["hidden_acceptance"])]}
                    cell = replay_eval.execute_cell(config, task, mode, 1, output, 60)
                    accepted[(key, mode)] = cell["accepted"]
                    self.assertNotIn("PRIVATE", json.dumps(cell))
        self.assertEqual(accepted, {(key, mode): mode == "solve" for key in ("valid", "home") for mode in MODES})
        self.assertFalse((real_home / "probe").exists())


    def test_regression_in_pass_to_pass_is_rejected(self):
        # Added after GREEN, before counterproofs: the integration tasks above have no pass_to_pass.
        replay_eval = importlib.import_module("replay_eval")
        task = {t["accepted"]: t for t in self.replay_tasks(self.rows(), self.root / "oracle")}[self.ids["mixed"]]
        self.assertIn("test_mul.T.test_add_still", task["acceptance"][0])
        self.assertNotIn("test_mul.T.test_broken_on_commit", task["acceptance"][0])
        good = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
        accepted, output = {}, self.root / "cells-mixed"
        output.mkdir()
        with patch.dict(os.environ, {"PYTHONPATH": "tests"}):
            for mode, text in (("solve", good), ("regress", good.replace("a + b", "0"))):
                solution = self.root / f"mixed-{mode}"
                solution.mkdir()
                (solution / "calc.py").write_text(text)
                config = {"repos": {"fixture": str(self.repo)}, "arms": {mode: {"model": "fake", "effort": "none", "doctrine": ""}},
                          "agent_command": [sys.executable, "-c", AGENT, "solve", "{cwd}", str(solution),
                                            *(h["target"] for h in task["hidden_acceptance"])]}
                accepted[mode] = replay_eval.execute_cell(config, task, mode, 1, output, 60)["accepted"]
        self.assertEqual(accepted, {"solve": True, "regress": False})


if __name__ == "__main__":
    unittest.main()
