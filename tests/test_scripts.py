import json
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest import mock
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


GRANDCHILD_SPAWNER = (
    "import subprocess, sys, time; "
    "subprocess.Popen([sys.executable, '-c', "
    "'import os, sys, time; open(sys.argv[1], \"w\").write(str(os.getpid())); time.sleep(60)', sys.argv[1]]); "
    "time.sleep(60)"
)


EXIT0_SPAWNER = (
    "import subprocess, sys; "
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
    "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
    "open(sys.argv[1], 'w').write(str(child.pid)); sys.exit(0)"
)


def make_base_repo(tmp):
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
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()
    return repo, base


def reap(pid, process=None):
    try:
        os.kill(pid, 9)
    except ProcessLookupError:
        pass
    if process is not None:
        process.wait(timeout=5)


def process_alive(pid, settle_s=3.0):
    deadline = time.monotonic() + settle_s
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        if time.monotonic() > deadline:
            return True
        time.sleep(0.1)


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

    def test_replay_summary_binds_exact_set_and_replicate_count(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                replay_set = root / "set.json"
                output = root / "out"
                output.mkdir()
                config = {
                    "experiment_id": "experiment-1",
                    "seed": 17,
                    "replicates_per_arm_task": 3,
                }
                replay_set.write_text(json.dumps(config))

                replay_eval.write_summary(output, replay_set, config, 3, [])

                summary = json.loads((output / "summary.json").read_text())
                self.assertEqual(summary["experiment_id"], "experiment-1")
                self.assertEqual(summary["replicates_per_arm_task"], 3)
                self.assertEqual(
                    summary["replay_set_sha256"],
                    __import__("hashlib").sha256(replay_set.read_bytes()).hexdigest(),
                )
        finally:
            sys.path.pop(0)

    def test_replay_rejects_replicate_override_against_frozen_set(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            self.assertEqual(
                replay_eval.experiment_replicates({"replicates_per_arm_task": 3}, None), 3,
            )
            with self.assertRaises(ValueError):
                replay_eval.experiment_replicates({"replicates_per_arm_task": 3}, 2)
        finally:
            sys.path.pop(0)

    def test_replay_arm_order_is_global_across_task_slices(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            schedule = replay_eval.experiment_schedule(
                {"seed": 7007, "tasks": [{"id": "a"}, {"id": "b"}]},
                ["OLD", "NEW"], 3,
            )
            self.assertEqual(
                [schedule[("a", replicate)] for replicate in range(1, 4)],
                [["OLD", "NEW"], ["OLD", "NEW"], ["NEW", "OLD"]],
            )
            self.assertEqual(
                [schedule[("b", replicate)] for replicate in range(1, 4)],
                [["OLD", "NEW"], ["NEW", "OLD"], ["OLD", "NEW"]],
            )
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
            repo = Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
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
            initialized = self.run_script(
                "framework_cli.py", "init", "--repo", str(repo), "--registry", str(registry),
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)

            result = self.run_script(
                "framework_cli.py", "route", "--task-class", "implement",
                "--config", str(config), "--repo", str(repo), "--format", "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            decision = json.loads(result.stdout)
            self.assertEqual(decision["schema"], "007-framework/route-decision/v1")
            self.assertEqual(decision["strategy"], "policy-fallback")
            self.assertEqual(decision["selected"]["id"], "local-default")
            self.assertEqual(decision["evidence_scope"], "repository-local")

            text_result = self.run_script(
                "framework_cli.py", "route", "--task-class", "implement",
                "--config", str(config), "--repo", str(repo),
            )
            self.assertEqual(text_result.returncode, 0, text_result.stderr)
            self.assertIn("[repository-local]", text_result.stdout)

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

    def unavailable_config(self, **overrides):
        return {
            "allow_cost_unavailable": True,
            "cost_unavailable_map": [{
                "observed_cost_status": "UNMEASURED",
                "observed_cost_source": "chatgpt-plan-unpriced-route",
                "normalized_cost_source": "custom:chatgpt-plan",
                "cost_unavailable_reason": "subscription route is unpriced",
                "policy_sha256": "a" * 64,
            }],
            **overrides,
        }

    def unavailable_runner(self, **overrides):
        return {
            "schema": "007-framework/runner-receipt/v1", "valid": True,
            "requested": {"provider": "openai", "model": "gpt-test", "effort": "medium"},
            "served": {"provider": "openai", "model": "gpt-test", "effort": "medium"},
            "identity_source": "test-structured-output", "source_sha256": "b" * 64,
            "cost_usd": None, "cost_status": "UNMEASURED",
            "cost_source": "chatgpt-plan-unpriced-route", "cost_policy_sha256": "a" * 64,
            **overrides,
        }

    def test_replay_cost_unavailable_map_requires_exact_triple_match(self):
        # gate 7
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            policy = {"provider": "openai", "model": "gpt-test", "effort": "medium"}
            mapping = replay_eval.cost_unavailable_map(self.unavailable_config())
            identity, failure = replay_eval.validate_served_identity(self.unavailable_runner(), policy, mapping)
            self.assertIsNone(failure)
            self.assertIsNone(identity["cost_usd"])
            self.assertEqual(identity["cost_status"], "unavailable")
            self.assertEqual(identity["cost_source"], "custom:chatgpt-plan")
            self.assertEqual(identity["cost_unavailable_reason"], "subscription route is unpriced")
            self.assertEqual(identity["cost_status_observed"], "UNMEASURED")
            self.assertEqual(identity["cost_source_observed"], "chatgpt-plan-unpriced-route")
            self.assertEqual(identity["cost_policy_sha256"], "a" * 64)
            for label, overrides in (
                ("status-case", {"cost_status": "unmeasured"}),
                ("source-near", {"cost_source": "chatgpt-plan-unpriced-route-v2"}),
                ("policy-sha", {"cost_policy_sha256": "c" * 64}),
                ("policy-missing", {"cost_policy_sha256": None}),
                ("no-mapping", {}),
            ):
                with self.subTest(label=label):
                    used = None if label == "no-mapping" else mapping
                    self.assertEqual(
                        replay_eval.validate_served_identity(self.unavailable_runner(**overrides), policy, used),
                        (None, "cost-missing"),
                    )
            absent = self.unavailable_runner()
            del absent["cost_usd"]
            self.assertEqual(replay_eval.validate_served_identity(absent, policy, mapping), (None, "cost-missing"))
            priced, failure = replay_eval.validate_served_identity(
                self.unavailable_runner(cost_usd=0.25), policy, mapping,
            )
            self.assertIsNone(failure)
            self.assertEqual(priced["cost_usd"], 0.25)
            self.assertEqual(priced["cost_source"], "chatgpt-plan-unpriced-route")
            self.assertNotIn("cost_status", priced)
            self.assertNotIn("cost_status_observed", priced)
            entry = self.unavailable_config()["cost_unavailable_map"][0]
            for label, config, message in (
                ("duplicate", self.unavailable_config(cost_unavailable_map=[entry, {**entry, "policy_sha256": "d" * 64}]), "duplicate"),
                ("map-without-opt-in", {"cost_unavailable_map": [entry]}, "requires allow_cost_unavailable"),
                ("map-with-false", self.unavailable_config(allow_cost_unavailable=False), "requires allow_cost_unavailable"),
                ("opt-in-without-map", {"allow_cost_unavailable": True}, "requires a cost_unavailable_map"),
                ("non-bool", {"allow_cost_unavailable": "true"}, "must be a boolean"),
                ("bad-namespace", self.unavailable_config(cost_unavailable_map=[{**entry, "normalized_cost_source": "plan"}]), "custom:<name>"),
                ("bad-sha", self.unavailable_config(cost_unavailable_map=[{**entry, "policy_sha256": "xyz"}]), "SHA-256"),
                ("missing-field", self.unavailable_config(cost_unavailable_map=[{**entry, "cost_unavailable_reason": ""}]), "entries require"),
            ):
                with self.subTest(label=label):
                    with self.assertRaisesRegex(ValueError, message):
                        replay_eval.cost_unavailable_map(config)
            self.assertEqual(replay_eval.cost_unavailable_map({}), {})
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as tmp:
            replay_set = Path(tmp, "set.json")
            replay_set.write_text(json.dumps({
                **self.unavailable_config(cost_unavailable_map=[entry, entry]),
                "seed": 1, "repos": {}, "arms": {"NEW": {}}, "agent_command": [], "tasks": [],
            }))
            result = self.run_script("replay_eval.py", "--set", str(replay_set), "run", "--out", str(Path(tmp, "out")))
            self.assertEqual(result.returncode, 2)
            self.assertIn("duplicate cost_unavailable_map entry", result.stderr)
            self.assertFalse(Path(tmp, "out").exists())

    def test_replay_cell_records_observed_and_normalized_unavailable_cost(self):
        # gate 6 (cell side); usage absent from the runner receipt stays unmeasured in the cell
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
                    ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True,
                ).stdout.strip()
                output = Path(tmp, "out")
                output.mkdir()
                runner = Path(tmp, "runner.json")
                runner.write_text(json.dumps(self.unavailable_runner()))
                config = {
                    **self.unavailable_config(),
                    "repos": {"repo": str(repo)},
                    "require_served_identity": True,
                    "agent_command": [sys.executable, "-c", "import shutil,sys; shutil.copy(sys.argv[1], sys.argv[2])",
                                      str(runner), "{runner_receipt}"],
                    "arms": {"NEW": {"provider": "openai", "model": "gpt-test", "effort": "medium", "doctrine": "minimal"}},
                }
                task = {
                    "id": "unpriced-cell", "repo": "repo", "base": base, "accepted": base,
                    "prompt": "Keep the base valid.", "acceptance": [[sys.executable, "-c", "raise SystemExit(0)"]],
                }

                cell = replay_eval.execute_cell(config, task, "NEW", 1, output, 30)

                self.assertTrue(cell["valid"])
                self.assertEqual(cell["failure_class"], "none")
                self.assertIsNone(cell["cost_usd"])
                self.assertEqual(cell["cost_status"], "unavailable")
                self.assertEqual(cell["cost_source"], "custom:chatgpt-plan")
                self.assertEqual(cell["cost_unavailable_reason"], "subscription route is unpriced")
                self.assertEqual(cell["cost_status_observed"], "UNMEASURED")
                self.assertEqual(cell["cost_source_observed"], "chatgpt-plan-unpriced-route")
                self.assertEqual(cell["cost_policy_sha256"], "a" * 64)
                self.assertEqual(json.loads(runner.read_text())["cost_status"], "UNMEASURED")
                self.assertEqual(cell["usage"], "unmeasured")
                self.assertEqual(cell["tokens"], "unmeasured")
        finally:
            sys.path.pop(0)

    def test_replay_usage_structure_is_validated_not_interpreted(self):
        # structure only: absent/null stay unmeasured, non-object and bad counters fail closed,
        # unknown keys are preserved verbatim, nothing is summed or derived
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            policy = {"provider": "openai", "model": "gpt-test", "effort": "medium"}

            def identity(**overrides):
                return replay_eval.validate_served_identity(
                    self.unavailable_runner(cost_usd=0.01, **overrides), policy,
                )

            absent = self.unavailable_runner(cost_usd=0.01)
            self.assertNotIn("usage", absent)
            self.assertEqual(replay_eval.validate_served_identity(absent, policy)[1], None)
            self.assertIsNone(replay_eval.validate_served_identity(absent, policy)[0]["usage"])
            explicit_null, failure = identity(usage=None)
            self.assertIsNone(failure)
            self.assertIsNone(explicit_null["usage"])
            for label, usage in (
                ("full", {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}),
                ("no-total", {"input_tokens": 10, "output_tokens": 2}),
                ("empty", {}),
                ("zero", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}),
                ("big-int", {"total_tokens": 10 ** 30}),
                ("no-relation-check", {"input_tokens": 20, "output_tokens": 5, "total_tokens": 12}),
                ("unknown-preserved", {
                    "total_tokens": 3, "cached_input_tokens": 8, "reasoning_output_tokens": "n/a",
                    "vendor_tokens": None, "provider_extra": [1, 2],
                }),
            ):
                with self.subTest(label=label):
                    result, failure = identity(usage=dict(usage))
                    self.assertIsNone(failure)
                    self.assertEqual(result["usage"], usage)
            self.assertNotIn("total_tokens", identity(usage={"input_tokens": 10, "output_tokens": 2})[0]["usage"])
            for label, usage in (
                ("string", "not-an-object"), ("list", []), ("bool", True), ("int", 12),
                ("total-string", {"total_tokens": "12"}), ("total-bool", {"total_tokens": True}),
                ("total-negative", {"total_tokens": -1}), ("total-fraction", {"total_tokens": 12.5}),
                ("total-float-whole", {"total_tokens": 12.0}), ("total-nan", {"total_tokens": float("nan")}),
                ("total-inf", {"total_tokens": float("inf")}), ("total-null", {"total_tokens": None}),
                ("input-null", {"input_tokens": None, "total_tokens": 1}),
                ("input-negative", {"input_tokens": -5}), ("output-bool", {"output_tokens": False}),
                ("output-fraction", {"output_tokens": 0.5}),
            ):
                with self.subTest(label=label):
                    self.assertEqual(identity(usage=usage), (None, "usage-invalid"))
        finally:
            sys.path.pop(0)

    def test_replay_run_stops_on_invalid_usage_before_next_executor(self):
        # public execution path: an invalid usage produces an invalid cell and exit 2 before the next cell
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
                ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True,
            ).stdout.strip()
            runner = Path(tmp, "runner.json")
            runner.write_text(json.dumps(self.unavailable_runner(cost_usd=0.01, usage={"total_tokens": "12"})))
            launches = Path(tmp, "launches.txt")
            replay_set = Path(tmp, "set.json")
            replay_set.write_text(json.dumps({
                "seed": 3, "replicates_per_arm_task": 2,
                "repos": {"repo": str(repo)}, "require_served_identity": True,
                "agent_command": [
                    sys.executable, "-c",
                    "import shutil,sys; open(sys.argv[3],'a').write('x'); shutil.copy(sys.argv[1], sys.argv[2])",
                    str(runner), "{runner_receipt}", str(launches),
                ],
                "arms": {"NEW": {"provider": "openai", "model": "gpt-test", "effort": "medium", "doctrine": "minimal"}},
                "tasks": [{
                    "id": "usage-cell", "repo": "repo", "base": base, "accepted": base,
                    "prompt": "Keep the base valid.", "acceptance": [[sys.executable, "-c", "raise SystemExit(0)"]],
                }],
            }))
            output = Path(tmp, "out")

            result = self.run_script(
                "replay_eval.py", "--set", str(replay_set), "run", "--arms", "NEW", "--out", str(output),
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("invalid cell: usage-cell r01 NEW; stopped", result.stderr)
            self.assertEqual(launches.read_text(), "x")
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(len(summary["cells"]), 1)
            cell = summary["cells"][0]
            self.assertFalse(cell["valid"])
            self.assertEqual(cell["failure_class"], "usage-invalid")
            self.assertEqual(cell["usage"], "unmeasured")
            self.assertEqual(cell["tokens"], "unmeasured")
            self.assertFalse((output / "usage-cell-r02-NEW.json").exists())

    def test_router_excludes_unavailable_cost_route_without_implicit_fallback(self):
        # gate 11
        sys.path.insert(0, str(SCRIPTS))
        try:
            import framework_cli

            def outcomes(model, cost):
                return [
                    {
                        "task_class": "implement", "status": "accepted", "first_pass": "yes",
                        "repair_rounds": 0, "escape_7d": "no", "served_provider": "openai",
                        "served_model": model, "served_effort": "medium", "wall_s": 5,
                        **({"cost_usd": cost, "cost_source": "rate-card-estimate", "cost_status": "provisional"}
                           if cost is not None else {
                               "cost_usd": None, "cost_status": "unavailable",
                               "cost_source": "custom:chatgpt-plan", "cost_unavailable_reason": "unpriced",
                           }),
                    }
                    for _ in range(5)
                ]

            def candidate(identifier, model, **extra):
                return {
                    "id": identifier, "command": [sys.executable], "provider": "openai",
                    "model": model, "effort": "medium", "task_classes": ["implement"], **extra,
                }

            receipts = outcomes("gpt-unpriced", None) + outcomes("gpt-priced", 9.0)
            decision = framework_cli.select_route(
                [candidate("unpriced", "gpt-unpriced"), candidate("priced", "gpt-priced")], receipts, "implement",
            )
            self.assertEqual(decision["strategy"], "measured")
            self.assertEqual(decision["selected"]["id"], "priced")
            self.assertIn("cost coverage incomplete", decision["rejected"]["unpriced"])
            blocked = framework_cli.select_route([candidate("unpriced", "gpt-unpriced")], receipts, "implement")
            self.assertEqual(blocked["strategy"], "blocked")
            self.assertIsNone(blocked["selected"])
            explicit = framework_cli.select_route(
                [candidate("unpriced", "gpt-unpriced", fallback=True)], receipts, "implement",
            )
            self.assertEqual(explicit["strategy"], "policy-fallback")
            self.assertEqual(explicit["eligible_candidates"], 0)
        finally:
            sys.path.pop(0)

    def test_replay_timeout_kills_agent_descendants(self):
        # public cell path: a timed-out agent and its grandchild are gone; the cell is invalid as timeout
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
                    ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True,
                ).stdout.strip()
                output = Path(tmp, "out")
                output.mkdir()
                pidfile = Path(tmp, "grandchild.pid")
                config = {
                    "repos": {"repo": str(repo)},
                    "agent_command": [sys.executable, "-c", GRANDCHILD_SPAWNER, str(pidfile)],
                    "arms": {"NEW": {"model": "gpt-test", "effort": "medium", "doctrine": "minimal"}},
                }
                task = {
                    "id": "timeout-cell", "repo": "repo", "base": base, "accepted": base,
                    "prompt": "Never finish.", "acceptance": [[sys.executable, "-c", "raise SystemExit(0)"]],
                }

                cell = replay_eval.execute_cell(config, task, "NEW", 1, output, 1)

                self.addCleanup(reap, int(pidfile.read_text()))
                self.assertEqual(cell["failure_class"], "timeout")
                self.assertEqual(cell["agent_exit"], -9)
                self.assertFalse(cell["valid"])
                self.assertLess(cell["wall_s"], 20)
                self.assertFalse(process_alive(int(pidfile.read_text())), "grandchild survived the timeout")
        finally:
            sys.path.pop(0)

    def test_replay_run_kills_descendants_after_normal_exit(self):
        # main command exits 0 at once and leaves a detached-stdio descendant in its group
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            with tempfile.TemporaryDirectory() as tmp:
                pidfile = Path(tmp, "grandchild.pid")

                completed = replay_eval.run([sys.executable, "-c", EXIT0_SPAWNER, str(pidfile)], timeout=10)

                self.addCleanup(reap, int(pidfile.read_text()))
                self.assertEqual(completed.returncode, 0)
                self.assertFalse(process_alive(int(pidfile.read_text())), "grandchild survived a normal exit")
        finally:
            sys.path.pop(0)

    def test_cleanup_states_are_derived_from_bounded_waits(self):
        # deterministic: killpg, wait and the clock are substituted at the existing boundary
        sys.path.insert(0, str(SCRIPTS))
        try:
            import framework_cli
            import replay_eval

            class FakeProcess:
                def __init__(self, wait_behaviour):
                    self.pid, self.returncode, self.waits, self.wait_behaviour = 4242, None, [], wait_behaviour

                def wait(self, timeout=None):
                    self.waits.append(timeout)
                    if self.wait_behaviour == "hang":
                        raise subprocess.TimeoutExpired("cmd", timeout)
                    self.returncode = 0

            for module in (replay_eval, framework_cli):
                with self.subTest(module=module.__name__, case="gone-before-signal"):
                    process = FakeProcess("ok")
                    with mock.patch.object(os, "killpg", side_effect=ProcessLookupError):
                        self.assertEqual(module.kill_process_group(process, wait_s=2.0), "gone")
                    self.assertEqual(process.waits, [])
                with self.subTest(module=module.__name__, case="child-unconfirmed"):
                    process = FakeProcess("hang")
                    with mock.patch.object(os, "killpg", return_value=None):
                        self.assertEqual(module.kill_process_group(process, wait_s=2.0), "cleanup-child-unconfirmed")
                    self.assertEqual(len(process.waits), 1)
                    self.assertGreaterEqual(process.waits[0], 0.0)
                    self.assertLessEqual(process.waits[0], 2.0)
                with self.subTest(module=module.__name__, case="group-observable"):
                    process = FakeProcess("ok")
                    clock = iter(float(tick) for tick in range(100))
                    with mock.patch.object(os, "killpg", return_value=None), \
                            mock.patch.object(time, "monotonic", side_effect=lambda: next(clock)), \
                            mock.patch.object(time, "sleep", return_value=None):
                        self.assertEqual(module.kill_process_group(process, wait_s=2.0), "cleanup-group-observable")
                    self.assertLess(next(clock), 10.0)
                with self.subTest(module=module.__name__, case="gone-after-signal"):
                    process = FakeProcess("ok")
                    with mock.patch.object(os, "killpg", side_effect=[None, ProcessLookupError]):
                        self.assertEqual(module.kill_process_group(process, wait_s=2.0), "gone")
                with self.subTest(module=module.__name__, case="eperm-at-signal"):
                    process = FakeProcess("ok")
                    with mock.patch.object(os, "killpg", side_effect=PermissionError):
                        self.assertEqual(module.kill_process_group(process, wait_s=2.0), "cleanup-group-observable")
                    self.assertEqual(process.waits, [])
                with self.subTest(module=module.__name__, case="eperm-at-poll"):
                    process = FakeProcess("ok")
                    with mock.patch.object(os, "killpg", side_effect=[None, PermissionError]):
                        self.assertEqual(module.kill_process_group(process, wait_s=2.0), "cleanup-group-observable")
        finally:
            sys.path.pop(0)

    def test_cleanup_exception_closes_pipes_and_keeps_original_context(self):
        # an unexpected exception inside cleanup must not leak pipes nor hide the timeout
        sys.path.insert(0, str(SCRIPTS))
        try:
            import framework_cli
            import replay_eval
            started = []
            real_popen = subprocess.Popen

            class RecordingPopen(real_popen):
                def __init__(self, args, *a, **k):
                    super().__init__(args, *a, **k)
                    started.append(self)

            def pipes_closed(process):
                return all(s is None or s.closed for s in (process.stdin, process.stdout, process.stderr))

            with mock.patch.object(subprocess, "Popen", RecordingPopen):
                with mock.patch.object(replay_eval, "kill_process_group", side_effect=RuntimeError("cleanup boom")):
                    with self.assertRaisesRegex(RuntimeError, "cleanup boom") as caught:
                        replay_eval.run([sys.executable, "-c", "import time; time.sleep(60)"], timeout=1)
                self.addCleanup(reap, started[-1].pid, started[-1])
                self.assertIsInstance(caught.exception.__context__, subprocess.TimeoutExpired)
                self.assertTrue(pipes_closed(started[-1]))
                with tempfile.TemporaryDirectory() as tmp:
                    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
                    task = {"acceptance": {"schema": framework_cli.ACCEPTANCE_SCHEMA, "timeout_s": 1,
                                           "commands": [[sys.executable, "-c", "import time; time.sleep(60)"]]}}
                    with mock.patch.object(framework_cli, "kill_process_group", side_effect=RuntimeError("cleanup boom")):
                        with self.assertRaisesRegex(RuntimeError, "cleanup boom") as caught:
                            framework_cli.run_acceptance(tmp, task)
                    self.addCleanup(reap, started[-1].pid, started[-1])
                    self.assertIsInstance(caught.exception.__cause__, subprocess.TimeoutExpired)
                    self.assertTrue(pipes_closed(started[-1]))
        finally:
            sys.path.pop(0)

    def cleanup_stub(self, module, failing, state):
        # substitutes only the reported state: the real kill still runs so no process is left behind
        real = module.kill_process_group

        def fake(process, wait_s=2.0):
            observed = real(process, wait_s)
            return state if failing(process.args) else observed
        return fake

    def test_replay_cell_is_invalid_and_skips_acceptance_when_cleanup_unconfirmed(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            with tempfile.TemporaryDirectory() as tmp:
                repo, base = make_base_repo(tmp)
                marker = Path(tmp, "acceptance-ran")
                task = {
                    "id": "cleanup-cell", "repo": "repo", "base": base, "accepted": base,
                    "prompt": "Exit.", "acceptance": [[sys.executable, "-c", f"open({str(marker)!r}, 'w').write('x')"]],
                }
                arms = {"NEW": {"model": "gpt-test", "effort": "medium", "doctrine": "minimal"}}
                not_git = lambda args: args[0] != "git"
                for label, agent, timeout_s, state, expected_exit, expected_tail in (
                    ("normal-exit", "raise SystemExit(0)", 30, "cleanup-group-observable", 0, ""),
                    ("timeout", "import time; time.sleep(60)", 1, "cleanup-child-unconfirmed", -9, "TIMEOUT"),
                ):
                    with self.subTest(label=label):
                        output = Path(tmp, f"out-{label}")
                        output.mkdir()
                        config = {"repos": {"repo": str(repo)}, "agent_command": [sys.executable, "-c", agent], "arms": arms}
                        with mock.patch.object(replay_eval, "kill_process_group", self.cleanup_stub(replay_eval, not_git, state)):
                            cell = replay_eval.execute_cell(config, task, "NEW", 1, output, timeout_s)
                        self.assertFalse(cell["valid"])
                        self.assertFalse(cell["accepted"])
                        self.assertEqual(cell["failure_class"], state)
                        self.assertEqual(cell["agent_exit"], expected_exit)
                        self.assertEqual(cell["agent_tail"], expected_tail if expected_tail else cell["agent_tail"])
                        self.assertEqual(cell["acceptance"], [])
                        self.assertFalse(marker.exists(), "acceptance ran after an unconfirmed cleanup")
                        self.assertTrue((output / "cleanup-cell-r01-NEW.json").is_file())
                with self.subTest(label="acceptance-command-cleanup"):
                    output = Path(tmp, "out-acceptance")
                    output.mkdir()
                    config = {"repos": {"repo": str(repo)}, "agent_command": [sys.executable, "-c", "raise SystemExit(0)"], "arms": arms}
                    is_acceptance = lambda args: args[0] != "git" and "acceptance-ran" in " ".join(args)
                    with mock.patch.object(replay_eval, "kill_process_group", self.cleanup_stub(replay_eval, is_acceptance, "cleanup-group-observable")):
                        cell = replay_eval.execute_cell(config, task, "NEW", 1, output, 30)
                    self.assertFalse(cell["valid"])
                    self.assertEqual(cell["failure_class"], "cleanup-group-observable")
                    self.assertEqual(cell["agent_exit"], 0)
        finally:
            sys.path.pop(0)

    def test_replay_helper_cleanup_failure_stops_before_agent(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import replay_eval
            with tempfile.TemporaryDirectory() as tmp:
                repo, base = make_base_repo(tmp)
                output = Path(tmp, "out")
                output.mkdir()
                launched = Path(tmp, "agent-launched")
                config = {
                    "repos": {"repo": str(repo)},
                    "agent_command": [sys.executable, "-c", f"open({str(launched)!r}, 'w').write('x')"],
                    "arms": {"NEW": {"model": "gpt-test", "effort": "medium", "doctrine": "minimal"}},
                }
                task = {"id": "helper-cell", "repo": "repo", "base": base, "accepted": base, "prompt": "Exit.", "acceptance": []}
                is_git = lambda args: args[0] == "git"
                with mock.patch.object(replay_eval, "kill_process_group", self.cleanup_stub(replay_eval, is_git, "cleanup-group-observable")):
                    with self.assertRaisesRegex(replay_eval.CleanupIncomplete, "cleanup-group-observable: process group"):
                        replay_eval.execute_cell(config, task, "NEW", 1, output, 30)
                self.assertFalse(launched.exists(), "agent started after a helper cleanup failure")
                self.assertEqual(list(output.iterdir()), [])
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
