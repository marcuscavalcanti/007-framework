#!/usr/bin/env python3
"""Pre-registered analysis of the effort trial (protocol field-2026-10-25; v2 = amendment 2, written before any outcome existed).

Question: in real use, does code delivered by sessions randomly assigned MEDIUM effort last as well as code from sessions assigned
XHIGH, with less waiting and less quota?
- Intention to treat: sessions are grouped by `assigned_effort` (the arm drawn before the session began), never by the effort used.
- Enrollment: a session is ENROLLED when it has >= 1 integrated attributed commit. Enrollment closes when both arms reach TARGET
  (100) enrolled sessions (at the start of the session that completes the later arm) or at the end of DEADLINE (2026-12-20, UTC),
  whichever comes first; sessions started after the close are left out. Counts only, never outcomes; integration is read at
  analysis time, so a commit merged later can move the close.
- Primary outcome: Kaplan-Meier survival of the LINES added by enrolled sessions' integrated commits, pooled by assigned arm, with
  right-censoring (choice_observatory.line_survival: lines alive on each day, censored at the analysis). Day d: at risk = lines
  alive at d-1 among sessions observed >= d; deaths = lines lost on day d. Outcome S(30). Non-inferiority of medium:
  S_medium(30) - S_xhigh(30) >= MARGIN_V2 (-5 percentage points) on the LOWER limit of the 95 % interval; 90 % and 99 % reported.
- Interval: bootstrap of sessions stratified by project (arm x project strata), 10 000 draws, seed 20261025.
- Secondary: S(7) and S(14); share of corrective later commits (fix|bug|revert|hotfix|regress) by arm; time, tokens and reasoning
  tokens per session; the v1 analysis (7-day retouched rate, amendment 1) and its 30-day rate.
- Validity gates (any failing -> INCONCLUSIVE): compliance (observed effort == assigned) >= 70 %; >= MIN_N enrolled sessions per
  arm whose last activity is >= 30 days old; manipulation check: median reasoning tokens per session higher in xhigh.
- BLINDING: until the pre-registered readout (enrollment closed AND the last enrolled session >= 30 days old; >= 7 days for the
  7-day secondaries: S(7) and the v1 7-day rate) the output carries ONLY counts, compliance, gates and enrollment status; every
  outcome key reads "blinded" and is not even computed. An early look needs a new registered amendment first.
Usage: python3 scripts/effort_trial_analysis.py [--json]   (reads the observatory store through observatory_history; per-day line
survival is computed only once a readout is open)
"""
import argparse
from datetime import datetime, timezone
import json
import random
import statistics
import sys

from choice_observatory import _ts

MARGIN, MIN_N, MIN_COMPLIANCE, DRAWS, SEED = 0.05, 10, 0.70, 10000, 20261025
LEVELS = {"90": (0.05, 0.95), "95": (0.025, 0.975), "99": (0.005, 0.995)}
ARMS = ("medium", "xhigh")
SCHEMA = "007-effort-trial-analysis/v2"
MARGIN_V2, HORIZON, TARGET, DAY = -0.05, 30, 100, 86400
DEADLINE = "2026-12-20"  # last enrollment day (UTC), amendment 2
DEADLINE_END = datetime(2026, 12, 21, tzinfo=timezone.utc).timestamp()
READOUTS = (7, 30)  # 7: S(7) and the v1 7-day rate; 30: everything else
BLINDED, NOT_COMPUTED = "blinded", "not-computed"
LIMITS = ["not blinded to the arm: the CLIs show the effort (only the outcomes are blinded)",
          "session-to-commit attribution is a heuristic (activity intervals)",
          "lines are followed by git blame on daily HEAD revisions: renames, moves and reformatting count as modifications",
          "corrective = message substring fix|bug|revert|hotfix|regress (\"debug\" and \"prefix\" match too)",
          "one user's real work across projects; generalizes to that use, not to other users"]


def window(row, days):
    w = (row.get("durability") or {}).get(str(days)) or {}
    if w.get("status") != "mature" or not w.get("lines_added"):
        return None
    return w["lines_added"], w["lines_added"] - w["lines_surviving"]


def pooled(rows, days):
    added = retouched = 0
    for row in rows:
        w = window(row, days)
        if w:
            added, retouched = added + w[0], retouched + w[1]
    return retouched / added if added else None


def _intervals(draws):
    draws = sorted(draws)
    return {lv: [draws[int(lo * len(draws))], draws[min(len(draws) - 1, int(hi * len(draws)))]] if draws else None
            for lv, (lo, hi) in LEVELS.items()}


def analyze_v1(rows, project_of=lambda r: r.get("project_id")):
    """Amendment 1 (now secondary): 7-day retouched rate, non-inferiority +5 pp on the upper 95 % limit."""
    trial = [r for r in rows if r.get("assigned_effort") in ARMS]
    by_arm = {a: [r for r in trial if r["assigned_effort"] == a] for a in ARMS}
    compliance_known = [r for r in trial if r.get("effort_compliant") is not None]
    compliance = sum(r["effort_compliant"] is True for r in compliance_known) / len(compliance_known) if compliance_known else None
    mature = {a: [r for r in by_arm[a] if window(r, 7)] for a in ARMS}
    reasoning = {a: statistics.median([r["reasoning_output_tokens"] for r in by_arm[a] if isinstance(r.get("reasoning_output_tokens"), int)])
                 if any(isinstance(r.get("reasoning_output_tokens"), int) for r in by_arm[a]) else None for a in ARMS}
    rate = {a: pooled(mature[a], 7) for a in ARMS}
    diff = rate["medium"] - rate["xhigh"] if None not in rate.values() else None
    rng, draws = random.Random(SEED), []
    strata = {}
    for a in ARMS:
        for r in mature[a]:
            strata.setdefault((a, project_of(r)), []).append(r)
    for _ in range(DRAWS if diff is not None else 0):
        sample = {a: [] for a in ARMS}
        for (a, _project), group in strata.items():
            sample[a] += rng.choices(group, k=len(group))
        m, x = pooled(sample["medium"], 7), pooled(sample["xhigh"], 7)
        if m is not None and x is not None:
            draws.append(m - x)
    intervals = _intervals(draws)
    gates = {"compliance": compliance is not None and compliance >= MIN_COMPLIANCE,
             "sample": all(len(mature[a]) >= MIN_N for a in ARMS),
             "manipulation": None not in reasoning.values() and reasoning["xhigh"] > reasoning["medium"]}
    if not all(gates.values()) or intervals["95"] is None:
        verdict = "INCONCLUSIVE"
    elif intervals["95"][1] <= MARGIN:
        verdict = "NON-INFERIOR"
    elif intervals["95"][0] > MARGIN:
        verdict = "INFERIOR"
    else:
        verdict = "NOT-SHOWN-NON-INFERIOR"
    return {"schema": "007-effort-trial-analysis/v1", "verdict": verdict, "margin": MARGIN, "gates": gates,
            "compliance": compliance, "min_compliance": MIN_COMPLIANCE, "min_n": MIN_N,
            "sessions": {a: len(by_arm[a]) for a in ARMS}, "mature_sessions_7d": {a: len(mature[a]) for a in ARMS},
            "retouched_rate_7d": rate, "difference_medium_minus_xhigh": diff, "intervals": intervals,
            "bootstrap": {"draws": DRAWS, "seed": SEED, "estimable": len(draws), "stratified_by": "project"},
            "median_reasoning_tokens": reasoning,
            "secondary": {a: {"median_total_tokens": statistics.median([r["total_tokens"] for r in by_arm[a]
                                                                        if isinstance(r.get("total_tokens"), int)] or [0]),
                              "retouched_rate_30d": pooled(by_arm[a], 30)} for a in ARMS},
            "limits": ["not blinded: the CLIs show the effort", "session-to-commit attribution is a heuristic (activity intervals)",
                       "one user's real work across projects; generalizes to that use, not to other users"]}


def _integrated(row):
    loose = set(row.get("unintegrated_commits") or [])
    return [sha for sha in row.get("commits") or [] if sha not in loose]


def _end(row):
    return _ts(row.get("updated_at")) or _ts(row["started_at"])


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def _vector(row):
    """One session's lines at risk on days 1..HORIZON followed by its deaths on those days (zeros once censored)."""
    survival = row["line_survival"]
    alive = survival["alive_by_day"][:HORIZON]
    before = [survival["added"], *alive[:-1]]
    pad = [0] * (HORIZON - len(alive))
    return before + pad + [b - a for b, a in zip(before, alive)] + pad


def _sum(vectors):
    return [sum(column) for column in zip(*vectors)] if vectors else [0] * (2 * HORIZON)


def _curve(vector):
    """Kaplan-Meier product over the summed at-risk/deaths vector; stops at the first day nobody is at risk."""
    curve, s = [], 1.0
    for day in range(HORIZON):
        at_risk, deaths = vector[day], vector[HORIZON + day]
        if not at_risk:
            break
        s *= 1 - deaths / at_risk
        curve.append(s)
    return curve


def kaplan_meier(rows):
    """Discrete Kaplan-Meier over the LINES of `rows` (each with line_survival), right-censored after each session's observed days."""
    vector = _sum([_vector(r) for r in rows])
    curve = _curve(vector)
    return {"curve": curve, "at_risk": vector[:len(curve)], "deaths": vector[HORIZON:HORIZON + len(curve)]}


def _at(curve, day):
    return curve[day - 1] if len(curve) >= day else None


def decide(gates, band95):
    """Non-inferiority of medium on S(30): lower 95 % limit of S_medium - S_xhigh >= MARGIN_V2; validity gates first."""
    if not all(gates.values()) or band95 is None:
        return "INCONCLUSIVE"
    if band95[0] >= MARGIN_V2:
        return "NON-INFERIOR"
    if band95[1] < MARGIN_V2:
        return "INFERIOR"
    return "NOT-SHOWN-NON-INFERIOR"


def _bootstrap(by_arm, project_of, days=(7, 14, 30)):
    """Session bootstrap stratified by (arm, project): intervals of S_medium(d) - S_xhigh(d) and the draws where each is estimable."""
    rng, strata, diffs = random.Random(SEED), {}, {d: [] for d in days}
    for a in ARMS:
        for r in by_arm[a]:
            strata.setdefault((a, project_of(r)), []).append(_vector(r))
    for _ in range(DRAWS):
        sample = {a: [] for a in ARMS}
        for (a, _project), group in strata.items():
            sample[a] += rng.choices(group, k=len(group))
        curves = {a: _curve(_sum(sample[a])) for a in ARMS}
        for d in days:
            if all(len(curves[a]) >= d for a in ARMS):
                diffs[d].append(curves["medium"][d - 1] - curves["xhigh"][d - 1])
    return {d: (_intervals(v), len(v)) for d, v in diffs.items()}


def _median(values):
    values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return statistics.median(values) if values else None


def enrollment(rows, now):
    """(included sessions, close epoch or None): intention to treat by assigned arm, closed by TARGET per arm or DEADLINE_END."""
    trial = [r for r in rows if r.get("assigned_effort") in ARMS and _ts(r.get("started_at")) is not None
             and _ts(r["started_at"]) < DEADLINE_END]
    starts = {a: sorted(_ts(r["started_at"]) for r in trial if r["assigned_effort"] == a and _integrated(r)) for a in ARMS}
    if all(len(starts[a]) >= TARGET for a in ARMS):
        closed_at = max(starts[a][TARGET - 1] for a in ARMS)
    else:
        closed_at = DEADLINE_END if _ts(now) >= DEADLINE_END else None
    return [r for r in trial if closed_at is None or _ts(r["started_at"]) <= closed_at], closed_at


def analyze(rows, now, project_of=lambda r: r.get("project_id")):
    now = _ts(now)
    included, closed_at = enrollment(rows, now)
    by_arm = {a: [r for r in included if r["assigned_effort"] == a] for a in ARMS}
    enrolled = {a: [r for r in by_arm[a] if _integrated(r)] for a in ARMS}
    everyone = enrolled["medium"] + enrolled["xhigh"]
    # readout clock: the last enrolled session's end; while open, the deadline (earlier if both arms reach TARGET)
    base = (max(map(_end, everyone)) if everyone else closed_at) if closed_at is not None else DEADLINE_END
    readout = {str(d): closed_at is not None and now >= base + d * DAY for d in READOUTS}
    known = [r for r in included if r.get("effort_compliant") is not None]
    compliance = sum(r["effort_compliant"] is True for r in known) / len(known) if known else None
    mature = {a: sum(_end(r) + HORIZON * DAY <= now for r in enrolled[a]) for a in ARMS}
    reasoning = {a: _median(r.get("reasoning_output_tokens") for r in by_arm[a]) for a in ARMS}
    gates = {"compliance": compliance is not None and compliance >= MIN_COMPLIANCE,
             "sample": all(mature[a] >= MIN_N for a in ARMS),
             "manipulation": None not in reasoning.values() and reasoning["xhigh"] > reasoning["medium"]}
    out = {"schema": SCHEMA, "verdict": BLINDED, "margin": MARGIN_V2, "horizon_days": HORIZON, "min_compliance": MIN_COMPLIANCE,
           "min_n": MIN_N,
           "enrollment": {"open": closed_at is None, "per_arm": {a: len(enrolled[a]) for a in ARMS}, "target": TARGET,
                          "deadline": DEADLINE, "closed_at": None if closed_at is None else _iso(closed_at)},
           "sessions": {a: len(by_arm[a]) for a in ARMS}, "mature_sessions_30d": mature, "compliance": compliance,
           "gates": gates, "readout": readout, "blinded_until": {str(d): _iso(base + d * DAY) for d in READOUTS},
           "primary": BLINDED, "kaplan_meier": BLINDED,
           "secondary": {k: BLINDED for k in ("survival_7d", "survival_14d", "corrective_share", "per_session",
                                              "retouched_7d_v1", "retouched_30d_v1")},
           "bootstrap": {"draws": DRAWS, "seed": SEED, "stratified_by": "project"}, "limits": LIMITS}
    if not readout["7"]:
        return out  # blinded: no outcome is computed at all
    v1 = analyze_v1(included, project_of)
    sec = out["secondary"]
    sec["retouched_7d_v1"] = {k: v1[k] for k in ("verdict", "retouched_rate_7d", "difference_medium_minus_xhigh", "intervals",
                                                 "mature_sessions_7d", "gates")}
    measured = {a: [r for r in enrolled[a] if isinstance(r.get("line_survival"), dict)] for a in ARMS}
    if not any(measured.values()):  # the dashboard never asks for per-day survival: point to this script instead
        sec["survival_7d"] = NOT_COMPUTED
        if readout["30"]:
            out["verdict"] = out["primary"] = out["kaplan_meier"] = sec["survival_14d"] = sec["corrective_share"] = NOT_COMPUTED
    else:
        km = {a: kaplan_meier(measured[a]) for a in ARMS}
        boot = _bootstrap(measured, project_of)

        def contrast(day):
            s = {a: _at(km[a]["curve"], day) for a in ARMS}
            diff = s["medium"] - s["xhigh"] if None not in s.values() else None
            return {"by_arm": s, "difference_medium_minus_xhigh": diff, "intervals": boot[day][0], "estimable_draws": boot[day][1]}

        sec["survival_7d"] = contrast(7)
        if readout["30"]:
            primary = contrast(30)
            out["primary"] = {"survival_30d": primary.pop("by_arm"), **primary}
            out["verdict"] = decide(gates, out["primary"]["intervals"]["95"] if out["primary"]["difference_medium_minus_xhigh"]
                                    is not None else None)
            out["kaplan_meier"] = km
            sec["survival_14d"] = contrast(14)
            sec["corrective_share"] = {}
            for a in ARMS:
                later = sum(r["corrective_share"]["later_commits"] for r in measured[a] if r.get("corrective_share"))
                hits = sum(r["corrective_share"]["corrective_commits"] for r in measured[a] if r.get("corrective_share"))
                sec["corrective_share"][a] = {"later_commits": later, "corrective_commits": hits,
                                              "share": hits / later if later else None}
    if readout["30"]:
        sec["retouched_30d_v1"] = {a: v1["secondary"][a]["retouched_rate_30d"] for a in ARMS}
        sec["per_session"] = {a: {"median_minutes": _median((_end(r) - _ts(r["started_at"])) / 60 for r in by_arm[a]),
                                  "median_total_tokens": _median(r.get("total_tokens") for r in by_arm[a]),
                                  "median_reasoning_tokens": reasoning[a]} for a in ARMS}
    return out


def blind_view(view, until):
    """Blinding outside the trial block (amendment 3): until the readout, a session that belongs to the trial shows neither its drawn arm
    nor its durability, so nobody can group outcomes by arm by hand. Observed effort (question 1) stays: it is not an outcome."""
    for session in view.get("sessions") or []:
        if session.get("assigned_effort") not in ARMS:
            continue
        session.update({"assigned_effort": BLINDED, "effort_compliant": BLINDED, "durability": BLINDED})
        session["questions"] = [q if q.get("question") != "Did it last?" else
                                {"question": "Did it last?", "level": None, "badge": None, "windows": None,
                                 "answer": f"in the effort trial: durability blinded until {until}"}
                                for q in session.get("questions") or []]
    return view


def main():
    parser = argparse.ArgumentParser(description="Pre-registered analysis of the effort trial (intention to treat)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    import framework_cli
    import observatory_history
    home = observatory_history.HOME
    config = observatory_history.read_config(home / "config.json")
    entries = framework_cli.load_registry(framework_cli.default_registry_path())["projects"]
    store = home / "observatory" / "sessions.jsonl"
    allowed = observatory_history.allowed(config, entries, store)
    repos = observatory_history.trial_repos(config)
    now = datetime.now(timezone.utc).timestamp()

    def collect(survival_days=None):
        rows = []
        for pid in sorted(allowed):
            try:
                rows += [{**r, "project_id": pid} for r in observatory_history.report(
                    store, entries, pid, allowed, now, trial_repos=repos, survival_days=survival_days)]
            except (OSError, PermissionError, RuntimeError, ValueError):
                continue
        return rows

    result = analyze(collect(), now)
    if any(result["readout"].values()):  # per-day line survival (one blame per day) only once a readout is open
        result = analyze(collect(HORIZON), now)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        e = result["enrollment"]
        print(f"effort trial: {result['verdict']} · enrollment {'open' if e['open'] else 'closed'} {e['per_arm']} "
              f"(target {e['target']} per arm, deadline {e['deadline']}) · compliance {result['compliance']} · "
              f"gates {result['gates']} · outcomes blinded until {result['blinded_until']['30']}"
              if not result["readout"]["30"] else f"effort trial: {result['verdict']} · primary {result['primary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
