"""Public completed-evidence CLI with stable fail-closed exit classes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, NoReturn

from cernora import __version__
from cernora.cli.profiles import BUILTIN_PROFILE_SELECTORS, load_builtin_profile
from cernora.conformance import ConformanceError, check_profile_conformance
from cernora.core.canonical import canonical_json
from cernora.core.errors import ContractError
from cernora.evaluation.package import evaluate_imported_case
from cernora.ingestion.errors import IngestionConfigurationError, IngestionIntegrityError
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profile import Profile
from cernora.profile_loader import ProfileLoadError, load_local_profile
from cernora.profile_workspace import ProfileWorkspaceError, init_profile


class UsageParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"cernora: error: {message}", file=sys.stderr)
        raise SystemExit(2)


def parser() -> argparse.ArgumentParser:
    root = UsageParser(prog="cernora")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = root.add_subparsers(dest="command", required=True)

    profile = commands.add_parser("profile")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    init = profile_commands.add_parser("init")
    init.add_argument("name")
    init.add_argument("--output", type=Path)
    validate = profile_commands.add_parser("validate")
    _add_profile_selector(validate)

    evidence = commands.add_parser("evidence")
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_import = evidence_commands.add_parser("import")
    _add_profile_selector(evidence_import)
    evidence_import.add_argument("--bundle", type=Path, required=True)
    evidence_import.add_argument("--output", type=Path, required=True)
    evidence_evaluate = evidence_commands.add_parser("evaluate")
    _add_profile_selector(evidence_evaluate)
    evidence_evaluate.add_argument("--import-root", type=Path, required=True)
    evidence_evaluate.add_argument("--output", type=Path, required=True)
    return root


def _add_profile_selector(command: argparse.ArgumentParser) -> None:
    selection = command.add_mutually_exclusive_group(required=True)
    selection.add_argument("--profile", choices=BUILTIN_PROFILE_SELECTORS)
    selection.add_argument("--profile-path", type=Path)


def _load_selected_profile(args: argparse.Namespace) -> Profile:
    if args.profile_path is not None:
        return load_local_profile(args.profile_path)
    return load_builtin_profile(args.profile)


def _emit(value: Any) -> None:
    sys.stdout.buffer.write(canonical_json(value) + b"\n")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result: Any
    try:
        if args.command == "profile" and args.profile_command == "init":
            result = init_profile(args.name, output=args.output)
            code = 0
        else:
            profile = _load_selected_profile(args)
        if args.command == "profile" and args.profile_command == "validate":
            check_profile_conformance(profile)
            result = profile.authority
            code = 0
        elif args.command == "evidence" and args.evidence_command == "import":
            result = import_evidence_bundle_v2(
                profile=profile,
                bundle_path=args.bundle,
                output=args.output,
            )
            code = 0
        elif args.command == "evidence":
            result = evaluate_imported_case(
                profile=profile,
                import_root=args.import_root,
                output=args.output,
            )
            code = {"pass": 0, "fail": 1, "inconclusive": 3}[result.case_outcome]
    except (
        ConformanceError,
        IngestionConfigurationError,
        ProfileLoadError,
        ProfileWorkspaceError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except IngestionIntegrityError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (ContractError, OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2 if args.command == "profile" else 3
    except Exception as exc:
        print(f"evaluation failed closed: {type(exc).__name__}", file=sys.stderr)
        return 3
    _emit(result)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
