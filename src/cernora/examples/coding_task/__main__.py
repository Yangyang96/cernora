"""Run one coding example from an installed wheel."""

from __future__ import annotations

import sys
from pathlib import Path

from cernora.examples.coding_task.workflow import run_coding_task


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python -m cernora.examples.coding_task WORKDIR CASE_ID", file=sys.stderr)
        return 2
    print(run_coding_task(Path(sys.argv[1]), sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
