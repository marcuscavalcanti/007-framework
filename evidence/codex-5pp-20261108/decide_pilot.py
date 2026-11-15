"""AMENDMENT-5 (d): the pilot's decision after the serial re-grade. No model.
- NO-INSTRUMENT if the serial re-grade disagrees on more than 2% of the valid cells, or if the primary freeze says GO and the freeze
  of the re-graded cells does not.
- Otherwise the primary freeze decides: GO or NO-GO.
Writes pilot-decision.json. Usage: python3 -I -B decide_pilot.py"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIMIT = .02


def main():
    primary = json.loads((HERE / "pilot-summary.json").read_text())["decision"]
    regrade = json.loads((HERE / "serial" / "regrade.json").read_text())
    serial = json.loads((HERE / "serial-freeze" / "pilot-summary.json").read_text())["decision"]
    discordance = regrade["discordance"]
    if discordance is None or discordance > LIMIT or (primary == "GO" and serial != "GO"):
        decision = "NO-INSTRUMENT"
    else:
        decision = primary
    out = {"decision": decision, "primary": primary, "serial": serial, "discordance": discordance, "limit": LIMIT,
           "per_arm": regrade["per_arm"], "unapplied": len(regrade["unapplied"])}
    (HERE / "pilot-decision.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
