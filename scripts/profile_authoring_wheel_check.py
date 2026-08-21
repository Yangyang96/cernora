#!/usr/bin/env python3
"""Wheel-only Profile authoring loop acceptance.

Proves that a third party can start from ``cernora profile init``, implement one
deterministic assessment, and reach all three outcome classes plus import rejection
without importing a Cernora source checkout. Run against an installed wheel, not the
repository tree.
"""

from __future__ import annotations

import argparse
import json
import socket
from importlib import metadata
from pathlib import Path
from typing import NoReturn
from unittest.mock import patch

import cernora
from cernora.examples.profile_authoring import write_implemented_profile
from cernora.profile_loader import load_local_profile
from cernora.profile_testing import run_profile_tests
from cernora.profile_workspace import init_profile

_REPETITIONS = 3
_EXPECTED_OUTCOMES = {
    "pass": "pass",
    "fail": "fail",
    "inconclusive": "inconclusive",
    "corrupt-artifact": "import_rejection",
    "authority-mismatch": "import_rejection",
    "scorer-policy-mismatch": "import_rejection",
    "gate-policy-mismatch": "import_rejection",
}


class ProfileAuthoringCheckError(RuntimeError):
    """The wheel-only authoring loop could not prove its declared result."""


def _block_network(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise ProfileAuthoringCheckError("authoring acceptance attempted network access")


def run(output: Path, *, allow_source: bool = False) -> dict[str, object]:
    """Author one scaffold from an installed wheel and prove every outcome class."""

    repository = Path(__file__).resolve().parents[1]
    module_path = Path(cernora.__file__).resolve()
    if module_path.is_relative_to(repository) and not allow_source:
        raise ProfileAuthoringCheckError("Cernora must be imported from an installed wheel")
    if output.exists() or output.is_symlink():
        raise ProfileAuthoringCheckError("authoring acceptance output must not already exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()

    with (
        patch.object(socket, "socket", _block_network),
        patch.object(socket, "create_connection", _block_network),
    ):
        profile_directory = output / "profiles" / "my-profile"
        init_profile("my-profile", output=profile_directory, cwd=output)
        write_implemented_profile(profile_directory)
        profile = load_local_profile(profile_directory)
        summary = run_profile_tests(
            profile,
            profile_directory,
            output / "test-output",
            repetitions=_REPETITIONS,
        )
    if not summary.ok:
        raise ProfileAuthoringCheckError("authored Profile did not pass every declared case")
    outcomes = {row.fixture: row.actual for row in summary.cases}
    if outcomes != _EXPECTED_OUTCOMES:
        raise ProfileAuthoringCheckError(f"authored Profile outcomes mismatch: {outcomes}")
    result: dict[str, object] = {
        "schema_version": "cernora.profile-authoring-wheel-check/v1",
        "cernora_version": metadata.version("cernora"),
        "execution": {
            "credentials_required": False,
            "network_blocked": True,
            "repository_source_import": False,
            "wheel_only": True,
        },
        "repetitions": _REPETITIONS,
        "outcomes": outcomes,
    }
    (output / "summary.json").write_bytes(
        (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
    print("pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
