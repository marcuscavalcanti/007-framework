import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ConfigGuardTests(unittest.TestCase):
    """Configuration may tune 007, never invalidate it: what can change is bounded, what defines the evidence cannot change."""

    def setUp(self):
        self.guard = importlib.import_module("config_guard")
        self.tmp = tempfile.TemporaryDirectory()
        self.trial_log = Path(self.tmp.name, "effort_trial.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, observatory, **kw):
        return self.guard.check({"observatory": observatory}, trial_log=self.trial_log, **kw)

    def test_a_sound_configuration_passes_untouched(self):
        config = {"projects": ["p1"], "auto": True, "exclude": ["Finance"], "lookback_hours": 168, "activity_gap_minutes": 30,
                  "calibrations": [], "effort_trial": {"enabled": True, "arms": {"codex": ["medium", "xhigh"]}, "seed": 7,
                                                       "repos": [], "agents": ["codex"]},
                  "evidence": {"confidence": 0.95, "min_n": 10, "margin": 0.0, "min_gain": 0.25}}
        self.assertEqual(self.check(config), [])

    def test_an_unknown_key_is_refused_with_the_likely_name(self):
        problems = self.check({"projets": ["p1"]})
        self.assertEqual(len(problems), 1)
        self.assertIn("observatory.projets", problems[0])
        self.assertIn("projects", problems[0])

    def test_bounds_that_would_invalidate_a_verdict_are_refused(self):
        for evidence, needle in (({"margin": -0.05}, "margin"), ({"min_n": 2}, "min_n"), ({"confidence": 0.8}, "confidence"),
                                 ({"min_gain": 0.0}, "min_gain")):
            with self.subTest(evidence=evidence):
                problems = self.check({"evidence": evidence})
                self.assertTrue(any(needle in p for p in problems), problems)
        self.assertTrue(self.check({"lookback_hours": 1}))
        self.assertTrue(self.check({"activity_gap_minutes": 0}))

    def test_evidence_level_semantics_are_not_configurable(self):
        problems = self.check({"evidence": {"levels": {"3": "Observed"}}})
        self.assertTrue(any("not configurable" in p for p in problems), problems)

    def test_trial_arms_must_be_two_distinct_levels_the_agent_supports(self):
        for arms in ({"codex": ["medium"]}, {"codex": ["medium", "medium"]}, {"codex": ["medium", "ultra"]}, {"gemini": ["low", "high"]}):
            with self.subTest(arms=arms):
                self.assertTrue(self.check({"effort_trial": {"enabled": True, "arms": arms, "seed": 1}}), arms)

    def test_a_running_trial_cannot_change_its_seed_or_arms_but_can_be_switched_off(self):
        self.trial_log.write_text(json.dumps({"event": "assign", "agent": "codex", "arm": "medium", "seed": 7,
                                              "arms": ["medium", "xhigh"], "trial_id": "default"}) + "\n")
        running = {"enabled": True, "arms": {"codex": ["medium", "xhigh"]}, "seed": 7}
        self.assertEqual(self.check({"effort_trial": running}), [])
        reseeded = self.check({"effort_trial": {**running, "seed": 8}})
        self.assertTrue(any("seed" in p and "new trial" in p for p in reseeded), reseeded)
        rearmed = self.check({"effort_trial": {**running, "arms": {"codex": ["low", "xhigh"]}}})
        self.assertTrue(any("arms" in p and "new trial" in p for p in rearmed), rearmed)
        self.assertEqual(self.check({"effort_trial": {**running, "enabled": False}}), [])
        renamed = self.check({"effort_trial": {**running, "seed": 8, "trial_id": "t2"}})
        self.assertEqual(renamed, [], "a new trial id starts a new trial, so new seed and arms are fine")

    def test_load_refuses_an_invalid_file_and_names_every_problem(self):
        path = Path(self.tmp.name, "config.json")
        path.write_text(json.dumps({"observatory": {"projets": [], "evidence": {"margin": -1}}}))
        with self.assertRaises(self.guard.ConfigError) as ctx:
            self.guard.load(path, trial_log=self.trial_log)
        self.assertIn("projets", str(ctx.exception))
        self.assertIn("margin", str(ctx.exception))
        path.write_text("{not json")
        with self.assertRaises(self.guard.ConfigError):
            self.guard.load(path, trial_log=self.trial_log)
        self.assertEqual(self.guard.load(Path(self.tmp.name, "absent.json"), trial_log=self.trial_log), {})


if __name__ == "__main__":
    unittest.main()
