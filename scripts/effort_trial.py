#!/usr/bin/env python3
"""Effort trial: a seeded, recorded randomization of the DEFAULT reasoning effort that local agent CLIs give NEW sessions, so
the observatory can compare durability (7/30 days) by randomly assigned effort (intention to treat, field `assigned_effort`).

Each CLI reads its default effort from its own config file when a session starts. `apply` writes only that one value (TOML: the
value on one line; JSON: one string, or a dump that reproduces every other byte), atomically (temp file + rename, mode kept,
symlinks followed), after a one-time backup, and appends each assignment to ~/.007-framework/observatory/effort_trial.jsonl.
The key each CLI actually reads (checked in the installed binaries, 2026-10-25):
- codex  ~/.codex/config.toml     top-level `model_reasoning_effort`; an active `profile` with its own effort wins: refused.
- claude ~/.claude/settings.json  `modelSettings.<claude_model>.effortLevel` (what /effort writes). Claude Code 2.1.296 uses the
                                  top-level `effortLevel` of user settings only for a legacy model list, never for current models.
- kimi   ~/.kimi-code/config.toml `[thinking] effort`: it wins over each model's `default_effort` (which Kimi refreshes from its
                                  server); arms must be in the default model's `support_efforts`.
Gemini settings expose no effort key: observed only.

Draw: arm k of an agent = arms[sha256("<seed>:<agent>:<k>") mod len(arms)]; nothing about any task enters it. k advances once
per NEW session id, when that session's first prompt reaches the UserPromptSubmit hook: the session has loaded its config by
then, so the write sets the arm of the next session. (Claude spawns SessionStart hooks before it reads the effort, a race; a
per-call counter would let hook frequency - prompts, resumes - pick the index.) A value the trial did not write is a hand edit:
recorded as "manual-override" and left alone; `restore` then ends the run keeping that value.
Usage: effort_trial.py apply [--agent A [--session-id S | --hook]] | restore [--agent A] | status
       | install [--agent A] [--dry-run] | uninstall [--agent A]      [--home DIR] [--config FILE]
"""
import argparse
from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile
import tomllib

import config_guard

AGENTS = {"codex": (".codex/config.toml", {"none", "minimal", "low", "medium", "high", "xhigh", "max"}),
          "claude": (".claude/settings.json", {"low", "medium", "high", "xhigh"}),  # "max" is session-only in Claude Code
          "kimi": (".kimi-code/config.toml", None)}                                # None: the default model's support_efforts
DEFAULTS = {"enabled": False, "agents": ["codex", "claude"], "seed": None, "claude_model": None, "repos": [], "trial_id": "default",
            "arms": {"codex": ["medium", "xhigh"], "claude": ["medium", "xhigh"]}}
STATE_EVENTS = ("assign", "restore", "manual-override")
HOOK = "effort_trial.py apply --agent "  # marks the hook entries install adds
TIMEOUT_S = 10


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def draw(seed, agent, k, arms):
    return arms[int.from_bytes(hashlib.sha256(f"{seed}:{agent}:{k}".encode()).digest()[:8], "big") % len(arms)]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _state_dir(home):
    return Path(home, ".007-framework", "observatory")


def _log(home):
    return _state_dir(home) / "effort_trial.jsonl"


def settings(home, config=None):
    """The trial settings, through config_guard: an invalid or experiment-breaking configuration raises ConfigError, and
    `apply` then changes nothing (in hook mode it stays silent and never blocks a prompt)."""
    path = Path(config) if config else Path(home, ".007-framework", "config.json")
    data = config_guard.load(path, trial_log=_log(home))
    return {**DEFAULTS, **((data.get("observatory") or {}).get("effort_trial") or {})}


def key_path(agent, s):
    return {"codex": ["model_reasoning_effort"], "claude": ["modelSettings", s.get("claude_model"), "effortLevel"],
            "kimi": ["thinking", "effort"]}[agent]


def _problem(agent, s, data):
    """Why this agent cannot be randomized now, or None."""
    if type(s.get("seed")) is not int:
        return "observatory.effort_trial.seed must be an integer"
    allowed = AGENTS[agent][1]
    if agent == "claude" and not (isinstance(s.get("claude_model"), str) and s["claude_model"]):
        return "observatory.effort_trial.claude_model must name the model whose modelSettings entry Claude Code reads"
    profile = data.get("profile")
    if agent == "codex" and isinstance(profile, str) and "model_reasoning_effort" in (data.get("profiles") or {}).get(profile, {}):
        return f"active profile {profile} sets its own model_reasoning_effort"
    if agent == "kimi":
        if (data.get("thinking") or {}).get("enabled") is False:
            return "kimi thinking is disabled ([thinking] enabled = false)"
        allowed = set((data.get("models") or {}).get(data.get("default_model"), {}).get("support_efforts") or [])
    arms = (s.get("arms") or {}).get(agent)
    if not (isinstance(arms, list) and all(isinstance(a, str) for a in arms) and len(set(arms)) == len(arms) >= 2
            and set(arms) <= allowed):
        return f"arms for {agent} must be 2+ distinct values among {sorted(allowed)}"
    return None


def _get(data, path):
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def _missing_parents(data, path):
    return sum(1 for i in range(1, len(path)) if not isinstance(_get(data, path[:i]), dict))


def _with(data, path, value, prune=0):
    """A copy of `data` with `path` set to value; None deletes it, then the `prune` innermost parents it leaves empty."""
    out = copy.deepcopy(data)
    node, parents = out, []
    for key in path[:-1]:
        parents.append((node, key))
        node = node.setdefault(key, {})
    if value is None:
        node.pop(path[-1], None)
        for parent, key in reversed(parents[len(parents) - prune:] if prune else []):
            if parent[key] == {}:
                del parent[key]
    else:
        node[path[-1]] = value
    return out


def _fmt(file):
    return "json" if str(file).endswith(".json") else "toml"


def _parse(fmt, text):
    return json.loads(text) if fmt == "json" else tomllib.loads(text)


def _same(fmt, text, want):
    try:
        return _parse(fmt, text) == want
    except ValueError:
        return False


def _dump_like(text, obj):
    """`obj` in `text`'s JSON style, or None when that style does not reproduce `text` itself byte for byte."""
    m = re.search(r"\n([ \t]+)\S", text)
    dump = lambda o: json.dumps(o, indent=m.group(1) if m else None, ensure_ascii=False) + ("\n" if text.endswith("\n") else "")
    return dump(obj) if dump(json.loads(text)) == text else None


def edit(fmt, text, path, value, prune=0):
    """`text` with the string at `path` set to `value` (None removes it), every other byte kept; None when no edit verifies.
    Each candidate edit must parse back to exactly the expected document."""
    data = _parse(fmt, text)
    try:
        want = _with(data, path, value, prune)
    except (AttributeError, TypeError):  # a parent on the path is not a table/object
        return None
    if want == data:
        return text
    key = re.escape(path[-1])
    if fmt == "json":
        candidates = [text[:m.start(1)] + json.dumps(value) + text[m.end(1):] for m in
                      re.finditer(rf'"{key}"\s*:\s*("(?:[^"\\\n]|\\.)*")', text)] if value is not None else []
        new = next((c for c in candidates if _same(fmt, c, want)), None)
        return new if new is not None else _dump_like(text, want)
    lines = list(re.finditer(rf'(?m)^[ \t]*(?:{key}|"{key}")[ \t]*=[ \t]*("[^"\n]*"|\'[^\'\n]*\')[^\n]*(?:\n|$)', text))
    if value is None:
        candidates = [text[:m.start()] + text[m.end():] for m in lines]
    else:
        line = f"{path[-1]} = {json.dumps(value)}\n"
        candidates = [text[:m.start(1)] + json.dumps(value) + text[m.end(1):] for m in lines]
        if len(path) == 1:
            candidates.append(line + text)  # a top-level key may always come first
        else:
            candidates += [text[:m.end()] + line + text[m.end():] for m in re.finditer(r"(?m)^[ \t]*\[[^\[][^\n]*\n", text)]
            header = ".".join(p if re.fullmatch(r"[A-Za-z0-9_-]+", p) else json.dumps(p) for p in path[:-1])
            candidates.append(text + ("\n" if text and not text.endswith("\n") else "") + f"\n[{header}]\n" + line)
    return next((c for c in candidates if _same(fmt, c, want)), None)


def _read(file):
    """(raw bytes, text, parsed, problem)."""
    try:
        raw = Path(file).read_bytes()
    except OSError as exc:
        return None, None, None, f"cannot read {file}: {exc.strerror}"
    try:
        text = raw.decode("utf-8")
        data = _parse(_fmt(file), text)
    except ValueError as exc:  # UnicodeDecodeError, TOMLDecodeError and JSONDecodeError are ValueErrors
        return raw, None, None, f"{file} does not parse: {exc}"
    return (raw, text, data, None) if isinstance(data, dict) else (raw, None, None, f"{file} is not a table/object")


def _write(file, text, before):
    """Atomic replace (temp file + rename in the same directory), keeping the mode; refuses if the file changed since read."""
    real = Path(os.path.realpath(file))
    if sha256(real.read_bytes()) != before:
        raise RuntimeError(f"{file} changed while being edited; the next call retries")
    handle, tmp = tempfile.mkstemp(dir=real.parent, prefix=f".{real.name}.effort-trial.")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(text.encode("utf-8"))
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, real.stat().st_mode & 0o7777)
        os.replace(tmp, real)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _backup(home, agent, file, raw):
    """One copy of the file as it was before the trial first wrote it; never overwritten (it may hold credentials: 0600)."""
    dest = _state_dir(home) / "effort_trial_backup" / f"{agent}-{Path(file).name}"
    if dest.exists():
        return
    dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with os.fdopen(os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
        out.write(raw)


def records(log):
    out = []
    if Path(log).is_file():
        for line in Path(log).read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # ponytail: a torn last line is skipped, earlier lines stay valid
    return out


def _append(home, record):
    _state_dir(home).mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(_log(home), "a") as out:
        out.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def _note(home, record):
    """Append a refusal or override unless it repeats the agent's last record (hooks call apply on every prompt)."""
    mine = [r for r in records(_log(home)) if r.get("agent") == record["agent"]]
    keys = ("event", "reason", "found", "file_sha256_before")
    if mine and all(mine[-1].get(k) == record.get(k) for k in keys):
        return record
    return _append(home, record)


def _state(home, agent):
    mine = [r for r in records(_log(home)) if r.get("agent") == agent]
    runs = [r for r in mine if r.get("event") in ("assign", "restore")]
    assigns = [r for r in mine if r.get("event") == "assign"]
    last = runs[-1] if runs else None
    return {"active": bool(last) and last["event"] == "assign", "last": last, "draws": len(assigns),
            "k": max((r["draw_index"] for r in assigns), default=-1), "tail": mine[-1] if mine else None,
            "sessions": {r.get("session_id") for r in assigns} - {None}}


def _apply(home, agent, s, session_id):
    if not s.get("enabled") or agent not in (s.get("agents") or []):
        return _restore(home, agent)
    state, file = _state(home, agent), Path(home, AGENTS[agent][0])
    base = {"at": _now(), "agent": agent}
    raw, text, data, problem = _read(file)
    problem = problem or _problem(agent, s, data)
    if problem:
        return _note(home, {**base, "event": "refused", "reason": problem, "file_sha256_before": raw and sha256(raw)})
    path = state["last"]["key"] if state["active"] else key_path(agent, s)
    current = _get(data, path)
    if state["active"] and current != state["last"]["arm"]:
        return _note(home, {**base, "event": "manual-override", "found": current, "expected": state["last"]["arm"],
                            "file_sha256_before": sha256(raw)})
    if state["active"] and (session_id is None or session_id in state["sessions"]):
        return {**base, "event": "unchanged", "arm": current}
    k = state["k"] + 1
    arm = draw(s["seed"], agent, k, s["arms"][agent])
    run = state["last"] if state["active"] else {"original": current, "created_parents": _missing_parents(data, path)}
    new = edit(_fmt(file), text, path, arm)
    if new is None:
        return _note(home, {**base, "event": "refused", "reason": f"no byte-preserving edit of {'.'.join(path)} in {file}",
                            "file_sha256_before": sha256(raw)})
    _backup(home, agent, file, raw)
    if new != text:
        _write(file, new, sha256(raw))
    # trial_id + arms let config_guard refuse a seed/arms change while this trial runs (that would mix two experiments)
    return _append(home, {**base, "event": "assign", "arm": arm, "draw_index": k, "seed": s["seed"], "session_id": session_id,
                          "trial_id": s.get("trial_id", "default"), "arms": list(s["arms"][agent]),
                          "key": path, "original": run["original"], "created_parents": run["created_parents"],
                          "file": str(file), "file_sha256_before": sha256(raw), "file_sha256_after": sha256(new.encode())})


def _restore(home, agent):
    state = _state(home, agent)
    if not state["active"]:
        return None
    last, file = state["last"], Path(home, AGENTS[agent][0])
    base = {"at": _now(), "agent": agent}
    raw, text, data, problem = _read(file)
    if problem:
        return _note(home, {**base, "event": "refused", "reason": problem, "file_sha256_before": raw and sha256(raw)})
    current = _get(data, last["key"])
    # a hand edit since the last assignment is the human's value: the run ends without touching it
    value = last["original"] if current == last["arm"] else current
    new = edit(_fmt(file), text, last["key"], value, prune=last.get("created_parents", 0))
    if new is None:
        return _note(home, {**base, "event": "refused", "reason": f"no byte-preserving edit of {'.'.join(last['key'])} in {file}",
                            "file_sha256_before": sha256(raw)})
    if new != text:
        _write(file, new, sha256(raw))
    return _append(home, {**base, "event": "restore", "arm": value, "key": last["key"], "file": str(file),
                          "file_sha256_before": sha256(raw), "file_sha256_after": sha256(new.encode())})


@contextmanager
def _locked(home):
    """Hooks of concurrent sessions serialize here."""
    _state_dir(home).mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(_state_dir(home) / "effort_trial.lock", "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def apply(home, agent=None, session_id=None, config=None):
    """Keep each agent's file on its current arm; a NEW `session_id` of `agent` draws that agent's next arm. Disabled (or an
    agent outside `agents`): restore. Returns one result per agent. A configuration config_guard refuses changes NO file: the
    refusal is recorded and the files keep their current values (switching off must be explicit, never a side effect of a typo)."""
    try:
        s = settings(home, config)
    except config_guard.ConfigError as exc:
        return [_note(home, {"at": _now(), "agent": agent, "event": "refused", "reason": str(exc)[:600]})]
    with _locked(home):
        return [_apply(home, a, s, session_id if agent else None) for a in ([agent] if agent else AGENTS)]


def restore(home, agent=None):
    with _locked(home):
        return [_restore(home, a) for a in ([agent] if agent else AGENTS)]


def status(home, config=None):
    s = settings(home, config)
    out = {"enabled": s.get("enabled") is True, "seed": s.get("seed"), "agents": s.get("agents"), "log": str(_log(home)),
           "by_agent": {}}
    for agent, (name, _) in AGENTS.items():
        state = _state(home, agent)
        raw, text, data, problem = _read(Path(home, name))
        path = state["last"]["key"] if state["last"] else key_path(agent, s)
        value = _get(data, path) if data is not None else None
        in_trial = out["enabled"] and agent in (s.get("agents") or [])
        out["by_agent"][agent] = {
            "in_trial": in_trial, "arms": (s.get("arms") or {}).get(agent), "file": str(Path(home, name)), "key": path,
            "file_value": value, "draws": state["draws"], "last_record": state["tail"],
            "holds_last_applied": value == state["last"]["arm"] if state["active"] else None,
            "problem": problem or (_problem(agent, s, data) if in_trial else None)}
    return out


def hook_command(agent, python=sys.executable, script=__file__):
    """The hook command: silent (Claude, Codex and Kimi add a hook's stdout to the prompt) and always exit 0 (exit 2 blocks
    a Claude prompt; python exits 2 when the script is missing)."""
    return f"{shlex.quote(python)} {shlex.quote(str(Path(script).resolve()))} apply --agent {agent} --hook >/dev/null 2>&1 || true"


def snippet(agent, command):
    """The exact entry install adds to the agent's file (all three run it on UserPromptSubmit)."""
    if agent == "claude":
        return {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": command, "timeout": TIMEOUT_S}]}]}}
    if agent == "codex":
        return (f'\n[[hooks.UserPromptSubmit]]\nhooks = [{{ type = "command", command = {json.dumps(command)}, '
                f"timeout = {TIMEOUT_S} }}]\n")
    return f'\n[[hooks]]\nevent = "UserPromptSubmit"\ncommand = {json.dumps(command)}\ntimeout = {TIMEOUT_S}\n'


def _ours(entry):
    return isinstance(entry, dict) and HOOK in str(entry.get("command", ""))


def _without_ours(agent, data):
    out = copy.deepcopy(data)
    if agent == "kimi":
        kept = [h for h in out.get("hooks", []) if not _ours(h)]
        if kept:
            out["hooks"] = kept
        else:
            out.pop("hooks", None)
        return out
    hooks = out.get("hooks") or {}
    groups = [{**g, "hooks": [h for h in g.get("hooks", []) if not _ours(h)]} for g in hooks.get("UserPromptSubmit", [])]
    groups = [g for g in groups if g["hooks"]]
    if groups:
        hooks["UserPromptSubmit"] = groups
    else:
        hooks.pop("UserPromptSubmit", None)
    if not hooks:
        out.pop("hooks", None)
    return out


def _drop_blocks(text):
    """`text` without the [[...]] array-of-tables blocks that hold a hook of ours (and the blank line install put before)."""
    lines, out, i = text.splitlines(keepends=True), [], 0
    while i < len(lines):
        if lines[i].lstrip().startswith("[["):
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("["):
                j += 1
            if any(HOOK in line for line in lines[i:j]):
                if out and not out[-1].strip():
                    out.pop()
                i = j
                continue
        out.append(lines[i])
        i += 1
    return "".join(out)


def _hook_edit(agent, text, data, command):
    fmt = "json" if agent == "claude" else "toml"
    entries = (data.get("hooks") if agent == "kimi" else
               [h for g in (data.get("hooks") or {}).get("UserPromptSubmit", []) for h in g.get("hooks", [])]) or []
    installed = any(_ours(h) for h in entries)
    if command is None:
        if not installed:
            return text
        want = _without_ours(agent, data)
        return _dump_like(text, want) if fmt == "json" else next((c for c in [_drop_blocks(text)] if _same(fmt, c, want)), None)
    if installed:
        return text
    want = copy.deepcopy(data)
    if agent == "kimi":
        want.setdefault("hooks", []).append({"event": "UserPromptSubmit", "command": command, "timeout": TIMEOUT_S})
    else:
        group, = snippet("claude", command)["hooks"]["UserPromptSubmit"]
        want.setdefault("hooks", {}).setdefault("UserPromptSubmit", []).append(group)
    if fmt == "json":
        return _dump_like(text, want)
    new = text + ("\n" if text and not text.endswith("\n") else "") + snippet(agent, command)
    return new if _same(fmt, new, want) else None


def _hooks(home, agents, command, event):
    """Add (command given) or remove (None) our UserPromptSubmit hook in each agent's file, idempotently, after a backup."""
    results = []
    with _locked(home):
        for agent in agents:
            file = Path(home, AGENTS[agent][0])
            raw, text, data, problem = _read(file)
            try:
                new = None if problem else _hook_edit(agent, text, data, command and command.get(agent))
            except (AttributeError, TypeError):  # hooks declared in a shape this edit does not handle
                new = None
            if new is None:
                results.append({"agent": agent, "event": "refused", "reason": problem or f"no verified {event} edit of {file}"})
                continue
            if new == text:
                results.append({"agent": agent, "event": "unchanged"})
                continue
            _backup(home, agent, file, raw)
            _write(file, new, sha256(raw))
            results.append(_append(home, {"at": _now(), "agent": agent, "event": event, "file": str(file),
                                          "file_sha256_before": sha256(raw), "file_sha256_after": sha256(new.encode())}))
    return results


def install(home, agents, command=None):
    return _hooks(home, agents, {a: command or hook_command(a) for a in agents}, "install")


def uninstall(home, agents):
    return _hooks(home, agents, None, "uninstall")


def _epoch(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def assignment(trial_records, session):
    """Intention-to-treat arm of one observed session: its agent's last assignment before the session started, or None when
    the trial did not hold that agent's key then (never started, restored, or overridden by hand). The record a session's own
    first prompt wrote is the NEXT session's arm. `effort_compliant`: observed effort == assigned (None if either is unknown)."""
    start, last, last_at = _epoch(session.get("started_at")), None, None
    for r in trial_records:
        if r.get("agent") != session.get("source") or r.get("event") not in STATE_EVENTS:
            continue
        if r["event"] == "assign" and r.get("session_id") is not None and r["session_id"] == session.get("session_id"):
            continue
        at = _epoch(r.get("at"))
        if start is not None and at is not None and at < start and (last_at is None or at >= last_at):
            last, last_at = r, at
    assigned = last["arm"] if last and last["event"] == "assign" else None
    observed = session.get("effort")
    return {"assigned_effort": assigned,
            "effort_compliant": None if assigned is None or observed in (None, "unmeasured") else observed == assigned}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Effort trial: randomize the default reasoning effort of new agent sessions")
    parser.add_argument("command", choices=("apply", "restore", "status", "install", "uninstall"))
    parser.add_argument("--agent", choices=tuple(AGENTS))
    parser.add_argument("--session-id")
    parser.add_argument("--hook", action="store_true", help="from an agent hook: session id from the hook JSON on stdin; "
                                                            "prints nothing and always exits 0")
    parser.add_argument("--dry-run", action="store_true", help="install: print the entries instead of writing them")
    parser.add_argument("--home", default=str(Path.home()))
    parser.add_argument("--config")
    args = parser.parse_args(argv)
    if args.hook:
        try:
            if not args.agent:
                raise ValueError("--hook needs --agent")
            raw = sys.stdin.read()
            session = json.loads(raw).get("session_id") if raw.strip() else None
            apply(args.home, args.agent, session if isinstance(session, str) and session else None, args.config)
        except Exception as exc:  # a hook must never break or block the agent; the failure is on record
            try:
                _note(args.home, {"at": _now(), "agent": args.agent, "event": "refused",
                                  "reason": f"hook failed: {type(exc).__name__}: {exc}"[:300]})
            except Exception:
                pass
        return 0
    agents = [args.agent] if args.agent else (settings(args.home, args.config).get("agents") or [])
    if args.command == "apply":
        if args.session_id and not args.agent:
            parser.error("--session-id needs --agent")
        result = apply(args.home, args.agent, args.session_id, args.config)
    elif args.command == "restore":
        result = restore(args.home, args.agent)
    elif args.command == "status":
        result = status(args.home, args.config)
    elif args.command == "install" and args.dry_run:
        result = {a: snippet(a, hook_command(a)) for a in agents}
    elif args.command == "install":
        result = install(args.home, agents)
    else:
        result = uninstall(args.home, agents)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
