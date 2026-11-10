"""Bounded, sanitized consumption from one fresh native CLI command."""

import hashlib
import json
import os
import re
import selectors
import sys
import time
from pathlib import Path
import harness_report

# Codex reports the served model only by exception, as an item: "model rerouted: <requested> -> <served> (<reason>)"
# (codex-rs exec event_processor_with_jsonl_output.rs, from the server's openai-model header). A match is silent.
CODEX_REROUTE = re.compile(r"model rerouted: [A-Za-z0-9_.:/-]{1,160} -> ([A-Za-z0-9_.:/-]{1,160}) \(\w+\)")


def validate_command(provider, command):
    if not command or Path(command[0]).name != provider:
        raise ValueError("native telemetry requires the declared CLI directly")
    if provider == "codex":
        valid = command[1:2] == ["exec"] and {"--json", "--ephemeral"} <= set(command)
        forbidden = {"resume", "fork"}
    else:
        valid = {"--print", "--verbose", "--no-session-persistence"} <= set(command)
        valid &= any(command[i:i + 2] == ["--output-format", "stream-json"] for i in range(len(command)))
        valid &= not any(len(arg) > 1 and arg.startswith("-") and not arg.startswith("--")
                         for arg in command[1:])
        forbidden = {"--resume", "--continue", "--fork-session", "--session-id", "--from-pr", "--teleport", "--cloud"}
    if not valid or any(arg.split("=", 1)[0] in forbidden for arg in command[1:]):
        raise ValueError("native telemetry requires a fresh non-interactive JSON session")


SEVERITY = ["native-error-transient", "native-error", "native-error-rate-limit"]
MAX_ROW_BYTES, MAX_STREAM_BYTES = 1024 * 1024, 256 * 1024 * 1024  # r48: was 32 MiB; memory stays bounded by the row limit
# r48: the only rows that may exceed MAX_ROW_BYTES (skipped, counted): agent content, declared by the row's own leading type.
CONTENT_ROW = {"codex": re.compile(rb'\{"type":"item\.(started|updated|completed)"'),
               "claude": re.compile(rb'\{"type":"(user|assistant)"')}


def native_error_class(row):
    """Review r40 D2: a rate limit must be told apart from a transient stream error; only the fixed class leaves, never the text."""
    text = json.dumps(row).lower()
    if re.search(r"rate.?limit|\b429\b|quota|usage.?limit|too many requests", text):
        return "native-error-rate-limit"
    if re.search(r"reconnect|disconnect|stream|timed? ?out|timeout|connection|overloaded|\b50[23]\b", text):
        return "native-error-transient"
    return "native-error"


class NativeTelemetry:
    def __init__(self, provider):
        if provider not in ("codex", "claude"):
            raise ValueError("unsupported native CLI")
        self.provider, self.buffer, self.size, self.skipping, self.oversized = provider, b"", 0, False, 0
        self.digest, self.session, self.problem = hashlib.sha256(), None, None
        self.started, self.completed, self.result_seen = False, 0, False
        self.usage = {key: 0 for key in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                                       "output_tokens", "reasoning_output_tokens", "total_tokens")}
        self.available = set(self.usage)
        self.cost, self.models = None, {}

    def feed(self, chunk):
        self.digest.update(chunk)
        self.size += len(chunk)
        if self.size > MAX_STREAM_BYTES:
            self.problem, self.buffer = "stream-limit", b""
        if self.problem and not self.problem.startswith("native-error"):
            return  # review r42 D2: after a native error, keep scanning so a later, more severe class is not lost
        self.buffer += chunk
        cursor = 0
        while True:
            end = self.buffer.find(b"\n", cursor)
            if self.skipping:  # the rest of an oversize content row: discard up to its newline
                if end < 0:
                    self.buffer = b""
                    return
                self.skipping, cursor = False, end + 1
                continue
            if end < 0:
                self.buffer = self.buffer[cursor:]
                if len(self.buffer) > MAX_ROW_BYTES:
                    self.oversize(self.buffer)
                    self.buffer = b""
                return
            if end - cursor > MAX_ROW_BYTES:
                self.oversize(self.buffer[cursor:cursor + 64])
                self.skipping, cursor = False, end + 1
                if self.problem and not self.problem.startswith("native-error"):
                    return
                continue
            self.row(self.buffer[cursor:end])
            cursor = end + 1

    def oversize(self, head):
        """r48: an oversize row is skipped only when its own prefix declares agent CONTENT; anything else rejects the stream."""
        if CONTENT_ROW[self.provider].match(head[:64]):
            self.oversized += 1
            self.skipping = True
        else:
            self.problem, self.buffer = "stream-limit", b""

    def row(self, line):
        if not line.strip():
            return
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("invalid-event")
            kind = row.get("type")
            if self.provider == "codex" and kind != "thread.started" and "thread_id" in row:
                thread = row["thread_id"]
                if not isinstance(thread, str) or self.session != hashlib.sha256(thread.encode()).hexdigest():
                    raise ValueError("foreign-thread-usage")
            session = row.get("thread_id") if self.provider == "codex" and kind == "thread.started" else (
                row.get("session_id") if self.provider == "claude" and kind == "system" and row.get("subtype") == "init" else None)
            if session is not None:
                if self.session is not None or not isinstance(session, str) or not session:
                    raise ValueError("ambiguous-session")
                self.session = hashlib.sha256(session.encode()).hexdigest()
            if self.provider == "codex" and kind == "turn.started":
                if not self.session or self.started:
                    raise ValueError("ambiguous-turn")
                self.started = True
            if self.provider == "codex" and kind == "turn.completed":
                if not self.started:
                    raise ValueError("duplicate-terminal")
                self.add_usage(row.get("usage"))
                self.completed += 1
                self.started = False
            if self.provider == "codex" and kind == "item.completed" and isinstance(row.get("item"), dict) and row["item"].get("type") == "error":
                rerouted = CODEX_REROUTE.fullmatch(str(row["item"].get("message", "")))
                if rerouted:  # the served model differs from the request: the runner then fails it as served-model-mismatch
                    self.models[rerouted.group(1)] = {}
            if self.provider == "codex" and kind in ("error", "turn.failed"):
                raise ValueError(native_error_class(row))
            if self.provider == "claude" and kind == "result":
                if self.result_seen or not self.session or self.session != hashlib.sha256(str(row.get("session_id")).encode()).hexdigest():
                    raise ValueError("ambiguous-terminal")
                self.add_usage(row.get("usage"))
                self.result_seen = True
                self.completed = row.get("num_turns") if type(row.get("num_turns")) is int and row["num_turns"] >= 0 else None
                cost = row.get("total_cost_usd")
                if cost is not None and not harness_report._valid_money(cost):
                    raise ValueError("invalid-cost")
                self.cost = cost
                for model, values in (row.get("modelUsage") or {}).items():
                    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", model) or not isinstance(values, dict):
                        raise ValueError("invalid-model-usage")
                    self.models[model] = {key: value for key, value in values.items()
                                          if key in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "costUSD")
                                          and harness_report._valid_money(value)}
                if row.get("subtype") != "success" or row.get("is_error") is not False:
                    raise ValueError("native-error")
        except (ValueError, TypeError, AttributeError, UnicodeDecodeError) as error:
            # keep our own fixed codes (e.g. native-error); anything else, such as a JSON parser message, stays generic
            code = str(error) if isinstance(error, ValueError) and re.fullmatch(r"[a-z]+(-[a-z]+)+", str(error)) else "invalid-native-event"
            if code.startswith("native-error") and (self.problem or "").startswith("native-error"):
                code = max(code, self.problem, key=SEVERITY.index)  # review r42 D2: the most severe class wins
            elif self.problem:
                code = self.problem
            self.problem = code

    def add_usage(self, raw):
        if not isinstance(raw, dict) or not {"input_tokens", "output_tokens"} <= raw.keys():
            raise ValueError("missing-usage")
        values = {key: raw.get(key, 0) for key in self.usage if key != "total_tokens"}
        if self.provider == "claude":
            values["cached_input_tokens"] = raw.get("cache_read_input_tokens", 0)
            values["cache_write_input_tokens"] = raw.get("cache_creation_input_tokens", 0)
            details = raw.get("output_tokens_details")
            thinking = details.get("thinking_tokens") if isinstance(details, dict) else None
            if type(thinking) is int:  # Claude reports reasoning as a part of output_tokens
                values["reasoning_output_tokens"] = thinking
        if any(type(value) is not int or not 0 <= value <= 2**53 - 1 for value in values.values()):
            raise ValueError("invalid-usage")
        if (self.provider == "codex"
                and values["cached_input_tokens"] + values["cache_write_input_tokens"] > values["input_tokens"]):
            raise ValueError("invalid-cache")
        if values["reasoning_output_tokens"] > values["output_tokens"]:
            raise ValueError("invalid-reasoning")
        total = values["input_tokens"] + values["output_tokens"]
        if self.provider == "claude":
            total += values["cached_input_tokens"] + values["cache_write_input_tokens"]
        if "total_tokens" in raw and (type(raw["total_tokens"]) is not int or raw["total_tokens"] != total):
            raise ValueError("inconsistent-total")
        provided = set(raw) | {"total_tokens"}
        if self.provider == "claude":
            provided |= {normal for native, normal in (("cache_read_input_tokens", "cached_input_tokens"),
                                                       ("cache_creation_input_tokens", "cache_write_input_tokens")) if native in raw}
            if type(thinking) is int:
                provided.add("reasoning_output_tokens")
        self.available &= provided
        for key, value in {**values, "total_tokens": total}.items():
            self.usage[key] += value

    def finish(self):
        if self.buffer and not self.problem:
            self.row(self.buffer)
        return {
            "source": self.provider + "-cli", "scope": "fresh-command",
            "status": "complete" if not self.problem and self.session and (self.result_seen or self.completed) and not self.started else "incomplete",
            "stream_sha256": self.digest.hexdigest(), "stream_bytes": self.size,
            "session_sha256": self.session, "completed_turns": self.completed,
            "usage": {key: value for key, value in self.usage.items() if key in self.available} if self.result_seen or self.completed else None,
            "estimated_cost_usd": self.cost,
            "cost_basis": "client-estimate" if self.cost is not None else "unavailable",
            "reported_model": next(iter(self.models)) if len(self.models) == 1 else "unmeasured",
            "model_usage": self.models, "problem": self.problem, "oversized_content_rows": self.oversized,
        }


def drain(process, reader, wait=False, echo=True):
    """Never wait for descendants to close the pipe after the direct child exits."""
    fd = process.stdout.fileno()
    os.set_blocking(fd, False)
    eof = False
    def take():
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            return False
        if chunk:
            reader.feed(chunk)
            if echo and sys.stdout is not None:
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
        return chunk
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)
        while not wait or process.poll() is None:
            if not selector.select(0.1 if wait else 0):
                if not wait:
                    break
                continue
            chunk = take()
            if chunk == b"":
                eof = True
                break
        if wait:
            process.wait()
            # review r40 T1: the child is gone, so all it wrote is already in the pipe; read it now without waiting on descendants.
            # review r42 T1: bounded in time, so a descendant that keeps writing cannot hold the runner (ponytail: 2 s, raise if needed)
            deadline = time.monotonic() + 2.0
            while not eof and time.monotonic() < deadline and selector.select(0):
                chunk = take()
                if chunk == b"":
                    eof = True
                elif not chunk:
                    break
    return eof


def enrich(value, telemetry):
    if not isinstance(value, dict):
        raise ValueError("receipt must be an object")
    if telemetry["status"] != "complete":
        raise ValueError("incomplete native telemetry; terminal receipt not published")
    # requested_*, served_* (declared) and native_telemetry.model_usage (observed) stay separate fields, but may not contradict:
    # Claude lists every model in modelUsage; Codex names one only when it rerouted, and its silence claims nothing.
    # Neither stream reports a provider, so served_provider stays declared.
    observed = sorted(telemetry["model_usage"])
    if observed and value.get("served_model") not in observed:
        raise ValueError(f"declared served_model is not a model the native stream reported ({', '.join(observed)}); "
                         "terminal receipt not published")
    value = dict(value)
    value.update(tokens=telemetry["usage"]["total_tokens"], wall_s=telemetry["wall_s"], usage=telemetry["usage"])
    if telemetry["estimated_cost_usd"] is not None:
        value.update(cost_usd=telemetry["estimated_cost_usd"], cost_source="rate-card-estimate", cost_status="provisional")
        value.pop("cost_unavailable_reason", None)
    return value
