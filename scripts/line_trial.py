#!/usr/bin/env python3
"""`007 trial`: randomize effort per launcher run and measure whether the lines each run added are still there N days later.

assign    the arm of a run, from sha256(seed:run_id): any launcher can call it, no state, no vendor.
record    after the run: content hashes of every line it added (base..HEAD or the working tree), appended to a JSONL ledger.
survival  for each recorded run old enough: share of its added lines still present, by content, at the last first-parent
          revision on or before run time + days. Content, not blame, so it holds whoever commits and however the work is squashed.
No model and no network; git only. Usage:
  line_trial.py assign --seed S --run-id ID [--arms medium,high]
  line_trial.py record --repo R --run-id ID --arm A --base SHA --ledger L.jsonl [--worktree]
  line_trial.py survival --repo R --ledger L.jsonl [--days 30] [--branch main]
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

DAY = 86400


def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr.strip()[:300] or "git failed")
    return p.stdout


def assign(seed, run_id, arms=("medium", "high")):
    return arms[int(hashlib.sha256(f"{seed}:{run_id}".encode()).hexdigest(), 16) % len(arms)]


def _key(line):
    """Hash of a meaningful added line; None for blank or punctuation-only lines, which would match anywhere."""
    text = line.strip()
    # ponytail: a 4-char floor stops "}" and ")" from surviving by coincidence; a token-level filter if short lines matter
    return hashlib.sha256(text.encode()).hexdigest()[:16] if len(text) >= 4 and any(c.isalnum() for c in text) else None


def added_lines(repo, base, worktree=False):
    diff = git(repo, "diff", "--no-color", "--unified=0", "--no-renames", base, *([] if worktree else ["HEAD"]))
    files, current = {}, None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = None if line.endswith("/dev/null") else line[6:]
        elif line.startswith("+") and current and (key := _key(line[1:])):
            files.setdefault(current, []).append(key)
    if worktree:  # files the run created are untracked: `git diff` never lists them
        for path in filter(None, git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\0")):
            keys = [k for k in map(_key, (Path(repo) / path).read_text(errors="ignore").splitlines()) if k]
            if keys:
                files[path] = keys
    return files


def record(repo, run_id, arm, base, ledger, worktree=False):
    files = added_lines(repo, base, worktree)
    entry = {"schema": "007-line-trial/v1", "run_id": run_id, "arm": arm, "base": base, "head": git(repo, "rev-parse", "HEAD").strip(),
             "worktree": worktree, "at": int(time.time()), "added": sum(map(len, files.values())), "files": files}
    with open(ledger, "a") as handle:
        handle.write(json.dumps(entry) + "\n")
    return {k: v for k, v in entry.items() if k != "files"}


def alive(repo, entry, rev):
    """Recorded lines whose content still appears in the same file at `rev` (counted as a multiset, never above what was added)."""
    kept = 0
    for path, keys in entry["files"].items():
        try:
            present = Counter(k for k in map(_key, git(repo, "show", f"{rev}:{path}").splitlines()) if k)
        except RuntimeError:  # file deleted or renamed away: its lines are gone
            continue
        kept += sum(min(n, present[k]) for k, n in Counter(keys).items())
    return kept


def survival(repo, ledger, days=30, branch="main", now=None):
    now = time.time() if now is None else now
    out = []
    for line in Path(ledger).read_text().splitlines():
        entry = json.loads(line)
        due = entry["at"] + days * DAY
        if due > now or not entry["added"]:
            out.append({"run_id": entry["run_id"], "arm": entry["arm"], "status": "pending" if due > now else "empty"})
            continue
        rev = git(repo, "rev-list", "-1", "--first-parent", f"--before=@{due}", branch).strip()
        kept = alive(repo, entry, rev)
        out.append({"run_id": entry["run_id"], "arm": entry["arm"], "status": "mature", "added": entry["added"], "alive": kept,
                    "share": kept / entry["added"], "rev": rev, "matured_at": datetime.fromtimestamp(due, timezone.utc).isoformat()})
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(prog="007 trial")
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("assign")
    a.add_argument("--seed", required=True)
    a.add_argument("--run-id", required=True)
    a.add_argument("--arms", default="medium,high")
    r = sub.add_parser("record")
    s = sub.add_parser("survival")
    for p in (r, s):
        p.add_argument("--repo", required=True)
        p.add_argument("--ledger", required=True)
    r.add_argument("--run-id", required=True)
    r.add_argument("--arm", required=True)
    r.add_argument("--base", required=True)
    r.add_argument("--worktree", action="store_true")
    s.add_argument("--days", type=int, default=30)
    s.add_argument("--branch", default="main")
    args = parser.parse_args(argv)
    if args.command == "assign":
        print(assign(args.seed, args.run_id, tuple(args.arms.split(","))))
    elif args.command == "record":
        print(json.dumps(record(args.repo, args.run_id, args.arm, args.base, args.ledger, args.worktree)))
    else:
        print(json.dumps(survival(args.repo, args.ledger, args.days, args.branch)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
