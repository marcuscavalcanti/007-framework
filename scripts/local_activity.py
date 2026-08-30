#!/usr/bin/env python3
"""Read sanitized local coding-agent usage for the 007 dashboard."""

import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRICING_WORKER = Path(__file__).with_name("headroom_pricing.py")
USAGE_KEYS = (
    "input_tokens", "cached_input_tokens", "cache_write_input_tokens",
    "cache_write_5m_input_tokens", "cache_write_1h_input_tokens",
    "output_tokens", "reasoning_output_tokens", "total_tokens",
)


def iso_datetime(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def safe_number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else 0


def empty_usage():
    return {key: 0 for key in USAGE_KEYS}


def pricing_request(session):
    usage = session.get("usage", {})
    if usage.get("usage_complete") is False:
        return None
    cached = int(safe_number(usage.get("cached_input_tokens")))
    cache_write = int(safe_number(usage.get("cache_write_input_tokens")))
    prompt = int(safe_number(usage.get("input_tokens")))
    if usage.get("input_includes_cache"):
        prompt = max(0, prompt - cached - cache_write)
    return {
        "model": session.get("model"),
        "prompt_tokens": prompt,
        "completion_tokens": int(safe_number(usage.get("output_tokens"))) + (
            0 if usage.get("output_includes_reasoning", True)
            else int(safe_number(usage.get("reasoning_output_tokens")))
        ),
        "cache_read_input_tokens": cached,
        "cache_creation_input_tokens": cache_write,
        "cache_creation_1h_input_tokens": int(safe_number(usage.get("cache_write_1h_input_tokens"))),
    }


def headroom_python():
    override = os.environ.get("HEADROOM_PYTHON")
    candidates = [override] if override else []
    executable = shutil.which("headroom")
    if executable:
        try:
            first = Path(executable).read_text(errors="ignore").splitlines()[0]
            if first.startswith("#!"):
                candidates.append(first[2:].strip())
        except (OSError, IndexError):
            pass
    try:
        if __import__("importlib.util").util.find_spec("headroom"):
            candidates.append(sys.executable)
    except (ImportError, AttributeError):
        pass
    return next((value for value in candidates if value and Path(value).is_file() and os.access(value, os.X_OK)), None)


class HeadroomPricer:
    """Batch cost estimates through Headroom's LiteLLM pricing engine."""

    def __init__(self, runner=None):
        self.python = headroom_python() if runner is None else None
        self.runner = runner or self._run
        self.cache = {}

    def _run(self, requests):
        if not self.python:
            return [{"cost_usd": None, "pricing_source": "headroom-unavailable"} for _ in requests]
        result = subprocess.run(
            [self.python, str(PRICING_WORKER)],
            input=json.dumps(requests), capture_output=True, text=True,
            timeout=20, check=False,
        )
        if result.returncode:
            return [{"cost_usd": None, "pricing_source": "headroom-error"} for _ in requests]
        value = json.loads(result.stdout)
        if not isinstance(value, list) or len(value) != len(requests):
            raise ValueError("invalid Headroom pricing response")
        return value

    def quote(self, sessions):
        keys, pending, pending_keys = [], [], []
        for session in sessions:
            request = pricing_request(session)
            key = json.dumps(request, sort_keys=True, separators=(",", ":")) if request else None
            keys.append(key)
            if key is not None and key not in self.cache and key not in pending_keys:
                pending.append(request)
                pending_keys.append(key)
        if pending:
            try:
                results = self.runner(pending)
            except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
                results = [{"cost_usd": None, "pricing_source": "headroom-error"} for _ in pending]
            for key, result in zip(pending_keys, results):
                self.cache[key] = result
        return [
            self.cache.get(key, {"cost_usd": None, "pricing_source": "usage-incomplete"})
            for key in keys
        ]


def json_rows(path, max_bytes=None, from_tail=False):
    path = Path(path)
    with path.open("rb") as handle:
        if max_bytes and from_tail and path.stat().st_size > max_bytes:
            handle.seek(-max_bytes, os.SEEK_END)
            handle.readline()
        read = 0
        for raw in handle:
            read += len(raw)
            if max_bytes and not from_tail and read > max_bytes:
                break
            try:
                value = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                yield value


def first_matching(path, predicate, max_bytes=262_144):
    for row in json_rows(path, max_bytes=max_bytes):
        if predicate(row):
            return row
    return None


def parse_codex_session(path, now=None, lookback_hours=24):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)
    meta = first_matching(path, lambda row: row.get("type") == "session_meta")
    if not meta:
        return None
    payload = meta.get("payload", {})
    session_id, cwd = payload.get("id"), payload.get("cwd")
    if not isinstance(session_id, str) or not isinstance(cwd, str):
        return None
    model = effort = None
    usage = empty_usage()
    usage["usage_complete"] = True
    usage["input_includes_cache"] = True
    updated = iso_datetime(meta.get("timestamp") or payload.get("timestamp"))
    last_task_event = None
    snapshots = []
    increments = []
    increment_missing = False
    for row in json_rows(path, max_bytes=4 * 1024 * 1024, from_tail=True):
        stamp = iso_datetime(row.get("timestamp"))
        if stamp and (updated is None or stamp > updated):
            updated = stamp
        if row.get("type") == "turn_context":
            context = row.get("payload", {})
            model = context.get("model") or model
            effort = context.get("effort") or effort
        event = row.get("payload", {}) if row.get("type") == "event_msg" else {}
        if event.get("type") in ("task_started", "task_complete"):
            last_task_event = event.get("type")
        if event.get("type") == "token_count":
            info = event.get("info", {})
            total = info.get("total_token_usage", {})
            snapshots.append((stamp, {
                "input_tokens": int(safe_number(total.get("input_tokens"))),
                "cached_input_tokens": int(safe_number(total.get("cached_input_tokens"))),
                "cache_write_input_tokens": int(safe_number(total.get("cache_write_input_tokens"))),
                "output_tokens": int(safe_number(total.get("output_tokens"))),
                "reasoning_output_tokens": int(safe_number(total.get("reasoning_output_tokens"))),
                "total_tokens": int(safe_number(total.get("total_tokens"))),
            }))
            if stamp and stamp >= cutoff:
                last = info.get("last_token_usage")
                if isinstance(last, dict):
                    increments.append({key: int(safe_number(last.get(key))) for key in USAGE_KEYS})
                else:
                    increment_missing = True
    started = iso_datetime(payload.get("timestamp") or meta.get("timestamp"))
    if increments:
        for key in USAGE_KEYS:
            usage[key] = sum(value.get(key, 0) for value in increments)
        usage["usage_complete"] = not increment_missing
    elif snapshots:
        latest = snapshots[-1][1]
        baseline = None
        if started and started < cutoff:
            before = [value for stamp, value in snapshots if stamp and stamp <= cutoff]
            if before:
                baseline = before[-1]
            else:
                inside = [value for stamp, value in snapshots if stamp and stamp > cutoff]
                if inside:
                    baseline = inside[0]
                    usage["usage_complete"] = False
        for key in USAGE_KEYS:
            usage[key] = max(0, latest.get(key, 0) - (baseline or {}).get(key, 0))
    else:
        usage["usage_complete"] = False
    return {
        "session_id": session_id,
        "source": "codex",
        "runtime_provider": payload.get("model_provider") or "openai",
        "cwd": cwd,
        "started_at": payload.get("timestamp") or meta.get("timestamp"),
        "updated_at": updated.isoformat().replace("+00:00", "Z") if updated else None,
        "status": "active" if last_task_event == "task_started" else "idle",
        "model": model or "unmeasured",
        "effort": effort or "unmeasured",
        "usage": usage,
    }


def parse_claude_session(path, now=None, max_usage_bytes=64 * 1024 * 1024, lookback_hours=24):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)
    meta = first_matching(path, lambda row: row.get("type") in ("user", "assistant"), max_bytes=1024 * 1024)
    if not meta:
        return None
    session_id, cwd = meta.get("sessionId"), meta.get("cwd")
    if not isinstance(session_id, str) or not isinstance(cwd, str):
        return None
    usage = empty_usage()
    complete = Path(path).stat().st_size <= max_usage_bytes
    usage["usage_complete"] = complete
    usage["input_includes_cache"] = False
    model = effort = None
    reported_costs = []
    updated = iso_datetime(meta.get("timestamp"))
    rows = json_rows(path) if complete else json_rows(path, max_bytes=4 * 1024 * 1024, from_tail=True)
    for row in rows:
        stamp = iso_datetime(row.get("timestamp"))
        cost = row.get("total_cost_usd")
        if row.get("type") == "result" and stamp and stamp >= cutoff and isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0:
            reported_costs.append(float(cost))
        if stamp and (updated is None or stamp > updated):
            updated = stamp
        message = row.get("message") if row.get("type") == "assistant" else None
        if not isinstance(message, dict):
            continue
        model = message.get("model") or model
        effort = row.get("effort") or effort
        if not complete or not stamp or stamp < cutoff or not isinstance(message.get("usage"), dict):
            continue
        raw = message["usage"]
        cache = raw.get("cache_creation") if isinstance(raw.get("cache_creation"), dict) else {}
        usage["input_tokens"] += int(safe_number(raw.get("input_tokens")))
        usage["cached_input_tokens"] += int(safe_number(raw.get("cache_read_input_tokens")))
        usage["cache_write_5m_input_tokens"] += int(safe_number(cache.get("ephemeral_5m_input_tokens")))
        usage["cache_write_1h_input_tokens"] += int(safe_number(cache.get("ephemeral_1h_input_tokens")))
        usage["output_tokens"] += int(safe_number(raw.get("output_tokens")))
        details = raw.get("output_tokens_details") if isinstance(raw.get("output_tokens_details"), dict) else {}
        usage["reasoning_output_tokens"] += int(safe_number(details.get("thinking_tokens")))
    usage["cache_write_input_tokens"] = usage["cache_write_5m_input_tokens"] + usage["cache_write_1h_input_tokens"]
    usage["total_tokens"] = (
        usage["input_tokens"] + usage["cached_input_tokens"]
        + usage["cache_write_input_tokens"] + usage["output_tokens"]
    ) if complete else 0
    active = bool(updated and (now - updated).total_seconds() <= 120)
    return {
        "session_id": session_id,
        "source": "claude",
        "runtime_provider": "anthropic",
        "cwd": cwd,
        "started_at": meta.get("timestamp"),
        "updated_at": updated.isoformat().replace("+00:00", "Z") if updated else None,
        "status": "active" if active else "idle",
        "model": model or "unmeasured",
        "effort": effort or "unmeasured",
        "usage": usage,
        "cost_usd_reported": sum(reported_costs) if reported_costs else None,
    }


def parse_kimi_session(path, now=None, lookback_hours=24):
    now = now or datetime.now(timezone.utc)
    cutoff_ms = int((now - timedelta(hours=lookback_hours)).timestamp() * 1000)
    state = json.loads(Path(path).read_text())
    session_id, cwd = state.get("id"), state.get("cwd")
    if not isinstance(session_id, str) or not isinstance(cwd, str):
        return None
    usage = empty_usage()
    usage.update({"usage_complete": True, "input_includes_cache": False})
    model = None
    for wire in Path(path).parent.glob("agents/*/wire.jsonl"):
        for row in json_rows(wire):
            raw = row.get("usage")
            if row.get("type") != "usage.record" or row.get("time", 0) < cutoff_ms or not isinstance(raw, dict):
                continue
            model = row.get("model") or model
            usage["input_tokens"] += int(safe_number(raw.get("inputOther")))
            usage["cached_input_tokens"] += int(safe_number(raw.get("inputCacheRead")))
            usage["cache_write_input_tokens"] += int(safe_number(raw.get("inputCacheCreation")))
            usage["output_tokens"] += int(safe_number(raw.get("output")))
    usage["total_tokens"] = sum(usage[key] for key in (
        "input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens",
    ))
    updated_ms = int(safe_number(state.get("updatedAt")))
    updated = datetime.fromtimestamp(updated_ms / 1000, timezone.utc) if updated_ms else None
    active = bool(updated and (now - updated).total_seconds() <= 120 and state.get("lastTurnReason") not in ("completed", "cancelled", "error"))
    started_ms = int(safe_number(state.get("createdAt")))
    return {
        "session_id": session_id, "source": "kimi", "runtime_provider": "moonshot",
        "cwd": cwd,
        "started_at": datetime.fromtimestamp(started_ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z") if started_ms else None,
        "updated_at": updated.isoformat().replace("+00:00", "Z") if updated else None,
        "status": "active" if active else "idle", "model": model or "unmeasured",
        "effort": "unmeasured", "usage": usage, "cost_usd_reported": None,
    }


def parse_gemini_session(path, cwd, now=None, lookback_hours=24):
    if not isinstance(cwd, str):
        return None
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)
    meta = first_matching(path, lambda row: isinstance(row.get("sessionId"), str))
    if not meta:
        return None
    usage = empty_usage()
    usage.update({"usage_complete": True, "input_includes_cache": True, "output_includes_reasoning": False})
    model = None
    updated = iso_datetime(meta.get("startTime"))
    for row in json_rows(path):
        stamp = iso_datetime(row.get("timestamp"))
        if stamp and (updated is None or stamp > updated):
            updated = stamp
        raw = row.get("tokens")
        if row.get("type") != "gemini" or not stamp or stamp < cutoff or not isinstance(raw, dict):
            continue
        model = row.get("model") or model
        usage["input_tokens"] += int(safe_number(raw.get("input"))) + int(safe_number(raw.get("tool")))
        usage["cached_input_tokens"] += int(safe_number(raw.get("cached")))
        usage["output_tokens"] += int(safe_number(raw.get("output")))
        usage["reasoning_output_tokens"] += int(safe_number(raw.get("thoughts")))
        usage["total_tokens"] += int(safe_number(raw.get("total")))
    active = bool(updated and (now - updated).total_seconds() <= 120)
    return {
        "session_id": meta["sessionId"], "source": "gemini", "runtime_provider": "google",
        "cwd": cwd, "started_at": meta.get("startTime"),
        "updated_at": updated.isoformat().replace("+00:00", "Z") if updated else None,
        "status": "active" if active else "idle", "model": model or "unmeasured",
        "effort": "unmeasured", "usage": usage, "cost_usd_reported": None,
    }


def git_identity(path):
    try:
        value = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return str(Path(value).resolve()) if value else None


def empty_summary(window_hours):
    usage = empty_usage()
    usage.pop("usage_complete", None)
    return {
        "window_hours": window_hours,
        "sessions": 0,
        "active_sessions": 0,
        "idle_sessions": 0,
        **usage,
        "tokens_total": 0,
        "cost_usd_known_sum": 0,
        "cost_usd_estimate": None,
        "priced_sessions": 0,
        "unpriced_sessions": 0,
        "pricing_coverage": None,
        "cost_usd_reported_sum": 0,
        "reported_cost_sessions": 0,
        "reported_cost_coverage": None,
        "routes": [],
        "recent_sessions": [],
    }


def summarize(sessions, window_hours):
    result = empty_summary(window_hours)
    result["sessions"] = len(sessions)
    result["active_sessions"] = sum(item["status"] == "active" for item in sessions)
    result["idle_sessions"] = len(sessions) - result["active_sessions"]
    for item in sessions:
        for key in USAGE_KEYS:
            result[key] += int(safe_number(item["usage"].get(key)))
    result["tokens_total"] = result.pop("total_tokens")
    priced = [item for item in sessions if item.get("cost_usd_estimate") is not None]
    result["priced_sessions"] = len(priced)
    result["unpriced_sessions"] = len(sessions) - len(priced)
    result["pricing_coverage"] = len(priced) / len(sessions) if sessions else None
    result["cost_usd_known_sum"] = round(sum(item["cost_usd_estimate"] for item in priced), 6)
    result["cost_usd_estimate"] = result["cost_usd_known_sum"] if sessions and len(priced) == len(sessions) else None
    reported = [item for item in sessions if item.get("cost_usd_reported") is not None]
    result["cost_usd_reported_sum"] = round(sum(item["cost_usd_reported"] for item in reported), 6)
    result["reported_cost_sessions"] = len(reported)
    result["reported_cost_coverage"] = len(reported) / len(sessions) if sessions else None
    routes = {}
    for item in sessions:
        key = (item["runtime_provider"], item["model"], item["effort"])
        row = routes.setdefault(key, {"provider": key[0], "model": key[1], "effort": key[2], "sessions": 0, "tokens": 0, "cost_usd_estimate": 0, "priced_sessions": 0})
        row["sessions"] += 1
        row["tokens"] += item["usage"].get("total_tokens", 0)
        if item.get("cost_usd_estimate") is not None:
            row["cost_usd_estimate"] += item["cost_usd_estimate"]
            row["priced_sessions"] += 1
    result["routes"] = sorted(routes.values(), key=lambda row: (-row["tokens"], row["provider"], row["model"]))
    for row in result["routes"]:
        row["cost_usd_estimate"] = round(row["cost_usd_estimate"], 6) if row["priced_sessions"] == row["sessions"] else None
    result["recent_sessions"] = sorted(sessions, key=lambda item: item.get("updated_at") or "", reverse=True)[:20]
    return result


class ActivityCollector:
    def __init__(self, codex_root=None, claude_root=None, kimi_root=None, gemini_root=None, pricer=None, lookback_hours=24):
        home = Path.home()
        self.codex_root = Path(codex_root or home / ".codex/sessions")
        self.claude_root = Path(claude_root or home / ".claude/projects")
        self.kimi_root = Path(kimi_root or home / ".kimi-code/sessions")
        self.gemini_root = Path(gemini_root or home / ".gemini")
        self.pricer = pricer or HeadroomPricer()
        self.lookback_hours = lookback_hours
        self.cache = {}
        self.identity_cache = {}

    def candidates(self, now):
        cutoff = (now - timedelta(hours=self.lookback_hours)).timestamp()
        sources = (
            ("codex", self.codex_root, "*.jsonl"),
            ("claude", self.claude_root, "*.jsonl"),
            ("kimi", self.kimi_root, "state.json"),
            ("gemini", self.gemini_root / "tmp", "session-*.jsonl"),
        )
        for source, root, pattern in sources:
            if not root.exists():
                continue
            for path in root.rglob(pattern):
                try:
                    if path.is_file() and path.stat().st_mtime >= cutoff:
                        yield source, path
                except OSError:
                    continue

    def parse(self, source, path, now):
        stat = path.stat()
        key = (stat.st_size, stat.st_mtime_ns)
        cached = self.cache.get(path)
        if cached and cached[0] == key:
            return cached[1]
        if source == "codex":
            value = parse_codex_session(path, now, self.lookback_hours)
        elif source == "claude":
            value = parse_claude_session(path, now, lookback_hours=self.lookback_hours)
        elif source == "kimi":
            value = parse_kimi_session(path, now, self.lookback_hours)
        else:
            slug = path.parents[1].name
            projects = json.loads((self.gemini_root / "projects.json").read_text()).get("projects", {})
            cwd = next((project for project, key in projects.items() if key == slug), None)
            value = parse_gemini_session(path, cwd, now, self.lookback_hours)
        self.cache[path] = (key, value)
        return value

    def identity(self, path):
        path = str(Path(path).resolve())
        if path not in self.identity_cache:
            self.identity_cache[path] = git_identity(path)
        return self.identity_cache[path]

    def project_id(self, session, entries, identities):
        cwd = Path(session["cwd"]).resolve()
        for entry in entries:
            project = Path(entry["path"]).resolve()
            if cwd == project or project in cwd.parents:
                return entry["project_id"]
        cwd_identity = self.identity(cwd)
        if cwd_identity:
            for entry in entries:
                if identities.get(entry["project_id"]) == cwd_identity:
                    return entry["project_id"]
        return None

    def collect(self, entries, now=None):
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=self.lookback_hours)
        identities = {entry["project_id"]: self.identity(entry["path"]) for entry in entries}
        sessions_by_project = {entry["project_id"]: [] for entry in entries}
        errors = []
        for source, path in self.candidates(now):
            try:
                session = self.parse(source, path, now)
                if not session:
                    continue
                started = iso_datetime(session.get("started_at"))
                updated = iso_datetime(session.get("updated_at"))
                if not any(value and value >= cutoff for value in (started, updated)):
                    continue
                project_id = self.project_id(session, entries, identities)
                if not project_id:
                    continue
                session["project_id"] = project_id
                sessions_by_project[project_id].append(session)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append({"file": path.name, "error": str(exc)})
        all_sessions = [session for sessions in sessions_by_project.values() for session in sessions]
        for session, pricing in zip(all_sessions, self.pricer.quote(all_sessions)):
            session["cost_usd_estimate"] = pricing.get("cost_usd")
            session["pricing_source"] = pricing.get("pricing_source")
            session["pricing_model"] = pricing.get("pricing_model")
            session["pricing_version"] = pricing.get("pricing_version")
        projects = {project_id: summarize(sessions, self.lookback_hours) for project_id, sessions in sessions_by_project.items()}
        return {"aggregate": summarize(all_sessions, self.lookback_hours), "projects": projects, "errors": errors}
