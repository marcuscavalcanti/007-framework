import re
import subprocess
import unittest
import json
import hashlib
import tempfile
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageContractTests(unittest.TestCase):
    def test_skill_identity_and_version(self):
        skill = (ROOT / "SKILL.md").read_text()
        self.assertRegex(skill, r"(?m)^name: 007-framework$")
        self.assertRegex(skill, r"(?m)^  version: 1\.5\.1$")

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
        self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(), "af18a8d85705d02b5fb5363c20ae130311e609322deba56eb84a8c083bd6ab6d")
        release = "301b1aa30522e87a486088c79687a93d95d2aa4a"
        if subprocess.run(["git", "cat-file", "-e", f"{release}^{{tree}}"], cwd=ROOT).returncode:
            return
        mismatches = []
        for line in manifest.read_text().splitlines():
            digest, relative = line.split("  ", 1)
            source = subprocess.run(["git", "show", f"{release}:{relative}"], cwd=ROOT, capture_output=True)
            if source.returncode or hashlib.sha256(source.stdout).hexdigest() != digest:
                mismatches.append(relative)
        self.assertEqual(mismatches, [])


    def test_v15_manifest_matches_historical_release_not_current_runtime(self):
        release = "460e98535752b18d1b4738babf8ad1f7d859d4a1"
        if subprocess.run(["git", "cat-file", "-e", f"{release}^{{tree}}"],
                          cwd=ROOT, capture_output=True).returncode:
            self.skipTest("Historical v1.5.0 tree requires a full Git checkout")
        for line in (ROOT / "evidence/v1.5.0/manifest.sha256").read_text().splitlines():
            digest, name = line.split("  ", 1)
            source = subprocess.run(["git", "show", f"{release}:{name}"], cwd=ROOT, capture_output=True)
            self.assertEqual(source.returncode, 0, name)
            self.assertEqual(hashlib.sha256(source.stdout).hexdigest(), digest, name)

    def test_v15_rc_evidence_and_manifest_are_bound(self):
        directory = ROOT / "evidence/v1.5.0-rc.2"
        manifest = ROOT / "evidence/v1.5.0/manifest.sha256"
        self.assertTrue(manifest.is_file(), "stable candidate manifest missing")
        listed = {}
        self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(),
                         "7e5d9f009939c252a5cfe6ab667931bacda7618f7e81e16cd73e970497367951")
        for line in manifest.read_text().splitlines():
            digest, name = line.split("  ", 1)
            self.assertNotIn(name, listed)
            listed[name] = digest
        self.assertIn("SKILL.md", listed)
        self.assertIn("scripts/framework_cli.py", listed)
        self.assertIn("tests/test_package.py", listed)
        qualification = json.loads((ROOT / "evidence/v1.5.0/qualification.json").read_text())
        self.assertEqual(qualification["version"], "1.5.0")
        self.assertEqual(qualification["status"], "local-candidate")
        self.assertFalse(qualification["stable_approved"])
        self.assertFalse(qualification["final_candidate_ci_observed"])
        self.assertEqual(qualification["independent_review_verdicts"], ["reject", "reject"])
        self.assertEqual(qualification["source_rc_manifest_sha256"],
                         hashlib.sha256((directory / "manifest.sha256").read_bytes()).hexdigest())
        self.assertEqual(qualification["ci"]["tested_commit"], qualification["source_rc_commit"])
        self.assertEqual({(job["python"], job["attempt"], job["observed_tests"])
                          for job in qualification["ci"]["jobs"]},
                         {("3.11", 2, 148), ("3.13", 2, 148), ("3.12", 3, 148)})
        protocol = json.loads((directory / "mechanism-protocol.json").read_text())
        result = json.loads((directory / "mechanism-result.json").read_text())
        self.assertEqual(protocol["retries"], 0)
        self.assertEqual(result["source_protocol_sha256"], protocol["source_protocol_sha256"])
        self.assertEqual(result["runtime_source_sha256"], listed["scripts/framework_cli.py"])
        self.assertEqual(result["target_test_sha256"], listed["tests/test_dashboard.py"])
        self.assertEqual(protocol["test_sha256"], result["target_test_sha256"])
        self.assertEqual(protocol["replicates"], 3)
        self.assertEqual(result["total_cells"], 12)
        self.assertEqual(len(result["cells"]), 12)
        combinations = set()
        for cell in result["cells"]:
            key = (cell["replicate"], cell["arm"], cell["scenario"])
            self.assertNotIn(key, combinations)
            combinations.add(key)
            self.assertEqual(cell["exit"], 1 if key[1:] == ("MUTANT", "target") else 0)
            self.assertFalse(cell["timeout"])
            self.assertTrue(cell["matched"])
        self.assertEqual(combinations, {
            (replicate, arm, scenario) for replicate in (1, 2, 3)
            for arm in ("MUTANT", "CURRENT") for scenario in ("target", "control")
        })


    def test_v15_rc_mutation_patch_reproduces_exact_mutant(self):
        directory = ROOT / "evidence/v1.5.0-rc.2"
        patch = directory / "mechanism-mutant.patch"
        self.assertTrue(patch.is_file(), "public causal mutant patch missing")
        protocol = json.loads((directory / "mechanism-protocol.json").read_text())
        self.assertEqual(hashlib.sha256(patch.read_bytes()).hexdigest(),
                         protocol["mutation_patch_sha256"])
        source = (ROOT / "scripts/framework_cli.py").read_bytes()
        old = b"        if shutdown_signal is None:\n"
        self.assertEqual(source.count(old), 1)
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run(["git", "init", "-q"], cwd=temporary, capture_output=True, check=True)
            target = Path(temporary) / "scripts/framework_cli.py"
            target.parent.mkdir()
            target.write_bytes(source)
            for argv in (["git", "apply", "--check", str(patch)],
                         ["git", "apply", str(patch)]):
                applied = subprocess.run(argv, cwd=temporary, capture_output=True)
                self.assertEqual(applied.returncode, 0, applied.stderr.decode())
            mutated = target.read_bytes()
        self.assertEqual(mutated, source.replace(old, b"        if True:\n", 1))
        self.assertEqual(hashlib.sha256(mutated).hexdigest(), protocol["mutant_source_sha256"])

    def test_v15_rc_mutation_patch_does_not_inherit_tmpdir_git_repo(self):
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run(["git", "init", "-q"], cwd=temporary,
                           capture_output=True, check=True)
            result = subprocess.run(
                [sys.executable, "-B", str(Path(__file__).resolve()),
                 "PackageContractTests.test_v15_rc_mutation_patch_reproduces_exact_mutant"],
                cwd=temporary, env={**os.environ, "TMPDIR": temporary},
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0,
                             "mutation reproduction inherited an ancestor Git repository:\n"
                             + result.stderr)

    def test_v15_rc_failures_have_observed_assertion_evidence(self):
        directory = ROOT / "evidence/v1.5.0-rc.2"
        result = json.loads((directory / "mechanism-result.json").read_text())
        for cell in result["cells"]:
            negative = cell["arm"] == "MUTANT" and cell["scenario"] == "target"
            self.assertEqual(cell.get("failure_signature"),
                             "executor survived shutdown cleanup" if negative else None)
            self.assertEqual(cell.get("assertion_message"),
                             "AssertionError: ProcessLookupError not raised : executor survived shutdown cleanup"
                             if negative else None)
            self.assertEqual(cell.get("failure_count"), 1 if negative else 0)
            self.assertEqual(cell.get("error_count"), 0)


if __name__ == "__main__":
    unittest.main()
