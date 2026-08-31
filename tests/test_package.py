import re
import unittest
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


if __name__ == "__main__":
    unittest.main()
