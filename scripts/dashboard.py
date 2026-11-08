#!/usr/bin/env python3
"""Build and serve safe multi-project snapshots for 007 Framework."""

import json
import copy
import hashlib
import math
import os
import stat
import subprocess
import sys
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
import effort_trial_analysis
import observatory_history
import replay_capture
import replay_eval
import touch_rate


MISSING = {"", "unmeasured", "pending", "N/A", "N/D", "unknown", None}  # "N/D": legacy receipts, still accepted
VERSION = "1.6.0"
ACTIVITY_COLLECTOR = local_activity.ActivityCollector()
TELEMETRY_FIELDS = ("provider", "model", "effort", "tokens", "wall_s")
RAW_METRICS = (
    "tasks", "accepted", "blocked", "no_op",
    "accepted_controller_observed", "accepted_declared",
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


def has_bound_acceptance(receipt):
    summary = receipt.get("acceptance_summary")
    digest = receipt.get("acceptance_sha256")
    return (
        receipt.get("acceptance_evidence") == "controlled"
        and isinstance(summary, dict)
        and type(summary.get("passed")) is int and summary["passed"] >= 1
        and type(summary.get("failed")) is int and summary["failed"] == 0
        and isinstance(digest, str) and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest)
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
    task["cost_basis"] = harness_report.receipt_cost_basis(receipt)
    ref = receipt.get("replay_ref")
    if (isinstance(ref, dict) and isinstance(ref.get("sha256"), str)
            and len(ref["sha256"]) == 64 and all(c in "0123456789abcdef" for c in ref["sha256"])):
        task["input_sha256"] = ref["sha256"]
    summary = receipt.get("acceptance_summary")
    digest = receipt.get("acceptance_sha256")
    if (receipt.get("acceptance_evidence") == "controlled" and isinstance(summary, dict)
            and all(type(summary.get(key)) is int and summary[key] >= 0 for key in ("passed", "failed"))
            and summary["passed"] + summary["failed"] > 0
            and (receipt.get("status") != "accepted" or has_bound_acceptance(receipt))
            and isinstance(digest, str) and len(digest) == 64
            and all(char in "0123456789abcdef" for char in digest)):
        task.update(acceptance_evidence="declared", acceptance_sha256=digest,
                    acceptance_summary={key: summary[key] for key in ("passed", "failed")})
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


def route_metrics(receipts, *, starts=None, followups=None, as_of=None, acquisition_errors=()):
    as_of = as_of or datetime.now(timezone.utc)
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
            "cost_sources": Counter(), "cost_provisional_tasks": 0,
            "wall_s_known_sum": 0, "wall_s_known_tasks": 0,
            "_receipts": [],
        })
        row["_receipts"].append(receipt)
        if row["binding"] != binding:
            row["binding"] = "mixed"
        row["tasks"] += 1
        row["accepted"] += int(receipt.get("status") == "accepted")
        mature = receipt.get("status") == "accepted" and receipt.get("first_pass") in ("yes", "no") and receipt.get("escape_7d") in (True, False, "yes", "no")
        row["reliable_known"] += int(mature)
        row["reliable"] += int(
            receipt.get("status") == "accepted"
            and receipt.get("first_pass") == "yes"
            and receipt.get("escape_7d") in (False, "no")
        )
        if has_accounted_cost(receipt):
            row["cost_usd_known_sum"] += receipt["cost_usd"]
            row["cost_usd_known_tasks"] += 1
            row["cost_sources"][receipt["cost_source"]] += 1
            row["cost_provisional_tasks"] += int(receipt["cost_status"] == "provisional")
        if is_number(receipt.get("wall_s")):
            row["wall_s_known_sum"] += receipt["wall_s"]
            row["wall_s_known_tasks"] += 1
    for row in routes.values():
        members = row.pop("_receipts")
        ids = {harness_report._identity(r) for r in members}
        terminals = {harness_report._identity(r) for r in receipts}
        cohort_starts = [s for s in (starts or []) if harness_report._identity(s) in ids
                         or harness_report._identity(s) not in terminals]
        events = followups if followups is not None else [r["followup_7d"] for r in members if isinstance(r.get("followup_7d"), dict)]
        economics = harness_report.summarize_economics(members, starts=cohort_starts,
            followups=events, cost_basis=None, as_of=as_of or datetime.now(timezone.utc), acquisition_errors=acquisition_errors)
        if any(harness_report.route_identity_unavailable(r) for r in receipts):
            economics["cohort_complete"] = False
            economics["cost_scope_complete"] = False
            economics["cost_usd_per_declared_accepted_with_overhead"] = None
            economics["cost_usd_per_reliable_with_overhead_declared"] = None
            economics["reasons"] = sorted(set(economics["reasons"]) | {"terminal route scope unavailable"})
            economics["cost_usd_per_reliable_declared"] = None
            economics["wall_s_per_reliable_declared"] = None
        row["cost_usd_known_sum"] = round(row["cost_usd_known_sum"], 6)
        row.update({
            "economics": economics,
            "cost_sources": dict(row["cost_sources"]),
            "cost_accounting_status": (
                None if not row["cost_usd_known_tasks"]
                else "provisional" if row["cost_provisional_tasks"] else "final"
            ),
            "reliable": economics["reliable_declared"],
            "reliable_known": economics["quality_known_declared"],
            "reliable_rate": ratio(economics["reliable_declared"], economics["quality_known_declared"]),
            "cost_usd_per_reliable": economics["cost_usd_per_reliable_declared"],
            "wall_s_per_reliable": economics["wall_s_per_reliable_declared"],
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
    # Local files bind contracts, but cannot authenticate their producer.
    controlled_acceptance = 0

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
            authority_totals["authority_declared_tasks"] += 1
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
        "accepted_controller_observed": controlled_acceptance,
        "accepted_declared": len(accepted) - controlled_acceptance,
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
        "cost_sources": dict(Counter(item["cost_source"] for item in receipts if has_accounted_cost(item))),
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


def metrics_from_observations(receipts, starts, *, followups=None, as_of=None, acquisition_errors=()):
    as_of = datetime.now(timezone.utc) if as_of is None else as_of
    result = metrics_from_receipts(receipts)
    cutoff = harness_report._instant(as_of)
    instants = [harness_report._instant(item.get(field))
                for items, field in ((receipts, "completed_at"), (starts, "started_at")) for item in items]
    observed = [instant for instant in instants if cutoff is not None and instant is not None and instant <= cutoff]
    result["latest_event_at"] = max(observed).isoformat() if observed else None
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
    events = followups if followups is not None else [r["followup_7d"] for r in receipts if isinstance(r.get("followup_7d"), dict)]
    result["economics"] = harness_report.summarize_economics(receipts, starts=starts,
        followups=events, cost_basis=None, as_of=as_of, acquisition_errors=acquisition_errors)
    result["cost_usd_per_reliable"] = result["economics"]["cost_usd_per_reliable_declared"]
    result["wall_s_per_reliable"] = result["economics"]["wall_s_per_reliable_declared"]
    result["reliable_outcomes_per_usd"] = (
        1 / result["cost_usd_per_reliable"] if result["cost_usd_per_reliable"] else None)
    result["legacy_cost_metric_scope"] = "unseparated-declared-totals"
    result["routes"] = route_metrics(receipts, starts=starts, followups=events, as_of=as_of, acquisition_errors=acquisition_errors)
    return result


def load_task_starts(path, *, project_id=None):
    path = Path(path)
    try:
        with os.scandir(path) as entries:
            sources = sorted(Path(entry.path) for entry in entries if entry.name.endswith(".task.json"))
    except FileNotFoundError:
        return [], []
    except OSError:
        return [], [{"file": path.name, "error": "task directory unavailable"}]
    starts, errors = [], []
    for source in sources:
        try:
            value = framework_cli.validate_task_start(framework_cli.read_json(source))
            starts.extend(harness_report.scope_project([value], project_id) if project_id is not None else [value])
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
    bound = metrics.get("authority_bound_tasks", 0)
    controlled = 0
    declared = bound
    if not bound:
        label = "not-observed"
    else:
        label = "declared"
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


def event_trend(starts, receipts, *, as_of=None):
    instant = harness_report._instant(datetime.now(timezone.utc) if as_of is None else as_of)
    if instant is None:
        raise ValueError("event timeline requires an aware cutoff")
    days = [(instant.date() - timedelta(days=offset)).isoformat() for offset in range(30)]
    rows = {day: {"at": day + "T00:00:00+00:00", "started": 0, "terminal": 0} for day in days}
    excluded, outside = 0, 0
    for key, records, field in (("started", starts, "started_at"), ("terminal", receipts, "completed_at")):
        identities = Counter(record.get("task_id") for record in records if isinstance(record.get("task_id"), str))
        for record in records:
            identifier = record.get("task_id")
            point = harness_report._instant(record.get(field))
            if (not isinstance(identifier, str) or not replay_capture.ID.fullmatch(identifier)
                    or identities[identifier] != 1 or point is None or point > instant):
                excluded += 1
            elif point.date().isoformat() not in rows:
                outside += 1
            else:
                rows[point.date().isoformat()][key] += 1
    return {"scope": "declared-events-utc-30d", "complete": excluded == 0,
            "excluded": excluded, "outside_window": outside, "rows": [rows[day] for day in sorted(rows)]}


def objective_state(
    metrics, touch, invalid_receipts=0, unavailable_projects=0,
    registry_errors=0, invalid_starts=0,
):
    mature = metrics.get("reliable_first_pass_known", 0)
    economics = metrics.get("economics") or {}
    economics_ready = (economics.get("cohort_complete") is True
                       and economics.get("cost_coverage") == 1 and economics.get("followup_pending") == 0
                       and economics.get("cost_scope_complete") is True)
    if economics:
        mature = economics.get("linked_followups", 0)
        quality_known = economics.get("quality_known_declared", mature)
        reliable_rate = ratio(economics.get("reliable_declared", 0), quality_known)
        escape_rate = ratio(economics.get("escapes_declared", 0), mature)
    else:
        quality_known = mature
        reliable_rate, escape_rate = metrics.get("reliable_first_pass_rate"), metrics.get("escape_7d_rate")
    definitions = (
        ("mature", "Accepted with declared D7 follow-up", mature, ">= 5", "pass" if mature >= 5 else "wait", mature),
        ("reliable", "First-pass with no declared D7 escape", reliable_rate, ">= 70%", None, quality_known),
        ("repairs", "Mean repair rounds", metrics.get("repair_rounds_mean"), "<= 0.5", None, metrics.get("repair_rounds_known_tasks", 0)),
        ("escape", "Declared D7 escape rate", escape_rate, "<= 5%", None, mature),
        ("touch", "Corrective touch over 30 days", touch.get("30", {}).get("rate"), "<= 15%", None, touch.get("30", {}).get("agent_lines_added", 0)),
        ("cost", "Terminal cost coverage", metrics.get("cost_coverage"), "100%", None, metrics.get("tasks", 0)),
        ("telemetry", "Telemetry completeness", metrics.get("telemetry_completeness"), ">= 80%", None, metrics.get("telemetry_possible", 0)),
        ("economics", "Declared cohort, USD basis, overhead and follow-up", economics_ready, "complete", "pass" if economics_ready else "wait", economics.get("cohort_tasks", 0)),
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
        primary = f"Fix {data_failures} invalid or unavailable data source(s)."
    elif metrics.get("started_tasks", 0) == 0:
        primary = "Start measured work with 007 begin or 007 run."
    elif metrics.get("tasks", 0) == 0 and metrics.get("active_tasks", 0):
        active = metrics["active_tasks"]
        primary = f"Complete {active} active task(s) with 007 record."
    elif metrics.get("cost_coverage") is None or metrics.get("cost_coverage", 0) < 1:
        missing = max(metrics.get("tasks", 0) - metrics.get("cost_usd_known_tasks", 0), 0)
        primary = f"Record the terminal cost of {missing} outcome(s)."
    elif metrics.get("telemetry_completeness") is None or metrics.get("telemetry_completeness", 0) < 0.8:
        missing = max(metrics.get("telemetry_possible", 0) - metrics.get("telemetry_known", 0), 0)
        primary = f"Capture {missing} missing telemetry field(s)."
    elif mature < 5:
        primary = f"Collect a D7 follow-up for {5 - mature} more accepted outcome(s); do not infer the absence of an escape."
    elif not economics_ready:
        primary = "Close the cohort, the USD basis and the linked follow-ups; isolated declarations are not enough."
    else:
        failed = next((gate for gate in gates if gate["status"] == "fail"), None)
        primary = (
            f"Improve {failed['label']} to {failed['target']}."
            if failed else "Keep collecting controlled outcomes."
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
            "on-target": "OPERATIONAL TARGETS MET",
            "off-target": "OFF OPERATIONAL TARGETS",
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
            if gate["key"] == "mature" else f"{gate['label'].lower()} is N/A or incomplete"
            for gate in waiting
        ],
    }


def unavailable_project(base, error):
    touch = {str(days): unknown_touch(days, error) for days in (7, 30)}
    metrics = metrics_from_observations([], [])
    return {**base, "available": False, "error": error, "metrics": metrics,
        "touch": touch, "recent_tasks": [], "invalid_receipts": [], "invalid_task_starts": [],
        "evidence": {"status": "collecting", "reasons": [error]},
        "objective": objective_state(metrics, touch, unavailable_projects=1),
        "authority_confidence": authority_confidence(metrics), "trend_30d": outcome_trend([])}


def project_snapshot(entry, touch_provider=touch_rate.calculate, dataset_provider=None):
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
        receipts, errors = harness_report.load_receipts(receipt_dir, project_id=marker["project_id"])
    except (OSError, ValueError) as exc:
        return unavailable_project(base, str(exc))

    touch = {}
    for days in (7, 30):
        try:
            touch[str(days)] = touch_provider(path, days)
        except (OSError, RuntimeError, ValueError) as exc:
            touch[str(days)] = unknown_touch(days, f"touch sensor failed: {exc}")
    starts, start_errors = load_task_starts(path / ".007" / "tasks", project_id=marker["project_id"])
    dataset = (dataset_provider or DatasetCache())(marker["project_id"], starts, receipts)
    metrics = metrics_from_observations(receipts, starts, acquisition_errors=errors + start_errors)
    recent = [safe_task(item) for item in receipts[-20:]][::-1]
    cases = {item["task_id"]: item for item in dataset["cases"]}
    for task in recent:
        task["matched_start"] = task.get("task_id") in {item["task_id"] for item in starts}
        task["retention"] = cases.get(task.get("task_id"))
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
        "events_30d": event_trend(starts, receipts),
        "dataset": dataset,
        "source_sha256": hashlib.sha256(json.dumps({"receipts": receipts, "starts": starts},
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
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
    result["accepted_controller_observed"] = 0
    result["accepted_declared"] = result["accepted"]
    result["authority_controlled_tasks"] = 0
    result["authority_declared_tasks"] = result["authority_bound_tasks"]
    result["cost_usd_known_sum"] = round(result["cost_usd_known_sum"], 6)
    result["accepted_cost_usd_known_sum"] = round(result["accepted_cost_usd_known_sum"], 6)
    sources = Counter()
    for project in available:
        sources.update(project.get("metrics", {}).get("cost_sources", {}))
    result["cost_sources"] = dict(sources)
    combined_routes = {}
    for project in available:
        for route in project.get("metrics", {}).get("routes", []):
            row = combined_routes.setdefault(route["key"], {
                key: route[key] for key in ("key", "task_class", "provider", "model", "effort", "binding")
            } | {
                "tasks": 0, "accepted": 0, "reliable": 0, "reliable_known": 0,
                "cost_usd_known_sum": 0, "cost_usd_known_tasks": 0,
                "cost_sources": Counter(), "cost_provisional_tasks": 0,
                "wall_s_known_sum": 0, "wall_s_known_tasks": 0,
            })
            if row["binding"] != route["binding"]:
                row["binding"] = "mixed"
            row["cost_sources"].update(route.get("cost_sources", {}))
            row["cost_provisional_tasks"] += route.get("cost_provisional_tasks", 0)
            for key in (
                "tasks", "accepted", "reliable", "reliable_known",
                "cost_usd_known_sum", "cost_usd_known_tasks",
                "wall_s_known_sum", "wall_s_known_tasks",
            ):
                row[key] += route[key]
    for row in combined_routes.values():
        row["cost_usd_known_sum"] = round(row["cost_usd_known_sum"], 6)
        row.update({
            "cost_sources": dict(row["cost_sources"]),
            "cost_accounting_status": (
                None if not row["cost_usd_known_tasks"]
                else "provisional" if row["cost_provisional_tasks"] else "final"
            ),
            "reliable_rate": ratio(row["reliable"], row["reliable_known"]),
            "cost_usd_per_reliable": None,
            "wall_s_per_reliable": None,
        })
    if len(available) == 1:
        for route in available[0].get("metrics", {}).get("routes", []):
            combined_routes[route["key"]]["cost_usd_per_reliable"] = route.get("cost_usd_per_reliable")
            combined_routes[route["key"]]["wall_s_per_reliable"] = route.get("wall_s_per_reliable")
            combined_routes[route["key"]]["economics"] = route.get("economics")
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
    result["economics"] = (
        available[0].get("metrics", {}).get("economics")
        if len(available) == len(projects) == 1 and not registry_error_count else None)
    result["economics_by_project"] = [
        {"project_id": project.get("project_id"), "economics": project.get("metrics", {}).get("economics")}
        for project in available]
    events = [project.get("metrics", {}).get("latest_event_at") for project in available]
    result["latest_event_at"] = max((event for event in events if event), default=None)
    datasets = [project.get("dataset") for project in projects]
    complete = not registry_error_count and all(project.get("available") and isinstance(data, dict)
        and data.get("complete") for project, data in zip(projects, datasets))
    result["dataset"] = {"complete": complete, "scope": "last-checked-retention",
        "oldest_checked_at": min((data["oldest_checked_at"] for data in datasets
            if isinstance(data, dict) and data.get("oldest_checked_at")), default=None),
        "latest_checked_at": max((data["latest_checked_at"] for data in datasets
            if isinstance(data, dict) and data.get("latest_checked_at")), default=None),
        "counts": {key: sum(data["counts"][key] for data in datasets) for key in DATASET_STAGES}
        if complete else None}
    result["ingested_at"] = max((project.get("ingested_at") for project in projects
        if project.get("ingested_at")), default=None)
    result["cost_usd_per_reliable"] = (
        result["economics"]["cost_usd_per_reliable_declared"] if result["economics"] else None)
    result["wall_s_per_reliable"] = (
        result["economics"]["wall_s_per_reliable_declared"] if result["economics"] else None)
    result["reliable_outcomes_per_usd"] = (
        1 / result["cost_usd_per_reliable"] if result["cost_usd_per_reliable"] else None)
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
    timelines = [project.get("events_30d") for project in projects]
    if not registry_error_count and all(project.get("available") and isinstance(data, dict)
            for project, data in zip(projects, timelines)):
        events = event_trend([], [])
        events["complete"] = all(data["complete"] for data in timelines)
        events["excluded"] = sum(data["excluded"] for data in timelines)
        events["outside_window"] = sum(data["outside_window"] for data in timelines)
        by_day = {row["at"]: row for row in events["rows"]}
        for data in timelines:
            for row in data["rows"]:
                if row["at"] in by_day:
                    for key in ("started", "terminal"):
                        by_day[row["at"]][key] += row[key]
        result["events_30d"] = events
    else:
        result["events_30d"] = None
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


DATASET_STAGES = ("observational", "inputs-retained", "case-retained", "replay-ready", "qualified-comparison")


def case_signature(case):
    """Cheap identity scan, bounded to one input and output inventory; no file hashes."""
    rows, pending = [], [case.parent.parent, case.parent, case]
    while pending:
        path = pending.pop()
        try:
            info = path.lstat()
        except FileNotFoundError:
            rows.append((str(path), None))
            continue
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError("unsupported retained entry")
        # Sibling publications do not change this case; parent ownership/path identity still matter.
        identity = (*replay_capture._stamp(info), info.st_uid) if path == case or case in path.parents else (
            info.st_dev, info.st_ino, info.st_mode, info.st_uid)
        rows.append((str(path), identity))
        if len(rows) + len(pending) > replay_capture.MAX_ENTRIES * 2 + 10:
            raise OSError("retained identity scan budget exceeded")
        if path == case or case in path.parents:
            if stat.S_ISDIR(info.st_mode):
                with os.scandir(path) as entries:
                    for entry in entries:
                        if len(rows) + len(pending) >= replay_capture.MAX_ENTRIES * 2 + 10:
                            raise OSError("retained identity scan budget exceeded")
                        pending.append(path / entry.name)
    return tuple(sorted(rows))


class DatasetCache:
    def __init__(self, vault_root=None, now=lambda: datetime.now(timezone.utc)):
        self.vault = Path(vault_root) if vault_root is not None else replay_capture.default_vault()
        self.now = now
        self.values = {}
        self.lock = threading.Lock()

    def __call__(self, project_id, starts, receipts):
        groups = {}
        incomplete = False
        for kind, records in (("start", starts), ("receipt", receipts)):
            for record in records:
                identifier = record.get("task_id")
                if not isinstance(identifier, str) or not replay_capture.ID.fullmatch(identifier):
                    incomplete = True
                    continue
                groups.setdefault(identifier, []).append((kind, record.get("replay_ref")))
        rows = []
        with self.lock:
            # shortcut: Polling qualifies at most 100 cases; use an admission index for larger corpora.
            for identifier, records in sorted(groups.items())[:100]:
                ref = records[0][1]
                duplicate = any(sum(kind == label for kind, _ in records) > 1 for label in ("start", "receipt"))
                if duplicate or any(value != ref for _, value in records):
                    value = {"state": "invalid", "gaps": ["ambiguous-task-reference"]}
                    incomplete = True
                elif ref is None:
                    value = replay_capture.qualify_case(self.vault, project_id, identifier, None)
                else:
                    try:
                        replay_capture.validate_ref_shape(ref)
                        if ref["manifest"] != f"{project_id}/{identifier}/input.json":
                            raise ValueError("reference identity differs")
                        root = self.vault.absolute()
                        replay_capture._path(Path(root.anchor), str(root.relative_to(root.anchor)))
                        case = replay_capture._path(root, ref["manifest"]).parent
                        before = case_signature(case)
                        key = (project_id, identifier, ref["sha256"])
                        cached = self.values.get(key)
                        if cached and cached[0] == before:
                            value = cached[1]
                        else:
                            value = replay_capture.qualify_case(root, project_id, identifier, ref)
                            if case_signature(case) != before:
                                raise OSError("retained source changed during qualification")
                            if value["state"] != "unavailable":
                                value["checked_at"] = self.now().isoformat()
                                self.values[key] = (before, value)
                    except OSError:
                        value = {"state": "unavailable", "gaps": ["retained-read-unavailable"]}
                    except ValueError:
                        value = {"state": "invalid", "gaps": ["retained-reference-invalid"]}
                incomplete |= value["state"] == "unavailable"
                rows.append({"task_id": identifier, **copy.deepcopy(value)})
        counts = {key: 0 for key in DATASET_STAGES}
        counts.update(observational=len(groups), **{
            "inputs-retained": sum(row.get("inputs_recoverable") is True for row in rows),
            "case-retained": sum(row.get("candidate_recoverable") is True for row in rows)})
        checked = [row["checked_at"] for row in rows if row.get("checked_at")]
        return {"scope": "last-checked-retention", "complete": not incomplete and len(groups) <= 100,
                "oldest_checked_at": min(checked, default=None), "latest_checked_at": max(checked, default=None),
                "counts": counts, "cases": rows}


class ProjectCollector:
    def __init__(self, dataset_provider=None, now=lambda: datetime.now(timezone.utc)):
        self.dataset = dataset_provider or DatasetCache()
        self.now = now
        self.values = {}
        self.lock = threading.Lock()

    def __call__(self, entry, touch_provider):
        with self.lock:
            key = (entry["project_id"], entry["path"])
            prior = self.values.get(key)
            try:
                current = project_snapshot(entry, touch_provider, self.dataset)
            except (OSError, ValueError):
                current = unavailable_project(entry, "source acquisition unavailable")
            instant = self.now().isoformat()
            lost = prior and any(current["metrics"].get(field, 0) < prior["metrics"].get(field, 0)
                for field in ("tasks", "started_tasks", "matched_terminal_tasks"))
            failed = not current["available"] or current.get("invalid_receipts") or current.get("invalid_task_starts")
            if failed or lost:
                message = "source histories shrank; review possible receipt loss" if lost else current.get("error") or "incomplete source acquisition"
                current = copy.deepcopy(prior) if prior else current
                current.update(available=False, stale=prior is not None, error=message,
                    read_at=instant, ingested_at=prior.get("ingested_at") if prior else None)
                current["objective"] = {**current.get("objective", {}), "status": "not-measurable",
                    "headline": "STALE DATA" if prior else "READ UNAVAILABLE",
                    "primary_action": "Restore the source read; old values are not current progress.",
                    "gates": [{**gate, "status": "wait"} for gate in current.get("objective", {}).get("gates", [])]}
            else:
                unchanged = prior and (prior.get("source_sha256"), prior.get("dataset")) == (
                    current.get("source_sha256"), current.get("dataset"))
                current.update(stale=False, read_at=instant,
                    ingested_at=prior["ingested_at"] if unchanged else instant)
                history = copy.deepcopy(prior.get("dataset_history", [])) if prior else []
                if not unchanged:
                    data = current.get("dataset", {})
                    history.append({"at": instant, "counts": copy.deepcopy(data.get("counts"))
                        if data.get("complete") else None})
                current["dataset_history"] = history[-60:]
                self.values[key] = copy.deepcopy(current)
            return current


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


def curation_counts(rows):
    counts = replay_eval.dataset_counts(rows)
    events = [row.get("declared_followups", []) for row in rows]
    hypotheses = [event for row in rows for event in row.get("declared_hypotheses", [])]
    counts.update(
        followup_sources=sum(len(items) for items in events),
        followup_cases=sum(bool(items) for items in events),
        corrected_cases_declared=sum(any(event.get("corrective_lines", 0) > 0 or
            event.get("repair_rounds", 0) > 0 for event in items) for items in events),
        escaped_cases_declared=sum(any(event.get("escape_7d") in (True, "yes")
            for event in items) for items in events),
        hypothesis_sources=len(hypotheses),
        gate_hypotheses_declared=sum(event["kind"] == "gate" for event in hypotheses),
        routing_hypotheses_declared=sum(event["kind"] == "routing" for event in hypotheses),
    )
    return counts


class CurationCollector:
    def __init__(self, checkpoint=None, vault_root=None):
        self.checkpoint = checkpoint
        self.vault = vault_root or replay_capture.default_vault()
        self.last = {"configured": checkpoint is not None, "available": False, "stale": False,
                     "completed_at": None, "checkpoint_sha256": None, "counts": None, "by_project": {},
                     "proposals": [], "proposals_by_project": {}}

    def __call__(self):
        if self.checkpoint is None:
            return self.last
        try:
            value, _ = replay_eval.read_curation_checkpoint(self.checkpoint, vault_root=self.vault)
            rows = value["admission"]["cases"]
            projects = {row["id"]: row.get("project_id") for row in rows}
            proposals = [(projects[entry["case_id"]], {key: entry[key] for key in ("kind", "source_sha256")})
                         for entry in value["admission"].get("proposal_delta", [])]
            self.last = {"configured": True, "available": True, "stale": False,
                         "completed_at": value["completed_at"], "checkpoint_sha256": value["checkpoint_sha256"],
                         "verifier_sha256": value["verifier_sha256"], "counts": curation_counts(rows),
                         "proposals": [entry for _, entry in proposals],
                         "proposals_by_project": {key: [entry for project, entry in proposals if project == key]
                             for key in set(projects.values()) if isinstance(key, str)},
                         "by_project": {key: curation_counts([r for r in rows if r.get("project_id") == key])
                                        for key in {r.get("project_id") for r in rows} if isinstance(key, str)}}
        except (OSError, ValueError, KeyError, TypeError):
            self.last = {**self.last, "available": False, "stale": True}
        return self.last


class ObservatoryCollector:
    """Thesis D three questions for opted-in projects (config observatory.projects). Durability runs git blame per session and
    the browser polls every 2 s, so the answer is recomputed at most once per ttl."""

    def __init__(self, config=None, store=None, ttl=300, clock=time.monotonic, now=time.time):
        self.config = Path(config) if config else observatory_history.HOME / "config.json"
        self.store = Path(store) if store else observatory_history.HOME / "observatory" / "sessions.jsonl"
        self.ttl, self.clock, self.now = ttl, clock, now
        self.cached = None
        self.lock = threading.Lock()

    def __call__(self, entries):
        key = tuple((entry["project_id"], entry["path"]) for entry in entries)
        with self.lock:
            if self.cached and self.cached[1] == key and self.clock() - self.cached[0] < self.ttl:
                return self.cached[2]
            value = self.collect(entries)
            self.cached = (self.clock(), key, value)
            return value

    def collect(self, entries):
        try:
            config = observatory_history.read_config(self.config)
        except (OSError, ValueError) as exc:
            return {"projects": {}, "errors": [f"unreadable config: {exc}"[:300]]}
        allowed = observatory_history.allowed(config, entries, self.store)
        calibrations = observatory_history.calibrations(config, self.config.parent)
        projects, now = {}, self.now()
        # auto mode also follows git repositories outside the 007 registry (id "git:<root>"); they get their own list
        extra = [{"project_id": p, "path": p[4:]} for p in sorted(allowed) if p.startswith("git:")]
        for entry in [*entries, *extra]:
            if entry["project_id"] in allowed:
                try:
                    projects[entry["project_id"]] = observatory_history.view(
                        self.store, entries, entry["project_id"], allowed, calibrations, now,
                        trial_repos=observatory_history.trial_repos(config))
                except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                    projects[entry["project_id"]] = {"opted_in": True, "available": False, "error": str(exc)[:300]}
        # the effort trial's pre-registered readout over every followed project (intention to treat; validity gates first). Until
        # the readout it is blinded (counts, compliance, gates, enrollment only); per-day line survival is never asked here (one
        # blame per day and session every ttl), so after the readout the primary reads "not-computed": effort_trial_analysis.py
        rows = [{**row, "project_id": pid} for pid, view in projects.items() for row in (view.get("sessions") or [])]
        trial_cfg = config.get("observatory", {}).get("effort_trial") or {}
        trial = {"enabled": trial_cfg.get("enabled") is True, "trial_id": trial_cfg.get("trial_id", "default"),
                 "arms": trial_cfg.get("arms"), **effort_trial_analysis.analyze(rows, now)} if trial_cfg else None
        if trial and not (trial.get("readout") or {}).get("30"):
            for view in projects.values():  # amendment 3: no per-session path around the trial's blinding
                effort_trial_analysis.blind_view(view, (trial.get("blinded_until") or {}).get("30"))
        return {"projects": projects, "errors": [c["error"] for c in calibrations if "project_id" not in c], "trial": trial}


OBSERVATORY_COLLECTOR = ObservatoryCollector()


def load_lab_report(config=None):
    """The verdict of the latest `007 lab report` named by observatory.lab_report, if any: the thesis panel never claims more than this."""
    try:
        path = observatory_history.read_config(Path(config) if config else observatory_history.HOME / "config.json").get("observatory", {}).get("lab_report")
        report = json.loads(Path(path).expanduser().read_text()) if path else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return report.get("verdict") if isinstance(report, dict) and isinstance(report.get("verdict"), dict) else None


def build_snapshot(registry, touch_provider=touch_rate.calculate, activity_provider=None, project_provider=None, curation_provider=None,
                   observatory_provider=None):
    entries, registry_errors = registry_entries(registry)
    project_provider = project_provider or ProjectCollector()
    projects = [project_provider(entry, touch_provider) for entry in entries]
    activity = (activity_provider or ACTIVITY_COLLECTOR.collect)(entries)
    for project in projects:
        project["activity"] = activity.get("projects", {}).get(
            project["project_id"], local_activity.empty_summary(ACTIVITY_COLLECTOR.lookback_hours)
        )
    observatory = (observatory_provider or OBSERVATORY_COLLECTOR)(entries)
    for project in projects:
        project["observatory"] = observatory["projects"].get(project["project_id"], dict(observatory_history.NOT_OPTED_IN))
    aggregate = aggregate_projects(projects, len(registry_errors))
    aggregate["activity"] = activity.get("aggregate", local_activity.empty_summary(ACTIVITY_COLLECTOR.lookback_hours))
    curation = (curation_provider or CurationCollector())()
    for project in projects:
        in_scope = project["project_id"] in curation["by_project"]
        project["curation"] = {key: value for key, value in curation.items() if key not in ("by_project", "proposals_by_project")}
        project["curation"].update(in_scope=in_scope, counts=curation["by_project"].get(project["project_id"]),
            proposals=curation.get("proposals_by_project", {}).get(project["project_id"], []))
    return {
        "schema": "007-framework/dashboard-snapshot/v1",
        "framework_version": VERSION,
        "telemetry_fields": list(TELEMETRY_FIELDS),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "aggregate": aggregate,
        "projects": projects,
        "registry_errors": registry_errors,
        "activity_errors": activity.get("errors", []),
        "observatory_errors": observatory["errors"],
        "observatory_unregistered": {p: v for p, v in observatory["projects"].items() if p.startswith("git:")},
        "effort_trial": observatory.get("trial"),
        "measurement_boundary": {
            "cost_denominator": "observed-terminal-receipts",
            "cost_authority": "terminal-receipt",
            "label": "Operational coverage starts at 007 begin and ends at 007 record. Runs before or outside that cycle stay outside the denominator.",
        },
        "causal_evidence": load_causal_evidence(),
        "lab_report": load_lab_report(),
        "curation": {key: value for key, value in curation.items() if key not in ("by_project", "proposals_by_project")},
    }


class LiveSnapshot:
    """Repositories and durability take minutes on a large registry, sessions take milliseconds. A daemon rebuilds the heavy part;
    every read serves the latest one with fresh activity, so a 2 s poll stays a 2 s poll. None until the first build ends."""

    def __init__(self, build, entries, activity=None, pause_s=15):
        self.build, self.entries, self.activity, self.pause_s = build, entries, activity or ACTIVITY_COLLECTOR.collect, pause_s
        self.latest = None
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            try:
                self.latest = self.build()
            except Exception as exc:  # the last good evidence stays; a failed rebuild must not end the daemon
                print(f"dashboard: rebuild failed: {exc}"[:300], file=sys.stderr)
            time.sleep(self.pause_s)

    def read(self):
        latest = self.latest
        if latest is None:
            return None
        activity = self.activity(self.entries())
        fresh = activity.get("projects", {})
        return {**latest, "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "aggregate": {**latest["aggregate"], "activity": activity.get("aggregate", latest["aggregate"]["activity"])},
                "projects": [{**p, "activity": fresh.get(p["project_id"], p["activity"])} for p in latest["projects"]]}


def handler_class(registry, static_dir, touch_provider, activity_provider=None, curation_checkpoint=None, curation_vault=None, background=False):
    static_dir = Path(static_dir)
    project_provider = ProjectCollector()
    curation_provider = CurationCollector(curation_checkpoint, curation_vault)
    snapshot_lock = threading.Lock()
    build = lambda: build_snapshot(registry, touch_provider, activity_provider, project_provider, curation_provider)
    live = LiveSnapshot(build, lambda: registry_entries(registry)[0], activity_provider) if background else None
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
                if not snapshot_lock.acquire(blocking=False):
                    self.json_response(503, {"error": "snapshot collection already in progress"})
                    return
                try:
                    snapshot = live.read() if live else build()
                    if snapshot is None:
                        self.json_response(503, {"error": "first read in progress"})
                    else:
                        self.json_response(200, snapshot)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # A timed-out client cannot enqueue another collection while this one runs.
                except Exception:
                    self.json_response(500, {"error": "snapshot unavailable"})
                finally:
                    snapshot_lock.release()
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


def create_server(host, port, registry, static_dir, activity_provider=None, *, curation_checkpoint=None, curation_vault=None, background=False):
    cache = TouchCache()
    server = ThreadingHTTPServer(
        (host, port), handler_class(Path(registry), Path(static_dir), cache, activity_provider, curation_checkpoint, curation_vault, background)
    )
    server.daemon_threads = True
    return server
