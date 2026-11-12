"""DECISIONS.md part 3: can one repository, alone, reach a 5-point verdict with 80% power if the arms are equal? Never enters GO /
NO-GO and never changes the confirmatory verdict: it reads only variances, counts and a simulated critical value.
- Size: the repository's reaching tasks in the primary freeze's frozen-reach.json (never mined tasks); fewer than 8 cannot hold.
- Noise: tau2 (the larger estimate, at least 0) + sigma2 / 4, from the confirmatory cells, on every reaching task and on the
  repository's own; the larger is used.
- Critical value: max(2.198, c), c simulated from the repository's own confirmatory cells (100,000 draws); none simulable: no hold.
- Holds if size >= noise x ((critical + 0.8416) / 0.05)^2.
- Without confirmatory results nothing holds; the pilot's n80 is compared with each size as a description only.
Reported, never deciding: a task-bootstrap 95% interval of each required size (critical value held fixed), the required size at a
true difference of -0.9 points, each repository's own same-change reading, and the break-even margin reading from the pilot.
No model. Usage: python3 -I -B part3.py [confirm_results_dir]   (writes part3.json next to this file)"""
import json
import math
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script directory out
import pinned  # noqa: E402

lab = pinned.load()
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import freeze_pilot_v3 as F  # noqa: E402  imports the hash-checked analyze_topup as F.A

pinned.check_loaded()
A, TASKS = F.A, HERE / "tasks"
MARGIN, ATTEMPTS, FLOOR, Z80, MIN_SIZE, GO_JSON_MEAN = .05, 8, 2.198, 0.8416, 8, -.009
SEED, BOOT = 20261112, 2000


def noise_of(rows, reach, attempts):
    A.TASKS, A.REACH = TASKS, reach
    n = A.tau2(rows)
    tau2 = max([0.0] + [v for v in (n["tau2_moments"], n["tau2_covariance"]) if v is not None])
    return tau2 + n["sigma2"] * 2 / attempts


def required(noise, critical, margin, delta=0.0):
    return noise * ((critical + Z80) / (margin + delta)) ** 2


def bootstrap(rows, reach, critical, margin, attempts, rng):
    tasks, values = sorted(reach), []
    for _ in range(BOOT):
        pick = [rng.choice(tasks) for _ in tasks]
        draw_rows = [{**r, "task": f"{t}#{i}"} for i, t in enumerate(pick) for r in rows if r["task"] == t]
        try:
            values.append(required(noise_of(draw_rows, {f"{t}#{i}": reach[t] for i, t in enumerate(pick)}, attempts), critical, margin))
        except (statistics.StatisticsError, ZeroDivisionError):
            continue
    values.sort()
    return [values[int(.025 * len(values))], values[int(.975 * len(values)) - 1]] if len(values) >= 100 else None


def break_even():
    """docs/lab.md: reference acceptance x the saving share, inputs from the pilot; 2 attempts per arm."""
    rows = [r for r in lab.load_cells(HERE / "results") if r["valid"] is True]
    accepted = statistics.fmean(bool(r["accepted"]) for r in rows if r["arm"] == A.REF)
    saving = A.median_saving(rows, "agent_wall_s", sorted({r["task"] for r in rows}))
    return rows, {"reference_acceptance": accepted, "time_saving": saving, "margin": accepted * saving}


def main():
    reach = json.loads((HERE / "frozen-reach.json").read_text())
    summary = json.loads((HERE / "pilot-summary.json").read_text())
    repo_of = {t["id"]: t["repo"] for t in json.loads((HERE / "pilot-set.json").read_text())["tasks"]}
    repos = sorted({repo_of[t] for t in reach})
    sizes = {repo: sum(repo_of[t] == repo for t in reach) for repo in repos}
    pilot_rows, be = break_even()
    be_noise = noise_of([r for r in pilot_rows if r["task"] in reach], reach, 2)
    out = {"sizes_reaching_tasks": sizes, "pilot_n80_description_only": summary["primary"]["n80_if_equal"],
           "break_even_never_deciding": {**be, "noise_at_2_attempts": be_noise,
                                         "required_at_floor": required(be_noise, FLOOR, be["margin"]) if be["margin"] > 0 else None},
           "repositories": {}}
    confirm = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else None
    if confirm is None:
        out["holds_any"] = False
        out["reason"] = "no finished confirmatory run: nothing holds"
    else:
        rows = [r for r in lab.load_cells(confirm) if r["valid"] is True and r["task"] in reach]
        lab.GATES["draws"] = 100_000
        rng = random.Random(SEED)
        pooled_noise = noise_of(rows, reach, ATTEMPTS)
        for repo in repos:
            own_reach = {t: v for t, v in reach.items() if repo_of[t] == repo}
            own = [r for r in rows if r["task"] in own_reach]
            entry = {"size": sizes[repo], "noise_pooled": pooled_noise}
            try:
                entry["noise_own"] = noise_of(own, own_reach, ATTEMPTS)
            except (statistics.StatisticsError, ZeroDivisionError):
                entry["noise_own"] = None
            noise = max(v for v in (pooled_noise, entry["noise_own"]) if v is not None)
            c = lab.proven_critical(own, TASKS, A.LOW, A.REF, SEED, margin=MARGIN, reach=own_reach, attempts=ATTEMPTS) if own else None
            critical = max(FLOOR, math.inf if c is None else c)
            need = required(noise, critical, MARGIN) if math.isfinite(critical) else None
            interval = lab.paired_interval(lab.reachable_diffs(own, TASKS, A.LOW, A.REF, reach=own_reach))
            entry.update(noise_used=noise, critical_own=c, critical=critical, required=need,
                         holds=sizes[repo] >= MIN_SIZE and need is not None and sizes[repo] >= need,
                         never_deciding={"required_95": bootstrap(own, own_reach, critical, MARGIN, ATTEMPTS, rng) if need is not None else None,
                                         "required_at_go_json_mean": required(noise, critical, MARGIN, GO_JSON_MEAN) if need is not None else None,
                                         "own_reading": {k: interval[k] for k in ("tasks", "mean", "ci95")},
                                         "own_statistic": lab.studentized(lab.reachable_diffs(own, TASKS, A.LOW, A.REF, reach=own_reach), MARGIN)
                                         if interval["tasks"] > 1 else None})
            out["repositories"][repo] = entry
        out["holds_any"] = any(e["holds"] for e in out["repositories"].values())
    (HERE / "part3.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
