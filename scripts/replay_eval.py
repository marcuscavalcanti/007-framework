#!/usr/bin/env python3
"""Run paired policy replays in isolated temporary directories.

The accepted implementation is never exposed to the agent. Similarity metrics
are emitted only as diagnostics; repository-specific acceptance commands decide
whether a cell passes.
"""

import argparse
import difflib
import hashlib
import json
import os
import random
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
import replay_capture
import harness_report


TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CUSTOM_COST_SOURCE = re.compile(r"^custom:[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
COST_UNAVAILABLE_FIELDS = (
    "observed_cost_status", "observed_cost_source", "normalized_cost_source",
    "cost_unavailable_reason", "policy_sha256",
)
USAGE_COUNTERS = ("input_tokens", "output_tokens", "total_tokens")
D0_DIAGNOSTIC_FIELDS = (
    "changed_files", "lines_added", "lines_deleted", "binary_files_changed",
    "dependency_manifests_changed", "file_jaccard_diagnostic", "line_similarity_diagnostic",
)
ACCEPT_OUTCOMES = ("pass", "fail", "error", "skip", "expected-failure", "unexpected-success")
MAX_ACCEPT_OUTCOMES = 2000
MAX_CANDIDATE_PATCH = 4 * 1024 * 1024
DEPENDENCY_MANIFESTS = {
    "Cargo.toml", "Gemfile", "Pipfile", "go.mod", "package.json",
    "package-lock.json", "pnpm-lock.yaml", "poetry.lock", "pyproject.toml",
    "requirements.txt", "uv.lock", "yarn.lock",
}


def validate_task_id(value):
    if not isinstance(value, str) or not TASK_ID.fullmatch(value):
        raise ValueError(f"unsafe task id: {value!r}")
    return value


class CleanupIncomplete(RuntimeError):
    """Raised when a command returned but its 007-created process group was not confirmed gone."""

    def __init__(self, state, process, original=None):
        super().__init__(f"{state}: process group {process.pid} after command returned")
        self.state, self.returncode, self.original = state, process.returncode, original


def kill_process_group(process, wait_s=2.0):
    """SIGKILL every remaining member of the child's group and observe the outcome.

    Returns "gone", "cleanup-child-unconfirmed" (child exit not confirmed within
    wait_s) or "cleanup-group-observable" (group still observable; no execution
    inferred). Every wait consumes the same deadline; sending SIGKILL is not proof.
    """
    deadline = time.monotonic() + wait_s
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return "gone"
    except PermissionError:
        # Initial signal denied: group absence is unconfirmed.
        return "cleanup-group-observable"
    try:
        process.wait(timeout=max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        return "cleanup-child-unconfirmed"
    while True:
        if time.monotonic() >= deadline:
            return "cleanup-group-observable"
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return "gone" if time.monotonic() <= deadline else "cleanup-group-observable"
        except PermissionError:
            pass  # A transient poll denial is not success; await confirmed absence.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "cleanup-group-observable"
        time.sleep(min(0.01, remaining))


def validate_timeout(seconds):
    # POSIX poll accepts a signed32-bit millisecond wait.
    if not harness_report._valid_money(seconds) or not 0 < seconds <= (2**31 - 1) // 1000:
        raise ValueError("timeout limit must be positive and fit the portable subprocess wait range")
    return seconds


def run(args, cwd=None, timeout=1800, input_text=None, env=None):
    timeout = validate_timeout(timeout)
    # The child leads its own session; whenever it returns (exit, failure or timeout)
    # every remaining member of that group is killed before the result is interpreted.
    # No context manager: Popen.__exit__ would add an unbounded wait.
    process = subprocess.Popen(
        args, cwd=cwd, env=env, stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    original = None
    try:
        stdout, stderr = process.communicate(input_text, timeout=timeout)
    except BaseException as exc:
        original = exc
        raise
    finally:
        # Pipes close even if cleanup itself raises; an unexpected cleanup exception
        # propagates with the original exception kept as its context.
        try:
            state = kill_process_group(process)
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        if state != "gone":
            raise CleanupIncomplete(state, process, original) from original
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def new_archive_path(destination):
    fd, name = tempfile.mkstemp(
        prefix=f"{Path(destination).name}-", suffix=".tar", dir=Path(destination).parent
    )
    os.close(fd)
    return Path(name)


def extract_archive(archive, destination):
    destination_root = Path(destination).resolve()
    links = []
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            target = (destination_root / member.name).resolve()
            # This containment check is sound only while no link exists on disk: hard links and other non-regular entries are
            # rejected below, and symbolic links are only materialized as copies, after every regular entry is written.
            if destination_root not in target.parents and target != destination_root:
                raise RuntimeError(f"unsafe archive member: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(0o755)
                continue
            if member.issym():
                links.append(member)
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
    materialize_links(links, destination_root)


def materialize_links(links, root):
    """A relative symbolic link whose target stays inside the snapshot becomes a copy of that target (a file, or a directory
    without links); links to links resolve in later passes. An absolute link, one that leaves the snapshot, one that contains its
    own target, or one whose target never appears is refused: the snapshot never holds a link."""
    pending = list(links)
    while pending:
        later = []
        for member in pending:
            target = root / member.name
            if os.path.isabs(member.linkname):
                raise RuntimeError(f"archive link is absolute: {member.name}")
            source = Path(os.path.normpath(target.parent / member.linkname))
            if root not in source.parents and source != root:
                raise RuntimeError(f"archive link leaves the snapshot: {member.name}")
            if not source.exists():
                later.append(member)
                continue
            if source.is_dir():
                if target == source or source in target.parents:
                    raise RuntimeError(f"archive link contains its own target: {member.name}")
                shutil.copytree(source, target, symlinks=False)
            else:
                shutil.copyfile(source, target)
                target.chmod(source.stat().st_mode & 0o777)
        if len(later) == len(pending):
            raise RuntimeError(f"archive link has no target in the snapshot: {later[0].name}")
        pending = later


def export_snapshot(repo, revision, destination):
    archive = new_archive_path(destination)
    try:
        result = run(["git", "archive", "--format=tar", f"--output={archive}", revision], cwd=repo, timeout=300)
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[:500])
        extract_archive(archive, destination)
    finally:
        archive.unlink(missing_ok=True)
    initialize_snapshot(destination)


def initialize_snapshot(destination):
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


def diagnostics(task, workspace, source_repo, base):
    """The candidate's change: the work tree against `base`, the snapshot commit fixed before the agent ran, so staging or
    committing it changes nothing (audit 2026-11-08, F02)."""
    run(["git", "add", "-N", "--", "."], cwd=workspace, timeout=60)
    produced_files, produced_lines = changed_lines(workspace, base)
    numstat = run(["git", "diff", "--numstat", base], cwd=workspace, timeout=300)
    added = deleted = 0
    binary = []
    complete = numstat.returncode == 0
    for line in numstat.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0] == parts[1] == "-":
            binary.append(parts[2])
            continue
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            complete = False
            continue
        added += int(parts[0])
        deleted += int(parts[1])
    accepted_files, accepted_lines = changed_lines(
        source_repo, f"{task['base']}..{task['accepted']}"
    ) if source_repo is not None else (set(), [])
    union = produced_files | accepted_files
    return {
        "d0_complete": complete,
        "changed_files": len(produced_files),
        "lines_added": added,
        "lines_deleted": deleted,
        "binary_files_changed": sorted(binary),
        "dependency_manifests_changed": sorted(
            path for path in produced_files if Path(path).name in DEPENDENCY_MANIFESTS
        ),
        "file_jaccard_diagnostic": "unmeasured" if source_repo is None else round(len(produced_files & accepted_files) / len(union), 3) if union else 0.0,
        "line_similarity_diagnostic": round(
            difflib.SequenceMatcher(None, "\n".join(produced_lines), "\n".join(accepted_lines)).ratio(), 3
        ) if produced_lines and accepted_lines else "unmeasured" if source_repo is None else 0.0,
    }


def _diagnostic_retention(config, output_dir):
    retain = config.get("retain_diagnostic_text", True)
    if type(retain) is not bool:
        raise ValueError("retain_diagnostic_text must be a boolean")
    if output_dir.is_symlink():
        raise ValueError("replay output directory must not be a symlink")
    return retain


def _output_metadata(result):
    # Popen text mode normalizes newlines: these hashes describe re-encoded text, not original wire bytes.
    metadata = {"representation": "subprocess-text-utf8"}
    for name in ("stdout", "stderr"):
        payload = (getattr(result, name) or "").encode("utf-8")
        metadata[name + "_utf8_sha256"] = hashlib.sha256(payload).hexdigest()
        metadata[name + "_utf8_bytes"] = len(payload)
    return metadata


def acceptance_policy(sandbox=None, env=None):
    """A configured prefix is not proof of sandboxing; an explicit environment never inherits the parent's values."""
    if sandbox is not None and not (isinstance(sandbox, list) and all(isinstance(part, str) for part in sandbox)):
        raise ValueError("acceptance_sandbox must be a list of strings")
    if env is not None and (not isinstance(env, Mapping) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in env.items())):
        raise ValueError("acceptance_env must be a string mapping or null")
    return list(sandbox or []), dict(os.environ if env is None else env)


def acceptance(task, workspace, sandbox=None, env=None, *, retain_diagnostic_text=True):
    sandbox, env = acceptance_policy(sandbox, env)
    if type(retain_diagnostic_text) is not bool:
        raise ValueError("retain_diagnostic_text must be a boolean")
    results = []
    for command in task.get("acceptance", []):
        argv = command if isinstance(command, list) else shlex.split(command)
        if sandbox:
            argv = [part.replace("{cwd}", str(workspace)) for part in sandbox] + list(argv)
        result = run(argv, cwd=workspace, timeout=task.get("acceptance_timeout_s", 900), env=env)
        results.append({"command": argv if retain_diagnostic_text else [], "exit": result.returncode,
                        "tail": (result.stdout + result.stderr)[-1000:] if retain_diagnostic_text else "",
                        "command_sha256": hashlib.sha256(json.dumps(argv).encode()).hexdigest(),
                        "output": _output_metadata(result), "diagnostic_text_retained": retain_diagnostic_text})
    return results, bool(results) and all(item["exit"] == 0 for item in results)


def acceptance_outcomes(path):
    """r45: the commit_replay.BOOT report, test id -> outcome only (never output); anything else is unavailable."""
    try:
        value = json.loads(replay_capture._read(Path(path), replay_capture.MAX_MANIFEST))
    except (OSError, ValueError, RecursionError):
        return "unavailable"
    ok = isinstance(value, dict) and len(value) <= MAX_ACCEPT_OUTCOMES and all(v in ACCEPT_OUTCOMES for v in value.values())
    return value if ok else "unavailable"


def candidate_patch(workspace, destination, base):
    """r45 opt-in: the candidate's change against `base`, the snapshot commit fixed before the agent ran (an agent's own commit
    used to empty the patch: audit 2026-11-08, F02), untracked files included (ignored ones are not)."""
    with tempfile.TemporaryDirectory(prefix="007-patch-") as scratch:
        staged = Path(scratch) / "candidate.patch"
        diff = ["git", "diff", "--cached", "--binary", "--no-color", "--no-ext-diff", "--no-textconv", f"--output={staged}", base]
        if run(["git", "add", "-A"], cwd=workspace, timeout=300).returncode or run(diff, cwd=workspace, timeout=300).returncode:
            return "unavailable"
        if staged.stat().st_size > MAX_CANDIDATE_PATCH:
            return "too-large"
        payload = staged.read_bytes()
    replay_capture.write_bytes_no_replace(destination, payload, "candidate patch")
    return {"path": destination.name, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}


def hidden_target(workspace, value):
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"unsafe hidden acceptance target: {value!r}")
    root = Path(workspace).resolve()
    target = root / relative
    current = root
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            raise ValueError(f"unsafe hidden acceptance parent: {value!r}")
        current.mkdir(exist_ok=True)
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError(f"unsafe hidden acceptance target: {value!r}")
    return target


def reset_to_base(task, workspace):
    """Paths matching task["reset_to_base"] that the agent changed, other than hidden targets: the oracle grades them at base. A Go
    test the agent wrote beside a hidden one can redeclare its names and break the whole package, and the agent's tests never grade."""
    patterns = task.get("reset_to_base", [])
    if not patterns:
        return {}
    git = lambda *args: run(["git", *args], cwd=workspace, timeout=300)
    roots = git("rev-list", "--max-parents=0", "HEAD").stdout.split()
    if len(roots) != 1:
        raise ValueError("reset_to_base needs the base snapshot repository")
    listed = lambda *args: set(filter(None, git(*args).stdout.split("\0")))
    changed = listed("diff", "--name-only", "--no-renames", "-z", roots[0]) | listed("ls-files", "--others", "-z")
    in_base = listed("ls-tree", "-r", "--name-only", "-z", roots[0])
    hidden = {entry["target"] for entry in task.get("hidden_acceptance", [])}
    return {name: roots[0] if name in in_base else None for name in sorted(changed - hidden) if any(Path(name).match(p) for p in patterns)}


@contextmanager
def hidden_acceptance(task, workspace):
    backups = []
    try:
        for name, root in reset_to_base(task, workspace).items():
            target = hidden_target(workspace, name)
            backups.append((name, target.read_bytes() if target.exists() else None))
            target.unlink(missing_ok=True)
            if root is not None and run(["git", "--literal-pathspecs", "checkout", root, "--", name], cwd=workspace, timeout=300).returncode:
                raise ValueError(f"cannot reset to base: {name}")
        for entry in task.get("hidden_acceptance", []):
            source = Path(entry["source"]).expanduser().resolve()
            hidden_bytes = source.read_bytes()
            digest = hashlib.sha256(hidden_bytes).hexdigest()
            if not SHA256.fullmatch(entry.get("sha256", "")) or digest != entry["sha256"]:
                raise ValueError(f"hidden acceptance hash mismatch: {source}")
            target = hidden_target(workspace, entry["target"])
            backups.append((entry["target"], target.read_bytes() if target.exists() else None))
            target.write_bytes(hidden_bytes)
        yield
    finally:
        for value, previous in reversed(backups):
            target = hidden_target(workspace, value)
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(previous)


def grade_cell(agent_exit, checks_passed):
    valid = agent_exit == 0
    return valid, valid and checks_passed


def cost_unavailable_map(config):
    allow = config.get("allow_cost_unavailable", False)
    if not isinstance(allow, bool):
        raise ValueError("allow_cost_unavailable must be a boolean")
    if not allow:
        if "cost_unavailable_map" in config:
            raise ValueError("cost_unavailable_map requires allow_cost_unavailable: true")
        return {}
    entries = config.get("cost_unavailable_map")
    if not isinstance(entries, list):
        raise ValueError("allow_cost_unavailable requires a cost_unavailable_map list")
    mapping = {}
    for entry in entries:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key), str) and entry[key] for key in COST_UNAVAILABLE_FIELDS
        ):
            raise ValueError(f"cost_unavailable_map entries require: {', '.join(COST_UNAVAILABLE_FIELDS)}")
        if not CUSTOM_COST_SOURCE.fullmatch(entry["normalized_cost_source"]):
            raise ValueError("normalized_cost_source must use custom:<name>")
        if not SHA256.fullmatch(entry["policy_sha256"]):
            raise ValueError("policy_sha256 must be a lowercase SHA-256")
        observed = (entry["observed_cost_status"], entry["observed_cost_source"])
        if observed in mapping:
            raise ValueError(f"duplicate cost_unavailable_map entry: {observed}")
        mapping[observed] = entry
    return mapping


def validate_usage(value):
    usage = value.get("usage")
    if usage is None:
        return None, None
    if not isinstance(usage, dict):
        return None, "usage-invalid"
    for key in USAGE_COUNTERS:
        if key in usage and (
            isinstance(usage[key], bool) or not isinstance(usage[key], int) or usage[key] < 0
        ):
            return None, "usage-invalid"
    return usage, None


def validate_served_identity(value, policy, unavailable_map=None, requested_only=False):
    if value is None:
        return None, "served-identity-missing"
    if not isinstance(value, dict) or value.get("schema") != "007-framework/runner-receipt/v1":
        return None, "runner-receipt-invalid"
    if value.get("valid") is not True:
        return None, "runner-invalid"
    if value.get("requested") != {key: policy.get(key) for key in ("provider", "model", "effort")}:
        return None, "requested-policy-mismatch"
    served = value.get("served")
    if not isinstance(served, dict):
        return None, "served-identity-missing"
    for key in ("provider", "model", "effort"):
        if requested_only and served.get(key) is None:
            continue  # master plan 3.2 decision 2(a): an unreported field stays "unverified", never copied from the request
        if served.get(key) != policy.get(key):
            return None, f"served-{key}-mismatch"
    if not isinstance(value.get("identity_source"), str) or not value["identity_source"]:
        return None, "identity-source-missing"
    if not isinstance(value.get("source_sha256"), str) or not SHA256.fullmatch(value["source_sha256"]):
        return None, "identity-source-hash-invalid"
    cost = value.get("cost_usd")
    observed = (value.get("cost_status"), value.get("cost_source"))
    unavailable = None
    if "cost_usd" in value and cost is None and all(isinstance(item, str) for item in observed):
        unavailable = (unavailable_map or {}).get(observed)
        if unavailable and value.get("cost_policy_sha256") != unavailable["policy_sha256"]:
            unavailable = None
    if unavailable is None and not harness_report._valid_money(cost):
        return None, "cost-missing"
    if not isinstance(value.get("cost_source"), str) or not value["cost_source"]:
        return None, "cost-source-missing"
    usage, usage_failure = validate_usage(value)
    if usage_failure:
        return None, usage_failure
    identity = {
        **served,
        **{key: "unverified" for key in ("provider", "model", "effort") if served.get(key) is None},
        "identity_source": value["identity_source"],
        "source_sha256": value["source_sha256"],
        "usage": usage,
        "cost_usd": cost,
        "cost_source": value["cost_source"],
    }
    if unavailable is not None:
        identity.update({
            "cost_status": "unavailable",
            "cost_source": unavailable["normalized_cost_source"],
            "cost_unavailable_reason": unavailable["cost_unavailable_reason"],
            "cost_status_observed": observed[0],
            "cost_source_observed": observed[1],
            "cost_policy_sha256": value["cost_policy_sha256"],
        })
    return identity, None


def experiment_seed(config):
    seed = config.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("replay set requires an integer seed fixed before execution")
    return seed


def experiment_replicates(config, requested):
    configured = config.get("replicates_per_arm_task")
    if configured is None:
        configured = 1 if requested is None else requested
    if not isinstance(configured, int) or isinstance(configured, bool) or configured < 1:
        raise ValueError("replicates_per_arm_task must be a positive integer")
    if requested is not None and requested != configured:
        raise ValueError("--replicates does not match the frozen replay set")
    return configured


def experiment_schedule(config, arms, replicates):
    rng = random.Random(experiment_seed(config))
    schedule = {}
    for task in config["tasks"]:
        for replicate in range(1, replicates + 1):
            pair = arms[:]
            rng.shuffle(pair)
            schedule[(task["id"], replicate)] = pair
    return schedule


def write_summary(output_dir, replay_set, config, replicates, rows):
    (output_dir / "summary.json").write_text(
        json.dumps({
            "experiment_id": config.get("experiment_id"),
            "replay_set_sha256": hashlib.sha256(replay_set.read_bytes()).hexdigest(),
            "seed": experiment_seed(config),
            "replicates_per_arm_task": replicates,
            "cells": rows,
        }, indent=2)
    )


def is_cell_id(value):
    return isinstance(value, str) and re.fullmatch(r".+-r[0-9]{2,}-.+", value) is not None


CELL_ARTIFACT_SUFFIXES = (".json", ".runner.json", ".observation.json", ".prompt.txt", ".candidate.patch", ".stream.jsonl")


def artifact_case_sensitive(directory):
    with tempfile.TemporaryDirectory(prefix=".007-names-", dir=directory) as temporary:
        root = Path(temporary)
        (root / "CaseProbe").write_bytes(b"")
        return not (root / "caseprobe").exists()


def validate_cell_artifacts(tasks, arms, replicates, *, directory=None):
    sensitive = directory is None or artifact_case_sensitive(directory)
    paths = set()
    for task in tasks:
        validate_timeout(task.get("acceptance_timeout_s", 900))
        for replicate in range(1, replicates + 1):
            for arm in arms:
                identifier = cell_id(task, arm, replicate)
                for suffix in CELL_ARTIFACT_SUFFIXES:
                    path = identifier + suffix
                    key = path if sensitive else path.casefold()
                    if key in paths:
                        raise ValueError("task and arm pairs must produce distinct cell identities and artifact paths")
                    paths.add(key)


def read_cell_artifacts(directory):
    """Read identified cell/receipt shapes before applying legacy filename conventions. Never rewrite ambiguous evidence."""
    results, receipts = {}, {}
    for path in sorted(directory.iterdir()):
        if not path.name.endswith(".json") or not is_cell_id(path.stem):
            continue
        raw = path.read_bytes()
        row = json.loads(raw) if raw.strip() else {}
        if not isinstance(row, dict):
            raise ValueError("invalid replay artifact")
        if row.get("schema") == "007-framework/replay-cell/v1" or "runner_receipt_sha256" in row:
            results[path.stem] = row
        elif row.get("observation_kind") == "replay-candidate":
            continue
        elif path.name.endswith(".runner.json"):
            if row.get("schema") is None and "valid" in row:
                paired_result = directory / (path.name.removesuffix(".runner.json") + ".json")
                if not paired_result.is_file() or (directory / (path.stem + ".runner.json")).exists():
                    raise ValueError("ambiguous legacy replay artifact")
            receipts[path.name.removesuffix(".runner.json")] = row
        else:
            results[path.stem] = row
    return results, receipts


def load_dispatch_history(directory):
    """Share timestamp and per-stage uniqueness checks between recovery and observational accounting."""
    try:
        lines = (directory / "dispatch.jsonl").read_text().splitlines()
    except FileNotFoundError:
        lines = []
    rows, invalid, ambiguous = [], 0, 0
    seen = {"dispatched_at": {}, "finished_at": {}}
    # a refused attempt set aside (`requeued`) may be dispatched once more, and that dispatch finished once more
    again = {"dispatched_at": set(), "finished_at": set()}
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            invalid += 1
            continue
        times = {key: harness_report._instant(row[key]) for key in seen if key in row} if isinstance(row, dict) else {}
        if not isinstance(row, dict) or not is_cell_id(row.get("cell")) or not times or any(t is None for t in times.values()):
            invalid += 1
            continue
        for key, stamp in times.items():
            if row["cell"] in again[key]:
                again[key].discard(row["cell"])
                if key == "dispatched_at":
                    again["finished_at"].add(row["cell"])
            else:
                ambiguous += row["cell"] in seen[key]
            seen[key][row["cell"]] = stamp
        if "finished_at" in times and row.get("requeued") is True:
            again["dispatched_at"].add(row["cell"])
        rows.append(row)
    for cell in seen["dispatched_at"].keys() & seen["finished_at"].keys():
        invalid += seen["finished_at"][cell] < seen["dispatched_at"][cell]
    return rows, invalid, ambiguous


def cell_id(task, arm, replicate):
    validate_task_id(task["id"])
    validate_task_id(arm)
    if type(replicate) is not int or replicate < 1:
        raise ValueError("replicate must be a positive integer")
    return f"{task['id']}-r{replicate:02d}-{arm}"


def execute_reserved_cell(config, task, arm, replicate, output_dir, timeout_s, *, vault_root, budget, upper_usd, bound_source_sha256):
    _diagnostic_retention(config, output_dir)
    if "replay_ref" in task or vault_root is not None:
        if vault_root is None or task.get("replay_ref") is None:
            raise ValueError("retained replay requires an explicit vault and reference")
        metadata = replay_capture.validate_replay_ref(
            vault_root, task["project_id"], task.get("source_task_id", task["id"]), task["replay_ref"])
        if metadata["schema"] == replay_capture.INPUT_SCHEMA_V2:
            raise ValueError("v2-execution-unqualified")
    identifier = cell_id(task, arm, replicate)
    grant = budget.reserve(identifier, "executor_cells", upper_usd, bound_source_sha256=bound_source_sha256)
    if not grant["launch_granted"]:
        raise ValueError("replay call already reserved; never launch a second time")
    # Exceptions retain the reservation: unknown execution/spend is not an automatic refund.
    record = execute_cell(config, task, arm, replicate, output_dir, timeout_s, vault_root=vault_root)
    payload = replay_capture._read(output_dir / (identifier + ".json"), replay_capture.MAX_MANIFEST)
    if payload != replay_capture._json_bytes(record):
        raise ValueError("cell bytes changed before budget reconciliation; reservation retained")
    source_basis = harness_report.receipt_cost_basis(record)
    cost = record.get("cost_usd")
    if source_basis != grant["state"]["cost_basis"] or not harness_report._valid_money(cost):
        cost = None
    state = budget.settle(identifier, cost, cost_basis=grant["state"]["cost_basis"], source_sha256=hashlib.sha256(payload).hexdigest())
    if state["violations"]:
        raise ValueError("observed cost violated reservation; cell preserved, dispatch stopped")
    return record


def execute_cell(config, task, arm, replicate, output_dir, timeout_s, *, vault_root=None):
    timeout_s = validate_timeout(timeout_s)
    retain_text = _diagnostic_retention(config, output_dir)
    acceptance_sandbox, acceptance_env = acceptance_policy(config.get("acceptance_sandbox"), config.get("acceptance_env"))
    attempt_id = cell_id(task, arm, replicate)
    for suffix in CELL_ARTIFACT_SUFFIXES:
        existing = output_dir / (attempt_id + suffix)
        if existing.exists() or existing.is_symlink():
            raise RuntimeError(f"replay output already exists: {existing}")
    identity_mode = config.get("served_identity")
    if identity_mode is not None and (identity_mode not in ("verified", "requested-only") or config.get("require_served_identity")):
        raise ValueError("served identity policy must be verified or requested-only, without require_served_identity")
    if config.get("require_served_identity"):
        identity_mode = "verified"
    unavailable_map = cost_unavailable_map(config)
    metadata, retained_ref = None, None
    if "replay_ref" in task or vault_root is not None:
        if vault_root is None or task.get("replay_ref") is None:
            raise ValueError("retained replay requires an explicit vault and reference")
        project, source_task = task["project_id"], task.get("source_task_id", task["id"])
        metadata = replay_capture.validate_replay_ref(vault_root, project, source_task, task["replay_ref"])
        if metadata["schema"] == replay_capture.INPUT_SCHEMA_V2:
            raise ValueError("v2-execution-unqualified")
        if ".007-prompt.txt" in metadata["config"]["files"] + metadata["config"]["output_files"]:
            raise ValueError("capture path collides with replay prompt")
        if metadata["config"]["external_inputs"] or metadata["versions"]["python"] != sys.version.split()[0]:
            raise ValueError("retained environment is unqualified")
        case = (Path(vault_root).absolute() / task["replay_ref"]["manifest"]).parent
        frozen_prompt = replay_capture._read_private_artifact(case, "inputs/" + metadata["config"]["prompt_file"], replay_capture.MAX_FILE).decode("utf-8")
        contract = json.loads(replay_capture._read_private_artifact(case, "inputs/" + metadata["config"]["acceptance_file"], replay_capture.MAX_FILE))
        if ("prompt" in task and task["prompt"] != frozen_prompt
                or "acceptance" in task and task["acceptance"] != contract["commands"]
                or "acceptance_timeout_s" in task and task["acceptance_timeout_s"] != contract.get("timeout_s", 900)):
            raise ValueError("retained prompt or acceptance differs from frozen bytes")
        task = {**task, "prompt": frozen_prompt, "acceptance": contract["commands"], "acceptance_timeout_s": contract.get("timeout_s", 900)}
        for entry in task.get("hidden_acceptance", []):
            payload = replay_capture._read(Path(entry["source"]).expanduser().resolve(), replay_capture.MAX_FILE)
            if not SHA256.fullmatch(entry.get("sha256", "")) or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise ValueError("hidden acceptance hash mismatch before execution")
        source_repo = None
    else:
        source_repo = Path(config["repos"][task["repo"]]).expanduser().resolve()
    validate_timeout(task.get("acceptance_timeout_s", 900))
    policy = config["arms"][arm]
    workspace = Path(tempfile.mkdtemp(prefix=f"007-{task['id']}-{arm}-r{replicate:02d}-")).resolve()
    try:
        if metadata is None:
            export_snapshot(source_repo, task["base"], workspace)
        else:
            replay_capture.restore_input(vault_root, project, source_task, task["replay_ref"], workspace)
            initialize_snapshot(workspace)
            retained_ref = replay_capture.capture_input(workspace, project, attempt_id, metadata["config"], vault_root=output_dir / "cases")
        base = run(["git", "rev-parse", "--verify", "HEAD"], cwd=workspace, timeout=60).stdout.strip()  # before the agent can commit
        prompt = workspace / ".007-prompt.txt"
        effective_prompt = task["prompt"] + "\n\n" + policy["doctrine"]
        prompt.write_text(effective_prompt)
        if retained_ref is not None:
            prompt_artifact = output_dir / (attempt_id + ".prompt.txt")
            replay_capture.write_bytes_no_replace(prompt_artifact, effective_prompt.encode("utf-8"), "replay effective prompt")
        runner_receipt = output_dir / f"{task['id']}-r{replicate:02d}-{arm}.runner.json"
        if runner_receipt.exists():
            raise RuntimeError(f"runner receipt already exists: {runner_receipt}")
        replacements = {
            "{cwd}": str(workspace), "{prompt_file}": str(prompt),
            "{model}": policy["model"], "{effort}": policy["effort"],
            "{runner_receipt}": str(runner_receipt),
            "{stream_copy}": str(output_dir / f"{attempt_id}.stream.jsonl"),  # native_runner --stream-copy, opt-in
        }
        argv = []
        for part in config["agent_command"]:
            for marker, value in replacements.items():
                part = part.replace(marker, value)
            argv.append(part)
        started = time.monotonic()
        cleanup_failure = None
        agent_output = "unavailable"
        try:
            agent = run(argv, cwd=workspace, timeout=timeout_s, input_text=effective_prompt)
            exit_code, tail = agent.returncode, (agent.stdout + agent.stderr)[-1500:] if retain_text else ""
            agent_output = _output_metadata(agent)
        except subprocess.TimeoutExpired:
            exit_code, tail = -9, "TIMEOUT"
        except CleanupIncomplete as exc:
            cleanup_failure = exc.state
            timed_out = isinstance(exc.original, subprocess.TimeoutExpired)
            exit_code, tail = (-9, "TIMEOUT") if timed_out else (exc.returncode, str(exc) if retain_text else exc.state)
        agent_wall_s = round(time.monotonic() - started, 2)  # r46: the agent alone; wall_s also spans grading
        prompt.unlink(missing_ok=True)
        # An unconfirmed cleanup invalidates the cell and skips acceptance entirely.
        hidden_failure, checks, checks_passed, outcomes = cleanup_failure, [], False, "unavailable"
        if cleanup_failure is None:
            try:
                with tempfile.TemporaryDirectory(prefix=f"007-acceptance-{task['id']}-") as acceptance_tmp:
                    acceptance_workspace = Path(acceptance_tmp) / "workspace"
                    shutil.copytree(workspace, acceptance_workspace, symlinks=True)
                    report = Path(acceptance_tmp) / "accept-report.json"  # r45: beside the copy, never inside it
                    accept_env = {**acceptance_env, "ACCEPT_REPORT": str(report)}
                    with hidden_acceptance(task, acceptance_workspace):
                        checks, checks_passed = acceptance(task, acceptance_workspace, acceptance_sandbox, accept_env,
                                                          retain_diagnostic_text=retain_text)
                    # ponytail: every command shares one report path, so only single-command tasks get outcomes
                    outcomes = acceptance_outcomes(report) if len(checks) == 1 else "unavailable"
            except CleanupIncomplete as exc:
                hidden_failure = cleanup_failure = exc.state
            except subprocess.TimeoutExpired:  # review r40 A1: the paid attempt still gets its cell
                hidden_failure = "acceptance-timeout"
            except (OSError, ValueError, RuntimeError) as exc:
                hidden_failure = f"hidden-acceptance-{type(exc).__name__.lower()}"
        try:
            runner_value = json.loads(runner_receipt.read_text()) if runner_receipt.is_file() else None
        except json.JSONDecodeError:
            runner_value = {}
        identity, identity_failure = (
            validate_served_identity(runner_value, policy, unavailable_map, requested_only=identity_mode == "requested-only")
            if identity_mode else (None, None)
        )
        if cleanup_failure:
            # No Git helper may start after an unconfirmed cleanup: diagnostics are unmeasured, never zero.
            d0 = {"d0_complete": False, **{key: "unmeasured" for key in D0_DIAGNOSTIC_FIELDS}}
        else:
            d0 = diagnostics(task, workspace, source_repo, base)
        d0_failure = None if d0["d0_complete"] else "d0-incomplete"
        agent_valid, _ = grade_cell(exit_code, checks_passed)
        valid = agent_valid and identity_failure is None and hidden_failure is None and d0["d0_complete"]
        accepted = valid and checks_passed
        failure_class = cleanup_failure or (
            "timeout" if exit_code == -9 else "agent-exit" if exit_code != 0
            else hidden_failure or identity_failure or d0_failure or "none"
        )
        usage = identity.get("usage") if identity else None
        record = {
            "schema": "007-framework/replay-cell/v1",
            "task": task["id"],
            "arm": arm,
            "replicate": replicate,
            "requested_provider": policy.get("provider", "unmeasured"),
            "requested_model": policy["model"],
            "requested_effort": policy["effort"],
            "served_provider": identity["provider"] if identity else "unmeasured",
            "served_model": identity["model"] if identity else "unmeasured",
            "served_effort": identity["effort"] if identity else "unmeasured",
            "identity_source": identity["identity_source"] if identity else "unmeasured",
            "identity_source_sha256": identity["source_sha256"] if identity else "unmeasured",
            "runner_receipt_sha256": (
                hashlib.sha256(runner_receipt.read_bytes()).hexdigest()
                if runner_receipt.is_file() else "unmeasured"
            ),
            "usage": usage if usage is not None else "unmeasured",
            "tokens": usage.get("total_tokens", "unmeasured") if isinstance(usage, dict) else "unmeasured",
            "cost_usd": identity["cost_usd"] if identity else "unmeasured",
            "cost_source": identity["cost_source"] if identity else "unmeasured",
            **{key: identity[key] for key in (
                "cost_status", "cost_unavailable_reason", "cost_status_observed",
                "cost_source_observed", "cost_policy_sha256",
            ) if identity and key in identity},
            "agent_exit": exit_code,
            "wall_s": round(time.monotonic() - started, 2),
            "agent_wall_s": agent_wall_s,
            "valid": valid,
            "accepted": accepted,
            "failure_class": failure_class,
            "acceptance": checks,
            "acceptance_outcomes": outcomes,
            "acceptance_execution": {"boundary": "wrapper-configured-unverified" if acceptance_sandbox else "host-unqualified",
                                     "environment": "inherited" if config.get("acceptance_env") is None else "explicit"},
            **d0,
            "agent_tail": tail,
            "agent_output": agent_output,
            "diagnostic_text_retained": retain_text,
        }
        if retained_ref is not None:
            record.update(task_id=attempt_id, project_id=project, source_replay_ref=task["replay_ref"], replay_ref=retained_ref,
                          generator_isolation="unqualified", causal_eligible=False, economic_eligible=False,
                          effective_prompt={"path": prompt_artifact.name, "sha256": hashlib.sha256(effective_prompt.encode("utf-8")).hexdigest()})
            record["candidate_retention"] = "cleanup-unconfirmed" if cleanup_failure else "unavailable"
            if cleanup_failure is None:
                observation = {"observation_kind": "replay-candidate", "task_id": attempt_id,
                    "project_id": project, "replay_ref": retained_ref, "checks": checks,
                    **{key: record[key] for key in ("served_provider", "served_model", "served_effort", "tokens", "wall_s", "cost_usd", "cost_source")},
                    "cost_status": record.get("cost_status", "unmeasured"), "repair_rounds": "unmeasured"}
                observation_path = output_dir / f"{attempt_id}.observation.json"
                try:
                    replay_capture.write_bytes_no_replace(observation_path, replay_capture._json_bytes(observation), "replay observation")
                    result_path = replay_capture.finalize_case(workspace, project, {"task_id": attempt_id, "replay_ref": retained_ref}, observation_path, vault_root=output_dir / "cases")
                    record.update(candidate_retention="declared-outputs-retained", result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest())
                except (OSError, ValueError, RuntimeError):
                    record.update(valid=False, accepted=False, failure_class="candidate-preservation-failed")
        if config.get("retain_candidate_patch"):
            try:
                record["candidate_patch"] = "cleanup-unconfirmed" if cleanup_failure else candidate_patch(
                    workspace, output_dir / f"{attempt_id}.candidate.patch", base)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):  # the paid attempt still gets its cell
                record["candidate_patch"] = "unavailable"
        replay_capture.write_bytes_no_replace(output_dir / f"{task['id']}-r{replicate:02d}-{arm}.json", replay_capture._json_bytes(record), "replay cell")
        return record
    finally:
        shutil.rmtree(workspace)


def recheck_retained_case(task, vault_root, *, acceptance_config=None):
    policy = acceptance_config if acceptance_config is not None else {}
    sandbox, env = acceptance_policy(policy.get("acceptance_sandbox"), policy.get("acceptance_env"))
    project, source_task, ref = task["project_id"], task.get("source_task_id", task["id"]), task["replay_ref"]
    metadata = replay_capture.validate_replay_ref(vault_root, project, source_task, ref)
    if metadata["schema"] == replay_capture.INPUT_SCHEMA_V2:
        return {"replay_ready": False, "oracle_exits": [], "gaps": ["v2-execution-unqualified"]}
    if metadata["config"]["external_inputs"]:
        return {"replay_ready": False, "oracle_exits": [], "gaps": ["external-environment-unqualified"]}
    if metadata["versions"]["python"] != sys.version.split()[0]:
        return {"replay_ready": False, "oracle_exits": [], "gaps": ["runtime-version-mismatch"]}
    case = (Path(vault_root).absolute() / ref["manifest"]).parent
    contract = json.loads(replay_capture._read_private_artifact(case, "inputs/" + metadata["config"]["acceptance_file"], replay_capture.MAX_FILE))
    from framework_cli import validate_acceptance
    validate_acceptance(contract)
    exits, gaps = [], []
    deadline = time.monotonic() + 300
    try:
        for _ in range(2):
            with tempfile.TemporaryDirectory(prefix="007-recheck-") as temporary:
                workspace = Path(temporary).resolve() / "candidate"
                replay_capture.restore_candidate(vault_root, project, source_task, ref, workspace)
                row = []
                exits.append(row)
                with hidden_acceptance(task, workspace):
                    for command in contract["commands"]:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(command, 300)
                        checks, _ = acceptance({"acceptance": [command], "acceptance_timeout_s": min(contract.get("timeout_s", 900), remaining)},
                                               workspace, sandbox, {**env, "ACCEPT_REPORT": str(Path(temporary) / "accept-report.json")})
                        row.append(checks[0]["exit"])
        if exits[0] != exits[1]:
            gaps.append("oracle-unstable")
        if any(code != 0 for row in exits for code in row):
            gaps.append("oracle-nonzero-unattributed")
    except subprocess.TimeoutExpired:
        gaps.append("oracle-timeout")
    except CleanupIncomplete as exc:
        gaps.append(exc.state)
    except (OSError, ValueError, RuntimeError):
        gaps.append("reconstruction-or-oracle-unavailable")
    return {"replay_ready": not gaps and len(exits) == 2, "oracle_exits": exits, "gaps": sorted(gaps)}


def dataset_counts(rows):
    return {"observational": sum(r["state"] == "observational" for r in rows),
            "replay-ready": sum(r["replay_ready"] for r in rows),
            "qualified-comparison": sum(r["state"] == "qualified-comparison" for r in rows),
            "retained": sum(r["retained_case"] for r in rows),
            "holdout_admitted": sum(r["split"] == "holdout" and r["admitted"] for r in rows),
            "admitted": sum(r["admitted"] for r in rows), "excluded": sum(not r["admitted"] for r in rows)}


def admit_dataset(tasks, *, vault_root, recheck=False, acceptance_config=None):
    """Partition retained cases; file claims never qualify a causal comparison."""
    if type(recheck) is not bool or not isinstance(tasks, list) or len(tasks) > 100:
        raise ValueError("admission requires at most 100 tasks and an explicit boolean recheck")
    if recheck and len(tasks) > 3:
        raise ValueError("explicit recheck is limited to three cases per invocation")
    from framework_cli import TASK_CLASSES
    cases, groups = [], {}
    identities, trial_ids = {}, {}
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("dataset tasks must be objects")
        identifier = task.get("id")
        if not isinstance(identifier, str) or not replay_capture.ID.fullmatch(identifier):
            raise ValueError("dataset case id must be a safe bounded identifier")
        project, source = task.get("project_id"), task.get("source_task_id", identifier)
        family, split = task.get("family"), task.get("split", "calibration" if "accepted" in task else "discovery")
        if split not in ("discovery", "calibration", "holdout"):
            raise ValueError("unsupported dataset split")
        exclusions = []
        task_class = task.get("class")
        if not isinstance(task_class, str) or task_class not in TASK_CLASSES:
            task_class = "unclassified"
            exclusions.append("task-class-unavailable")
        if not isinstance(family, str) or not replay_capture.ID.fullmatch(family):
            exclusions.append("family-identity-unavailable")
            family = None
        family_hash = hashlib.sha256(family.encode()).hexdigest() if family else None
        projection = {"state": "observational", "inputs_fingerprint_sha256": None,
                      "input_sha256": None, "result_sha256": None, "gaps": ["retained-input-unavailable"]}
        if not all(isinstance(v, str) and replay_capture.ID.fullmatch(v) for v in (project, source)):
            exclusions.append("source-identity-unavailable")
            project = project if isinstance(project, str) and replay_capture.ID.fullmatch(project) else None
            source = source if isinstance(source, str) and replay_capture.ID.fullmatch(source) else None
        else:
            projection = replay_capture.qualify_case(vault_root, project, source, task.get("replay_ref"))
        retained = projection["state"] == "case-retained"
        if "result_sha256" in task:
            expected = task["result_sha256"]
            if not isinstance(expected, str) or not SHA256.fullmatch(expected):
                raise ValueError("prefrozen candidate identity must be SHA-256")
            if expected != projection["result_sha256"]:
                exclusions.append("candidate-identity-mismatch")
        if projection["state"] in ("invalid", "unavailable"):
            exclusions.append("retained-source-" + projection["state"])
        checked = {"replay_ready": False, "oracle_exits": [], "gaps": projection["gaps"]}
        if split == "holdout":
            exclusions.append("generator-isolation-unqualified")
            if "accepted" in task:
                exclusions.append("historical-solution-known")
        if split == "calibration" and not retained:
            exclusions.append("retained-candidate-unavailable")
        row = {"id": identifier, "project_id": project, "source_task_id": source,
               "class": task_class, "family_sha256": family_hash,
               "split": split, "state": "replay-ready" if checked["replay_ready"] else "observational",
               "retained_case": retained, "input_sha256": projection["input_sha256"],
               "result_sha256": projection["result_sha256"],
               "replay_ready": checked["replay_ready"], "oracle_exits": checked["oracle_exits"],
               "causal_eligible": False, "economic_eligible": False,
               "gaps": checked["gaps"], "exclusions": exclusions}
        keys = [("task", project, source)] if project and source else []
        if family_hash:
            keys.append(("family", project, family_hash))
        if projection["inputs_fingerprint_sha256"]:
            keys.append(("inputs", projection["inputs_fingerprint_sha256"]))
        for key in keys:
            groups.setdefault(key, set()).add(split)
        identities[(project, source)] = identities.get((project, source), 0) + 1
        trial_ids[identifier] = trial_ids.get(identifier, 0) + 1
        cases.append((row, keys, task))
    rows = []
    for row, keys, task in cases:
        if any(len(groups[key]) > 1 for key in keys):
            row["exclusions"].append("cross-split-contamination")
        if identities[(row["project_id"], row["source_task_id"])] > 1 or trial_ids[row["id"]] > 1:
            row["exclusions"].append("duplicate-case-identity")
        row["exclusions"] = sorted(set(row["exclusions"]))
        row["admitted"] = not row["exclusions"]
        if recheck and row["retained_case"] and not any(reason != "generator-isolation-unqualified" for reason in row["exclusions"]):
            try:
                checked = recheck_retained_case(task, vault_root, acceptance_config=acceptance_config)
            except (OSError, ValueError):
                checked = {"replay_ready": False, "oracle_exits": [], "gaps": ["reconstruction-or-oracle-unavailable"]}
            row.update(checked)
            row["state"] = "replay-ready" if row["replay_ready"] else "observational"
        rows.append(row)
    rows.sort(key=lambda r: json.dumps(r, sort_keys=True))
    return {"schema": "007-framework/dataset-admission/v1", "scope": "retention-and-current-host-recheck",
            "counts": dataset_counts(rows), "cases": rows,
            "by_project": {key: dataset_counts([r for r in rows if (r["project_id"] or "_unmeasured") == key])
                           for key in sorted({r["project_id"] or "_unmeasured" for r in rows})},
            "by_class": {key: dataset_counts([r for r in rows if r["class"] == key])
                         for key in sorted({r["class"] for r in rows})},
            "by_split": {key: dataset_counts([r for r in rows if r["split"] == key])
                         for key in ("discovery", "calibration", "holdout")}}


def _followup_projection(value, digest):
    if not isinstance(value, dict) or not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise ValueError("invalid followup source")
    observed = harness_report._instant(value.get("observed_at"))
    if observed is None or observed > datetime.now(timezone.utc):
        raise ValueError("invalid or future followup date")
    projected = {"source_sha256": digest, "observed_at": observed.isoformat()}
    for name in ("repair_rounds", "corrective_lines"):
        if name in value:
            if type(value[name]) is not int or value[name] < 0:
                raise ValueError("invalid corrective count")
            projected[name] = value[name]
    if "escape_7d" in value:
        flag = value["escape_7d"]
        if not (type(flag) is bool or type(flag) is str and flag in ("yes", "no")):
            raise ValueError("invalid declared escape")
        projected["escape_7d"] = flag
    if len(projected) == 2:
        raise ValueError("followup contains no correction or escape")
    return projected


def _hypothesis_projection(value, digest):
    if (not isinstance(value, dict) or set(value) != {"kind", "source_sha256"}
            or not isinstance(digest, str) or not SHA256.fullmatch(digest)
            or value["source_sha256"] != digest or not isinstance(value["kind"], str)
            or value["kind"] not in ("gate", "routing")):
        raise ValueError("invalid proposed hypothesis projection")
    return {"kind": value["kind"], "source_sha256": digest}


def _curation_links(task, row, vault_root, kind):
    refs = task.get(kind + "_refs", [])
    if not isinstance(refs, list) or len(refs) > 8:
        raise ValueError("curation reference budget exceeded")
    if refs:
        if not row["retained_case"]:
            raise ValueError("followup requires the retained task and candidate")
        replay_capture.validate_replay_ref(vault_root, row["project_id"], row["source_task_id"], task["replay_ref"])
        case = Path(task["replay_ref"]["manifest"]).parent
    projected = []
    for ref in refs:
        if (not isinstance(ref, dict) or set(ref) != {"manifest", "sha256"}
                or not isinstance(ref["sha256"], str) or not SHA256.fullmatch(ref["sha256"])):
            raise ValueError("invalid curation reference")
        expected = str(case / f"{kind}-{ref['sha256']}.json")
        if ref["manifest"] != expected or not row["retained_case"]:
            raise ValueError("followup requires the retained task and candidate")
        payload = replay_capture._read_private_artifact(Path(vault_root).absolute(), expected, 8192)
        if hashlib.sha256(payload).hexdigest() != ref["sha256"]:
            raise ValueError("followup source changed")
        value = json.loads(payload)
        if (not isinstance(value, dict)
                or any(value.get(key) != row[field] for key, field in (
                    ("project_id", "project_id"), ("task_id", "source_task_id"),
                    ("input_sha256", "input_sha256"), ("result_sha256", "result_sha256")))):
            raise ValueError("followup task or candidate identity differs")
        if kind == "hypothesis":
            if value.get("status") != "proposed" or any(not isinstance(value.get(key), str)
                    or not value[key].strip() or len(value[key]) > 1024 for key in
                    ("mechanism", "evidence", "counterproof", "positive_control", "experiment")):
                raise ValueError("hypothesis requires proposed status and a bounded falsifiable recipe")
            projected.append(_hypothesis_projection({"kind": value.get("kind"), "source_sha256": ref["sha256"]}, ref["sha256"]))
        else:
            projected.append(_followup_projection(value, ref["sha256"]))
    if len({event["source_sha256"] for event in projected}) != len(projected):
        raise ValueError("duplicate followup source")
    return sorted(projected, key=lambda event: event["source_sha256"])


def _check_curation_link_scope(rows):
    owners = {}
    for row in rows:
        links = row.get("declared_followups", []) + row.get("declared_hypotheses", [])
        identity = (row.get("project_id"), row.get("source_task_id"))
        if links and (any(not isinstance(part, str) or not part for part in identity)
                or sum((other.get("project_id"), other.get("source_task_id")) == identity for other in rows) != 1):
            raise ValueError("ambiguous curation task identity")
        for event in links:
            owner = (row["id"], *identity)
            if owners.setdefault(event["source_sha256"], owner) != owner:
                raise ValueError("curation source has multiple task owners")


def read_curation_checkpoint(checkpoint, *, vault_root):
    """Validate persisted read-only admission, not producer or current-corpus authority."""
    checkpoint = Path(checkpoint).expanduser().absolute()
    if checkpoint.parent.resolve() != checkpoint.parent:
        raise ValueError("symlink in curation checkpoint path")
    info = checkpoint.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
        raise ValueError("curation directory must be owner-only")
    payload = replay_capture._read_private_artifact(checkpoint.parent, checkpoint.name, replay_capture.MAX_MANIFEST)
    value = json.loads(payload)
    vault_hash = hashlib.sha256(str(Path(vault_root).expanduser().absolute()).encode()).hexdigest()
    if (not isinstance(value, dict)
            or set(value) != {"schema", "completed_at", "checkpoint_sha256", "vault_sha256", "verifier_sha256", "admission"}
            or value["schema"] != "007-framework/dataset-curation/v1" or value["vault_sha256"] != vault_hash
            or not isinstance(value["verifier_sha256"], str) or not SHA256.fullmatch(value["verifier_sha256"])
            or not isinstance(value["admission"], dict) or not isinstance(value["admission"].get("cases"), list)
            or len(value["admission"]["cases"]) > 100
            or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not replay_capture.ID.fullmatch(row["id"])
                   for row in value["admission"]["cases"])):
        raise ValueError("invalid or foreign curation checkpoint")
    if not isinstance(value["completed_at"], str) or datetime.fromisoformat(value["completed_at"]).tzinfo is None:
        raise ValueError("invalid curation completion date")
    rows = value["admission"]["cases"]
    for row in rows:
        for field, project in (("declared_followups", _followup_projection), ("declared_hypotheses", _hypothesis_projection)):
            events = row.get(field, [])
            if (not isinstance(events, list) or len(events) > 8
                    or events and (row.get("retained_case") is not True or row.get("admitted") is not True
                        or sum(other["id"] == row["id"] for other in rows) != 1
                        or any(not isinstance(row.get(key), str) or not SHA256.fullmatch(row[key])
                               for key in ("input_sha256", "result_sha256")))
                    or any(not isinstance(event, dict) or event != project(event, event.get("source_sha256")) for event in events)
                    or len({event["source_sha256"] for event in events}) != len(events)):
                raise ValueError("invalid curation links")
    _check_curation_link_scope(rows)
    delta = value["admission"].get("proposal_delta", [])
    bound = [{"case_id": row["id"], **event} for row in rows for event in row.get("declared_hypotheses", [])]
    if (not isinstance(delta, list) or len(delta) > 2 or any(entry not in bound for entry in delta)
            or len({entry["kind"] for entry in delta}) != len(delta)):
        raise ValueError("invalid curation proposal delta")
    if (value["admission"].get("schema") != "007-framework/dataset-admission/v1"
            or any(row.get("state") != "observational" or row.get("replay_ready") is not False
                   or row.get("causal_eligible") is not False or row.get("economic_eligible") is not False
                   or row.get("oracle_exits") != [] or type(row.get("retained_case")) is not bool
                   or type(row.get("admitted")) is not bool or row.get("split") not in ("discovery", "calibration", "holdout") for row in rows)
            or value["admission"].get("counts") != dataset_counts(rows)):
        raise ValueError("checkpoint cannot claim an executed oracle or causal promotion")
    content = {key: value[key] for key in ("vault_sha256", "verifier_sha256", "admission")}
    if hashlib.sha256(replay_capture._json_bytes(content)).hexdigest() != value["checkpoint_sha256"]:
        raise ValueError("curation checkpoint identity differs")
    return value, payload


def curate_dataset(tasks, *, vault_root, checkpoint):
    """Checkpoint read-only admission; unchanged evidence is quiet, never promoted."""
    from framework_cli import write_json_atomic
    checkpoint = Path(checkpoint).expanduser().absolute()
    if checkpoint.parent.resolve() != checkpoint.parent:
        raise ValueError("symlink in curation checkpoint path")
    replay_capture._relative(checkpoint.name)
    replay_capture._private_dir(checkpoint.parent)
    lock = checkpoint.with_name(checkpoint.name + ".lock")
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise ValueError("curation checkpoint already owned; stale locks require review") from exc
    try:
        vault_hash = hashlib.sha256(str(Path(vault_root).expanduser().absolute()).encode()).hexdigest()
        sources = {name: hashlib.sha256(replay_capture._read(Path(__file__).parent / name, replay_capture.MAX_FILE)).hexdigest()
                   for name in ("replay_eval.py", "replay_capture.py", "framework_cli.py")}
        verifier = hashlib.sha256(replay_capture._json_bytes(sources)).hexdigest()
        previous = None
        try:
            previous, previous_bytes = read_curation_checkpoint(checkpoint, vault_root=vault_root)
        except FileNotFoundError:
            previous_bytes = None
        admission = admit_dataset(tasks, vault_root=vault_root, recheck=False)
        rows = admission["cases"]
        for row in rows:
            matched = [task for task in tasks if task["id"] == row["id"]]
            if any(task.get("followup_refs") or task.get("hypothesis_refs") for task in matched) and (len(matched) != 1 or not row["admitted"]):
                raise ValueError("followup case identity or split is ambiguous")
            task = matched[0]
            for kind, field in (("followup", "declared_followups"), ("hypothesis", "declared_hypotheses")):
                events = _curation_links(task, row, vault_root, kind)
                if events:
                    row[field] = events
        _check_curation_link_scope(rows)
        identifiers = {row["id"] for row in rows}
        prior_rows = previous["admission"]["cases"] if previous else []
        gaps = []
        if any(reason.startswith("retained-source-") for row in rows for reason in row["exclusions"]):
            gaps.append("source-acquisition-incomplete")
        if any(row["input_sha256"] and not row["retained_case"] for row in rows):
            gaps.append("candidate-publication-incomplete")
        if any(row["id"] not in identifiers
               or row.get("input_sha256") and not any(r["input_sha256"] for r in rows if r["id"] == row["id"])
               or row.get("retained_case") and not any(r["retained_case"] for r in rows if r["id"] == row["id"])
               for row in prior_rows):
            gaps.append("source-history-shrank")
        if any(row["id"] in identifiers and not any((r["project_id"], r["source_task_id"]) == (row.get("project_id"), row.get("source_task_id"))
                   for r in rows if r["id"] == row["id"]) for row in prior_rows):
            gaps.append("source-identity-changed")
        if any(not any(r["id"] == row["id"] and all(event in r.get("declared_followups", [])
                    for event in row.get("declared_followups", [])) for r in rows) for row in prior_rows):
            gaps.append("followup-history-shrank")
        if any(not any(r["id"] == row["id"] and all(event in r.get("declared_hypotheses", [])
                    for event in row.get("declared_hypotheses", [])) for r in rows) for row in prior_rows):
            gaps.append("hypothesis-history-shrank")
        if gaps:
            return {"complete": False, "changed": False, "delta_ids": [], "gaps": gaps, "admission": admission,
                    "checkpoint_sha256": previous["checkpoint_sha256"] if previous else None}
        content = {"vault_sha256": vault_hash, "verifier_sha256": verifier, "admission": admission}
        prior_content = {key: previous[key] for key in content} if previous else None
        if prior_content:
            prior_content = {**prior_content, "admission": {key: value for key, value in prior_content["admission"].items() if key != "proposal_delta"}}
        if previous and content == prior_content:
            return {**previous, "complete": True, "changed": False, "delta_ids": [], "gaps": []}
        proposals = [{"case_id": row["id"], **event} for row in rows for event in row.get("declared_hypotheses", [])
                     if not any(prior["id"] == row["id"] and event in prior.get("declared_hypotheses", []) for prior in prior_rows)]
        if any(sum(entry["kind"] == kind for entry in proposals) > 1 for kind in ("gate", "routing")):
            raise ValueError("at most one new routing and gate hypothesis per cycle")
        if proposals or any(row.get("declared_hypotheses") for row in rows):
            admission["proposal_delta"] = sorted(proposals, key=lambda entry: (entry["kind"], entry["source_sha256"]))
        digest = hashlib.sha256(replay_capture._json_bytes(content)).hexdigest()
        delta = sorted(identifier for identifier in identifiers
                       if [r for r in rows if r["id"] == identifier] != [r for r in prior_rows if r["id"] == identifier])
        value = {"schema": "007-framework/dataset-curation/v1", "completed_at": datetime.now(timezone.utc).isoformat(),
                 "checkpoint_sha256": digest, **content}
        if previous_bytes is None:
            replay_capture.write_bytes_no_replace(checkpoint, replay_capture._json_bytes(value), "curation checkpoint")
        else:
            if replay_capture._read_private_artifact(checkpoint.parent, checkpoint.name, replay_capture.MAX_MANIFEST) != previous_bytes:
                raise ValueError("curation checkpoint changed during collection")
            # shortcut: atomic replace only; add fsync before promising power-loss durability.
            write_json_atomic(checkpoint, value)
        return {**value, "complete": True, "changed": True, "delta_ids": delta, "gaps": []}
    finally:
        lock.rmdir()


def main():
    parser = argparse.ArgumentParser(description="Run frozen OLD×NEW coding replays")
    parser.add_argument("--set", required=True)
    parser.add_argument("command", choices=("list", "run", "admit", "curate"))
    parser.add_argument("--vault", type=Path, help="private retained-input vault (admit/curate only)")
    parser.add_argument("--checkpoint", type=Path, help="private completed curation checkpoint (curate only)")
    parser.add_argument("--recheck", action="store_true", help="explicitly run the frozen acceptance commands on restored candidates")
    parser.add_argument("--tasks", default="all", help="all or comma-separated task ids")
    parser.add_argument("--arms", default="OLD,NEW")
    parser.add_argument("--out", default="replay-results")
    parser.add_argument("--timeout-min", type=int, default=30)
    parser.add_argument("--replicates", type=int)
    args = parser.parse_args()
    replay_set = Path(args.set).expanduser().resolve()
    if args.recheck and args.command != "admit":
        parser.error("--recheck is only valid for admit")
    if args.vault is not None and args.command not in ("admit", "curate"):
        parser.error("--vault is only valid for admit/curate")
    if (args.checkpoint is not None) != (args.command == "curate"):
        parser.error("curate requires --checkpoint; other commands cannot use it")
    if args.command in ("admit", "curate"):
        run_flags = ("--tasks", "--arms", "--out", "--timeout-min", "--replicates")
        if any(arg == flag or arg.startswith(flag + "=") for arg in sys.argv[1:] for flag in run_flags):
            parser.error("run options do not apply to admit/curate; recheck has its own bounded profile")
        config = json.loads(replay_capture._read(replay_set, replay_capture.MAX_MANIFEST))
        vault = (args.vault or replay_capture.default_vault()).expanduser()
        if args.command == "curate":
            try:
                result = curate_dataset(config["tasks"], vault_root=vault, checkpoint=args.checkpoint)
            except (OSError, ValueError):
                parser.error("curation unavailable; checkpoint not confirmed")
            if result["changed"] or not result["complete"]:
                print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["complete"] else 2
        print(json.dumps(admit_dataset(config["tasks"], vault_root=vault, recheck=args.recheck, acceptance_config=config), indent=2, sort_keys=True))
        return 0
    config = json.loads(replay_set.read_text())
    cost_unavailable_map(config)
    tasks = config["tasks"]
    for task in tasks:
        validate_task_id(task["id"])
    if args.command == "list":
        for task in tasks:
            print(f"{task['id']:24s} {task.get('class', 'unclassified'):12s} {task.get('subject', '')}")
        return 0

    try:
        timeout_s = validate_timeout(args.timeout_min * 60)
    except ValueError as error:
        parser.error(str(error))

    wanted = None if args.tasks == "all" else set(args.tasks.split(","))
    tasks = [task for task in tasks if wanted is None or task["id"] in wanted]
    arms = args.arms.split(",")
    unknown = set(arms) - set(config["arms"])
    if unknown:
        parser.error(f"unknown arms: {sorted(unknown)}")
    replicates = experiment_replicates(config, args.replicates)
    validate_cell_artifacts(tasks, arms, replicates)
    schedule = experiment_schedule(config, arms, replicates)
    output_dir = Path(args.out).expanduser().resolve()
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    validate_cell_artifacts(tasks, arms, replicates, directory=output_dir)
    rows = []
    for task in tasks:
        for replicate in range(1, replicates + 1):
            for arm in schedule[(task["id"], replicate)]:
                record = execute_cell(config, task, arm, replicate, output_dir, timeout_s)
                record["execution_index"] = len(rows) + 1
                rows.append(record)
                if not record["valid"]:
                    write_summary(output_dir, replay_set, config, replicates, rows)
                    print(f"invalid cell: {task['id']} r{replicate:02d} {arm}; stopped", file=sys.stderr)
                    return 2
    write_summary(output_dir, replay_set, config, replicates, rows)
    print(f"wrote {len(rows)} cells to {output_dir}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
