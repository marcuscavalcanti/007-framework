"""v2 readers cannot turn byte retention into execution or economic proof."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_replay_capture_v2 as fixtures

capture = importlib.import_module("replay_capture")
cli = importlib.import_module("framework_cli")
replay = importlib.import_module("replay_eval")


class NativeReplayReadersTests(unittest.TestCase):
    def test_closed_binding_does_not_unlock_v2(self):
        from test_native_binding import BindingFixture
        binding = BindingFixture(methodName="runTest")
        binding.setUp()
        self.addCleanup(binding.doCleanups)
        binding.arm()
        binding.consume(binding.consumption())
        (binding.journal / "neighbor").mkdir(mode=0o700)
        (binding.journal / "neighbor/binding").mkdir(mode=0o700)
        binding.close(binding.closure())
        cli.init_project(binding.repo, binding.root / "registry.json")
        marker = json.loads((binding.repo / ".007/project.json").read_bytes())
        marker["project_id"] = "project"
        (binding.repo / ".007/project.json").write_text(json.dumps(marker))
        start = cli.begin_task(binding.repo, "task")
        start["replay_ref"] = binding.ref
        (binding.repo / ".007/tasks/task.task.json").write_text(json.dumps(start))
        terminal = json.loads((fixtures.fixtures.ROOT / "examples/task.receipt.example.json").read_text())
        terminal.update(task_id="task", project_id="project", replay_ref=binding.ref)
        source = binding.repo / "terminal.json"
        source.write_text(json.dumps(terminal))
        capture.finalize_case(binding.repo, "project", start, source, vault_root=binding.vault)
        metadata = json.loads((binding.vault / binding.ref["manifest"]).read_bytes())
        capture_config = binding.root / "native-config.json"
        capture_config.write_text(json.dumps(metadata["config"]))
        task = {"id": "attempt-a", "source_task_id": "task", "project_id": "project",
                "family": "value-fix", "split": "calibration", "class": "implement", "replay_ref": binding.ref}
        output = binding.root / "no-execution"
        output.mkdir()
        class Budget:
            def reserve(self, *args, **kwargs):
                raise AssertionError("closed binding consumed budget")
        config = {"arms": {"NEW": {"provider": "fixture", "model": "fixture", "effort": "medium"}},
                  "agent_command": [sys.executable, "-c", "raise AssertionError('executor ran')"]}
        with (patch.object(cli, "write_json_no_replace", side_effect=AssertionError("operational publication")),
              patch.object(replay, "run", side_effect=AssertionError("oracle/agent ran")),
              patch.object(capture, "restore_input", side_effect=AssertionError("input restored")),
              patch.object(capture, "restore_candidate", side_effect=AssertionError("candidate restored")),
              patch.object(replay.tempfile, "mkdtemp", side_effect=AssertionError("workspace created")),
              patch.object(replay.tempfile, "TemporaryDirectory", side_effect=AssertionError("workspace created"))):
            with self.assertRaisesRegex(ValueError, "v2-execution-unqualified"):
                cli.begin_task(binding.repo, "next", capture_config_file=capture_config, vault_root=binding.vault)
            with self.assertRaisesRegex(ValueError, "v2-execution-unqualified"):
                cli.run_task(binding.repo, "next", binding.repo / "no-receipt.json", config["agent_command"],
                             capture_config_file=capture_config, vault_root=binding.vault)
            with self.assertRaisesRegex(ValueError, "v2-execution-unqualified"):
                cli.record_receipt(binding.repo, source, vault_root=binding.vault)
            with self.assertRaisesRegex(ValueError, "v2-execution-unqualified"):
                replay.execute_cell(config, task, "NEW", 1, output, 10, vault_root=binding.vault)
            with self.assertRaisesRegex(ValueError, "v2-execution-unqualified"):
                replay.execute_reserved_cell(config, task, "NEW", 1, output, 10, vault_root=binding.vault,
                                             budget=Budget(), upper_usd=1, bound_source_sha256="a" * 64)
            self.assertEqual(replay.recheck_retained_case(task, binding.vault),
                             {"replay_ready": False, "oracle_exits": [], "gaps": ["v2-execution-unqualified"]})
            row = replay.admit_dataset([task], vault_root=binding.vault, recheck=True)["cases"][0]
            self.assertEqual(row["state"], "observational")
            self.assertFalse(row["replay_ready"] or row["economic_eligible"] or row["causal_eligible"])
            rows = replay.admit_dataset([task, {**task, "id": "another-attempt"}], vault_root=binding.vault)["cases"]
            self.assertTrue(all("duplicate-case-identity" in row["exclusions"] for row in rows))
        self.assertEqual(list(output.iterdir()), [])
        self.assertFalse((binding.repo / ".007/tasks/next.task.json").exists())
        self.assertFalse(any((binding.repo / ".007/receipts").iterdir()))
        self.assertFalse(any((binding.repo / ".007/events").glob("*")))

    def setUp(self):
        self.fixture = fixtures.ReplayCaptureV2Tests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.repo, self.vault = self.fixture.root, self.fixture.repo, self.fixture.vault

    def retain(self, attempt="attempt-a", kind="native-host"):
        ref = self.fixture.retain(attempt, kind)
        terminal = json.loads((fixtures.fixtures.ROOT / "examples/task.receipt.example.json").read_text())
        terminal.update(task_id="task", project_id="project", replay_ref=ref)
        source = self.repo / "terminal.json"
        source.write_text(json.dumps(terminal))
        result = capture.finalize_case(self.repo, "project", {"task_id": "task", "replay_ref": ref},
                                       source, vault_root=self.vault)
        task = {"id": attempt, "source_task_id": "task", "project_id": "project",
                "family": "value-fix", "split": "calibration", "class": "implement", "replay_ref": ref}
        return task, result

    def test_v2_lifecycle_refuses_before_publication(self):
        marker = cli.init_project(self.repo, self.root / "registry.json")
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(self.fixture.config_v2()))
        for task_id, operation in (("start", cli.begin_task), ("run", cli.run_task)):
            with self.subTest(operation=task_id), self.assertRaisesRegex(ValueError, "v2-execution-unqualified"):
                if task_id == "start":
                    operation(self.repo, task_id, capture_config_file=config_path, vault_root=self.vault)
                else:
                    operation(self.repo, task_id, self.repo / "receipt.json",
                              [sys.executable, "-c", "open('executed.marker','w').write('bad')"],
                              capture_config_file=config_path, vault_root=self.vault)
            self.assertFalse((self.repo / f".007/tasks/{task_id}.task.json").exists())
        self.assertFalse((self.repo / "executed.marker").exists())
        self.assertFalse(self.vault.exists())
        self.assertFalse(any((self.repo / ".007/events").glob("*")))
        self.assertFalse(any((self.repo / ".007/receipts").glob("*")))
        start = cli.begin_task(self.repo, "task")
        ref = capture.capture_input(self.repo, marker["project_id"], "task", self.fixture.config_v2(),
                                    vault_root=self.vault, attempt_id="attempt-a")
        start["replay_ref"] = ref
        (self.repo / ".007/tasks/task.task.json").write_text(json.dumps(start))
        terminal = json.loads((fixtures.fixtures.ROOT / "examples/task.receipt.example.json").read_text())
        terminal.update(task_id="task", project_id=marker["project_id"], replay_ref=ref)
        source = self.repo / "terminal.json"
        source.write_text(json.dumps(terminal))
        with self.assertRaisesRegex(ValueError, "v2-execution-unqualified"):
            cli.record_receipt(self.repo, source, vault_root=self.vault)
        self.assertFalse((self.repo / ".007/receipts/task.receipt.json").exists())
        self.assertFalse((self.vault / ref["manifest"]).with_name("result.json").exists())

    def test_v2_execution_and_recheck_have_no_effects(self):
        class Budget:
            def reserve(self, *args, **kwargs):
                raise AssertionError("v2 consumed budget")
        for kind in ("command", "native-host"):
            task, _ = self.retain("attempt-" + kind, kind)
            output = self.root / ("cells-" + kind)
            output.mkdir()
            config = {"arms": {"NEW": {"provider": "fixture", "model": "fixture", "effort": "medium"}},
                      "agent_command": [sys.executable, "-c", "raise AssertionError('executor ran')"]}
            with (self.subTest(kind=kind),
                  patch.object(replay, "run", side_effect=AssertionError("oracle/agent ran")),
                  patch.object(capture, "restore_input", side_effect=AssertionError("input restored")),
                  patch.object(capture, "restore_candidate", side_effect=AssertionError("candidate restored")),
                  patch.object(replay.tempfile, "mkdtemp", side_effect=AssertionError("workspace created")),
                  patch.object(replay.tempfile, "TemporaryDirectory", side_effect=AssertionError("workspace created"))):
                with self.assertRaisesRegex(ValueError, "v2-execution-unqualified"):
                    replay.execute_cell(config, task, "NEW", 1, output, 10, vault_root=self.vault)
                with self.assertRaisesRegex(ValueError, "v2-execution-unqualified"):
                    replay.execute_reserved_cell(config, task, "NEW", 1, output, 10, vault_root=self.vault,
                                                 budget=Budget(), upper_usd=1, bound_source_sha256="a" * 64)
                checked = replay.recheck_retained_case(task, self.vault)
                self.assertEqual(checked, {"replay_ready": False, "oracle_exits": [],
                                           "gaps": ["v2-execution-unqualified"]})
            self.assertEqual(list(output.iterdir()), [])

    def test_v2_admission_stays_observational(self):
        task, _ = self.retain()
        for recheck in (False, True):
            with self.subTest(recheck=recheck):
                row = replay.admit_dataset([task], vault_root=self.vault, recheck=recheck)["cases"][0]
                self.assertEqual(row["state"], "observational")
                self.assertTrue(row["retained_case"])
                self.assertFalse(row["replay_ready"])
                self.assertFalse(row["causal_eligible"])
                self.assertFalse(row["economic_eligible"])
                self.assertEqual(row["oracle_exits"], [])

    def test_attempts_do_not_become_independent_cases(self):
        first, _ = self.retain()
        second, _ = self.retain("attempt-b")
        for split in ("calibration", "holdout"):
            tasks = [first, {**second, "split": split}]
            rows = replay.admit_dataset(tasks, vault_root=self.vault)["cases"]
            for row in rows:
                self.assertIn("duplicate-case-identity", row["exclusions"])
                self.assertFalse(row["admitted"])
                if split == "holdout":
                    self.assertIn("cross-split-contamination", row["exclusions"])

    def link(self, task, result, kind, **changes):
        value = {"project_id": "project", "task_id": "task", "input_sha256": task["replay_ref"]["sha256"],
                 "result_sha256": hashlib.sha256(result.read_bytes()).hexdigest()}
        if kind == "followup":
            value.update(observed_at="2026-10-12T12:00:00Z", corrective_lines=9, repair_rounds=1,
                         escape_7d="yes", description="PRIVATE-SENTINEL")
        else:
            value.update(kind="gate", status="proposed", mechanism="PRIVATE-SENTINEL", evidence="fixture",
                         counterproof="mutant fails", positive_control="control passes", experiment="not executed")
        value.update(changes)
        payload = capture._json_bytes(value)
        digest = hashlib.sha256(payload).hexdigest()
        name = f"{kind}-{digest}.json"
        capture.write_bytes_no_replace(result.parent / name, payload, "fixture link")
        return {"manifest": str(Path(task["replay_ref"]["manifest"]).parent / name), "sha256": digest}

    def test_v2_curation_binds_case_directory_and_exact_hashes(self):
        task, result = self.retain()
        followup = self.link(task, result, "followup")
        hypothesis = self.link(task, result, "hypothesis")
        linked = {**task, "followup_refs": [followup], "hypothesis_refs": [hypothesis]}
        checkpoint = self.root / "curation/checkpoint.json"
        first = replay.curate_dataset([linked], vault_root=self.vault, checkpoint=checkpoint)
        row = first["admission"]["cases"][0]
        self.assertEqual(row["declared_followups"][0]["corrective_lines"], 9)
        self.assertEqual(row["declared_hypotheses"][0]["kind"], "gate")
        self.assertFalse(row["replay_ready"])
        previous = checkpoint.read_bytes()
        self.assertNotIn(b"PRIVATE-SENTINEL", previous)
        self.assertFalse(replay.curate_dataset([linked], vault_root=self.vault, checkpoint=checkpoint)["changed"])
        self.assertEqual(checkpoint.read_bytes(), previous)
        bad_links = [{**followup, "manifest": "project/task/" + Path(followup["manifest"]).name},
                     self.link(task, result, "followup", input_sha256="a" * 64),
                     self.link(task, result, "followup", result_sha256="b" * 64)]
        other, other_result = self.retain("attempt-b")
        bad_links.append(self.link(other, other_result, "followup"))
        for link in bad_links:
            with self.subTest(link=link), self.assertRaises(ValueError):
                replay.curate_dataset([{**task, "followup_refs": [link]}], vault_root=self.vault, checkpoint=checkpoint)
            self.assertEqual(checkpoint.read_bytes(), previous)
        for tasks in ([linked, {**other, "followup_refs": [self.link(other, other_result, "followup", repair_rounds=2)]}],
                      [{**task, "followup_refs": [followup, followup]}]):
            with self.subTest(tasks=tasks), self.assertRaises(ValueError):
                replay.curate_dataset(tasks, vault_root=self.vault, checkpoint=checkpoint)
            self.assertEqual(checkpoint.read_bytes(), previous)

    def test_unretained_curation_link_refuses_cleanly_and_releases_lock(self):
        task = {"id": "discovered", "source_task_id": "task", "project_id": "project",
                "family": "value-fix", "split": "discovery", "class": "implement"}
        link = {"manifest": "project/task/followup-" + "a" * 64 + ".json", "sha256": "a" * 64}
        checkpoint = self.root / "curation/checkpoint.json"
        for kind in ("followup", "hypothesis"):
            for reference in ("missing", None, {}):
                candidate = {**task, kind + "_refs": [link]}
                if reference != "missing":
                    candidate["replay_ref"] = reference
                with self.subTest(kind=kind, reference=reference):
                    try:
                        with self.assertRaises(ValueError):
                            replay.curate_dataset([candidate], vault_root=self.vault, checkpoint=checkpoint)
                    except KeyError:
                        self.fail("Unretained link escaped as KeyError instead of a validation refusal")
                    self.assertFalse(checkpoint.exists())
                    self.assertFalse(checkpoint.with_name("checkpoint.json.lock").exists())
        result = replay.curate_dataset([task], vault_root=self.vault, checkpoint=checkpoint)
        self.assertTrue(result["complete"])
        self.assertFalse(result["admission"]["cases"][0]["retained_case"])


if __name__ == "__main__":
    unittest.main()
