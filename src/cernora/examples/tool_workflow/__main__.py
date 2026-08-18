"""Run one wheel-packaged tool-workflow fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

from cernora.examples.tool_workflow.workflow import run_tool_workflow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cernora.examples.tool_workflow")
    parser.add_argument("workdir", type=Path)
    parser.add_argument("fixture_id", nargs="?", default="happy-path")
    args = parser.parse_args(argv)
    outcome = run_tool_workflow(args.workdir, args.fixture_id)
    print(outcome)
    return {"pass": 0, "fail": 1, "inconclusive": 3}[outcome]


if __name__ == "__main__":
    raise SystemExit(main())
