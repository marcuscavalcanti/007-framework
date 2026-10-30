#!/usr/bin/env python3
"""Offline Codex hook projection. Not installed or enrolled by this command."""

from datetime import datetime, timezone
from pathlib import Path
import sys

from native_capture import (BASE_GAPS, SCHEMA, CaptureError, SafeArgumentParser,
                            append_event, decode_json, event_key, record_gap, validate_event)

MAX_INPUT_BYTES = 1024 * 1024
HOOKS = {"SessionStart": "session_start", "SessionEnd": "session_end",
         "UserPromptSubmit": "turn_start", "PreToolUse": "tool_start",
         "PostToolUse": "tool_finish", "Stop": "turn_stop", "Interrupt": "interrupt"}


def normalize_hook(payload, *, surface, host_version, observed_at):
    if not isinstance(payload, dict):
        raise CaptureError("event-invalid")
    name = payload.get("hook_event_name")
    if not isinstance(name, str):
        raise CaptureError("hook-unsupported")
    if name in ("SubagentStart", "SubagentStop") or payload.get("agent_id") is not None:
        raise CaptureError("child-attribution-unqualified")
    if name not in HOOKS:
        raise CaptureError("hook-unsupported")
    kind = HOOKS[name]
    gaps = set(BASE_GAPS)
    if host_version is None:
        gaps.add("host-version-unavailable")
    model = payload.get("model")
    if model is None:
        gaps.add("model-unavailable")
    value = {"schema": SCHEMA, "adapter": "codex-hooks", "adapter_version": "1",
             "host_version": host_version, "surface": surface, "kind": kind,
             "session_id": payload.get("session_id"),
             "turn_id": None if kind.startswith("session_") else payload.get("turn_id"),
             "tool_call_id": payload.get("tool_use_id") if kind.startswith("tool_") else None,
             "agent_id": None, "model_reported": model, "observed_at": observed_at,
             "gaps": sorted(gaps)}
    value["event_key"] = event_key(value)
    return validate_event(value)


def main(argv=None):
    args = None
    try:
        parser = SafeArgumentParser(description="Offline metadata-only hook projection; no enrollment")
        parser.add_argument("--surface", required=True, choices=("terminal", "desktop"))
        parser.add_argument("--state-dir", required=True, type=Path)
        parser.add_argument("--binding-id", required=True)
        args = parser.parse_args(argv)
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise CaptureError("input-limit")
        value = normalize_hook(decode_json(raw), surface=args.surface, host_version=None,
                               observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        append_event(args.state_dir, args.binding_id, value)
        print("{}")
        return 0
    except (CaptureError, OSError, ValueError, TypeError, RecursionError) as exc:
        code = exc.code if isinstance(exc, CaptureError) else "event-invalid"
        if args is not None:
            try:
                record_gap(args.state_dir, args.binding_id, code)
            except (CaptureError, OSError):
                pass  # No claim of delivery and no recursive error persistence.
        print(code, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
