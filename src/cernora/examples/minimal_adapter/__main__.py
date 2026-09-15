"""Materialize synthetic records, or export a completed record for inspection."""

from __future__ import annotations

import argparse
import sys
from importlib import resources
from pathlib import Path

from cernora.core.errors import ContractError
from cernora.examples._completed_export import publish_directory_no_replace, write_tree
from cernora.examples.minimal_adapter import export_record


def _publish(staging: Path, output: Path) -> None:
    publish_directory_no_replace(staging, output, error_type=ValueError)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fixtures = commands.add_parser("fixtures")
    fixtures.add_argument("output", type=Path)
    export = commands.add_parser("export")
    export.add_argument("source", type=Path)
    export.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "fixtures":
            directory = resources.files(__package__).joinpath("resources")
            files = {item.name: item.read_bytes() for item in directory.iterdir() if item.is_file()}
            write_tree(args.output, files, error_type=ValueError, publish=_publish)
        else:
            export_record(args.source, args.output)
    except (ContractError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
