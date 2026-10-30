"""Oracle calibration on public synthetic cases: both legitimate variants pass, each focal mutant fails.

Calibration, not a holdout: the oracles and the candidates have the same author (spec section 8).
"""
import importlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

replay = importlib.import_module("replay_eval")
ROOT = Path(__file__).parent / "fixtures/calibration"
# Review r25-r32 R6 / re-review r35 N1: pinned inventory; the expectation comes from the name (legit_* accepted, mutant_* rejected).
INVENTORY = {"lru": ["legit_a", "legit_b", "mutant_m1", "mutant_m2"],
             "queue": ["legit_a", "legit_b", "mutant_m1", "mutant_m2", "mutant_m3"],
             "limiter": ["legit_a", "legit_b", "mutant_m1", "mutant_m2"]}


def accepted(case, candidate):
    contract = json.loads((ROOT / case / "acceptance.json").read_bytes())
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        for name in ("oracle.py", "acceptance.json"):
            shutil.copy(ROOT / case / name, work / name)
        shutil.copy(ROOT / case / "candidates" / f"{candidate}.py", work / "candidate.py")
        return all(replay.run(command, cwd=work, timeout=contract["timeout_s"]).returncode == 0
                   for command in contract["commands"])


class CalibrationTests(unittest.TestCase):
    def test_oracles_accept_legitimate_variants_and_reject_focal_mutants(self):
        for case in ("lru", "queue", "limiter"):
            names = sorted(p.stem for p in (ROOT / case / "candidates").glob("*.py"))
            self.assertEqual(names, INVENTORY[case])  # re-review r35 N1: the focal controls are pinned, not just counted
            expected_by_name = {name: name.startswith("legit_") for name in names}
            for candidate, expected in expected_by_name.items():
                with self.subTest(case=case, candidate=candidate):
                    # 3 repetitions x 2 fresh directories: any disagreement is flakiness, not a verdict.
                    self.assertEqual([accepted(case, candidate) for _ in range(6)], [expected] * 6)


if __name__ == "__main__":
    unittest.main()
