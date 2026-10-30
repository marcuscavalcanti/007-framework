"""Literal cohort arithmetic; supplied records never authenticate their author."""

from datetime import datetime, timezone
import importlib
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
report = importlib.import_module("harness_report")
AS_OF = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


def receipt(task, cost=2, status="accepted", **extra):
    return {"task_id": task, "project_id": "project", "status": status,
            "first_pass": "yes" if status == "accepted" else "no",
            "completed_at": "2026-10-01T12:00:00Z", "candidate_sha256": "a" * 64,
            "cost_usd": cost, "cost_source": "rate-card-estimate",
            "cost_status": "provisional", "cost_basis": "api-equivalent", **extra}


def start(task, **extra):
    return {"task_id": task, "project_id": "project",
            "started_at": "2026-10-01T11:00:00Z", **extra}


def followup(task, **extra):
    return {"task_id": task, "project_id": "project", "candidate_sha256": "a" * 64,
            "source_sha256": "b" * 64, "used_at": "2026-10-01T12:00:00Z",
            "observed_from": "2026-10-01T12:00:00Z",
            "observed_through": "2026-10-09T12:00:00Z", "escape_7d": "no", **extra}


class EconomicsTests(unittest.TestCase):
    def summarize(self, rows, starts, followups=(), basis=None):
        self.assertTrue(hasattr(report, "summarize_economics"),
                        "shared cohort accounting is not implemented")
        return report.summarize_economics(rows, starts=starts, followups=list(followups),
                                         cost_basis=basis, as_of=AS_OF)

    def test_failed_attempt_cost_is_in_numerator(self):
        result = self.summarize([receipt("failed", 8, "blocked"), receipt("accepted", 2)],
                                [start("failed"), start("accepted")])
        self.assertEqual(result["cost_usd_known_sum"], 10)
        self.assertEqual(result["accepted_declared"], 1)
        self.assertEqual(result["cost_usd_per_declared_accepted"], 10)
        self.assertEqual(result["cost_basis"], "api-equivalent")
        self.assertEqual(result["evidence_scope"], "supplied-declarations")

    def test_amount_only_does_not_qualify_full_cost_scope(self):
        result = self.summarize([receipt("failed", 8, "blocked"), receipt("accepted", 2)],
                                [start("failed"), start("accepted")])
        self.assertEqual(result["cost_usd_known_sum"], 10)
        self.assertEqual(result["cost_usd_per_declared_accepted"], 10)
        self.assertFalse(result["cost_scope_complete"])
        self.assertIsNone(result["cost_usd_per_declared_accepted_with_overhead"])

    def test_disjoint_components_reconcile_without_double_counting(self):
        components = {"executor": 2, "review": 1, "retries": 1,
                      "verification": 0.5, "infrastructure": 0.25, "preparation": 0.25}
        row = receipt("accepted", 5, cost_components_usd=components)
        result = self.summarize([row], [start("accepted")], [followup("accepted")])
        self.assertEqual(result["cost_usd_known_sum"], 5)
        self.assertTrue(result["cost_scope_complete"])
        self.assertEqual(result["cost_usd_per_declared_accepted_with_overhead"], 5)
        self.assertEqual(result["cost_usd_per_reliable_with_overhead_declared"], 5)
        self.assertEqual(result["cost_component_known_tasks"], {
            "executor": 1, "review": 1, "retries": 1, "verification": 1,
            "infrastructure": 1, "preparation": 1})

    def test_partial_or_mismatched_scope_keeps_full_cost_unknown(self):
        complete = {"executor": 2, "review": 0, "retries": 0,
                    "verification": 0, "infrastructure": 0, "preparation": 0}
        for components in ({"executor": 2}, {**complete, "review": None},
                           {**complete, "review": 1}):
            with self.subTest(components=components):
                result = self.summarize([receipt("a", cost_components_usd=components)], [start("a")])
                self.assertFalse(result["cost_scope_complete"])
                self.assertEqual(result["cost_usd_known_sum"], 2)
                self.assertIsNone(result["cost_usd_per_declared_accepted_with_overhead"])

    def test_invalid_cost_component_is_not_silently_ignored(self):
        for components in (True, [], {"unknown": 2}, {"review": True},
                           {"executor": -1}, {"review": float("nan")},
                           {"executor": float("inf")}, {"executor": "2"}):
            with self.subTest(components=components), self.assertRaises(ValueError):
                self.summarize([receipt("a", cost_components_usd=components)], [start("a")])

    def test_overflow_or_invalid_included_child_components_are_rejected(self):
        with self.assertRaises(ValueError):
            self.summarize([receipt("a", 1e308, cost_components_usd={
                "executor": 1e308, "review": 1e308, "retries": 0,
                "verification": 0, "infrastructure": 0, "preparation": 0})], [start("a")])
        with self.assertRaises(ValueError):
            self.summarize([receipt("parent", 10, cost_includes_children=True),
                            receipt("child", 3, parent_task_id="parent", cost_components_usd=True)],
                           [start("parent"), start("child")])

    def test_receipt_writer_rejects_bad_component_before_persistence(self):
        cli = importlib.import_module("framework_cli")
        with self.assertRaisesRegex(ValueError, "component"):
            cli.validate_receipt({"schema": cli.RECEIPT_SCHEMA, **receipt("a", cost_components_usd=True)})

    def test_selector_does_not_rank_amount_only_as_cheapest(self):
        cli = importlib.import_module("framework_cli")
        candidates, rows, starts, events = self.route_fixture()
        result = cli.select_route(candidates, rows, "implement", which=lambda _: "fixture",
                                  starts=starts, followups=events, as_of=AS_OF)
        self.assertNotEqual(result["strategy"], "measured")
        self.assertIn("overhead cost scope incomplete", result["rejected"]["b"])

    def test_dashboard_does_not_approve_amount_only_economics(self):
        dashboard = importlib.import_module("dashboard")
        _, rows, starts, events = self.route_fixture()
        metrics = dashboard.metrics_from_observations(rows, starts, followups=events, as_of=AS_OF)
        metrics["telemetry_completeness"] = 1
        self.assertNotEqual(dashboard.objective_state(metrics, {"30": {"rate": 0}})["status"], "on-target")

    def test_missing_cost_keeps_ratio_unknown(self):
        result = self.summarize([receipt("a"), receipt("b", None, "blocked")],
                                [start("a"), start("b")])
        self.assertEqual(result["cost_usd_known_sum"], 2)
        self.assertEqual(result["cost_coverage"], 0.5)
        self.assertIsNone(result["cost_usd_per_declared_accepted"])

    def test_empty_or_zero_accepted_outcomes_have_no_ratio(self):
        for rows, starts in (([], []), ([receipt("a", 8, "blocked")], [start("a")])):
            result = self.summarize(rows, starts)
            self.assertEqual(result["accepted_declared"], 0)
            self.assertIsNone(result["cost_usd_per_declared_accepted"])
            self.assertIsNone(result["cost_usd_per_reliable_declared"])

    def test_invalid_money_is_rejected(self):
        for value in (True, -1, float("nan"), float("inf"), "2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.summarize([receipt("a", value)], [start("a")])

    def test_mixed_bases_remain_separate(self):
        rows = [receipt("a", 2), receipt("b", 3, cost_basis="billed", cost_source="provider-reported")]
        result = self.summarize(rows, [start("a"), start("b")])
        self.assertEqual(result["cost_usd_by_basis"], {"api-equivalent": 2, "billed": 3})
        self.assertIsNone(result["cost_basis"])
        self.assertIsNone(result["cost_usd_known_sum"])
        self.assertIsNone(result["cost_usd_per_declared_accepted"])
        one = self.summarize(rows, [start("a"), start("b")], basis="api-equivalent")
        self.assertEqual(one["cost_coverage"], 0.5)
        self.assertIsNone(one["cost_usd_per_declared_accepted"])

    def test_ambiguous_reported_usd_is_not_assumed_billed(self):
        row = receipt("a", 2, cost_source="provider-reported")
        row.pop("cost_basis")
        result = self.summarize([row], [start("a")])
        self.assertEqual(result["cost_coverage"], 0)
        self.assertIsNone(result["cost_usd_per_declared_accepted"])

    def test_open_or_unbound_tasks_block_comparable_ratio(self):
        for starts in ([start("a"), start("open")], []):
            result = self.summarize([receipt("a")], starts)
            self.assertFalse(result["cohort_complete"])
            self.assertIsNone(result["cost_usd_per_declared_accepted"])

    def test_duplicate_or_mixed_project_identity_blocks_cohort(self):
        rows = [receipt("a"), receipt("a")]
        result = self.summarize(rows, [start("a")])
        self.assertFalse(result["cohort_complete"])
        self.assertIsNone(result["cost_usd_per_declared_accepted"])
        result = self.summarize([receipt("a", project_id="wrong")], [start("a")])
        self.assertFalse(result["cohort_complete"])
        self.assertIsNone(result["cost_usd_per_declared_accepted"])

    def test_future_terminal_remains_open_at_cutoff(self):
        row = receipt("a", completed_at="2026-10-13T12:00:00Z")
        result = self.summarize([row], [start("a")])
        self.assertEqual(result["accepted_declared"], 0)
        self.assertEqual(result["open_tasks"], 1)
        self.assertIsNone(result["cost_usd_per_reliable_declared"])

    def test_age_without_followup_is_not_reliable(self):
        result = self.summarize([receipt("a", escape_7d="no", acceptance_evidence="controlled")],
                                [start("a")])
        self.assertEqual(result["reliable_declared"], 0)
        self.assertIsNone(result["cost_usd_per_reliable_declared"])

    def test_linked_followup_enables_only_declared_survival(self):
        result = self.summarize([receipt("a")], [start("a")], [followup("a")])
        self.assertEqual(result["reliable_declared"], 1)
        self.assertEqual(result["cost_usd_per_reliable_declared"], 2)
        self.assertEqual(result["evidence_scope"], "supplied-declarations")

    def test_short_future_unused_or_wrong_candidate_followup_does_not_mature(self):
        invalid = [followup("a", observed_through="2026-10-03T12:00:00Z"),
                   followup("a", observed_through="2026-10-13T12:00:00Z"),
                   followup("a", used_at=None), followup("a", candidate_sha256="c" * 64)]
        for event in invalid:
            with self.subTest(event=event):
                result = self.summarize([receipt("a")], [start("a")], [event])
                self.assertEqual(result["reliable_declared"], 0)

    def test_parent_inclusive_total_is_counted_once(self):
        rows = [receipt("parent", 10, cost_includes_children=True),
                receipt("child", 3, parent_task_id="parent")]
        result = self.summarize(rows, [start("parent"), start("child")])
        self.assertEqual(result["cost_usd_known_sum"], 10)
        self.assertEqual(result["accepted_declared"], 1)
        self.assertEqual(result["cost_usd_per_declared_accepted"], 10)

    def test_unknown_parent_cost_scope_blocks_ratio(self):
        rows = [receipt("parent", 10), receipt("child", 3, parent_task_id="parent")]
        result = self.summarize(rows, [start("parent"), start("child")])
        self.assertFalse(result["cohort_complete"])
        self.assertIsNone(result["cost_usd_per_declared_accepted"])

    def test_receipt_order_does_not_change_summary(self):
        rows = [receipt("a", 0.1), receipt("b", 0.2), receipt("c", 0.3, "blocked")]
        expected = self.summarize(rows, [start("a"), start("b"), start("c")])
        self.assertEqual(expected["cost_usd_known_sum"], 0.6)
        self.assertEqual(expected["cost_usd_per_declared_accepted"], 0.3)
        for order in itertools.permutations(rows):
            self.assertEqual(self.summarize(list(order), [start("a"), start("b"), start("c")]),
                             expected)

    def test_numeric_false_is_not_a_followup_verdict(self):
        result = self.summarize([receipt("a")], [start("a")], [followup("a", escape_7d=0)])
        self.assertEqual(result["reliable_declared"], 0)

    def test_inconsistent_first_pass_and_repairs_block_ratio(self):
        result = self.summarize([receipt("a", repair_rounds=2)], [start("a")], [followup("a")])
        self.assertFalse(result["cohort_complete"])
        self.assertIsNone(result["cost_usd_per_reliable_declared"])

    def test_huge_cost_and_malformed_id_are_rejected_as_value_errors(self):
        for row in (receipt("a", 10 ** 400), receipt("a", project_id=[]),
                    receipt("a", parent_task_id=[])):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.summarize([row], [start("a")])

    def test_report_dashboard_and_route_share_cohort_arithmetic(self):
        cli = importlib.import_module("framework_cli")
        dashboard = importlib.import_module("dashboard")
        rows = [receipt("failed", 8, "blocked"), receipt("accepted", 2)]
        for row in rows:
            row.update(task_class="implement", served_provider="fixture", served_model="model",
                       served_effort="medium", repair_rounds=0, wall_s=1)
        starts = [start("failed"), start("accepted")]
        events = [followup("accepted")]
        summary = report.summarize(rows, [], starts=starts, followups=events, as_of=AS_OF)
        snapshot = dashboard.metrics_from_observations(rows, starts, followups=events, as_of=AS_OF)
        route = cli.route_performance({"provider": "fixture", "model": "model", "effort": "medium"},
                                     rows, "implement", starts=starts, followups=events, as_of=AS_OF)
        expected = self.summarize(rows, starts, events)
        self.assertEqual(summary["economics"], expected)
        self.assertEqual(snapshot["economics"], expected)
        self.assertEqual(route["economics"], expected)
        self.assertEqual(route["cost_usd_per_reliable"], 10)
        self.assertEqual(summary["cost_usd_per_accepted"], 2)
        self.assertEqual(summary["legacy_cost_metric_scope"], "accepted-only-mean")

    def test_open_unknown_route_cannot_make_other_route_look_cheaper(self):
        cli = importlib.import_module("framework_cli")
        row = receipt("closed", served_provider="fixture", served_model="model",
                      served_effort="medium", task_class="implement", wall_s=1, repair_rounds=0)
        result = cli.route_performance({"provider": "fixture", "model": "model", "effort": "medium"},
            [row], "implement", starts=[start("closed"), start("open")],
            followups=[followup("closed")], as_of=AS_OF)
        self.assertIsNone(result["cost_usd_per_reliable"])
        self.assertEqual(result["economics"]["open_tasks"], 1)

    def test_aggregate_cannot_recreate_unqualified_survival_cost(self):
        dashboard = importlib.import_module("dashboard")
        row = receipt("a", escape_7d="no")
        metrics = dashboard.metrics_from_observations([row], [start("a")], as_of=AS_OF)
        result = dashboard.aggregate_projects([{"project_id": "project", "available": True,
                                               "metrics": metrics, "touch": {}}])
        self.assertIsNone(result["cost_usd_per_reliable"])
        self.assertEqual(result["economics"], metrics["economics"])

    def test_dashboard_route_uses_shared_followup_and_all_attempt_cost(self):
        dashboard = importlib.import_module("dashboard")
        rows = [receipt("failed", 8, "blocked"), receipt("accepted", 2)]
        for row in rows:
            row.update(task_class="implement", served_provider="fixture", served_model="model",
                       served_effort="medium", wall_s=1)
        route = dashboard.route_metrics(rows, starts=[start("failed"), start("accepted")],
                                        followups=[followup("accepted")], as_of=AS_OF)[0]
        self.assertEqual(route["cost_usd_per_reliable"], 10)
        self.assertEqual(route["economics"], self.summarize(
            rows, [start("failed"), start("accepted")], [followup("accepted")]))
        without = dashboard.route_metrics(rows, starts=[start("failed"), start("accepted")],
                                          followups=[], as_of=AS_OF)[0]
        self.assertIsNone(without["cost_usd_per_reliable"])

    def test_unknown_terminal_route_scope_cannot_be_dropped_for_price(self):
        cli = importlib.import_module("framework_cli")
        rows = [receipt("closed", task_class="implement", served_provider="fixture",
                        served_model="model", served_effort="medium", wall_s=1, repair_rounds=0,
                        cost_components_usd={"executor": 2, "review": 0, "retries": 0,
                            "verification": 0, "infrastructure": 0, "preparation": 0}),
                receipt("unknown", 8, "blocked", task_class="implement")]
        control = self.summarize(rows[:1], [start("closed")], [followup("closed")])
        self.assertTrue(control["cost_scope_complete"])
        self.assertEqual(control["cost_usd_per_reliable_with_overhead_declared"], 2)
        result = cli.route_performance({"provider": "fixture", "model": "model", "effort": "medium"},
            rows, "implement", starts=[start("closed"), start("unknown")],
            followups=[followup("closed")], as_of=AS_OF)
        self.assertIsNone(result["cost_usd_per_reliable"])
        self.assertIn("terminal route scope unavailable", result["economics"]["reasons"])
        dashboard = importlib.import_module("dashboard")
        known = next(r for r in dashboard.route_metrics(rows, starts=[start("closed"), start("unknown")],
            followups=[followup("closed")], as_of=AS_OF) if r["model"] == "model")
        for economics in (result["economics"], known["economics"]):
            self.assertFalse(economics["cost_scope_complete"])
            self.assertIsNone(economics["cost_usd_per_declared_accepted_with_overhead"])
            self.assertIsNone(economics["cost_usd_per_reliable_with_overhead_declared"])

    def test_legacy_green_metrics_cannot_claim_complete_economics(self):
        dashboard = importlib.import_module("dashboard")
        metrics = {"tasks": 5, "started_tasks": 5, "reliable_first_pass_known": 5,
                   "reliable_first_pass_rate": 1, "repair_rounds_mean": 0,
                   "escape_7d_rate": 0, "cost_coverage": 1, "telemetry_completeness": 1}
        result = dashboard.objective_state(metrics, {"30": {"rate": 0}})
        self.assertNotEqual(result["status"], "on-target")

    def test_inclusive_parent_cannot_understate_child_cost(self):
        rows = [receipt("parent", 2, cost_includes_children=True),
                receipt("child", 3, parent_task_id="parent")]
        result = self.summarize(rows, [start("parent"), start("child")])
        self.assertFalse(result["cohort_complete"])
        self.assertIsNone(result["cost_usd_per_declared_accepted"])

    def test_parent_decimal_positive_control(self):
        rows = [receipt("parent", 0.3, cost_includes_children=True),
                receipt("a", 0.1, parent_task_id="parent"), receipt("b", 0.2, parent_task_id="parent")]
        result = self.summarize(rows, [start(r["task_id"]) for r in rows])
        self.assertTrue(result["cohort_complete"])
        self.assertEqual(result["cost_usd_known_sum"], 0.3)

    def test_duplicate_parent_order_cannot_change_diagnosis(self):
        rows = [receipt("parent", 10, cost_includes_children=True), receipt("parent", 10),
                receipt("child", 3, parent_task_id="parent")]
        expected = self.summarize(rows, [start("parent"), start("child")])
        for order in itertools.permutations(rows):
            self.assertEqual(self.summarize(list(order), [start("parent"), start("child")]), expected)

    def test_terminal_and_followup_cannot_precede_start(self):
        result = self.summarize([receipt("a")], [start("a", started_at="2026-10-10T12:00:00Z")], [followup("a")])
        self.assertFalse(result["cohort_complete"])
        self.assertIsNone(result["cost_usd_per_reliable_declared"])

    def test_report_acquisition_error_blocks_ratio_not_known_cost(self):
        result = report.summarize([receipt("a")], [{"error": "invalid JSON"}],
                                  starts=[start("a")], followups=[followup("a")], as_of=AS_OF)["economics"]
        self.assertFalse(result["cohort_complete"])
        self.assertEqual(result["cost_usd_known_sum"], 2)
        self.assertIsNone(result["cost_usd_per_reliable_declared"])

    def test_dashboard_uses_linked_escapes_not_legacy_tags(self):
        dashboard = importlib.import_module("dashboard")
        rows = [receipt(str(i), escape_7d="no", repair_rounds=0, wall_s=1,
                        served_provider="fixture", served_model="model", served_effort="high") for i in range(5)]
        metrics = dashboard.metrics_from_observations(rows, [start(r["task_id"]) for r in rows],
            followups=[followup(r["task_id"], escape_7d="yes") for r in rows], as_of=AS_OF)
        metrics.update(telemetry_completeness=1)
        result = dashboard.objective_state(metrics, {"30": {"rate": 0}})
        self.assertEqual(result["status"], "off-target")
        self.assertEqual(next(g for g in result["gates"] if g["key"] == "escape")["actual"], 1)

    def test_unknown_provider_blocks_dashboard_route_price(self):
        dashboard = importlib.import_module("dashboard")
        rows = [receipt("ok", served_provider="fixture", served_model="model", served_effort="medium"),
                receipt("fail", 8, "blocked", served_provider="unmeasured", served_model="model", served_effort="medium")]
        result = dashboard.route_metrics(rows, starts=[start("ok"), start("fail")],
                                         followups=[followup("ok")], as_of=AS_OF)
        self.assertTrue(all(r["cost_usd_per_reliable"] is None for r in result))

    def route_fixture(self, cost_a=10, cost_b=1, basis_b="api-equivalent", project_b="project"):
        candidates, rows, starts, events = [], [], [], []
        for model, cost, basis, project in (("a", cost_a, "api-equivalent", "project"),
                                           ("b", cost_b, basis_b, project_b)):
            candidates.append({"id": model, "provider": "fixture", "model": model,
                               "effort": "medium", "task_classes": ["implement"], "command": ["fixture"]})
            for i in range(5):
                task = model + str(i)
                rows.append(receipt(task, cost, served_provider="fixture", served_model=model, served_effort="medium",
                                    project_id=project, task_class="implement", repair_rounds=0,
                                    wall_s=1 if model == "a" else 2, cost_basis=basis,
                                    cost_source="rate-card-estimate" if basis == "api-equivalent" else "provider-reported"))
                starts.append(start(task, project_id=project))
                events.append(followup(task, project_id=project))
        return candidates, rows, starts, events

    def test_selector_never_compares_mixed_usd_bases_or_projects(self):
        cli = importlib.import_module("framework_cli")
        for basis, project in (("billed", "project"), ("api-equivalent", "other")):
            candidates, rows, starts, events = self.route_fixture(basis_b=basis, project_b=project)
            for row in rows:  # Explicit synthetic scope keeps comparability as the blocking gate.
                row["cost_components_usd"] = {"executor": row["cost_usd"], "review": 0, "retries": 0,
                    "verification": 0, "infrastructure": 0, "preparation": 0}
            result = cli.select_route(candidates, rows, "implement", which=lambda _: "fixture",
                                      starts=starts, followups=events, as_of=AS_OF)
            self.assertNotEqual(result["strategy"], "measured")
            self.assertEqual(result["rejected"], {
                candidate["id"]: ["non-comparable project or USD basis"] for candidate in candidates})

    def test_sub_microdollar_cost_is_not_rounded_to_zero_for_routing(self):
        cli = importlib.import_module("framework_cli")
        candidates, rows, starts, events = self.route_fixture(4e-7, 1e-7)
        for row in rows:  # Synthetic positive control, not inferred real overhead.
            row["cost_components_usd"] = {"executor": row["cost_usd"], "review": 0, "retries": 0,
                "verification": 0, "infrastructure": 0, "preparation": 0}
        result = cli.select_route(candidates, rows, "implement", which=lambda _: "fixture",
                                  starts=starts, followups=events, as_of=AS_OF)
        self.assertEqual(result["selected"]["id"], "b")
        economics = self.summarize([receipt("a", 4e-7)], [start("a")])
        self.assertEqual(economics["cost_usd_known_sum"], 4e-7)

    def test_dashboard_and_selector_use_same_quality_denominator(self):
        dashboard = importlib.import_module("dashboard")
        cli = importlib.import_module("framework_cli")
        candidates, rows, starts, events = self.route_fixture()
        rows = [r for r in rows if r["served_model"] == "a"]
        starts = [s for s in starts if s["task_id"].startswith("a")]
        events = [e for e in events if e["task_id"].startswith("a")]
        for i in range(5):
            task = "failed" + str(i)
            rows.append(receipt(task, 2, "blocked", task_class="implement", served_provider="fixture",
                                served_model="a", served_effort="medium", repair_rounds=0, wall_s=1))
            starts.append(start(task))
        metrics = dashboard.metrics_from_observations(rows, starts, followups=events, as_of=AS_OF)
        metrics["telemetry_completeness"] = 1
        objective = dashboard.objective_state(metrics, {"30": {"rate": 0}})
        gate = next(g for g in objective["gates"] if g["key"] == "reliable")
        performance = cli.route_performance(candidates[0], rows, "implement", starts=starts, followups=events, as_of=AS_OF)
        self.assertEqual(gate["actual"], performance["reliable_rate"])
        self.assertEqual(gate["denominator"], 10)
        self.assertEqual(objective["status"], "off-target")

    def test_legacy_project_scoping_preserves_sources_and_rejects_foreign_identity(self):
        rows = [{"task_id": "a"}]
        scoped = report.scope_project(rows, "project")
        self.assertEqual(scoped, [{"task_id": "a", "project_id": "project"}])
        self.assertEqual(rows, [{"task_id": "a"}])
        with self.assertRaises(ValueError):
            report.scope_project([{"task_id": "a", "project_id": "foreign"}], "project")

    def test_dashboard_acquisition_error_preserves_unknown_ratio(self):
        dashboard = importlib.import_module("dashboard")
        result = dashboard.metrics_from_observations([receipt("a")], [start("a")],
            followups=[followup("a")], as_of=AS_OF, acquisition_errors=[{"error": "unreadable"}])
        self.assertIsNone(result["cost_usd_per_reliable"])
        self.assertIn("incomplete source acquisition", result["economics"]["reasons"])


if __name__ == "__main__":
    unittest.main()
