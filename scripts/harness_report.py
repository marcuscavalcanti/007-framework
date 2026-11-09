#!/usr/bin/env python3
"""Summarize 007 Framework receipts using the Python standard library."""

import argparse
import json
import math
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
import re


COST_BASES = {"api-equivalent", "subscription-allocated", "billed", "local-compute"}
SOURCE_BASES = {"rate-card-estimate": "api-equivalent",
                "subscription-allocated": "subscription-allocated", "local-compute": "local-compute"}
COST_COMPONENTS = ("executor", "review", "retries", "verification", "infrastructure", "preparation")


def _instant(value):
    try:
        value = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        return value.astimezone(timezone.utc) if isinstance(value, datetime) and value.tzinfo else None
    except ValueError:
        return None


def _identity(value):
    project = value.get("project_id")
    if project is not None and (not isinstance(project, str) or not project):
        raise ValueError("invalid project identity")
    task = value.get("task_id")
    return (project, task) if isinstance(task, str) and task else None


def receipt_cost_basis(value):
    source = value.get("cost_source")
    if not isinstance(source, str):
        return None
    basis = value.get("cost_basis", SOURCE_BASES.get(source))
    if not isinstance(basis, str) or basis not in COST_BASES:
        return None
    source_basis = SOURCE_BASES.get(source)
    return basis if source_basis is None or source_basis == basis else None


def _valid_money(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _money_sum(values):
    with localcontext() as context:
        context.prec = 700  # Covers the finite float exponent range without decimal subtotal loss.
        total = sum((Decimal(str(value)) for value in values), Decimal(0))
    if not math.isfinite(float(total)):
        raise ValueError("declared USD total is not finite")
    return total


def _money_total(values):
    values = tuple(values)
    if any(not _valid_money(value) for value in values):
        return None
    try:
        return float(_money_sum(values))
    except ValueError:
        return None


def route_identity_unavailable(row):
    return any(not isinstance(value, str) or value.strip().lower() in ("", "unmeasured", "unknown", "n/d")
               for value in (row.get("served_" + field) or row.get(field) for field in ("provider", "model", "effort")))


def validate_cost_components(row):
    if "cost_components_usd" not in row:
        return None
    components = row["cost_components_usd"]
    if not isinstance(components, dict) or set(components) - set(COST_COMPONENTS):
        raise ValueError("invalid declared USD components")
    if any(value is not None and not _valid_money(value) for value in components.values()):
        raise ValueError("invalid declared USD component amount")
    return components


def scope_project(records, project_id):
    """Bind legacy file location to its validated marker, without authenticating or rewriting it."""
    if not isinstance(project_id, str) or not project_id or any(
            not isinstance(row, dict) or row.get("project_id", project_id) != project_id for row in records):
        raise ValueError("record project differs from validated marker")
    return [{"project_id": project_id, **row} for row in records]


def summarize_economics(receipts, *, starts, followups, cost_basis, as_of, acquisition_errors=()):
    """Repeatable accounting of supplied declarations, not producer attestation."""
    instant = _instant(as_of)
    if instant is None or (cost_basis is not None and (not isinstance(cost_basis, str) or cost_basis not in COST_BASES)):
        raise ValueError("accounting requires an aware cutoff and a supported USD basis")
    receipts, starts, followups = list(receipts), list(starts or []), list(followups or [])
    if any(not isinstance(row, dict) for row in receipts + starts + followups):
        raise ValueError("accounting records must be objects")
    reasons = set()
    if acquisition_errors:
        reasons.add("incomplete source acquisition")
    rows, future = [], 0
    for row in receipts:
        validate_cost_components(row)
        cost = row.get("cost_usd")
        if cost is not None and not _valid_money(cost):
            raise ValueError("invalid declared USD cost")
        completed = _instant(row.get("completed_at"))
        if completed is None:
            reasons.add("completion time unavailable")
        elif completed > instant:
            future += 1
            continue
        rows.append(row)
        if row.get("first_pass") == "yes" and type(row.get("repair_rounds")) is int and row["repair_rounds"] > 0:
            reasons.add("first-pass claim contradicts repair rounds")
    observed_starts = []
    for row in starts:
        started = _instant(row.get("started_at"))
        if started is None:
            reasons.add("start time unavailable")
        if started is None or started <= instant:
            observed_starts.append(row)
    ids, start_ids = [_identity(row) for row in rows], [_identity(row) for row in observed_starts]
    if None in ids or None in start_ids:
        reasons.add("task identity unavailable")
    duplicates = len(ids) - len(set(ids)) + len(start_ids) - len(set(start_ids))
    if duplicates:
        reasons.add("duplicate task identities")
    projects = {key[0] for key in ids + start_ids if key is not None and key[0] is not None}
    if len(projects) > 1:
        reasons.add("mixed project cohort")
    if any(key is not None and key[0] is None for key in ids + start_ids):
        reasons.add("project identity unavailable")
    latest_starts = {}
    for key, row in zip(start_ids, observed_starts):
        started = _instant(row.get("started_at"))
        if started is not None:
            latest_starts[key] = max(latest_starts.get(key, started), started)
    if any(_instant(row.get("completed_at")) is not None
           and latest_starts.get(key, _instant(row["completed_at"])) > _instant(row["completed_at"])
           for key, row in zip(ids, rows)):
        reasons.add("completion precedes matching start")
    open_tasks = len(set(start_ids) - set(ids) - {None})
    unbound = len(set(ids) - set(start_ids) - {None})
    if open_tasks:
        reasons.add("open task starts")
    if unbound:
        reasons.add("terminal receipts without matching starts")
    by_id = {} if duplicates else {key: row for key, row in zip(ids, rows) if key is not None}
    children = set()
    child_costs = {}
    ambiguous_tree = False
    for key, row in by_id.items():
        if "parent_task_id" not in row:
            continue
        if not isinstance(row["parent_task_id"], str) or not row["parent_task_id"]:
            raise ValueError("invalid parent task identity")
        parent_key = (row.get("project_id"), row["parent_task_id"])
        parent = by_id.get(parent_key)
        seen, cursor = {key}, parent_key
        while cursor in by_id:
            if cursor in seen:
                ambiguous_tree = True
                break
            seen.add(cursor)
            ancestor = by_id[cursor]
            if "parent_task_id" not in ancestor:
                break
            if not isinstance(ancestor["parent_task_id"], str) or not ancestor["parent_task_id"]:
                raise ValueError("invalid parent task identity")
            cursor = (ancestor.get("project_id"), ancestor["parent_task_id"])
        if (parent is None or parent.get("cost_includes_children") is not True
                or receipt_cost_basis(parent) != receipt_cost_basis(row)):
            ambiguous_tree = True
        else:
            children.add(key)
            if row.get("cost_usd") is not None:
                child_costs.setdefault(parent_key, []).append(row["cost_usd"])
    for key, values in child_costs.items():
        try:
            if by_id[key].get("cost_usd") is not None and _money_sum(values) > Decimal(str(by_id[key]["cost_usd"])):
                ambiguous_tree = True
        except OverflowError as exc:
            raise ValueError("declared child USD total is not finite") from exc
    if ambiguous_tree:
        reasons.add("ambiguous parent/child cost scope")
    roots = [row for row in rows if _identity(row) not in children]
    groups = {}
    for row in roots:
        basis = receipt_cost_basis(row)
        if has_accounted_cost(row) and basis:
            groups.setdefault(basis, []).append(row["cost_usd"])
    try:
        sums = {key: float(_money_sum(values)) for key, values in sorted(groups.items())}
    except (ValueError, OverflowError) as exc:
        raise ValueError("declared USD total is not finite") from exc
    selected = cost_basis or (next(iter(sums)) if len(sums) == 1 else None)
    if selected is None and len(sums) > 1:
        reasons.add("mixed USD accounting bases")
    known = sum(has_accounted_cost(row) and receipt_cost_basis(row) == selected
                for row in roots) if selected else 0
    total = sums.get(selected, 0) if selected or len(sums) <= 1 else None
    if duplicates or ambiguous_tree:
        total = None
    coverage = known / len(roots) if roots else None
    if roots and known != len(roots):
        reasons.add("incomplete cost basis coverage")
    accepted = [row for row in roots if row.get("status") == "accepted"]
    first_pass = sum(row.get("first_pass") == "yes" for row in accepted)
    events = {}
    for event in followups:
        key = _identity(event)
        events.setdefault(key, []).append(event)
    linked, reliable, escapes = 0, 0, 0
    for row in accepted:
        observations = events.get(_identity(row), [])
        if len(observations) != 1:
            continue
        event = observations[0]
        completed, used = _instant(row.get("completed_at")), _instant(event.get("used_at"))
        begin, end = _instant(event.get("observed_from")), _instant(event.get("observed_through"))
        digest = row.get("candidate_sha256")
        if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or event.get("candidate_sha256") != digest
                or not isinstance(event.get("source_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", event["source_sha256"])
                or None in (completed, used, begin, end) or not completed <= used
                or not begin <= used <= end <= instant or end - used < timedelta(days=7)
                or not (type(event.get("escape_7d")) is bool or event.get("escape_7d") in ("yes", "no"))):
            continue
        linked += 1
        escaped = event["escape_7d"] in (True, "yes")
        escapes += int(escaped)
        reliable += int(row.get("first_pass") == "yes" and not escaped)
    complete = not reasons
    can_price = complete and coverage == 1 and total is not None
    component_known = dict.fromkeys(COST_COMPONENTS, 0)
    reconciled, scope_reasons = 0, set()
    for row in roots:
        if "cost_components_usd" not in row:
            continue
        components = row["cost_components_usd"]
        if not has_accounted_cost(row) or receipt_cost_basis(row) != selected:
            continue
        for name in COST_COMPONENTS:
            component_known[name] += int(components.get(name) is not None)
        if all(components.get(name) is not None for name in COST_COMPONENTS):
            if _money_sum(components.values()) == Decimal(str(row["cost_usd"])):
                reconciled += 1
            else:
                scope_reasons.add("USD components do not reconcile with declared total")
    scope_complete = bool(roots) and can_price and reconciled == len(roots)
    if roots and reconciled != len(roots):
        scope_reasons.add("incomplete overhead cost scope")
    wall_values = [row["wall_s"] for row in roots if _valid_money(row.get("wall_s"))]
    try:
        wall_total = round(math.fsum(wall_values), 6)
    except OverflowError as exc:
        raise ValueError("declared wall time is not finite") from exc
    wall_coverage = len(wall_values) / len(roots) if roots else None
    return {
        "currency": "USD", "cost_basis": selected, "as_of": instant.isoformat(),
        "project_id": next(iter(projects)) if len(projects) == 1 else None,
        "evidence_scope": "supplied-declarations", "cohort_complete": complete,
        "cohort_tasks": len(roots), "component_receipts": len(rows), "outside_cutoff": future,
        "open_tasks": open_tasks, "unbound_receipts": unbound,
        "duplicate_identities": duplicates, "cost_usd_by_basis": sums,
        "cost_usd_known_sum": total, "cost_usd_known_tasks": known,
        "cost_scope_complete": scope_complete,
        "cost_component_known_tasks": component_known, "cost_scope_reasons": sorted(scope_reasons),
        "cost_usd_per_declared_accepted_with_overhead": total / len(accepted)
            if scope_complete and accepted else None,
        "cost_usd_per_reliable_with_overhead_declared": total / reliable
            if scope_complete and reliable and linked == len(accepted) else None,
        "cost_coverage": coverage, "accepted_declared": len(accepted),
        "first_pass_declared": first_pass, "reliable_declared": reliable,
        "quality_known_declared": linked + sum(row.get("status") == "blocked" for row in roots),
        "linked_followups": linked, "followup_pending": len(accepted) - linked,
        "followup_coverage": linked / len(accepted) if accepted else None,
        "escapes_declared": escapes,
        "wall_s_known_sum": wall_total, "wall_coverage": wall_coverage,
        "wall_s_per_reliable_declared": round(wall_total / reliable, 3)
            if complete and wall_coverage == 1 and not children and reliable and linked == len(accepted) else None,
        "cost_usd_per_declared_accepted": total / len(accepted) if can_price and accepted else None,
        "cost_usd_per_first_pass_declared": total / first_pass if can_price and first_pass else None,
        "cost_usd_per_reliable_declared": total / reliable
            if can_price and reliable and linked == len(accepted) else None,
        "reasons": sorted(reasons),
    }


def has_accounted_cost(receipt):
    value = receipt.get("cost_usd")
    return (
        _valid_money(value)
        and isinstance(receipt.get("cost_source"), str)
        and bool(receipt["cost_source"])
        and receipt.get("cost_status") in ("final", "provisional")
    )


def load_receipts(directory, *, project_id=None):
    receipts = []
    errors = []
    directory = Path(directory).expanduser()
    files = []
    def denied(error):
        errors.append({"file": str(error.filename or directory), "error": "receipt directory unavailable"})
    for root, _, names in os.walk(directory, onerror=denied):
        files.extend(Path(root) / name for name in names if name.endswith(".receipt.json"))
    for path in sorted(files):
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict) or "status" not in value:
                raise ValueError("receipt must be an object with status")
            receipts.extend(scope_project([value], project_id) if project_id is not None else [value])
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"file": str(path), "error": str(exc)})
    return receipts, errors


def summarize(receipts, errors, *, starts=None, followups=None, as_of=None):
    statuses = Counter(str(r.get("status", "unknown")) for r in receipts)
    first_pass = Counter(str(r.get("first_pass", "unmeasured")) for r in receipts)
    numeric_tokens = [r["tokens"] for r in receipts if isinstance(r.get("tokens"), int)]
    tokens = sum(numeric_tokens) if len(numeric_tokens) == len(receipts) and receipts else "unmeasured"
    repairs = [r["repair_rounds"] for r in receipts if isinstance(r.get("repair_rounds"), int)]
    costs = [r["cost_usd"] for r in receipts if has_accounted_cost(r)]
    accepted = [r for r in receipts if r.get("status") == "accepted"]
    accepted_costs = [r["cost_usd"] for r in accepted if has_accounted_cost(r)]
    economics = summarize_economics(receipts, starts=starts, followups=followups,
        cost_basis=None, as_of=as_of or datetime.now(timezone.utc), acquisition_errors=errors)
    return {
        "economics": economics,
        "legacy_cost_metric_scope": "accepted-only-mean",
        "tasks": len(receipts),
        "accepted": statuses["accepted"],
        "blocked": statuses["blocked"],
        "no_op": statuses["no-op"],
        "first_pass_yes": first_pass["yes"],
        "repair_rounds_known": sum(repairs),
        "tokens": tokens,
        "tokens_known_sum": sum(numeric_tokens),
        "tokens_known_tasks": len(numeric_tokens),
        "tokens_missing_tasks": len(receipts) - len(numeric_tokens),
        "cost_usd_known_sum": round(math.fsum(costs), 6),
        "cost_usd_known_tasks": len(costs),
        "cost_unaccounted_tasks": len(receipts) - len(costs),
        "cost_coverage": len(costs) / len(receipts) if receipts else None,
        "cost_usd_per_accepted": (
            round(math.fsum(accepted_costs) / len(accepted), 6)
            if accepted and len(accepted_costs) == len(accepted) else None
        ),
        "cost_status": (
            None if not costs
            else "provisional" if any(r.get("cost_status") == "provisional" for r in receipts if has_accounted_cost(r))
            else "final"
        ),
        "invalid_receipts": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="Summarize 007 Framework task receipts")
    parser.add_argument("--receipt-dir", required=True)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args()
    starts = []
    task_dir = Path(args.receipt_dir).expanduser().parent / "tasks"
    receipts, errors = load_receipts(args.receipt_dir)
    for path in sorted(task_dir.glob("*.task.json")):
        try:
            starts.append(json.loads(path.read_text()))
        except (OSError, ValueError) as exc:
            errors.append({"file": str(path), "error": str(exc)})
    try:
        marker_path = task_dir.parent / "project.json"
        if marker_path.exists():
            from framework_cli import validate_marker
            project_id = validate_marker(json.loads(marker_path.read_text()))["project_id"]
            starts = scope_project(starts, project_id)
            receipts = scope_project(receipts, project_id)
        summary = summarize(receipts, errors, starts=starts,
                            followups=[r["followup_7d"] for r in receipts if isinstance(r.get("followup_7d"), dict)])
    except (OSError, ValueError) as exc:
        print(json.dumps({"invalid_receipts": errors, "economics_error": str(exc)}))
        return 1
    if args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"tasks={summary['tasks']} accepted={summary['accepted']} blocked={summary['blocked']} no_op={summary['no_op']}")
        print(f"first_pass_yes={summary['first_pass_yes']} repair_rounds_known={summary['repair_rounds_known']} tokens={summary['tokens']}")
        print(f"cost_usd={summary['cost_usd_known_sum']} coverage={summary['cost_coverage']} status={summary['cost_status']}")
        print(f"invalid_receipts={len(summary['invalid_receipts'])}")
    return 1 if errors_are_fatal(summary) else 0


def errors_are_fatal(summary):
    return bool(summary["invalid_receipts"])


if __name__ == "__main__":
    sys.exit(main())
