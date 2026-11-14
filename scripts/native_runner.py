#!/usr/bin/env python3
"""Run one fresh native CLI session for scripts/replay_eval.py and write its runner receipt (master plan 3.2, step 3a).

Usage: native_runner.py --cli codex|claude --receipt PATH --provider P --model M --effort E -- <native argv>
The prompt arrives on stdin and is passed through. The receipt records only what the JSON stream proves: neither CLI reports the
served effort or provider, and Codex reports the served model only when the server reroutes it (recorded, so the run fails as a
mismatch); otherwise those stay None (never copied from the request).
Stream content is never echoed or stored; only its sha256 and the normalized usage are kept, unless --stream-copy names a new
file (owner-only): then the raw stream is kept there, byte for byte, for diagnosis. It holds the session's content.
"""
import argparse
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
import subprocess
import sys

from cli_telemetry import NativeTelemetry, drain, validate_command
import harness_report

PRICE_KEYS = ("input", "cached_input", "output")


def price_table(path):
    """Frozen USD rate card (plan 3.2, decision 1b): validated before any execution."""
    try:
        raw = Path(path).read_bytes()
        value = json.loads(raw)
    except (OSError, ValueError):
        raise ValueError("invalid price table") from None
    ok = (isinstance(value, dict) and value.get("schema") == "007-framework/price-table/v1" and value.get("currency") == "USD"
          and type(value.get("per_tokens")) is int and value["per_tokens"] > 0 and isinstance(value.get("models"), dict)
          and all(isinstance(model, str) and isinstance(prices, dict) and set(prices) == set(PRICE_KEYS)
                  and all(harness_report._valid_money(prices[k]) for k in PRICE_KEYS)
                  for model, prices in value["models"].items()))
    if not ok:
        raise ValueError("invalid price table")
    return value, hashlib.sha256(raw).hexdigest()


def rate_card_cost(table, model, usage):
    """Codex usage: cached input is part of input, reasoning is part of output. Missing data is None, never zero."""
    prices = table["models"].get(model)
    if not prices or not usage or not {"input_tokens", "cached_input_tokens", "output_tokens"} <= usage.keys():
        return None
    cost = ((usage["input_tokens"] - usage["cached_input_tokens"]) * Decimal(str(prices["input"]))
            + usage["cached_input_tokens"] * Decimal(str(prices["cached_input"]))
            + usage["output_tokens"] * Decimal(str(prices["output"]))) / table["per_tokens"]
    amount = float(cost)
    return amount if harness_report._valid_money(amount) else None


# Review r40 R2: identity is bound only when EVERY option is a listed one; anything else (other spellings, profiles, provider
# tables, agents, MCP servers, plugin dirs) is refused, and the CLI's own configuration sources must be switched off.
CODEX_VALUE = {"-C", "--sandbox", "--disable", "-c", "-m", "-o"}
CODEX_BARE = {"--json", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check"}
# r47: features.network_proxy routes a profile's network through codex's managed proxy (loopback for httptest, no domain allowed);
# it changes reach, never identity. Every other feature flag stays refused.
CODEX_KEYS = {"model_reasoning_effort", "default_permissions", "web_search", "features.network_proxy"}
CODEX_PREFIXES = ("permissions.", "shell_environment_policy.")
CLAUDE_VALUE = {"--output-format", "--tools", "--allowedTools", "--permission-mode", "--settings", "--model", "--effort",
                "--setting-sources", "--mcp-config", "--max-budget-usd", "--permission-prompts", "--prompt-suggestions"}
CLAUDE_BARE = {"--print", "--verbose", "--no-session-persistence", "--restricted", "--strict-mcp-config", "--disable-slash-commands",
               "--safe-mode", "--no-chrome", "--include-partial-messages", "--tools="}
EMPTY_MCP = json.dumps({"mcpServers": {}})


def native_request(cli, command):
    """(models, efforts, providers) the native CLI is actually asked for, from listed options only (reviews r25-r32 R2, r35, r40)."""
    args = command[1:]
    if cli == "codex":
        if args[:1] != ["exec"]:
            raise ValueError("Codex must run exec")
        args, value, bare = args[1:], CODEX_VALUE, CODEX_BARE
    else:
        value, bare = CLAUDE_VALUE, CLAUDE_BARE
    pairs, i = [], 0
    while i < len(args):
        if args[i] in value and i + 1 < len(args):
            pairs.append((args[i], args[i + 1]))
            i += 2
        elif args[i] in bare:
            pairs.append((args[i], None))
            i += 1
        elif cli == "codex" and args[i] == "-" and i == len(args) - 1:  # prompt on stdin
            i += 1
        else:
            raise ValueError("unlisted option or argument refused")
    # `--disable` is repeatable natively and only switches a feature off, so repeating it cannot override a checked option.
    flags = [flag for flag, _ in pairs if flag not in ("-c", "--disable")]
    keys = [item.split("=", 1)[0] for flag, item in pairs if flag == "-c"]
    if len(flags) != len(set(flags)) or len(keys) != len(set(keys)):
        raise ValueError("repeated option refused")  # review r42 R2: native last-occurrence parsing could override a checked one
    if cli == "codex":
        if ("--ignore-user-config", None) not in pairs:
            raise ValueError("Codex must run with --ignore-user-config")
        for flag, item in pairs:
            key = (item or "").split("=", 1)[0]
            if flag == "-c" and ("=" not in item or key != key.strip() or not (key in CODEX_KEYS or key.startswith(CODEX_PREFIXES))):
                raise ValueError("unlisted configuration override refused")
        models = [item for flag, item in pairs if flag == "-m"]
        efforts = [item.split("=", 1)[1].strip('"') for flag, item in pairs if flag == "-c" and item.startswith("model_reasoning_effort=")]
        return models, efforts, ["openai"]
    if ("--restricted", None) not in pairs and ("--setting-sources", "") not in pairs:
        raise ValueError('Claude must run with --restricted or --setting-sources ""')
    if any(flag == "--mcp-config" and item != EMPTY_MCP for flag, item in pairs):
        raise ValueError("only the empty MCP configuration is allowed")
    return ([item for flag, item in pairs if flag == "--model"], [item for flag, item in pairs if flag == "--effort"], ["anthropic"])


def claude_settings(cli, command):
    """r40: Claude may get ONE --settings FILE carrying only permissions/sandbox (the deny-read sandbox); returns its sha256 or None."""
    paths = [b for a, b in zip(command[1:], command[2:]) if a == "--settings"]
    if cli != "claude" or not paths:
        return None
    try:
        # review r42 G2: an inline JSON value is the verified bytes themselves (no file swap between check and use)
        data = (paths[0].encode() if paths[0].lstrip().startswith("{") else Path(paths[0]).read_bytes()) if len(paths) == 1 else b""
        value = json.loads(data)
    except (OSError, ValueError):
        raise ValueError("settings must be exactly one JSON file") from None
    if not isinstance(value, dict) or not set(value) <= {"permissions", "sandbox"}:
        raise ValueError("settings may only carry permissions and sandbox")
    return hashlib.sha256(data).hexdigest()


class _Tee:
    """Feeds the telemetry and keeps the same bytes in the stream copy."""
    def __init__(self, telemetry, copy):
        self.telemetry, self.copy = telemetry, copy

    def feed(self, chunk):
        self.copy.write(chunk)
        self.telemetry.feed(chunk)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", choices=("codex", "claude"), required=True)
    for name in ("--receipt", "--provider", "--model", "--effort"):
        parser.add_argument(name, required=True)
    parser.add_argument("--price-table")
    parser.add_argument("--settings-sha256", help="required with a Claude --settings file: the frozen digest it must have (r41 G2)")
    parser.add_argument("--stream-copy", help="keep the raw stream in this new file (absolute path, owner-only); off by default")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    receipt = Path(args.receipt)
    table = digest = settings_digest = None
    try:
        validate_command(args.cli, command)
        if receipt.exists() or receipt.is_symlink():
            raise ValueError("runner receipt already exists")
        # Canary incident: fail before spending if the receipt cannot be written where asked (relative path or missing directory).
        if not receipt.is_absolute() or not receipt.parent.is_dir():
            raise ValueError("receipt path must be absolute with an existing directory")
        if native_request(args.cli, command) != ([args.model], [args.effort], [args.provider]):
            raise ValueError("requested provider/model/effort must be exactly the ones the native command carries")
        settings_digest = claude_settings(args.cli, command)
        if settings_digest != args.settings_sha256:
            raise ValueError("settings file digest must equal --settings-sha256")
        if args.price_table:
            if args.cli != "codex":  # ponytail: Claude usage semantics (cache read/write apart from input) come with that executor
                raise ValueError("price table supports Codex usage only")
            table, digest = price_table(args.price_table)
        if args.stream_copy and not Path(args.stream_copy).is_absolute():
            raise ValueError("stream copy path must be absolute")
        if args.stream_copy and (os.path.lexists(args.stream_copy)):
            raise ValueError("stream copy already exists")
        handle = open(receipt, "x")  # r41 G1: reserve the receipt before spending; an empty one left behind marks an attempt
        copy = None
        if args.stream_copy:  # after the receipt: a refused copy leaves the reserved receipt, which marks the attempt
            copy = os.fdopen(os.open(args.stream_copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb")
    except (ValueError, OSError) as error:
        print(f"native-runner refused: {error}", file=sys.stderr)
        return 2
    telemetry = NativeTelemetry(args.cli)
    stderr_state = {"bytes": 0}
    reader = telemetry if copy is None else _Tee(telemetry, copy)
    # Same process group: replay_eval owns cleanup. Both pipes are counted in memory.
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        streams_closed = drain(process, reader, wait=True, echo=False, stderr_state=stderr_state)
    if copy is not None:
        copy.close()
    result = telemetry.finish()
    if not streams_closed:
        result["status"] = "incomplete"
        result["problem"] = result["problem"] or "stream-closure-unconfirmed"
    # review r40 T2: keep every reported model; the requested one is "served" only if present, auxiliary models stay recorded
    models = sorted(result["model_usage"])
    served_model = None if not models else (args.model if args.model in models else ",".join(models))
    cost, source = result["estimated_cost_usd"], result["cost_basis"]
    if table is not None:
        cost = rate_card_cost(table, args.model, result["usage"])
        source = "rate-card-estimate" if cost is not None else "unavailable"
    value = {"schema": "007-framework/runner-receipt/v1", "valid": result["status"] == "complete" and process.returncode == 0,
             "requested": {"provider": args.provider, "model": args.model, "effort": args.effort},
             "served": {"provider": None, "model": served_model, "effort": None}, "served_models": models,
             "identity_source": f"{args.cli}-cli-json-stream", "source_sha256": result["stream_sha256"],
             "usage": result["usage"], "cost_usd": cost, "cost_source": source,
             "cost_status": "provisional" if cost is not None else "unavailable", "stderr_bytes": stderr_state["bytes"],
             "streams_closed": streams_closed,
             "problem": result["problem"], "settings_sha256": settings_digest}  # pilot cell 3: fixed telemetry code (e.g. native-error), never stream content
    if digest is not None:
        value["price_table_sha256"] = digest
    if result["continuations"]:
        value["continuations"] = result["continuations"]  # turns the CLI reopened for a background task (counted in usage)
    if copy is not None:
        value["stream_copy"] = Path(args.stream_copy).name  # its bytes hash to source_sha256
    with handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
