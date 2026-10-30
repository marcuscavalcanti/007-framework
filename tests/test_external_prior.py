import csv
import importlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

HEADER = ["experiment", "owner", "task", "judge", "status", "started_at", "finished_at", "language", "model", "tooling", "prompt",
          "effort", "agent", "stack", "replicate", "code_quality", "test_coverage", "defect_rate", "maintainability", "idiomatic",
          "token_efficiency", "requirement_coverage", "factual_accuracy", "runtime", "duration_seconds", "tokens", "cost_usd", "turns",
          "max_context_tokens", "second_try", "agent_steps"]


def row(**values):
    return {**{h: "" for h in HEADER}, "status": "completed", "task": "rest-api-crud", "language": "python", **values}


class ExternalPriorTests(unittest.TestCase):
    """Retort's public master.csv as a labelled external prior (spec 2026-10-22-007-retort-interop-design.md)."""

    def setUp(self):
        self.prior = importlib.import_module("external_prior")
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name, "master.csv")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rows):
        with open(self.path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADER)
            writer.writeheader()
            writer.writerows(rows)

    def test_groups_count_only_first_attempt_full_passes_and_keep_unknown_cost_unknown(self):
        self.write([
            row(model="opus-4.8", effort="low", requirement_coverage="1.0", duration_seconds="30", cost_usd="0.4"),
            row(model="claude-opus-4-8", effort="low", requirement_coverage="1.0", duration_seconds="50", cost_usd=""),
            row(model="opus-4.8", effort="low", requirement_coverage="1.0", duration_seconds="40", cost_usd="0.6", second_try="1"),
            row(model="opus-4.8", effort="low", requirement_coverage="0.9", duration_seconds="20", cost_usd="0.2"),
            row(model="opus-4.8", effort="low", requirement_coverage="1.0", status="failed"),
        ])
        groups = self.prior.summarize(self.path)
        key = ("opus-4-8", "low", "rest-api-crud", "python")
        g = groups[key]
        self.assertEqual((g["n"], g["passes"]), (4, 2))           # the failed-status row is excluded; second try is not a pass
        self.assertEqual((g["unknown_cost"], g["median_cost_usd"]), (1, 0.4))
        self.assertEqual(g["median_duration_s"], 35.0)
        self.assertEqual(g["source_sha256"], self.prior.sha256(self.path))
        self.assertEqual(g["evidence"], "external")

    def test_wilson_interval_and_default_effort_flagged_not_comparable(self):
        self.write([row(model="m", effort="", requirement_coverage="1.0") for _ in range(3)])
        g = self.prior.summarize(self.path)[("m", "default", "rest-api-crud", "python")]
        low, high = g["pass_ci95"]
        self.assertAlmostEqual(low, 0.4385, places=3)
        self.assertEqual(high, 1.0)
        self.assertFalse(g["effort_comparable"])

    def test_language_can_be_pooled_and_small_groups_are_marked(self):
        self.write([row(model="m", effort="low", requirement_coverage="1.0", language=lang) for lang in ("python", "go")])
        groups = self.prior.summarize(self.path, by_language=False, min_n=3)
        g = groups[("m", "low", "rest-api-crud", "*")]
        self.assertEqual((g["n"], g["below_min_n"]), (2, True))


if __name__ == "__main__":
    unittest.main()
