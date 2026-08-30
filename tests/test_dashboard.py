import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "framework_cli.py"
BIN = ROOT / "bin" / "007"


class DashboardTests(unittest.TestCase):
    def run_cli(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_init_registers_project_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")

            first = self.run_cli("init", "--repo", str(repo), "--registry", str(registry))
            second = self.run_cli("init", "--repo", str(repo), "--registry", str(registry))

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            marker = json.loads((repo / ".007/project.json").read_text())
            projects = json.loads(registry.read_text())["projects"]
            self.assertEqual(marker["schema"], "007-framework/project/v1")
            self.assertEqual(marker["receipt_dir"], "receipts")
            self.assertEqual(len(projects), 1)
            self.assertEqual(projects[0]["project_id"], marker["project_id"])
            self.assertEqual(projects[0]["path"], str(repo.resolve()))
            self.assertTrue((repo / ".007/receipts").is_dir())

    def test_init_rejects_non_git_directory_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "not-git")
            repo.mkdir()
            registry = Path(tmp, "state", "projects.json")

            result = self.run_cli("init", "--repo", str(repo), "--registry", str(registry))

            self.assertEqual(result.returncode, 2)
            self.assertIn("not a Git repository", result.stderr)
            self.assertFalse((repo / ".007").exists())
            self.assertFalse(registry.exists())

    def test_init_rejects_malformed_registry_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            registry.parent.mkdir()
            registry.write_text(json.dumps({
                "schema": "007-framework/registry/v1",
                "projects": ["not-an-entry"],
            }))

            result = self.run_cli("init", "--repo", str(repo), "--registry", str(registry))

            self.assertEqual(result.returncode, 2)
            self.assertIn("invalid registry", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_bin_entrypoint_exposes_help(self):
        result = subprocess.run(
            [str(BIN), "--help"], capture_output=True, text=True, timeout=30,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("007 Framework", result.stdout)


if __name__ == "__main__":
    unittest.main()
