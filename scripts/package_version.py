"""Read the source and installed distribution version from SKILL.md."""

from pathlib import Path
import re


def version():
    match = re.search(r"(?m)^  version: (\S+)$", (Path(__file__).resolve().parents[1] / "SKILL.md").read_text())
    return match.group(1) if match else "unknown"
