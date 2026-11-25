"""1.11.0 item 4: a Claude usage limit is a rate limit and a quota hold, never an invalid cell. Synthetic Claude streams through the
real runner and cell, synthetic receipts for the controller, synthetic probes for the quota reading. No model."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import effort_lab as lab  # noqa: E402
import replay_eval  # noqa: E402

RUNNER = ROOT / "scripts" / "native_runner.py"
GIT_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
CLI = ["--print", "--verbose", "--no-session-persistence", "--restricted", "--output-format", "stream-json", "--model", "m", "--effort", "medium"]
# A fake `claude`: it works (one tool call, FAKE_CMD), then ends as FAKE_LIMIT says. With FAKE_MARKER, only the first call anywhere
# ends that way and every later one is served.
FAKE = r"""import json, os, pathlib, sys
sys.stdin.read()
pathlib.Path("answer.txt").write_text("done")
mode, marker = os.environ.get("FAKE_LIMIT", "ok"), os.environ.get("FAKE_MARKER")
if marker:
    mode = "ok" if pathlib.Path(marker).exists() else mode
    pathlib.Path(marker).touch()
reset = int(os.environ.get("FAKE_RESET", "1795039200"))
work = {"type": "assistant", "session_id": "s1",
        "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": os.environ.get("FAKE_CMD", "ls")}}]}}
result = {"type": "result", "subtype": "success", "is_error": False, "session_id": "s1", "num_turns": 2,
          "usage": {"input_tokens": 900, "output_tokens": 300}, "total_cost_usd": 0.4, "modelUsage": {"m": {"inputTokens": 900, "outputTokens": 300}}}
rows = [{"type": "system", "subtype": "init", "session_id": "s1"}, work]
if mode == "worked-limit":  # the limit cut the call after the agent worked: real usage and cost, the CLI's own error text
    result.update(is_error=True, result=f"Claude AI usage limit reached|{reset}")
elif mode == "zero-limit":  # study F-1's shape: zero usage and cost
    result.update(is_error=True, result=f"Claude AI usage limit reached|{reset}", total_cost_usd=0.0,
                  usage={"input_tokens": 0, "output_tokens": 0}, modelUsage={})
elif mode == "event-limit":  # a rejected rate_limit_event, then an error result that names nothing
    rows.append({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": reset, "rateLimitType": "seven_day"}})
    result.update(is_error=True, subtype="error_during_execution", result="API Error")
elif mode == "api-429":  # a rate limit that is not the account's usage limit, after work
    result.update(is_error=True, result="API Error: 429 rate_limit_error")
for row in rows + [result]:
    print(json.dumps(row), flush=True)
sys.exit(0 if mode == "ok" else 1)
"""


def now():
    return int(datetime.now(timezone.utc).timestamp())


class RealCell(unittest.TestCase):
    """The receipt native_runner writes from a synthetic stream, read by the real cell and the real controller."""

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        (self.root / "bin").mkdir()
        claude = self.root / "bin" / "claude"
        claude.write_text(f"#!{sys.executable}\n" + FAKE)
        claude.chmod(0o755)
        repo = self.root / "source"
        repo.mkdir()
        (repo / "base.txt").write_text("base\n")
        for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "base"]):
            subprocess.run(["git", "-C", str(repo), *args], env=GIT_ENV, check=True, capture_output=True)
        base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], env=GIT_ENV, check=True, capture_output=True, text=True).stdout.strip()
        runner = [sys.executable, "-B", str(RUNNER), "--cli", "claude", "--receipt", "{runner_receipt}", "--provider", "anthropic",
                  "--model", "{model}", "--effort", "{effort}", "--stream-copy", "{stream_copy}", "--", str(claude), *CLI]
        task = {"id": "t1", "repo": "r", "base": base, "accepted": base, "prompt": "do the task",
                "acceptance": [[sys.executable, "-c", "import pathlib; raise SystemExit(0 if pathlib.Path('answer.txt').exists() else 1)"]]}
        self.path, self.out = self.root / "set.json", self.root / "results"
        self.path.write_text(json.dumps({"seed": 1, "repos": {"r": str(repo)}, "agent_command": runner, "tasks": [task],
                                         "arms": {"claude": {"provider": "anthropic", "model": "m", "effort": "medium", "doctrine": ""}}}))

    def run_(self, env, **options):
        with mock.patch.dict(os.environ, env):
            return lab.run(self.path, self.out, **{"replicates": 1, "jobs": 1, "max_calls": 9, "max_usd": 9, "stop_usd": 1, **options})

    def test_a_limit_after_work_is_refused_held_until_its_reset_and_then_dispatched_again(self):
        reset = now() + 3600
        env = {"FAKE_LIMIT": "worked-limit", "FAKE_MARKER": str(self.root / "limited"), "FAKE_RESET": str(reset)}
        with mock.patch.object(lab.time, "sleep") as sleep:
            first = self.run_(env, requeue_refused=True, rate_limit_wait_s=3600, max_invalid=1)
        sleep.assert_not_called()  # a usage limit is not waited out 10 minutes at a time
        self.assertEqual((first["stop"], first["invalid"], first["refused"], first["requeued"], first["resets_at"]),
                         ("quota-hold", 0, 1, 1, reset))
        self.assertEqual(first["spent"], 0.4)  # the work it did is still charged
        self.assertFalse((self.out / "STOP.json").exists())  # a planned pause, as a failed quota gate
        kept = json.loads((self.out / "refused" / "t1-r01-claude.1.runner.json").read_text())
        self.assertEqual((kept["problem"], kept["usage"]["total_tokens"], kept["usage_limit"]),
                         ("native-error-rate-limit", 1200, {"source": "result", "resets_at": reset}))
        self.assertNotIn("usage limit reached", json.dumps(kept))  # the fixed fields only, never the stream's text
        cell = json.loads((self.out / "refused" / "t1-r01-claude.1.json").read_text())
        self.assertEqual(cell["failure_class"], "provider-rate-limit")
        finished = [r for r in replay_eval.load_dispatch_history(self.out)[0] if "finished_at" in r]
        self.assertEqual({k: finished[-1].get(k) for k in ("refused", "requeued", "usage_limit", "resets_at")},
                         {"refused": True, "requeued": True, "usage_limit": True, "resets_at": reset})
        second = self.run_(env, requeue_refused=True)  # before the reset: nothing is dispatched, the hold says until when
        self.assertEqual((second["stop"], second["calls"], second["resets_at"]), ("quota-hold", 0, reset))
        self.assertTrue(0 < second["retry_after_s"] <= 3600)

        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz) + timedelta(hours=2)
        with mock.patch.object(lab, "datetime", Later):
            third = self.run_(env, requeue_refused=True)
        self.assertEqual((third["stop"], third["calls"], third["invalid"]), (None, 1, 0))
        served = json.loads((self.out / "t1-r01-claude.json").read_text())
        self.assertEqual((served["valid"], served["accepted"]), (True, True))

    def test_a_rejected_event_and_a_zero_usage_limit_read_the_same(self):
        for mode, source in (("event-limit", "rate-limit-event"), ("zero-limit", "result")):
            with self.subTest(mode=mode):
                self.out = self.root / f"results-{mode}"
                state = self.run_({"FAKE_LIMIT": mode, "FAKE_RESET": "1795039200"}, max_invalid=1)
                self.assertEqual((state["stop"], state["invalid"], state["refused"], state["resets_at"]), ("quota-hold", 0, 1, 1795039200))
                self.assertEqual(lab.usage_limit(self.out, "t1-r01-claude"), {"source": source, "resets_at": 1795039200})

    def test_another_rate_limit_after_work_is_still_an_invalid_cell(self):
        # scope pinned: only the account's usage limit exempts a call that did work (1.8.1's guard on usage stays for the rest)
        state = self.run_({"FAKE_LIMIT": "api-429"}, max_invalid=1, requeue_refused=True)
        self.assertEqual((state["stop"], state["invalid"], state["refused"]), ("invalid-budget", 1, 0))
        receipt = json.loads((self.out / "t1-r01-claude.runner.json").read_text())
        self.assertEqual(receipt["problem"], "native-error-rate-limit")
        self.assertNotIn("usage_limit", receipt)

    def test_a_refused_call_that_read_a_protected_path_stays_contaminated(self):
        # item 3c's hand-over: contaminated wins over rate-limited; the cell is invalid, counted, and never requeued
        for mode in ("worked-limit", "zero-limit"):
            with self.subTest(mode=mode):
                self.out = self.root / f"read-{mode}"
                state = self.run_({"FAKE_LIMIT": mode, "FAKE_CMD": f"cat {self.out}/dispatch.jsonl"}, max_invalid=1, requeue_refused=True)
                self.assertEqual((state["stop"], state["invalid"], state["refused"], state["requeued"]), ("invalid-budget", 1, 0, 0))
                self.assertTrue(lab.refused(self.out, "t1-r01-claude"))  # the receipt alone would read as a refusal
                cell = json.loads((self.out / "t1-r01-claude.json").read_text())
                self.assertEqual((cell["valid"], cell["failure_class"], cell["contamination"]["status"]), (False, "contaminated", "contaminated"))
                finished = [r for r in replay_eval.load_dispatch_history(self.out)[0] if "finished_at" in r]
                self.assertNotIn("refused", finished[-1])
                self.assertFalse((self.out / "refused").exists())


def write_set(root, tasks=2, **extra):
    root.mkdir(exist_ok=True)
    path = root / "set.json"
    path.write_text(json.dumps({"seed": 1, "arms": {"a": {}, "b": {}}, "tasks": [{"id": f"T{i}"} for i in range(tasks)], **extra}))
    return path


def executor(receipts, rows=None):
    """A fake cell: `receipts(cid, attempt)` gives the receipt of a refused call (or None for a served one), `rows` the cell's fields."""
    calls = []

    def execute(config, task, arm, rep, out, timeout):
        cid = replay_eval.cell_id(task, arm, rep)
        calls.append(cid)
        receipt = receipts(cid, calls.count(cid))
        (out / f"{cid}.runner.json").write_text(json.dumps(receipt or {}))
        row = ({"valid": False, "cost_usd": "unmeasured", "failure_class": "agent-exit", **((rows or {}).get(cid, {}))}
               if receipt else {"valid": True, "cost_usd": 1.0})
        row.update(task=task["id"], arm=arm, replicate=rep, runner_receipt_sha256=lab._sha256(out / f"{cid}.runner.json"))
        (out / f"{cid}.json").write_text(json.dumps(row))
        return row
    execute.calls = calls
    return execute


ZERO = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
PLAIN = {"problem": "native-error-rate-limit", "usage": ZERO, "cost_usd": 0.0}
LIMIT = lambda resets: {**PLAIN, "usage_limit": {"source": "result", "resets_at": resets}}


class Controller(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.path, self.out = write_set(self.root), self.root / "out"
        for patch in (mock.patch.object(lab, "RATE_LIMIT_COOLDOWN_S", 0), mock.patch.object(lab.time, "sleep")):
            patch.start()
            self.addCleanup(patch.stop)

    def go(self, execute, **options):
        return lab.run(self.path, self.out, execute=execute, **{"replicates": 1, "jobs": 1, "max_calls": 99, "max_usd": 99, "stop_usd": 1, **options})

    def test_a_usage_limit_outranks_a_plain_refusal_in_the_same_chunk(self):
        box = []  # --jobs 2: the first two cells are both in flight; whichever finishes first, the usage limit decides the pause
        execute = executor(lambda cid, n: n == 1 and {0: PLAIN, 1: LIMIT(now() + 60)}.get(box[0].calls.index(cid)))
        box.append(execute)
        state = self.go(execute, jobs=2, requeue_refused=True)
        self.assertEqual((state["stop"], state["refused"], state["calls"]), ("quota-hold", 2, 2))
        plain = self.root / "plain"  # a refusal that names no usage limit keeps 1.8.1's pause and its cooldown
        self.assertEqual(lab.run(self.path, plain, execute=executor(lambda cid, n: n == 1 and cid == "T0-r01-a" and PLAIN),
                                 replicates=1, jobs=1, max_calls=99, max_usd=99, stop_usd=1)["stop"], "rate-limit")

    def test_a_limit_without_a_reset_falls_back_to_the_cooldown(self):
        execute = executor(lambda cid, n: n == 1 and cid == "T0-r01-a" and LIMIT(None))
        first = self.go(execute, requeue_refused=True)
        self.assertEqual(first["stop"], "quota-hold")
        self.assertNotIn("resets_at", first)  # never a guessed reset
        second = self.go(execute, requeue_refused=True)  # no reset to hold until: the (patched) 10-minute cooldown alone
        self.assertEqual((second["stop"], len(lab.load_cells(self.out))), (None, 4))

    def test_an_expired_reset_needs_no_cooldown_and_a_probe_hold_is_honoured(self):
        """Review #14: a usage limit whose reset has passed fell through to the 10-minute cooldown; a failed quota probe's reset was
        logged but not read on resume, so the next resume paid for another probe at once."""
        with mock.patch.object(lab, "RATE_LIMIT_COOLDOWN_S", 600):
            execute = executor(lambda cid, n: n == 1 and cid == "T0-r01-a" and LIMIT(now() - 5))
            self.assertEqual(self.go(execute, requeue_refused=True)["stop"], "quota-hold")
            again = self.go(execute, requeue_refused=True)
            self.assertEqual((again["stop"], len(lab.load_cells(self.out))), (None, 4))
        probes = self.root / "probes.log"
        reset = now() + 3600
        (self.root / "probe.py").write_text(
            "import json\nopen(%r, 'a').write('x')\n" % str(probes)
            + "print(json.dumps({'type': 'result', 'is_error': True, 'result': 'Claude AI usage limit reached|%d', 'total_cost_usd': 0.0}))\n" % reset)
        path = write_set(self.root / "gated", quota_probe={"command": [sys.executable, "-I", str(self.root / "probe.py")]})
        out = self.root / "gated-out"
        go = lambda: lab.run(path, out, execute=executor(lambda cid, n: None), replicates=1, jobs=1, max_calls=99, max_usd=99,
                             stop_usd=1, quota_gate=True)
        first = go()
        self.assertEqual((first["stop"], first["calls"], first["resets_at"]), ("quota-hold", 0, reset))
        second = go()
        self.assertEqual((second["stop"], second["calls"], second["resets_at"]), ("quota-hold", 0, reset))
        self.assertEqual(probes.read_text(), "x")  # one paid probe, not two

    def test_a_finished_run_is_not_held(self):
        box = []  # the last cell dispatched is refused, and not requeued: nothing is left to hold
        execute = executor(lambda cid, n: len(box[0].calls) == 4 and LIMIT(now() + 3600))
        box.append(execute)
        self.assertEqual(self.go(execute)["stop"], "quota-hold")
        again = self.go(execute)
        self.assertEqual((again["stop"], again["calls"]), (None, 0))

    def test_contamination_wins_even_when_another_label_masks_it(self):
        # the cleanup label comes first in replay_eval; the scan still says contaminated, and that is enough
        masked = {"failure_class": "cleanup-incomplete", "contamination": {"status": "contaminated"}}
        execute = executor(lambda cid, n: LIMIT(now() + 3600), {f"T{i}-r01-{a}": masked for i in range(2) for a in "ab"})
        state = self.go(execute, max_invalid=1, requeue_refused=True)
        self.assertEqual((state["stop"], state["calls"], state["invalid"], state["refused"], state["requeued"]), ("invalid-budget", 1, 1, 0, 0))
        self.assertEqual(json.loads((self.out / f"{execute.calls[0]}.json").read_text())["failure_class"], "cleanup-incomplete")


PROBE = r"""import json, sys
mode = sys.argv[1]
if mode == "limit":  # the probe's own call hit the limit: the CLI's error result, no rate_limit_event
    print(json.dumps({"type": "result", "is_error": True, "result": "Claude AI usage limit reached|1795039200", "total_cost_usd": 0.0}))
elif mode == "rejected":
    print(json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 1794434400, "rateLimitType": "seven_day"}}))
else:
    print(json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "resetsAt": 1795039200,
                      "unifiedWindows": {"seven_day": {"utilization": 0.1, "status": "allowed"}}}}))
    print(json.dumps({"type": "result", "is_error": False, "result": "ok", "total_cost_usd": 0.01}))
"""


class QuotaReading(unittest.TestCase):
    def test_the_probe_names_the_limit_and_its_reset(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "probe.py").write_text(PROBE)
            for mode, ok, reason, resets in (("limit", False, "usage limit reached", 1795039200),
                                             ("rejected", False, "status 'rejected'", 1794434400), ("allowed", True, "headroom", None)):
                with self.subTest(mode=mode):
                    out = root / mode
                    out.mkdir()
                    config = {"quota_probe": {"command": [sys.executable, "-I", str(root / "probe.py"), mode]}}
                    self.assertEqual(lab.quota_check(config, out, 1.0)[:2], (ok, reason))
                    row = json.loads((out / "quota.jsonl").read_text())
                    self.assertEqual((row["ok"], row["reason"], row["resets_at"]), (ok, reason, resets))

    def test_a_limited_probe_stops_dispatch_as_a_limited_cell_does(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "probe.py").write_text(PROBE)
            path = write_set(root, quota_probe={"command": [sys.executable, "-I", str(root / "probe.py"), "limit"]})
            calls = []
            state = lab.run(path, root / "out", execute=lambda *a: calls.append(a), replicates=1, jobs=1, max_calls=99, max_usd=99,
                            stop_usd=1, quota_gate=True)
            self.assertEqual((state["stop"], state["calls"], calls), ("quota-hold", 0, []))


if __name__ == "__main__":
    unittest.main()
