#!/usr/bin/env python3
"""Explicit private replay inputs. Byte integrity is not producer authentication."""

import hashlib
import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

CONFIG_SCHEMA = "007-framework/capture-config/v1"
INPUT_SCHEMA = "007-framework/replay-input/v1"
CONFIG_SCHEMA_V2 = "007-framework/capture-config/v2"
INPUT_SCHEMA_V2 = "007-framework/replay-input/v2"
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_ENTRIES = 5000
MAX_MANIFEST = 1024 * 1024
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA = re.compile(r"^[0-9a-f]{64}$")


def default_vault():
    return Path.home() / ".007-framework" / "replay"


def _relative(value):
    if (not isinstance(value, str) or not value or len(value) > 1024
            or "\0" in value or "\\" in value or Path(value).is_absolute()
            or str(Path(value)) != value
            or any(part.casefold() in (".", "..", ".git", ".007") for part in value.split("/"))):
        raise ValueError("unsafe capture path")
    return value


def _path(root, value):
    path = root
    for part in _relative(value).split("/"):
        path = path / part
        if path.is_symlink():
            raise ValueError("symlink in capture path")
    return path


def _regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o7000:
        raise ValueError("capture requires a regular file without special mode bits")
    return info


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mode,
            info.st_mtime_ns, info.st_ctime_ns)


def _read(path, limit, expected=None):
    before = _regular(path)
    if expected is not None and _stamp(before) != _stamp(expected):
        raise ValueError("capture source changed since inventory")
    if before.st_size > limit:
        raise ValueError("capture budget exceeded")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        if _stamp(os.fstat(source.fileno())) != _stamp(before):
            raise ValueError("capture source changed")
        payload = source.read(min(limit, before.st_size) + 1)
        if len(payload) != before.st_size or _stamp(os.fstat(source.fileno())) != _stamp(before):
            raise ValueError("capture source changed")
    if _stamp(_regular(path)) != _stamp(before):
        raise ValueError("capture source changed")
    return payload


def _private_dir(path):
    if path.is_symlink():
        raise ValueError("symlink in private vault")
    if not path.exists():
        if not path.parent.exists():
            _private_dir(path.parent)
        path.mkdir(mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
        raise ValueError("vault directory must be owner-only")


class PublishedArtifactError(OSError):
    """Bytes are visible, but a later publication step failed."""


def write_bytes_no_replace(path, payload, label):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    published = durable = False
    try:
        try:
            fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as out:
                    out.write(payload)
                    out.flush()
                    os.fsync(out.fileno())
                try:
                    os.link(name, path)
                except FileExistsError as exc:
                    raise ValueError(f"{label} already exists: {path.name}") from exc
                published = True
                os.fsync(directory)
                durable = True
            except BaseException:
                try:
                    os.unlink(name)
                except OSError:
                    pass  # Preserve the original failure.
                raise
            else:
                os.unlink(name)
        finally:
            if sys.exc_info()[0] is None:
                os.close(directory)
            else:
                try:
                    os.close(directory)
                except OSError:
                    pass  # Preserve the original failure.
    except OSError as exc:
        if published:
            state = "fsync returned; cleanup failed" if durable else "durability unconfirmed"
            raise PublishedArtifactError(f"{label} published; {state}") from exc
        raise


def _json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _config(value):
    keys = {"schema", "files", "prompt_file", "context_files", "acceptance_file",
            "environment_file", "output_files", "command", "requested",
            "executor_timeout_s", "exclusions", "external_inputs"}
    if not isinstance(value, dict) or value.get("schema") not in (CONFIG_SCHEMA, CONFIG_SCHEMA_V2):
        raise ValueError("invalid capture config")
    native = False
    if value["schema"] == CONFIG_SCHEMA_V2:
        keys = keys - {"command"} | {"execution"}
    if set(value) != keys:
        raise ValueError("invalid capture config")
    if value["schema"] == CONFIG_SCHEMA_V2:
        execution = value["execution"]
        if not isinstance(execution, dict):
            raise ValueError("invalid capture execution")
        native = execution.get("kind") == "native-host"
        if native:
            if (set(execution) != {"kind", "adapter", "surface", "binding_id"}
                    or execution["surface"] not in ("terminal", "desktop")
                    or any(not isinstance(execution[k], str) or not ID.fullmatch(execution[k])
                           for k in ("adapter", "binding_id"))):
                raise ValueError("invalid native execution")
        elif set(execution) != {"kind", "argv"} or execution["kind"] != "command":
            raise ValueError("invalid command execution")
        command = None if native else execution["argv"]
    else:
        command = value["command"]
    if not native and (not isinstance(command, list) or not command
                       or any(not isinstance(p, str) or not p for p in command)):
        raise ValueError("capture requires a command")
    for key in ("files", "context_files", "output_files", "exclusions", "external_inputs"):
        if not isinstance(value[key], list) or any(not isinstance(p, str) or not p for p in value[key]):
            raise ValueError("capture fields must be lists of non-empty strings")
    if not value["files"] or not value["context_files"]:
        raise ValueError("capture requires files, command and context")
    for key in ("files", "context_files", "output_files"):
        if len(value[key]) > MAX_ENTRIES:
            raise ValueError("capture entry budget exceeded")
        for name in value[key]:
            _relative(name)
        if len({unicodedata.normalize("NFC", name).casefold() for name in value[key]}) != len(value[key]):
            raise ValueError("duplicate capture path")
    roles = [value[k] for k in ("prompt_file", "acceptance_file", "environment_file")]
    for name in roles:
        _relative(name)
    if any(name not in value["files"] for name in roles + value["context_files"]):
        raise ValueError("capture role must be included in files")
    timeout = value["executor_timeout_s"]
    if (native and timeout is not None) or (not native and (type(timeout) is not int or not 1 <= timeout <= 3600)):
        raise ValueError("executor_timeout_s must be an integer from 1 to 3600")
    requested = value["requested"]
    if not (native and requested is None) and (not isinstance(requested, dict) or set(requested) != {"provider", "model", "effort"}
            or any(not isinstance(v, str) or not v for v in requested.values())):
        raise ValueError("invalid requested route")
    return value


def load_capture_config(path, repo):
    path = Path(path).expanduser().absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("symlink in capture config path")
    return _config(json.loads(_read(path, MAX_MANIFEST)))


def _inventory(root, names):
    if len(names) > MAX_ENTRIES:
        raise ValueError("capture entry budget exceeded")
    infos = [(name, _regular(_path(root, name))) for name in names]
    if any(info.st_size > MAX_FILE for _, info in infos) or sum(info.st_size for _, info in infos) > MAX_TOTAL:
        raise ValueError("capture byte budget exceeded")
    return infos


def _revision(repo):
    result = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD", "HEAD^{tree}"],
                            capture_output=True, text=True, timeout=30,
                            env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")})
    if result.returncode:
        raise ValueError("capture requires a committed Git base")
    return result.stdout.splitlines()


def capture_input(repo, project_id, task_id, config, *, vault_root, attempt_id=None):
    config = _config(config)
    if not all(isinstance(v, str) and ID.fullmatch(v) for v in (project_id, task_id)):
        raise ValueError("invalid capture identity")
    v2 = config["schema"] == CONFIG_SCHEMA_V2
    if (v2 and (not isinstance(attempt_id, str) or not ID.fullmatch(attempt_id))) or (not v2 and attempt_id is not None):
        raise ValueError("invalid capture attempt")
    case_id = attempt_id if v2 else task_id
    repo, vault_root = Path(repo).resolve(), Path(vault_root).absolute()
    infos = _inventory(repo, config["files"])
    revision = _revision(repo)
    from framework_cli import validate_acceptance
    validate_acceptance(json.loads(_read(_path(repo, config["acceptance_file"]), MAX_FILE)))
    environment = json.loads(_read(_path(repo, config["environment_file"]), MAX_FILE))
    if not isinstance(environment, dict):
        raise ValueError("environment recipe must be an object")
    artifacts = [{"path": name, "bytes": info.st_size, "mode": stat.S_IMODE(info.st_mode),
                  "sha256": "0" * 64} for name, info in infos]
    value = {"schema": INPUT_SCHEMA_V2 if v2 else INPUT_SCHEMA, "project_id": project_id, "task_id": task_id,
             "checkout": str(repo), "head": revision[0], "tree": revision[1],
             "config": config, "artifacts": artifacts, "environment": environment,
             "versions": {"python": sys.version.split()[0],
                          "capture_sha256": "0" * 64, "framework_sha256": "0" * 64}}
    if v2:
        value["attempt_id"] = attempt_id
    # Fixed-width digests make this the exact final manifest size, before copying.
    if len(_json_bytes(value)) > MAX_MANIFEST:
        raise ValueError("capture manifest budget exceeded")
    _path(Path(vault_root.anchor), str(vault_root.relative_to(vault_root.anchor)))
    _private_dir(vault_root)
    _private_dir(vault_root / project_id)
    case = vault_root / project_id / case_id
    try:
        case.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise ValueError("capture already exists") from exc
    for artifact, (name, info) in zip(artifacts, infos):
        payload = _read(_path(repo, name), MAX_FILE, info)
        destination = _path(case, f"inputs/{name}")
        _private_dir(destination.parent)
        write_bytes_no_replace(destination, payload, "input artifact")
        artifact["sha256"] = hashlib.sha256(payload).hexdigest()
    after = _inventory(repo, config["files"])
    if [_stamp(info) for _, info in infos] != [_stamp(info) for _, info in after] or revision != _revision(repo):
        raise ValueError("capture source changed")
    for artifact, (name, info) in zip(artifacts, after):
        if hashlib.sha256(_read(_path(repo, name), MAX_FILE, info)).hexdigest() != artifact["sha256"]:
            raise ValueError("capture source bytes changed")
    value["versions"]["capture_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    value["versions"]["framework_sha256"] = hashlib.sha256(Path(__file__).with_name("framework_cli.py").read_bytes()).hexdigest()
    payload = _json_bytes(value)
    if len(payload) > MAX_MANIFEST:
        raise ValueError("capture manifest budget exceeded")
    write_bytes_no_replace(case / "input.json", payload, "input manifest")
    return {"manifest": f"{project_id}/{case_id}/input.json", "sha256": hashlib.sha256(payload).hexdigest()}


def validate_ref_shape(ref):
    if (not isinstance(ref, dict) or set(ref) != {"manifest", "sha256"}
            or not isinstance(ref["sha256"], str) or not SHA.fullmatch(ref["sha256"])):
        raise ValueError("invalid replay_ref")
    _relative(ref["manifest"])
    return ref


def validate_replay_ref(vault_root, project_id, task_id, ref, *, expected_attempt_id=None):
    validate_ref_shape(ref)
    if not all(isinstance(v, str) and ID.fullmatch(v) for v in (project_id, task_id)):
        raise ValueError("invalid replay identity")
    parts = ref["manifest"].split("/")
    if (len(parts) != 3 or parts[0] != project_id or parts[2] != "input.json"
            or not ID.fullmatch(parts[1])
            or expected_attempt_id is not None and
            (not isinstance(expected_attempt_id, str) or not ID.fullmatch(expected_attempt_id))):
        raise ValueError("replay identity does not match reference")
    vault_root = Path(vault_root).absolute()
    _path(Path(vault_root.anchor), str(vault_root.relative_to(vault_root.anchor)))
    manifest = _path(vault_root, ref["manifest"])
    for directory in (vault_root, manifest.parent.parent, manifest.parent):
        info = directory.lstat()
        if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
            raise ValueError("vault directory must be owner-only")
    if stat.S_IMODE(manifest.lstat().st_mode) != 0o600 or manifest.lstat().st_uid != os.getuid():
        raise ValueError("vault file must be owner-only")
    payload = _read(manifest, MAX_MANIFEST)
    if hashlib.sha256(payload).hexdigest() != ref["sha256"]:
        raise ValueError("input manifest hash mismatch")
    value = json.loads(payload)
    if (not isinstance(value, dict) or value.get("schema") not in (INPUT_SCHEMA, INPUT_SCHEMA_V2)
            or value.get("project_id") != project_id or value.get("task_id") != task_id):
        raise ValueError("input manifest identity mismatch")
    v2 = value["schema"] == INPUT_SCHEMA_V2
    case_id = value.get("attempt_id") if v2 else task_id
    if (not isinstance(case_id, str) or not ID.fullmatch(case_id) or parts[1] != case_id
            or expected_attempt_id is not None and (not v2 or case_id != expected_attempt_id)):
        raise ValueError("input attempt identity mismatch")
    keys = {"schema", "project_id", "task_id", "checkout", "head", "tree", "config", "artifacts", "environment", "versions"}
    if v2:
        keys.add("attempt_id")
    if (set(value) != keys
            or not isinstance(value["checkout"], str) or not Path(value["checkout"]).is_absolute()
            or any(not isinstance(value[k], str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value[k]) for k in ("head", "tree"))
            or not isinstance(value["environment"], dict) or not isinstance(value["versions"], dict)
            or set(value["versions"]) != {"python", "framework_sha256", "capture_sha256"}
            or not isinstance(value["versions"]["python"], str) or not value["versions"]["python"]
            or any(not isinstance(value["versions"][k], str) or not SHA.fullmatch(value["versions"][k]) for k in ("framework_sha256", "capture_sha256"))):
        raise ValueError("invalid input metadata")
    config = _config(value.get("config"))
    if (config["schema"] == CONFIG_SCHEMA_V2) != v2:
        raise ValueError("input config version mismatch")
    artifacts = value.get("artifacts")
    if (not isinstance(artifacts, list) or len(artifacts) != len(config["files"])
            or any(not isinstance(a, dict) or set(a) != {"path", "bytes", "mode", "sha256"} for a in artifacts)
            or [a["path"] for a in artifacts] != config["files"]):
        raise ValueError("invalid artifact inventory")
    for artifact in artifacts:
        if (type(artifact["bytes"]) is not int or not 0 <= artifact["bytes"] <= MAX_FILE
                or type(artifact["mode"]) is not int or not 0 <= artifact["mode"] <= 0o777
                or not isinstance(artifact["sha256"], str) or not SHA.fullmatch(artifact["sha256"])):
            raise ValueError("invalid artifact fields")
    _inventory(manifest.parent / "inputs", config["files"])
    for artifact in artifacts:
        path = _path(manifest.parent, f"inputs/{artifact['path']}")
        for directory in path.parents:
            if directory == manifest.parent:
                break
            if stat.S_IMODE(directory.lstat().st_mode) != 0o700 or directory.lstat().st_uid != os.getuid():
                raise ValueError("vault directory must be owner-only")
        if stat.S_IMODE(path.lstat().st_mode) != 0o600 or path.lstat().st_uid != os.getuid():
            raise ValueError("vault file must be owner-only")
        data = _read(path, MAX_FILE)
        if len(data) != artifact["bytes"] or hashlib.sha256(data).hexdigest() != artifact["sha256"]:
            raise ValueError("input artifact hash mismatch")
    from framework_cli import validate_acceptance
    validate_acceptance(json.loads(_read(manifest.parent / "inputs" / config["acceptance_file"], MAX_FILE)))
    if json.loads(_read(manifest.parent / "inputs" / config["environment_file"], MAX_FILE)) != value["environment"]:
        raise ValueError("environment metadata differs from captured bytes")
    return value


def _read_private_artifact(case, name, limit):
    path = _path(case, name)
    directory = path.parent
    while directory != case:
        info = directory.lstat()
        if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
            raise ValueError("retained directory must be owner-only")
        directory = directory.parent
    info = _regular(path)
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
        raise ValueError("retained file must be owner-only")
    return _read(path, limit, info)


def qualify_case(vault_root, project_id, task_id, ref, *, expected_attempt_id=None):
    """Sanitized retained-byte integrity; never runs an oracle or authenticates a producer."""
    projection = {"state": "observational", "input_sha256": None, "result_sha256": None,
                  "inputs_fingerprint_sha256": None, "inputs_recoverable": False,
                  "candidate_recoverable": False, "replay_ready": False,
                  "causal_eligible": False, "economic_eligible": False,
                  "gaps": ["retained-input-unavailable"]}
    if ref is None:
        return projection
    try:
        value = validate_replay_ref(vault_root, project_id, task_id, ref, expected_attempt_id=expected_attempt_id)
    except OSError:
        projection.update(state="unavailable", inputs_recoverable=None, gaps=["retained-input-unreadable"])
        return projection
    except ValueError:
        projection.update(state="invalid", gaps=["retained-input-invalid"])
        return projection
    projection.update(state="inputs-retained", input_sha256=ref["sha256"], inputs_recoverable=True,
                      inputs_fingerprint_sha256=hashlib.sha256(_json_bytes(sorted(value["artifacts"], key=lambda a: a["path"]))).hexdigest(),
                      gaps=["terminal-candidate-unavailable", "environment-not-reconstructed",
                            "oracle-not-independently-executed", "generator-isolation-unqualified"])
    if value["schema"] == INPUT_SCHEMA_V2:
        projection["gaps"].append("v2-execution-unqualified")
    case = Path(vault_root).absolute() / ref["manifest"]
    case = case.parent
    try:
        case.joinpath("result.json").lstat()
    except FileNotFoundError:
        return projection
    except OSError:
        projection.update(state="unavailable", candidate_recoverable=None, gaps=["retained-candidate-unreadable"])
        return projection
    try:
        payload = _read_private_artifact(case, "result.json", MAX_MANIFEST)
        result = json.loads(payload)
        if (not isinstance(result, dict) or set(result) != {"schema", "input_sha256", "receipt", "outputs", "deleted_files", "checks", "telemetry"}
                or result["schema"] != "007-framework/replay-result/v1" or result["input_sha256"] != ref["sha256"]
                or not isinstance(result["receipt"], dict) or set(result["receipt"]) != {"path", "sha256"}
                or result["receipt"]["path"] != "outputs/receipt.json"
                or not isinstance(result["receipt"]["sha256"], str) or not SHA.fullmatch(result["receipt"]["sha256"])
                or not isinstance(result["outputs"], list) or not isinstance(result["deleted_files"], list)):
            raise ValueError("invalid retained result")
        names = value["config"]["output_files"]
        outputs, deleted = result["outputs"], result["deleted_files"]
        if len(outputs) + len(deleted) != len(names):
            raise ValueError("incomplete retained output inventory")
        for artifact in outputs:
            if (not isinstance(artifact, dict) or set(artifact) != {"path", "bytes", "mode", "sha256"}
                    or type(artifact["bytes"]) is not int or not 0 <= artifact["bytes"] <= MAX_FILE
                    or type(artifact["mode"]) is not int or not 0 <= artifact["mode"] <= 0o777
                    or not isinstance(artifact["sha256"], str) or not SHA.fullmatch(artifact["sha256"])):
                raise ValueError("invalid retained artifact")
            _relative(artifact["path"])
        for name in deleted:
            _relative(name)
        paths = [a["path"] for a in outputs] + deleted
        if len(set(paths)) != len(paths) or set(paths) != set(names):
            raise ValueError("retained output paths differ")
        infos = _inventory(case / "outputs/files", [a["path"] for a in outputs])
        receipt = _read_private_artifact(case, "outputs/receipt.json", MAX_MANIFEST)
        if sum(i.st_size for _, i in infos) + len(receipt) > MAX_TOTAL:
            raise ValueError("retained output byte budget exceeded")
        terminal = json.loads(receipt)
        if (hashlib.sha256(receipt).hexdigest() != result["receipt"]["sha256"]
                or not isinstance(terminal, dict) or terminal.get("task_id") != task_id
                or terminal.get("project_id", project_id) != project_id or terminal.get("replay_ref") != ref
                or result["checks"] != terminal.get("checks") or not isinstance(result["telemetry"], dict)
                or set(result["telemetry"]) != {"served_provider", "served_model", "served_effort", "tokens",
                                               "wall_s", "cost_usd", "cost_source", "cost_status", "repair_rounds"}
                or result["telemetry"] != {k: terminal.get(k) for k in result["telemetry"]}):
            raise ValueError("retained terminal binding differs")
        for artifact in outputs:
            data = _read_private_artifact(case, f"outputs/files/{artifact['path']}", MAX_FILE)
            if len(data) != artifact["bytes"] or hashlib.sha256(data).hexdigest() != artifact["sha256"]:
                raise ValueError("retained candidate hash differs")
        projection.update(state="case-retained", candidate_recoverable=True,
                          result_sha256=hashlib.sha256(payload).hexdigest(), gaps=projection["gaps"][1:])
    except OSError:
        projection.update(state="unavailable", candidate_recoverable=None, gaps=["retained-candidate-unreadable"])
    except ValueError:
        projection.update(state="invalid", gaps=["retained-candidate-invalid"])
    return projection


def finalize_case(repo, project_id, task, receipt_path, *, vault_root):
    value = validate_replay_ref(vault_root, project_id, task["task_id"], task["replay_ref"],
                                expected_attempt_id=task.get("attempt_id"))
    case = Path(vault_root) / task["replay_ref"]["manifest"]
    case = case.parent
    if (case / "result.json").exists():
        raise ValueError("result already exists")
    names = value["config"]["output_files"]
    present = [name for name in names if _path(repo, name).exists()]
    deleted = [name for name in names if name not in present]
    revision = _revision(repo)
    infos = _inventory(repo, present)
    receipt = _read(receipt_path, MAX_MANIFEST)
    terminal = json.loads(receipt)
    if (not isinstance(terminal, dict) or terminal.get("task_id") != task["task_id"]
            or terminal.get("replay_ref") != task["replay_ref"]):
        raise ValueError("terminal replay identity mismatch")
    if sum(i.st_size for _, i in infos) + len(receipt) > MAX_TOTAL:
        raise ValueError("terminal capture byte budget exceeded")
    _private_dir(case / "outputs")
    write_bytes_no_replace(case / "outputs/receipt.json", receipt, "terminal receipt copy")
    outputs = []
    for name, info in infos:
        data = _read(_path(repo, name), MAX_FILE, info)
        destination = _path(case, f"outputs/files/{name}")
        _private_dir(destination.parent)
        write_bytes_no_replace(destination, data, "output artifact")
        outputs.append({"path": name, "bytes": len(data), "mode": stat.S_IMODE(info.st_mode),
                        "sha256": hashlib.sha256(data).hexdigest()})
    if ([_stamp(i) for _, i in infos] != [_stamp(i) for _, i in _inventory(repo, present)]
            or any(_path(repo, name).exists() for name in deleted) or revision != _revision(repo)):
        raise ValueError("output source changed")
    for artifact, (name, info) in zip(outputs, infos):
        if hashlib.sha256(_read(_path(repo, name), MAX_FILE, info)).hexdigest() != artifact["sha256"]:
            raise ValueError("output source bytes changed")
    result = {"schema": "007-framework/replay-result/v1", "input_sha256": task["replay_ref"]["sha256"],
              "receipt": {"path": "outputs/receipt.json", "sha256": hashlib.sha256(receipt).hexdigest()},
              "outputs": outputs, "deleted_files": deleted, "checks": terminal["checks"], "telemetry": {
                  key: terminal[key] for key in ("served_provider", "served_model", "served_effort",
                      "tokens", "wall_s", "cost_usd", "cost_source", "cost_status", "repair_rounds")}}
    payload = _json_bytes(result)
    if len(payload) > MAX_MANIFEST:
        raise ValueError("result manifest budget exceeded")
    write_bytes_no_replace(case / "result.json", payload, "result manifest")
    return case / "result.json"


def preserve_incomplete_case(repo, project_id, task, reason, command_exit, *, vault_root, wall_s, telemetry=None):
    ref = task["replay_ref"]
    validate_replay_ref(vault_root, project_id, task["task_id"], ref, expected_attempt_id=task.get("attempt_id"))
    case = _path(Path(vault_root).absolute(), ref["manifest"]).parent
    observation = {"observation_kind": "execution-incomplete", "task_id": task["task_id"],
                   "project_id": project_id, "replay_ref": ref, "reason_code": reason,
                   "command_exit": command_exit, "checks": [], "wall_s": wall_s,
                   "served_provider": "unmeasured", "served_model": "unmeasured", "served_effort": "unmeasured",
                   "tokens": None, "cost_usd": None, "cost_source": "custom:unpriced-execution-observation",
                   "cost_status": "unavailable", "repair_rounds": "unmeasured"}
    if telemetry is not None:
        observation["native_telemetry"] = telemetry
    payload = _json_bytes(observation)
    if len(payload) > MAX_MANIFEST:
        raise ValueError("incomplete observation budget exceeded")
    source = case / "observation.json"
    write_bytes_no_replace(source, payload, "incomplete execution observation")
    return finalize_case(repo, project_id, task, source, vault_root=vault_root)


def restore_input(vault_root, project_id, task_id, ref, destination, *, expected_attempt_id=None):
    value = validate_replay_ref(vault_root, project_id, task_id, ref, expected_attempt_id=expected_attempt_id)
    destination = Path(destination).absolute()
    if any(p.is_symlink() for p in (destination, *destination.parents)):
        raise ValueError("symlink in restore destination")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("restore destination must be new or empty")
    _private_dir(destination)
    case = Path(vault_root) / ref["manifest"]
    for artifact in value["artifacts"]:
        source = _path(case.parent, f"inputs/{artifact['path']}")
        data = _read(source, MAX_FILE)
        if hashlib.sha256(data).hexdigest() != artifact["sha256"]:
            raise ValueError("input changed during restore")
        target = _path(destination, artifact["path"])
        _private_dir(target.parent)
        write_bytes_no_replace(target, data, "restored input")
        target.chmod(artifact["mode"])
        if (hashlib.sha256(_read(target, MAX_FILE)).hexdigest() != artifact["sha256"]
                or stat.S_IMODE(target.stat().st_mode) != artifact["mode"]):
            raise ValueError("restore verification failed")
    return value


def restore_candidate(vault_root, project_id, task_id, ref, destination, *, expected_attempt_id=None):
    projection = qualify_case(vault_root, project_id, task_id, ref, expected_attempt_id=expected_attempt_id)
    if projection["state"] != "case-retained":
        raise ValueError("retained candidate is not readable and coherent")
    case = (Path(vault_root).absolute() / ref["manifest"]).parent
    payload = _read_private_artifact(case, "result.json", MAX_MANIFEST)
    if hashlib.sha256(payload).hexdigest() != projection["result_sha256"]:
        raise ValueError("retained result changed before restoration")
    result = json.loads(payload)
    restore_input(vault_root, project_id, task_id, ref, destination, expected_attempt_id=expected_attempt_id)
    destination = Path(destination).absolute()
    for artifact in result["outputs"]:
        data = _read_private_artifact(case, f"outputs/files/{artifact['path']}", MAX_FILE)
        if len(data) != artifact["bytes"] or hashlib.sha256(data).hexdigest() != artifact["sha256"]:
            raise ValueError("retained candidate changed during restoration")
        target = _path(destination, artifact["path"])
        if target.exists():
            _regular(target)
            target.unlink()  # Only overlays the fresh copy made by restore_input.
        _private_dir(target.parent)
        write_bytes_no_replace(target, data, "restored candidate")
        if hashlib.sha256(_read(target, MAX_FILE)).hexdigest() != artifact["sha256"]:
            raise ValueError("restored candidate bytes differ")
        target.chmod(artifact["mode"])
        if stat.S_IMODE(target.stat().st_mode) != artifact["mode"]:
            raise ValueError("restored candidate mode differs")
    for name in result["deleted_files"]:
        target = _path(destination, name)
        if target.exists():
            _regular(target)
            target.unlink()
    final = qualify_case(vault_root, project_id, task_id, ref, expected_attempt_id=expected_attempt_id)
    if final["state"] != "case-retained" or final["result_sha256"] != projection["result_sha256"]:
        raise ValueError("retained source changed during restoration")
    return {"input_sha256": ref["sha256"], "result_sha256": projection["result_sha256"]}


class CaptureArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "capture/restore refused: invalid-arguments\n")


def main(argv=None):
    parser = CaptureArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capture", "restore"))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--attempt-id")
    for field in ("vault-root", "repo", "config", "out"):
        parser.add_argument("--" + field, type=Path)
    parser.add_argument("--manifest")
    parser.add_argument("--sha256")
    args = parser.parse_args(argv)
    capture_flags = (args.repo, args.config)
    restore_flags = (args.manifest, args.sha256, args.out)
    required, forbidden = ((capture_flags + (args.vault_root,), restore_flags) if args.command == "capture"
                           else (restore_flags, capture_flags))
    if any(value is None for value in required) or any(value is not None for value in forbidden):
        parser.error("invalid operation flags")
    try:
        if args.command == "capture":
            config = load_capture_config(args.config, args.repo)
            result = capture_input(args.repo, args.project_id, args.task_id, config,
                                   vault_root=args.vault_root, attempt_id=args.attempt_id)
        else:
            value = restore_input(args.vault_root if args.vault_root is not None else default_vault(),
                                  args.project_id, args.task_id,
                                  {"manifest": args.manifest, "sha256": args.sha256}, args.out,
                                  expected_attempt_id=args.attempt_id)
            result = {"project_id": args.project_id, "task_id": args.task_id,
                      "input_sha256": args.sha256, "restored_files": len(value["artifacts"])}
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"{args.command} refused: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
