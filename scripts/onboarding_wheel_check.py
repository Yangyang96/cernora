#!/usr/bin/env python3
"""Exercise the first-integration tutorial outside the source checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import cernora


def run(output: Path) -> dict[str, object]:
    origin = Path(cernora.__file__).resolve()
    repository = Path(__file__).resolve().parents[1]
    if origin.is_relative_to(repository):
        raise ValueError("onboarding acceptance requires an installed wheel")
    output.mkdir(parents=True, exist_ok=False)

    def command(*args: str, expected: int = 0) -> bytes:
        result = subprocess.run(
            [sys.executable, "-I", *args], cwd=output, capture_output=True, check=False
        )
        if result.returncode != expected:
            raise ValueError(
                f"{args}: expected {expected}, got {result.returncode}: "
                f"{result.stderr.decode(errors='replace')}"
            )
        return result.stdout

    module = "cernora.examples.minimal_adapter"
    command("-m", module, "fixtures", "records")
    outcomes: dict[str, object] = {}
    for name, code in (("success", 0), ("failure", 1), ("missing-evidence", 3)):
        command("-m", module, "export", f"records/{name}.json", f"{name}.json")
        command("-m", module, "export", f"records/{name}.json", f"{name}-repeat.json")
        payload = (output / f"{name}.json").read_bytes()
        if payload != (output / f"{name}-repeat.json").read_bytes():
            raise ValueError("repeated adapter export changed bytes")
        args = (
            "-m",
            "cernora",
            "agent-run",
            "inspect",
            f"{name}.json",
            "--reference",
            "records/reference.json",
        )
        first = command(*args, expected=code)
        if first != command(*args, expected=code):
            raise ValueError("repeated inspection changed bytes")
        (output / f"{name}-inspection.json").write_bytes(first)
        outcomes[name] = {"exit": code, "inspection": json.loads(first)}
    command("-m", module, "export", "records/field-error.json", "invalid.json", expected=3)
    if (output / "invalid.json").exists():
        raise ValueError("invalid source published an export")
    outcomes["field-error"] = {"exit": 3, "export_created": False}

    command("-m", "cernora.examples.offline_workflow", "full-evaluation")
    command(
        "-m",
        "cernora",
        "evidence",
        "import",
        "--profile",
        "builtin:offline-workflow",
        "--bundle",
        "full-evaluation/bundle/bundle.json",
        "--output",
        "imported",
    )
    command(
        "-m",
        "cernora",
        "evidence",
        "evaluate",
        "--profile",
        "builtin:offline-workflow",
        "--import-root",
        "imported",
        "--output",
        "evaluated",
    )
    command(
        "-c",
        "from pathlib import Path; "
        "from cernora import read_imported_evaluation; "
        "from cernora.profiles.offline_workflow import OfflineWorkflowProfile; "
        "assert read_imported_evaluation(Path('evaluated'), OfflineWorkflowProfile())"
        ".case_outcome == 'pass'",
    )
    command("-m", "cernora", "profile", "init", "my-profile")
    command(
        "-c",
        "from pathlib import Path; "
        "from cernora.examples.profile_authoring import write_implemented_profile; "
        "write_implemented_profile(Path('.cernora/profiles/my-profile'))",
    )
    command(
        "-m", "cernora", "profile", "validate", "--profile-path", ".cernora/profiles/my-profile"
    )
    profile_test = command(
        "-m", "cernora", "profile", "test", "--profile-path", ".cernora/profiles/my-profile"
    )
    (output / "profile-test.json").write_bytes(profile_test)
    summary: dict[str, object] = {
        "python": sys.version.split()[0],
        "package_version": cernora.__version__,
        "installed_outside_checkout": True,
        "inspection": outcomes,
        "full_evaluation": "pass",
        "profile_test": json.loads(profile_test),
        "export_sha256": hashlib.sha256((output / "success.json").read_bytes()).hexdigest(),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output.resolve())
    print("pass")
