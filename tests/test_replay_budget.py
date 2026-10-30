"""Literal USD ledger controls; no model calls or provider billing claims."""
import importlib
from contextlib import closing
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ReplayBudgetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name).resolve() / "budget.sqlite"
        try:
            self.module = importlib.import_module("replay_budget")
        except ModuleNotFoundError:
            self.fail("replay reservation ledger is missing")
        self.prior = {"executor_cells": 0, "independent_review": 0, "contingency": 0}

    def create(self, **changes):
        args = {"protocol_sha256": "a" * 64, "cost_basis": "api-equivalent", "prior_costs": self.prior,
                "prior_costs_source_sha256": "b" * 64, **changes}
        return self.module.ReplayBudget.create(self.path, **args)

    def reserve(self, budget, name, usd, category="executor_cells"):
        return budget.reserve(name, category, usd, bound_source_sha256="c" * 64)

    def settle(self, budget, name, usd, source="d" * 64):
        return budget.settle(name, usd, cost_basis="api-equivalent", source_sha256=source)

    def test_explicit_prior_cost_is_included_and_unknown_is_not_zero(self):
        self.prior["executor_cells"] = 3
        budget = self.create()
        self.assertEqual(budget.snapshot()["spent_usd"], 3)
        self.assertEqual(budget.snapshot()["remaining_usd"], 27)
        other = self.path.with_name("unknown.sqlite")
        with self.assertRaises(ValueError):
            self.module.ReplayBudget.create(other, protocol_sha256="a" * 64, cost_basis="api-equivalent",
                prior_costs={**self.prior, "contingency": None}, prior_costs_source_sha256="b" * 64)
        self.assertFalse(other.exists())

    def test_reservation_survives_restart_and_prevents_parallel_launch(self):
        budget = self.create()
        self.assertTrue(self.reserve(budget, "one", 4)["launch_granted"])
        restarted = self.module.ReplayBudget(self.path, protocol_sha256="a" * 64)
        self.assertEqual(restarted.snapshot(), budget.snapshot())
        self.assertEqual(restarted.snapshot()["reserved_usd"], 4)
        self.assertEqual(restarted.snapshot()["remaining_usd"], 26)
        with self.assertRaises(ValueError):
            self.reserve(restarted, "two", 1)

    def test_repeated_reservation_cannot_grant_another_launch(self):
        budget = self.create()
        self.reserve(budget, "one", 1)
        state = budget.snapshot()
        self.assertFalse(self.reserve(budget, "one", 1)["launch_granted"])
        self.assertEqual(budget.snapshot(), state)
        with self.assertRaises(ValueError):
            self.reserve(budget, "one", 2)

    def test_unknown_cost_blocks_until_explicit_reconciliation(self):
        budget = self.create()
        self.reserve(budget, "one", 3)
        state = self.settle(budget, "one", None)
        self.assertIsNone(state["remaining_usd"])
        self.assertEqual(state["unpriced_calls"], 1)
        with self.assertRaises(ValueError):
            self.reserve(budget, "two", 1)
        state = self.settle(budget, "one", 2, "e" * 64)
        self.assertEqual(state["spent_usd"], 2)
        self.assertEqual(state["unpriced_calls"], 0)
        self.assertEqual(state["reserved_usd"], 0)
        self.assertTrue(self.reserve(budget, "two", 1)["launch_granted"])

    def test_paid_failure_counts_and_ten_dollar_checkpoint_stops_dispatch(self):
        budget = self.create()
        self.reserve(budget, "failed", 8)
        self.settle(budget, "failed", 8)
        self.reserve(budget, "accepted", 2)
        state = self.settle(budget, "accepted", 2)
        self.assertEqual(state["spent_usd"], 10)
        self.assertTrue(state["checkpoint_due"])
        with self.assertRaises(ValueError):
            self.reserve(budget, "another", 0.1)
        with self.assertRaises(ValueError):
            budget.acknowledge_checkpoint("f" * 64, review_source_sha256="e" * 64)
        budget.acknowledge_checkpoint(state["state_sha256"], review_source_sha256="e" * 64)
        self.assertTrue(self.reserve(budget, "another", 0.1)["launch_granted"])

    def test_six_completed_cells_trigger_checkpoint_even_when_cheap(self):
        budget = self.create()
        for index in range(6):
            self.reserve(budget, "cell-" + str(index), 0.1)
            state = self.settle(budget, "cell-" + str(index), 0.1)
        self.assertEqual(state["completed_cells"], 6)
        self.assertEqual(state["spent_usd"], 0.6)
        self.assertTrue(state["checkpoint_due"])
        with self.assertRaises(ValueError):
            self.reserve(budget, "seventh", 0.1)

    def test_total_and_category_limits_cannot_be_increased(self):
        self.prior.update(executor_cells=20, independent_review=5, contingency=4)
        budget = self.create()
        state = budget.snapshot()
        budget.acknowledge_checkpoint(state["state_sha256"], review_source_sha256="e" * 64)
        with self.assertRaises(ValueError):
            self.reserve(budget, "extra-review", 0.1, "independent_review")
        self.reserve(budget, "last", 1, "contingency")
        state = self.settle(budget, "last", 1)
        self.assertEqual(state["spent_usd"], 30)
        with self.assertRaises(ValueError):
            self.reserve(budget, "over", 0.000001, "contingency")

    def test_tiny_positive_reservation_is_not_rounded_away_at_checkpoint(self):
        self.prior["executor_cells"] = 10
        budget = self.create()
        with self.assertRaises(ValueError):
            self.reserve(budget, "tiny", 1e-40)

    def test_overrun_is_recorded_and_never_silently_released(self):
        budget = self.create()
        self.reserve(budget, "one", 1)
        state = self.settle(budget, "one", 2)
        self.assertEqual(state["spent_usd"], 2)
        self.assertEqual(state["violations"], ["reservation-overrun:one"])
        self.assertIsNone(state["remaining_usd"])
        with self.assertRaises(ValueError):
            self.reserve(budget, "two", 1)

    def test_basis_and_protocol_mismatch_fail_closed_without_reset(self):
        budget = self.create()
        self.reserve(budget, "one", 1)
        state = budget.snapshot()
        with self.assertRaises(ValueError):
            budget.settle("one", 1, cost_basis="billed", source_sha256="d" * 64)
        self.assertEqual(budget.snapshot(), state)
        with self.assertRaises(ValueError):
            self.module.ReplayBudget(self.path, protocol_sha256="f" * 64).snapshot()
        with self.assertRaises(ValueError):
            self.create()
        self.assertEqual(budget.snapshot(), state)

    def test_money_types_are_strict_and_settlement_is_idempotent(self):
        budget = self.create()
        for value in (True, -1, float("nan"), float("inf"), "1", 0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.reserve(budget, "bad", value)
        self.reserve(budget, "one", 1)
        state = self.settle(budget, "one", 0)
        self.assertEqual(self.settle(budget, "one", 0), state)
        with self.assertRaises(ValueError):
            self.settle(budget, "one", 0.1)

    def test_two_controllers_cannot_both_obtain_launch_permission(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        self.create()
        barrier = threading.Barrier(2)
        def attempt(name):
            budget = self.module.ReplayBudget(self.path, protocol_sha256="a" * 64)
            barrier.wait(timeout=3)
            try:
                return self.reserve(budget, name, 1)["launch_granted"]
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt, ["one", "two"])), [False, True])
        self.assertEqual(self.module.ReplayBudget(self.path, protocol_sha256="a" * 64).snapshot()["open_calls"], 1)

    def test_forged_early_checkpoint_is_not_an_authorized_budget_extension(self):
        import json
        import sqlite3
        budget = self.create()
        state = budget.snapshot()
        event = {"kind": "checkpoint", "state_sha256": state["state_sha256"], "source_sha256": "e" * 64}
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("INSERT INTO events VALUES (?)", (json.dumps(event),))
        with self.assertRaises(ValueError):
            budget.snapshot()

    def test_malformed_history_is_rejected_without_creating_a_replacement(self):
        import sqlite3
        budget = self.create()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("INSERT INTO events VALUES (?)", ("[]",))
        with self.assertRaises(ValueError):
            budget.snapshot()
        self.assertTrue(self.path.exists())

    def test_unknown_reservation_never_acknowledges_a_checkpoint(self):
        budget = self.create()
        self.reserve(budget, "one", 10)
        state = self.settle(budget, "one", None)
        with self.assertRaises(ValueError):
            budget.acknowledge_checkpoint(state["state_sha256"], review_source_sha256="e" * 64)

    def test_event_limit_refuses_launch_before_it_can_prevent_settlement(self):
        budget = self.create()
        for index in range(62):
            self.reserve(budget, "cell-" + str(index), 0.1)
            state = self.settle(budget, "cell-" + str(index), 0)
            if state["checkpoint_due"]:
                budget.acknowledge_checkpoint(state["state_sha256"], review_source_sha256="e" * 64)
        before = budget.snapshot()
        with self.assertRaises(ValueError):
            self.reserve(budget, "one-too-many", 0.1)
        self.assertEqual(budget.snapshot(), before)
        self.assertEqual(before["open_calls"], 0)

    def test_loosened_ledger_permissions_fail_closed(self):
        budget = self.create()
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            budget.snapshot()
        self.path.chmod(0o600)
        self.assertEqual(budget.snapshot()["spent_usd"], 0)
