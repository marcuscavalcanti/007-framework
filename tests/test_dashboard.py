import json
import hashlib
import importlib
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


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
            self.assertEqual(
                subprocess.run(
                    ["git", "status", "--short"], cwd=repo,
                    capture_output=True, text=True, check=True,
                ).stdout,
                "",
            )

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

    def test_begin_creates_no_replace_task_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(
                self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode,
                0,
            )

            first = self.run_cli("begin", "--repo", str(repo), "--task-id", "task-001")
            second = self.run_cli("begin", "--repo", str(repo), "--task-id", "task-001")

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("task-001", first.stdout)
            self.assertEqual(second.returncode, 2)
            self.assertIn("already exists", second.stderr)
            stored = json.loads((repo / ".007/tasks/task-001.task.json").read_text())
            self.assertEqual(stored["schema"], "007-framework/task-start/v1")
            self.assertEqual(stored["task_id"], "task-001")
            self.assertRegex(stored["started_at"], r"Z$")

    def test_begin_generates_safe_id_and_rejects_unsafe_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(
                self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode,
                0,
            )

            generated = self.run_cli("begin", "--repo", str(repo))
            unsafe = self.run_cli("begin", "--repo", str(repo), "--task-id", "../escape")

            self.assertEqual(generated.returncode, 0, generated.stderr)
            task_id = generated.stdout.strip().split()[-1]
            self.assertRegex(task_id, r"^task-[A-Za-z0-9_-]+$")
            self.assertTrue((repo / f".007/tasks/{task_id}.task.json").is_file())
            self.assertEqual(unsafe.returncode, 2)
            self.assertIn("task_id", unsafe.stderr)
            self.assertFalse((repo / ".007/escape.task.json").exists())

    def test_bound_authority_accepts_safe_events_and_summarizes_fences(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode, 0)
            authority = Path(tmp, "authority.json")
            authority.write_text(json.dumps({
                "schema": "007-framework/authority/v1",
                "allow": ["test"],
                "deny": ["deploy"],
            }))
            begun = self.run_cli(
                "begin", "--repo", str(repo), "--task-id", "authority-safe",
                "--authority-file", str(authority),
            )
            self.assertEqual(begun.returncode, 0, begun.stderr)
            authority_hash = hashlib.sha256(authority.read_bytes()).hexdigest()
            receipt = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
            receipt.update({
                "task_id": "authority-safe",
                "authority_sha256": authority_hash,
                "boundary_events": [
                    {"action": "test", "outcome": "executed"},
                    {"action": "deploy", "outcome": "blocked"},
                ],
            })
            source = Path(tmp, "receipt.json")
            source.write_text(json.dumps(receipt))

            recorded = self.run_cli("record", "--repo", str(repo), "--file", str(source))

            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            stored = json.loads((repo / ".007/receipts/authority-safe.receipt.json").read_text())
            self.assertEqual(stored["authority_sha256"], authority_hash)
            self.assertEqual(stored["authority_summary"], {
                "bound": True,
                "events": 2,
                "allowed_executions": 1,
                "protected_blocks": 1,
                "friction_blocks": 0,
                "unclassified_blocks": 0,
            })
            self.assertEqual(stored["authority_evidence"], "declared")

    def test_bound_authority_rejects_executed_denied_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode, 0)
            authority = Path(tmp, "authority.json")
            authority.write_text(json.dumps({
                "schema": "007-framework/authority/v1",
                "allow": ["test"],
                "deny": ["deploy"],
            }))
            self.assertEqual(self.run_cli(
                "begin", "--repo", str(repo), "--task-id", "authority-violation",
                "--authority-file", str(authority),
            ).returncode, 0)
            receipt = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
            receipt.update({
                "task_id": "authority-violation",
                "authority_sha256": hashlib.sha256(authority.read_bytes()).hexdigest(),
                "boundary_events": [{"action": "deploy", "outcome": "executed"}],
            })
            source = Path(tmp, "receipt.json")
            source.write_text(json.dumps(receipt))

            recorded = self.run_cli("record", "--repo", str(repo), "--file", str(source))

            self.assertEqual(recorded.returncode, 2)
            self.assertIn("outside bound authority", recorded.stderr)
            self.assertFalse((repo / ".007/receipts/authority-violation.receipt.json").exists())

    def test_run_blocks_denied_action_before_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode, 0)
            authority = Path(tmp, "authority.json")
            authority.write_text(json.dumps({
                "schema": "007-framework/authority/v1",
                "allow": ["test"],
                "deny": ["deploy"],
            }))

            result = self.run_cli(
                "run", "--repo", str(repo), "--task-id", "deny-1",
                "--receipt", "blocked.json", "--authority-file", str(authority),
                "--action", "deploy", "--", sys.executable, "-c",
                "from pathlib import Path; Path('sentinel').write_text('ran')",
            )

            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertFalse((repo / "sentinel").exists())
            stored = json.loads((repo / ".007/receipts/deny-1.receipt.json").read_text())
            self.assertEqual(stored["authority_evidence"], "controlled")
            self.assertEqual(stored["authority_summary"]["protected_blocks"], 1)
            event = json.loads((repo / ".007/events/deny-1.event.json").read_text())
            self.assertEqual(event["outcome"], "blocked")
            self.assertIsNone(event["exit_code"])

    def test_run_records_allowed_action_as_controlled(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode, 0)
            authority = Path(tmp, "authority.json")
            authority.write_text(json.dumps({
                "schema": "007-framework/authority/v1",
                "allow": ["test"],
                "deny": ["deploy"],
            }))
            adapter = Path(tmp, "adapter.py")
            adapter.write_text(
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "value = json.loads(Path(sys.argv[1]).read_text())\n"
                "value['task_id'] = os.environ['FRAMEWORK_007_TASK_ID']\n"
                "Path('sentinel').write_text('ran')\n"
                "Path(os.environ['FRAMEWORK_007_RECEIPT_PATH']).write_text(json.dumps(value))\n"
            )

            result = self.run_cli(
                "run", "--repo", str(repo), "--task-id", "allow-1",
                "--receipt", "allowed.json", "--authority-file", str(authority),
                "--action", "test", "--", sys.executable, str(adapter),
                str(ROOT / "examples/task.receipt.example.json"),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((repo / "sentinel").exists())
            stored = json.loads((repo / ".007/receipts/allow-1.receipt.json").read_text())
            self.assertEqual(stored["authority_evidence"], "controlled")
            self.assertEqual(stored["authority_summary"]["allowed_executions"], 1)
            event = json.loads((repo / ".007/events/allow-1.event.json").read_text())
            self.assertEqual(event["exit_code"], 0)

    def test_run_rejects_partial_authority_arguments_before_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode, 0)
            authority = Path(tmp, "authority.json")
            authority.write_text(json.dumps({
                "schema": "007-framework/authority/v1",
                "allow": ["test"],
                "deny": ["deploy"],
            }))

            missing_action = self.run_cli(
                "run", "--repo", str(repo), "--task-id", "partial-1",
                "--receipt", "partial-1.json", "--authority-file", str(authority),
                "--", sys.executable, "-c", "raise SystemExit(0)",
            )
            missing_authority = self.run_cli(
                "run", "--repo", str(repo), "--task-id", "partial-2",
                "--receipt", "partial-2.json", "--action", "test",
                "--", sys.executable, "-c", "raise SystemExit(0)",
            )

            self.assertEqual(missing_action.returncode, 2)
            self.assertEqual(missing_authority.returncode, 2)
            self.assertFalse((repo / ".007/tasks/partial-1.task.json").exists())
            self.assertFalse((repo / ".007/tasks/partial-2.task.json").exists())

    def test_record_rejects_caller_supplied_controlled_provenance(self):
        cli = self.module("framework_cli")
        receipt = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        receipt["authority_evidence"] = "controlled"

        with self.assertRaisesRegex(ValueError, "authority provenance"):
            cli.validate_receipt(receipt)

    def test_record_requires_cost_and_writes_no_replace_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(
                self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode,
                0,
            )
            self.assertEqual(
                self.run_cli("begin", "--repo", str(repo), "--task-id", "task-001").returncode,
                0,
            )
            receipt = {
                "schema": "007-framework/receipt/v1",
                "task_id": "task-001",
                "status": "accepted",
                "proof_required": "integrated",
                "proof_reached": "integrated",
                "checks": [{"command": "python3 -m unittest", "exit": 0}],
                "delta": {"files": 1, "added": 3, "deleted": 1, "dependencies": 0},
                "first_pass": "yes",
                "repair_rounds": 0,
                "corrective_lines": "pending",
                "escape_7d": "pending",
                "requested_provider": "openai",
                "requested_model": "gpt-requested",
                "requested_effort": "high",
                "served_provider": "openai",
                "served_model": "gpt-served",
                "served_effort": "xhigh",
                "tokens": 1200,
                "wall_s": 31,
                "cost_usd": 0.42,
                "cost_source": "provider-reported",
                "cost_status": "final",
                "uncertainty": "none",
            }
            source = Path(tmp, "receipt.json")
            source.write_text(json.dumps(receipt))

            first = self.run_cli("record", "--repo", str(repo), "--file", str(source))
            second = self.run_cli("record", "--repo", str(repo), "--file", str(source))

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 2)
            stored = json.loads((repo / ".007/receipts/task-001.receipt.json").read_text())
            self.assertEqual(stored["cost_usd"], 0.42)
            self.assertEqual(stored["served_model"], "gpt-served")
            self.assertRegex(stored["completed_at"], r"Z$")

    def test_record_rejects_receipt_without_matching_task_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(
                self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode,
                0,
            )
            source = Path(tmp, "receipt.json")
            source.write_text((ROOT / "examples/task.receipt.example.json").read_text())

            result = self.run_cli("record", "--repo", str(repo), "--file", str(source))

            self.assertEqual(result.returncode, 2)
            self.assertIn("matching task start", result.stderr)
            self.assertFalse((repo / ".007/receipts/task-001.receipt.json").exists())

    def test_record_rejects_task_start_with_mismatched_task_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(
                self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode,
                0,
            )
            self.assertEqual(
                self.run_cli("begin", "--repo", str(repo), "--task-id", "task-001").returncode,
                0,
            )
            task_path = repo / ".007/tasks/task-001.task.json"
            task = json.loads(task_path.read_text())
            task["task_id"] = "another-task"
            task_path.write_text(json.dumps(task))
            source = Path(tmp, "receipt.json")
            receipt = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
            receipt["task_id"] = "task-001"
            source.write_text(json.dumps(receipt))

            result = self.run_cli("record", "--repo", str(repo), "--file", str(source))

            self.assertEqual(result.returncode, 2)
            self.assertIn("task start task_id does not match receipt", result.stderr)
            self.assertFalse((repo / ".007/receipts/task-001.receipt.json").exists())

    def test_record_rejects_malformed_matching_task_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(
                self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode,
                0,
            )
            self.assertEqual(
                self.run_cli("begin", "--repo", str(repo), "--task-id", "task-001").returncode,
                0,
            )
            (repo / ".007/tasks/task-001.task.json").write_text("not-json")
            source = Path(tmp, "receipt.json")
            receipt = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
            receipt["task_id"] = "task-001"
            source.write_text(json.dumps(receipt))

            result = self.run_cli("record", "--repo", str(repo), "--file", str(source))

            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse((repo / ".007/receipts/task-001.receipt.json").exists())

    def test_record_rejects_unaccounted_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(
                self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode,
                0,
            )
            source = Path(tmp, "receipt.json")
            source.write_text(json.dumps({
                "schema": "007-framework/receipt/v1",
                "task_id": "task-no-cost",
                "status": "blocked",
                "cost_usd": "unmeasured",
                "cost_source": "unaccounted",
                "cost_status": "unaccounted",
            }))

            result = self.run_cli("record", "--repo", str(repo), "--file", str(source))

            self.assertEqual(result.returncode, 2)
            self.assertIn("cost_usd", result.stderr)
            self.assertFalse((repo / ".007/receipts/task-no-cost.receipt.json").exists())

    def test_record_rejects_non_finite_or_unaccounted_cost(self):
        cli = self.module("framework_cli")
        base = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        with self.assertRaisesRegex(ValueError, "cost_usd"):
            cli.validate_receipt({**base, "cost_usd": float("nan")})
        with self.assertRaisesRegex(ValueError, "cost_source"):
            cli.validate_receipt({**base, "cost_source": "unaccounted"})
        with self.assertRaisesRegex(ValueError, "authority_summary"):
            cli.validate_receipt({**base, "authority_summary": {"bound": True}})

    def test_record_accepts_documented_or_namespaced_cost_sources_only(self):
        cli = self.module("framework_cli")
        base = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        for source in (
            "provider-reported", "rate-card-estimate", "subscription-allocated",
            "local-compute", "custom:team-chargeback",
        ):
            with self.subTest(source=source):
                self.assertEqual(cli.validate_receipt({**base, "cost_source": source})["cost_source"], source)
        with self.assertRaisesRegex(ValueError, "cost_source"):
            cli.validate_receipt({**base, "cost_source": "provider_reported"})

    def test_run_wraps_command_with_one_observed_task_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(
                self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode,
                0,
            )
            adapter = Path(tmp, "adapter.py")
            adapter.write_text(
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "value = json.loads(Path(sys.argv[1]).read_text())\n"
                "value['task_id'] = os.environ['FRAMEWORK_007_TASK_ID']\n"
                "value['uncertainty'] = os.environ['FRAMEWORK_007_REPO']\n"
                "Path(os.environ['FRAMEWORK_007_RECEIPT_PATH']).write_text(json.dumps(value))\n"
                "print('adapter-ok')\n"
            )

            result = self.run_cli(
                "run", "--repo", str(repo), "--task-id", "wrapped-001",
                "--receipt", "task.receipt.json", "--",
                sys.executable, str(adapter), str(ROOT / "examples/task.receipt.example.json"),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("adapter-ok", result.stdout)
            self.assertTrue((repo / ".007/tasks/wrapped-001.task.json").is_file())
            stored = json.loads((repo / ".007/receipts/wrapped-001.receipt.json").read_text())
            self.assertEqual(stored["task_id"], "wrapped-001")
            self.assertEqual(stored["uncertainty"], str(repo.resolve()))

    def test_run_leaves_start_open_when_command_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(
                self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode,
                0,
            )

            result = self.run_cli(
                "run", "--repo", str(repo), "--task-id", "wrapped-failed",
                "--receipt", "task.receipt.json", "--",
                sys.executable, "-c", "raise SystemExit(7)",
            )

            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertTrue((repo / ".007/tasks/wrapped-failed.task.json").is_file())
            self.assertFalse((repo / ".007/receipts/wrapped-failed.receipt.json").exists())

    def test_run_rejects_success_without_terminal_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(
                self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode,
                0,
            )

            result = self.run_cli(
                "run", "--repo", str(repo), "--task-id", "wrapped-missing",
                "--receipt", "task.receipt.json", "--", sys.executable, "-c", "pass",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("did not produce terminal receipt", result.stderr)
            self.assertTrue((repo / ".007/tasks/wrapped-missing.task.json").is_file())
            self.assertFalse((repo / ".007/receipts/wrapped-missing.receipt.json").exists())

    def test_unregister_removes_only_the_registry_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            self.assertEqual(
                self.run_cli("init", "--repo", str(repo), "--registry", str(registry)).returncode,
                0,
            )

            result = self.run_cli(
                "unregister", "--project", str(repo), "--registry", str(registry)
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(registry.read_text())["projects"], [])
            self.assertTrue((repo / ".007/project.json").exists())

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

    def test_lifecycle_reconciles_starts_and_reliable_cost(self):
        dashboard = self.module("dashboard")
        starts = [
            {"task_id": "accepted-stable"},
            {"task_id": "accepted-escaped"},
            {"task_id": "still-running"},
        ]
        receipts = [
            {
                "task_id": "accepted-stable", "status": "accepted",
                "first_pass": "yes", "escape_7d": "no",
                "cost_usd": 0.4, "cost_source": "provider-reported", "cost_status": "final",
            },
            {
                "task_id": "accepted-escaped", "status": "accepted",
                "first_pass": "yes", "escape_7d": "yes",
                "cost_usd": 0.5, "cost_source": "provider-reported", "cost_status": "final",
            },
            {
                "task_id": "legacy-blocked", "status": "blocked",
                "first_pass": "no", "escape_7d": "no",
                "cost_usd": 0.1, "cost_source": "provider-reported", "cost_status": "final",
            },
        ]

        result = dashboard.metrics_from_observations(receipts, starts)

        self.assertEqual(result["started_tasks"], 3)
        self.assertEqual(result["matched_terminal_tasks"], 2)
        self.assertEqual(result["active_tasks"], 1)
        self.assertEqual(result["unstarted_terminal_tasks"], 1)
        self.assertEqual(result["observation_coverage"], 2 / 3)
        self.assertEqual(result["accepted_first_pass_yes"], 2)
        self.assertEqual(result["reliable_first_pass_yes"], 1)
        self.assertEqual(result["reliable_first_pass_known"], 2)
        self.assertEqual(result["reliable_first_pass_rate"], 0.5)
        self.assertEqual(result["cost_usd_per_reliable"], 1.0)

    def test_lifecycle_is_unknown_without_starts_or_matured_outcomes(self):
        dashboard = self.module("dashboard")
        receipts = [{
            "task_id": "legacy", "status": "accepted", "first_pass": "yes",
            "escape_7d": "pending", "cost_usd": 0.2,
            "cost_source": "provider-reported", "cost_status": "final",
        }]

        result = dashboard.metrics_from_observations(receipts, [])

        self.assertIsNone(result["observation_coverage"])
        self.assertIsNone(result["reliable_first_pass_rate"])
        self.assertIsNone(result["cost_usd_per_reliable"])
        self.assertEqual(result["unstarted_terminal_tasks"], 1)

    def test_evidence_state_names_inactive_instrumentation(self):
        dashboard = self.module("dashboard")
        metrics = dashboard.metrics_from_observations([], [])
        touch = {"7": {"rate": None}, "30": {"rate": None}}

        result = dashboard.evidence_state(metrics, touch)

        self.assertEqual(result["status"], "instrumentation-inactive")
        self.assertEqual(result["reasons"], ["no observed task starts"])

    def test_evidence_state_gates_on_reliable_first_pass(self):
        dashboard = self.module("dashboard")
        metrics = {
            "started_tasks": 5,
            "reliable_first_pass_known": 5,
            "reliable_first_pass_rate": 0.6,
            "repair_rounds_mean": 0.2,
            "escape_7d_rate": 0.0,
            "telemetry_completeness": 1.0,
            "cost_coverage": 1.0,
            "observation_coverage": 0.8,
        }
        touch = {"7": {"rate": 0.0}, "30": {"rate": 0.0}}

        result = dashboard.evidence_state(metrics, touch)

        self.assertEqual(result["status"], "needs-attention")
        self.assertIn("reliable first-pass rate below 70%", result["reasons"])

    def test_aggregate_touch_is_unknown_when_any_project_is_missing(self):
        dashboard = self.module("dashboard")
        projects = [
            {"available": True, "touch": {"30": {
                "agent_lines_added": 10, "surviving_lines": 9, "rate": 10.0,
            }}},
            {"available": True, "touch": {"30": {
                "agent_lines_added": 0, "surviving_lines": 0, "rate": None,
                "reason": "no attributable agent commits",
            }}},
        ]

        result = dashboard.aggregate_touch(projects, 30)

        self.assertIsNone(result["rate"])
        self.assertEqual(result["known_projects"], 1)
        self.assertEqual(result["missing_projects"], 1)
        self.assertIn("1 of 2", result["reason"])

    def test_unavailable_project_blocks_evidence_but_not_touch_denominator(self):
        dashboard = self.module("dashboard")
        projects = [
            {"available": True, "touch": {"30": {
                "agent_lines_added": 10, "surviving_lines": 9, "rate": 10.0,
            }}},
            {"available": False, "touch": {"30": {"rate": None}}},
        ]

        result = dashboard.aggregate_touch(projects, 30)

        self.assertAlmostEqual(result["rate"], 10.0)
        self.assertEqual(result["known_projects"], 1)
        self.assertEqual(result["missing_projects"], 0)

    def test_unavailable_project_and_registry_error_block_aggregate_state(self):
        dashboard = self.module("dashboard")
        available = {"available": True, "metrics": dashboard.metrics_from_receipts([]),
                     "touch": {"7": {"rate": None}, "30": {"rate": None}},
                     "invalid_receipts": []}
        unavailable = {"available": False, "metrics": dashboard.metrics_from_receipts([]),
                       "touch": {"7": {"rate": None}, "30": {"rate": None}},
                       "invalid_receipts": []}

        result = dashboard.aggregate_projects([available, unavailable], registry_error_count=1)

        self.assertEqual(result["evidence"]["status"], "needs-attention")
        self.assertIn("1 unavailable project(s)", result["evidence"]["reasons"])
        self.assertIn("1 registry error(s)", result["evidence"]["reasons"])

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

    def test_routes_prefer_served_model_and_cost_requires_source(self):
        dashboard = self.module("dashboard")
        receipts = [
            {
                "status": "accepted",
                "requested_provider": "openai", "requested_model": "gpt-requested",
                "served_provider": "openai", "served_model": "gpt-served",
                "cost_usd": 0.4, "cost_source": "provider-reported", "cost_status": "final",
            },
            {
                "status": "accepted",
                "requested_provider": "moonshot", "requested_model": "kimi-k3",
                "cost_usd": 0.2,
            },
        ]

        metrics = dashboard.metrics_from_receipts(receipts)

        self.assertEqual(metrics["cost_usd_known_sum"], 0.4)
        self.assertEqual(metrics["cost_usd_known_tasks"], 1)
        self.assertEqual(metrics["cost_coverage"], 0.5)
        self.assertEqual(metrics["cost_final_tasks"], 1)
        self.assertEqual(metrics["cost_provisional_tasks"], 0)
        self.assertEqual(metrics["cost_usd_per_accepted"], None)
        self.assertEqual(metrics["routes"], [
            {
                "key": "moonshot/kimi-k3", "provider": "moonshot", "model": "kimi-k3",
                "binding": "requested-unverified", "tasks": 1, "accepted": 1,
                "cost_usd_known_sum": 0, "cost_usd_known_tasks": 0,
            },
            {
                "key": "openai/gpt-served", "provider": "openai", "model": "gpt-served",
                "binding": "served", "tasks": 1, "accepted": 1,
                "cost_usd_known_sum": 0.4, "cost_usd_known_tasks": 1,
            },
        ])

    def test_authority_metrics_separate_protection_from_friction(self):
        dashboard = self.module("dashboard")
        metrics = dashboard.metrics_from_receipts([
            {"status": "accepted", "authority_summary": {
                "bound": True, "events": 6, "allowed_executions": 3,
                "protected_blocks": 1, "friction_blocks": 1,
                "unclassified_blocks": 1,
            }},
            {"status": "accepted"},
        ])

        self.assertEqual(metrics["authority_bound_tasks"], 1)
        self.assertEqual(metrics["authority_coverage"], 0.5)
        self.assertEqual(metrics["boundary_events"], 6)
        self.assertEqual(metrics["protected_blocks"], 1)
        self.assertEqual(metrics["friction_blocks"], 1)
        self.assertEqual(metrics["boundary_friction_rate"], 0.25)

    def test_aggregate_authority_friction_matches_project_denominator(self):
        dashboard = self.module("dashboard")
        metrics = dashboard.metrics_from_receipts([{
            "status": "accepted",
            "authority_summary": {
                "bound": True, "events": 6, "allowed_executions": 3,
                "protected_blocks": 1, "friction_blocks": 1,
                "unclassified_blocks": 1,
            },
        }])
        project = {
            "available": True,
            "metrics": metrics,
            "touch": {
                "7": {"agent_lines_added": 0, "surviving_lines": 0, "rate": 0.0},
                "30": {"agent_lines_added": 0, "surviving_lines": 0, "rate": 0.0},
            },
        }

        aggregate = dashboard.aggregate_projects([project])

        self.assertEqual(aggregate["boundary_friction_rate"], 0.25)

    def test_telemetry_completeness_uses_served_route(self):
        dashboard = self.module("dashboard")
        metrics = dashboard.metrics_from_receipts([{
            "status": "accepted",
            "served_provider": "anthropic",
            "served_model": "claude-opus-5",
            "served_effort": "xhigh",
            "tokens": 100,
            "wall_s": 2,
            "cost_usd": 0.1,
            "cost_source": "provider-reported",
            "cost_status": "final",
        }])

        self.assertEqual(metrics["telemetry_completeness"], 1.0)
        without_provider = dashboard.metrics_from_receipts([{
            "status": "accepted", "served_model": "claude-opus-5",
            "served_effort": "xhigh", "tokens": 100, "wall_s": 2,
        }])
        self.assertEqual(without_provider["telemetry_completeness"], 0.8)

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
                "authority_summary": {"private_detail": "must not escape"},
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
            self.assertEqual(result["metrics"]["telemetry_completeness"], 0.4)
            self.assertEqual(result["recent_tasks"][0]["task_id"], "task-1")
            self.assertNotIn("checks", result["recent_tasks"][0])
            self.assertNotIn("private_prompt", result["recent_tasks"][0])
            self.assertNotIn("authority_summary", result["recent_tasks"][0])

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

    def test_snapshot_keeps_unavailable_projects_visible(self):
        dashboard = self.module("dashboard")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "available")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            registered = self.run_cli(
                "init", "--repo", str(repo), "--registry", str(registry)
            )
            self.assertEqual(registered.returncode, 0, registered.stderr)
            (repo / ".007/receipts/one.receipt.json").write_text(json.dumps({
                "schema": "007-framework/receipt/v1",
                "task_id": "one", "status": "accepted", "first_pass": "yes",
                "repair_rounds": 0, "escape_7d": "pending",
                "model": "unmeasured", "effort": "unmeasured",
                "tokens": "unmeasured", "wall_s": "unmeasured",
                "delta": {"files": 1, "added": 2, "deleted": 0},
            }))
            value = json.loads(registry.read_text())
            value["projects"].append({
                "project_id": "missing", "name": "Missing",
                "path": str(Path(tmp, "gone")),
                "registered_at": "2026-08-30T00:00:00Z",
            })
            registry.write_text(json.dumps(value))
            no_touch = lambda _repo, days: {
                "window_days": days, "agent_commits": 0, "human_commits": 0,
                "agent_lines_added": 0, "surviving_lines": 0,
                "rate": None, "reason": "no attribution",
            }

            snapshot = dashboard.build_snapshot(registry, touch_provider=no_touch)

            self.assertEqual(snapshot["aggregate"]["projects_total"], 2)
            self.assertEqual(snapshot["aggregate"]["projects_available"], 1)
            self.assertEqual(snapshot["aggregate"]["tasks"], 1)
            missing = next(item for item in snapshot["projects"] if item["project_id"] == "missing")
            self.assertFalse(missing["available"])

    def test_touch_cache_reuses_sensor_until_ttl_expires(self):
        dashboard = self.module("dashboard")
        calls = []
        clock = [100.0]

        def sensor(repo, days):
            calls.append((str(repo), days))
            return {"window_days": days, "rate": 1.0}

        cache = dashboard.TouchCache(sensor, ttl=60, clock=lambda: clock[0])
        first = cache(Path("/repo"), 30)
        clock[0] = 159.0
        second = cache(Path("/repo"), 30)
        clock[0] = 161.0
        third = cache(Path("/repo"), 30)

        self.assertIs(first, second)
        self.assertIsNot(second, third)
        self.assertEqual(len(calls), 2)

    def test_server_exposes_only_allowlisted_routes(self):
        dashboard = self.module("dashboard")
        with tempfile.TemporaryDirectory() as tmp:
            static = Path(tmp, "static")
            static.mkdir()
            (static / "index.html").write_text("<!doctype html><title>007</title>")
            (static / "styles.css").write_text("body{}")
            (static / "app.js").write_text("'use strict';")
            registry = Path(tmp, "projects.json")
            server = dashboard.create_server("127.0.0.1", 0, registry, static)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(base + "/api/health") as response:
                    self.assertEqual(json.load(response)["status"], "ok")
                    self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
                with urlopen(base + "/api/snapshot") as response:
                    self.assertEqual(json.load(response)["aggregate"]["projects_total"], 0)
                with self.assertRaises(HTTPError) as denied:
                    urlopen(base + "/api/snapshot?path=/etc")
                self.assertEqual(denied.exception.code, 400)
                denied.exception.close()
                with self.assertRaises(HTTPError) as missing:
                    urlopen(base + "/../SKILL.md")
                self.assertEqual(missing.exception.code, 404)
                missing.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_clean_project_e2e_records_cost_and_enters_snapshot(self):
        dashboard = self.module("dashboard")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "project")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            init = self.run_cli("init", "--repo", str(repo), "--registry", str(registry))
            self.assertEqual(init.returncode, 0, init.stderr)
            begun = self.run_cli("begin", "--repo", str(repo), "--task-id", "e2e-task")
            self.assertEqual(begun.returncode, 0, begun.stderr)
            receipt = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
            receipt["task_id"] = "e2e-task"
            receipt["escape_7d"] = "no"
            source = Path(tmp, "receipt.json")
            source.write_text(json.dumps(receipt))
            recorded = self.run_cli("record", "--repo", str(repo), "--file", str(source))
            self.assertEqual(recorded.returncode, 0, recorded.stderr)

            snapshot = dashboard.build_snapshot(registry, touch_provider=lambda _repo, days: {
                "window_days": days, "agent_lines_added": 0, "surviving_lines": 0,
                "rate": None, "reason": "no attribution",
            })

            self.assertEqual(snapshot["aggregate"]["tasks"], 1)
            self.assertEqual(snapshot["aggregate"]["started_tasks"], 1)
            self.assertEqual(snapshot["aggregate"]["active_tasks"], 0)
            self.assertEqual(snapshot["aggregate"]["observation_coverage"], 1.0)
            self.assertEqual(snapshot["aggregate"]["reliable_first_pass_rate"], 1.0)
            self.assertEqual(snapshot["aggregate"]["cost_usd_per_reliable"], receipt["cost_usd"])
            self.assertEqual(snapshot["aggregate"]["cost_coverage"], 1.0)
            self.assertEqual(snapshot["aggregate"]["cost_usd_per_accepted"], receipt["cost_usd"])
            self.assertEqual(snapshot["aggregate"]["routes"][0]["binding"], "served")
            self.assertEqual(snapshot["measurement_boundary"]["cost_denominator"], "observed-terminal-receipts")
            self.assertEqual(
                snapshot["telemetry_fields"],
                ["provider", "model", "effort", "tokens", "wall_s"],
            )

    def test_snapshot_attaches_observed_activity_without_creating_outcomes(self):
        dashboard = self.module("dashboard")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "project")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            registry = Path(tmp, "state", "projects.json")
            init = self.run_cli("init", "--repo", str(repo), "--registry", str(registry))
            self.assertEqual(init.returncode, 0, init.stderr)
            project_id = json.loads((repo / ".007/project.json").read_text())["project_id"]
            activity = {
                "window_hours": 24, "sessions": 2, "active_sessions": 1,
                "idle_sessions": 1, "tokens_total": 1200,
                "cost_usd_estimate": 0.42, "priced_sessions": 2,
                "unpriced_sessions": 0, "pricing_coverage": 1.0,
                "routes": [], "recent_sessions": [],
            }

            snapshot = dashboard.build_snapshot(
                registry,
                touch_provider=lambda _repo, days: {"window_days": days, "rate": None},
                activity_provider=lambda _entries: {
                    "aggregate": activity,
                    "projects": {project_id: activity},
                    "errors": [],
                },
            )

        self.assertEqual(snapshot["aggregate"]["activity"]["sessions"], 2)
        self.assertEqual(snapshot["projects"][0]["activity"]["tokens_total"], 1200)
        self.assertEqual(snapshot["aggregate"]["tasks"], 0)
        self.assertEqual(snapshot["aggregate"]["accepted"], 0)
        self.assertEqual(snapshot["aggregate"]["evidence"]["status"], "instrumentation-inactive")
        self.assertEqual(snapshot["activity_errors"], [])
        self.assertEqual(snapshot["measurement_boundary"]["cost_authority"], "terminal-receipt")

    def test_dashboard_shell_is_semantic_and_self_contained(self):
        class ShellParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.tags = []
                self.urls = []
                self.live_regions = 0

            def handle_starttag(self, tag, attrs):
                self.tags.append(tag)
                values = dict(attrs)
                for key in ("src", "href"):
                    if values.get(key):
                        self.urls.append(values[key])
                self.live_regions += int("aria-live" in values)

        static = ROOT / "dashboard"
        self.assertTrue((static / "index.html").is_file(), "dashboard shell is missing")
        self.assertTrue((static / "styles.css").is_file(), "dashboard styles are missing")
        self.assertTrue((static / "app.js").is_file(), "dashboard application is missing")
        parser = ShellParser()
        parser.feed((static / "index.html").read_text())

        self.assertTrue({"header", "nav", "main", "section"}.issubset(parser.tags))
        self.assertGreaterEqual(parser.live_regions, 1)
        self.assertEqual(set(parser.urls), {"/styles.css", "/app.js"})
        self.assertFalse(any(url.startswith(("http://", "https://", "//")) for url in parser.urls))

        shell = (static / "index.html").read_text()
        for required_id in (
            'id="instrumentation-panel"', 'id="metric-reliable"',
            'id="metric-reliable-cost"', 'id="reliability-funnel"',
            'id="funnel-started"', 'id="funnel-terminal"',
            'id="funnel-accepted"', 'id="funnel-first-pass"',
            'id="funnel-reliable"', 'id="runtime-activity-panel"',
            'id="activity-sessions"', 'id="activity-active"',
            'id="activity-tokens"', 'id="activity-cost"',
            'id="activity-equivalent-cost"',
            'id="authority-coverage"', 'id="authority-protected"',
            'id="authority-friction"', 'id="authority-friction-detail"',
            'id="authority-unclassified"',
        ):
            self.assertIn(required_id, shell)
        self.assertIn("O 007 está produzindo mais mudanças confiáveis por dólar", shell)
        self.assertIn("Atividade local não é outcome verificado", shell)
        self.assertIn("Codex · Claude · Kimi · Gemini", shell)
        self.assertIn("USD terminal observado", shell)
        self.assertIn('setText("authority-friction-detail"', (static / "app.js").read_text())


if __name__ == "__main__":
    unittest.main()
