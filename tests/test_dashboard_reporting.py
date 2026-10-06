"""Reporting regressions: statements must not exceed observed evidence."""

import importlib
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
dashboard = importlib.import_module("dashboard")


class ReportingTests(unittest.TestCase):
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

    def test_route_and_aggregate_use_accepted_followup_denominator(self):
        receipts = [
            {"status": "accepted", "first_pass": "yes", "escape_7d": "no", "model": "example"},
            {"status": "blocked", "first_pass": "no", "escape_7d": "no", "model": "example"},
        ]
        metrics = dashboard.metrics_from_observations(receipts, [])
        self.assertEqual(metrics["reliable_first_pass_rate"], 1.0)
        self.assertEqual(metrics["routes"][0]["reliable_rate"], 1.0)
        self.assertEqual(metrics["routes"][0]["reliable_known"], 1)

    def test_acceptance_is_not_inferred_from_authority_or_executor_exit(self):
        receipts = [
            {"status": "accepted", "authority_evidence": "controlled"},
            {"status": "accepted", "acceptance_evidence": "controlled",
             "acceptance_summary": {"passed": 1, "failed": 0}, "acceptance_sha256": "a" * 64},
            {"status": "blocked", "acceptance_evidence": "controlled"},
        ]
        metrics = dashboard.metrics_from_observations(receipts, [])
        self.assertEqual(metrics["accepted_controller_observed"], 1)
        self.assertEqual(metrics["accepted_declared"], 1)
        task = dashboard.safe_task(receipts[1])
        self.assertEqual(task["acceptance_evidence"], "controlled")
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
