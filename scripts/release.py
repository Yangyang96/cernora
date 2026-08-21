#!/usr/bin/env python3
"""Run Cernora's repeatable pre-release and post-release checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_release import (  # noqa: E402
    ReleaseCheckError,
    artifact_paths,
    check_artifacts,
    check_release,
    project_version,
)


class ReleaseCommandError(RuntimeError):
    """A release command could not prove its required condition."""


def _run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> str:
    print(f"+ {shlex.join(command)}", flush=True)
    completed = subprocess.run(
        command,
        check=True,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
    )
    if capture and completed.stdout:
        print(completed.stdout, end="")
    return completed.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_release_metadata(version: str, root: Path = ROOT) -> None:
    source = (root / "src/cernora/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', source, flags=re.MULTILINE)
    if match is None or match.group(1) != version:
        raise ReleaseCommandError("pyproject.toml and cernora.__version__ disagree")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = re.search(
        r"^## Unreleased\s*(.*?)(?=^## |\Z)", changelog, flags=re.MULTILINE | re.DOTALL
    )
    if unreleased is not None and unreleased.group(1).strip():
        raise ReleaseCommandError("CHANGELOG.md still has content under Unreleased")
    heading = rf"^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$"
    if re.search(heading, changelog, flags=re.MULTILINE) is None:
        raise ReleaseCommandError(
            f"CHANGELOG.md has no dated release heading for version {version}"
        )


def _verify_built_profile_authoring(wheel: Path, root: Path) -> None:
    """Install one freshly built wheel offline and run the Profile authoring acceptance."""

    venv = root / "authoring-venv"
    _run(["uv", "venv", str(venv), "--python", sys.executable], cwd=root)
    python = _venv_python(venv)
    _run(
        ["uv", "pip", "install", "--python", str(python), "--offline", str(wheel)],
        cwd=root,
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    _run(
        [
            str(python),
            "-I",
            str(ROOT / "scripts/profile_authoring_wheel_check.py"),
            "--output",
            str(root / "authoring-acceptance"),
        ],
        cwd=root,
        env=environment,
    )


def preflight() -> int:
    """Run all local release gates and inspect a fresh temporary build."""

    version = project_version(ROOT)
    _validate_release_metadata(version)
    commands = [
        ["uv", "run", "pytest", "-q"],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "mypy"],
        ["git", "diff", "--check"],
    ]
    for command in commands:
        _run(command)

    with tempfile.TemporaryDirectory(prefix="cernora-preflight-") as temporary:
        temporary_root = Path(temporary)
        dist = temporary_root / "dist"
        _run(["uv", "run", "python", "-m", "build", "--outdir", str(dist)])
        wheel, sdist = artifact_paths(dist, version)
        check_release(ROOT, wheel, sdist)
        _verify_built_profile_authoring(wheel, temporary_root)
        summary = {
            "sdist": {"name": sdist.name, "sha256": _sha256(sdist)},
            "version": version,
            "wheel": {"name": wheel.name, "sha256": _sha256(wheel)},
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _json_document(url: str) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ReleaseCommandError("release verification requires an HTTPS JSON endpoint")
    request = urllib.request.Request(url, headers={"User-Agent": "cernora-release-verifier"})
    with urllib.request.urlopen(request, timeout=30) as response:
        document = json.load(response)
    if not isinstance(document, dict):
        raise ReleaseCommandError("package-index JSON response is not an object")
    return document


def _download(url: str, destination: Path) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ReleaseCommandError("release artifacts must use HTTPS URLs")
    request = urllib.request.Request(url, headers={"User-Agent": "cernora-release-verifier"})
    with (
        urllib.request.urlopen(request, timeout=60) as response,
        destination.open("wb") as output,
    ):
        shutil.copyfileobj(response, output)


def _pypi_files(version: str, destination: Path, json_url: str) -> tuple[Path, Path]:
    document = _json_document(json_url)
    info = document.get("info")
    if not isinstance(info, dict) or info.get("version") != version:
        raise ReleaseCommandError("package-index JSON reports a different version")
    urls = document.get("urls")
    if not isinstance(urls, list):
        raise ReleaseCommandError("package-index JSON has no artifact list")

    expected_wheel, expected_sdist = artifact_paths(destination, version)
    expected_names = {expected_wheel.name, expected_sdist.name}
    records: dict[str, dict[str, Any]] = {}
    for value in urls:
        if not isinstance(value, dict) or not isinstance(value.get("filename"), str):
            raise ReleaseCommandError("package-index JSON contains an invalid artifact record")
        records[value["filename"]] = value
    if set(records) != expected_names:
        raise ReleaseCommandError(
            f"published artifact set differs: expected={sorted(expected_names)} "
            f"actual={sorted(records)}"
        )

    for path in (expected_wheel, expected_sdist):
        record = records[path.name]
        url = record.get("url")
        digests = record.get("digests")
        expected_digest = digests.get("sha256") if isinstance(digests, dict) else None
        if not isinstance(url, str) or not isinstance(expected_digest, str):
            raise ReleaseCommandError(f"published artifact metadata is incomplete: {path.name}")
        _download(url, path)
        actual_digest = _sha256(path)
        if actual_digest != expected_digest:
            raise ReleaseCommandError(f"downloaded artifact digest differs: {path.name}")
        print(f"verified download: {path.name} sha256={actual_digest}")
    return expected_wheel, expected_sdist


def _venv_python(venv: Path) -> Path:
    windows = venv / "Scripts/python.exe"
    return windows if windows.is_file() else venv / "bin/python"


def _tree_digest(root: Path) -> str:
    manifest = [
        {"path": path.relative_to(root).as_posix(), "sha256": _sha256(path)}
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]
    payload = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _verify_installed(version: str, interpreter: str, index_url: str, root: Path) -> str:
    expected_match = re.search(r"(?<!\d)3\.(12|13)(?!\d)", interpreter)
    if expected_match is None:
        raise ReleaseCommandError("each --python value must identify Python 3.12 or 3.13")
    expected_python = [3, int(expected_match.group(1))]
    executable = shutil.which(interpreter)
    if executable is None:
        discovered = _run(["uv", "python", "find", interpreter], capture=True).strip().splitlines()
        if not discovered or not Path(discovered[-1]).is_file():
            raise ReleaseCommandError(f"required Python interpreter is unavailable: {interpreter}")
        executable = discovered[-1]
    venv = root / f"venv-{interpreter.replace('/', '_')}"
    _run([executable, "-m", "venv", str(venv)], cwd=root)
    python = _venv_python(venv)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--isolated",
            "--no-cache-dir",
            "--only-binary=:all:",
            "--index-url",
            index_url,
            f"cernora=={version}",
        ],
        cwd=root,
        env=environment,
    )
    _run([str(python), "-m", "pip", "check"], cwd=root, env=environment)
    probe = _run(
        [
            str(python),
            "-I",
            "-c",
            (
                "import cernora,json,pathlib,sys;"
                "print(json.dumps({'origin':str(pathlib.Path(cernora.__file__).resolve()),"
                "'python':list(sys.version_info[:2]),'version':cernora.__version__},sort_keys=True))"
            ),
        ],
        cwd=root,
        env=environment,
        capture=True,
    )
    identity = json.loads(probe.strip().splitlines()[-1])
    origin = Path(identity["origin"])
    if (
        identity["version"] != version
        or identity["python"] != expected_python
        or not origin.is_relative_to(venv.resolve())
    ):
        raise ReleaseCommandError(f"installed package identity is invalid for {interpreter}")

    output = root / f"acceptance-{interpreter.replace('/', '_')}"
    _run(
        [
            str(python),
            "-I",
            str(ROOT / "scripts/rebuild_acceptance.py"),
            "--output",
            str(output),
        ],
        cwd=root,
        env=environment,
    )
    authoring_output = root / f"authoring-{interpreter.replace('/', '_')}"
    _run(
        [
            str(python),
            "-I",
            str(ROOT / "scripts/profile_authoring_wheel_check.py"),
            "--output",
            str(authoring_output),
        ],
        cwd=root,
        env=environment,
    )
    digest = _tree_digest(output)
    print(f"verified installed flows: {interpreter} manifest_sha256={digest}")
    return digest


def verify(version: str, interpreters: list[str], index_url: str, json_url: str) -> int:
    """Verify exact production artifacts and installed README-equivalent flows."""

    current_version = project_version(ROOT)
    if version != current_version:
        raise ReleaseCommandError(
            f"checkout version {current_version} does not match requested release {version}"
        )
    _validate_release_metadata(version)
    requested_minors = [
        re.search(r"(?<!\d)3\.(12|13)(?!\d)", interpreter) for interpreter in interpreters
    ]
    if len(interpreters) != 2 or any(match is None for match in requested_minors):
        raise ReleaseCommandError("verification requires exactly Python 3.12 and 3.13")
    if {int(match.group(1)) for match in requested_minors if match is not None} != {12, 13}:
        raise ReleaseCommandError("verification requires one Python 3.12 and one Python 3.13")
    with tempfile.TemporaryDirectory(prefix="cernora-post-release-") as temporary:
        root = Path(temporary)
        artifacts = root / "artifacts"
        artifacts.mkdir()
        wheel, sdist = _pypi_files(version, artifacts, json_url)
        check_artifacts(wheel, sdist, version)
        manifests = {
            interpreter: _verify_installed(version, interpreter, index_url, root)
            for interpreter in interpreters
        }
        if len(set(manifests.values())) != 1:
            raise ReleaseCommandError("supported Python versions produced different results")
        print(
            json.dumps(
                {
                    "installed_flow_manifests": manifests,
                    "sdist_sha256": _sha256(sdist),
                    "version": version,
                    "wheel_sha256": _sha256(wheel),
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight", help="run all local release gates and inspect a fresh build")
    verify_parser = subparsers.add_parser(
        "verify", help="verify a production-PyPI release in clean Python environments"
    )
    verify_parser.add_argument("--version", default=project_version(ROOT))
    verify_parser.add_argument("--python", action="append", dest="interpreters")
    verify_parser.add_argument("--index-url", default="https://pypi.org/simple")
    verify_parser.add_argument("--json-url")
    args = parser.parse_args()

    try:
        if args.command == "preflight":
            return preflight()
        interpreters = args.interpreters or ["python3.12", "python3.13"]
        json_url = args.json_url or f"https://pypi.org/pypi/cernora/{args.version}/json"
        return verify(args.version, interpreters, args.index_url, json_url)
    except (OSError, ReleaseCheckError, ReleaseCommandError, subprocess.CalledProcessError) as exc:
        print(f"release command failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
