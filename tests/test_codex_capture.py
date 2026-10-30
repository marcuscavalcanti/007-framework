"""Synthetic native-hook contracts; never read a real transcript or run a model."""

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def payload(name="PreToolUse", **changes):
    value = dict(hook_event_name=name, session_id="s1", turn_id="t1",
                 tool_use_id="c1", tool_name="Bash", tool_input={"command": "synthetic only"},
                 tool_response={"output": "synthetic only"}, permission_mode="default",
                 model="fixture-model", cwd="/synthetic/project", transcript_path=None)
    if name in ("SessionStart", "SessionEnd"):
        value.pop("turn_id")
    value.update(changes)
    return value


class CodexCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "state"
        try:
            self.adapter = importlib.import_module("codex_capture")
        except ModuleNotFoundError:
            self.fail("Codex metadata adapter is not implemented")

    def normalize(self, value):
        return self.adapter.normalize_hook(value, surface="desktop", host_version=None,
                                           observed_at="2026-10-16T00:00:00Z")

    def cli(self, raw, *extra):
        if isinstance(raw, dict):
            raw = json.dumps(raw).encode()
        return subprocess.run([sys.executable, str(ROOT / "scripts/codex_capture.py"),
                               "--surface", "desktop", "--state-dir", str(self.root),
                               "--binding-id", "b1", *extra], input=raw, capture_output=True, timeout=10)

    def test_documented_hook_shapes_map_to_event_kinds(self):
        for name, kind in (("SessionStart", "session_start"), ("SessionEnd", "session_end"),
                           ("UserPromptSubmit", "turn_start"), ("Stop", "turn_stop"),
                           ("Interrupt", "interrupt"), ("PreToolUse", "tool_start"),
                           ("PostToolUse", "tool_finish")):
            with self.subTest(name=name):
                value = self.normalize(payload(name))
                self.assertEqual(value["kind"], kind)
                self.assertEqual(value["surface"], "desktop")
                self.assertEqual(value["tool_call_id"], "c1" if name in ("PreToolUse", "PostToolUse") else None)
                self.assertEqual(value["turn_id"], None if name in ("SessionStart", "SessionEnd") else "t1")

    def test_turn_tool_ids_required(self):
        for changes in ({"session_id": None}, {"turn_id": None}, {"tool_use_id": None},
                        {"session_id": []}, {"turn_id": {"PRIVATE": "value"}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.normalize(payload(**changes))

    def test_native_model_is_reported_not_served(self):
        value = self.normalize(payload())
        self.assertEqual(value["model_reported"], "fixture-model")
        self.assertNotIn("model_served", value)
        self.assertIsNone(value["host_version"])
        self.assertIn("usage-unobserved", value["gaps"])
        self.assertIn("host-version-unavailable", value["gaps"])

    def test_unknown_hook_and_child_attribution_are_not_silently_accepted(self):
        for value in (payload("Unknown"), payload("SubagentStart"), payload("SubagentStop"),
                      payload(agent_id="child-1")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.normalize(value)

    def test_sensitive_sentinels_never_reach_disk_stdout_stderr_or_hash(self):
        values = []
        for sentinel in ("PRIVATE_SENTINEL_A", "PRIVATE_SENTINEL_B"):
            value = payload(prompt=sentinel, tool_input={"command": sentinel},
                            tool_response={"output": sentinel}, last_assistant_message=sentinel,
                            transcript_path=sentinel, description=sentinel, env={"key": sentinel})
            values.append(self.normalize(value))
            run = self.cli(value)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout, b"{}\n")
            self.assertEqual(run.stderr, b"")
            for path in self.root.rglob("*.json"):
                self.assertNotIn(sentinel.encode(), path.read_bytes())
        self.assertEqual(values[0], values[1])
        self.assertEqual(len(list((self.root / "b1/events").iterdir())), 1)

    def test_oversized_invalid_json_and_wrong_types_are_bounded(self):
        for raw in (b"x" * (1024 * 1024 + 1), b'{"PRIVATE":', b"[]", b"null",
                    b'{"hook_event_name":"Stop","hook_event_name":"PRIVATE"}',
                    b"[" * 2000 + b"]" * 2000, b'{"ignored":NaN}', b"\xff"):
            run = self.cli(raw)
            self.assertEqual(run.returncode, 1)
            self.assertEqual(run.stdout, b"")
            self.assertLess(len(run.stderr), 80)
            self.assertNotIn(b"PRIVATE", run.stderr)
        self.assertFalse(list((self.root / "b1/events").glob("*.json")))

    def test_no_path_payload_is_opened(self):
        fifo = self.root.parent / "never-open"
        os.mkfifo(fifo)
        run = self.cli(payload(transcript_path=str(fifo), cwd=str(fifo), tool_input={"path": str(fifo)}))
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_two_sessions_same_turn_label_do_not_collide(self):
        self.assertNotEqual(self.normalize(payload())["event_key"],
                            self.normalize(payload(session_id="s2"))["event_key"])

    def test_missing_model_stays_unknown(self):
        value = payload()
        value.pop("model")
        normalized = self.normalize(value)
        self.assertIsNone(normalized["model_reported"])
        self.assertIn("model-unavailable", normalized["gaps"])

    def test_unknown_event_and_argument_errors_are_sanitized(self):
        unknown = self.cli(payload("PRIVATE_SECRET"))
        self.assertEqual(unknown.returncode, 1)
        self.assertEqual(unknown.stderr, b"hook-unsupported\n")
        bad_arg = self.cli(payload(), "--surface", "PRIVATE_SECRET")
        self.assertEqual(bad_arg.returncode, 1)
        self.assertNotIn(b"PRIVATE_SECRET", bad_arg.stdout + bad_arg.stderr)

    def test_untrusted_path_and_busy_writer_do_not_escape_scope(self):
        bad = self.cli(payload(), "--binding-id", "../escape")
        self.assertEqual(bad.returncode, 1)
        self.assertFalse(self.root.exists())
        self.assertEqual(self.cli(payload()).returncode, 0)
        lock = self.root / "b1/lock"
        lock.mkdir(mode=0o700)
        busy = self.cli(payload(turn_id="t2"))
        self.assertEqual(busy.returncode, 1)
        self.assertEqual(busy.stderr, b"lock-busy\n")
        self.assertTrue(lock.exists())

    def test_stop_never_requests_continuation(self):
        run = self.cli(payload("Stop", stop_hook_active=True, last_assistant_message="PRIVATE"))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), {})


if __name__ == "__main__":
    unittest.main()
