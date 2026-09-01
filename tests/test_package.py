import re
import unittest
import json
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageContractTests(unittest.TestCase):
    def test_skill_identity_and_version(self):
        skill = (ROOT / "SKILL.md").read_text()
        self.assertRegex(skill, r"(?m)^name: 007-framework$")
        self.assertRegex(skill, r"(?m)^  version: 1\.4\.0$")

    def test_local_markdown_links_exist(self):
        markdown = list(ROOT.glob("*.md")) + list((ROOT / "docs").glob("*.md"))
        markdown += list((ROOT / "references").glob("*.md"))
        missing = []
        for source in markdown:
            for target in re.findall(r"\[[^]]+\]\(([^)]+\.md(?:#[^)]+)?)\)", source.read_text()):
                path = target.split("#", 1)[0]
                if not (source.parent / path).resolve().exists():
                    missing.append(f"{source.relative_to(ROOT)} -> {target}")
        self.assertEqual(missing, [])

    def test_public_bytes_exclude_private_paths_and_secret_markers(self):
        forbidden = (
            "/Users/" + "marcus",
            "~/.codex/skills/" + "personal-harness",
            "BEGIN OPENSSH " + "PRIVATE KEY",
            "BEGIN RSA " + "PRIVATE KEY",
            "sk-" + "ant-",
        )
        hits = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or path.suffix == ".pyc":
                continue
            text = path.read_text(errors="replace")
            for marker in forbidden:
                if marker in text:
                    hits.append(f"{path.relative_to(ROOT)}: {marker}")
        self.assertEqual(hits, [])

    def test_similarity_is_diagnostic_only(self):
        doctrine = (ROOT / "references" / "causal-testing.md").read_text().lower()
        self.assertIn("diagnostic only", doctrine)
        self.assertIn("never an acceptance, review, or release gate", doctrine)

    def test_rejected_provider_password_doctrine_is_not_shipped(self):
        skill = (ROOT / "SKILL.md").read_text().lower()
        self.assertNotIn("password field", skill)
        self.assertNotIn("new password", skill)

    def test_current_narrow_result_is_not_called_controlled(self):
        current_claims = (ROOT / "README.md").read_text() + (ROOT / "docs/evidence.md").read_text()
        self.assertNotRegex(current_claims.lower(), r"controlled (mechanism|decision|result)")

    def test_replay_example_is_valid_json(self):
        import json
        example = json.loads((ROOT / "examples" / "replay-set.example.json").read_text())
        self.assertEqual(set(example["arms"]), {"OLD", "NEW"})
        self.assertEqual(len(example["tasks"]), 1)

    def test_route_example_is_valid_and_contains_no_shell_string(self):
        import importlib
        import json
        import sys
        scripts = ROOT / "scripts"
        sys.path.insert(0, str(scripts))
        try:
            framework_cli = importlib.import_module("framework_cli")
            example = json.loads((ROOT / "examples" / "routes.example.json").read_text())
            framework_cli.validate_route_config(example)
        finally:
            sys.path.pop(0)
        self.assertTrue(all(isinstance(item["command"], list) for item in example["candidates"]))

    def test_release_manifest_gate_targets_the_current_tag(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("if: startsWith(github.ref, 'refs/tags/v')", workflow)
        self.assertIn('evidence/${GITHUB_REF_NAME}/manifest.sha256', workflow)
        self.assertNotIn("sha256sum --check evidence/v1.1.0/manifest.sha256", workflow)

    def test_v14_public_evidence_keeps_support_and_inconclusive_results_distinct(self):
        causal = json.loads((ROOT / "evidence/v1.4.0/causal-roi-result.json").read_text())
        incident = json.loads((ROOT / "evidence/v1.4.0/phase-zero-v16-inconclusive.json").read_text())

        self.assertEqual(causal["status"], "supported-task-local")
        self.assertEqual(causal["sample"], {"tasks": 1, "cells": 6, "accepted": 6})
        self.assertEqual(causal["served_identity"]["verified_cells"], 6)
        self.assertEqual(len(causal["old"]["cell_cost_usd"]), 3)
        self.assertEqual(len(causal["new"]["cell_wall_s"]), 3)
        self.assertEqual(causal["delta"]["cost_pct"], -42.6)
        expected_wall_delta = round(
            (causal["new"]["wall_s_per_accepted"] / causal["old"]["wall_s_per_accepted"] - 1) * 100,
            1,
        )
        self.assertEqual(causal["delta"]["wall_per_accepted_pct"], expected_wall_delta)
        self.assertNotIn("median_wall_pct", causal["delta"])
        self.assertEqual(incident["status"], "inconclusive-instrument-conflict")
        self.assertEqual(incident["executed_cells"], 6)
        self.assertEqual(incident["not_executed_cells"], 36)
        self.assertIsNone(incident["claims"]["cost_reduction_per_accepted_task"])

    def test_v14_adversarial_release_review_is_hash_bound(self):
        review = json.loads((ROOT / "evidence/v1.4.0/adversarial-review.json").read_text())

        self.assertEqual(review["schema"], "007-framework/adversarial-review/v1")
        self.assertEqual(review["reviewer"], "anthropic/claude-opus-5")
        self.assertEqual(review["effort"], "xhigh")
        self.assertFalse(review["tools"])
        self.assertEqual(review["final"], {
            "context_sha256": "f05da0125155ad013bd654e9e216051829d1a23d03c5537258ba6e20bbe56d77",
            "source_result_sha256": "d6e7472edd04d657fe649d88596e10c618ff9be5ee12ce5c6f5546964a17fe8d",
            "verdict": "approve",
            "highest_severity": "low",
        })
        self.assertEqual([item["verdict"] for item in review["history"]], ["reject", "reject"])
        self.assertEqual(len(review["reconciled_low_findings"]), 3)

    def test_v14_release_manifest_matches_public_bytes(self):
        manifest = ROOT / "evidence/v1.4.0/manifest.sha256"
        mismatches = []
        for line in manifest.read_text().splitlines():
            digest, relative = line.split("  ", 1)
            source = ROOT / relative
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                mismatches.append(relative)
        self.assertEqual(mismatches, [])


if __name__ == "__main__":
    unittest.main()
