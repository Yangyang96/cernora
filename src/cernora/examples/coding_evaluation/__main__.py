"""Run one wheel-packaged coding-evaluation fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

from cernora.examples.coding_evaluation.workflow import run_coding_evaluation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cernora.examples.coding_evaluation")
    parser.add_argument("workdir", type=Path)
    parser.add_argument("fixture_id", nargs="?", default="happy-path")
    args = parser.parse_args(argv)
    outcome = run_coding_evaluation(args.workdir, args.fixture_id)
    print(outcome)
    return {"pass": 0, "fail": 1, "inconclusive": 3}[outcome]


if __name__ == "__main__":
    raise SystemExit(main())
