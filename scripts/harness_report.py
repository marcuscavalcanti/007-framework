#!/usr/bin/env python3
"""Summarize 007 Framework receipts using the Python standard library."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def load_receipts(directory):
    receipts = []
    errors = []
    for path in sorted(Path(directory).expanduser().rglob("*.receipt.json")):
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict) or "status" not in value:
                raise ValueError("receipt must be an object with status")
            receipts.append(value)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"file": str(path), "error": str(exc)})
    return receipts, errors


def summarize(receipts, errors):
    statuses = Counter(str(r.get("status", "unknown")) for r in receipts)
    first_pass = Counter(str(r.get("first_pass", "unmeasured")) for r in receipts)
    numeric_tokens = [r["tokens"] for r in receipts if isinstance(r.get("tokens"), int)]
    tokens = sum(numeric_tokens) if len(numeric_tokens) == len(receipts) and receipts else "unmeasured"
    repairs = [r["repair_rounds"] for r in receipts if isinstance(r.get("repair_rounds"), int)]
    return {
        "tasks": len(receipts),
        "accepted": statuses["accepted"],
        "blocked": statuses["blocked"],
        "no_op": statuses["no-op"],
        "first_pass_yes": first_pass["yes"],
        "repair_rounds_known": sum(repairs),
        "tokens": tokens,
        "tokens_known_sum": sum(numeric_tokens),
        "tokens_known_tasks": len(numeric_tokens),
        "tokens_missing_tasks": len(receipts) - len(numeric_tokens),
        "invalid_receipts": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="Summarize 007 Framework task receipts")
    parser.add_argument("--receipt-dir", required=True)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args()
    summary = summarize(*load_receipts(args.receipt_dir))
    if args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"tasks={summary['tasks']} accepted={summary['accepted']} blocked={summary['blocked']} no_op={summary['no_op']}")
        print(f"first_pass_yes={summary['first_pass_yes']} repair_rounds_known={summary['repair_rounds_known']} tokens={summary['tokens']}")
        print(f"invalid_receipts={len(summary['invalid_receipts'])}")
    return 1 if errors_are_fatal(summary) else 0


def errors_are_fatal(summary):
    return bool(summary["invalid_receipts"])


if __name__ == "__main__":
    sys.exit(main())
