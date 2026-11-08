"""Reporting regressions: statements must not exceed observed evidence."""

import importlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from datetime import datetime, timezone
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
dashboard = importlib.import_module("dashboard")


class ReportingTests(unittest.TestCase):
    def test_receipt_replay_reference_is_not_displayed_as_replay_ready(self):
        value = dashboard.safe_task({"task_id": "case", "status": "accepted",
                                    "replay_ref": {"manifest": "private/case/manifest.json", "sha256": "a" * 64},
                                    "cost_usd": 2, "cost_source": "rate-card-estimate", "cost_status": "provisional"})
        self.assertEqual(value.get("input_sha256"), "a" * 64)
        self.assertEqual(value.get("cost_basis"), "api-equivalent")
        self.assertNotIn("replay_ref", value)
        self.assertNotIn("private", str(value))
        self.assertIsNone(value.get("replay_ready"))

    def test_event_clock_does_not_advance_with_empty_dashboard_reads(self):
        receipts = [{"task_id": "case", "status": "accepted", "completed_at": "2026-10-12T12:00:00Z"}]
        starts = [{"task_id": "case", "started_at": "2026-10-12T11:00:00Z"},
                  {"task_id": "future", "started_at": "2030-01-01T00:00:00Z"}]
        for cutoff in (datetime(2026, 10, 12, 13, tzinfo=timezone.utc),
                       datetime(2026, 10, 12, 14, tzinfo=timezone.utc)):
            metrics = dashboard.metrics_from_observations(receipts, starts, as_of=cutoff)
            self.assertEqual(metrics.get("latest_event_at"), "2026-10-12T12:00:00+00:00")

    def test_shared_iso_cutoff_remains_supported_by_dashboard_clock(self):
        metrics = dashboard.metrics_from_observations(
            [{"task_id": "case", "completed_at": "2026-10-12T12:00:00Z"}], [],
            as_of="2026-10-12T13:00:00Z")
        self.assertEqual(metrics["latest_event_at"], "2026-10-12T12:00:00+00:00")

    def test_invalid_cutoff_is_not_replaced_with_current_time(self):
        for cutoff in ("", "invalid", "2026-10-12T13:00:00"):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                dashboard.metrics_from_observations([], [], as_of=cutoff)

    def test_unavailable_project_does_not_complete_the_aggregate_usd_cohort(self):
        metrics = dashboard.metrics_from_observations([], [])
        good = {"project_id": "good", "available": True, "metrics": metrics, "touch": {}}
        unavailable = {"project_id": "missing", "available": False, "metrics": {}, "touch": {}}
        aggregate = dashboard.aggregate_projects([good, unavailable])
        self.assertIsNone(aggregate["economics"])
        self.assertIsNone(dashboard.aggregate_projects([good], registry_error_count=1)["economics"])
        self.assertEqual(dashboard.aggregate_projects([good])["economics"], metrics["economics"])

    def test_bound_receipt_does_not_authenticate_producer(self):
        receipt = {"status": "accepted", "acceptance_evidence": "controlled",
                   "acceptance_summary": {"passed": 1, "failed": 0},
                   "acceptance_sha256": "a" * 64,
                   "authority_evidence": "controlled",
                   "authority_summary": {"bound": True, "events": 1,
                                         "allowed_executions": 1}}
        metrics = dashboard.metrics_from_observations([receipt], [])
        self.assertEqual(metrics["accepted"], 1)
        self.assertEqual(metrics["accepted_controller_observed"], 0)
        self.assertEqual(metrics["accepted_declared"], 1)
        self.assertEqual(metrics["authority_controlled_tasks"], 0)
        self.assertEqual(dashboard.authority_confidence(metrics)["label"], "declared")
        task = dashboard.safe_task(receipt)
        self.assertEqual(task["acceptance_evidence"], "declared")
        self.assertEqual(task["acceptance_summary"], {"passed": 1, "failed": 0})

    def test_legacy_authority_counts_do_not_authenticate_producer(self):
        confidence = dashboard.authority_confidence({
            "tasks": 2, "authority_bound_tasks": 2,
            "authority_controlled_tasks": 2, "authority_declared_tasks": 0})
        self.assertEqual(confidence["controlled"], 0)
        self.assertEqual(confidence["declared"], 2)
        self.assertEqual(confidence["label"], "declared")

    def test_aggregate_legacy_project_does_not_authenticate_producer(self):
        old = dashboard.metrics_from_receipts([{"status": "accepted"}])
        old.update(accepted_controller_observed=1, accepted_declared=0,
                   authority_bound_tasks=1, authority_controlled_tasks=1,
                   authority_declared_tasks=0)
        aggregate = dashboard.aggregate_projects([
            {"available": True, "metrics": old, "touch": {}}])
        self.assertEqual(aggregate["accepted_controller_observed"], 0)
        self.assertEqual(aggregate["accepted_declared"], 1)
        self.assertEqual(aggregate["authority_controlled_tasks"], 0)
        self.assertEqual(aggregate["authority_declared_tasks"], 1)

    def test_empty_or_failed_checks_do_not_become_observed_acceptance(self):
        common = {"status": "accepted", "acceptance_evidence": "controlled",
                  "acceptance_sha256": "a" * 64}
        for summary in ({"passed": 0, "failed": 0}, {"passed": 1, "failed": 1}):
            receipt = {**common, "acceptance_summary": summary}
            self.assertNotIn("acceptance_evidence", dashboard.safe_task(receipt))
            metrics = dashboard.metrics_from_observations([receipt], [])
            self.assertEqual(metrics["accepted_controller_observed"], 0)
            self.assertEqual(metrics["accepted_declared"], 1)
        blocked = {**common, "status": "blocked",
                   "acceptance_summary": {"passed": 0, "failed": 1}}
        self.assertEqual(dashboard.safe_task(blocked)["acceptance_summary"],
                         {"passed": 0, "failed": 1})

    def test_route_cost_provenance_survives_mixed_project_aggregation(self):
        common = {"status": "accepted", "first_pass": "yes", "escape_7d": "no"}
        first = dashboard.metrics_from_observations([
            {**common, "model": "estimate", "cost_usd": 0.4,
             "cost_source": "rate-card-estimate", "cost_status": "provisional"},
            {**common, "model": "billed", "cost_usd": 0.6,
             "cost_source": "provider-reported", "cost_status": "final"},
        ], [])
        by_model = {route["model"]: route for route in first["routes"]}
        self.assertEqual(by_model["estimate"].get("cost_sources"), {"rate-card-estimate": 1})
        self.assertEqual(by_model["estimate"].get("cost_accounting_status"), "provisional")
        self.assertEqual(by_model["billed"].get("cost_accounting_status"), "final")
        second = dashboard.metrics_from_observations([
            {**common, "model": "estimate", "cost_usd": 0.2,
             "cost_source": "provider-reported", "cost_status": "final"},
        ], [])
        aggregate = dashboard.aggregate_projects([
            {"available": True, "metrics": first, "touch": {}},
            {"available": True, "metrics": second, "touch": {}},
        ])
        routes = {route["model"]: route for route in aggregate["routes"]}
        self.assertEqual(routes["estimate"].get("cost_sources"),
                         {"rate-card-estimate": 1, "provider-reported": 1})
        self.assertEqual(routes["estimate"].get("cost_accounting_status"), "provisional")
        self.assertEqual(routes["billed"].get("cost_sources"), {"provider-reported": 1})
        self.assertEqual(routes["billed"].get("cost_accounting_status"), "final")

    def test_legacy_quality_tags_do_not_mature_route_economics(self):
        receipts = [
            {"status": "accepted", "first_pass": "yes", "escape_7d": "no", "model": "example"},
            {"status": "blocked", "first_pass": "no", "escape_7d": "no", "model": "example"},
        ]
        metrics = dashboard.metrics_from_observations(receipts, [])
        self.assertEqual(metrics["reliable_first_pass_rate"], 1.0)
        self.assertEqual(metrics["routes"][0]["reliable_rate"], 0.0)
        self.assertEqual(metrics["routes"][0]["reliable_known"], 1)
        self.assertIsNone(metrics["routes"][0]["cost_usd_per_reliable"])
        self.assertFalse(metrics["routes"][0]["economics"]["cohort_complete"])

    def test_acceptance_is_not_inferred_from_authority_or_executor_exit(self):
        receipts = [
            {"status": "accepted", "authority_evidence": "controlled"},
            {"status": "accepted", "acceptance_evidence": "controlled",
             "acceptance_summary": {"passed": 1, "failed": 0}, "acceptance_sha256": "a" * 64},
            {"status": "blocked", "acceptance_evidence": "controlled"},
        ]
        metrics = dashboard.metrics_from_observations(receipts, [])
        self.assertEqual(metrics["accepted_controller_observed"], 0)
        self.assertEqual(metrics["accepted_declared"], 2)
        task = dashboard.safe_task(receipts[1])
        self.assertEqual(task["acceptance_evidence"], "declared")
        private = {**receipts[1], "acceptance_summary": {"passed": 1, "failed": 0, "raw_output": "private"}}
        self.assertEqual(dashboard.safe_task(private)["acceptance_summary"], {"passed": 1, "failed": 0})

    def test_cost_sources_survive_project_aggregation(self):
        metrics = dashboard.metrics_from_observations([
            {"status": "accepted", "cost_usd": 0.4, "cost_source": "rate-card-estimate", "cost_status": "provisional"},
            {"status": "blocked", "cost_usd": 0.6, "cost_source": "provider-reported", "cost_status": "final"},
        ], [{"task_id": "open"}])
        aggregate = dashboard.aggregate_projects([{"available": True, "metrics": metrics, "touch": {}}])
        self.assertEqual(aggregate["cost_sources"], {"rate-card-estimate": 1, "provider-reported": 1})
        self.assertEqual(aggregate["active_tasks"], 1)
        self.assertEqual(aggregate["cost_coverage"], 1.0)
        self.assertEqual(aggregate["cost_accounting_status"], "provisional")

    def test_lab_ledger_sums_007_receipts_per_experiment_and_never_crashes_on_a_bad_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.json"
            self.assertEqual(dashboard.load_lab_ledger(config)["configured"], False)  # no config file: nothing configured
            first, second = root / "results", root / "next-results"
            first.mkdir(), second.mkdir()
            write = lambda path, value: path.write_text(value if isinstance(value, str) else json.dumps(value))
            write(first / "t1-r01-low.json", {"valid": True})
            write(first / "t1-r01-low.runner.json", {"cost_usd": 1.25, "cost_source": "client-estimate", "valid": True})
            write(first / "t1-r01-high.json", {"valid": False})
            write(first / "t1-r01-high.runner.json", {"cost_usd": 0.5, "cost_source": "client-estimate", "valid": False})
            write(first / "t2-r01-low.runner.json", "")  # orphan: reserved, never finished
            write(first / "t2-r01-high.json", {"valid": False, "runner_receipt_sha256": "unmeasured"})  # refused before spending
            write(first / "dispatch.jsonl", '{"cell":"t1-r01-low","dispatched_at":"2026-11-01T10:00:00+00:00"}\n'
                  '{"cell":"t1-r01-high","finished_at":"2026-11-02T09:00:00Z"}\n{"cut')
            write(second / "t1-next-r01-low.json", {"valid": True})
            write(second / "t1-next-r01-low.runner.json", {"cost_usd": 2, "cost_source": "rate-card-estimate"})
            write(first / "report.json", {"valid": True})  # not a cell
            write(config, {"observatory": {"lab_ledger": [
                {"name": "chain", "results": ["results", str(second)]},
                {"name": "gone", "results": "missing"},
                {"name": "broken"}]}})
            ledger = dashboard.load_lab_ledger(config)
        chain, gone, broken = ledger["experiments"]
        self.assertTrue(ledger["configured"])
        self.assertEqual({key: chain[key] for key in ("attempts", "valid", "invalid", "orphans", "unpriced")},
                         {"attempts": 5, "valid": 2, "invalid": 2, "orphans": 1, "unpriced": 1})
        self.assertEqual((chain["cost_usd"], chain["invalid_cost_usd"]), (3.75, 0.5))
        self.assertEqual(chain["cost_sources"], {"client-estimate": 2, "rate-card-estimate": 1})
        self.assertEqual((chain["first_attempt_at"], chain["last_attempt_at"]),
                         ("2026-11-01T10:00:00+00:00", "2026-11-02T09:00:00+00:00"))
        self.assertEqual((gone["available"], gone["error"]), (False, "results directory unavailable"))
        self.assertFalse(broken["available"])
        self.assertEqual(ledger["total_cost_usd"], 3.75)
        self.assertFalse(ledger["total_complete"])  # an orphan and two unavailable experiments: the total is a lower bound

    def test_lab_ledger_does_not_price_a_missing_receipt_or_unattributed_amount_as_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "missing-r01-low.json").write_text(json.dumps({"valid": True}))
            (root / "amount-r01-low.json").write_text(json.dumps({"valid": False}))
            (root / "amount-r01-low.runner.json").write_text(json.dumps({"cost_usd": 7}))
            config = root / "config.json"
            config.write_text(json.dumps({"observatory": {"lab_ledger": [{"name": "fixture", "results": "."}]}}))
            ledger = dashboard.load_lab_ledger(config)
            self.assertEqual(ledger["experiments"][0]["unpriced"], 2)
            self.assertFalse(ledger["total_complete"])
            self.assertEqual(ledger["total_cost_usd"], 0)  # known subtotal, not a measured zero for these attempts

    def test_lab_report_carries_the_repository_cli_and_model_it_is_bound_to(self):
        # audit F09: a bare report path has no repository identity, so its verdict must not read as evidence for any repository
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, config = root / "report.json", root / "config.json"
            report.write_text(json.dumps({"schema": "007-lab/report/v6", "verdict": {"same_change_reachable": "PROVEN", "durability": "PROVEN"}}))
            binding = {"project_id": "repository-a", "cli": "codex", "model": "m", "effort": "medium", "against": "high"}
            for value, bound in ((str(report), None), ({"path": str(report), **binding}, binding),
                                 ({"path": str(report), "project_id": "repository-a"}, None),
                                 ({"path": str(report), "project_id": "repository-a", "cli": "codex", "model": "m"}, None)):
                with self.subTest(value=value):
                    config.write_text(json.dumps({"observatory": {"lab_report": value}}))
                    loaded = dashboard.load_lab_report(config)
                    self.assertEqual(loaded["same_change_reachable"], "PROVEN")
                    self.assertEqual(loaded["bound_to"], bound)

    def test_failed_rebuild_marks_the_preserved_evidence_stale_with_its_own_read_time(self):
        # audit F10: after a failed rebuild the old evidence must not read as current while the response clock advances
        objective = {"status": "on-target", "headline": "OPERATIONAL TARGETS MET", "gates": [{"key": "economics", "status": "pass"}]}
        good = {"generated_at": "2026-11-08T10:00:00Z", "aggregate": {"activity": {}, "objective": objective},
                "projects": [{"project_id": "p", "activity": {}, "available": True, "stale": False, "objective": objective}]}
        builds = [good, OSError("fixture acquisition failed"), {**good, "generated_at": "2026-11-08T10:05:00Z"}]
        with mock.patch.object(dashboard.threading.Thread, "start"):
            live = dashboard.LiveSnapshot(mock.Mock(side_effect=builds), lambda: [], lambda _: {"aggregate": {}, "projects": {}}, pause_s=0)
        run = lambda steps: mock.patch.object(dashboard.time, "sleep", side_effect=[None] * (steps - 1) + [StopIteration])
        with run(2), redirect_stderr(io.StringIO()), self.assertRaises(StopIteration):
            live.loop()
        read = live.read()
        self.assertEqual(read["evidence_read_at"], "2026-11-08T10:00:00Z")
        self.assertNotEqual(read["generated_at"], read["evidence_read_at"])
        self.assertIn("fixture acquisition failed", read["rebuild_error"])
        self.assertTrue(read["aggregate"]["stale"])
        self.assertEqual((read["projects"][0]["stale"], read["projects"][0]["available"]), (True, False))
        for scope in (read["aggregate"], read["projects"][0]):
            self.assertEqual((scope["objective"]["status"], scope["objective"]["gates"][0]["status"]), ("not-measurable", "wait"))
        with run(1), redirect_stderr(io.StringIO()), self.assertRaises(StopIteration):
            live.loop()
        read = live.read()
        self.assertEqual((read["evidence_read_at"], read["rebuild_error"]), ("2026-11-08T10:05:00Z", None))
        self.assertFalse(read["aggregate"].get("stale", False))
        self.assertEqual((read["projects"][0]["stale"], read["projects"][0]["available"]), (False, True))
        self.assertEqual(read["aggregate"]["objective"]["status"], "on-target")

    @unittest.skipUnless(shutil.which("node"), "Node required for dashboard renderer proof")
    def test_renderer_evidence_boundaries(self):
        result = subprocess.run(["node", "--test", str(ROOT / "tests/dashboard_reporting.test.cjs")],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
