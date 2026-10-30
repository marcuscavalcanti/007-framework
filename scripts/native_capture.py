#!/usr/bin/env python3
"""Bounded offline metadata journal. Observation never grants replay admission."""

import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

import replay_capture
from replay_capture import ID, SHA, _path, _private_dir, _read, write_bytes_no_replace

SCHEMA = "007-framework/native-event/v1"
SUMMARY_SCHEMA = "007-framework/native-summary/v1"
MAX_EVENT_BYTES = 16 * 1024
MAX_EVENTS = 2000
BASE_GAPS = {"runtime-unqualified", "context-unobserved", "usage-unobserved"}
EVENT_GAPS = BASE_GAPS | {"host-version-unavailable", "model-unavailable", "child-attribution-unqualified"}
OPERATIONAL_GAPS = {"identity-invalid", "event-conflict", "event-invalid", "input-limit",
                    "event-limit", "journal-limit", "hook-unsupported", "journal-io",
                    "lock-busy", "orphan-tool-event"}
GAP_CODES = EVENT_GAPS | OPERATIONAL_GAPS
KINDS = {"session_start", "turn_start", "tool_start", "tool_finish", "turn_stop", "interrupt", "session_end"}
IDENTITY = ("adapter", "kind", "session_id", "turn_id", "tool_call_id", "agent_id")
FIELDS = set(IDENTITY) | {"schema", "adapter_version", "host_version", "surface", "event_key",
                          "model_reported", "observed_at", "gaps"}
NATIVE_ID = re.compile(r"[A-Za-z0-9._:-]{1,256}")
MAX_BINDING_BYTES = 16 * 1024
MAX_BINDINGS = 128
BINDING_MARKERS = {"binding-conflict", "binding-integrity", "binding-publication-uncertain"}
BINDING_ERRORS = BINDING_MARKERS | {"binding-unavailable", "binding-lock-busy"}
BINDING_FIELDS = {
    "reservation": set("schema project_id task_id attempt_id binding_id replay_ref checkout authority_file producer dispatch_id source_kind observed_at".split()),
    "consumption": set("schema reservation_sha256 dispatch_id source_kind producer turn_id start_event_ref observed_at".split()),
    "closure": set("schema reservation_sha256 consumption_sha256 outcome terminal_event_ref observed_at".split()),
}


class BindingError(ValueError):
    def __init__(self, code):
        self.code = code if code in BINDING_ERRORS else "binding-integrity"
        super().__init__(self.code)


def _binding_expect(condition):
    if not condition:
        raise BindingError("binding-integrity")


def validate_binding_record(value, kind):
    try:
        _binding_expect(kind in BINDING_FIELDS and isinstance(value, dict) and set(value) == BINDING_FIELDS[kind])
        suffix = "close" if kind == "closure" else kind
        _binding_expect(value["schema"] == f"007-framework/binding-{suffix}/v1" and len(_json(value)) <= MAX_BINDING_BYTES)
        observed = value["observed_at"]
        _binding_expect(isinstance(observed, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z", observed))
        datetime.fromisoformat(observed.replace("Z", "+00:00"))
        if kind != "closure":
            _binding_expect(value["source_kind"] in ("synthetic", "declared")
                            and isinstance(value["dispatch_id"], str) and ID.fullmatch(value["dispatch_id"]))
            producer = value["producer"]
            _binding_expect(isinstance(producer, dict) and set(producer) == {
                "namespace", "adapter", "surface", "host_version", "session_id", "thread_id"})
            _binding_expect(all(isinstance(producer[k], str) and ID.fullmatch(producer[k]) for k in ("namespace", "adapter")))
            _binding_expect(all(isinstance(producer[k], str) and NATIVE_ID.fullmatch(producer[k]) for k in ("session_id", "thread_id")))
            _binding_expect(producer["surface"] in ("terminal", "desktop")
                            and (producer["host_version"] is None or _text(producer["host_version"], 128)))
        if kind == "reservation":
            _binding_expect(all(isinstance(value[k], str) and ID.fullmatch(value[k])
                                for k in ("project_id", "task_id", "attempt_id", "binding_id")))
            replay_capture.validate_ref_shape(value["replay_ref"])
            replay_capture._relative(value["authority_file"])
            checkout = value["checkout"]
            _binding_expect(isinstance(checkout, dict) and set(checkout) == {"path", "device", "inode"})
            _binding_expect(all(type(checkout[k]) is int and checkout[k] >= 0 for k in ("device", "inode")))
            path = checkout["path"]
            _binding_expect(isinstance(path, str) and Path(path).is_absolute() and str(Path(path)) == path
                            and ".." not in Path(path).parts and "\x00" not in path)
        else:
            _binding_expect(isinstance(value["reservation_sha256"], str) and SHA.fullmatch(value["reservation_sha256"]))
            if kind == "consumption":
                _binding_expect(isinstance(value["turn_id"], str) and NATIVE_ID.fullmatch(value["turn_id"]))
                ref = value["start_event_ref"]
            else:
                _binding_expect(value["outcome"] in ("stop-observed", "interrupt-observed", "cancelled-before-consume"))
                ref = value["terminal_event_ref"]
                if value["outcome"] == "cancelled-before-consume":
                    _binding_expect(value["consumption_sha256"] is None and ref is None)
                    return value
                _binding_expect(isinstance(value["consumption_sha256"], str) and SHA.fullmatch(value["consumption_sha256"]))
            _binding_expect(isinstance(ref, dict) and set(ref) == {"event_key", "sha256"}
                            and all(isinstance(v, str) and SHA.fullmatch(v) for v in ref.values()))
        return value
    except BindingError:
        raise
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise BindingError("binding-integrity") from None


def _binding_input(vault_root, reservation, *, check_checkout):
    try:
        validate_binding_record(reservation, "reservation")
        _binding_expect(type(check_checkout) is bool)
        checkout = reservation["checkout"]
        path = Path(checkout["path"])
        if check_checkout:
            _path(Path(path.anchor), str(path.relative_to(path.anchor)))
            before = path.lstat()
            _binding_expect(stat.S_ISDIR(before.st_mode)
                            and (before.st_dev, before.st_ino) == (checkout["device"], checkout["inode"]))
        ref = reservation["replay_ref"]
        value = replay_capture.validate_replay_ref(vault_root, reservation["project_id"], reservation["task_id"], ref,
                                                   expected_attempt_id=reservation["attempt_id"])
        _binding_expect(value["schema"] == replay_capture.INPUT_SCHEMA_V2 and value["checkout"] == checkout["path"])
        execution = value["config"]["execution"]
        _binding_expect(execution == {"kind": "native-host", "adapter": reservation["producer"]["adapter"],
                                      "surface": reservation["producer"]["surface"], "binding_id": reservation["binding_id"]})
        case = Path(vault_root).absolute() / Path(ref["manifest"]).parent
        raw = replay_capture._read_private_artifact(case, "input.json", replay_capture.MAX_MANIFEST)
        _binding_expect(hashlib.sha256(raw).hexdigest() == ref["sha256"] and decode_json(raw) == value)
        artifact = next((a for a in value["artifacts"] if a["path"] == reservation["authority_file"]), None)
        _binding_expect(artifact is not None)
        raw = replay_capture._read_private_artifact(case, "inputs/" + artifact["path"], replay_capture.MAX_FILE)
        _binding_expect(len(raw) == artifact["bytes"] and hashlib.sha256(raw).hexdigest() == artifact["sha256"])
        authority = decode_json(raw)
        _binding_expect(isinstance(authority, dict) and set(authority) == {"schema", "allow", "deny"})
        from framework_cli import validate_authority
        validate_authority(authority)
        if check_checkout:
            _path(Path(path.anchor), str(path.relative_to(path.anchor)))
            after = path.lstat()
            _binding_expect(stat.S_ISDIR(after.st_mode) and (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino))
        return value
    except BindingError:
        raise
    except (OSError, ImportError):
        raise BindingError("binding-unavailable") from None
    except (ValueError, TypeError, KeyError, RecursionError):
        raise BindingError("binding-integrity") from None


def _binding_sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _binding_dir(path, create=False, *, created=None, new=False, parent_owner=None):
    needs_create = create and not path.exists()
    if needs_create:
        parent_owner = path.parent.lstat()
        try:
            path.mkdir(mode=0o700)
            new = True
        except FileExistsError:
            pass  # A concurrent creator is acceptable only after the same identity/mode checks.
    try:
        info = path.lstat()
        _binding_expect(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid())
        if new and stat.S_IMODE(info.st_mode) != 0o700:
            _binding_expect(not stat.S_IMODE(info.st_mode) & ~0o700 and parent_owner is not None)
            _binding_sync(path.parent)
            with os.scandir(path) as entries:
                _binding_expect(next(entries, None) is None)
            for node, expected in ((path.parent, parent_owner), (path, info)):
                actual = node.lstat()
                _binding_expect(all(getattr(actual, field) == getattr(expected, field)
                                    for field in ("st_dev", "st_ino", "st_mode", "st_uid")))
            path.rmdir()  # Only this call's verified empty directory; never widen permissions.
            _binding_sync(path.parent)
            actual = path.parent.lstat()
            _binding_expect(all(getattr(actual, field) == getattr(parent_owner, field)
                                for field in ("st_dev", "st_ino", "st_mode", "st_uid")))
            _binding_expect(not path.exists() and not path.is_symlink())
        else:
            _binding_expect(stat.S_IMODE(info.st_mode) == 0o700)
    except (OSError, ValueError):
        if new:
            raise BindingError("binding-publication-uncertain") from None
        raise
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise BindingError("binding-unavailable")
    if new and created is not None:
        created.append((path, info))
    if needs_create:
        _binding_sync(path.parent)
    return info


def _validate_binding_chain(case, result, hashes):
    reservation, consumption, closure = (result[k] for k in BINDING_FIELDS)
    _binding_expect(reservation["binding_id"] == case.name)
    producer = reservation["producer"]
    for kind, ref_name, expected_kind in (("consumption", "start_event_ref", "turn_start"),
            ("closure", "terminal_event_ref", "turn_stop" if closure and closure["outcome"] == "stop-observed" else "interrupt")):
        record = result[kind]
        if record is None:
            continue
        _binding_expect(record["reservation_sha256"] == hashes["reservation"])
        if kind == "consumption":
            _binding_expect(all(record[k] == reservation[k] for k in ("producer", "dispatch_id", "source_kind")))
        elif record["outcome"] == "cancelled-before-consume":
            _binding_expect(consumption is None)
            continue
        else:
            _binding_expect(consumption is not None and record["consumption_sha256"] == hashes["consumption"])
        ref = record[ref_name]
        raw = replay_capture._read_private_artifact(case, "events/" + ref["event_key"] + ".json", MAX_EVENT_BYTES)
        _binding_expect(hashlib.sha256(raw).hexdigest() == ref["sha256"])
        value = validate_event(decode_json(raw))
        _binding_expect(value["event_key"] == ref["event_key"] and value["kind"] == expected_kind
                        and value["turn_id"] == consumption["turn_id"] and value["agent_id"] is None
                        and all(value[k] == producer[k] for k in ("adapter", "surface", "host_version", "session_id")))


def _read_binding_chain(root, binding_id):
    try:
        _binding_expect(isinstance(binding_id, str) and ID.fullmatch(binding_id))
        root = Path(root).absolute()
        _path(Path(root.anchor), str(root.relative_to(root.anchor)))
        _binding_dir(root)
        result = dict(reservation=None, consumption=None, closure=None, gaps=[])
        case = root / binding_id
        if not case.exists() and not case.is_symlink():
            return result
        _binding_dir(case)
        directory = case / "binding"
        if not directory.exists() and not directory.is_symlink():
            return result
        _binding_dir(directory)
        paths = {p.name: p for p in _paths(directory, 4)}
        _binding_expect("reservation.json" in paths and set(paths) <= {
            "reservation.json", "consumption.json", "closure.json", "gaps"})
        hashes = {}
        for kind in BINDING_FIELDS:
            if kind + ".json" in paths:
                raw = replay_capture._read_private_artifact(directory, kind + ".json", MAX_BINDING_BYTES)
                hashes[kind] = hashlib.sha256(raw).hexdigest()
                result[kind] = validate_binding_record(decode_json(raw), kind)
        _validate_binding_chain(case, result, hashes)
        if "gaps" in paths:
            _binding_dir(directory / "gaps")
            for path in _paths(directory / "gaps", len(BINDING_MARKERS)):
                _binding_expect(path.name in {code + ".json" for code in BINDING_MARKERS})
                raw = replay_capture._read_private_artifact(directory, "gaps/" + path.name, 1024)
                _binding_expect(decode_json(raw) == {"code": path.stem})
                result["gaps"].append(path.stem)
        result["gaps"].sort()
        return result
    except BindingError:
        raise
    except OSError:
        raise BindingError("binding-unavailable") from None
    except (ValueError, TypeError, KeyError, RecursionError):
        raise BindingError("binding-integrity") from None


@contextmanager
def _binding_lock(root):
    try:
        _path(Path(root.anchor), str(root.relative_to(root.anchor)))
        root_owner = _binding_dir(root, create=True)
        lock = root / ".bindings.lock"
        try:
            lock.mkdir(mode=0o700)
        except FileExistsError:
            raise BindingError("binding-lock-busy") from None
        owner = _binding_dir(lock, new=True, parent_owner=root_owner)
    except BindingError:
        raise
    except (KeyboardInterrupt, ImportError):
        raise BindingError("binding-publication-uncertain") from None
    except (OSError, ValueError):
        raise BindingError("binding-unavailable") from None
    failure = None
    publication = {"started": False, "created": [], "cleanup": None}
    try:
        _binding_sync(root)
        yield publication
    except BindingError as exc:
        if exc.code == "binding-publication-uncertain":
            raise
        failure = exc
    except (KeyboardInterrupt, ImportError) as exc:
        if publication["started"]:
            raise BindingError("binding-publication-uncertain") from None
        failure = exc if isinstance(exc, KeyboardInterrupt) else BindingError("binding-unavailable")
    except OSError:
        failure = BindingError("binding-unavailable")
    except (ValueError, TypeError, KeyError, RecursionError):
        failure = BindingError("binding-integrity")
    try:
        owners = [(root, root_owner), (lock, owner)]
        if publication["cleanup"] is not None:
            owners += publication["created"]
        for path, expected in owners:
            actual = _binding_dir(path)
            _binding_expect((actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino))
        if publication["cleanup"] is not None:
            target = publication["cleanup"]
            _binding_expect(not target.exists() and not target.is_symlink())
            for path, _ in reversed(publication["created"]):
                path.rmdir()  # Never remove files or a directory another writer has populated.
                _binding_sync(path.parent)
            for path, expected in ((root, root_owner), (lock, owner)):
                actual = _binding_dir(path)
                _binding_expect((actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino))
        lock.rmdir()
        _binding_sync(root)
    except (OSError, ValueError, KeyboardInterrupt, ImportError):
        raise BindingError("binding-publication-uncertain") from None
    if failure:
        raise failure


def _binding_publish(root, binding_id, name, value, publication):
    # Interrupts cannot prove which filesystem mutations became visible.
    publication["started"] = True
    directory = root / binding_id / "binding"
    try:
        for path in (directory.parent, directory):
            _binding_dir(path, create=True, created=publication["created"])
        if name in BINDING_MARKERS:
            directory /= "gaps"
            _binding_dir(directory, create=True, created=publication["created"])
        write_bytes_no_replace(directory / (name + ".json"), _json(value), "binding metadata")
    except replay_capture.PublishedArtifactError:
        raise BindingError("binding-publication-uncertain") from None
    except (OSError, BindingError) as exc:
        if isinstance(exc, BindingError) and exc.code != "binding-unavailable":
            raise
        if name == "reservation":
            publication["cleanup"] = directory / "reservation.json"
        raise


def _binding_conflict(root, binding_id, publication):
    try:
        _binding_publish(root, binding_id, "binding-conflict", {"code": "binding-conflict"}, publication)
    except (ValueError, OSError):
        raise BindingError("binding-publication-uncertain") from None
    raise BindingError("binding-conflict")


def _binding_chains(root, binding_id):
    paths = [p for p in _paths(root, MAX_BINDINGS + 1) if p.name != ".bindings.lock"]
    _binding_expect(len(paths) + (0 if root / binding_id in paths else 1) <= MAX_BINDINGS)
    chains = {}
    for path in paths:
        _binding_expect(ID.fullmatch(path.name))
        _binding_dir(path)
        chains[path.name] = _read_binding_chain(root, path.name)
        _binding_expect(not chains[path.name]["gaps"])
    return chains


def arm_binding(root, binding_id, reservation, *, vault_root, exclusive=False):
    validate_binding_record(reservation, "reservation")
    _binding_expect(binding_id == reservation["binding_id"])
    root = Path(root).absolute()
    with _binding_lock(root) as publication:
        chains = _binding_chains(root, binding_id)
        chain = chains.get(binding_id)
        previous = chain["reservation"] if chain else None
        _binding_input(vault_root, previous or reservation, check_checkout=previous is None)
        if previous:
            if {k: v for k, v in previous.items() if k != "observed_at"} != {
                    k: v for k, v in reservation.items() if k != "observed_at"}:
                _binding_conflict(root, binding_id, publication)
            if exclusive:
                # The caller must own this binding's first dispatch; an earlier reservation is not reusable.
                raise BindingError("binding-conflict")
            return "closed" if chain["closure"] else "bound" if chain["consumption"] else "reserved"
        for other in chains.values():
            old = other["reservation"]
            if old is None or other["closure"] is not None:
                continue
            same_checkout = old["checkout"]["path"] == reservation["checkout"]["path"] or all(
                old["checkout"][k] == reservation["checkout"][k] for k in ("device", "inode"))
            same_session = all(old["producer"][k] == reservation["producer"][k] for k in ("namespace", "session_id"))
            if same_checkout or same_session:
                raise BindingError("binding-conflict")
        _binding_publish(root, binding_id, "reservation", reservation, publication)
        return "reserved"


def _transition_binding(root, binding_id, value, kind, vault_root):
    validate_binding_record(value, kind)
    _binding_expect(isinstance(binding_id, str) and ID.fullmatch(binding_id))
    root = Path(root).absolute()
    with _binding_lock(root) as publication:
        chain = (_read_binding_chain(root, binding_id) if kind == "closure"
                 else _binding_chains(root, binding_id).get(binding_id))
        _binding_expect(chain is not None and chain["reservation"] is not None and not chain["gaps"])
        previous = chain[kind]
        _binding_input(vault_root, chain["reservation"],
                       check_checkout=kind == "consumption" and previous is None and chain["closure"] is None)
        if previous:
            if {k: v for k, v in previous.items() if k != "observed_at"} != {
                    k: v for k, v in value.items() if k != "observed_at"}:
                _binding_conflict(root, binding_id, publication)
            return "closed" if chain["closure"] else "bound"
        if chain["closure"]:
            raise BindingError("binding-conflict")
        case = root / binding_id
        hashes = {}
        for name in ("reservation", "consumption"):
            if chain[name] is not None:
                raw = replay_capture._read_private_artifact(case, "binding/" + name + ".json", MAX_BINDING_BYTES)
                _binding_expect(decode_json(raw) == chain[name])
                hashes[name] = hashlib.sha256(raw).hexdigest()
        chain[kind] = value
        _validate_binding_chain(case, chain, hashes)
        _binding_publish(root, binding_id, kind, value, publication)
        return "closed" if kind == "closure" else "bound"


def consume_binding(root, binding_id, consumption, *, vault_root):
    return _transition_binding(root, binding_id, consumption, "consumption", vault_root)


def close_binding(root, binding_id, closure, *, vault_root):
    return _transition_binding(root, binding_id, closure, "closure", vault_root)


def inspect_binding(root, binding_id, *, vault_root):
    _binding_expect(isinstance(binding_id, str) and ID.fullmatch(binding_id))
    summary = dict(schema="007-framework/binding-summary/v1", project_id=None, task_id=None,
                   attempt_id=None, binding_id=binding_id, binding_state="absent", source_kind=None,
                   coverage="partial", execution_authorized=False, replay_admissible=False, economic_admissible=False)
    gaps = BASE_GAPS | {"binding-correlation-unqualified"}
    root = Path(root).absolute()
    lock = root / ".bindings.lock"
    invalid = False
    try:
        if lock.exists() or lock.is_symlink():
            raise BindingError("binding-lock-busy")
        chain = _read_binding_chain(root, binding_id)
        reservation = chain["reservation"]
        if reservation:
            _binding_input(vault_root, reservation, check_checkout=False)
            summary.update({key: reservation[key] for key in ("project_id", "task_id", "attempt_id", "source_kind")})
            summary["binding_state"] = "closed" if chain["closure"] else "bound" if chain["consumption"] else "reserved"
            gaps.add("binding-source-" + reservation["source_kind"])
        gaps.update(chain["gaps"])
        invalid = bool(chain["gaps"])
        case = root / binding_id
        if any(p.exists() or p.is_symlink() for p in (case / "events", case / "gaps", case / "lock")):
            observed = summarize_events(root, binding_id)
            gaps.update(observed["gaps"])
            invalid |= observed["coverage"] == "invalid"
        if lock.exists() or lock.is_symlink():
            raise BindingError("binding-lock-busy")
    except (BindingError, CaptureError) as exc:
        gaps.add(exc.code)
        invalid = True
    except (OSError, ValueError, TypeError):
        gaps.add("binding-unavailable")
        invalid = True
    if invalid:
        summary.update(binding_state="invalid", coverage="invalid")
    summary["gaps"] = sorted(gaps)
    return summary


class CaptureError(ValueError):
    """Only fixed codes may cross the capture boundary."""

    def __init__(self, code):
        self.code = code if code in GAP_CODES else "event-invalid"
        super().__init__(self.code)


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise CaptureError("identity-invalid")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CaptureError("event-invalid")
        result[key] = value
    return result


def decode_json(payload):
    try:
        return json.loads(payload, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(CaptureError("event-invalid")))
    except (ValueError, UnicodeError, RecursionError):
        raise CaptureError("event-invalid") from None


def event_key(value):
    return hashlib.sha256(_json([value[name] for name in IDENTITY])).hexdigest()


def _text(value, limit):
    return (isinstance(value, str) and 0 < len(value) <= limit
            and not any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value))


def validate_event(value):
    try:
        if not isinstance(value, dict) or set(value) != FIELDS or value["schema"] != SCHEMA:
            raise CaptureError("event-invalid")
        if (not isinstance(value["adapter"], str) or not ID.fullmatch(value["adapter"])
                or value["kind"] not in KINDS or value["surface"] not in ("terminal", "desktop")
                or not _text(value["adapter_version"], 64)):
            raise CaptureError("event-invalid")
        for name in ("session_id", "turn_id", "tool_call_id", "agent_id"):
            item = value[name]
            required = name == "session_id" or (name == "turn_id" and not value["kind"].startswith("session_"))
            required |= name == "tool_call_id" and value["kind"].startswith("tool_")
            if item is None and not required:
                continue
            if not isinstance(item, str) or not NATIVE_ID.fullmatch(item):
                raise CaptureError("identity-invalid")
        if ((value["kind"].startswith("session_") and value["turn_id"] is not None)
                or (not value["kind"].startswith("tool_") and value["tool_call_id"] is not None)):
            raise CaptureError("identity-invalid")
        for name in ("host_version", "model_reported"):
            if value[name] is not None and not _text(value[name], 128):
                raise CaptureError("event-invalid")
        observed = value["observed_at"]
        if not isinstance(observed, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z", observed):
            raise CaptureError("event-invalid")
        datetime.fromisoformat(observed.replace("Z", "+00:00"))
        gaps = value["gaps"]
        required_gaps = BASE_GAPS | ({"host-version-unavailable"} if value["host_version"] is None else set())
        required_gaps |= {"model-unavailable"} if value["model_reported"] is None else set()
        required_gaps |= {"child-attribution-unqualified"} if value["agent_id"] is not None else set()
        if (not isinstance(gaps, list) or any(not isinstance(g, str) for g in gaps)
                or not required_gaps <= set(gaps) <= EVENT_GAPS or gaps != sorted(set(gaps))):
            raise CaptureError("event-invalid")
        if not isinstance(value["event_key"], str) or not SHA.fullmatch(value["event_key"]) or value["event_key"] != event_key(value):
            raise CaptureError("identity-invalid")
        if len(_json(value)) > MAX_EVENT_BYTES:
            raise CaptureError("event-limit")
        return value
    except CaptureError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CaptureError("event-invalid") from None


def _case(root, binding_id, create=False):
    if not isinstance(binding_id, str) or not ID.fullmatch(binding_id):
        raise CaptureError("identity-invalid")
    try:
        root = Path(root).absolute()
        _path(Path(root.anchor), str(root.relative_to(root.anchor)))
        if not root.parent.is_dir():
            raise CaptureError("journal-io")
        case = _path(root, binding_id)
        for directory in (root, case, case / "events", case / "gaps"):
            if not create and not directory.exists():
                raise CaptureError("journal-io")
            _private_dir(directory)
            if create:
                # A durable file entry alone does not publish newly created parent directories.
                fd = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        return case
    except (ValueError, OSError):
        raise CaptureError("journal-io") from None


@contextmanager
def _locked(case):
    lock = case / "lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        raise CaptureError("lock-busy") from None
    except OSError:
        raise CaptureError("journal-io") from None
    owner = lock.lstat()
    try:
        yield
    finally:
        try:
            current = lock.lstat()
            if (current.st_dev, current.st_ino) != (owner.st_dev, owner.st_ino) or lock.is_symlink():
                raise CaptureError("journal-io")
            lock.rmdir()
        except OSError:
            raise CaptureError("journal-io") from None


def _paths(directory, limit):
    paths = []
    try:
        for path in directory.iterdir():
            if len(paths) == limit:
                raise CaptureError("journal-limit")
            paths.append(path)
        return paths
    except OSError:
        raise CaptureError("journal-io") from None


def _load(path, limit):
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.getuid()):
            raise CaptureError("journal-io")
        return decode_json(_read(path, limit))
    except (OSError, ValueError):
        raise CaptureError("journal-io") from None


def _publish(path, value):
    try:
        write_bytes_no_replace(path, _json(value), "native metadata")
    except (OSError, ValueError):
        raise CaptureError("journal-io") from None


def _gap(case, code):
    path = case / "gaps" / (code + ".json")
    value = {"code": code}
    if path.exists() or path.is_symlink():
        if _load(path, 1024) != value:
            raise CaptureError("journal-io")
    else:
        _publish(path, value)


def record_gap(root, binding_id, code):
    if not isinstance(code, str) or code not in GAP_CODES:
        raise CaptureError("event-invalid")
    case = _case(root, binding_id, create=True)
    with _locked(case):
        _gap(case, code)


def append_event(root, binding_id, event):
    event = validate_event(event)
    case = _case(root, binding_id, create=True)
    with _locked(case):
        try:
            path = case / "events" / (event["event_key"] + ".json")
            if path.exists() or path.is_symlink():
                old = validate_event(_load(path, MAX_EVENT_BYTES))
                if {k: v for k, v in old.items() if k != "observed_at"} != {k: v for k, v in event.items() if k != "observed_at"}:
                    raise CaptureError("event-conflict")
                return "duplicate"
            if len(_paths(case / "events", MAX_EVENTS)) >= MAX_EVENTS:
                raise CaptureError("journal-limit")
            _publish(path, event)
            return "written"
        except CaptureError as exc:
            try:
                _gap(case, exc.code)
            except CaptureError:
                pass  # The caller still receives failure; no recursive error delivery.
            raise


def summarize_events(root, binding_id):
    case = _case(root, binding_id)
    lock = case / "lock"
    if lock.exists() or lock.is_symlink():
        raise CaptureError("lock-busy")
    # Published entries are immutable; this bounded observation must not lock out writers.
    gaps, starts, finishes = set(BASE_GAPS), set(), set()
    paths = _paths(case / "events", MAX_EVENTS)
    for path in paths:
        if not re.fullmatch(r"[0-9a-f]{64}\.json", path.name):
            raise CaptureError("identity-invalid")
        value = validate_event(_load(path, MAX_EVENT_BYTES))
        if path.name != value["event_key"] + ".json":
            raise CaptureError("identity-invalid")
        gaps.update(value["gaps"])
        key = tuple(value[k] for k in IDENTITY if k != "kind")
        if value["kind"] == "tool_start":
            starts.add(key)
        elif value["kind"] == "tool_finish":
            finishes.add(key)
    stored = set()
    for path in _paths(case / "gaps", len(GAP_CODES)):
        if path.suffix != ".json" or path.stem not in GAP_CODES:
            raise CaptureError("journal-io")
        value = _load(path, 1024)
        if (not isinstance(value, dict) or set(value) != {"code"}
                or not isinstance(value["code"], str) or value["code"] not in GAP_CODES
                or path.name != value["code"] + ".json"):
            raise CaptureError("journal-io")
        stored.add(value["code"])
    if lock.exists() or lock.is_symlink():
        raise CaptureError("lock-busy")
    gaps.update(stored)
    if starts != finishes:
        gaps.add("orphan-tool-event")
    return {"schema": SUMMARY_SCHEMA, "coverage": "invalid" if stored & OPERATIONAL_GAPS else "partial",
            "event_count": len(paths), "gaps": sorted(gaps)}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    operations = {"arm": arm_binding, "consume": consume_binding, "close": close_binding, "inspect": inspect_binding}
    b2 = skip_value = False
    for arg in argv:
        if skip_value:
            skip_value = False
            continue
        b2 |= arg in operations or arg.split("=", 1)[0] == "--vault-root"
        skip_value = arg in ("--state-dir", "--binding-id", "--vault-root")
    try:
        parser = SafeArgumentParser(description="Inspect an offline metadata journal; not replay admission")
        parser.add_argument("operation", nargs="?")
        parser.add_argument("--state-dir", required=True, type=Path)
        parser.add_argument("--binding-id", required=True)
        parser.add_argument("--vault-root", type=Path)
        args = parser.parse_args(argv)
        b2 |= args.operation in operations or args.vault_root is not None
        if args.operation is not None and not b2:
            raise CaptureError("identity-invalid")
        if b2:
            _binding_expect(args.operation in operations and args.vault_root is not None)
            if args.operation == "inspect":
                summary = inspect_binding(args.state_dir, args.binding_id, vault_root=args.vault_root)
                print(_json(summary).decode("utf-8"))
                return int(summary["coverage"] == "invalid")
            raw = sys.stdin.buffer.read(MAX_BINDING_BYTES + 1)
            _binding_expect(len(raw) <= MAX_BINDING_BYTES)
            state = operations[args.operation](args.state_dir, args.binding_id, decode_json(raw), vault_root=args.vault_root)
            print(_json({"binding_state": state}).decode("utf-8"))
            return 0
        print(_json(summarize_events(args.state_dir, args.binding_id)).decode("utf-8"))
        return 0
    except (KeyboardInterrupt, ImportError) as exc:
        if not b2:
            raise
        print("binding-unavailable", file=sys.stderr)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1
    except (CaptureError, BindingError, OSError, ValueError, TypeError) as exc:
        if isinstance(exc, BindingError):
            code = exc.code
        elif b2:
            code = "binding-unavailable" if isinstance(exc, OSError) else "binding-integrity"
        else:
            code = exc.code if isinstance(exc, CaptureError) else "journal-io"
        print(code, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
