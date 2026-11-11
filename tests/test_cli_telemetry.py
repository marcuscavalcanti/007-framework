import importlib
import itertools
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class NativeTelemetryTests(unittest.TestCase):
    def test_claude_alias_presence_type_and_conflict_are_validated(self):
        aliases = (("cache_read_input_tokens", "cached_input_tokens"),
                   ("cache_creation_input_tokens", "cache_write_input_tokens"),
                   ("thinking_tokens", "reasoning_output_tokens"))
        for native, canonical in aliases:
            for value in (None, True, 2.0, "2", -1, 2**53, 0, 1, 2):
                for form in ("native", "canonical", "both"):
                    usage = {"input_tokens": 1, "output_tokens": 1}
                    if form != "native":
                        usage[canonical] = value
                    if form != "canonical":
                        if native == "thinking_tokens":
                            usage["output_tokens_details"] = {native: value}
                        else:
                            usage[native] = value
                    valid = type(value) is int and 0 <= value < 2**53
                    valid &= native != "thinking_tokens" or value in (0, 1)
                    with self.subTest(alias=native, form=form, value=value):
                        rows = [{"type": "system", "subtype": "init", "session_id": "s"},
                                {"type": "result", "subtype": "success", "is_error": False,
                                 "session_id": "s", "num_turns": 1, "usage": usage}]
                        result = self.parse("claude", rows)
                        self.assertEqual(result["status"], "complete" if valid else "incomplete")
                        if valid:
                            self.assertEqual(result["usage"][canonical], value)
                        else:
                            with self.assertRaises(ValueError):
                                self.module().enrich({}, result)
            for canonical_value in (True, 0, 2.0, "1"):
                usage = {"input_tokens": 1, "output_tokens": 1, canonical: canonical_value}
                if native == "thinking_tokens":
                    usage["output_tokens_details"] = {native: 1}
                else:
                    usage[native] = 1
                with self.subTest(conflict=native, canonical_value=canonical_value):
                    with self.assertRaises(ValueError):
                        self.module().NativeTelemetry("claude").add_usage(usage)
        for details in (None, [], True, "private"):
            with self.subTest(details_type=type(details).__name__):
                with self.assertRaises(ValueError):
                    self.module().NativeTelemetry("claude").add_usage(
                        {"input_tokens": 1, "output_tokens": 1, "output_tokens_details": details})

    def test_fatal_accounting_diagnostics_are_chunk_invariant(self):
        rows = [{"type": "thread.started", "thread_id": "s"}, {"type": "turn.started"},
                {"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 1,
                                                       "cache_write_input_tokens": 0, "output_tokens": 0}},
                {"type": "turn.started"},
                {"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 2,
                                                       "output_tokens": 0}},
                {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 0}}]
        wire = b"".join(json.dumps(row).encode() + b"\n" for row in rows)
        expected = None
        for width in (1, 7, 64, len(wire)):
            reader = self.module().NativeTelemetry("codex")
            for offset in range(0, len(wire), width):
                reader.feed(wire[offset:offset + width])
            result = reader.finish()
            self.assertEqual(result["completed_turns"], 1)
            self.assertEqual(result["usage"]["cached_input_tokens"], 1)
            if expected is not None:
                self.assertEqual(result, expected)
            expected = result

    def test_native_error_at_eof_keeps_the_most_severe_class(self):
        reader = self.module().NativeTelemetry("codex")
        reader.feed(b'{"type":"error","message":"Reconnecting"}\n')
        reader.feed(b'{"type":"error","message":"quota exceeded"}')
        self.assertEqual(reader.finish()["problem"], "native-error-rate-limit")

    def test_stream_limit_preserves_the_same_accepted_prefix(self):
        from unittest.mock import patch
        wire = (b'{"type":"thread.started","thread_id":"s"}\n{"type":"turn.started"}\n'
                b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":0}}\n')
        expected = None
        with patch.object(self.module(), "MAX_STREAM_BYTES", len(wire)):
            for width in (1, 7, len(wire) + 1):
                reader = self.module().NativeTelemetry("codex")
                data = wire + b"x"
                for offset in range(0, len(data), width):
                    reader.feed(data[offset:offset + width])
                result = reader.finish()
                self.assertEqual(result["problem"], "stream-limit")
                self.assertEqual(result["completed_turns"], 1)
                if expected is not None:
                    self.assertEqual(result, expected)
                expected = result

    def test_large_content_preserves_identity_anywhere_in_the_envelope(self):
        big = "PRIVATE" * (self.module().MAX_ROW_BYTES // 7 + 2)
        for kind in ("item.started", "item.updated", "item.completed"):
            for position in ("before", "after"):
                row = {"type": kind}
                if position == "before":
                    row["thread_id"] = "foreign"
                row["item"] = {"type": "command_execution", "aggregated_output": big}
                if position == "after":
                    row["thread_id"] = "foreign"
                wire = (b'{"type":"thread.started","thread_id":"s"}\n{"type":"turn.started"}\n'
                        + json.dumps(row, separators=(",", ":")).encode() + b"\n"
                        + b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":0}}\n')
                for width in (65521, len(wire)):
                    with self.subTest(kind=kind, position=position, width=width):
                        reader = self.module().NativeTelemetry("codex")
                        for offset in range(0, len(wire), width):
                            reader.feed(wire[offset:offset + width])
                        result = reader.finish()
                        self.assertEqual(result["status"], "incomplete")
                        self.assertEqual(result["problem"], "foreign-thread-usage")
                        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_large_error_item_preserves_reroute_before_and_after_padding(self):
        for order in ("before", "after"):
            item = {"type": "error", "message": "model rerouted: requested -> other (reason)"}
            row = {"type": "item.completed"}
            if order == "before":
                row["item"] = item
            row["padding"] = "x" * (self.module().MAX_ROW_BYTES + 1)
            row["item"] = item
            wire = (b'{"type":"thread.started","thread_id":"s"}\n{"type":"turn.started"}\n'
                    + json.dumps(row, separators=(",", ":")).encode() + b"\n"
                    + b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":0}}\n')
            for width in (65521, len(wire)):
                with self.subTest(order=order, width=width):
                    reader = self.module().NativeTelemetry("codex")
                    for offset in range(0, len(wire), width):
                        reader.feed(wire[offset:offset + width])
                    result = reader.finish()
                    self.assertEqual(result["model_usage"], {"other": {}})
                    with self.assertRaises(ValueError):
                        self.module().enrich({"model": "requested"}, result)

    def test_large_envelopes_preserve_escaped_metadata_and_validate_discarded_text(self):
        from unittest.mock import patch
        module = self.module()
        header = b'{"type":"thread.started","thread_id":"s"}\n{"type":"turn.started"}\n'
        terminal = b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":0}}\n'
        with patch.object(module, "MAX_ROW_BYTES", 4096):
            for suffix in (b'","thread_id":"foreign"}', b'","thread_id":"s"}',
                           b'","thread\\u005fid":"foreign"}', b'","type":[]}',
                           b'\\q"}', b'\\uZZZZ"}', b'\x01"}', b'\xff"}', b'\\"}'):
                row = b'{"type":"item.completed","padding":"' + b'x' * 4097 + suffix
                expected = None
                for width in (1, 7, 513, len(row) + len(header) + len(terminal) + 1):
                    with self.subTest(suffix=suffix, width=width):
                        data = header + row + b'\n' + terminal
                        reader = module.NativeTelemetry("codex")
                        for offset in range(0, len(data), width):
                            reader.feed(data[offset:offset + width])
                        result = reader.finish()
                        valid = suffix == b'","thread_id":"s"}'
                        self.assertEqual(result["status"], "complete" if valid else "incomplete")
                        if expected is not None:
                            self.assertEqual(result, expected)
                        expected = result

    def test_large_valid_strings_keep_bounded_state_at_eof_and_across_escapes(self):
        from unittest.mock import patch
        module = self.module()
        with patch.object(module, "MAX_ROW_BYTES", 4096):
            for token in ('a', '\\', '"', '\n', '\U0001f680'):
                row = json.dumps({"item": {"type": "command_execution", "aggregated_output": token * 5000},
                                  "thread_id": "s", "type": "item.completed"},
                                 ensure_ascii=False, separators=(",", ":")).encode()
                header = b'{"type":"thread.started","thread_id":"s"}\n{"type":"turn.started"}\n'
                terminal = b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":0}}\n'
                for width in (7, 257, len(row)):
                    with self.subTest(token=token, width=width):
                        reader = module.NativeTelemetry("codex")
                        reader.feed(header + terminal)
                        for offset in range(0, len(row), width):
                            reader.feed(row[offset:offset + width])
                            self.assertLessEqual(len(reader.buffer), 4096)
                            if reader.large_row:
                                self.assertLessEqual(len(reader.large_row.data), 4096)
                        result = reader.finish()
                        self.assertEqual(result["status"], "complete")
                        self.assertEqual(result["oversized_content_rows"], 1)
                        self.assertEqual(reader.finish(), result)
                reader = module.NativeTelemetry("codex")
                reader.feed(header + terminal + row[:-1])
                self.assertEqual(reader.finish()["status"], "incomplete")

    def test_fatal_error_after_a_service_error_stops_further_accounting(self):
        rows = [{"type": "thread.started", "thread_id": "s"}, {"type": "turn.started"},
                {"type": "error", "message": "Reconnecting"},
                {"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 2,
                                                       "output_tokens": 0}},
                {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 0}}]
        result = self.parse("codex", rows)
        self.assertEqual(result["completed_turns"], 0)
        self.assertEqual(result["problem"], "invalid-cache")

    def test_json_parser_resource_errors_stay_sanitized_for_every_row_path(self):
        from unittest.mock import patch
        module = self.module()
        for large, newline in itertools.product((False, True), (b"", b"\n")):
            padding = b'x' * (module.MAX_ROW_BYTES + 1) if large else b'x'
            row = b'{"type":"item.completed","padding":"' + padding + b'"}'
            reader = module.NativeTelemetry("codex")
            with patch.object(module.json, "loads", side_effect=RecursionError("PRIVATE")):
                reader.feed(row + newline)
                result = reader.finish()
            self.assertEqual(result["problem"], "invalid-native-event")
            self.assertNotIn("PRIVATE", json.dumps(result))

    def test_compaction_near_the_envelope_limit_is_chunk_invariant(self):
        from unittest.mock import patch
        module = self.module()
        with patch.object(module, "MAX_ROW_BYTES", 4096):
            for filler in (1900, 1970, 1990, 2010):
                row = (b'{"type":"item.completed","padding":"' + b'x' * 5000
                       + b'","values":[' + b'0,' * filler + b'0],"more":"'
                       + b'x' * 5000 + b'"}\n')
                data = (b'{"type":"thread.started","thread_id":"s"}\n{"type":"turn.started"}\n'
                        + row + b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":0}}\n')
                expected = None
                for width in (1, 7, 257, 65536):
                    reader = module.NativeTelemetry("codex")
                    for offset in range(0, len(data), width):
                        reader.feed(data[offset:offset + width])
                    result = reader.finish()
                    self.assertEqual(result["status"], "complete")
                    if expected is not None:
                        self.assertEqual(result, expected)
                    expected = result

    def test_codex_fork_cannot_be_assigned_as_fresh_task_usage(self):
        with self.assertRaises(ValueError):
            self.module().validate_command("codex", [
                "codex", "exec", "fork", "--json", "--ephemeral", "old-session"])

    def test_parent_inclusive_usage_is_not_summed_twice(self):
        result = self.parse("codex", [
            {"type": "thread.started", "thread_id": "parent"},
            {"type": "turn.started", "thread_id": "parent"},
            {"type": "turn.completed", "thread_id": "child",
             "usage": {"input_tokens": 10, "output_tokens": 2}},
        ])
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["usage"])

    def test_reported_parent_identity_preserves_legitimate_usage(self):
        result = self.parse("codex", [
            {"type": "thread.started", "thread_id": "parent"},
            {"type": "turn.started", "thread_id": "parent"},
            {"type": "turn.completed", "thread_id": "parent",
             "usage": {"input_tokens": 10, "output_tokens": 2}},
        ])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["usage"]["total_tokens"], 12)

    def test_a_codex_reroute_is_the_served_model_and_other_error_items_are_not(self):
        rows = [{"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "error", "message": "Code Mode is unavailable"}},
                {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}]
        self.assertEqual(self.parse("codex", rows)["model_usage"], {})  # a matching model is silent: nothing is claimed
        rerouted = {"type": "item.completed", "item": {"type": "error", "message": "model rerouted: gpt-6.1-sol -> gpt-5.2 (HighRiskCyberActivity)"}}
        self.assertEqual(self.parse("codex", rows[:3] + [rerouted] + rows[3:])["model_usage"], {"gpt-5.2": {}})

    def module(self):
        try:
            return importlib.import_module("cli_telemetry")
        except ModuleNotFoundError:
            self.fail("native command telemetry is not implemented")

    def parse(self, provider, rows):
        reader = self.module().NativeTelemetry(provider)
        data = b"".join(json.dumps(row).encode() + b"\n" for row in rows)
        for index in range(0, len(data), 7):
            reader.feed(data[index:index + 7])
        return reader.finish()

    def test_codex_counts_completed_turns_not_cached_or_reasoning_twice(self):
        result = self.parse("codex", [
            {"type": "thread.started", "thread_id": "session-1"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"text": "PRIVATE_OUTPUT"}},
            {"type": "turn.completed", "usage": {
                "input_tokens": 100, "cached_input_tokens": 80,
                "output_tokens": 20, "reasoning_output_tokens": 10}},
            {"type": "turn.started"},
            {"type": "turn.completed", "usage": {
                "input_tokens": 50, "cached_input_tokens": 40, "output_tokens": 5}},
        ])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["usage"]["total_tokens"], 175)
        self.assertEqual(result["usage"]["cached_input_tokens"], 120)
        self.assertEqual(result["completed_turns"], 2)
        self.assertIsNone(result["estimated_cost_usd"])
        self.assertNotIn("PRIVATE_OUTPUT", json.dumps(result))
        self.assertNotIn("session-1", json.dumps(result))

    def test_codex_duplicate_terminal_cannot_inflate_usage(self):
        result = self.parse("codex", [
            {"type": "thread.started", "thread_id": "session-1"},
            {"type": "turn.started"},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}},
        ])
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["usage"]["total_tokens"], 12)

    def test_codex_cache_partition_admission_and_receipt_enrichment(self):
        cases = 0
        for prompt, cached, written, output, mask in itertools.product(range(5), range(5), range(5), range(3), range(4)):
            usage = {"input_tokens": prompt, "output_tokens": output, "total_tokens": prompt + output}
            if mask & 1:
                usage["cached_input_tokens"] = cached
            if mask & 2:
                usage["cache_write_input_tokens"] = written
            expected = usage.get("cached_input_tokens", 0) + usage.get("cache_write_input_tokens", 0) <= prompt
            result = self.parse("codex", [{"type": "thread.started", "thread_id": "synthetic-allocation"},
                                           {"type": "turn.started"},
                                           {"type": "turn.completed", "usage": usage}])
            context = (prompt, cached, written, output, mask)
            self.assertEqual(result["status"] == "complete", expected, context)
            if expected:
                receipt = self.module().enrich({}, {**result, "wall_s": 0})
                self.assertEqual(receipt["usage"], usage, context)
                self.assertEqual(receipt["tokens"], prompt + output, context)
            else:
                with self.assertRaisesRegex(ValueError, "incomplete native telemetry"):
                    self.module().enrich({}, {**result, "wall_s": 0})
            cases += 1
        self.assertEqual(cases, 1500)

    def test_native_cache_contract_preserves_provider_semantics_and_prior_turns(self):
        for prompt, cached, written in ((1, 1, 0), (1, 0, 1), (2, 1, 1), (1, 1, 1), (1, 0, 2),
                                        (2**53 - 1, 2**53 - 1, 0), (2**53 - 1, 2**53 - 1, 1)):
            codex = self.parse("codex", [{"type": "thread.started", "thread_id": "synthetic"},
                                          {"type": "turn.started"},
                                          {"type": "turn.completed", "usage": {
                                              "input_tokens": prompt, "output_tokens": 0,
                                              "cached_input_tokens": cached, "cache_write_input_tokens": written}}])
            self.assertEqual(codex["status"] == "complete", cached + written <= prompt)
            claude = self.parse("claude", [{"type": "system", "subtype": "init", "session_id": "synthetic"},
                                            {"type": "result", "subtype": "success", "session_id": "synthetic",
                                             "is_error": False, "num_turns": 1, "usage": {
                                                 "input_tokens": prompt, "output_tokens": 0,
                                                 "cache_read_input_tokens": cached,
                                                 "cache_creation_input_tokens": written}}])
            self.assertEqual(claude["status"], "complete")
            self.assertEqual(claude["usage"]["total_tokens"], prompt + cached + written)
        result = self.parse("codex", [{"type": "thread.started", "thread_id": "synthetic"},
                                       {"type": "turn.started"},
                                       {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 0,
                                                                              "cached_input_tokens": 1,
                                                                              "cache_write_input_tokens": 0}},
                                       {"type": "turn.started"},
                                       {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 0,
                                                                              "cached_input_tokens": 1,
                                                                              "cache_write_input_tokens": 1}}])
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["completed_turns"], 1)
        self.assertEqual(result["usage"]["total_tokens"], 1)
        self.assertEqual(result["usage"]["cache_write_input_tokens"], 0)

    def test_absent_optional_counters_remain_unknown_not_zero(self):
        result = self.parse("codex", [
            {"type": "thread.started", "thread_id": "s"}, {"type": "turn.started"},
            {"type": "turn.completed", "usage": {"input_tokens": 2, "output_tokens": 1}},
        ])
        self.assertEqual(result["usage"], {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3})

    def test_inconsistent_reported_total_cannot_qualify(self):
        result = self.parse("codex", [
            {"type": "thread.started", "thread_id": "s"}, {"type": "turn.started"},
            {"type": "turn.completed", "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 99}},
        ])
        self.assertEqual(result["status"], "incomplete")

    def test_claude_uses_one_final_total_not_partial_message_usage(self):
        result = self.parse("claude", [
            {"type": "system", "subtype": "init", "session_id": "session-2"},
            {"type": "assistant", "message": {"content": "PRIVATE_OUTPUT", "usage": {"input_tokens": 999}}},
            {"type": "result", "session_id": "session-2", "subtype": "success",
             "is_error": False, "num_turns": 2, "total_cost_usd": 1.25,
             "usage": {"input_tokens": 10, "output_tokens": 5,
                       "cache_read_input_tokens": 20, "cache_creation_input_tokens": 3},
             "modelUsage": {"claude-opus-5-5": {"costUSD": 1.25}}},
        ])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["usage"]["total_tokens"], 38)
        self.assertEqual(result["estimated_cost_usd"], 1.25)
        self.assertEqual(result["completed_turns"], 2)
        self.assertEqual(result["reported_model"], "claude-opus-5-5")
        self.assertNotIn("PRIVATE_OUTPUT", json.dumps(result))

    def test_claude_thinking_tokens_are_reported_as_reasoning(self):
        reader = self.module().NativeTelemetry("claude")
        for row in ({"type": "system", "subtype": "init", "session_id": "s1"},
                    {"type": "result", "subtype": "success", "is_error": False, "session_id": "s1", "num_turns": 1,
                     "usage": {"input_tokens": 10, "output_tokens": 50, "cache_read_input_tokens": 0,
                               "cache_creation_input_tokens": 0, "output_tokens_details": {"thinking_tokens": 20}},
                     "total_cost_usd": 0.01,
                     "modelUsage": {"claude-x": {"inputTokens": 10, "outputTokens": 50, "costUSD": 0.01}}}):
            reader.feed(json.dumps(row).encode() + b"\n")
        result = reader.finish()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["usage"]["reasoning_output_tokens"], 20)

    def test_missing_invalid_mixed_or_truncated_streams_are_incomplete(self):
        cases = [[], [{"type": "turn.completed", "usage": {"input_tokens": True, "output_tokens": 2}}],
                 [{"type": "thread.started", "thread_id": "a"}, {"type": "thread.started", "thread_id": "b"}]]
        for rows in cases:
            self.assertEqual(self.parse("codex", rows)["status"], "incomplete")
        reader = self.module().NativeTelemetry("codex")
        reader.feed(b'{"type":"thread.started"')
        self.assertEqual(reader.finish()["status"], "incomplete")
        reader = self.module().NativeTelemetry("codex")
        reader.feed(b"x" * (1024 * 1024 + 1))
        self.assertEqual(reader.finish()["status"], "incomplete")

    def test_claude_duplicate_result_and_nonfinite_cost_are_incomplete(self):
        rows = [{"type": "system", "subtype": "init", "session_id": "s"},
                {"type": "result", "session_id": "s", "subtype": "success", "is_error": False,
                 "usage": {"input_tokens": 1, "output_tokens": 1}, "total_cost_usd": 0.2}]
        self.assertEqual(self.parse("claude", rows + rows[1:])["status"], "incomplete")
        for cost in (True, -1, float("nan"), float("inf"), 10 ** 400):
            rows[-1]["total_cost_usd"] = cost
            self.assertEqual(self.parse("claude", rows)["status"], "incomplete")

    def test_invalid_optional_model_cost_does_not_discard_the_valid_total(self):
        result = self.parse("claude", [
            {"type": "system", "subtype": "init", "session_id": "s"},
            {"type": "result", "session_id": "s", "subtype": "success", "is_error": False,
             "usage": {"input_tokens": 1, "output_tokens": 1}, "total_cost_usd": 0.2,
             "modelUsage": {"claude-test": {"inputTokens": 1, "costUSD": 10 ** 400}}}])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["estimated_cost_usd"], 0.2)
        self.assertEqual(result["reported_model"], "claude-test")
        self.assertEqual(result["model_usage"]["claude-test"], {"inputTokens": 1})

    def test_command_boundary_enriches_receipt_without_rewriting_source(self):
        self.run_fixture("codex", exit_code=0)
        self.run_fixture("claude", exit_code=0)
        self.run_fixture("claude", exit_code=0, declared_cost=999)

    def test_a_served_model_the_native_stream_contradicts_is_not_published(self):
        # audit F03: claude-cli telemetry reported claude-opus-5-5 and the recorded receipt kept a different declared model
        self.run_fixture("claude", served_model="different-openai-model")
        self.run_fixture("claude", served_model="different-openai-model", acceptance_bound=True)

    def test_served_identity_is_reconciled_with_every_model_the_stream_reports(self):
        enrich = self.module().enrich
        receipt = json.loads((ROOT / "examples/task.receipt.example.json").read_text())  # declares gpt-5.6-sol-2026-08-01
        observed = lambda models: {"status": "complete", "usage": {"total_tokens": 1}, "wall_s": 1, "estimated_cost_usd": None,
                                   "model_usage": models}
        self.assertEqual(enrich(receipt, observed({}))["served_model"], "gpt-5.6-sol-2026-08-01")  # Codex silence claims nothing
        rerouted = observed({"gpt-5.2": {}})
        with self.assertRaisesRegex(ValueError, r"served_model .*\(gpt-5\.2\)"):
            enrich(receipt, rerouted)  # declaring the requested model after a reroute
        self.assertEqual(enrich({**receipt, "served_model": "gpt-5.2"}, rerouted)["served_model"], "gpt-5.2")
        several = observed({"claude-opus-5-5": {"costUSD": 1.0}, "claude-haiku-5": {"costUSD": 0.01}})
        self.assertEqual(enrich({**receipt, "served_model": "claude-opus-5-5"}, several)["served_provider"], "openai")  # declared
        with self.assertRaisesRegex(ValueError, "claude-haiku-5, claude-opus-5-5"):
            enrich({**receipt, "served_model": "claude-sonnet-5-5"}, several)

    def test_native_error_class_keeps_the_most_severe_whatever_the_chunking(self):
        # Review r42 D2: a later rate-limit row must not be lost behind an earlier transient one, nor overwritten by one.
        import cli_telemetry
        rows = [json.dumps(r).encode() + b"\n" for r in (
            {"type": "thread.started", "thread_id": "t1"}, {"type": "turn.started"},
            {"type": "error", "message": "Reconnecting... 1/5"}, {"type": "error", "message": "Rate limit reached (429)"},
            {"type": "error", "message": "Reconnecting... 2/5"})]
        for chunks in ([b"".join(rows)], rows):
            telemetry = cli_telemetry.NativeTelemetry("codex")
            for chunk in chunks:
                telemetry.feed(chunk)
            self.assertEqual(telemetry.finish()["problem"], "native-error-rate-limit")

    def test_post_exit_drain_is_time_bounded_when_a_descendant_keeps_writing(self):
        # Review r42 T1: reading what is left after the child exits must not follow a descendant that writes forever.
        import time
        import cli_telemetry
        script = ("import os, sys, time\nif os.fork() == 0:\n    os.setsid()\n    t = time.time()\n"
                  "    while time.time() - t < 30:\n        os.write(1, b'x' * 512)\n    os._exit(0)\ntime.sleep(0.5)\nos._exit(0)")
        process = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE)
        started = time.monotonic()
        cli_telemetry.drain(process, cli_telemetry.NativeTelemetry("codex"), wait=True, echo=False)
        process.stdout.close()
        self.assertLess(time.monotonic() - started, 10)

    def test_wait_drain_reads_what_is_still_in_the_pipe_after_the_child_exited(self):
        # Review r40 T1: the wait loop stopped on child exit before reading buffered stdout (empty or partial telemetry).
        import cli_telemetry
        rows = [{"type": "thread.started", "thread_id": "t1"}, {"type": "turn.started"},
                {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2}}]
        script = "import json\nfor r in %r: print(json.dumps(r))" % rows
        process = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE)
        process.wait()  # the child is gone before the first poll; all its bytes sit in the pipe
        telemetry = cli_telemetry.NativeTelemetry("codex")
        cli_telemetry.drain(process, telemetry, wait=True, echo=False)
        process.stdout.close()
        result = telemetry.finish()
        self.assertEqual((result["status"], result["usage"]["input_tokens"]), ("complete", 10))

    def test_native_pipe_is_drained_after_descendant_cleanup_not_before(self):
        self.run_fixture("codex", hold_stdout=True)

    def test_failed_command_keeps_usage_without_manufacturing_receipt(self):
        self.run_fixture("codex", exit_code=7)

    def test_invalid_stream_cannot_publish_terminal_receipt(self):
        self.run_fixture("codex", invalid=True)

    def test_telemetry_collision_preserves_executed_event_without_overwrite(self):
        self.run_fixture("codex", authority_bound=True)
        self.run_fixture("codex", authority_bound=True, telemetry_collision=True)

    def test_non_object_outcome_is_rejected_with_contract_exit(self):
        self.run_fixture("codex", authority_bound=True, acceptance_bound=True)
        self.run_fixture("codex", authority_bound=True, acceptance_bound=True, malformed_receipt=True)

    def test_cleanup_diagnostic_survives_telemetry_collision(self):
        for collision in (False, True):
            with self.subTest(collision=collision):
                self.run_fixture("codex", authority_bound=True, acceptance_bound=True,
                                 telemetry_collision=collision, cleanup_state="cleanup-group-observable")

    def test_line_limit_does_not_depend_on_read_chunk_boundaries(self):
        header = b'{"type":"thread.started","thread_id":"s"}\n{"type":"turn.started"}\n'
        row = json.dumps({"type": "item.completed", "text": "x" * (1024 * 1024 - 80)},
                         separators=(",", ":")).encode() + b"\n"
        terminal = b'{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":1}}\n'
        wire = header + row + terminal + b"\n" * 65536
        for width in (65536, 65521):
            with self.subTest(chunk_bytes=width):
                reader = self.module().NativeTelemetry("codex")
                for offset in range(0, len(wire), width):
                    reader.feed(wire[offset:offset + width])
                result = reader.finish()
                self.assertEqual(result["status"], "complete")
                self.assertEqual(result["usage"]["total_tokens"], 11)

    def test_oversize_complete_and_partial_rows_remain_rejected(self):
        for newline in (b"", b"\n"):
            reader = self.module().NativeTelemetry("codex")
            reader.feed(b"x" * (1024 * 1024 + 1) + newline)
            self.assertEqual(reader.finish()["problem"], "stream-limit")

    def test_oversize_content_rows_are_skipped_and_counted_but_never_terminal_ones(self):
        # r48: a real Go repository made one Codex tool-output row exceed 1 MiB and the whole cell lost its usage. A row whose own
        # prefix declares agent CONTENT (Codex item.*, Claude user/assistant) is skipped and counted; identity, usage and terminal
        # rows are never skipped, so an oversize one still rejects the stream.
        big = "x" * (1024 * 1024 + 10)
        codex = [b'{"type":"thread.started","thread_id":"s"}\n{"type":"turn.started"}\n',
                 json.dumps({"type": "item.completed", "item": {"aggregated_output": big}}, separators=(",", ":")).encode() + b"\n",
                 b'{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":1}}\n']
        claude = [b'{"type":"system","subtype":"init","session_id":"s"}\n',
                  json.dumps({"type": "user", "message": {"content": big}}, separators=(",", ":")).encode() + b"\n",
                  b'{"type":"result","subtype":"success","is_error":false,"session_id":"s","num_turns":1,'
                  b'"usage":{"input_tokens":3,"output_tokens":2}}\n']
        for provider, rows, total in (("codex", codex, 11), ("claude", claude, 5)):
            wire = b"".join(rows)
            for width in (65536, 65521, len(wire)):
                with self.subTest(provider=provider, chunk_bytes=width):
                    reader = self.module().NativeTelemetry(provider)
                    for offset in range(0, len(wire), width):
                        reader.feed(wire[offset:offset + width])
                    result = reader.finish()
                    self.assertEqual((result["status"], result["problem"]), ("complete", None))
                    self.assertEqual((result["usage"]["total_tokens"], result["oversized_content_rows"]), (total, 1))
        terminal = json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}, "pad": big},
                              separators=(",", ":")).encode() + b"\n"
        reader = self.module().NativeTelemetry("codex")
        reader.feed(codex[0] + terminal)
        self.assertEqual(reader.finish()["problem"], "stream-limit")

    def test_aggregate_stream_limit_has_an_exact_positive_boundary(self):
        limit = self.module().MAX_STREAM_BYTES
        reader = self.module().NativeTelemetry("codex")
        header = (b'{"type":"thread.started","thread_id":"s"}\n{"type":"turn.started"}\n'
                  b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n')
        prefix, suffix = b'{"type":"ignored","padding":"', b'"}\n'
        row = prefix + b"x" * (65536 - len(prefix) - len(suffix)) + suffix
        reader.feed(header)
        remaining = limit - len(header)
        while remaining >= len(row):
            reader.feed(row)
            remaining -= len(row)
        reader.feed(b" " * (remaining - 1) + b"\n")
        boundary = reader.finish()
        self.assertEqual(boundary["status"], "complete")
        self.assertEqual(boundary["stream_bytes"], limit)
        self.assertEqual(boundary["usage"]["total_tokens"], 2)
        reader.feed(b"\n")
        over = reader.finish()
        self.assertEqual(over["stream_bytes"], limit + 1)
        self.assertEqual(over["status"], "incomplete")
        self.assertEqual(over["problem"], "stream-limit")

    def test_claude_other_resume_forms_cannot_claim_a_fresh_command(self):
        base = ["claude", "--print", "--verbose", "--no-session-persistence",
                "--output-format", "stream-json"]
        self.module().validate_command("claude", base + ["synthetic"])
        for option in ("--from-pr", "--teleport", "--cloud", "-rSESSION", "-cvalue"):
            for argument in (option, option + "=synthetic"):
                with self.subTest(argument=argument), self.assertRaises(ValueError):
                    self.module().validate_command("claude", base + [argument, "synthetic"])

    def test_claude_stream_requires_verbose_before_execution(self):
        with self.assertRaises(ValueError):
            self.module().validate_command("claude", ["claude", "--print", "--no-session-persistence",
                                                      "--output-format", "stream-json", "synthetic"])

    def test_claude_native_envelope_refuses_short_options_and_clusters(self):
        base = ["claude", "--print", "--verbose", "--no-session-persistence",
                "--output-format", "stream-json"]
        self.module().validate_command("claude", base + ["--model", "synthetic", "--effort", "high", "-"])
        for option in ("-pc", "-prSESSION", "-pcrSESSION", "-p", "-v"):
            with self.subTest(option=option), self.assertRaises(ValueError):
                self.module().validate_command("claude", base + [option, "synthetic"])

    def run_fixture(self, provider, exit_code=0, invalid=False, declared_cost=None, hold_stdout=False,
                    authority_bound=False, telemetry_collision=False, malformed_receipt=False,
                    acceptance_bound=False, cleanup_state=None, served_model=None):
        contradicted = served_model is not None
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "project")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            cli = [sys.executable, "-B", str(ROOT / "scripts/framework_cli.py")]
            subprocess.run(cli + ["init", "--repo", str(repo), "--registry", str(Path(tmp, "registry.json"))],
                           capture_output=True, check=True)
            base = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
            base.update({"tokens": "unmeasured", "wall_s": "unmeasured"})
            if provider == "claude":  # the identity the fixture's stream reports
                base.update(requested_provider="anthropic", requested_model="claude-opus-5-5",
                            served_provider="anthropic", served_model="claude-opus-5-5")
            if contradicted:
                base["served_model"] = served_model
            authority = Path(tmp, "authority.json")
            if authority_bound:
                authority.write_text(json.dumps({"schema": "007-framework/authority/v1",
                                                 "allow": ["test"], "deny": ["deploy"]}))
            acceptance = Path(tmp, "acceptance.json")
            if acceptance_bound:
                acceptance.write_text(json.dumps({"schema": "007-framework/acceptance/v1", "timeout_s": 5,
                    "commands": [[sys.executable, "-c", "from pathlib import Path; Path('gate.ran').touch()"]]}))
            if provider == "claude":
                if declared_cost is None:
                    for key in ("cost_usd", "cost_source", "cost_status"):
                        base.pop(key)
                else:
                    base["cost_usd"] = declared_cost
            rows = ([{"type": "thread.started", "thread_id": "native-1"}, {"type": "turn.started"},
                     {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 8, "output_tokens": 2}}]
                    if provider == "codex" else
                    [{"type": "system", "subtype": "init", "session_id": "native-2"},
                     {"type": "result", "session_id": "native-2", "subtype": "success", "is_error": False,
                      "usage": {"input_tokens": 10, "output_tokens": 2}, "total_cost_usd": 0.25,
                      "modelUsage": {"claude-opus-5-5": {"costUSD": 0.25}}}])
            if invalid:
                rows = []
            executable = Path(tmp, provider)
            executable.write_text("#!" + sys.executable + "\nimport json, os, sys\nfrom pathlib import Path\n"
                                  + ("import subprocess\nsubprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n" if hold_stdout else "")
                                  + "value = " + repr(base) + "\nvalue['task_id'] = os.environ['FRAMEWORK_007_TASK_ID']\n"
                                  + ("Path(os.environ['FRAMEWORK_007_REPO'], '.007/tasks/native-task.telemetry.json').write_text('{}')\n" if telemetry_collision else "")
                                  + "Path(os.environ['FRAMEWORK_007_RECEIPT_PATH']).write_text(json.dumps(" + ("[1, 2]" if malformed_receipt else "value") + "))\n"
                                  + "for row in " + repr(rows) + ": print(json.dumps(row), flush=True)\n"
                                  + "sys.exit(" + str(exit_code) + ")\n")
            executable.chmod(0o700)
            args = (["exec", "--json", "--ephemeral", "test"] if provider == "codex" else
                    ["--print", "--verbose", "--output-format", "stream-json", "--no-session-persistence", "test"])
            if cleanup_state:
                cli = [sys.executable, "-B", "-c", "import sys\nsys.path.insert(0, " + repr(str(ROOT / "scripts")) + ")\n"
                       "import framework_cli as f\noriginal = f.kill_process_group\n"
                       "def cleanup(process):\n    assert original(process) == 'gone'\n    return " + repr(cleanup_state) + "\n"
                       "f.kill_process_group = cleanup\nsys.exit(f.main(sys.argv[1:]))\n"]
            result = subprocess.run(cli + ["run", "--repo", str(repo), "--task-id", "native-task",
                                          "--receipt", "outcome.json", "--native-cli", provider]
                                    + (["--authority-file", str(authority), "--action", "test"] if authority_bound else [])
                                    + (["--acceptance-file", str(acceptance)] if acceptance_bound else [])
                                    + ["--", str(executable), *args],
                                    capture_output=True, text=True, timeout=10)
            if acceptance_bound:
                self.assertEqual((repo / "gate.ran").exists(),
                                 not (exit_code or invalid or malformed_receipt or telemetry_collision or cleanup_state
                                      or contradicted),
                                 result.stderr)
            if cleanup_state:
                self.assertIn("executor cleanup incomplete: " + cleanup_state, result.stderr)
            evidence = repo / ".007/tasks/native-task.telemetry.json"
            self.assertTrue(evidence.exists(), result.stderr)
            if authority_bound:
                event = repo / ".007/events/native-task.event.json"
                self.assertTrue(event.is_file(), "telemetry suppressed the executed controller event")
                self.assertEqual(json.loads(event.read_text())["exit_code"], 0)
                self.assertEqual(json.loads(event.read_text())["outcome"], "executed")
            if telemetry_collision:
                self.assertEqual(evidence.read_text(), "{}")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse((repo / ".007/receipts/native-task.receipt.json").exists())
                self.assertIn("native telemetry already exists", result.stderr)
                return
            telemetry = json.loads(evidence.read_text())
            self.assertEqual(telemetry["task_id"], "native-task")
            self.assertEqual(telemetry["command_exit"], exit_code)
            self.assertTrue(telemetry["stream_closed"])
            self.assertEqual(telemetry["cleanup_state"], cleanup_state or "gone")
            if cleanup_state:
                self.assertEqual(telemetry["status"], "incomplete")
            self.assertEqual(evidence.stat().st_mode & 0o077, 0)
            destination = repo / ".007/receipts/native-task.receipt.json"
            if exit_code or invalid or malformed_receipt or cleanup_state or contradicted:
                self.assertEqual(result.returncode, exit_code or 2, result.stderr)
                self.assertFalse(destination.exists())
                if contradicted:
                    self.assertIn("declared served_model is not a model the native stream reported", result.stderr)
                    self.assertEqual(telemetry["reported_model"], "claude-opus-5-5")  # the observation itself is kept
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                stored = json.loads(destination.read_text())
                self.assertEqual(stored["tokens"], 12)
                self.assertEqual(stored["native_telemetry"]["stream_sha256"], telemetry["stream_sha256"])
                self.assertGreaterEqual(stored["wall_s"], 0)
                original = json.loads((repo / "outcome.json").read_text())
                self.assertEqual(original["tokens"], "unmeasured")
                if declared_cost is not None:
                    self.assertEqual(original["cost_usd"], declared_cost)
                if provider == "claude":
                    self.assertEqual(stored["cost_usd"], 0.25)
                    self.assertEqual(stored["cost_status"], "provisional")
                    self.assertEqual(stored["cost_source"], "rate-card-estimate")

    def test_resumed_command_is_refused_before_start_or_execution(self):
        module = self.module()
        for provider, argv in (("claude", ["claude", "--print", "--resume", "s"]),
                               ("codex", ["codex", "exec", "resume", "--json", "--ephemeral", "s"])):
            with self.assertRaises(ValueError):
                module.validate_command(provider, argv)

    def test_manual_receipt_cannot_claim_native_observation(self):
        import framework_cli
        value = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
        value["native_telemetry"] = {"status": "complete"}
        with self.assertRaisesRegex(ValueError, "native telemetry"):
            framework_cli.validate_receipt(value)


if __name__ == "__main__":
    unittest.main()
