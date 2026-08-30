#!/usr/bin/env python3
"""Build safe multi-project snapshots for the 007 Framework dashboard."""

import math
from collections import Counter
from pathlib import Path

import framework_cli
import harness_report
import touch_rate


MISSING = {"", "unmeasured", "pending", "N/D", "unknown", None}
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
    "escape_7d_yes", "escape_7d_known",
    "telemetry_known", "telemetry_possible",
    "delta_files", "delta_added", "delta_deleted",
)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_known_label(value):
    return isinstance(value, str) and value not in MISSING


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def safe_task(receipt):
    task = {
        key: receipt.get(key)
        for key in (
            "task_id", "status", "proof_required", "proof_reached",
            "first_pass", "repair_rounds", "corrective_lines", "escape_7d",
            "model", "effort", "tokens", "wall_s", "cost_usd",
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


def metrics_from_receipts(receipts):
    statuses = Counter(str(item.get("status", "unknown")) for item in receipts)
    first_pass = Counter(str(item.get("first_pass", "unmeasured")) for item in receipts)
    repairs = [item.get("repair_rounds") for item in receipts if is_number(item.get("repair_rounds"))]
    tokens = [item.get("tokens") for item in receipts if is_number(item.get("tokens"))]
    wall = [item.get("wall_s") for item in receipts if is_number(item.get("wall_s"))]
    costs = [item.get("cost_usd") for item in receipts if is_number(item.get("cost_usd"))]
    accepted = [item for item in receipts if item.get("status") == "accepted"]
    accepted_tokens = [item.get("tokens") for item in accepted if is_number(item.get("tokens"))]
    accepted_wall = [item.get("wall_s") for item in accepted if is_number(item.get("wall_s"))]
    accepted_cost = [item.get("cost_usd") for item in accepted if is_number(item.get("cost_usd"))]

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
        for key in ("model", "effort"):
            if is_known_label(item.get(key)):
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
        "escape_7d_yes": escape_yes,
        "escape_7d_known": escape_known,
        "telemetry_known": telemetry_known,
        "telemetry_possible": tasks * 4,
        "delta_files": delta_totals["files"],
        "delta_added": delta_totals["added"],
        "delta_deleted": delta_totals["deleted"],
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
        "escape_7d_rate": ratio(result["escape_7d_yes"], result["escape_7d_known"]),
        "escape_7d_pending_tasks": result["tasks"] - result["escape_7d_known"],
        "telemetry_completeness": ratio(result["telemetry_known"], result["telemetry_possible"]),
    })
    touch = {str(days): aggregate_touch(projects, days) for days in (7, 30)}
    result["touch"] = touch
    invalid = sum(len(project.get("invalid_receipts", [])) for project in available)
    result["invalid_receipts"] = invalid
    result["evidence"] = evidence_state(result, touch, invalid)
    return result
