#!/usr/bin/env python3
"""Approximate how many attributable agent-authored lines were later changed."""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


DEFAULT_AGENT_REGEX = r"(?i)codex|claude|copilot|kimi|agent|bot|co-authored-by:.*(claude|codex|openai|moonshot)"


def git(repo, *args):
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, timeout=60
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:300] or "git command failed")
    return result.stdout


def calculate(repo, days=30, agent_regex=DEFAULT_AGENT_REGEX, max_commits=60):
    repo = Path(repo).expanduser().resolve()
    if not (repo / ".git").exists():
        raise ValueError(f"not a Git repository: {repo}")

    pattern = re.compile(agent_regex)
    log = git(
        repo,
        "log",
        f"--since={days} days ago",
        "--no-merges",
        "--format=%H%x1f%an <%ae>%x1f%(trailers:key=Co-Authored-By,valueonly,separator=; )",
    )
    commits = []
    for line in log.splitlines():
        fields = line.split("\x1f")
        if len(fields) == 3:
            sha, author, trailers = fields
            commits.append((sha, bool(pattern.search(author) or pattern.search(trailers))))
    agents = [sha for sha, is_agent in commits if is_agent][:max_commits]
    human_count = sum(not is_agent for _, is_agent in commits)
    if not agents:
        return {
            "window_days": days,
            "agent_commits": 0,
            "human_commits": human_count,
            "agent_lines_added": 0,
            "surviving_lines": 0,
            "rate": None,
            "reason": "no attributable agent commits",
        }

    added = {}
    files = defaultdict(set)
    for sha in agents:
        total = 0
        for line in git(repo, "show", "--numstat", "--format=", sha).splitlines():
            fields = line.split("\t")
            if len(fields) == 3 and fields[0].isdigit():
                total += int(fields[0])
                files[sha].add(fields[2])
        added[sha] = total

    prefixes = {sha[:12]: sha for sha in agents}
    surviving = defaultdict(int)
    for filename in sorted({name for names in files.values() for name in names}):
        try:
            blame = git(repo, "blame", "-w", "--line-porcelain", "HEAD", "--", filename)
        except RuntimeError:
            continue
        for line in blame.splitlines():
            token = line.split(" ", 1)[0]
            if token[:12] in prefixes and len(token) >= 12:
                surviving[prefixes[token[:12]]] += 1

    total_added = sum(added.values())
    total_surviving = sum(min(surviving[sha], added[sha]) for sha in agents)
    rate = 0.0 if total_added == 0 else 100 * (1 - total_surviving / total_added)
    return {
        "window_days": days,
        "agent_commits": len(agents),
        "human_commits": human_count,
        "agent_lines_added": total_added,
        "surviving_lines": total_surviving,
        "rate": rate,
        "reason": None,
    }


def main():
    parser = argparse.ArgumentParser(description="Estimate corrective touch rate from Git attribution")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--agent-regex", default=DEFAULT_AGENT_REGEX)
    parser.add_argument("--max-commits", type=int, default=60)
    args = parser.parse_args()
    result = calculate(args.repo, args.days, args.agent_regex, args.max_commits)
    print(
        f"repo={Path(args.repo).expanduser().resolve()} window={args.days}d "
        f"agent_commits={result['agent_commits']} human_commits={result['human_commits']}"
    )
    if result["rate"] is None:
        print("TOUCH-RATE N/D (no attributable agent commits)")
        return 0
    print(
        f"agent_lines_added={result['agent_lines_added']} "
        f"surviving={result['surviving_lines']} TOUCH-RATE≈{result['rate']:.1f}%"
    )
    print("approximation: renames, deletions, formatting, and mixed commits can distort this value")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
