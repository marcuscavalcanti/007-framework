"""Run the existing CLI from its installed resource layout."""

from pathlib import Path
import sys


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
    from framework_cli import main as cli_main

    return cli_main()
