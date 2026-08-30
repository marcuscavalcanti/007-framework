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


if __name__ == "__main__":
    unittest.main()
