#!/usr/bin/env python3
"""Read sanitized local coding-agent usage for the 007 dashboard."""

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
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
GAP_S = 1800  # observatory.activity_gap_minutes default
MAX_INTERVALS = 500


def iso_datetime(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def valid_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def safe_number(value):
    return value if valid_number(value) else 0


def empty_usage():
    return {key: 0 for key in USAGE_KEYS}


def pricing_request(session):
    usage = session.get("usage", {})
    if usage.get("usage_complete") is False or usage.get("cache_write_tiers_complete") is False:
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


try:
    from compression import zstd as ZSTD  # Python 3.14+
except ImportError:
    ZSTD = None


class UnreadableLog(OSError):
    """A *.jsonl.zst log on a machine with neither compression.zstd (Python 3.14+) nor the zstd binary."""


def log_lines(path, offset=0):
    """Raw lines of a log from byte `offset`; a *.jsonl.zst log (Codex archives) is decompressed and always read from its start."""
    path = Path(path)
    if path.suffix != ".zst":
        with path.open("rb") as handle:
            handle.seek(offset)
            yield from handle
        return
    if ZSTD is not None:
        try:
            with ZSTD.open(path, "rb") as handle:
                yield from handle
        except (ZSTD.ZstdError, EOFError) as exc:
            raise OSError(f"{path.name}: {exc}") from None
        return
    binary = shutil.which("zstd")
    if not binary:
        raise UnreadableLog(f"{path.name}: no zstd decoder")
    process = subprocess.Popen([binary, "-dcq", "--", str(path)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        yield from process.stdout
    finally:
        process.stdout.close()
        code = process.wait()
    if code:
        raise OSError(f"{path.name}: zstd exited with {code}")


def json_rows(path, max_bytes=None):
    read = 0
    for raw in log_lines(path):
        read += len(raw)
        if max_bytes and read > max_bytes:
            break
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            yield value


def read_log(path, parser, offset=0, digest=None):
    """Feeds `parser` every row of `path` after byte `offset` and returns the offset after the last whole row: a torn last row (still
    being written) waits for the next read. Consumed JSON is decoded once per generation, with memory bounded by metadata."""
    for raw in log_lines(path, offset):
        try:
            row = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            if not raw.endswith(b"\n"):
                break
            row = None
        offset += len(raw)
        if digest is not None:
            digest.update(raw)
        if isinstance(row, dict):
            parser.feed(row)
    return offset


def unchanged_prefix(path, length, digest):
    """Verify all consumed bytes before reusing a changed plain log's incremental parser."""
    observed = hashlib.sha256()
    with path.open("rb") as handle:
        while length:
            chunk = handle.read(min(length, 1024 * 1024))
            if not chunk:
                return False
            observed.update(chunk)
            length -= len(chunk)
    return observed.digest() == digest.digest()


def active_intervals(stamps, gap_s=GAP_S, cap=MAX_INTERVALS):
    """Sorted [start, end] epoch-second pairs from row timestamps (never content): consecutive stamps at most gap_s apart share an
    interval; past `cap`, the closest neighbours merge (only the cap - 1 widest pauses split), so the store stays small."""
    points = sorted({int(stamp) for stamp in stamps})
    splits = [i for i in range(1, len(points)) if points[i] - points[i - 1] > gap_s]
    if len(splits) >= cap:
        splits = sorted(sorted(splits, key=lambda i: points[i - 1] - points[i])[:cap - 1])
    bounds = [0, *splits, len(points)]
    return [[points[a], points[b - 1]] for a, b in zip(bounds, bounds[1:])] if points else []


def first_matching(path, predicate, max_bytes=262_144):
    for row in json_rows(path, max_bytes=max_bytes):
        if predicate(row):
            return row
    return None


def add_segment(segments, stamp, model, effort):
    """Appends [start epoch, model, effort] when the route changes; a value a turn leaves out keeps the previous one."""
    last = segments[-1] if segments else [None, None, None]
    model = model if isinstance(model, str) and model else last[1]
    effort = effort if isinstance(effort, str) and effort else last[2]
    if (model, effort) != (last[1], last[2]):
        segments.append([int(stamp.timestamp()) if stamp else None, model, effort])


def labels(segments):
    """The session's model and effort: its one value, "mixed" when its segments differ, "unmeasured" without any."""
    def label(values):
        found = {value for value in values if value}
        return found.pop() if len(found) == 1 else "mixed" if found else "unmeasured"
    return label(s[1] for s in segments), label(s[2] for s in segments)


def counts(raw, keys):
    """The token counters `keys` of one usage record (an absent one is 0), or None when one is present but not a non-negative
    finite number: an invalid counter is unknown, never zero."""
    if any(key in raw and not valid_number(raw[key]) for key in keys):
        return None
    return tuple(int(raw.get(key, 0)) for key in keys)


def codex_counts(raw):
    if not isinstance(raw, dict) or not any(key in raw for key in ("input_tokens", "output_tokens", "total_tokens")):
        return None
    return counts(raw, USAGE_KEYS)


def codex_usage_complete(raw):
    return (codex_counts(raw) is not None
            and all(key in raw for key in ("input_tokens", "output_tokens", "total_tokens"))
            and raw["total_tokens"] == raw["input_tokens"] + raw["output_tokens"])


def iso(stamp):
    return stamp.isoformat().replace("+00:00", "Z") if stamp else None


class CodexLog:
    """Metadata of one Codex rollout, fed row by row (never retained content). A thread another thread spawned
    (subagent, guardian review) reports its root session's id, as a Claude subagent log does, with its own id as log_id."""

    def __init__(self, path=None):
        self.meta, self.updated, self.last_task, self.previous = None, None, None, None
        self.stamps, self.segments, self.tokens = set(), [], []

    def feed(self, row):
        stamp = iso_datetime(row.get("timestamp"))
        if stamp:
            self.stamps.add(int(stamp.timestamp()))
            self.updated = max(self.updated or stamp, stamp)
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        kind = row.get("type")
        if kind == "session_meta" and self.meta is None:
            self.meta = codex_identity(row, payload) or {}
        elif kind == "turn_context":
            add_segment(self.segments, stamp, payload.get("model"), payload.get("effort"))
        elif kind == "event_msg" and payload.get("type") in ("task_started", "task_complete"):
            self.last_task = payload["type"]
        elif kind == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info")
            if not isinstance(info, dict):
                self.tokens.append((stamp, None, None, False, False))
                return
            total = info.get("total_token_usage") if isinstance(info.get("total_token_usage"), dict) else None
            last = info.get("last_token_usage")
            absent = last is None or (isinstance(last, dict) and not any(
                key in last for key in ("input_tokens", "output_tokens", "total_tokens")))
            total_ok, last_ok = codex_usage_complete(total), absent or codex_usage_complete(last)
            if total and total == self.previous:
                if not total_ok or not last_ok:
                    self.tokens.append((stamp, None, None, False, False))
                return
            self.previous = total
            self.tokens.append((stamp, codex_counts(total), codex_counts(last),
                                total_ok, last_ok))

    def result(self, now=None, lookback_hours=24, gap_s=GAP_S):
        if not self.meta:
            return None
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=lookback_hours)
        usage = {**empty_usage(), "usage_complete": True, "input_includes_cache": True}
        inside = [(total, last, total_ok, last_ok) for stamp, total, last, total_ok, last_ok in self.tokens
                  if stamp and stamp >= cutoff]
        increments = [last for total, last, _, _ in inside if last is not None]
        snapshots = [(stamp, total, total_ok) for stamp, total, _, total_ok, _ in self.tokens if total is not None]
        started = iso_datetime(self.meta["started_at"])
        if increments:
            usage.update({key: sum(value[i] for value in increments) for i, key in enumerate(USAGE_KEYS)})
            usage["usage_complete"] = all(total is not None and last is not None for total, last, _, _ in inside)
            previous = (0,) * len(USAGE_KEYS) if started and started >= cutoff else None
            for stamp, total, last, total_ok, _ in self.tokens:
                if stamp and stamp >= cutoff and last is not None:
                    usage["usage_complete"] &= previous is not None and total is not None and all(
                        last[i] == total[i] - previous[i] for i, key in enumerate(USAGE_KEYS)
                        if key in ("input_tokens", "output_tokens", "total_tokens"))
                previous = total if total_ok else None
        elif snapshots:
            baseline = None
            if started and started < cutoff:
                before = [(value, complete) for stamp, value, complete in snapshots if stamp and stamp <= cutoff]
                after = [(value, complete) for stamp, value, complete in snapshots if stamp and stamp > cutoff]
                selected = before[-1] if before else after[0] if after else None
                baseline = selected[0] if selected else None
                usage["usage_complete"] = (bool(before) or not after) and (selected is None or selected[1])
            usage.update({key: max(0, snapshots[-1][1][i] - (baseline[i] if baseline else 0)) for i, key in enumerate(USAGE_KEYS)})
        else:
            usage["usage_complete"] = False
        usage["usage_complete"] &= all(total_ok and last_ok for _, _, total_ok, last_ok in inside)
        usage["usage_complete"] &= usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
        model, effort = labels(self.segments)
        return {
            **{key: self.meta[key] for key in ("session_id", "log_id", "cwd", "started_at", "subagent")},
            "source": "codex",
            "runtime_provider": self.meta["provider"] or "openai",
            "updated_at": iso(self.updated or started),
            "status": "active" if self.last_task == "task_started" else "idle",
            "model": model,
            "effort": effort,
            "effort_segments": list(self.segments),
            "usage": usage,
            "active_intervals": active_intervals(self.stamps, gap_s),
        }


def codex_identity(row, payload):
    """Session fields of a rollout's first session_meta. A child carries `parent_thread_id` (also under
    source.subagent.thread_spawn) and Codex's `session_id` names its root; reviews are thread_source "guardian_review"."""
    thread, cwd = payload.get("id"), payload.get("cwd")
    if not isinstance(thread, str) or not isinstance(cwd, str):
        return None
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    sub = source.get("subagent") if isinstance(source.get("subagent"), dict) else {}
    spawn = sub.get("thread_spawn") if isinstance(sub.get("thread_spawn"), dict) else {}
    parent = payload.get("parent_thread_id") or spawn.get("parent_thread_id")
    child = bool(parent or sub or "subagent" in source or payload.get("thread_source") in ("subagent", "guardian_review"))
    root = payload.get("session_id") if child and isinstance(payload.get("session_id"), str) else None
    root = root if root and root != thread else parent if child and isinstance(parent, str) else thread
    return {"session_id": root, "log_id": thread, "cwd": cwd, "subagent": child,
            "started_at": payload.get("timestamp") or row.get("timestamp"), "provider": payload.get("model_provider")}


def parse_codex_session(path, now=None, lookback_hours=24, gap_s=GAP_S):
    log = CodexLog()
    read_log(path, log)
    return log.result(now, lookback_hours, gap_s)


CLAUDE_USAGE = ("input_tokens", "cache_read_input_tokens", "ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens",
                "cache_creation_input_tokens", "output_tokens", "thinking_tokens")


class ClaudeLog:
    """Metadata of one Claude Code log, fed row by row. Every cwd the rows carry is kept in order (`cwds`): a session opened
    outside a repository and moved into one maps to that repository."""

    def __init__(self, path):
        # a subagent log carries the parent's sessionId; it must never speak for the session's model, effort or start
        self.in_subagents, self.log_id = "subagents" in Path(path).parts, Path(path).stem
        self.meta, self.updated = None, None
        self.stamps, self.segments, self.cwds, self.messages, self.costs = set(), [], [], {}, []

    def feed(self, row):
        stamp = iso_datetime(row.get("timestamp"))
        if stamp:
            self.stamps.add(int(stamp.timestamp()))
            self.updated = max(self.updated or stamp, stamp)
        kind = row.get("type")
        if self.meta is None and kind in ("user", "assistant"):
            self.meta = {"session_id": row.get("sessionId"), "cwd": row.get("cwd"), "started_at": row.get("timestamp"),
                         "sidechain": row.get("isSidechain") is True}
        if isinstance(row.get("cwd"), str) and row["cwd"] not in self.cwds:
            self.cwds.append(row["cwd"])
        cost = row.get("total_cost_usd")
        if kind == "result" and stamp:
            valid = type(cost) in (int, float) and math.isfinite(cost) and cost >= 0
            self.costs.append((stamp, float(cost) if valid else None))
        message = row.get("message") if kind == "assistant" else None
        if not isinstance(message, dict):
            return
        model = message.get("model")
        add_segment(self.segments, stamp, None if isinstance(model, str) and model.startswith("<") else model, row.get("effort"))
        if stamp:
            raw = message.get("usage")
            key = message.get("id") if isinstance(message.get("id"), str) and message["id"] else object()
            if not isinstance(raw, dict):
                if not (isinstance(model, str) and model.startswith("<")):
                    self.messages.setdefault(key, (stamp, None, False))
                return
            cache = raw.get("cache_creation") if isinstance(raw.get("cache_creation"), dict) else {}
            details = raw.get("output_tokens_details") if isinstance(raw.get("output_tokens_details"), dict) else {}
            # Claude Code writes one row per content block of a response, each with the response's usage (the last one final):
            # one count per message id
            required = all(valid_number(raw.get(name)) for name in ("input_tokens", "output_tokens"))
            tier_sum = sum(safe_number(cache.get(name)) for name in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"))
            aggregate = raw.get("cache_creation_input_tokens", tier_sum)
            coherent = valid_number(aggregate) and aggregate >= tier_sum
            value = counts({**details, **cache, **raw, "cache_creation_input_tokens": aggregate}, CLAUDE_USAGE) if required and coherent else None
            self.messages[key] = (stamp, value, value is not None and aggregate == tier_sum)

    def result(self, now=None, lookback_hours=24, gap_s=GAP_S):
        meta = self.meta
        if not meta or not isinstance(meta["session_id"], str) or not isinstance(meta["cwd"], str):
            return None
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=lookback_hours)
        observed = [(value, tiers) for stamp, value, tiers in self.messages.values() if stamp >= cutoff]
        window = [value for value, _ in observed]
        usage = {**empty_usage(), "usage_complete": None not in window, "input_includes_cache": False}
        usage["cache_write_tiers_complete"] = all(tiers for _, tiers in observed)
        sums = [sum(column) for column in zip(*(value for value in window if value is not None))] or [0] * 7
        (usage["input_tokens"], usage["cached_input_tokens"], usage["cache_write_5m_input_tokens"],
         usage["cache_write_1h_input_tokens"], usage["cache_write_input_tokens"], usage["output_tokens"],
         usage["reasoning_output_tokens"]) = sums
        usage["total_tokens"] = usage["input_tokens"] + usage["cached_input_tokens"] + usage["cache_write_input_tokens"] + usage["output_tokens"]
        started = iso_datetime(meta["started_at"])
        baseline = 0 if started and started >= cutoff else None
        latest, inside, valid = None, False, True
        for stamp, cost in self.costs:
            if cost is None:
                valid = False
                continue
            valid &= latest is None or cost >= latest
            latest = cost
            if stamp <= cutoff:
                baseline = latest
            else:
                inside = True
        model, effort = labels(self.segments)
        return {
            "session_id": meta["session_id"],
            "log_id": self.log_id,
            "source": "claude",
            "runtime_provider": "anthropic",
            "cwd": meta["cwd"],
            "cwds": list(self.cwds),
            "started_at": meta["started_at"],
            "updated_at": iso(self.updated),
            "status": "active" if self.updated and (now - self.updated).total_seconds() <= 120 else "idle",
            "model": model,
            "effort": effort,
            "effort_segments": list(self.segments),
            "usage": usage,
            "cost_usd_reported": latest - baseline if valid and inside and baseline is not None else None,
            "active_intervals": active_intervals(self.stamps, gap_s),
            "subagent": self.in_subagents or meta["sidechain"],
        }


def parse_claude_session(path, now=None, lookback_hours=24, gap_s=GAP_S):
    log = ClaudeLog(path)
    read_log(path, log)
    return log.result(now, lookback_hours, gap_s)


LOGS = {"codex": CodexLog, "claude": ClaudeLog}


def parse_kimi_session(path, now=None, lookback_hours=24, gap_s=GAP_S):
    now = now or datetime.now(timezone.utc)
    cutoff_ms = int((now - timedelta(hours=lookback_hours)).timestamp() * 1000)
    state = json.loads(Path(path).read_text())
    session_id, cwd = state.get("id"), state.get("cwd")
    if not isinstance(session_id, str) or not isinstance(cwd, str):
        return None
    usage = empty_usage()
    usage.update({"usage_complete": True, "input_includes_cache": False})
    model = None
    stamps = []
    for wire in Path(path).parent.glob("agents/*/wire.jsonl"):
        for row in json_rows(wire):
            if safe_number(row.get("time")):
                stamps.append(row["time"] / 1000)
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
        "active_intervals": active_intervals(stamps, gap_s),
    }


def parse_gemini_session(path, cwd, now=None, lookback_hours=24, gap_s=GAP_S):
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
    stamps = [updated.timestamp()] if updated else []
    for row in json_rows(path):
        stamp = iso_datetime(row.get("timestamp"))
        if stamp:
            stamps.append(stamp.timestamp())
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
        "active_intervals": active_intervals(stamps, gap_s),
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
        "usage_incomplete_sessions": 0,
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
    result["usage_incomplete_sessions"] = sum(item["usage"].get("usage_complete") is not True for item in sessions)
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
    def __init__(self, codex_root=None, claude_root=None, kimi_root=None, gemini_root=None, pricer=None, lookback_hours=24,
                 activity_gap_minutes=GAP_S / 60):
        home = Path.home()
        self.codex_root = Path(codex_root or home / ".codex/sessions")
        self.claude_root = Path(claude_root or home / ".claude/projects")
        self.kimi_root = Path(kimi_root or home / ".kimi-code/sessions")
        self.gemini_root = Path(gemini_root or home / ".gemini")
        self.pricer = pricer or HeadroomPricer()
        self.lookback_hours = lookback_hours
        self.gap_s = float(activity_gap_minutes) * 60
        self.cursors = {}  # path -> (stat stamp, consumed offset, parser, consumed-byte hash)
        self._lock = threading.RLock()
        self.unreadable = set()  # *.jsonl.zst logs no decoder could read (reported, never skipped silently)
        self.identity_cache = {}

    def candidates(self, now):
        cutoff = (now - timedelta(hours=self.lookback_hours)).timestamp()
        sources = (
            ("codex", self.codex_root, ("*.jsonl", "*.jsonl.zst")),
            ("claude", self.claude_root, ("*.jsonl",)),
            ("kimi", self.kimi_root, ("state.json",)),
            ("gemini", self.gemini_root / "tmp", ("session-*.jsonl",)),
        )
        for source, root, patterns in sources:
            if not root.exists():
                continue
            for path in (path for pattern in patterns for path in root.rglob(pattern)):
                try:
                    if path.is_file() and path.stat().st_mtime >= cutoff:
                        yield source, path
                except OSError:
                    continue

    def parse(self, source, path, now):
        with self._lock:
            return self._parse(source, path, now)

    def _parse(self, source, path, now):
        """The session of one log as of `now`. Only what the rows say is kept between calls (a cursor per Codex/Claude log); status
        and the lookback window are recomputed every call, since they move with the clock even when the file does not."""
        if source not in LOGS:
            # ponytail: Kimi and Gemini logs are re-read on every call; give them a cursor like LOGS if a large one shows up
            if source == "kimi":
                return parse_kimi_session(path, now, self.lookback_hours, self.gap_s)
            slug = path.parents[1].name
            projects = json.loads((self.gemini_root / "projects.json").read_text()).get("projects", {})
            cwd = next((project for project, key in projects.items() if key == slug), None)
            return parse_gemini_session(path, cwd, now, self.lookback_hours, self.gap_s)
        stat = path.stat()
        known, offset, log, digest = self.cursors.pop(path, (None, 0, None, None))
        stamp = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        # Changed plain files must retain every consumed byte before their parser can read on. Hashing the prefix costs I/O
        # but avoids reparsing unchanged JSON. Unchanged files and archives do not perform this prefix check.
        packed = path.suffix == ".zst"
        stale = known != stamp if packed else known is None or known[:2] != stamp[:2] or offset > stat.st_size
        if log is not None and not packed and not stale and known != stamp:
            stale = not unchanged_prefix(path, offset, digest)
        if log is None or stale:
            offset, log, digest = 0, LOGS[source](path), None if packed else hashlib.sha256()
        try:
            if not packed or offset == 0:
                offset = read_log(path, log, offset, digest)
        except UnreadableLog:
            self.unreadable.add(path)
            return None
        self.unreadable.discard(path)
        self.cursors[path] = (stamp, offset, log, digest)
        return log.result(now, self.lookback_hours, self.gap_s)

    def identity(self, path):
        path = str(Path(path).resolve())
        if path not in self.identity_cache:
            self.identity_cache[path] = git_identity(path)
        return self.identity_cache[path]

    def project_id(self, session, entries, identities):
        for cwd in session.get("cwds") or [session["cwd"]]:  # the first cwd of the session that maps to a project
            cwd = Path(cwd).resolve()
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
        with self._lock:
            return self._collect(entries, now)

    def _collect(self, entries, now=None):
        if not entries:
            self.cursors.clear()
            self.unreadable.clear()
            return {"aggregate": summarize([], self.lookback_hours), "projects": {}, "errors": []}
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=self.lookback_hours)
        identities = {entry["project_id"]: self.identity(entry["path"]) for entry in entries}
        sessions_by_project = {entry["project_id"]: [] for entry in entries}
        errors, seen = [], set()
        for source, path in self.candidates(now):
            seen.add(path)
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
        self.cursors = {path: cursor for path, cursor in self.cursors.items() if path in seen}
        unread = len(self.unreadable & seen)
        if unread:
            errors.append({"file": "*.jsonl.zst", "error": f"{unread} compressed log(s) not read: needs Python 3.14+ "
                                                          "(compression.zstd) or the zstd binary"})
        all_sessions = [session for sessions in sessions_by_project.values() for session in sessions]
        for session, pricing in zip(all_sessions, self.pricer.quote(all_sessions)):
            session["cost_usd_estimate"] = pricing.get("cost_usd")
            session["pricing_source"] = pricing.get("pricing_source")
            session["pricing_model"] = pricing.get("pricing_model")
            session["pricing_version"] = pricing.get("pricing_version")
        projects = {project_id: summarize(sessions, self.lookback_hours) for project_id, sessions in sessions_by_project.items()}
        return {"aggregate": summarize(all_sessions, self.lookback_hours), "projects": projects, "errors": errors}
