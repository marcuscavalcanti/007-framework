"""Adversarial reviewer route by host session (AGENTS.md revision 2026-10-21b; master plan 3.3). Selection only, no launch, fail-closed."""
import importlib
import unittest

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
            ("claude", ALL, ("openai", "codex", "gpt-6-astra", "xhigh", "primary")),
            ("codex", ALL, ("anthropic", "claude", "claude-opus-5-5", "xhigh", "primary")),
        ]
        for host, available, expected in cases:
            with self.subTest(host=host, available=sorted(available)):
                route = select(host, which=which_from(available), env={})
                self.assertEqual(tuple(route[k] for k in ("provider", "cli", "model", "effort", "reason")), expected)
                self.assertEqual(route["host"], host)
                self.assertEqual(route["executable"], available[route["cli"]])
                self.assertNotEqual(route["provider"], {"claude": "anthropic", "codex": "openai"}[host])
        # 2026-10-21b (Marcus): no fallback model; a missing primary or an unrecognized host means no route (fail-closed).
        for host, available in (("claude", {"claude": "/bin/claude", "kimi": "/bin/kimi"}),
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
        codex = module.select_reviewer("claude", which=which_from(ALL), env={})
        argv = module.review_argv(codex)
        validate_command("codex", argv)
        for pair in (["-m", "gpt-6-astra"], ["-c", 'model_reasoning_effort="xhigh"'], ["--sandbox", "read-only"]):
            self.assertIn(pair, [argv[i:i + 2] for i in range(len(argv) - 1)])
        self.assertIn("--ignore-user-config", argv)
        # r33: the reviewer reads only the context on stdin — no shell (a read-only sandbox still reads the whole disk), no web,
        # no apps/plugins/hooks/memory/agents/browser; same features Marcus's other reviewer sessions disable on this binary.
        disabled = {argv[i + 1] for i in range(len(argv) - 1) if argv[i] == "--disable"}
        self.assertLessEqual({"shell_tool", "unified_exec", "apps", "plugins", "hooks", "memories", "multi_agent", "browser_use",
                              "computer_use", "in_app_browser"}, disabled)
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
        forged = {**claude, "cli": "kimi", "model": "kimi-k3", "effort": "high"}
        with self.assertRaisesRegex(ValueError, "^review-route-unknown$"):
            module.review_argv(forged)


if __name__ == "__main__":
    unittest.main()
