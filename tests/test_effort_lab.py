"""`007 lab` end to end: a synthetic repository, a fake agent, no model and no vendor."""
import contextlib
import difflib
import hashlib
import io
import json
import os
import re
import shutil
from pathlib import Path
import subprocess
import statistics
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import effort_lab as lab

FAKE_AGENT = """import json, sys
cwd, receipt, effort, prompt, good, partial = sys.argv[1:7]
path = cwd + "/calc.py"
if "report_total" in open(prompt).read():
    open(path, "a").write("\\n\\ndef report_total(a, b):\\n    return clamp_total(a, b)\\n")
else:
    open(path, "w").write(good if effort == "high" else partial)
requested = {"provider": "none", "model": "none", "effort": effort}
json.dump({"schema": "007-framework/runner-receipt/v1", "valid": True, "requested": requested, "served": requested, "identity_source": "fake", "source_sha256": "0" * 64,
           "cost_usd": 0.5, "cost_source": "fake", "usage": {"reasoning_output_tokens": 100}}, open(receipt, "w"))
"""
# the leakage probe: FAKE_AGENT after a record of everything the agent process sees, written where LAB_CAPTURE says
CAPTURE_AGENT = """import json, os, sys, uuid
here = os.getcwd()
tree = sorted(os.path.relpath(os.path.join(top, name), here) for top, dirs, files in os.walk(here) for name in dirs + files)
seen = {"cwd": here, "argv": sys.argv, "env": dict(os.environ), "tree": tree, "stdin": sys.stdin.read(), "prompt_file": open(sys.argv[4]).read()}
json.dump(seen, open(os.path.join(os.environ["LAB_CAPTURE"], uuid.uuid4().hex + ".json"), "w"))
""" + FAKE_AGENT
GOOD = "def add(a, b):\n    return a + b\n\n\ndef clamp_total(a, b):\n    return min(add(a, b), 100)\n"
PARTIAL = "def add(a, b):\n    return a + b\n\n\ndef clamp_total(a, b):\n    return add(a, b)\n"


def git(repo, *args, date=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return subprocess.run(["git", "-C", str(repo), *args], env=env, capture_output=True, text=True, check=True).stdout


def commit(repo, files, message, date):
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message, date=date)
    return git(repo, "rev-parse", "HEAD").strip()


def synthetic(repo):
    git(repo, "init", "-qb", "main")
    commit(repo, {"calc.py": "def add(a, b):\n    return a - b\n", "tests/__init__.py": "", "tests/test_old.py": "import unittest\n\n\nclass Old(unittest.TestCase):\n    def test_truth(self):\n        self.assertTrue(True)\n"}, "base", "2026-01-01T00:00:00Z")
    hidden = "import unittest\nimport calc\n\n\nclass Add(unittest.TestCase):\n" + "".join(f"    def test_add_{i}(self):\n        self.assertEqual(calc.add({i}, 1), {i + 1})\n\n" for i in range(5))
    message = "feat: fix addition and cap totals\n\n" + "Addition must really add, and clamp_total caps the sum at one hundred so later reports stay bounded. " * 2
    sha = commit(repo, {"calc.py": GOOD, "tests/test_add.py": hidden}, message, "2026-01-05T00:00:00Z")
    later = "import unittest\nimport calc\n\n\nclass Report(unittest.TestCase):\n" + "".join(f"    def test_report_{i}(self):\n        self.assertEqual(calc.report_total(90, {20 + i}), 100)\n\n" for i in range(5))
    commit(repo, {"calc.py": GOOD + "\n\ndef report_total(a, b):\n    return clamp_total(a, b)\n", "tests/test_report.py": later}, "feat: add report_total on top of the capped sum", "2026-01-10T00:00:00Z")
    return sha


class LabRunAccountingTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.config = self.root / "set.json"
        self.config.write_text(json.dumps({"seed": 1, "tasks": [{"id": "case"}], "arms": {"high": {}}}))
        self.calls = 0

    def execute(self, config, task, arm, replicate, output, timeout):
        self.calls += 1
        cell = lab.replay_eval.cell_id(task, arm, replicate)
        row = {"valid": False, "cost_usd": 0, "task": task["id"], "arm": arm, "cell": cell}
        (output / (cell + ".json")).write_text(json.dumps(row))
        return row

    def run_lab(self, output):
        return lab.run(self.config, output, replicates=1, jobs=1, max_calls=1, max_usd=1,
                       stop_usd=1, execute=self.execute)

    def test_dispatch_without_terminal_or_damaged_history_blocks_another_execution(self):
        for name, history, stop in (
                ("started", '{"cell":"case-r01-high","dispatched_at":"2026-11-09T10:00:00Z"}\n', "uncertain-attempts"),
                ("finished", '{"cell":"case-r01-high","finished_at":"2026-11-09T10:00:00Z"}\n', "uncertain-attempts"),
                ("torn", '{"cell":"case', "unreadable-dispatch-history")):
            with self.subTest(name=name):
                output = self.root / name
                output.mkdir()
                (output / "dispatch.jsonl").write_text(history)
                self.assertEqual(self.run_lab(output)["stop"], stop)
                self.assertEqual(self.calls, 0)
        completed = self.root / "completed"
        self.assertEqual(self.run_lab(completed)["calls"], 1)
        self.assertEqual(self.run_lab(completed)["calls"], 0)
        self.assertEqual(self.calls, 1)

    def test_two_controllers_cannot_dispatch_into_one_output_directory(self):
        entered, release = threading.Event(), threading.Event()
        real_pool = lab.ThreadPoolExecutor
        failures = []

        def pause_owner(*args, **kwargs):
            if threading.current_thread().name == "lab-owner":
                entered.set()
                release.wait(5)
            return real_pool(*args, **kwargs)

        output = self.root / "shared"

        def first():
            try:
                self.run_lab(output)
            except Exception as error:
                failures.append(type(error).__name__)

        owner = threading.Thread(target=first, name="lab-owner")
        with mock.patch.object(lab, "ThreadPoolExecutor", side_effect=pause_owner):
            owner.start()
            try:
                self.assertTrue(entered.wait(5))
                other = self.run_lab(output)
            finally:
                release.set()
                owner.join(5)
        self.assertFalse(owner.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(self.calls, 1)
        self.assertEqual(other["stop"], "run-already-active")

    def test_duplicate_dispatch_history_blocks_new_work_even_when_the_cell_has_a_result(self):
        output = self.root / "duplicate"
        self.run_lab(output)
        with (output / "dispatch.jsonl").open("a") as handle:
            handle.write(json.dumps({"cell": "case-r01-high", "dispatched_at": "2026-11-09T10:00:00Z"}) + "\n")
        self.config.write_text(json.dumps({"seed": 1, "tasks": [{"id": "case"}, {"id": "new-case"}], "arms": {"high": {}}}))
        result = self.run_lab(output)
        self.assertEqual(result["stop"], "ambiguous-dispatch-history")
        self.assertEqual(self.calls, 1)

    def test_three_digit_replicates_remain_visible_to_budget_and_result_readers(self):
        output = self.root / "long-run"
        output.mkdir()
        (output / "case-r100-high.json").write_text(json.dumps({"task": "case", "arm": "high", "valid": False,
            "cost_usd": 0.5, "runner_receipt_sha256": "unmeasured"}))
        result = lab.run(self.config, output, replicates=100, jobs=1, max_calls=1, max_usd=0.75,
                         stop_usd=1, execute=self.execute)
        self.assertEqual(result["spent"], 0.5)
        self.assertEqual(self.calls, 0)
        self.assertEqual(len(lab.load_cells(output)), 1)

    def test_different_task_arm_pairs_cannot_share_one_cell_identity(self):
        self.config.write_text(json.dumps({"seed": 1, "tasks": [{"id": "case"}, {"id": "case-r01-x"}],
                                           "arms": {"x-r01-high": {}, "high": {}}}))
        output = self.root / "collision"
        with self.assertRaisesRegex(ValueError, "cell identities"):
            self.run_lab(output)
        self.assertEqual(self.calls, 0)
        self.assertFalse((output / "dispatch.jsonl").exists())

    def test_distinct_cells_cannot_share_a_result_and_receipt_path(self):
        self.config.write_text(json.dumps({"seed": 1, "tasks": [{"id": "case"}],
                                           "arms": {"high": {}, "high.runner": {}}}))
        with self.assertRaisesRegex(ValueError, "artifact"):
            self.run_lab(self.root / "artifact-collision")
        self.assertEqual(self.calls, 0)

    def test_standalone_replay_rejects_all_artifact_collisions_before_execution(self):
        cases = [({"high": {}, "x-r01-high": {}}, [{"id": "case"}, {"id": "case-r01-x"}]),
                 ({"high": {}, "high.runner": {}}, [{"id": "case"}]),
                 ({"high": {}, "high.observation": {}}, [{"id": "case"}])]
        for index, (arms, tasks) in enumerate(cases):
            with self.subTest(arms=arms):
                self.config.write_text(json.dumps({"seed": 1, "arms": arms, "tasks": tasks}))
                argv = ["replay_eval.py", "--set", str(self.config), "run", "--arms", ",".join(arms),
                        "--replicates", "1", "--out", str(self.root / f"standalone-{index}")]
                with mock.patch.object(sys, "argv", argv), mock.patch.object(sys, "stdout"), \
                        mock.patch.object(lab.replay_eval, "execute_cell", return_value={"valid": True}) as execute, \
                        mock.patch.object(lab.replay_eval, "write_summary"):
                    with self.assertRaisesRegex(ValueError, "cell identities|artifact"):
                        lab.replay_eval.main()
                    execute.assert_not_called()

    def test_standalone_replay_rejects_nonpositive_timeouts_before_output(self):
        for index, timeout in enumerate((-1, 0, 1, 10 ** 400, 10 ** 9)):
            with self.subTest(timeout=timeout):
                output = self.root / f"timeout-{index}"
                argv = ["replay_eval.py", "--set", str(self.config), "run", "--arms", "high", "--replicates", "1",
                        "--timeout-min", str(timeout), "--out", str(output)]
                with mock.patch.object(sys, "argv", argv), mock.patch.object(sys, "stdout"), \
                        mock.patch.object(sys, "stderr"), \
                        mock.patch.object(lab.replay_eval, "execute_cell", return_value={"valid": True}) as execute, \
                        mock.patch.object(lab.replay_eval, "write_summary"):
                    if timeout != 1:
                        with self.assertRaises(SystemExit):
                            lab.replay_eval.main()
                        execute.assert_not_called()
                        self.assertFalse(output.exists())
                    else:
                        self.assertEqual(lab.replay_eval.main(), 0)
                        self.assertEqual(execute.call_args.args[-1], 60)

    def test_invalid_timestamps_and_repeated_terminal_history_block_recovery(self):
        for name, history in (
                ("invalid-time", [{"cell": "case-r01-high", "dispatched_at": "not-a-time"}]),
                ("invalid-extra-time", [{"cell": "case-r01-high", "dispatched_at": None,
                                          "finished_at": "2026-11-09T10:00:00Z"}]),
                ("repeated-finish", [{"cell": "case-r01-high", "finished_at": "2026-11-09T10:00:00Z", "cost_usd": 0},
                                     {"cell": "case-r01-high", "finished_at": "2026-11-09T10:01:00Z", "cost_usd": 0.5}])):
            with self.subTest(name=name):
                output = self.root / name
                output.mkdir()
                (output / "case-r01-high.json").write_text(json.dumps({"valid": True, "cost_usd": 0}))
                (output / "dispatch.jsonl").write_text("".join(json.dumps(row) + "\n" for row in history))
                self.config.write_text(json.dumps({"seed": 1, "tasks": [{"id": "case"}, {"id": "new-case"}],
                                                   "arms": {"high": {}}}))
                result = self.run_lab(output)
                self.assertIn(result["stop"], {"unreadable-dispatch-history", "ambiguous-dispatch-history"})
                self.assertEqual(self.calls, 0)

    def test_case_aliases_use_the_output_filesystems_naming_rules(self):
        probe = self.root / "CaseProbe"
        probe.write_bytes(b"synthetic")
        sensitive = not (self.root / "caseprobe").exists()
        probe.unlink()
        self.config.write_text(json.dumps({"seed": 1, "tasks": [{"id": "case"}],
                                           "arms": {"high": {}, "HIGH": {}}}))
        def run():
            return lab.run(self.config, self.root / "case-output", replicates=1, jobs=1, max_calls=2,
                           max_usd=10, stop_usd=1, execute=self.execute)
        if sensitive:
            self.assertEqual(run()["calls"], 2)
        else:
            with self.assertRaisesRegex(ValueError, "artifact"):
                run()
            self.assertEqual(self.calls, 0)

    def test_case_alias_guard_covers_both_execution_entrypoints(self):
        self.config.write_text(json.dumps({"seed": 1, "tasks": [{"id": "case"}],
                                           "arms": {"high": {}, "HIGH": {}}}))
        with mock.patch.object(lab.replay_eval, "artifact_case_sensitive", return_value=False, create=True):
            with self.assertRaisesRegex(ValueError, "artifact"):
                self.run_lab(self.root / "forced-lab")
            self.assertEqual(self.calls, 0)
            argv = ["replay_eval.py", "--set", str(self.config), "run", "--arms", "high,HIGH",
                    "--replicates", "1", "--out", str(self.root / "forced-replay")]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(sys, "stdout"), \
                    mock.patch.object(lab.replay_eval, "execute_cell", return_value={"valid": True}) as execute, \
                    mock.patch.object(lab.replay_eval, "write_summary"):
                with self.assertRaisesRegex(ValueError, "artifact"):
                    lab.replay_eval.main()
                execute.assert_not_called()


class LabEndToEnd(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.sha = synthetic(self.repo)
        agent = self.root / "agent.py"
        agent.write_text(FAKE_AGENT)
        self.config = {"repo": str(self.repo), "adapter": "unittest", "tests": "tests/test_*.py", "as_of": "2026-03-01T00:00:00+00:00", "seed": 7, "want": 1, "min_source_lines": 1, "min_message": 50,
                       "agent_command": [sys.executable, "-I", str(agent), "{cwd}", "{runner_receipt}", "{effort}", "{prompt_file}", GOOD, PARTIAL],
                       "arms": {e: {"provider": "none", "model": "none", "effort": e, "doctrine": ""} for e in ("medium", "high")},
                       "compare": {"candidate": "medium", "reference": "high"}, "served_identity": "requested-only"}

    def test_lab_contract_rejects_wrong_command_count_before_execution(self):
        source = self.root / "contract-preflight"
        self.assertEqual(lab.mine(self.config, source, 2), 1)
        config = json.loads((source / "replay-set.json").read_text())
        original = config["tasks"][0]
        for count in (0, 2):
            task = {**original, "acceptance": original["acceptance"] * count}
            with self.subTest(count=count, boundary="plan"):
                with self.assertRaisesRegex(ValueError, "requires exactly one acceptance command"):
                    lab.plan({**config, "tasks": [task]}, 1)
            with self.subTest(count=count, boundary="direct"):
                output = self.root / f"invalid-contract-{count}"
                output.mkdir()
                with self.assertRaisesRegex(ValueError, "requires exactly one acceptance command"):
                    lab.replay_eval.execute_cell(config, task, "high", 1, output, 30)
                self.assertEqual(list(output.iterdir()), [])
        lab.plan(config, 1)
        with self.assertRaisesRegex(ValueError, "acceptance_timeout_s of at least 900"):  # exit 3 could never show
            lab.plan({**config, "tasks": [{**original, "acceptance_timeout_s": 600}]}, 1)
        # No contract means existing generic multi-command semantics are unchanged.
        legacy = {**original, "acceptance": original["acceptance"] * 2}
        legacy.pop("acceptance_exit_contract")
        lab.plan({**config, "tasks": [legacy]}, 1)

    def test_lab_oracle_error_is_invalid_but_candidate_rejection_is_valid(self):
        source = self.root / "contract-classification"
        self.assertEqual(lab.mine(self.config, source, 2), 1)
        manifest = json.loads((source / "replay-set.json").read_text())
        original = manifest["tasks"][0]
        self.assertEqual(original["acceptance_exit_contract"], "lab-accept-v1")
        real_acceptance = lab.replay_eval.acceptance

        def hung(*args, **kwargs):  # lab_accept's exit when a suite command does not finish in time (800 s: not run here)
            checks, _ = real_acceptance(*args, **kwargs)  # the real grade leaves an all-pass report the exit 3 must not read
            assert json.loads(Path(args[3]["ACCEPT_REPORT"]).read_text())
            return [{**checks[0], "exit": 3}], False
        for name, oracle_exit, valid, accepted in (
                ("accept", 0, True, True), ("reject", 1, True, False),
                ("broken", 2, False, False), ("legacy", 2, True, False), ("hung", 3, True, False)):
            with self.subTest(name=name):
                task = json.loads(json.dumps(original))
                config = json.loads(json.dumps(manifest))
                if name in ("broken", "legacy"):
                    task["acceptance"][0][-1] += ".missing"
                if name == "legacy":
                    task.pop("acceptance_exit_contract")
                if name == "reject":
                    config["agent_command"][-2] = "def add(a, b):\n    return -887\n"
                output = self.root / name
                output.mkdir()
                with mock.patch.object(lab.replay_eval, "acceptance", side_effect=hung if name == "hung" else real_acceptance):
                    row = lab.replay_eval.execute_cell(config, task, "high", 1, output, 30)
                self.assertEqual([check["exit"] for check in row["acceptance"]], [oracle_exit])
                self.assertEqual((row["valid"], row["accepted"]), (valid, accepted))
                self.assertEqual(row["failure_class"], "none" if valid else "acceptance-harness-error")
                if name == "hung":
                    self.assertEqual(row["acceptance_outcomes"], "unavailable")
        broken = json.loads(json.dumps(manifest))
        broken["tasks"][0]["acceptance"][0][-1] += ".missing"
        config_path = source / "broken.json"
        config_path.write_text(json.dumps(broken))
        result = lab.run(config_path, self.root / "controlled", replicates=1, jobs=1,
                         chunk=1, max_calls=2, max_usd=10, stop_usd=1, max_invalid=1)
        self.assertEqual({k: result[k] for k in ("calls", "invalid", "stop")},
                         {"calls": 1, "invalid": 1, "stop": "invalid-budget"})

    def test_a_real_exit_3_that_leaves_descendants_is_a_valid_rejection(self):
        """r2 should-fix 6: the grader exits 3 while a grandchild (as under `go test`) still runs; replay_eval's session cleanup
        kills it, so the cell reaches the contract as a valid rejection, not CleanupIncomplete or a harness error."""
        source = self.root / "contract-real-exit-3"
        self.assertEqual(lab.mine(self.config, source, 2), 1)
        config = json.loads((source / "replay-set.json").read_text())
        task = json.loads(json.dumps(config["tasks"][0]))
        stub = ("import subprocess, sys\n"
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                "sys.exit(3)\n")
        task["acceptance"] = [[sys.executable, "-c", stub]]
        output = self.root / "real-exit-3"
        output.mkdir()
        row = lab.replay_eval.execute_cell(config, task, "high", 1, output, 30)
        self.assertEqual([check["exit"] for check in row["acceptance"]], [3])
        self.assertEqual((row["valid"], row["accepted"], row["failure_class"]), (True, False, "none"))
        self.assertEqual(row["acceptance_outcomes"], "unavailable")

    def test_mine_pairs_a_commit_with_its_next_change(self):
        out = self.root / "lab"
        self.assertEqual(lab.mine(self.config, out, 2), 1)
        task = json.loads((out / "replay-set.json").read_text())["tasks"][0]
        meta = json.loads((out / "pairs.json").read_text())[task["id"]]
        self.assertEqual(task["accepted"], self.sha)
        self.assertIn("report_total", meta["next"]["prompt"])
        self.assertNotIn("report_total", task["prompt"])

    def test_a_latent_defect_surfaces_in_the_next_change(self):
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path, results, stage2 = out / "replay-set.json", self.root / "results", self.root / "stage2"
        state = lab.run(path, results, replicates=1, jobs=2, max_calls=2, max_usd=10, stop_usd=1)
        self.assertEqual((state["stop"], state["calls"], state["invalid"]), (None, 2, 0))
        self.assertEqual(lab.chain(path, results, stage2)["broken"], [])
        state = lab.run(stage2 / "replay-set.json", self.root / "next", replicates=1, jobs=2, max_calls=2, max_usd=10, stop_usd=1)
        self.assertEqual((state["stop"], state["invalid"]), (None, 0), state)
        lab.sensitivity(path, 2)
        result = lab.report(path, results, self.root / "next")
        self.assertEqual((result["contrast"]["medium"]["accepted"], result["contrast"]["high"]["accepted"]), (1, 1))
        self.assertEqual((result["contrast"]["medium"]["durable"], result["contrast"]["high"]["durable"]), (0, 1))
        self.assertEqual(result["verdict"]["durability"], "NO-INFORMATION")  # one task can prove nothing
        # stage 2 is bound to these results at the reference arm: a chain run at another effort, or of other results, is refused
        manifest = self.root / "next" / "run-manifest.json"
        sealed = manifest.read_text()
        for name, edit in (("other effort", lambda m: {**m, "arms": {"next": {**m["arms"]["next"], "effort": "low"}}}),
                           ("other parent", lambda m: {**m, "parent_manifest_sha256": "0" * 64})):
            with self.subTest(next_results=name):
                manifest.write_text(json.dumps(edit(json.loads(sealed))))
                with self.assertRaisesRegex(ValueError, "not chained from these results"):
                    lab.report(path, results, self.root / "next")
        manifest.write_text(sealed)
        report = lab.report(path, results, self.root / "next")
        self.assertEqual((report["next_run_manifest"]["state"], report["next_run_manifest"]["stage1_cells_chained"]), ("sealed", 2))
        self.assertIn("- **Stage 2:** sealed; 2 of 2", (results / "report.md").read_text())
        self.assertEqual(report["verdict"]["run_binding"], "sealed")
        ledger = (self.root / "next" / "dispatch.jsonl").read_text()
        for name, row, message in (("another digest", {"manifest_sha256": "0" * 64}, "do not match their own seal"),
                                   ("no digest", {}, "unbound from their own seal")):
            with self.subTest(stage2_ledger=name):  # stage 2 holds to the same seal rules as stage 1
                (self.root / "next" / "dispatch.jsonl").write_text(ledger + json.dumps({"cell": "X-r01-next", "dispatched_at": lab._now(), **row}) + "\n")
                with self.assertRaisesRegex(ValueError, message):
                    lab.report(path, results, self.root / "next")
        (self.root / "next" / "dispatch.jsonl").write_text(ledger)
        set_ = json.loads(path.read_text())
        path.write_text(json.dumps({**set_, "seed": set_["seed"] + 1}))  # a changed set, through report and chain themselves
        with self.assertRaisesRegex(ValueError, "different set"):
            lab.report(path, results, None)
        with self.assertRaisesRegex(ValueError, "different set"):
            lab.chain(path, results, self.root / "stage2-seed")
        path.write_text(json.dumps(set_))  # chain picks stage 2's arm from compare: a compare moved since the seal is refused
        path.write_text(json.dumps({**set_, "compare": {**set_["compare"], "reference": set_["compare"]["candidate"]}}))
        with self.assertRaisesRegex(ValueError, "comparison changed"):
            lab.chain(path, results, self.root / "stage2-other")
        path.write_text(json.dumps(set_))
        existing = json.loads((stage2 / "replay-set.json").read_text())
        (stage2 / "replay-set.json").write_text(json.dumps({**existing, "tasks": []}))  # a set a stage 2 may already be sealed on
        with self.assertRaisesRegex(ValueError, "different chain set already exists"):
            lab.chain(path, results, stage2)
        for state, phrase in (("absent", "nothing binds the attempts"), ("sealed-late", "sealed only after some attempts"),
                              ("unbound", "the seal binds none of them")):
            text = lab.summary({**result, "run_manifest": {"state": state, "compare_changed": None}}, "medium", "high", 2)
            self.assertIn(phrase, text)
        legacy = {k: v for k, v in result.items() if k not in ("run_manifest", "arm_accounting")}  # a v6 report written by 1.7.0
        text = lab.summary(legacy, "medium", "high", 2)
        self.assertNotIn("Run binding", text)
        self.assertNotIn("Cells,", text)

    def test_a_stage_1_from_before_the_seal_chains_and_reports_and_stage_2_keeps_its_agent_command(self):
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path, results = out / "replay-set.json", self.root / "results"
        lab.run(path, results, replicates=1, jobs=2, max_calls=2, max_usd=10, stop_usd=1)
        (results / "run-manifest.json").unlink()  # a stage 1 run by 1.7.0: no manifest, no digests in its ledger
        rows = [json.loads(line) for line in (results / "dispatch.jsonl").read_text().splitlines()]
        (results / "dispatch.jsonl").write_text("".join(json.dumps({k: v for k, v in r.items() if k != "manifest_sha256"}) + "\n" for r in rows))
        stage2, nxt = self.root / "stage2-legacy", self.root / "next-legacy"
        lab.chain(path, results, stage2)
        lab.run(stage2 / "replay-set.json", nxt, replicates=1, jobs=2, max_calls=2, max_usd=10, stop_usd=1)
        lab.sensitivity(path, 2)
        report = lab.report(path, results, nxt)
        self.assertEqual((report["verdict"]["run_binding"], report["verdict"]["next_run_binding"]), ("absent", "sealed"))
        manifest = nxt / "run-manifest.json"  # a stage 2 whose agent command differs from stage 1's set, its ledger consistent
        sealed, ledger = manifest.read_text(), (nxt / "dispatch.jsonl").read_text()
        edited = json.dumps({**json.loads(sealed), "agent_command_sha256": "0" * 64})
        manifest.write_text(edited)
        (nxt / "dispatch.jsonl").write_text(ledger.replace(lab.hashlib.sha256(sealed.encode()).hexdigest(), lab.hashlib.sha256(edited.encode()).hexdigest()))
        with self.assertRaisesRegex(ValueError, "another agent command"):
            lab.report(path, results, nxt)
        manifest.unlink()  # a stage 2 that lost the manifest its ledger names
        with self.assertRaisesRegex(ValueError, "lost the manifest"):
            lab.report(path, results, nxt)

    def test_report_guard_single_look_and_refused_rows_through_the_real_cells(self):
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path, results = out / "replay-set.json", self.root / "results"

        def refusing(config, task, arm, rep, out_, timeout):  # one call the provider refused, as the real runner writes it
            cid = lab.replay_eval.cell_id(task, arm, rep)
            if cid.endswith("-r02-medium"):
                (out_ / f"{cid}.runner.json").write_text(json.dumps({"problem": "native-error-rate-limit", "cost_usd": 0.0,
                                                                     "usage": {"input_tokens": 0, "output_tokens": 0}}))
                row = {"schema": "007-framework/replay-cell/v1", "task": task["id"], "arm": arm, "replicate": rep, "valid": False,
                       "accepted": False, "failure_class": "agent-exit", "cost_usd": "unmeasured", "acceptance_outcomes": "unavailable",
                       "runner_receipt_sha256": lab._sha256(out_ / f"{cid}.runner.json")}
                (out_ / f"{cid}.json").write_text(json.dumps(row))
                return row
            return lab.replay_eval.execute_cell(config, task, arm, rep, out_, timeout)
        state = lab.run(path, results, replicates=2, jobs=2, max_calls=9, max_usd=10, stop_usd=1, execute=refusing)
        self.assertEqual((state["stop"], state["refused_per_arm"]), ("rate-limit", {"medium": 1, "high": 0}))
        self.assertIn(next(r["cell"] for r in lab.load_cells(results) if r.get("failure_class") == "provider-rate-limit"),
                      lab.chain(path, results, self.root / "stage2")["broken"])  # 1.8.1 review item 5
        lab.sensitivity(path, 2)
        with self.assertRaisesRegex(ValueError, "planned replicates"):
            lab.report(path, results, None, missing_data_guard_reserve=1.0)
        with self.assertRaisesRegex(ValueError, "beyond the 1 planned"):
            lab.report(path, results, None, missing_data_guard_reserve=1.0, planned_replicates=1)
        config = json.loads(path.read_text())
        task = config["tasks"][0]["id"]
        reach = {task: [k for k in json.loads((out / "tasks" / task / "hidden.json").read_text()) if k != "__module__"]}
        with (results / ".run.lock").open("a") as held:  # a run is active: the single look waits
            lab.fcntl.flock(held, lab.fcntl.LOCK_EX)
            with self.assertRaisesRegex(ValueError, "a run is active"):
                lab.report(path, results, None, single_look=True)
            lab.fcntl.flock(held, lab.fcntl.LOCK_UN)
        result = lab.report(path, results, None, single_look=True, missing_data_guard_reserve=1.0, frozen_reach=reach, planned_replicates=3)
        guard = result["missing_data_guard"]
        self.assertEqual(guard["missing_data"]["planned"], 6)  # the plan, not what was attempted: 2 cells never dispatched
        self.assertEqual(guard["missing_data"]["imputed_in_L2"], {"absent": 2, "refused": 1})
        self.assertEqual((result["reach_frozen"], result["frozen_reach_sha256"] is not None, result["verdict"]["refused_unequal"]), (True, True, True))
        self.assertIn("Missing-data guard", (results / "report.md").read_text())
        self.assertIn("1 attempts refused by the provider", (results / "report.md").read_text())
        self.assertEqual(json.loads((results / "LOOK.json").read_text())["report_sha256"], lab._sha256(results / "report.json"))
        with self.assertRaisesRegex(ValueError, "single look"):
            lab.report(path, results, None)
        self.assertEqual(lab.run(path, results, replicates=3, jobs=1, max_calls=9, max_usd=10, stop_usd=1)["stop"], "looked")

    def test_chain_skips_a_cell_with_no_candidate_patch(self):
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path, results = out / "replay-set.json", self.root / "results"
        first = json.loads(path.read_text())["tasks"][0]["id"]

        def failing(config, task, arm, rep, out_, timeout):
            if task["id"] == first and arm == "high":
                raise RuntimeError("snapshot refused")
            return lab.replay_eval.execute_cell(config, task, arm, rep, out_, timeout)
        state = lab.run(path, results, replicates=1, jobs=1, max_calls=99, max_usd=10, stop_usd=1, execute=failing)
        self.assertEqual(state["invalid"], 1)
        chained = lab.chain(path, results, self.root / "stage2-skip")
        self.assertIn(f"{first}-r01-high", chained["broken"])

    def test_an_arm_without_a_valid_cell_is_reported_with_its_reason_instead_of_raising(self):
        # 1.11.0: the median reasoning tokens of an empty arm raised statistics.StatisticsError and no report was written
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path = out / "replay-set.json"
        lab.sensitivity(path, 2)
        for dead in ("medium", "high", None):
            with self.subTest(dead=dead):
                results = self.root / f"results-{dead}"

                def failing(config, task, arm, rep, out_, timeout):
                    if arm == dead:
                        raise RuntimeError("snapshot refused")
                    return lab.replay_eval.execute_cell(config, task, arm, rep, out_, timeout)
                lab.run(path, results, replicates=2, jobs=1, max_calls=9, max_usd=10, stop_usd=1, max_invalid=9, execute=failing)
                result = lab.report(path, results, None, missing_data_guard_reserve=1.0, planned_replicates=2)
                tier, text = result["verdict"], (results / "report.md").read_text()
                if dead is None:  # both arms valid: the new label is empty and the verdict is computed as before
                    self.assertEqual(tier["arms_without_valid_cells"], [])
                    self.assertNotIn("No comparison", text)
                    continue
                self.assertEqual({k: tier[k] for k in ("arms_without_valid_cells", "same_change_reachable", "thesis", "time", "durability", "rework_ok")},
                                 {"arms_without_valid_cells": [dead], "same_change_reachable": "NO-INFORMATION", "thesis": "UNPROVEN",
                                  "time": "NO-INFORMATION", "durability": "NO-INFORMATION", "rework_ok": None})
                self.assertIsNone(result["median_reasoning_tokens"][dead])
                self.assertEqual(result["missing_data_guard"]["verdict"], "NO-INFORMATION")
                self.assertIn(f"**No comparison:** `{dead}` has no valid cell", text)
                self.assertIn("none (no valid cell)", text)
        with self.assertRaisesRegex(ValueError, "no valid cells to report"):  # no arm at all: still an explicit refusal
            results = self.root / "results-all"
            lab.run(path, results, replicates=1, jobs=1, max_calls=9, max_usd=10, stop_usd=1, max_invalid=9,
                    execute=lambda *a: (_ for _ in ()).throw(RuntimeError("snapshot refused")))
            lab.report(path, results, None)

    def test_report_uses_the_shared_classifier_for_receipt_like_arm_names(self):
        self.config["arms"]["high.runner"] = self.config["arms"].pop("high")
        self.config["compare"]["reference"] = "high.runner"
        output = self.root / "suffix-lab"
        lab.mine(self.config, output, 1)
        path, results = output / "replay-set.json", self.root / "suffix-results"
        state = lab.run(path, results, replicates=1, jobs=1, max_calls=2, max_usd=10, stop_usd=1)
        self.assertEqual((state["calls"], state["invalid"]), (2, 0))
        lab.sensitivity(path, 1)
        report = lab.report(path, results, None)
        self.assertEqual(report["orphan_receipts"], [])

    def test_chain_creates_private_outputs_and_preserves_existing_directory_permissions(self):
        config_path = self.root / "chain-input.json"
        config_path.write_text(json.dumps({"repos": {"synthetic": str(self.repo)}, "arms": self.config["arms"], "tasks": [],
                                           "compare": {"reference": "high"}}))
        (self.root / "pairs.json").write_text("{}")
        previous = os.umask(0o022)
        try:
            for existing, expected in ((False, 0o700), (True, 0o755)):
                with self.subTest(existing=existing):
                    output = self.root / ("existing-output" if existing else "new-output")
                    if existing:
                        output.mkdir(mode=0o755)
                    self.assertEqual(lab.chain(config_path, self.root / "empty-results", output)["tasks"], 0)
                    self.assertEqual(output.stat().st_mode & 0o777, expected)
        finally:
            os.umask(previous)

    def test_an_invalid_cell_leaves_the_report_and_is_named(self):
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path, results = out / "replay-set.json", self.root / "results"
        lab.run(path, results, replicates=2, jobs=2, max_calls=4, max_usd=10, stop_usd=1)
        lab.sensitivity(path, 2)
        cell = next(results.glob("*-r01-medium.json"))
        cell.write_text(json.dumps({**json.loads(cell.read_text()), "valid": False, "cost_usd": "unmeasured", "usage": "unmeasured"}))
        result = lab.report(path, results, None)
        self.assertEqual(result["excluded_invalid"], [cell.stem])
        self.assertEqual((result["contrast"]["medium"]["units"], result["contrast"]["high"]["units"]), (1, 2))

    def test_the_report_accounts_for_every_planned_cell_per_arm(self):
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path, results = out / "replay-set.json", self.root / "results"
        config = json.loads(path.read_text())
        tasks, arms = config["tasks"], sorted(config["arms"])
        lab.run(path, results, replicates=1, jobs=2, max_calls=99, max_usd=10, stop_usd=1)
        lab.sensitivity(path, 2)
        orphan = lab.replay_eval.cell_id(tasks[0], arms[0], 2)  # replicate 2 dispatched, its controller gone before a result
        with (results / "dispatch.jsonl").open("a") as handle:
            handle.write(json.dumps({"cell": orphan, "dispatched_at": lab._now()}) + "\n")
        report = lab.report(path, results, None)
        self.assertEqual((report["arm_accounting"]["history"], report["arm_accounting"]["unread_cells"]), ("complete", 0))
        accounting = report["arm_accounting"]["arms"]
        self.assertEqual(sorted(accounting), arms)
        for arm, a in accounting.items():
            with self.subTest(arm=arm):
                self.assertEqual(a["planned"], 2 * len(tasks))
                self.assertEqual(a["valid"] + sum(a["invalid"].values()), len(tasks))
                self.assertEqual(a["no_result"], int(arm == arms[0]))
                self.assertEqual(a["not_dispatched"] + a["no_result"] + a["valid"] + sum(a["invalid"].values()), a["planned"])
                self.assertLessEqual(a["accepted"], a["valid"])
                self.assertIn(f"- **Cells, `{arm}`:** {2 * len(tasks)} planned", (results / "report.md").read_text())

    def test_accounting_reads_receipts_chain_ids_damaged_rows_and_an_unreadable_ledger(self):
        results = self.root / "acct"
        results.mkdir()
        config = {"tasks": [{"id": "A"}, {"id": "B"}], "arms": {"low": {}, "high": {}}}
        rows = [{"cell": "A-r01-low", "valid": True, "accepted": True},
                {"cell": "A-r01-high", "valid": False, "failure_class": None},  # 1.7.0 accepted rows without replicate or class
                {"cell": "B-r01-high", "valid": False, "failure_class": "timeout"}]
        a = lab.arm_accounting(config, results, rows, {"B-r02-low": {}})  # no ledger: a receipt alone shows the attempt
        self.assertEqual((a["history"], a["unread_cells"]), ("absent", 0))
        self.assertEqual(a["arms"]["low"], {"planned": 4, "not_dispatched": 2, "no_result": 1, "valid": 1, "accepted": 1, "invalid": {}, "refused": 0})
        self.assertEqual(a["arms"]["high"]["invalid"], {"timeout": 1, "unknown": 1})
        chain = {"tasks": [{"id": "T-r100-low-next"}], "arms": {"next": {}}}  # a stage-2 task id carries its parent's replicate
        a = lab.arm_accounting(chain, results, [{"cell": "T-r100-low-next-r01-next", "valid": True, "accepted": False}], {})
        self.assertEqual(a["arms"]["next"]["planned"], 1)
        (results / "dispatch.jsonl").write_text("not json\n")  # a damaged line
        self.assertEqual(lab.arm_accounting(config, results, rows, {})["history"], "damaged")
        (results / "dispatch.jsonl").unlink()
        (results / "dispatch.jsonl").mkdir()  # unreadable ledger: the report still reads, and says so
        self.assertEqual(lab.arm_accounting(config, results, rows, {})["history"], "unreadable")
        huge = {"cell": "A-r" + "9" * 5000 + "-low", "valid": True, "accepted": True}  # unread, never millions of planned cells
        self.assertEqual(lab.arm_accounting(config, self.root, [huge], {})["unread_cells"], 1)

    def test_report_with_and_without_aa_and_the_verdict_unchanged_by_the_copy(self):
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path = out / "replay-set.json"
        lab.sensitivity(path, 2)
        plain, twin = self.root / "plain", self.root / "twin"
        lab.run(path, plain, replicates=2, jobs=2, max_calls=99, max_usd=99, stop_usd=1)
        with mock.patch.object(lab.replay_eval.tempfile, "mkdtemp", wraps=tempfile.mkdtemp) as made:
            state = lab.run(path, twin, replicates=2, jobs=2, max_calls=99, max_usd=99, stop_usd=1, aa="high")
        tasks = len(json.loads(path.read_text())["tasks"])
        self.assertEqual((state["stop"], state["calls"], state["cells"]), (None, 6 * tasks, 6 * tasks))
        workspaces = [c.kwargs.get("prefix", "") for c in made.call_args_list if c.kwargs.get("prefix", "").startswith("007-") and "acceptance" not in c.kwargs["prefix"]]
        self.assertEqual(len(workspaces), 6 * tasks)
        # 1.11.0: every cell, the copy's included, works under its own salted token: no arm name, effort word or A/A suffix
        self.assertEqual([w for w in workspaces if not re.fullmatch(r"007-\d{16}-", w)], [])
        self.assertEqual(len(set(workspaces)), 6 * tasks)
        without, with_ = lab.report(path, plain, None), lab.report(path, twin, None)
        # the verdict reads the set's arms only: the copy changes none of it
        for key in ("same_change_reachable", "durability", "margin", "refused_unequal"):
            self.assertEqual(without["verdict"][key], with_["verdict"][key])
        self.assertEqual(without["reachable_behaviour"], with_["reachable_behaviour"])
        self.assertEqual(without["unseen_behaviour"], with_["unseen_behaviour"])
        self.assertEqual(without["excluded_invalid"], with_["excluded_invalid"])
        self.assertEqual((without["contrast"]["high"]["units"], without["contrast"]["high"]["accepted"]),
                         (with_["contrast"]["high"]["units"], with_["contrast"]["high"]["accepted"]))
        self.assertEqual((without["aa"], without["verdict"]["aa_status"], without["verdict"]["aa_qualified"]), (None, "absent", False))
        self.assertIn("no A/A cells, so this verdict carries no measured noise floor and is not A/A-qualified", (plain / "report.md").read_text())
        aa = with_["aa"]
        self.assertEqual((aa["arm"], aa["label"], aa["rejects_equality"]), ("high", "high-aa", False))
        self.assertEqual(aa["discordance"]["pairs"], 2 * tasks)
        self.assertEqual((aa["discordance"]["discordant"], aa["discordance"]["missing_pairs"], aa["missing_cells"]), (0, 0, {}))
        self.assertEqual((with_["verdict"]["aa_status"], with_["verdict"]["aa_qualified"]), ("too-few-tasks", False))  # under 8 tasks
        self.assertEqual(with_["arm_accounting"]["arms"]["high-aa"]["valid"], 2 * tasks)
        self.assertEqual(with_["arm_accounting"]["unread_cells"], 0)
        text = (twin / "report.md").read_text()
        self.assertIn("- **A/A, `high` twice:** not A/A-qualified: fewer than 8 tasks", text)
        self.assertIn(f"acceptance differs in 0 of {2 * tasks} pairs", text)
        self.assertIn(f"- **Cells, `high-aa`:** {2 * tasks} planned", text)
        # a third replicate planned and never dispatched: its pairs are missing, not absent from the count (review #5)
        planned = lab.report(path, twin, None, planned_replicates=3)["aa"]
        self.assertEqual((planned["discordance"]["pairs"], planned["discordance"]["missing_pairs"]), (2 * tasks, tasks))
        self.assertEqual(len(planned["missing_cells"]["absent"]), 2 * tasks)
        self.assertEqual((planned["planned_replicates"], with_["aa"]["planned_replicates"]), (3, None))
        with self.assertRaisesRegex(ValueError, "beyond the 1 planned"):
            lab.report(path, twin, None, planned_replicates=1)
        chained = lab.chain(path, twin, self.root / "stage2-twin")  # the copies are no part of the contrast stage 2 serves
        self.assertEqual((chained["tasks"], chained["aa_not_chained"]), (4 * tasks, 2 * tasks))
        self.assertNotIn("aa_not_chained", lab.chain(path, plain, self.root / "stage2-plain"))

    def test_nothing_the_agent_sees_names_its_arm(self):
        """1.11.0: the agent's cwd, argv, environment, workspace names and prompt carry no arm name, effort word or A/A marker, in
        stage 1 (A/A copy included) and in stage 2, whose task ids name stage-1 cells. Only the effort flag itself differs."""
        (self.root / "agent.py").write_text(CAPTURE_AGENT)
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path, results, stage2, capture = out / "replay-set.json", self.root / "results", self.root / "stage2", self.root / "capture"
        capture.mkdir()
        lab.sensitivity(path, 2)
        inherited = {**os.environ, "LAB_CAPTURE": str(capture)}
        with mock.patch.dict(os.environ, {"LAB_CAPTURE": str(capture)}):
            first = lab.run(path, results, replicates=1, jobs=2, max_calls=99, max_usd=99, stop_usd=1, aa="high")
            again = lab.run(path, results, replicates=2, jobs=2, max_calls=99, max_usd=99, stop_usd=1, aa="high")  # a resume
            lab.chain(path, results, stage2)
            last = lab.run(stage2 / "replay-set.json", self.root / "later", replicates=1, jobs=2, max_calls=99, max_usd=99, stop_usd=1)
        self.assertEqual([s["stop"] for s in (first, again, last)], [None, None, None])
        captures = [json.loads(p.read_text()) for p in sorted(capture.iterdir())]
        self.assertEqual(len(captures), first["calls"] + again["calls"] + last["calls"])
        self.assertEqual(len({json.dumps(c["env"], sort_keys=True) for c in captures}), 1)  # one environment for all; never printed
        roots = sorted({str(p) for base in (self.root, Path(tempfile.gettempdir())) for p in (base, base.resolve())}, key=len, reverse=True)
        words = ("medium", "high", "xhigh", "low", "aa", "next")  # the arms, effort words, the A/A suffix and stage 2's arm
        leaks = []
        for seen in captures:
            self.assertRegex(Path(seen["cwd"]).name, r"^007-\d{16}-")
            self.assertRegex(Path(seen["argv"][2]).name, r"^\d{16}\.runner\.json$")
            fields = {"cwd": seen["cwd"], "argv": seen["argv"][:3] + seen["argv"][4:],  # argv[3] is {effort}: the treatment itself
                      "env": {k: v for k, v in seen["env"].items() if inherited.get(k) != v},
                      "tree": [name for name in seen["tree"] if name.split(os.sep)[0] != ".git"],  # git's own hex object names
                      "stdin": seen["stdin"], "prompt_file": seen["prompt_file"]}
            for field, value in fields.items():
                text = json.dumps(value)
                for root in roots:
                    text = text.replace(root, "/")
                leaks += [(field, w) for w in words if re.search(rf"(?<![A-Za-z0-9_]){w}(?![A-Za-z0-9_])", text, re.I)]
        self.assertEqual(sorted(set(leaks)), [])
        # the human side keeps the real names; each cell records the token its agent saw, all from the one salt the seal holds
        tokens = {Path(seen["argv"][2]).name.removesuffix(".runner.json") for seen in captures}
        for directory in (results, self.root / "later"):
            salt = json.loads((directory / "run-manifest.json").read_text())["blind_salt"]
            self.assertRegex(salt, r"^[0-9a-f]{32}$")
            self.assertEqual(list((directory / ".blind").iterdir()), [])  # every receipt moved to its cell's name
            for cell in lab.load_cells(directory):
                self.assertTrue((directory / f"{cell['cell']}.runner.json").is_file())
                self.assertEqual(cell["blind_token"], lab.replay_eval.blind_token(salt, cell["cell"]))
                tokens.discard(cell["blind_token"])
        self.assertEqual(tokens, set())
        report = lab.report(path, results, self.root / "later")
        self.assertEqual(sorted(report["arm_accounting"]["arms"]), ["high", "high-aa", "medium"])
        self.assertEqual(report["aa"]["label"], "high-aa")

    def test_a_run_sealed_before_1_11_resumes_with_its_labelled_paths(self):
        """A manifest without a salt (1.10 and before) keeps labelled workspaces on resume: one run never mixes the two."""
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path, results = out / "replay-set.json", self.root / "results"
        lab.sensitivity(path, 2)
        with mock.patch.object(lab.secrets, "token_hex", return_value=None):
            self.assertIsNone(lab.run(path, results, replicates=1, jobs=2, max_calls=99, max_usd=99, stop_usd=1)["stop"])
        sealed = results / "run-manifest.json"
        old = sealed.read_bytes()
        manifest = json.loads(old)
        del manifest["blind_salt"]  # the manifest exactly as 1.10 wrote it, and the ledger bound to it
        sealed.write_text(json.dumps(manifest, indent=1) + "\n")
        ledger = results / "dispatch.jsonl"
        ledger.write_text(ledger.read_text().replace(hashlib.sha256(old).hexdigest(), lab._sha256(sealed)))
        with mock.patch.object(lab.replay_eval.tempfile, "mkdtemp", wraps=tempfile.mkdtemp) as made:
            state = lab.run(path, results, replicates=2, jobs=2, max_calls=99, max_usd=99, stop_usd=1)
        self.assertEqual((state["stop"], state["calls"]), (None, state["cells"] // 2))
        workspaces = [c.kwargs["prefix"] for c in made.call_args_list if c.kwargs.get("prefix", "").startswith("007-")
                      and "acceptance" not in c.kwargs["prefix"]]
        self.assertEqual(sorted(w.split("-")[-3] for w in workspaces), sorted(["high", "medium"] * (state["cells"] // 4)))
        self.assertFalse([cell for cell in lab.load_cells(results) if "blind_token" in cell])
        self.assertFalse((results / ".blind").exists())
        self.assertEqual(lab.report(path, results, None)["run_manifest"]["state"], "sealed")

    def test_oracle_health_is_blind_in_status_never_moves_the_verdict_and_holds_until_acknowledged(self):
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path, results = out / "replay-set.json", self.root / "results"
        lab.sensitivity(path, 2)
        seen, real = [], lab.replay_eval.execute_cell

        def watched(*args, **kwargs):  # status between cells, while the run is in flight
            row = real(*args, **kwargs)
            seen.append(json.dumps(lab.status(path, results)))
            return row
        lab.run(path, results, replicates=2, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=watched)
        tasks = len(json.loads(path.read_text())["tasks"])
        self.assertEqual(len(seen), 4 * tasks)
        for text in seen:  # pooled only: no arm, task, cell or per-arm count
            self.assertNotIn("medium", text)
            self.assertNotIn("high", text)
            self.assertNotIn("per_arm", text)
            self.assertNotIn(json.loads(path.read_text())["tasks"][0]["id"], text)
        healthy = lab.report(path, results, None)
        health = healthy["oracle_health"]
        self.assertEqual((health["status"], health["alarms"], health["cells"]), ("no-alarm", [], 4 * tasks))
        self.assertEqual(set(health["per_arm"]), {"medium", "high"})  # per arm only in the report
        self.assertEqual((healthy["verdict"]["oracle_status"], healthy["verdict"]["oracle_suspect"]), ("no-alarm", False))
        self.assertIn("- **Oracle health:** no alarm;", (results / "report.md").read_text())
        files = [p for p in results.glob("*.json") if lab.replay_eval.is_cell_id(p.stem) and not p.name.endswith(".runner.json")]
        original = {p: p.read_text() for p in files}
        verdict = lambda r: {k: v for k, v in r["verdict"].items() if not k.startswith("oracle_")}

        def rewrite(change):
            for p, text in original.items():
                row = json.loads(text)
                change(row)
                p.write_text(json.dumps(row))
        rewrite(lambda row: row.pop("acceptance"))  # cells from before any health data: the verdict and report read as before
        old = lab.report(path, results, None)
        self.assertEqual((verdict(old), old["oracle_health"]["status"], old["verdict"]["oracle_suspect"]), (verdict(healthy), "unmeasured", False))
        self.assertNotIn("Oracle-suspect", (results / "report.md").read_text())

        def broken(row):  # every grade an internal error that a pre-1.10.1 set reads as a rejection: same verdict inputs
            row["acceptance"][0]["exit"] = 2
        rewrite(broken)
        suspect = lab.report(path, results, None)
        self.assertEqual(verdict(suspect), verdict(healthy))  # an alarm never changes a verdict
        self.assertIn("oracle-errors", suspect["oracle_health"]["alarms"])
        self.assertEqual((suspect["verdict"]["oracle_status"], suspect["verdict"]["oracle_suspect"]), ("oracle-suspect", True))
        self.assertIn("**Oracle-suspect:** an oracle alarm is open", (results / "report.md").read_text())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(lab.main(["status", "--set", str(path), "--results", str(results)]), 1)
        with self.assertRaisesRegex(ValueError, "needs a reason"):
            lab.status(path, results, " ")
        self.assertEqual(lab.status(path, results, "the grader was fixed and the run is discarded")["oracle_health"]["status"], "acknowledged")
        acked = lab.report(path, results, None)
        self.assertEqual((verdict(acked), acked["verdict"]["oracle_status"], acked["verdict"]["oracle_suspect"]), (verdict(healthy), "acknowledged", False))
        self.assertIn("alarm acknowledged by a person", (results / "report.md").read_text())
        with self.assertRaisesRegex(ValueError, "no open oracle alarm"):
            lab.status(path, results, "again")
        first = files[0]
        row = json.loads(first.read_text())
        row["acceptance"][0]["exit"] = 137  # any change to the counts voids the acknowledgement
        first.write_text(json.dumps(row))
        self.assertEqual(lab.report(path, results, None)["verdict"]["oracle_status"], "oracle-suspect")
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(lab.main(["status", "--set", str(path), "--results", str(results)]), 1)
        self.assertEqual(json.loads(printed.getvalue())["oracle_health"]["status"], "oracle-suspect")

    def test_the_report_reads_the_declared_margin_and_says_it_in_plain_words(self):
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path, results = out / "replay-set.json", self.root / "results"
        lab.run(path, results, replicates=1, jobs=2, max_calls=4, max_usd=10, stop_usd=1)
        lab.sensitivity(path, 2)
        self.assertEqual(lab.report(path, results, None)["verdict"]["margin"], .03)
        self.assertIn("margin 3 points", (results / "report.md").read_text())
        config = json.loads(path.read_text())
        path.write_text(json.dumps({**config, "compare": {**config["compare"], "margin": .1}}))
        changed = lab.report(path, results, None)
        self.assertEqual((changed["verdict"]["margin"], changed["run_manifest"]["state"], changed["run_manifest"]["compare_changed"]), (.1, "sealed", True))
        self.assertIn("margin 10 points", (results / "report.md").read_text())
        self.assertIn("the comparison or margin changed after the seal", (results / "report.md").read_text())
        path.write_text(json.dumps({**config, "compare": {**config["compare"], "margin": .5}}))
        with self.assertRaises(ValueError):
            lab.report(path, results, None)

    def test_a_task_past_the_outcome_cap_is_never_mined(self):
        candidate = next(c for c in lab.pool(self.config) if c["sha"] == self.sha)
        with mock.patch.object(lab.replay_eval, "MAX_ACCEPT_OUTCOMES", 5):  # 5 hidden tests + "__module__"
            self.assertEqual(lab.oracle(self.config, candidate), "too-many-hidden-tests")
        with mock.patch.object(lab.replay_eval, "MAX_ACCEPT_OUTCOMES", 6):
            self.assertEqual(len(lab.oracle(self.config, candidate)["hidden"]), 5)

    def test_the_reference_is_graded_the_way_a_candidate_is(self):
        """The miner's controls graded the reference at its own tree; a candidate is graded as base + patch behind reset_to_base.
        A commit that renames a Go test file passed the first and no patch could pass the second (LZ4-12377E5F, 2026-11-15)."""
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        task = json.loads((out / "replay-set.json").read_text())["tasks"][0]
        self.assertTrue(lab.reference_passes_as_candidate(self.config, out, task))
        self.assertFalse(lab.reference_passes_as_candidate(self.config, out, {**task, "reset_to_base": ["calc.py"]}))  # the fix itself is reset

    def test_a_grader_failure_while_mining_is_not_a_failing_reference(self):
        out = self.root / "lab"
        harness = lambda *a, **k: ([{"exit": 2}], False)
        with mock.patch.object(lab.replay_eval, "acceptance", side_effect=harness):
            self.assertEqual(lab.mine(self.config, out, 2), 0)
        drops = {json.loads(l)["sha"]: json.loads(l).get("drop") for l in (out / "mine.jsonl").read_text().splitlines()}
        self.assertTrue(drops[self.sha].startswith("AcceptanceHarnessError"), drops)  # with its message when the set keeps diagnostic text
        self.assertEqual(list((out / "tasks").glob("*")), [])

    def test_a_reference_whose_suite_hangs_fails_as_a_candidate(self):
        out = self.root / "lab"
        with mock.patch.object(lab.replay_eval, "acceptance", side_effect=lambda *a, **k: ([{"exit": 3}], False)):
            self.assertEqual(lab.mine(self.config, out, 2), 0)
        drops = {json.loads(l)["sha"]: json.loads(l).get("drop") for l in (out / "mine.jsonl").read_text().splitlines()}
        self.assertEqual(drops[self.sha], "reference-fails-as-candidate")

    def test_a_failing_next_reference_is_named_as_such(self):
        out = self.root / "lab"
        only_next = lambda config, out_, task: not task["id"].endswith("-next")
        with mock.patch.object(lab, "reference_passes_as_candidate", side_effect=only_next):
            self.assertEqual(lab.mine(self.config, out, 2), 0)
        drops = {json.loads(l)["sha"]: json.loads(l).get("drop") for l in (out / "mine.jsonl").read_text().splitlines()}
        self.assertEqual(drops[self.sha], "next-reference-fails-as-candidate")
        self.assertEqual(list((out / "tasks").glob("*")), [])

    def test_a_task_whose_reference_fails_as_a_candidate_is_dropped(self):
        out = self.root / "lab"
        with mock.patch.object(lab, "reference_passes_as_candidate", return_value=False):
            self.assertEqual(lab.mine(self.config, out, 2), 0)
        drops = {json.loads(l)["sha"]: json.loads(l).get("drop") for l in (out / "mine.jsonl").read_text().splitlines()}
        self.assertEqual(drops[self.sha], "reference-fails-as-candidate")
        self.assertEqual(list((out / "tasks").glob("*")), [])

    def test_a_test_file_the_commit_deleted_does_not_drop_the_task(self):
        candidate = next(c for c in lab.pool(self.config) if c["sha"] == self.sha)
        built = lab.oracle(self.config, {**candidate, "tests": candidate["tests"] + ["tests/test_gone.py"]})
        self.assertEqual((len(built["hidden"]), built["hidden_files"]), (5, candidate["tests"]))

    def test_a_cell_the_runner_refused_before_its_receipt_is_invalid_not_a_broken_directory(self):
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path, results = out / "replay-set.json", self.root / "results"
        lab.run(path, results, replicates=1, jobs=2, max_calls=2, max_usd=10, stop_usd=1)
        lab.sensitivity(path, 2)
        cell = json.loads(next(results.glob("*-r01-high.json")).read_text())
        (results / "X-r01-high.json").write_text(json.dumps({**cell, "task": cell["task"], "valid": False, "cost_usd": "unmeasured", "usage": "unmeasured",
                                                             "runner_receipt_sha256": "unmeasured", "acceptance_outcomes": "unavailable"}))
        result = lab.report(path, results, None)
        self.assertEqual(result["excluded_invalid"], ["X-r01-high"])

    def test_an_unreadable_outcome_counts_as_no_pass_and_is_named(self):
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        path, results = out / "replay-set.json", self.root / "results"
        lab.run(path, results, replicates=1, jobs=2, max_calls=2, max_usd=10, stop_usd=1)
        lab.sensitivity(path, 2)
        cell = next(results.glob("*-r01-high.json"))
        cell.write_text(json.dumps({**json.loads(cell.read_text()), "acceptance_outcomes": "unavailable"}))
        result = lab.report(path, results, None)
        self.assertEqual(result["unreadable_outcomes"], [cell.stem])
        self.assertEqual(result["excluded_invalid"], [])

    def test_the_source_repository_is_never_written(self):
        head = git(self.repo, "rev-parse", "HEAD")
        refs = git(self.repo, "for-each-ref")
        self.test_a_latent_defect_surfaces_in_the_next_change()
        self.assertEqual((git(self.repo, "rev-parse", "HEAD"), git(self.repo, "for-each-ref"), git(self.repo, "status", "--short")), (head, refs, ""))

    def test_sensitivity_catches_the_missing_cap_only_when_b_lands(self):
        out = self.root / "lab"
        lab.mine(self.config, out, 2)
        result = lab.sensitivity(out / "replay-set.json", 2)
        self.assertEqual((len(result["conformant"]), result["errors"]), (1, 0), result)
        config = json.loads((out / "replay-set.json").read_text())
        task, base = config["tasks"][0], "def add(a, b):\n    return a - b\n"
        pair = json.loads((out / "pairs.json").read_text())[task["id"]]
        partial = "diff --git a/calc.py b/calc.py\n--- a/calc.py\n+++ b/calc.py\n" + "".join(list(difflib.unified_diff(base.splitlines(True), PARTIAL.splitlines(True), n=0))[2:])
        real_next = git(self.repo, "diff", pair["next"]["base"], pair["next"]["accepted"])
        self.assertEqual(lab.probe(config, out, task["id"], partial, real_next), (True, None))  # B edits the lines the partial patch left out


class CRLFPatches(unittest.TestCase):
    def test_a_patch_with_crlf_lines_reads_and_applies_intact(self, apply_env=None):
        with tempfile.TemporaryDirectory() as d:
            repo, tree = Path(d) / "repo", Path(d) / "tree"
            repo.mkdir()
            git(repo, "init", "-q")
            (repo / "a.txt").write_bytes(b"x\r\ny\r\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "base")
            (repo / "a.txt").write_bytes(b"x\r\nz\r\n")
            patch = Path(d) / "change.patch"
            patch.write_bytes(subprocess.run(["git", "-C", str(repo), "diff", "--binary"], capture_output=True, check=True).stdout)
            self.assertIn(b"\r", patch.read_bytes())
            git(repo, "checkout", "-q", "--", "a.txt")
            shutil.copytree(repo, tree, ignore=shutil.ignore_patterns(".git"))
            with mock.patch.dict(os.environ, apply_env or {}):
                if apply_env is None:  # newline translation breaks it, as 1.8.0 read it (autocrlf would mend that read)
                    self.assertFalse(lab.apply_patch(tree, patch.read_text()))
                self.assertTrue(lab.apply_patch(tree, lab.read_patch(patch)))
            self.assertEqual((tree / "a.txt").read_bytes(), b"x\r\nz\r\n")

    def test_a_crlf_patch_applies_under_an_operators_core_autocrlf(self):
        # 1.8.1 review N2: git apply keeps the operator's config; with core.autocrlf=true it must still apply intact
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "gitconfig"
            config.write_text("[core]\n\tautocrlf = true\n[apply]\n\twhitespace = fix\n")
            self.test_a_patch_with_crlf_lines_reads_and_applies_intact(apply_env={"GIT_CONFIG_GLOBAL": str(config)})


class Budget(unittest.TestCase):
    def test_invalid_budget_operands_are_rejected_before_dispatch(self):
        cases = [(value, 1) for value in (float("nan"), float("inf"), -1, False)]
        cases += [(0, value) for value in (float("nan"), float("inf"), -1, False)]
        for maximum, reserve in cases:
            with self.subTest(max_type=type(maximum).__name__, reserve_type=type(reserve).__name__), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                execute = mock.Mock(side_effect=self.fake(cost=0)[0])
                output = root / "out"
                with self.assertRaisesRegex(ValueError, "budget"):
                    lab.run(self.config(root), output, replicates=1, jobs=1, max_calls=1,
                            max_usd=maximum, stop_usd=reserve, execute=execute)
                execute.assert_not_called()
                self.assertFalse((output / "dispatch.jsonl").exists())
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            execute = mock.Mock(side_effect=self.fake()[0])
            result = lab.run(self.config(root), root / "zero", replicates=1, jobs=1, max_calls=1,
                             max_usd=0, stop_usd=1, execute=execute)
            self.assertEqual((result["stop"], result["calls"]), ("usd-budget", 0))
            execute.assert_not_called()

    def test_invalid_control_limits_are_rejected_before_dispatch(self):
        cases = [(name, value) for name in ("jobs", "replicates", "max_calls", "max_invalid")
                 for value in (-1, False, 1.5)]
        cases += [("timeout_s", value) for value in (0, -1, False, float("nan"), float("inf"), 10 ** 400, 1e308)]
        for name, value in cases:
            with self.subTest(name=name, value_type=type(value).__name__), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                options = {"replicates": 1, "jobs": 1, "max_calls": 1, "max_invalid": 3,
                           "timeout_s": 30, "max_usd": 10, "stop_usd": 1, name: value}
                execute = mock.Mock(side_effect=self.fake(cost=0)[0])
                output = root / "out"
                with self.assertRaisesRegex(ValueError, "limit"):
                    lab.run(self.config(root), output, execute=execute, **options)
                execute.assert_not_called()
                self.assertFalse((output / "dispatch.jsonl").exists())

    def config(self, root, tasks=4):
        path = root / "set.json"
        path.write_text(json.dumps({"seed": 1, "arms": {"a": {}, "b": {}}, "tasks": [{"id": f"T{i}"} for i in range(tasks)]}))
        return path

    def fake(self, cost=1.0, valid=True, delay=0.0):
        peak, lock, live = {"max": 0}, threading.Lock(), [0]

        def execute(config, task, arm, rep, out, timeout):
            with lock:
                live[0] += 1
                peak["max"] = max(peak["max"], live[0])
            time.sleep(delay)
            cid = f"{task['id']}-r{rep:02d}-{arm}"
            (out / f"{cid}.runner.json").write_text("{}")
            row = {"valid": valid, "cost_usd": cost}
            (out / f"{cid}.json").write_text(json.dumps(row))
            with lock:
                live[0] -= 1
            return row
        return execute, peak

    def test_spend_overflow_is_unavailable_in_live_and_recovered_accounting(self):
        for recovering in (False, True):
            with self.subTest(recovering=recovering), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                config = self.config(root)
                output = root / "out"
                if recovering:
                    output.mkdir()
                    populate, _ = self.fake(cost=1e308)
                    for arm in ("a", "b"):
                        populate({}, {"id": "T0"}, arm, 1, output, 30)
                execute = mock.Mock(side_effect=self.fake(cost=1e308, delay=.02)[0])
                result = lab.run(config, output, replicates=1, jobs=2, max_calls=8,
                                 max_usd=10, stop_usd=1, execute=execute)
                self.assertIsNotNone(result["stop"])
                self.assertIsNone(result["spent"])
                self.assertEqual(execute.call_count, 0 if recovering else 2)
                stopped = json.loads((output / "STOP.json").read_text())
                self.assertIsNone(stopped["spent"])

    def test_reservation_overflow_stops_without_losing_the_first_terminal(self):
        for reserve, budget in ((10 ** 308, 1.7e308), (1e308, 1.7e308), (1, 1.7)):
            with self.subTest(reserve_type=type(reserve).__name__), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                execute = mock.Mock(side_effect=self.fake(cost=0, delay=.02)[0])
                output = root / "out"
                result = lab.run(self.config(root), output, replicates=1, jobs=2, max_calls=2,
                                 max_usd=budget, stop_usd=reserve, execute=execute)
                self.assertEqual((result["stop"], result["calls"], execute.call_count), ("usd-budget", 1, 1))
                self.assertEqual(result["spent"], 0)
                self.assertEqual(json.loads((output / "STOP.json").read_text())["stop"], "usd-budget")

    def test_arm_monetary_totals_remain_representable(self):
        for amount, expected in ((1e308, None), (0.25, 0.5), (0, 0)):
            with self.subTest(amount=amount):
                rows = [{"accepted": True, "agent_wall_s": 1, "cost_usd": amount, "cell": str(i)} for i in range(2)]
                stats = lab.arm_stats(rows, {}, {row["cell"]: row for row in rows})
                self.assertEqual(stats["cost_usd"], expected)
                self.assertEqual(stats["total_cost_usd"], None if expected is None else expected * 2)
                self.assertEqual(stats["cost_per_accepted_usd"], None if expected is None else expected / 2)
                json.dumps(stats, allow_nan=False)

    def test_parallel_cells_never_overrun_the_money_cap(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            execute, peak = self.fake(delay=.02)
            state = lab.run(self.config(root), root / "out", replicates=1, jobs=3, max_calls=99, max_usd=4, stop_usd=1, execute=execute)
            self.assertEqual(state["stop"], "usd-budget")
            self.assertLessEqual(state["spent"], 4)
            self.assertEqual(peak["max"], 3)

    def test_resume_skips_finished_cells_and_third_invalid_stops(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = self.config(root)
            first = lab.run(path, root / "out", replicates=1, jobs=1, max_calls=3, max_usd=99, stop_usd=1, execute=self.fake()[0])
            self.assertEqual(first["stop"], "call-budget")
            second = lab.run(path, root / "out", replicates=1, jobs=2, max_calls=99, max_usd=99, stop_usd=1, execute=self.fake()[0])
            self.assertEqual((second["stop"], second["calls"]), (None, 5))
            bad = lab.run(path, root / "bad", replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=self.fake(valid=False)[0])
            self.assertEqual((bad["stop"], bad["calls"]), ("invalid-budget", 3))

    def test_resume_refuses_anything_sealed_that_changed_and_resumes_once_restored(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = self.config(root)
            tool, other = root / "agent", root / "other-agent"
            tool.write_text("#!/bin/sh\n")
            other.write_text("#!/bin/sh\necho other\n")
            link = root / "agent-link"
            link.symlink_to(tool)
            config = json.loads(path.read_text())
            config["agent_command"] = [str(link), "--", str(tool)]
            path.write_text(json.dumps(config))
            original = path.read_text()
            out = root / "out"
            first = lab.run(path, out, replicates=1, jobs=1, max_calls=1, max_usd=99, stop_usd=1, execute=self.fake()[0])
            self.assertEqual(first["stop"], "call-budget")
            manifest = json.loads((out / "run-manifest.json").read_text())
            self.assertEqual(manifest["cells_before_seal"], 0)
            self.assertEqual(set(manifest["executables"]), {str(link), str(tool)})
            dispatched = (out / "dispatch.jsonl").read_text()

            def changed_arm():
                path.write_text(json.dumps({**config, "arms": {"a": {"effort": "low"}, "b": {}}}))

            def changed_task():
                path.write_text(json.dumps({**config, "tasks": [{**config["tasks"][0], "prompt": "other"}, *config["tasks"][1:]]}))

            def changed_binary():
                tool.write_text("#!/bin/sh\nexit 1\n")

            def retargeted_link():
                link.unlink()
                link.symlink_to(other)

            def same_bytes_elsewhere():  # the path alone moved: resolve(), not the bytes, catches it
                twin = root / "twin-agent"
                twin.write_bytes(tool.read_bytes())
                link.unlink()
                link.symlink_to(twin)

            for name, change, key in (("arm", changed_arm, ["arms", "set_sha256"]), ("task", changed_task, "set_sha256"),
                                      ("arm order", lambda: path.write_text(json.dumps({**config, "arms": {"b": {}, "a": {}}})), "set_sha256"),
                                      ("binary", changed_binary, sorted([f"executables:{tool}", f"executables:{link}"])), ("symlink", retargeted_link, f"executables:{link}"),
                                      ("same bytes elsewhere", same_bytes_elsewhere, f"executables:{link}"),
                                      ("python", None, "python"), ("framework", None, "framework_sha256")):
                with self.subTest(change=name):
                    execute = mock.Mock(side_effect=self.fake()[0])
                    if name == "python":
                        with mock.patch.object(lab.sys, "version", "0.0.0 (other)"):
                            state = lab.run(path, out, replicates=1, jobs=1, max_calls=9, max_usd=99, stop_usd=1, execute=execute)
                    elif name == "framework":
                        (root / "fw").mkdir(exist_ok=True)
                        (root / "fw" / "effort_lab.py").write_text("# another 007\n")
                        with mock.patch.object(lab, "HERE", root / "fw"):
                            state = lab.run(path, out, replicates=1, jobs=1, max_calls=9, max_usd=99, stop_usd=1, execute=execute)
                    else:
                        change()
                        state = lab.run(path, out, replicates=1, jobs=1, max_calls=9, max_usd=99, stop_usd=1, execute=execute)
                    self.assertEqual((state["stop"], state["changed"], state["calls"]), ("manifest-mismatch", key if isinstance(key, list) else [key], 0))
                    execute.assert_not_called()
                    self.assertEqual((out / "dispatch.jsonl").read_text(), dispatched)
                    self.assertFalse((out / "STOP.json").exists())
                    path.write_text(original)
                    tool.write_text("#!/bin/sh\n")
                    link.unlink()
                    link.symlink_to(tool)
            sealed = (out / "run-manifest.json").read_text()
            for name, damage, stop in (("deleted", lambda m: m.unlink(), "manifest-missing"),
                                       ("edited", lambda m: m.write_text(sealed.replace('"cells_before_seal": 0', '"cells_before_seal": 1')), "manifest-mismatch"),
                                       ("truncated", lambda m: m.write_text(sealed[:40]), "manifest-unreadable"),
                                       ("not a file", lambda m: (m.unlink(), m.mkdir()), "manifest-unreadable")):
                with self.subTest(manifest=name):
                    execute = mock.Mock(side_effect=self.fake()[0])
                    damage(out / "run-manifest.json")
                    state = lab.run(path, out, replicates=1, jobs=1, max_calls=9, max_usd=99, stop_usd=1, execute=execute)
                    self.assertEqual((state["stop"], state["calls"]), (stop, 0))
                    execute.assert_not_called()
                    self.assertEqual((out / "dispatch.jsonl").read_text(), dispatched)
                    if (out / "run-manifest.json").is_dir():
                        (out / "run-manifest.json").rmdir()
                    (out / "run-manifest.json").write_text(sealed)
            path.write_text(json.dumps({**config, "compare": {"candidate": "a", "reference": "b", "margin": .1}}))  # analysis only
            resumed = lab.run(path, out, replicates=2, jobs=2, max_calls=99, max_usd=99, stop_usd=1, execute=self.fake()[0])
            self.assertEqual((resumed["stop"], resumed["calls"]), (None, 15))  # limits, replicates and compare stay adjustable
            self.assertTrue(lab.sealed_state(json.loads(path.read_text()), out)["compare_changed"])
            digest = lab._sha256(out / "run-manifest.json")
            rows = [json.loads(line) for line in (out / "dispatch.jsonl").read_text().splitlines()]
            self.assertTrue(all(r["manifest_sha256"] == digest for r in rows if "dispatched_at" in r))

    def test_a_file_the_attempts_rewrite_is_sealed_unless_the_set_leaves_it_out(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            log = root / "agent.log"
            for leave_out in (False, True):
                with self.subTest(unsealed_files=leave_out):
                    path, out = self.config(root), root / f"out-{leave_out}"
                    config = {**json.loads(path.read_text()), "agent_command": ["/bin/sh", "--log", str(log)],
                              **({"unsealed_files": [str(log)]} if leave_out else {})}
                    path.write_text(json.dumps(config))
                    log.write_text("start")
                    lab.run(path, out, replicates=1, jobs=1, max_calls=1, max_usd=99, stop_usd=1, execute=self.fake()[0])
                    log.write_text("start\nattempt 1")  # what the agent wrote while it ran
                    state = lab.run(path, out, replicates=1, jobs=1, max_calls=9, max_usd=99, stop_usd=1, execute=self.fake()[0])
                    self.assertEqual(state["stop"], None if leave_out else "manifest-mismatch")
                    if not leave_out:
                        self.assertEqual(state["changed"], [f"executables:{log}"])

    def test_dispatches_after_the_seal_that_do_not_name_it_unbind_the_run(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, out = self.config(root), root / "out"
            config = json.loads(path.read_text())
            lab.run(path, out, replicates=1, jobs=1, max_calls=1, max_usd=99, stop_usd=1, execute=self.fake()[0])
            self.assertEqual(lab.sealed_state(config, out)["state"], "sealed")
            done = {json.loads(line)["cell"] for line in (out / "dispatch.jsonl").read_text().splitlines()}
            cell = next(c for c in (f"T{i}-r01-{a}" for i in range(4) for a in "ab") if c not in done)
            task, arm = cell.split("-r01-")
            self.fake()[0](config, {"id": task}, arm, 1, out, 30)  # a 1.7.0 controller: a result and a dispatch naming no manifest
            with (out / "dispatch.jsonl").open("a") as handle:
                handle.write(json.dumps({"cell": cell, "dispatched_at": lab._now()}) + "\n")
                handle.write(json.dumps({"cell": cell, "finished_at": lab._now(), "cost_usd": 1, "valid": True}) + "\n")
            self.assertEqual((lab.sealed_state(config, out)["state"], lab.sealed_state(config, out)["unbound_dispatches"]), ("unbound", 1))
            execute = mock.Mock(side_effect=self.fake()[0])
            state = lab.run(path, out, replicates=1, jobs=1, max_calls=9, max_usd=99, stop_usd=1, execute=execute)
            self.assertEqual((state["stop"], state["changed"]), ("manifest-mismatch", ["unbound-dispatches", "unbound-cells"]))
            execute.assert_not_called()

    def test_results_no_sealed_dispatch_produced_unbind_the_run_and_a_sealed_ledger_must_be_readable(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, out = self.config(root), root / "out"
            config = json.loads(path.read_text())
            lab.run(path, out, replicates=1, jobs=1, max_calls=1, max_usd=99, stop_usd=1, execute=self.fake()[0])
            done = {json.loads(line)["cell"] for line in (out / "dispatch.jsonl").read_text().splitlines()}
            cell = next(c for c in (f"T{i}-r01-{a}" for i in range(4) for a in "ab") if c not in done)
            task, arm = cell.split("-r01-")
            self.fake()[0](config, {"id": task}, arm, 1, out, 30)  # a result copied in: no dispatch row at all
            self.assertEqual((lab.sealed_state(config, out)["state"], lab.sealed_state(config, out)["unbound_cells"]), ("unbound", 1))
            execute = mock.Mock(side_effect=self.fake()[0])
            state = lab.run(path, out, replicates=1, jobs=1, max_calls=9, max_usd=99, stop_usd=1, execute=execute)
            self.assertEqual((state["stop"], state["changed"]), ("manifest-mismatch", ["unbound-cells"]))
            execute.assert_not_called()
            ledger = (out / "dispatch.jsonl").read_text()
            (out / "dispatch.jsonl").unlink()
            (out / "dispatch.jsonl").mkdir()
            with self.assertRaisesRegex(ValueError, "cannot be read"):
                lab.sealed_state(config, out)
            (out / "dispatch.jsonl").rmdir()
            (out / "dispatch.jsonl").write_text(ledger)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads a mode-0 file")
    def test_an_unreadable_sealed_file_is_a_structured_stop(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, tool = self.config(root), root / "secret-agent"
            tool.write_text("x")
            tool.chmod(0)
            try:
                path.write_text(json.dumps({**json.loads(path.read_text()), "agent_command": [str(tool)]}))
                state = lab.run(path, root / "out", replicates=1, jobs=1, max_calls=1, max_usd=99, stop_usd=1, execute=self.fake()[0])
                self.assertEqual((state["stop"], state["calls"]), ("executable-unreadable", 0))
            finally:
                tool.chmod(0o600)

    def test_one_cells_controller_error_is_an_invalid_cell_not_the_end_of_the_run(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, out = self.config(root), root / "out"
            good = self.fake()[0]

            def execute(config, task, arm, rep, out_, timeout):
                if task["id"] == "T1" and arm == "a":
                    raise RuntimeError("archive entry is not a regular file")  # a refused snapshot, before any agent ran
                return good(config, task, arm, rep, out_, timeout)
            state = lab.run(path, out, replicates=1, jobs=2, max_calls=99, max_usd=99, stop_usd=1, execute=execute)
            self.assertEqual((state["stop"], state["calls"], state["invalid"]), (None, 8, 1))
            row = json.loads((out / "T1-r01-a.json").read_text())
            self.assertEqual((row["valid"], row["failure_class"]), (False, "controller-error:RuntimeError"))
            again = lab.run(path, out, replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=good)
            self.assertEqual((again["stop"], again["calls"]), (None, 0))  # recorded, never retried, never an orphan
            rows = [{**json.loads(p.read_text()), "cell": p.stem} for p in out.glob("*-r01-*.json") if not p.name.endswith(".runner.json")]
            accounting = lab.arm_accounting(json.loads(path.read_text()), out, rows, {})
            self.assertEqual(accounting["arms"]["a"]["invalid"], {"controller-error:RuntimeError": 1})

    def test_a_provider_rate_limit_pauses_the_run_instead_of_spending_the_invalid_budget(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, out = self.config(root), root / "out"
            good, calls = self.fake()[0], []

            def limited(config, task, arm, rep, out_, timeout):
                calls.append(task["id"])
                if len(calls) <= 3:
                    return good(config, task, arm, rep, out_, timeout)
                cid = f"{task['id']}-r{rep:02d}-{arm}"  # refused before any work: no usage, no cost
                (out_ / f"{cid}.runner.json").write_text(json.dumps({"problem": "native-error-rate-limit", "usage": None, "cost_usd": None}))
                row = {"valid": False, "cost_usd": "unmeasured", "failure_class": "agent-exit"}
                (out_ / f"{cid}.json").write_text(json.dumps(row))
                return row
            state = lab.run(path, out, replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=limited, max_invalid=1)
            # charged its reserve like any invalid cell (no cost was measured), but not counted toward --max-invalid
            self.assertEqual((state["stop"], state["calls"], state["invalid"], state["refused"], state["spent"]), ("rate-limit", 4, 0, 1, 4.0))
            self.assertFalse((out / "STOP.json").exists())  # a planned pause, not a final stop
            refused = [json.loads(p.read_text()) for p in out.glob("*-r01-*.json") if not p.name.endswith(".runner.json")]
            self.assertEqual(sum(r.get("failure_class") == "provider-rate-limit" for r in refused), 1)
            early = lab.run(path, out, replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=good, max_invalid=1)
            self.assertEqual((early["stop"], early["calls"]), ("rate-limit-cooldown", 0))  # resuming inside the outage would lose cells
            with mock.patch.object(lab, "RATE_LIMIT_COOLDOWN_S", 0):
                resumed = lab.run(path, out, replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=good, max_invalid=1)
            self.assertEqual((resumed["stop"], resumed["calls"], resumed["invalid"], resumed["refused"], resumed["spent"]), (None, 4, 0, 1, 8.0))

    def test_resume_charges_what_the_live_run_charged_and_only_the_label_exempts_a_cell(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, out = self.config(root), root / "out"
            good = self.fake()[0]

            def recovered(config, task, arm, rep, out_, timeout):
                row = good(config, task, arm, rep, out_, timeout)
                if task["id"] == "T0" and arm == "a":  # a valid cell whose CLI recovered from a 429: its receipt still names it
                    cid = f"{task['id']}-r{rep:02d}-{arm}"
                    (out_ / f"{cid}.runner.json").write_text(json.dumps({"problem": "native-error-rate-limit", "cost_usd": 2.0}))
                    row = {"valid": True, "cost_usd": 2.0}
                    (out_ / f"{cid}.json").write_text(json.dumps(row))
                return row
            live = lab.run(path, out, replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=3, execute=recovered)
            again = lab.run(path, out, replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=3, execute=good)
            self.assertEqual((live["stop"], live["refused"], live["spent"]), (None, 0, 9.0))
            self.assertEqual((again["calls"], again["spent"]), (0, 9.0))

    def test_unsealed_files_can_name_the_file_of_a_flag(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "agent.log"
            log.write_text("x")
            sealed = lab.seal({"agent_command": ["/bin/sh", f"--log={log}"], "unsealed_files": [str(log)]})
            self.assertEqual(list(sealed["executables"]), ["/bin/sh"])

    def test_a_flag_that_names_an_absolute_file_is_sealed(self):
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "agent.toml"
            config.write_text("model = 'x'")
            part = f"--config={config}"
            sealed = lab.seal({"agent_command": ["/bin/sh", part]})
            self.assertEqual(sealed["executables"][part]["path"], str(config.resolve()))
            config.write_text("model = 'y'")
            self.assertNotEqual(lab.seal({"agent_command": ["/bin/sh", part]})["executables"], sealed["executables"])

    def test_the_program_is_sealed_through_path_and_a_relative_one_is_named_unsealed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first, second = root / "agentcli", root / "agentcli-2"
            first.write_text("one")
            second.write_text("two")
            with mock.patch.object(lab.shutil, "which", return_value=str(first)):
                one = lab.seal({"agent_command": ["agentcli", "{prompt_file}"]})
            with mock.patch.object(lab.shutil, "which", return_value=str(second)):
                two = lab.seal({"agent_command": ["agentcli", "{prompt_file}"]})
            self.assertTrue(one["program_sealed"])
            self.assertEqual(one["executables"]["agentcli"]["path"], str(first.resolve()))
            self.assertNotEqual(one["executables"], two["executables"])
            relative = lab.seal({"agent_command": ["./run-agent.sh", "{prompt_file}"]})
            self.assertEqual((relative["program_sealed"], relative["executables"]), (False, {}))

    def test_results_are_read_only_with_the_set_they_were_sealed_with(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, out = self.config(root), root / "out"
            config = json.loads(path.read_text())
            state = lambda c: {k: v for k, v in lab.sealed_state(c, out).items() if k in ("state", "compare_changed", "program_sealed")}
            self.assertEqual(state(config), {"state": "absent", "compare_changed": None, "program_sealed": None})
            lab.run(path, out, replicates=1, jobs=1, max_calls=1, max_usd=99, stop_usd=1, execute=self.fake()[0])
            self.assertEqual(state(config), {"state": "sealed", "compare_changed": False, "program_sealed": False})
            self.assertEqual(state({**config, "compare": {"margin": .1}}), {"state": "sealed", "compare_changed": True, "program_sealed": False})
            with self.assertRaisesRegex(ValueError, "different set"):
                lab.sealed_state({**config, "seed": 2}, out)
            sealed = (out / "run-manifest.json").read_text()
            (out / "run-manifest.json").unlink()  # after a sealed dispatch, a missing manifest is refused, never re-sealed
            with self.assertRaisesRegex(ValueError, "missing for sealed dispatches"):
                lab.sealed_state(config, out)
            (out / "run-manifest.json").write_text(sealed.replace("\n", "\n "))  # same values, other bytes: not what was dispatched
            with self.assertRaisesRegex(ValueError, "changed after dispatch"):
                lab.sealed_state(config, out)
        with tempfile.TemporaryDirectory() as d:  # a real directory from before 1.8: cells, a ledger without manifest digests
            root = Path(d)
            path, out = self.config(root), root / "out"
            config = json.loads(path.read_text())
            out.mkdir()
            self.fake()[0](config, config["tasks"][0], "a", 1, out, 30)
            (out / "dispatch.jsonl").write_text(json.dumps({"cell": "T0-r01-a", "dispatched_at": lab._now()}) + "\n"
                                               + json.dumps({"cell": "T0-r01-a", "finished_at": lab._now(), "cost_usd": 1, "valid": True}) + "\n")
            lab.run(path, out, replicates=1, jobs=1, max_calls=1, max_usd=99, stop_usd=1, execute=self.fake()[0])
            self.assertEqual(json.loads((out / "run-manifest.json").read_text())["cells_before_seal"], 1)
            self.assertEqual(lab.sealed_state(config, out)["state"], "sealed-late")

    def test_failed_calls_without_a_cost_are_charged_their_reserve_up_to_the_invalid_budget(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = self.config(root, tasks=8)
            # the go-json shape: a native error leaves a receipt with cost null and no usage; the run must go on, charging stop_usd
            state = lab.run(path, root / "out", replicates=1, jobs=1, max_calls=4, max_usd=99, stop_usd=1, execute=self.fake(valid=False, cost="unmeasured")[0], max_invalid=20)
            self.assertEqual((state["stop"], state["calls"], state["invalid"], state["spent"]), ("call-budget", 4, 4, 4.0))
            resumed = lab.run(path, root / "out", replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=self.fake(valid=False, cost="unmeasured")[0], max_invalid=6)
            self.assertEqual((resumed["stop"], resumed["invalid"], resumed["spent"]), ("invalid-budget", 6, 6.0))  # earlier invalid cells count
            # a valid cell with no cost is a receipt defect and still stops the run
            state = lab.run(path, root / "valid", replicates=1, jobs=1, max_calls=9, max_usd=9, stop_usd=1, execute=self.fake(cost="unmeasured")[0], max_invalid=20)
            self.assertEqual(state["stop"], "cost-unavailable")

    def test_unknown_cost_stops(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = lab.run(self.config(root), root / "out", replicates=1, jobs=1, max_calls=9, max_usd=9, stop_usd=1, execute=self.fake(cost="unmeasured")[0])
            self.assertEqual(state["stop"], "cost-unavailable")

    def test_recovery_preserves_the_valid_unpriced_stop_before_new_dispatch(self):
        for valid, cost, expected in ((True, "unmeasured", "cost-unavailable"),
                                      (True, 0, "call-budget"), (False, "unmeasured", "call-budget")):
            with self.subTest(valid=valid, cost=cost), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                config = self.config(root)
                execute, _ = self.fake(valid=valid, cost=cost)
                output = root / "out"
                lab.run(config, output, replicates=1, jobs=1, max_calls=1, max_usd=99,
                        stop_usd=1, execute=execute, max_invalid=20)
                (output / "STOP.json").unlink(missing_ok=True)  # result survives an interrupted controller
                recovered = lab.run(config, output, replicates=1, jobs=1, max_calls=1, max_usd=99,
                                    stop_usd=1, execute=execute, max_invalid=20)
                self.assertEqual(recovered["stop"], expected)
                self.assertEqual(recovered["calls"], 0 if valid and cost == "unmeasured" else 1)

    def test_recovery_restores_per_cell_and_invalid_limits_before_dispatch(self):
        for valid, cost, expected in ((True, 2, "cell-over-limit"), (False, 0, "invalid-budget")):
            with self.subTest(valid=valid, cost=cost), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                config = self.config(root)
                execute, _ = self.fake(valid=valid, cost=cost)
                output = root / "out"
                first = lab.run(config, output, replicates=1, jobs=1, max_calls=1, max_usd=99,
                                stop_usd=1, execute=execute, max_invalid=1)
                self.assertEqual(first["stop"], expected)
                (output / "STOP.json").unlink()
                recovered = lab.run(config, output, replicates=1, jobs=1, max_calls=1, max_usd=99,
                                    stop_usd=1, execute=execute, max_invalid=1)
                self.assertEqual(recovered["stop"], expected)
                self.assertEqual(recovered["calls"], 0)

    def test_invalid_numeric_costs_never_become_budget_credit_or_measured_zero(self):
        for cost in (float("nan"), float("inf"), -1, False):
            with self.subTest(cost_type=type(cost).__name__), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                result = lab.run(self.config(root), root / "out", replicates=1, jobs=1, max_calls=1,
                                 max_usd=99, stop_usd=1, execute=self.fake(cost=cost)[0])
                self.assertEqual(result["stop"], "cost-unavailable")
                self.assertEqual(result["spent"], 0)


class Gates(unittest.TestCase):
    def c(self, reduction=.4, diff=0.0, low=6, ref=6, low_total=80, ref_total=100):
        return {"medium": {"accepted": low, "total_wall_s": low_total}, "high": {"accepted": ref, "total_wall_s": ref_total}, "reduction": reduction, "durable_diff": diff}

    def v(self, c, ci, **kw):
        return lab.verdict(c, ci, **{"valid": 60, "tasks": 10, "split_tasks": ["T"], "sensitive": True, "accepted_share": .5, "next_share": .5, **kw})

    def test_proof_needs_every_gate(self):
        self.assertEqual(self.v(self.c(), [-.04, .04])["thesis"], "HOLDS")
        self.assertEqual(self.v(self.c(), [-.2, .1])["thesis"], "UNPROVEN")
        self.assertEqual(self.v(self.c(low_total=101), [-.04, .04])["thesis"], "UNPROVEN")  # rework ate the saving

    def test_insensitive_instruments_and_floors_inform_nothing(self):
        self.assertEqual(self.v(self.c(), [-.04, .04], sensitive=False)["durability"], "NO-INFORMATION")
        self.assertEqual(self.v(self.c(), [0, 0], split_tasks=[])["durability"], "NO-INFORMATION")
        self.assertEqual(self.v(self.c(), [-.04, .04], accepted_share=.2)["thesis"], "UNPROVEN")
        self.assertEqual(self.v(self.c(), [-.04, .04], next_share=.95)["durability"], "NO-INFORMATION")
        self.assertEqual(self.v(self.c(), [-.04, .04], valid=39)["durability"], "NO-INFORMATION")

    def test_margin_kills_and_time_fails(self):
        self.assertEqual(self.v(self.c(diff=-.06), [-.2, .0])["thesis"], "KILLED")
        self.assertEqual(self.v(self.c(diff=-.05), [-.05, .0])["durability"], "PROVEN")
        self.assertEqual(self.v(self.c(reduction=.2), [-.04, .04])["thesis"], "NOT-SURVIVES")
        self.assertEqual(self.v(self.c(low=5), [-.04, .04])["time"], "SURVIVES")  # acceptance counts only through time per accepted change

    def test_a_mutant_keeps_every_unsampled_block(self):
        text = ("diff --git a/a.go b/a.go\n--- a/a.go\n+++ b/a.go\n@@ -1,1 +1,1 @@\n-x\n+y\n@@ -9,1 +9,1 @@\n-p\n+q\n")
        binary = "diff --git a/f.bin b/f.bin\nindex 1..2 100644\nGIT binary patch\nliteral 3\nKcmZ\n\nliteral 0\nHcmV\n\n"
        rename = "diff --git a/old.go b/new.go\nsimilarity index 100%\nrename from old.go\nrename to new.go\n"
        mode = "diff --git a/run.sh b/run.sh\nold mode 100644\nnew mode 100755\n"
        out = list(lab.mutants(text + binary + rename + mode, 6, __import__("random").Random(1)))
        self.assertEqual(len(out), 2)
        for m in out:
            self.assertTrue(m.endswith(binary + rename + mode))  # 1.9.0 dropped all three from every mutant
            self.assertEqual(m.count("\n@@ "), 1)

    def test_binary_is_a_line_not_a_phrase_and_one_hunk_has_no_mutant(self):
        text = ('diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n@@ -1,1 +1,1 @@\n-a\n+s = "GIT binary patch"\n'
                "@@ -5,1 +5,1 @@\n-b\n+c\n")
        self.assertEqual(len(lab.hunks(text)[0][1]), 2)  # 1.9.0 read this text diff as binary and made no mutant
        self.assertEqual(list(lab.mutants(text.split("@@ -5")[0], 6, __import__("random").Random(1))), [])  # minus it, the base

    def test_a_rejected_mutant_counts_only_where_the_reference_passes(self):
        rows = [("A", True, (True, None)), ("B", True, (False, None))] + [("A", False, (False, None))] * 10 + [("B", False, (False, None))] * 10
        immediate = lab.sensitivity_summary(rows)["immediate"]
        self.assertEqual((immediate["mutants"], immediate["rejected"]), (10, 10))  # B's oracle rejects even the reference


class OperatorV2(unittest.TestCase):
    BASE = "def add(a, b):\n    return a - b\n\n\n# helper\ndef mul(a, b):\n    return a + b\n"
    HEAD = "def add(a, b):\n    return a + b\n\n\n# helper for products\ndef mul(a, b):\n    return a * b\n"

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-qb", "main")

    def test_units_rebuild_the_change_and_one_mutant_per_unit(self):
        (self.repo / "f.bin").write_bytes(b"\0\1")
        base = commit(self.repo, {"a.go": "package a\n\nfunc A() int { return 1 }\n\nfunc B() int { return 2 }\n", "old.go": "package a\n\nvar X = 1\n",
                                  "a_test.go": "package a\n"}, "base", "2026-01-01T00:00:00Z")
        (self.repo / "f.bin").write_bytes(b"\0\2")
        git(self.repo, "mv", "old.go", "new.go")
        head = commit(self.repo, {"a.go": "package a\n\nfunc A() int { return 10 }\n\nfunc B() int { return 20 }\n", "b.go": "package a\n\nvar Y = 2",
                                  "a_test.go": "package a\n\n// changed\n"}, "head", "2026-01-02T00:00:00Z")
        files, binaries = lab.units(self.repo, base, head)
        self.assertEqual(binaries, 1)
        self.assertEqual(sorted(f[0] for f in files), ["a.go", "b.go", "new.go", "old.go"])  # a_test.go is a test: no unit
        self.assertTrue(all(lab.rebuilds(*f[1:]) for f in files))
        self.assertEqual(sum(len(f[3]) for f in files), 5)  # A, B, the renamed file as delete + add, the new file
        old = next(f for f in files if f[0] == "old.go")
        self.assertEqual(lab.revert(old[1], old[2], old[3][0]), old[1])  # the deleted file comes back whole
        b = next(f for f in files if f[0] == "b.go")
        self.assertEqual(lab.revert(b[1], b[2], b[3][0]), [])  # an added file reverted is absent (sensitivity_v2 deletes it)
        self.assertFalse(lab.rebuilds(old[1], old[2], [(0, 1, 0, 0)]))  # a wrong parse fails the construction control

    def test_a_comment_only_unit_is_equivalent_and_code_is_not(self):
        base, head = lab._lines(self.BASE.encode()), lab._lines(self.HEAD.encode())
        hunks = [(1, 1, 1, 1), (4, 1, 4, 1), (6, 1, 6, 1)]
        self.assertTrue(lab.rebuilds(base, head, hunks))
        self.assertEqual([lab.equivalent("calc.py", base, head, h) for h in hunks], [False, True, False])
        go = (lab._lines(b"package a\n\n// one\nvar r = `//x`\n"), lab._lines(b"package a\n\n// two\nvar r = `//x`\n"))
        self.assertTrue(lab.equivalent("a.go", *go, (2, 1, 2, 1)))
        self.assertFalse(lab.equivalent("a.go", lab._lines(b"x := 1 // a\n"), lab._lines(b"x := 2 // a\n"), (0, 1, 0, 1)))

    def test_v2_end_to_end_classifies_every_unit(self):
        old = "import unittest\n\n\nclass Old(unittest.TestCase):\n    def test_truth(self):\n        self.assertTrue(True)\n"
        commit(self.repo, {"calc.py": self.BASE, "unused.py": "X = 1\n", "tests/__init__.py": "", "tests/test_old.py": old}, "base", "2026-01-01T00:00:00Z")
        hidden = ("import unittest\nimport calc\n\n\nclass Calc(unittest.TestCase):\n" + "".join(f"    def test_add_{i}(self):\n        self.assertEqual(calc.add({i}, 1), {i + 1})\n\n" for i in range(5))
                  + "    def test_mul(self):\n        self.assertEqual(calc.mul(2, 2), 4)\n")
        message = "feat: fix addition and multiplication\n\n" + "Addition must really add and multiplication must really multiply, in every caller. " * 2
        commit(self.repo, {"calc.py": self.HEAD, "unused.py": "X = 2\n", "tests/test_calc.py": hidden}, message, "2026-01-05T00:00:00Z")
        config = {"repo": str(self.repo), "adapter": "unittest", "tests": "tests/test_*.py", "as_of": "2026-03-01T00:00:00+00:00", "seed": 7, "want": 1,
                  "min_source_lines": 1, "min_message": 50, "require_next": False}
        out = self.root / "lab"
        self.assertEqual(lab.mine(config, out, 2), 1)
        result = lab.sensitivity_v2(out / "replay-set.json", 2)
        self.assertEqual(result["controls"], {"ok": 1, "control-failed": 0, "operator-invalid": 0})
        self.assertEqual(result["funnel"], {"trivial": 0, "invalid": 0, "equivalent": 1, "out-of-scope": 1, "valid": 2, "error": 0})
        self.assertEqual((result["jobs"], result["equivalents_loaded"]), (2, 1))  # the comment unit sits in calc.py, which the hidden tests load
        self.assertEqual(result["valid_outcomes"], {"rejected-contract": 0, "rejected-assert": 1, "survived": 1})  # mul(2, 2) is 4 either way
        self.assertEqual((result["sensitivity"], result["specificity"], result["decision"]), (.5, 1.0, "no-information"))
        saved = json.loads((out / "sensitivity-v2.json").read_text())
        self.assertEqual(saved["operator"], "revert-one-unit/1")
        self.assertNotIn("calc.py", json.dumps(saved["rows"]))  # rows carry a file index, never a name

    def test_the_decision_has_three_states_and_never_rounds_up(self):
        tasks = {f"T{i}": {"control": "ok"} for i in range(8)}
        def rows(rejected, equivalent_outcome="pass"):
            out = [{"task": f"T{i}", "class": "valid", "outcome": "rejected-assert" if j < rejected else "survived"} for i in range(8) for j in range(3)]
            return out + [{"task": "T0", "class": "equivalent", "outcome": equivalent_outcome, "loaded": True}]
        decide = lambda r, floor: lab.sensitivity_v2_summary(r, tasks, floor, draws=500)["decision"]
        self.assertEqual(decide(rows(3), .5), "passes")
        self.assertEqual(decide(rows(0), .5), "fails")
        self.assertEqual(decide(rows(3), None), "floor-unset")
        self.assertEqual(decide(rows(3, "assert"), .5), "fails")  # an oracle that rejects a harmless change fails, whatever its sensitivity
        self.assertEqual(decide([r for r in rows(3) if r["class"] == "valid"], .5), "indeterminate")  # no equivalent: no specificity
        mixed = rows(0) + [{"task": f"T{i}", "class": "valid", "outcome": "rejected-assert"} for i in range(4) for _ in range(6)]
        self.assertEqual(decide(mixed, .5), "indeterminate")
        self.assertEqual(decide(rows(3)[:9] + rows(3)[-1:], .5), "no-information")  # 9 valid in 3 tasks


class OperatorV2Review(unittest.TestCase):
    """Review of 1.10.0 (Fable 5.2 xhigh, 2026-11-16)."""
    def test_an_all_rejected_minimum_sample_does_not_pass_a_floor_near_one(self):
        tasks = {f"T{i}": {"control": "ok"} for i in range(8)}
        equivalent = [{"task": "T0", "class": "equivalent", "outcome": "pass", "loaded": True}]
        rows = [{"task": f"T{i % 8}", "class": "valid", "outcome": "rejected-assert"} for i in range(20)] + equivalent
        decide = lambda r, floor: lab.sensitivity_v2_summary(r, tasks, floor, draws=500)
        self.assertEqual(decide(rows, .99)["decision"], "indeterminate")  # the bootstrap alone read [1, 1] and passed
        self.assertAlmostEqual(decide(rows, .99)["interval"][0], .025 ** (1 / 20), places=6)
        self.assertEqual(decide(rows, .8)["decision"], "passes")
        # round 2, N1: one survivor must not read better than none (a cap only at all-or-none let 19 of 20 pass at 0.85)
        worse = [dict(rows[0], outcome="survived")] + rows[1:]
        self.assertEqual((decide(rows, .85)["decision"], decide(worse, .85)["decision"]), ("indeterminate", "indeterminate"))
        self.assertLess(decide(worse, .85)["interval"][0], decide(rows, .85)["interval"][0])
        half = [{"task": f"T{i}", "class": "valid", "outcome": o} for i in range(8) for o in ("rejected-assert", "survived") * 2] + equivalent
        self.assertLess(decide(half, .45)["interval"][0], .4)  # every task 2 of 4: zero-width bootstrap at 0.5, capped at 0.32
        self.assertEqual(decide(half, .45)["decision"], "indeterminate")

    def test_an_equivalent_in_a_file_no_test_loads_cannot_carry_specificity(self):
        tasks = {f"T{i}": {"control": "ok"} for i in range(8)}
        valid = [{"task": f"T{i}", "class": "valid", "outcome": "rejected-assert"} for i in range(8) for _ in range(3)]
        decide = lambda loaded: lab.sensitivity_v2_summary(valid + [{"task": "T0", "class": "equivalent", "outcome": "pass", "loaded": loaded}], tasks, .5, draws=500)["decision"]
        self.assertEqual((decide(True), decide(False)), ("passes", "indeterminate"))
        count = lambda loaded: lab.sensitivity_v2_summary(valid + [{"task": "T0", "class": "equivalent", "outcome": "pass", "loaded": loaded}], tasks, .5, draws=500)["equivalents_loaded"]
        self.assertEqual((count(True), count(False)), (1, 0))  # the summary says why a clear interval reads indeterminate

    def test_a_restored_file_gets_its_removed_directories_back(self):
        with tempfile.TemporaryDirectory() as scratch:
            lab._put(Path(scratch), "gone/deeper/file.py", ["x = 1\n"])
            self.assertEqual((Path(scratch) / "gone/deeper/file.py").read_text(), "x = 1\n")

    def test_a_directive_comment_is_not_an_equivalent_change(self):
        one = (0, 1, 0, 1)
        self.assertTrue(lab.equivalent("a.go", ["// old note\n", "x := 1\n"], ["// new note\n", "x := 1\n"], one))
        for base, head in (("//go:build linux\n", "//go:build darwin\n"), ("// +build linux\n", "// +build darwin\n"), ("//export Old\n", "//export New\n")):
            self.assertFalse(lab.equivalent("a.go", [base, "x := 1\n"], [head, "x := 1\n"], one), base)
        self.assertFalse(lab.equivalent("a.py", ["# -*- coding: latin-1 -*-\n"], ["# -*- coding: utf-8 -*-\n"], one))
        self.assertFalse(lab.equivalent("a.py", ["#!/usr/bin/python2\n", "x = 1\n"], ["#!/usr/bin/python3\n", "x = 1\n"], one))

    def test_bytes_that_are_not_utf8_do_not_end_the_run(self):
        self.assertIn(lab._code(lab._lines(b"# caf\xe9\nx = 1\n"), "a.py") is None, (True, False))  # read or refused, never raised
        self.assertFalse(lab.equivalent("a.py", lab._lines(b"x = 'caf\xe9'\n"), lab._lines(b"x = 'cafe'\n"), (0, 1, 0, 1)))

    def test_a_symbolic_link_is_never_a_unit_and_never_written_through(self):
        with tempfile.TemporaryDirectory() as scratch:
            repo, outside = Path(scratch) / "repo", Path(scratch) / "outside"
            repo.mkdir()
            outside.write_text("host file\n")
            git(repo, "init", "-qb", "main")
            (repo / "link").symlink_to("first-target")
            base = commit(repo, {"calc.py": "x = 1\n"}, "base", "2026-01-01T00:00:00Z")
            (repo / "link").unlink()
            (repo / "link").symlink_to(str(outside))
            head = commit(repo, {"calc.py": "x = 2\n"}, "head", "2026-01-02T00:00:00Z")
            files, without_units = lab.units(repo, base, head)
            self.assertEqual(([f[0] for f in files], without_units), (["calc.py"], 1))
            self.assertEqual(lab.units(repo, base, head, skip=("calc.py",))[0], [])  # a hidden file is never a unit
            tree = Path(scratch) / "tree"
            lab.extract(repo, head, tree)
            with self.assertRaises(ValueError):
                lab._put(tree, "link", ["chosen bytes\n"])
            self.assertEqual(outside.read_text(), "host file\n")

    def test_floor_is_a_rate_and_only_v2_reads_it(self):
        for argv in (["sensitivity", "--set", "x.json", "--floor", "0.3"], ["sensitivity", "--set", "x.json", "--operator", "v2", "--floor", "95"]):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()) as err:
                lab.main(argv)
            self.assertIn("--floor is a rate", err.getvalue())


class MinerSafety(unittest.TestCase):
    def test_a_mined_tree_cannot_redirect_writes_through_a_symlink(self):
        with tempfile.TemporaryDirectory() as scratch:
            tree, outside = Path(scratch) / "tree", Path(scratch) / "outside"
            tree.mkdir()
            outside.mkdir()
            (tree / "tests").symlink_to(outside)
            with mock.patch.object(lab, "_git", return_value=b"x"), self.assertRaises(ValueError):
                lab.overlay(None, tree, "rev", ["tests/test_a.py"])
            (tree / ".007-accept").symlink_to(outside)
            with self.assertRaises(ValueError):
                lab.collect(tree, {}, None, None)
            self.assertEqual(list(outside.iterdir()), [])


class UnseenBehaviour(unittest.TestCase):
    rows = [{"task": "T", "arm": a, "acceptance_outcomes": {"always": "pass", "never": "fail", "split": s, "split2": s2}} for a, s, s2 in (("medium", "pass", "pass"), ("high", "fail", "pass"))] + \
           [{"task": "U", "arm": a, "acceptance_outcomes": {"x": "pass"}} for a in ("medium", "high")]

    def test_only_tests_that_split_cells_count_and_the_rule_ignores_the_arm(self):
        tests = lab.unseen(self.rows, {"T": ["always", "never", "split", "split2"], "U": ["x"]}, "medium", "high")
        self.assertEqual(tests, {"T": ["split"], "U": []})
        self.assertEqual(lab.unseen_diff(self.rows, tests, "medium", "high"), (1.0, 1.0, 0.0))

    def test_same_change_needs_signal_and_a_seeing_oracle(self):
        self.assertEqual(lab.same_change(.0, [-.04, .04], 30, 10, True), "PROVEN")
        self.assertEqual(lab.same_change(.0, [-.2, .2], 30, 10, True), "NOT-PROVEN")
        self.assertEqual(lab.same_change(-.06, [-.2, .1], 30, 10, True), "KILL")
        self.assertEqual(lab.same_change(.0, [-.01, .01], 19, 10, True), "NO-INFORMATION")
        self.assertEqual(lab.same_change(.0, [-.01, .01], 30, 7, True), "NO-INFORMATION")
        self.assertEqual(lab.same_change(.0, [-.01, .01], 30, 10, False), "NO-INFORMATION")


class Contract(unittest.TestCase):
    def test_pinned_literal_needs_to_be_new_and_in_the_reference(self):
        block = 'assert.match(x, /job com falhas/); use("already_known")'
        self.assertEqual(lab.pinned(block, 'label = "job com falhas parciais"; already_known()', "already_known"), {"job com falhas", "falhas"})

    def test_contract_reaches_the_prompt_and_trailers_do_not(self):
        text = lab.prompt_for({}, "feat: x\n\nbody\n\nCo-Authored-By: a <a@a>", ["job_sweep"])
        self.assertIn("`job_sweep`", text)
        self.assertNotIn("Co-Authored", text)


class DashboardSeams(unittest.TestCase):
    def test_live_snapshot_keeps_heavy_evidence_and_refreshes_sessions(self):
        import dashboard
        built = threading.Event()

        def build():
            built.set()
            return {"generated_at": "old", "aggregate": {"activity": {"sessions": 0}, "other": 1}, "projects": [{"project_id": "p", "activity": {"sessions": 0}, "observatory": "heavy"}]}
        live = dashboard.LiveSnapshot(build, lambda: [], lambda entries: {"aggregate": {"sessions": 2}, "projects": {"p": {"sessions": 2}}}, pause_s=60)
        built.wait(2)
        while live.latest is None:
            time.sleep(.01)
        read = live.read()
        self.assertEqual((read["projects"][0]["activity"], read["projects"][0]["observatory"], read["aggregate"]["activity"], read["aggregate"]["other"]), ({"sessions": 2}, "heavy", {"sessions": 2}, 1))
        self.assertNotEqual(read["generated_at"], "old")

    def test_live_snapshot_is_none_until_the_first_build(self):
        import dashboard
        gate = threading.Event()
        self.addCleanup(gate.set)
        live = dashboard.LiveSnapshot(lambda: gate.wait(5), lambda: [], lambda entries: {}, pause_s=60)
        self.assertIsNone(live.read())

    def test_arms_are_ordered_low_to_high_and_unreadable_is_empty(self):
        import choice_observatory as observatory
        analysis = {"contrasts": {"medium_vs_xhigh": {"medium": {"accepted": 3}, "xhigh": {"accepted": 3}}, "low_vs_xhigh": {"low": {"accepted": 2}, "xhigh": {"accepted": 3}}}}
        self.assertEqual(list(observatory.arms(analysis)), ["low", "medium", "xhigh"])
        self.assertEqual(observatory.arms({"contrasts": {}}), {})

    def test_lab_report_is_read_only_from_the_configured_path(self):
        import dashboard
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "config.json").write_text(json.dumps({"observatory": {"lab_report": str(root / "report.json")}}))
            self.assertIsNone(dashboard.load_lab_report(root / "config.json"))
            (root / "report.json").write_text(json.dumps({"verdict": {"durability": "NOT-PROVEN"}}))
            self.assertEqual(dashboard.load_lab_report(root / "config.json"), {"durability": "NOT-PROVEN", "bound_to": None})  # a bare path binds nothing
            (root / "config.json").write_text("{}")
            self.assertIsNone(dashboard.load_lab_report(root / "config.json"))


def cell(task, arm, rep, passing, tests=("a", "b", "c", "d")):
    return {"task": task, "arm": arm, "replicate": rep, "valid": True, "acceptance_outcomes": {k: "pass" if k in passing else "fail" for k in tests}}


class ReachableBehaviour(unittest.TestCase):
    """The instrument fixes from the 2026-11-04 method review: scale, symmetric verdict, pseudo A/A, feasibility, sufficiency."""

    def tasks(self, root, n, baseline=("a",)):
        for i in range(n):
            (root / "tasks" / f"T{i}").mkdir(parents=True)
            (root / "tasks" / f"T{i}" / "hidden.json").write_text(json.dumps(["__module__", "a", "b", "c", "d"]))
            (root / "tasks" / f"T{i}" / "baseline.json").write_text(json.dumps(list(baseline)))

    def test_reachable_scale_drops_base_passing_and_never_passed_tests_but_keeps_agreement(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.tasks(root, 1)
            rows = [cell("T0", "medium", 1, {"a", "b", "c"}), cell("T0", "xhigh", 1, {"a", "b"})]
            # a passes at base, d never passes: reachable = b, c; medium 2/2, xhigh 1/2
            self.assertEqual(lab.reachable_diffs(rows, root / "tasks", "medium", "xhigh"), {"T0": 0.5})
            aa = [cell("T0", "medium", 1, {"b", "c"}), cell("T0", "medium", 2, {"b"}), cell("T0", "medium", 3, {"b"})]
            self.assertEqual(lab.reachable_diffs(aa, root / "tasks", "medium", "xhigh", split="medium"), {"T0": 0.5})

    def test_tests_the_commit_left_untouched_are_old_behaviour(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            git(repo, "init", "-qb", "main")
            body = "class X(unittest.TestCase):\n    def test_old(self):\n        pass\n\n    def test_edit(self):\n        pass\n"
            base = commit(repo, {"tests/test_x.py": body}, "base", "2026-01-01T00:00:00Z")
            edited = body.replace("    def test_edit(self):\n        pass\n", "    def test_edit(self):\n        assert 1\n\n    def test_new(self):\n        pass\n")
            sha = commit(repo, {"tests/test_x.py": edited, "tests/test_y.py": "def test_added():\n    pass\n"}, "change", "2026-01-02T00:00:00Z")
            self.assertEqual(lab.unedited_tests(repo, base, sha, ["tests/test_x.py", "tests/test_y.py"], "unittest"), {"test_old"})
        self.assertEqual(lab.leaf("tests/test_x.py :: 0 :: X.test_old", "unittest"), "test_old")
        self.assertEqual(lab.leaf("example.com/json :: 0 :: TestMarshal/nested_case", "go"), "TestMarshal")

    def test_verdict_is_symmetric_a_point_estimate_never_kills(self):
        wide = {"tasks": 20, "mean": -.06, "ci95": [-.20, .08]}
        self.assertEqual(lab.behaviour_verdict(wide, True), "NOT-PROVEN")
        self.assertEqual(lab.behaviour_verdict({"tasks": 20, "mean": -.08, "ci95": [-.12, -.04]}, True), "KILL")
        self.assertEqual(lab.behaviour_verdict({"tasks": 20, "mean": .0, "ci95": [-.02, .02]}, True), "PROVEN")
        self.assertEqual(lab.behaviour_verdict({"tasks": 5, "mean": .0, "ci95": [-.02, .02]}, True), "NO-INFORMATION")
        self.assertEqual(lab.behaviour_verdict({"tasks": 20, "mean": .0, "ci95": [-.02, .02]}, False), "NO-INFORMATION")

    def test_paired_interval_uses_t_on_tasks(self):
        out = lab.paired_interval({"T0": .1, "T1": -.1, "T2": .0})
        self.assertAlmostEqual(out["mean"], 0)
        self.assertAlmostEqual(out["ci95"][1], 4.303 * .1 / 3 ** .5, places=6)
        self.assertEqual(lab.t975(30), 2.042)
        self.assertAlmostEqual(lab.t975(31), 2.0395, places=4)
        self.assertAlmostEqual(lab.t975(40), 2.0211, places=4)
        self.assertAlmostEqual(lab.t975(120), 1.9799, places=4)

    def test_proven_beats_a_critical_value_simulated_from_the_run(self):
        sample = {"tasks": 20, "mean": .0, "sd": .05, "ci95": [-.023, .023]}  # studentized (0 + .03) / (.05 / 20 ** .5) = 2.68
        self.assertEqual(lab.behaviour_verdict(sample, True, critical=2.5), "PROVEN")
        self.assertEqual(lab.behaviour_verdict(sample, True, critical=3.0), "NOT-PROVEN")
        self.assertEqual(lab.behaviour_verdict(sample, True, critical=float("inf")), "NOT-PROVEN")
        self.assertEqual(lab.behaviour_verdict({"tasks": 20, "mean": -.08, "sd": .05, "ci95": [-.12, -.04]}, True, critical=2.5), "KILL")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.tasks(root, 10)
            rows = [cell(f"T{i}", arm, rep, {"a", "b", "c"} if (i + rep) % 3 else {"a", "b"}) for i in range(10) for arm in ("medium", "xhigh") for rep in (1, 2)]
            with mock.patch.dict(lab.GATES, {"draws": 300}):
                critical = lab.proven_critical(rows, root / "tasks", "medium", "xhigh", 7)
                self.assertEqual(critical, lab.proven_critical(rows, root / "tasks", "medium", "xhigh", 7))
                self.assertGreater(critical, 0)
                self.assertTrue(0 <= lab.false_proven(rows, root / "tasks", "medium", "xhigh", 7) <= 1)
                self.assertIsNone(lab.proven_critical(rows[:28], root / "tasks", "medium", "xhigh", 7))  # 7 tasks
                self.assertIsNone(lab.proven_critical(rows, root / "tasks", "medium", "xhigh", 7, margin=.9))  # cannot lose 90 points of ~83
                planned = lab.proven_critical(rows, root / "tasks", "medium", "xhigh", 7, attempts=8)
                self.assertNotEqual(planned, critical)
                self.assertEqual(planned, lab.proven_critical(rows, root / "tasks", "medium", "xhigh", 7, attempts=8))

    def test_proven_critical_takes_the_larger_of_independent_and_clustered_loss(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.tasks(root, 10)
            rows = [cell(f"T{i}", arm, rep, {"a", "b", "c"} if (i + rep) % 3 else {"a", "b"}) for i in range(10) for arm in ("medium", "xhigh") for rep in (1, 2)]
            with mock.patch.dict(lab.GATES, {"draws": 300}):
                # pinned from the code before 1.11.0 (proven_critical without `loss`): the independent model is unchanged draw for draw
                self.assertEqual(lab.proven_critical(rows, root / "tasks", "medium", "xhigh", 7, loss=("independent",)), 2.749545416973504)
                self.assertEqual(lab.proven_critical(rows, root / "tasks", "medium", "xhigh", 7, attempts=8, loss=("independent",)), 2.588732983824029)
                each = [lab.proven_critical(rows, root / "tasks", "medium", "xhigh", 7, loss=(m,)) for m in lab.LOSS_MODELS]
                self.assertEqual(lab.proven_critical(rows, root / "tasks", "medium", "xhigh", 7), max(each))
                for bad in ((), ("correlated",)):
                    with self.assertRaises(ValueError):
                        lab.proven_critical(rows, root / "tasks", "medium", "xhigh", 7, loss=bad)
            with mock.patch.dict(lab.GATES, {"draws": 2000}):
                for attempts in (1, 2, 4):
                    draws = {m: list(lab.whole_loss_draws(rows, root / "tasks", "medium", "xhigh", 7, .3, attempts=attempts, clustered=m))
                             for m in (False, True)}
                    for m, sets in draws.items():  # both models lose the margin on average
                        self.assertAlmostEqual(statistics.fmean(v for s in sets for v in s.values()), -.3, delta=.02, msg=(attempts, m))
                    if attempts == 1:  # one attempt: losing it alone or with the task's others is the same draw
                        self.assertEqual(draws[False], draws[True])
                    else:  # clustered: a lost task's attempts all fail, so per-task differences spread further
                        spread = {m: statistics.pstdev(v for s in sets for v in s.values()) for m, sets in draws.items()}
                        self.assertGreater(spread[True], spread[False])

    def test_a_frozen_reach_set_fixes_the_denominator(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.tasks(root, 2)
            rows = [cell("T0", "medium", 1, {"a", "b"}), cell("T0", "xhigh", 1, {"a", "b", "c"}), cell("T1", "medium", 1, {"b"}), cell("T1", "xhigh", 1, {"b"})]
            self.assertEqual(lab.reachable_diffs(rows, root / "tasks", "medium", "xhigh"), {"T0": -.5, "T1": .0})
            # frozen from earlier attempts: c and d count for T0 although only one fresh cell passes them; T1 is outside the set
            self.assertEqual(lab.reachable_diffs(rows, root / "tasks", "medium", "xhigh", reach={"T0": ["b", "c", "d"]}), {"T0": -1 / 3})

    def test_feasibility_says_before_spending_what_a_verdict_needs(self):
        self.assertEqual(lab.tasks_needed(.154, .03), 207)
        self.assertIsNone(lab.tasks_needed(.1, .03, delta=-.05))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "set.json").write_text(json.dumps({"compare": {"candidate": "medium", "reference": "xhigh"}, "tasks": [{"id": f"T{i}"} for i in range(24)]}))
            out = lab.feasibility(root / "set.json", None, sd=.154)
            self.assertEqual(out["tasks_needed_if_equal"], 207)
            self.assertLess(out["power_proven_if_equal"], .2)
            with self.assertRaises(ValueError):
                lab.feasibility(root / "set.json", None)
            with self.assertRaises(ValueError):
                lab.feasibility(root / "set.json", None, sd=0.0)

    def test_feasibility_counts_only_the_tasks_a_pilot_reaches(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.tasks(root, 4)
            (root / "set.json").write_text(json.dumps({"compare": {"candidate": "medium", "reference": "xhigh"}, "tasks": [{"id": f"T{i}"} for i in range(24)]}))
            # T0 and T1 reach b; T2 and T3 pass only a, which passes at base
            rows = [cell(t, arm, 1, {"a", "b"} if t in ("T0", "T1") else {"a"}) for t in ("T0", "T1", "T2", "T3") for arm in ("medium", "xhigh")]
            with mock.patch.object(lab, "load_cells", return_value=rows):
                out = lab.feasibility(root / "set.json", root, sd=.154)
            self.assertEqual(out["reach_share"], .5)
            self.assertEqual(out["planned_reaching"], 12)
            self.assertAlmostEqual(out["planned_halfwidth"], 1.96 * .154 / 12 ** .5)
            self.assertEqual(out["tasks_needed_if_equal"], 207)
            self.assertEqual(out["tasks_to_mine_if_equal"], 414)

    def test_sufficiency_drops_tasks_the_prompt_cannot_reach(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.tasks(root, 2, baseline=())
            (root / "sensitivity.json").write_text("{}")
            (root / "set.json").write_text(json.dumps({"tasks": [{"id": "T0"}, {"id": "T1"}]}))
            original = lab.load_cells
            lab.load_cells = lambda _: [cell("T0", "calib", 1, {"a", "b", "c", "d"}), cell("T1", "calib", 1, {"a"})]
            try:
                out = lab.sufficiency(root / "set.json", root, .8, root / "filtered" / "set.json")
            finally:
                lab.load_cells = original
            self.assertEqual([t for t, _ in out["kept"]], ["T0"])
            self.assertEqual([t for t, _ in out["dropped"]], ["T1"])
            self.assertEqual([t["id"] for t in json.loads((root / "filtered" / "set.json").read_text())["tasks"]], ["T0"])
            self.assertTrue((root / "filtered" / "tasks").is_symlink())

    def test_sufficiency_never_counts_old_behaviour_an_empty_patch_passes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.tasks(root, 1, baseline=("a", "b", "c"))
            (root / "set.json").write_text(json.dumps({"tasks": [{"id": "T0"}]}))
            original = lab.load_cells
            lab.load_cells = lambda _: [cell("T0", "calib", 1, {"a", "b", "c"})]  # old behaviour only: 3/4 of hidden
            try:
                out = lab.sufficiency(root / "set.json", root, .7, root / "filtered" / "set.json")
            finally:
                lab.load_cells = original
            self.assertEqual(out["dropped"], [("T0", 0.0)])


# Recorded numbers only, under neutral labels: counts, rates and intervals of the D-2 gate (2026-11-14) and of the go-json
# studies. No repository content. A tuple of reasons is the order the verdict lists them in.
REPO_A = {"tasks": 7, "sensitivity": {"mutants": 42, "rejected": 17}, "load_sensitive": []}
REPO_B = {"tasks": 52, "sensitivity": {"mutants": 310, "rejected": 92}, "load_sensitive": []}
# repo-C: 24 mined tasks with their gate; reference acceptance, saving, SD and reach come from an earlier 24-task replay of the
# same repository (accepted xhigh 3 of 70; median per-task saving 0.679; SD 0.198 over 21 reaching tasks, replicates 1 and 2).
# The 9 accepted cells of both arms fell in 3 distinct tasks, so no arm had more than 3 of 24.
REPO_C = {"tasks": 24, "sensitivity": {"mutants": 136, "rejected": 46}, "load_sensitive": [], "reference_acceptance": [3, 70],
          "saving": 0.6793728227263807, "sd": 0.19758041884322772, "reach_share": 21 / 24, "accepted_task_share": {"candidate": 3 / 24, "reference": 3 / 24}}
# Study F as planned (PREREG-F): the 2026-11-07 Claude run on go-json's 41 reaching commits, 2 attempts per arm. SD from its
# primary t interval [-0.118, +0.0073] around -0.0553; xhigh accepted 63/82, medium 55/81, so at least 32 and 28 distinct tasks
# had an accepted cell; 36 commits had one in some attempt; median cost US$0.568 vs US$2.272. Oracle: go-json's mined set,
# 255 of 321 planted defects rejected.
GO_JSON_PLANNED = {"tasks": 41, "sensitivity": {"mutants": 321, "rejected": 255}, "load_sensitive": [], "reach_share": 1.0,
                   "sd": (0.0073296801017865496 + 0.055326787034104104) * 41 ** .5 / lab.t975(40), "sufficient_share": 36 / 41,
                   "reference_acceptance": [63, 82], "saving": 1 - 0.5682964 / 2.27185, "accepted_task_share": {"candidate": 28 / 41, "reference": 32 / 41},
                   "declared_margin": 0.2}
# Study F's own cells (RESULT-F): interval [-0.030, +0.047] around +0.0085; xhigh 61/81, medium 56/82 accepted; mean cost per
# cell US$0.70 vs US$2.90 (no median published).
GO_JSON_F = {**GO_JSON_PLANNED, "sd": (0.047348909666070395 - 0.00848210644074907) * 41 ** .5 / lab.t975(40), "reference_acceptance": [61, 81],
             "saving": 1 - 0.70 / 2.90, "accepted_task_share": {"candidate": 28 / 41, "reference": 31 / 41}, "sufficient_share": 31 / 41}


class Viability(unittest.TestCase):
    """`007 lab viability`: whether a repository can give a decisive verdict, from recorded numbers, before any paid run."""

    def reasons(self, result):
        return tuple(r["reason"] for r in result["reasons"])

    def test_the_three_d2_repositories_read_not_viable_for_their_recorded_reason(self):
        a, b, c = map(lab.viability_verdict, (REPO_A, REPO_B, REPO_C))
        self.assertEqual((a["verdict"], self.reasons(a)), ("NOT-VIABLE", ("too-few-tasks",)))  # its oracle passed (17/42)
        self.assertEqual((b["verdict"], self.reasons(b)), ("NOT-VIABLE", ("oracle-blind",)))
        low, high = b["derived"]["sensitivity"]["clopper_pearson95"]
        self.assertLess(low, .30)  # the interval straddles the gate (Wilson 0.249-0.35 in the record): the point estimate decides,
        self.assertGreater(high, .30)  # as report() does
        self.assertAlmostEqual(b["derived"]["sensitivity"]["rate"], .2968, places=4)
        self.assertEqual((c["verdict"], self.reasons(c)), ("NOT-VIABLE", ("reference-does-not-deliver", "pays-unreachable", "underpowered")))
        self.assertAlmostEqual(c["derived"]["break_even_margin"], 0.029115978116844885)  # the recorded break-even margin
        self.assertAlmostEqual(c["derived"]["power_proven_if_equal"], .0994, places=3)
        pooled = lab.viability_verdict({**REPO_C, "reference_acceptance": [9, 141]})  # both arms pooled, as the record also quotes it
        self.assertIn("reference-does-not-deliver", self.reasons(pooled))

    def test_go_json_study_f_reads_viable_as_planned_and_on_its_own_cells(self):
        for inputs in (GO_JSON_PLANNED, GO_JSON_F):
            out = lab.viability_verdict(inputs)
            self.assertEqual((out["verdict"], out["reasons"], out["missing"], out["notes"]), ("VIABLE", [], [], []))
            self.assertEqual(out["derived"]["break_even_margin"], .20)  # PREREG-F's m = min(0.20, 0.768 x 0.75)
            self.assertGreater(out["derived"]["power_proven_if_equal"], .99)

    def test_each_reason_fires_alone(self):
        cases = {"too-few-tasks": {"tasks": 7}, "load-sensitive-oracle": {"load_sensitive": ["T1"]},
                 "oracle-blind": {"sensitivity": {"mutants": 100, "rejected": 29}},
                 "oracle-blind-v2": {"sensitivity_v2": {"decision": "fails", "sensitivity": .1, "interval": [.05, .2]}},
                 "too-few-reaching-tasks": {"reach_share": 7 / 41}, "prompt-insufficient": {"sufficient_share": 7 / 41},
                 "reference-does-not-deliver": {"reference_acceptance": [20, 82], "saving": 1.0},
                 "pays-unreachable": {"accepted_task_share": {"candidate": 3 / 41, "reference": 32 / 41}},
                 "underpowered": {"sd": .9}}
        for reason, change in cases.items():
            with self.subTest(reason):
                out = lab.viability_verdict({**GO_JSON_PLANNED, **change})
                self.assertEqual((out["verdict"], self.reasons(out)), ("NOT-VIABLE", (reason,)))
        few_mutants = lab.viability_verdict({**GO_JSON_PLANNED, "sensitivity": {"mutants": 19, "rejected": 19}})
        self.assertEqual(self.reasons(few_mutants), ("oracle-blind",))  # report's gate: 20 mutants at least
        for decision in ("passes", "indeterminate", "no-information", "floor-unset"):  # v2 is not qualified: only `fails` decides
            self.assertEqual(lab.viability_verdict({**GO_JSON_PLANNED, "sensitivity_v2": {"decision": decision}})["verdict"], "VIABLE")
        nothing_saved = lab.viability_verdict({**GO_JSON_PLANNED, "saving": -.1})
        self.assertEqual((self.reasons(nothing_saved), nothing_saved["derived"]["break_even_margin"]), (("underpowered",), 0.0))

    def test_missing_data_reads_unknown_never_viable(self):
        for key in lab.VIABILITY_INPUTS:
            with self.subTest(key):
                out = lab.viability_verdict({k: v for k, v in GO_JSON_PLANNED.items() if k != key})
                self.assertEqual((out["verdict"], out["missing"]), ("UNKNOWN", [key]))
        empty = lab.viability_verdict({})
        self.assertEqual((empty["verdict"], empty["missing"]), ("UNKNOWN", list(lab.VIABILITY_INPUTS)))
        # a known failure decides whatever is missing
        self.assertEqual(lab.viability_verdict({"tasks": 3})["verdict"], "NOT-VIABLE")

    def test_a_declared_margin_off_break_even_is_noted(self):
        out = lab.viability_verdict({**GO_JSON_PLANNED, "declared_margin": .03})
        self.assertEqual(out["verdict"], "VIABLE")
        self.assertIn("break-even margin 0.2", out["notes"][0])

    def test_unknown_or_malformed_inputs_are_refused(self):
        for bad in ({"task": 41}, {"tasks": "41"}, {"tasks": True}, {"reach_share": 1.5}, {"sd": 0}, {"reference_acceptance": [5, 4]},
                    {"reference_acceptance": [1, 0]}, {"sensitivity": {"mutants": 3, "rejected": 4}}, {"accepted_task_share": {}},
                    {"saving": float("nan")}, {"sensitivity_v2": {"sensitivity": .1}}):
            with self.subTest(bad), self.assertRaises(ValueError):
                lab.viability_verdict(bad)

    def test_accepted_task_shares_name_both_roles_and_v2_a_known_decision(self):
        # one favourable arm, a misspelled arm or a typo in the v2 decision must not pass as a complete input
        for bad in ({"accepted_task_share": {"candidate": 1.0}}, {"accepted_task_share": {"medium": .9, "xhigh": .9}},
                    {"accepted_task_share": {"candidate": .9, "reference": .9, "other": .1}}, {"sensitivity_v2": {"decision": "fail"}}):
            with self.subTest(bad), self.assertRaises(ValueError):
                lab.viability_verdict({**GO_JSON_PLANNED, **bad})

    def test_a_known_zero_break_even_margin_decides_at_once(self):
        # nothing saved: the margin is 0 whatever the reference acceptance, SD or reach turn out to be
        for saving in (0.0, -.3):
            with self.subTest(saving):
                out = lab.viability_verdict({"tasks": 41, "saving": saving})
                self.assertEqual((out["verdict"], self.reasons(out), out["derived"]["break_even_margin"]), ("NOT-VIABLE", ("underpowered",), 0.0))

    def write_set(self, root, n, sensitivity, v2=None):
        for i in range(n):
            (root / "tasks" / f"T{i}").mkdir(parents=True)
            (root / "tasks" / f"T{i}" / "hidden.json").write_text(json.dumps(["__module__", "a", "b", "c", "d"]))
            (root / "tasks" / f"T{i}" / "baseline.json").write_text(json.dumps(["a"]))
        (root / "set.json").write_text(json.dumps({"compare": {"candidate": "medium", "reference": "xhigh", "margin": .2}, "tasks": [{"id": f"T{i}"} for i in range(n)]}))
        (root / "sensitivity.json").write_text(json.dumps(sensitivity))
        if v2 is not None:
            (root / "sensitivity-v2.json").write_text(json.dumps(v2))

    def test_inputs_are_read_from_the_set_and_a_pilot_of_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.write_set(root, 10, {"immediate": {"mutants": 40, "rejected": 30, "passed": True}, "load_sensitive": []})
            rows = []
            for i in range(10):
                for rep in (1, 2):
                    whole = i >= 5 or bool((i + rep) % 2)  # half the tasks lose d in one attempt: a spread to plan with
                    rows.append({**cell(f"T{i}", "medium", rep, {"a", "b", "c", "d"} if whole else {"a", "b", "c"}), "cell": f"T{i}-r0{rep}-medium",
                                 "accepted": whole, "cost_usd": 1.0})
                    rows.append({**cell(f"T{i}", "xhigh", rep, {"a", "b", "c", "d"}), "cell": f"T{i}-r0{rep}-xhigh", "accepted": True, "cost_usd": 4.0})
            with mock.patch.object(lab, "load_cells", return_value=rows):
                out = lab.viability(root / "set.json", root)
            inputs = out["inputs"]
            self.assertEqual((inputs["tasks"], inputs["reach_share"], inputs["sufficient_share"], inputs["reference_acceptance"]), (10, 1.0, 1.0, [20, 20]))
            self.assertEqual((inputs["saving"], inputs["accepted_task_share"], inputs["declared_margin"]), (.75, {"candidate": 1.0, "reference": 1.0}, .2))
            self.assertEqual(inputs["sensitivity"], {"mutants": 40, "rejected": 30})
            self.assertEqual(out["sources"]["sensitivity"], "sensitivity.json immediate")
            self.assertEqual(out["verdict"], "VIABLE")
            # stated numbers win over the pilot and say so
            with mock.patch.object(lab, "load_cells", return_value=rows):
                stated = lab.viability(root / "set.json", root, {"reference_acceptance": [2, 20]})
            self.assertEqual((stated["verdict"], self.reasons(stated), stated["sources"]["reference_acceptance"]),
                             ("NOT-VIABLE", ("reference-does-not-deliver",), "stated"))
            with mock.patch.object(lab, "load_cells", return_value=rows + [{**rows[0], "task": "OTHER"}]), self.assertRaises(ValueError):
                lab.viability(root / "set.json", root)
            with self.assertRaises(ValueError):
                lab.viability(None, root)

    def test_a_sensitivity_without_counts_is_unknown_and_a_failing_v2_is_read(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # a `passed` asserted on a basis, with no mutant counted (go-json's F set carries one): no measure
            tasks = {f"T{i}": {"control": "ok"} for i in range(8)}
            rows = [{"task": f"T{i}", "class": "valid", "outcome": "survived"} for i in range(8) for _ in range(5)]
            self.write_set(root, 8, {"immediate": {"passed": True, "basis": "mined"}, "load_sensitive": []}, {"seed": 1, "rows": rows, "tasks": tasks})
            out = lab.viability(root / "set.json")
            self.assertNotIn("sensitivity", out["inputs"])
            self.assertIn("sensitivity", out["missing"])
            self.assertEqual(out["inputs"]["sensitivity_v2"]["decision"], "fails")
            self.assertEqual((out["verdict"], self.reasons(out)), ("NOT-VIABLE", ("oracle-blind-v2",)))

    def test_cli_prints_json_or_text_and_exits_by_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name, inputs, code in (("b", REPO_B, 1), ("f", GO_JSON_PLANNED, 0), ("u", {"tasks": 41}, 3)):
                (root / f"{name}.json").write_text(json.dumps(inputs))
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(lab.main(["viability", "--inputs", str(root / f"{name}.json")]), code)
                self.assertEqual(json.loads(stdout.getvalue())["verdict"], {0: "VIABLE", 1: "NOT-VIABLE", 3: "UNKNOWN"}[code])
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                lab.main(["viability", "--inputs", str(root / "b.json"), "--format", "text"])
            self.assertTrue(stdout.getvalue().startswith("007 lab viability: NOT-VIABLE\n- oracle-blind: "))
            (root / "bad.json").write_text(json.dumps({"tasks": "many"}))
            for argv in (["viability"], ["viability", "--inputs", str(root / "bad.json")]):
                with self.subTest(argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
                    lab.main(argv)
                self.assertEqual(stop.exception.code, 2)


class AA(unittest.TestCase):
    """`run --aa`: the same arm twice, its discordance and the verdict's own statistic A against A, next to the verdict."""

    def tasks(self, root, n):
        for i in range(n):
            (root / "tasks" / f"T{i}").mkdir(parents=True)
            (root / "tasks" / f"T{i}" / "hidden.json").write_text(json.dumps(["__module__", "a", "b", "c", "d"]))
            (root / "tasks" / f"T{i}" / "baseline.json").write_text(json.dumps(["a"]))

    def check(self, root, cells, tasks=10, replicates=2, **options):
        with mock.patch.dict(lab.GATES, {"draws": 300}):
            return lab.aa_check(cells, root / "tasks", {"arm": "xhigh", "label": "xhigh-aa"}, .03, 7, True,
                                [f"T{i}" for i in range(tasks)], replicates, **options)

    def test_qualification_needs_usable_matched_pairs_and_the_plan(self):
        """Review #5: the equality statistic pools valid cells per task, so originals at replicate 1 and copies at replicate 2
        alone gave a clean interval with no matched pair at all, and qualified."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.tasks(root, 10)
            base = [self.accepted(cell(f"T{i}", "xhigh", rep, {"a", "b", "c", "d"} if (i + rep) % 3 else {"a", "b"})) for i in range(10) for rep in (1, 2)]
            split = [r for r in base if r["replicate"] == 1] + [{**r, "arm": "xhigh-aa"} for r in base if r["replicate"] == 2]
            out = self.check(root, split)
            self.assertEqual((out["discordance"]["pairs"], out["discordance"]["missing_pairs"]), (0, 20))
            self.assertEqual((out["status"], out["rejects_equality"]), ("too-few-tasks", False))
            self.assertIn("matched pair", lab.aa_line(out, .03))
            # the statistic itself is the verdict's own, unchanged: valid cells per task, A against A
            self.assertEqual(out["reachable_behaviour"]["tasks"], 10)
            # without the run's planned replicates, trailing undispatched copies cannot be counted: never qualified
            twins = base + [{**r, "arm": "xhigh-aa"} for r in base]
            unplanned = self.check(root, twins, planned=False)
            self.assertEqual((unplanned["status"], unplanned["discordance"]["pairs"]), ("plan-unknown", 20))
            self.assertIn("report --replicates", lab.aa_line(unplanned, .03))
            self.assertEqual(self.check(root, twins)["status"], "qualified")

    def test_a_copy_set_aside_under_refused_reads_refused_not_absent(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.tasks(root, 10)
            base = [self.accepted(cell(f"T{i}", "xhigh", rep, {"a", "b", "c", "d"})) for i in range(10) for rep in (1, 2)]
            twins = [{**r, "arm": "xhigh-aa"} for r in base if (r["task"], r["replicate"]) != ("T0", 1)]
            out = self.check(root, base + twins, archived={"T0-r01-xhigh-aa"})
            self.assertEqual(out["missing_cells"], {"refused": ["T0-r01-xhigh-aa"]})
            self.assertIn("independent", out["discordance"]["ci95_assumes"])

    @staticmethod
    def accepted(row):
        return {**row, "accepted": all(v == "pass" for k, v in row["acceptance_outcomes"].items() if k != "a")}

    def test_the_copy_is_dispatched_accounted_and_budgeted_like_its_arm(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "set.json"
            arms = {"low": {"model": "m", "effort": "medium", "doctrine": ""}, "xhigh": {"model": "m", "effort": "xhigh", "doctrine": ""}}
            path.write_text(json.dumps({"seed": 1, "arms": arms, "tasks": [{"id": f"T{i}"} for i in range(4)]}))
            seen = []

            def execute(config, task, arm, rep, out, timeout):
                seen.append((arm, config["arms"][arm]))
                cid = f"{task['id']}-r{rep:02d}-{arm}"
                (out / f"{cid}.runner.json").write_text("{}")
                row = {"valid": True, "cost_usd": 1.0}
                (out / f"{cid}.json").write_text(json.dumps(row))
                return row
            with self.assertRaisesRegex(ValueError, "names no arm"):
                lab.run(path, root / "bad", replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=execute, aa="high")
            with self.assertRaisesRegex(ValueError, "must name an arm"):
                lab.run(path, root / "bad", replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=execute, aa=True)
            self.assertEqual(seen, [])
            # the copy's cells take their reserve and their cost like the arm's: the cap stops the run at 9 of 12 cells
            state = lab.run(path, root / "capped", replicates=1, jobs=1, max_calls=99, max_usd=9, stop_usd=1, execute=execute, aa="xhigh")
            self.assertEqual((state["stop"], state["calls"], state["spent"], state["cells"]), ("usd-budget", 9, 9.0, 12))
            self.assertEqual(state["refused_per_arm"], {"low": 0, "xhigh": 0, "xhigh-aa": 0})
            out = root / "out"
            self.assertEqual(lab.run(path, out, replicates=1, jobs=1, max_calls=9, max_usd=99, stop_usd=1, execute=execute, aa="xhigh")["stop"], "call-budget")
            copies = [policy for arm, policy in seen if arm == "xhigh-aa"]
            self.assertTrue(copies)
            self.assertTrue(all({k: v for k, v in p.items() if k != "aa_of"} == arms["xhigh"] and p["aa_of"] == "xhigh" for p in copies))
            manifest = json.loads((out / "run-manifest.json").read_text())
            self.assertEqual((manifest["aa"], manifest["arms"]), ({"arm": "xhigh", "label": "xhigh-aa"}, arms))  # the set as written
            self.assertEqual(lab.run(path, out, replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=execute)["changed"], ["aa"])
            self.assertEqual(lab.run(path, out, replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=execute, aa="low")["changed"], ["aa"])
            resumed = lab.run(path, out, replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=execute, aa="xhigh")
            self.assertEqual((resumed["stop"], resumed["calls"], resumed["spent"]), (None, 3, 12.0))
            self.assertEqual(sum(1 for _ in out.glob("*-xhigh-aa.json")), 4)
            plain = root / "plain"  # without --aa nothing changes: two arms, no copy, aa sealed as none
            self.assertEqual(lab.run(path, plain, replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=execute)["cells"], 8)
            self.assertIsNone(json.loads((plain / "run-manifest.json").read_text())["aa"])
            self.assertEqual(lab.run(path, plain, replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=execute, aa="xhigh")["changed"], ["aa"])
            config = json.loads(path.read_text())
            path.write_text(json.dumps({**config, "arms": {**arms, "xhigh-aa": arms["xhigh"]}}))
            with self.assertRaisesRegex(ValueError, "already has an arm"):
                lab.run(path, root / "clash", replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1, execute=execute, aa="xhigh")

    def test_an_identical_copy_gives_zero_discordance_and_qualifies(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.tasks(root, 10)
            base = [self.accepted(cell(f"T{i}", "xhigh", rep, {"a", "b", "c", "d"} if (i + rep) % 3 else {"a", "b"})) for i in range(10) for rep in (1, 2)]
            out = self.check(root, base + [{**r, "arm": "xhigh-aa"} for r in base])
            self.assertEqual(out["discordance"]["pairs"], 20)
            self.assertEqual((out["discordance"]["discordant"], out["discordance"]["rate"], out["discordance"]["missing_pairs"]), (0, 0.0, 0))
            self.assertEqual(out["discordance"]["ci95"][0], 0.0)
            self.assertLess(out["discordance"]["ci95"][1], .2)  # Clopper-Pearson upper bound for 0 of 20: 0.168
            self.assertEqual((out["reachable_behaviour"]["mean"], out["reachable_behaviour"]["ci95"]), (0, [0.0, 0.0]))
            self.assertEqual((out["rejects_equality"], out["status"], out["same_change_reachable"]), (False, "qualified", "PROVEN"))
            self.assertEqual(out["per_task"]["T0"], {"pairs": 2, "discordant": 0, "missing": 0})
            only = self.check(root, base)  # the arm alone: no copy, never qualified
            self.assertEqual((only["status"], only["discordance"]["pairs"], only["discordance"]["missing_pairs"]), ("absent", 0, 20))
            few = self.check(root, base[:4] + [{**r, "arm": "xhigh-aa"} for r in base[:4]], tasks=2)
            self.assertEqual(few["status"], "too-few-tasks")

    def test_a_planted_noisy_copy_rejects_equality_and_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.tasks(root, 10)
            base = [self.accepted(cell(f"T{i}", "xhigh", rep, {"a", "b", "c", "d"} if (i + rep) % 4 else {"a", "b", "c"})) for i in range(10) for rep in (1, 2)]
            # planted: the copy loses one or two of the three reachable tests on every task, as a noisy instrument would
            noisy = [self.accepted(cell(f"T{i}", "xhigh-aa", rep, {"a", "b"} if (i + rep) % 2 else {"a", "b", "c"})) for i in range(10) for rep in (1, 2)]
            out = self.check(root, base + noisy)
            self.assertTrue(out["rejects_equality"])
            self.assertGreater(out["reachable_behaviour"]["ci95"][0], 0)
            self.assertEqual(out["status"], "rejects-equality")
            self.assertGreater(out["discordance"]["discordant"], 0)
            self.assertEqual(out["discordance"]["rate"], out["discordance"]["discordant"] / 20)
            line = lab.aa_line(out, .03)
            self.assertIn("the A/A rejects equality at the verdict's 95% level", line)
            self.assertIn("the verdict is not A/A-qualified", line)

    def test_missing_refused_invalid_and_unreadable_copies_are_reported_never_agreement(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.tasks(root, 10)
            base = [self.accepted(cell(f"T{i}", "xhigh", rep, {"a", "b", "c", "d"})) for i in range(10) for rep in (1, 2)]
            twins = {(r["task"], r["replicate"]): {**r, "arm": "xhigh-aa"} for r in base}
            del twins[("T0", 1)]  # never dispatched or lost
            twins[("T1", 1)] = {**twins[("T1", 1)], "valid": False, "accepted": False, "failure_class": "timeout"}
            twins[("T2", 2)] = {**twins[("T2", 2)], "valid": False, "accepted": False, "failure_class": "provider-rate-limit"}
            twins[("T3", 1)] = {**twins[("T3", 1)], "outcomes_unreadable": True, "accepted": False}
            arm = [r if (r["task"], r["replicate"]) != ("T4", 2) else {**r, "valid": False, "failure_class": "agent-exit"} for r in base]
            out = self.check(root, arm + list(twins.values()))
            d_ = out["discordance"]
            self.assertEqual((d_["pairs"], d_["discordant"], d_["missing_pairs"]), (15, 0, 5))
            self.assertEqual(out["missing_cells"], {"absent": ["T0-r01-xhigh-aa"], "invalid": ["T1-r01-xhigh-aa", "T4-r02-xhigh"],
                                                    "refused": ["T2-r02-xhigh-aa"], "unreadable": ["T3-r01-xhigh-aa"]})
            self.assertEqual(out["per_task"]["T1"], {"pairs": 1, "discordant": 0, "missing": 1})
            self.assertEqual((d_["rate"], d_["worst_case_rate"]), (0.0, 5 / 20))  # missing pairs count as discordant, never as agreement
            line = lab.aa_line(out, .03)
            self.assertIn("acceptance differs in 0 of 15 pairs", line)
            self.assertIn("5 pairs have an absent or unusable cell, never counted as agreement (worst case 25.0%)", line)
            self.assertIn("not A/A-qualified", lab.aa_line(None, .03))
            self.assertIn("not A/A-qualified", lab.aa_line(self.check(root, arm), .03))


def graded(task, arm, rep, exit_code, *, valid=True, report=True, failure="none"):
    """A synthetic replay cell as the grader leaves it: one lab_accept exit, its report (or none) and the cell's reading."""
    accepted = valid and exit_code == 0
    return {"task": task, "arm": arm, "replicate": rep, "valid": valid, "accepted": accepted, "failure_class": failure,
            "acceptance": [{"exit": exit_code}], "acceptance_outcomes": {"a": "pass" if accepted else "fail"} if report else "unavailable"}


class OracleHealth(unittest.TestCase):
    """Backlog 0.4: a broken grader rings while the run is in flight, never per arm, and never moves a verdict."""

    def mixed(self, accepted, rejected, arms=("medium", "xhigh")):
        rows = [graded(f"T{i}", arms[i % 2], 1, 0) for i in range(accepted)]
        return rows + [graded(f"U{i}", arms[i % 2], 1, 1) for i in range(rejected)]

    def test_thresholds_follow_the_verdicts_acceptance_gates(self):
        t = lab.ORACLE_THRESHOLDS
        self.assertEqual((t["zero_accepted_after"], t["all_accepted_after"], t["min_count"]), (17, 44, 3))
        self.assertLess((1 - lab.GATES["floor"]) ** t["zero_accepted_after"], .01)
        self.assertGreater((1 - lab.GATES["floor"]) ** (t["zero_accepted_after"] - 1), .01)
        self.assertLess(lab.GATES["ceiling"] ** t["all_accepted_after"], .01)
        self.assertGreater(lab.GATES["ceiling"] ** (t["all_accepted_after"] - 1), .01)

    def test_a_0_of_124_replay_rings(self):
        rejected = [graded(f"T{i % 62}", ("medium", "xhigh")[i // 62], 1, 1) for i in range(124)]
        health = lab.oracle_health(rejected, .03)
        self.assertEqual((health["alarms"], health["status"], health["graded"]), (["rejects-everything"], "oracle-suspect", 124))
        # the 2026-11-15 grader: a KeyError exited 1 before writing its report, so each rejection had no grade behind it
        crashed = [{**r, "acceptance_outcomes": "unavailable"} for r in rejected]
        health = lab.oracle_health(crashed, .03)
        self.assertEqual((health["alarms"], health["classes"]["oracle-error"], health["exit_codes"]), (["oracle-errors"], 124, {"1": 124}))
        self.assertEqual(lab.oracle_health(rejected[:16], .03)["alarms"], [])  # 16: an honest oracle at the floor gives this over 1% of the time

    def test_an_all_accept_run_rings(self):
        self.assertEqual(lab.oracle_health(self.mixed(44, 0), .03)["alarms"], ["accepts-everything"])
        self.assertEqual(lab.oracle_health(self.mixed(43, 0), .03)["alarms"], [])

    def test_an_internal_error_or_timeout_flood_rings(self):
        legacy = [graded(f"E{i}", "xhigh", 1, 2) for i in range(4)]  # 1.10.0 reading: a valid rejection
        contract = [graded(f"E{i}", "xhigh", 1, 2, valid=False, failure="acceptance-harness-error") for i in range(4)]
        for errors in (legacy, contract):
            health = lab.oracle_health(self.mixed(30, 30) + errors, .03)
            self.assertEqual((health["alarms"], health["classes"]["oracle-error"]), (["oracle-errors"], 4))
        hung = [graded(f"H{i}", "xhigh", 1, 3, report=False) for i in range(4)]
        self.assertEqual(lab.oracle_health(self.mixed(30, 30) + hung, .03)["alarms"], ["oracle-timeouts"])
        self.assertEqual(lab.oracle_health(self.mixed(30, 30) + hung, .1)["alarms"], [])  # 4 of 64 is under a 10-point margin
        killed = graded("K", "xhigh", 1, -9)
        self.assertEqual(lab.oracle_health(self.mixed(30, 30) + [killed], .03)["alarms"], ["exit-contract"])

    def test_a_healthy_mixed_run_stays_silent(self):
        rows = self.mixed(30, 26) + [graded("H", "xhigh", 1, 3, report=False), graded("E", "medium", 1, 2, valid=False, failure="acceptance-harness-error"),
                                     graded("A", "medium", 1, 1, valid=False, failure="agent-exit"),
                                     {"task": "R", "arm": "xhigh", "replicate": 1, "valid": False, "failure_class": "provider-rate-limit", "acceptance": []}]
        health = lab.oracle_health(rows, .03)
        self.assertEqual((health["alarms"], health["status"]), ([], "no-alarm"))
        self.assertEqual(health["classes"], {"accepted": 30, "rejected": 26, "oracle-error": 1, "timeout": 1, "invalid": 2, "unrecorded": 0})
        self.assertEqual(health["exit_codes"], {"0": 30, "1": 27, "2": 1, "3": 1})

    def test_cells_without_grades_are_unmeasured_never_healthy(self):
        rows = [cell("T0", "medium", 1, {"a"}), cell("T0", "xhigh", 1, {"a"})]
        health = lab.oracle_health(rows, .03)
        self.assertEqual((health["status"], health["alarms"], health["classes"]["unrecorded"]), ("unmeasured", [], 2))
        self.assertEqual(lab.oracle_health([], .03)["status"], "unmeasured")

    def test_status_mid_run_is_pooled_and_shows_no_arm(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "set.json").write_text(json.dumps({"compare": {"candidate": "medium", "reference": "xhigh"}}))
            results = root / "results"
            self.assertEqual(lab.status(root / "set.json", results)["oracle_health"]["status"], "unmeasured")  # nothing written yet
            results.mkdir()
            rows = [graded(f"T{i}", "medium", 1, 0) for i in range(5)] + [graded(f"T{i}", "xhigh", 1, 1) for i in range(3)]
            for row in rows:  # each arm's numbers differ, so a per-arm count would show
                (results / f"{row['task']}-r01-{row['arm']}.json").write_text(json.dumps({**row, "runner_receipt_sha256": "unmeasured"}))
            out = lab.status(root / "set.json", results)
            text = json.dumps(out)
            for leak in ("medium", "xhigh", "T0", "per_arm", "r01"):
                self.assertNotIn(leak, text)
            self.assertEqual((out["oracle_health"]["classes"]["accepted"], out["oracle_health"]["classes"]["rejected"]), (5, 3))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(lab.main(["status", "--set", str(root / "set.json"), "--results", str(results)]), 0)


if __name__ == "__main__":
    unittest.main()
