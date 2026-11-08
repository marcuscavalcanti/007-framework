"""Adversarial reviewer route by host session (AGENTS.md revision 2026-10-21b; master plan 3.3).

Selection only: it never launches a review and never authorizes a call. The reviewer always comes from a different model family
than the host. Fail-closed: a missing primary CLI or an unrecognized host yields no route (failed validation, stop); no fallback.
"""
import json
import os
import shutil

ROUTES = {  # host session -> reviewer
    "claude": {"provider": "openai", "cli": "codex", "model": "gpt-6-astra", "effort": "xhigh", "budget_control": None},
    "codex": {"provider": "anthropic", "cli": "claude", "model": "claude-opus-5-5", "effort": "xhigh",
              "budget_control": "cli-max-budget-usd"},
}
HOST_FAMILY = {"claude": "anthropic", "codex": "openai"}
# r33: the Codex reviewer gets only the context on stdin — a read-only sandbox still reads the whole disk, so no shell, web or extensions
# (the same features Marcus's other reviewer sessions disable on this binary).
CODEX_REVIEW_DISABLED = ("shell_tool", "unified_exec", "apps", "plugins", "hooks", "memories", "multi_agent", "browser_use",
                         "browser_use_external", "computer_use", "image_generation", "view_image", "in_app_browser", "tool_suggest",
                         "goals", "remote_plugin", "sleep_tool", "code_mode_host")  # code_mode_host: on by default since 0.165


def host_session(env=None):
    env = os.environ if env is None else env
    hosts = [host for host, marker in (("claude", "CLAUDECODE"), ("codex", "CODEX_THREAD_ID")) if env.get(marker)]
    if len(hosts) > 1:
        raise ValueError("host-ambiguous")  # nested sessions inherit both markers: the caller must declare the host
    return hosts[0] if hosts else None


def select_reviewer(host=None, *, which=shutil.which, env=None):
    if host is None:
        host = host_session(env)
    elif host not in ROUTES:
        raise ValueError("host-unknown")
    route = ROUTES.get(host)
    if route is None or not which(route["cli"]):
        return None  # fail-closed: the caller records a failed validation and stops; no other model or effort
    if route["provider"] == HOST_FAMILY[host]:
        raise ValueError("reviewer-same-family")
    return {**route, "host": host, "reason": "primary", "executable": which(route["cli"])}


def review_argv(route, *, max_budget_usd=None):
    """Fresh, read-only, non-interactive argv; the prompt goes on stdin. Context binding and authorization stay with the caller."""
    exe, model, effort = route["executable"], route["model"], route["effort"]
    if route["cli"] == "codex":  # ponytail: no USD cap exists in this CLI; the grant must accept that or refuse the call
        return [exe, "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
                "--sandbox", "read-only", *(arg for feature in CODEX_REVIEW_DISABLED for arg in ("--disable", feature)),
                "-c", 'web_search="disabled"', "-m", model, "-c", f'model_reasoning_effort="{effort}"', "-"]
    if route["cli"] == "claude":  # flags of the route verified in review r24, new model/effort, cap mandatory
        if type(max_budget_usd) not in (int, float) or not max_budget_usd > 0:
            raise ValueError("review-budget-required")
        return [exe, "--print", "--verbose", "--permission-mode", "plan", "--permission-prompts", "none", "--no-session-persistence",
                "--model", model, "--effort", effort, "--tools=", "--max-budget-usd", str(max_budget_usd), "--safe-mode",
                "--disable-slash-commands", "--no-chrome", "--setting-sources", "", "--strict-mcp-config",
                "--mcp-config", json.dumps({"mcpServers": {}}), "--prompt-suggestions", "false",
                "--output-format", "stream-json", "--include-partial-messages"]
    raise ValueError("review-route-unknown")


def identity_level(route, rows):
    """AGENTS.md reviewer identity level from a review's parsed JSON stream rows: "verified", "pinned-no-reroute" or "failed".
    The served identity is never filled from the request; "pinned-no-reroute" qualifies a release only as such."""
    import cli_telemetry  # the one place that knows the Codex reroute item
    if not rows or any(not isinstance(row, dict) for row in rows):
        return "failed"
    kinds = [row.get("type") for row in rows]
    if any(kind in ("error", "turn.failed") for kind in kinds):
        return "failed"
    if route.get("cli") == "codex":
        if (kinds.count("turn.started") != 1 or kinds.count("turn.completed") != 1
                or kinds[-1] != "turn.completed" or kinds.index("turn.started") > kinds.index("turn.completed")):
            return "failed"
        rerouted = any(row.get("type") == "item.completed" and isinstance(row.get("item"), dict) and row["item"].get("type") == "error"
                       and cli_telemetry.CODEX_REROUTE.fullmatch(str(row["item"].get("message", ""))) for row in rows if isinstance(row, dict))
        return "failed" if rerouted else "pinned-no-reroute"
    if route.get("cli") == "claude":
        if kinds.count("result") != 1 or kinds[-1] != "result":
            return "failed"
        result = rows[-1]
        if not isinstance(result.get("modelUsage"), dict) or set(result["modelUsage"]) != {route.get("model")}:
            return "failed"
        models = set(result["modelUsage"])
        for row in rows:
            usage = row.get("modelUsage")
            if usage is not None and not isinstance(usage, dict):
                return "failed"
            models.update(usage or {})
            for name in (row.get("model"), (row.get("message") or {}).get("model") if isinstance(row.get("message"), dict) else None):
                if name is not None:
                    if not isinstance(name, str) or not name:
                        return "failed"
                    models.add(name)
        ok = result is not None and result.get("subtype") == "success" and result.get("is_error") is False
        return "verified" if ok and models == {route.get("model")} else "failed"
    return "failed"
