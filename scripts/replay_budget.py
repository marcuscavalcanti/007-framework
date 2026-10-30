"""Serial USD30 experiment reservations; accounting, not a provider hard cap."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from urllib.parse import quote

import harness_report
import replay_capture

ALLOCATIONS = {"executor_cells": 20, "independent_review": 5, "contingency": 5}


def digest(value):
    return hashlib.sha256(replay_capture._json_bytes(value)).hexdigest()


def check_hash(value):
    if not isinstance(value, str) or not replay_capture.SHA.fullmatch(value):
        raise ValueError("budget source/protocol requires SHA-256")


def check_money(value, positive=False):
    if not harness_report._valid_money(value) or positive and value == 0:
        raise ValueError("budget requires finite nonnegative numeric USD")


def snapshot(config, events):
    if (not isinstance(config, dict) or len(events) > 128 or any(not isinstance(event, dict) for event in events)
            or set(config) != {"protocol_sha256", "cost_basis", "prior_costs", "prior_costs_source_sha256"}
            or not isinstance(config["cost_basis"], str) or config["cost_basis"] not in harness_report.COST_BASES
            or not isinstance(config["prior_costs"], dict)
            or set(config["prior_costs"]) != set(ALLOCATIONS)):
        raise ValueError("invalid budget configuration")
    check_hash(config["protocol_sha256"])
    check_hash(config["prior_costs_source_sha256"])
    for amount in config["prior_costs"].values():
        check_money(amount)
    reservations, settled, unknown = {}, {}, set()
    acknowledged = False
    for index, event in enumerate(events):
        kind = event.get("kind")
        check_hash(event.get("source_sha256"))
        if kind == "checkpoint":
            if (set(event) != {"kind", "state_sha256", "source_sha256"} or acknowledged
                    or event["state_sha256"] != digest({"config": config, "events": events[:index]})):
                raise ValueError("invalid checkpoint binding")
            previous = snapshot(config, events[:index])
            if not previous["checkpoint_due"] or previous["open_calls"] or previous["unpriced_calls"] or previous["violations"]:
                raise ValueError("checkpoint history bypasses incomplete accounting")
            acknowledged = True
            continue
        if set(event) != {"kind", "call_id", "category", "usd", "source_sha256"}:
            raise ValueError("invalid budget event")
        identifier, category = event["call_id"], event["category"]
        if (not isinstance(identifier, str) or not replay_capture.ID.fullmatch(identifier)
                or not isinstance(category, str) or category not in ALLOCATIONS):
            raise ValueError("invalid budget call identity/category")
        if kind == "reserve":
            check_money(event["usd"], positive=True)
            if identifier in reservations:
                raise ValueError("duplicate budget reservation")
            reservations[identifier] = event
        elif kind in ("settle", "unknown"):
            if identifier not in reservations or category != reservations[identifier]["category"] or identifier in settled:
                raise ValueError("settlement is not bound to an open reservation")
            if kind == "unknown":
                if event["usd"] is not None or identifier in unknown:
                    raise ValueError("invalid unknown-cost event")
                unknown.add(identifier)
            else:
                check_money(event["usd"])
                settled[identifier] = event
                unknown.discard(identifier)
        else:
            raise ValueError("unsupported budget event")
    spent_values = list(config["prior_costs"].values()) + [row["usd"] for row in settled.values()]
    pending = [row for key, row in reservations.items() if key not in settled]
    spent = harness_report._money_sum(spent_values)
    reserved = harness_report._money_sum(row["usd"] for row in pending)
    exposure = harness_report._money_sum(spent_values + [row["usd"] for row in pending])
    category_exposure = {category: harness_report._money_sum([config["prior_costs"][category]]
        + [row["usd"] for row in settled.values() if row["category"] == category]
        + [row["usd"] for row in pending if row["category"] == category]) for category in ALLOCATIONS}
    violations = ["reservation-overrun:" + key for key, row in settled.items()
                  if harness_report._money_sum([row["usd"]]) > harness_report._money_sum([reservations[key]["usd"]])]
    violations += ["allocation-exceeded:" + key for key in ALLOCATIONS if category_exposure[key] > ALLOCATIONS[key]]
    if exposure > 30:
        violations.append("total-ceiling-exceeded")
    completed = sum(row["category"] == "executor_cells" for row in settled.values())
    return {"currency": "USD", "cost_basis": config["cost_basis"], "protocol_sha256": config["protocol_sha256"],
            "spent_usd": float(spent), "reserved_usd": float(reserved), "exposure_usd": float(exposure),
            "remaining_usd": None if unknown or violations else float(30 - exposure),
            "category_exposure_usd": {key: float(value) for key, value in category_exposure.items()},
            "open_calls": len(pending), "unpriced_calls": len(unknown), "completed_cells": completed,
            "checkpoint_due": not acknowledged and (exposure >= 10 or completed >= 6),
            "checkpoint_acknowledged": acknowledged, "violations": sorted(violations),
            "state_sha256": digest({"config": config, "events": events})}


class ReplayBudget:
    def __init__(self, path, *, protocol_sha256):
        check_hash(protocol_sha256)
        self.path, self.protocol_sha256 = Path(path).absolute(), protocol_sha256

    @classmethod
    def create(cls, path, *, protocol_sha256, cost_basis, prior_costs, prior_costs_source_sha256):
        value = {"protocol_sha256": protocol_sha256, "cost_basis": cost_basis,
                 "prior_costs": prior_costs, "prior_costs_source_sha256": prior_costs_source_sha256}
        snapshot(value, [])  # Unknown prior spend must never create a fresh zero ledger.
        ledger = cls(path, protocol_sha256=protocol_sha256)
        replay_capture._path(Path(ledger.path.anchor), str(ledger.path.relative_to(ledger.path.anchor)))
        replay_capture._private_dir(ledger.path.parent)
        try:
            descriptor = os.open(ledger.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise ValueError("budget ledger already exists") from exc
        os.close(descriptor)
        with ledger.connection() as connection:
            connection.execute("CREATE TABLE config (data TEXT NOT NULL)")
            connection.execute("CREATE TABLE events (data TEXT NOT NULL)")
            connection.execute("INSERT INTO config VALUES (?)", (json.dumps(value, allow_nan=False),))
        return ledger

    @contextmanager
    def connection(self, write=True):
        replay_capture._path(Path(self.path.anchor), str(self.path.relative_to(self.path.anchor)))
        info = replay_capture._regular(self.path)
        parent = self.path.parent.lstat()
        if (stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid()
                or stat.S_IMODE(parent.st_mode) != 0o700 or parent.st_uid != os.getuid()):
            raise ValueError("budget ledger must be owner-only")
        connection = sqlite3.connect("file:" + quote(str(self.path), safe="/") + "?mode=rw", uri=True, timeout=1)
        try:
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read(self, connection):
        configs = connection.execute("SELECT data FROM config LIMIT 2").fetchall()
        events = connection.execute("SELECT data FROM events ORDER BY rowid LIMIT 129").fetchall()
        if len(configs) != 1 or len(events) > 128:
            raise ValueError("budget ledger is incomplete or exceeds the event bound")
        config, rows = json.loads(configs[0][0]), [json.loads(row[0]) for row in events]
        state = snapshot(config, rows)
        if config["protocol_sha256"] != self.protocol_sha256:
            raise ValueError("budget protocol mismatch")
        return config, rows, state

    def snapshot(self):
        with self.connection(write=False) as connection:
            return self.read(connection)[2]

    def reserve(self, call_id, category, upper_usd, *, bound_source_sha256):
        if not isinstance(call_id, str) or not replay_capture.ID.fullmatch(call_id) or not isinstance(category, str) or category not in ALLOCATIONS:
            raise ValueError("invalid budget call/category")
        check_money(upper_usd, positive=True)
        check_hash(bound_source_sha256)
        event = {"kind": "reserve", "call_id": call_id, "category": category, "usd": upper_usd, "source_sha256": bound_source_sha256}
        with self.connection() as connection:
            config, events, state = self.read(connection)
            prior = next((row for row in events if row.get("call_id") == call_id and row["kind"] == "reserve"), None)
            if prior is not None:
                if prior != event:
                    raise ValueError("budget reservation identity reused with different input")
                return {"launch_granted": False, "state": state}
            proposed = snapshot(config, events + [event])
            if (len(events) > 124 or state["open_calls"] or state["unpriced_calls"] or state["violations"] or state["checkpoint_due"]
                    or proposed["violations"] or not state["checkpoint_acknowledged"] and proposed["exposure_usd"] > 10):
                raise ValueError("budget reservation denied: serial/checkpoint/ceiling or unknown cost")
            # Check exact Decimal exposure; a tiny positive USD cannot vanish in a displayed float.
            if not state["checkpoint_acknowledged"] and harness_report._money_sum(
                    list(config["prior_costs"].values()) + [row["usd"] for row in events if row["kind"] == "settle"] + [upper_usd]) > 10:
                raise ValueError("budget reservation exceeds checkpoint")
            connection.execute("INSERT INTO events VALUES (?)", (json.dumps(event, allow_nan=False),))
            return {"launch_granted": True, "state": proposed}

    def settle(self, call_id, cost_usd, *, cost_basis, source_sha256):
        if cost_usd is not None:
            check_money(cost_usd)
        check_hash(source_sha256)
        with self.connection() as connection:
            config, events, state = self.read(connection)
            reservation = next((row for row in events if row.get("call_id") == call_id and row["kind"] == "reserve"), None)
            if reservation is None or cost_basis != config["cost_basis"]:
                raise ValueError("settlement requires matching call and USD basis")
            event = {"kind": "unknown" if cost_usd is None else "settle", "call_id": call_id,
                     "category": reservation["category"], "usd": cost_usd, "source_sha256": source_sha256}
            existing = [row for row in events if row.get("call_id") == call_id and row["kind"] == event["kind"]]
            if existing:
                if existing[-1] != event:
                    raise ValueError("settlement identity reused with different cost/source")
                return state
            proposed = snapshot(config, events + [event])
            connection.execute("INSERT INTO events VALUES (?)", (json.dumps(event, allow_nan=False),))
            return proposed

    def acknowledge_checkpoint(self, state_sha256, *, review_source_sha256):
        check_hash(review_source_sha256)
        with self.connection() as connection:
            config, events, state = self.read(connection)
            if (state_sha256 != state["state_sha256"] or not state["checkpoint_due"]
                    or state["open_calls"] or state["unpriced_calls"] or state["violations"]):
                raise ValueError("checkpoint requires a current, complete, nonviolating reviewed state")
            event = {"kind": "checkpoint", "state_sha256": state_sha256, "source_sha256": review_source_sha256}
            connection.execute("INSERT INTO events VALUES (?)", (json.dumps(event, allow_nan=False),))
            return snapshot(config, events + [event])
