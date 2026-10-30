"""Public synthetic controller proof: no provider, billing or business task."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import test_dataset_admission as fixtures
import test_roi_accounting as economics_fixtures
from replay_budget import ReplayBudget


class SemanticReplayTests(unittest.TestCase):
    def test_semantic_replay_is_deterministic(self):
        fixture = fixtures.DatasetTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        (fixture.repo / "tracked.py").write_bytes(b"value = 4\n")
        negative = fixture.additional_case(
            [sys.executable, "-c", "from pathlib import Path; assert Path('tracked.py').read_bytes() == b'value = 3\\n'"])
        tasks = [fixture.task, negative]
        fixture.repo.rename(fixture.root / "original-unavailable")
        frozen = {path: path.read_bytes() for path in fixture.vault.rglob("*") if path.is_file()}
        configuration = {"seed": 4007, "tasks": [{"id": "case"}]}
        receipts = [economics_fixtures.receipt("guarded", 8, "blocked"),
                    economics_fixtures.receipt("task", 2)]
        starts = [economics_fixtures.start("guarded"), economics_fixtures.start("task")]
        protocol_hash = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
        costs_hash = hashlib.sha256(json.dumps(receipts, sort_keys=True).encode()).hexdigest()
        results = []
        for repetition in range(3):
            restores = []
            for index in range(2):
                destination = fixture.root / f"restore-{repetition}-{index}"
                fixtures.capture.restore_candidate(fixture.vault, "project", "task", fixture.ref, destination)
                self.assertEqual((destination / "tracked.py").read_bytes(), b"value = 3\n")
                self.assertEqual((destination / "ignored.bin").read_bytes(), b"\x00binary\xff")
                self.assertEqual((destination / "tracked.py").stat().st_mode & 0o777, 0o750)
                restores.append({
                    path.relative_to(destination).as_posix(): {
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "mode": path.stat().st_mode & 0o777,
                    } for path in destination.rglob("*") if path.is_file()
                })
            self.assertEqual(restores[0], restores[1])
            admission = fixtures.replay.admit_dataset(
                tasks if repetition % 2 == 0 else list(reversed(tasks)),
                vault_root=fixture.vault, recheck=True)
            rows = {row["id"]: row for row in admission["cases"]}
            self.assertEqual({row["source_task_id"] for row in rows.values()},
                             {row["task_id"] for row in receipts})
            self.assertEqual(rows["case"]["oracle_exits"], [[0], [0]])
            self.assertTrue(rows["case"]["replay_ready"])
            self.assertEqual(rows["guarded"]["oracle_exits"], [[1], [1]])
            self.assertFalse(rows["guarded"]["replay_ready"])
            for row in rows.values():
                self.assertTrue(row["admitted"])
                self.assertFalse(row["causal_eligible"])
                self.assertFalse(row["economic_eligible"])
            schedule = list(fixtures.replay.experiment_schedule(configuration, ["OLD", "NEW"], 3).values())
            self.assertEqual(schedule, [["NEW", "OLD"], ["OLD", "NEW"], ["NEW", "OLD"]])
            budget = ReplayBudget.create(fixture.root / f"budget-{repetition}.sqlite",
                protocol_sha256=protocol_hash, cost_basis="api-equivalent",
                prior_costs={"executor_cells": 0, "independent_review": 0, "contingency": 0},
                prior_costs_source_sha256=hashlib.sha256(b"synthetic prior spend = 0").hexdigest())
            for row in receipts:
                identifier, cost = row["task_id"], row["cost_usd"]
                budget.reserve(identifier, "executor_cells", cost, bound_source_sha256=costs_hash)
                budget.settle(identifier, cost, cost_basis="api-equivalent", source_sha256=costs_hash)
            state = budget.snapshot()
            self.assertEqual(state["spent_usd"], 10)
            self.assertEqual(state["remaining_usd"], 20)
            self.assertTrue(state["checkpoint_due"])
            with self.assertRaises(ValueError):
                budget.reserve("third", "executor_cells", 0.01, bound_source_sha256=costs_hash)
            self.assertEqual(budget.snapshot(), state)
            economics = economics_fixtures.report.summarize_economics(
                receipts if repetition % 2 == 0 else list(reversed(receipts)),
                starts=starts, followups=[], cost_basis="api-equivalent",
                as_of=economics_fixtures.AS_OF)
            self.assertEqual(economics["cost_usd_known_sum"], 10)
            self.assertEqual(economics["cost_usd_per_declared_accepted"], 10)
            self.assertIsNone(economics["cost_usd_per_reliable_declared"])
            results.append({"restored": restores[0], "admission": admission,
                            "schedule": schedule, "budget": state, "economics": economics})
            self.assertEqual({path: path.read_bytes() for path in frozen}, frozen)
        canonical = [json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
                     for row in results]
        self.assertEqual(canonical, [canonical[0]] * 3)
        candidate = fixture.result.parent / "outputs/files/tracked.py"
        payload = candidate.read_bytes()
        candidate.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
        rejected = fixtures.replay.admit_dataset([fixture.task], vault_root=fixture.vault, recheck=True)
        self.assertEqual(rejected["counts"]["excluded"], 1)
        self.assertFalse(rejected["cases"][0]["replay_ready"])
        self.assertEqual(rejected["cases"][0]["oracle_exits"], [])
        print(json.dumps({
            "proof": "synthetic-controller-only", "repetitions": 3,
            "canonical_sha256": hashlib.sha256(canonical[0].encode()).hexdigest(),
            "seed": 4007, "positive_oracle": [[0], [0]], "focal_negative_oracle": [[1], [1]],
            "synthetic_usd": 10, "third_reservation": "blocked",
            "corrupt_candidate": "excluded-before-oracle", "economic_roi": None,
        }, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
