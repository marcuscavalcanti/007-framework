"""Synthetic replay controls: metadata by default, explicit private text retention."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

import test_replay_capture as fixtures
import replay_eval as replay


class ReplayDiagnosticPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ReplayCaptureTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.config = {"seed": 7, "arms": {"NEW": {"provider": "fixture", "model": "fixture",
                        "effort": "medium", "doctrine": ""}},
                       "agent_command": [sys.executable, "-c",
                           "import sys; print('AGENT-OUT-SENTINEL'); print('AGENT-ERR-SENTINEL', file=sys.stderr)"]}
        self.argv = [sys.executable, "-c",
            "import sys; print('CHECK-OUT-SENTINEL'); print('CHECK-ERR-SENTINEL', file=sys.stderr); raise SystemExit(int(sys.argv[1]))", "0"]
        (self.fixture.repo / "acceptance.json").write_text(json.dumps({
            "schema": "007-framework/acceptance/v1", "commands": [self.argv]}))
        self.ref = self.fixture.capture()
        self.task = {"id": "privacy", "source_task_id": "task", "project_id": "project", "replay_ref": self.ref}

    def execute(self, config, name):
        output = self.root / name
        output.mkdir(mode=0o700)
        cell = replay.execute_cell(config, self.task, "NEW", 1, output, 10, vault_root=self.fixture.vault)
        replay.write_summary(output, self.fixture.repo / "task.txt", config, 1, [cell])
        return cell, output

    def test_explicit_metadata_only_mode_sanitizes_copies_and_preserves_replay(self):
        for option in ({"retain_diagnostic_text": False},):
            with self.subTest(option=option):
                cell, output = self.execute({**self.config, **option}, "out-" + str(len(option)))
                self.assertTrue(cell["accepted"])
                self.assertEqual(cell["agent_tail"], "")
                self.assertEqual(cell["acceptance"][0]["tail"], "")
                self.assertEqual(cell["acceptance"][0]["command"], [])
                self.assertFalse(cell["diagnostic_text_retained"])
                self.assertEqual(cell["agent_output"]["stdout_utf8_sha256"],
                                 hashlib.sha256(b"AGENT-OUT-SENTINEL\n").hexdigest())
                copies = [json.loads(p.read_text()) for p in output.rglob("*.json")
                          if "inputs" not in p.parts]
                for value in copies:
                    serialized = json.dumps(value)
                    for secret in ("AGENT-OUT-SENTINEL", "AGENT-ERR-SENTINEL", "CHECK-OUT-SENTINEL", "CHECK-ERR-SENTINEL"):
                        self.assertNotIn(secret, serialized)
                restored = output / "restored"
                self.fixture.module().restore_input(output / "cases", "project", cell["task_id"], cell["replay_ref"], restored)
                self.assertEqual((restored / "acceptance.json").read_bytes(),
                                 (self.fixture.repo / "acceptance.json").read_bytes())
                self.assertEqual((restored / "tracked.py").read_bytes(), b"value = 2\n")

    def test_local_default_and_explicit_retention_keep_full_diagnostics(self):
        for option in ({}, {"retain_diagnostic_text": True}):
            with self.subTest(option=option):
                cell, _ = self.execute({**self.config, **option}, "local-" + str(len(option)))
                self.assertTrue(cell["diagnostic_text_retained"])
                self.assertIn("AGENT-ERR-SENTINEL", cell["agent_tail"])
                self.assertIn("CHECK-ERR-SENTINEL", cell["acceptance"][0]["tail"])
                self.assertEqual(cell["acceptance"][0]["command"], self.argv)
                self.assertTrue(cell["accepted"])

    def test_failed_acceptance_keeps_status_and_hashes_without_raw_text(self):
        for value, expected in (("0", True), ("3", False)):
            command = self.argv[:-1] + [value]
            checks, passed = replay.acceptance({"acceptance": [command]}, self.fixture.repo, retain_diagnostic_text=False)
            self.assertEqual(passed, expected)
            self.assertEqual(checks[0]["exit"], int(value))
            self.assertNotIn("SENTINEL", json.dumps(checks))
            self.assertEqual(checks[0]["output"]["stderr_utf8_bytes"], len(b"CHECK-ERR-SENTINEL\n"))

    def test_retention_requires_a_boolean_before_any_subprocess(self):
        output = self.root / "invalid"; output.mkdir(mode=0o700)
        for value in ("false", "true", 0, 1, None, []):
            with self.subTest(value=value), mock.patch.object(replay, "run") as launched:
                with self.assertRaisesRegex(ValueError, "retain_diagnostic_text"):
                    replay.execute_cell({**self.config, "retain_diagnostic_text": value}, self.task,
                                        "NEW", 1, output, 10, vault_root=self.fixture.vault)
                launched.assert_not_called()

    def test_local_policy_preserves_directory_permissions_but_refuses_symlink_outputs(self):
        public = self.root / "public"; public.mkdir(); public.chmod(0o755)
        alias = self.root / "alias"; alias.symlink_to(public, target_is_directory=True)
        with mock.patch.object(replay, "run") as launched:
            with self.assertRaisesRegex(ValueError, "symlink"):
                replay.execute_cell(self.config, self.task, "NEW", 1, alias, 10, vault_root=self.fixture.vault)
            launched.assert_not_called()
        cell = replay.execute_cell(self.config, self.task, "NEW", 1, public, 10, vault_root=self.fixture.vault)
        self.assertTrue(cell["accepted"])
        self.assertEqual(public.stat().st_mode & 0o777, 0o755)
