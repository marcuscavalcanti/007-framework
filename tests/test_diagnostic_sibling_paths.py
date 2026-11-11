"""Counterexamples from the independent review; synthetic argv and data only."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import effort_lab
import framework_cli
import replay_eval


class DiagnosticSiblingPathsTests(unittest.TestCase):
    def test_same_argv_uses_the_same_hash_across_cli_and_replay(self):
        command = [sys.executable, "-c", "pass", "synthetic-é"]
        with tempfile.TemporaryDirectory() as temporary:
            cli = framework_cli.run_acceptance(Path(temporary), {"acceptance": {
                "schema": framework_cli.ACCEPTANCE_SCHEMA, "commands": [command]}})
            replay, passed = replay_eval.acceptance({"acceptance": [command]}, Path(temporary))
        self.assertTrue(passed)
        self.assertEqual(cli[0]["command_sha256"], replay[0]["command_sha256"])

    def test_controlled_cli_acceptance_preserves_local_argv_and_its_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            checks = framework_cli.run_acceptance(Path(temporary), {"acceptance": {
                "schema": framework_cli.ACCEPTANCE_SCHEMA,
                "commands": [[sys.executable, "-c", "pass", "SYNTHETIC-ARG"]]}})
        self.assertEqual(checks[0]["exit"], 0)
        self.assertTrue("SYNTHETIC-ARG" in json.dumps(checks))
        self.assertEqual(checks[0]["command"][-1], "SYNTHETIC-ARG")
        self.assertIn("command_sha256", checks[0])

    def test_mining_subprocess_errors_do_not_serialize_argv_or_output(self):
        errors = [subprocess.CalledProcessError(3, ["SYNTHETIC-ARG"], output="SYNTHETIC-OUTPUT"),
                  subprocess.TimeoutExpired(["SYNTHETIC-ARG"], 2, output="SYNTHETIC-OUTPUT"),
                  ValueError("SYNTHETIC-ARG")]
        for error in errors:
            with self.subTest(error_type=type(error).__name__), tempfile.TemporaryDirectory() as temporary:
                output, printed = Path(temporary), io.StringIO()
                with mock.patch.object(effort_lab, "pool", return_value=[{"sha": "a" * 40}]), \
                        mock.patch.object(effort_lab, "build", side_effect=error), \
                        mock.patch.object(effort_lab, "write_set", return_value=0), redirect_stdout(printed):
                    self.assertEqual(effort_lab.mine({"want": 1, "retain_diagnostic_text": False}, output, 1), 0)
                payload = printed.getvalue() + (output / "mine.jsonl").read_text()
                self.assertFalse("SYNTHETIC-ARG" in payload)
                self.assertFalse("SYNTHETIC-OUTPUT" in payload)
                self.assertIn(type(error).__name__, payload)

    def test_private_opt_in_preserves_a_bounded_mining_failure_diagnostic(self):
        with tempfile.TemporaryDirectory() as temporary:
            output, printed = Path(temporary), io.StringIO()
            error = subprocess.CalledProcessError(3, ["SYNTHETIC-ARG"])
            with mock.patch.object(effort_lab, "pool", return_value=[{"sha": "a" * 40}]), \
                    mock.patch.object(effort_lab, "build", side_effect=error), \
                    mock.patch.object(effort_lab, "write_set", return_value=0), redirect_stdout(printed):
                effort_lab.mine({"want": 1, "retain_diagnostic_text": True}, output, 1)
            row = json.loads((output / "mine.jsonl").read_text())
            self.assertTrue("SYNTHETIC-ARG" in row["drop"])
            self.assertLessEqual(len(row["drop"]), 200)
            self.assertFalse("SYNTHETIC-ARG" in printed.getvalue())
