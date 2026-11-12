"""Adversarial reviewer route by host session (AGENTS.md revision 2026-10-21b; master plan 3.3). Selection only, no launch, fail-closed."""
import importlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cli_telemetry import validate_command

ALL = {"codex": "/bin/codex", "claude": "/bin/claude", "kimi": "/bin/kimi"}


def which_from(available):
    return lambda name: available.get(name)


class ReviewRouteTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module("review_route")
        except ModuleNotFoundError:
            self.fail("review route is missing")

    def test_identity_level_never_takes_served_identity_from_the_request(self):
        level, codex, claude = self.module().identity_level, {"cli": "codex", "model": "gpt-6-astra"}, {"cli": "claude", "model": "claude-opus-5-5"}
        done = [{"type": "thread.started"}, {"type": "turn.started"}, {"type": "item.completed", "item": {"type": "error", "message": "Code Mode is unavailable"}},
                {"type": "turn.completed", "usage": {}}]
        self.assertEqual(level(codex, done), "pinned-no-reroute")  # a silent match is pinned, never verified
        rerouted = {"type": "item.completed", "item": {"type": "error", "message": "model rerouted: gpt-6-astra -> gpt-5.2 (HighRiskCyberActivity)"}}
        self.assertEqual(level(codex, done[:2] + [rerouted] + done[2:]), "failed")
        self.assertEqual(level(codex, done[:2]), "failed")  # incomplete stream
        self.assertEqual(level(codex, done + [{"type": "turn.failed"}]), "failed")
        result = {"type": "result", "subtype": "success", "is_error": False, "modelUsage": {"claude-opus-5-5": {}}}
        self.assertEqual(level(claude, [result]), "verified")
        self.assertEqual(level(claude, [{**result, "modelUsage": {"claude-opus-5-5": {}, "claude-haiku-5-5": {}}}]), "failed")
        self.assertEqual(level(claude, [{**result, "modelUsage": {}}]), "failed")
        self.assertEqual(level({"cli": "kimi"}, [result]), "failed")

    def test_identity_level_rejects_later_turns_results_and_errors(self):
        level = self.module().identity_level
        codex = {"cli": "codex", "model": "gpt-6-astra"}
        done = [{"type": "turn.started"}, {"type": "turn.completed"}]
        for stream in (done + [{"type": "turn.started"}], done + done,
                       done + [{"type": "error"}], [{"type": "turn.completed"}]):
            with self.subTest(stream=stream):
                self.assertEqual(level(codex, stream), "failed")
        claude = {"cli": "claude", "model": "claude-opus-5-5"}
        result = {"type": "result", "subtype": "success", "is_error": False,
                  "modelUsage": {"claude-opus-5-5": {}}}
        for stream in ([result, {"type": "error"}], [result, result],
                       [result, {**result, "modelUsage": {"other": {}}}],
                       [{"type": "system", "model": "other"}, result],
                       [{"type": "system", "model": "claude-opus-5-5"}, {**result, "modelUsage": {}}]):
            with self.subTest(stream=stream):
                self.assertEqual(level(claude, stream), "failed")

    def test_identity_rejects_wrapped_stream_models_and_errors(self):
        level = self.module().identity_level
        route = {"cli": "claude", "model": "claude-opus-5-5"}
        result = {"type": "result", "subtype": "success", "is_error": False,
                  "modelUsage": {"claude-opus-5-5": {}}}
        for event in ({"type": "message_start", "message": {"model": "other"}},
                      {"type": "error", "error": {"type": "overloaded_error"}}):
            with self.subTest(event=event):
                self.assertEqual(level(route, [{"type": "stream_event", "event": event}, result]), "failed")
        self.assertEqual(level(route, [{"type": "stream_event", "event":
            {"type": "message_start", "message": {"model": "claude-opus-5-5"}}}, result]), "verified")

    def test_host_session_from_markers_and_ambiguity_is_refused(self):
        host = self.module().host_session
        self.assertEqual(host({"CLAUDECODE": "1"}), "claude")
        self.assertEqual(host({"CODEX_THREAD_ID": "thread"}), "codex")
        self.assertIsNone(host({}))
        self.assertIsNone(host({"CLAUDECODE": "", "CODEX_THREAD_ID": ""}))
        with self.assertRaisesRegex(ValueError, "^host-ambiguous$"):
            host({"CLAUDECODE": "1", "CODEX_THREAD_ID": "thread"})

    def test_reviewer_is_the_other_family_and_unavailability_fails_closed(self):
        select = self.module().select_reviewer
        cases = [
            ("claude", ALL, ("anthropic", "claude", "claude-fable-5-2", "xhigh", "primary")),  # 2026-11-12 (Marcus): same family by decision
            ("codex", ALL, ("anthropic", "claude", "claude-opus-5-5", "xhigh", "primary")),
        ]
        for host, available, expected in cases:
            with self.subTest(host=host, available=sorted(available)):
                route = select(host, which=which_from(available), env={})
                self.assertEqual(tuple(route[k] for k in ("provider", "cli", "model", "effort", "reason")), expected)
                self.assertEqual(route["host"], host)
                self.assertEqual(route["executable"], available[route["cli"]])
                if host == "codex":
                    self.assertNotEqual(route["provider"], "openai")
        # 2026-10-21b (Marcus): no fallback model; a missing primary or an unrecognized host means no route (fail-closed).
        for host, available in (("claude", {"codex": "/bin/codex", "kimi": "/bin/kimi"}),
                                ("codex", {"codex": "/bin/codex", "kimi": "/bin/kimi"}), (None, ALL)):
            with self.subTest(host=host, available=sorted(available)):
                self.assertIsNone(select(host, which=which_from(available), env={}))
        both = {"CLAUDECODE": "1", "CODEX_THREAD_ID": "thread"}
        self.assertEqual(select("codex", which=which_from(ALL), env=both)["model"], "claude-opus-5-5")
        with self.assertRaisesRegex(ValueError, "^host-ambiguous$"):
            select(which=which_from(ALL), env=both)
        with self.assertRaisesRegex(ValueError, "^host-unknown$"):
            select("gemini", which=which_from(ALL), env={})

    def test_review_argv_is_fresh_read_only_and_capped_where_the_cli_allows(self):
        module = self.module()
        # the Codex transport stays for recorded routes (the 1.6.2/1.7.0 Astra reviews); no host selects it since 2026-11-12
        codex = {"provider": "openai", "cli": "codex", "model": "gpt-6-astra", "effort": "xhigh", "budget_control": None, "executable": "/bin/codex"}
        argv = module.review_argv(codex)
        validate_command("codex", argv)
        for pair in (["-m", "gpt-6-astra"], ["-c", 'model_reasoning_effort="xhigh"'], ["--sandbox", "read-only"]):
            self.assertIn(pair, [argv[i:i + 2] for i in range(len(argv) - 1)])
        self.assertIn("--ignore-user-config", argv)
        # r33: the reviewer reads only the context on stdin — no shell (a read-only sandbox still reads the whole disk), no web,
        # no apps/plugins/hooks/memory/agents/browser; same features Marcus's other reviewer sessions disable on this binary.
        disabled = {argv[i + 1] for i in range(len(argv) - 1) if argv[i] == "--disable"}
        self.assertLessEqual({"shell_tool", "unified_exec", "apps", "plugins", "hooks", "memories", "multi_agent", "browser_use",
                              "computer_use", "in_app_browser", "code_mode_host"}, disabled)
        # The runner that launches the review must accept this exact argv (repeated --disable was refused after r42 R2).
        import native_runner
        self.assertEqual(native_runner.native_request("codex", argv), (["gpt-6-astra"], ["xhigh"], ["openai"]))
        self.assertIn(["-c", 'web_search="disabled"'], [argv[i:i + 2] for i in range(len(argv) - 1)])
        self.assertIn("--ignore-rules", argv)
        self.assertIsNone(codex["budget_control"])
        claude = module.select_reviewer("codex", which=which_from(ALL), env={})
        argv = module.review_argv(claude, max_budget_usd=6)
        validate_command("claude", argv)
        pairs = [argv[i:i + 2] for i in range(len(argv) - 1)]
        for pair in (["--model", "claude-opus-5-5"], ["--effort", "xhigh"], ["--permission-mode", "plan"], ["--max-budget-usd", "6"]):
            self.assertIn(pair, pairs)
        self.assertIn("--tools=", argv)
        self.assertEqual(claude["budget_control"], "cli-max-budget-usd")
        for budget in (None, 0, -1, True, "6"):
            with self.subTest(budget=budget), self.assertRaisesRegex(ValueError, "^review-budget-required$"):
                module.review_argv(claude, max_budget_usd=budget)
        fable = module.select_reviewer("claude", which=which_from(ALL), env={})
        pairs = [module.review_argv(fable, max_budget_usd=25)[i:i + 2] for i in range(len(module.review_argv(fable, max_budget_usd=25)) - 1)]
        for pair in (["--model", "claude-fable-5-2"], ["--effort", "xhigh"], ["--permission-mode", "plan"], ["--max-budget-usd", "25"]):
            self.assertIn(pair, pairs)
        self.assertEqual(fable["budget_control"], "cli-max-budget-usd")
        forged = {**claude, "cli": "kimi", "model": "kimi-k3", "effort": "high"}
        with self.assertRaisesRegex(ValueError, "^review-route-unknown$"):
            module.review_argv(forged)


if __name__ == "__main__":
    unittest.main()
