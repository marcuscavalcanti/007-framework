"""Offline metadata custody: no model calls or real session payloads."""

import hashlib
import importlib
import json
import os
import stat
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def event(kind="tool_start", **changes):
    value = dict(schema="007-framework/native-event/v1", adapter="fixture",
                 adapter_version="1", host_version=None, surface="terminal",
                 kind=kind, session_id="s1", turn_id="t1", tool_call_id="c1",
                 agent_id=None, model_reported=None, observed_at="2026-10-16T00:00:00Z",
                 gaps=["context-unobserved", "host-version-unavailable", "model-unavailable",
                       "runtime-unqualified", "usage-unobserved"])
    if kind.startswith("session_"):
        value.update(turn_id=None, tool_call_id=None)
    elif not kind.startswith("tool_"):
        value["tool_call_id"] = None
    value.update(changes)
    identity = [value[k] for k in ("adapter", "kind", "session_id", "turn_id", "tool_call_id", "agent_id")]
    value["event_key"] = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()
    return value


class NativeCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "journal"
        try:
            self.core = importlib.import_module("native_capture")
        except ModuleNotFoundError:
            self.fail("native metadata journal is not implemented")

    def append(self, value=None, binding="b1"):
        return self.core.append_event(self.root, binding, value or event())

    def report(self, binding="b1"):
        return self.core.summarize_events(self.root, binding)

    def test_event_contract_rejects_extra_fields_and_invalid_ids(self):
        for changes in ({"prompt": "forbidden"}, {"session_id": None},
                        {"session_id": "../x"}, {"turn_id": "x" * 257},
                        {"tool_call_id": True}, {"surface": "unknown"},
                        {"schema": "unknown"}, {"observed_at": "yesterday"},
                        {"model_reported": "line\nsecret"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.append(event(**changes))
        self.assertFalse(self.root.exists())

    def test_event_key_and_required_gaps_are_checked(self):
        for value in (dict(event(), event_key="0" * 64), dict(event(), gaps=[]),
                      dict(event(), gaps=["raw private message"])):
            with self.assertRaises(ValueError):
                self.append(value)

    def test_absent_host_version_is_gap(self):
        self.append()
        self.assertIn("host-version-unavailable", self.report()["gaps"])
        self.assertEqual(self.report()["coverage"], "partial")

    def test_generic_adapter_has_no_codex_policy(self):
        self.assertEqual(self.append(event(adapter="independent-host")), "written")
        self.assertEqual(self.report()["event_count"], 1)

    def test_same_event_is_idempotent_across_observation_times(self):
        self.assertEqual(self.append(), "written")
        path = self.root / "b1" / "events" / (event()["event_key"] + ".json")
        original = path.read_bytes()
        self.assertEqual(self.append(event(observed_at="2026-10-16T01:00:00Z")), "duplicate")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.report()["event_count"], 1)

    def test_conflicting_same_key_preserves_original(self):
        self.append()
        path = self.root / "b1" / "events" / (event()["event_key"] + ".json")
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "^event-conflict$"):
            self.append(event(host_version="fixture-2"))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.report()["coverage"], "invalid")
        self.assertIn("event-conflict", self.report()["gaps"])

    def test_two_bindings_do_not_mix(self):
        self.append(binding="first")
        self.append(event(session_id="s2"), binding="second")
        self.assertEqual(self.report("first")["event_count"], 1)
        self.assertEqual(self.report("second")["event_count"], 1)
        with self.assertRaises(ValueError):
            self.append(binding="../outside")

    def test_post_before_pre_is_joined_by_id(self):
        self.append(event("tool_finish"))
        self.assertIn("orphan-tool-event", self.report()["gaps"])
        self.append()
        self.assertNotIn("orphan-tool-event", self.report()["gaps"])
        self.append(event("tool_finish", session_id="other"))
        self.assertIn("orphan-tool-event", self.report()["gaps"])

    def test_orphan_post_and_missing_terminal_stay_partial(self):
        self.append()
        self.assertEqual(self.report()["coverage"], "partial")
        self.assertIn("orphan-tool-event", self.report()["gaps"])

    def test_stop_is_not_task_acceptance(self):
        self.append(event("turn_stop"))
        value = self.report()
        self.assertEqual(value["coverage"], "partial")
        self.assertEqual(set(value), {"schema", "coverage", "event_count", "gaps"})
        self.assertEqual(value["schema"], "007-framework/native-summary/v1")

    def test_byte_and_count_limits_reject_without_truncation(self):
        with patch.object(self.core, "MAX_EVENT_BYTES", 64), self.assertRaises(ValueError):
            self.append()
        self.append()
        for index in range(1, 2000):
            value = event(turn_id=f"t{index + 1}")
            path = self.root / "b1" / "events" / (value["event_key"] + ".json")
            path.write_text(json.dumps(value))
            path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "^journal-limit$"):
            self.append(event(turn_id="overflow"))
        self.assertEqual(len(list((self.root / "b1" / "events").iterdir())), 2000)
        self.assertEqual(self.append(), "duplicate")

    def test_existing_lock_is_not_removed(self):
        self.append()
        lock = self.root / "b1" / "lock"
        lock.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "^lock-busy$"):
            self.append(event(turn_id="other"))
        with self.assertRaisesRegex(ValueError, "^lock-busy$"):
            self.report()
        self.assertTrue(lock.is_dir())

    def test_diagnostic_read_does_not_refuse_a_concurrent_writer(self):
        self.append()
        real_load = self.core._load
        outcomes = []

        def append_during_read(path, limit):
            if not outcomes:
                try:
                    outcomes.append(self.append(event(turn_id="second")))
                except self.core.CaptureError as exc:
                    outcomes.append(exc.code)
            return real_load(path, limit)

        with patch.object(self.core, "_load", side_effect=append_during_read):
            observed = self.report()
        self.assertEqual(outcomes, ["written"])
        self.assertEqual(observed["event_count"], 1)
        self.assertEqual(observed["coverage"], "partial")
        self.assertEqual(self.report()["event_count"], 2)

    def test_gap_published_during_diagnostic_read_is_not_hidden(self):
        self.append()
        real_load = self.core._load
        outcomes = []

        def gap_during_read(path, limit):
            if not outcomes:
                try:
                    self.core.record_gap(self.root, "b1", "event-invalid")
                    outcomes.append("written")
                except self.core.CaptureError as exc:
                    outcomes.append(exc.code)
            return real_load(path, limit)

        with patch.object(self.core, "_load", side_effect=gap_during_read):
            observed = self.report()
        self.assertEqual(outcomes, ["written"])
        self.assertEqual(observed["coverage"], "invalid")
        self.assertIn("event-invalid", observed["gaps"])

    def test_event_disappearing_after_listing_is_not_ignored(self):
        self.append()
        real_load = self.core._load

        def remove_before_read(path, limit):
            path.unlink()
            return real_load(path, limit)

        with patch.object(self.core, "_load", side_effect=remove_before_read):
            with self.assertRaisesRegex(ValueError, "^journal-io$"):
                self.report()

    def test_writer_still_active_after_read_is_reported_without_removing_lock(self):
        self.append()
        lock = self.root / "b1/lock"
        real_load = self.core._load

        def acquire_during_read(path, limit):
            lock.mkdir(mode=0o700)
            return real_load(path, limit)

        with patch.object(self.core, "_load", side_effect=acquire_during_read):
            with self.assertRaisesRegex(ValueError, "^lock-busy$"):
                self.report()
        self.assertTrue(lock.is_dir())

    def test_unpublished_metadata_filename_is_rejected_before_read(self):
        self.append()
        real_load = self.core._load
        for directory, code in (("events", "identity-invalid"), ("gaps", "journal-io")):
            with self.subTest(directory=directory):
                temporary = self.root / "b1" / directory / ".unpublished"
                temporary.write_text("PRIVATE not a published entry")
                temporary.chmod(0o600)

                def published_only(path, limit):
                    self.assertNotEqual(path, temporary, "diagnostic read an unpublished file")
                    return real_load(path, limit)

                with patch.object(self.core, "_load", side_effect=published_only):
                    with self.assertRaisesRegex(ValueError, "^" + code + "$"):
                        self.report()
                self.assertTrue(temporary.exists())
                temporary.unlink()

    def test_symlink_traversal_is_rejected(self):
        target = self.root.parent / "outside"
        target.mkdir()
        self.root.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.append()
        self.assertEqual(list(target.iterdir()), [])

    def test_private_files_and_read_denial(self):
        self.append()
        for path in self.root.rglob("*"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700 if path.is_dir() else 0o600)
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            self.report()

    def test_published_fsync_failure_does_not_retry_under_new_key(self):
        import replay_capture
        real_fsync = os.fsync
        saw_file = False
        failed = False

        def fail_directory_once(fd):
            nonlocal saw_file, failed
            if stat.S_ISREG(os.fstat(fd).st_mode):
                saw_file = True
            elif saw_file and not failed:
                failed = True
                raise OSError("PRIVATE filesystem path")
            return real_fsync(fd)

        with patch.object(replay_capture.os, "fsync", fail_directory_once):
            with self.assertRaisesRegex(ValueError, "^journal-io$"):
                self.append()
        self.assertEqual(len(list((self.root / "b1" / "events").iterdir())), 1)
        self.assertEqual(self.append(), "duplicate")
        self.assertEqual(self.report()["coverage"], "invalid")
        self.assertIn("journal-io", self.report()["gaps"])

    def test_parent_directory_sync_failure_prevents_event_publication(self):
        real_fsync = os.fsync

        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("PRIVATE parent directory")
            return real_fsync(fd)

        with patch.object(os, "fsync", fail_directory), self.assertRaises(ValueError):
            self.append()
        self.assertFalse(list(self.root.rglob("*.json")))

    def test_missing_root_parent_is_rejected_without_creating_ancestors(self):
        missing_parent = self.root.parent / "not-provisioned"
        self.root = missing_parent / "journal"
        with self.assertRaisesRegex(ValueError, "^journal-io$"):
            self.append()
        with self.assertRaisesRegex(ValueError, "^journal-io$"):
            self.core.record_gap(self.root, "b1", "journal-io")
        self.assertFalse(missing_parent.exists())

    def test_corrupt_or_missing_event_is_not_green(self):
        with self.assertRaises(ValueError):
            self.report()
        self.assertFalse(self.root.exists())
        self.append()
        path = next((self.root / "b1" / "events").iterdir())
        path.write_text('{"PRIVATE":"not an event"}')
        with self.assertRaisesRegex(ValueError, "^(event-invalid|journal-io)$"):
            self.report()

    def test_gap_write_failure_does_not_recurse_or_claim_delivery(self):
        with patch.object(self.core, "write_bytes_no_replace", side_effect=OSError("PRIVATE")):
            with self.assertRaisesRegex(ValueError, "^journal-io$"):
                self.core.record_gap(self.root, "b1", "journal-io")
        self.assertFalse(list(self.root.rglob("*.json")))

    def test_gap_is_idempotent_and_never_free_text(self):
        self.core.record_gap(self.root, "b1", "hook-unsupported")
        self.core.record_gap(self.root, "b1", "hook-unsupported")
        self.assertEqual(len(list((self.root / "b1" / "gaps").iterdir())), 1)
        with self.assertRaises(ValueError):
            self.core.record_gap(self.root, "b1", "PRIVATE raw error")
        self.assertIn("hook-unsupported", self.report()["gaps"])

    def diagnostic(self, binding="b1"):
        return subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/native_capture.py"),
                               "--state-dir", str(self.root), "--binding-id", binding],
                              capture_output=True, timeout=10)

    def test_report_never_promotes_observed_to_replay_or_economic_valid(self):
        self.append(event("session_start"))
        self.append(event("turn_start"))
        self.append()
        self.append(event("tool_finish"))
        self.append(event("turn_stop"))
        self.append(event("session_end"))
        run = self.diagnostic()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(run.stdout, "diagnostic CLI emitted no result")
        report = json.loads(run.stdout)
        self.assertEqual(report["coverage"], "partial")
        self.assertEqual(report["event_count"], 6)
        self.assertEqual(set(report), {"schema", "coverage", "event_count", "gaps"})
        self.assertIn("usage-unobserved", report["gaps"])

    def test_read_denial_and_missing_journal_are_not_zero_work(self):
        missing = self.diagnostic()
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(missing.stdout, b"")
        self.assertFalse(self.root.exists())
        self.append()
        self.root.chmod(0o755)
        denied = self.diagnostic()
        self.assertEqual(denied.returncode, 1)
        self.assertEqual(denied.stdout, b"")

    def test_cli_report_contains_no_raw_payloads(self):
        self.append()
        path = next((self.root / "b1/events").iterdir())
        path.write_text('{"PRIVATE_CORRUPTED_PAYLOAD":')
        run = self.diagnostic()
        self.assertEqual(run.returncode, 1)
        self.assertNotIn(b"PRIVATE", run.stdout + run.stderr)
        self.assertNotIn(str(self.root).encode(), run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
