"""Bounded, sanitized consumption from one fresh native CLI command."""

import codecs
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
# Large content still carries identity. Only string bodies may be compacted;
# json.loads validates the remaining envelope, including metadata after content.
CONTENT_TYPES = {"codex": ("item.started", "item.updated", "item.completed"),
                 "claude": ("user", "assistant")}


class _LargeContentRow:
    """Bounded JSON string compaction, used only after a row exceeds the limit.

    This lexer validates UTF-8 and string escapes even in discarded text.
    The stdlib JSON parser remains responsible for the object grammar. Long
    strings become null, so identity fields cannot silently become absent.
    A large key or an envelope exceeding the retained limit fails closed.
    """
    special = re.compile(rb'["\\\x00-\x1f]')
    escape_pattern = re.compile(rb'\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})')

    def __init__(self):
        self.data = bytearray()
        self.string_start = None
        self.discarding = False
        self.escape = b""
        self.decoder = codecs.getincrementaldecoder("utf-8")()

    def append(self, data):
        if self.discarding:
            return
        if self.string_start is not None and len(self.data) - self.string_start + len(data) > MAX_ROW_BYTES // 16:
            del self.data[self.string_start:]
            self.data.extend(b"null")
            self.discarding = True
            return
        if self.string_start is None and len(self.data) + len(data) > MAX_ROW_BYTES:
            raise ValueError("stream-limit")
        self.data.extend(data)

    def feed(self, part):
        # Fixed-size slices avoid allocating a decoded copy of a caller's large chunk.
        for offset in range(0, len(part), 65536):
            fragment = part[offset:offset + 65536]
            self.decoder.decode(fragment)
            cursor = 0
            while cursor < len(fragment):
                if self.escape:
                    needed = (6 if self.escape[1:2] == b"u" else 2) - len(self.escape)
                    take = min(needed, len(fragment) - cursor)
                    self.escape += fragment[cursor:cursor + take]
                    cursor += take
                    if len(self.escape) == 2 and self.escape[1:2] == b"u":
                        continue
                    if len(self.escape) < (6 if self.escape[1:2] == b"u" else 2):
                        continue
                    if not self.escape_pattern.fullmatch(self.escape):
                        raise ValueError("invalid-native-event")
                    self.append(self.escape)
                    self.escape = b""
                    continue
                match = self.special.search(fragment, cursor)
                end = match.start() if match else len(fragment)
                self.append(fragment[cursor:end])
                cursor = end
                if match is None:
                    break
                byte = fragment[cursor:cursor + 1]
                cursor += 1
                if self.string_start is None:
                    self.append(byte)
                    if byte == b'"':
                        self.string_start = len(self.data) - 1
                elif byte == b'"':
                    if not self.discarding:
                        self.append(byte)
                    self.string_start, self.discarding = None, False
                    if len(self.data) > MAX_ROW_BYTES:
                        raise ValueError("stream-limit")
                elif byte == b"\\":
                    self.escape = byte
                else:
                    raise ValueError("invalid-native-event")

    def finish(self):
        self.decoder.decode(b"", final=True)
        if self.string_start is not None or self.escape:
            raise ValueError("invalid-native-event")
        return bytes(self.data)


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
        self.provider, self.buffer, self.size, self.oversized = provider, b"", 0, 0
        self.large_row = None
        self.digest, self.session, self.problem = hashlib.sha256(), None, None
        self.started, self.completed, self.result_seen = False, 0, False
        self.usage = {key: 0 for key in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                                       "output_tokens", "reasoning_output_tokens", "total_tokens")}
        self.available = set(self.usage)
        self.cost, self.models = None, {}

    def feed(self, chunk):
        self.digest.update(chunk)
        accepted = max(0, MAX_STREAM_BYTES - self.size)
        self.size += len(chunk)
        if self.problem and not self.problem.startswith("native-error"):
            if self.size > MAX_STREAM_BYTES:
                self.problem = "stream-limit"
            return
        try:
            for offset in range(0, min(len(chunk), accepted), 65536):
                parts = chunk[offset:min(offset + 65536, accepted)].split(b"\n")
                for index, part in enumerate(parts):
                    if self.large_row is None:
                        self.buffer += part
                        if len(self.buffer) > MAX_ROW_BYTES:
                            self.large_row = _LargeContentRow()
                            self.large_row.feed(self.buffer)
                            self.buffer = b""
                    else:
                        self.large_row.feed(part)
                    if index < len(parts) - 1:
                        self.end_row()
                    if self.problem and not self.problem.startswith("native-error"):
                        break
                if self.problem and not self.problem.startswith("native-error"):
                    break
        except (ValueError, UnicodeDecodeError, RecursionError) as error:
            self.problem = "stream-limit" if str(error) == "stream-limit" else "invalid-native-event"
        if self.size > MAX_STREAM_BYTES:
            self.problem = "stream-limit"
        if self.problem and not self.problem.startswith("native-error"):
            self.buffer, self.large_row = b"", None

    def end_row(self):
        line = self.buffer
        if self.large_row is not None:
            line = self.large_row.finish()
            value = json.loads(line)
            if not isinstance(value, dict) or value.get("type") not in CONTENT_TYPES[self.provider]:
                raise ValueError("stream-limit")
            self.oversized += 1
        self.buffer, self.large_row = b"", None
        self.row(line)

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
                message = row["item"].get("message")
                if not isinstance(message, str):
                    raise ValueError("invalid-model-observation")
                rerouted = CODEX_REROUTE.fullmatch(message)
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
        except (ValueError, TypeError, AttributeError, UnicodeDecodeError, RecursionError) as error:
            # keep our own fixed codes (e.g. native-error); anything else, such as a JSON parser message, stays generic
            code = str(error) if isinstance(error, ValueError) and re.fullmatch(r"[a-z]+(-[a-z]+)+", str(error)) else "invalid-native-event"
            if code.startswith("native-error") and (self.problem or "").startswith("native-error"):
                code = max(code, self.problem, key=SEVERITY.index)  # review r42 D2: the most severe class wins
            elif self.problem and not self.problem.startswith("native-error"):
                code = self.problem
            self.problem = code

    def add_usage(self, raw):
        if not isinstance(raw, dict) or not {"input_tokens", "output_tokens"} <= raw.keys():
            raise ValueError("missing-usage")
        values = {key: raw.get(key, 0) for key in self.usage if key != "total_tokens"}
        if self.provider == "claude":
            details = raw.get("output_tokens_details", {})
            if not isinstance(details, dict):
                raise ValueError("invalid-usage")
            for source, native, normal in ((raw, "cache_read_input_tokens", "cached_input_tokens"),
                                           (raw, "cache_creation_input_tokens", "cache_write_input_tokens"),
                                           (details, "thinking_tokens", "reasoning_output_tokens")):
                if native in source:
                    value = source[native]
                    if (normal in raw and (type(raw[normal]) is not int or raw[normal] != value)):
                        raise ValueError("conflicting-usage")
                    values[normal] = value
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
            if "thinking_tokens" in details:
                provided.add("reasoning_output_tokens")
        self.available &= provided
        for key, value in {**values, "total_tokens": total}.items():
            self.usage[key] += value

    def finish(self):
        if (self.buffer or self.large_row is not None) and (not self.problem or self.problem.startswith("native-error")):
            try:
                self.end_row()
            except (ValueError, UnicodeDecodeError, RecursionError) as error:
                self.problem = "stream-limit" if str(error) == "stream-limit" else "invalid-native-event"
            self.buffer, self.large_row = b"", None
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


def drain(process, reader, wait=False, echo=True, stderr_state=None):
    """Never wait for descendants to close the pipe after the direct child exits."""
    stdout_fd = process.stdout.fileno()
    descriptors = [stdout_fd]
    if stderr_state is not None:
        descriptors.append(process.stderr.fileno())
    remaining = set(descriptors)
    for fd in descriptors:
        os.set_blocking(fd, False)

    def take(fd):
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            return None
        if chunk:
            if fd == stdout_fd:
                reader.feed(chunk)
                if echo and sys.stdout is not None:
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
            else:
                stderr_state["bytes"] += len(chunk)
        return chunk

    with selectors.DefaultSelector() as selector:
        for fd in descriptors:
            selector.register(fd, selectors.EVENT_READ)

        def read_ready(timeout):
            progressed = False
            for key, _ in selector.select(timeout):
                chunk = take(key.fd)
                progressed |= chunk is not None
                if chunk == b"":
                    remaining.remove(key.fd)
                    selector.unregister(key.fd)
            return progressed

        while remaining and (not wait or process.poll() is None):
            if not read_ready(0.1 if wait else 0) and not wait:
                break
        if wait:
            process.wait()
            # review r40 T1: the child is gone, so all it wrote is already in the pipe; read it now without waiting on descendants.
            # review r42 T1: bounded in time, so a descendant that keeps writing cannot hold the runner (ponytail: 2 s, raise if needed)
            deadline = time.monotonic() + 2.0
            while remaining and time.monotonic() < deadline and read_ready(0):
                pass
    return not remaining


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
