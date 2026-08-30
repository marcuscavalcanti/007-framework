#!/usr/bin/env python3
"""Build and serve safe multi-project snapshots for 007 Framework."""

import json
import math
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import framework_cli
import harness_report
import touch_rate


MISSING = {"", "unmeasured", "pending", "N/D", "unknown", None}
VERSION = "1.1.0"
RAW_METRICS = (
    "tasks", "accepted", "blocked", "no_op",
    "first_pass_yes", "first_pass_known",
    "repair_rounds_sum", "repair_rounds_known_tasks",
    "tokens_known_sum", "tokens_known_tasks",
    "accepted_tokens_known_sum", "accepted_tokens_known_tasks",
    "wall_s_known_sum", "wall_s_known_tasks",
    "accepted_wall_s_known_sum", "accepted_wall_s_known_tasks",
    "cost_usd_known_sum", "cost_usd_known_tasks",
    "accepted_cost_usd_known_sum", "accepted_cost_usd_known_tasks",
    "cost_final_tasks", "cost_provisional_tasks",
    "escape_7d_yes", "escape_7d_known",
    "telemetry_known", "telemetry_possible",
    "delta_files", "delta_added", "delta_deleted",
)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_known_label(value):
    return isinstance(value, str) and value not in MISSING


def has_accounted_cost(receipt):
    return (
        is_number(receipt.get("cost_usd"))
        and is_known_label(receipt.get("cost_source"))
        and receipt.get("cost_status") in ("final", "provisional")
    )


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def safe_task(receipt):
    task = {
        key: receipt.get(key)
        for key in (
            "task_id", "status", "proof_required", "proof_reached",
            "first_pass", "repair_rounds", "corrective_lines", "escape_7d",
            "requested_provider", "requested_model", "requested_effort",
            "served_provider", "served_model", "served_effort",
            "provider", "model", "effort", "tokens", "wall_s",
            "cost_usd", "cost_source", "cost_status",
            "completed_at", "uncertainty",
        )
        if key in receipt
    }
    delta = receipt.get("delta")
    if isinstance(delta, dict):
        task["delta"] = {
            key: delta[key]
            for key in ("files", "added", "deleted", "dependencies")
            if is_number(delta.get(key))
        }
    return task


def route_for(receipt):
    served_provider = receipt.get("served_provider") or receipt.get("provider")
    served_model = receipt.get("served_model") or receipt.get("model")
    if is_known_label(served_model):
        provider = served_provider if is_known_label(served_provider) else "provider-unmeasured"
        return provider, served_model, "served"
    requested_provider = receipt.get("requested_provider")
    requested_model = receipt.get("requested_model")
    if is_known_label(requested_model):
        provider = requested_provider if is_known_label(requested_provider) else "provider-unmeasured"
        return provider, requested_model, "requested-unverified"
    return "provider-unmeasured", "model-unmeasured", "unmeasured"


def route_metrics(receipts):
    routes = {}
    for receipt in receipts:
        provider, model, binding = route_for(receipt)
        key = f"{provider}/{model}"
        row = routes.setdefault(key, {
            "key": key, "provider": provider, "model": model, "binding": binding,
            "tasks": 0, "accepted": 0,
            "cost_usd_known_sum": 0, "cost_usd_known_tasks": 0,
        })
        if row["binding"] != binding:
            row["binding"] = "mixed"
        row["tasks"] += 1
        row["accepted"] += int(receipt.get("status") == "accepted")
        if has_accounted_cost(receipt):
            row["cost_usd_known_sum"] += receipt["cost_usd"]
            row["cost_usd_known_tasks"] += 1
    for row in routes.values():
        row["cost_usd_known_sum"] = round(row["cost_usd_known_sum"], 6)
    return [routes[key] for key in sorted(routes)]


def metrics_from_receipts(receipts):
    statuses = Counter(str(item.get("status", "unknown")) for item in receipts)
    first_pass = Counter(str(item.get("first_pass", "unmeasured")) for item in receipts)
    repairs = [item.get("repair_rounds") for item in receipts if is_number(item.get("repair_rounds"))]
    tokens = [item.get("tokens") for item in receipts if is_number(item.get("tokens"))]
    wall = [item.get("wall_s") for item in receipts if is_number(item.get("wall_s"))]
    costs = [item.get("cost_usd") for item in receipts if has_accounted_cost(item)]
    accepted = [item for item in receipts if item.get("status") == "accepted"]
    accepted_tokens = [item.get("tokens") for item in accepted if is_number(item.get("tokens"))]
    accepted_wall = [item.get("wall_s") for item in accepted if is_number(item.get("wall_s"))]
    accepted_cost = [
        item.get("cost_usd") for item in accepted if has_accounted_cost(item)
    ]

    escape_yes = 0
    escape_known = 0
    telemetry_known = 0
    delta_totals = {"files": 0, "added": 0, "deleted": 0}
    for item in receipts:
        escape = item.get("escape_7d")
        if escape in (True, "yes"):
            escape_yes += 1
            escape_known += 1
        elif escape in (False, "no"):
            escape_known += 1
        for served, legacy in (("served_model", "model"), ("served_effort", "effort")):
            if is_known_label(item.get(served) or item.get(legacy)):
                telemetry_known += 1
        telemetry_known += int(is_number(item.get("tokens")))
        telemetry_known += int(is_number(item.get("wall_s")))
        delta = item.get("delta")
        if isinstance(delta, dict):
            for key in delta_totals:
                if is_number(delta.get(key)):
                    delta_totals[key] += delta[key]

    tasks = len(receipts)
    first_pass_known = first_pass["yes"] + first_pass["no"]
    result = {
        "tasks": tasks,
        "accepted": statuses["accepted"],
        "blocked": statuses["blocked"],
        "no_op": statuses["no-op"],
        "first_pass_yes": first_pass["yes"],
        "first_pass_known": first_pass_known,
        "repair_rounds_sum": sum(repairs),
        "repair_rounds_known_tasks": len(repairs),
        "tokens_known_sum": sum(tokens),
        "tokens_known_tasks": len(tokens),
        "accepted_tokens_known_sum": sum(accepted_tokens),
        "accepted_tokens_known_tasks": len(accepted_tokens),
        "wall_s_known_sum": sum(wall),
        "wall_s_known_tasks": len(wall),
        "accepted_wall_s_known_sum": sum(accepted_wall),
        "accepted_wall_s_known_tasks": len(accepted_wall),
        "cost_usd_known_sum": round(sum(costs), 6),
        "cost_usd_known_tasks": len(costs),
        "accepted_cost_usd_known_sum": round(sum(accepted_cost), 6),
        "accepted_cost_usd_known_tasks": len(accepted_cost),
        "cost_final_tasks": sum(has_accounted_cost(item) and item.get("cost_status") == "final" for item in receipts),
        "cost_provisional_tasks": sum(has_accounted_cost(item) and item.get("cost_status") == "provisional" for item in receipts),
        "escape_7d_yes": escape_yes,
        "escape_7d_known": escape_known,
        "telemetry_known": telemetry_known,
        "telemetry_possible": tasks * 4,
        "delta_files": delta_totals["files"],
        "delta_added": delta_totals["added"],
        "delta_deleted": delta_totals["deleted"],
        "routes": route_metrics(receipts),
    }
    result.update({
        "first_pass_rate": ratio(result["first_pass_yes"], first_pass_known),
        "first_pass_unknown_tasks": tasks - first_pass_known,
        "repair_rounds_mean": ratio(result["repair_rounds_sum"], len(repairs)),
        "tokens_missing_tasks": tasks - len(tokens),
        "tokens_per_accepted": (
            ratio(sum(accepted_tokens), len(accepted))
            if accepted and len(accepted_tokens) == len(accepted) else None
        ),
        "wall_s_per_accepted": (
            ratio(sum(accepted_wall), len(accepted))
            if accepted and len(accepted_wall) == len(accepted) else None
        ),
        "cost_usd_per_accepted": (
            ratio(sum(accepted_cost), len(accepted))
            if accepted and len(accepted_cost) == len(accepted) else None
        ),
        "cost_coverage": ratio(len(costs), tasks),
        "cost_accounting_status": (
            None if not costs
            else "provisional" if any(item.get("cost_status") == "provisional" for item in receipts if has_accounted_cost(item))
            else "final"
        ),
        "escape_7d_rate": ratio(escape_yes, escape_known),
        "escape_7d_pending_tasks": tasks - escape_known,
        "telemetry_completeness": ratio(telemetry_known, tasks * 4),
    })
    return result


def unknown_touch(days, reason):
    return {
        "window_days": days,
        "agent_commits": 0,
        "human_commits": 0,
        "agent_lines_added": 0,
        "surviving_lines": 0,
        "rate": None,
        "reason": reason,
    }


def evidence_state(metrics, touch, invalid_receipts=0):
    reasons = []
    if invalid_receipts:
        return {"status": "needs-attention", "reasons": [f"{invalid_receipts} invalid receipt(s)"]}
    if metrics["accepted"] < 5:
        reasons.append("fewer than 5 accepted tasks")
    required = {
        "first-pass rate": metrics.get("first_pass_rate"),
        "mean repair rounds": metrics.get("repair_rounds_mean"),
        "7-day escape rate": metrics.get("escape_7d_rate"),
        "30-day touch proxy": touch.get("30", {}).get("rate"),
        "telemetry completeness": metrics.get("telemetry_completeness"),
        "cost coverage": metrics.get("cost_coverage"),
    }
    reasons.extend(f"{name} is N/D" for name, value in required.items() if value is None)
    if reasons:
        return {"status": "collecting", "reasons": reasons}
    failures = []
    if required["first-pass rate"] < 0.70:
        failures.append("first-pass rate below 70%")
    if required["mean repair rounds"] > 0.5:
        failures.append("mean repair rounds above 0.5")
    if required["7-day escape rate"] > 0.05:
        failures.append("7-day escape rate above 5%")
    if required["30-day touch proxy"] > 15:
        failures.append("30-day touch proxy above 15%")
    if required["telemetry completeness"] < 0.80:
        failures.append("telemetry completeness below 80%")
    if required["cost coverage"] < 1:
        failures.append("cost coverage below 100%")
    return {
        "status": "needs-attention" if failures else "on-target",
        "reasons": failures,
    }


def project_snapshot(entry, touch_provider=touch_rate.calculate):
    path = Path(entry["path"])
    base = {
        "project_id": entry["project_id"],
        "name": entry["name"],
        "path": str(path),
        "registered_at": entry["registered_at"],
    }
    try:
        if not path.exists() or not (path / ".git").exists():
            raise ValueError("project path is unavailable")
        marker = framework_cli.validate_marker(framework_cli.read_json(path / ".007/project.json"))
        if marker["project_id"] != entry["project_id"]:
            raise ValueError("project marker does not match registry")
        receipt_dir = path / ".007" / marker["receipt_dir"]
        receipts, errors = harness_report.load_receipts(receipt_dir)
    except (OSError, ValueError) as exc:
        touch = {str(days): unknown_touch(days, str(exc)) for days in (7, 30)}
        metrics = metrics_from_receipts([])
        return {
            **base,
            "available": False,
            "error": str(exc),
            "metrics": metrics,
            "touch": touch,
            "recent_tasks": [],
            "invalid_receipts": [],
            "evidence": {"status": "collecting", "reasons": [str(exc)]},
        }

    touch = {}
    for days in (7, 30):
        try:
            touch[str(days)] = touch_provider(path, days)
        except (OSError, RuntimeError, ValueError) as exc:
            touch[str(days)] = unknown_touch(days, f"touch sensor failed: {exc}")
    metrics = metrics_from_receipts(receipts)
    recent = [safe_task(item) for item in receipts[-20:]][::-1]
    invalid = [{"file": Path(item["file"]).name, "error": item["error"]} for item in errors]
    return {
        **base,
        "available": True,
        "error": None,
        "metrics": metrics,
        "touch": touch,
        "recent_tasks": recent,
        "invalid_receipts": invalid,
        "evidence": evidence_state(metrics, touch, len(invalid)),
    }


def aggregate_touch(projects, days):
    rows = [
        project.get("touch", {}).get(str(days), {})
        for project in projects if project.get("available")
    ]
    known = [row for row in rows if row.get("rate") is not None]
    added = sum(row.get("agent_lines_added", 0) for row in known)
    surviving = sum(row.get("surviving_lines", 0) for row in known)
    rate = (100 * (1 - surviving / added)) if added else (0.0 if known else None)
    return {
        "window_days": days,
        "agent_lines_added": added,
        "surviving_lines": surviving,
        "rate": rate,
        "known_projects": len(known),
        "missing_projects": len(rows) - len(known),
        "reason": None if known else "no project has attributable agent commits",
    }


def aggregate_projects(projects):
    available = [project for project in projects if project.get("available")]
    result = {key: 0 for key in RAW_METRICS}
    for project in available:
        for key in RAW_METRICS:
            result[key] += project.get("metrics", {}).get(key, 0)
    result["cost_usd_known_sum"] = round(result["cost_usd_known_sum"], 6)
    result["accepted_cost_usd_known_sum"] = round(result["accepted_cost_usd_known_sum"], 6)
    combined_routes = {}
    for project in available:
        for route in project.get("metrics", {}).get("routes", []):
            row = combined_routes.setdefault(route["key"], {
                key: route[key] for key in ("key", "provider", "model", "binding")
            } | {"tasks": 0, "accepted": 0, "cost_usd_known_sum": 0, "cost_usd_known_tasks": 0})
            if row["binding"] != route["binding"]:
                row["binding"] = "mixed"
            for key in ("tasks", "accepted", "cost_usd_known_sum", "cost_usd_known_tasks"):
                row[key] += route[key]
    for row in combined_routes.values():
        row["cost_usd_known_sum"] = round(row["cost_usd_known_sum"], 6)
    result.update({
        "projects_total": len(projects),
        "projects_available": len(available),
        "projects_unavailable": len(projects) - len(available),
        "first_pass_rate": ratio(result["first_pass_yes"], result["first_pass_known"]),
        "first_pass_unknown_tasks": result["tasks"] - result["first_pass_known"],
        "repair_rounds_mean": ratio(result["repair_rounds_sum"], result["repair_rounds_known_tasks"]),
        "tokens_missing_tasks": result["tasks"] - result["tokens_known_tasks"],
        "tokens_per_accepted": (
            ratio(result["accepted_tokens_known_sum"], result["accepted"])
            if result["accepted"] and result["accepted_tokens_known_tasks"] == result["accepted"] else None
        ),
        "wall_s_per_accepted": (
            ratio(result["accepted_wall_s_known_sum"], result["accepted"])
            if result["accepted"] and result["accepted_wall_s_known_tasks"] == result["accepted"] else None
        ),
        "cost_usd_per_accepted": (
            ratio(result["accepted_cost_usd_known_sum"], result["accepted"])
            if result["accepted"] and result["accepted_cost_usd_known_tasks"] == result["accepted"] else None
        ),
        "cost_coverage": ratio(result["cost_usd_known_tasks"], result["tasks"]),
        "cost_accounting_status": (
            None if not result["cost_usd_known_tasks"]
            else "provisional" if result["cost_provisional_tasks"]
            else "final"
        ),
        "escape_7d_rate": ratio(result["escape_7d_yes"], result["escape_7d_known"]),
        "escape_7d_pending_tasks": result["tasks"] - result["escape_7d_known"],
        "telemetry_completeness": ratio(result["telemetry_known"], result["telemetry_possible"]),
        "routes": [combined_routes[key] for key in sorted(combined_routes)],
    })
    touch = {str(days): aggregate_touch(projects, days) for days in (7, 30)}
    result["touch"] = touch
    invalid = sum(len(project.get("invalid_receipts", [])) for project in available)
    result["invalid_receipts"] = invalid
    result["evidence"] = evidence_state(result, touch, invalid)
    return result


class TouchCache:
    def __init__(self, sensor=touch_rate.calculate, ttl=60, clock=time.monotonic):
        self.sensor = sensor
        self.ttl = ttl
        self.clock = clock
        self.values = {}
        self.lock = threading.Lock()

    def __call__(self, repo, days):
        key = (str(Path(repo).resolve()), days)
        with self.lock:
            cached = self.values.get(key)
            now = self.clock()
            if cached and now - cached[0] < self.ttl:
                return cached[1]
            value = self.sensor(repo, days)
            self.values[key] = (now, value)
            return value


def registry_entries(path):
    path = Path(path).expanduser()
    if not path.exists():
        return [], []
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [], [{"location": str(path), "error": f"invalid registry: {exc}"}]
    if not isinstance(value, dict) or value.get("schema") != framework_cli.REGISTRY_SCHEMA or not isinstance(value.get("projects"), list):
        return [], [{"location": str(path), "error": "invalid registry schema"}]
    required = ("project_id", "name", "path", "registered_at")
    entries, errors = [], []
    for index, item in enumerate(value["projects"]):
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key] for key in required):
            errors.append({"location": f"projects[{index}]", "error": "invalid registry entry"})
            continue
        entries.append({key: item[key] for key in required})
    return entries, errors


def build_snapshot(registry, touch_provider=touch_rate.calculate):
    entries, registry_errors = registry_entries(registry)
    projects = [project_snapshot(entry, touch_provider) for entry in entries]
    return {
        "schema": "007-framework/dashboard-snapshot/v1",
        "framework_version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "aggregate": aggregate_projects(projects),
        "projects": projects,
        "registry_errors": registry_errors,
        "causal_evidence": {
            "status": "narrow-positive",
            "claim": "One frozen mechanism test observed OLD 0/3 versus NEW 3/3.",
            "boundary": "Operational project metrics are observational and do not prove causality.",
        },
    }


def handler_class(registry, static_dir, touch_provider):
    static_dir = Path(static_dir)
    assets = {
        "/": (static_dir / "index.html", "text/html; charset=utf-8"),
        "/styles.css": (static_dir / "styles.css", "text/css; charset=utf-8"),
        "/app.js": (static_dir / "app.js", "text/javascript; charset=utf-8"),
    }

    class Handler(BaseHTTPRequestHandler):
        server_version = "007Dashboard/1.1"

        def send_common_headers(self, content_type, length, cache="no-store"):
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")

        def json_response(self, status, value):
            payload = json.dumps(value, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_common_headers("application/json; charset=utf-8", len(payload))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            request = urlsplit(self.path)
            if request.query or request.fragment:
                self.json_response(400, {"error": "query parameters are not supported"})
                return
            if request.path == "/api/health":
                self.json_response(200, {"status": "ok", "version": VERSION})
                return
            if request.path == "/api/snapshot":
                try:
                    self.json_response(200, build_snapshot(registry, touch_provider))
                except Exception:
                    self.json_response(500, {"error": "snapshot unavailable"})
                return
            asset = assets.get(request.path)
            if not asset:
                self.json_response(404, {"error": "not found"})
                return
            try:
                payload = asset[0].read_bytes()
            except OSError:
                self.json_response(404, {"error": "asset not found"})
                return
            self.send_response(200)
            self.send_common_headers(asset[1], len(payload), "public, max-age=60")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format, *_args):
            pass

    return Handler


def create_server(host, port, registry, static_dir):
    cache = TouchCache()
    server = ThreadingHTTPServer(
        (host, port), handler_class(Path(registry), Path(static_dir), cache)
    )
    server.daemon_threads = True
    return server
