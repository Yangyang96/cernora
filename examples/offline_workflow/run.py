"""Run after installing the Cernora wheel: python run.py [workdir]."""

from __future__ import annotations

import sys
from pathlib import Path

from cernora.examples.offline_workflow import run_offline_workflow


def main() -> int:
    workdir = Path(sys.argv[1]) if len(sys.argv) == 2 else Path("cernora-offline-example")
    outcome = run_offline_workflow(workdir)
    print(outcome)
    return 0 if outcome == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
