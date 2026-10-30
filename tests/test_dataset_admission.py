"""Literal retained-case/split controls; fixture oracles only, no LLM calls."""
import hashlib
import importlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_replay_capture as capture_fixtures

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
capture = importlib.import_module("replay_capture")
replay = importlib.import_module("replay_eval")


class RetainedExecutionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = capture_fixtures.ReplayCaptureTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.repo, self.root, self.vault = self.fixture.repo, self.fixture.root, self.fixture.vault
        (self.repo / "acceptance.json").write_text(json.dumps({
            "schema": "007-framework/acceptance/v1", "timeout_s": 5,
            "commands": [[sys.executable, "-c", "from pathlib import Path; assert Path('tracked.py').read_bytes() == b'value = 3\\n'"]]}))
        self.ref = self.fixture.capture()
        self.task = {"id": "case", "source_task_id": "task", "project_id": "project", "replay_ref": self.ref}
        self.output = self.root / "cells"
        self.output.mkdir(mode=0o700)
        self.config = {"arms": {"NEW": {"provider": "fixture", "model": "fixture", "effort": "medium", "doctrine": "Keep scope small."}},
                       "agent_command": [sys.executable, "-c", "from pathlib import Path; assert Path('tracked.py').read_bytes() == b'value = 2\\n'; assert Path('ignored.bin').read_bytes() == b'\\x00binary\\xff'; Path('tracked.py').write_bytes(b'value = 3\\n')"]}

    def execute(self):
        try:
            return replay.execute_cell(self.config, self.task, "NEW", 1, self.output, 10, vault_root=self.vault)
        except TypeError as exc:
            if "unexpected keyword argument 'vault_root'" in str(exc):
                self.fail("execute_cell cannot consume retained input bytes")
            raise

    def test_execution_uses_dirty_and_ignored_retained_bytes_without_checkout(self):
        self.repo.rename(self.root / "original-unavailable")
        record = self.execute()
        self.assertTrue(record["valid"])
        self.assertTrue(record["accepted"])
        self.assertEqual(record["source_replay_ref"], self.ref)
        self.assertEqual(record["lines_added"], 1)
        self.assertEqual(record["file_jaccard_diagnostic"], "unmeasured")
        destination = self.root / "restored-output"
        capture.restore_candidate(self.output / "cases", "project", record["task_id"], record["replay_ref"], destination)
        self.assertEqual((destination / "tracked.py").read_bytes(), b"value = 3\n")
        self.assertEqual((destination / "ignored.bin").read_bytes(), b"\x00binary\xff")
        self.assertEqual((destination / "tracked.py").stat().st_mode & 0o777, 0o750)
        self.assertEqual(record["cost_usd"], "unmeasured")
        prompt = self.output / record["effective_prompt"]["path"]
        self.assertEqual(prompt.read_bytes(), b"Preserve this fixture's value.\n\nKeep scope small.")
        self.assertEqual(hashlib.sha256(prompt.read_bytes()).hexdigest(), record["effective_prompt"]["sha256"])

    def test_executor_cannot_replace_the_frozen_acceptance_contract(self):
        self.config["agent_command"] = [sys.executable, "-c", "from pathlib import Path; Path('tracked.py').write_bytes(b'value = 4\\n'); Path('acceptance.json').write_text('{}')"]
        record = self.execute()
        self.assertTrue(record["valid"])
        self.assertFalse(record["accepted"])
        self.assertEqual(record["acceptance"][0]["exit"], 1)
        destination = self.root / "rejected-candidate"
        capture.restore_candidate(self.output / "cases", "project", record["task_id"], record["replay_ref"], destination)
        self.assertEqual((destination / "tracked.py").read_bytes(), b"value = 4\n")

    def test_corrupt_retained_input_stops_before_executor(self):
        marker = self.root / "launched"
        self.config["agent_command"] = [sys.executable, "-c", "from pathlib import Path; Path(" + repr(str(marker)) + ").touch()"]
        (self.vault / "project/task/inputs/tracked.py").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.execute()
        self.assertFalse(marker.exists())

    def test_prompt_override_is_rejected_before_executor(self):
        marker = self.root / "launched"
        self.config["agent_command"] = [sys.executable, "-c", "from pathlib import Path; Path(" + repr(str(marker)) + ").touch()"]
        self.task["prompt"] = "Different task."
        with self.assertRaises(ValueError):
            self.execute()
        self.assertFalse(marker.exists())

    def test_nonzero_executor_still_preserves_a_stable_candidate(self):
        self.config["agent_command"] = [sys.executable, "-c", "from pathlib import Path; Path('tracked.py').write_bytes(b'value = 4\\n'); raise SystemExit(2)"]
        record = self.execute()
        self.assertFalse(record["valid"])
        self.assertFalse(record["accepted"])
        self.assertEqual(record["failure_class"], "agent-exit")
        destination = self.root / "failed-candidate"
        capture.restore_candidate(self.output / "cases", "project", record["task_id"], record["replay_ref"], destination)
        self.assertEqual((destination / "tracked.py").read_bytes(), b"value = 4\n")

    def test_acceptance_override_is_rejected_before_executor(self):
        marker = self.root / "launched"
        self.config["agent_command"] = [sys.executable, "-c", "from pathlib import Path; Path(" + repr(str(marker)) + ").touch()"]
        self.task["acceptance"] = [[sys.executable, "-c", "pass"]]
        with self.assertRaises(ValueError):
            self.execute()
        self.assertFalse(marker.exists())

    def test_existing_cell_is_not_reexecuted_or_overwritten(self):
        marker = self.root / "launched"
        self.config["agent_command"] = [sys.executable, "-c", "from pathlib import Path; Path(" + repr(str(marker)) + ").touch()"]
        cell = self.output / "case-r01-NEW.json"
        cell.write_bytes(b"preserve existing cell")
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertFalse(marker.exists())
        self.assertEqual(cell.read_bytes(), b"preserve existing cell")

    def test_bad_hidden_oracle_hash_stops_before_executor(self):
        marker = self.root / "launched"
        self.config["agent_command"] = [sys.executable, "-c", "from pathlib import Path; Path(" + repr(str(marker)) + ").touch()"]
        oracle = self.root / "oracle.py"
        oracle.write_bytes(b"pass\n")
        self.task["hidden_acceptance"] = [{"source": str(oracle), "target": "oracle.py", "sha256": "0" * 64}]
        with self.assertRaises(ValueError):
            self.execute()
        self.assertFalse(marker.exists())

    def test_failed_output_preservation_cannot_publish_a_valid_cell(self):
        self.config["agent_command"] = [sys.executable, "-c", "from pathlib import Path; Path('tracked.py').unlink(); Path('tracked.py').symlink_to('task.txt')"]
        record = self.execute()
        self.assertFalse(record["valid"])
        self.assertFalse(record["accepted"])
        self.assertEqual(record["candidate_retention"], "unavailable")
        self.assertEqual(record["failure_class"], "candidate-preservation-failed")

    def test_reserved_prompt_path_cannot_be_overwritten_as_an_input(self):
        marker = self.root / "launched"
        self.config["agent_command"] = [sys.executable, "-c", "from pathlib import Path; Path(" + repr(str(marker)) + ").touch()"]
        (self.repo / ".007-prompt.txt").write_bytes(b"original reserved file")
        config = {**self.fixture.config, "files": self.fixture.config["files"] + [".007-prompt.txt"]}
        self.task.update(source_task_id="reserved", replay_ref=capture.capture_input(self.repo, "project", "reserved", config, vault_root=self.vault))
        with self.assertRaises(ValueError):
            self.execute()
        self.assertFalse(marker.exists())

    def test_unconfirmed_cleanup_never_preserves_a_candidate_or_runs_oracle(self):
        from unittest.mock import patch
        cleanup = replay.kill_process_group
        def uncertain(process, wait_s=2):
            return "cleanup-group-observable" if process.args[0] == sys.executable else cleanup(process, wait_s)
        with patch.object(replay, "kill_process_group", uncertain):
            record = self.execute()
        self.assertFalse(record["valid"])
        self.assertFalse(record["accepted"])
        self.assertFalse(record["d0_complete"])
        self.assertEqual(record["acceptance"], [])
        self.assertEqual(record["candidate_retention"], "cleanup-unconfirmed")
        self.assertFalse((self.output / "cases/project" / record["task_id"] / "result.json").exists())

    def budget(self, prior=0):
        from replay_budget import ReplayBudget
        return ReplayBudget.create(self.root / "budget.sqlite", protocol_sha256="a" * 64,
            cost_basis="api-equivalent", prior_costs={"executor_cells": prior, "independent_review": 0, "contingency": 0},
            prior_costs_source_sha256="b" * 64)

    def budgeted(self, budget, replicate=1, upper=3):
        return replay.execute_reserved_cell(self.config, self.task, "NEW", replicate, self.output, 10,
            vault_root=self.vault, budget=budget, upper_usd=upper, bound_source_sha256="c" * 64)

    def test_budget_denial_precedes_any_executor_launch(self):
        marker = self.root / "launched"
        self.config["agent_command"] = [sys.executable, "-c", "from pathlib import Path; Path(" + repr(str(marker)) + ").touch()"]
        with self.assertRaises(ValueError):
            self.budgeted(self.budget(prior=10))
        self.assertFalse(marker.exists())

    def test_unknown_cell_cost_preserves_the_candidate_and_blocks_next_call(self):
        budget = self.budget()
        record = self.budgeted(budget)
        self.assertTrue(record["accepted"])
        self.assertEqual(record["candidate_retention"], "declared-outputs-retained")
        self.assertEqual(budget.snapshot()["unpriced_calls"], 1)
        with self.assertRaises(ValueError):
            self.budgeted(budget, replicate=2)
        self.assertFalse((self.output / "case-r02-NEW.json").exists())

    def priced_executor(self, cost, exit_code=0):
        receipt = {"schema": "007-framework/runner-receipt/v1", "valid": True,
            "requested": {"provider": "fixture", "model": "fixture", "effort": "medium"},
            "served": {"provider": "fixture", "model": "fixture", "effort": "medium"},
            "identity_source": "synthetic-only", "source_sha256": "f" * 64,
            "cost_usd": cost, "cost_source": "rate-card-estimate"}
        self.config["require_served_identity"] = True
        self.config["agent_command"] = [sys.executable, "-c",
            "import sys; from pathlib import Path; Path('tracked.py').write_bytes(b'value = 3\\n'); Path(sys.argv[1]).write_text(" + repr(json.dumps(receipt)) + "); raise SystemExit(" + str(exit_code) + ")", "{runner_receipt}"]

    def test_cost_of_failed_and_accepted_cells_is_reconciled_from_saved_records(self):
        budget = self.budget()
        self.priced_executor(8, exit_code=2)
        first = self.budgeted(budget, upper=8)
        self.assertFalse(first["accepted"])
        self.priced_executor(2)
        second = self.budgeted(budget, replicate=2, upper=2)
        self.assertTrue(second["accepted"])
        self.assertEqual(budget.snapshot()["spent_usd"], 10)
        self.assertTrue(budget.snapshot()["checkpoint_due"])
        self.assertEqual(budget.snapshot()["open_calls"], 0)

    def test_observed_cost_overrun_is_preserved_and_stops_the_controller(self):
        budget = self.budget()
        self.priced_executor(2)
        with self.assertRaises(ValueError):
            self.budgeted(budget, upper=1)
        self.assertTrue((self.output / "case-r01-NEW.json").exists())
        self.assertEqual(budget.snapshot()["spent_usd"], 2)
        self.assertEqual(budget.snapshot()["violations"], ["reservation-overrun:case-r01-NEW"])

    def test_changed_cell_bytes_cannot_reconcile_a_different_in_memory_cost(self):
        from unittest.mock import patch
        budget = self.budget()
        self.priced_executor(2)
        execute = replay.execute_cell
        def altered(*args, **kwargs):
            record = execute(*args, **kwargs)
            path = self.output / "case-r01-NEW.json"
            tampered = {**record, "cost_usd": 3}
            path.write_bytes(capture._json_bytes(tampered))
            return record
        with patch.object(replay, "execute_cell", altered), self.assertRaises(ValueError):
            self.budgeted(budget)
        self.assertEqual(budget.snapshot()["open_calls"], 1)
        self.assertEqual(budget.snapshot()["spent_usd"], 0)


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.fixture = capture_fixtures.ReplayCaptureTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.repo, self.root, self.vault = self.fixture.repo, self.fixture.root, self.fixture.vault
        (self.repo / "acceptance.json").write_text(json.dumps({
            "schema": "007-framework/acceptance/v1", "timeout_s": 5,
            "commands": [[sys.executable, "-c", "from pathlib import Path; assert Path('tracked.py').read_bytes() == b'value = 3\\n'"]]}))
        self.ref = self.fixture.capture()
        (self.repo / "tracked.py").write_bytes(b"value = 3\n")
        terminal = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        terminal.update(task_id="task", project_id="project", replay_ref=self.ref)
        source = self.repo / "terminal.json"
        source.write_text(json.dumps(terminal))
        self.result = capture.finalize_case(self.repo, "project", {"task_id": "task", "replay_ref": self.ref}, source, vault_root=self.vault)
        self.task = {"id": "case", "source_task_id": "task", "project_id": "project",
                     "family": "value-fix", "split": "calibration", "class": "implement", "replay_ref": self.ref}

    def admit(self, tasks, **extra):
        self.assertTrue(hasattr(replay, "admit_dataset"), "dataset admission is not implemented")
        return replay.admit_dataset(tasks, vault_root=self.vault, **extra)

    def test_candidate_reconstruction_does_not_depend_on_original_checkout(self):
        self.assertTrue(hasattr(capture, "restore_candidate"), "candidate reconstruction is not implemented")
        before = self.result.read_bytes()
        self.repo.rename(self.root / "original-unavailable")
        for name in ("restored-one", "restored-two"):
            destination = self.root / name
            capture.restore_candidate(self.vault, "project", "task", self.ref, destination)
            self.assertEqual((destination / "tracked.py").read_bytes(), b"value = 3\n")
            self.assertEqual((destination / "tracked.py").stat().st_mode & 0o777, 0o750)
            self.assertEqual((destination / "ignored.bin").read_bytes(), b"\x00binary\xff")
        self.assertEqual(self.result.read_bytes(), before)

    def test_candidate_restore_rejects_corruption_and_occupied_destination(self):
        self.assertTrue(hasattr(capture, "restore_candidate"), "candidate reconstruction is not implemented")
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "keep").write_bytes(b"keep")
        with self.assertRaises(ValueError):
            capture.restore_candidate(self.vault, "project", "task", self.ref, occupied)
        self.assertEqual((occupied / "keep").read_bytes(), b"keep")
        (self.result.parent / "outputs/files/tracked.py").write_bytes(b"corrupt")
        destination = self.root / "not-created"
        with self.assertRaises(ValueError):
            capture.restore_candidate(self.vault, "project", "task", self.ref, destination)
        self.assertFalse(destination.exists())

    def test_read_only_admission_does_not_trust_replay_flags(self):
        forged = {**self.task, "replay_ready": True, "causal_eligible": True,
                  "economic_eligible": True, "verification": {"passed": True}}
        before = self.result.read_bytes()
        row = self.admit([forged])["cases"][0]
        self.assertEqual(row["state"], "observational")
        self.assertTrue(row["retained_case"])
        self.assertFalse(row["replay_ready"])
        self.assertFalse(row["causal_eligible"])
        self.assertFalse(row["economic_eligible"])
        self.assertEqual(self.result.read_bytes(), before)

    def test_explicit_recheck_runs_restored_oracle_not_a_declared_stamp(self):
        self.repo.rename(self.root / "original-unavailable")
        result = self.admit([self.task], recheck=True)
        row = result["cases"][0]
        self.assertEqual(row["state"], "replay-ready")
        self.assertEqual(row["oracle_exits"], [[0], [0]])
        self.assertTrue(row["replay_ready"])
        self.assertFalse(row["causal_eligible"])
        self.assertFalse(row["economic_eligible"])
        self.assertEqual(result["counts"]["replay-ready"], 1)
        self.assertEqual(result["counts"]["qualified-comparison"], 0)

    def test_cross_split_identity_or_family_is_not_holdout(self):
        tasks = [self.task, {**self.task, "id": "another", "split": "holdout"}]
        for order in itertools.permutations(tasks):
            result = self.admit(list(order))
            self.assertEqual(result["counts"]["holdout_admitted"], 0)
            self.assertTrue(all("cross-split-contamination" in row["exclusions"] for row in result["cases"]))
            self.assertFalse(any(row["admitted"] for row in result["cases"]))

    def test_historical_solution_never_becomes_holdout(self):
        row = self.admit([{**self.task, "split": "holdout", "accepted": "a" * 40}])["cases"][0]
        self.assertFalse(row["admitted"])
        self.assertIn("historical-solution-known", row["exclusions"])

    def test_admission_order_and_projection_are_repeatable_and_sanitized(self):
        tasks = [self.task, {**self.task, "id": "unretained", "source_task_id": "new", "replay_ref": None,
                             "family": "other", "split": "discovery", "prompt": "PRIVATE FIXTURE MARKER"}]
        before = json.dumps(tasks, sort_keys=True)
        first = self.admit(tasks)
        self.assertEqual(first, self.admit(list(reversed(tasks))))
        self.assertEqual(json.dumps(tasks, sort_keys=True), before)
        serialized = json.dumps(first)
        for private in ("PRIVATE FIXTURE MARKER", str(self.repo), "untracked.txt", "value-fix"):
            self.assertNotIn(private, serialized)

    def test_read_only_admit_cli_emits_no_business_execution(self):
        manifest = self.root / "set.json"
        manifest.write_text(json.dumps({"tasks": [self.task]}))
        process = subprocess.run([sys.executable, str(ROOT / "scripts/replay_eval.py"), "--set", str(manifest),
                                  "--vault", str(self.vault), "admit"], capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["counts"]["replay-ready"], 0)

    def additional_case(self, command, name="guarded"):
        (self.repo / "acceptance.json").write_text(json.dumps({
            "schema": "007-framework/acceptance/v1", "timeout_s": 5, "commands": [command]}))
        ref = capture.capture_input(self.repo, "project", name, self.fixture.config, vault_root=self.vault)
        terminal = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        terminal.update(task_id=name, project_id="project", replay_ref=ref)
        source = self.repo / (name + ".json")
        source.write_text(json.dumps(terminal))
        capture.finalize_case(self.repo, "project", {"task_id": name, "replay_ref": ref}, source, vault_root=self.vault)
        return {**self.task, "id": name, "source_task_id": name, "replay_ref": ref}

    def test_contamination_is_checked_before_any_oracle_executes(self):
        marker = self.root / "oracle-executed"
        command = [sys.executable, "-c", "from pathlib import Path; Path(" + repr(str(marker)) + ").touch()"]
        task = self.additional_case(command)
        tasks = [task, {**task, "id": "heldout", "split": "holdout"}]
        result = self.admit(tasks, recheck=True)
        self.assertFalse(marker.exists())
        self.assertFalse(any(r["replay_ready"] for r in result["cases"]))

    def test_arbitrary_class_payload_does_not_enter_projection(self):
        row = self.admit([{**self.task, "class": "PRIVATE CLASS PAYLOAD"}])["cases"][0]
        self.assertEqual(row["class"], "unclassified")
        self.assertNotIn("PRIVATE CLASS PAYLOAD", json.dumps(row))
        self.assertFalse(row["admitted"])

    def test_nonzero_oracle_is_not_attributed_to_an_agent_failure(self):
        task = self.additional_case([sys.executable, "-c", "raise SystemExit(2)"], "nonzero")
        row = self.admit([task], recheck=True)["cases"][0]
        self.assertFalse(row["replay_ready"])
        self.assertEqual(row["oracle_exits"], [[2], [2]])
        self.assertIn("oracle-nonzero-unattributed", row["gaps"])

    def test_candidate_copy_corruption_is_detected_before_ready(self):
        from unittest.mock import patch
        writer = capture.write_bytes_no_replace
        def corrupt(path, payload, label):
            return writer(path, b"corrupted" if label == "restored candidate" else payload, label)
        with patch.object(capture, "write_bytes_no_replace", corrupt):
            with self.assertRaises(ValueError):
                capture.restore_candidate(self.vault, "project", "task", self.ref, self.root / "corrupted-copy")

    def test_recheck_batch_is_bounded_before_execution(self):
        with self.assertRaises(ValueError):
            self.admit([{**self.task, "id": "case" + str(i)} for i in range(4)], recheck=True)

    def test_duplicate_trial_ids_have_order_independent_exclusion(self):
        tasks = [self.task, {**self.task, "source_task_id": "absent", "replay_ref": None, "family": "different"}]
        self.assertEqual(self.admit(tasks), self.admit(list(reversed(tasks))))
        self.assertEqual(self.admit(tasks)["counts"]["excluded"], 2)

    def test_counts_are_partitioned_by_project_class_and_split(self):
        result = self.admit([self.task])
        self.assertTrue({"by_project", "by_class", "by_split"} <= result.keys())
        self.assertEqual(result["by_project"]["project"]["retained"], 1)
        self.assertEqual(result["by_class"]["implement"]["observational"], 1)
        self.assertEqual(result["by_split"]["calibration"]["admitted"], 1)
        self.assertEqual(result["by_split"]["holdout"]["admitted"], 0)

    def test_vault_flag_is_not_silently_ignored_by_legacy_run(self):
        manifest = self.root / "set.json"
        manifest.write_text(json.dumps({"tasks": []}))
        process = subprocess.run([sys.executable, str(ROOT / "scripts/replay_eval.py"), "--set", str(manifest),
                                  "--vault", str(self.vault), "run"], capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 2)
        self.assertIn("--vault", process.stderr)

    def test_recheck_does_not_ignore_a_requested_run_timeout(self):
        manifest = self.root / "set.json"
        manifest.write_text(json.dumps({"tasks": [self.task]}))
        process = subprocess.run([sys.executable, str(ROOT / "scripts/replay_eval.py"), "--set", str(manifest),
                                  "--vault", str(self.vault), "--timeout-min", "1", "admit", "--recheck"],
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 2)
        self.assertIn("run options", process.stderr)

    def test_prefrozen_candidate_identity_is_checked_before_recheck(self):
        task = {**self.task, "result_sha256": "f" * 64}
        row = self.admit([task], recheck=True)["cases"][0]
        self.assertFalse(row["replay_ready"])
        self.assertFalse(row["admitted"])
        self.assertIn("candidate-identity-mismatch", row["exclusions"])
        digest = hashlib.sha256(self.result.read_bytes()).hexdigest()
        row = self.admit([{**self.task, "result_sha256": digest}], recheck=True)["cases"][0]
        self.assertTrue(row["replay_ready"])
        self.assertEqual(row["result_sha256"], digest)

    def test_family_contamination_does_not_require_same_task_or_bytes(self):
        other = self.additional_case([sys.executable, "-c", "pass"], "different-source")
        other.update(split="holdout")
        result = self.admit([self.task, other])
        self.assertTrue(all("cross-split-contamination" in row["exclusions"] for row in result["cases"]))

    def test_exact_inputs_detect_cross_project_contamination_without_shared_family(self):
        copied = self.root / "copied-input"
        capture.restore_input(self.vault, "project", "task", self.ref, copied)
        subprocess.run(["git", "init", "-q"], cwd=copied, check=True)
        subprocess.run(["git", "add", "."], cwd=copied, check=True)
        subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                        "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "copied input"], cwd=copied, check=True)
        ref = capture.capture_input(copied, "other-project", "other", self.fixture.config, vault_root=self.vault)
        terminal = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        terminal.update(task_id="other", project_id="other-project", replay_ref=ref)
        source = copied / "terminal.json"
        source.write_text(json.dumps(terminal))
        capture.finalize_case(copied, "other-project", {"task_id": "other", "replay_ref": ref}, source, vault_root=self.vault)
        other = {**self.task, "id": "other", "source_task_id": "other", "project_id": "other-project",
                 "family": "unrelated", "split": "holdout", "replay_ref": ref}
        result = self.admit([self.task, other])
        self.assertTrue(all("cross-split-contamination" in row["exclusions"] for row in result["cases"]))


if __name__ == "__main__":
    unittest.main()
