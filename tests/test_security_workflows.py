"""Keep analysis reports scoped to this repository's Actions artifacts."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SecurityWorkflowTests(unittest.TestCase):
    def workflow(self, name):
        path = ROOT / ".github/workflows" / name
        self.assertTrue(path.is_file(), "expected security workflow " + name)
        return path.read_text()

    def test_codeql_covers_python_and_javascript_with_artifact_reports(self):
        text = self.workflow("codeql.yml")
        self.assertIn("language: [python, javascript-typescript]", text)
        self.assertIn("build-mode: none", text)
        self.assertIn("upload: never", text)
        self.assertIn("upload-database: false", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotRegex(text, r"(?:security-events|id-token|attestations):\s*write")
        self.assertIn("if: always()", text)
        self.assertIn("if-no-files-found: error", text)

    def test_scorecard_targets_default_branch_and_keeps_results_in_actions(self):
        text = self.workflow("scorecard.yml")
        self.assertIn("branches: [main]", text)
        self.assertNotIn("pull_request", text)
        self.assertNotIn("schedule:", text)
        self.assertIn("publish_results: false", text)
        self.assertIn("results_format: json", text)
        self.assertIn("path: scorecard-results.json", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotRegex(text, r"(?:security-events|id-token|attestations):\s*write")

    def test_both_workflows_pin_actions_and_bound_execution(self):
        for name in ("codeql.yml", "scorecard.yml"):
            with self.subTest(workflow=name):
                text = self.workflow(name)
                actions = re.findall(r"(?m)^\s*- uses: (\S+)", text)
                self.assertTrue(actions)
                for action in actions:
                    self.assertRegex(action, r"^[A-Za-z0-9_./-]+@[0-9a-f]{40}$")
                self.assertRegex(text, r"timeout-minutes: (15|20)\b")
