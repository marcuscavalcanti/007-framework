"""Thesis D choice observatory, evidence levels 0 and 1 (choice-observatory design; internal record, not published).

Level 0: a session was observed (model, effort, times). Level 1: commits are attributed to it and at least one durability window
is mature. Attribution is a heuristic: a commit belongs to the one session of this repository whose active intervals (row
timestamps, local_activity.active_intervals) +- slack hold its committer time; a session without intervals falls back to
[start - slack, end + slack]; inside two sessions it is "ambiguous", never guessed. Commits come from every local branch and every
worktree's HEAD (BRANCHES). Durability is line survival (git blame) on HEAD at the last commit before each window's cutoff; an
attributed commit HEAD does not reach is "not merged": neither surviving nor reworked. Callers pass the project's sessions
(local_activity maps cwd to project) and, as rivals, those of other projects on the same repository (a worktree registered apart).
Level 3 (Calibrated): `calibrated` reads a holdout analysis (007-thesis-d-holdout-analysis/v1) configured for the session's
project, CLI and model; `questions` turns one session into the dashboard's three questions. Level 2 and External are not built.
"""
from datetime import datetime, timezone
import re

from touch_rate import git, survival

DAY = 86400
# amendment 2 of the effort trial, pre-registered: a later commit is corrective when its message matches (plain substring, any case,
# so "debug" and "prefix" match too: a declared limit of the frozen definition)
CORRECTIVE = re.compile(r"\b(fix(e[sd])?|bug(s|fix)?|revert(s|ed)?|hotfix(es)?|regress(ion|ions|ed)?)\b", re.IGNORECASE)  # amendment 3: whole words
SCHEMA_L3 = "007-thesis-d-holdout-analysis/v1"
LADDER = ("minimal", "low", "medium", "high", "xhigh", "max")
NO_EVIDENCE = "no evidence to judge"
BRANCHES = ("local branches (refs/heads) and the HEAD of each worktree; excluded: remotes, tags, stash, notes and tool refs "
            "(refs/codex/snapshots)")


def _ts(value):
    """Epoch seconds from an int/float or an ISO-8601 string (local_activity emits ...Z); None otherwise."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    return None


def _commits(repo):
    """(sha, committer epoch) of non-merge commits reachable from BRANCHES, newest first. Remote refs are other people's or
    already-local work, and stash/tool refs (`git log --all` would bring them) hold snapshots, not deliverables."""
    try:
        heads = [line[5:] for line in git(repo, "worktree", "list", "--porcelain").splitlines() if line.startswith("HEAD ")]
        log = git(repo, "log", "--no-merges", "--format=%H %ct", "--branches", *heads, "--")
    except RuntimeError:  # repository without commits
        return []
    return [(sha, int(when)) for sha, _, when in (line.partition(" ") for line in log.splitlines())]


def _on_head(repo):
    try:
        return set(git(repo, "rev-list", "HEAD").split())
    except RuntimeError:
        return set()


def _spans(session, slack_s):
    intervals = session.get("active_intervals")
    if intervals:
        return [(start - slack_s, end + slack_s) for start, end in intervals]
    start, end = _ts(session.get("started_at")), _ts(session.get("updated_at"))
    return [] if start is None or end is None else [(start - slack_s, end + slack_s)]


def attribute(repo, sessions, slack_s=600):
    windows = [(s["session_id"], _spans(s, slack_s)) for s in sessions]
    result = {"sessions": {s["session_id"]: [] for s in sessions}, "unattributed": {},
              "ambiguous": {s["session_id"]: [] for s in sessions}}
    for sha, when in reversed(_commits(repo)):  # oldest first
        owners = [sid for sid, spans in windows if any(start <= when <= end for start, end in spans)]
        if len(owners) == 1:
            result["sessions"][owners[0]].append(sha)
        else:
            result["unattributed"][sha] = "ambiguous" if owners else "no-session"
            for sid in owners:
                result["ambiguous"][sid].append(sha)
    return result


def _last(repo, shas):
    """Committer epoch of the newest of `shas` (the origin of every durability clock)."""
    return max(int(when) for when in git(repo, "show", "-s", "--format=%ct", *shas).split())


def durability(repo, shas, now, windows=(7, 30)):
    last = _last(repo, shas)
    out = {}
    for days in windows:
        cutoff = last + days * DAY
        if _ts(now) < cutoff:
            out[str(days)] = {"status": "pending", "matures_at": cutoff}
            continue
        rev = git(repo, "rev-list", "-1", f"--before=@{cutoff}", "HEAD").strip()
        added, alive = survival(repo, shas, rev)
        out[str(days)] = {"status": "mature", "lines_added": added, "lines_surviving": alive,
                          "retouched_rate": round(1 - alive / added, 4) if added else None}
    return out


def line_survival(repo, shas, now, max_days=30):
    """Per-day survival of the lines added by `shas` (effort trial amendment 2): alive_by_day[d - 1] = those lines still blamed on
    them at the last HEAD revision on or before the newest commit + d days, for d = 1..observed_days (whole days elapsed, capped at
    max_days; later days are censored). A line lost stays lost (running minimum: time to FIRST modification), which also absorbs a
    day whose revision is an older side-branch commit merged later."""
    last = _last(repo, shas)
    observed = max(0, min(max_days, int((_ts(now) - last) // DAY)))
    alive, by_rev, added = [], {}, None
    for day in range(1, observed + 1):
        rev = git(repo, "rev-list", "-1", "--first-parent", f"--before=@{last + day * DAY}", "HEAD").strip()  # main line only
        if rev not in by_rev:  # ponytail: a quiet day reuses the blame of the same revision; still one blame per changed day
            by_rev[rev] = survival(repo, shas, rev)
        added, count = by_rev[rev]
        alive.append(min(count, alive[-1]) if alive else count)
    if added is None:
        added = survival(repo, shas, "HEAD")[0]
    return {"added": added, "alive_by_day": alive, "observed_days": observed}


def corrective_share(repo, shas, until):
    """Among the later non-merge commits on HEAD that touched the files of `shas`, up to `until` (epoch), the share whose message
    matches CORRECTIVE: "modified" is not "defective" (amendment 2 secondary)."""
    files = sorted({name for sha in shas for name in git(repo, "show", "--name-only", "--format=", sha).splitlines() if name})
    own = set(shas)
    log = git(repo, "log", "--no-merges", "-z", "--format=%H%n%B", f"--since=@{_last(repo, shas)}", f"--until=@{int(_ts(until))}",
              "HEAD", "--", *files) if files else ""
    later = [body for sha, _, body in (entry.strip("\n").partition("\n") for entry in log.split("\0")) if sha and sha not in own]
    corrective = sum(bool(CORRECTIVE.search(body)) for body in later)
    return {"later_commits": len(later), "corrective_commits": corrective, "share": corrective / len(later) if later else None}


def observe(repo, sessions, now, slack_s=600, windows=(7, 30), rivals=(), survival_days=None):
    """One row per session; `rivals` (sessions of other projects on the same repository) only compete for commits. With
    `survival_days` (asked by effort_trial_analysis, never by the dashboard's refresh: one blame per day per session), rows with
    integrated commits also carry `line_survival` and `corrective_share` over the same window (newest commit + survival_days)."""
    attribution = attribute(repo, [*sessions, *rivals], slack_s)
    owned = attribution["sessions"]
    head = _on_head(repo) if any(owned.values()) else set()
    rows = []
    for s in sessions:
        shas = owned.get(s["session_id"], [])
        integrated = [sha for sha in shas if sha in head]
        dur = durability(repo, integrated, now, windows) if integrated else None
        mature = bool(dur) and any(v["status"] == "mature" for v in dur.values())
        extra = {}
        if survival_days and integrated:
            until = min(_ts(now), _last(repo, integrated) + survival_days * DAY)
            extra = {"line_survival": line_survival(repo, integrated, now, survival_days),
                     "corrective_share": corrective_share(repo, integrated, until)}
        rows.append({**{k: s.get(k) for k in ("session_id", "source", "model", "effort", "started_at", "updated_at",
                                               "total_tokens", "reasoning_output_tokens")},
                     "commits": shas, "unintegrated_commits": [sha for sha in shas if sha not in head],
                     "ambiguous_commits": attribution["ambiguous"].get(s["session_id"], []),
                     "durability": dur, "evidence_level": 1 if mature else 0, **extra})
    return rows


def _pp(value):
    """A proportion difference as signed percentage points, e.g. -0.0897 -> "−9", 0.0897 -> "+9"."""
    points = round(100 * value)
    return f"−{abs(points)}" if points < 0 else f"+{points}"


def _pct(x):
    return f"{round(100 * x)}%"


def _change(reduction):
    return ("−" if reduction >= 0 else "+") + _pct(abs(reduction))


def _usd(x):
    return f"${x:.2f}"


def no_evidence(reason, **extra):
    return {"level": None, "badge": None, "verdict": "no-evidence", "answer": f"{NO_EVIDENCE}: {reason}", **extra}


def calibrated(analysis, effort, ci=None):
    """Question 3 at level 3 for a session at `effort`, from one holdout analysis (contrasts "<effort>_vs_<reference>").
    `ci` (optional, schema 007-ci-report/v1) adds the 90/95/99% intervals: acceptance difference and time/cost reduction.

    A lower effort is enough when its contrast SURVIVES and it accepted at least as many units as the session's effort.
    The time interval exists only against the reference arm; cost has none. Cost comes from the experiment's receipts only.
    """
    if not isinstance(analysis, dict) or analysis.get("schema") != SCHEMA_L3:
        return no_evidence("analysis with an unknown schema")
    try:
        return _judge(analysis, effort or "unmeasured", ci)
    except (AttributeError, KeyError, TypeError, ValueError, ZeroDivisionError):
        return no_evidence("unreadable analysis")


def _judge(analysis, effort, ci=None):
    contrasts = {key.partition("_vs_")[0]: value for key, value in analysis["contrasts"].items()}
    refs = {key.partition("_vs_")[2] for key in analysis["contrasts"]}
    if len(refs) != 1 or not contrasts:
        raise ValueError("no single reference arm")
    ref = refs.pop()
    arms = {ref: next(iter(contrasts.values()))[ref], **{e: c[e] for e, c in contrasts.items()}}
    order = sorted(arms, key=LADDER.index)
    verdict = {e: c["verdict"] for e, c in contrasts.items()}
    base = {"measured_efforts": order, "limits_full": list(analysis.get("limits", [])),
            "limits": f"Limits: one repository, {analysis['tasks']} well-specified tasks, immediate acceptance only "
                      "(durability not measured in the experiment)."}
    if analysis.get("manipulation_check_reasoning_monotonic") is not True:
        return no_evidence("the manipulation check failed (the effort may not have changed)", **base)
    if effort not in arms:
        return no_evidence(f"effort {effort} was not measured in the experiment ({', '.join(order)})", **base)

    reported = ci.get("contrasts", {}) if isinstance(ci, dict) and ci.get("schema") == "007-ci-report/v1" else {}

    def intervals(e):
        return (reported.get(f"{e}_vs_{ref}") or {}).get("intervals")

    def counts(e):
        return f"{arms[e]['accepted']}/{arms[e]['units']}"

    def accepted(e, against):
        diff = (intervals(e) or {}).get("95", {}).get("acceptance_difference") if against == ref else None
        tail = f" (acceptance difference, 95% CI: {_pp(diff[0])} to {_pp(diff[1])} pp)" if diff else ""
        return f"{e} accepted {counts(e)} vs {counts(against)} for {against}{tail}"

    def killed(e):
        c = contrasts[e]
        if c["acceptance_ok"]:
            return accepted(e, ref) + f", but reduced time by only {_pct(c['reduction'])} (minimum {_pct(c['kill_threshold'])})"
        return accepted(e, ref) + ("" if c.get("reduction") is None else f" ({_change(c['reduction'])} time per accepted delivery)")

    def gain(e, against):
        t_e, t_s = arms[e]["wall_per_accepted_s"], arms[against]["wall_per_accepted_s"]
        c_e, c_s = arms[e].get("cost_per_accepted_usd"), arms[against].get("cost_per_accepted_usd")
        ci = (contrasts[e].get("bootstrap") or {}).get("ci95_conditional") if against == ref else None
        cost = 1 - c_e / c_s if c_e is not None and c_s else None
        return {"effort": e, "against": against, "time_per_accepted_s": [t_e, t_s], "time_reduction": 1 - t_e / t_s,
                "time_ci95": ci, "cost_per_accepted_usd": [c_e, c_s], "cost_reduction": cost,
                "cost_basis": "experiment receipts", "intervals": intervals(e) if against == ref else None}

    def cost_ci(g):
        band = ((g.get("intervals") or {}).get("95") or {}).get("cost_reduction")
        return f"95% CI: {round(100 * band[0])}–{_pct(band[1])}" if band else "no CI"

    def ci_text(g):
        levels = g.get("intervals") or {}
        if all((levels.get(k) or {}).get("time_reduction") for k in ("90", "95", "99")):
            return "CI 90/95/99%: " + " / ".join(f"{round(100 * levels[k]['time_reduction'][0])}–{_pct(levels[k]['time_reduction'][1])}"
                                                 for k in ("90", "95", "99")).replace("% /", " /")
        if g["time_ci95"]:
            low, high = g["time_ci95"]
            return f"95% CI: {round(100 * low)}–{_pct(high)}"
        return "no CI" if g["against"] == ref else f"CI exists only against {ref}"

    def calibrated_(code, answer, **extra):
        return {"level": 3, "badge": "Calibrated", "verdict": code, "answer": answer, **base, **extra}

    lower = order[:order.index(effort)]
    enough = [e for e in lower if verdict[e] == "SURVIVES" and arms[e]["accepted"] >= arms[effort]["accepted"]]
    if enough:
        g = gain(enough[0], effort)
        t_e, t_s = g["time_per_accepted_s"]
        cost = ("cost per accepted delivery N/A" if g["cost_reduction"] is None else
                f"cost per accepted delivery of {_usd(g['cost_per_accepted_usd'][0])} vs "
                f"{_usd(g['cost_per_accepted_usd'][1])} ({_change(g['cost_reduction'])}; "
                f"{cost_ci(g)})")
        return calibrated_("above-necessary", f"effort above what was needed: {accepted(enough[0], effort)}, with agent "
                           f"time per accepted delivery of {t_e:.0f} s vs {t_s:.0f} s ({_change(g['time_reduction'])}; "
                           f"{ci_text(g)}) and {cost}", gain=g)
    if any(verdict[e] != "KILLED" for e in lower):
        unclear = ", ".join(f"{e}: {verdict[e]}" for e in lower if verdict[e] != "KILLED")
        return no_evidence(f"effort lower than {effort} without a clear verdict in the experiment ({unclear})", **base)
    if effort == ref:
        # a margin-0 kill is not evidence that the reference was needed, so this is never "good choice"
        return calibrated_("no-cheaper-proven", f"no lower effort passed the experiment's rule (accept as many as "
                           f"{ref}): " + "; ".join(killed(e) for e in lower))
    if verdict[effort] == "SURVIVES":
        g = gain(effort, ref)
        tail = f"; lower effort did not pass: {'; '.join(killed(e) for e in lower)}" if lower else f"; {effort} is the lowest effort measured"
        return calibrated_("good-choice", f"good choice: {accepted(effort, ref)}, with {_change(g['time_reduction'])} agent time "
                           f"per accepted delivery ({ci_text(g)}){tail}", gain=g)
    if verdict[effort] == "KILLED":
        return calibrated_("cannot-spend-less", f"not proven by the experiment: {killed(effort)}")
    return no_evidence(f"the {effort} × {ref} contrast was inconclusive", **base)


def _duration(row):
    start, end = _ts(row.get("started_at")), _ts(row.get("updated_at"))
    if start is None or end is None:
        return "duration N/A"
    seconds = end - start
    return f"{round(seconds)} s" if seconds < 60 else f"{round(seconds / 60)} min" if seconds < 3600 else f"{round(seconds / 3600)} h"


def _window(w):
    if w["status"] == "pending":
        return "matures on " + datetime.fromtimestamp(w["matures_at"], timezone.utc).date().isoformat()
    if w["retouched_rate"] is None:
        return "no added lines to measure"
    if w["retouched_rate"] == 0:
        return f"delivered code that lasted ({w['lines_surviving']}/{w['lines_added']} lines alive)"
    return f"was corrected ({_pct(w['retouched_rate'])} of the lines retouched)"


def questions(row, q3):
    """The dashboard's three questions for one observed session; q3 comes from `calibrated` or `no_evidence`."""
    tokens, reasoning = row.get("total_tokens"), row.get("reasoning_output_tokens")
    quota = "quota N/A" if tokens is None else f"{tokens} tokens ({'N/A' if reasoning is None else reasoning} reasoning)"
    q1 = {"question": "What did you run?", "level": 0, "badge": "Observed",
          "answer": " · ".join([row.get("source") or "CLI N/A", row.get("model") or "model N/A",
                                f"effort {row.get('effort') or 'unmeasured'}", _duration(row), quota])}
    windows, loose = row.get("durability"), len(row.get("unintegrated_commits") or [])
    if not row.get("commits"):
        n = len(row.get("ambiguous_commits") or [])
        answer = f"not attributed: {n} commit(s) in the window of more than one session" if n else "not attributed: no commit in the session's window"
        q2 = {"question": "Did it last?", "level": None, "badge": None, "answer": answer, "windows": None}
    elif not windows:
        q2 = {"question": "Did it last?", "level": None, "badge": None, "windows": None,
              "answer": f"commit not yet merged into the main branch ({loose} commit(s) from the session)"}
    else:
        answer = "; ".join(f"{days} days: {_window(w)}" for days, w in windows.items())
        if loose:
            answer += f"; {loose} commit(s) not yet merged into the main branch, outside the measurement"
        linked = row.get("evidence_level") == 1
        q2 = {"question": "Did it last?", "level": 1 if linked else None, "badge": "Linked" if linked else None,
              "answer": answer if linked else f"{NO_EVIDENCE} yet: {answer}", "windows": windows}
    return [q1, q2, {"question": "Could you have spent less?", **q3}]
