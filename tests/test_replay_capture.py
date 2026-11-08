"""Retained-input recovery and counterproofs, with no provider calls."""

import importlib
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ReplayCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        (self.repo / "tracked.py").write_bytes(b"value = 1\n")
        (self.repo / ".gitignore").write_text("ignored.bin\n")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "base"], cwd=self.repo, check=True)
        (self.repo / "tracked.py").write_bytes(b"value = 2\n")
        (self.repo / "untracked.txt").write_bytes(b"required untracked input\n")
        (self.repo / "ignored.bin").write_bytes(b"\x00binary\xff")
        (self.repo / "tracked.py").chmod(0o750)
        (self.repo / "task.txt").write_text("Preserve this fixture's value.")
        (self.repo / "context.txt").write_text("Fixture-only context.")
        (self.repo / "acceptance.json").write_text(json.dumps({
            "schema": "007-framework/acceptance/v1",
            "commands": [[sys.executable, "-c", "pass"]]}))
        (self.repo / "environment.json").write_text(json.dumps({"offline": True}))
        self.config = {
            "schema": "007-framework/capture-config/v1",
            "files": ["tracked.py", "untracked.txt", "ignored.bin", "task.txt",
                      "context.txt", "acceptance.json", "environment.json"],
            "prompt_file": "task.txt", "context_files": ["context.txt"],
            "acceptance_file": "acceptance.json", "environment_file": "environment.json",
            "output_files": ["tracked.py"], "command": ["fixture-executor"],
            "requested": {"provider": "fixture", "model": "fixture", "effort": "medium"},
            "executor_timeout_s": 30, "exclusions": [".git", ".007"], "external_inputs": []}
        self.vault = self.root / "vault"

    def module(self):
        try:
            return importlib.import_module("replay_capture")
        except ModuleNotFoundError:
            self.fail("retained-input capture is not integrated")

    def capture(self):
        return self.module().capture_input(self.repo, "project", "task", self.config,
                                           vault_root=self.vault)

    def test_restore_roundtrip_preserves_declared_bytes(self):
        capture = self.module()
        ref = self.capture()
        for name in ("restore-a", "restore-b"):
            target = self.root / name
            capture.restore_input(self.vault, "project", "task", ref, target)
            self.assertEqual((target / "tracked.py").read_bytes(), b"value = 2\n")
            self.assertEqual((target / "untracked.txt").read_bytes(), b"required untracked input\n")
            self.assertEqual((target / "ignored.bin").read_bytes(), b"\x00binary\xff")
            self.assertEqual((target / "tracked.py").stat().st_mode & 0o777, 0o750)
        self.assertEqual((self.vault / ref["manifest"]).stat().st_mode & 0o777, 0o600)

    def qualify(self, ref):
        self.assertTrue(hasattr(self.module(), "qualify_case"), "case qualification is not implemented")
        return self.module().qualify_case(self.vault, "project", "task", ref)

    def test_qualification_does_not_promote_an_unbacked_hash(self):
        missing = self.qualify({"manifest": "project/task/input.json", "sha256": "a" * 64})
        self.assertEqual(missing["state"], "unavailable")
        self.assertIsNone(missing["inputs_recoverable"])
        self.assertFalse(missing["causal_eligible"])
        self.assertFalse(missing["economic_eligible"])
        self.assertEqual(self.qualify(None)["state"], "observational")

    def test_qualification_is_deterministic_and_sanitized(self):
        ref = self.capture()
        first = self.qualify(ref)
        self.assertEqual(first, self.qualify(ref))
        self.assertEqual(first["state"], "inputs-retained")
        self.assertTrue(first["inputs_recoverable"])
        self.assertFalse(first["candidate_recoverable"])
        self.assertFalse(first["replay_ready"])
        serialized = json.dumps(first)
        self.assertNotIn(str(self.repo), serialized)
        self.assertNotIn("Preserve this fixture", serialized)
        self.assertNotIn("untracked.txt", serialized)

    def test_terminal_retention_is_not_an_independent_oracle(self):
        ref = self.capture()
        value = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        value.update(task_id="task", replay_ref=ref, project_id="project")
        source = self.repo / "outcome.json"
        source.write_text(json.dumps(value))
        result = self.module().finalize_case(self.repo, "project", {"task_id": "task", "replay_ref": ref}, source, vault_root=self.vault)
        before = result.read_bytes()
        projection = self.qualify(ref)
        self.assertEqual(projection["state"], "case-retained")
        self.assertTrue(projection["candidate_recoverable"])
        self.assertEqual(projection["result_sha256"], hashlib.sha256(before).hexdigest())
        self.assertFalse(projection["replay_ready"])
        self.assertFalse(projection["causal_eligible"])
        self.assertIn("oracle-not-independently-executed", projection["gaps"])
        self.assertEqual(result.read_bytes(), before)
        (result.parent / "outputs/files/tracked.py").write_bytes(b"corrupt")
        corrupted = self.qualify(ref)
        self.assertEqual(corrupted["state"], "invalid")
        self.assertTrue(corrupted["inputs_recoverable"])
        self.assertFalse(corrupted["candidate_recoverable"])

    def test_missing_candidate_is_unavailable_not_invalid_business_result(self):
        ref = self.capture()
        value = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        value.update(task_id="task", replay_ref=ref, project_id="project")
        source = self.repo / "outcome.json"
        source.write_text(json.dumps(value))
        result = self.module().finalize_case(self.repo, "project", {"task_id": "task", "replay_ref": ref}, source, vault_root=self.vault)
        (result.parent / "outputs/files/tracked.py").unlink()
        projection = self.qualify(ref)
        self.assertEqual(projection["state"], "unavailable")
        self.assertIsNone(projection["candidate_recoverable"])
        self.assertFalse(projection["replay_ready"])

    def test_denied_result_metadata_is_inconclusive(self):
        ref = self.capture()
        original = Path.lstat
        def denied(path, *args, **kwargs):
            if path.name == "result.json":
                raise PermissionError("fixture deny")
            return original(path, *args, **kwargs)
        with patch.object(Path, "lstat", denied):
            projection = self.qualify(ref)
        self.assertEqual(projection["state"], "unavailable")
        self.assertIsNone(projection["candidate_recoverable"])
        self.assertTrue(projection["inputs_recoverable"])

    def test_input_fingerprint_is_independent_of_role_listing_order(self):
        first = self.qualify(self.capture())
        config = {**self.config, "files": list(reversed(self.config["files"]))}
        ref = self.module().capture_input(self.repo, "project", "second", config, vault_root=self.vault)
        second = self.module().qualify_case(self.vault, "project", "second", ref)
        self.assertNotEqual(first["input_sha256"], second["input_sha256"])
        self.assertEqual(first["inputs_fingerprint_sha256"], second["inputs_fingerprint_sha256"])

    def test_legacy_terminal_without_separate_project_field_retains_ref_binding(self):
        ref = self.capture()
        value = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        value.update(task_id="task", replay_ref=ref)
        value.pop("project_id", None)
        source = self.repo / "outcome.json"
        source.write_text(json.dumps(value))
        result = self.module().finalize_case(self.repo, "project", {"task_id": "task", "replay_ref": ref}, source, vault_root=self.vault)
        before = result.read_bytes()
        projection = self.qualify(ref)
        self.assertEqual(projection["state"], "case-retained")
        self.assertFalse(projection["causal_eligible"])
        self.assertEqual(result.read_bytes(), before)

    def test_manifest_without_retained_bytes_is_not_ready(self):
        ref = self.capture()
        (self.vault / "project/task/inputs/ignored.bin").unlink()
        with self.assertRaises((OSError, ValueError)):
            self.module().validate_replay_ref(self.vault, "project", "task", ref)

    def test_changed_artifact_or_wrong_identity_is_rejected(self):
        ref = self.capture()
        with self.assertRaises(ValueError):
            self.module().validate_replay_ref(self.vault, "other-project", "task", ref)
        (self.vault / "project/task/inputs/untracked.txt").write_bytes(b"tampered\n")
        with self.assertRaises(ValueError):
            self.module().validate_replay_ref(self.vault, "project", "task", ref)

    def test_capture_and_restore_do_not_overwrite_existing_case(self):
        ref = self.capture()
        original = (self.vault / ref["manifest"]).read_bytes()
        with self.assertRaises(ValueError):
            self.capture()
        self.assertEqual((self.vault / ref["manifest"]).read_bytes(), original)
        dest = self.root / "occupied"
        dest.mkdir()
        (dest / "keep").write_bytes(b"keep")
        with self.assertRaises(ValueError):
            self.module().restore_input(self.vault, "project", "task", ref, dest)
        self.assertEqual((dest / "keep").read_bytes(), b"keep")

    def test_capture_rejects_concurrent_source_change(self):
        capture = self.module()
        inventory = capture._inventory
        calls = 0
        def observe(root, names):
            nonlocal calls
            calls += 1
            if calls == 2:
                (self.repo / "tracked.py").write_bytes(b"value = 3\n")
            return inventory(root, names)
        with patch.object(capture, "_inventory", side_effect=observe):
            with self.assertRaises(ValueError):
                self.capture()
        self.assertFalse((self.vault / "project/task/input.json").exists())

    def test_capture_rejects_same_size_mutation_when_filesystem_stamps_collide(self):
        capture = self.module()
        with patch.object(capture, '_stamp', side_effect=lambda info: (info.st_dev,info.st_ino,info.st_size,info.st_mode,0,0)):
            self.test_capture_rejects_concurrent_source_change()

    def test_finalize_rejects_same_size_mutation_when_filesystem_stamps_collide(self):
        capture = self.module()
        ref = self.capture()
        receipt = json.loads((ROOT/'examples/task.receipt.example.json').read_text())
        receipt.update(task_id='task',replay_ref=ref)
        source = self.repo/'terminal.json'
        source.write_text(json.dumps(receipt))
        inventory = capture._inventory
        calls = 0
        def observe(root,names):
            nonlocal calls
            if root == self.repo:
                calls += 1
                if calls == 2:
                    (self.repo/'tracked.py').write_bytes(b'value = 3\n')
            return inventory(root,names)
        with (patch.object(capture,'_stamp',side_effect=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mode,0,0)),
              patch.object(capture,'_inventory',side_effect=observe)):
            with self.assertRaises(ValueError):
                capture.finalize_case(self.repo,'project',{'task_id':'task','replay_ref':ref},source,vault_root=self.vault)
        self.assertFalse((self.vault/'project/task/result.json').exists())

    def test_capture_rejects_traversal_symlinks_and_oversize(self):
        capture = self.module()
        for name in ("../outside", "a/../b", ".git/config", ".007/project.json"):
            config = {**self.config, "files": self.config["files"] + [name]}
            with self.subTest(name=name), self.assertRaises(ValueError):
                capture.capture_input(self.repo, "project", "task", config, vault_root=self.vault)
        (self.repo / "untracked.txt").unlink()
        (self.repo / "untracked.txt").symlink_to(self.repo / "tracked.py")
        with self.assertRaises(ValueError):
            self.capture()
        (self.repo / "untracked.txt").unlink()
        with (self.repo / "untracked.txt").open("wb") as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
        with self.assertRaises(ValueError):
            self.capture()
        self.assertFalse(self.vault.exists())

    def test_begin_and_record_bind_retained_input_before_edits(self):
        cli = importlib.import_module("framework_cli")
        cli.init_project(self.repo, self.root / "registry.json")
        config = self.root / "capture.json"
        config.write_text(json.dumps(self.config))
        task = cli.begin_task(self.repo, "captured", capture_config_file=config,
                              vault_root=self.vault)
        (self.repo / "tracked.py").write_bytes(b"value = 9\n")
        value = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        value["task_id"] = "captured"
        source = self.repo / "outcome.json"
        source.write_text(json.dumps(value))
        terminal = cli.record_receipt(self.repo, source, vault_root=self.vault)
        stored = json.loads(terminal.read_text())
        self.assertEqual(stored["replay_ref"], task["replay_ref"])
        marker = json.loads((self.repo / ".007/project.json").read_text())
        self.module().restore_input(self.vault, marker["project_id"], "captured",
                                    task["replay_ref"], self.root / "before")
        self.assertEqual((self.root / "before/tracked.py").read_bytes(), b"value = 2\n")
        result = json.loads((self.vault / task["replay_ref"]["manifest"]).with_name("result.json").read_text())
        self.assertEqual(result["input_sha256"], task["replay_ref"]["sha256"])
        self.assertEqual((self.vault / task["replay_ref"]["manifest"]).parent.joinpath(
            "outputs/files/tracked.py").read_bytes(), b"value = 9\n")

    def test_deleted_output_is_preserved_as_absence(self):
        capture = self.module()
        ref = self.capture()
        (self.repo / "tracked.py").unlink()
        value = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        value.update(task_id="task", replay_ref=ref)
        source = self.repo / "outcome.json"
        source.write_text(json.dumps(value))
        result_path = capture.finalize_case(self.repo, "project",
            {"task_id": "task", "replay_ref": ref}, source, vault_root=self.vault)
        result = json.loads(result_path.read_text())
        self.assertEqual(result["outputs"], [])
        self.assertEqual(result["deleted_files"], ["tracked.py"])

    def test_foreign_terminal_cannot_finalize_another_case(self):
        ref = self.capture()
        value = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        value.update(task_id="other-task", replay_ref=ref)
        source = self.repo / "outcome.json"
        source.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            self.module().finalize_case(self.repo, "project",
                {"task_id": "task", "replay_ref": ref}, source, vault_root=self.vault)
        self.assertFalse((self.vault / "project/task/result.json").exists())

    def test_run_uses_frozen_contract_and_keeps_pre_edit_bytes(self):
        cli = importlib.import_module("framework_cli")
        cli.init_project(self.repo, self.root / "registry.json")
        receipt = self.repo / "outcome.json"
        script = (
            "import json,os; from pathlib import Path; "
            "Path('tracked.py').write_text('value = 9\\n'); "
            "Path('acceptance.json').write_text('{}'); "
            "v=json.loads(Path('template.json').read_text()); "
            "v['task_id']=os.environ['FRAMEWORK_007_TASK_ID']; "
            "Path(os.environ['FRAMEWORK_007_RECEIPT_PATH']).write_text(json.dumps(v))")
        command = [sys.executable, "-c", script]
        (self.repo / "template.json").write_bytes((ROOT / "examples/task.receipt.example.json").read_bytes())
        config = {**self.config, "command": command,
                  "files": self.config["files"] + ["template.json"]}
        source = self.root / "capture.json"
        source.write_text(json.dumps(config))
        contract = (self.repo / "acceptance.json").read_bytes()
        code, destination = cli.run_task(self.repo, "run-captured", receipt, command,
                                        capture_config_file=source, vault_root=self.vault)
        self.assertEqual(code, 0)
        terminal = json.loads(destination.read_text())
        self.assertEqual(terminal["acceptance_sha256"], hashlib.sha256(contract).hexdigest())
        self.assertEqual(terminal["acceptance_summary"], {"passed": 1, "failed": 0})
        marker = json.loads((self.repo / ".007/project.json").read_text())
        self.module().restore_input(self.vault, marker["project_id"], "run-captured",
            terminal["replay_ref"], self.root / "run-before")
        self.assertEqual((self.root / "run-before/tracked.py").read_bytes(), b"value = 2\n")
        self.assertEqual((self.root / "run-before/acceptance.json").read_bytes(), contract)

    def test_run_rejects_command_different_from_retained_input(self):
        cli = importlib.import_module("framework_cli")
        cli.init_project(self.repo, self.root / "registry.json")
        config = self.root / "capture.json"
        config.write_text(json.dumps(self.config))
        with self.assertRaises(ValueError):
            cli.run_task(self.repo, "wrong-command", self.repo / "outcome.json",
                         [sys.executable, "-c", "open('should-not-run','w').write('bad')"],
                         capture_config_file=config, vault_root=self.vault)
        self.assertFalse((self.repo / "should-not-run").exists())
        self.assertFalse((self.repo / ".007/receipts/wrong-command.receipt.json").exists())

    def test_deleted_output_list_is_bounded_before_capture(self):
        config = {**self.config, "output_files": [f"missing-{i}" for i in range(5001)]}
        with self.assertRaises(ValueError):
            self.module().capture_input(self.repo, "project", "task", config,
                                        vault_root=self.vault)
        self.assertFalse(self.vault.exists())

    def test_denied_action_in_a_captured_project_closes_the_case_without_running_anything(self):
        # audit F04 where it always fired: a capture config always binds acceptance, so every denied action lost its receipt
        cli, command, config = self.incomplete_run("deny", "pass")
        authority = self.root / "authority.json"
        authority.write_text(json.dumps({"schema": "007-framework/authority/v1", "allow": ["test"], "deny": ["deploy"]}))
        status, destination = cli.run_task(self.repo, "deny", self.repo / "outcome.json", command, authority_file=authority,
                                           action="deploy", capture_config_file=config, vault_root=self.vault)
        self.assertEqual(status, 3)
        self.assertEqual((self.repo / "tracked.py").read_bytes(), b"value = 2\n")  # the executor never ran
        self.assertEqual(json.loads(destination.read_text())["acceptance_evidence"], "not-executed")
        task = json.loads((self.repo / ".007/tasks/deny.task.json").read_text())
        marker = json.loads((self.repo / ".007/project.json").read_text())
        self.assertEqual(self.module().qualify_case(self.vault, marker["project_id"], "deny", task["replay_ref"])["state"],
                         "case-retained")

    def incomplete_run(self, name, tail):
        cli = importlib.import_module("framework_cli")
        cli.init_project(self.repo, self.root / "registry.json")
        (self.repo / "template.json").write_bytes((ROOT / "examples/task.receipt.example.json").read_bytes())
        script = "from pathlib import Path; import json,os; Path('tracked.py').write_text('value = 9\\n'); " + tail
        command = [sys.executable, "-c", script]
        source = self.root / (name + ".capture.json")
        source.write_text(json.dumps({**self.config, "command": command,
                                     "files": self.config["files"] + ["template.json"]}))
        return cli, command, source

    def retained_observation(self, name):
        task = json.loads((self.repo / ".007/tasks" / (name + ".task.json")).read_text())
        marker = json.loads((self.repo / ".007/project.json").read_text())
        case = (self.vault / task["replay_ref"]["manifest"]).parent
        self.assertTrue((case / "result.json").exists(), "rejected official receipt lost the candidate")
        observation = json.loads((case / "outputs/receipt.json").read_text())
        self.assertEqual(observation["observation_kind"], "execution-incomplete")
        self.assertNotIn("status", observation)
        self.assertEqual(observation["task_id"], name)
        self.assertIsNone(observation["cost_usd"])
        self.assertFalse((self.repo / ".007/receipts" / (name + ".receipt.json")).exists())
        destination = self.root / (name + "-restored")
        self.module().restore_candidate(self.vault, marker["project_id"], name, task["replay_ref"], destination)
        self.assertEqual((destination / "tracked.py").read_bytes(), b"value = 9\n")
        return observation

    def test_missing_usd_does_not_discard_replay_candidate(self):
        name = "unpriced"
        tail = ("v=json.loads(Path('template.json').read_text()); v['task_id']=os.environ['FRAMEWORK_007_TASK_ID']; "
                "v['cost_usd']=None; v['cost_status']='unavailable'; v['cost_source']='custom:flat'; "
                "v['cost_unavailable_reason']='fixture unpriced'; "
                "Path(os.environ['FRAMEWORK_007_RECEIPT_PATH']).write_text(json.dumps(v))")
        cli, command, source = self.incomplete_run(name, tail)
        with self.assertRaises(ValueError):
            cli.run_task(self.repo, name, self.repo / "outcome.json", command,
                         capture_config_file=source, vault_root=self.vault)
        self.assertEqual(self.retained_observation(name)["reason_code"], "receipt-rejected")

    def test_nonzero_executor_candidate_is_preserved_without_terminal(self):
        name = "failed-exec"
        cli, command, source = self.incomplete_run(name, "raise SystemExit(7)")
        code, destination = cli.run_task(self.repo, name, self.repo / "outcome.json", command,
                                         capture_config_file=source, vault_root=self.vault)
        self.assertEqual((code, destination), (7, None))
        self.assertEqual(self.retained_observation(name)["command_exit"], 7)

    def test_absent_receipt_candidate_is_preserved_without_fake_status(self):
        name = "no-receipt"
        cli, command, source = self.incomplete_run(name, "pass")
        with self.assertRaises(ValueError):
            cli.run_task(self.repo, name, self.repo / "outcome.json", command,
                         capture_config_file=source, vault_root=self.vault)
        self.assertEqual(self.retained_observation(name)["reason_code"], "missing-receipt")

    def test_foreign_receipt_does_not_control_preserved_task_identity(self):
        name = "foreign-receipt"
        tail = ("v=json.loads(Path('template.json').read_text()); v['task_id']='foreign'; "
                "Path(os.environ['FRAMEWORK_007_RECEIPT_PATH']).write_text(json.dumps(v))")
        cli, command, source = self.incomplete_run(name, tail)
        with self.assertRaises(ValueError):
            cli.run_task(self.repo, name, self.repo / "outcome.json", command,
                         capture_config_file=source, vault_root=self.vault)
        self.assertEqual(self.retained_observation(name)["task_id"], name)

    def test_unconfirmed_cleanup_never_snapshots_mutable_candidate(self):
        name = "unconfirmed"
        cli, command, source = self.incomplete_run(name, "pass")
        with patch.object(cli, "kill_process_group", return_value="cleanup-group-observable"):
            with self.assertRaises(ValueError):
                cli.run_task(self.repo, name, self.repo / "outcome.json", command,
                             capture_config_file=source, vault_root=self.vault)
        task = json.loads((self.repo / ".007/tasks" / (name + ".task.json")).read_text())
        case = (self.vault / task["replay_ref"]["manifest"]).parent
        self.assertFalse((case / "result.json").exists())
        self.assertFalse((case / "observation.json").exists())

    def test_incomplete_observation_cannot_replace_existing_evidence(self):
        ref = self.capture()
        path = (self.vault / ref["manifest"]).parent / "observation.json"
        path.write_bytes(b"keep-existing")
        with self.assertRaises(ValueError):
            self.module().preserve_incomplete_case(self.repo, "project", {"task_id": "task", "replay_ref": ref},
                "receipt-rejected", 0, vault_root=self.vault, wall_s=1)
        self.assertEqual(path.read_bytes(), b"keep-existing")


if __name__ == "__main__":
    unittest.main()
