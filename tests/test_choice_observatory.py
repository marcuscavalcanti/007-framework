import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

DAY = 86400
T0 = 1_790_000_000  # fixed epoch for synthetic commits


def commit(repo, when, path, text, message):
    (repo / path).write_text(text)
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.test", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.test", "GIT_AUTHOR_DATE": f"@{when} +0000", "GIT_COMMITTER_DATE": f"@{when} +0000"}
    subprocess.run(["git", "add", path], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True, env=env)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


class ChoiceObservatoryTests(unittest.TestCase):
    """Thesis D observatory, evidence levels 0 and 1 (spec 2026-10-22-007-choice-observatory-design.md)."""

    def setUp(self):
        self.obs = importlib.import_module("choice_observatory")
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name, "repo")
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, sid, start, end, **extra):
        return {"session_id": sid, "source": "codex", "cwd": str(self.repo), "model": "m", "effort": "low",
                "started_at": start, "updated_at": end, **extra}

    def test_commits_attach_to_the_one_session_whose_window_holds_them_never_to_a_guess(self):
        base = commit(self.repo, T0, "base.txt", "base\n", "base")
        inside_a = commit(self.repo, T0 + 1000, "a.txt", "a\n", "a")
        overlap = commit(self.repo, T0 + 5000, "ab.txt", "ab\n", "ab")
        outside = commit(self.repo, T0 + 50000, "c.txt", "c\n", "c")
        sessions = [self.session("A", T0 + 500, T0 + 6000), self.session("B", T0 + 4500, T0 + 9000)]
        result = self.obs.attribute(self.repo, sessions, slack_s=0)
        self.assertEqual(result["sessions"]["A"], [inside_a])
        self.assertEqual(result["sessions"]["B"], [])
        self.assertEqual(result["unattributed"], {overlap: "ambiguous", outside: "no-session", base: "no-session"})

    def test_durability_counts_lines_still_alive_at_the_window_and_waits_until_it_is_mature(self):
        sha = commit(self.repo, T0, "f.txt", "".join(f"line{i}\n" for i in range(10)), "agent work")
        commit(self.repo, T0 + 3 * DAY, "f.txt", "".join(("fixed" if i < 4 else "line") + f"{i}\n" for i in range(10)), "fix")
        result = self.obs.durability(self.repo, [sha], now=T0 + 10 * DAY, windows=(7, 30))
        self.assertEqual(result["7"], {"status": "mature", "lines_added": 10, "lines_surviving": 6, "retouched_rate": 0.4})
        self.assertEqual(result["30"], {"status": "pending", "matures_at": T0 + 30 * DAY})

    def history(self):
        """A at T0 adds 10 lines; later commits retouch them (B day 2.5, D day 6.5, F day 9), C touches another file only."""
        lines = lambda prefix, n: "".join((prefix if i < n else "line") + f"{i}\n" for i in range(10))
        a = commit(self.repo, T0, "f.txt", lines("line", 0), "agent work")
        commit(self.repo, T0 + 2 * DAY + DAY // 2, "f.txt", lines("fixed", 4), "Fix crash")
        commit(self.repo, T0 + 3 * DAY + DAY // 2, "g.txt", "g\n", "fix docs elsewhere")
        commit(self.repo, T0 + 6 * DAY + DAY // 2, "f.txt", lines("named", 6), "rename helpers")
        commit(self.repo, T0 + 9 * DAY, "f.txt", lines("undone", 7), "REVERT rename")
        commit(self.repo, T0 + 50 * DAY, "f.txt", lines("hot", 8), "hotfix after the window")
        return a

    def test_line_survival_gives_the_lines_alive_on_each_day_censored_at_now_and_capped(self):
        a = self.history()
        # day d reads the last HEAD revision on or before T0 + d days; day 4.5 has elapsed 4 whole days
        self.assertEqual(self.obs.line_survival(self.repo, [a], now=T0 + 4 * DAY + DAY // 2),
                         {"added": 10, "alive_by_day": [10, 10, 6, 6], "observed_days": 4})
        self.assertEqual(self.obs.line_survival(self.repo, [a], now=T0 + 40 * DAY, max_days=8),
                         {"added": 10, "alive_by_day": [10, 10, 6, 6, 6, 6, 4, 4], "observed_days": 8})
        self.assertEqual(self.obs.line_survival(self.repo, [a], now=T0 + 3600)["alive_by_day"], [])

    def test_corrective_share_counts_later_commits_on_the_same_files_whose_message_is_corrective(self):
        a = self.history()
        # B "Fix crash" and F "REVERT rename" match (case-insensitive); D does not; C touched another file; the hotfix is after until
        self.assertEqual(self.obs.corrective_share(self.repo, [a], until=T0 + 30 * DAY),
                         {"later_commits": 3, "corrective_commits": 2, "share": 2 / 3})
        self.assertEqual(self.obs.corrective_share(self.repo, [a], until=T0)["share"], None)
        classify = lambda message: bool(self.obs.CORRECTIVE.search(message))
        self.assertEqual([classify(m) for m in ("bugfix in parser", "Regression test", "HOTFIX", "Revert \"x\"", "rename helpers",
                                                "add feature")], [True, True, True, True, False, False])

    def test_observe_adds_line_survival_and_corrective_share_only_when_asked(self):
        a = self.history()
        sessions = [self.session("s", T0 - 10, T0 + 10)]
        plain, = self.obs.observe(self.repo, sessions, now=T0 + 40 * DAY, slack_s=0)
        self.assertNotIn("line_survival", plain)
        self.assertNotIn("corrective_share", plain)
        asked, = self.obs.observe(self.repo, sessions, now=T0 + 40 * DAY, slack_s=0, survival_days=8)
        self.assertEqual((asked["commits"], asked["line_survival"]["alive_by_day"]), ([a], [10, 10, 6, 6, 6, 6, 4, 4]))
        # the corrective window ends with the survival window (last commit + 8 days): F (day 9) is outside
        self.assertEqual(asked["corrective_share"], {"later_commits": 2, "corrective_commits": 1, "share": 0.5})

    def test_ambiguous_commits_are_listed_on_every_session_that_claims_them_and_owned_by_none(self):
        overlap = commit(self.repo, T0 + 5000, "ab.txt", "ab\n", "ab")
        sessions = [self.session("A", T0 + 500, T0 + 6000), self.session("B", T0 + 4500, T0 + 9000)]
        self.assertEqual(self.obs.attribute(self.repo, sessions, slack_s=0)["ambiguous"], {"A": [overlap], "B": [overlap]})
        rows = {r["session_id"]: r for r in self.obs.observe(self.repo, sessions, now=T0 + 40 * DAY, slack_s=0)}
        self.assertEqual((rows["A"]["commits"], rows["A"]["ambiguous_commits"]), ([], [overlap]))

    def test_each_session_states_its_evidence_level(self):
        sha = commit(self.repo, T0 + 100, "g.txt", "g\n", "work")
        sessions = [self.session("worked", T0, T0 + 200), self.session("idle", T0 + 90 * DAY, T0 + 90 * DAY + 10)]
        rows = {r["session_id"]: r for r in self.obs.observe(self.repo, sessions, now=T0 + 40 * DAY, slack_s=0)}
        self.assertEqual((rows["worked"]["evidence_level"], rows["worked"]["commits"]), (1, [sha]))
        self.assertEqual(rows["worked"]["durability"]["7"]["retouched_rate"], 0.0)
        self.assertEqual((rows["idle"]["evidence_level"], rows["idle"]["commits"], rows["idle"]["durability"]), (0, [], None))
        self.assertEqual(rows["worked"]["model"], "m")

    def test_active_intervals_decide_ownership_and_the_session_span_is_only_a_fallback(self):
        # Marcus, 2026-10-25: one Claude session resumed over 271 h made 28 commits ambiguous and short Codex sessions own nothing.
        early = commit(self.repo, T0 + 300, "a.txt", "a\n", "a")
        during_b = commit(self.repo, T0 + 5500, "b.txt", "b\n", "b")
        in_a_pause = commit(self.repo, T0 + 50_000, "c.txt", "c\n", "c")
        both = commit(self.repo, T0 + 95_000, "d.txt", "d\n", "d")
        long_a = self.session("A", T0, T0 + 100_000, active_intervals=[[T0, T0 + 600], [T0 + 90_000, T0 + 100_000]])
        short_b = self.session("B", T0 + 5000, T0 + 6000, active_intervals=[[T0 + 5000, T0 + 6000]])
        no_intervals = self.session("C", T0 + 94_000, T0 + 96_000)
        result = self.obs.attribute(self.repo, [long_a, short_b, no_intervals], slack_s=60)
        self.assertEqual((result["sessions"]["A"], result["sessions"]["B"], result["sessions"]["C"]), ([early], [during_b], []))
        self.assertEqual(result["unattributed"], {in_a_pause: "no-session", both: "ambiguous"})
        self.assertEqual(result["ambiguous"], {"A": [both], "B": [], "C": [both]})
        old_rule = self.obs.attribute(self.repo, [{**s, "active_intervals": None} for s in (long_a, short_b)], slack_s=60)
        self.assertEqual(old_rule["unattributed"][during_b], "ambiguous")
        # slack applies around each interval
        self.assertEqual(self.obs.attribute(self.repo, [{**short_b, "active_intervals": [[T0 + 5600, T0 + 6000]]}], slack_s=100)
                         ["sessions"]["B"], [during_b])

    def git_at(self, when, *args, cwd=None):
        env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
               "GIT_AUTHOR_EMAIL": "t@example.test", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test",
               "GIT_AUTHOR_DATE": f"@{when} +0000", "GIT_COMMITTER_DATE": f"@{when} +0000"}
        return subprocess.run(["git", *args], cwd=cwd or self.repo, check=True, env=env, capture_output=True, text=True).stdout.strip()

    def test_commits_of_every_local_branch_and_worktree_count_but_remote_stash_and_tool_refs_do_not(self):
        main = commit(self.repo, T0 + 10, "m.txt", "m\n", "main")
        branch = self.git_at(T0, "branch", "--show-current")
        self.git_at(T0, "checkout", "-qb", "agent")
        side = commit(self.repo, T0 + 20, "s.txt", "s\n", "side branch")
        self.git_at(T0, "checkout", "-q", branch)
        worktree = Path(self.tmp.name, "wt")
        self.git_at(T0, "worktree", "add", "-q", "--detach", str(worktree))
        detached = commit(worktree, T0 + 30, "w.txt", "w\n", "detached worktree")
        tree = self.git_at(T0, "write-tree")
        for when, ref in ((T0 + 40, "refs/remotes/origin/someone"), (T0 + 50, "refs/codex/snapshots/x"), (T0 + 55, "refs/notes/n")):
            self.git_at(T0, "update-ref", ref, self.git_at(when, "commit-tree", tree, "-p", main, "-m", ref))
        (self.repo / "m.txt").write_text("dirty\n")
        self.git_at(T0 + 60, "stash", "-q")
        sessions = [self.session("A", T0, T0 + 100)]
        self.assertEqual(sorted(self.obs.attribute(self.repo, sessions, slack_s=0)["sessions"]["A"]), sorted([main, side, detached]))

    def test_a_commit_off_head_is_not_integrated_neither_surviving_nor_reworked(self):
        on_head = commit(self.repo, T0 + 100, "f.txt", "".join(f"l{i}\n" for i in range(4)), "merged work")
        branch = self.git_at(T0, "branch", "--show-current")
        self.git_at(T0, "checkout", "-qb", "agent")
        loose = commit(self.repo, T0 + 200, "g.txt", "".join(f"g{i}\n" for i in range(6)), "work not merged yet")
        only_loose = commit(self.repo, T0 + 5000, "h.txt", "h\n", "other work not merged yet")
        self.git_at(T0, "checkout", "-q", branch)
        sessions = [self.session("mixed", T0, T0 + 300), self.session("loose", T0 + 4900, T0 + 5100)]
        rows = {r["session_id"]: r for r in self.obs.observe(self.repo, sessions, now=T0 + 40 * DAY, slack_s=0)}
        mixed = rows["mixed"]
        self.assertEqual((mixed["commits"], mixed["unintegrated_commits"]), ([on_head, loose], [loose]))
        self.assertEqual(mixed["durability"]["7"], {"status": "mature", "lines_added": 4, "lines_surviving": 4, "retouched_rate": 0.0})
        self.assertEqual(mixed["evidence_level"], 1)
        q2 = self.obs.questions(mixed, {"answer": "x"})[1]
        self.assertEqual(q2["badge"], "Linked")
        self.assertTrue(q2["answer"].endswith("; 1 commit(s) not yet merged into the main branch, outside the measurement"), q2["answer"])
        alone = rows["loose"]
        self.assertEqual((alone["commits"], alone["unintegrated_commits"], alone["durability"], alone["evidence_level"]),
                         ([only_loose], [only_loose], None, 0))
        q2 = self.obs.questions(alone, {"answer": "x"})[1]
        self.assertEqual((q2["level"], q2["badge"], q2["windows"]), (None, None, None))
        self.assertEqual(q2["answer"], "commit not yet merged into the main branch (1 commit(s) from the session)")



def arm(accepted, wall, cost, units=39):
    return {"accepted": accepted, "units": units, "wall_per_accepted_s": wall, "cost_per_accepted_usd": cost}


XHIGH = arm(39, 275.88, 0.4157)


def contrast(name, verdict, own, reduction, ci, acceptance_ok):
    return {"verdict": verdict, "acceptance_ok": acceptance_ok, "reduction": reduction, "kill_threshold": 0.25,
            "bootstrap": {"ci95_conditional": ci, "draws": 10000}, name: own, "xhigh": XHIGH}


def holdout_analysis(medium=None, low=None, manipulation=True):
    """Synthetic 007-thesis-d-holdout-analysis/v1; defaults mirror a medium-SURVIVES / low-KILLED executor."""
    return {"schema": "007-thesis-d-holdout-analysis/v1", "tasks": 13, "units": 39, "time_field": "agent_wall_s",
            "manipulation_check_reasoning_monotonic": manipulation,
            "limits": ["corpus = 13 tasks of one repository", "immediate acceptance only"],
            "contrasts": {
                "medium_vs_xhigh": medium or contrast("medium", "SURVIVES", arm(39, 132.88, 0.2367), 0.5183, [0.4431, 0.5786], True),
                "low_vs_xhigh": low or contrast("low", "KILLED", arm(37, 102.73, 0.1876), 0.6276, [0.5941, 0.6614], False)}}


ALL_KILLED = dict(medium=contrast("medium", "KILLED", arm(37, 72.17, 0.079), 0.5058, [0.3928, 0.6217], False),
                  low=contrast("low", "KILLED", arm(36, 48.95, 0.069), 0.6648, [0.5431, 0.7746], False))


class CalibratedTests(unittest.TestCase):
    """Question 3 at evidence level 3 (Calibrated) from a holdout analysis; never "bad", never above the evidence."""

    def setUp(self):
        self.obs = importlib.import_module("choice_observatory")

    def assert_calibrated(self, result, verdict):
        self.assertEqual((result["verdict"], result["level"], result["badge"]), (verdict, 3, "Calibrated"))
        self.assertNotIn("bad", result["answer"].lower())
        self.assertIn("one repository", result["limits"])
        self.assertIn("immediate acceptance only", result["limits"])

    def test_effort_above_a_lower_effort_that_survives_is_above_necessary_with_the_gain_and_its_interval(self):
        result = self.obs.calibrated(holdout_analysis(), "xhigh")
        self.assert_calibrated(result, "above-necessary")
        self.assertIn("effort above what was needed: medium accepted 39/39 vs 39/39 for xhigh", result["answer"])
        self.assertIn("133 s vs 276 s (−52%; 95% CI: 44–58%)", result["answer"])
        self.assertIn("$0.24 vs $0.42 (−43%; no CI)", result["answer"])
        gain = result["gain"]
        self.assertEqual((gain["effort"], gain["time_ci95"], gain["cost_basis"]), ("medium", [0.4431, 0.5786], "experiment receipts"))
        self.assertAlmostEqual(gain["time_reduction"], 1 - 132.88 / 275.88)

    def test_unknown_cost_stays_unknown_never_zero(self):
        medium = contrast("medium", "SURVIVES", arm(39, 132.88, None), 0.5183, [0.4431, 0.5786], True)
        result = self.obs.calibrated(holdout_analysis(medium=medium), "xhigh")
        self.assertIn("cost per accepted delivery N/A", result["answer"])
        self.assertIsNone(result["gain"]["cost_reduction"])

    def test_lowest_effort_that_survives_is_a_good_choice_and_names_the_killed_lower_effort_with_counts(self):
        result = self.obs.calibrated(holdout_analysis(), "medium")
        self.assert_calibrated(result, "good-choice")
        self.assertIn("good choice: medium accepted 39/39 vs 39/39 for xhigh, with −52% agent time", result["answer"])
        self.assertIn("lower effort did not pass: low accepted 37/39 vs 39/39 for xhigh", result["answer"])

    def test_a_ci_report_adds_the_three_confidence_levels_and_the_acceptance_difference(self):
        # Marcus, 2026-10-25: 90%, 95% and 99% intervals; the acceptance difference shows that "same" still has uncertainty
        ci = {"schema": "007-ci-report/v1", "contrasts": {"medium_vs_xhigh": {"intervals": {
            "90": {"acceptance_difference": [-0.06, 0.06], "time_reduction": [0.46, 0.57], "cost_reduction": [0.41, 0.45]},
            "95": {"acceptance_difference": [-0.0897, 0.0897], "time_reduction": [0.44, 0.58], "cost_reduction": [0.41, 0.46]},
            "99": {"acceptance_difference": [-0.15, 0.15], "time_reduction": [0.42, 0.59], "cost_reduction": [0.40, 0.46]}}}}}
        result = self.obs.calibrated(holdout_analysis(), "xhigh", ci=ci)
        self.assert_calibrated(result, "above-necessary")
        self.assertIn("acceptance difference, 95% CI: −9 to +9 pp", result["answer"])
        self.assertIn("CI 90/95/99%: 46–57 / 44–58 / 42–59%", result["answer"])
        self.assertEqual(result["gain"]["intervals"]["99"]["acceptance_difference"], [-0.15, 0.15])
        plain = self.obs.calibrated(holdout_analysis(), "xhigh")              # without a report: the 95% analysis interval only
        self.assertIn("95% CI: 44–58%", plain["answer"])
        self.assertNotIn("90/95/99", plain["answer"])
        self.assertEqual(self.obs.calibrated(holdout_analysis(), "xhigh", ci={"schema": "other"})["answer"], plain["answer"])

    def test_reference_effort_with_every_lower_effort_killed_is_not_called_a_good_choice(self):
        # a margin-0 kill (37/39 vs 39/39) is not evidence that the reference was needed; show the time it costs instead
        result = self.obs.calibrated(holdout_analysis(**ALL_KILLED), "xhigh")
        self.assert_calibrated(result, "no-cheaper-proven")
        self.assertNotIn("good choice", result["answer"])
        self.assertIn("no lower effort passed the experiment's rule (accept as many as xhigh)", result["answer"])
        self.assertRegex(result["answer"], r"medium accepted 37/39 vs 39/39 for xhigh \(−\d+% time per accepted delivery\)")
        self.assertIn("low accepted 36/39 vs 39/39 for xhigh", result["answer"])
        small_gain = contrast("medium", "KILLED", arm(39, 250.0, 0.39), 0.0938, [0.01, 0.2], True)
        self.assertIn("medium accepted 39/39 vs 39/39 for xhigh, but reduced time by only 9% (minimum 25%)",
                      self.obs.calibrated(holdout_analysis(**{**ALL_KILLED, "medium": small_gain}), "xhigh")["answer"])
        inconclusive = {**ALL_KILLED, "low": {**ALL_KILLED["low"], "verdict": "INCONCLUSIVE"}}
        self.assertEqual(self.obs.calibrated(holdout_analysis(**inconclusive), "xhigh")["verdict"], "no-evidence")

    def test_effort_whose_contrast_was_killed_reports_the_counts_never_a_bad_label(self):
        result = self.obs.calibrated(holdout_analysis(), "low")
        self.assert_calibrated(result, "cannot-spend-less")
        self.assertRegex(result["answer"], r"^not proven by the experiment: low accepted 37/39 vs 39/39 for xhigh "
                                           r"\(−\d+% time per accepted delivery\)$")
        self.assertIn("medium accepted 37/39 vs 39/39 for xhigh", self.obs.calibrated(holdout_analysis(**ALL_KILLED), "medium")["answer"])

    def test_lower_surviving_effort_against_a_non_reference_session_has_no_interval(self):
        low = contrast("low", "SURVIVES", arm(39, 100.0, 0.18), 0.6375, [0.59, 0.66], True)
        result = self.obs.calibrated(holdout_analysis(low=low), "medium")
        self.assert_calibrated(result, "above-necessary")
        self.assertIn("100 s vs 133 s (−25%; CI exists only against xhigh)", result["answer"])
        self.assertIsNone(result["gain"]["time_ci95"])

    def test_no_evidence_when_inconclusive_manipulation_failed_or_the_effort_was_not_measured(self):
        inconclusive = {**holdout_analysis()["contrasts"]["medium_vs_xhigh"], "verdict": "INCONCLUSIVE"}
        cases = [(holdout_analysis(manipulation=False), "xhigh", "manipulation check"),
                 (holdout_analysis(medium=inconclusive), "medium", "inconclusive"),
                 (holdout_analysis(), "high", "effort high was not measured"),
                 (holdout_analysis(), "unmeasured", "effort unmeasured was not measured"),
                 ({**holdout_analysis(), "schema": "other/v1"}, "xhigh", "schema"),
                 ({"schema": "007-thesis-d-holdout-analysis/v1", "contrasts": "torn"}, "xhigh", "unreadable")]
        for analysis, effort, reason in cases:
            result = self.obs.calibrated(analysis, effort)
            self.assertEqual((result["verdict"], result["level"], result["badge"]), ("no-evidence", None, None), effort)
            self.assertTrue(result["answer"].startswith("no evidence to judge"), result["answer"])
            self.assertIn(reason, result["answer"])


class QuestionsTests(unittest.TestCase):
    """Questions 1 (Observed) and 2 (Linked) per session, with window maturity explicit."""

    def setUp(self):
        self.obs = importlib.import_module("choice_observatory")
        self.row = {"session_id": "s", "source": "codex", "model": "gpt-x", "effort": "medium",
                    "started_at": "2026-10-01T10:00:00Z", "updated_at": "2026-10-01T10:25:00Z",
                    "total_tokens": 120000, "reasoning_output_tokens": 3400, "commits": ["abc"], "ambiguous_commits": [],
                    "durability": {"7": {"status": "mature", "lines_added": 10, "lines_surviving": 10, "retouched_rate": 0.0},
                                   "30": {"status": "pending", "matures_at": 1793318400}},
                    "evidence_level": 1}
        self.q3 = {"level": None, "badge": None, "verdict": "no-evidence", "answer": "no evidence to judge: x"}

    def test_three_questions_carry_level_badge_and_plain_answers(self):
        q1, q2, q3 = self.obs.questions(self.row, self.q3)
        self.assertEqual((q1["question"], q1["level"], q1["badge"]), ("What did you run?", 0, "Observed"))
        self.assertEqual(q1["answer"], "codex · gpt-x · effort medium · 25 min · 120000 tokens (3400 reasoning)")
        self.assertEqual((q2["question"], q2["level"], q2["badge"]), ("Did it last?", 1, "Linked"))
        self.assertEqual(q2["answer"], "7 days: delivered code that lasted (10/10 lines alive); 30 days: matures on 2026-10-30")
        self.assertEqual(q2["windows"], self.row["durability"])
        long_session = {**self.row, "updated_at": "2026-10-12T09:00:00Z"}
        self.assertIn("· 263 h ·", self.obs.questions(long_session, self.q3)[0]["answer"])
        self.assertEqual((q3["question"], q3["verdict"]), ("Could you have spent less?", "no-evidence"))

    def test_rework_pending_windows_and_ambiguity_are_explicit(self):
        retouched = {**self.row, "durability": {"7": {"status": "mature", "lines_added": 10, "lines_surviving": 6,
                                                      "retouched_rate": 0.4}}}
        self.assertEqual(self.obs.questions(retouched, self.q3)[1]["answer"], "7 days: was corrected (40% of the lines retouched)")
        pending = {**self.row, "evidence_level": 0, "durability": {"7": {"status": "pending", "matures_at": 1793318400}}}
        q2 = self.obs.questions(pending, self.q3)[1]
        self.assertEqual((q2["level"], q2["badge"]), (None, None))
        self.assertEqual(q2["answer"], "no evidence to judge yet: 7 days: matures on 2026-10-30")
        ambiguous = {**self.row, "commits": [], "ambiguous_commits": ["a", "b"], "durability": None, "evidence_level": 0,
                     "effort": "unmeasured", "total_tokens": None}
        q1, q2, _ = self.obs.questions(ambiguous, self.q3)
        self.assertIn("effort unmeasured", q1["answer"])
        self.assertIn("quota N/A", q1["answer"])
        self.assertEqual((q2["level"], q2["answer"]), (None, "not attributed: 2 commit(s) in the window of more than one session"))
        lonely = {**ambiguous, "ambiguous_commits": []}
        self.assertEqual(self.obs.questions(lonely, self.q3)[1]["answer"], "not attributed: no commit in the session's window")


if __name__ == "__main__":
    unittest.main()
