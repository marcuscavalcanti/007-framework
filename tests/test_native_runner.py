"""Step 3a (master 3.2): native CLI runner writing an honest runner receipt for replay_eval; fake CLIs only, no model."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
RUNNER = ROOT / "scripts" / "native_runner.py"
GIT_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
# Fake CLIs: read the prompt from stdin, write answer.txt, print a JSON stream. FAKE_MODE picks the behaviour.
FAKE = r"""import json, os, pathlib, sys
prompt = sys.stdin.read()
pathlib.Path("answer.txt").write_text(str(len(prompt)))
mode, name = os.environ.get("FAKE_MODE", "ok"), pathlib.Path(sys.argv[0]).name
sys.stderr.write("PRIVATE-SENTINEL on stderr\n")  # review r25-r32 R5: native stderr must not reach retained evidence
if name == "codex":
    rows = [{"type": "thread.started", "thread_id": "t1"}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "PRIVATE-SENTINEL"}}]
    if mode == "native-error":  # pilot cell 3: a transient error event (e.g. stream reconnect) before the turn completes
        rows.append({"type": "error", "message": "Reconnecting... 1/5"})
    if mode == "rate-limit":
        rows.append({"type": "error", "message": "Rate limit reached for requests (429)"})
    if mode != "incomplete":
        rows.append({"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2,
                                                       "reasoning_output_tokens": 1}})
else:
    rows = [{"type": "system", "subtype": "init", "session_id": "s1"},
            {"type": "assistant", "message": {"content": "PRIVATE-SENTINEL"}, "session_id": "s1"},
            {"type": "result", "subtype": "success", "is_error": False, "session_id": "s1", "num_turns": 1,
             "usage": {"input_tokens": 10, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
             "total_cost_usd": 0.01, "modelUsage": {"claude-x": {"inputTokens": 10, "outputTokens": 2, "costUSD": 0.01}}}]
    if mode == "mixed-model":  # review r40 T2: an auxiliary model in the same result
        rows[-1]["modelUsage"]["claude-aux"] = {"inputTokens": 1, "outputTokens": 1, "costUSD": 0.001}
for row in rows:
    print(json.dumps(row), flush=True)
sys.exit(3 if mode == "fail-exit" else 0)
"""
PROVIDER = {"codex": "openai", "claude": "anthropic"}
CLI = {"codex": ["exec", "--json", "--ephemeral", "--ignore-user-config", "-m", "m", "-c", 'model_reasoning_effort="medium"', "-"],
       "claude": ["--print", "--verbose", "--no-session-persistence", "--restricted", "--output-format", "stream-json", "--model", "m",
                  "--effort", "medium"]}


class NativeRunnerTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in CLI:
            (self.bin / name).write_text(f"#!{sys.executable}\n" + FAKE)
            (self.bin / name).chmod(0o755)
        self.repo = self.root / "source"
        self.repo.mkdir()
        (self.repo / "base.txt").write_text("base\n")
        for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "base"]):
            subprocess.run(["git", "-C", str(self.repo), *args], env=GIT_ENV, check=True, capture_output=True)
        self.base = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], env=GIT_ENV, check=True,
                                   capture_output=True, text=True).stdout.strip()
        self.output = self.root / "cells"
        self.output.mkdir()

    def runner(self, cli, receipt, *extra, mode="ok", cwd=None, price_table=None, provider=None, model="m", runner_args=()):
        self.assertTrue(RUNNER.is_file(), "native runner is missing")
        prices = ["--price-table", str(price_table)] if price_table else []
        provider = provider or PROVIDER[cli]
        return subprocess.run([sys.executable, "-B", str(RUNNER), "--cli", cli, "--receipt", str(receipt), "--provider", provider,
                               "--model", model, "--effort", "medium", *prices, *runner_args, "--", str(self.bin / cli), *(extra or CLI[cli])],
                              input="do the task", capture_output=True, text=True, cwd=cwd or self.root,
                              env={**os.environ, "FAKE_MODE": mode})

    def price_table(self, models=None, **changes):
        path = self.root / f"prices-{len(list(self.root.glob('prices-*.json')))}.json"
        value = {"schema": "007-framework/price-table/v1", "currency": "USD", "per_tokens": 1000000,
                 "models": {"m": {"input": 1.25, "cached_input": 0.125, "output": 10.0}} if models is None else models, **changes}
        path.write_text(json.dumps(value))
        return path

    def cell(self, cli, *, require=False, served=None, replicate=1, mode="ok", price_table=None):
        replay_eval = importlib.import_module("replay_eval")
        prices = ["--price-table", str(price_table)] if price_table else []
        config = {"repos": {"r": str(self.repo)}, "require_served_identity": require,
                  "arms": {cli: {"provider": PROVIDER[cli], "model": "m", "effort": "medium", "doctrine": ""}},
                  "agent_command": [sys.executable, "-B", str(RUNNER), "--cli", cli, "--receipt", "{runner_receipt}",
                                    "--provider", PROVIDER[cli], "--model", "{model}", "--effort", "{effort}", *prices, "--",
                                    str(self.bin / cli), *CLI[cli]]}
        if served is not None:
            config["served_identity"] = served
        task = {"id": f"t{replicate}", "repo": "r", "base": self.base, "accepted": self.base, "prompt": "do the task",
                "acceptance": [[sys.executable, "-c", "import pathlib; raise SystemExit(0 if pathlib.Path('answer.txt').exists() else 1)"]]}
        old = os.environ.get("FAKE_MODE")
        os.environ["FAKE_MODE"] = mode
        try:
            record = replay_eval.execute_cell(config, task, cli, replicate, self.output, 60)
        finally:
            os.environ.pop("FAKE_MODE") if old is None else os.environ.update(FAKE_MODE=old)
        receipt = self.output / f"t{replicate}-r{replicate:02d}-{cli}.runner.json"
        return record, json.loads(receipt.read_text())

    def test_codex_receipt_records_only_what_the_stream_proves(self):
        record, receipt = self.cell("codex", require=False)
        self.assertEqual((record["valid"], record["accepted"]), (True, True))
        self.assertEqual(receipt["schema"], "007-framework/runner-receipt/v1")
        self.assertEqual((receipt["valid"], receipt["requested"]), (True, {"provider": "openai", "model": "m", "effort": "medium"}))
        self.assertEqual(receipt["served"], {"provider": None, "model": None, "effort": None})
        self.assertEqual(receipt["usage"]["total_tokens"], 12)
        self.assertEqual((receipt["cost_usd"], receipt["cost_source"]), (None, "unavailable"))
        self.assertRegex(receipt["source_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("PRIVATE", json.dumps(record) + json.dumps(receipt))
        # The gap stays visible: requiring served identity cannot be met without fabricating it.
        strict, _ = self.cell("codex", require=True, replicate=2)
        self.assertEqual((strict["valid"], strict["failure_class"]), (False, "served-provider-mismatch"))

    def test_claude_receipt_keeps_reported_model_and_client_cost_estimate(self):
        _, receipt = self.cell("claude", require=False)
        self.assertEqual(receipt["served"], {"provider": None, "model": "claude-x", "effort": None})
        self.assertEqual((receipt["cost_usd"], receipt["cost_source"], receipt["usage"]["total_tokens"]),
                         (0.01, "client-estimate", 12))

    def test_requested_only_records_usage_and_frozen_rate_card_cost(self):
        # Step 3b (decisions 1b, 2a): unreported served fields stay "unverified"; cost = measured tokens x frozen price table.
        table = self.price_table()
        record, receipt = self.cell("codex", served="requested-only", price_table=table)
        self.assertEqual((record["valid"], record["accepted"], record["failure_class"]), (True, True, "none"))
        self.assertEqual((record["served_provider"], record["served_model"], record["served_effort"]), ("unverified",) * 3)
        self.assertEqual((record["tokens"], record["cost_source"]), (12, "rate-card-estimate"))
        self.assertAlmostEqual(record["cost_usd"], (6 * 1.25 + 4 * 0.125 + 2 * 10.0) / 1e6, places=15)
        self.assertEqual(receipt["price_table_sha256"], hashlib.sha256(table.read_bytes()).hexdigest())

    def test_requested_only_still_rejects_a_reported_identity_that_differs_and_bad_policies(self):
        record, _ = self.cell("claude", served="requested-only")  # the fake reports claude-x; the policy asks for m
        self.assertEqual((record["valid"], record["failure_class"]), (False, "served-model-mismatch"))
        for kwargs in ({"require": True, "served": "requested-only"}, {"served": "trust-me"}):
            with self.subTest(**kwargs), self.assertRaisesRegex(ValueError, "^served identity policy"):
                self.cell("codex", replicate=3, **kwargs)
        self.assertFalse((self.output / "t3-r03-codex.json").exists())

    def test_price_table_never_turns_missing_data_into_zero_and_bad_tables_are_refused(self):
        for name, table, mode in (("absent-model", self.price_table({"other": {"input": 1, "cached_input": 1, "output": 1}}), "ok"),
                                  ("incomplete", self.price_table(), "incomplete")):
            with self.subTest(case=name):
                receipt = self.root / f"{name}.json"
                self.runner("codex", receipt, mode=mode, price_table=table)
                value = json.loads(receipt.read_text())
                self.assertEqual((value["cost_usd"], value["cost_source"]), (None, "unavailable"))
        work = self.root / "bad-tables"
        work.mkdir()
        bad = [self.price_table({"m": {"input": -1, "cached_input": 0, "output": 1}}), self.price_table({"m": {"input": 1}}),
               self.price_table(schema="other"), self.price_table(currency="BRL"), self.price_table({"m": {"input": True, "cached_input": 0, "output": 1}})]
        for index, table in enumerate(bad):
            with self.subTest(table=index):
                receipt = self.root / f"bad-{index}.json"
                result = self.runner("codex", receipt, cwd=work, price_table=table)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(receipt.exists())
        claude = self.root / "claude-priced.json"
        self.assertEqual(self.runner("claude", claude, cwd=work, price_table=self.price_table()).returncode, 2)
        self.assertFalse(claude.exists() or (work / "answer.txt").exists())

    def test_incomplete_stream_or_failing_cli_is_not_a_valid_receipt(self):
        for mode, exit_code in (("incomplete", 0), ("fail-exit", 3), ("native-error", 0)):
            with self.subTest(mode=mode):
                receipt = self.root / f"{mode}.json"
                result = self.runner("codex", receipt, mode=mode)
                self.assertEqual(result.returncode, exit_code)
                value = json.loads(receipt.read_text())
                self.assertFalse(value["valid"])
                if mode == "incomplete":  # ponytail: after an error event, usage depends on pipe chunking; invalid cost is never used
                    self.assertIsNone(value["usage"])
                # pilot cell 3: the invalid receipt names the telemetry problem as a fixed code, never stream or stderr content
                self.assertEqual(value["problem"], "native-error-transient" if mode == "native-error" else None)
                self.assertNotIn("Reconnecting", receipt.read_text())

    def test_requested_identity_must_be_the_one_the_native_command_carries(self):
        # Review r25-r32 R2: the receipt's requested model/effort (and so its price) must be what the native CLI was asked for.
        work = self.root / "identity"
        work.mkdir()
        for name, argv in (("other-model", ["exec", "--json", "--ephemeral", "-m", "other", "-c", 'model_reasoning_effort="medium"', "-"]),
                           ("other-effort", ["exec", "--json", "--ephemeral", "-m", "m", "-c", 'model_reasoning_effort="high"', "-"]),
                           ("no-model", ["exec", "--json", "--ephemeral", "-c", 'model_reasoning_effort="medium"', "-"]),
                           ("no-effort", ["exec", "--json", "--ephemeral", "-m", "m", "-"])):
            with self.subTest(case=name):
                receipt = self.root / f"{name}.json"
                self.assertEqual(self.runner("codex", receipt, *argv, cwd=work).returncode, 2)
                self.assertFalse(receipt.exists() or (work / "answer.txt").exists())
        claude = self.root / "claude-other.json"
        argv = CLI["claude"][:-1] + ["high"]
        self.assertEqual(self.runner("claude", claude, *argv, cwd=work).returncode, 2)
        self.assertFalse(claude.exists())
        # Re-review r35 R2: provider is bound too, and alternative spellings of identity options are refused.
        refused = [("codex", CLI["codex"], "anthropic"),
                   ("codex", CLI["codex"][:-1] + ['--config=model_reasoning_effort="high"', "-"], None),
                   ("codex", CLI["codex"][:-1] + ["-c", 'model="other"', "-"], None),
                   ("codex", CLI["codex"][:-1] + ["-c", 'model_provider="other"', "-"], None),
                   ("codex", CLI["codex"][:-1] + ["-p", "profile", "-"], None),
                   ("codex", CLI["codex"][:-1] + ["--oss", "-"], None),
                   ("claude", CLI["claude"], "openai"),
                   ("claude", CLI["claude"] + ["--fallback-model", "other"], None),
                   ("claude", CLI["claude"] + ["--model=other"], None)]
        for index, (cli, argv, provider) in enumerate(refused):
            with self.subTest(case=index):
                receipt = self.root / f"refused-{index}.json"
                self.assertEqual(self.runner(cli, receipt, *argv, cwd=work, provider=provider).returncode, 2)
                self.assertFalse(receipt.exists() or (work / "answer.txt").exists())

    def test_claude_reported_model_set_is_kept_and_a_mixture_never_becomes_unreported(self):
        # Review r40 T2: several modelUsage entries used to become served.model = null, which requested-only validation accepts.
        work = self.root / "models"
        work.mkdir()
        for name, model, served in (("asked-present", "claude-x", "claude-x"), ("asked-absent", "m", "claude-aux,claude-x")):
            with self.subTest(case=name):
                receipt = self.root / f"models-{name}.json"
                argv = [a if a != "m" else model for a in CLI["claude"]]
                self.assertEqual(self.runner("claude", receipt, *argv, cwd=work, mode="mixed-model", model=model).returncode, 0)
                value = json.loads(receipt.read_text())
                self.assertEqual((value["served"]["model"], value["served_models"]), (served, ["claude-aux", "claude-x"]))

    def test_unwritable_receipt_directory_is_refused_before_spending(self):
        # Review r40 G1: an existing absolute directory that cannot take the receipt must stop the run before the CLI starts.
        work, locked = self.root / "g1", self.root / "locked"
        work.mkdir()
        locked.mkdir()
        locked.chmod(0o500)
        try:
            self.assertEqual(self.runner("codex", locked / "r.json", cwd=work).returncode, 2)
            self.assertFalse((work / "answer.txt").exists())
        finally:
            locked.chmod(0o700)

    def test_only_listed_options_and_controlled_config_sources_are_accepted(self):
        # Review r40 R2: identity is bound only if every option is known; config sources must be controlled
        # (Codex --ignore-user-config; Claude --restricted or --setting-sources "").
        work = self.root / "r2"
        work.mkdir()
        codex, claude = CLI["codex"], CLI["claude"]
        refused = [("codex", [a for a in codex if a != "--ignore-user-config"]),
                   ("codex", codex[:-1] + ["-c", 'model_reasoning_effort = "high"', "-"]),
                   ("codex", codex[:-1] + ["-c", 'model_providers.openai.base_url="http://x"', "-"]),
                   ("codex", codex[:-1] + ["--foo", "-"]),
                   ("codex", codex[:-1] + ["do the task"]),
                   ("claude", [a for a in claude if a != "--restricted"]),
                   ("claude", claude + ["--agents", "{}"]),
                   ("claude", claude + ["--mcp-config", '{"mcpServers": {"x": {"command": "y"}}}']),
                   # review r42 R2: a repeated identity/config option is refused (native last-occurrence parsing could win)
                   ("claude", [a for a in claude if a != "--restricted"] + ["--setting-sources", "", "--setting-sources", "user"]),
                   ("claude", claude + ["--model", "m"]),
                   ("codex", codex[:-1] + ["-m", "m", "-"]),
                   ("codex", codex[:-1] + ["-c", 'model_reasoning_effort="medium"', "-"]),
                   # r47: only the managed network proxy feature is listed; any other feature flag stays refused
                   ("codex", codex[:-1] + ["-c", "features.multi_agent=true", "-"])]
        for index, (cli, argv) in enumerate(refused):
            with self.subTest(case=index):
                receipt = self.root / f"r2-{index}.json"
                self.assertEqual(self.runner(cli, receipt, *argv, cwd=work).returncode, 2)
                self.assertFalse(receipt.exists() or (work / "answer.txt").exists())
        h3 = 'permissions.h3={extends=":workspace", filesystem={":root"="deny"}}'
        accepted = [("codex", ["exec", "--json", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "-C", str(work),
                               "-c", h3, "-c", 'default_permissions="h3"', "-c", 'shell_environment_policy.set={A="1"}',
                               "-c", "features.network_proxy=true", "-m", "m", "-c", 'model_reasoning_effort="medium"', "-"]),
                    ("claude", ["--print", "--verbose", "--no-session-persistence", "--output-format", "stream-json", "--restricted",
                                "--tools", "Bash,Read", "--allowedTools", "Bash,Read", "--strict-mcp-config", "--disable-slash-commands",
                                "--permission-mode", "dontAsk", "--model", "m", "--effort", "medium"])]
        for index, (cli, argv) in enumerate(accepted):
            with self.subTest(accepted=index):
                receipt = self.root / f"r2-ok-{index}.json"
                self.assertEqual(self.runner(cli, receipt, *argv, cwd=work).returncode, 0)

    def test_native_error_events_keep_a_rate_limit_apart_from_a_transient_stream_error(self):
        # Review r40 D2: the pilot's rate-limit stop needs an observable class; only fixed codes reach the receipt.
        work = self.root / "d2"
        work.mkdir()
        receipt = self.root / "rate.json"
        self.runner("codex", receipt, mode="rate-limit", cwd=work)
        value = json.loads(receipt.read_text())
        self.assertEqual((value["valid"], value["problem"]), (False, "native-error-rate-limit"))
        self.assertNotIn("429", receipt.read_text())

    def test_claude_settings_file_may_only_carry_permissions_and_sandbox(self):
        # Claude executor (r40): --restricted ignores personal settings; the deny-read sandbox comes from ONE --settings file, which must
        # not be able to change identity or behaviour beyond permissions/sandbox (model, env, apiKeyHelper, hooks...).
        work = self.root / "settings"
        work.mkdir()
        ok = self.root / "ok-settings.json"
        ok.write_text(json.dumps({"permissions": {"deny": ["WebFetch"]}, "sandbox": {"enabled": True}}))
        bad = self.root / "bad-settings.json"
        bad.write_text(json.dumps({"sandbox": {"enabled": True}, "model": "other"}))
        receipt = self.root / "settings-ok.json"
        pinned = ("--settings-sha256", hashlib.sha256(ok.read_bytes()).hexdigest())
        self.assertEqual(self.runner("claude", receipt, *CLI["claude"], "--settings", str(ok), cwd=work, runner_args=pinned).returncode, 0)
        value = json.loads(receipt.read_text())
        self.assertTrue(value["valid"])
        self.assertEqual(value["settings_sha256"], hashlib.sha256(ok.read_bytes()).hexdigest())
        # review r42 G2: the verified bytes themselves may be passed inline, so what the CLI consumes is what was checked
        inline = self.root / "settings-inline.json"
        self.assertEqual(self.runner("claude", inline, *CLI["claude"], "--settings", ok.read_text(), cwd=work, runner_args=pinned).returncode, 0)
        self.assertEqual(json.loads(inline.read_text())["settings_sha256"], pinned[1])
        bad_pin = ("--settings-sha256", hashlib.sha256(bad.read_bytes()).hexdigest())
        for index, (extra, pin) in enumerate(((["--settings", str(bad)], bad_pin), ([f"--settings={ok}"], pinned),
                                              (["--settings", str(ok), "--settings", str(ok)], pinned), (["--settings", '{"sandbox": {}}'], pinned),
                                              (["--settings", str(ok)], ()), (["--settings", str(ok)], ("--settings-sha256", "0" * 64)))):
            with self.subTest(case=index):  # r41 G2: cases 4-5 = settings without the expected digest, or with another digest
                refused = self.root / f"settings-refused-{index}.json"
                self.assertEqual(self.runner("claude", refused, *CLI["claude"], *extra, cwd=work, runner_args=pin).returncode, 2)
                self.assertFalse(refused.exists())

    def test_non_fresh_command_or_existing_receipt_is_refused_before_execution(self):
        receipt = self.root / "refused.json"
        work = self.root / "work"
        work.mkdir()
        result = self.runner("codex", receipt, "exec", "resume", "--json", "--ephemeral", "old", cwd=work)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(receipt.exists() or (work / "answer.txt").exists())
        receipt.write_text("{}")
        result = self.runner("codex", receipt, cwd=work)
        self.assertEqual((result.returncode, receipt.read_text()), (2, "{}"))
        self.assertFalse((work / "answer.txt").exists())
        self.assertEqual(result.stdout, "")
        # Canary incident: a receipt whose directory does not exist, or a relative path, must be refused BEFORE running (no spend).
        missing = self.root / "no-such-dir" / "r.json"
        self.assertEqual(self.runner("codex", missing, cwd=work).returncode, 2)
        self.assertFalse(missing.exists() or (work / "answer.txt").exists())
        rel = subprocess.run([sys.executable, "-B", str(RUNNER), "--cli", "codex", "--receipt", "rel.json", "--provider", "openai",
                              "--model", "m", "--effort", "medium", "--", str(self.bin / "codex"), *CLI["codex"]],
                             input="do", capture_output=True, text=True, cwd=work, env={**os.environ, "FAKE_MODE": "ok"})
        self.assertEqual(rel.returncode, 2)
        self.assertFalse((work / "rel.json").exists() or (work / "answer.txt").exists())


if __name__ == "__main__":
    unittest.main()
