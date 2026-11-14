"""AMENDMENT-5 (a): reference-failed is the union over every run on the pinned code: gate-run1/, gate/ (the re-run used) and the dry
run (dryrun3/reference-failed-dryrun.json). It only adds to reference-failed.json, and logs what it added. No model.
Usage: python3 -I -B reference_union.py"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    current = set(json.loads((HERE / "reference-failed.json").read_text()))
    pooled = {t["id"] for t in json.loads((HERE / "pilot-set.json").read_text())["tasks"]}
    found = set()
    for d in ("gate-run1", "gate"):
        for p in sorted((HERE / d).glob("*.json")) if (HERE / d).is_dir() else []:
            found |= set(json.loads(p.read_text())["reference_failed"])
    dry = HERE / "dryrun3" / "reference-failed-dryrun.json"
    found |= set(json.loads(dry.read_text())) if dry.is_file() else set()
    added = sorted((found & pooled) - current)
    (HERE / "reference-failed.json").write_text(json.dumps(sorted(current | (found & pooled)), indent=1))
    print(json.dumps({"reference_failed": len(current | (found & pooled)), "added": added}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
