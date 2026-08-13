"""Run the wheel-packaged offline workflow example."""

from __future__ import annotations

import argparse
from pathlib import Path

from cernora.examples.offline_workflow import run_offline_workflow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cernora.examples.offline_workflow")
    parser.add_argument("workdir", type=Path)
    args = parser.parse_args(argv)
    outcome = run_offline_workflow(args.workdir)
    print(outcome)
    return 0 if outcome == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
