#!/usr/bin/env python3
"""Run paired policy replays in isolated temporary directories.

The accepted implementation is never exposed to the agent. Similarity metrics
are emitted only as diagnostics; repository-specific acceptance commands decide
whether a cell passes.
"""

import argparse
import difflib
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path


TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_task_id(value):
    if not isinstance(value, str) or not TASK_ID.fullmatch(value):
        raise ValueError(f"unsafe task id: {value!r}")
    return value


def run(args, cwd=None, timeout=1800, input_text=None):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=timeout, input=input_text
    )


def new_archive_path(destination):
    fd, name = tempfile.mkstemp(
        prefix=f"{Path(destination).name}-", suffix=".tar", dir=Path(destination).parent
    )
    os.close(fd)
    return Path(name)


def extract_archive(archive, destination):
    destination_root = Path(destination).resolve()
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            target = (destination_root / member.name).resolve()
            # This containment check is sound only while links and all other
            # non-regular entry types remain rejected below.
            if destination_root not in target.parents and target != destination_root:
                raise RuntimeError(f"unsafe archive member: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(0o755)
                continue
            if not member.isfile():
                raise RuntimeError(f"archive entry is not a regular file: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise RuntimeError(f"cannot read archive member: {member.name}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)


def export_snapshot(repo, revision, destination):
    archive = new_archive_path(destination)
    try:
        result = run(["git", "archive", "--format=tar", f"--output={archive}", revision], cwd=repo, timeout=300)
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[:500])
        extract_archive(archive, destination)
    finally:
        archive.unlink(missing_ok=True)
    run(["git", "init", "-q"], cwd=destination)
    run(["git", "add", "-A"], cwd=destination)
    commit = run(
        ["git", "-c", "user.email=replay@local", "-c", "user.name=replay", "commit", "-qm", "base"],
        cwd=destination,
    )
    if commit.returncode:
        raise RuntimeError(commit.stderr.strip()[:500])


def changed_lines(repo, revision_range=None):
    args = ["git", "diff"]
    if revision_range:
        args.append(revision_range)
    result = run(args, cwd=repo, timeout=300)
    files, lines = set(), []
    for line in result.stdout.splitlines():
        if line.startswith("+++ b/"):
            files.add(line[6:])
        elif line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:].strip())
    return files, sorted(lines)


def diagnostics(task, workspace, source_repo):
    run(["git", "add", "-N", "--", "."], cwd=workspace, timeout=60)
    produced_files, produced_lines = changed_lines(workspace)
    accepted_files, accepted_lines = changed_lines(
        source_repo, f"{task['base']}..{task['accepted']}"
    )
    union = produced_files | accepted_files
    return {
        "file_jaccard_diagnostic": round(len(produced_files & accepted_files) / len(union), 3) if union else 0.0,
        "line_similarity_diagnostic": round(
            difflib.SequenceMatcher(None, "\n".join(produced_lines), "\n".join(accepted_lines)).ratio(), 3
        ) if produced_lines and accepted_lines else 0.0,
    }


def acceptance(task, workspace):
    results = []
    for command in task.get("acceptance", []):
        argv = command if isinstance(command, list) else shlex.split(command)
        result = run(argv, cwd=workspace, timeout=task.get("acceptance_timeout_s", 900))
        results.append({"command": argv, "exit": result.returncode, "tail": (result.stdout + result.stderr)[-1000:]})
    return results, bool(results) and all(item["exit"] == 0 for item in results)


def grade_cell(agent_exit, checks_passed):
    valid = agent_exit == 0
    return valid, valid and checks_passed


def experiment_seed(config):
    seed = config.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("replay set requires an integer seed fixed before execution")
    return seed


def write_summary(output_dir, seed, rows):
    (output_dir / "summary.json").write_text(
        json.dumps({"seed": seed, "cells": rows}, indent=2)
    )


def execute_cell(config, task, arm, replicate, output_dir, timeout_s):
    validate_task_id(task["id"])
    source_repo = Path(config["repos"][task["repo"]]).expanduser().resolve()
    policy = config["arms"][arm]
    workspace = Path(tempfile.mkdtemp(prefix=f"007-{task['id']}-{arm}-r{replicate:02d}-"))
    try:
        export_snapshot(source_repo, task["base"], workspace)
        prompt = workspace / ".007-prompt.txt"
        prompt.write_text(task["prompt"] + "\n\n" + policy["doctrine"])
        argv = [part.format(cwd=workspace, prompt_file=prompt, model=policy["model"], effort=policy["effort"])
                for part in config["agent_command"]]
        started = time.monotonic()
        try:
            agent = run(argv, cwd=workspace, timeout=timeout_s, input_text=prompt.read_text())
            exit_code, tail = agent.returncode, (agent.stdout + agent.stderr)[-1500:]
        except subprocess.TimeoutExpired:
            exit_code, tail = -9, "TIMEOUT"
        prompt.unlink(missing_ok=True)
        checks, checks_passed = acceptance(task, workspace)
        valid, accepted = grade_cell(exit_code, checks_passed)
        record = {
            "schema": "007-framework/replay-cell/v1",
            "task": task["id"],
            "arm": arm,
            "replicate": replicate,
            "requested_model": policy["model"],
            "requested_effort": policy["effort"],
            "served_model": "unmeasured",
            "served_effort": "unmeasured",
            "tokens": "unmeasured",
            "agent_exit": exit_code,
            "wall_s": round(time.monotonic() - started, 2),
            "valid": valid,
            "accepted": accepted,
            "acceptance": checks,
            **diagnostics(task, workspace, source_repo),
            "agent_tail": tail,
        }
        (output_dir / f"{task['id']}-r{replicate:02d}-{arm}.json").write_text(json.dumps(record, indent=2))
        return record
    finally:
        shutil.rmtree(workspace)


def main():
    parser = argparse.ArgumentParser(description="Run frozen OLD×NEW coding replays")
    parser.add_argument("--set", required=True)
    parser.add_argument("command", choices=("list", "run"))
    parser.add_argument("--tasks", default="all", help="all or comma-separated task ids")
    parser.add_argument("--arms", default="OLD,NEW")
    parser.add_argument("--out", default="replay-results")
    parser.add_argument("--timeout-min", type=int, default=30)
    parser.add_argument("--replicates", type=int, default=1)
    args = parser.parse_args()
    config = json.loads(Path(args.set).expanduser().read_text())
    tasks = config["tasks"]
    for task in tasks:
        validate_task_id(task["id"])
    if args.command == "list":
        for task in tasks:
            print(f"{task['id']:24s} {task.get('class', 'unclassified'):12s} {task.get('subject', '')}")
        return 0

    wanted = None if args.tasks == "all" else set(args.tasks.split(","))
    tasks = [task for task in tasks if wanted is None or task["id"] in wanted]
    arms = args.arms.split(",")
    unknown = set(arms) - set(config["arms"])
    if unknown:
        parser.error(f"unknown arms: {sorted(unknown)}")
    output_dir = Path(args.out).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    if args.replicates < 1:
        parser.error("--replicates must be at least 1")
    seed = experiment_seed(config)
    rng = random.Random(seed)
    rows = []
    for task in tasks:
        for replicate in range(1, args.replicates + 1):
            pair = arms[:]
            rng.shuffle(pair)
            for arm in pair:
                record = execute_cell(config, task, arm, replicate, output_dir, args.timeout_min * 60)
                record["execution_index"] = len(rows) + 1
                rows.append(record)
                if not record["valid"]:
                    write_summary(output_dir, seed, rows)
                    print(f"invalid cell: {task['id']} r{replicate:02d} {arm}; stopped", file=sys.stderr)
                    return 2
    write_summary(output_dir, seed, rows)
    print(f"wrote {len(rows)} cells to {output_dir}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
