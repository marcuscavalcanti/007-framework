import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_choice_observatory import holdout_analysis

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
T0 = 1_790_000_000


class FakeCollector:
    """Stands in for local_activity.ActivityCollector: candidates -> parse -> project_id."""

    def __init__(self, sessions):
        self.sessions = sessions

    def candidates(self, now):
        return [("codex", Path(f"/fake/{i}")) for i in range(len(self.sessions))]

    def parse(self, source, path, now):
        return dict(self.sessions[int(path.name)])

    def project_id(self, session, entries, identities):
        return session.get("_project")

    def identity(self, path):
        return None


class ObservatoryHistoryTests(unittest.TestCase):
    """Thesis D step 2: session metadata outlives the 24 h log lookback so durability can mature (7/30 days)."""

    def setUp(self):
        self.hist = importlib.import_module("observatory_history")
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Path(self.tmp.name, "sessions.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, sid, updated, project="p1", **extra):
        return {"source": "codex", "session_id": sid, "cwd": "/repo", "model": "m", "effort": "low",
                "started_at": "2026-10-22T10:00:00Z", "updated_at": updated, "_project": project,
                "usage": {"total_tokens": 10, "reasoning_output_tokens": 3}, **extra}

    def test_snapshot_keeps_only_opted_in_projects_and_only_metadata(self):
        collector = FakeCollector([self.session("a", "2026-10-22T10:05:00Z", title="PRIVATE prompt text"),
                                   self.session("b", "2026-10-22T10:06:00Z", project="p2"),
                                   self.session("c", "2026-10-22T10:07:00Z", project=None)])
        rows = self.hist.snapshot(collector, entries=[], allowed={"p1"}, now=None)
        self.assertEqual([r["session_id"] for r in rows], ["a"])
        self.assertEqual(set(rows[0]), set(self.hist.FIELDS))
        self.assertEqual((rows[0]["project_id"], rows[0]["total_tokens"], rows[0]["reasoning_output_tokens"]), ("p1", 10, 3))
        self.assertNotIn("PRIVATE", json.dumps(rows))

    def git_repo(self, name, commit_at=T0 + 100):
        repo = Path(self.tmp.name, name)
        repo.mkdir()
        env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
               "GIT_AUTHOR_EMAIL": "t@example.test", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test",
               "GIT_AUTHOR_DATE": f"@{commit_at} +0000", "GIT_COMMITTER_DATE": f"@{commit_at} +0000"}
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "f.txt").write_text("x\n")
        subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "commit", "-qm", "work"], cwd=repo, check=True, env=env)
        (repo / "sub").mkdir()
        return repo.resolve()

    def test_auto_follows_every_project_with_an_active_session_except_the_excluded_ones(self):
        # Marcus, 2026-10-25: durability evidence must come from wherever Codex/Claude sessions are active, not a fixed list.
        free, money = self.git_repo("WorldCup"), self.git_repo("Finance")
        plain = Path(self.tmp.name, "not-git")
        plain.mkdir()
        collector = FakeCollector([self.session("a", "2026-10-22T10:05:00Z", project="p2"),            # registered, not listed
                                   self.session("b", "2026-10-22T10:06:00Z", project=None, cwd=str(free / "sub")),
                                   self.session("c", "2026-10-22T10:07:00Z", project=None, cwd=str(money)),
                                   self.session("d", "2026-10-22T10:08:00Z", project=None, cwd=str(plain)),
                                   self.session("e", "2026-10-22T10:09:00Z", project="p9")])          # registered, excluded
        entries = [{"project_id": "p2", "path": "/x/project-beta"}, {"project_id": "p9", "path": "/x/project-gamma"}]
        manual = self.hist.snapshot(collector, entries, allowed={"p1"}, now=None)
        self.assertEqual(manual, [])
        self.assertEqual(self.hist.snapshot(collector, entries, {"p1"}, None, auto=True, exclude=["finance", "project-gamma"])[1:], [],
                         "a repository under the temporary directory (experiment workspaces) is never followed")
        with mock.patch.object(self.hist, "TEMPORARY", ()):  # this test's repositories live in the temporary directory
            rows = self.hist.snapshot(collector, entries, allowed={"p1"}, now=None, auto=True, exclude=["finance", "project-gamma"])
        self.assertEqual([(r["session_id"], r["project_id"]) for r in rows], [("a", "p2"), ("b", f"git:{free}")])
        self.hist.record(self.store, rows)
        config = {"observatory": {"projects": ["p1"], "auto": True, "exclude": ["Finance", "project-gamma"]}}
        self.assertEqual(self.hist.allowed(config, entries, self.store), {"p1", "p2", f"git:{free}"})
        self.assertEqual(self.hist.allowed({"observatory": {"projects": ["p1"]}}, entries, self.store), {"p1"})

    def test_report_follows_an_unregistered_git_project_by_its_root(self):
        repo = self.git_repo("project-alpha")
        pid = f"git:{repo}"
        self.hist.record(self.store, [{"source": "claude", "session_id": "s", "project_id": pid, "cwd": str(repo), "model": "m",
                                       "effort": "high", "started_at": T0, "updated_at": T0 + 200, "total_tokens": 1,
                                       "reasoning_output_tokens": 0}])
        rows = self.hist.report(self.store, [], pid, allowed={pid}, now=T0 + 40 * 86400, slack_s=0)
        self.assertEqual((len(rows), rows[0]["evidence_level"]), (1, 1))

    def test_projects_on_the_same_repository_compete_for_its_commits(self):
        # project-beta and a Codex worktree of it (~/.codex/worktrees/.../project-beta) are registered apart and now see the same branches
        repo = self.git_repo("project-beta", commit_at=T0 + 100)
        worktree = Path(self.tmp.name, "wt")
        subprocess.run(["git", "worktree", "add", "-q", "--detach", str(worktree)], cwd=repo, check=True, capture_output=True)
        other = self.git_repo("Other", commit_at=T0 + 100)
        entries = [{"project_id": "main", "path": str(repo)}, {"project_id": "wt", "path": str(worktree)},
                   {"project_id": "other", "path": str(other)}]
        self.hist.record(self.store, [{"source": src, "session_id": sid, "project_id": pid, "cwd": "/x", "model": "m",
                                       "effort": "low", "started_at": T0, "updated_at": T0 + 300, "total_tokens": 1,
                                       "reasoning_output_tokens": 0, "active_intervals": [[T0 + start, T0 + 300]]}
                                      for src, sid, pid, start in (("claude", "a", "main", 0), ("codex", "b", "wt", 50),
                                                                   ("codex", "c", "other", 0))])
        allowed = {"main", "wt", "other"}
        for pid in ("main", "wt"):
            row, = self.hist.report(self.store, entries, pid, allowed, now=T0 + 40 * 86400, slack_s=0)
            self.assertEqual((row["commits"], len(row["ambiguous_commits"])), ([], 1), pid)
        row, = self.hist.report(self.store, entries, "other", allowed, now=T0 + 40 * 86400, slack_s=0)
        self.assertEqual((len(row["commits"]), row["ambiguous_commits"]), (1, []), "another repository never competes")

    def test_load_takes_the_session_metadata_from_its_main_log_not_from_a_later_subagent(self):
        base = {"source": "claude", "session_id": "s", "project_id": "p1", "cwd": "/repo", "total_tokens": 100,
                "reasoning_output_tokens": 5}
        main = {**base, "model": "claude-opus-5-5", "effort": "high", "started_at": T0, "updated_at": T0 + 3600,
                "subagent": False, "active_intervals": [[T0, T0 + 3600]]}
        sub = {**base, "model": "claude-haiku-5-5", "effort": "unmeasured", "started_at": T0 + 7000, "updated_at": T0 + 8000,
               "subagent": True, "total_tokens": 7, "active_intervals": [[T0 + 7000, T0 + 8000]]}
        self.hist.record(self.store, [main, sub])
        (row,) = self.hist.load(self.store)
        self.assertEqual((row["model"], row["effort"], row["started_at"], row["total_tokens"]), ("claude-opus-5-5", "high", T0, 100))
        self.assertEqual(row["updated_at"], T0 + 8000)                      # the session lasted until its subagent finished
        self.assertEqual(row["active_intervals"], [[T0, T0 + 3600], [T0 + 7000, T0 + 8000]])
        only_sub = Path(self.tmp.name, "only-sub.jsonl")
        self.hist.record(only_sub, [sub])
        self.assertEqual(self.hist.load(only_sub)[0]["model"], "claude-haiku-5-5")   # no main log seen: the subagent is all we have
        legacy = Path(self.tmp.name, "legacy.jsonl")                        # rows stored before the mark existed
        self.hist.record(legacy, [{k: v for k, v in sub.items() if k != "subagent"}, main])
        self.assertEqual(self.hist.load(legacy)[0]["model"], "claude-opus-5-5")     # a declared main log beats an unmarked row

    def test_record_is_append_only_without_duplicates_and_load_keeps_the_latest(self):
        first = self.hist.snapshot(FakeCollector([self.session("a", "2026-10-22T10:05:00Z")]), [], {"p1"}, None)
        later = self.hist.snapshot(FakeCollector([self.session("a", "2026-10-22T11:00:00Z")]), [], {"p1"}, None)
        self.assertEqual(self.hist.record(self.store, first), 1)
        self.assertEqual(self.hist.record(self.store, first), 0)
        self.assertEqual(self.hist.record(self.store, later), 1)
        self.assertEqual(len(self.store.read_text().splitlines()), 2)
        latest = self.hist.load(self.store)
        self.assertEqual([(r["session_id"], r["updated_at"]) for r in latest], [("a", "2026-10-22T11:00:00Z")])

    def test_a_stored_row_without_intervals_is_recorded_again_once_a_parse_brings_them(self):
        # the store from before active_intervals existed (2026-10-22..25) must gain them, or those days keep the 271 h span
        old = self.hist.snapshot(FakeCollector([self.session("a", "2026-10-22T10:05:00Z")]), [], {"p1"}, None)
        fresh = self.hist.snapshot(FakeCollector([self.session("a", "2026-10-22T10:05:00Z", title="PRIVATE",
                                                               active_intervals=[[T0, T0 + 60]])]), [], {"p1"}, None)
        self.assertIn("active_intervals", self.hist.FIELDS)
        self.assertEqual((old[0]["active_intervals"], fresh[0]["active_intervals"]), (None, [[T0, T0 + 60]]))
        self.assertNotIn("PRIVATE", json.dumps(fresh))
        self.assertEqual(self.hist.record(self.store, old), 1)
        self.assertEqual(self.hist.record(self.store, fresh), 1)
        self.assertEqual(self.hist.record(self.store, fresh), 0)
        self.assertEqual(self.hist.record(self.store, old), 0, "a parse without intervals never replaces one with them")
        self.assertEqual([r["active_intervals"] for r in self.hist.load(self.store)], [[[T0, T0 + 60]]])

    def test_one_session_id_over_several_logs_keeps_the_latest_row_with_the_union_of_their_intervals(self):
        # Claude subagent logs (<session>/subagents/agent-*.jsonl) carry the parent sessionId; the latest row alone can be a
        # 20-minute subagent, and its intervals alone would hand the main session's commits to another session (a guess)
        main = self.session("a", "2026-10-25T18:05:00Z", model="main-model", source="claude",
                            active_intervals=[[T0, T0 + 60], [T0 + 9000, T0 + 9100]])
        sub = self.session("a", "2026-10-25T04:05:00Z", model="sub-model", source="claude", active_intervals=[[T0 + 30, T0 + 5000]])
        rows = self.hist.snapshot(FakeCollector([main, sub]), [], {"p1"}, None)
        self.assertEqual(self.hist.record(self.store, rows), 2)
        self.assertEqual(self.hist.record(self.store, rows), 0, "an older log's row is not appended again on every pass")
        loaded, = self.hist.load(self.store)
        self.assertEqual((loaded["updated_at"], loaded["model"]), ("2026-10-25T18:05:00Z", "main-model"))
        self.assertEqual(loaded["active_intervals"], [[T0, T0 + 5000], [T0 + 9000, T0 + 9100]])

    def codex_row(self, sid, **extra):
        return {"source": "codex", "session_id": sid, "project_id": "p1", "cwd": "/x", "model": "m", "effort": "high",
                "started_at": T0, "updated_at": T0 + 9000, "total_tokens": 1, "reasoning_output_tokens": 0, **extra}

    def test_a_whole_log_read_replaces_the_interval_a_clipped_tail_read_stored(self):
        # 1.6 stored one fake 291 h interval for a 527 MB rollout read from its last 4 MiB; a union of rows would keep it forever
        clipped = self.codex_row("a", active_intervals=[[T0, T0 + 9000]])
        whole = self.codex_row("a", log_id="a", subagent=False, active_intervals=[[T0, T0 + 60], [T0 + 8000, T0 + 9000]])
        self.assertEqual(self.hist.record(self.store, [clipped]), 1)
        self.assertEqual(self.hist.record(self.store, [whole]), 1, "same updated_at, but the parse differs")
        self.assertEqual(self.hist.record(self.store, [whole, clipped]), 0)
        self.assertEqual(self.hist.load(self.store)[0]["active_intervals"], [[T0, T0 + 60], [T0 + 8000, T0 + 9000]])

    def test_codex_children_and_reviews_join_their_root_session_even_when_stored_under_their_own_id(self):
        repo = self.git_repo("project-delta", commit_at=T0 + 5000)
        self.hist.record(self.store, [
            self.codex_row("root", log_id="root", subagent=False, active_intervals=[[T0, T0 + 600]]),
            self.codex_row("root", log_id="worker", subagent=True, model="m2", active_intervals=[[T0 + 4800, T0 + 5200]]),
            self.codex_row("root", log_id="review", subagent=True, model="codex-auto-review", active_intervals=[[T0 + 4900, T0 + 5100]]),
            self.codex_row("legacy", active_intervals=[[T0 + 4900, T0 + 5100]]),  # a child as 1.6 stored it, under its own id
            self.codex_row("root", log_id="legacy", subagent=True, active_intervals=[[T0 + 4900, T0 + 5100]])])
        row, = self.hist.report(self.store, [{"project_id": "p1", "path": str(repo)}], "p1", {"p1"}, now=T0 + 40 * 86400, slack_s=0)
        self.assertEqual((row["session_id"], row["model"], len(row["commits"]), row["ambiguous_commits"]), ("root", "m", 1, []))

    def test_a_linked_worktree_is_one_project_with_its_repository(self):
        repo = self.git_repo("project-zeta")
        worktree = Path(self.tmp.name, "worktrees", "w1", "project-zeta")
        subprocess.run(["git", "worktree", "add", "-q", "--detach", str(worktree)], cwd=repo, check=True, capture_output=True)
        with mock.patch.object(self.hist, "TEMPORARY", ()):  # this test's repositories live in the temporary directory
            self.assertEqual({self.hist.git_root(str(path)) for path in (repo, repo / "sub", worktree)}, {str(repo)})

    def test_auto_follows_a_session_into_the_repository_its_rows_moved_to(self):
        repo, home = self.git_repo("project-eta"), Path(self.tmp.name, "home")
        home.mkdir()
        session = self.session("a", "2026-10-22T10:05:00Z", project=None, cwd=str(home), cwds=[str(home), str(repo / "sub")])
        with mock.patch.object(self.hist, "TEMPORARY", ()):
            rows = self.hist.snapshot(FakeCollector([session]), [], allowed=set(), now=None, auto=True)
        self.assertEqual([r["project_id"] for r in rows], [f"git:{repo}"])

    def test_report_runs_the_observatory_on_an_opted_in_project_and_refuses_others(self):
        repo = Path(self.tmp.name, "repo")
        repo.mkdir()
        env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
               "GIT_AUTHOR_EMAIL": "t@example.test", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test",
               "GIT_AUTHOR_DATE": f"@{T0 + 100} +0000", "GIT_COMMITTER_DATE": f"@{T0 + 100} +0000"}
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "f.txt").write_text("x\n")
        subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "commit", "-qm", "work"], cwd=repo, check=True, env=env)
        stored = [{"source": "codex", "session_id": "a", "project_id": "p1", "cwd": str(repo), "model": "m", "effort": "low",
                   "started_at": T0, "updated_at": T0 + 200, "total_tokens": 10, "reasoning_output_tokens": 3}]
        self.hist.record(self.store, stored)
        entries = [{"project_id": "p1", "path": str(repo)}, {"project_id": "p2", "path": str(repo)}]
        rows = self.hist.report(self.store, entries, "p1", allowed={"p1"}, now=T0 + 40 * 86400, slack_s=0)
        self.assertEqual((len(rows), rows[0]["evidence_level"], rows[0]["model"]), (1, 1, "m"))
        with self.assertRaises(PermissionError):
            self.hist.report(self.store, entries, "p2", allowed={"p1"}, now=T0 + 40 * 86400)
        self.assertNotIn("line_survival", rows[0])  # per-day survival runs only on request (the dashboard never asks)
        asked, = self.hist.report(self.store, entries, "p1", allowed={"p1"}, now=T0 + 40 * 86400, slack_s=0, survival_days=3)
        self.assertEqual(asked["line_survival"], {"added": 1, "alive_by_day": [1, 1, 1], "observed_days": 3})


    def test_calibrations_come_from_configuration_and_only_matching_sessions_get_level_three(self):
        repo = Path(self.tmp.name, "repo")
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        analysis = Path(self.tmp.name, "codex-ANALYSIS.json")
        analysis.write_text(json.dumps(holdout_analysis()))
        config = {"observatory": {"projects": ["p1"], "calibrations": [
            {"project_id": "p1", "cli": "codex", "model": "gpt-x", "analysis": "codex-ANALYSIS.json"},
            {"project_id": "p1", "cli": "claude", "model": "sonnet", "analysis": "missing.json"},
            {"project_id": "p1"}]}}
        calibrations = self.hist.calibrations(config, Path(self.tmp.name))
        self.assertEqual(calibrations[0]["analysis"], str(analysis))
        self.assertEqual(calibrations[0]["sha256"], hashlib.sha256(analysis.read_bytes()).hexdigest())
        self.assertEqual([c["error"] for c in calibrations],
                         [None, "unreadable analysis", "invalid entry in observatory.calibrations"])
        stored = [{"source": src, "session_id": sid, "project_id": "p1", "cwd": str(repo), "model": model, "effort": "xhigh",
                   "started_at": T0, "updated_at": T0 + 600, "total_tokens": 10, "reasoning_output_tokens": 3}
                  for sid, src, model in (("a", "codex", "gpt-x"), ("b", "claude", "sonnet"), ("c", "codex", "other"))]
        self.hist.record(self.store, stored)
        view = self.hist.view(self.store, [{"project_id": "p1", "path": str(repo)}], "p1", {"p1"}, calibrations, T0 + 86400)
        q3 = {s["session_id"]: s["questions"][2] for s in view["sessions"]}
        self.assertEqual((q3["a"]["verdict"], q3["a"]["badge"]), ("above-necessary", "Calibrated"))
        self.assertEqual(q3["a"]["source"], {"analysis": str(analysis), "sha256": calibrations[0]["sha256"]})
        self.assertEqual(q3["b"]["answer"], "no evidence to judge: unreadable calibration analysis (" +
                         str(Path(self.tmp.name, "missing.json")) + ")")
        self.assertEqual(q3["c"]["answer"], "no evidence to judge: codex other not calibrated in this repository")
        summary = view["calibrations"][0]
        self.assertEqual({k: v["verdict"] for k, v in summary["by_effort"].items()},
                         {"low": "cannot-spend-less", "medium": "good-choice", "xhigh": "above-necessary"})
        self.assertIn("immediate acceptance only", summary["limits"])
        self.assertEqual(view["parameters"]["windows_days"], [7, 30])
        self.assertIn("session's activity intervals", view["parameters"]["attribution"])
        self.assertIn("local branches", view["parameters"]["branches"])
        json.dumps(view)  # headless: the view is plain JSON

    def test_render_prints_the_three_questions_with_their_badges(self):
        view = {"opted_in": True, "available": True, "calibrations": [], "parameters": {}, "sessions": [{
            "session_id": "a", "questions": [
                {"question": "What did you run?", "badge": "Observed", "answer": "codex · m"},
                {"question": "Did it last?", "badge": None, "answer": "not attributed: x"},
                {"question": "Could you have spent less?", "badge": "Calibrated", "answer": "good choice: y", "limits": "Limits: z"}]}]}
        text = self.hist.render(view)
        self.assertIn("1. What did you run? [Observed] codex · m", text)
        self.assertIn("2. Did it last? [no badge] not attributed: x", text)
        self.assertIn("3. Could you have spent less? [Calibrated] good choice: y\n     Limits: z", text)


if __name__ == "__main__":
    unittest.main()
