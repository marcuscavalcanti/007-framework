#!/usr/bin/env python3
"""Retort's public results (master.csv, github.com/adrianco/retort, Apache-2.0) as a labelled EXTERNAL prior for 007.

External evidence never becomes a verdict about the user's repository; 007 computes its own n and interval. Rules:
a pass is a first-attempt full pass (requirement_coverage == 1.0 and no second try); an empty cost stays unknown, never zero;
an empty effort is "default", which is not comparable across models or CLI versions; rows whose status is not completed are
excluded. Model ids are normalized so retort's aliases (opus-4.8, claude-opus-4-8) group together.
Usage: python3 scripts/external_prior.py --csv master.csv [--pool-languages] [--min-n 3]
"""
import argparse
import csv
import hashlib
import json
import math
import statistics


def sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def model_key(model):
    key = (model or "").strip().lower().replace(".", "-")
    return key[len("claude-"):] if key.startswith("claude-") else key


def wilson(passes, n, z=1.96):
    if n == 0:
        return None
    p, z2 = passes / n, z * z
    center = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return [max(0.0, round(center - half, 4)), min(1.0, round(center + half, 4))]


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def summarize(path, by_language=True, min_n=3):
    digest, groups = sha256(path), {}
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") != "completed":
                continue
            effort = (row.get("effort") or "").strip() or "default"
            key = (model_key(row.get("model")), effort, row.get("task") or "", (row.get("language") or "") if by_language else "*")
            g = groups.setdefault(key, {"passes": 0, "durations": [], "costs": [], "n": 0})
            g["n"] += 1
            coverage, second = _number(row.get("requirement_coverage")), (row.get("second_try") or "").strip().lower()
            g["passes"] += coverage == 1.0 and second in ("", "0", "false", "no")
            for field, bucket in (("duration_seconds", "durations"), ("cost_usd", "costs")):
                value = _number(row.get(field)) if (row.get(field) or "").strip() else None
                if value is not None:
                    g[bucket].append(value)
    out = {}
    for key, g in groups.items():
        out[key] = {"evidence": "external", "source": "retort master.csv", "source_sha256": digest,
                    "n": g["n"], "passes": g["passes"], "pass_rate": g["passes"] / g["n"], "pass_ci95": wilson(g["passes"], g["n"]),
                    "below_min_n": g["n"] < min_n, "effort_comparable": key[1] != "default",
                    "median_duration_s": statistics.median(g["durations"]) if g["durations"] else None,
                    "median_cost_usd": statistics.median(g["costs"]) if g["costs"] else None,
                    "unknown_cost": g["n"] - len(g["costs"])}
    return out


def main():
    parser = argparse.ArgumentParser(description="Summarize retort's master.csv as a labelled external prior")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--pool-languages", action="store_true")
    parser.add_argument("--min-n", type=int, default=3)
    args = parser.parse_args()
    groups = summarize(args.csv, by_language=not args.pool_languages, min_n=args.min_n)
    rows = [{"model": k[0], "effort": k[1], "task": k[2], "language": k[3], **v} for k, v in sorted(groups.items())]
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
