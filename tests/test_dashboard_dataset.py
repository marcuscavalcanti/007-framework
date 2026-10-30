"""Read-only dataset projection and acquisition clocks, using retained fixtures."""
import importlib
import copy
import json
import os
from datetime import datetime, timedelta, timezone
from unittest import TestCase, mock
from types import SimpleNamespace

import test_replay_capture as fixtures

dashboard = importlib.import_module("dashboard")
capture = importlib.import_module("replay_capture")


class DatasetDashboardTests(TestCase):
    def setUp(self):
        self.fixture = fixtures.ReplayCaptureTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.repo, self.vault = self.fixture.repo, self.fixture.vault
        self.ref = self.fixture.capture()
        self.start = {"task_id": "task", "replay_ref": self.ref}

    def collector(self):
        self.assertTrue(hasattr(dashboard, "DatasetCache"), "dataset dashboard collector is missing")
        return dashboard.DatasetCache(self.vault)

    def finalize(self, **extra):
        source = self.repo / "terminal.json"
        terminal = json.loads((fixtures.ROOT / "examples/task.receipt.example.json").read_text())
        terminal.update(task_id="task", project_id="project", replay_ref=self.ref)
        terminal.update(extra)
        source.write_text(json.dumps(terminal))
        return capture.finalize_case(self.repo, "project", self.start, source, vault_root=self.vault)

    def test_unchanged_poll_reuses_integrity_without_oracle_execution(self):
        cache = self.collector()
        with (mock.patch.object(capture, "qualify_case", wraps=capture.qualify_case) as qualify,
              mock.patch.object(capture.subprocess, "run", side_effect=AssertionError("oracle must not run"))):
            first = cache("project", [self.start], [])
            second = cache("project", [self.start], [])
        self.assertEqual(first, second)
        self.assertEqual(qualify.call_count, 1)
        self.assertEqual(first["counts"]["inputs-retained"], 1)
        self.assertEqual(first["counts"]["case-retained"], 0)
        self.assertEqual(first["counts"]["replay-ready"], 0)

    def test_new_result_invalidates_cache_and_preserves_no_qualification_claim(self):
        cache = self.collector()
        cache("project", [self.start], [])
        self.finalize()
        result = cache("project", [self.start], [{**self.start, "replay_ready": True, "causal_eligible": True}])
        self.assertEqual(result["counts"]["case-retained"], 1)
        self.assertEqual(result["counts"]["qualified-comparison"], 0)
        self.assertFalse(result["cases"][0]["replay_ready"])
        serialized = json.dumps(result)
        for private in (str(self.repo), "tracked.py", "Fixture-only context.", "manifest"):
            self.assertNotIn(private, serialized)

    def test_changed_candidate_generation_invalidates_cached_hash(self):
        self.finalize()
        cache = self.collector()
        self.assertEqual(cache("project", [self.start], [self.start])["counts"]["case-retained"], 1)
        target = self.vault / "project/task/outputs/files/tracked.py"
        before = target.stat()
        target.write_bytes(b"value = 9\n")
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
        result = cache("project", [self.start], [self.start])
        self.assertEqual(result["counts"]["case-retained"], 0)
        self.assertEqual(result["cases"][0]["state"], "invalid")

    def test_cache_check_time_does_not_advance_on_empty_poll(self):
        clock = [datetime(2026, 10, 13, 12, tzinfo=timezone.utc)]
        cache = dashboard.DatasetCache(self.vault, now=lambda: clock[0])
        first = cache("project", [self.start], [])
        self.assertEqual(first["cases"][0]["checked_at"], "2026-10-13T12:00:00+00:00")
        self.assertEqual(first["oldest_checked_at"], first["latest_checked_at"])
        clock[0] += timedelta(seconds=2)
        self.assertEqual(cache("project", [self.start], []), first)

    def test_stamp_collision_is_only_dated_history_and_fresh_check_rejects(self):
        self.finalize()
        cache = self.collector()
        with mock.patch.object(dashboard, "case_signature", return_value=("same-metadata",)):
            first = cache("project", [self.start], [self.start])
            (self.vault / "project/task/outputs/files/tracked.py").write_bytes(b"value = 9\n")
            cached = cache("project", [self.start], [self.start])
        self.assertEqual(cached, first)
        self.assertEqual(cached["scope"], "last-checked-retention")
        self.assertIsNotNone(cached["cases"][0]["checked_at"])
        self.assertEqual(cached["counts"]["case-retained"], 1)
        fresh = capture.qualify_case(self.vault, "project", "task", self.ref)
        self.assertEqual(fresh["state"], "invalid")
        self.assertFalse(fresh["candidate_recoverable"])

    def test_aggregate_preserves_range_of_check_dates_not_latest_poll(self):
        projects = [{"available": True, "metrics": {}, "dataset": {
            "complete": True, "counts": {key: 0 for key in dashboard.DATASET_STAGES},
            "oldest_checked_at": earlier, "latest_checked_at": later}}
            for earlier, later in [("2026-10-13T10:00:00+00:00", "2026-10-13T11:00:00+00:00"),
                                   ("2026-10-13T09:00:00+00:00", "2026-10-13T12:00:00+00:00")]]
        data = dashboard.aggregate_projects(projects)["dataset"]
        self.assertEqual(data["oldest_checked_at"], "2026-10-13T09:00:00+00:00")
        self.assertEqual(data["latest_checked_at"], "2026-10-13T12:00:00+00:00")
        self.assertEqual(data["scope"], "last-checked-retention")

    def test_other_case_publication_does_not_rehash_this_case(self):
        cache = self.collector()
        with mock.patch.object(capture, "qualify_case", wraps=capture.qualify_case) as qualify:
            cache("project", [self.start], [])
            capture.capture_input(self.repo, "project", "other", self.fixture.config, vault_root=self.vault)
            cache("project", [self.start], [])
        self.assertEqual(qualify.call_count, 1)

    def test_identity_scan_budget_is_inconclusive_not_invalid_business_evidence(self):
        cache = self.collector()
        entries = mock.MagicMock()
        entries.__enter__.return_value = (SimpleNamespace(name=str(i)) for i in range(capture.MAX_ENTRIES * 2 + 11))
        with (mock.patch.object(capture.os, "scandir", return_value=entries),
              mock.patch.object(capture, "qualify_case", wraps=capture.qualify_case) as qualify):
            result = cache("project", [self.start], [])
        self.assertFalse(result["complete"])
        self.assertEqual(result["cases"][0]["state"], "unavailable")
        self.assertEqual(qualify.call_count, 0)

    def test_mutation_during_qualification_is_not_cached_as_retained(self):
        cache = self.collector()
        qualify = capture.qualify_case
        def mutate(*args):
            result = qualify(*args)
            target = self.vault / "project/task/inputs/tracked.py"
            before = target.stat()
            target.write_bytes(b"value = 9\n")
            os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
            return result
        with mock.patch.object(capture, "qualify_case", side_effect=mutate):
            result = cache("project", [self.start], [])
        self.assertFalse(result["complete"])
        self.assertEqual(result["cases"][0]["state"], "unavailable")
        self.assertEqual(cache("project", [self.start], [])["cases"][0]["state"], "invalid")

    def test_duplicate_receipts_or_disagreeing_reference_do_not_preserve_a_case(self):
        self.finalize()
        cache = self.collector()
        for receipts in ([self.start, self.start], [{**self.start, "replay_ref": None}]):
            with self.subTest(receipts=receipts):
                result = cache("project", [self.start], receipts)
                self.assertFalse(result["complete"])
                self.assertEqual(result["counts"]["case-retained"], 0)

    def test_bound_batch_is_explicitly_partial_not_zero_activity(self):
        result = self.collector()("project", [{"task_id": f"task-{i}"} for i in range(101)], [])
        self.assertFalse(result["complete"])
        self.assertEqual(result["counts"]["observational"], 101)
        self.assertEqual(len(result["cases"]), 100)

    def test_denied_or_escaping_case_is_not_read_as_retained(self):
        cache = self.collector()
        escaping = {**self.start, "replay_ref": {"manifest": "../private/input.json", "sha256": "a" * 64}}
        self.assertEqual(cache("project", [escaping], [])["cases"][0]["state"], "invalid")
        with mock.patch.object(dashboard, "case_signature", side_effect=PermissionError("PRIVATE PATH")):
            result = cache("project", [self.start], [])
        self.assertFalse(result["complete"])
        self.assertNotIn("PRIVATE PATH", json.dumps(result))

    def test_project_collector_keeps_last_good_data_stale_and_ingest_clock_stable(self):
        self.assertTrue(hasattr(dashboard, "ProjectCollector"), "project acquisition collector is missing")
        clock = [datetime(2026, 10, 12, 12, tzinfo=timezone.utc)]
        collector = dashboard.ProjectCollector(now=lambda: clock[0])
        entry = {"project_id": "project", "path": str(self.repo), "name": "Fixture", "registered_at": "x"}
        good = {"available": True, "metrics": {"tasks": 2}, "recent_tasks": [],
                "source_sha256": "a" * 64, "dataset": {"complete": True},
                "objective": {"gates": [{"key": "economics", "status": "pass"}]},
                "invalid_receipts": [], "invalid_task_starts": []}
        failed = {**good, "available": False, "metrics": {"tasks": 0}, "error": "unavailable"}
        with mock.patch.object(dashboard, "project_snapshot", side_effect=[copy.deepcopy(item) for item in (good, good, failed, good)]):
            first = collector(entry, lambda *_: {})
            clock[0] += timedelta(seconds=2)
            same = collector(entry, lambda *_: {})
            clock[0] += timedelta(seconds=2)
            stale = collector(entry, lambda *_: {})
            clock[0] += timedelta(seconds=2)
            recovered = collector(entry, lambda *_: {})
        self.assertEqual(first["ingested_at"], same["ingested_at"])
        self.assertEqual(first["ingested_at"], stale["ingested_at"])
        self.assertEqual(stale["metrics"]["tasks"], 2)
        self.assertTrue(stale["stale"])
        self.assertFalse(stale["available"])
        self.assertEqual(stale["objective"]["gates"][0]["status"], "wait")
        self.assertEqual(recovered["objective"]["gates"][0]["status"], "pass")
        self.assertGreater(stale["read_at"], first["read_at"])
        self.assertFalse(recovered["stale"])
        self.assertEqual(recovered["ingested_at"], first["ingested_at"])

    def test_project_path_identity_change_does_not_inherit_last_good_data(self):
        self.assertTrue(hasattr(dashboard, "ProjectCollector"), "project acquisition collector is missing")
        collector = dashboard.ProjectCollector()
        entry = {"project_id": "project", "path": str(self.repo)}
        with mock.patch.object(dashboard, "project_snapshot", side_effect=[
                {"available": True, "metrics": {"tasks": 2}, "source_sha256": "a" * 64},
                {"available": False, "metrics": {"tasks": 0}, "error": "unavailable"}]):
            collector(entry, lambda *_: {})
            changed = collector({**entry, "path": str(self.repo / "other")}, lambda *_: {})
        self.assertEqual(changed["metrics"]["tasks"], 0)
        self.assertIsNone(changed["ingested_at"])

    def test_reader_exception_retains_old_data_or_an_explicit_unavailable_project(self):
        entry = {"project_id": "project", "path": str(self.repo), "name": "Fixture", "registered_at": "fixture"}
        collector = dashboard.ProjectCollector()
        good = {"available": True, "metrics": {"tasks": 2}, "source_sha256": "a" * 64}
        with mock.patch.object(dashboard, "project_snapshot", side_effect=[good, PermissionError("private path")]):
            collector(entry, lambda *_: {})
            stale = collector(entry, lambda *_: {})
        self.assertEqual(stale["metrics"]["tasks"], 2)
        self.assertTrue(stale["stale"])
        self.assertNotIn("private path", json.dumps(stale))
        with mock.patch.object(dashboard, "project_snapshot", side_effect=PermissionError("private path")):
            first = dashboard.ProjectCollector()(entry, lambda *_: {})
        self.assertFalse(first["available"])
        self.assertIsNone(first["ingested_at"])
        self.assertEqual(first["recent_tasks"], [])

    def test_directory_listing_denial_is_not_an_empty_source(self):
        report = importlib.import_module("harness_report")
        with mock.patch.object(capture.os, "scandir", side_effect=PermissionError("fixture listing denied")):
            receipts, receipt_errors = report.load_receipts(self.repo)
            starts, start_errors = dashboard.load_task_starts(self.repo)
        self.assertEqual(receipts, [])
        self.assertEqual(starts, [])
        self.assertTrue(receipt_errors)
        self.assertTrue(start_errors)

    def test_history_shrink_is_not_published_as_improvement_or_zero_activity(self):
        entry = {"project_id": "project", "path": str(self.repo)}
        collector = dashboard.ProjectCollector()
        good = {"available": True, "metrics": {"tasks": 2, "started_tasks": 2, "matched_terminal_tasks": 2}, "source_sha256": "a" * 64}
        lost = {**good, "metrics": {"tasks": 0, "started_tasks": 0, "matched_terminal_tasks": 0}, "source_sha256": "b" * 64}
        with mock.patch.object(dashboard, "project_snapshot", side_effect=[good, lost]):
            collector(entry, lambda *_: {})
            result = collector(entry, lambda *_: {})
        self.assertFalse(result["available"])
        self.assertTrue(result["stale"])
        self.assertEqual(result["metrics"]["tasks"], 2)
        self.assertRegex(result["error"], "shrank|loss")

    def test_real_project_reader_observes_terminal_then_holds_stale_data_on_denial(self):
        state = self.repo / ".007"
        (state / "tasks").mkdir(parents=True)
        (state / "receipts").mkdir()
        cli = importlib.import_module("framework_cli")
        (state / "project.json").write_text(json.dumps({"schema": cli.PROJECT_SCHEMA,
            "project_id": "project", "name": "Fixture", "receipt_dir": "receipts"}))
        clock = [datetime.now(timezone.utc) - timedelta(seconds=10)]
        start = {**self.start, "schema": cli.TASK_START_SCHEMA, "project_id": "project",
                 "started_at": clock[0].isoformat()}
        (state / "tasks/task.task.json").write_text(json.dumps(start))
        entry = {"project_id": "project", "path": str(self.repo), "name": "Fixture", "registered_at": "fixture"}
        collector = dashboard.ProjectCollector(self.collector(), now=lambda: clock[0])
        touch = lambda _, days: dashboard.unknown_touch(days, "fixture")
        initial = collector(entry, touch)
        self.assertEqual(initial["metrics"]["active_tasks"], 1)
        self.assertEqual(initial["metrics"]["tasks"], 0)
        self.assertEqual(initial["dataset"]["counts"]["inputs-retained"], 1)
        clock[0] += timedelta(seconds=2)
        self.finalize(completed_at=clock[0].isoformat())
        (state / "receipts/task.receipt.json").write_bytes((self.repo / "terminal.json").read_bytes())
        terminal = collector(entry, touch)
        clock[0] += timedelta(seconds=2)
        unchanged = collector(entry, touch)
        self.assertEqual(terminal["metrics"]["tasks"], 1)
        self.assertEqual(terminal["metrics"]["active_tasks"], 0)
        self.assertTrue(terminal["recent_tasks"][0]["matched_start"])
        self.assertEqual(terminal["dataset"]["counts"]["case-retained"], 1)
        self.assertEqual(terminal["dataset"]["counts"]["qualified-comparison"], 0)
        self.assertNotEqual(initial["ingested_at"], terminal["ingested_at"])
        self.assertEqual(terminal["ingested_at"], unchanged["ingested_at"])
        clock[0] += timedelta(seconds=2)
        with mock.patch.object(cli, "read_json", side_effect=PermissionError("fixture denial")):
            stale = collector(entry, touch)
        self.assertTrue(stale["stale"])
        self.assertEqual(stale["metrics"]["tasks"], 1)
        self.assertEqual(stale["dataset"]["counts"]["case-retained"], 1)
        self.assertEqual(stale["objective"]["status"], "not-measurable")
        self.assertEqual(stale["ingested_at"], terminal["ingested_at"])


class TemporalProjectionTests(TestCase):
    def test_events_are_unique_known_declarations_in_the_frozen_utc_window(self):
        self.assertTrue(hasattr(dashboard, "event_trend"), "event timeline is missing")
        starts = [{"task_id": "one", "started_at": "2026-10-12T23:59:00-03:00"},
                  {"task_id": "duplicate", "started_at": "2026-10-13T00:00:00Z"}]
        starts.append(dict(starts[-1]))
        receipts = [{"task_id": "one", "completed_at": "2026-10-13T03:00:00Z"},
                    {"task_id": "future", "completed_at": "2026-10-14T00:00:00Z"},
                    {"task_id": "unknown", "completed_at": "2026-10-13T01:00:00"}]
        result = dashboard.event_trend(starts, receipts, as_of="2026-10-13T04:00:00Z")
        self.assertEqual(result, dashboard.event_trend(list(reversed(starts)), list(reversed(receipts)),
                                                      as_of="2026-10-13T04:00:00Z"))
        self.assertEqual(len(result["rows"]), 30)
        self.assertEqual(sum(row["started"] for row in result["rows"]), 1)
        self.assertEqual(sum(row["terminal"] for row in result["rows"]), 1)
        self.assertEqual(result["rows"][-1]["at"], "2026-10-13T00:00:00+00:00")
        self.assertEqual(result["excluded"], 4)
        self.assertFalse(result["complete"])
        self.assertEqual(result["scope"], "declared-events-utc-30d")

    def test_empty_event_series_is_known_empty_but_bad_cutoff_is_not_now(self):
        self.assertTrue(hasattr(dashboard, "event_trend"), "event timeline is missing")
        empty = dashboard.event_trend([], [], as_of="2026-10-13T04:00:00Z")
        self.assertTrue(empty["complete"])
        self.assertEqual(sum(row["started"] + row["terminal"] for row in empty["rows"]), 0)
        for cutoff in ("", "invalid", "2026-10-13T04:00:00"):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                dashboard.event_trend([], [], as_of=cutoff)

    def test_retention_history_is_baseline_plus_changes_not_a_poll_counter(self):
        clock = [datetime(2026, 10, 13, tzinfo=timezone.utc)]
        collector = dashboard.ProjectCollector(now=lambda: clock[0])
        entry = {"project_id": "project", "path": "fixture-only"}
        baseline = {"available": True, "metrics": {"tasks": 1}, "source_sha256": "a" * 64,
                    "dataset": {"complete": True, "counts": {key: 0 for key in dashboard.DATASET_STAGES}}}
        changed = copy.deepcopy(baseline)
        changed["dataset"]["counts"]["case-retained"] = 1
        unavailable = {"available": False, "metrics": {"tasks": 0}, "error": "denied"}
        with mock.patch.object(dashboard, "project_snapshot", side_effect=[copy.deepcopy(row) for row in (
                baseline, baseline, changed, unavailable, changed)]):
            first = collector(entry, lambda *_: {})
            clock[0] += timedelta(seconds=2)
            same = collector(entry, lambda *_: {})
            clock[0] += timedelta(seconds=2)
            new = collector(entry, lambda *_: {})
            clock[0] += timedelta(seconds=2)
            failed = collector(entry, lambda *_: {})
            clock[0] += timedelta(seconds=2)
            recovered = collector(entry, lambda *_: {})
        self.assertEqual(len(first.get("dataset_history", [])), 1)
        self.assertEqual(first["dataset_history"], same["dataset_history"])
        self.assertEqual(len(new["dataset_history"]), 2)
        self.assertEqual(new["dataset_history"][-1]["counts"]["case-retained"], 1)
        self.assertEqual(new["dataset_history"], failed["dataset_history"])
        self.assertEqual(new["dataset_history"], recovered["dataset_history"])
        self.assertEqual(len(first["dataset_history"]), 1)

    def test_unknown_retention_does_not_become_a_zero_stock(self):
        collector = dashboard.ProjectCollector()
        entry = {"project_id": "project", "path": "fixture-only"}
        with mock.patch.object(dashboard, "project_snapshot", return_value={
                "available": True, "metrics": {"tasks": 1}, "source_sha256": "a" * 64,
                "dataset": {"complete": False, "counts": {key: 0 for key in dashboard.DATASET_STAGES}}}):
            result = collector(entry, lambda *_: {})
        self.assertEqual(len(result.get("dataset_history", [])), 1)
        self.assertIsNone(result["dataset_history"][0]["counts"])
