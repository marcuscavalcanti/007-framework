"""Offline v2 byte retention; no native execution or provider calls."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_replay_capture as fixtures


class ReplayCaptureV2Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ReplayCaptureTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.capture = self.fixture.module()
        self.repo, self.vault, self.root = self.fixture.repo, self.fixture.vault, self.fixture.root

    def config_v2(self, kind="native-host"):
        config = copy.deepcopy(self.fixture.config)
        argv = config.pop("command")
        config["schema"] = "007-framework/capture-config/v2"
        config["execution"] = ({"kind": "command", "argv": argv} if kind == "command" else
                               {"kind": "native-host", "adapter": "fixture-hooks",
                                "surface": "desktop", "binding_id": "binding-a"})
        if kind == "native-host":
            config.update(requested=None, executor_timeout_s=None)
        return config

    def retain(self, attempt="attempt-a", kind="native-host", config=None):
        return self.capture.capture_input(self.repo, "project", "task", config or self.config_v2(kind),
                                          vault_root=self.vault, attempt_id=attempt)

    def test_v2_roundtrip_keeps_task_and_attempt_distinct(self):
        refs = [self.retain("attempt-" + kind, kind) for kind in ("command", "native-host")]
        self.repo.rename(self.root / "original-unavailable")
        for kind, ref in zip(("command", "native-host"), refs):
            with self.subTest(kind=kind):
                self.assertEqual(ref["manifest"], f"project/attempt-{kind}/input.json")
                restored = self.root / ("restored-" + kind)
                metadata = self.capture.restore_input(self.vault, "project", "task", ref, restored,
                                                       expected_attempt_id="attempt-" + kind)
                self.assertEqual(metadata["task_id"], "task")
                self.assertEqual(metadata["attempt_id"], "attempt-" + kind)
                self.assertEqual((restored / "tracked.py").read_bytes(), b"value = 2\n")
                self.assertEqual((restored / "tracked.py").stat().st_mode & 0o777, 0o750)
                self.assertEqual((restored / "ignored.bin").read_bytes(), b"\x00binary\xff")
                self.assertEqual((restored / "untracked.txt").read_bytes(), b"required untracked input\n")
                self.assertFalse((restored / ".007").exists())

    def test_v2_config_is_exact(self):
        valid = self.config_v2()
        before = copy.deepcopy(valid)
        self.assertEqual(self.capture._config(valid), before)
        self.assertEqual(valid, before)
        alternate = copy.deepcopy(valid)
        alternate["execution"].update(adapter="another-host", surface="terminal")
        alternate["requested"] = {"provider": "fixture", "model": "declared", "effort": "high"}
        self.assertEqual(self.capture._config(alternate), alternate)
        self.assertEqual(self.capture._config(self.config_v2("command"))["execution"]["argv"], ["fixture-executor"])
        cases = []
        for key, value in (("requested", {}), ("executor_timeout_s", 30), ("extra", 1)):
            cases.append({**valid, key: value})
        for key in ("requested", "executor_timeout_s"):
            candidate = copy.deepcopy(valid)
            candidate.pop(key)
            cases.append(candidate)
        for execution in ({**valid["execution"], "argv": ["fake"]}, {"kind": "command"},
                          {"kind": "command", "argv": []}, {"kind": "command", "argv": [1]},
                          {**valid["execution"], "adapter": "../bad"},
                          {**valid["execution"], "surface": "unknown"}):
            cases.append({**valid, "execution": execution})
        for timeout in (0, 3601, True, None):
            cases.append({**self.config_v2("command"), "executor_timeout_s": timeout})
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                self.capture._config(candidate)

    def test_v2_identity_and_collision_refusals(self):
        ref = self.retain()
        original = (self.vault / ref["manifest"]).read_bytes()
        other = self.retain("attempt-b")
        self.assertNotEqual(other, ref)
        for project, task, attempt in (("other", "task", "attempt-a"),
                                       ("project", "other", "attempt-a"),
                                       ("project", "task", "attempt-b")):
            with self.subTest(project=project, task=task, attempt=attempt), self.assertRaises(ValueError):
                self.capture.validate_replay_ref(self.vault, project, task, ref, expected_attempt_id=attempt)
        with self.assertRaises(ValueError):
            self.retain()
        self.assertEqual((self.vault / ref["manifest"]).read_bytes(), original)
        legacy = self.fixture.capture()
        with self.assertRaises(ValueError):
            self.retain("task")
        with self.assertRaises(ValueError):
            self.capture.capture_input(self.repo, "project", "attempt-a", self.fixture.config, vault_root=self.vault)
        with self.assertRaises(ValueError):
            self.capture.capture_input(self.repo, "project", "new", self.fixture.config,
                                       vault_root=self.vault, attempt_id="new-attempt")
        with self.assertRaises(ValueError):
            self.capture.capture_input(self.repo, "project", "new", self.config_v2(), vault_root=self.vault)
        with self.assertRaises(ValueError):
            self.capture.validate_replay_ref(self.vault, "project", "task", legacy, expected_attempt_id="task")
        partial = self.vault / "project" / "partial"
        partial.mkdir(mode=0o700)
        (partial / "sentinel").write_bytes(b"preserve")
        with self.assertRaises(ValueError):
            self.retain("partial")
        self.assertEqual((partial / "sentinel").read_bytes(), b"preserve")

    def test_v2_result_binds_exact_attempt_ref(self):
        ref, other = self.retain(), self.retain("attempt-b")
        task = {"task_id": "task", "attempt_id": "attempt-a", "replay_ref": ref}
        terminal = json.loads((fixtures.ROOT / "examples/task.receipt.example.json").read_text())
        terminal.update(task_id="task", project_id="project", replay_ref=other, cost_usd=None,
                        cost_status="unavailable")
        source = self.repo / "terminal.json"
        source.write_text(json.dumps(terminal))
        with self.assertRaises(ValueError):
            self.capture.finalize_case(self.repo, "project", task, source, vault_root=self.vault)
        terminal["replay_ref"] = ref
        source.write_text(json.dumps(terminal))
        (self.repo / "tracked.py").unlink()
        result = self.capture.finalize_case(self.repo, "project", task, source, vault_root=self.vault)
        self.assertIsNone(json.loads(result.read_text())["telemetry"]["cost_usd"])
        self.assertEqual(json.loads(result.read_text())["deleted_files"], ["tracked.py"])
        projection = self.capture.qualify_case(self.vault, "project", "task", ref)
        self.assertEqual(projection["state"], "case-retained")
        self.assertIn("v2-execution-unqualified", projection["gaps"])
        self.assertFalse(projection["replay_ready"])
        destination = self.root / "candidate"
        self.capture.restore_candidate(self.vault, "project", "task", ref, destination,
                                        expected_attempt_id="attempt-a")
        self.assertFalse((destination / "tracked.py").exists())
        self.assertEqual((destination / "untracked.txt").read_bytes(), b"required untracked input\n")

    def test_v2_integrity_and_permissions(self):
        ref = self.retain()
        manifest = self.vault / ref["manifest"]
        original = manifest.read_bytes()
        manifest.write_bytes(original + b" ")
        with self.assertRaises(ValueError):
            self.capture.validate_replay_ref(self.vault, "project", "task", ref)
        manifest.write_bytes(original)
        manifest.chmod(0o644)
        with self.assertRaises(ValueError):
            self.capture.validate_replay_ref(self.vault, "project", "task", ref)
        manifest.chmod(0o600)
        with patch.object(self.capture.os, "getuid", return_value=os.getuid() + 1), self.assertRaises(ValueError):
            self.capture.validate_replay_ref(self.vault, "project", "task", ref)
        value = json.loads(original)
        value["attempt_id"] = "other-attempt"
        malformed = json.dumps(value).encode()
        manifest.write_bytes(malformed)
        altered_ref = {**ref, "sha256": hashlib.sha256(malformed).hexdigest()}
        with self.assertRaises(ValueError):
            self.capture.validate_replay_ref(self.vault, "project", "task", altered_ref)
        manifest.write_bytes(original)
        artifact = manifest.parent / "inputs/untracked.txt"
        artifact.write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            self.capture.validate_replay_ref(self.vault, "project", "task", ref)
        artifact.unlink()
        artifact.symlink_to(self.repo / "untracked.txt")
        with self.assertRaises(ValueError):
            self.capture.validate_replay_ref(self.vault, "project", "task", ref)

    def test_v2_limits_refuse_before_payload_reads(self):
        excessive = self.config_v2()
        excessive["files"] += [f"extra-{i}" for i in range(5001)]
        with patch.object(self.capture, "_read", side_effect=AssertionError("unexpected read")):
            with self.assertRaises(ValueError):
                self.retain(config=excessive)
        with (self.repo / "untracked.txt").open("wb") as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
        with patch.object(self.capture, "_read", side_effect=AssertionError("unexpected read")):
            with self.assertRaises(ValueError):
                self.retain()
        (self.repo / "untracked.txt").write_bytes(b"small")
        config = self.config_v2()
        for i in range(8):
            name = f"large-{i}"
            with (self.repo / name).open("wb") as stream:
                stream.truncate(8 * 1024 * 1024)
            config["files"].append(name)
        with patch.object(self.capture, "_read", side_effect=AssertionError("unexpected read")):
            with self.assertRaises(ValueError):
                self.retain(config=config)
        oversized_manifest = {**self.config_v2(), "exclusions": ["x" * (1024 * 1024)]}
        with self.assertRaises(ValueError):
            self.retain(config=oversized_manifest)
        self.assertFalse(self.vault.exists())

    def test_v2_source_mutation_during_copy_never_publishes_manifest(self):
        inventory = self.capture._inventory
        count = 0
        def observe(root, names):
            nonlocal count
            count += 1
            if count == 2:
                (self.repo / "tracked.py").write_bytes(b"value = 3\n")
            return inventory(root, names)
        with patch.object(self.capture, "_inventory", side_effect=observe), self.assertRaises(ValueError):
            self.retain()
        self.assertFalse((self.vault / "project/attempt-a/input.json").exists())

    def test_v2_failed_publication_cannot_be_retried_under_same_identity(self):
        manifest = self.vault / "project/attempt-a/input.json"
        fsync = os.fsync
        def fail_after_manifest(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode) and manifest.exists():
                raise OSError("fixture: directory fsync failed")
            return fsync(fd)
        with patch.object(self.capture.os, "fsync", side_effect=fail_after_manifest):
            with self.assertRaises(self.capture.PublishedArtifactError):
                self.retain()
        original = manifest.read_bytes()
        with self.assertRaises(ValueError):
            self.retain()
        self.assertEqual(manifest.read_bytes(), original)

    def invoke(self, *args):
        return subprocess.run([sys.executable, str(fixtures.ROOT / "scripts/replay_capture.py"),
                               *map(str, args)], capture_output=True, text=True, timeout=10)

    def test_cli_v2_capture_restore_without_execution(self):
        config_path = self.root / "config.json"
        marker = self.root / "executed.marker"
        for kind in ("command", "native-host"):
            config = self.config_v2(kind)
            if kind == "command":
                config["execution"]["argv"] = [sys.executable, "-c", f"open({str(marker)!r}, 'w').write('bad')"]
            config_path.write_text(json.dumps(config))
            result = self.invoke("capture", "--repo", self.repo, "--project-id", "project", "--task-id", "task",
                                 "--config", config_path, "--vault-root", self.vault, "--attempt-id", kind)
            self.assertEqual(result.returncode, 0, result.stderr)
            ref = json.loads(result.stdout)
            self.assertEqual(set(ref), {"manifest", "sha256"})
            self.assertEqual(ref["manifest"], f"project/{kind}/input.json")
            self.assertEqual(result.stderr, "")
            output = self.root / ("restore-" + kind)
            result = self.invoke("restore", "--project-id", "project", "--task-id", "task",
                                 "--manifest", ref["manifest"], "--sha256", ref["sha256"], "--out", output,
                                 "--vault-root", self.vault, "--attempt-id", kind)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((output / "tracked.py").read_bytes(), b"value = 2\n")
            self.assertEqual((output / "tracked.py").stat().st_mode & 0o777, 0o750)
            self.assertFalse(marker.exists())
            self.assertFalse((self.repo / ".007").exists())
            wrong_output = self.root / ("wrong-attempt-" + kind)
            result = self.invoke("restore", "--project-id", "project", "--task-id", "task",
                                 "--manifest", ref["manifest"], "--sha256", ref["sha256"], "--out", wrong_output,
                                 "--vault-root", self.vault, "--attempt-id", "other-attempt")
            self.assertEqual(result.returncode, 2)
            self.assertFalse(wrong_output.exists())

    def test_cli_operation_flags_and_private_errors(self):
        config_path = self.root / "PRIVATE-SENTINEL-config.json"
        config_path.write_text(json.dumps(self.config_v2()))
        common = ["--project-id", "project", "--task-id", "task"]
        capture_args = ["capture", *common, "--repo", self.repo, "--config", config_path]
        restore_args = ["restore", *common, "--manifest", "project/attempt-a/input.json",
                        "--sha256", "a" * 64, "--out", self.root / "restored"]
        cases = [capture_args, [*capture_args, "--vault-root", self.vault],
                 [*capture_args, "--vault-root", self.vault, "--attempt-id", "attempt-a", "--out", "PRIVATE-SENTINEL"],
                 [*restore_args, "--repo", "PRIVATE-SENTINEL"],
                 ["PRIVATE-SENTINEL"], [*restore_args, "--unknown", "PRIVATE-SENTINEL"],
                 [*capture_args, "--vault-root", self.vault, "--attempt-id", "PRIVATE-SENTINEL/unsafe"]]
        for args in cases:
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("PRIVATE-SENTINEL", result.stderr)
                self.assertNotIn(str(self.root), result.stderr)
                self.assertFalse(self.vault.exists())
                self.assertFalse((self.root / "restored").exists())
        config_path.write_text(json.dumps(self.fixture.config))
        result = self.invoke(*capture_args, "--vault-root", self.vault, "--attempt-id", "attempt-a")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.vault.exists())
        config_path.write_text('{"PRIVATE-SENTINEL":')
        result = self.invoke(*capture_args, "--vault-root", self.vault, "--attempt-id", "attempt-a")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("PRIVATE-SENTINEL", result.stdout + result.stderr)
        self.assertFalse(self.vault.exists())

    def test_cli_git_timeout_is_sanitized_before_publication(self):
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(self.config_v2()))
        stdout, stderr = io.StringIO(), io.StringIO()
        args = ["capture", "--repo", str(self.repo), "--project-id", "project",
                "--task-id", "task", "--config", str(config_path), "--vault-root",
                str(self.vault), "--attempt-id", "attempt-a"]
        def timeout(command, **kwargs):
            self.assertEqual(command[:2], ["git", "-C"])
            raise subprocess.TimeoutExpired([*command, "PRIVATE-SENTINEL"], 30)
        with patch.object(self.capture.subprocess, "run", side_effect=timeout), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = self.capture.main(args)
            except subprocess.SubprocessError:
                self.fail("CLI leaked a subprocess exception instead of a sanitized refusal")
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("TimeoutExpired", stderr.getvalue())
        self.assertNotIn("PRIVATE-SENTINEL", stderr.getvalue())
        self.assertNotIn(str(self.repo), stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertFalse(self.vault.exists())

    def test_legacy_restore_invocation_is_unchanged(self):
        ref = self.fixture.capture()
        for verb_first in (True, False):
            output = self.root / ("legacy-restore-" + str(verb_first))
            stdout = io.StringIO()
            flags = ["--project-id", "project", "--task-id", "task", "--manifest", ref["manifest"],
                     "--sha256", ref["sha256"], "--out", str(output)]
            argv = ["restore", *flags] if verb_first else [*flags, "restore"]
            with patch.object(self.capture, "default_vault", return_value=self.vault), redirect_stdout(stdout):
                code = self.capture.main(argv)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue()), {"project_id": "project", "task_id": "task",
                             "input_sha256": ref["sha256"], "restored_files": 7})
            self.assertEqual((output / "tracked.py").read_bytes(), b"value = 2\n")


if __name__ == "__main__":
    unittest.main()
