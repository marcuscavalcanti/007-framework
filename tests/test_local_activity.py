import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


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

    def test_claude_reported_cost_sums_results_inside_window(self):
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

        self.assertEqual(result["cost_usd_reported"], 1.5)

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
