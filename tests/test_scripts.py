import json
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class ScriptContractTests(unittest.TestCase):
    def run_script(self, name, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / name), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_all_scripts_have_help(self):
        for name in ("harness_report.py", "touch_rate.py", "replay_eval.py"):
            with self.subTest(name=name):
                result = self.run_script(name, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout.lower())

    def test_touch_rate_is_not_defined_without_agent_attribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            Path(tmp, "README.md").write_text("human commit\n")
            subprocess.run(["git", "add", "README.md"], cwd=tmp, check=True)
            env = {**os.environ, "GIT_AUTHOR_NAME": "Human", "GIT_AUTHOR_EMAIL": "human@example.test",
                   "GIT_COMMITTER_NAME": "Human", "GIT_COMMITTER_EMAIL": "human@example.test"}
            subprocess.run(["git", "commit", "-qm", "human"], cwd=tmp, check=True, env=env)
            result = self.run_script("touch_rate.py", "--repo", tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("TOUCH-RATE N/D", result.stdout)

    def test_touch_rate_counts_agent_root_commit_as_surviving(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            Path(tmp, "code.py").write_text("answer = 42\n")
            subprocess.run(["git", "add", "code.py"], cwd=tmp, check=True)
            env = {**os.environ, "GIT_AUTHOR_NAME": "Agent Bot", "GIT_AUTHOR_EMAIL": "agent@example.test",
                   "GIT_COMMITTER_NAME": "Agent Bot", "GIT_COMMITTER_EMAIL": "agent@example.test"}
            subprocess.run(["git", "commit", "-qm", "agent root"], cwd=tmp, check=True, env=env)
            result = self.run_script("touch_rate.py", "--repo", tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("TOUCH-RATE≈0.0%", result.stdout)

    def test_replay_rejects_unsafe_task_ids(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            for unsafe in ("../escape", "/absolute", "two words", "x/y", ""):
                with self.subTest(task_id=unsafe):
                    with self.assertRaises(ValueError):
                        replay_eval.validate_task_id(unsafe)
            self.assertEqual(replay_eval.validate_task_id("case-1.safe"), "case-1.safe")
        finally:
            sys.path.pop(0)

    def test_agent_failure_cannot_be_accepted(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            self.assertEqual(replay_eval.grade_cell(0, True), (True, True))
            self.assertEqual(replay_eval.grade_cell(0, False), (True, False))
            self.assertEqual(replay_eval.grade_cell(1, True), (False, False))
            self.assertEqual(replay_eval.grade_cell(-9, True), (False, False))
        finally:
            sys.path.pop(0)

    def test_replay_requires_exact_served_identity_when_policy_is_causal(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            policy = {
                "provider": "openai", "model": "gpt-test", "effort": "medium",
            }
            exact = {
                "schema": "007-framework/runner-receipt/v1",
                "valid": True,
                "requested": policy,
                "served": policy,
                "identity_source": "thread/start",
                "source_sha256": "a" * 64,
                "usage": {"input_tokens": 10, "output_tokens": 2},
                "cost_usd": 0.01,
                "cost_source": "rate-card-estimate",
            }

            identity, failure = replay_eval.validate_served_identity(exact, policy)
            self.assertIsNone(failure)
            self.assertEqual(identity["model"], "gpt-test")
            self.assertEqual(identity["effort"], "medium")

            for value, expected in (
                (None, "served-identity-missing"),
                ({**exact, "served": {**policy, "model": "wrong"}}, "served-model-mismatch"),
                ({**exact, "valid": False}, "runner-invalid"),
                ({**exact, "cost_usd": float("nan")}, "cost-missing"),
            ):
                with self.subTest(expected=expected):
                    identity, failure = replay_eval.validate_served_identity(value, policy)
                    self.assertIsNone(identity)
                    self.assertEqual(failure, expected)
        finally:
            sys.path.pop(0)

    def test_replay_cell_binds_standard_runner_identity_and_cost(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            with tempfile.TemporaryDirectory() as tmp:
                repo = Path(tmp, "repo")
                repo.mkdir()
                subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
                env = {
                    **os.environ,
                    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.test",
                    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.test",
                }
                (repo / "value.txt").write_text("base\n")
                subprocess.run(["git", "add", "value.txt"], cwd=repo, check=True)
                subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True, env=env)
                base = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                    capture_output=True, text=True,
                ).stdout.strip()
                (repo / "value.txt").write_text("accepted\n")
                subprocess.run(["git", "commit", "-qam", "accepted"], cwd=repo, check=True, env=env)
                accepted = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                    capture_output=True, text=True,
                ).stdout.strip()
                output = Path(tmp, "out")
                output.mkdir()
                identity_script = (
                    "import json,sys; from pathlib import Path; "
                    "Path(sys.argv[1]).write_text(json.dumps({"
                    "'schema':'007-framework/runner-receipt/v1','valid':True,"
                    "'requested':{'provider':'openai','model':sys.argv[2],'effort':sys.argv[3]},"
                    "'served':{'provider':'openai','model':sys.argv[2],'effort':sys.argv[3]},"
                    "'identity_source':'test-structured-output','source_sha256':'b'*64,"
                    "'usage':{'input_tokens':10,'output_tokens':2},"
                    "'cost_usd':0.01,'cost_source':'rate-card-estimate'}))"
                )
                config = {
                    "repos": {"repo": str(repo)},
                    "require_served_identity": True,
                    "agent_command": [
                        sys.executable, "-c", identity_script,
                        "{runner_receipt}", "{model}", "{effort}",
                    ],
                    "arms": {"NEW": {
                        "provider": "openai", "model": "gpt-test", "effort": "medium",
                        "doctrine": "minimal",
                    }},
                }
                task = {
                    "id": "identity-cell", "repo": "repo", "base": base,
                    "accepted": accepted, "prompt": "Keep the base valid.",
                    "acceptance": [[sys.executable, "-c",
                        "from pathlib import Path; Path('acceptance-side-effect.bin').write_bytes(b'\\0'); raise SystemExit(0)"]],
                }

                cell = replay_eval.execute_cell(config, task, "NEW", 1, output, 30)

                self.assertTrue(cell["valid"])
                self.assertTrue(cell["accepted"])
                self.assertEqual(cell["served_model"], "gpt-test")
                self.assertEqual(cell["served_effort"], "medium")
                self.assertEqual(cell["cost_usd"], 0.01)
                self.assertEqual(cell["changed_files"], 0)
                self.assertEqual(cell["lines_added"], 0)
                self.assertEqual(cell["lines_deleted"], 0)
                self.assertEqual(cell["dependency_manifests_changed"], [])
                self.assertEqual(cell["binary_files_changed"], [])
                self.assertRegex(cell["runner_receipt_sha256"], r"^[0-9a-f]{64}$")
        finally:
            sys.path.pop(0)

    def test_replay_d0_records_agent_binary_without_marking_it_incomplete(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            with tempfile.TemporaryDirectory() as tmp:
                repo = Path(tmp)
                subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
                (repo / "base.txt").write_text("base\n")
                subprocess.run(["git", "add", "base.txt"], cwd=repo, check=True)
                env = {
                    **os.environ,
                    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.test",
                    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.test",
                }
                subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True, env=env)
                base = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                    capture_output=True, text=True,
                ).stdout.strip()
                (repo / "artifact.bin").write_bytes(b"\0binary")

                result = replay_eval.diagnostics({"base": base, "accepted": base}, repo, repo)

                self.assertTrue(result["d0_complete"])
                self.assertEqual(result["binary_files_changed"], ["artifact.bin"])
                self.assertEqual(result["lines_added"], 0)
                self.assertEqual(result["lines_deleted"], 0)
        finally:
            sys.path.pop(0)

    def test_hidden_acceptance_is_hash_bound_and_restores_agent_bytes(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                workspace = root / "workspace"
                workspace.mkdir()
                target = workspace / "tests" / "test_hidden.py"
                target.parent.mkdir()
                target.write_text("agent-version\n")
                hidden = root / "private-test.py"
                hidden.write_text("controller-version\n")
                digest = __import__("hashlib").sha256(hidden.read_bytes()).hexdigest()
                task = {"hidden_acceptance": [{
                    "source": str(hidden),
                    "target": "tests/test_hidden.py",
                    "sha256": digest,
                }]}

                with replay_eval.hidden_acceptance(task, workspace):
                    self.assertEqual(target.read_text(), "controller-version\n")

                self.assertEqual(target.read_text(), "agent-version\n")
                task["hidden_acceptance"][0]["sha256"] = "0" * 64
                with self.assertRaises(ValueError):
                    with replay_eval.hidden_acceptance(task, workspace):
                        pass
                self.assertEqual(target.read_text(), "agent-version\n")
        finally:
            sys.path.pop(0)

    def test_hidden_acceptance_rejects_workspace_escape(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                workspace = root / "workspace"
                workspace.mkdir()
                hidden = root / "private-test.py"
                hidden.write_text("hidden\n")
                digest = __import__("hashlib").sha256(hidden.read_bytes()).hexdigest()
                task = {"hidden_acceptance": [{
                    "source": str(hidden), "target": "../escape.py", "sha256": digest,
                }]}
                with self.assertRaises(ValueError):
                    with replay_eval.hidden_acceptance(task, workspace):
                        pass
                self.assertFalse((root / "escape.py").exists())
        finally:
            sys.path.pop(0)

    def test_replay_archive_paths_are_unique(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            with tempfile.TemporaryDirectory() as tmp:
                destination = Path(tmp, "case.with-dot")
                first = replay_eval.new_archive_path(destination)
                second = replay_eval.new_archive_path(destination)
                try:
                    self.assertNotEqual(first, second)
                    self.assertEqual(first.parent, Path(tmp))
                    self.assertTrue(first.exists())
                finally:
                    first.unlink(missing_ok=True)
                    second.unlink(missing_ok=True)
        finally:
            sys.path.pop(0)

    def test_report_emits_machine_readable_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp, "task.receipt.json")
            receipt.write_text(json.dumps({"schema": "007-framework/receipt/v1", "status": "accepted", "proof": "unit", "tokens": "unmeasured"}))
            Path(tmp, "foreign.json").write_text("not a receipt")
            result = self.run_script("harness_report.py", "--receipt-dir", tmp, "--format", "json")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["tasks"], 1)
            self.assertEqual(data["accepted"], 1)
            self.assertEqual(data["tokens"], "unmeasured")
            self.assertEqual(data["tokens_known_sum"], 0)
            self.assertEqual(data["tokens_missing_tasks"], 1)

    def test_report_preserves_known_tokens_and_fails_on_malformed_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "known.receipt.json").write_text(json.dumps({
                "schema": "007-framework/receipt/v1", "status": "accepted", "tokens": 120
            }))
            Path(tmp, "missing.receipt.json").write_text(json.dumps({
                "schema": "007-framework/receipt/v1", "status": "blocked", "tokens": "unmeasured"
            }))
            Path(tmp, "broken.receipt.json").write_text("{")
            result = self.run_script("harness_report.py", "--receipt-dir", tmp, "--format", "json")
            self.assertEqual(result.returncode, 1)
            data = json.loads(result.stdout)
            self.assertEqual(data["tasks"], 2)
            self.assertEqual(data["tokens_known_sum"], 120)
            self.assertEqual(data["tokens_known_tasks"], 1)
            self.assertEqual(data["tokens_missing_tasks"], 1)
            self.assertEqual(len(data["invalid_receipts"]), 1)

    def test_report_exposes_mandatory_cost_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "accounted.receipt.json").write_text(json.dumps({
                "schema": "007-framework/receipt/v1", "status": "accepted",
                "tokens": 100, "cost_usd": 0.25,
                "cost_source": "provider-reported", "cost_status": "final",
            }))
            Path(tmp, "missing.receipt.json").write_text(json.dumps({
                "schema": "007-framework/receipt/v1", "status": "blocked",
                "tokens": 50,
            }))

            result = self.run_script("harness_report.py", "--receipt-dir", tmp, "--format", "json")
            data = json.loads(result.stdout)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(data["cost_usd_known_sum"], 0.25)
            self.assertEqual(data["cost_usd_known_tasks"], 1)
            self.assertEqual(data["cost_unaccounted_tasks"], 1)
            self.assertEqual(data["cost_coverage"], 0.5)
            self.assertEqual(data["cost_usd_per_accepted"], 0.25)

    def test_replay_requires_a_preregistered_seed(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            self.assertEqual(replay_eval.experiment_seed({"seed": 17}), 17)
            with self.assertRaises(ValueError):
                replay_eval.experiment_seed({})
            with self.assertRaises(ValueError):
                replay_eval.experiment_seed({"seed": "17"})
        finally:
            sys.path.pop(0)

    def test_replay_extracts_regular_files_and_rejects_links(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp, "fixture.tar")
                with tarfile.open(archive, "w") as bundle:
                    directory = tarfile.TarInfo("nested")
                    directory.type = tarfile.DIRTYPE
                    directory.mode = 0o777
                    bundle.addfile(directory)
                    payload = b"safe\n"
                    regular = tarfile.TarInfo("nested/file.txt")
                    regular.size = len(payload)
                    regular.mode = 0o777
                    bundle.addfile(regular, io.BytesIO(payload))
                    plain = tarfile.TarInfo("plain.txt")
                    plain.size = len(payload)
                    plain.mode = 0o666
                    bundle.addfile(plain, io.BytesIO(payload))
                target = Path(tmp, "regular")
                target.mkdir()
                old_umask = os.umask(0)
                try:
                    replay_eval.extract_archive(archive, target)
                finally:
                    os.umask(old_umask)
                self.assertEqual((target / "nested/file.txt").read_text(), "safe\n")
                self.assertEqual(stat.S_IMODE((target / "nested").stat().st_mode), 0o755)
                self.assertEqual(stat.S_IMODE((target / "nested/file.txt").stat().st_mode), 0o755)
                self.assertEqual(stat.S_IMODE((target / "plain.txt").stat().st_mode), 0o644)

                with tarfile.open(archive, "w") as bundle:
                    link = tarfile.TarInfo("escape")
                    link.type = tarfile.SYMTYPE
                    link.linkname = "../outside"
                    bundle.addfile(link)
                with self.assertRaises(RuntimeError):
                    replay_eval.extract_archive(archive, target)
        finally:
            sys.path.pop(0)

    def test_router_selects_lowest_cost_eligible_route_and_rejects_quality_loss(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import framework_cli
            candidates = [
                {
                    "id": "terra", "command": [sys.executable], "provider": "openai",
                    "model": "gpt-5.6-terra", "effort": "medium",
                    "task_classes": ["implement"], "fallback": True,
                },
                {
                    "id": "sol", "command": [sys.executable], "provider": "openai",
                    "model": "gpt-5.6-sol", "effort": "high",
                    "task_classes": ["implement"],
                },
            ]

            def outcomes(model, cost, wall, escaped=False):
                return [
                    {
                        "task_class": "implement", "status": "accepted",
                        "first_pass": "yes", "repair_rounds": 0,
                        "escape_7d": "yes" if escaped and index == 0 else "no",
                        "served_provider": "openai", "served_model": model,
                        "served_effort": "medium" if "terra" in model else "high",
                        "cost_usd": cost, "cost_source": "rate-card-estimate",
                        "cost_status": "provisional", "wall_s": wall,
                    }
                    for index in range(5)
                ]

            selected = framework_cli.select_route(
                candidates,
                outcomes("gpt-5.6-terra", 0.2, 10) + outcomes("gpt-5.6-sol", 0.8, 8),
                "implement",
            )
            rejected = framework_cli.select_route(
                candidates,
                outcomes("gpt-5.6-terra", 0.2, 10, escaped=True) + outcomes("gpt-5.6-sol", 0.8, 8),
                "implement",
            )

            self.assertEqual(selected["strategy"], "measured")
            self.assertEqual(selected["selected"]["id"], "terra")
            self.assertEqual(selected["selected"]["cost_usd_per_reliable"], 0.2)
            self.assertEqual(rejected["selected"]["id"], "sol")
            self.assertIn("terra", rejected["rejected"])
            self.assertTrue(any("escape" in reason for reason in rejected["rejected"]["terra"]))
        finally:
            sys.path.pop(0)

    def test_router_falls_back_only_to_an_available_configured_candidate(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import framework_cli
            candidates = [
                {
                    "id": "missing", "command": ["definitely-not-installed-007"],
                    "provider": "example", "model": "missing", "effort": "medium",
                    "task_classes": ["implement"], "fallback": True,
                },
                {
                    "id": "available", "command": [sys.executable],
                    "provider": "local", "model": "configured-default", "effort": "medium",
                    "task_classes": ["implement"], "fallback": True,
                },
            ]

            decision = framework_cli.select_route(candidates, [], "implement")

            self.assertEqual(decision["strategy"], "policy-fallback")
            self.assertEqual(decision["selected"]["id"], "available")
            self.assertEqual(decision["eligible_candidates"], 0)
        finally:
            sys.path.pop(0)

    def test_router_blocks_when_no_measured_or_explicit_fallback_exists(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import framework_cli
            candidates = [{
                "id": "available-but-unproved", "command": [sys.executable],
                "provider": "local", "model": "unproved", "effort": "medium",
                "task_classes": ["implement"],
            }]

            decision = framework_cli.select_route(candidates, [], "implement")

            self.assertEqual(decision["strategy"], "blocked")
            self.assertIsNone(decision["selected"])
        finally:
            sys.path.pop(0)

    def test_route_cli_reads_global_config_and_returns_machine_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp, "routes.json")
            registry = Path(tmp, "projects.json")
            config.write_text(json.dumps({
                "schema": "007-framework/routes/v1",
                "candidates": [{
                    "id": "local-default", "command": [sys.executable],
                    "provider": "local", "model": "configured-default",
                    "effort": "medium", "task_classes": ["implement"],
                    "fallback": True,
                }],
            }))
            registry.write_text(json.dumps({
                "schema": "007-framework/registry/v1", "projects": [],
            }))

            result = self.run_script(
                "framework_cli.py", "route", "--task-class", "implement",
                "--config", str(config), "--registry", str(registry), "--format", "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            decision = json.loads(result.stdout)
            self.assertEqual(decision["schema"], "007-framework/route-decision/v1")
            self.assertEqual(decision["strategy"], "policy-fallback")
            self.assertEqual(decision["selected"]["id"], "local-default")

    def test_route_selector_matches_frozen_old_new_mechanism_cells(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import framework_cli
            protocol = json.loads((ROOT / "evidence/v1.4.0/route-selector-protocol.json").read_text())
            expected = json.loads((ROOT / "evidence/v1.4.0/route-selector-result.json").read_text())
            candidates = [
                {
                    "id": "cheap", "command": [sys.executable], "provider": "test",
                    "model": "cheap", "effort": "medium", "task_classes": ["implement"],
                    "fallback": True, "nominal_cost": 0.2,
                },
                {
                    "id": "stable", "command": [sys.executable], "provider": "test",
                    "model": "stable", "effort": "medium", "task_classes": ["implement"],
                    "fallback": True, "nominal_cost": 0.8,
                },
            ]

            def outcomes(model, cost, *, escaped=False, missing_cost=False):
                return [{
                    "task_class": "implement", "status": "accepted", "first_pass": "yes",
                    "repair_rounds": 0, "escape_7d": "yes" if escaped and index == 0 else "no",
                    "served_provider": "test", "served_model": model, "served_effort": "medium",
                    "cost_usd": None if missing_cost else cost,
                    "cost_source": "rate-card-estimate", "cost_status": "provisional", "wall_s": 10,
                } for index in range(5)]

            scenarios = {
                "eligible_control": outcomes("cheap", 0.2) + outcomes("stable", 0.8),
                "quality_regression": outcomes("cheap", 0.2, escaped=True) + outcomes("stable", 0.8),
                "telemetry_gap": outcomes("cheap", 0.2, missing_cost=True) + outcomes("stable", 0.8),
            }
            cells = []
            for scenario in protocol["scenarios"]:
                for replicate in range(1, protocol["replicates"] + 1):
                    old = min(candidates, key=lambda item: item["nominal_cost"])["id"]
                    new = framework_cli.select_route(candidates, scenarios[scenario["id"]], "implement")["selected"]["id"]
                    cells.extend([
                        {"scenario": scenario["id"], "arm": "OLD", "replicate": replicate,
                         "selected": old, "matched": old == scenario["expected_old"]},
                        {"scenario": scenario["id"], "arm": "NEW", "replicate": replicate,
                         "selected": new, "matched": new == scenario["expected_new"]},
                    ])

            self.assertEqual(len(cells), protocol["cells"])
            self.assertTrue(all(cell["matched"] for cell in cells), cells)
            self.assertEqual(expected["matched_cells"], len(cells))
            self.assertEqual(expected["total_cells"], len(cells))
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
