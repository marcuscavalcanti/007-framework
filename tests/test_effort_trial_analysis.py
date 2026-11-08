from datetime import datetime, timezone
from fractions import Fraction
import importlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def session(arm, project, added, surviving, compliant=True, reasoning=None, mature=True):
    durability = {"7": {"status": "mature", "lines_added": added, "lines_surviving": surviving} if mature else {"status": "pending"}}
    return {"assigned_effort": arm, "project_id": project, "effort_compliant": compliant, "durability": durability,
            "reasoning_output_tokens": reasoning if reasoning is not None else (900 if arm == "xhigh" else 300), "total_tokens": 1000}


class EffortTrialAnalysisTests(unittest.TestCase):
    """The trial's pre-registered verdict: intention to treat, non-inferiority +5 pp on the 7-day retouched rate, validity gates."""

    def setUp(self):
        self.a = importlib.import_module("effort_trial_analysis")

    def trial(self, medium_rate, xhigh_rate, n=12, compliant=True):
        rows = []
        for i in range(n):
            project = f"p{i % 3}"
            rows.append(session("medium", project, 100, round(100 * (1 - medium_rate)), compliant))
            rows.append(session("xhigh", project, 100, round(100 * (1 - xhigh_rate))))
        return rows

    def test_equal_durability_is_non_inferior_and_reports_three_levels(self):
        r = self.a.analyze_v1(self.trial(0.10, 0.10))
        self.assertEqual(r["verdict"], "NON-INFERIOR")
        self.assertEqual(r["difference_medium_minus_xhigh"], 0.0)
        self.assertEqual(set(r["intervals"]), {"90", "95", "99"})

    def test_clearly_worse_medium_is_inferior(self):
        self.assertEqual(self.a.analyze_v1(self.trial(0.40, 0.10))["verdict"], "INFERIOR")

    def test_grouping_is_by_the_assigned_arm_never_by_the_effort_used(self):
        rows = self.trial(0.10, 0.10)
        for row in rows:
            row["effort"] = "xhigh"          # whatever the user ended up using, the arm drawn decides the group
        self.assertEqual(self.a.analyze_v1(rows)["sessions"], {"medium": 12, "xhigh": 12})

    def test_low_compliance_small_samples_or_no_manipulation_never_give_a_verdict(self):
        noncompliant = self.trial(0.10, 0.10)
        for row in noncompliant[:10]:
            row["effort_compliant"] = False
        self.assertEqual(self.a.analyze_v1(noncompliant)["verdict"], "INCONCLUSIVE")
        self.assertEqual(self.a.analyze_v1(self.trial(0.10, 0.10, n=5))["verdict"], "INCONCLUSIVE")
        flat = self.trial(0.10, 0.10)
        for row in flat:
            row["reasoning_output_tokens"] = 500
        result = self.a.analyze_v1(flat)
        self.assertEqual((result["verdict"], result["gates"]["manipulation"]), ("INCONCLUSIVE", False))

    def test_sessions_without_a_drawn_arm_or_without_mature_lines_are_left_out(self):
        rows = self.trial(0.10, 0.10) + [session(None, "p0", 100, 0), session("medium", "p0", 100, 0, mature=False)]
        r = self.a.analyze_v1(rows)
        self.assertEqual(r["mature_sessions_7d"], {"medium": 12, "xhigh": 12})
        self.assertEqual(r["sessions"], {"medium": 13, "xhigh": 12})


DAY = 86400
START = datetime(2026, 10, 26, tzinfo=timezone.utc).timestamp()
DEADLINE_END = datetime(2026, 12, 21, tzinfo=timezone.utc).timestamp()  # enrollment runs through 2026-12-20 (UTC)
# numeric leaves a blinded readout may carry: parameters, counts and compliance; anything else is an outcome
NOT_OUTCOMES = {"margin", "horizon_days", "min_compliance", "min_n", "target", "draws", "seed", "compliance", "sessions", "per_arm",
                "mature_sessions_30d"}


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def numeric_paths(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from numeric_paths(item, path + (key,))
    elif isinstance(value, list):
        for item in value:
            yield from numeric_paths(item, path)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield path


def outcome_leaks(readout):
    """Paths of numbers in the JSON that are not parameters, counts or compliance."""
    return [p for p in numeric_paths(json.loads(json.dumps(readout))) if not NOT_OUTCOMES & set(p)]


def v2_row(arm, project, start, alive=None, added=100, integrated=True, corrective=(4, 1), effort=None, compliant=True):
    """One observatory row as observatory_history.report gives it (with survival_days when `alive` is set)."""
    row = {"assigned_effort": arm, "effort": effort or arm, "project_id": project, "effort_compliant": compliant,
           "started_at": start, "updated_at": start + 3600, "commits": ["c1"], "unintegrated_commits": [] if integrated else ["c1"],
           "reasoning_output_tokens": 900 if arm == "xhigh" else 300, "total_tokens": 1000,
           "durability": {"7": {"status": "mature", "lines_added": 100, "lines_surviving": 93},
                          "30": {"status": "mature", "lines_added": 100, "lines_surviving": 91}}}
    if alive is not None:
        row["line_survival"] = {"added": added, "alive_by_day": alive, "observed_days": len(alive)}
        row["corrective_share"] = {"later_commits": corrective[0], "corrective_commits": corrective[1],
                                   "share": corrective[1] / corrective[0]}
    return row


def declining(final, added=100, days=30):
    """Alive lines on days 1..days falling evenly from `added` to `final`."""
    return [added - round((added - final) * d / days) for d in range(1, days + 1)]


def trial_rows(medium_final, xhigh_final, start, n=12, corrective=((4, 1), (4, 1))):
    rows = []
    for i in range(n):
        jitter = 2 if (i // 3) % 2 else -2  # 88/92 inside each project: the stratified bootstrap has something to resample
        rows.append(v2_row("medium", f"p{i % 3}", start + i * 60, declining(medium_final + jitter), corrective=corrective[0]))
        rows.append(v2_row("xhigh", f"p{i % 3}", start + i * 60, declining(xhigh_final + jitter), corrective=corrective[1]))
    return rows


class EffortTrialV2Tests(unittest.TestCase):
    """Amendment 2: Kaplan-Meier line survival by assigned arm, enrollment to 100 per arm or 2026-12-20, outcomes blinded."""

    @classmethod
    def setUpClass(cls):
        cls.a = importlib.import_module("effort_trial_analysis")

    def test_kaplan_meier_over_lines_with_right_censoring_matches_the_hand_computed_example(self):
        # A: 10 lines, seen 3 days (8, 8, 5 alive); B: 4 lines, seen 1 day then censored; C: 6 lines, seen 2 days (6, 3)
        # day 1: at risk 10+4+6 = 20, lost 2      -> S1 = 18/20                = 9/10
        # day 2: at risk 8+6 = 14 (B censored), lost 3 -> S2 = 9/10 * 11/14   = 99/140
        # day 3: at risk 8 (C censored), lost 3   -> S3 = 99/140 * 5/8         = 99/224 ≈ 0.442
        rows = [v2_row("medium", "p", START, [8, 8, 5], added=10), v2_row("medium", "p", START, [4], added=4),
                v2_row("medium", "p", START, [6, 3], added=6)]
        km = self.a.kaplan_meier(rows)
        self.assertEqual((km["at_risk"], km["deaths"]), ([20, 14, 8], [2, 3, 3]))
        self.assertEqual(len(km["curve"]), 3)  # day 4: nobody at risk, the curve stops instead of extrapolating
        for got, want in zip(km["curve"], (Fraction(9, 10), Fraction(99, 140), Fraction(99, 224))):
            self.assertAlmostEqual(got, float(want), places=12)
        # without censoring the same data would read 12/20 (censored lines counted alive) or 5/10 (dropped): both biased

    def test_a_curve_that_reaches_zero_stays_zero_but_censoring_still_stops_it(self):
        # audit F07: 10 lines all lost on day 1 read S(30) = None, and the bootstrap dropped every such draw as not estimable
        dead = [v2_row("medium", "p", START, [0] * 30, added=10)]
        km = self.a.kaplan_meier(dead)
        self.assertEqual((km["curve"], km["at_risk"][:2], km["deaths"][:2]), ([0.0] * 30, [10, 0], [10, 0]))
        self.assertEqual(self.a._at(km["curve"], 30), 0.0)
        self.assertEqual(self.a.kaplan_meier([v2_row("medium", "p", START, [0], added=10)])["curve"], [0.0] * 30)  # seen 1 day
        # control: lines alive when observation ends are censored, not dead: the curve stops and S(30) stays unknown
        self.assertEqual(self.a.kaplan_meier([v2_row("medium", "p", START, [10], added=10)])["curve"], [1.0])
        self.assertIsNone(self.a._at([1.0], 30))
        self.assertEqual(self.a._curve(self.a._sum([])), [])
        boot = self.a._bootstrap({"medium": dead, "xhigh": [v2_row("xhigh", "p", START, [10] * 30, added=10)]},
                                 lambda r: r["project_id"], days=(30,))
        self.assertEqual(boot[30], ({"90": [-1.0, -1.0], "95": [-1.0, -1.0], "99": [-1.0, -1.0]}, self.a.DRAWS))

    def test_non_inferiority_is_judged_on_the_lower_95_limit_against_minus_5_points(self):
        ok = {"compliance": True, "sample": True, "manipulation": True}
        self.assertEqual(self.a.decide(ok, [-0.04, 0.03]), "NON-INFERIOR")
        self.assertEqual(self.a.decide(ok, [-0.05, 0.03]), "NON-INFERIOR")  # S_medium - S_xhigh >= -5 pp
        self.assertEqual(self.a.decide(ok, [-0.08, 0.01]), "NOT-SHOWN-NON-INFERIOR")
        self.assertEqual(self.a.decide(ok, [-0.20, -0.06]), "INFERIOR")
        self.assertEqual(self.a.decide({**ok, "sample": False}, [-0.01, 0.01]), "INCONCLUSIVE")
        self.assertEqual(self.a.decide(ok, None), "INCONCLUSIVE")

    def test_enrollment_counts_sessions_with_an_integrated_commit_by_assigned_arm_until_100_each(self):
        # intention to treat: 100 sessions drawn medium that ran at xhigh still count as medium
        rows = [v2_row("medium", "p", START + i * 60, effort="xhigh", compliant=False) for i in range(100)]
        rows += [v2_row("xhigh", "p", START + i * 60) for i in range(99)]
        rows += [v2_row("xhigh", "p", START, integrated=False), v2_row(None, "p", START)]  # unmerged; outside the trial
        now = START + DAY
        self.assertEqual(self.a.analyze(rows, now)["enrollment"],
                         {"open": True, "per_arm": {"medium": 100, "xhigh": 99}, "target": 100, "deadline": "2026-12-20",
                          "closed_at": None})
        closing, late = v2_row("xhigh", "p", START + 200 * 60), v2_row("medium", "p", START + 300 * 60)
        r = self.a.analyze(rows + [closing, late], now)
        self.assertEqual(r["enrollment"]["per_arm"], {"medium": 100, "xhigh": 100})
        self.assertEqual((r["enrollment"]["open"], r["enrollment"]["closed_at"]), (False, iso(START + 200 * 60)))
        self.assertEqual(r["sessions"], {"medium": 100, "xhigh": 101})  # the session started after the close is left out

    def test_enrollment_closes_at_the_deadline_whatever_the_counts(self):
        rows = [v2_row("medium", "p", START), v2_row("xhigh", "p", DEADLINE_END + 60)]
        r = self.a.analyze(rows, DEADLINE_END + DAY)
        self.assertEqual((r["enrollment"]["open"], r["enrollment"]["closed_at"]), (False, "2026-12-21T00:00:00Z"))
        self.assertEqual(r["sessions"], {"medium": 1, "xhigh": 0})

    def test_an_open_enrollment_readout_holds_no_outcome_number_anywhere(self):
        r = self.a.analyze(trial_rows(70, 95, START, corrective=((4, 3), (4, 0))), START + 40 * DAY)
        self.assertTrue(r["enrollment"]["open"])
        self.assertEqual((r["verdict"], r["primary"], r["kaplan_meier"]), ("blinded", "blinded", "blinded"))
        self.assertEqual(set(r["secondary"].values()), {"blinded"})
        self.assertEqual(r["readout"], {"7": False, "30": False})
        # if enrollment runs to its deadline; earlier when both arms reach 100
        self.assertEqual(r["blinded_until"], {"7": "2026-12-28T00:00:00Z", "30": "2027-01-20T00:00:00Z"})
        self.assertEqual(outcome_leaks(r), [])
        self.assertEqual((r["sessions"], r["gates"]["compliance"], r["gates"]["manipulation"]),
                         ({"medium": 12, "xhigh": 12}, True, True))

    def test_the_readout_opens_the_7_day_secondaries_first_and_everything_else_after_30_days(self):
        rows = trial_rows(90, 90, DEADLINE_END - 2 * DAY)
        early = self.a.analyze(rows, DEADLINE_END + 10 * DAY)  # enrollment closed; the last session is ~12 days old
        self.assertEqual(early["readout"], {"7": True, "30": False})
        for arm in ("medium", "xhigh"):  # day 7 alive: 97 (final 88) and 98 (final 92) per 100 lines, nobody censored
            self.assertAlmostEqual(early["secondary"]["survival_7d"]["by_arm"][arm], 0.975)
        self.assertEqual(early["secondary"]["retouched_7d_v1"]["retouched_rate_7d"], {"medium": 0.07, "xhigh": 0.07})
        for blinded in (early["verdict"], early["primary"], early["kaplan_meier"], early["secondary"]["survival_14d"],
                        early["secondary"]["corrective_share"], early["secondary"]["per_session"]):
            self.assertEqual(blinded, "blinded")
        r = self.a.analyze(rows, DEADLINE_END + 40 * DAY)
        self.assertEqual((r["readout"], r["verdict"]), ({"7": True, "30": True}, "NON-INFERIOR"))
        self.assertAlmostEqual(r["primary"]["survival_30d"]["medium"], 0.90)  # nobody censored: KM = pooled alive/added
        self.assertEqual(r["primary"]["difference_medium_minus_xhigh"], 0.0)
        bands = r["primary"]["intervals"]
        self.assertEqual(set(bands), {"90", "95", "99"})
        self.assertTrue(bands["99"][0] <= bands["95"][0] < 0 < bands["95"][1] <= bands["99"][1])  # nested, around 0
        self.assertGreaterEqual(bands["95"][0], -0.05)
        self.assertEqual(r["bootstrap"], {"draws": 10000, "seed": 20261025, "stratified_by": "project"})
        self.assertEqual(len(r["kaplan_meier"]["medium"]["curve"]), 30)

    def test_clearly_less_durable_medium_is_inferior_and_corrective_share_is_pooled_by_arm(self):
        rows = trial_rows(60, 92, DEADLINE_END - 2 * DAY, corrective=((4, 2), (4, 1)))
        r = self.a.analyze(rows, DEADLINE_END + 40 * DAY)
        self.assertEqual(r["verdict"], "INFERIOR")
        self.assertLess(r["primary"]["intervals"]["95"][1], -0.05)
        self.assertEqual(r["secondary"]["corrective_share"],
                         {"medium": {"later_commits": 48, "corrective_commits": 24, "share": 0.5},
                          "xhigh": {"later_commits": 48, "corrective_commits": 12, "share": 0.25}})

    def test_an_open_readout_without_line_survival_says_not_computed_never_a_verdict(self):
        # the dashboard never asks for per-day survival (CPU): after the readout it points to this script instead
        rows = [v2_row(arm, f"p{i % 3}", DEADLINE_END - 2 * DAY) for i in range(12) for arm in ("medium", "xhigh")]
        r = self.a.analyze(rows, DEADLINE_END + 40 * DAY)
        self.assertEqual((r["verdict"], r["primary"], r["secondary"]["survival_7d"]), ("not-computed",) * 3)
        self.assertEqual(r["secondary"]["retouched_30d_v1"], {"medium": 0.09, "xhigh": 0.09})


if __name__ == "__main__":
    unittest.main()


class BlindingOutsideTheTrialBlockTests(unittest.TestCase):
    """Amendment 3: a trial session shows neither its drawn arm nor its durability before the readout; other sessions are untouched."""

    def test_trial_sessions_lose_arm_and_durability_but_keep_observed_effort(self):
        a = importlib.import_module("effort_trial_analysis")
        q = lambda text: [{"question": "What did you run?", "answer": "claude · effort medium"},
                          {"question": "Did it last?", "answer": text, "badge": "Linked", "level": 1}]
        view = {"sessions": [{"assigned_effort": "medium", "effort_compliant": True, "durability": {"7": {"lines_added": 9}},
                              "questions": q("7 days: lasted (9/9)")},
                             {"assigned_effort": None, "durability": {"7": {"lines_added": 5}}, "questions": q("7 days: lasted (5/5)")}]}
        a.blind_view(view, "2027-01-20")
        trial, other = view["sessions"]
        self.assertEqual((trial["assigned_effort"], trial["effort_compliant"], trial["durability"]), ("blinded",) * 3)
        self.assertEqual(trial["questions"][1]["answer"], "in the effort trial: durability blinded until 2027-01-20")
        self.assertIsNone(trial["questions"][1]["badge"])
        self.assertEqual(trial["questions"][0]["answer"], "claude · effort medium")
        self.assertEqual(other["questions"][1]["answer"], "7 days: lasted (5/5)")
        self.assertNotIn("9/9", json.dumps(view))

    def test_corrective_matches_whole_words_only(self):
        c = importlib.import_module("choice_observatory").CORRECTIVE
        for text in ("Fix the cutoff", "bugfix: nil map", "Revert \"x\"", "hotfix", "regression in sync", "fixes #12"):
            self.assertTrue(c.search(text), text)
        for text in ("debug logging", "add prefix", "suffix rename", "debugger"):
            self.assertFalse(c.search(text), text)
