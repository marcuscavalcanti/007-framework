import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
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
