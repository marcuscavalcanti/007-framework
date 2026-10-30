"""Allowlisted App Server metadata and an offline one-turn reducer; no transport."""
import copy
import json

import native_capture as native

VERSION = "0.160.1"
CONTENT = {"item/agentMessage/delta", "item/reasoning/textDelta", "item/reasoning/summaryTextDelta",
           "item/plan/delta", "item/reasoning/summaryPartAdded", "item/commandExecution/outputDelta",
           "item/fileChange/outputDelta", "item/fileChange/patchUpdated", "turn/diff/updated", "turn/plan/updated"}
METADATA = {"thread/status/changed", "account/rateLimits/updated"}
MESSAGE_ITEMS = ("agentMessage", "reasoning", "userMessage", "plan")
TOOL_ITEMS = ("fileChange", "commandExecution")  # recorded as a gap until tool events are qualified
# Schema 0.160.1 SandboxPolicy: write only the checkout, no network, /tmp and $TMPDIR excluded.
ISOLATED = {"type": "workspaceWrite", "writableRoots": [], "networkAccess": False,
            "excludeSlashTmp": True, "excludeTmpdirEnvVar": True}
WRITE_DEFAULTS = {"writableRoots": [], "networkAccess": False, "excludeSlashTmp": False, "excludeTmpdirEnvVar": False}
USAGE_KEYS = (("inputTokens", "input_tokens"), ("cachedInputTokens", "cached_input_tokens"),
              ("cacheWriteInputTokens", "cache_write_input_tokens"), ("outputTokens", "output_tokens"),
              ("reasoningOutputTokens", "reasoning_output_tokens"), ("totalTokens", "total_tokens"))


def _usage(token_usage):
    # Plan Task 12: cli_telemetry's Codex keys and rules on the thread total; anything else is unavailable (None), never zero.
    try:
        raw = token_usage["total"]
        values = {normal: raw.get(native, 0) if native == "cacheWriteInputTokens" else raw[native] for native, normal in USAGE_KEYS}
    except (KeyError, TypeError, AttributeError):
        return None
    if not all(type(v) is int and 0 <= v <= 2 ** 53 - 1 for v in values.values()):
        return None
    if (values["cached_input_tokens"] > values["input_tokens"] or values["reasoning_output_tokens"] > values["output_tokens"]
            or values["total_tokens"] != values["input_tokens"] + values["output_tokens"]):
        return None
    return values


def _require(value, code="protocol-invalid"):
    if not value:
        raise ValueError(code)


def _id(value):
    _require(isinstance(value, str) and native.NATIVE_ID.fullmatch(value))
    return value


def _turn_items(turn):
    """Snapshot items follow the Task 9 policy (review r25-r32 R7): message items pass, tool items are a gap, others refuse."""
    items = turn["items"]
    _require(type(items) is list and len(items) <= 2000, "protocol-limit")
    _require(all(isinstance(item, dict) and item.get("type") in MESSAGE_ITEMS + TOOL_ITEMS for item in items), "protocol-unsupported")
    return any(item["type"] in TOOL_ITEMS for item in items)


def project_frame(frame: bytes, *, channel: str, observed_at: str) -> dict | None:
    _require(type(frame) is bytes and len(frame) <= 1024 * 1024, "protocol-limit")
    _require(channel in ("stdout", "stderr"))
    out = {"kind": "stderr", "wire_bytes": len(frame)}
    if channel == "stderr":
        return out
    try:
        value = native.decode_json(frame)
        _require(isinstance(value, dict) and "error" not in value)
        if "id" in value:
            _require("method" not in value)
            out["request_id"] = _id(value["id"])
            result = value["result"]
            if "thread" in result:
                thread = result["thread"]
                _require(thread["cliVersion"] == VERSION and thread["ephemeral"] is True
                         and thread["turns"] == [] and thread.get("parentThreadId") is None
                         and thread.get("forkedFromId") is None and result["cwd"] == thread["cwd"])
                _require(result["approvalPolicy"] == "never" and result["approvalsReviewer"] == "user")
                sandbox = result["sandbox"]
                _require(isinstance(sandbox, dict) and set(sandbox) <= set(ISOLATED))
                sandbox = {**WRITE_DEFAULTS, **sandbox}
                _require(sandbox == ISOLATED and all(type(sandbox[k]) is bool for k in
                                                     ("networkAccess", "excludeSlashTmp", "excludeTmpdirEnvVar")))
                _require(result.get("instructionSources", []) == [])  # no instruction file loaded: clean context
                out.update(kind="bootstrap", thread_id=_id(thread["id"]), session_id=_id(thread["sessionId"]),
                           host_version=VERSION, cwd=thread["cwd"], model=_id(result["model"]),
                           provider=_id(result["modelProvider"]), effort=result["reasoningEffort"])
                _require(isinstance(out["cwd"], str) and out["cwd"].startswith("/")
                         and len(out["cwd"]) <= 4096 and not any(ord(c) < 32 for c in out["cwd"]))
                _require(out["effort"] is None or out["effort"] in ("none", "minimal", "low", "medium", "high", "xhigh"))
            else:
                turn = result["turn"]
                tools = _turn_items(turn)
                _require(turn["status"] == "inProgress")
                out.update(kind="response", turn_id=_id(turn["id"]), status=turn["status"], **({"tool_items": True} if tools else {}))
        else:
            method, params = value["method"], value["params"]
            if method == "remoteControl/status/changed":  # plan Task 10: a live remote link is external steering
                _require(params["status"] == "disabled", "protocol-unsupported")
                out["kind"] = "ignored"
            elif method in CONTENT or method in METADATA or (method in ("item/started", "item/completed")
                    and params["item"]["type"] in MESSAGE_ITEMS):
                out["kind"] = "ignored"
            elif method in ("item/started", "item/completed") and params["item"]["type"] in TOOL_ITEMS:
                out.update(kind="tool", thread_id=_id(params["threadId"]), turn_id=_id(params["turnId"]))
            elif method == "thread/tokenUsage/updated":
                out.update(kind="usage", thread_id=_id(params["threadId"]), turn_id=_id(params["turnId"]),
                           total=_usage(params.get("tokenUsage")))
            else:
                _require(method in ("turn/started", "turn/completed"), "protocol-unsupported")
                turn = params["turn"]
                tools = _turn_items(turn)
                status = turn["status"]
                _require(status in (("inProgress",) if method == "turn/started" else ("completed", "failed", "interrupted")))
                out.update(kind="start" if method == "turn/started" else "terminal",
                           thread_id=_id(params["threadId"]), turn_id=_id(turn["id"]), status=status,
                           **({"tool_items": True} if tools else {}))
        _require(len(json.dumps(out).encode()) <= native.MAX_EVENT_BYTES, "protocol-limit")
        return out
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError) as error:
        code = str(error) if str(error) in ("protocol-unsupported", "protocol-limit") else "protocol-invalid"
        raise ValueError(code) from None


def reduce_message(state: dict, message: dict) -> dict:
    result = copy.deepcopy(state)
    _require(result["phase"] in ("sent", "bound", "terminal-observed"))
    result["stream_bytes"] += message["wire_bytes"]
    result["message_count"] += 1
    _require(result["stream_bytes"] <= 32 * 1024 * 1024 and result["message_count"] <= 2000, "protocol-limit")
    kind = message["kind"]
    if kind in ("ignored", "stderr"):
        return result
    if kind == "usage":  # plan Task 12: last valid cumulative total of the bound turn; invalid/decreasing is definitive N/A
        _require(message["thread_id"] == result["producer"]["thread_id"])
        turn = result["turn_id"] or next((p["turn_id"] for p in result["pending"]), None)
        if turn is None:
            if "usage-unbound" not in result["gaps"]:
                result["gaps"].append("usage-unbound")
            return result
        _require(message["turn_id"] == turn)
        if {"usage-invalid", "usage-inconsistent"} & set(result["gaps"]):
            return result
        total, previous = message["total"], result["usage"]
        gap = ("usage-invalid" if total is None else
               "usage-inconsistent" if previous and any(total[k] < previous[k] for k in total) else None)
        if gap:
            result["gaps"].append(gap)
        result["usage"] = None if gap else total
        return result
    if kind == "tool":
        _require(message["thread_id"] == result["producer"]["thread_id"])
        _require(result["turn_id"] is None or result["turn_id"] == message["turn_id"])
        if "tool-unqualified" not in result["gaps"]:
            result["gaps"].append("tool-unqualified")
        return result
    _require(kind in ("response", "start", "terminal"))
    if message.get("tool_items") and "tool-unqualified" not in result["gaps"]:
        result["gaps"].append("tool-unqualified")
    item = {k: v for k, v in message.items() if k not in ("wire_bytes", "tool_items")}
    if kind == "response":
        _require(item["request_id"] == result["request_id"])
        _require(result["turn_id"] is None or result["turn_id"] == item["turn_id"])
        result["turn_id"] = item["turn_id"]
        if result["pending"]:
            pending = result["pending"].pop()
            _require(pending["turn_id"] == result["turn_id"])
            result["events"].append(pending)
            result["phase"] = "bound"
        return result
    _require(item["thread_id"] == result["producer"]["thread_id"])
    _require(result["turn_id"] is None or result["turn_id"] == item["turn_id"])
    existing = [e for e in result["events"] + result["pending"] if e["kind"] == kind]
    if existing:
        _require(existing == [item])
        return result
    if kind == "start":
        _require(result["phase"] == "sent")
        result["pending" if result["turn_id"] is None else "events"].append(item)
        if result["turn_id"] is not None:
            result["phase"] = "bound"
    else:
        _require(result["phase"] == "bound")
        result["events"].append(item)
        result["phase"] = "terminal-observed"
    return result


def to_native_event(message: dict, *, producer: dict, observed_at: str) -> dict:
    _id(producer["session_id"])
    _id(message["turn_id"])
    _require(producer["adapter"] == "codex-app-server" and producer["namespace"] == "codex-app-server-v2"
             and producer["surface"] == "terminal" and producer["host_version"] == VERSION)
    _require(message["kind"] in ("start", "terminal") and message["thread_id"] == producer["thread_id"])
    _require(message["status"] in (("inProgress",) if message["kind"] == "start" else ("completed", "failed", "interrupted")))
    kind = "turn_start" if message["kind"] == "start" else "interrupt" if message["status"] == "interrupted" else "turn_stop"
    event = dict(schema=native.SCHEMA, adapter=producer["adapter"], adapter_version="1",
                 host_version=producer["host_version"], surface=producer["surface"], kind=kind,
                 session_id=producer["session_id"], turn_id=message["turn_id"], tool_call_id=None,
                 agent_id=None, model_reported=None, observed_at=observed_at,
                 gaps=sorted(native.BASE_GAPS | {"model-unavailable"}))
    event["event_key"] = native.event_key(event)
    return native.validate_event(event)
