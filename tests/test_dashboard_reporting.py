"""Reporting regressions: statements must not exceed observed evidence."""

import importlib
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone

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

    @unittest.skipUnless(shutil.which("node"), "Node required for dashboard renderer proof")
    def test_renderer_evidence_boundaries(self):
        result = subprocess.run(["node", "--test", str(ROOT / "tests/dashboard_reporting.test.cjs")],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
