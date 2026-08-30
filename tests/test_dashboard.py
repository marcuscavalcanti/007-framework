import json
import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CLI = ROOT / "scripts" / "framework_cli.py"
BIN = ROOT / "bin" / "007"


class DashboardTests(unittest.TestCase):
    def module(self, name):
        sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            self.fail(f"missing production module: {name}")
        finally:
            sys.path.pop(0)

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

    def test_aggregate_reconciles_raw_project_totals(self):
        dashboard = self.module("dashboard")
        projects = [
            {"available": True, "metrics": {
                "tasks": 2, "accepted": 1, "blocked": 1, "no_op": 0,
                "first_pass_yes": 1, "first_pass_known": 1,
                "repair_rounds_sum": 0, "repair_rounds_known_tasks": 1,
                "tokens_known_sum": 100, "tokens_known_tasks": 1,
                "wall_s_known_sum": 20, "wall_s_known_tasks": 1,
                "cost_usd_known_sum": 0.2, "cost_usd_known_tasks": 1,
                "escape_7d_yes": 0, "escape_7d_known": 1,
                "telemetry_known": 4, "telemetry_possible": 8,
                "delta_files": 2, "delta_added": 10, "delta_deleted": 3,
            }, "touch": {
                "7": {"agent_lines_added": 10, "surviving_lines": 9, "rate": 10.0},
                "30": {"agent_lines_added": 10, "surviving_lines": 8, "rate": 20.0},
            }},
            {"available": True, "metrics": {
                "tasks": 3, "accepted": 2, "blocked": 0, "no_op": 1,
                "first_pass_yes": 1, "first_pass_known": 2,
                "repair_rounds_sum": 2, "repair_rounds_known_tasks": 2,
                "tokens_known_sum": 0, "tokens_known_tasks": 0,
                "wall_s_known_sum": 30, "wall_s_known_tasks": 2,
                "cost_usd_known_sum": 0, "cost_usd_known_tasks": 0,
                "escape_7d_yes": 1, "escape_7d_known": 2,
                "telemetry_known": 3, "telemetry_possible": 12,
                "delta_files": 4, "delta_added": 20, "delta_deleted": 5,
            }, "touch": {
                "7": {"agent_lines_added": 20, "surviving_lines": 20, "rate": 0.0},
                "30": {"agent_lines_added": 20, "surviving_lines": 10, "rate": 50.0},
            }},
        ]

        result = dashboard.aggregate_projects(projects)

        self.assertEqual(result["tasks"], 5)
        self.assertEqual(result["accepted"], 3)
        self.assertEqual(result["first_pass_rate"], 2 / 3)
        self.assertEqual(result["tokens_known_sum"], 100)
        self.assertEqual(result["tokens_missing_tasks"], 4)
        self.assertEqual(result["repair_rounds_mean"], 2 / 3)
        self.assertEqual(result["escape_7d_rate"], 1 / 3)
        self.assertEqual(result["touch"]["30"]["rate"], 40.0)
        self.assertEqual(result["delta_added"], 30)

    def test_cost_per_accepted_excludes_blocked_task_telemetry(self):
        dashboard = self.module("dashboard")
        project = {"available": True, "metrics": {
            "tasks": 2, "accepted": 1,
            "tokens_known_sum": 1099, "tokens_known_tasks": 2,
            "accepted_tokens_known_sum": 100, "accepted_tokens_known_tasks": 1,
            "wall_s_known_sum": 1010, "wall_s_known_tasks": 2,
            "accepted_wall_s_known_sum": 10, "accepted_wall_s_known_tasks": 1,
            "cost_usd_known_sum": 9.5, "cost_usd_known_tasks": 2,
            "accepted_cost_usd_known_sum": 0.5, "accepted_cost_usd_known_tasks": 1,
        }, "touch": {"7": {}, "30": {}}}

        result = dashboard.aggregate_projects([project])

        self.assertEqual(result["tokens_per_accepted"], 100)
        self.assertEqual(result["wall_s_per_accepted"], 10)
        self.assertEqual(result["cost_usd_per_accepted"], 0.5)

    def test_project_snapshot_sanitizes_receipts_and_preserves_unknowns(self):
        dashboard = self.module("dashboard")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            (repo / ".git").mkdir()
            (repo / ".007/receipts").mkdir(parents=True)
            marker = {
                "schema": "007-framework/project/v1",
                "project_id": "project-1",
                "name": "Example",
                "receipt_dir": "receipts",
            }
            (repo / ".007/project.json").write_text(json.dumps(marker))
            (repo / ".007/receipts/task.receipt.json").write_text(json.dumps({
                "schema": "007-framework/receipt/v1",
                "task_id": "task-1",
                "status": "accepted",
                "proof_required": "integrated",
                "proof_reached": "integrated",
                "checks": [{"command": "secret command", "exit": 0, "tail": "secret"}],
                "delta": {"files": 2, "added": 10, "deleted": 1, "dependencies": 0},
                "first_pass": "yes",
                "repair_rounds": 0,
                "corrective_lines": "pending",
                "escape_7d": "pending",
                "model": ["malformed"],
                "effort": "medium",
                "tokens": "unmeasured",
                "wall_s": 12,
                "uncertainty": "runtime not exercised",
                "private_prompt": "must not escape",
            }))
            entry = {
                "project_id": "project-1", "name": "Example",
                "path": str(repo), "registered_at": "2026-08-30T00:00:00Z",
            }
            no_touch = lambda _repo, days: {
                "window_days": days, "agent_commits": 0, "human_commits": 0,
                "agent_lines_added": 0, "surviving_lines": 0,
                "rate": None, "reason": "no attributable agent commits",
            }

            result = dashboard.project_snapshot(entry, touch_provider=no_touch)

            self.assertTrue(result["available"])
            self.assertEqual(result["metrics"]["tasks"], 1)
            self.assertEqual(result["metrics"]["first_pass_rate"], 1.0)
            self.assertIsNone(result["metrics"]["tokens_per_accepted"])
            self.assertEqual(result["metrics"]["tokens_missing_tasks"], 1)
            self.assertEqual(result["metrics"]["telemetry_completeness"], 0.5)
            self.assertEqual(result["recent_tasks"][0]["task_id"], "task-1")
            self.assertNotIn("checks", result["recent_tasks"][0])
            self.assertNotIn("private_prompt", result["recent_tasks"][0])

    def test_touch_rate_exposes_structured_unknown_result(self):
        touch_rate = self.module("touch_rate")
        self.assertTrue(hasattr(touch_rate, "calculate"), "touch_rate.calculate is missing")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            Path(repo, "README.md").write_text("human\n")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
            env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "Human", "GIT_AUTHOR_EMAIL": "human@example.test",
                "GIT_COMMITTER_NAME": "Human", "GIT_COMMITTER_EMAIL": "human@example.test",
            }
            subprocess.run(["git", "commit", "-qm", "human"], cwd=repo, check=True, env=env)

            result = touch_rate.calculate(repo, days=30)

            self.assertIsNone(result["rate"])
            self.assertEqual(result["agent_commits"], 0)
            self.assertEqual(result["reason"], "no attributable agent commits")


if __name__ == "__main__":
    unittest.main()
