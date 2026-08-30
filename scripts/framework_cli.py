#!/usr/bin/env python3
"""Local project registration and dashboard entrypoint for 007 Framework."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path


PROJECT_SCHEMA = "007-framework/project/v1"
REGISTRY_SCHEMA = "007-framework/registry/v1"


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


def init_project(repo, registry_path, now=None):
    root = git_root(repo)
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


def parser():
    result = argparse.ArgumentParser(description="007 Framework local tooling")
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="register a Git project for 007 telemetry")
    init.add_argument("--repo", default=".")
    init.add_argument("--registry", type=Path, default=default_registry_path())
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
        if args.command == "dashboard":
            return run_dashboard(args.host, args.port, args.registry, not args.no_open)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
