import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NOW = datetime(2026, 8, 30, 15, 0, tzinfo=timezone.utc)


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    timestamp = NOW.timestamp()
    os.utime(path, (timestamp, timestamp))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    timestamp = NOW.timestamp()
    os.utime(path, (timestamp, timestamp))


def codex_rows(session_id, cwd, model="gpt-5.6-sol"):
    return [
        {
            "timestamp": "2026-08-30T14:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "cwd": str(cwd),
                "timestamp": "2026-08-30T14:00:00Z",
                "model_provider": "openai",
                "source": "vscode",
            },
        },
        {
            "timestamp": "2026-08-30T14:00:01Z",
            "type": "response_item",
            "payload": {"type": "message", "content": "SECRET_PROMPT"},
        },
        {
            "timestamp": "2026-08-30T14:00:02Z",
            "type": "turn_context",
            "payload": {"model": model, "effort": "xhigh", "cwd": str(cwd)},
        },
        {"timestamp": "2026-08-30T14:00:03Z", "type": "event_msg", "payload": {"type": "task_started"}},
        {
            "timestamp": "2026-08-30T14:05:00Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {"total_token_usage": {
                    "input_tokens": 1_000_000,
                    "cached_input_tokens": 500_000,
                    "cache_write_input_tokens": 100_000,
                    "output_tokens": 100_000,
                    "reasoning_output_tokens": 50_000,
                    "total_tokens": 1_100_000,
                }},
            },
        },
        {"timestamp": "2026-08-30T14:05:01Z", "type": "event_msg", "payload": {"type": "task_complete"}},
    ]


class LocalActivityTests(unittest.TestCase):
    def module(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("local_activity")
        finally:
            sys.path.pop(0)

    def test_codex_session_normalizes_usage_and_builds_headroom_pricing_request(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "codex.jsonl")
            write_jsonl(path, codex_rows("codex-1", Path(tmp)))

            result = activity.parse_codex_session(path, NOW)
            request = activity.pricing_request(result)

        self.assertEqual(result["session_id"], "codex-1")
        self.assertEqual(result["source"], "codex")
        self.assertEqual(result["status"], "idle")
        self.assertEqual(result["model"], "gpt-5.6-sol")
        self.assertEqual(result["effort"], "xhigh")
        self.assertEqual(result["usage"]["total_tokens"], 1_100_000)
        self.assertEqual(request, {
            "model": "gpt-5.6-sol",
            "prompt_tokens": 400_000,
            "completion_tokens": 100_000,
            "cache_read_input_tokens": 500_000,
            "cache_creation_input_tokens": 100_000,
            "cache_creation_1h_input_tokens": 0,
        })
        self.assertNotIn("SECRET_PROMPT", json.dumps(result))
        self.assertNotIn("content", result)

    def test_codex_long_session_uses_cumulative_delta_inside_window(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "codex-long.jsonl")
            rows = codex_rows("codex-long", Path(tmp))[:3]
            rows[0]["timestamp"] = rows[0]["payload"]["timestamp"] = "2026-08-28T12:00:00Z"
            rows += [
                {"timestamp": "2026-08-29T14:59:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
                    "input_tokens": 1000, "cached_input_tokens": 600, "output_tokens": 100,
                    "reasoning_output_tokens": 20, "total_tokens": 1100,
                }, "last_token_usage": {"input_tokens": 999, "cached_input_tokens": 599, "output_tokens": 99, "reasoning_output_tokens": 19, "total_tokens": 1098}}}},
                {"timestamp": "2026-08-30T14:00:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
                    "input_tokens": 1600, "cached_input_tokens": 900, "output_tokens": 180,
                    "reasoning_output_tokens": 50, "total_tokens": 1780,
                }, "last_token_usage": {"input_tokens": 600, "cached_input_tokens": 300, "output_tokens": 80, "reasoning_output_tokens": 30, "total_tokens": 680}}}},
            ]
            write_jsonl(path, rows)

            result = activity.parse_codex_session(path, NOW, lookback_hours=24)

        self.assertEqual(result["usage"]["input_tokens"], 600)
        self.assertEqual(result["usage"]["cached_input_tokens"], 300)
        self.assertEqual(result["usage"]["output_tokens"], 80)
        self.assertEqual(result["usage"]["total_tokens"], 680)
        self.assertTrue(result["usage"]["usage_complete"])

    def test_codex_invalid_token_info_is_incomplete_without_hiding_valid_delta(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            for invalid in ({"info": None}, {}, {"info": []}):
                path = Path(tmp, "codex-invalid.jsonl")
                rows = codex_rows("codex-invalid", Path(tmp))[:4] + [
                    {"timestamp": "2026-08-30T14:01:00Z", "type": "event_msg", "payload": {"type": "token_count", **invalid}},
                    {"timestamp": "2026-08-30T14:02:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {}, "last_token_usage": {"input_tokens": 7, "total_tokens": 7}}}},
                ]
                write_jsonl(path, rows)
                result = activity.parse_codex_session(path, NOW)
                self.assertEqual(result["usage"]["input_tokens"], 7)
                self.assertFalse(result["usage"]["usage_complete"])
                self.assertIsNone(activity.pricing_request(result))

    def test_codex_invalid_event_after_a_valid_snapshot_stays_incomplete(self):
        activity = self.module()
        for info in (None, {}, {"total_token_usage": {}}, {"total_token_usage": []}):
            with self.subTest(info=info), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp, "snapshot.jsonl")
                write_jsonl(path, codex_rows("snapshot", tmp) + [
                    {"timestamp": "2026-08-30T14:06:00Z", "type": "event_msg",
                     "payload": {"type": "token_count", "info": info}}])
                result = activity.parse_codex_session(path, NOW)
                self.assertEqual(result["usage"]["total_tokens"], 1_100_000)
                self.assertFalse(result["usage"]["usage_complete"])
                self.assertIsNone(activity.pricing_request(result))

    def test_codex_empty_delta_uses_cumulative_counts_and_explicit_zero_stays_valid(self):
        activity = self.module()
        for last in ({}, {"unrecognized": 0}, {"cached_input_tokens": 0}):
            with self.subTest(last=last), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp, "delta.jsonl")
                rows = codex_rows("delta", tmp)
                rows[-2]["payload"]["info"] = {"total_token_usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                                               "last_token_usage": last}
                write_jsonl(path, rows)
                result = activity.parse_codex_session(path, NOW)
                self.assertEqual(result["usage"]["total_tokens"], 120)
                self.assertTrue(result["usage"]["usage_complete"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "zero.jsonl")
            rows = codex_rows("zero", tmp)
            zero = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            rows[-2]["payload"]["info"] = {"total_token_usage": zero, "last_token_usage": zero}
            write_jsonl(path, rows)
            result = activity.parse_codex_session(path, NOW)
            self.assertEqual(result["usage"]["total_tokens"], 0)
            self.assertTrue(result["usage"]["usage_complete"])

    def test_partial_primary_zero_deltas_and_opposing_incoherence_stay_incomplete(self):
        activity = self.module()
        for deltas in ([{"input_tokens": 0}], [{"output_tokens": 0}], [{"total_tokens": 0}],
                       [{"input_tokens": 5, "output_tokens": 0, "total_tokens": 4},
                        {"input_tokens": 5, "output_tokens": 0, "total_tokens": 6}]):
            with self.subTest(deltas=deltas), tempfile.TemporaryDirectory() as tmp:
                rows = codex_rows("partial-primary", tmp)[:4]
                for index, delta in enumerate(deltas, 1):
                    rows.append({"timestamp": f"2026-08-30T14:0{index}:00Z", "type": "event_msg",
                                 "payload": {"type": "token_count", "info": {
                                     "total_token_usage": {"input_tokens": 100 * index, "output_tokens": 20 * index,
                                                           "total_tokens": 120 * index},
                                     "last_token_usage": delta}}})
                path = Path(tmp, "partial-primary.jsonl")
                write_jsonl(path, rows)
                result = activity.parse_codex_session(path, NOW)
                self.assertFalse(result["usage"]["usage_complete"])
                self.assertIsNone(activity.pricing_request(result))

    def test_complete_deltas_must_reconcile_with_available_cumulative_observations(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            rows = codex_rows("reconcile", tmp)[:4]
            for index in (1, 2):
                rows.append({"timestamp": f"2026-08-30T14:0{index}:00Z", "type": "event_msg",
                             "payload": {"type": "token_count", "info": {
                                 "total_token_usage": {"input_tokens": 100 * index, "output_tokens": 20 * index,
                                                       "total_tokens": 120 * index},
                                 "last_token_usage": {"input_tokens": 5, "output_tokens": 0, "total_tokens": 5}}}})
            path = Path(tmp, "reconcile.jsonl")
            write_jsonl(path, rows)
            result = activity.parse_codex_session(path, NOW)
            self.assertEqual(result["usage"]["total_tokens"], 10)
            self.assertFalse(result["usage"]["usage_complete"])
            self.assertIsNone(activity.pricing_request(result))

    def test_duplicate_cumulative_records_cannot_hide_an_invalid_delta(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            rows = codex_rows("duplicate-invalid", tmp)
            duplicate = json.loads(json.dumps(rows[-2]))
            duplicate["timestamp"] = "2026-08-30T14:06:00Z"
            duplicate["payload"]["info"]["last_token_usage"] = {"input_tokens": 0}
            path = Path(tmp, "duplicate-invalid.jsonl")
            write_jsonl(path, rows + [duplicate])
            result = activity.parse_codex_session(path, NOW)
            self.assertEqual(result["usage"]["total_tokens"], 1_100_000)
            self.assertFalse(result["usage"]["usage_complete"])
            self.assertIsNone(activity.pricing_request(result))

    def test_cumulative_only_windows_require_continuity(self):
        activity = self.module()
        for totals, complete in (((0,), False), ((0, 240), False), ((120,), True), ((240,), True)):
            with self.subTest(totals=totals), tempfile.TemporaryDirectory() as tmp:
                rows = codex_rows("reset", tmp)[:3]
                rows[0]["timestamp"] = rows[0]["payload"]["timestamp"] = "2026-08-28T12:00:00Z"
                observations = [("2026-08-29T14:59:00Z", 120)]
                observations += [(f"2026-08-30T14:0{i}:00Z", total) for i, total in enumerate(totals, 1)]
                for stamp, total in observations:
                    rows.append({"timestamp": stamp, "type": "event_msg", "payload": {"type": "token_count", "info": {
                        "total_token_usage": {"input_tokens": total * 5 // 6, "output_tokens": total // 6,
                                              "total_tokens": total}}}})
                path = Path(tmp, "reset.jsonl")
                write_jsonl(path, rows)
                result = activity.parse_codex_session(path, NOW)
                self.assertEqual(result["usage"]["usage_complete"], complete)
                self.assertEqual(activity.pricing_request(result) is not None, complete)

    def test_cumulative_window_does_not_certify_a_timestamp_rewind(self):
        activity = self.module()
        cases = (("2026-08-29T15:01:00Z", "2026-08-29T14:59:30Z", False),
                 ("2026-08-29T15:01:00Z", "2026-08-29T15:02:00Z", True),
                 ("2026-08-29T15:00:00Z", "2026-08-29T15:02:00Z", True))
        for second_stamp, stamp, complete in cases:
            with self.subTest(second_stamp=second_stamp, stamp=stamp), tempfile.TemporaryDirectory() as tmp:
                rows = codex_rows("rewind", tmp)[:3]
                rows[0]["timestamp"] = rows[0]["payload"]["timestamp"] = "2026-08-28T12:00:00Z"
                for timestamp, total in (("2026-08-29T14:59:00Z", 120), (second_stamp, 240), (stamp, 360)):
                    rows.append({"timestamp": timestamp, "type": "event_msg", "payload": {"type": "token_count", "info": {
                        "total_token_usage": {"input_tokens": total * 5 // 6, "output_tokens": total // 6,
                                              "total_tokens": total}}}})
                rows.append({"timestamp": "2026-08-30T14:00:00Z", "type": "event_msg", "payload": {"type": "task_complete"}})
                path = Path(tmp, "rewind.jsonl")
                write_jsonl(path, rows)
                result = activity.parse_codex_session(path, NOW)
                self.assertEqual(result["usage"]["usage_complete"], complete)
                self.assertEqual(activity.pricing_request(result) is not None, complete)
                if complete:
                    self.assertEqual(result["usage"]["total_tokens"], 240)

    def test_codex_cache_write_tiers_must_reconcile_before_pricing(self):
        activity = self.module()
        for first_five, last_five, last_hour, price_ok in ((0, 30, 0, False), (0, 0, 30, True), (30, 30, 30, False)):
            with self.subTest(first_five=first_five, last_hour=last_hour), tempfile.TemporaryDirectory() as tmp:
                total = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                         "cache_write_input_tokens": 30, "cache_write_5m_input_tokens": first_five,
                         "cache_write_1h_input_tokens": 30}
                last = {**total, "cache_write_5m_input_tokens": last_five, "cache_write_1h_input_tokens": last_hour}
                rows = codex_rows("cache-tiers", tmp)
                rows[-2]["payload"]["info"] = {"total_token_usage": total, "last_token_usage": last}
                path = Path(tmp, "cache-tiers.jsonl")
                write_jsonl(path, rows)
                result = activity.parse_codex_session(path, NOW)
                self.assertTrue(result["usage"]["usage_complete"])
                self.assertEqual(result["usage"]["total_tokens"], 120)
                request = activity.pricing_request(result)
                self.assertEqual(request is not None, price_ok)
                if request:
                    self.assertEqual(request["cache_creation_1h_input_tokens"], 30)

    def test_duplicate_cumulative_timestamps_preserve_window_uncertainty(self):
        activity = self.module()
        cases = [("2026-08-29T14:59:30Z", False), (None, False),
                 ("2026-08-29T15:02:00Z", True)]
        for duplicate_stamp, complete in cases:
            with self.subTest(stamp=duplicate_stamp), tempfile.TemporaryDirectory() as tmp:
                rows = codex_rows("duplicate-clock", tmp)[:3]
                rows[0]["timestamp"] = rows[0]["payload"]["timestamp"] = "2026-08-28T12:00:00Z"
                for stamp, amount in (("2026-08-29T14:59:00Z", 120),
                                      ("2026-08-29T15:01:00Z", 240), (duplicate_stamp, 240)):
                    rows.append({"type": "event_msg", "timestamp": stamp, "payload": {
                        "type": "token_count", "info": {"total_token_usage": {
                            "input_tokens": amount * 5 // 6, "output_tokens": amount // 6,
                            "total_tokens": amount}}}})
                filename = Path(tmp, "duplicate-clock.jsonl")
                write_jsonl(filename, rows)
                result = activity.parse_codex_session(filename, NOW)
                self.assertEqual(result["usage"]["total_tokens"], 120)
                self.assertEqual(result["usage"]["usage_complete"], complete)
                self.assertEqual(activity.pricing_request(result) is not None, complete)

    def test_cumulative_pricing_requires_valid_baseline_allocation(self):
        activity = self.module()
        for cached, priced in ((180, False), (100, True)):
            with self.subTest(cached=cached), tempfile.TemporaryDirectory() as tmp:
                rows = codex_rows("baseline-allocation", tmp)[:3]
                rows[0]["timestamp"] = rows[0]["payload"]["timestamp"] = "2026-08-28T12:00:00Z"
                for stamp, amount, cache in (("2026-08-29T14:59:00Z", 120, cached),
                                             ("2026-08-29T15:01:00Z", 240, 200)):
                    rows.append({"type": "event_msg", "timestamp": stamp, "payload": {
                        "type": "token_count", "info": {"total_token_usage": {
                            "input_tokens": amount * 5 // 6, "output_tokens": amount // 6,
                            "total_tokens": amount, "cached_input_tokens": cache}}}})
                filename = Path(tmp, "baseline-allocation.jsonl")
                write_jsonl(filename, rows)
                result = activity.parse_codex_session(filename, NOW)
                self.assertTrue(result["usage"]["usage_complete"])
                self.assertEqual(result["usage"]["total_tokens"], 120)
                request = activity.pricing_request(result)
                self.assertEqual(request is not None, priced)
                if request:
                    self.assertEqual(request["prompt_tokens"], 0)
                    self.assertEqual(request["cache_read_input_tokens"], 100)

    def test_invalid_cache_allocation_cannot_cancel_out_across_observations(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            rows = codex_rows("cache-observations", tmp)[:3]
            for i, cached in ((1, 180), (2, 0)):
                total = {"input_tokens": 100 * i, "output_tokens": 20 * i, "total_tokens": 120 * i,
                         "cached_input_tokens": 180}
                last = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120, "cached_input_tokens": cached}
                rows.append({"timestamp": f"2026-08-30T14:0{i}:00Z", "type": "event_msg", "payload": {
                    "type": "token_count", "info": {"total_token_usage": total, "last_token_usage": last}}})
            path = Path(tmp, "cache-observations.jsonl")
            write_jsonl(path, rows)
            result = activity.parse_codex_session(path, NOW)
            self.assertTrue(result["usage"]["usage_complete"])
            self.assertEqual(result["usage"]["total_tokens"], 240)
            self.assertIsNone(activity.pricing_request(result))

    def test_cumulative_cache_allocation_validates_derived_intervals(self):
        activity = self.module()
        cases = [(30, 40, False), (30, 60, True)]
        for initial_write, final_write, priced in cases:
            with self.subTest(final_write=final_write), tempfile.TemporaryDirectory() as tmp:
                rows = codex_rows("derived-tiers", tmp)[:3]
                rows[0]["timestamp"] = rows[0]["payload"]["timestamp"] = "2026-08-28T12:00:00Z"
                for stamp, amount, writes, hour in (("2026-08-29T14:59:00Z", 120, initial_write, 0),
                                                    ("2026-08-30T14:00:00Z", 240, final_write, 30)):
                    rows.append({"timestamp": stamp, "type": "event_msg", "payload": {"type": "token_count", "info": {
                        "total_token_usage": {"input_tokens": amount * 5 // 6, "output_tokens": amount // 6,
                            "total_tokens": amount, "cache_write_input_tokens": writes, "cache_write_1h_input_tokens": hour}}}})
                path = Path(tmp, "derived-tiers.jsonl")
                write_jsonl(path, rows)
                result = activity.parse_codex_session(path, NOW)
                self.assertTrue(result["usage"]["usage_complete"])
                self.assertEqual(result["usage"]["total_tokens"], 120)
                self.assertEqual(activity.pricing_request(result) is not None, priced)
        with tempfile.TemporaryDirectory() as tmp:
            rows = codex_rows("derived-cache", tmp)[:3]
            rows[0]["timestamp"] = rows[0]["payload"]["timestamp"] = "2026-08-28T12:00:00Z"
            for stamp, amount, cached in (("2026-08-29T14:59:00Z", 120, 0),
                                          ("2026-08-30T14:00:00Z", 240, 150),
                                          ("2026-08-30T14:01:00Z", 360, 150)):
                rows.append({"timestamp": stamp, "type": "event_msg", "payload": {"type": "token_count", "info": {
                    "total_token_usage": {"input_tokens": amount * 5 // 6, "output_tokens": amount // 6,
                                         "total_tokens": amount, "cached_input_tokens": cached}}}})
            path = Path(tmp, "derived-cache.jsonl")
            write_jsonl(path, rows)
            result = activity.parse_codex_session(path, NOW)
            self.assertTrue(result["usage"]["usage_complete"])
            self.assertEqual(result["usage"]["total_tokens"], 240)
            self.assertIsNone(activity.pricing_request(result))

    def test_duplicate_allocation_anomaly_keeps_primary_tokens_without_pricing(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            rows = codex_rows("duplicate-allocation", tmp)
            duplicate = json.loads(json.dumps(rows[-2]))
            duplicate["timestamp"] = "2026-08-30T14:06:00Z"
            duplicate["payload"]["info"]["last_token_usage"] = {
                "input_tokens": 1_000_000, "output_tokens": 100_000, "total_tokens": 1_100_000,
                "cached_input_tokens": 1_500_000}
            path = Path(tmp, "duplicate-allocation.jsonl")
            write_jsonl(path, rows + [duplicate])
            result = activity.parse_codex_session(path, NOW)
            self.assertEqual(result["usage"]["total_tokens"], 1_100_000)
            self.assertTrue(result["usage"]["usage_complete"])
            self.assertIsNone(activity.pricing_request(result))

    def test_cache_only_codex_deltas_validate_allocations_before_fallback_and_dedup(self):
        activity = self.module()
        keys = ("cached_input_tokens", "cache_write_input_tokens",
                "cache_write_5m_input_tokens", "cache_write_1h_input_tokens")
        for key in keys:
            for value, priced in ((-1, False), (False, False), (10 ** 400, False), (1, False), (0, True)):
                for repeated in (False, True):
                    with self.subTest(key=key, kind=type(value).__name__, priced=priced, repeated=repeated):
                        with tempfile.TemporaryDirectory() as tmp:
                            rows = codex_rows("cache-only", tmp)[:3]
                            event = {"type": "event_msg", "timestamp": "2026-08-30T14:05:00Z", "payload": {
                                "type": "token_count", "info": {
                                    "total_token_usage": {"input_tokens": 100, "cached_input_tokens": 40,
                                                          "output_tokens": 20, "total_tokens": 120},
                                    "last_token_usage": {key: value}}}}
                            filename = Path(tmp, "cache-only.jsonl")
                            write_jsonl(filename, rows + [event] * (2 if repeated else 1))
                            result = activity.parse_codex_session(filename, NOW)
                            self.assertEqual(result["usage"]["total_tokens"], 120)
                            self.assertTrue(result["usage"]["usage_complete"])
                            self.assertEqual(activity.pricing_request(result) is not None, priced)

    def test_claude_counter_aggregation_exposes_unrepresentable_usage(self):
        activity = self.module()
        for amount, expected in ((10 ** 308, None), (10, 20), (0, 0)):
            with self.subTest(representable=expected is not None), tempfile.TemporaryDirectory() as tmp:
                filename = Path(tmp, "counter-sum.jsonl")
                rows = [{"type": "assistant", "sessionId": "counter-sum", "cwd": tmp,
                         "timestamp": "2026-08-30T14:00:00Z", "message": {
                             "id": str(index), "model": "claude-test",
                             "usage": {"input_tokens": amount, "output_tokens": 0}}} for index in range(2)]
                write_jsonl(filename, rows)
                result = activity.parse_claude_session(filename, NOW)
                self.assertEqual(result["usage"]["input_tokens"], expected)
                self.assertEqual(result["usage"]["total_tokens"], expected)
                self.assertEqual(result["usage"]["usage_complete"], expected is not None)
                request = activity.pricing_request(result)
                self.assertEqual(request is not None, expected is not None)
                if request:
                    self.assertEqual(request["prompt_tokens"], expected)
                summary = activity.summarize([result], 24)
                self.assertEqual(summary["tokens_total"], expected)
                self.assertEqual(summary["routes"][0]["tokens"], expected)
                self.assertEqual(summary["usage_incomplete_sessions"], int(expected is None))

    def test_activity_token_totals_preserve_known_subtotals_without_overflow(self):
        activity = self.module()
        cases = [([10 ** 308, 10 ** 308], None, 0), ([None], None, 1),
                 ([None, 20], 20, 1), ([10, 10], 20, 0), ([0, 0], 0, 0)]
        for amounts, expected, incomplete in cases:
            with self.subTest(case=incomplete, expected=expected):
                sessions = [{"session_id": str(index), "source": "claude", "status": "idle",
                             "runtime_provider": "anthropic", "model": "test", "effort": "medium",
                             "usage": {**activity.empty_usage(), "input_tokens": amount,
                                       "total_tokens": amount, "usage_complete": amount is not None}}
                            for index, amount in enumerate(amounts)]
                summary = activity.summarize(sessions, 24)
                self.assertEqual(summary["tokens_total"], expected)
                self.assertEqual(summary["input_tokens"], expected)
                self.assertEqual(summary["routes"][0]["tokens"], expected)
                self.assertEqual(summary["usage_incomplete_sessions"], incomplete)
                json.dumps(summary, allow_nan=False)

    def test_pricing_rejects_unrepresentable_counters_and_completion_sums(self):
        activity = self.module()
        for usage in ({"input_tokens": 2 * 10 ** 308, "output_tokens": 0},
                      {"input_tokens": 0, "output_tokens": 10 ** 308,
                       "reasoning_output_tokens": 10 ** 308, "output_includes_reasoning": False}):
            with self.subTest(keys=sorted(usage)):
                self.assertIsNone(activity.pricing_request({"model": "test", "usage": usage}))

    def test_other_native_adapters_keep_aggregate_and_invalid_counter_uncertainty(self):
        activity = self.module()
        cases = ((10 ** 308, None, False), (10, 20, True), (0, 0, True), (-1, 0, False))
        for source in ("kimi", "gemini"):
            for amount, expected, complete in cases:
                with self.subTest(source=source, expected=expected, complete=complete), tempfile.TemporaryDirectory() as tmp:
                    if source == "kimi":
                        filename = Path(tmp, "state.json")
                        write_json(filename, {"id": "counter-sum", "cwd": tmp,
                                             "createdAt": int(NOW.timestamp() * 1000) - 60000,
                                             "updatedAt": int(NOW.timestamp() * 1000)})
                        write_jsonl(Path(tmp, "agents/main/wire.jsonl"), [
                            {"type": "usage.record", "time": int(NOW.timestamp() * 1000),
                             "model": "kimi-test", "usage": {"inputOther": amount, "output": 0}}
                            for _ in range(2)])
                        result = activity.parse_kimi_session(filename, NOW)
                    else:
                        filename = Path(tmp, "session.jsonl")
                        write_jsonl(filename, [{"sessionId": "counter-sum", "startTime": "2026-08-30T14:00:00Z"}] + [
                            {"type": "gemini", "timestamp": "2026-08-30T14:01:00Z", "model": "gemini-test",
                             "tokens": {"input": amount, "output": 0, "total": amount}} for _ in range(2)])
                        result = activity.parse_gemini_session(filename, tmp, NOW)
                    self.assertEqual(result["usage"]["input_tokens"], expected)
                    self.assertEqual(result["usage"]["total_tokens"], expected)
                    self.assertEqual(result["usage"]["usage_complete"], complete)
                    self.assertEqual(activity.pricing_request(result) is not None, complete)

    def test_primary_usage_and_price_allocation_have_separate_completeness(self):
        activity = self.module()
        cases = [("increment", 80, 0, False), ("increment", 80, 80, True),
                 ("increment", 180, 180, False), ("cumulative", 80, 0, False),
                 ("cumulative", 80, 160, True)]
        for mode, first_cache, second_cache, price_ok in cases:
            with self.subTest(mode=mode, first=first_cache, second=second_cache), tempfile.TemporaryDirectory() as tmp:
                rows = codex_rows("cache-allocation", tmp)[:3]
                if mode == "cumulative":
                    rows[0]["timestamp"] = rows[0]["payload"]["timestamp"] = "2026-08-28T12:00:00Z"
                    rows.append({"timestamp": "2026-08-29T14:59:00Z", "type": "event_msg", "payload": {
                        "type": "token_count", "info": {"total_token_usage": {"input_tokens": 100,
                        "output_tokens": 20, "total_tokens": 120, "cached_input_tokens": first_cache}}}})
                    info = {"total_token_usage": {"input_tokens": 200, "output_tokens": 40,
                                                   "total_tokens": 240, "cached_input_tokens": second_cache}}
                else:
                    info = {"total_token_usage": {"input_tokens": 100, "output_tokens": 20,
                                                   "total_tokens": 120, "cached_input_tokens": first_cache},
                            "last_token_usage": {"input_tokens": 100, "output_tokens": 20,
                                                  "total_tokens": 120, "cached_input_tokens": second_cache}}
                rows.append({"timestamp": "2026-08-30T14:01:00Z", "type": "event_msg",
                             "payload": {"type": "token_count", "info": info}})
                path = Path(tmp, "cache-allocation.jsonl")
                write_jsonl(path, rows)
                result = activity.parse_codex_session(path, NOW)
                self.assertEqual(result["usage"]["total_tokens"], 120)
                self.assertTrue(result["usage"]["usage_complete"])
                request = activity.pricing_request(result)
                self.assertEqual(request is not None, price_ok)
                if request:
                    self.assertEqual((request["prompt_tokens"], request["cache_read_input_tokens"]), (20, 80))

    def test_extreme_native_counters_are_incomplete_instead_of_breaking_collection(self):
        activity = self.module()
        for value in (10 ** 400, float("inf"), float("nan"), -1, False):
            with self.subTest(counter_type=type(value).__name__), tempfile.TemporaryDirectory() as tmp:
                rows = codex_rows("invalid-counter", tmp)
                rows[-2]["payload"]["info"]["total_token_usage"]["input_tokens"] = value
                path = Path(tmp, "invalid-counter.jsonl")
                write_jsonl(path, rows)
                result = activity.parse_codex_session(path, NOW)
                self.assertFalse(result["usage"]["usage_complete"])
                self.assertIsNone(activity.pricing_request(result))

    def test_untimed_counter_observation_cannot_qualify_a_window(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            rows = codex_rows("untimed", tmp)[:3]
            rows.append({"type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}}}})
            path = Path(tmp, "untimed.jsonl")
            write_jsonl(path, rows)
            result = activity.parse_codex_session(path, NOW)
            self.assertEqual(result["usage"]["total_tokens"], 120)
            self.assertFalse(result["usage"]["usage_complete"])
            self.assertIsNone(activity.pricing_request(result))

    def test_claude_aggregate_cache_writes_survive_optional_tiers_without_pricing_unknown_tiers(self):
        activity = self.module()
        cases = [({"cache_creation_input_tokens": 30}, 30, False),
                 ({"cache_creation_input_tokens": 0}, 0, True),
                 ({"cache_creation": {"ephemeral_5m_input_tokens": 30}}, 30, True),
                 ({"cache_creation_input_tokens": 30, "cache_creation": {"ephemeral_1h_input_tokens": 30}}, 30, True),
                 ({"cache_creation_input_tokens": 30, "cache_creation": {"ephemeral_5m_input_tokens": 20}}, 30, False)]
        for extra, writes, tiers_complete in cases:
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp, "cache.jsonl")
                write_jsonl(path, [{"type": "assistant", "sessionId": "cache", "cwd": tmp,
                                   "timestamp": "2026-08-30T14:00:00Z", "message": {"id": "response", "model": "claude-opus-5",
                                   "usage": {"input_tokens": 100, "output_tokens": 20, **extra}}}])
                result = activity.parse_claude_session(path, NOW)
                self.assertEqual(result["usage"]["cache_write_input_tokens"], writes)
                self.assertEqual(result["usage"]["total_tokens"], 120 + writes)
                self.assertTrue(result["usage"]["usage_complete"])
                self.assertEqual(result["usage"]["cache_write_tiers_complete"], tiers_complete)
                self.assertEqual(activity.pricing_request(result) is not None, tiers_complete)

    def test_inconsistent_codex_counts_and_claude_cache_aggregates_stay_unpriced(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "inconsistent.jsonl")
            rows = codex_rows("inconsistent", tmp)
            rows[-2]["payload"]["info"]["last_token_usage"] = {"input_tokens": 5}
            write_jsonl(path, rows)
            partial = activity.parse_codex_session(path, NOW)
            self.assertEqual(partial["usage"]["input_tokens"], 5)
            self.assertFalse(partial["usage"]["usage_complete"])
            self.assertIsNone(activity.pricing_request(partial))
            write_jsonl(path, [{"type": "assistant", "sessionId": "inconsistent", "cwd": tmp,
                               "timestamp": "2026-08-30T14:00:00Z", "message": {"id": "response", "model": "claude-opus-5",
                               "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 10,
                                         "cache_creation": {"ephemeral_5m_input_tokens": 30}}}}])
            partial = activity.parse_claude_session(path, NOW)
            self.assertTrue(partial["usage"]["usage_complete"])
            self.assertEqual(partial["usage"]["total_tokens"], 130)
            self.assertIsNone(activity.pricing_request(partial))

    def test_claude_pricing_validates_emitted_cache_tiers_and_alias_conflicts(self):
        activity = self.module()
        cases = [(None, 30, True), (30, 30, True), (60, 30, False),
                 (20, 30, False), (30, 60, False)]
        for top_level, nested, priced in cases:
            with self.subTest(top_level=top_level, nested=nested), tempfile.TemporaryDirectory() as tmp:
                usage = {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 30,
                         "cache_creation": {"ephemeral_1h_input_tokens": nested}}
                if top_level is not None:
                    usage["ephemeral_1h_input_tokens"] = top_level
                filename = Path(tmp, "merged-tiers.jsonl")
                write_jsonl(filename, [{"type": "assistant", "sessionId": "merged-tiers", "cwd": tmp,
                    "timestamp": "2026-08-30T14:00:00Z", "message": {
                        "id": "one", "model": "claude-test", "usage": usage}}])
                result = activity.parse_claude_session(filename, NOW)
                self.assertTrue(result["usage"]["usage_complete"])
                self.assertEqual(result["usage"]["total_tokens"], 150)
                self.assertEqual(result["usage"]["cache_write_tiers_complete"], priced)
                request = activity.pricing_request(result)
                self.assertEqual(request is not None, priced)
                if request:
                    self.assertEqual(request["cache_creation_input_tokens"], 30)
                    self.assertEqual(request["cache_creation_1h_input_tokens"], 30)

    def test_claude_missing_response_usage_is_unknown_and_a_final_update_can_repair_it(self):
        activity = self.module()
        for raw in (None, {}, [], {"input_tokens": 3}):
            with self.subTest(usage=raw), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp, "missing.jsonl")
                row = {"type": "assistant", "sessionId": "missing", "cwd": tmp,
                       "timestamp": "2026-08-30T14:00:00Z",
                       "message": {"id": "response", "model": "claude-opus-5", "usage": raw}}
                write_jsonl(path, [row])
                incomplete = activity.parse_claude_session(path, NOW)
                self.assertFalse(incomplete["usage"]["usage_complete"])
                self.assertIsNone(activity.pricing_request(incomplete))
                final = {**row, "message": {**row["message"], "usage": {"input_tokens": 100, "output_tokens": 20}}}
                no_usage = {**row, "message": {k: v for k, v in row["message"].items() if k != "usage"}}
                write_jsonl(path, [row, final, no_usage])
                repaired = activity.parse_claude_session(path, NOW)
                self.assertEqual(repaired["usage"]["total_tokens"], 120)
                self.assertTrue(repaired["usage"]["usage_complete"])

    def test_untimed_claude_usage_remains_uncertain_until_a_timed_update(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp, "untimed-usage.jsonl")
            meta = {"type": "user", "sessionId": "untimed-usage", "cwd": tmp,
                    "timestamp": "2026-08-30T14:00:00Z"}
            response = {"type": "assistant", "message": {
                "id": "one", "model": "claude-test", "usage": {"input_tokens": 10, "output_tokens": 2}}}
            write_jsonl(filename, [meta, response])
            incomplete = activity.parse_claude_session(filename, NOW)
            self.assertFalse(incomplete["usage"]["usage_complete"])
            self.assertIsNone(activity.pricing_request(incomplete))
            write_jsonl(filename, [meta, response, {**response, "timestamp": "2026-08-30T14:01:00Z"}])
            repaired = activity.parse_claude_session(filename, NOW)
            self.assertTrue(repaired["usage"]["usage_complete"])
            self.assertEqual(repaired["usage"]["total_tokens"], 12)

    def test_codex_log_over_4_mib_is_read_whole_so_usage_is_complete_and_priced(self):
        # a 527 MB rollout read only in its last 4 MiB reported 4 M tokens instead of 2.5 bn, unpriced
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "codex-large.jsonl")
            rows = codex_rows("codex-clipped", Path(tmp))[:4] + [
                {"timestamp": "2026-08-30T14:01:00Z", "type": "event_msg", "payload": {
                    "type": "token_count", "info": {
                        "total_token_usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                        "last_token_usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}}}},
                {"type": "response_item", "payload": {"padding": "x" * (4 * 1024 * 1024)}},
                {"timestamp": "2026-08-30T14:02:00Z", "type": "turn_context",
                 "payload": {"model": "gpt-5.6-sol", "effort": "xhigh"}},
                {"timestamp": "2026-08-30T14:03:00Z", "type": "event_msg", "payload": {
                    "type": "token_count", "info": {
                        "total_token_usage": {"input_tokens": 107, "output_tokens": 22, "total_tokens": 129},
                        "last_token_usage": {"input_tokens": 7, "output_tokens": 2, "total_tokens": 9}}}},
            ]
            write_jsonl(path, rows)
            result = activity.parse_codex_session(path, NOW)

        self.assertEqual(result["usage"]["total_tokens"], 129)
        self.assertTrue(result["usage"]["usage_complete"])
        self.assertEqual(activity.pricing_request(result)["completion_tokens"], 22)

    def test_usage_completeness_is_visible_in_project_summary_without_promoting_cost(self):
        activity = self.module()
        sessions = [{"status": "idle", "runtime_provider": "openai", "model": "m",
                     "effort": "high", "usage": {"total_tokens": 9, "usage_complete": False}},
                    {"status": "idle", "runtime_provider": "openai", "model": "m",
                     "effort": "high", "usage": {"total_tokens": 120, "usage_complete": True}}]
        result = activity.summarize(sessions, 24)
        self.assertEqual(result["tokens_total"], 129)
        self.assertEqual(result.get("usage_incomplete_sessions"), 1)
        self.assertIsNone(result["cost_usd_estimate"])

    def test_claude_session_sums_token_classes_and_cache_tiers(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "claude.jsonl")
            rows = [
                {
                    "type": "user", "cwd": str(Path(tmp)), "sessionId": "claude-1",
                    "timestamp": "2026-08-30T14:00:00Z",
                    "message": {"role": "user", "content": "SECRET_PROMPT"},
                },
                {
                    "type": "assistant", "cwd": str(Path(tmp)), "sessionId": "claude-1",
                    "timestamp": "2026-08-30T14:01:00Z", "effort": "xhigh",
                    "message": {"role": "assistant", "model": "claude-opus-5", "content": "SECRET_OUTPUT", "usage": {
                        "input_tokens": 100_000, "cache_read_input_tokens": 200_000,
                        "cache_creation_input_tokens": 30_000,
                        "cache_creation": {"ephemeral_5m_input_tokens": 10_000, "ephemeral_1h_input_tokens": 20_000},
                        "output_tokens": 10_000, "output_tokens_details": {"thinking_tokens": 4_000},
                    }},
                },
                {
                    "type": "assistant", "cwd": str(Path(tmp)), "sessionId": "claude-1",
                    "timestamp": "2026-08-30T14:59:30Z", "effort": "xhigh",
                    "message": {"role": "assistant", "model": "claude-opus-5", "content": "SECRET_OUTPUT_2", "usage": {
                        "input_tokens": 50_000, "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "output_tokens": 5_000, "output_tokens_details": {"thinking_tokens": 1_000},
                    }},
                },
                {"type": "result", "timestamp": "2026-08-30T14:59:31Z", "total_cost_usd": 1.25},
            ]
            write_jsonl(path, rows)

            result = activity.parse_claude_session(path, NOW)
            request = activity.pricing_request(result)

        self.assertEqual(result["status"], "active")
        self.assertEqual(result["usage"]["input_tokens"], 150_000)
        self.assertEqual(result["usage"]["cached_input_tokens"], 200_000)
        self.assertEqual(result["usage"]["cache_write_5m_input_tokens"], 10_000)
        self.assertEqual(result["usage"]["cache_write_1h_input_tokens"], 20_000)
        self.assertEqual(result["usage"]["output_tokens"], 15_000)
        self.assertEqual(result["cost_usd_reported"], 1.25)
        self.assertEqual(request["prompt_tokens"], 150_000)
        self.assertEqual(request["cache_read_input_tokens"], 200_000)
        self.assertEqual(request["cache_creation_input_tokens"], 30_000)
        self.assertEqual(request["cache_creation_1h_input_tokens"], 20_000)
        self.assertNotIn("SECRET", json.dumps(result))

    def test_claude_subagent_logs_are_marked_so_they_never_speak_for_the_session(self):
        # one sessionId spans the main log and <session>/subagents/agent-*.jsonl; only the main log may give model/effort/start
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            row = {"type": "user", "cwd": str(Path(tmp)), "sessionId": "s", "timestamp": "2026-08-30T14:00:00Z"}
            main, sub = Path(tmp, "s.jsonl"), Path(tmp, "s", "subagents", "agent-1.jsonl")
            sub.parent.mkdir(parents=True)
            write_jsonl(main, [row])
            write_jsonl(sub, [row])
            flagged = Path(tmp, "flag.jsonl")
            write_jsonl(flagged, [{**row, "isSidechain": True}])
            marks = [activity.parse_claude_session(p, NOW)["subagent"] for p in (main, sub, flagged)]
        self.assertEqual(marks, [False, True, True])

    def test_codex_children_and_reviews_report_their_root_session_as_subagents(self):
        # 200 of 247 commits were "ambiguous" because each subagent and auto-review thread competed with the thread that spawned it
        activity = self.module()
        spawn = {"subagent": {"thread_spawn": {"parent_thread_id": "root", "depth": 1}}}
        metas = {"root": {"thread_source": "user", "source": "vscode", "session_id": "root"},
                 "worker": {"thread_source": "subagent", "source": spawn, "parent_thread_id": "root", "session_id": "root"},
                 "review": {"thread_source": "guardian_review", "source": {"subagent": {"other": "guardian"}},
                            "parent_thread_id": "worker", "session_id": "root"},
                 "older": {"thread_source": "subagent", "source": spawn, "parent_thread_id": "root", "session_id": "older"}}
        with tempfile.TemporaryDirectory() as tmp:
            results = {}
            for thread, meta in metas.items():
                rows = codex_rows(thread, Path(tmp))
                rows[0]["payload"].update(meta)
                write_jsonl(Path(tmp, f"{thread}.jsonl"), rows)
                results[thread] = activity.parse_codex_session(Path(tmp, f"{thread}.jsonl"), NOW)
        self.assertEqual({t: (r["session_id"], r["log_id"], r["subagent"]) for t, r in results.items()},
                         {"root": ("root", "root", False), "worker": ("root", "worker", True), "review": ("root", "review", True),
                          "older": ("root", "older", True)})

    def test_codex_effort_segments_follow_turn_context_and_a_mixed_session_is_labelled_mixed(self):
        activity = self.module()
        epoch = lambda text: int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "mixed.jsonl")
            write_jsonl(path, codex_rows("mixed", Path(tmp)) + [
                {"timestamp": "2026-08-30T14:10:00Z", "type": "turn_context", "payload": {"model": "gpt-5.6-sol", "effort": "xhigh"}},
                {"timestamp": "2026-08-30T14:20:00Z", "type": "turn_context", "payload": {"model": "gpt-5.6-sol", "effort": "high"}}])
            result = activity.parse_codex_session(path, NOW)
            write_jsonl(path, codex_rows("one", Path(tmp)))
            same = activity.parse_codex_session(path, NOW)
        self.assertEqual((result["model"], result["effort"]), ("gpt-5.6-sol", "mixed"))
        self.assertEqual(result["effort_segments"], [[epoch("2026-08-30T14:00:02Z"), "gpt-5.6-sol", "xhigh"],
                                                     [epoch("2026-08-30T14:20:00Z"), "gpt-5.6-sol", "high"]])
        self.assertEqual((same["effort"], len(same["effort_segments"])), ("xhigh", 1))

    def test_compressed_codex_logs_are_read_and_counted_as_unread_without_a_decoder(self):
        # 2819 of 2879 local rollouts are *.jsonl.zst: compression.zstd (3.14+), else the zstd binary, else a visible count
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plain = root / "codex/rollout-z.jsonl"
            write_jsonl(plain, codex_rows("z", root))
            packed = Path(f"{plain}.zst")
            binary = shutil.which("zstd")
            if activity.ZSTD is not None:
                packed.write_bytes(activity.ZSTD.compress(plain.read_bytes()))
            elif binary:
                subprocess.run([binary, "-q", str(plain), "-o", str(packed)], check=True)
            else:
                self.skipTest("no zstd encoder")
            plain.unlink()
            os.utime(packed, (NOW.timestamp(), NOW.timestamp()))

            def collect(module, which):
                with mock.patch.object(activity, "ZSTD", module), mock.patch.object(activity.shutil, "which", lambda _: which):
                    result = activity.ActivityCollector(codex_root=root / "codex", claude_root=root / "x", kimi_root=root / "x",
                                                        gemini_root=root / "x", pricer=activity.HeadroomPricer(runner=lambda r: [])
                                                        ).collect([{"project_id": "p", "path": str(root)}], NOW)
                return result["projects"]["p"]["sessions"], [error["error"] for error in result["errors"]]

            if activity.ZSTD is not None:
                self.assertEqual(collect(activity.ZSTD, None), (1, []))
            if binary:
                self.assertEqual(collect(None, binary), (1, []))
            sessions, errors = collect(None, None)
        self.assertEqual(sessions, 0)
        self.assertEqual(errors, ["1 compressed log(s) not read: needs Python 3.14+ (compression.zstd) or the zstd binary"])

    def test_claude_session_opened_outside_a_repository_maps_to_the_repository_its_rows_move_into(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root, repo = Path(tmp), Path(tmp, "repo")
            (repo / "sub").mkdir(parents=True)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            row = {"type": "user", "sessionId": "c", "timestamp": "2026-08-30T14:00:00Z"}
            write_jsonl(root / "claude/c.jsonl", [{**row, "cwd": tmp}, {**row, "cwd": str(repo / "sub")}])
            collector = activity.ActivityCollector(codex_root=root / "x", claude_root=root / "claude", kimi_root=root / "x",
                                                   gemini_root=root / "x", pricer=activity.HeadroomPricer(runner=lambda r: []))
            result = collector.collect([{"project_id": "p", "path": str(repo)}], NOW)
        self.assertEqual(result["projects"]["p"]["sessions"], 1)
        self.assertEqual(result["projects"]["p"]["recent_sessions"][0]["cwds"], [tmp, str(repo / "sub")])

    def test_status_and_window_move_with_the_clock_when_the_log_does_not_change(self):
        # audit F05: a result cached by file size/mtime stayed "active" and kept tokens that had left the window
        activity = self.module()
        row = {"type": "assistant", "sessionId": "c", "message": {"id": "m1", "model": "claude-opus-5", "usage": {"input_tokens": 100, "output_tokens": 20}}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(root / "claude/c.jsonl", [{**row, "cwd": tmp, "timestamp": "2026-08-29T15:01:00Z"},
                                                   {**row, "cwd": tmp, "timestamp": "2026-08-30T14:59:30Z",
                                                    "message": {**row["message"], "id": "m2", "usage": {"input_tokens": 10, "output_tokens": 2}}}])
            collector = activity.ActivityCollector(codex_root=root / "x", claude_root=root / "claude", kimi_root=root / "x",
                                                   gemini_root=root / "x", pricer=activity.HeadroomPricer(runner=lambda r: []))
            now = collector.parse("claude", root / "claude/c.jsonl", NOW)
            later = collector.parse("claude", root / "claude/c.jsonl", NOW + timedelta(minutes=10))
        self.assertEqual((now["status"], now["usage"]["total_tokens"]), ("active", 132))
        self.assertEqual((later["status"], later["usage"]["total_tokens"]), ("idle", 12))

    def test_claude_counts_each_message_once_and_an_invalid_counter_is_unknown_not_zero(self):
        # audit F06: Claude Code writes one row per content block of a response, each with its usage (52% of local rows repeat an
        # earlier message id; the last row carries the final output count)
        activity = self.module()
        row = {"type": "assistant", "sessionId": "c", "timestamp": "2026-08-30T14:00:00Z"}
        usage = lambda output: {"model": "claude-opus-5", "id": "m1", "usage": {"input_tokens": 100, "output_tokens": output}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "c.jsonl")
            write_jsonl(path, [{**row, "cwd": tmp, "message": usage(5)}, {**row, "cwd": tmp, "message": usage(20)}])
            once = activity.parse_claude_session(path, NOW)
            write_jsonl(path, [{**row, "cwd": tmp, "message": {**usage(20), "usage": {"input_tokens": "invalid", "output_tokens": -10}}}])
            invalid = activity.parse_claude_session(path, NOW)
        self.assertEqual((once["usage"]["total_tokens"], once["usage"]["usage_complete"]), (120, True))
        self.assertFalse(invalid["usage"]["usage_complete"])
        self.assertIsNone(activity.pricing_request(invalid))

    def test_claude_usage_excludes_messages_before_window(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "claude-window.jsonl")
            rows = [
                {"type": "user", "cwd": str(Path(tmp)), "sessionId": "claude-window", "timestamp": "2026-08-28T12:00:00Z"},
                {"type": "assistant", "cwd": str(Path(tmp)), "sessionId": "claude-window", "timestamp": "2026-08-29T14:00:00Z", "message": {"model": "claude-opus-5", "usage": {"input_tokens": 999, "output_tokens": 999}}},
                {"type": "assistant", "cwd": str(Path(tmp)), "sessionId": "claude-window", "timestamp": "2026-08-30T14:00:00Z", "message": {"model": "claude-opus-5", "usage": {"input_tokens": 10, "output_tokens": 2}}},
            ]
            write_jsonl(path, rows)

            result = activity.parse_claude_session(path, NOW, lookback_hours=24)

        self.assertEqual(result["usage"]["input_tokens"], 10)
        self.assertEqual(result["usage"]["output_tokens"], 2)
        self.assertEqual(result["usage"]["total_tokens"], 12)

    def test_claude_counter_reset_keeps_cost_unknown(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "claude-cost-window.jsonl")
            write_jsonl(path, [
                {"type": "user", "cwd": str(Path(tmp)), "sessionId": "claude-cost", "timestamp": "2026-08-28T12:00:00Z"},
                {"type": "result", "timestamp": "2026-08-29T12:00:00Z", "total_cost_usd": 9.0},
                {"type": "result", "timestamp": "2026-08-30T13:00:00Z", "total_cost_usd": 1.0},
                {"type": "result", "timestamp": "2026-08-30T14:00:00Z", "total_cost_usd": 0.5},
            ])

            result = activity.parse_claude_session(path, NOW, lookback_hours=24)

        self.assertIsNone(result["cost_usd_reported"])

    def test_codex_repeated_cumulative_event_does_not_repeat_consumption(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "duplicate.jsonl")
            event = {"timestamp": "2026-08-30T14:05:00Z", "type": "event_msg", "payload": {
                "type": "token_count", "info": {
                    "total_token_usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                    "last_token_usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}}}}
            write_jsonl(path, codex_rows("duplicate", Path(tmp))[:4] + [event, event])
            result = activity.parse_codex_session(path, NOW)
        self.assertEqual(result["usage"]["total_tokens"], 120)

    def test_claude_cost_is_latest_session_total_not_sum_of_resumes(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "cost.jsonl")
            write_jsonl(path, [
                {"type": "user", "cwd": tmp, "sessionId": "cost", "timestamp": "2026-08-30T14:00:00Z"},
                {"type": "result", "timestamp": "2026-08-30T14:01:00Z", "total_cost_usd": 1.0},
                {"type": "result", "timestamp": "2026-08-30T14:02:00Z", "total_cost_usd": 1.0},
                {"type": "result", "timestamp": "2026-08-30T14:03:00Z", "total_cost_usd": 1.5},
            ])
            result = activity.parse_claude_session(path, NOW)
        self.assertEqual(result["cost_usd_reported"], 1.5)

    def test_claude_invalid_monetary_values_keep_the_session_and_usage(self):
        activity = self.module()
        for cost, expected in ((10 ** 400, None), (True, None), (-1, None), (float("inf"), None), (0, 0), (0.25, 0.25)):
            with self.subTest(cost_type=type(cost).__name__), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp, "reported-cost.jsonl")
                write_jsonl(path, [
                    {"type": "user", "cwd": tmp, "sessionId": "reported-cost", "timestamp": "2026-08-30T14:00:00Z"},
                    {"type": "assistant", "timestamp": "2026-08-30T14:01:00Z", "message": {
                        "id": "one", "model": "claude-test", "usage": {"input_tokens": 10, "output_tokens": 2}}},
                    {"type": "result", "timestamp": "2026-08-30T14:02:00Z", "total_cost_usd": cost}])
                result = activity.parse_claude_session(path, NOW)
                self.assertEqual(result["session_id"], "reported-cost")
                self.assertEqual(result["usage"]["total_tokens"], 12)
                self.assertEqual(result["cost_usd_reported"], expected)

    def test_claude_cost_window_rejects_rewinds_and_includes_the_cutoff(self):
        activity = self.module()
        cases = [("2026-08-28T12:00:00Z", [("2026-08-29T14:59:00Z", 1), ("2026-08-29T15:01:00Z", 2),
                                                         ("2026-08-29T14:59:30Z", 3)], None),
                 ("2026-08-28T12:00:00Z", [("2026-08-29T14:59:00Z", 1), ("2026-08-29T15:01:00Z", 2),
                                                         ("2026-08-29T15:02:00Z", 3)], 2),
                 ("2026-08-29T15:00:00Z", [("2026-08-29T15:00:00Z", 0.5), ("2026-08-29T15:01:00Z", 1)], 1)]
        for started, costs, expected in cases:
            with self.subTest(started=started, expected=expected), tempfile.TemporaryDirectory() as tmp:
                rows = [{"type": "user", "cwd": tmp, "sessionId": "cost-clock", "timestamp": started}]
                rows += [{"type": "result", "timestamp": stamp, "total_cost_usd": cost} for stamp, cost in costs]
                path = Path(tmp, "cost-clock.jsonl")
                write_jsonl(path, rows)
                self.assertEqual(activity.parse_claude_session(path, NOW)["cost_usd_reported"], expected)

    def test_untimed_claude_cost_cannot_establish_zero_or_a_window_delta(self):
        activity = self.module()
        for include_untimed, final, expected in ((True, 1, None), (True, 2, None),
                                                  (False, 1, 0), (False, 2, 1)):
            with self.subTest(untimed=include_untimed, final=final), tempfile.TemporaryDirectory() as tmp:
                rows = [
                    {"type": "user", "cwd": tmp, "sessionId": "untimed-cost",
                     "timestamp": "2026-08-28T12:00:00Z"},
                    {"type": "result", "timestamp": "2026-08-29T14:59:00Z", "total_cost_usd": 1},
                ]
                if include_untimed:
                    rows.append({"type": "result", "total_cost_usd": 0})
                rows.append({"type": "result", "timestamp": "2026-08-29T15:01:00Z", "total_cost_usd": final})
                rows.append({"type": "assistant", "timestamp": "2026-08-30T14:00:00Z", "message": {
                    "id": "one", "model": "claude-test", "usage": {"input_tokens": 10, "output_tokens": 2}}})
                filename = Path(tmp, "untimed-cost.jsonl")
                write_jsonl(filename, rows)
                result = activity.parse_claude_session(filename, NOW)
                self.assertEqual(result["cost_usd_reported"], expected)
                self.assertEqual(result["usage"]["total_tokens"], 12)
                self.assertTrue(result["usage"]["usage_complete"])
                summary = activity.summarize([result], 24)
                reported = expected is not None
                self.assertEqual(summary["reported_cost_sessions"], int(reported))
                self.assertEqual(summary["reported_cost_coverage"], int(reported))
                if reported:
                    self.assertEqual(summary["cost_usd_reported_sum"], expected)

    def test_activity_monetary_totals_remain_representable(self):
        activity = self.module()
        for amount, expected in ((1e308, None), (0.25, 0.5), (0, 0)):
            with self.subTest(amount=amount):
                sessions = [{"session_id": str(i), "status": "idle", "runtime_provider": "anthropic",
                             "model": "test", "effort": "medium", "usage": {**activity.empty_usage(), "usage_complete": True},
                             "cost_usd_reported": amount, "cost_usd_estimate": amount} for i in range(2)]
                result = activity.summarize(sessions, 24)
                self.assertEqual(result["cost_usd_reported_sum"], expected)
                self.assertEqual(result["cost_usd_known_sum"], expected)
                self.assertEqual(result["cost_usd_estimate"], expected)
                self.assertEqual(result["routes"][0]["cost_usd_estimate"], expected)
                json.dumps(result, allow_nan=False)

    def test_claude_window_cost_requires_a_cumulative_baseline(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "cost.jsonl")
            meta = {"type": "user", "cwd": tmp, "sessionId": "cost", "timestamp": "2026-08-28T14:00:00Z"}
            inside = [{"type": "result", "timestamp": "2026-08-30T14:01:00Z", "total_cost_usd": 10.0},
                      {"type": "result", "timestamp": "2026-08-30T14:02:00Z", "total_cost_usd": 10.5}]
            write_jsonl(path, [meta, {"type": "result", "timestamp": "2026-08-29T12:00:00Z", "total_cost_usd": 9.0}, *inside])
            self.assertEqual(activity.parse_claude_session(path, NOW)["cost_usd_reported"], 1.5)
            write_jsonl(path, [meta, *inside])
            self.assertIsNone(activity.parse_claude_session(path, NOW)["cost_usd_reported"])

    def test_kimi_session_normalizes_turn_usage(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp, "session-1", "state.json")
            write_json(state, {
                "id": "kimi-1", "cwd": tmp,
                "createdAt": int(NOW.timestamp() * 1000) - 60_000,
                "updatedAt": int(NOW.timestamp() * 1000),
                "lastTurnReason": "completed",
            })
            write_jsonl(state.parent / "agents/main/wire.jsonl", [
                {"type": "usage.record", "model": "kimi-code/k3", "time": int(NOW.timestamp() * 1000), "usage": {
                    "inputOther": 100, "inputCacheRead": 200,
                    "inputCacheCreation": 30, "output": 40,
                }},
            ])

            result = activity.parse_kimi_session(state, NOW)
            request = activity.pricing_request(result)

        self.assertEqual(result["session_id"], "kimi-1")
        self.assertEqual(result["source"], "kimi")
        self.assertEqual(result["runtime_provider"], "moonshot")
        self.assertEqual(result["model"], "kimi-code/k3")
        self.assertEqual(result["usage"]["total_tokens"], 370)
        self.assertEqual(request["prompt_tokens"], 100)
        self.assertEqual(request["completion_tokens"], 40)

    def test_gemini_session_normalizes_usage_and_project_mapping(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "tmp/project-slug/chats/session-1.jsonl")
            write_jsonl(path, [
                {"sessionId": "gemini-1", "projectHash": "project-slug", "startTime": "2026-08-30T14:00:00Z"},
                {"type": "gemini", "timestamp": "2026-08-30T14:01:00Z", "model": "gemini-3.1-flash-lite", "tokens": {
                    "input": 100, "cached": 40, "output": 20,
                    "thoughts": 5, "tool": 3, "total": 128,
                }},
            ])

            result = activity.parse_gemini_session(path, tmp, NOW)
            request = activity.pricing_request(result)

        self.assertEqual(result["session_id"], "gemini-1")
        self.assertEqual(result["source"], "gemini")
        self.assertEqual(result["runtime_provider"], "google")
        self.assertEqual(result["cwd"], tmp)
        self.assertEqual(result["usage"]["input_tokens"], 103)
        self.assertEqual(result["usage"]["total_tokens"], 128)
        self.assertEqual(request["prompt_tokens"], 63)
        self.assertEqual(request["cache_read_input_tokens"], 40)
        self.assertEqual(request["completion_tokens"], 25)

    def test_active_intervals_merge_close_timestamps_and_cap_by_merging_the_closest(self):
        # Marcus, 2026-10-25: a session resumed over days (271 h) must not own every commit of its span; only its active stretches.
        activity = self.module()
        stamps = [5100, 0, 100, 2000, 5000, 100.9]
        self.assertEqual(activity.active_intervals(stamps, gap_s=1800), [[0, 100], [2000, 2000], [5000, 5100]])
        self.assertEqual(activity.active_intervals(stamps, gap_s=1800, cap=2), [[0, 2000], [5000, 5100]])
        self.assertEqual(activity.active_intervals(stamps, gap_s=1800, cap=1), [[0, 5100]])
        self.assertEqual(activity.active_intervals([], gap_s=1800), [])
        self.assertEqual(activity.MAX_INTERVALS, 500)
        self.assertEqual(len(activity.active_intervals(range(0, 10_000_000, 3600), gap_s=1800)), 500)

    def test_every_parser_emits_active_intervals_from_row_timestamps_only(self):
        activity = self.module()
        epoch = lambda text: int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
        with tempfile.TemporaryDirectory() as tmp:
            codex = Path(tmp, "codex.jsonl")
            write_jsonl(codex, codex_rows("codex-1", Path(tmp)) + [
                {"timestamp": "2026-08-30T14:40:00Z", "type": "event_msg", "payload": {"type": "task_started"}}])
            claude = Path(tmp, "claude.jsonl")
            write_jsonl(claude, [
                {"type": "user", "cwd": tmp, "sessionId": "c", "timestamp": "2026-08-30T10:00:00Z", "message": {"content": "SECRET"}},
                {"type": "assistant", "cwd": tmp, "sessionId": "c", "timestamp": "2026-08-30T10:20:00Z",
                 "message": {"model": "claude-opus-5", "content": "SECRET"}},
                {"type": "user", "cwd": tmp, "sessionId": "c", "timestamp": "2026-08-30T14:00:00Z", "message": {"content": "SECRET"}}])
            gemini = Path(tmp, "gemini.jsonl")
            write_jsonl(gemini, [{"sessionId": "g", "startTime": "2026-08-30T12:00:00Z"},
                                 {"type": "gemini", "timestamp": "2026-08-30T12:10:00Z", "model": "gm", "tokens": {"total": 1}},
                                 {"type": "user", "timestamp": "2026-08-30T13:00:00Z"}])
            kimi = Path(tmp, "kimi/state.json")
            write_json(kimi, {"id": "k", "cwd": tmp, "createdAt": 0, "updatedAt": 0})
            hour = 3_600_000
            write_jsonl(kimi.parent / "agents/main/wire.jsonl", [{"type": "turn.prompt", "time": epoch("2026-08-30T09:00:00Z") * 1000},
                                                                 {"type": "turn.ended", "time": epoch("2026-08-30T09:00:00Z") * 1000 + hour}])
            results = {"codex": activity.parse_codex_session(codex, NOW), "claude": activity.parse_claude_session(claude, NOW),
                       "gemini": activity.parse_gemini_session(gemini, tmp, NOW), "kimi": activity.parse_kimi_session(kimi, NOW)}
        self.assertEqual(results["codex"]["active_intervals"], [[epoch("2026-08-30T14:00:00Z"), epoch("2026-08-30T14:05:01Z")],
                                                                [epoch("2026-08-30T14:40:00Z")] * 2])
        self.assertEqual(results["claude"]["active_intervals"], [[epoch("2026-08-30T10:00:00Z"), epoch("2026-08-30T10:20:00Z")],
                                                                 [epoch("2026-08-30T14:00:00Z")] * 2])
        self.assertEqual(results["gemini"]["active_intervals"], [[epoch("2026-08-30T12:00:00Z"), epoch("2026-08-30T12:10:00Z")],
                                                                 [epoch("2026-08-30T13:00:00Z")] * 2])
        self.assertEqual(results["kimi"]["active_intervals"], [[epoch("2026-08-30T09:00:00Z")] * 2, [epoch("2026-08-30T10:00:00Z")] * 2])
        self.assertNotIn("SECRET", json.dumps(results))
        for result in results.values():
            self.assertTrue(all(isinstance(x, int) for pair in result["active_intervals"] for x in pair))

    def test_log_over_4_mib_keeps_its_real_pauses_instead_of_one_interval_from_the_start(self):
        # the unread head of a clipped log counted as active: one fake 291 h interval instead of 34 real ones (58 h)
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "codex-large.jsonl")
            rows = codex_rows("codex-clipped", Path(tmp))[:1] + [
                {"type": "response_item", "payload": {"padding": "x" * (4 * 1024 * 1024)}},
                {"timestamp": "2026-08-30T18:02:00Z", "type": "turn_context", "payload": {"model": "m", "effort": "low"}},
                {"timestamp": "2026-08-30T18:03:00Z", "type": "event_msg", "payload": {"type": "task_complete"}}]
            write_jsonl(path, rows)
            result = activity.parse_codex_session(path, NOW)
        start = int(datetime(2026, 8, 30, 14, 0, tzinfo=timezone.utc).timestamp())
        self.assertEqual(result["active_intervals"], [[start, start], [start + 4 * 3600 + 120, start + 4 * 3600 + 180]])

    def test_collector_reads_a_growing_log_from_its_cursor_and_waits_for_a_torn_row(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "codex/grow.jsonl"
            lines = [json.dumps(row) + "\n" for row in codex_rows("grow", root)]
            collector = activity.ActivityCollector(codex_root=root / "codex", claude_root=root / "x", kimi_root=root / "x",
                                                   gemini_root=root / "x", pricer=activity.HeadroomPricer(runner=lambda r: []))
            path.parent.mkdir()
            for chunk in ("".join(lines[:3]), "".join(lines[3:5]) + lines[5][:20], lines[5][20:]):
                with path.open("a") as handle:
                    handle.write(chunk)
                collector.parse("codex", path, NOW)
            self.assertEqual(collector.cursors[path][1], path.stat().st_size)
            self.assertEqual(collector.parse("codex", path, NOW), activity.parse_codex_session(path, NOW))

    def test_collector_detects_same_inode_rewrites_even_with_unchanged_edges(self):
        activity = self.module()
        for kind in ("equal", "regrown", "middle"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root, path = Path(tmp), Path(tmp, "rewrite.jsonl")
                rows = codex_rows("old-id", root, model="model-a")
                rows[1]["payload"]["content"] = "x" * 8192
                rows[-1]["payload"]["padding"] = "y" * 8192
                write_jsonl(path, rows)
                before = path.read_bytes()
                inode = path.stat().st_ino
                collector = activity.ActivityCollector(pricer=activity.HeadroomPricer(runner=lambda r: []))
                collector.parse("codex", path, NOW)
                if kind == "middle":
                    rows[2]["payload"]["model"] = "model-b"
                else:
                    rows[0]["payload"]["id"] = "new-id"
                if kind == "regrown":
                    rows.append({"type": "ignored", "padding": "longer replacement"})
                write_jsonl(path, rows)
                self.assertEqual(path.stat().st_ino, inode)
                if kind == "middle":
                    self.assertEqual(before[:4096], path.read_bytes()[:4096])
                    self.assertEqual(before[-4096:], path.read_bytes()[-4096:])
                self.assertEqual(collector.parse("codex", path, NOW), activity.parse_codex_session(path, NOW))

    def test_a_successful_decoder_recovery_clears_the_prior_unreadable_marker(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root, path = Path(tmp), Path(tmp, "recover.jsonl.zst")
            path.write_bytes(b"synthetic-decoder-fixture")
            collector = activity.ActivityCollector(pricer=activity.HeadroomPricer(runner=lambda requests: []))
            with mock.patch.object(activity, "read_log", side_effect=activity.UnreadableLog("synthetic-unavailable")):
                self.assertIsNone(collector.parse("codex", path, NOW))
            self.assertIn(path, collector.unreadable)

            def recovered(source, parser, offset=0, digest=None):
                for row in codex_rows("recovered", root):
                    parser.feed(row)
                return path.stat().st_size

            with mock.patch.object(activity, "read_log", side_effect=recovered):
                self.assertEqual(collector.parse("codex", path, NOW)["session_id"], "recovered")
            self.assertNotIn(path, collector.unreadable)

    def test_concurrent_collection_does_not_mix_old_usage_with_new_route_metadata(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root, path = Path(tmp), Path(tmp, "codex", "concurrent.jsonl")
            write_jsonl(path, codex_rows("concurrent", root, model="model-a"))
            collector = activity.ActivityCollector(codex_root=path.parent, claude_root=root / "none",
                                                   kimi_root=root / "none", gemini_root=root / "none",
                                                   pricer=activity.HeadroomPricer(runner=lambda requests: []))
            entries = [{"project_id": "p", "path": str(root)}]
            entered, release, second_done = threading.Event(), threading.Event(), threading.Event()
            original_labels, results, errors = activity.labels, {}, []

            def labels(segments):
                if threading.current_thread().name == "old-snapshot":
                    entered.set()
                    release.wait(5)
                return original_labels(segments)

            def collect(name):
                try:
                    results[name] = collector.collect(entries, NOW)["projects"]["p"]["recent_sessions"][0]
                except Exception as error:
                    errors.append(type(error).__name__)
                finally:
                    if name == "second":
                        second_done.set()

            first = threading.Thread(target=collect, args=("first",), name="old-snapshot")
            second = threading.Thread(target=collect, args=("second",))
            with mock.patch.object(activity, "labels", side_effect=labels):
                first.start()
                try:
                    self.assertTrue(entered.wait(5))
                    with path.open("a") as handle:
                        handle.write(json.dumps({"timestamp": "2026-08-30T14:06:00Z", "type": "turn_context",
                                                 "payload": {"model": "model-b", "effort": "low"}}) + "\n")
                    second.start()
                    second_done.wait(1)
                finally:
                    release.set()
                    first.join(5)
                    if second.ident is not None:
                        second.join(5)
            self.assertFalse(first.is_alive() or second.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual((results["first"]["model"], results["first"]["usage"]["total_tokens"]), ("model-a", 1_100_000))
            self.assertEqual(results["second"]["model"], "mixed")

    def test_collector_applies_the_activity_gap_parameter(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(root / "codex/s.jsonl", codex_rows("s", root) + [
                {"timestamp": "2026-08-30T14:40:00Z", "type": "event_msg", "payload": {"type": "task_started"}}])
            values = {}
            for minutes in (30, 60):
                collector = activity.ActivityCollector(codex_root=root / "codex", claude_root=root / "claude", kimi_root=root / "kimi",
                                                       gemini_root=root / "gemini", pricer=activity.HeadroomPricer(runner=lambda r: []),
                                                       activity_gap_minutes=minutes)
                (_, path), = collector.candidates(NOW)
                values[minutes] = len(collector.parse("codex", path, NOW)["active_intervals"])
        self.assertEqual(values, {30: 2, 60: 1})

    def test_summary_keeps_provider_reported_cost_separate_from_rate_card(self):
        activity = self.module()
        sessions = [{
            "status": "idle", "runtime_provider": "anthropic",
            "model": "claude-opus-5", "effort": "xhigh",
            "usage": activity.empty_usage(),
            "cost_usd_estimate": 2.0, "cost_usd_reported": 1.5,
        }]

        result = activity.summarize(sessions, 24)

        self.assertEqual(result["cost_usd_estimate"], 2.0)
        self.assertEqual(result["cost_usd_reported_sum"], 1.5)
        self.assertEqual(result["reported_cost_coverage"], 1.0)

    def test_collector_discovers_kimi_and_gemini_for_registered_project(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root, repo = Path(tmp), Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            kimi = root / "kimi/session-1/state.json"
            write_json(kimi, {"id": "kimi-1", "cwd": str(repo), "createdAt": int(NOW.timestamp() * 1000), "updatedAt": int(NOW.timestamp() * 1000), "lastTurnReason": "completed"})
            write_jsonl(kimi.parent / "agents/main/wire.jsonl", [{"type": "usage.record", "model": "kimi-code/k3", "time": int(NOW.timestamp() * 1000), "usage": {"inputOther": 1, "output": 1}}])
            gemini = root / "gemini"
            write_json(gemini / "projects.json", {"projects": {str(repo): "repo-slug"}})
            write_jsonl(gemini / "tmp/repo-slug/chats/session-1.jsonl", [
                {"sessionId": "gemini-1", "startTime": "2026-08-30T14:00:00Z"},
                {"type": "gemini", "timestamp": "2026-08-30T14:01:00Z", "model": "gemini-3.1-flash-lite", "tokens": {"input": 1, "output": 1, "total": 2}},
            ])
            collector = activity.ActivityCollector(
                codex_root=root / "codex", claude_root=root / "claude",
                kimi_root=root / "kimi", gemini_root=gemini,
                pricer=activity.HeadroomPricer(runner=lambda rows: [{"cost_usd": 1} for _ in rows]),
            )

            result = collector.collect([{"project_id": "p", "name": "Repo", "path": str(repo), "registered_at": "2026-08-30T12:00:00Z"}], NOW)

        self.assertEqual(result["projects"]["p"]["sessions"], 2)
        self.assertEqual({item["source"] for item in result["projects"]["p"]["recent_sessions"]}, {"kimi", "gemini"})

    def test_headroom_pricer_is_batch_cached_and_unknown_model_is_unpriced(self):
        activity = self.module()
        calls = []

        def runner(requests):
            calls.append(requests)
            return [
                {
                    "cost_usd": 10.0,
                    "pricing_model": "gpt-5.6-sol",
                    "pricing_source": "headroom/litellm",
                    "pricing_version": "headroom=0.36.5;litellm=1.98.0",
                },
                {
                    "cost_usd": None,
                    "pricing_model": None,
                    "pricing_source": "headroom/litellm",
                    "pricing_version": "headroom=0.36.5;litellm=1.98.0",
                },
            ]

        pricer = activity.HeadroomPricer(runner=runner)
        sessions = [
            {"model": "gpt-5.6-sol", "usage": codex_rows("a", "/tmp")[-2]["payload"]["info"]["total_token_usage"] | {"input_includes_cache": True}},
            {"model": "unknown-model", "usage": {"input_tokens": 1000, "input_includes_cache": True}},
        ]

        first = pricer.quote(sessions)
        second = pricer.quote(sessions)

        self.assertEqual(first[0]["cost_usd"], 10.0)
        self.assertIsNone(first[1]["cost_usd"])
        self.assertEqual(second, first)
        self.assertEqual(len(calls), 1)

    def test_collector_maps_worktree_and_keeps_unpriced_cost_unknown(self):
        activity = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            worktree = root / "worktree"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-qm", "init"],
                cwd=repo, check=True,
            )
            subprocess.run(["git", "worktree", "add", "-qb", "test-worktree", str(worktree)], cwd=repo, check=True)
            codex_root = root / "codex"
            claude_root = root / "claude"
            write_jsonl(codex_root / "priced.jsonl", codex_rows("priced", worktree))
            write_jsonl(codex_root / "unpriced.jsonl", codex_rows("unpriced", repo, "codex-auto-review"))
            write_jsonl(codex_root / "other.jsonl", codex_rows("other", root / "unrelated"))
            def price(sessions):
                return [
                    {"cost_usd": 10.0, "pricing_source": "headroom/litellm"}
                    if item["model"] == "gpt-5.6-sol"
                    else {"cost_usd": None, "pricing_source": "headroom/litellm"}
                    for item in sessions
                ]

            collector = activity.ActivityCollector(
                codex_root=codex_root,
                claude_root=claude_root,
                kimi_root=root / "kimi",
                gemini_root=root / "gemini",
                pricer=activity.HeadroomPricer(runner=price),
                lookback_hours=24,
            )
            entries = [{
                "project_id": "project-1", "name": "Repo", "path": str(repo),
                "registered_at": "2026-08-30T12:00:00Z",
            }]

            result = collector.collect(entries, NOW)

        project = result["projects"]["project-1"]
        self.assertEqual(project["sessions"], 2)
        self.assertEqual(project["tokens_total"], 2_200_000)
        self.assertEqual(project["priced_sessions"], 1)
        self.assertEqual(project["unpriced_sessions"], 1)
        self.assertEqual(project["pricing_coverage"], 0.5)
        self.assertEqual(project["cost_usd_known_sum"], 10.0)
        self.assertIsNone(project["cost_usd_estimate"])
        self.assertEqual({item["session_id"] for item in project["recent_sessions"]}, {"priced", "unpriced"})


if __name__ == "__main__":
    unittest.main()
