"""`007 lab` end to end: a synthetic repository, a fake agent, no model and no vendor."""
import difflib
import json
import os
from pathlib import Path
import subprocess
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
                with self.assertRaisesRegex(ValueError, "not the chain of these results"):
                    lab.report(path, results, self.root / "next")
        manifest.write_text(sealed)
        set_ = json.loads(path.read_text())  # chain picks stage 2's arm from compare: a compare moved since the seal is refused
        path.write_text(json.dumps({**set_, "compare": {**set_["compare"], "reference": set_["compare"]["candidate"]}}))
        with self.assertRaisesRegex(ValueError, "comparison changed"):
            lab.chain(path, results, self.root / "stage2-other")
        path.write_text(json.dumps(set_))
        existing = json.loads((stage2 / "replay-set.json").read_text())
        (stage2 / "replay-set.json").write_text(json.dumps({**existing, "tasks": []}))  # a set a stage 2 may already be sealed on
        with self.assertRaisesRegex(ValueError, "different chain set already exists"):
            lab.chain(path, results, stage2)
        for state, phrase in (("absent", "nothing binds the attempts"), ("sealed-late", "sealed only after some attempts")):
            text = lab.summary({**result, "run_manifest": {"state": state, "compare_changed": None}}, "medium", "high", 2)
            self.assertIn(phrase, text)
        legacy = {k: v for k, v in result.items() if k not in ("run_manifest", "arm_accounting")}  # a v6 report written by 1.7.0
        text = lab.summary(legacy, "medium", "high", 2)
        self.assertNotIn("Run binding", text)
        self.assertNotIn("Cells,", text)

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
        self.assertEqual((a["history"], a["unread_cells"]), ("complete", 0))
        self.assertEqual(a["arms"]["low"], {"planned": 4, "not_dispatched": 2, "no_result": 1, "valid": 1, "accepted": 1, "invalid": {}})
        self.assertEqual(a["arms"]["high"]["invalid"], {"timeout": 1, "unknown": 1})
        chain = {"tasks": [{"id": "T-r100-low-next"}], "arms": {"next": {}}}  # a stage-2 task id carries its parent's replicate
        a = lab.arm_accounting(chain, results, [{"cell": "T-r100-low-next-r01-next", "valid": True, "accepted": False}], {})
        self.assertEqual(a["arms"]["next"]["planned"], 1)
        (results / "dispatch.jsonl").mkdir()  # unreadable ledger: the report still reads, and says so
        self.assertEqual(lab.arm_accounting(config, results, rows, {})["history"], "unreadable")

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
            state = lambda c: {k: v for k, v in lab.sealed_state(c, out).items() if k != "sha256"}
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

    def test_a_rejected_mutant_counts_only_where_the_reference_passes(self):
        rows = [("A", True, (True, None)), ("B", True, (False, None))] + [("A", False, (False, None))] * 10 + [("B", False, (False, None))] * 10
        immediate = lab.sensitivity_summary(rows)["immediate"]
        self.assertEqual((immediate["mutants"], immediate["rejected"]), (10, 10))  # B's oracle rejects even the reference


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


if __name__ == "__main__":
    unittest.main()
