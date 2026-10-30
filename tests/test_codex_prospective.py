"""Protocol counterproofs over literal synthetic messages, without native IO."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib
import io
import json
import unittest
from unittest.mock import patch

NOW = "2026-10-17T00:00:00Z"
PRODUCER = dict(namespace="codex-app-server-v2", adapter="codex-app-server", surface="terminal",
                host_version="0.160.1", session_id="session-a", thread_id="thread-a")


def state():
    return dict(phase="sent", request_id="dispatch-a", producer=copy.deepcopy(PRODUCER),
                turn_id=None, pending=[], events=[], gaps=[], stream_bytes=0, message_count=0, usage=None)


def usage(input=100, cached=40, output=30, reasoning=10, total=None, turn="turn-a", thread="thread-a", **extra):
    breakdown = dict(inputTokens=input, cachedInputTokens=cached, outputTokens=output, reasoningOutputTokens=reasoning,
                     totalTokens=input + output if total is None else total, **extra)
    return {"method": "thread/tokenUsage/updated", "params": {"threadId": thread, "turnId": turn, "tokenUsage": {
        "total": breakdown, "last": copy.deepcopy(breakdown), "modelContextWindow": 1000}}}


def notification(method="turn/started", status="inProgress", turn="turn-a", thread="thread-a"):
    return {"method": method, "params": {"threadId": thread, "turn": {
        "id": turn, "status": status, "items": []}}}


def reply(request="dispatch-a", turn="turn-a"):
    return {"id": request, "result": {"turn": {"id": turn, "status": "inProgress", "items": []}}}


ISOLATED = {"type": "workspaceWrite", "writableRoots": [], "networkAccess": False,
            "excludeSlashTmp": True, "excludeTmpdirEnvVar": True}


def bootstrap():
    return {"id": "bootstrap-a", "result": {"thread": {
        "id": "thread-a", "sessionId": "session-a", "cliVersion": "0.160.1", "cwd": "/synthetic",
        "ephemeral": True, "turns": [], "parentThreadId": None, "forkedFromId": None},
        "cwd": "/synthetic", "model": "fixture-model", "modelProvider": "fixture", "reasoningEffort": None,
        "approvalPolicy": "never", "approvalsReviewer": "user", "sandbox": copy.deepcopy(ISOLATED),
        "instructionSources": []}}


class ProtocolTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module("codex_prospective")
        except ModuleNotFoundError:
            self.fail("bounded protocol projection is missing")

    def project(self, value):
        return self.module().project_frame(json.dumps(value).encode(), channel="stdout", observed_at=NOW)

    def advance(self, initial, *values):
        result = initial
        for value in values:
            result = self.module().reduce_message(result, self.project(value))
        return result

    def test_bootstrap_requires_isolated_workspace_write_and_no_loaded_instructions(self):
        # Schema 0.160.1: the producer must write its output, but only inside the checkout, offline, with no
        # instruction files loaded into the thread (effective context).
        omitted = bootstrap()
        omitted["result"]["sandbox"] = {"type": "workspaceWrite", "excludeSlashTmp": True, "excludeTmpdirEnvVar": True}
        del omitted["result"]["instructionSources"]
        for value in (bootstrap(), omitted):
            self.assertEqual(self.project(value)["kind"], "bootstrap")
        for change in ({"sandbox": {"type": "readOnly"}}, {"sandbox": {"type": "dangerFullAccess"}},
                       {"sandbox": dict(ISOLATED, networkAccess=True)}, {"sandbox": dict(ISOLATED, writableRoots=["/tmp"])},
                       {"sandbox": dict(ISOLATED, excludeSlashTmp=False)}, {"sandbox": dict(ISOLATED, excludeTmpdirEnvVar=False)},
                       {"sandbox": dict(ISOLATED, unknown=True)}, {"sandbox": dict(ISOLATED, networkAccess=0)},
                       {"instructionSources": ["/home/user/.codex/AGENTS.md"]}):
            bad = bootstrap()
            bad["result"].update(change)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "^protocol-invalid$"):
                self.project(bad)

    def test_schema_content_and_metadata_notifications_are_discarded(self):
        secret = "PRIVATE-CONTENT"
        frames = [{"method": method, "params": {"threadId": "thread-a", "turnId": "turn-a", "delta": secret}}
                  for method in ("item/plan/delta", "item/reasoning/summaryPartAdded", "item/commandExecution/outputDelta",
                                 "item/fileChange/outputDelta", "item/fileChange/patchUpdated", "turn/diff/updated",
                                 "turn/plan/updated")]
        frames += [{"method": "thread/status/changed", "params": {"threadId": "thread-a", "status": {"type": "active"}}},
                   {"method": "account/rateLimits/updated", "params": {"rateLimits": {"note": secret}}},
                   {"method": "item/started", "params": {"threadId": "thread-a", "turnId": "turn-a", "startedAtMs": 1,
                                                         "item": {"type": "plan", "id": "item-p", "text": secret}}}]
        for frame in frames:
            with self.subTest(method=frame["method"]):
                projected = self.project(frame)
                self.assertEqual(projected["kind"], "ignored")
                self.assertNotIn(secret, json.dumps(projected))

    def test_token_usage_is_normalized_and_invalid_numbers_become_unavailable(self):
        # Plan Task 12: same keys and rules as cli_telemetry for Codex; bad numbers are N/A, not a protocol failure.
        projected = self.project(usage(cacheWriteInputTokens=5))
        self.assertEqual((projected["kind"], projected["thread_id"], projected["turn_id"]), ("usage", "thread-a", "turn-a"))
        self.assertEqual(projected["total"], dict(input_tokens=100, cached_input_tokens=40, cache_write_input_tokens=5,
                                                  output_tokens=30, reasoning_output_tokens=10, total_tokens=130))
        self.assertEqual(set(projected), {"kind", "wire_bytes", "thread_id", "turn_id", "total"})
        self.assertEqual(self.project(usage())["total"]["cache_write_input_tokens"], 0)
        missing = usage()
        del missing["params"]["tokenUsage"]["total"]["outputTokens"]
        for bad in (usage(input=-1), usage(input=True), usage(cached=101), usage(reasoning=31), usage(total=131),
                    usage(output=2 ** 53), usage(cacheWriteInputTokens=-1), missing):
            with self.subTest(bad=bad["params"]["tokenUsage"]["total"]):
                self.assertIsNone(self.project(bad)["total"])
        for key in ("threadId", "turnId"):
            bad = usage()
            del bad["params"][key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "^protocol-invalid$"):
                self.project(bad)

    def test_token_usage_is_bound_to_the_turn_monotonic_and_definitive_when_inconsistent(self):
        bound = self.advance(state(), reply(), notification())
        first = self.advance(bound, usage(), usage())
        self.assertEqual((first["usage"]["total_tokens"], first["gaps"]), (130, []))
        later = self.advance(first, usage(input=200, output=50), notification("turn/completed", "completed"),
                             usage(input=250, output=50))
        self.assertEqual((later["phase"], later["usage"]["total_tokens"]), ("terminal-observed", 300))
        broken = self.advance(first, usage(input=90), usage(input=500, output=50))
        self.assertEqual((broken["usage"], broken["gaps"]), (None, ["usage-inconsistent"]))
        invalid = self.advance(first, usage(total=1), usage(input=500, output=50))
        self.assertEqual((invalid["usage"], invalid["gaps"]), (None, ["usage-invalid"]))
        for bad in (usage(turn="other"), usage(thread="other")):
            with self.subTest(bad=bad["params"]), self.assertRaisesRegex(ValueError, "^protocol-invalid$"):
                self.advance(bound, bad)
        unbound = self.advance(state(), usage())
        self.assertEqual((unbound["usage"], unbound["gaps"]), (None, ["usage-unbound"]))
        self.assertEqual(self.advance(state(), notification(), usage())["usage"]["total_tokens"], 130)

    def test_remote_control_status_is_ignored_only_when_disabled(self):
        # r29 probe: 0.160.1 emits remoteControl/status/changed unprompted (plan Task 10); a live remote link is external steering.
        def frame(**params):
            return {"method": "remoteControl/status/changed", "params": params}
        identity = dict(installationId="PRIVATE-INSTALL", serverName="PRIVATE-SERVER", environmentId=None)
        projected = self.project(frame(status="disabled", **identity))
        self.assertEqual(projected["kind"], "ignored")
        self.assertNotIn("PRIVATE", json.dumps(projected))
        for status in ("connecting", "connected", "errored"):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "^protocol-unsupported$"):
                self.project(frame(status=status, **identity))
        with self.assertRaisesRegex(ValueError, "^protocol-invalid$"):
            self.project(frame(**identity))

    def test_file_and_command_items_record_one_gap_and_other_surfaces_refuse(self):
        def item(method, kind):
            stamp = {"startedAtMs": 1} if method == "item/started" else {"completedAtMs": 2}
            return {"method": method, "params": dict(stamp, threadId="thread-a", turnId="turn-a",
                                                    item={"type": kind, "id": "item-1", "status": "inProgress"})}
        bound = self.advance(state(), reply(), notification())
        after = self.advance(bound, item("item/started", "fileChange"), item("item/completed", "fileChange"),
                             item("item/started", "commandExecution"))
        self.assertEqual((after["gaps"], after["events"]), (["tool-unqualified"], bound["events"]))
        self.assertEqual(self.advance(after, notification("turn/completed", "completed"))["phase"], "terminal-observed")
        with self.assertRaisesRegex(ValueError, "^protocol-invalid$"):
            self.advance(bound, {"method": "item/started", "params": dict(item("item/started", "fileChange")["params"],
                                                                           threadId="other")})
        for kind in ("mcpToolCall", "webSearch", "collabAgentToolCall", "subAgentActivity", "dynamicToolCall"):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "^protocol-unsupported$"):
                self.project(item("item/started", kind))
        for method in ("hook/started", "model/rerouted", "mcpServer/startupStatus/updated", "thread/settings/updated", "error"):
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, "^protocol-unsupported$"):
                self.project({"method": method, "params": {"threadId": "thread-a"}})

    def test_notification_before_response_waits_for_exact_request(self):
        pending = self.advance(state(), notification())
        self.assertEqual(pending["phase"], "sent")
        self.assertIsNone(pending["turn_id"])
        self.assertEqual(pending["events"], [])
        bound = self.advance(pending, reply())
        self.assertEqual(bound["phase"], "bound")
        self.assertEqual(bound["turn_id"], "turn-a")
        self.assertEqual(len(bound["events"]), 1)
        with self.assertRaisesRegex(ValueError, "^protocol-invalid$"):
            self.advance(pending, reply(request="other"))

    def test_duplicate_and_conflicting_ids_do_not_rebind(self):
        bound = self.advance(state(), reply(), notification(), notification(), reply())
        self.assertEqual(len(bound["events"]), 1)
        for bad in (reply(turn="other"), notification(turn="other"), notification(thread="other")):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "^protocol-invalid$"):
                self.advance(bound, bad)
        done = self.advance(bound, notification("turn/completed", "completed"))
        self.assertEqual(done["phase"], "terminal-observed")
        self.assertEqual(len(self.advance(done, notification("turn/completed", "completed"))["events"]), 2)
        with self.assertRaisesRegex(ValueError, "^protocol-invalid$"):
            self.advance(done, notification("turn/completed", "failed"))

    def test_premature_terminal_does_not_close(self):
        for initial in (state(), self.advance(state(), reply()), self.advance(state(), notification())):
            with self.assertRaisesRegex(ValueError, "^protocol-invalid$"):
                self.advance(initial, notification("turn/completed", "completed"))

    def test_protocol_provenance_is_not_hook_semantics(self):
        module = self.module()
        projected = self.project(bootstrap())
        self.assertEqual(projected["session_id"], "session-a")
        self.assertNotEqual(projected["session_id"], projected["thread_id"])
        start = module.to_native_event(self.project(notification()), producer=PRODUCER, observed_at=NOW)
        self.assertEqual(start["adapter"], "codex-app-server")
        self.assertEqual(start["kind"], "turn_start")
        self.assertIn("runtime-unqualified", start["gaps"])
        stop = module.to_native_event(self.project(notification("turn/completed", "completed")),
                                      producer=PRODUCER, observed_at=NOW)
        self.assertEqual(stop["kind"], "turn_stop")
        self.assertNotIn("accepted", stop)
        bad = bootstrap()
        del bad["result"]["thread"]["sessionId"]
        with self.assertRaisesRegex(ValueError, "^protocol-invalid$"):
            self.project(bad)

    def test_unsupported_tool_child_steer_resume_or_route_change_disqualifies(self):
        # r28: commandExecution/fileChange became a recorded gap (plan Task 9); unqualified tools still disqualify.
        for method in ("turn/steer", "thread/resume", "thread/fork", "model/changed", "item/started"):
            bad = {"method": method, "params": {"threadId": "thread-a", "turnId": "turn-a",
                    "item": {"id": "tool-a", "type": "mcpToolCall", "status": "inProgress"}}}
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, "^protocol-unsupported$"):
                self.advance(state(), bad)
        for key, value in (("parentThreadId", "parent"), ("forkedFromId", "old"),
                           ("turns", [{}]), ("cliVersion", "other"), ("ephemeral", False)):
            bad = bootstrap()
            bad["result"]["thread"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.project(bad)

    def test_sensitive_frames_never_reach_hash_disk_or_output(self):
        module = self.module()
        output, error = io.StringIO(), io.StringIO()
        hashes = []
        for sentinel in ("PRIVATE-AAAA", "PRIVATE-BBBB"):
            raw = notification()
            raw["params"]["turn"]["items"] = [{"type": "reasoning", "text": sentinel}]
            raw["params"].update(prompt=sentinel, transcript_path=sentinel)
            with redirect_stdout(output), redirect_stderr(error):
                event = module.to_native_event(self.project(raw), producer=PRODUCER, observed_at=NOW)
                self.assertNotIn(sentinel, json.dumps(event))
                hashes.append(event["event_key"])
                projected = module.project_frame(sentinel.encode(), channel="stderr", observed_at=NOW)
                self.assertNotIn(sentinel, json.dumps(projected))
                with self.assertRaisesRegex(ValueError, "^protocol-invalid$"):
                    self.project({"id": "dispatch-a", "error": {"message": sentinel}})
        self.assertEqual(hashes[0], hashes[1])
        self.assertEqual(output.getvalue() + error.getvalue(), "")

    def test_stream_limits_and_duplicate_json_keys_fail_closed(self):
        module = self.module()
        for raw in (b'{"id":"a","id":"b"}', b'\xff', b'{', b'x' * (1024 * 1024 + 1)):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                module.project_frame(raw, channel="stdout", observed_at=NOW)
        for count, size in ((2000, 0), (0, 32 * 1024 * 1024)):
            initial = state()
            initial.update(message_count=count, stream_bytes=size)
            with self.assertRaisesRegex(ValueError, "^protocol-limit$"):
                module.reduce_message(initial, module.project_frame(b'x', channel="stderr", observed_at=NOW))
        initial = state()
        initial.update(message_count=1999, stream_bytes=32 * 1024 * 1024 - 1)
        result = module.reduce_message(initial, module.project_frame(b'x', channel="stderr", observed_at=NOW))
        self.assertEqual(result["message_count"], 2000)
        self.assertEqual(result["stream_bytes"], 32 * 1024 * 1024)
        self.assertEqual(len(module.project_frame(b'x' * (1024 * 1024), channel="stderr", observed_at=NOW)), 2)

    def test_snapshot_tool_and_invalid_id_are_rejected_before_hash(self):
        # Explicit rule change (review r25-r32 R7): snapshots follow the Task 9 item policy — plan is a message item,
        # fileChange/commandExecution record the tool-unqualified gap once, any other item type still refuses; no content kept.
        module = self.module()
        def snapshot(value, items):
            turn = value["result"]["turn"] if "result" in value else value["params"]["turn"]
            turn["items"] = items
            return value
        tools = [{"type": "commandExecution", "command": "PRIVATE-SENTINEL"}, {"type": "fileChange", "changes": "PRIVATE-SENTINEL"},
                 {"type": "plan", "text": "PRIVATE-SENTINEL"}]
        for value in (reply(), notification(), notification("turn/completed", "completed")):
            projected = self.project(snapshot(value, tools))
            self.assertNotIn("PRIVATE", json.dumps(projected))
            with self.assertRaisesRegex(ValueError, "^protocol-unsupported$"):
                self.project(snapshot(value, [{"type": "mcpToolCall", "tool": "PRIVATE-SENTINEL"}]))
        bound = self.advance(state(), snapshot(reply(), tools), notification(),
                             snapshot(notification("turn/completed", "completed"), tools))
        self.assertEqual((bound["phase"], bound["gaps"]), ("terminal-observed", ["tool-unqualified"]))
        self.assertEqual(self.advance(state(), reply(), notification())["gaps"], [])
        projected = self.project(notification())
        producer = {**PRODUCER, "session_id": "/PRIVATE-SENTINEL"}
        with patch.object(module.native, "event_key", side_effect=AssertionError("hash forbidden")):
            with self.assertRaisesRegex(ValueError, "^protocol-invalid$"):
                module.to_native_event(projected, producer=producer, observed_at=NOW)


if __name__ == "__main__":
    unittest.main()
