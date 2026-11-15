"""AMENDMENT-4: build_pilot_v2.py, except that a repository whose final gate re-run is inconsistent leaves the pool instead of
stopping the build. Everything else is build_pilot_v2.py (AMENDMENT-2: the corrected gate, the reference-failed list, the cost check
and the pinned native runner).
- Gate per repository: gate/<repo>.json (gate_rerun.py) when it exists; otherwise the recorded sensitivity.json, accepted only when
  every control was conformant, which makes the corrected gate equal to the recorded one. Enters at >= 30%.
- Every pooled task gets attempts. reference-failed.json lists the tasks the primary freeze leaves out (blind to arms).
- Agent command, arms and comparison from the go-json top-up set, except the native runner path, which is the pinned v1.7.0 one.
- Expected cost 4 x tasks x US$0.264 must fit US$150: no subset (AMENDMENT-1 change 2 stays inactive).
No model. Usage: python3 -I -B build_pilot_v2.py"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script directory out
import pinned  # noqa: E402

HERE = Path(__file__).resolve().parent
MINED = HERE.parent / "public-yield-20261107" / "mine2"
TOPUP = HERE.parent / "public-replay-20261105" / "gojson-topup" / "topup-set.json"
REPOS = ("BurntSushi_toml", "traefik_yaegi", "pelletier_go-toml", "pierrec_lz4", "klauspost_compress")
GATE, SEED, MARGIN, CAP, PER_ATTEMPT = .30, 20261110, .05, 150, .264
OLD_RUNNER = str(HERE.parent.parent / "repo" / "scripts" / "native_runner.py")  # the top-up's, at commit 46dd81f


def gate_for(name, mined):
    rerun = HERE / "gate" / f"{name}.json"
    if rerun.is_file():
        value = json.loads(rerun.read_text())
        if not value["consistent"]:  # AMENDMENT-4: its gate cannot be verified, so it leaves the pool
            return None, value["reference_failed"], "gate_rerun inconsistent: left out (Amendment 4)"
        return value["corrected"]["immediate"]["sensitivity"], value["reference_failed"], "gate_rerun"
    recorded = json.loads((MINED / name / "sensitivity.json").read_text())
    if sorted(recorded["conformant"]) != sorted(t["id"] for t in mined["tasks"]):
        raise SystemExit(f"{name}: a control was not conformant, so the corrected gate needs gate_rerun.py first")
    return recorded["immediate"]["sensitivity"], [], "recorded, every control conformant"


def main():
    pinned.verify()
    topup = json.loads(TOPUP.read_text())
    pooled, gate, failed = None, {}, []
    (HERE / "tasks").mkdir(exist_ok=True)
    for name in REPOS:
        d = MINED / name
        mined = json.loads((d / "replay-set.json").read_text())
        sens, ref_failed, source = gate_for(name, mined)
        gate[name] = {"tasks": len(mined["tasks"]), "sensitivity": sens, "source": source, "reference_failed": ref_failed,
                      "pooled": bool(mined["tasks"]) and sens is not None and sens >= GATE, "below_60": sens is None or sens < .60}
        if not gate[name]["pooled"]:
            continue
        if pooled and set(mined["repos"]) & set(pooled["repos"]):
            raise SystemExit(f"{name}: repository key collides with an earlier repository")
        for key in ("acceptance_sandbox", "acceptance_env"):
            if pooled and mined.get(key) != pooled.get(key):
                raise SystemExit(f"{name}: {key} differs from the first pooled repository")
        pooled = pooled or {**mined, "repos": {}, "tasks": []}
        pooled["repos"].update(mined["repos"])
        pooled["tasks"] += mined["tasks"]
        failed += ref_failed
        for task in mined["tasks"]:
            if not (HERE / "tasks" / task["id"]).exists():
                (HERE / "tasks" / task["id"]).symlink_to(d / "tasks" / task["id"])
    (HERE / "pilot-gate.json").write_text(json.dumps(gate, indent=1))
    if pooled is None:
        print(json.dumps({"gate": gate, "tasks": 0}))
        return 1
    command = list(topup["agent_command"])
    if command.count(OLD_RUNNER) != 1:
        raise SystemExit("the top-up agent command does not name the expected native runner once")
    command[command.index(OLD_RUNNER)] = str(pinned.PINNED / "scripts" / "native_runner.py")
    pooled.update({k: topup[k] for k in ("served_identity", "arms")}, agent_command=command, seed=SEED,
                  compare={**topup["compare"], "margin": MARGIN})
    cost = 4 * len(pooled["tasks"]) * PER_ATTEMPT
    if cost > CAP:
        raise SystemExit(f"expected cost US${cost:.2f} exceeds the cap: AMENDMENT-1 change 2 applies, not implemented here")
    data = json.dumps(pooled, indent=1, ensure_ascii=False)
    (HERE / "pilot-set.json").write_text(data)
    (HERE / "reference-failed.json").write_text(json.dumps(sorted(failed), indent=1))
    summary = {"gate": gate, "tasks": len(pooled["tasks"]), "reference_failed": len(failed), "cells_at_2": 4 * len(pooled["tasks"]),
               "expected_usd": round(cost, 2), "pilot_set_sha256": hashlib.sha256(data.encode()).hexdigest()}
    (HERE / "pilot-build.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
