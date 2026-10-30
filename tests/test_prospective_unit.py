"""New synthetic units only; no native server, model or user configuration."""
import copy
import hashlib
import importlib
import inspect
import io
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import tarfile
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import test_replay_capture_v2 as fixtures
import test_codex_prospective as protocol_fixture


def drive_in_process(prepared, args, connection, hold_in_send=False):
    # Disposable spawn child: same prepared unit and shared journal, its own dispatch root.
    import prospective_unit
    connection.recv()
    sends = []
    def send(payload):
        sends.append(payload)
        if hold_in_send:  # keep this dispatch in flight until the parent releases it
            connection.send("in-flight")
            connection.recv()
    try:
        result = prospective_unit.drive_offline(prepared, **args, send=send)
        outcome = {"phase": result["phase"], "gaps": result["gaps"], "sends": len(sends)}
    except BaseException as error:
        outcome = {"error": type(error).__name__, "sends": len(sends)}
    connection.send(outcome)
    connection.close()


class ProspectiveFixture(unittest.TestCase):
    def setUp(self):
        self.host = fixtures.ReplayCaptureV2Tests(methodName="runTest")
        self.host.setUp()
        self.addCleanup(self.host.doCleanups)
        self.repo, self.root, self.vault = self.host.repo, self.host.root, self.host.vault
        payload = (Path(__file__).parent / "fixtures/semantic-replay.tar.gz").read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(),
                         "c15a598d5f09258aa8907d5725e446f19631af8b60f5a66a08954a775b89797c")
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            data = archive.extractfile("project/task/inputs/tracked.py").read()
        self.assertEqual(data, b"value = 2\n")
        (self.repo / "tracked.py").write_bytes(data)
        (self.repo / "task.txt").write_text("Change only tracked.py to value = 3. Offline fixture.")
        (self.repo / "authority.json").write_text(json.dumps({
            "schema": "007-framework/authority/v1", "allow": [], "deny": ["execute"]}))
        self.config = self.host.config_v2()
        self.config["files"] += ["authority.json", ".gitignore"]
        self.config["execution"].update(adapter="codex-app-server", surface="terminal", binding_id="binding-new")
        self.identity = dict(project_id="project-new", task_id="task-new", attempt_id="attempt-new",
                             binding_id="binding-new")
        self.restore = self.root / "restored"
        self.send = Mock()

    def module(self):
        try:
            return importlib.import_module("prospective_unit")
        except ModuleNotFoundError:
            self.fail("prospective unit preparation is missing")

    def prepare(self):
        return self.module().prepare_unit(self.repo, self.config, self.identity,
                                         vault_root=self.vault, restore_to=self.restore)


class PreparationTests(ProspectiveFixture):
    def test_new_unit_captures_before_send_and_restores(self):
        prepared = self.prepare()
        self.module().verify_prepared(prepared, vault_root=self.vault)
        self.assertEqual((self.restore / "tracked.py").read_bytes(), b"value = 2\n")
        self.assertEqual((self.restore / "tracked.py").stat().st_mode & 0o777, 0o750)
        self.assertEqual(prepared["identity"], self.identity)
        self.assertEqual(prepared["replay_ref"]["manifest"], "project-new/attempt-new/input.json")
        manifest = json.loads((self.vault / prepared["replay_ref"]["manifest"]).read_bytes())
        self.assertEqual(manifest["config"]["execution"]["kind"], "native-host")
        self.assertEqual(manifest["config"]["requested"], None)
        self.assertFalse((self.repo / ".007").exists())
        self.assertFalse(any(self.vault.rglob("*receipt*")))
        self.assertEqual(self.send.call_count, 0)

    def test_prepared_rejects_bootstrap_mutation_identity_swap_and_corruption(self):
        prepared = self.prepare()
        for name in self.config["files"]:
            target = self.repo / name
            original = target.read_bytes()
            with self.subTest(artifact=name):
                target.write_bytes(b"PRIVATE-SENTINEL")
                with self.assertRaisesRegex(ValueError, "^unit-invalid$"):
                    self.module().verify_prepared(prepared, vault_root=self.vault)
                target.write_bytes(original)
        for target in (self.restore / "tracked.py", self.vault / prepared["replay_ref"]["manifest"]):
            original = target.read_bytes()
            target.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "^unit-invalid$"):
                self.module().verify_prepared(prepared, vault_root=self.vault)
            target.write_bytes(original)
        for key in self.identity:
            changed = copy.deepcopy(prepared)
            changed["identity"][key] = "wrong"
            with self.assertRaisesRegex(ValueError, "^unit-invalid$"):
                self.module().verify_prepared(changed, vault_root=self.vault)
        old = self.root / "old-repo"
        self.repo.rename(old)
        self.repo.mkdir()
        with self.assertRaisesRegex(ValueError, "^unit-invalid$"):
            self.module().verify_prepared(prepared, vault_root=self.vault)
        self.assertEqual(self.send.call_count, 0)

    def test_undeclared_files_modes_and_symlinks_are_not_ignored(self):
        prepared = self.prepare()
        extra = self.repo / "outside.txt"
        extra.write_text("PRIVATE-SENTINEL")
        with self.assertRaisesRegex(ValueError, "^unit-invalid$"):
            self.module().verify_prepared(prepared, vault_root=self.vault)
        extra.unlink()
        empty = self.repo / "extra-directory"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "^unit-invalid$"):
            self.module().verify_prepared(prepared, vault_root=self.vault)
        empty.rmdir()
        file = self.repo / "tracked.py"
        file.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "^unit-invalid$"):
            self.module().verify_prepared(prepared, vault_root=self.vault)
        file.chmod(0o750)
        file.rename(self.repo / "moved.py")
        file.symlink_to(self.repo / "moved.py")
        with self.assertRaisesRegex(ValueError, "^unit-invalid$"):
            self.module().verify_prepared(prepared, vault_root=self.vault)

    def test_restore_failure_prevents_preparation_and_preserves_source(self):
        module = self.module()
        before = (self.repo / "tracked.py").read_bytes()
        with patch.object(module.capture, "restore_input", side_effect=OSError("PRIVATE-SENTINEL")):
            with self.assertRaisesRegex(ValueError, "^unit-invalid$"):
                self.prepare()
        self.assertEqual((self.repo / "tracked.py").read_bytes(), before)
        self.assertEqual(self.send.call_count, 0)

    def test_unsafe_source_and_destination_rejected_before_capture(self):
        module = self.module()
        alias = self.root / "alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        for repo, destination in ((alias, self.restore), (self.repo, self.repo / "nested")):
            with self.subTest(repo=repo), self.assertRaisesRegex(ValueError, "^unit-invalid$"):
                module.prepare_unit(repo, self.config, self.identity,
                                    vault_root=self.vault, restore_to=destination)
        self.assertFalse(self.vault.exists())

    def test_protected_role_cannot_be_candidate_before_capture(self):
        for name in ("task.txt", "acceptance.json", "environment.json", "authority.json",
                     self.config["context_files"][0]):
            config = copy.deepcopy(self.config)
            config["output_files"] = [name]
            with self.subTest(output=name), self.assertRaisesRegex(ValueError, "^unit-invalid$"):
                self.module().prepare_unit(self.repo, config, self.identity,
                                          vault_root=self.vault, restore_to=self.restore)
            self.assertFalse(self.vault.exists())


    def test_subprocess_failures_are_sanitized_at_prepare_and_verify(self):
        # F2: Git subprocess failures leave the public boundary as the exact unit-invalid error.
        module = self.module()
        errors = (subprocess.TimeoutExpired(["git", "-C", "PRIVATE-SENTINEL"], 30),
                  subprocess.CalledProcessError(128, ["git", "-C", "PRIVATE-SENTINEL"]))
        for error in errors:
            for operation in ("prepare", "verify"):
                with self.subTest(error=type(error).__name__, operation=operation):
                    case = PreparationTests(methodName="runTest")
                    case.setUp()
                    try:
                        prepared = None if operation == "prepare" else case.prepare()
                        with patch.object(module.capture, "_revision", side_effect=error), \
                                self.assertRaises(ValueError) as caught:
                            if operation == "prepare":
                                case.prepare()
                            else:
                                module.verify_prepared(prepared, vault_root=case.vault)
                        self.assertEqual(str(caught.exception), "unit-invalid")
                        self.assertIsNone(caught.exception.__cause__)
                        self.assertTrue(caught.exception.__suppress_context__)
                        self.assertNotIn("PRIVATE-SENTINEL", repr(caught.exception))
                    finally:
                        case.doCleanups()


class DispatchTests(ProspectiveFixture):
    def dispatch_arguments(self, messages=None):
        prepared = self.prepare()
        bootstrap = protocol_fixture.bootstrap()
        bootstrap["result"]["cwd"] = str(self.repo)
        bootstrap["result"]["thread"]["cwd"] = str(self.repo)
        request = {"id": "dispatch-a", "method": "turn/start", "params": {"threadId": "thread-a",
                   "input": [{"type": "text", "text": (self.repo / "task.txt").read_text()}]}}
        stream = messages if messages is not None else [protocol_fixture.notification(), protocol_fixture.reply(),
                  protocol_fixture.notification("turn/completed", "completed")]
        return prepared, dict(messages=[("stdout", json.dumps(v).encode()) for v in stream],
            bootstrap={"request_id": "bootstrap-a", "response": bootstrap, "observed_at": protocol_fixture.NOW},
            request=request, root=self.root / "dispatch", journal_root=self.root / "journal",
            vault_root=self.vault, send=self.send)

    def drive(self, prepared, args):
        self.assertTrue(hasattr(self.module(), "drive_offline"), "single-send offline driver is missing")
        return self.module().drive_offline(prepared, **args)

    def test_intent_is_durable_before_only_send(self):
        prepared, args = self.dispatch_arguments()
        payloads = []
        def send(payload):
            intent = json.loads((args["root"] / "dispatch.claim/intent.json").read_bytes())
            self.assertEqual(intent["request_sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(intent["identity"], self.identity)
            self.assertEqual(intent["producer"]["session_id"], "session-a")
            self.assertEqual(json.loads(payload), args["request"])
            self.assertTrue((args["journal_root"] / "binding-new/binding/reservation.json").exists())
            payloads.append(payload)
        args["send"] = send
        result = self.drive(prepared, args)
        self.assertEqual(result["phase"], "terminal-observed")
        self.assertEqual(len(payloads), 1)
        self.assertEqual(json.loads((args["root"] / "dispatch.claim/result.json").read_bytes())["status"], "response-observed")

    def test_result_records_the_observed_turn_usage(self):
        # Plan Task 12: the driver itself makes the turn's usage durable.
        stream = [protocol_fixture.notification(), protocol_fixture.reply(), protocol_fixture.usage(),
                  protocol_fixture.notification("turn/completed", "completed")]
        prepared, args = self.dispatch_arguments(messages=stream)
        self.assertEqual(self.drive(prepared, args)["usage"]["total_tokens"], 130)
        result = json.loads((args["root"] / "dispatch.claim/result.json").read_bytes())
        self.assertEqual((result["status"], result["usage"]["total_tokens"]), ("response-observed", 130))

    def test_result_usage_is_null_not_zero_when_unobserved(self):
        prepared, args = self.dispatch_arguments()
        self.assertEqual(self.drive(prepared, args)["phase"], "terminal-observed")
        self.assertIsNone(json.loads((args["root"] / "dispatch.claim/result.json").read_bytes())["usage"])

    def test_existing_claim_lost_ack_and_post_publish_failure_never_retry(self):
        prepared, args = self.dispatch_arguments(messages=[])
        result = self.drive(prepared, args)
        self.assertEqual(result["phase"], "uncertain")
        self.assertEqual(self.send.call_count, 1)
        claim = args["root"] / "dispatch.claim"
        before = {p.name: p.read_bytes() for p in claim.iterdir()}
        self.assertEqual(self.drive(prepared, args)["phase"], "refused")
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(before, {p.name: p.read_bytes() for p in claim.iterdir()})

    def test_same_binding_never_dispatches_twice_from_another_root(self):
        # F1: ownership of the first dispatch follows the binding, not the caller's dispatch root.
        native = self.module().native
        def unsent(case, prepared, args):
            with patch.object(case.module(), "publish_dispatch_intent", side_effect=OSError("PRIVATE-SENTINEL")):
                return case.drive(prepared, args)
        stages = {
            "reserved-unsent": (None, unsent, "refused", 0, (True, False, False)),
            "reserved-lost-ack": ([], None, "uncertain", 1, (True, False, False)),
            "bound": ([protocol_fixture.notification(), protocol_fixture.reply()], None, "uncertain", 1, (True, True, False)),
            "closed": (None, None, "terminal-observed", 1, (True, True, True)),
        }
        for stage, (messages, first_drive, first_phase, sends, recorded) in stages.items():
            with self.subTest(stage=stage):
                case = DispatchTests(methodName="runTest")
                case.setUp()
                try:
                    prepared, args = case.dispatch_arguments(messages=messages)
                    first = first_drive(case, prepared, args) if first_drive else case.drive(prepared, args)
                    self.assertEqual((first["phase"], case.send.call_count), (first_phase, sends))
                    chain = native._read_binding_chain(args["journal_root"], "binding-new")
                    self.assertEqual(tuple(chain[k] is not None for k in ("reservation", "consumption", "closure")),
                                     recorded)
                    before = native.inspect_binding(args["journal_root"], "binding-new", vault_root=case.vault)
                    other = case.root / "other-dispatch"
                    retry = case.drive(prepared, {**args, "root": other})
                    self.assertEqual((retry["phase"], retry["gaps"]), ("refused", ["preflight-refused"]))
                    self.assertEqual(case.send.call_count, sends)
                    self.assertFalse(other.exists())
                    self.assertEqual(native.inspect_binding(args["journal_root"], "binding-new",
                                                            vault_root=case.vault), before)
                    self.assertFalse(native._read_binding_chain(args["journal_root"], "binding-new")["gaps"])
                finally:
                    case.doCleanups()

    def test_same_attempt_never_dispatches_again_from_another_journal(self):
        # R1: ownership of the first dispatch follows the attempt record in the vault, not the journal.
        for stage, messages, first_phase in (("uncertain", [], "uncertain"), ("closed", None, "terminal-observed")):
            with self.subTest(stage=stage):
                case = DispatchTests(methodName="runTest")
                case.setUp()
                try:
                    prepared, args = case.dispatch_arguments(messages=messages)
                    self.assertEqual(case.drive(prepared, args)["phase"], first_phase)
                    other = {**args, "root": case.root / "dispatch-two", "journal_root": case.root / "journal-two"}
                    retry = case.drive(prepared, other)
                    self.assertEqual((retry["phase"], retry["gaps"]), ("refused", ["preflight-refused"]))
                    self.assertEqual(case.send.call_count, 1)
                    self.assertFalse(other["root"].exists())
                    self.assertFalse(other["journal_root"].exists())
                finally:
                    case.doCleanups()

    def test_journal_lock_contention_does_not_burn_the_attempt(self):
        prepared, args = self.dispatch_arguments()
        args["journal_root"].mkdir(mode=0o700)
        lock = args["journal_root"] / ".bindings.lock"
        lock.mkdir(mode=0o700)
        busy = self.drive(prepared, args)
        self.assertEqual((busy["phase"], busy["gaps"], self.send.call_count), ("refused", ["preflight-refused"], 0))
        self.assertFalse((self.vault / prepared["replay_ref"]["manifest"]).parent.joinpath("dispatch.owner").exists())
        lock.rmdir()
        self.assertEqual(self.drive(prepared, args)["phase"], "terminal-observed")
        self.assertEqual(self.send.call_count, 1)

    def test_unavailable_journal_does_not_burn_the_attempt(self):
        # N1: binding-unavailable publishes nothing, so ownership is released like lock contention.
        prepared, args = self.dispatch_arguments()
        owner = (self.vault / prepared["replay_ref"]["manifest"]).parent / "dispatch.owner"
        missing = self.root / "missing-parent" / "journal"
        refused = self.drive(prepared, {**args, "journal_root": missing})
        self.assertEqual((refused["phase"], refused["gaps"], self.send.call_count), ("refused", ["preflight-refused"], 0))
        self.assertFalse(owner.exists())
        self.assertEqual(self.drive(prepared, args)["phase"], "terminal-observed")
        self.assertEqual(self.send.call_count, 1)

    def test_open_binding_on_the_same_checkout_burns_the_attempt(self):
        # binding-conflict is the same code with or without a published marker, so it never releases ownership.
        busy, busy_args = self.dispatch_arguments(messages=[])
        self.assertEqual(self.drive(busy, busy_args)["phase"], "uncertain")
        self.identity = dict(self.identity, attempt_id="attempt-2", binding_id="binding-2")
        self.config["execution"]["binding_id"] = "binding-2"
        self.restore = self.root / "restored-2"
        prepared, args = self.dispatch_arguments()
        args = {**args, "root": self.root / "dispatch-2"}
        self.assertEqual(self.drive(prepared, args)["phase"], "refused")
        self.assertTrue((self.vault / prepared["replay_ref"]["manifest"]).parent.joinpath("dispatch.owner").is_dir())
        self.assertEqual(self.drive(prepared, {**args, "root": self.root / "dispatch-3"})["phase"], "refused")
        self.assertEqual(self.send.call_count, 1)

    def test_journal_replaced_before_send_is_refused(self):
        # The recorded journal identity is rechecked immediately before the only send.
        prepared, args = self.dispatch_arguments()
        module = self.module()
        real = module.publish_dispatch_intent
        def swap(*a, **k):
            path = real(*a, **k)
            args["journal_root"].rename(self.root / "journal-moved")
            args["journal_root"].mkdir(mode=0o700)
            return path
        with patch.object(module, "publish_dispatch_intent", side_effect=swap):
            result = self.drive(prepared, args)
        self.assertEqual(result["phase"], "refused")
        self.send.assert_not_called()

    def test_new_legitimate_attempt_dispatches_after_the_first_closed(self):
        prepared, args = self.dispatch_arguments()
        self.assertEqual(self.drive(prepared, args)["phase"], "terminal-observed")
        for index, journal in ((2, args["journal_root"]), (3, self.root / "journal-three")):
            with self.subTest(journal=journal.name):
                self.identity = dict(self.identity, attempt_id=f"attempt-{index}", binding_id=f"binding-{index}")
                self.config["execution"]["binding_id"] = f"binding-{index}"
                self.restore = self.root / f"restored-{index}"
                fresh, fresh_args = self.dispatch_arguments()
                result = self.drive(fresh, {**fresh_args, "root": self.root / f"dispatch-{index}", "journal_root": journal})
                self.assertEqual((result["phase"], result["gaps"]), ("terminal-observed", []))
                self.assertEqual(self.send.call_count, index)

    def test_two_processes_with_distinct_roots_dispatch_one_binding_once(self):
        # F1: real cross-process contention on one binding and one shared journal.
        # "in-flight": the second process arms after the first released the binding lock but
        # while its dispatch is still in send. "simultaneous": both race for the lock.
        context = multiprocessing.get_context("spawn")
        def receive(connection):
            self.assertTrue(connection.poll(30), "dispatch process did not report")
            return connection.recv()
        for scenario, shared_journal in (("in-flight", True), ("simultaneous", True),
                                         ("in-flight", False), ("simultaneous", False)):
            with self.subTest(scenario=scenario, shared_journal=shared_journal):
                case = DispatchTests(methodName="runTest")
                case.setUp()
                connections, children, roots = [], [], [case.root / "dispatch-one", case.root / "dispatch-two"]
                try:
                    prepared, args = case.dispatch_arguments()
                    args.pop("send")
                    for index, root in enumerate(roots):
                        parent, child = context.Pipe()
                        hold = scenario == "in-flight" and index == 0
                        journal = args["journal_root"] if shared_journal else case.root / f"journal-{index}"
                        process = context.Process(target=drive_in_process,
                                                  args=(prepared, {**args, "root": root, "journal_root": journal},
                                                        child, hold))
                        process.start()
                        child.close()
                        connections.append(parent)
                        children.append(process)
                    first, second = connections
                    if scenario == "in-flight":
                        first.send("start")
                        self.assertEqual(receive(first), "in-flight")
                        second.send("start")
                        results = [None, receive(second)]
                        first.send("release")
                        results[0] = receive(first)
                    else:
                        for connection in connections:
                            connection.send("start")
                        results = [receive(connection) for connection in connections]
                    for process in children:
                        process.join(timeout=30)
                        self.assertFalse(process.is_alive(), "bounded dispatch process did not finish")
                        self.assertEqual(process.exitcode, 0)
                    self.assertEqual(sum(r["sends"] for r in results), 1, results)
                    refused = [r for r in results if r.get("phase") == "refused"]
                    self.assertEqual([r["gaps"] for r in refused], [["preflight-refused"]], results)
                    sender = [r for r in results if r["sends"] == 1]
                    self.assertIn(sender[0].get("phase"), ("terminal-observed", "uncertain"), results)
                    if scenario == "in-flight":
                        self.assertEqual(results[0]["phase"], "terminal-observed", results)
                    self.assertEqual(sum((root / "dispatch.claim").exists() for root in roots), 1)
                finally:
                    for process in children:
                        if process.is_alive():
                            process.kill()
                            process.join()
                    case.doCleanups()

    def test_concurrent_dispatch_from_another_root_while_first_is_in_flight_is_refused(self):
        # F1: a second driver racing the in-flight first dispatch must be refused before sending.
        prepared, args = self.dispatch_arguments()
        concurrent, other, inner_send = [], self.root / "concurrent-dispatch", Mock()
        def send(payload):
            concurrent.append(self.drive(prepared, {**args, "root": other, "send": inner_send}))
        args["send"] = send
        outer = self.drive(prepared, args)
        self.assertEqual([r["phase"] for r in concurrent], ["refused"])
        inner_send.assert_not_called()
        self.assertFalse(other.exists())
        self.assertEqual(outer["phase"], "terminal-observed")

    def test_callback_and_interrupt_failures_preserve_intent(self):
        for error in (OSError("PRIVATE-SENTINEL"), TimeoutError("PRIVATE-SENTINEL"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                case = DispatchTests(methodName="runTest")
                case.setUp()
                try:
                    prepared, args = case.dispatch_arguments()
                    args["send"].side_effect = error
                    result = case.drive(prepared, args)
                    self.assertEqual(result["phase"], "uncertain")
                    self.assertNotIn("PRIVATE-SENTINEL", json.dumps(result))
                    self.assertEqual(case.send.call_count, 1)
                    self.assertTrue((args["root"] / "dispatch.claim/intent.json").exists())
                    self.assertFalse((args["journal_root"] / "binding-new/binding/closure.json").exists())
                finally:
                    case.doCleanups()

    def test_binding_uses_exact_published_event_bytes(self):
        prepared, args = self.dispatch_arguments()
        self.assertEqual(self.drive(prepared, args)["phase"], "terminal-observed")
        base = args["journal_root"] / "binding-new"
        for name, key in (("consumption", "start_event_ref"), ("closure", "terminal_event_ref")):
            record = json.loads((base / "binding" / (name + ".json")).read_bytes())
            ref = record[key]
            self.assertEqual(ref["sha256"], hashlib.sha256((base / "events" / (ref["event_key"] + ".json")).read_bytes()).hexdigest())
        consumed = json.loads((base / "binding/consumption.json").read_bytes())
        self.assertEqual(consumed["source_kind"], "synthetic")
        self.assertEqual(consumed["turn_id"], "turn-a")

    def test_no_legacy_start_receipt_or_accounting_side_effect(self):
        prepared, args = self.dispatch_arguments()
        self.drive(prepared, args)
        self.assertFalse((self.repo / ".007").exists())
        self.assertFalse(any(self.vault.rglob("*receipt*")))
        self.assertFalse(any(self.root.rglob("*.sqlite")))

    def test_bootstrap_request_scope_or_prestate_mismatch_never_sends(self):
        prepared, args = self.dispatch_arguments()
        bad_cases = []
        bad = copy.deepcopy(args); bad["bootstrap"]["request_id"] = "other"; bad_cases.append(bad)
        bad = copy.deepcopy(args); bad["request"]["params"]["input"][0]["text"] = "different"; bad_cases.append(bad)
        bad = copy.deepcopy(args); bad["request"]["params"]["model"] = "other"; bad_cases.append(bad)
        for bad in bad_cases:
            bad["send"] = self.send
            self.assertEqual(self.drive(prepared, bad)["phase"], "refused")
        (self.repo / "task.txt").write_text("changed after bootstrap")
        self.assertEqual(self.drive(prepared, args)["phase"], "refused")
        self.assertEqual(self.send.call_count, 0)

    def test_result_publication_uncertainty_stays_inconclusive(self):
        prepared, args = self.dispatch_arguments()
        module = self.module()
        publish = module.capture.write_bytes_no_replace
        def fail_result(path, data, label):
            publish(path, data, label)
            if path.name == "result.json":
                raise module.capture.PublishedArtifactError("PRIVATE-SENTINEL")
        with patch.object(module.capture, "write_bytes_no_replace", side_effect=fail_result):
            result = self.drive(prepared, args)
        self.assertEqual(result["phase"], "uncertain")
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.drive(prepared, args)["phase"], "refused")

    def test_protocol_error_after_consumption_preserves_claim_without_close(self):
        prepared, args = self.dispatch_arguments(messages=[protocol_fixture.reply(), protocol_fixture.notification()])
        args["messages"].append(("stdout", b'{"error":{"message":"PRIVATE-SENTINEL"}}'))
        result = self.drive(prepared, args)
        self.assertEqual(result["phase"], "uncertain")
        self.assertNotIn("PRIVATE-SENTINEL", json.dumps(result))
        base = args["journal_root"] / "binding-new/binding"
        self.assertTrue((base / "consumption.json").exists())
        self.assertFalse((base / "closure.json").exists())
        self.assertEqual(self.drive(prepared, args)["phase"], "refused")
        self.assertEqual(self.send.call_count, 1)

    def test_intent_publication_failure_never_sends(self):
        prepared, args = self.dispatch_arguments()
        module = self.module()
        publish = module.capture.write_bytes_no_replace
        def fail_intent(path, data, label):
            publish(path, data, label)
            if path.name == "intent.json":
                raise module.capture.PublishedArtifactError("PRIVATE-SENTINEL")
        with patch.object(module.capture, "write_bytes_no_replace", side_effect=fail_intent):
            result = self.drive(prepared, args)
        self.assertIn(result["phase"], ("uncertain", "refused"))
        self.assertEqual(self.send.call_count, 0)
        self.assertTrue((args["root"] / "dispatch.claim/intent.json").exists())
        self.drive(prepared, args)
        self.assertEqual(self.send.call_count, 0)


class RetentionTests(ProspectiveFixture):
    dispatch_arguments = DispatchTests.dispatch_arguments
    drive = DispatchTests.drive

    def setUp(self):
        super().setUp()
        self.oracle = self.root / "oracle.json"
        self.oracle.write_bytes(b'{"expected":"value = 3\\n"}\n')
        self.oracle_hash = hashlib.sha256(self.oracle.read_bytes()).hexdigest()
        environment = {"offline": True, "oracle": {"path": str(self.oracle), "sha256": self.oracle_hash}}
        (self.repo / "environment.json").write_text(json.dumps(environment))

    def observation(self, prepared):
        return dict(scope="offline-calibration", source_kind="synthetic", project_id="project-new",
            task_id="task-new", attempt_id="attempt-new", replay_ref=prepared["replay_ref"], checks=[],
            **{k: None for k in ("served_provider", "served_model", "served_effort", "tokens", "wall_s",
                                 "cost_usd", "cost_source", "cost_status", "repair_rounds")})

    def retain(self, prepared, args, observation=None):
        module = self.module()
        self.assertTrue(hasattr(module, "retain_offline_candidate"), "offline candidate retention is missing")
        return module.retain_offline_candidate(prepared, observation or self.observation(prepared), repo=self.repo,
            journal_root=args["journal_root"], vault_root=self.vault,
            observation_path=self.root / "observation.json", restore_to=self.root / "candidate")

    def report(self, prepared, protocol, candidate=None, exits=None):
        self.assertTrue(hasattr(self.module(), "qualification_report"), "qualification report is missing")
        return self.module().qualification_report(prepared, protocol, candidate=candidate, oracle_exits=exits,
                                                  journal_root=self.root / "journal", vault_root=self.vault)

    def test_report_derives_dispatch_and_retention_from_sources_not_caller_claims(self):
        # R2/R3: a refused resend or a partial observation must not read as preserved or retained evidence.
        prepared, args = self.dispatch_arguments()
        flags = lambda r: (r["dispatch_correlated"], r["terminal_observed"], r["candidate_retained"])
        self.assertEqual(flags(self.report(prepared, {"phase": "terminal-observed"}, {"state": "case-retained"})),
                         (False, False, False))
        terminal = self.drive(prepared, args)
        self.assertEqual(terminal["phase"], "terminal-observed")
        self.assertEqual(flags(self.report(prepared, terminal, {"state": "case-retained"})), (True, True, False))
        copied = self.root / "journal-copy"
        shutil.copytree(args["journal_root"], copied)
        report = self.module().qualification_report(prepared, terminal, candidate=None, oracle_exits=None,
                                                    journal_root=copied, vault_root=self.vault)
        self.assertEqual(flags(report), (False, False, False))

    def test_report_rejects_a_closed_chain_with_a_later_conflict(self):
        prepared, args = self.dispatch_arguments()
        terminal = self.drive(prepared, args)
        native = self.module().native
        reservation = json.loads((args["journal_root"] / "binding-new/binding/reservation.json").read_bytes())
        with self.assertRaises(native.BindingError):
            native.arm_binding(args["journal_root"], "binding-new", {**reservation, "dispatch_id": "dispatch-b"},
                               vault_root=self.vault)
        report = self.report(prepared, terminal)
        self.assertEqual((report["dispatch_correlated"], report["terminal_observed"]), (False, False))

    def test_retention_requires_the_journal_recorded_for_the_attempt(self):
        # R1: a byte-identical copy of the journal is not the journal that owned the dispatch.
        prepared, args = self.dispatch_arguments()
        self.assertEqual(self.drive(prepared, args)["phase"], "terminal-observed")
        copied = self.root / "journal-copy"
        shutil.copytree(args["journal_root"], copied)
        with self.assertRaises(ValueError) as caught:
            self.retain(prepared, {**args, "journal_root": copied})
        self.assertEqual(str(caught.exception), "unit-invalid")
        self.assertFalse((self.root / "observation.json").exists())
        self.assertFalse((self.root / "candidate").exists())
        self.assertEqual(self.retain(prepared, args)["state"], "case-retained")

    def test_terminal_and_empty_managed_list_do_not_prove_quiescence(self):
        prepared, args = self.dispatch_arguments()
        terminal = self.drive(prepared, args)
        for hints in ({}, {"quiescence": True}, {"managed_terminals": []}, {"exit_code": 0, "pid": None}):
            report = self.report(prepared, {**terminal, **hints})
            self.assertFalse(report["runtime_qualified"])
            self.assertFalse(report["replay_ready"])
            self.assertFalse(report["economic_eligible"])
            self.assertIsNone(report["cost_usd"])
            self.assertIn("writer-boundary-unproved", report["gaps"])

    def test_late_detached_writer_invalidates_capture_claim(self):
        prepared, args = self.dispatch_arguments()
        terminal = self.drive(prepared, args)
        child = subprocess.Popen([sys.executable, "-c",
            "import sys; from pathlib import Path; sys.stdin.readline(); Path(sys.argv[1]).write_bytes(b'value = 4\\n')",
            str(self.repo / "tracked.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertIsNone(child.poll())
            self.assertFalse(self.report(prepared, terminal)["runtime_qualified"])
            child.communicate(b"go\n", timeout=5)
            self.assertEqual(child.returncode, 0)
            self.assertEqual((self.repo / "tracked.py").read_bytes(), b"value = 4\n")
            self.assertFalse(self.report(prepared, terminal)["runtime_qualified"])
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=5)

    def test_fresh_candidate_restores_without_original_and_controls_discriminate(self):
        prepared, args = self.dispatch_arguments()
        terminal = self.drive(prepared, args)
        subprocess.run([sys.executable, "-c",
            "import sys; from pathlib import Path; Path(sys.argv[1]).write_bytes(b'value = 3\\n')",
            str(self.repo / "tracked.py")], check=True, timeout=5)
        candidate = self.retain(prepared, args)
        self.assertEqual(candidate["state"], "case-retained")
        self.assertIn("v2-execution-unqualified", candidate["gaps"])
        self.repo.rename(self.root / "original-unavailable")
        second = self.root / "candidate-second"
        self.host.capture.restore_candidate(self.vault, "project-new", "task-new", prepared["replay_ref"],
                                            second, expected_attempt_id="attempt-new")
        self.assertEqual((second / "tracked.py").read_bytes(), b"value = 3\n")
        self.assertEqual((self.restore / "tracked.py").read_bytes(), b"value = 2\n")
        self.assertEqual(hashlib.sha256(self.oracle.read_bytes()).hexdigest(), self.oracle_hash)
        wrong = self.root / "wrong.py"
        wrong.write_bytes(b"value = 4\n")
        code = "import json,sys; from pathlib import Path; sys.exit(0 if Path(sys.argv[1]).read_bytes()==json.loads(Path(sys.argv[2]).read_bytes())['expected'].encode() else 1)"
        exits = [subprocess.run([sys.executable, "-c", code, str(p), str(self.oracle)], timeout=5).returncode
                 for p in (second / "tracked.py", wrong)]
        self.assertEqual(exits, [0, 1])
        report = self.report(prepared, terminal, candidate, exits)
        self.assertEqual(report["oracle_exits"], [0, 1])
        self.assertTrue(report["candidate_retained"])
        self.assertTrue(report["input_restored"])
        for key in ("runtime_qualified", "replay_ready", "causal_eligible", "economic_eligible"):
            self.assertFalse(report[key])
        stored = self.vault / "project-new/attempt-new/outputs/files/tracked.py"
        stored.write_bytes(b"value = 4\n")
        with self.assertRaises(ValueError):
            self.host.capture.restore_candidate(self.vault, "project-new", "task-new", prepared["replay_ref"],
                                                self.root / "corrupt-restore", expected_attempt_id="attempt-new")

    def test_candidate_corruption_scope_drift_oracle_mutation_and_missing_close_reject(self):
        for mutation in ("input", "extra", "closure", "oracle", "ref", "receipt", "symlink"):
            with self.subTest(mutation=mutation):
                case = RetentionTests(methodName="runTest")
                case.setUp()
                try:
                    prepared, args = case.dispatch_arguments()
                    terminal = case.drive(prepared, args)
                    observation = case.observation(prepared)
                    (case.repo / "tracked.py").write_bytes(b"value = 3\n")
                    if mutation == "input": (case.repo / "authority.json").write_text("changed")
                    if mutation == "extra": (case.repo / "outside.txt").write_text("extra")
                    if mutation == "closure": (args["journal_root"] / "binding-new/binding/closure.json").unlink()
                    if mutation == "oracle": case.oracle.write_text("changed")
                    if mutation == "ref": prepared["replay_ref"]["sha256"] = "0" * 64
                    if mutation == "receipt": observation["cost_usd"] = 0
                    if mutation == "symlink":
                        (case.repo / "tracked.py").unlink()
                        (case.repo / "tracked.py").symlink_to(case.oracle)
                    with self.assertRaisesRegex(ValueError, "^unit-invalid$"):
                        case.retain(prepared, args, observation)
                    self.assertFalse(case.report(prepared, terminal)["replay_ready"])
                finally:
                    case.doCleanups()

    def test_retention_destinations_cannot_modify_source_or_evidence_roots(self):
        prepared, args = self.dispatch_arguments()
        self.drive(prepared, args)
        (self.repo / "tracked.py").write_bytes(b"value = 3\n")
        for root in (self.repo, self.restore, self.vault, args["journal_root"]):
            for field in ("observation_path", "restore_to"):
                paths = dict(observation_path=self.root / "observation.json", restore_to=self.root / "candidate")
                paths[field] = root / "nested"
                with self.subTest(root=root.name, field=field), self.assertRaisesRegex(ValueError, "^unit-invalid$"):
                    self.module().retain_offline_candidate(prepared, self.observation(prepared), repo=self.repo,
                        journal_root=args["journal_root"], vault_root=self.vault, **paths)
                self.assertFalse((root / "nested").exists())
                self.assertFalse((self.root / "observation.json").exists())
                self.assertFalse((self.vault / "project-new/attempt-new/result.json").exists())

    def test_subprocess_failure_during_retention_is_sanitized_before_side_effects(self):
        # F2: a Git timeout while retaining leaves only the exact error and publishes nothing.
        module = self.module()
        errors = (subprocess.TimeoutExpired(["git", "-C", "PRIVATE-SENTINEL"], 30),
                  subprocess.CalledProcessError(128, ["git", "-C", "PRIVATE-SENTINEL"]))
        for error in errors:
            with self.subTest(error=type(error).__name__):
                case = RetentionTests(methodName="runTest")
                case.setUp()
                try:
                    prepared, args = case.dispatch_arguments()
                    self.assertEqual(case.drive(prepared, args)["phase"], "terminal-observed")
                    (case.repo / "tracked.py").write_bytes(b"value = 3\n")
                    with patch.object(module.capture, "_revision", side_effect=error), \
                            self.assertRaises(ValueError) as caught:
                        case.retain(prepared, args)
                    self.assertEqual(str(caught.exception), "unit-invalid")
                    self.assertIsNone(caught.exception.__cause__)
                    self.assertTrue(caught.exception.__suppress_context__)
                    self.assertNotIn("PRIVATE-SENTINEL", repr(caught.exception))
                    self.assertFalse((case.root / "observation.json").exists())
                    self.assertFalse((case.root / "candidate").exists())
                finally:
                    case.doCleanups()


class LauncherTests(ProspectiveFixture):
    # Task 11 (r29): vault and journal come from fixed authority, never from the caller; the oracle exists only after the terminal.
    dispatch_arguments = DispatchTests.dispatch_arguments
    observation = RetentionTests.observation

    def setUp(self):
        super().setUp()
        self.oracle = self.root / "oracle.json"
        self.oracle_bytes = b'{"expected":"value = 3\\n"}\n'
        environment = {"offline": True, "oracle": {"path": str(self.oracle),
                                                    "sha256": hashlib.sha256(self.oracle_bytes).hexdigest()}}
        (self.repo / "environment.json").write_text(json.dumps(environment))
        self.oracle.write_bytes(self.oracle_bytes)
        self.home = self.root / "home"
        self.home.mkdir(mode=0o700)
        environ = patch.dict(os.environ, {"HOME": str(self.home)})
        environ.start()
        self.addCleanup(environ.stop)
        self.vault = self.home / ".007-framework/replay"
        self.journal = self.home / ".007-framework/journal"
        self.calls = []

    def launcher(self):
        self.assertTrue(hasattr(self.module(), "launch_unit"), "launcher core is missing")
        return self.module().launch_unit

    def launch(self, messages=None, during=None, oracle_present=False):
        prepared, args = self.dispatch_arguments(messages)
        if not oracle_present:
            self.oracle.unlink()
        def send(payload):
            self.calls.append("send")
            self.assertFalse(self.oracle.exists())
            (self.repo / "tracked.py").write_bytes(b"value = 3\n")  # the producer writes during its turn
            if during:
                during()
        def materialize(path):
            self.calls.append("oracle")
            self.assertEqual(Path(path), self.oracle)
            self.assertTrue((self.journal / "binding-new/binding/closure.json").exists())
            Path(path).write_bytes(self.oracle_bytes)
        result = self.launcher()(prepared, args["messages"], bootstrap=args["bootstrap"], request=args["request"],
            root=args["root"], send=send, materialize_oracle=materialize, observation=self.observation(prepared),
            observation_path=self.root / "observation.json", restore_to=self.root / "candidate")
        return prepared, args, result

    def test_fixed_roots_and_oracle_materialized_only_after_the_closed_terminal(self):
        self.assertFalse({"vault_root", "journal_root", "repo"} & set(inspect.signature(self.launcher()).parameters))
        prepared, args, result = self.launch()
        self.assertEqual((result["protocol"]["phase"], result["candidate"]["state"]), ("terminal-observed", "case-retained"))
        self.assertEqual(self.calls, ["send", "oracle"])
        owner = json.loads((self.vault / "project-new/attempt-new/dispatch.owner/journal.json").read_bytes())
        self.assertEqual(owner["path"], str(self.journal))
        self.assertFalse(args["journal_root"].exists())

    def test_oracle_on_disk_before_dispatch_refuses_without_sending(self):
        with self.assertRaisesRegex(ValueError, "^unit-invalid$"):
            self.launch(oracle_present=True)
        self.assertEqual(self.calls, [])
        self.assertFalse((self.root / "dispatch/dispatch.claim").exists())
        self.assertFalse(self.journal.exists())

    def test_no_terminal_never_materializes_the_oracle(self):
        prepared, args, result = self.launch(messages=[])
        self.assertEqual((result["protocol"]["phase"], result["candidate"]), ("uncertain", None))
        self.assertEqual(self.calls, ["send"])
        self.assertFalse(self.oracle.exists())

    def test_oracle_appearing_during_generation_blocks_retention(self):
        prepared, args, result = self.launch(during=lambda: self.oracle.write_bytes(self.oracle_bytes))
        self.assertEqual((result["protocol"]["phase"], result["candidate"]), ("terminal-observed", None))
        self.assertIn("oracle-present-during-generation", result["protocol"]["gaps"])
        self.assertEqual(self.calls, ["send"])
        self.assertFalse((self.root / "candidate").exists())

    def test_retention_failure_after_dispatch_is_a_gap_not_an_exception(self):
        prepared, args, result = self.launch(during=lambda: (self.repo / "outside.txt").write_text("extra"))
        self.assertEqual((result["protocol"]["phase"], result["candidate"]), ("terminal-observed", None))
        self.assertIn("retention-failed", result["protocol"]["gaps"])
        self.assertEqual(self.calls, ["send", "oracle"])


if __name__ == "__main__":
    unittest.main()
