#!/usr/bin/env python3
"""Build and serve safe multi-project snapshots for 007 Framework."""

import json
import math
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import framework_cli
import harness_report
import local_activity
import touch_rate


MISSING = {"", "unmeasured", "pending", "N/D", "unknown", None}
VERSION = "1.4.0"
ACTIVITY_COLLECTOR = local_activity.ActivityCollector()
TELEMETRY_FIELDS = ("provider", "model", "effort", "tokens", "wall_s")
RAW_METRICS = (
    "tasks", "accepted", "blocked", "no_op",
    "started_tasks", "matched_terminal_tasks", "active_tasks", "unstarted_terminal_tasks",
    "accepted_first_pass_yes", "reliable_first_pass_yes", "reliable_first_pass_known",
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
    "authority_bound_tasks", "authority_controlled_tasks", "authority_declared_tasks",
    "boundary_events", "allowed_executions",
    "protected_blocks", "friction_blocks", "unclassified_blocks",
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


def is_preventive_controller_block(receipt):
    return (
        receipt.get("status") == "blocked"
        and receipt.get("proof_reached") == "controller-blocked-before-execution"
    )


def load_causal_evidence(path=None):
    source = Path(path) if path else Path(__file__).resolve().parents[1] / "evidence" / "v1.4.0" / "causal-roi-result.json"
    try:
        value = json.loads(source.read_text())
        if (
            not isinstance(value, dict)
            or value.get("schema") != "007-framework/causal-roi/v1"
            or not all(isinstance(value.get(key), expected) for key, expected in (
                ("status", str), ("claim", str), ("boundary", str),
                ("sample", dict), ("served_identity", dict),
                ("old", dict), ("new", dict), ("delta", dict),
            ))
        ):
            raise ValueError("invalid causal ROI evidence")
        return value
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "status": "unavailable",
            "claim": "No causal ROI result is available.",
            "boundary": "The frozen causal ROI artifact is not available; operational metrics remain observational.",
            "sample": {}, "served_identity": {}, "old": {}, "new": {}, "delta": {},
        }


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def safe_task(receipt):
    task = {
        key: receipt.get(key)
        for key in (
            "task_id", "task_class", "status", "proof_required", "proof_reached",
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
    served_effort = receipt.get("served_effort") or receipt.get("effort")
    if is_known_label(served_model):
        provider = served_provider if is_known_label(served_provider) else "provider-unmeasured"
        effort = served_effort if is_known_label(served_effort) else "effort-unmeasured"
        return provider, served_model, effort, "served"
    requested_provider = receipt.get("requested_provider")
    requested_model = receipt.get("requested_model")
    requested_effort = receipt.get("requested_effort")
    if is_known_label(requested_model):
        provider = requested_provider if is_known_label(requested_provider) else "provider-unmeasured"
        effort = requested_effort if is_known_label(requested_effort) else "effort-unmeasured"
        return provider, requested_model, effort, "requested-unverified"
    return "provider-unmeasured", "model-unmeasured", "effort-unmeasured", "unmeasured"


def route_metrics(receipts):
    routes = {}
    for receipt in receipts:
        provider, model, effort, binding = route_for(receipt)
        task_class = receipt.get("task_class") if receipt.get("task_class") in framework_cli.TASK_CLASSES else "unclassified"
        key = f"{provider}/{model}@{effort}" if task_class == "unclassified" else f"{task_class}:{provider}/{model}@{effort}"
        row = routes.setdefault(key, {
            "key": key, "task_class": task_class,
            "provider": provider, "model": model, "effort": effort, "binding": binding,
            "tasks": 0, "accepted": 0,
            "reliable": 0, "reliable_known": 0,
            "cost_usd_known_sum": 0, "cost_usd_known_tasks": 0,
            "wall_s_known_sum": 0, "wall_s_known_tasks": 0,
        })
        if row["binding"] != binding:
            row["binding"] = "mixed"
        row["tasks"] += 1
        row["accepted"] += int(receipt.get("status") == "accepted")
        mature = receipt.get("first_pass") in ("yes", "no") and receipt.get("escape_7d") in (True, False, "yes", "no")
        row["reliable_known"] += int(mature)
        row["reliable"] += int(
            receipt.get("status") == "accepted"
            and receipt.get("first_pass") == "yes"
            and receipt.get("escape_7d") in (False, "no")
        )
        if has_accounted_cost(receipt):
            row["cost_usd_known_sum"] += receipt["cost_usd"]
            row["cost_usd_known_tasks"] += 1
        if is_number(receipt.get("wall_s")):
            row["wall_s_known_sum"] += receipt["wall_s"]
            row["wall_s_known_tasks"] += 1
    for row in routes.values():
        row["cost_usd_known_sum"] = round(row["cost_usd_known_sum"], 6)
        row.update({
            "reliable_rate": ratio(row["reliable"], row["reliable_known"]),
            "cost_usd_per_reliable": (
                ratio(row["cost_usd_known_sum"], row["reliable"])
                if row["reliable"] and row["cost_usd_known_tasks"] == row["tasks"] else None
            ),
            "wall_s_per_reliable": (
                ratio(row["wall_s_known_sum"], row["reliable"])
                if row["reliable"] and row["wall_s_known_tasks"] == row["tasks"] else None
            ),
        })
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
    authority_totals = Counter()
    telemetry_known = 0
    delta_totals = {"files": 0, "added": 0, "deleted": 0}
    for item in receipts:
        escape = item.get("escape_7d")
        if escape in (True, "yes"):
            escape_yes += 1
            escape_known += 1
        elif escape in (False, "no"):
            escape_known += 1
        authority = item.get("authority_summary")
        if isinstance(authority, dict) and authority.get("bound") is True:
            authority_totals["authority_bound_tasks"] += 1
            authority_totals[
                "authority_controlled_tasks"
                if item.get("authority_evidence") == "controlled"
                else "authority_declared_tasks"
            ] += 1
            for key in (
                "events", "allowed_executions", "protected_blocks",
                "friction_blocks", "unclassified_blocks",
            ):
                if is_number(authority.get(key)):
                    authority_totals[key] += authority[key]
        if not is_preventive_controller_block(item):
            for served, legacy in (
                ("served_provider", "provider"),
                ("served_model", "model"),
                ("served_effort", "effort"),
            ):
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
        "authority_bound_tasks": authority_totals["authority_bound_tasks"],
        "authority_controlled_tasks": authority_totals["authority_controlled_tasks"],
        "authority_declared_tasks": authority_totals["authority_declared_tasks"],
        "boundary_events": authority_totals["events"],
        "allowed_executions": authority_totals["allowed_executions"],
        "protected_blocks": authority_totals["protected_blocks"],
        "friction_blocks": authority_totals["friction_blocks"],
        "unclassified_blocks": authority_totals["unclassified_blocks"],
        "telemetry_known": telemetry_known,
        "telemetry_possible": sum(
            not is_preventive_controller_block(item) for item in receipts
        ) * len(TELEMETRY_FIELDS),
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
        "authority_coverage": ratio(authority_totals["authority_bound_tasks"], tasks),
        "boundary_friction_rate": ratio(
            authority_totals["friction_blocks"],
            authority_totals["allowed_executions"] + authority_totals["friction_blocks"],
        ),
        "telemetry_completeness": ratio(telemetry_known, result["telemetry_possible"]),
    })
    return result


def metrics_from_observations(receipts, starts):
    result = metrics_from_receipts(receipts)
    start_ids = {item["task_id"] for item in starts}
    receipt_ids = {
        item.get("task_id") for item in receipts
        if isinstance(item.get("task_id"), str)
    }
    matched = len(start_ids & receipt_ids)
    accepted = [item for item in receipts if item.get("status") == "accepted"]
    accepted_first_pass = [item for item in accepted if item.get("first_pass") == "yes"]
    reliable_known = [
        item for item in accepted
        if item.get("first_pass") in ("yes", "no")
        and item.get("escape_7d") in (True, False, "yes", "no")
    ]
    reliable = [
        item for item in reliable_known
        if item.get("first_pass") == "yes" and item.get("escape_7d") in (False, "no")
    ]
    result.update({
        "started_tasks": len(start_ids),
        "matched_terminal_tasks": matched,
        "active_tasks": len(start_ids) - matched,
        "unstarted_terminal_tasks": len(receipt_ids - start_ids),
        "accepted_first_pass_yes": len(accepted_first_pass),
        "reliable_first_pass_yes": len(reliable),
        "reliable_first_pass_known": len(reliable_known),
        "observation_coverage": ratio(matched, len(start_ids)),
        "reliable_first_pass_rate": ratio(len(reliable), len(reliable_known)),
        "cost_usd_per_reliable": (
            ratio(result["cost_usd_known_sum"], len(reliable))
            if reliable and result["cost_usd_known_tasks"] == result["tasks"] else None
        ),
        "reliable_outcomes_per_usd": (
            ratio(len(reliable), result["cost_usd_known_sum"])
            if reliable and result["cost_usd_known_tasks"] == result["tasks"]
            and result["cost_usd_known_sum"] > 0 else None
        ),
        "wall_s_per_reliable": (
            ratio(result["wall_s_known_sum"], len(reliable))
            if reliable and result["wall_s_known_tasks"] == result["tasks"] else None
        ),
    })
    return result


def load_task_starts(path):
    path = Path(path)
    if not path.exists():
        return [], []
    starts, errors = [], []
    for source in sorted(path.glob("*.task.json")):
        try:
            starts.append(framework_cli.validate_task_start(framework_cli.read_json(source)))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"file": source.name, "error": str(exc)})
    return starts, errors


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


def authority_confidence(metrics):
    controlled = metrics.get("authority_controlled_tasks", 0)
    declared = metrics.get("authority_declared_tasks", 0)
    bound = metrics.get("authority_bound_tasks", 0)
    if not bound:
        label = "not-observed"
    elif controlled == bound:
        label = "controller-observed"
    elif not controlled:
        label = "declared"
    else:
        label = "mixed"
    return {
        "controlled": controlled,
        "declared": declared,
        "unobserved": max(metrics.get("tasks", 0) - bound, 0),
        "controlled_coverage": ratio(controlled, bound),
        "label": label,
    }


def outcome_trend(receipts, now=None, days=30):
    instant = now or datetime.now(timezone.utc)
    end = instant.astimezone(timezone.utc).date()
    rows = {
        (end - timedelta(days=offset)).isoformat(): {
            "date": (end - timedelta(days=offset)).isoformat(),
            "reliable": 0,
            "accepted_other": 0,
            "not_accepted": 0,
        }
        for offset in range(days)
    }
    for receipt in receipts:
        if is_preventive_controller_block(receipt):
            continue
        completed = receipt.get("completed_at")
        if not isinstance(completed, str):
            continue
        try:
            day = datetime.fromisoformat(completed.replace("Z", "+00:00")).astimezone(timezone.utc).date().isoformat()
        except ValueError:
            continue
        if day not in rows:
            continue
        if (
            receipt.get("status") == "accepted"
            and receipt.get("first_pass") == "yes"
            and receipt.get("escape_7d") in (False, "no")
        ):
            rows[day]["reliable"] += 1
        elif receipt.get("status") == "accepted":
            rows[day]["accepted_other"] += 1
        else:
            rows[day]["not_accepted"] += 1
    return [rows[key] for key in sorted(rows)]


def objective_state(
    metrics, touch, invalid_receipts=0, unavailable_projects=0,
    registry_errors=0, invalid_starts=0,
):
    mature = metrics.get("reliable_first_pass_known", 0)
    definitions = (
        ("mature", "Resultados aceitos maduros", mature, ">= 5", "pass" if mature >= 5 else "wait", mature),
        ("reliable", "Reliable first-pass em 7 dias", metrics.get("reliable_first_pass_rate"), ">= 70%", None, mature),
        ("repairs", "Média de rodadas de reparo", metrics.get("repair_rounds_mean"), "<= 0.5", None, metrics.get("repair_rounds_known_tasks", 0)),
        ("escape", "Taxa de escapes em 7 dias", metrics.get("escape_7d_rate"), "<= 5%", None, metrics.get("escape_7d_known", 0)),
        ("touch", "Toque corretivo em 30 dias", touch.get("30", {}).get("rate"), "<= 15%", None, touch.get("30", {}).get("agent_lines_added", 0)),
        ("cost", "Cobertura de custo terminal", metrics.get("cost_coverage"), "100%", None, metrics.get("tasks", 0)),
        ("telemetry", "Completude da telemetria", metrics.get("telemetry_completeness"), ">= 80%", None, metrics.get("telemetry_possible", 0)),
    )
    gates = []
    for key, label, actual, target, preset, denominator in definitions:
        if preset:
            status = preset
        elif actual is None or (key in ("reliable", "escape") and mature < 5):
            status = "wait"
        elif key in ("cost", "telemetry"):
            threshold = 1 if key == "cost" else 0.8
            status = "pass" if actual >= threshold else "wait"
        elif key == "reliable":
            status = "pass" if actual >= 0.7 else "fail"
        elif key == "repairs":
            status = "pass" if actual <= 0.5 else "fail"
        elif key == "escape":
            status = "pass" if actual <= 0.05 else "fail"
        else:
            status = "pass" if actual <= 15 else "fail"
        gates.append({
            "key": key, "label": label, "actual": actual, "target": target,
            "status": status, "denominator": denominator,
        })

    data_failures = (
        invalid_receipts + unavailable_projects + registry_errors + invalid_starts
    )
    if data_failures:
        primary = f"Corrija {data_failures} fonte(s) de dados inválida(s) ou indisponível(is)."
    elif metrics.get("started_tasks", 0) == 0:
        primary = "Inicie trabalho medido com 007 begin ou 007 run."
    elif metrics.get("tasks", 0) == 0 and metrics.get("active_tasks", 0):
        active = metrics["active_tasks"]
        primary = f"Conclua {active} tarefa(s) ativa(s) com 007 record."
    elif metrics.get("cost_coverage") is None or metrics.get("cost_coverage", 0) < 1:
        missing = max(metrics.get("tasks", 0) - metrics.get("cost_usd_known_tasks", 0), 0)
        primary = f"Registre o custo terminal de {missing} resultado(s)."
    elif metrics.get("telemetry_completeness") is None or metrics.get("telemetry_completeness", 0) < 0.8:
        missing = max(metrics.get("telemetry_possible", 0) - metrics.get("telemetry_known", 0), 0)
        primary = f"Capture {missing} campo(s) de telemetria ausente(s)."
    elif mature < 5:
        primary = f"Mature mais {5 - mature} resultado(s) aceito(s) por 7 dias."
    else:
        failed = next((gate for gate in gates if gate["status"] == "fail"), None)
        primary = (
            f"Melhore {failed['label']} até {failed['target']}."
            if failed else "Continue coletando resultados controlados."
        )
    failures = any(gate["status"] == "fail" for gate in gates)
    waiting = any(gate["status"] == "wait" for gate in gates)
    if data_failures or metrics.get("started_tasks", 0) == 0:
        status = "not-measurable"
    elif failures:
        status = "off-target"
    else:
        status = "not-measurable" if waiting else "on-target"
    return {
        "status": status,
        "headline": {
            "on-target": "YES — on target",
            "off-target": "NO — off target",
            "not-measurable": "NOT YET MEASURABLE",
        }[status],
        "primary_action": primary,
        "gates": gates,
    }


def evidence_state(metrics, touch, invalid_receipts=0, unavailable_projects=0, registry_errors=0, invalid_starts=0):
    data_failures = []
    if invalid_receipts:
        data_failures.append(f"{invalid_receipts} invalid receipt(s)")
    if invalid_starts:
        data_failures.append(f"{invalid_starts} invalid task start(s)")
    if unavailable_projects:
        data_failures.append(f"{unavailable_projects} unavailable project(s)")
    if registry_errors:
        data_failures.append(f"{registry_errors} registry error(s)")
    objective = objective_state(
        metrics, touch, invalid_receipts, unavailable_projects, registry_errors, invalid_starts,
    )
    if data_failures:
        return {"status": "needs-attention", "reasons": data_failures}
    if metrics.get("started_tasks", 0) == 0:
        return {"status": "instrumentation-inactive", "reasons": ["no observed task starts"]}
    failed_reasons = {
        "reliable": "reliable first-pass rate below 70%",
        "repairs": "mean repair rounds above 0.5",
        "escape": "7-day escape rate above 5%",
        "touch": "30-day touch proxy above 15%",
    }
    failures = [
        failed_reasons[gate["key"]]
        for gate in objective["gates"]
        if gate["status"] == "fail" and gate["key"] in failed_reasons
    ]
    if failures:
        return {"status": "needs-attention", "reasons": failures}
    waiting = [gate for gate in objective["gates"] if gate["status"] == "wait"]
    return {
        "status": "collecting" if waiting else "on-target",
        "reasons": [
            "fewer than 5 matured accepted tasks"
            if gate["key"] == "mature" else f"{gate['label'].lower()} is N/D or incomplete"
            for gate in waiting
        ],
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
        receipt_dir = framework_cli.receipt_directory(path / ".007/project.json", marker)
        receipts, errors = harness_report.load_receipts(receipt_dir)
    except (OSError, ValueError) as exc:
        touch = {str(days): unknown_touch(days, str(exc)) for days in (7, 30)}
        metrics = metrics_from_observations([], [])
        return {
            **base,
            "available": False,
            "error": str(exc),
            "metrics": metrics,
            "touch": touch,
            "recent_tasks": [],
            "invalid_receipts": [],
            "invalid_task_starts": [],
            "evidence": {"status": "collecting", "reasons": [str(exc)]},
            "objective": objective_state(metrics, touch, unavailable_projects=1),
            "authority_confidence": authority_confidence(metrics),
            "trend_30d": outcome_trend([]),
        }

    touch = {}
    for days in (7, 30):
        try:
            touch[str(days)] = touch_provider(path, days)
        except (OSError, RuntimeError, ValueError) as exc:
            touch[str(days)] = unknown_touch(days, f"touch sensor failed: {exc}")
    starts, start_errors = load_task_starts(path / ".007" / "tasks")
    metrics = metrics_from_observations(receipts, starts)
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
        "invalid_task_starts": start_errors,
        "evidence": evidence_state(metrics, touch, len(invalid), invalid_starts=len(start_errors)),
        "objective": objective_state(metrics, touch, len(invalid), invalid_starts=len(start_errors)),
        "authority_confidence": authority_confidence(metrics),
        "trend_30d": outcome_trend(receipts),
    }


def aggregate_touch(projects, days):
    available = [project for project in projects if project.get("available")]
    rows = [
        project.get("touch", {}).get(str(days), {})
        for project in available
    ]
    known = [row for row in rows if row.get("rate") is not None]
    added = sum(row.get("agent_lines_added", 0) for row in known)
    surviving = sum(row.get("surviving_lines", 0) for row in known)
    missing = len(rows) - len(known)
    rate = None if missing else ((100 * (1 - surviving / added)) if added else (0.0 if known else None))
    return {
        "window_days": days,
        "agent_lines_added": added,
        "surviving_lines": surviving,
        "rate": rate,
        "known_projects": len(known),
        "missing_projects": missing,
        "reason": (
            f"touch unavailable for {missing} of {len(rows)} projects" if missing
            else None if known
            else "no available projects"
        ),
    }


def aggregate_projects(projects, registry_error_count=0):
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
                key: route[key] for key in ("key", "task_class", "provider", "model", "effort", "binding")
            } | {
                "tasks": 0, "accepted": 0, "reliable": 0, "reliable_known": 0,
                "cost_usd_known_sum": 0, "cost_usd_known_tasks": 0,
                "wall_s_known_sum": 0, "wall_s_known_tasks": 0,
            })
            if row["binding"] != route["binding"]:
                row["binding"] = "mixed"
            for key in (
                "tasks", "accepted", "reliable", "reliable_known",
                "cost_usd_known_sum", "cost_usd_known_tasks",
                "wall_s_known_sum", "wall_s_known_tasks",
            ):
                row[key] += route[key]
    for row in combined_routes.values():
        row["cost_usd_known_sum"] = round(row["cost_usd_known_sum"], 6)
        row.update({
            "reliable_rate": ratio(row["reliable"], row["reliable_known"]),
            "cost_usd_per_reliable": (
                ratio(row["cost_usd_known_sum"], row["reliable"])
                if row["reliable"] and row["cost_usd_known_tasks"] == row["tasks"] else None
            ),
            "wall_s_per_reliable": (
                ratio(row["wall_s_known_sum"], row["reliable"])
                if row["reliable"] and row["wall_s_known_tasks"] == row["tasks"] else None
            ),
        })
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
        "observation_coverage": ratio(result["matched_terminal_tasks"], result["started_tasks"]),
        "reliable_first_pass_rate": ratio(
            result["reliable_first_pass_yes"], result["reliable_first_pass_known"]
        ),
        "cost_usd_per_reliable": (
            ratio(result["cost_usd_known_sum"], result["reliable_first_pass_yes"])
            if result["reliable_first_pass_yes"]
            and result["cost_usd_known_tasks"] == result["tasks"] else None
        ),
        "reliable_outcomes_per_usd": (
            ratio(result["reliable_first_pass_yes"], result["cost_usd_known_sum"])
            if result["reliable_first_pass_yes"]
            and result["cost_usd_known_tasks"] == result["tasks"]
            and result["cost_usd_known_sum"] > 0 else None
        ),
        "wall_s_per_reliable": (
            ratio(result["wall_s_known_sum"], result["reliable_first_pass_yes"])
            if result["reliable_first_pass_yes"]
            and result["wall_s_known_tasks"] == result["tasks"] else None
        ),
        "cost_coverage": ratio(result["cost_usd_known_tasks"], result["tasks"]),
        "cost_accounting_status": (
            None if not result["cost_usd_known_tasks"]
            else "provisional" if result["cost_provisional_tasks"]
            else "final"
        ),
        "escape_7d_rate": ratio(result["escape_7d_yes"], result["escape_7d_known"]),
        "escape_7d_pending_tasks": result["tasks"] - result["escape_7d_known"],
        "authority_coverage": ratio(result["authority_bound_tasks"], result["tasks"]),
        "boundary_friction_rate": ratio(
            result["friction_blocks"],
            result["allowed_executions"] + result["friction_blocks"],
        ),
        "telemetry_completeness": ratio(result["telemetry_known"], result["telemetry_possible"]),
        "routes": [combined_routes[key] for key in sorted(combined_routes)],
    })
    touch = {str(days): aggregate_touch(projects, days) for days in (7, 30)}
    result["touch"] = touch
    invalid = sum(len(project.get("invalid_receipts", [])) for project in available)
    invalid_starts = sum(len(project.get("invalid_task_starts", [])) for project in available)
    result["invalid_receipts"] = invalid
    result["invalid_task_starts"] = invalid_starts
    result["evidence"] = evidence_state(
        result, touch, invalid, result["projects_unavailable"], registry_error_count,
        invalid_starts,
    )
    result["objective"] = objective_state(
        result, touch, invalid, result["projects_unavailable"], registry_error_count,
        invalid_starts,
    )
    result["authority_confidence"] = authority_confidence(result)
    trend = {row["date"]: row for row in outcome_trend([])}
    for project in available:
        for row in project.get("trend_30d", []):
            if row.get("date") in trend:
                for key in ("reliable", "accepted_other", "not_accepted"):
                    trend[row["date"]][key] += row.get(key, 0)
    result["trend_30d"] = [trend[key] for key in sorted(trend)]
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


def build_snapshot(registry, touch_provider=touch_rate.calculate, activity_provider=None):
    entries, registry_errors = registry_entries(registry)
    projects = [project_snapshot(entry, touch_provider) for entry in entries]
    activity = (activity_provider or ACTIVITY_COLLECTOR.collect)(entries)
    for project in projects:
        project["activity"] = activity.get("projects", {}).get(
            project["project_id"], local_activity.empty_summary(ACTIVITY_COLLECTOR.lookback_hours)
        )
    aggregate = aggregate_projects(projects, len(registry_errors))
    aggregate["activity"] = activity.get("aggregate", local_activity.empty_summary(ACTIVITY_COLLECTOR.lookback_hours))
    return {
        "schema": "007-framework/dashboard-snapshot/v1",
        "framework_version": VERSION,
        "telemetry_fields": list(TELEMETRY_FIELDS),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "aggregate": aggregate,
        "projects": projects,
        "registry_errors": registry_errors,
        "activity_errors": activity.get("errors", []),
        "measurement_boundary": {
            "cost_denominator": "observed-terminal-receipts",
            "cost_authority": "terminal-receipt",
            "label": "A cobertura operacional começa em 007 begin e termina em 007 record. Execuções anteriores ou externas a esse ciclo permanecem fora do denominador.",
        },
        "causal_evidence": load_causal_evidence(),
    }


def handler_class(registry, static_dir, touch_provider, activity_provider=None):
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
                    self.json_response(200, build_snapshot(registry, touch_provider, activity_provider))
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


def create_server(host, port, registry, static_dir, activity_provider=None):
    cache = TouchCache()
    server = ThreadingHTTPServer(
        (host, port), handler_class(Path(registry), Path(static_dir), cache, activity_provider)
    )
    server.daemon_threads = True
    return server
