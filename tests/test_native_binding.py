"""Offline binding custody only; no native sessions, models or business inputs."""
import copy
import hashlib
import io
import json
import os
import multiprocessing
import stat
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import test_replay_capture_v2 as fixtures
from test_native_capture import event
import native_capture as core

NOW = "2026-10-16T00:00:00Z"


def reserve_in_process(journal, reservation, vault, connection, mask=None):
    connection.recv()
    if mask is not None:
        os.umask(mask)  # Only this disposable child, never the test runner or production process.
    try:
        with patch.object(os, "umask", side_effect=AssertionError("must honor caller umask")), \
             patch.object(os, "chmod", side_effect=AssertionError("must not widen permissions")):
            result = core.arm_binding(Path(journal), reservation["binding_id"], reservation, vault_root=Path(vault))
    except core.BindingError as error:
        result = error.code
    connection.send(result)
    connection.close()


class BindingFixture(unittest.TestCase):
    def setUp(self):
        self.host = fixtures.ReplayCaptureV2Tests(methodName="runTest")
        self.host.setUp()
        self.addCleanup(self.host.doCleanups)
        self.repo, self.root, self.vault = self.host.repo, self.host.root, self.host.vault
        self.journal = self.root / "journal"
        config = self.host.config_v2()
        (self.repo / "authority.json").write_text(json.dumps(
            {"schema": "007-framework/authority/v1", "allow": [], "deny": ["execute"]}))
        config["files"].append("authority.json")
        self.ref = self.host.retain(config=config)
        self.producer = {"namespace": "fixture-native", "adapter": "fixture-hooks",
                         "surface": "desktop", "host_version": None,
                         "session_id": "s1", "thread_id": "thread-a"}
        info = self.repo.stat()
        self.reservation = {"schema": "007-framework/binding-reservation/v1", "project_id": "project",
            "task_id": "task", "attempt_id": "attempt-a", "binding_id": "binding-a", "replay_ref": self.ref,
            "checkout": {"path": str(self.repo.resolve()), "device": info.st_dev, "inode": info.st_ino},
            "authority_file": "authority.json", "producer": self.producer, "dispatch_id": "dispatch-a",
            "source_kind": "synthetic", "observed_at": NOW}

    def require_contract(self):
        self.assertTrue(hasattr(core, "validate_binding_record"), "B2 record contracts are missing")

    def input(self, value=None, check_checkout=True):
        self.require_contract()
        return core._binding_input(self.vault, value or self.reservation, check_checkout=check_checkout)

    def rewrite_manifest(self, transform, raw_transform=lambda value: value):
        path = self.vault / self.ref["manifest"]
        value = json.loads(path.read_bytes())
        transform(value)
        payload = raw_transform(json.dumps(value).encode())
        path.write_bytes(payload)
        self.ref["sha256"] = hashlib.sha256(payload).hexdigest()

    def another_reservation(self, binding="binding-b", attempt="attempt-b"):
        value = copy.deepcopy(self.reservation)
        config = self.host.config_v2()
        config["files"].append("authority.json")
        config["execution"]["binding_id"] = binding
        value.update(binding_id=binding, attempt_id=attempt,
                     replay_ref=self.host.retain(attempt, config=config))
        return value

    def arm(self, value=None):
        self.assertTrue(hasattr(core, "arm_binding"), "B2 reservation publication is missing")
        value = value or self.reservation
        return core.arm_binding(self.journal, value["binding_id"], value, vault_root=self.vault)

    def stored(self, kind="reservation", binding="binding-a"):
        return self.journal / binding / "binding" / (kind + ".json")

    def event_ref(self, kind, **changes):
        value = event(kind, **{"adapter": "fixture-hooks", "surface": "desktop", "turn_id": "turn-a", **changes})
        core.append_event(self.journal, "binding-a", value)
        path = self.journal / "binding-a/events" / (value["event_key"] + ".json")
        return {"event_key": value["event_key"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def consumption(self):
        return {"schema": "007-framework/binding-consumption/v1",
            "reservation_sha256": hashlib.sha256(self.stored().read_bytes()).hexdigest(),
            "dispatch_id": "dispatch-a", "source_kind": "synthetic", "producer": self.producer,
            "turn_id": "turn-a", "start_event_ref": self.event_ref("turn_start"), "observed_at": NOW}

    def closure(self, cancel=False):
        return {"schema": "007-framework/binding-close/v1",
            "reservation_sha256": hashlib.sha256(self.stored().read_bytes()).hexdigest(),
            "consumption_sha256": None if cancel else hashlib.sha256(self.stored("consumption").read_bytes()).hexdigest(),
            "outcome": "cancelled-before-consume" if cancel else "stop-observed",
            "terminal_event_ref": None if cancel else self.event_ref("turn_stop"), "observed_at": NOW}

    def consume(self, value):
        self.assertTrue(hasattr(core, "consume_binding"), "B2 consumption is missing")
        return core.consume_binding(self.journal, "binding-a", value, vault_root=self.vault)

    def close(self, value):
        self.assertTrue(hasattr(core, "close_binding"), "B2 closure is missing")
        return core.close_binding(self.journal, "binding-a", value, vault_root=self.vault)


class BindingContractTests(BindingFixture):
    def test_exact_record_shapes_and_types(self):
        self.require_contract()
        consumption = {"schema": "007-framework/binding-consumption/v1", "reservation_sha256": "a" * 64,
            "dispatch_id": "dispatch-a", "source_kind": "declared", "producer": self.producer,
            "turn_id": "turn-a", "start_event_ref": {"event_key": "b" * 64, "sha256": "c" * 64},
            "observed_at": NOW}
        closure = {"schema": "007-framework/binding-close/v1", "reservation_sha256": "a" * 64,
            "consumption_sha256": None, "outcome": "cancelled-before-consume",
            "terminal_event_ref": None, "observed_at": NOW}
        for kind, value in (("reservation", self.reservation), ("consumption", consumption), ("closure", closure)):
            self.assertEqual(core.validate_binding_record(value, kind), value)
            candidates = [{**value, "extra": "PRIVATE-SENTINEL"}, {**value, "observed_at": "2026-01-01"},
                          {**value, "schema": "bad"}]
            candidates.extend({k: v for k, v in value.items() if k != missing} for missing in value)
            for candidate in candidates:
                before = copy.deepcopy(candidate)
                with self.subTest(kind=kind), self.assertRaises(core.BindingError) as error:
                    core.validate_binding_record(candidate, kind)
                self.assertEqual(error.exception.code, "binding-integrity")
                self.assertEqual(candidate, before)
        mutations = [("source_kind", "qualified"), ("dispatch_id", "../unsafe"), ("task_id", None),
                     ("authority_file", "/outside.json"), ("observed_at", "2026-02-31T00:00:00Z")]
        for key, value in mutations:
            with self.subTest(field=key), self.assertRaises(core.BindingError):
                core.validate_binding_record({**self.reservation, key: value}, "reservation")
        for key, value in (("device", True), ("inode", -1), ("path", "relative")):
            with self.subTest(field=key), self.assertRaises(core.BindingError):
                core.validate_binding_record({**self.reservation, "checkout": {
                    **self.reservation["checkout"], key: value}}, "reservation")
        for key, value in (("session_id", None), ("thread_id", ""), ("namespace", "../n"),
                           ("adapter", True), ("host_version", "x" * 129), ("surface", "other")):
            with self.subTest(field=key), self.assertRaises(core.BindingError):
                core.validate_binding_record({**self.reservation, "producer": {**self.producer, key: value}}, "reservation")
        for bad in ({**consumption, "turn_id": None}, {**consumption, "start_event_ref": {"path": "/private"}},
                    {**closure, "outcome": "success"}, {**closure, "consumption_sha256": "a" * 64},
                    {**closure, "outcome": "stop-observed"}):
            with self.assertRaises(core.BindingError):
                core.validate_binding_record(bad, "consumption" if "turn_id" in bad else "closure")
        with self.assertRaises(core.BindingError):
            core.validate_binding_record({**self.reservation, "authority_file": "x" * 16385}, "reservation")
        self.assertFalse(self.journal.exists())

    def test_reference_and_captured_authority_are_exact(self):
        self.assertEqual(self.input()["attempt_id"], "attempt-a")
        (self.repo / "authority.json").write_text("LIVE-PRIVATE-SENTINEL")
        self.assertEqual(self.input()["task_id"], "task")
        changes = [("project_id", "other"), ("task_id", "other"), ("attempt_id", "other"),
                   ("binding_id", "other"), ("authority_file", "not-captured.json"),
                   ("replay_ref", {**self.ref, "sha256": "a" * 64}),
                   ("checkout", {**self.reservation["checkout"], "path": str(self.root)})]
        for key, value in changes:
            with self.subTest(field=key), self.assertRaises(core.BindingError):
                self.input({**self.reservation, key: value})
        for key, value in (("adapter", "another"), ("surface", "terminal")):
            with self.subTest(field=key), self.assertRaises(core.BindingError):
                self.input({**self.reservation, "producer": {**self.producer, key: value}})
        command_ref = self.host.retain("command-a", kind="command")
        with self.assertRaises(core.BindingError):
            self.input({**self.reservation, "attempt_id": "command-a", "replay_ref": command_ref})
        legacy_ref = self.host.fixture.capture()
        with self.assertRaises(core.BindingError):
            self.input({**self.reservation, "replay_ref": legacy_ref})
        self.assertFalse(self.journal.exists())

    def test_duplicate_keys_and_checkout_substitution(self):
        self.require_contract()
        path = self.vault / self.ref["manifest"]
        original, digest = path.read_bytes(), self.ref["sha256"]
        path.write_bytes(b'{"task_id":"task",' + original.lstrip()[1:])
        self.ref["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(core.BindingError):
            self.input()
        path.write_bytes(original)
        self.ref["sha256"] = digest
        authority = path.parent / "inputs/authority.json"
        authority.write_bytes(b'{"schema":"007-framework/authority/v1","allow":[],"allow":[],"deny":["execute"]}')
        payload = authority.read_bytes()
        def update(value):
            record = next(a for a in value["artifacts"] if a["path"] == "authority.json")
            record.update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        self.rewrite_manifest(update)
        with self.assertRaises(core.BindingError):
            self.input()
        authority.write_text('{"schema":"007-framework/authority/v1","allow":[],"deny":["execute"]}')
        payload = authority.read_bytes()
        self.rewrite_manifest(update)
        path.chmod(0o644)
        with self.assertRaises(core.BindingError):
            self.input()
        path.chmod(0o600)
        self.repo.rename(self.root / "old-repo")
        self.assertEqual(self.input(check_checkout=False)["task_id"], "task")
        self.repo.mkdir()
        with self.assertRaises(core.BindingError):
            self.input()
        self.repo.rmdir()
        self.repo.symlink_to(self.root / "old-repo", target_is_directory=True)
        with self.assertRaises(core.BindingError):
            self.input()
        self.assertFalse(self.journal.exists())

    def test_strict_json_and_nested_types(self):
        for raw in (b'{"source_kind":"declared","source_kind":"synthetic"}', b'{"inode":NaN}'):
            with self.assertRaises(core.CaptureError):
                core.decode_json(raw)
        for name in ("producer", "checkout", "replay_ref"):
            for replacement in (None, [], {**self.reservation[name], "extra": None}):
                with self.subTest(field=name, value=replacement), self.assertRaises(core.BindingError):
                    core.validate_binding_record({**self.reservation, name: replacement}, "reservation")
        for name, value in (("device", float("nan")), ("inode", True), ("path", str(self.repo) + "/../repo")):
            with self.subTest(field=name), self.assertRaises(core.BindingError):
                core.validate_binding_record({**self.reservation, "checkout": {
                    **self.reservation["checkout"], name: value}}, "reservation")
        for authority in ("../authority.json", str(self.repo / "authority.json")):
            with self.assertRaises(core.BindingError):
                self.input({**self.reservation, "authority_file": authority})

    def test_owner_access_and_in_read_checkout_substitution(self):
        with patch.object(core.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(core.BindingError) as error:
                self.input()
            self.assertEqual(str(error.exception), "binding-integrity")
        with patch.object(core.replay_capture, "validate_replay_ref", side_effect=PermissionError("PRIVATE-SENTINEL")):
            with self.assertRaises(core.BindingError) as error:
                self.input()
            self.assertEqual(str(error.exception), "binding-unavailable")
        original = core.replay_capture.validate_replay_ref
        def replace_after_read(*args, **kwargs):
            value = original(*args, **kwargs)
            self.repo.rename(self.root / "old-checkout")
            self.repo.mkdir()
            return value
        with patch.object(core.replay_capture, "validate_replay_ref", side_effect=replace_after_read):
            with self.assertRaises(core.BindingError) as error:
                self.input()
            self.assertEqual(str(error.exception), "binding-integrity")
        self.assertEqual(self.input(check_checkout=False)["task_id"], "task")
        authority = (self.vault / self.ref["manifest"]).parent / "inputs/authority.json"
        authority.rename(authority.with_suffix(".saved"))
        authority.symlink_to(self.root / "old-checkout/authority.json")
        with self.assertRaises(core.BindingError):
            self.input(check_checkout=False)
        self.assertFalse(self.journal.exists())


class BindingReservationTests(BindingFixture):
    def test_umask_refusal_cleans_only_new_empty_setup(self):
        for existing_root in (False, True):
            for mask in (0, 0o077, 0o177):
                with self.subTest(existing_root=existing_root, mask=oct(mask)):
                    f = self.fresh()
                    if existing_root:
                        f.journal.mkdir(mode=0o700)
                        owner = f.journal.stat().st_ino
                    parent, child = multiprocessing.get_context("spawn").Pipe()
                    process = multiprocessing.get_context("spawn").Process(target=reserve_in_process,
                        args=(str(f.journal), f.reservation, str(f.vault), child, mask))
                    try:
                        process.start()
                        child.close()
                        parent.send("start")
                        process.join(timeout=10)
                        self.assertFalse(process.is_alive())
                        self.assertEqual(process.exitcode, 0)
                        self.assertTrue(parent.poll(1))
                        self.assertEqual(parent.recv(), "binding-unavailable" if mask == 0o177 else "reserved")
                    finally:
                        if process.is_alive():
                            process.terminate()
                            process.join(timeout=10)
                        parent.close()
                        child.close()
                    self.assertFalse((f.journal / ".bindings.lock").exists())
                    if existing_root:
                        self.assertEqual(f.journal.stat().st_ino, owner)
                    elif mask == 0o177:
                        self.assertFalse(f.journal.exists())
                    if mask == 0o177:
                        self.assertEqual(f.arm(), "reserved")
                    self.assertEqual(json.loads(f.stored().read_bytes()), f.reservation)

    def test_owner_stripped_publication_directory_is_clean_refusal(self):
        for name in ("binding-a", "binding"):
            with self.subTest(directory=name):
                f = self.fresh()
                mkdir = Path.mkdir
                def stripped_mkdir(path, *args, **kwargs):
                    if path.name == name:
                        kwargs["mode"] = 0o600
                    return mkdir(path, *args, **kwargs)
                with patch.object(Path, "mkdir", stripped_mkdir):
                    with self.assertRaises(core.BindingError) as error:
                        f.arm()
                self.assertEqual(error.exception.code, "binding-unavailable")
                self.assertEqual(list(f.journal.iterdir()), [])
                self.assertEqual(f.arm(), "reserved")

    def test_preexisting_owner_stripped_paths_are_preserved(self):
        for lock in (False, True):
            with self.subTest(lock=lock):
                f = self.fresh()
                f.journal.mkdir(mode=0o700)
                target = f.journal / ".bindings.lock" if lock else f.journal
                if lock:
                    target.mkdir(mode=0o700)
                target.chmod(0o600)
                self.addCleanup(target.chmod, 0o700)
                before = target.lstat()
                with self.assertRaises(core.BindingError) as error:
                    f.arm()
                self.assertEqual(error.exception.code, "binding-lock-busy" if lock else "binding-integrity")
                self.assertEqual((target.lstat().st_ino, target.lstat().st_mode), (before.st_ino, before.st_mode))

    def test_umask_cleanup_preserves_unknown_replaced_or_nonempty_setup(self):
        for where in ("root", "lock"):
            for fault in ("unknown", "uid", "replaced", "parent", "nonempty", "mode", "unreadable"):
                with self.subTest(where=where, fault=fault):
                    f = self.fresh()
                    f.journal.mkdir(mode=0o700)
                    target = f.journal if where == "root" else f.journal / ".bindings.lock"
                    if where == "root":
                        target.rmdir()
                    mkdir, lstat, sync = Path.mkdir, Path.lstat, core._binding_sync
                    changed = []
                    def create(path, *args, **kwargs):
                        result = mkdir(path, *args, **kwargs)
                        if path == target:
                            if fault == "nonempty":
                                (path / "foreign").write_bytes(b"preserve")
                            path.chmod(0o755 if fault == "mode" else 0 if fault == "unreadable" else 0o600)
                        return result
                    def inspect(path, *args, **kwargs):
                        info = lstat(path, *args, **kwargs)
                        if path == target and fault == "unknown":
                            raise OSError("owner unavailable")
                        if path == target and fault == "uid":
                            fields = list(info)
                            fields[4] = os.getuid() + 1
                            return os.stat_result(fields)
                        return info
                    def synchronize(path):
                        if path == target.parent and target.exists() and not changed and fault in ("replaced", "parent"):
                            changed.append(True)
                            moved = target.parent if fault == "parent" else target
                            # Root's parent contains the fixture: replace only lock's parent.
                            if where == "root" and fault == "parent":
                                raise OSError("parent cannot be verified")
                            moved.rename(f.root / "preserved")
                            mkdir(moved, mode=0o700)
                            if fault == "parent":
                                mkdir(target, mode=0o600)
                        return sync(path)
                    try:
                        with patch.object(Path, "mkdir", create), patch.object(Path, "lstat", inspect), \
                             patch.object(core, "_binding_sync", synchronize):
                            with self.assertRaises(core.BindingError) as error:
                                f.arm()
                        self.assertEqual(error.exception.code, "binding-publication-uncertain")
                        self.assertTrue(target.exists())
                        if fault == "nonempty":
                            target.chmod(0o700)
                            self.assertEqual((target / "foreign").read_bytes(), b"preserve")
                    finally:
                        if target.exists():
                            target.chmod(0o700)
                        preserved = f.root / "preserved"
                        if preserved.exists():
                            preserved.chmod(0o700)

    def test_umask_cleanup_failure_or_interrupt_remains_uncertain(self):
        for point in ("mkdir", "rmdir", "sync"):
            for error_type in (OSError, KeyboardInterrupt, ImportError):
                if point == "mkdir" and error_type is OSError:
                    continue
                with self.subTest(point=point, error=error_type.__name__):
                    f = self.fresh()
                    f.journal.mkdir(mode=0o700)
                    target = f.journal / ".bindings.lock"
                    mkdir, rmdir, sync = Path.mkdir, Path.rmdir, core._binding_sync
                    removed = []
                    def create(path, *args, **kwargs):
                        result = mkdir(path, *args, **kwargs)
                        if path == target:
                            path.chmod(0o600)
                            if point == "mkdir":
                                raise error_type("after creation")
                        return result
                    def remove(path):
                        if path == target and point == "rmdir":
                            raise error_type("before removal")
                        result = rmdir(path)
                        removed.append(path)
                        return result
                    def synchronize(path):
                        if point == "sync" and removed:
                            raise error_type("after removal")
                        return sync(path)
                    with patch.object(Path, "mkdir", create), patch.object(Path, "rmdir", remove), \
                         patch.object(core, "_binding_sync", synchronize):
                        with self.assertRaises(core.BindingError) as error:
                            f.arm()
                    self.assertEqual(error.exception.code, "binding-publication-uncertain")
                    self.assertEqual(target.exists(), point != "sync")
                    self.assertFalse(f.stored().exists())

    def test_umask_cleanup_rechecks_parent_and_removed_path(self):
        for change in ("parent", "path"):
            with self.subTest(change=change):
                f = self.fresh()
                f.journal.mkdir(mode=0o700)
                lock = f.journal / ".bindings.lock"
                mkdir, rmdir = Path.mkdir, Path.rmdir
                def create(path, *args, **kwargs):
                    if path == lock:
                        kwargs["mode"] = 0o600
                    return mkdir(path, *args, **kwargs)
                def remove(path):
                    rmdir(path)
                    if path == lock:
                        if change == "parent":
                            f.journal.rename(f.root / "preserved-root")
                            mkdir(f.journal, mode=0o700)
                        mkdir(lock, mode=0o700)
                with patch.object(Path, "mkdir", create), patch.object(Path, "rmdir", remove):
                    with self.assertRaises(core.BindingError) as error:
                        f.arm()
                self.assertEqual(error.exception.code, "binding-publication-uncertain")
                self.assertTrue(lock.is_dir())
                self.assertFalse(f.stored().exists())

    def test_safe_root_creation_race_rechecks_directory(self):
        original = Path.mkdir
        def concurrent_root(path, *args, **kwargs):
            if path == self.journal:
                original(path, mode=0o700)
                raise FileExistsError("concurrent root")
            return original(path, *args, **kwargs)
        with patch.object(Path, "mkdir", concurrent_root):
            self.assertEqual(self.arm(), "reserved")
        self.assertEqual(json.loads(self.stored().read_bytes()), self.reservation)

    def fresh(self):
        fixture = BindingFixture(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_root_limits_and_foreign_lock(self):
        self.journal.mkdir(mode=0o700)
        for i in range(127):
            (self.journal / f"a-{i}").mkdir(mode=0o700)
        self.assertEqual(self.arm(), "reserved")
        with self.assertRaises(core.BindingError):
            self.arm(self.another_reservation())
        self.assertFalse(self.stored(binding="binding-b").exists())
        for variant in ("foreign-lock", "root-symlink", "child-symlink", "file", "partial", "bad-marker", "large-marker"):
            with self.subTest(variant=variant):
                f = self.fresh()
                f.journal.mkdir(mode=0o700)
                if variant == "foreign-lock":
                    path = f.journal / ".bindings.lock"
                    path.mkdir(mode=0o700)
                    inode = path.stat().st_ino
                elif variant == "root-symlink":
                    f.journal.rename(f.root / "real-journal")
                    f.journal.symlink_to(f.root / "real-journal", target_is_directory=True)
                elif variant == "child-symlink":
                    (f.journal / "other").symlink_to(f.repo, target_is_directory=True)
                elif variant == "file":
                    (f.journal / "other").write_text("PRIVATE-SENTINEL")
                else:
                    directory = f.journal / "other/binding"
                    directory.mkdir(mode=0o700, parents=True)
                    directory.parent.chmod(0o700)
                    if variant != "partial":
                        other = f.another_reservation("other")
                        core.write_bytes_no_replace(directory / "reservation.json", json.dumps(other).encode(), "fixture")
                        (directory / "gaps").mkdir(mode=0o700)
                        name = "unexpected" if variant == "bad-marker" else "binding-conflict"
                        payload = b'{}' if variant == "bad-marker" else b' ' * 1025
                        core.write_bytes_no_replace(directory / "gaps" / (name + ".json"), payload, "fixture")
                with self.assertRaises(core.BindingError):
                    f.arm()
                self.assertFalse(f.stored().exists())
                if variant == "foreign-lock":
                    self.assertEqual(path.stat().st_ino, inode)

    def test_two_processes_cannot_reserve_same_resource(self):
        reservations = [self.reservation, self.another_reservation()]
        context = multiprocessing.get_context("spawn")
        connections, children = [], []
        try:
            for value in reservations:
                parent, child = context.Pipe()
                process = context.Process(target=reserve_in_process,
                    args=(str(self.journal), value, str(self.vault), child))
                process.start()
                child.close()
                connections.append(parent)
                children.append(process)
            for connection in connections:
                connection.send("start")
            for process in children:
                process.join(timeout=10)
                self.assertFalse(process.is_alive(), "bounded reservation process did not finish")
                self.assertEqual(process.exitcode, 0)
            results = [connection.recv() for connection in connections]
            self.assertEqual(results.count("reserved"), 1, results)
            self.assertTrue(set(results) <= {"reserved", "binding-lock-busy", "binding-conflict"}, results)
            records = list(self.journal.glob("*/binding/reservation.json"))
            self.assertEqual(len(records), 1)
            self.assertIn(json.loads(records[0].read_bytes()), reservations)
            winner = json.loads(records[0].read_bytes())
            closure = {"schema": "007-framework/binding-close/v1",
                "reservation_sha256": hashlib.sha256(records[0].read_bytes()).hexdigest(),
                "consumption_sha256": None, "outcome": "cancelled-before-consume",
                "terminal_event_ref": None, "observed_at": NOW}
            self.assertEqual(core.close_binding(self.journal, winner["binding_id"], closure,
                                                vault_root=self.vault), "closed")
        finally:
            for process in children:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=10)
            for connection in connections:
                connection.close()

    def test_publication_and_unlock_fault_boundaries(self):
        for fault in ("mkdir-root", "mkdir-lock", "fsync-root", "fsync-file", "link", "post-link", "cleanup", "rmdir", "post-rmdir", "lock-replaced"):
            with self.subTest(fault=fault):
                f = self.fresh()
                if fault != "mkdir-root":
                    f.journal.mkdir(mode=0o700)
                lock = f.journal / ".bindings.lock"
                original_mkdir, original_fsync = Path.mkdir, os.fsync
                original_link, original_unlink, original_rmdir = os.link, os.unlink, Path.rmdir
                injected = []
                def mkdir(path, *args, **kwargs):
                    if (fault == "mkdir-root" and path == f.journal or fault == "mkdir-lock" and path == lock):
                        injected.append(True)
                        raise OSError("PRIVATE-SENTINEL")
                    return original_mkdir(path, *args, **kwargs)
                def fsync(fd):
                    info = os.fstat(fd)
                    is_root = info.st_ino == f.journal.stat().st_ino and stat.S_ISDIR(info.st_mode)
                    fail = (fault == "fsync-root" and is_root and not injected or
                            fault == "fsync-file" and stat.S_ISREG(info.st_mode) or
                            fault == "post-link" and f.stored().exists() and info.st_ino == f.stored().parent.stat().st_ino or
                            fault == "post-rmdir" and is_root and f.stored().exists() and not lock.exists())
                    if fail:
                        injected.append(True)
                        raise OSError("PRIVATE-SENTINEL")
                    return original_fsync(fd)
                def link(source, destination, *args, **kwargs):
                    if fault == "link":
                        injected.append(True)
                        raise OSError("PRIVATE-SENTINEL")
                    result = original_link(source, destination, *args, **kwargs)
                    if fault == "lock-replaced":
                        lock.rename(f.root / "preserved-lock")
                        original_mkdir(lock, mode=0o700)
                        injected.append(True)
                    return result
                def unlink(path, *args, **kwargs):
                    if fault == "cleanup":
                        injected.append(True)
                        raise OSError("PRIVATE-SENTINEL")
                    return original_unlink(path, *args, **kwargs)
                def rmdir(path, *args, **kwargs):
                    if fault == "rmdir" and path == lock:
                        injected.append(True)
                        raise OSError("PRIVATE-SENTINEL")
                    return original_rmdir(path, *args, **kwargs)
                with patch.object(Path, "mkdir", mkdir), patch.object(os, "fsync", fsync), \
                     patch.object(os, "link", link), patch.object(os, "unlink", unlink), patch.object(Path, "rmdir", rmdir):
                    with self.assertRaises(core.BindingError) as error:
                        f.arm()
                self.assertTrue(injected, "fault injection did not reach the real syscall")
                uncertain = fault in ("post-link", "cleanup", "rmdir", "post-rmdir", "lock-replaced")
                self.assertEqual(error.exception.code, "binding-publication-uncertain" if uncertain else "binding-unavailable")
                self.assertEqual(f.stored().exists(), uncertain)
                self.assertEqual(lock.exists(), uncertain and fault != "post-rmdir")
                self.assertEqual(len(list(f.journal.glob("*/binding/reservation.json"))), int(uncertain))
                if lock.exists():
                    with self.assertRaises(core.BindingError) as second:
                        f.arm({**f.reservation, "binding_id": "new-key"})
                    self.assertEqual(second.exception.code, "binding-lock-busy")

    def test_marker_failure_preserves_lock_and_original(self):
        self.arm()
        before = self.stored().read_bytes()
        original = os.link
        def deny_marker(source, destination):
            if Path(destination).name == "binding-conflict.json":
                raise OSError("PRIVATE-SENTINEL")
            return original(source, destination)
        with patch.object(os, "link", deny_marker):
            with self.assertRaises(core.BindingError) as error:
                self.arm({**self.reservation, "dispatch_id": "conflicting"})
        self.assertEqual(error.exception.code, "binding-publication-uncertain")
        self.assertEqual(self.stored().read_bytes(), before)
        self.assertTrue((self.journal / ".bindings.lock").exists())
        self.assertFalse((self.stored().parent / "gaps/binding-conflict.json").exists())

    def test_chain_reader_validates_bytes_links_events_and_markers(self):
        self.arm()
        reservation_bytes = self.stored().read_bytes()
        start = event("turn_start", adapter="fixture-hooks", surface="desktop", turn_id="turn-a")
        core.append_event(self.journal, "binding-a", start)
        path = self.journal / "binding-a/events" / (start["event_key"] + ".json")
        consumed = {"schema": "007-framework/binding-consumption/v1",
            "reservation_sha256": hashlib.sha256(reservation_bytes).hexdigest(),
            "dispatch_id": "dispatch-a", "source_kind": "synthetic", "producer": self.producer,
            "turn_id": "turn-a", "start_event_ref": {"event_key": start["event_key"],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}, "observed_at": NOW}
        consumption_bytes = json.dumps(consumed).encode()
        core.write_bytes_no_replace(self.stored("consumption"), consumption_bytes, "fixture")
        self.assertEqual(core._read_binding_chain(self.journal, "binding-a"), {
            "reservation": self.reservation, "consumption": consumed, "closure": None, "gaps": []})
        for key, value in (("reservation_sha256", "0" * 64), ("dispatch_id", "wrong"),
                           ("turn_id", "other"), ("producer", {**self.producer, "thread_id": "other"}),
                           ("start_event_ref", {**consumed["start_event_ref"], "sha256": "0" * 64})):
            self.stored("consumption").write_text(json.dumps({**consumed, key: value}))
            with self.subTest(field=key), self.assertRaises(core.BindingError):
                core._read_binding_chain(self.journal, "binding-a")
        self.stored("consumption").write_bytes(consumption_bytes)
        for payload in (b'{"dispatch_id":"dispatch-a",' + consumption_bytes[1:],
                        consumption_bytes.replace(b'"synthetic"', b'NaN')):
            self.stored("consumption").write_bytes(payload)
            with self.assertRaises(core.BindingError):
                core._read_binding_chain(self.journal, "binding-a")
        self.stored("consumption").write_bytes(consumption_bytes)
        path.unlink()
        with self.assertRaises(core.BindingError):
            core._read_binding_chain(self.journal, "binding-a")

    def test_arm_is_durable_idempotent_and_private(self):
        with patch.object(core, "_locked", side_effect=AssertionError("A lock must not be acquired")):
            self.assertEqual(self.arm(), "reserved")
        record = self.stored()
        before, info = record.read_bytes(), record.stat()
        self.assertEqual(json.loads(before), self.reservation)
        self.assertEqual(info.st_mode & 0o777, 0o600)
        for directory in (self.journal, record.parent.parent, record.parent):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.arm({**self.reservation, "observed_at": "2026-10-17T00:00:00Z"}), "reserved")
        self.assertEqual((record.read_bytes(), record.stat().st_ino, record.stat().st_mtime_ns),
                         (before, info.st_ino, info.st_mtime_ns))
        self.assertFalse((self.repo / ".007/tasks").exists())
        self.assertFalse((self.journal / ".bindings.lock").exists())

    def test_exclusion_uses_namespace_session_and_checkout_identity(self):
        self.assertEqual(self.arm(), "reserved")
        other = self.another_reservation()
        other["producer"].update(namespace="other", session_id="other", thread_id="other")
        with self.assertRaises(core.BindingError) as error:
            self.arm(other)
        self.assertEqual(error.exception.code, "binding-conflict")
        self.assertFalse(self.stored(binding="binding-b").exists())
        self.assertEqual(json.loads(self.stored().read_bytes()), self.reservation)

    def test_rejected_competitor_does_not_poison_winner_lifecycle(self):
        self.arm()
        with self.assertRaises(core.BindingError) as error:
            self.arm(self.another_reservation())
        self.assertEqual(error.exception.code, "binding-conflict")
        self.assertEqual(self.consume(self.consumption()), "bound")
        self.assertEqual(self.close(self.closure()), "closed")
        self.assertFalse((self.journal / "binding-b/binding").exists())
        self.assertEqual(core.inspect_binding(self.journal, "binding-b", vault_root=self.vault)["binding_state"],
                         "absent")

    def test_session_exclusion_is_namespaced_but_not_thread_scoped(self):
        other = BindingFixture(methodName="runTest")
        other.setUp()
        self.addCleanup(other.doCleanups)
        other.journal = self.journal
        reserved = other.another_reservation()
        reserved["producer"]["thread_id"] = "another-thread"
        self.assertEqual(self.arm(), "reserved")
        with self.assertRaises(core.BindingError) as error:
            other.arm(reserved)
        self.assertEqual(error.exception.code, "binding-conflict")
        self.assertFalse(self.stored(binding="binding-b").exists())

    def test_distinct_namespace_and_checkout_can_coexist(self):
        other = BindingFixture(methodName="runTest")
        other.setUp()
        self.addCleanup(other.doCleanups)
        other.journal = self.journal
        reserved = other.another_reservation()
        reserved["producer"]["namespace"] = "another-native"
        self.assertEqual(self.arm(), "reserved")
        self.assertEqual(other.arm(reserved), "reserved")

    def test_checkout_path_and_inode_each_exclude_without_neighbor_vault_scan(self):
        for changed in ({"path": "/unavailable-historical-checkout"}, {"inode": 0, "device": 0}):
            with self.subTest(changed=changed):
                f = self.fresh()
                f.arm()
                old = copy.deepcopy(f.reservation)
                old["checkout"].update(changed)
                f.stored().write_text(json.dumps(old))
                new = f.another_reservation()
                new["producer"].update(namespace="other", session_id="other")
                # Neighbor bytes establish local exclusion, not renewed vault validity.
                (f.vault / f.ref["manifest"]).rename(f.root / "historical-input")
                with self.assertRaises(core.BindingError) as error:
                    f.arm(new)
                self.assertEqual(error.exception.code, "binding-conflict")
                self.assertFalse(f.stored(binding="binding-b").exists())

    def test_only_hash_valid_closure_releases_local_reservation(self):
        self.arm()
        before = self.stored().read_bytes()
        closed = {"schema": "007-framework/binding-close/v1",
            "reservation_sha256": hashlib.sha256(before).hexdigest(), "consumption_sha256": None,
            "outcome": "cancelled-before-consume", "terminal_event_ref": None, "observed_at": NOW}
        core.write_bytes_no_replace(self.stored("closure"), json.dumps(closed).encode(), "fixture")
        self.assertEqual(core._read_binding_chain(self.journal, "binding-a")["closure"], closed)
        self.stored("closure").write_text(json.dumps({**closed, "reservation_sha256": "0" * 64}))
        next_reservation = self.another_reservation()
        with self.assertRaises(core.BindingError):
            self.arm(next_reservation)
        self.assertFalse(self.stored(binding="binding-b").exists())
        self.stored("closure").write_text(json.dumps(closed))
        self.assertEqual(self.arm(next_reservation), "reserved")

    def test_conflict_marker_is_exact_and_blocks_later_idempotency(self):
        self.arm()
        before = self.stored().read_bytes()
        with self.assertRaises(core.BindingError) as error:
            self.arm({**self.reservation, "dispatch_id": "conflicting"})
        self.assertEqual(error.exception.code, "binding-conflict")
        marker = self.stored().parent / "gaps/binding-conflict.json"
        self.assertEqual(json.loads(marker.read_bytes()), {"code": "binding-conflict"})
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.stored().read_bytes(), before)
        with self.assertRaises(core.BindingError):
            self.arm()

    def test_neighbor_markers_deny_admission_but_not_selected_close(self):
        for code in ("binding-conflict", "binding-integrity", "binding-publication-uncertain"):
            with self.subTest(marker=code):
                f = self.fresh()
                f.arm()
                f.close(f.closure(cancel=True))
                f.arm(f.another_reservation())
                closure = {**f.closure(cancel=True), "reservation_sha256":
                    hashlib.sha256(f.stored(binding="binding-b").read_bytes()).hexdigest()}
                directory = f.stored().parent / "gaps"
                directory.mkdir(mode=0o700)
                marker = directory / (code + ".json")
                raw = json.dumps({"code": code}).encode()
                core.write_bytes_no_replace(marker, raw, "fixture")
                self.assertEqual(core.close_binding(f.journal, "binding-b", closure, vault_root=f.vault), "closed")
                closed = f.stored("closure", binding="binding-b")
                before = (closed.read_bytes(), closed.stat().st_ino, closed.stat().st_mtime_ns)
                self.assertEqual(core.close_binding(f.journal, "binding-b", {**closure, "observed_at":
                    "2026-10-17T00:00:00Z"}, vault_root=f.vault), "closed")
                self.assertEqual((closed.read_bytes(), closed.stat().st_ino, closed.stat().st_mtime_ns), before)
                for operation in (lambda: f.arm(), lambda: f.consume(f.consumption())):
                    with self.assertRaises(core.BindingError) as error:
                        operation()
                    self.assertEqual(error.exception.code, "binding-integrity")
                self.assertEqual(marker.read_bytes(), raw)

    def test_saturated_or_malformed_neighbor_does_not_trap_selected_close(self):
        for neighbor in ("saturated", "partial", "malformed", "symlink"):
            for consumed in (False, True):
                with self.subTest(neighbor=neighbor, consumed=consumed):
                    f = self.fresh()
                    f.arm()
                    start = f.consumption()
                    if consumed:
                        f.consume(start)
                    closure = f.closure(cancel=not consumed)
                    if neighbor == "saturated":
                        for i in range(128):
                            core.append_event(f.journal, f"neighbor-{i}", event("session_start"))
                    elif neighbor == "partial":
                        (f.journal / "neighbor/binding").mkdir(mode=0o700, parents=True)
                        (f.journal / "neighbor").chmod(0o700)
                    elif neighbor == "symlink":
                        (f.journal / "neighbor").symlink_to(f.root, target_is_directory=True)
                    else:
                        (f.journal / "unexpected-file").write_bytes(b"preserve")
                    for operation in (lambda: f.arm(), lambda: f.consume(start)):
                        with self.assertRaises(core.BindingError):
                            operation()
                    self.assertEqual(f.close(closure), "closed")
                    self.assertEqual(json.loads(f.stored("closure").read_bytes()), closure)
                    for operation in (lambda: f.arm(), lambda: f.consume(start)):
                        with self.assertRaises(core.BindingError):
                            operation()
                    summary = core.inspect_binding(f.journal, "binding-a", vault_root=f.vault)
                    self.assertEqual(summary["binding_state"], "closed")
                    for flag in ("execution_authorized", "replay_admissible", "economic_admissible"):
                        self.assertIs(summary[flag], False)

    def test_selected_close_still_refuses_own_invalid_chain_or_foreign_lock(self):
        for fault in ("reservation", "marker", "event", "vault", "lock"):
            with self.subTest(fault=fault):
                f = self.fresh()
                f.arm()
                f.consume(f.consumption())
                closure = f.closure()
                if fault == "reservation":
                    f.stored().write_bytes(b"{}")
                elif fault == "marker":
                    directory = f.stored().parent / "gaps"
                    directory.mkdir(mode=0o700)
                    core.write_bytes_no_replace(directory / "binding-integrity.json",
                        b'{"code":"binding-integrity"}', "fixture")
                elif fault == "event":
                    (f.journal / "binding-a/events" / (closure["terminal_event_ref"]["event_key"] + ".json")).write_bytes(b"{}")
                elif fault == "vault":
                    (f.vault / f.ref["manifest"]).write_bytes(b"{}")
                else:
                    (f.journal / ".bindings.lock").mkdir(mode=0o700)
                before = {p: p.read_bytes() for p in f.journal.rglob("*.json")}
                with self.assertRaises(core.BindingError):
                    f.close(closure)
                self.assertFalse(f.stored("closure").exists())
                self.assertEqual({p: p.read_bytes() for p in before}, before)
                self.assertEqual((f.journal / ".bindings.lock").exists(), fault == "lock")

    def test_ordinary_prepublication_failure_removes_only_own_empty_directories(self):
        for existing_case in (False, True):
            for fault in ("mkdir-binding", "sync-created", "file-fsync", "link"):
                with self.subTest(existing_case=existing_case, fault=fault):
                    f = self.fresh()
                    if existing_case:
                        core.append_event(f.journal, "binding-a", event("session_start"))
                    before = {p: p.read_bytes() for p in f.journal.rglob("*.json")}
                    mkdir, sync, fsync, link = Path.mkdir, core._binding_sync, os.fsync, os.link
                    injected = []
                    def fail_mkdir(path, *args, **kwargs):
                        if fault == "mkdir-binding" and path == f.stored().parent:
                            injected.append(True)
                            raise OSError("PRIVATE-SENTINEL")
                        return mkdir(path, *args, **kwargs)
                    def fail_sync(path):
                        if fault == "sync-created" and path == f.stored().parent.parent and not injected:
                            injected.append(True)
                            raise OSError("PRIVATE-SENTINEL")
                        return sync(path)
                    def fail_fsync(fd):
                        if fault == "file-fsync" and stat.S_ISREG(os.fstat(fd).st_mode):
                            injected.append(True)
                            raise OSError("PRIVATE-SENTINEL")
                        return fsync(fd)
                    def fail_link(source, destination, *args, **kwargs):
                        if fault == "link":
                            injected.append(True)
                            raise OSError("PRIVATE-SENTINEL")
                        return link(source, destination, *args, **kwargs)
                    with patch.object(Path, "mkdir", fail_mkdir), patch.object(core, "_binding_sync", fail_sync), \
                         patch.object(os, "fsync", fail_fsync), patch.object(os, "link", fail_link):
                        with self.assertRaises(core.BindingError) as error:
                            f.arm()
                    self.assertTrue(injected)
                    self.assertEqual(error.exception.code, "binding-unavailable")
                    self.assertFalse(f.stored().parent.exists())
                    self.assertEqual(f.stored().parent.parent.exists(), existing_case)
                    self.assertEqual({p: p.read_bytes() for p in f.journal.rglob("*.json")}, before)
                    self.assertFalse((f.journal / ".bindings.lock").exists())
                    self.assertEqual(f.arm(), "reserved")

    def test_cleanup_does_not_claim_concurrently_created_directory(self):
        mkdir = Path.mkdir
        def concurrent_create(path, *args, **kwargs):
            mkdir(path, *args, **kwargs)
            if path == self.stored().parent.parent:
                raise FileExistsError("created by another caller")
        with patch.object(Path, "mkdir", concurrent_create), patch.object(os, "link", side_effect=OSError("before link")):
            with self.assertRaises(core.BindingError) as error:
                self.arm()
        self.assertEqual(error.exception.code, "binding-unavailable")
        self.assertFalse(self.stored().parent.exists())
        self.assertTrue(self.stored().parent.parent.is_dir())
        self.assertFalse((self.journal / ".bindings.lock").exists())

    def test_cleanup_preserves_replaced_nonempty_or_concurrent_A_state(self):
        for change in ("root", "lock", "binding", "nonempty", "concurrent-A", "visible-reservation"):
            with self.subTest(change=change):
                f = self.fresh()
                preserved = f.root / "preserved"
                replacement = f.journal if change == "root" else f.journal / ".bindings.lock" if change == "lock" else f.stored().parent
                def fail_link(source, destination, *args, **kwargs):
                    if change in ("root", "lock", "binding"):
                        replacement.rename(preserved)
                        replacement.mkdir(mode=0o700)
                    elif change == "concurrent-A":
                        core.append_event(f.journal, "binding-a", event("session_start"))
                    else:
                        (f.stored() if change == "visible-reservation" else f.stored().parent / "foreign").write_bytes(b"preserve")
                    raise OSError("before link")
                # A has its own no-replace writer; inject only the B2 reservation link.
                link = os.link
                def reservation_link(source, destination, *args, **kwargs):
                    if Path(destination) == f.stored():
                        return fail_link(source, destination, *args, **kwargs)
                    return link(source, destination, *args, **kwargs)
                with patch.object(os, "link", reservation_link):
                    with self.assertRaises(core.BindingError) as error:
                        f.arm()
                self.assertEqual(error.exception.code, "binding-publication-uncertain")
                if change == "root":
                    self.assertTrue((preserved / ".bindings.lock").is_dir())
                    self.assertTrue((preserved / "binding-a/binding").is_dir())
                else:
                    self.assertTrue((f.journal / ".bindings.lock").is_dir())
                if change in ("root", "lock", "binding"):
                    self.assertTrue(preserved.is_dir())
                    self.assertTrue(replacement.is_dir())
                elif change == "concurrent-A":
                    self.assertEqual(len(list((f.journal / "binding-a/events").glob("*.json"))), 1)
                else:
                    self.assertEqual((f.stored() if change == "visible-reservation" else f.stored().parent / "foreign").read_bytes(), b"preserve")

    def test_cleanup_rechecks_lock_owner_before_unlock(self):
        rmdir = Path.rmdir
        lock = self.journal / ".bindings.lock"
        preserved = self.root / "preserved-lock"
        def replace_lock_after_cleanup(path):
            rmdir(path)
            if path == self.stored().parent:
                lock.rename(preserved)
                lock.mkdir(mode=0o700)
        with patch.object(os, "link", side_effect=OSError("before link")), \
             patch.object(Path, "rmdir", replace_lock_after_cleanup):
            with self.assertRaises(core.BindingError) as error:
                self.arm()
        self.assertEqual(error.exception.code, "binding-publication-uncertain")
        self.assertTrue(preserved.is_dir())
        self.assertTrue(lock.is_dir())
        self.assertFalse(self.stored().exists())

    def test_new_directory_without_verified_owner_is_never_cleaned(self):
        lstat = Path.lstat
        def unknown_owner(path, *args, **kwargs):
            info = lstat(path, *args, **kwargs)
            if path == self.stored().parent:
                raise OSError("cannot verify owner")
            return info
        with patch.object(Path, "lstat", unknown_owner):
            with self.assertRaises(core.BindingError) as error:
                self.arm()
        self.assertEqual(error.exception.code, "binding-publication-uncertain")
        self.assertTrue(self.stored().parent.is_dir())
        self.assertTrue((self.journal / ".bindings.lock").is_dir())
        self.assertFalse(self.stored().exists())

    def test_directory_cleanup_failure_is_uncertain_without_recreation(self):
        for fault in ("rmdir", "fsync"):
            with self.subTest(fault=fault):
                f = self.fresh()
                rmdir, sync = Path.rmdir, core._binding_sync
                removed = []
                def fail_remove(path):
                    if path == f.stored().parent:
                        if fault == "rmdir":
                            raise OSError("cleanup failed")
                        rmdir(path)
                        removed.append(path)
                        return
                    return rmdir(path)
                def fail_sync(path):
                    if removed:
                        raise OSError("cleanup fsync failed")
                    return sync(path)
                with patch.object(os, "link", side_effect=OSError("before link")), \
                     patch.object(Path, "rmdir", fail_remove), patch.object(core, "_binding_sync", fail_sync):
                    with self.assertRaises(core.BindingError) as error:
                        f.arm()
                self.assertEqual(error.exception.code, "binding-publication-uncertain")
                self.assertTrue((f.journal / ".bindings.lock").exists())
                self.assertTrue(f.stored().parent.parent.is_dir())
                self.assertEqual(f.stored().parent.exists(), fault == "rmdir")


class BindingLifecycleTests(BindingFixture):
    def test_every_mutation_checks_root_inventory(self):
        self.arm()
        consumed = self.consumption()
        (self.journal / "unexpected-file").write_text("PRIVATE-SENTINEL")
        with self.assertRaises(core.BindingError):
            self.consume(consumed)
        self.assertFalse(self.stored("consumption").exists())

    def test_live_checkout_is_required_only_for_new_consumption(self):
        self.arm()
        consumed = self.consumption()
        self.repo.rename(self.root / "old-repo")
        self.repo.mkdir()
        with self.assertRaises(core.BindingError):
            self.consume(consumed)
        self.assertFalse(self.stored("consumption").exists())
        self.repo.rmdir()
        (self.root / "old-repo").rename(self.repo)
        self.consume(consumed)
        self.repo.rename(self.root / "old-repo")
        closed = self.closure()
        closed.update(outcome="interrupt-observed", terminal_event_ref=self.event_ref("interrupt"))
        self.assertEqual(self.close(closed), "closed")

    def test_closure_other_turn_and_post_link_failure(self):
        self.arm()
        self.consume(self.consumption())
        closed = self.closure()
        with self.assertRaises(core.BindingError):
            self.close({**closed, "terminal_event_ref": self.event_ref("turn_stop", turn_id="other-turn")})
        self.assertFalse(self.stored("closure").exists())
        original = os.fsync
        def fail_after_link(fd):
            if self.stored("closure").exists() and os.fstat(fd).st_ino == self.stored().parent.stat().st_ino:
                raise OSError("PRIVATE-SENTINEL")
            return original(fd)
        with patch.object(os, "fsync", fail_after_link):
            with self.assertRaises(core.BindingError) as error:
                self.close(closed)
        self.assertEqual(error.exception.code, "binding-publication-uncertain")
        self.assertEqual(json.loads(self.stored("closure").read_bytes()), closed)
        self.assertTrue((self.journal / ".bindings.lock").exists())

    def test_explicit_start_and_terminal_chain(self):
        self.assertEqual(self.arm(), "reserved")
        consumption = self.consumption()
        self.assertEqual(self.consume(consumption), "bound")
        closure = self.closure()
        self.assertEqual(self.close(closure), "closed")
        self.assertEqual(json.loads(self.stored("consumption").read_bytes()), consumption)
        self.assertEqual(json.loads(self.stored("closure").read_bytes()), closure)
        self.assertFalse((self.repo / ".007/tasks").exists())

    def test_cancellation_without_consumption_never_invents_start(self):
        self.arm()
        closure = self.closure(cancel=True)
        self.assertEqual(self.close(closure), "closed")
        self.assertIsNone(closure["consumption_sha256"])
        self.assertIsNone(closure["terminal_event_ref"])
        self.assertFalse(self.stored("consumption").exists())
        with self.assertRaises(core.BindingError):
            self.consume(self.consumption())
        self.assertFalse(self.stored("consumption").exists())

    def test_late_consumption_does_not_poison_closed_binding(self):
        self.arm()
        closed = self.closure(cancel=True)
        self.close(closed)
        before = self.stored("closure").read_bytes()
        with self.assertRaises(core.BindingError) as error:
            self.consume(self.consumption())
        self.assertEqual(error.exception.code, "binding-conflict")
        self.assertEqual(self.close(closed), "closed")
        self.assertEqual(self.stored("closure").read_bytes(), before)
        self.assertFalse((self.stored().parent / "gaps").exists())
        self.assertEqual(self.arm(self.another_reservation()), "reserved")

    def test_cancelled_consume_needs_stored_integrity_not_live_checkout(self):
        self.arm()
        consumed = self.consumption()
        closed = self.closure(cancel=True)
        self.close(closed)
        self.repo.rename(self.root / "unavailable-checkout")
        for replaced in (False, True):
            with self.subTest(replaced=replaced):
                if replaced:
                    self.repo.mkdir()
                before = {p: (p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns)
                          for p in self.journal.rglob("*.json")}
                with self.assertRaises(core.BindingError) as error:
                    self.consume(consumed)
                self.assertEqual(error.exception.code, "binding-conflict")
                summary = core.inspect_binding(self.journal, "binding-a", vault_root=self.vault)
                self.assertEqual(summary["binding_state"], "closed")
                for flag in ("execution_authorized", "replay_admissible", "economic_admissible"):
                    self.assertIs(summary[flag], False)
                self.assertEqual({p: (p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns)
                                  for p in self.journal.rglob("*.json")}, before)
                self.assertFalse((self.stored().parent / "gaps").exists())
        for path in (self.vault / self.ref["manifest"],
                     self.vault / Path(self.ref["manifest"]).parent / "inputs/authority.json",
                     self.stored("closure")):
            with self.subTest(corrupt=path.name):
                raw = path.read_bytes()
                path.write_bytes(b"{}")
                try:
                    with self.assertRaises(core.BindingError) as error:
                        self.consume(consumed)
                    self.assertEqual(error.exception.code, "binding-integrity")
                finally:
                    path.write_bytes(raw)
        self.assertFalse(self.stored("consumption").exists())

    def test_event_and_dispatch_mismatches_never_advance(self):
        self.arm()
        consumed = self.consumption()
        mutants = [{**consumed, key: value} for key, value in (("dispatch_id", "other"),
            ("turn_id", "other"), ("source_kind", "declared"), ("reservation_sha256", "0" * 64),
            ("start_event_ref", {"event_key": "0" * 64, "sha256": "0" * 64}),
            ("start_event_ref", {**consumed["start_event_ref"], "sha256": "0" * 64}),
            ("start_event_ref", self.event_ref("turn_stop"))) ]
        mutants.extend({**consumed, "producer": {**self.producer, key: "other"}} for key in self.producer)
        mutants.append({k: v for k, v in consumed.items() if k != "dispatch_id"})
        for value in mutants:
            with self.subTest(value=value), self.assertRaises(core.BindingError):
                self.consume(value)
            self.assertFalse(self.stored("consumption").exists())
        self.assertEqual(self.consume(consumed), "bound")
        wrong = self.closure()
        wrong["terminal_event_ref"] = consumed["start_event_ref"]
        with self.assertRaises(core.BindingError):
            self.close(wrong)
        with self.assertRaises(core.BindingError):
            self.close(self.closure(cancel=True))
        self.assertFalse(self.stored("closure").exists())

    def test_closed_duplicates_do_not_reopen_or_bypass_integrity(self):
        self.arm()
        consumed = self.consumption()
        self.consume(consumed)
        closed = self.closure()
        self.close(closed)
        records = [self.stored(kind) for kind in ("reservation", "consumption", "closure")]
        before = [(p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns) for p in records]
        self.repo.rename(self.root / "unavailable-checkout")
        for action, record in ((self.arm, self.reservation), (self.consume, consumed), (self.close, closed)):
            self.assertEqual(action({**record, "observed_at": "2026-10-17T00:00:00Z"}), "closed")
        self.assertEqual([(p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns) for p in records], before)
        manifest = self.vault / self.ref["manifest"]
        manifest.write_bytes(manifest.read_bytes() + b" ")
        with self.assertRaises(core.BindingError):
            self.consume(consumed)
        with self.assertRaises(core.BindingError):
            self.close(closed)

    def test_event_host_version_cannot_override_reserved_producer(self):
        self.arm()
        consumed = self.consumption()
        path = self.journal / "binding-a/events" / (consumed["start_event_ref"]["event_key"] + ".json")
        value = json.loads(path.read_bytes())
        value["host_version"] = "different-host"
        raw = json.dumps(value).encode()
        path.write_bytes(raw)
        consumed["start_event_ref"]["sha256"] = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(core.BindingError) as error:
            self.consume(consumed)
        self.assertEqual(error.exception.code, "binding-integrity")
        self.assertFalse(self.stored("consumption").exists())
        self.assertEqual(path.read_bytes(), raw)

    def test_no_implicit_fork_resume_child_or_route_continuation(self):
        self.arm()
        consumed = self.consumption()
        child_ref = self.event_ref("turn_start", agent_id="child", gaps=sorted(core.EVENT_GAPS))
        with self.assertRaises(core.BindingError):
            self.consume({**consumed, "start_event_ref": child_ref})
        self.assertFalse(self.stored("consumption").exists())
        self.assertEqual(self.consume(consumed), "bound")
        before = self.stored("consumption").read_bytes()
        with self.assertRaises(core.BindingError) as error:
            self.consume({**consumed, "turn_id": "resumed-turn"})
        self.assertEqual(error.exception.code, "binding-conflict")
        self.assertEqual(self.stored("consumption").read_bytes(), before)

    def test_lifecycle_crash_boundaries(self):
        self.arm()
        self.assertIsNone(core._read_binding_chain(self.journal, "binding-a")["consumption"])
        consumed = self.consumption()
        # A published start by itself cannot select a dispatch or consume a reservation.
        self.assertFalse(self.stored("consumption").exists())
        original = os.fsync
        def fail_after_link(fd):
            if self.stored("consumption").exists() and os.fstat(fd).st_ino == self.stored().parent.stat().st_ino:
                raise OSError("PRIVATE-SENTINEL")
            return original(fd)
        with patch.object(os, "fsync", fail_after_link):
            with self.assertRaises(core.BindingError) as error:
                self.consume(consumed)
        self.assertEqual(error.exception.code, "binding-publication-uncertain")
        self.assertEqual(json.loads(self.stored("consumption").read_bytes()), consumed)
        self.assertTrue((self.journal / ".bindings.lock").exists())
        self.assertFalse(self.stored("closure").exists())


class BindingInspectionTests(BindingFixture):
    def inspect(self):
        self.assertTrue(hasattr(core, "inspect_binding"), "B2 observation is missing")
        return core.inspect_binding(self.journal, "binding-a", vault_root=self.vault)

    def assert_summary(self, state, source=None):
        summary = self.inspect()
        self.assertEqual(set(summary), {"schema", "project_id", "task_id", "attempt_id", "binding_id",
            "binding_state", "source_kind", "coverage", "gaps", "execution_authorized",
            "replay_admissible", "economic_admissible"})
        self.assertEqual(summary["schema"], "007-framework/binding-summary/v1")
        self.assertEqual(summary["binding_state"], state)
        self.assertEqual(summary["coverage"], "invalid" if state == "invalid" else "partial")
        self.assertEqual(summary["source_kind"], source)
        self.assertEqual(summary["binding_id"], "binding-a")
        self.assertEqual(summary["gaps"], sorted(set(summary["gaps"])))
        self.assertIn("binding-correlation-unqualified", summary["gaps"])
        for field in ("execution_authorized", "replay_admissible", "economic_admissible"):
            self.assertIs(summary[field], False)
        for private in (str(self.repo), str(self.vault), "authority.json", "PRIVATE-SENTINEL"):
            self.assertNotIn(private, json.dumps(summary))
        return summary

    def test_exact_summary_and_all_admissions_false(self):
        self.journal.mkdir(mode=0o700)
        summary = self.assert_summary("absent")
        self.assertTrue(all(summary[k] is None for k in ("project_id", "task_id", "attempt_id")))
        self.arm()
        summary = self.assert_summary("reserved", "synthetic")
        self.assertEqual([summary[k] for k in ("project_id", "task_id", "attempt_id")], ["project", "task", "attempt-a"])
        self.assertIn("binding-source-synthetic", summary["gaps"])
        self.consume(self.consumption())
        self.assert_summary("bound", "synthetic")
        self.close(self.closure())
        self.assert_summary("closed", "synthetic")

    def test_inspection_is_read_only_and_not_a_snapshot(self):
        self.assert_summary("invalid")
        self.assertFalse(self.journal.exists())
        self.arm()
        self.repo.rename(self.root / "original-unavailable")
        def snapshot():
            return [(str(p.relative_to(self.journal)), p.lstat().st_mode, p.lstat().st_ino,
                     p.lstat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                    for p in [self.journal, *sorted(self.journal.rglob("*"))]]
        before = snapshot()
        self.assert_summary("reserved", "synthetic")
        self.assertEqual(snapshot(), before)
        original = core._binding_input
        def lock_after_read(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.journal / ".bindings.lock").mkdir(mode=0o700)
            return result
        with patch.object(core, "_binding_input", side_effect=lock_after_read):
            self.assert_summary("invalid", "synthetic")
        self.assertTrue((self.journal / ".bindings.lock").exists())

    def test_partial_access_and_disappearing_evidence_never_mean_absent(self):
        self.journal.mkdir(mode=0o700)
        original = Path.lstat
        def denied(path, *args, **kwargs):
            if path == self.journal:
                raise PermissionError("PRIVATE-SENTINEL")
            return original(path, *args, **kwargs)
        with patch.object(Path, "lstat", denied):
            self.assert_summary("invalid")
        self.arm()
        original_read = core.replay_capture._read_private_artifact
        def disappear(case, name, limit):
            if name == "reservation.json":
                (case / name).unlink()
            return original_read(case, name, limit)
        with patch.object(core.replay_capture, "_read_private_artifact", side_effect=disappear):
            self.assert_summary("invalid")
        self.assert_summary("invalid")

    def test_summary_preserves_A_gaps_without_extending_A_schema(self):
        self.arm({**self.reservation, "source_kind": "declared"})
        core.record_gap(self.journal, "binding-a", "hook-unsupported")
        summary = self.assert_summary("invalid", "declared")
        self.assertIn("hook-unsupported", summary["gaps"])
        self.assertIn("binding-source-declared", summary["gaps"])
        self.assertNotIn("binding-correlation-unqualified", core.GAP_CODES)
        lock = self.journal / "binding-a/lock"
        lock.mkdir(mode=0o700)
        before = lock.stat().st_ino
        self.assertIn("lock-busy", self.assert_summary("invalid", "declared")["gaps"])
        self.assertEqual(lock.stat().st_ino, before)

    def test_reference_and_marker_changes_during_read_are_invalid(self):
        self.arm()
        original = core.replay_capture.validate_replay_ref
        manifest = self.vault / self.ref["manifest"]
        before = manifest.read_bytes()
        def change_after_validation(*args, **kwargs):
            value = original(*args, **kwargs)
            manifest.write_bytes(before + b" ")
            return value
        with patch.object(core.replay_capture, "validate_replay_ref", side_effect=change_after_validation):
            self.assert_summary("invalid")
        manifest.write_bytes(before)
        with self.assertRaises(core.BindingError):
            self.arm({**self.reservation, "dispatch_id": "conflict"})
        original_read = core.replay_capture._read_private_artifact
        def remove_marker(case, name, limit):
            if name == "gaps/binding-conflict.json":
                (case / name).unlink()
            return original_read(case, name, limit)
        with patch.object(core.replay_capture, "_read_private_artifact", side_effect=remove_marker):
            self.assert_summary("invalid")

    def test_invalid_selector_does_not_access_or_create_paths(self):
        self.assertTrue(hasattr(core, "inspect_binding"), "B2 observation is missing")
        with patch.object(core, "_read_binding_chain", side_effect=AssertionError("invalid selector reached I/O")):
            for invalid in ("../PRIVATE-SENTINEL", "", None, True):
                with self.subTest(selector=invalid), self.assertRaises(core.BindingError):
                    core.inspect_binding(self.journal, invalid, vault_root=self.vault)
        self.assertFalse(self.journal.exists())


class BindingBoundaryTests(BindingFixture):
    def fresh(self):
        fixture = BindingFixture(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def call(self, fixture, operation, value=None):
        with patch.object(core.sys, "stdin") as source, \
                patch.object(core.sys, "stdout", new_callable=io.StringIO) as out, \
                patch.object(core.sys, "stderr", new_callable=io.StringIO) as err:
            source.buffer.read.return_value = json.dumps(value).encode()
            try:
                code = core.main([operation, "--state-dir", str(fixture.journal),
                                  "--binding-id", "binding-a", "--vault-root", str(fixture.vault)])
            except (KeyboardInterrupt, ImportError) as exc:
                self.fail(f"B2 leaked {type(exc).__name__}")
        return code, out.getvalue(), err.getvalue()

    def prepare(self, operation):
        f = self.fresh()
        if operation == "arm":
            return f, f.reservation, "reservation"
        f.arm()
        value = f.consumption()
        if operation == "consume":
            return f, value, "consumption"
        f.consume(value)
        return f, f.closure(), "closure"

    def test_prepublication_failures_release_only_owned_lock(self):
        for operation in ("arm", "consume", "close"):
            for error, exit_code in ((KeyboardInterrupt, 130), (ImportError, 1)):
                with self.subTest(operation=operation, error=error.__name__):
                    f, value, kind = self.prepare(operation)
                    before = {p: p.read_bytes() for p in f.journal.rglob("*.json")}
                    with patch.object(core, "_binding_input", side_effect=error("PRIVATE-SENTINEL")):
                        self.assertEqual(self.call(f, operation, value), (exit_code, "", "binding-unavailable\n"))
                    self.assertFalse((f.journal / ".bindings.lock").exists())
                    self.assertFalse(f.stored(kind).exists())
                    self.assertTrue(all(p.read_bytes() == raw for p, raw in before.items()))
                    self.assertEqual(self.call(f, operation, value)[0], 0)
                    summary = core.inspect_binding(f.journal, "binding-a", vault_root=f.vault)
                    for flag in ("execution_authorized", "replay_admissible", "economic_admissible"):
                        self.assertIs(summary[flag], False)

    def test_lazy_import_failure_is_sanitized_for_arm_and_inspect(self):
        import builtins
        original = builtins.__import__
        def unavailable(name, *args, **kwargs):
            if name == "framework_cli":
                raise ImportError("PRIVATE-SENTINEL")
            return original(name, *args, **kwargs)
        with patch.object(builtins, "__import__", unavailable):
            self.assertEqual(self.call(self, "arm", self.reservation), (1, "", "binding-unavailable\n"))
        self.assertFalse((self.journal / ".bindings.lock").exists())
        self.assertFalse(self.stored().exists())
        self.arm()
        with patch.object(builtins, "__import__", unavailable):
            code, out, err = self.call(self, "inspect")
        self.assertEqual((code, err), (1, ""))
        summary = json.loads(out)
        self.assertEqual(summary["coverage"], "invalid")
        self.assertIn("binding-unavailable", summary["gaps"])

    def test_input_decoding_interrupt_and_import_failure_are_sanitized(self):
        for error, exit_code in ((KeyboardInterrupt, 130), (ImportError, 1)):
            with self.subTest(error=error.__name__), patch.object(core, "decode_json", side_effect=error("PRIVATE-SENTINEL")):
                self.assertEqual(self.call(self, "arm", self.reservation), (exit_code, "", "binding-unavailable\n"))
            self.assertFalse(self.journal.exists())

    def test_prepublication_sync_failure_releases_owned_lock(self):
        original = core._binding_sync
        for error, exit_code in ((KeyboardInterrupt, 130), (ImportError, 1)):
            with self.subTest(error=error.__name__):
                f = self.fresh()
                lock = f.journal / ".bindings.lock"
                def fail_once(path):
                    if path == f.journal and lock.exists():
                        raise error("PRIVATE-SENTINEL")
                    return original(path)
                with patch.object(core, "_binding_sync", fail_once):
                    self.assertEqual(self.call(f, "arm", f.reservation), (exit_code, "", "binding-unavailable\n"))
                self.assertFalse(lock.exists())
                self.assertFalse(f.stored().exists())

    def test_binding_directory_creation_is_already_publication_uncertainty(self):
        original = Path.mkdir
        for error in (KeyboardInterrupt, ImportError):
            with self.subTest(error=error.__name__):
                f = self.fresh()
                def create_then_fail(path, *args, **kwargs):
                    original(path, *args, **kwargs)
                    if path == f.stored().parent:
                        raise error("PRIVATE-SENTINEL")
                with patch.object(Path, "mkdir", create_then_fail):
                    self.assertEqual(self.call(f, "arm", f.reservation), (1, "", "binding-publication-uncertain\n"))
                self.assertTrue((f.journal / ".bindings.lock").exists())
                self.assertTrue(f.stored().parent.is_dir())
                self.assertFalse(f.stored().exists())

    def test_post_link_failures_preserve_published_record_and_lock(self):
        original = os.link
        for operation in ("arm", "consume", "close"):
            for error in (KeyboardInterrupt, ImportError):
                with self.subTest(operation=operation, error=error.__name__):
                    f, value, kind = self.prepare(operation)
                    before = {p: p.read_bytes() for p in f.journal.rglob("*.json")}
                    def publish_then_fail(source, destination, *args, **kwargs):
                        original(source, destination, *args, **kwargs)
                        raise error("PRIVATE-SENTINEL")
                    with patch.object(os, "link", publish_then_fail):
                        self.assertEqual(self.call(f, operation, value), (1, "", "binding-publication-uncertain\n"))
                    self.assertEqual(json.loads(f.stored(kind).read_bytes()), value)
                    self.assertTrue(all(p.read_bytes() == raw for p, raw in before.items()))
                    self.assertTrue((f.journal / ".bindings.lock").exists())
                    self.assertEqual(self.call(f, operation, value), (1, "", "binding-lock-busy\n"))
                    summary = core.inspect_binding(f.journal, "binding-a", vault_root=f.vault)
                    self.assertEqual(summary["coverage"], "invalid")
                    for flag in ("execution_authorized", "replay_admissible", "economic_admissible"):
                        self.assertIs(summary[flag], False)

    def test_publisher_failures_before_link_and_after_return_stay_uncertain(self):
        original = core._binding_publish
        for point in ("writer-entry", "publisher-return"):
            for error in (KeyboardInterrupt, ImportError):
                with self.subTest(point=point, error=error.__name__):
                    f = self.fresh()
                    def after_return(*args, **kwargs):
                        original(*args, **kwargs)
                        raise error("PRIVATE-SENTINEL")
                    target = "write_bytes_no_replace" if point == "writer-entry" else "_binding_publish"
                    effect = error("PRIVATE-SENTINEL") if point == "writer-entry" else after_return
                    with patch.object(core, target, side_effect=effect):
                        self.assertEqual(self.call(f, "arm", f.reservation), (1, "", "binding-publication-uncertain\n"))
                    self.assertEqual(f.stored().exists(), point == "publisher-return")
                    self.assertTrue((f.journal / ".bindings.lock").exists())

    def test_conflict_marker_interrupts_preserve_original(self):
        original = os.link
        for after_link in (False, True):
            for error in (KeyboardInterrupt, ImportError):
                with self.subTest(after_link=after_link, error=error.__name__):
                    f = self.fresh()
                    f.arm()
                    before = f.stored().read_bytes()
                    def marker_fault(source, destination, *args, **kwargs):
                        if after_link:
                            original(source, destination, *args, **kwargs)
                        raise error("PRIVATE-SENTINEL")
                    with patch.object(os, "link", marker_fault):
                        self.assertEqual(self.call(f, "arm", {**f.reservation, "dispatch_id": "conflicting"}),
                                         (1, "", "binding-publication-uncertain\n"))
                    self.assertEqual(f.stored().read_bytes(), before)
                    self.assertEqual((f.stored().parent / "gaps/binding-conflict.json").exists(), after_link)
                    self.assertTrue((f.journal / ".bindings.lock").exists())

    def test_unverified_lock_setup_failure_never_unlinks(self):
        original = core._binding_dir
        for error in (KeyboardInterrupt, ImportError):
            with self.subTest(error=error.__name__):
                f = self.fresh()
                lock = f.journal / ".bindings.lock"
                def fail_owner_check(path, *args, **kwargs):
                    if path == lock:
                        raise error("PRIVATE-SENTINEL")
                    return original(path, *args, **kwargs)
                with patch.object(core, "_binding_dir", fail_owner_check):
                    self.assertEqual(self.call(f, "arm", f.reservation), (1, "", "binding-publication-uncertain\n"))
                self.assertTrue(lock.exists())
                self.assertFalse(f.stored().exists())

    def test_cleanup_failure_does_not_recreate_removed_lock(self):
        original = Path.rmdir
        for after_rmdir in (False, True):
            for error in (KeyboardInterrupt, ImportError):
                with self.subTest(after_rmdir=after_rmdir, error=error.__name__):
                    f = self.fresh()
                    lock = f.journal / ".bindings.lock"
                    def cleanup_fault(path, *args, **kwargs):
                        if path == lock:
                            if after_rmdir:
                                original(path, *args, **kwargs)
                            raise error("PRIVATE-SENTINEL")
                        return original(path, *args, **kwargs)
                    with patch.object(Path, "rmdir", cleanup_fault):
                        self.assertEqual(self.call(f, "arm", f.reservation), (1, "", "binding-publication-uncertain\n"))
                    self.assertEqual(lock.exists(), not after_rmdir)
                    self.assertEqual(json.loads(f.stored().read_bytes()), f.reservation)

    def test_replaced_lock_is_preserved_during_prevalidation_interrupt(self):
        lock = self.journal / ".bindings.lock"
        preserved = self.root / "owned-lock"
        def replace_then_interrupt(*args, **kwargs):
            lock.rename(preserved)
            lock.mkdir(mode=0o700)
            raise KeyboardInterrupt("PRIVATE-SENTINEL")
        with patch.object(core, "_binding_input", replace_then_interrupt):
            self.assertEqual(self.call(self, "arm", self.reservation), (1, "", "binding-publication-uncertain\n"))
        self.assertTrue(lock.exists())
        self.assertTrue(preserved.exists())
        self.assertFalse(self.stored().exists())

    def test_legacy_interrupt_and_import_failure_still_propagate(self):
        for error in (KeyboardInterrupt, ImportError):
            with self.subTest(error=error.__name__), \
                    patch.object(core, "summarize_events", side_effect=error("PRIVATE-SENTINEL")), \
                    self.assertRaises(error):
                core.main(["--state-dir", str(self.journal), "--binding-id", "binding-a"])


class BindingCLITests(BindingFixture):
    def cli(self, operation=None, value=b"", *, options_first=False, extra=()):
        flags = ["--state-dir", str(self.journal), "--binding-id", "binding-a"]
        if operation:
            flags += ["--vault-root", str(self.vault)]
        command = flags + [operation] if options_first and operation else ([operation] if operation else []) + flags
        payload = json.dumps(value).encode() if isinstance(value, dict) else value
        return subprocess.run([sys.executable, str(Path(core.__file__)), *command, *extra],
                              input=payload, capture_output=True, timeout=10)

    def test_cli_offline_lifecycle_and_legacy_flags(self):
        for op, value, state in (("arm", self.reservation, "reserved"),):
            run = self.cli(op, value, options_first=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout), {"binding_state": state})
            self.assertEqual(run.stderr, b"")
        for op, value, state in (("consume", self.consumption(), "bound"),):
            run = self.cli(op, value)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout), {"binding_state": state})
        run = self.cli("close", self.closure(), options_first=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), {"binding_state": "closed"})
        run = self.cli("inspect", b"PRIVATE-SENTINEL is not stdin authority", options_first=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), core.inspect_binding(self.journal, "binding-a", vault_root=self.vault))
        legacy = self.cli()
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertEqual(json.loads(legacy.stdout), core.summarize_events(self.journal, "binding-a"))
        bad = self.cli(extra=("--PRIVATE-SENTINEL",))
        self.assertEqual(bad.stderr, b"identity-invalid\n")

    def test_cli_strict_bounded_input_and_errors(self):
        for raw in (b"x" * 16385, b'{"x":NaN}', b'{"x":1,"x":2}', b"[]", b"\xff",
                    {**self.reservation, "prompt": "PRIVATE-SENTINEL"},
                    {**self.reservation, "source_kind": "qualified"}):
            run = self.cli("arm", raw)
            self.assertEqual((run.returncode, run.stdout, run.stderr), (1, b"", b"binding-integrity\n"))
        for extra in (("--PRIVATE-SENTINEL",), ("--binding-id",), ("--vault-root",)):
            run = self.cli("arm", self.reservation, extra=extra)
            self.assertEqual((run.returncode, run.stdout, run.stderr), (1, b"", b"binding-integrity\n"))
        run = self.cli("arm", self.reservation, extra=("--binding-id", "binding-b"))
        self.assertEqual((run.returncode, run.stdout, run.stderr), (1, b"", b"binding-integrity\n"))
        self.assertFalse(self.journal.exists())
        run = self.cli("inspect")
        self.assertEqual(run.returncode, 1)
        self.assertEqual(json.loads(run.stdout)["binding_state"], "invalid")
        self.assertFalse(self.journal.exists())
        run = self.cli(extra=("--vault-root", str(self.vault)))
        self.assertEqual((run.returncode, run.stdout, run.stderr), (1, b"", b"binding-integrity\n"))

    def test_legacy_stray_positional_keeps_identity_error(self):
        run = self.cli(extra=("PRIVATE-SENTINEL",))
        self.assertEqual((run.returncode, run.stdout, run.stderr), (1, b"", b"identity-invalid\n"))
        self.assertFalse(self.journal.exists())

    def test_stdin_io_failure_is_sanitized_unavailable(self):
        with patch.object(core.sys, "stdin") as source, patch.object(core.sys, "stdout", new_callable=io.StringIO) as out, \
                patch.object(core.sys, "stderr", new_callable=io.StringIO) as err:
            source.buffer.read.side_effect = OSError("PRIVATE-SENTINEL")
            code = core.main(["arm", "--state-dir", str(self.journal), "--binding-id", "binding-a",
                              "--vault-root", str(self.vault)])
        self.assertEqual((code, out.getvalue(), err.getvalue()), (1, "", "binding-unavailable\n"))
        self.assertFalse(self.journal.exists())

    def test_hook_payload_never_becomes_binding_authority(self):
        import codex_capture
        from test_codex_capture import payload
        keys = []
        for sentinel in ("PRIVATE-SENTINEL-A", "PRIVATE-SENTINEL-B"):
            hook = payload("UserPromptSubmit", prompt=sentinel, cwd=sentinel,
                           tool_response={"output": sentinel}, transcript_path=sentinel)
            normalized = codex_capture.normalize_hook(hook, surface="desktop", host_version=None, observed_at=NOW)
            keys.append(normalized["event_key"])
            core.append_event(self.journal, "binding-a", normalized)
            failed = self.cli("arm", hook)
            self.assertEqual((failed.returncode, failed.stdout, failed.stderr), (1, b"", b"binding-integrity\n"))
            self.assertFalse(self.stored().exists())
            for path in self.journal.rglob("*.json"):
                self.assertNotIn(sentinel.encode(), path.read_bytes())
        self.assertEqual(keys[0], keys[1])


if __name__ == "__main__":
    unittest.main()
