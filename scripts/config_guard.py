#!/usr/bin/env python3
"""Configuration may TUNE 007, never INVALIDATE it.

Every entry point loads ~/.007-framework/config.json through `load`, which refuses (ConfigError, naming every problem) when:
- a key is unknown (a typo must not silently switch something off; the likely name is suggested);
- a value leaves the bounds that keep a verdict meaningful (e.g. a negative non-inferiority margin, n below 5, a confidence other
  than 90/95/99 %, a time cut of 0 %, a durability window under one day);
- someone tries to configure what DEFINES the evidence (the meaning of levels 0-3 and of the badges is code, not configuration);
- a running effort trial would change its seed or arms (that silently mixes two experiments): end it and start a new `trial_id`.
Switching the trial off, restricting repositories or agents, and moving thresholds inside their bounds stay free.
Usage: python3 scripts/config_guard.py [--config ~/.007-framework/config.json]   (prints the problems, exit 2 if any)
"""
import argparse
import difflib
import json
from pathlib import Path
import sys

HOME = Path.home() / ".007-framework"
# effort levels a trial may randomize, from the installed CLIs (Codex enum; Claude: "max" is session-only; Kimi K3 support_efforts)
EFFORTS = {"codex": ("none", "minimal", "low", "medium", "high", "xhigh", "max"), "claude": ("low", "medium", "high", "xhigh"),
           "kimi": ("low", "high", "max")}  # gemini exposes no effort setting: observed only, never randomized
OBSERVATORY = {"projects", "auto", "exclude", "lookback_hours", "activity_gap_minutes", "calibrations", "effort_trial", "evidence",
               "durability_windows_days", "attribution_slack_s", "lab_report", "_note", "_note_auto"}
TRIAL = {"enabled", "arms", "seed", "repos", "agents", "trial_id", "claude_model"}
EVIDENCE = {"confidence", "min_n", "margin", "min_gain"}
FIXED = {"levels", "badges", "level_semantics"}


class ConfigError(ValueError):
    pass


def _unknown(where, keys, allowed):
    out = []
    for key in sorted(set(keys) - allowed):
        near = difflib.get_close_matches(key, sorted(allowed), n=1)
        out.append(f"{where}.{key}: unknown key" + (f" (did you mean {where}.{near[0]}?)" if near else ""))
    return out


def _number(where, value, low, high, kind=(int, float)):
    if type(value) is bool or not isinstance(value, kind) or not low <= value <= high:
        return [f"{where}: must be a number in [{low}, {high}], got {value!r}"]
    return []


def _running(trial_log, trial_id):
    """The last logged state of each agent in this trial: {agent: (seed, arms)}."""
    state = {}
    if trial_log is not None and Path(trial_log).is_file():
        for line in Path(trial_log).read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("trial_id", "default") == trial_id and row.get("agent"):
                state[row["agent"]] = (row.get("seed"), row.get("arms"))
    return state


def check(config, trial_log=HOME / "observatory" / "effort_trial.jsonl"):
    if not isinstance(config, dict):
        return ["config: must be a JSON object"]
    obs = config.get("observatory", {})
    if not isinstance(obs, dict):
        return ["observatory: must be an object"]
    problems = _unknown("observatory", obs, OBSERVATORY)
    for key in ("projects", "exclude", "calibrations"):
        if key in obs and not isinstance(obs[key], list):
            problems.append(f"observatory.{key}: must be a list")
    if "auto" in obs and not isinstance(obs["auto"], bool):
        problems.append("observatory.auto: must be true or false")
    if "lookback_hours" in obs:
        problems += _number("observatory.lookback_hours", obs["lookback_hours"], 24, 24 * 30, int)
    if "activity_gap_minutes" in obs:
        problems += _number("observatory.activity_gap_minutes", obs["activity_gap_minutes"], 5, 240, int)
    if "attribution_slack_s" in obs:
        problems += _number("observatory.attribution_slack_s", obs["attribution_slack_s"], 0, 4 * 3600, int)
    if "durability_windows_days" in obs:
        windows = obs["durability_windows_days"]
        if not isinstance(windows, list) or not windows or any(type(w) is not int or w < 1 for w in windows):
            problems.append("observatory.durability_windows_days: must be a non-empty list of whole days >= 1")
    evidence = obs.get("evidence", {})
    if not isinstance(evidence, dict):
        problems.append("observatory.evidence: must be an object")
        evidence = {}
    for key in sorted(set(evidence) & FIXED):
        problems.append(f"observatory.evidence.{key}: not configurable (the meaning of evidence levels and badges is fixed in code)")
    problems += _unknown("observatory.evidence", set(evidence) - FIXED, EVIDENCE)
    if "confidence" in evidence and evidence["confidence"] not in (0.9, 0.95, 0.99):
        problems.append(f"observatory.evidence.confidence: must be 0.9, 0.95 or 0.99, got {evidence['confidence']!r}")
    if "min_n" in evidence:
        problems += _number("observatory.evidence.min_n", evidence["min_n"], 5, 10_000, int)
    if "margin" in evidence:  # non-inferiority margin on acceptance: 0 = no worse; negative would accept "worse" as "same"
        problems += _number("observatory.evidence.margin", evidence["margin"], 0.0, 0.10)
    if "min_gain" in evidence:
        problems += _number("observatory.evidence.min_gain", evidence["min_gain"], 0.05, 0.90)
    trial = obs.get("effort_trial")
    if trial is not None:
        problems += _trial(trial, trial_log)
    return problems


def _trial(trial, trial_log):
    if not isinstance(trial, dict):
        return ["observatory.effort_trial: must be an object"]
    problems = _unknown("observatory.effort_trial", trial, TRIAL)
    if "enabled" in trial and not isinstance(trial["enabled"], bool):
        problems.append("observatory.effort_trial.enabled: must be true or false")
    arms = trial.get("arms", {})
    if not isinstance(arms, dict):
        return problems + ["observatory.effort_trial.arms: must map agent -> [effort, effort]"]
    for agent, levels in arms.items():
        where = f"observatory.effort_trial.arms.{agent}"
        if agent not in EFFORTS:
            problems.append(f"{where}: {agent} has no effort setting that can be randomized (supported: {', '.join(EFFORTS)})")
        elif not isinstance(levels, list) or len(levels) < 2 or len(set(levels)) != len(levels):
            problems.append(f"{where}: must list at least two distinct effort levels")
        elif any(level not in EFFORTS[agent] for level in levels):
            problems.append(f"{where}: unsupported level in {levels} (supported: {', '.join(EFFORTS[agent])})")
    if "seed" in trial and (type(trial["seed"]) is not int):
        problems.append("observatory.effort_trial.seed: must be an integer")
    if trial.get("enabled") is not True:
        return problems  # switching off is always allowed
    for agent, (seed, logged_arms) in _running(trial_log, trial.get("trial_id", "default")).items():
        if "seed" in trial and seed is not None and seed != trial["seed"]:
            problems.append(f"observatory.effort_trial.seed: trial {trial.get('trial_id', 'default')!r} is running with seed {seed}; "
                            "changing it mixes two experiments — start a new trial (new trial_id) instead")
        if agent in arms and logged_arms is not None and list(logged_arms) != list(arms[agent]):
            problems.append(f"observatory.effort_trial.arms.{agent}: trial {trial.get('trial_id', 'default')!r} is running with "
                            f"{logged_arms}; changing arms mixes two experiments — start a new trial (new trial_id) instead")
    return problems


def load(path, trial_log=HOME / "observatory" / "effort_trial.jsonl"):
    """The validated configuration ({} when the file does not exist); ConfigError lists every problem otherwise."""
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        config = json.loads(path.read_text())
    except ValueError as exc:
        raise ConfigError(f"{path}: not valid JSON ({exc})") from None
    problems = check(config, trial_log=trial_log)
    if problems:
        raise ConfigError(f"{path}: configuration refused, 007 would no longer measure what it claims:\n  - " + "\n  - ".join(problems))
    return config


def main():
    parser = argparse.ArgumentParser(description="Validate the 007 configuration against the bounds that keep its evidence valid")
    parser.add_argument("--config", default=str(HOME / "config.json"))
    args = parser.parse_args()
    try:
        load(args.config)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    print("configuration ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
