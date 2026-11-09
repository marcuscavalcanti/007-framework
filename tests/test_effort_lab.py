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
        self.assertEqual(lab.report(path, results, None)["verdict"]["margin"], .1)
        self.assertIn("margin 10 points", (results / "report.md").read_text())
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
