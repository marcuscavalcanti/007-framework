#!/usr/bin/env python3
"""Local project registration and dashboard entrypoint for 007 Framework."""

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path


PROJECT_SCHEMA = "007-framework/project/v1"
REGISTRY_SCHEMA = "007-framework/registry/v1"
RECEIPT_SCHEMA = "007-framework/receipt/v1"
TASK_START_SCHEMA = "007-framework/task-start/v1"
AUTHORITY_SCHEMA = "007-framework/authority/v1"
TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COST_SOURCES = {
    "provider-reported", "rate-card-estimate", "subscription-allocated", "local-compute",
}
CUSTOM_COST_SOURCE = re.compile(r"^custom:[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def default_registry_path():
    return Path.home() / ".007-framework" / "projects.json"


def git_root(path):
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path(path).expanduser(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise ValueError(f"not a Git repository: {Path(path).expanduser()}")
    return Path(result.stdout.strip()).resolve()


def exclude_local_state(root):
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", "info/exclude"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise ValueError("cannot locate Git exclude file")
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = root / path
    marker = "/.007/"
    current = path.read_text() if path.exists() else ""
    if marker not in current.splitlines():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as output:
            if current and not current.endswith("\n"):
                output.write("\n")
            output.write(marker + "\n")


def read_json(path):
    return json.loads(path.read_text())


def write_json_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w") as output:
            json.dump(value, output, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def write_json_no_replace(path, value, label="receipt"):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w") as output:
            json.dump(value, output, indent=2, sort_keys=True)
            output.write("\n")
        try:
            os.link(name, path)
        except FileExistsError as exc:
            raise ValueError(f"{label} already exists: {path.name}") from exc
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def validate_marker(value):
    if not isinstance(value, dict) or value.get("schema") != PROJECT_SCHEMA:
        raise ValueError("invalid .007/project.json schema")
    if not all(isinstance(value.get(key), str) and value[key] for key in ("project_id", "name", "receipt_dir")):
        raise ValueError("invalid .007/project.json fields")
    receipt_dir = Path(value["receipt_dir"])
    if receipt_dir.is_absolute() or ".." in receipt_dir.parts:
        raise ValueError("receipt_dir must stay inside .007")
    return value


def load_registry(path):
    if not path.exists():
        return {"schema": REGISTRY_SCHEMA, "projects": []}
    value = read_json(path)
    if not isinstance(value, dict) or value.get("schema") != REGISTRY_SCHEMA or not isinstance(value.get("projects"), list):
        raise ValueError(f"invalid registry: {path}")
    required = ("project_id", "name", "path", "registered_at")
    if any(
        not isinstance(item, dict)
        or not all(isinstance(item.get(key), str) and item[key] for key in required)
        for item in value["projects"]
    ):
        raise ValueError(f"invalid registry entry: {path}")
    return value


def validate_task_id(task_id):
    if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
        raise ValueError("task_id must use only letters, numbers, dot, dash, or underscore")
    return task_id


def validate_authority(value):
    if not isinstance(value, dict) or value.get("schema") != AUTHORITY_SCHEMA:
        raise ValueError(f"authority schema must be {AUTHORITY_SCHEMA}")
    for key in ("allow", "deny"):
        actions = value.get(key)
        if not isinstance(actions, list) or any(not isinstance(action, str) or not TASK_ID.fullmatch(action) for action in actions):
            raise ValueError(f"authority {key} must be a list of action names")
        if len(actions) != len(set(actions)):
            raise ValueError(f"authority {key} contains duplicate actions")
    if set(value["allow"]) & set(value["deny"]):
        raise ValueError("authority actions cannot be both allowed and denied")
    return value


def read_authority(path):
    payload = Path(path).expanduser().read_bytes()
    authority = validate_authority(json.loads(payload))
    return authority, hashlib.sha256(payload).hexdigest()


def validate_task_start(value):
    if not isinstance(value, dict) or value.get("schema") != TASK_START_SCHEMA:
        raise ValueError(f"task start schema must be {TASK_START_SCHEMA}")
    validate_task_id(value.get("task_id"))
    if not isinstance(value.get("started_at"), str) or not value["started_at"]:
        raise ValueError("started_at must be a timestamp string")
    authority = value.get("authority")
    authority_hash = value.get("authority_sha256")
    if authority is not None or authority_hash is not None:
        validate_authority(authority)
        if not isinstance(authority_hash, str) or not SHA256.fullmatch(authority_hash):
            raise ValueError("authority_sha256 must be a lowercase SHA-256")
    return value


def init_project(repo, registry_path, now=None):
    root = git_root(repo)
    exclude_local_state(root)
    marker_path = root / ".007" / "project.json"
    if marker_path.exists():
        marker = validate_marker(read_json(marker_path))
    else:
        marker = {
            "schema": PROJECT_SCHEMA,
            "project_id": str(uuid.uuid4()),
            "name": root.name,
            "receipt_dir": "receipts",
        }
        write_json_atomic(marker_path, marker)
    (marker_path.parent / marker["receipt_dir"]).mkdir(parents=True, exist_ok=True)

    registry_path = Path(registry_path).expanduser().resolve()
    registry = load_registry(registry_path)
    existing = next(
        (item for item in registry["projects"] if item.get("project_id") == marker["project_id"]),
        None,
    )
    registered_at = (existing or {}).get("registered_at")
    if not registered_at:
        instant = now or datetime.now(timezone.utc)
        registered_at = instant.isoformat().replace("+00:00", "Z")
    entry = {
        "project_id": marker["project_id"],
        "name": marker["name"],
        "path": str(root),
        "registered_at": registered_at,
    }
    registry["projects"] = [
        item for item in registry["projects"]
        if item.get("project_id") != marker["project_id"] and item.get("path") != str(root)
    ] + [entry]
    registry["projects"].sort(key=lambda item: (item.get("name", "").lower(), item.get("path", "")))
    write_json_atomic(registry_path, registry)
    return entry


def unregister_project(project, registry_path):
    registry_path = Path(registry_path).expanduser().resolve()
    registry = load_registry(registry_path)
    target_path = str(Path(project).expanduser().resolve())
    removed = [
        item for item in registry["projects"]
        if item["project_id"] == project or item["path"] == target_path
    ]
    if not removed:
        raise ValueError(f"project is not registered: {project}")
    registry["projects"] = [item for item in registry["projects"] if item not in removed]
    write_json_atomic(registry_path, registry)
    return removed[0]


def begin_task(repo, task_id=None, now=None, authority_file=None):
    root = git_root(repo)
    marker_path = root / ".007" / "project.json"
    if not marker_path.exists():
        raise ValueError("project is not initialized; run 007 init first")
    validate_marker(read_json(marker_path))
    instant = now or datetime.now(timezone.utc)
    if task_id is None:
        stamp = instant.strftime("%Y%m%dT%H%M%SZ")
        task_id = f"task-{stamp}-{uuid.uuid4().hex[:8]}"
    validate_task_id(task_id)
    task = {
        "schema": TASK_START_SCHEMA,
        "task_id": task_id,
        "started_at": instant.isoformat().replace("+00:00", "Z"),
    }
    if authority_file:
        task["authority"], task["authority_sha256"] = read_authority(authority_file)
    validate_task_start(task)
    destination = marker_path.parent / "tasks" / f"{task_id}.task.json"
    write_json_no_replace(destination, task, "task start")
    return task


def validate_receipt(value):
    if not isinstance(value, dict) or value.get("schema") != RECEIPT_SCHEMA:
        raise ValueError(f"receipt schema must be {RECEIPT_SCHEMA}")
    if "authority_summary" in value:
        raise ValueError("authority_summary is computed by 007 record")
    validate_task_id(value.get("task_id"))
    if value.get("status") not in ("accepted", "blocked", "no-op"):
        raise ValueError("status must be accepted, blocked, or no-op")
    cost = value.get("cost_usd")
    if (
        isinstance(cost, bool)
        or not isinstance(cost, (int, float))
        or not math.isfinite(cost)
        or cost < 0
    ):
        raise ValueError("cost_usd must be a non-negative measured number")
    source = value.get("cost_source")
    if not isinstance(source, str) or (
        source not in COST_SOURCES and not CUSTOM_COST_SOURCE.fullmatch(source)
    ):
        raise ValueError("cost_source must be documented or use custom:<name>")
    if value.get("cost_status") not in ("final", "provisional"):
        raise ValueError("cost_status must be final or provisional")
    required_strings = (
        "proof_required", "proof_reached", "first_pass", "corrective_lines",
        "escape_7d", "requested_provider", "requested_model", "requested_effort",
        "served_provider", "served_model", "served_effort", "uncertainty",
    )
    missing = [key for key in required_strings if not isinstance(value.get(key), str) or not value[key]]
    if missing:
        raise ValueError(f"missing receipt field(s): {', '.join(missing)}")
    if not isinstance(value.get("checks"), list) or not isinstance(value.get("delta"), dict):
        raise ValueError("checks must be a list and delta must be an object")
    repairs = value.get("repair_rounds")
    if repairs != "unmeasured" and (isinstance(repairs, bool) or not isinstance(repairs, int) or repairs < 0):
        raise ValueError("repair_rounds must be a non-negative integer or unmeasured")
    for key in ("tokens", "wall_s"):
        measured = value.get(key)
        if measured != "unmeasured" and (
            isinstance(measured, bool) or not isinstance(measured, (int, float)) or measured < 0
        ):
            raise ValueError(f"{key} must be a non-negative number or unmeasured")
    authority_hash = value.get("authority_sha256")
    events = value.get("boundary_events")
    if authority_hash is not None or events is not None:
        if not isinstance(authority_hash, str) or not SHA256.fullmatch(authority_hash):
            raise ValueError("authority_sha256 must be a lowercase SHA-256")
        if not isinstance(events, list):
            raise ValueError("boundary_events must be a list")
        for event in events:
            if (
                not isinstance(event, dict)
                or not isinstance(event.get("action"), str)
                or not TASK_ID.fullmatch(event["action"])
                or event.get("outcome") not in ("executed", "blocked")
            ):
                raise ValueError("boundary event requires action and executed|blocked outcome")
    return value


def bind_authority(receipt, task):
    authority = task.get("authority") if task else None
    supplied = receipt.get("authority_sha256") is not None or receipt.get("boundary_events") is not None
    if authority is None:
        if supplied:
            raise ValueError("receipt claims authority but task start is not authority-bound")
        return receipt
    if receipt.get("authority_sha256") != task.get("authority_sha256"):
        raise ValueError("receipt authority_sha256 does not match task start")
    events = receipt.get("boundary_events")
    if not isinstance(events, list):
        raise ValueError("authority-bound task requires boundary_events")
    allowed, denied = set(authority["allow"]), set(authority["deny"])
    summary = {
        "bound": True, "events": len(events), "allowed_executions": 0,
        "protected_blocks": 0, "friction_blocks": 0, "unclassified_blocks": 0,
    }
    for event in events:
        action, outcome = event["action"], event["outcome"]
        if outcome == "executed":
            if action not in allowed:
                raise ValueError(f"executed action outside bound authority: {action}")
            summary["allowed_executions"] += 1
        elif action in allowed:
            summary["friction_blocks"] += 1
        elif action in denied:
            summary["protected_blocks"] += 1
        else:
            summary["unclassified_blocks"] += 1
    receipt["authority_summary"] = summary
    return receipt


def record_receipt(repo, source, now=None):
    root = git_root(repo)
    marker_path = root / ".007" / "project.json"
    if not marker_path.exists():
        raise ValueError("project is not initialized; run 007 init first")
    marker = validate_marker(read_json(marker_path))
    if source == "-":
        value = json.load(sys.stdin)
    else:
        value = read_json(Path(source).expanduser())
    receipt = validate_receipt(value)
    task_path = marker_path.parent / "tasks" / f"{receipt['task_id']}.task.json"
    if not task_path.exists():
        raise ValueError("receipt requires a matching task start")
    task = validate_task_start(read_json(task_path))
    if task["task_id"] != receipt["task_id"]:
        raise ValueError("task start task_id does not match receipt")
    receipt = bind_authority(receipt, task)
    if "completed_at" not in receipt:
        instant = now or datetime.now(timezone.utc)
        receipt["completed_at"] = instant.isoformat().replace("+00:00", "Z")
    elif not isinstance(receipt["completed_at"], str) or not receipt["completed_at"]:
        raise ValueError("completed_at must be a timestamp string")
    destination = marker_path.parent / marker["receipt_dir"] / f"{receipt['task_id']}.receipt.json"
    write_json_no_replace(destination, receipt)
    return destination


def run_task(repo, task_id, receipt, command, authority_file=None):
    root = git_root(repo)
    command = command[1:] if command[:1] == ["--"] else command
    if not command:
        raise ValueError("run requires a command after --")
    receipt_path = Path(receipt).expanduser()
    if not receipt_path.is_absolute():
        receipt_path = root / receipt_path
    receipt_path = receipt_path.resolve()
    if receipt_path.exists():
        raise ValueError(f"terminal receipt already exists: {receipt_path}")

    task = begin_task(root, task_id, authority_file=authority_file)
    environment = {
        **os.environ,
        "FRAMEWORK_007_TASK_ID": task["task_id"],
        "FRAMEWORK_007_RECEIPT_PATH": str(receipt_path),
        "FRAMEWORK_007_REPO": str(root),
    }
    if task.get("authority_sha256"):
        environment["FRAMEWORK_007_AUTHORITY_SHA256"] = task["authority_sha256"]
    completed = subprocess.run(command, cwd=root, env=environment)
    if completed.returncode:
        return completed.returncode, None
    if not receipt_path.is_file():
        raise ValueError(f"command did not produce terminal receipt: {receipt_path}")
    receipt_value = validate_receipt(read_json(receipt_path))
    if receipt_value["task_id"] != task["task_id"]:
        raise ValueError("terminal receipt task_id does not match the observed task")
    return 0, record_receipt(root, receipt_path)


def parser():
    result = argparse.ArgumentParser(description="007 Framework local tooling")
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="register a Git project for 007 telemetry")
    init.add_argument("--repo", default=".")
    init.add_argument("--registry", type=Path, default=default_registry_path())
    begin = commands.add_parser("begin", help="observe the start of one task")
    begin.add_argument("--repo", default=".")
    begin.add_argument("--task-id")
    begin.add_argument("--authority-file", type=Path)
    record = commands.add_parser("record", help="validate and persist one terminal task receipt")
    record.add_argument("--repo", default=".")
    record.add_argument("--file", required=True, help="receipt JSON path, or - for stdin")
    run = commands.add_parser("run", help="observe a command and require its terminal receipt")
    run.add_argument("--repo", default=".")
    run.add_argument("--task-id")
    run.add_argument("--receipt", required=True)
    run.add_argument("--authority-file", type=Path)
    run.add_argument("argv", nargs=argparse.REMAINDER, help="command after --")
    unregister = commands.add_parser("unregister", help="remove a stale project from the local registry")
    unregister.add_argument("--project", required=True, help="registered project path or project ID")
    unregister.add_argument("--registry", type=Path, default=default_registry_path())
    dashboard = commands.add_parser("dashboard", help="start the local multi-project dashboard")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=7007)
    dashboard.add_argument("--registry", type=Path, default=default_registry_path())
    dashboard.add_argument("--no-open", action="store_true")
    return result


def run_dashboard(host, port, registry, open_browser=True):
    import dashboard

    static_dir = Path(__file__).resolve().parents[1] / "dashboard"
    server = dashboard.create_server(host, port, registry, static_dir)
    url = f"http://{host}:{server.server_port}"
    print(f"007 dashboard: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            entry = init_project(args.repo, args.registry)
            print(f"registered {entry['name']} ({entry['path']})")
            print(f"receipts: {Path(entry['path']) / '.007' / 'receipts'}")
            return 0
        if args.command == "begin":
            task = begin_task(args.repo, args.task_id, authority_file=args.authority_file)
            print(f"started: {task['task_id']}")
            return 0
        if args.command == "record":
            destination = record_receipt(args.repo, args.file)
            print(f"recorded: {destination}")
            return 0
        if args.command == "run":
            status, destination = run_task(args.repo, args.task_id, args.receipt, args.argv, args.authority_file)
            if destination:
                print(f"recorded: {destination}")
            return status
        if args.command == "unregister":
            entry = unregister_project(args.project, args.registry)
            print(f"unregistered: {entry['name']} ({entry['path']})")
            return 0
        if args.command == "dashboard":
            return run_dashboard(args.host, args.port, args.registry, not args.no_open)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
