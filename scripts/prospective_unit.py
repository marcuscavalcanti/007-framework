"""Offline unit qualification and launcher core (fixed vault/journal). No transport, native authority or replay admission."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from collections.abc import Callable, Iterable

import replay_capture as capture
import native_capture as native
import codex_prospective as protocol


def _expect(value):
    if not value:
        raise ValueError("unit-invalid")


def _directory(path):
    path = Path(path).absolute()
    capture._path(Path(path.anchor), str(path.relative_to(path.anchor)))
    info = path.lstat()
    _expect(stat.S_ISDIR(info.st_mode))
    return {"path": str(path), "device": info.st_dev, "inode": info.st_ino}


def _inventory(repo):
    artifacts, total, entries = {}, 0, 0
    for parent, dirs, files in os.walk(repo, followlinks=False, onerror=lambda _: _expect(False)):
        _expect(Path(parent) == repo or dirs or files)
        if Path(parent) == repo and ".git" in dirs:
            _expect(not (repo / ".git").is_symlink())
            dirs.remove(".git")
        entries += len(dirs) + len(files)
        _expect(entries <= capture.MAX_ENTRIES)
        for name in dirs:
            _expect(not (Path(parent) / name).is_symlink())
        for name in files:
            file = Path(parent) / name
            relative = str(file.relative_to(repo))
            capture._relative(relative)
            info = capture._regular(file)
            total += info.st_size
            _expect(total <= capture.MAX_TOTAL)
            data = capture._read(file, capture.MAX_FILE, info)
            artifacts[relative] = {"path": relative, "bytes": len(data),
                                   "mode": stat.S_IMODE(info.st_mode),
                                   "sha256": hashlib.sha256(data).hexdigest()}
    return artifacts


def _input(prepared, vault_root):
    identity = prepared["identity"]
    _expect(set(identity) == {"project_id", "task_id", "attempt_id", "binding_id"})
    _expect(all(isinstance(v, str) and capture.ID.fullmatch(v) for v in identity.values()))
    _expect(identity["task_id"] != identity["attempt_id"])
    value = capture.validate_replay_ref(vault_root, identity["project_id"], identity["task_id"],
                                        prepared["replay_ref"], expected_attempt_id=identity["attempt_id"])
    _expect(value["config"] == prepared["config"])
    _expect(value["config"]["execution"]["binding_id"] == identity["binding_id"])
    _expect(value["checkout"] == prepared["checkout"]["path"])
    _expect(value["artifacts"] == prepared["input_inventory"])
    return value


def _owned_journal(case, journal_root):
    raw = capture._read_private_artifact(case, "dispatch.owner/journal.json", capture.MAX_MANIFEST)
    _expect(json.loads(raw) == _directory(journal_root))


def verify_prepared(prepared: dict, *, vault_root: Path) -> None:
    try:
        value = _input(prepared, vault_root)
        expected = {a["path"]: a for a in value["artifacts"]}
        for key in ("checkout", "restored_checkout"):
            directory = prepared[key]
            repo = Path(directory["path"])
            _expect(_directory(repo) == directory)
            _expect(_inventory(repo) == expected)
            _expect(_directory(repo) == directory)
        _expect(capture._revision(Path(prepared["checkout"]["path"])) == [value["head"], value["tree"]])
    except (OSError, ValueError, KeyError, TypeError, RecursionError, subprocess.SubprocessError):
        raise ValueError("unit-invalid") from None


def prepare_unit(repo: Path, config: dict, identity: dict, *, vault_root: Path, restore_to: Path) -> dict:
    try:
        checkout = _directory(repo)
        repo, restore_to, vault_root = Path(checkout["path"]), Path(restore_to).absolute(), Path(vault_root).absolute()
        capture._path(Path(restore_to.anchor), str(restore_to.relative_to(restore_to.anchor)))
        _expect(all(a != b and a not in b.parents and b not in a.parents
                    for a, b in ((repo, restore_to), (repo, vault_root), (restore_to, vault_root))))
        _expect(not restore_to.exists())
        config = copy.deepcopy(capture._config(config))
        _expect(config["schema"] == capture.CONFIG_SCHEMA_V2 and config["execution"]["kind"] == "native-host")
        _expect(set(identity) == {"project_id", "task_id", "attempt_id", "binding_id"})
        _expect(all(isinstance(v, str) and capture.ID.fullmatch(v) for v in identity.values()))
        _expect(identity["task_id"] != identity["attempt_id"])
        _expect(config["execution"]["binding_id"] == identity["binding_id"])
        _expect("authority.json" in config["files"] and len(config["output_files"]) == 1)
        _expect(config["output_files"][0] in config["files"] and not config["external_inputs"])
        protected = config["context_files"] + [config[k] for k in
                    ("prompt_file", "acceptance_file", "environment_file")] + ["authority.json"]
        _expect(config["output_files"][0] not in protected)
        before = _inventory(repo)
        _expect(set(before) == set(config["files"]))
        ref = capture.capture_input(repo, identity["project_id"], identity["task_id"], config,
                                    vault_root=vault_root, attempt_id=identity["attempt_id"])
        value = capture.restore_input(vault_root, identity["project_id"], identity["task_id"], ref,
                                       restore_to, expected_attempt_id=identity["attempt_id"])
        prepared = {"identity": copy.deepcopy(identity), "replay_ref": ref, "checkout": checkout,
                    "restored_checkout": _directory(restore_to), "config": config,
                    "input_inventory": value["artifacts"]}
        verify_prepared(prepared, vault_root=vault_root)
        return prepared
    except (OSError, ValueError, KeyError, TypeError, RecursionError, subprocess.SubprocessError):
        raise ValueError("unit-invalid") from None


def publish_dispatch_intent(prepared: dict, request: dict, *, root: Path, producer: dict) -> Path:
    root = Path(root).absolute()
    capture._path(Path(root.anchor), str(root.relative_to(root.anchor)))
    capture._private_dir(root)
    claim = root / "dispatch.claim"
    claim.mkdir(mode=0o700)
    capture._private_dir(claim)
    native._binding_sync(root)
    intent = dict(scope="offline-calibration", identity=prepared["identity"], replay_ref=prepared["replay_ref"],
                  checkout=prepared["checkout"], producer=producer, request_id=request["id"],
                  request_sha256=hashlib.sha256(capture._json_bytes(request)).hexdigest())
    path = claim / "intent.json"
    capture.write_bytes_no_replace(path, capture._json_bytes(intent), "dispatch intent")
    return path


def drive_offline(prepared: dict, messages: Iterable[tuple[str, bytes]], *, bootstrap: dict, request: dict,
                  root: Path, journal_root: Path, vault_root: Path, send: Callable[[bytes], None]) -> dict:
    state = dict(phase="prepared", request_id=None, producer=None, turn_id=None, pending=[], events=[],
                 gaps=[], stream_bytes=0, message_count=0, usage=None)
    intent, sent, armed = None, False, False
    try:
        _expect(not (Path(root) / "dispatch.claim").exists() and not (Path(root) / "dispatch.claim").is_symlink())
        verify_prepared(prepared, vault_root=vault_root)
        observed = bootstrap["observed_at"]
        raw = capture._json_bytes(bootstrap["response"])
        host = protocol.project_frame(raw, channel="stdout", observed_at=observed)
        _expect(host["kind"] == "bootstrap" and host["request_id"] == bootstrap["request_id"])
        _expect(host["cwd"] == prepared["checkout"]["path"])
        _expect(set(request) == {"id", "method", "params"} and request["method"] == "turn/start")
        _expect(isinstance(request["id"], str) and capture.ID.fullmatch(request["id"]))
        case = (Path(vault_root) / prepared["replay_ref"]["manifest"]).parent
        prompt = capture._read_private_artifact(case, "inputs/" + prepared["config"]["prompt_file"], capture.MAX_FILE).decode()
        _expect(request["params"] == {"threadId": host["thread_id"], "input": [{"type": "text", "text": prompt}]})
        producer = {k: host[k] for k in ("session_id", "thread_id", "host_version")}
        producer.update(namespace="codex-app-server-v2", adapter="codex-app-server", surface="terminal")
        _expect(prepared["config"]["execution"]["adapter"] == producer["adapter"]
                and prepared["config"]["execution"]["surface"] == producer["surface"])
        paths = [Path(p).absolute() for p in (root, journal_root, vault_root,
                 prepared["checkout"]["path"], prepared["restored_checkout"]["path"])]
        _expect(all(a != b and a not in b.parents and b not in a.parents
                    for i, a in enumerate(paths) for b in paths[i+1:]))
        identity = prepared["identity"]
        binding = identity["binding_id"]
        reservation = dict(schema="007-framework/binding-reservation/v1", **identity,
            replay_ref=prepared["replay_ref"], checkout=prepared["checkout"], authority_file="authority.json",
            producer=producer, dispatch_id=request["id"], source_kind="synthetic", observed_at=observed)
        owner = case / "dispatch.owner"
        owner.mkdir(mode=0o700)  # the attempt record owns its only dispatch, whatever journal or root is passed
        capture._private_dir(owner)
        native._binding_sync(case)
        try:
            native.arm_binding(journal_root, binding, reservation, vault_root=vault_root, exclusive=True)
        except native.BindingError as error:
            if error.code in ("binding-lock-busy", "binding-unavailable"):
                owner.rmdir()  # these codes mean this call published nothing: do not burn the attempt
            raise
        armed = True
        capture.write_bytes_no_replace(owner / "journal.json", capture._json_bytes(_directory(journal_root)),
                                       "dispatch journal")
        verify_prepared(prepared, vault_root=vault_root)
        state.update(phase="armed", request_id=request["id"], producer=producer, stream_bytes=len(raw), message_count=1)
        intent = publish_dispatch_intent(prepared, request, root=root, producer=producer)
        state["phase"] = "intent-published"
        verify_prepared(prepared, vault_root=vault_root)
        _owned_journal(case, journal_root)
        state["phase"], sent = "sent", True
        send(capture._json_bytes(request))
        binding_dir = Path(journal_root) / binding / "binding"
        reservation_hash = hashlib.sha256(capture._read_private_artifact(binding_dir, "reservation.json", native.MAX_BINDING_BYTES)).hexdigest()
        for channel, frame in messages:
            previous = len(state["events"])
            state = protocol.reduce_message(state, protocol.project_frame(frame, channel=channel, observed_at=observed))
            for message in state["events"][previous:]:
                event = protocol.to_native_event(message, producer=producer, observed_at=observed)
                native.append_event(journal_root, binding, event)
                event_raw = capture._read_private_artifact(Path(journal_root) / binding,
                            "events/" + event["event_key"] + ".json", native.MAX_EVENT_BYTES)
                ref = {"event_key": event["event_key"], "sha256": hashlib.sha256(event_raw).hexdigest()}
                if message["kind"] == "start":
                    native.consume_binding(journal_root, binding, dict(schema="007-framework/binding-consumption/v1",
                        reservation_sha256=reservation_hash, dispatch_id=request["id"], source_kind="synthetic",
                        producer=producer, turn_id=state["turn_id"], start_event_ref=ref, observed_at=observed), vault_root=vault_root)
                else:
                    consumed = capture._read_private_artifact(binding_dir, "consumption.json", native.MAX_BINDING_BYTES)
                    native.close_binding(journal_root, binding, dict(schema="007-framework/binding-close/v1",
                        reservation_sha256=reservation_hash, consumption_sha256=hashlib.sha256(consumed).hexdigest(),
                        outcome="interrupt-observed" if event["kind"] == "interrupt" else "stop-observed",
                        terminal_event_ref=ref, observed_at=observed), vault_root=vault_root)
        _expect(state["phase"] == "terminal-observed")
    except (Exception, KeyboardInterrupt):
        state["phase"] = "uncertain" if sent else "refused"
        state["gaps"].append("dispatch-unconfirmed" if sent else "preflight-refused")
        if armed:
            try:
                native.record_gap(journal_root, binding, "event-invalid")
            except (Exception, KeyboardInterrupt):
                state["gaps"].append("gap-publication-unconfirmed")
    if intent is not None:
        result = dict(scope="offline-calibration", status="response-observed" if state["phase"] == "terminal-observed"
                      else "uncertain" if sent else "not-sent", request_id=state["request_id"], turn_id=state["turn_id"],
                      usage=state["usage"])  # plan Task 12: null is not zero
        try:
            capture.write_bytes_no_replace(intent.parent / "result.json", capture._json_bytes(result), "dispatch result")
        except (Exception, KeyboardInterrupt):
            state["phase"] = "uncertain"
            state["gaps"].append("result-publication-unconfirmed")
    return state


def retain_offline_candidate(prepared: dict, observation: dict, *, repo: Path, journal_root: Path,
                             vault_root: Path, observation_path: Path, restore_to: Path) -> dict:
    try:
        value = _input(prepared, vault_root)
        identity, ref = prepared["identity"], prepared["replay_ref"]
        _owned_journal((Path(vault_root) / ref["manifest"]).parent, journal_root)
        _expect(_directory(repo) == prepared["checkout"])
        restore_to, observation_path = Path(restore_to).absolute(), Path(observation_path).absolute()
        roots = [Path(p).absolute() for p in (repo, journal_root, vault_root,
                 prepared["restored_checkout"]["path"], restore_to)]
        _expect(all(a != b and a not in b.parents and b not in a.parents
                    for i, a in enumerate(roots) for b in roots[i+1:]))
        _expect(all(p != observation_path and p not in observation_path.parents for p in roots))
        capture._path(Path(restore_to.anchor), str(restore_to.relative_to(restore_to.anchor)))
        _expect(not restore_to.exists())
        expected = {a["path"]: a for a in value["artifacts"]}
        _expect(_directory(prepared["restored_checkout"]["path"]) == prepared["restored_checkout"])
        _expect(_inventory(Path(prepared["restored_checkout"]["path"])) == expected)
        current = _inventory(repo)
        output = value["config"]["output_files"][0]
        protected = value["config"]["context_files"] + [value["config"][k] for k in
                    ("prompt_file", "acceptance_file", "environment_file")] + ["authority.json"]
        _expect(output not in protected and set(current) == set(expected))
        _expect(all(current[p] == artifact for p, artifact in expected.items() if p != output))
        _expect(current[output]["mode"] == expected[output]["mode"])
        _expect(capture._revision(repo) == [value["head"], value["tree"]])
        binding = native.inspect_binding(journal_root, identity["binding_id"], vault_root=vault_root)
        _expect(binding["binding_state"] == "closed" and binding["source_kind"] == "synthetic")
        _expect(all(binding[k] == v for k, v in identity.items()))
        chain = native._read_binding_chain(journal_root, identity["binding_id"])
        _expect(chain["reservation"]["replay_ref"] == ref and chain["consumption"] is not None)
        oracle = value["environment"]["oracle"]
        _expect(set(oracle) == {"path", "sha256"} and capture.SHA.fullmatch(oracle["sha256"]))
        oracle_path = Path(oracle["path"])
        _expect(oracle_path.is_absolute() and all(p != oracle_path and p not in oracle_path.parents
                for p in (repo, Path(vault_root), Path(restore_to), Path(prepared["restored_checkout"]["path"]))))
        capture._path(Path(oracle_path.anchor), str(oracle_path.relative_to(oracle_path.anchor)))
        _expect(hashlib.sha256(capture._read(oracle_path, capture.MAX_FILE)).hexdigest() == oracle["sha256"])
        terminal = dict(scope="offline-calibration", source_kind="synthetic", project_id=identity["project_id"],
            task_id=identity["task_id"], attempt_id=identity["attempt_id"], replay_ref=ref, checks=[],
            **{k: None for k in ("served_provider", "served_model", "served_effort", "tokens", "wall_s",
                                 "cost_usd", "cost_source", "cost_status", "repair_rounds")})
        _expect(observation == terminal)
        capture._path(Path(observation_path.anchor), str(observation_path.relative_to(observation_path.anchor)))
        capture._private_dir(observation_path.parent)
        capture.write_bytes_no_replace(observation_path, capture._json_bytes(terminal), "offline observation")
        capture.finalize_case(repo, identity["project_id"], {**identity, "replay_ref": ref},
                              observation_path, vault_root=vault_root)
        _expect(_inventory(repo) == current and _directory(repo) == prepared["checkout"])
        capture.restore_candidate(vault_root, identity["project_id"], identity["task_id"], ref,
                                   restore_to, expected_attempt_id=identity["attempt_id"])
        return capture.qualify_case(vault_root, identity["project_id"], identity["task_id"], ref,
                                    expected_attempt_id=identity["attempt_id"])
    except (OSError, ValueError, KeyError, TypeError, RecursionError, subprocess.SubprocessError):
        raise ValueError("unit-invalid") from None


def default_journal():
    return capture.default_vault().parent / "journal"  # ponytail: fixed sibling of the vault; config only if a host needs another


def launch_unit(prepared: dict, messages: Iterable[tuple[str, bytes]], *, bootstrap: dict, request: dict, root: Path,
                send: Callable[[bytes], None], materialize_oracle: Callable[[Path], None], observation: dict,
                observation_path: Path, restore_to: Path) -> dict:
    """Plan Task 11: vault/journal fixed by authority, never by the caller; the oracle exists on disk only after the closed terminal."""
    vault, journal = capture.default_vault(), default_journal()
    try:
        oracle = Path(_input(prepared, vault)["environment"]["oracle"]["path"])
        _expect(oracle.is_absolute() and not os.path.lexists(oracle))
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise ValueError("unit-invalid") from None
    state = drive_offline(prepared, messages, bootstrap=bootstrap, request=request, root=root,
                          journal_root=journal, vault_root=vault, send=send)
    candidate = None
    if state["phase"] == "terminal-observed":
        if os.path.lexists(oracle):  # the generator could have read or forged it
            state["gaps"].append("oracle-present-during-generation")
        else:
            try:
                materialize_oracle(oracle)
                candidate = retain_offline_candidate(prepared, observation, repo=Path(prepared["checkout"]["path"]),
                    journal_root=journal, vault_root=vault, observation_path=observation_path, restore_to=restore_to)
            except Exception:  # dispatch evidence is already durable in the journal: report the gap, do not lose the state
                state["gaps"].append("retention-failed")
    return {"protocol": state, "candidate": candidate}


def qualification_report(prepared: dict, protocol: dict, *, candidate: dict | None,
                         oracle_exits: list[int] | None, journal_root: Path, vault_root: Path) -> dict:
    _expect(oracle_exits is None or type(oracle_exits) is list and len(oracle_exits) <= 2
            and all(type(v) is int and -255 <= v <= 255 for v in oracle_exits))
    restored = False
    try:
        root = prepared["restored_checkout"]
        restored = (_directory(root["path"]) == root and _inventory(Path(root["path"])) ==
                    {a["path"]: a for a in prepared["input_inventory"]})
    except (OSError, ValueError, KeyError, TypeError):
        pass
    state, retained = None, False  # caller dicts are claims; the owned journal and the vault are the sources
    try:
        identity, ref = prepared["identity"], prepared["replay_ref"]
        _owned_journal((Path(vault_root) / ref["manifest"]).parent, journal_root)
        binding = native.inspect_binding(journal_root, identity["binding_id"], vault_root=vault_root)
        if all(binding[k] == v for k, v in identity.items()):
            state = binding["binding_state"]
        retained = capture.qualify_case(vault_root, identity["project_id"], identity["task_id"], ref,
                                        expected_attempt_id=identity["attempt_id"])["state"] == "case-retained"
    except (OSError, ValueError, KeyError, TypeError, RecursionError, subprocess.SubprocessError):
        pass
    return dict(scope="offline-calibration", input_restored=restored,
        dispatch_correlated=protocol.get("phase") in ("bound", "terminal-observed") and state in ("bound", "closed"),
        terminal_observed=protocol.get("phase") == "terminal-observed" and state == "closed",
        candidate_retained=bool(candidate and candidate.get("state") == "case-retained") and retained,
        oracle_exits=copy.deepcopy(oracle_exits), gaps=["writer-boundary-unproved", "runtime-unqualified",
        "oracle-origin-unverified", "usage-unobserved", "v2-execution-unqualified"],
        runtime_qualified=False, replay_ready=False, causal_eligible=False, economic_eligible=False, cost_usd=None)
