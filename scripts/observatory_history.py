#!/usr/bin/env python3
"""Thesis D step 2: keep session METADATA beyond the 24 h log lookback so durability (7/30 days) can mature.

Only projects the user opted in (config `observatory.projects`) are recorded, or, with `observatory.auto: true` (off by default),
every project with an active session (registered in 007, or any git repository by its root, id "git:<root>"; a linked worktree is
its repository) except `observatory.exclude` (names or ids); only FIELDS are stored, never conversation content (active_intervals are row timestamps merged across pauses of at most
`observatory.activity_gap_minutes`, default 30). `observatory.lookback_hours` (default 168) bounds each record pass.
The store is append-only JSONL; a session is appended again only when its updated_at changes, or when the stored row predates
active_intervals and a fresh parse brings them; readers keep the latest row, with the union of the session's intervals.
Sessions of other projects on the same repository (git common dir) compete for its commits.
Question 3 at level 3 uses the holdout analysis that config `observatory.calibrations` maps to (project_id, cli, model); no
guessing: an unmapped session is "no evidence to judge".
Effort trial (scripts/effort_trial.py): each reported session carries `assigned_effort`, the default effort the trial had written
for its CLI when it started (intention to treat; effort_trial.jsonl next to the store), and `effort_compliant` (observed ==
assigned); projects outside a non-empty `observatory.effort_trial.repos` (ids or folder names) get None. `report(...,
survival_days=30)` adds per-day line survival and the corrective share (effort_trial_analysis asks once a readout is open; the
dashboard never does).
Usage: python3 scripts/observatory_history.py record | report --project-id ID | questions --project-id ID
       [--config ~/.007-framework/config.json]
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import choice_observatory
import config_guard
import effort_trial
import local_activity

FIELDS = ("source", "session_id", "project_id", "cwd", "model", "effort", "started_at", "updated_at",
          "total_tokens", "reasoning_output_tokens", "active_intervals", "subagent", "log_id", "effort_segments")
HOME = Path.home() / ".007-framework"
CALIBRATION_KEYS = ("project_id", "cli", "model", "analysis")
NOT_OPTED_IN = {"opted_in": False, "answer": "outside observatory.projects: nothing is recorded or judged"}
TEMPORARY = ("/var/folders/", "/private/var/", "/tmp/", "/private/tmp/")  # experiment workspaces vanish; never followed


def git_root(cwd):
    """The repository root of a session's cwd, or None (not a directory, not git, or a temporary workspace). A linked worktree
    (e.g. ~/.codex/worktrees/<name>/<repo>) maps to its main repository through the git common dir, so it is one project."""
    if not isinstance(cwd, str) or not cwd or cwd.startswith(TEMPORARY) or not Path(cwd).is_dir():
        return None
    out = subprocess.run(["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir", "--show-toplevel"],
                         capture_output=True, text=True)
    common, _, top = out.stdout.strip().partition("\n")
    if out.returncode or not top:
        return None
    root = str(Path(common).parent.resolve() if Path(common).name == ".git" else Path(top).resolve())
    return None if root.startswith(TEMPORARY) else root


def _excluded(project, path, exclude):
    names = {str(x).casefold() for x in exclude}
    return str(project).casefold() in names or (path is not None and Path(path).name.casefold() in names)


def allowed(config, entries, store):
    """Projects whose sessions are recorded and judged: the listed ones, plus, in auto mode, every project already in the store."""
    section = config.get("observatory", {})
    listed = set(section.get("projects", []))
    if section.get("auto") is not True:
        return listed
    paths = {e["project_id"]: e["path"] for e in entries}
    seen = {r.get("project_id") for r in load(store)} | listed
    return {p for p in seen if p and not _excluded(p, paths.get(p) or (p[4:] if p.startswith("git:") else None),
                                                   section.get("exclude", []))}


def read_config(path):
    """The configuration through config_guard (ConfigError is a ValueError): nothing is recorded or judged under a config that
    would no longer measure what 007 claims."""
    return config_guard.load(Path(path), trial_log=Path(path).parent / "observatory" / "effort_trial.jsonl")


def trial_repos(config):
    """observatory.effort_trial.repos: the projects whose sessions enter the trial analysis; empty = all."""
    repos = (config.get("observatory", {}).get("effort_trial") or {}).get("repos") or []
    return repos if isinstance(repos, list) else []


def calibrations(config, base):
    """Entries of observatory.calibrations with their analysis loaded; a relative `analysis` path is relative to `base`."""
    out = []
    for item in config.get("observatory", {}).get("calibrations", []):
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k] for k in CALIBRATION_KEYS):
            out.append({"error": "invalid entry in observatory.calibrations", "data": None})
            continue
        path = Path(base, Path(item["analysis"]).expanduser())
        try:
            raw = path.read_bytes()
            data, digest, error = json.loads(raw), hashlib.sha256(raw).hexdigest(), None
        except (OSError, ValueError):
            data, digest, error = None, None, "unreadable analysis"
        ci, ci_digest = None, None
        if isinstance(item.get("ci_report"), str) and item["ci_report"]:  # optional: 90/95/99% intervals (ci_report.py)
            try:
                ci_raw = Path(base, Path(item["ci_report"]).expanduser()).read_bytes()
                ci, ci_digest = json.loads(ci_raw), hashlib.sha256(ci_raw).hexdigest()
            except (OSError, ValueError):
                error = error or "unreadable ci_report"
        out.append({**{k: item[k] for k in CALIBRATION_KEYS[:3]}, "analysis": str(path), "sha256": digest,
                    "error": error, "data": data, "ci": ci, "ci_sha256": ci_digest})
    return out


def snapshot(collector, entries, allowed, now, auto=False, exclude=()):
    now = now or datetime.now(timezone.utc)
    paths = {e["project_id"]: e["path"] for e in entries}
    identities = {e["project_id"]: collector.identity(e["path"]) for e in entries}
    rows = []
    for source, path in collector.candidates(now):
        try:
            session = collector.parse(source, path, now)
            project = session and collector.project_id(session, entries, identities)
        except (OSError, ValueError):
            continue
        if not session:
            continue
        if not project and auto:
            root = next(filter(None, map(git_root, session.get("cwds") or [session.get("cwd")])), None)
            project = root and "git:" + root
        if not project or (project not in allowed and not auto):
            continue
        if auto and _excluded(project, paths.get(project) or (project[4:] if project.startswith("git:") else None), exclude):
            continue
        usage = session.get("usage") if isinstance(session.get("usage"), dict) else {}
        merged = {**session, "project_id": project, "total_tokens": usage.get("total_tokens"),
                  "reasoning_output_tokens": usage.get("reasoning_output_tokens")}
        rows.append({k: merged.get(k) for k in FIELDS})
    return rows


def _rows(store):
    rows = []
    if Path(store).is_file():
        for line in Path(store).read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue  # ponytail: a torn last line is skipped, earlier lines stay valid
    return rows


def _union(intervals):
    out = []
    for start, end in sorted(intervals):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out


def load(store):
    """The latest row of each session; its active_intervals are the union over all its logs, because one session id spans
    several logs (Claude subagents under <session>/subagents/ carry the parent sessionId, Codex children their root's) and the
    latest may be a subagent's. A log named by its row (log_id; a Codex row before it is its own thread) speaks through its
    newest row with intervals, which reads the whole log: a 1.6 parse of a large log, clipped to its tail, is replaced."""
    rows = _rows(store)
    # a Codex child stored before 1.7 kept its own thread id as session id: a later row of the same log names its root
    alias = {r["log_id"]: r["session_id"] for r in rows
             if r.get("source") == "codex" and isinstance(r.get("log_id"), str) and r["log_id"] != r.get("session_id")}

    def root(session_id):
        seen = set()
        while session_id in alias and session_id not in seen:
            seen.add(session_id)
            session_id = alias[session_id]
        return session_id

    latest, main, spans, logs, last = {}, {}, {}, {}, {}
    newer = lambda row, kept: kept is None or choice_observatory._ts(row["updated_at"]) >= choice_observatory._ts(kept["updated_at"])
    for row in rows:
        codex = row.get("source") == "codex"
        key = (row.get("source"), root(row.get("session_id")) if codex else row.get("session_id"))
        log = row.get("log_id") or (row.get("session_id") if codex else None)
        if log is None:
            spans.setdefault(key, []).extend(row.get("active_intervals") or [])
        elif row.get("active_intervals") and newer(row, logs.get((key, log))):
            logs[(key, log)] = row
        if newer(row, latest.get(key)):
            latest[key] = row
        # model, effort, start and tokens come from the session's own log, never from a subagent's; a row stored before the
        # mark existed ("subagent" absent) counts only when no row declares itself the main log
        rank = 2 if row.get("subagent") is False else 1 if "subagent" not in row else 0
        kept = main.get(key)
        if rank and (kept is None or rank > kept[0] or (rank == kept[0] and newer(row, kept[1]))):
            main[key] = (rank, row)
        stamp = choice_observatory._ts(row["updated_at"])
        last[key] = row["updated_at"] if key not in last or stamp >= choice_observatory._ts(last[key]) else last[key]
    for (key, _), row in logs.items():
        spans.setdefault(key, []).extend(row["active_intervals"])
    return [{**(main[key][1] if key in main else row), "session_id": key[1], "updated_at": last[key],
             "active_intervals": _union(spans.get(key, [])) or None} for key, row in latest.items()]


def record(store, rows):
    store = Path(store)
    seen = {}
    parsed = lambda r: (r.get("log_id"), r.get("active_intervals"), r.get("effort_segments"))
    for r in _rows(store):  # every stored row, not only the latest: an older log of the same session is not appended again
        seen.setdefault((r.get("source"), r.get("session_id"), r.get("updated_at")), []).append(parsed(r))
    # a row whose parse brings what the stored ones lack (intervals; a whole-log read; 1.7 fields) is appended once, never one
    # without intervals
    new = [r for r in rows if (had := seen.get((r["source"], r["session_id"], r["updated_at"]))) is None
           or (r.get("active_intervals") and parsed(r) not in had)]
    if new:
        store.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(store, "a") as handle:
            handle.write("".join(json.dumps(r, sort_keys=True) + "\n" for r in new))
    return len(new)


def report(store, entries, project_id, allowed, now, slack_s=600, windows=(7, 30), trial_repos=(), survival_days=None):
    if project_id not in allowed:
        raise PermissionError(f"project {project_id} is not opted in (config observatory.projects)")
    path = _path(entries, project_id)
    if path is None:
        raise PermissionError(f"project {project_id} has no path (not registered and not a git root)")
    rows = load(store)
    # another project on the same repository (e.g. a worktree registered apart) sees the same branches: its sessions compete
    others = {r.get("project_id") for r in rows} - {project_id}
    repository = local_activity.git_identity(path)
    same = {p for p in others if repository and _path(entries, p) and local_activity.git_identity(_path(entries, p)) == repository}
    observed = choice_observatory.observe(Path(path), [r for r in rows if r.get("project_id") == project_id], now, slack_s=slack_s,
                                          windows=windows, rivals=[r for r in rows if r.get("project_id") in same],
                                          survival_days=survival_days)
    trial = effort_trial.records(Path(store).parent / "effort_trial.jsonl")
    in_trial = not trial_repos or _excluded(project_id, path, trial_repos)  # _excluded is the id-or-folder-name match
    outside = {"assigned_effort": None, "effort_compliant": None}
    return [{**row, **(effort_trial.assignment(trial, row) if in_trial else outside)} for row in observed]


def _path(entries, project_id):
    path = next((e["path"] for e in entries if e["project_id"] == project_id), None)
    return path or (project_id[4:] if isinstance(project_id, str) and project_id.startswith("git:") else None)


def view(store, entries, project_id, allowed, calibrations, now, slack_s=600, windows=(7, 30), trial_repos=()):
    """The dashboard's three questions for one opted-in project: levels 0, 1 and 3 (2 and External are not built)."""
    mine = [c for c in calibrations if c.get("project_id") == project_id]
    sessions = []
    for row in report(store, entries, project_id, allowed, now, slack_s=slack_s, windows=windows, trial_repos=trial_repos):
        cal = next((c for c in mine if (c["cli"], c["model"]) == (row.get("source"), row.get("model"))), None)
        if cal is None:
            q3 = choice_observatory.no_evidence(f"{row.get('source')} {row.get('model')} not calibrated in this repository")
        elif cal["data"] is None:
            q3 = choice_observatory.no_evidence(f"unreadable calibration analysis ({cal['analysis']})")
        else:
            q3 = {**choice_observatory.calibrated(cal["data"], row.get("effort"), ci=cal.get("ci")),
                  "source": {"analysis": cal["analysis"], "sha256": cal["sha256"]}}
        sessions.append({**row, "questions": choice_observatory.questions(row, q3)})
    summary = []
    for c in mine:
        probe = choice_observatory.calibrated(c["data"], None) if c["data"] is not None else {}
        summary.append({**{k: c[k] for k in ("cli", "model", "analysis", "sha256", "error")}, "limits": probe.get("limits"),
                        "arms": choice_observatory.arms(c["data"]) if c["data"] is not None else {},
                        "by_effort": {e: {k: v for k, v in choice_observatory.calibrated(c["data"], e, ci=c.get("ci")).items()
                                          if k in ("level", "badge", "verdict", "answer", "gain")}
                                      for e in probe.get("measured_efforts", [])}})
    return {"opted_in": True, "available": True, "sessions": sessions, "calibrations": summary,
            "parameters": {"slack_s": slack_s, "windows_days": list(windows), "levels_built": [0, 1, 3],
                           "attribution": "heuristic: repository + the session's activity intervals ± slack (without "
                                          "intervals: session start–end); ambiguous = not attributed",
                           "branches": choice_observatory.BRANCHES,
                           "calibration_match": "observatory.calibrations: exact project_id, cli and model"}}


def render(view):
    """Plain-text rendering of `view` (the same data the dashboard snapshot carries)."""
    if not view.get("opted_in"):
        return view.get("answer", NOT_OPTED_IN["answer"])
    if not view.get("available"):
        return f"observatory unavailable: {view.get('error')}"
    lines = [] if view["sessions"] else ["no session recorded (run observatory_history.py record)"]
    for session in view["sessions"]:
        lines.append(f"session {session['session_id']}")
        for number, q in enumerate(session["questions"], 1):
            lines.append(f"  {number}. {q['question']} [{q.get('badge') or 'no badge'}] {q['answer']}")
            if q.get("limits"):
                lines.append(f"     {q['limits']}")
    for c in view["calibrations"]:
        lines.append(f"calibration {c['cli']} {c['model']} ({c['analysis']})" + (f": {c['error']}" if c["error"] else ""))
        lines += [f"  at {effort}: [{v.get('badge') or 'no badge'}] {v['answer']}" for effort, v in c["by_effort"].items()]
        if c["limits"]:
            lines.append(f"  {c['limits']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Record session metadata for opted-in projects; report durability")
    parser.add_argument("command", choices=("record", "report", "questions"))
    parser.add_argument("--project-id")
    parser.add_argument("--config", default=str(HOME / "config.json"))
    parser.add_argument("--store", default=str(HOME / "observatory" / "sessions.jsonl"))
    args = parser.parse_args()
    import framework_cli
    config = read_config(args.config)
    section = config.get("observatory", {})
    entries = framework_cli.load_registry(framework_cli.default_registry_path())["projects"]
    if not section.get("projects") and section.get("auto") is not True:
        print("no project opted in: set observatory.projects or observatory.auto in " + args.config, file=sys.stderr)
        return 2
    if args.command == "record":
        collector = local_activity.ActivityCollector(lookback_hours=int(section.get("lookback_hours", 168)),
                                                     activity_gap_minutes=float(section.get("activity_gap_minutes", 30)))
        rows = snapshot(collector, entries, set(section.get("projects", [])), None, auto=section.get("auto") is True,
                        exclude=section.get("exclude", []))
        result = {"recorded": record(args.store, rows)}
        if collector.unreadable:
            result["unreadable_logs"] = len(collector.unreadable)
            print(f"{len(collector.unreadable)} compressed log(s) not read: needs Python 3.14+ (compression.zstd) or the zstd binary",
                  file=sys.stderr)
        print(json.dumps(result))
        return 0
    allowed_now = allowed(config, entries, args.store)
    now = datetime.now(timezone.utc).timestamp()
    repos = trial_repos(config)
    if args.command == "questions":
        cals = calibrations(config, Path(args.config).parent)
        shown = view(args.store, entries, args.project_id, allowed_now, cals, now, trial_repos=repos)
        if section.get("effort_trial"):  # amendment 3: the readout belongs to effort_trial_analysis.py, never to this listing
            import effort_trial_analysis
            effort_trial_analysis.blind_view(shown, "the pre-registered readout (effort_trial_analysis.py)")
        print(render(shown))
        return 0
    print(json.dumps(report(args.store, entries, args.project_id, allowed_now, now, trial_repos=repos), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
