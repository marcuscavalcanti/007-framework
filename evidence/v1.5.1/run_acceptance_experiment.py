#!/usr/bin/env python3
"""Frozen, synthetic admission-fence experiment. No models or private data."""
import argparse
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CLI = ROOT / "scripts/framework_cli.py"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def grade(case, raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique)
        if case == "eligible-row-contract":
            return int(not {"costBasisGenesis", "calculationConfidence", "evidenceCompleteness"}.issubset(value))
        return 0
    except (ValueError, TypeError):
        return 1


def claimed_receipt(task_id):
    receipt = json.loads((ROOT / "examples/task.receipt.example.json").read_text())
    receipt.update(task_id=task_id, status="accepted",
                   first_pass="yes", repair_rounds=0, escape_7d="pending",
                   proof_required="focused", proof_reached="focused",
                   checks=[{"command": "synthetic executor claims PASS", "exit": 0}],
                   tokens="unmeasured", wall_s="unmeasured",
                   cost_usd=None, cost_source="custom:synthetic-executor", cost_status="unavailable",
                   cost_unavailable_reason="Deterministic synthetic executor; monetary cost unmeasured")
    for field in ("provider", "model", "effort", "served_provider", "served_model", "served_effort",
                  "requested_provider", "requested_model", "requested_effort"):
        receipt[field] = "unmeasured"
    receipt["delta"] = {"files": 1, "added": 1, "deleted": 0, "dependencies": 0}
    receipt["uncertainty"] = "Synthetic executor deliberately claims acceptance; common grader establishes truth"
    return receipt


def execute(args, protocol):
    case = protocol["cases"][args.case]
    raw = case["bad"] if args.condition == "defective" else case["good"]
    Path("candidate.json").write_text(raw, encoding="utf-8")
    receipt = claimed_receipt(os.environ["FRAMEWORK_007_TASK_ID"])
    Path(os.environ["FRAMEWORK_007_RECEIPT_PATH"]).write_text(json.dumps(receipt))


def run(protocol, out, protocol_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import framework_cli
    framework_cli.validate_receipt(claimed_receipt("preflight"), allow_cost_unavailable=True)
    expected_matrix = {
        "OLD": {condition: {"exit": 0, "status": "accepted"} for condition in ("defective", "correct", "verifier-unavailable")},
        "NEW": {"defective": {"exit": 4, "status": "blocked"}, "correct": {"exit": 0, "status": "accepted"},
                "verifier-unavailable": {"exit": 2, "status": "open"}},
    }
    if len(protocol["cases"]) != 2 or protocol["replicates"] != 3 or protocol["expected"] != expected_matrix:
        raise SystemExit("Protocol does not match the fixed two-case, 36-cell experiment")
    protocol_digest = digest(protocol_path.read_bytes())
    pins = protocol["source_sha256"]
    for relative, expected in pins.items():
        if digest((ROOT / relative).read_bytes()) != expected:
            raise SystemExit(f"Source drift: {relative}")
    pairs = [(case, condition, replicate) for case in protocol["cases"]
             for condition in ("defective", "correct", "verifier-unavailable")
             for replicate in range(1, protocol["replicates"] + 1)]
    random.Random(protocol["seed"]).shuffle(pairs)
    cells = []
    with tempfile.TemporaryDirectory(prefix="007-admission-proof-") as scratch:
        for case, condition, replicate in pairs:
            for arm in ("OLD", "NEW"):
                repo = Path(scratch, f"{case}-{condition}-{replicate}-{arm}")
                repo.mkdir()
                subprocess.run(["git", "init", "-q", str(repo)], check=True)
                common = [sys.executable, str(CLI)]
                subprocess.run(common + ["init", "--repo", str(repo), "--registry", str(repo / "registry.json")],
                               check=True, capture_output=True)
                marker = repo / ".007/project.json"
                marker.write_text(json.dumps({**json.loads(marker.read_text()), "cost_unavailable_opt_in": True}))
                command = common + ["run", "--repo", str(repo), "--task-id", "cell", "--receipt", "executor.receipt.json"]
                if arm == "NEW":
                    oracle = [sys.executable, str(Path(__file__).resolve()), "--protocol", str(protocol_path), "--oracle", "--case", case]
                    if condition == "verifier-unavailable":
                        oracle = [str(repo / "verifier-does-not-exist")]
                    contract = repo / "acceptance.json"
                    contract.write_text(json.dumps({"schema": "007-framework/acceptance/v1", "commands": [oracle], "timeout_s": 5}))
                    command += ["--acceptance-file", str(contract)]
                command += ["--", sys.executable, str(Path(__file__).resolve()), "--protocol", str(protocol_path), "--executor", "--case", case, "--condition", condition]
                result = subprocess.run(command, capture_output=True, timeout=20)
                raw = (repo / "candidate.json").read_bytes()
                expected_raw = protocol["cases"][case]["bad" if condition == "defective" else "good"].encode()
                files = list((repo / ".007/receipts").glob("*.receipt.json"))
                receipt = json.loads(files[0].read_text()) if len(files) == 1 else {}
                task = framework_cli.validate_task_start(json.loads((repo / ".007/tasks/cell.task.json").read_text()))
                cell = {"case": case, "condition": condition, "replicate": replicate, "arm": arm,
                        "exit": result.returncode, "candidate_sha256": digest(raw),
                        "grader_exit": grade(case, raw), "status": receipt.get("status", "open"),
                        "acceptance_evidence": receipt.get("acceptance_evidence", "unobserved"),
                        "persisted_start": task["task_id"] == "cell",
                        "stdout_sha256": digest(result.stdout), "stderr_sha256": digest(result.stderr)}
                expected = protocol["expected"][arm][condition]
                cell["valid"] = (raw == expected_raw and cell["status"] == expected["status"]
                                 and cell["exit"] == expected["exit"]
                                 and cell["grader_exit"] == int(condition == "defective"))
                if arm == "NEW":
                    if condition == "verifier-unavailable":
                        cell["valid"] &= not files and b"verifier-does-not-exist" in result.stderr
                    else:
                        cell["valid"] &= receipt.get("acceptance_evidence") == "controlled" and receipt.get("acceptance_summary") == {
                            "passed": int(condition == "correct"), "failed": int(condition == "defective")}
                        cell["valid"] &= receipt.get("acceptance_sha256") == digest(contract.read_bytes())
                cell["valid"] &= cell["persisted_start"]
                cells.append(cell)
    drift = [relative for relative, expected in pins.items() if digest((ROOT / relative).read_bytes()) != expected]
    if digest(protocol_path.read_bytes()) != protocol_digest:
        drift.append("protocol")
    result = {"status": "supported-frozen-synthetic-cases" if len(cells) == 36 and not drift and all(c["valid"] for c in cells) else "inconclusive",
              "source_protocol_sha256": protocol_digest, "source_drift": drift,
              "source_sha256": pins, "runtime": {"python": platform.python_version(), "platform": platform.system()},
              "independent_cases": len(protocol["cases"]), "replicates": protocol["replicates"],
              "total_cells": len(cells), "invalid_cells": sum(not c["valid"] for c in cells), "cells": cells,
              "cost_usd": None, "cost_status": "unmeasured", "model_calls": 0,
              "boundary": "Controller admission only, on two sanitized structural fixtures derived from observed defects. Not private-project replays, model quality, economic ROI, general review replacement or D7 durability."}
    with out.open("x", encoding="utf-8") as target:
        json.dump(result, target, indent=2)
        target.write("\n")
    print(json.dumps({key: result[key] for key in ("status", "total_cells", "invalid_cells", "model_calls")}))
    return int(result["status"] != "supported-frozen-synthetic-cases")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor", action="store_true")
    parser.add_argument("--oracle", action="store_true")
    parser.add_argument("--case")
    parser.add_argument("--condition")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--protocol", type=Path, default=HERE / "protocol-r3.json")
    args = parser.parse_args()
    protocol_path = args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    if args.executor:
        execute(args, protocol)
    elif args.oracle:
        sys.exit(grade(args.case, Path("candidate.json").read_bytes()))
    elif args.out:
        sys.exit(run(protocol, args.out, protocol_path))
    else:
        parser.error("Use --out with a new result path")
