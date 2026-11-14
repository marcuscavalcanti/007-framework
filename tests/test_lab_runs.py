"""1.9.0 `007 lab run` and `report`: what the Claude study F did by script, made native. A fake agent, no model."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import effort_lab as lab  # noqa: E402
import replay_eval  # noqa: E402

ZERO = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def write_set(root, tasks=4, **extra):
    path = root / "set.json"
    path.write_text(json.dumps({"seed": 1, "arms": {"a": {}, "b": {}}, "tasks": [{"id": f"T{i}"} for i in range(tasks)], **extra}))
    return path


class Agent:
    """A fake cell executor. `refuse(cid, attempt)` makes a call the provider refused (the real Claude runner's receipt shape:
    zero-filled usage, cost 0.0); `cost(cid)` sets a served cell's cost; `raise_(cid)` raises in the controller."""

    def __init__(self, refuse=None, cost=None, raise_=None, valid=True, delay=None):
        self.refuse, self.cost, self.raise_, self.valid = refuse, cost, raise_, valid
        self.delay, self.calls, self.lock, self.live, self.peak = delay, [], threading.Lock(), 0, 0

    def __call__(self, config, task, arm, rep, out, timeout):
        cid = replay_eval.cell_id(task, arm, rep)
        with self.lock:
            self.calls.append(cid)
            attempt = self.calls.count(cid)
            self.live += 1
            self.peak = max(self.peak, self.live)
        try:
            if self.delay:
                time.sleep(self.delay(cid))
            if self.raise_ and self.raise_(cid, out):
                raise RuntimeError("snapshot refused")
            if self.refuse and self.refuse(cid, attempt):
                (out / f"{cid}.runner.json").write_text(json.dumps({"problem": "native-error-rate-limit", "usage": ZERO, "cost_usd": 0.0}))
                row = {"valid": False, "cost_usd": "unmeasured", "failure_class": "agent-exit", "task": task["id"], "arm": arm, "replicate": rep}
            else:
                (out / f"{cid}.runner.json").write_text("{}")
                row = {"valid": self.valid, "cost_usd": self.cost(cid) if self.cost else 1.0, "task": task["id"], "arm": arm, "replicate": rep}
            row["runner_receipt_sha256"] = lab._sha256(out / f"{cid}.runner.json")
            (out / f"{cid}.json").write_text(json.dumps(row))
            return row
        finally:
            with self.lock:
                self.live -= 1


def go(path, out, agent, **options):
    defaults = {"replicates": 1, "jobs": 1, "max_calls": 99, "max_usd": 99, "stop_usd": 1}
    return lab.run(path, out, execute=agent, **{**defaults, **options})


class Refusals(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.path, self.out = write_set(self.root), self.root / "out"
        for patch in (mock.patch.object(lab, "RATE_LIMIT_COOLDOWN_S", 0), mock.patch.object(lab.time, "sleep")):
            patch.start()
            self.addCleanup(patch.stop)

    def test_four_refusals_are_set_aside_dispatched_again_and_every_cell_ends_valid(self):
        for jobs in (1, 2):
            with self.subTest(jobs=jobs):
                out = self.root / f"out-{jobs}"
                agent = Agent(refuse=lambda cid, attempt: attempt == 1 and cid.startswith(("T0", "T1")))  # 4 cells, once each
                state = go(self.path, out, agent, jobs=jobs, requeue_refused=True, rate_limit_wait_s=3600, max_invalid=1)
                self.assertEqual((state["stop"], state["calls"], state["invalid"], state["refused"], state["requeued"]), (None, 12, 0, 4, 4))
                self.assertEqual(state["spent"], 8.0)  # the refused calls reported a cost of 0.0 and no usage
                rows = lab.load_cells(out)
                self.assertEqual((len(rows), sum(r["valid"] is True for r in rows)), (8, 8))
                self.assertEqual(len(list((out / "refused").glob("*.runner.json"))), 4)  # nothing deleted
                self.assertEqual(replay_eval.load_dispatch_history(out)[1:], (0, 0))
                again = go(self.path, out, Agent(), jobs=jobs, requeue_refused=True)
                self.assertEqual((again["calls"], again["spent"], again["refused"], again["requeued"]), (0, 8.0, 4, 4))

    def test_without_waiting_the_run_pauses_and_a_later_run_dispatches_the_refused_cell_again(self):
        agent = Agent(refuse=lambda cid, attempt: attempt == 1 and cid == "T2-r01-b")
        first = go(self.path, self.out, agent, requeue_refused=True)
        self.assertEqual((first["stop"], first["refused"]), ("rate-limit", 1))
        self.assertFalse((self.out / "STOP.json").exists())
        second = go(self.path, self.out, agent, requeue_refused=True)
        self.assertEqual((second["stop"], second["refused"], len(lab.load_cells(self.out))), (None, 1, 8))
        self.assertEqual(agent.calls.count("T2-r01-b"), 2)

    def test_refusals_are_counted_per_arm_in_the_run_and_in_the_accounting(self):
        agent = Agent(refuse=lambda cid, attempt: attempt == 1 and cid.endswith("-a") and cid[:2] in ("T0", "T3"))
        state = go(self.path, self.out, agent, requeue_refused=True, rate_limit_wait_s=3600)
        self.assertEqual(state["refused_per_arm"], {"a": 2, "b": 0})
        rows = lab.load_cells(self.out)
        accounting = lab.arm_accounting(json.loads(self.path.read_text()), self.out, rows, {})
        self.assertEqual((accounting["arms"]["a"]["refused"], accounting["arms"]["b"]["refused"]), (2, 0))

    def test_a_refusal_with_usage_is_an_ordinary_invalid_cell(self):
        def used(config, task, arm, rep, out, timeout):  # the guard on usage, pinned: a call that did work is not a refusal
            cid = replay_eval.cell_id(task, arm, rep)
            (out / f"{cid}.runner.json").write_text(json.dumps({"problem": "native-error-rate-limit", "usage": {"input_tokens": 5}, "cost_usd": 0.1}))
            row = {"valid": False, "cost_usd": 0.1}
            (out / f"{cid}.json").write_text(json.dumps(row))
            return row
        state = go(self.path, self.out, used, max_invalid=1)
        self.assertEqual((state["stop"], state["refused"], state["invalid"]), ("invalid-budget", 0, 1))

    def test_the_cooldown_reads_the_newest_refusal_even_when_a_later_cell_finished(self):
        # --jobs 2: the refused cell finishes first, a served one after it; 1.8.1 looked only at the newest row (review N3)
        agent = Agent(refuse=lambda cid, attempt: cid == agent.calls[0], delay=lambda cid: 0 if cid == agent.calls[0] else .2)
        first = go(self.path, self.out, agent, jobs=2)
        self.assertEqual(first["stop"], "rate-limit")
        history = replay_eval.load_dispatch_history(self.out)[0]
        self.assertNotIn("refused", [row for row in history if "finished_at" in row][-1])
        with mock.patch.object(lab, "RATE_LIMIT_COOLDOWN_S", 600):
            self.assertEqual(go(self.path, self.out, Agent(), jobs=2)["stop"], "rate-limit-cooldown")

    def test_only_the_live_label_exempts_a_cell_on_resume(self):
        def recovered(config, task, arm, rep, out, timeout):  # served after a 429: its receipt names the limit, the cell is valid
            row = Agent()(config, task, arm, rep, out, timeout)
            cid = replay_eval.cell_id(task, arm, rep)
            (out / f"{cid}.runner.json").write_text(json.dumps({"problem": "native-error-rate-limit", "cost_usd": 1.0}))
            return row
        go(self.path, self.out, recovered)
        again = go(self.path, self.out, Agent())
        self.assertEqual((again["calls"], again["refused"]), (0, 0))  # review N4
        out = self.root / "unlabelled"  # an invalid cell whose receipt refuses, but which no live run labelled
        out.mkdir()
        (out / "T0-r01-a.runner.json").write_text(json.dumps({"problem": "native-error-rate-limit", "usage": None}))
        (out / "T0-r01-a.json").write_text(json.dumps({"valid": False, "cost_usd": 0}))
        self.assertEqual(go(self.path, out, Agent(), max_invalid=1)["stop"], "invalid-budget")


class LedgerReader(unittest.TestCase):
    def test_a_requeued_cell_may_be_dispatched_once_more_and_nothing_else_repeats(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            rows = lambda *events: (out / "dispatch.jsonl").write_text("".join(json.dumps({"cell": "T0-r01-a", k: f"2026-11-14T10:00:0{i}Z", **x}) + "\n"
                                                                              for i, (k, x) in enumerate(events)))
            d_, f_ = "dispatched_at", "finished_at"
            rows((d_, {}), (f_, {"refused": True, "requeued": True}), (d_, {}), (f_, {}))
            self.assertEqual(replay_eval.load_dispatch_history(out)[1:], (0, 0))
            rows((d_, {}), (f_, {"refused": True}), (d_, {}), (f_, {}))
            self.assertEqual(replay_eval.load_dispatch_history(out)[2], 2)
            rows((d_, {}), (f_, {"requeued": True}), (d_, {}), (d_, {}))
            self.assertEqual(replay_eval.load_dispatch_history(out)[2], 1)


class Limits(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.path, self.out = write_set(self.root), self.root / "out"

    def test_a_cell_over_the_per_cell_brake_stops_by_default_and_is_recorded_on_request(self):
        dear = Agent(cost=lambda cid: 25.0 if cid == "T1-r01-a" else 1.0)
        stopped = go(self.path, self.root / "stop", dear, max_usd=400, stop_usd=20)
        self.assertEqual(stopped["stop"], "cell-over-limit")
        self.assertTrue((self.root / "stop" / "STOP.json").exists())
        recorded = go(self.path, self.root / "record", Agent(cost=dear.cost), max_usd=400, stop_usd=20, over_limit="record")
        self.assertEqual((recorded["stop"], recorded["over_limit_cells"], recorded["spent"], recorded["calls"]), (None, 1, 32.0, 8))
        capped = go(self.path, self.root / "cap", Agent(cost=lambda cid: 25.0), max_usd=60, stop_usd=20, over_limit="record")
        self.assertEqual(capped["stop"], "usd-budget")  # only the total cap stops it
        self.assertLessEqual(capped["spent"], 75.0)

    def test_chunks_finish_before_the_gates_run_again(self):
        gates = []
        with mock.patch.object(lab, "quiet", lambda out, m, w, step: gates.append(("load", step)) or True), \
                mock.patch.object(lab, "quota_check", lambda config, out, left: gates.append(("quota", round(left, 3))) or (True, "headroom")):
            state = go(self.path, self.out, Agent(delay=lambda cid: .01), jobs=2, chunk=3, max_load=8, quota_gate=True)
        self.assertEqual((state["stop"], state["calls"]), (None, 8))
        self.assertEqual(gates, [("load", "chunk at 0"), ("quota", 1.0), ("load", "chunk at 3"), ("quota", .625), ("load", "chunk at 6"), ("quota", .25)])
        sent = finished = 0
        for row in replay_eval.load_dispatch_history(self.out)[0]:  # the 4th and 7th dispatch wait for every earlier cell
            if "dispatched_at" in row:
                if sent in (3, 6):
                    self.assertEqual(finished, sent)
                sent += 1
            else:
                finished += 1

    def test_a_loaded_machine_or_a_short_quota_pauses_and_a_later_run_resumes(self):
        with mock.patch.object(lab.os, "getloadavg", return_value=(20.0, 20.0, 20.0)), mock.patch.object(lab, "LOAD_POLL_S", 0):
            busy = go(self.path, self.out, Agent(), max_load=8, load_wait_s=0)
        self.assertEqual((busy["stop"], busy["calls"]), ("machine-busy", 0))
        self.assertFalse((self.out / "STOP.json").exists())
        self.assertEqual(json.loads((self.out / "load.log").read_text().splitlines()[0])["load"], [20.0, 20.0, 20.0])
        with mock.patch.object(lab, "quota_check", return_value=(False, "seven_day at 0.9")):
            held = go(self.path, self.out, Agent(), quota_gate=True)
        self.assertEqual((held["stop"], held["calls"]), ("quota-hold", 0))
        with mock.patch.object(lab.os, "getloadavg", return_value=(1.0, 1.0, 1.0)):
            done = go(self.path, self.out, Agent(), max_load=8, load_wait_s=0)
        self.assertEqual((done["stop"], done["calls"]), (None, 8))

    def test_the_cost_marker_runs_once_on_exactly_its_first_cells(self):
        held = go(self.path, self.root / "held", Agent(), cost_marker_at=4, cost_marker_hold_usd=4)
        hold = json.loads((self.root / "held" / "HOLD.json").read_text())
        self.assertEqual((held["stop"], held["calls"], sum(hold["cells"].values())), ("cost-marker-hold", 4, 4))
        self.assertEqual(go(self.path, self.root / "held", Agent())["stop"], "stopped-before")  # terminal: nothing is redone
        out = self.root / "pass"
        first = go(self.path, out, Agent(), max_calls=5, cost_marker_at=4, cost_marker_hold_usd=100)
        marker = (out / "MARKER.json").read_text()
        self.assertEqual((first["stop"], first["calls"], json.loads(marker)["projection_usd"]), ("call-budget", 5, 8.0))
        rest = go(self.path, out, Agent(), cost_marker_at=4, cost_marker_hold_usd=1)  # a lower hold now changes nothing
        self.assertEqual((rest["stop"], (out / "MARKER.json").read_text()), (None, marker))

    def test_nothing_runs_or_is_read_after_the_single_look(self):
        self.out.mkdir()
        (self.out / "LOOK.json").write_text("{}")
        self.assertEqual(go(self.path, self.out, Agent())["stop"], "looked")
        with self.assertRaisesRegex(ValueError, "single look"):
            lab.report(self.path, self.out, None)

    def test_jobs_above_a_quarter_of_the_cores_warn_or_are_refused(self):
        with mock.patch.object(lab.os, "cpu_count", return_value=8):
            self.assertEqual(lab.jobs_limit(), 2)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                state = go(self.path, self.out, Agent(), jobs=3)
            self.assertIn("--jobs 3 is above 2", err.getvalue())
            self.assertEqual(state["calls"], 8)
            with self.assertRaisesRegex(ValueError, "jobs limit"):
                go(self.path, self.root / "strict", Agent(), jobs=3, strict_jobs=True)
            self.assertFalse((self.root / "strict").exists())
        for bad in ({"over_limit": "maybe"}, {"chunk": 0}, {"max_load": 0}, {"cost_marker_at": 4}, {"rate_limit_wait_s": -1}):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "limit"):
                go(self.path, self.root / "bad", Agent(), **bad)


class ControllerErrors(unittest.TestCase):
    def test_both_branches_keep_what_exists_and_name_the_frame(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, out = write_set(root), root / "out"

            def raise_(cid, out_):
                if cid == "T0-r01-a":  # the cell's result was written before the error: it stands
                    (out_ / f"{cid}.runner.json").write_text("{}")
                    (out_ / f"{cid}.json").write_text(json.dumps({"valid": True, "cost_usd": 1.0}))
                    return True
                if cid == "T1-r01-a":  # the agent ran (a receipt) and then the controller raised
                    (out_ / f"{cid}.runner.json").write_text('{"cost_usd": 2.0}')
                    return True
                return False
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                state = go(path, out, Agent(raise_=raise_), jobs=2, stop_usd=5)
            self.assertEqual((state["stop"], state["invalid"], state["spent"]), (None, 1, 9.0))
            kept = json.loads((out / "T0-r01-a.json").read_text())
            self.assertEqual(kept, {"valid": True, "cost_usd": 1.0})
            failed = json.loads((out / "T1-r01-a.json").read_text())
            self.assertEqual(failed["runner_receipt_sha256"], lab._sha256(out / "T1-r01-a.runner.json"))
            self.assertEqual((failed["controller_error"]["type"], failed["controller_error"]["message"]), ("RuntimeError", "snapshot refused"))
            self.assertIn("test_lab_runs.py", failed["controller_error"]["where"])
            self.assertIn("RuntimeError: snapshot refused (at test_lab_runs.py", err.getvalue())


class Seal(unittest.TestCase):
    def test_the_grading_toolchain_is_sealed_and_a_change_is_a_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            version = root / "version"
            version.write_text("3.99.0")
            python = root / "python"
            python.write_text(f"#!/bin/sh\necho \"Python $(cat {version})\"\n")
            python.chmod(0o755)
            path = write_set(root, tasks=1)
            config = json.loads(path.read_text())
            config["tasks"][0]["acceptance"] = [[str(python), "-I", ".007-accept/lab_accept.py"]]
            path.write_text(json.dumps(config))
            (root / "tasks" / "T0").mkdir(parents=True)
            (root / "tasks" / "T0" / "lab.json").write_text(json.dumps({"adapter": "unittest"}))
            out = root / "out"
            go(path, out, Agent(), max_calls=1)
            sealed = json.loads((out / "run-manifest.json").read_text())["toolchain"]
            self.assertEqual(sealed, {"python": {"path": str(python.resolve()), "version": "Python 3.99.0"}})
            version.write_text("3.99.1")
            moved = go(path, out, Agent())
            self.assertEqual((moved["stop"], moved["changed"]), ("manifest-mismatch", ["toolchain"]))
            self.assertEqual(moved["details"]["toolchain"]["found"]["python"]["version"], "Python 3.99.1")
            version.write_text("3.99.0")
            self.assertEqual(go(path, out, Agent())["stop"], None)

    def test_every_form_of_a_file_argument_is_sealed(self):
        with tempfile.TemporaryDirectory() as d:
            named = Path(d) / "agent.toml"
            named.write_text("x")
            for part in (f"KEY={named}", f"--flag=key={named}", f"-f{named}", f"@{named}", f"--config={named}"):
                with self.subTest(part=part):
                    self.assertEqual(lab.seal({"agent_command": ["/bin/sh", part]})["executables"][part]["path"], str(named.resolve()))
            self.assertNotIn("GIT_CONFIG_GLOBAL=/dev/null", lab.seal({"agent_command": ["/bin/sh", "GIT_CONFIG_GLOBAL=/dev/null"]})["executables"])


class QuotaGate(unittest.TestCase):
    def test_the_eight_cases_of_the_f1_dry_run(self):
        allowed = lambda u, status="allowed": {"status": status, "unifiedWindows": {"seven_day": {"utilization": u, "status": status}}}
        cases = {
            "blocked_top_level": ([{**allowed(.1), "status": "rejected", "rateLimitType": "seven_day", "utilization": .1}], False),
            "no_windows_seven_day": ([{"status": "allowed", "rateLimitType": "seven_day", "utilization": .1}], True),
            "no_windows_other_type": ([{"status": "allowed", "rateLimitType": "five_hour", "utilization": .1}], False),
            "extra_window": ([{"status": "allowed", "unifiedWindows": {"seven_day": {"utilization": .1, "status": "allowed"},
                                                                       "five_hour": {"utilization": .2, "status": "allowed"}}}], False),
            "no_event": ([], False),
            "headroom_short": ([allowed(.36, "allowed_warning")], False),
            "headroom_enough": ([allowed(.30, "allowed_warning")], True),
            "second_event_blocked": ([allowed(.1), {"status": "rejected"}], False),
        }
        for name, (events, expected) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(lab.quota_judge(events, 1.0)[0], expected)
        self.assertTrue(lab.quota_judge([allowed(.36)], .5)[0])  # less left to run, less room needed

    def test_the_probe_is_a_real_command_and_its_decision_is_logged(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            event = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "unifiedWindows": {"seven_day": {"utilization": .2, "status": "allowed"}}}}
            config = {"quota_probe": {"command": [sys.executable, "-c", f"print({json.dumps(json.dumps(event))}); print('not json')"]}}
            self.assertEqual(lab.quota_check(config, out, 1.0), (True, "headroom"))
            logged = json.loads((out / "quota.jsonl").read_text())
            self.assertEqual((logged["utilization"], logged["probe_exit"]), ({"seven_day": .2}, 0))
            with self.assertRaisesRegex(ValueError, "quota_probe"):
                lab.quota_check({}, out, 1.0)
            missing = {"quota_probe": {"command": [str(out / "absent")]}}
            self.assertEqual(lab.quota_check(missing, out, 1.0), (False, "no rate_limit_event"))  # fails closed


class LoadSensitiveOracle(unittest.TestCase):
    def test_a_control_whose_grade_moves_when_repeated_alone_leaves_the_set(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = write_set(root, tasks=2, repos={"r": str(root)})
            (root / "pairs.json").write_text(json.dumps({"T0": {}, "T1": {}}))
            for tid in ("T0", "T1"):
                (root / "tasks" / tid).mkdir(parents=True)
                (root / "tasks" / tid / "reference.patch").write_text("")
            seen = {}

            def probe(config, out, tid, patch_text, real_next):
                seen[tid] = seen.get(tid, 0) + 1
                return (True, None) if tid == "T0" or seen[tid] == 1 else (False, None)  # T1 passes in parallel, fails alone
            with mock.patch.object(lab, "probe", probe):
                result = lab.sensitivity(path, 2)
            self.assertEqual((result["load_sensitive"], result["tasks"], seen), (["T1"], 1, {"T0": 2, "T1": 2}))
            state = go(path, root / "out", Agent())
            self.assertEqual((state["stop"], state["tasks"], state["calls"]), ("load-sensitive-oracle", ["T1"], 0))


class SnapshotLinks(unittest.TestCase):
    def archive(self, root, links, files=(("a.txt", b"A\n"), ("d/x.txt", b"X\n"))):
        path = root / "snapshot.tar"
        with tarfile.open(path, "w") as bundle:
            for name, data in files:
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), 0o644
                bundle.addfile(info, io.BytesIO(data))
            for name, target in links:
                info = tarfile.TarInfo(name)
                info.type, info.linkname = tarfile.SYMTYPE, target
                bundle.addfile(info)
        return path

    def test_links_inside_the_snapshot_become_copies_and_the_rest_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            dest = root / "ok"
            dest.mkdir()
            replay_eval.extract_archive(self.archive(root, [("c.txt", "b.txt"), ("b.txt", "a.txt"), ("e", "d"), ("d/up.txt", "../a.txt")]), dest)
            for name, text in (("b.txt", "A\n"), ("c.txt", "A\n"), ("e/x.txt", "X\n"), ("d/up.txt", "A\n")):
                self.assertEqual((dest / name).read_text(), text)
            self.assertFalse(any(p.is_symlink() for p in dest.rglob("*")))
            for links, reason in (([("out", "../outside")], "leaves"), ([("abs", "/etc/hosts")], "absolute"),
                                  ([("d/self", "..")], "own target"), ([("gone", "missing.txt")], "no target"),
                                  ([("p", "q"), ("q", "p")], "no target")):
                with self.subTest(links=links):
                    target = root / f"bad-{len(list(root.iterdir()))}"
                    target.mkdir()
                    with self.assertRaisesRegex(RuntimeError, reason):
                        replay_eval.extract_archive(self.archive(root, links), target)


class MissingDataGuard(unittest.TestCase):
    """L0 and L2 from the plan, and R with its worst case, on hand-made cells (validated on the 2026-11-07 and F results)."""

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.tasks = [f"T{i}" for i in range(30)]
        for tid in self.tasks:
            (self.root / tid).mkdir()
            (self.root / tid / "hidden.json").write_text(json.dumps({"x": 1, "y": 1, "__module__": 1}))
            (self.root / tid / "baseline.json").write_text("{}")
        self.config = {"seed": 3, "compare": {}}
        self.planned = [(t, r, a) for t in self.tasks for r in (1, 2) for a in ("lo", "hi")]
        patch = mock.patch.dict(lab.GATES, {"draws": 2000})
        patch.start()
        self.addCleanup(patch.stop)

    def cells(self, invalid=(), low_fail=()):
        """y fails at lo r1 on T0-T2 and at hi r2 on T3-T5 (noise both ways), and at lo wherever `low_fail` says."""
        rows = []
        for t, r, a in self.planned:
            i = int(t[1:]) % 10
            fail = (t, r) in low_fail and a == "lo" or (a, r) == ("lo", 1) and i < 3 or (a, r) == ("hi", 2) and 3 <= i < 6
            rows.append({"task": t, "replicate": r, "arm": a, "cell": f"{t}-r{r:02d}-{a}", "valid": (t, r, a) not in invalid,
                         "accepted": True, "cost_usd": 1.0 if a == "lo" else 4.0, "acceptance_outcomes": {"x": "pass", "y": "fail" if fail else "pass"}})
        return rows

    def guard(self, rows, margin=.2):
        return lab.missing_data_guard(self.config, self.root, self.root, rows, self.planned, "lo", "hi", margin, 10.0)

    def test_complete_cells_prove_and_pay(self):
        g = self.guard(self.cells())
        self.assertEqual((g["verdict"], g["answer"], g["missing_data"]["imputed_in_L2"]), ("PROVEN", "PAYS", {}))
        self.assertAlmostEqual(g["cost_ratio"], .25)  # US$1 against US$4, every cell accepted
        self.assertLess(g["cost_ratio_ci95"][1], 1)

    def test_enough_missing_low_cells_make_it_not_decisive(self):
        invalid = {(t, 2, "lo") for t in self.tasks[:30] if int(t[1:]) % 10 >= 6}  # 12 low cells where the arms agree
        g = self.guard(self.cells(invalid=invalid))
        self.assertEqual(g["missing_data"]["imputed_in_L2"], {"invalid": 12})
        self.assertEqual((g["verdict"], g["missing_data"]["label"]), ("NOT-PROVEN", "not decisive by missing data"))
        self.assertEqual(g["readings"]["P"]["verdict"], "PROVEN")  # L0 alone would have said PROVEN
        absent = self.guard([r for r in self.cells() if not (r["task"] == "T9" and r["arm"] == "hi")])
        self.assertEqual(absent["missing_data"]["imputed_in_L2"], {"absent": 2})

    def test_a_kill_does_not_pay(self):
        g = self.guard(self.cells(low_fail={(t, r) for t in self.tasks for r in (1, 2)}))
        self.assertEqual((g["verdict"], g["answer"]), ("KILL", "DOES-NOT-PAY"))


if __name__ == "__main__":
    unittest.main()
