"""`007 trial`: per-run arm assignment and content-based line survival, on a throwaway git repository."""
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import line_trial as trial


def git(repo, *args, date=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return subprocess.run(["git", "-C", str(repo), *args], env=env, capture_output=True, text=True, check=True).stdout


def commit(repo, name, text, date):
    (repo / name).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "c", date=date)
    return git(repo, "rev-parse", "HEAD").strip()


class LineTrial(unittest.TestCase):
    def test_assignment_is_deterministic_and_roughly_balanced(self):
        self.assertEqual(trial.assign("s", "run-1"), trial.assign("s", "run-1"))
        counts = Counter(trial.assign("seed", f"run-{i}") for i in range(400))
        self.assertGreater(min(counts.values()), 160)
        self.assertEqual(set(counts), {"medium", "high"})

    def test_survival_counts_recorded_lines_by_content_after_the_window(self):
        with tempfile.TemporaryDirectory() as d:
            repo, ledger = Path(d) / "r", Path(d) / "ledger.jsonl"
            repo.mkdir()
            git(repo, "init", "-qb", "main")
            base = commit(repo, "app.py", "def keep():\n    return 1\n", "2026-01-01T00:00:00Z")
            body = "".join(f"value_{i} = compute({i})\n" for i in range(10)) + "}\n\n"
            commit(repo, "app.py", "def keep():\n    return 1\n" + body, "2026-01-02T00:00:00Z")
            entry = trial.record(repo, "run-1", "medium", base, ledger)
            self.assertEqual(entry["added"], 10)  # "}" and the blank line are not recorded
            # stamp the run in the past so the 30-day window has matured; then half the lines are rewritten on day 3
            data = json.loads(ledger.read_text())
            data["at"] = 1767312000  # 2026-01-02T00:00:00Z
            ledger.write_text(json.dumps(data) + "\n")
            rewritten = "".join(f"value_{i} = compute({i})\n" for i in range(5)) + "".join(f"value_{i} = other({i})\n" for i in range(5, 10))
            commit(repo, "app.py", "def keep():\n    return 1\n" + rewritten, "2026-01-05T00:00:00Z")
            out = trial.survival(repo, ledger, days=30, now=1767312000 + 40 * 86400)
            self.assertEqual(out[0]["status"], "mature")
            self.assertEqual((out[0]["added"], out[0]["alive"]), (10, 5))
            self.assertEqual(trial.survival(repo, ledger, days=30, now=1767312000 + 86400)[0]["status"], "pending")

    def test_worktree_record_counts_files_the_run_created(self):
        with tempfile.TemporaryDirectory() as d:
            repo, ledger = Path(d) / "r", Path(d) / "ledger.jsonl"
            repo.mkdir()
            git(repo, "init", "-qb", "main")
            base = commit(repo, "a.py", "x = 1\n", "2026-01-01T00:00:00Z")
            (repo / "a.py").write_text("x = 1\nalpha = beta(1)\n")
            (repo / "new_module.py").write_text("gamma = delta(2)\nepsilon = zeta(3)\n")  # untracked, as an agent leaves it
            entry = trial.record(repo, "run-1", "medium", base, ledger, worktree=True)
            self.assertEqual(entry["added"], 3)
            self.assertEqual(sorted(json.loads(ledger.read_text())["files"]), ["a.py", "new_module.py"])
            self.assertEqual(git(repo, "status", "--short").count("\n"), 2)  # the repository is only read

    def test_a_deleted_file_counts_as_lost(self):
        with tempfile.TemporaryDirectory() as d:
            repo, ledger = Path(d) / "r", Path(d) / "ledger.jsonl"
            repo.mkdir()
            git(repo, "init", "-qb", "main")
            base = commit(repo, "a.py", "x = 1\n", "2026-01-01T00:00:00Z")
            commit(repo, "b.py", "alpha = beta(1)\ngamma = delta(2)\n", "2026-01-02T00:00:00Z")
            entry = json.loads(json.dumps(trial.record(repo, "r", "high", base, ledger)))
            self.assertEqual(entry["added"], 2)
            git(repo, "rm", "-q", "b.py")
            git(repo, "commit", "-qm", "rm", date="2026-01-03T00:00:00Z")
            self.assertEqual(trial.alive(repo, json.loads(ledger.read_text()), "HEAD"), 0)


if __name__ == "__main__":
    unittest.main()
