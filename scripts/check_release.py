#!/usr/bin/env python3
"""Verify the closed Cernora public tree and distribution artifacts."""

from __future__ import annotations

import argparse
import re
import tarfile
import zipfile
from pathlib import Path

_ALLOWED_ROOT_FILES = frozenset(
    {
        ".gitignore",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "NOTICE",
        "README.md",
        "README.zh-CN.md",
        "ROADMAP.md",
        "ROADMAP.zh-CN.md",
        "SECURITY.md",
        "pyproject.toml",
        "uv.lock",
    }
)
_ALLOWED_ROOT_DIRECTORIES = frozenset({".github", "docs", "examples", "scripts", "src", "tests"})
_IGNORED_GENERATED = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "dist", "__pycache__"}
)
_MAX_PUBLIC_FILE_BYTES = 100_000
_OLD_IMPORT = "_".join(("agent", "evaluator"))
_FORBIDDEN_TEXT = (
    _OLD_IMPORT,
    "/" + "Users" + "/",
    "/" + "home" + "/",
    "\\" + "Users" + "\\",
    "-----BEGIN " + "PRIVATE KEY-----",
)
_FORBIDDEN_PRIVATE_WORD = re.compile(
    rb"(?i)\b(?:"
    + b"|".join(
        value.encode()
        for value in (
            "".join(("ob", "serv")),
            "".join(("ch", "ora")),
            "".join(("ali", "pay")),
            "".join(("ant", "group")),
            "".join(("har", "bor")),
            "".join(("co", "dex")),
        )
    )
    + rb")\b"
)
_SECRET_ASSIGNMENT = re.compile(
    rb"(?i)(?:token|password|secret|api[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{20,}"
)


class ReleaseCheckError(ValueError):
    """The public release tree or an archive is outside the closed policy."""


def _contained(path: str) -> None:
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
    ):
        raise ReleaseCheckError(f"archive member is not a contained POSIX path: {path}")


def _scan_payload(label: str, payload: bytes) -> None:
    if len(payload) > _MAX_PUBLIC_FILE_BYTES:
        raise ReleaseCheckError(f"public file exceeds 100 KB: {label}")
    for marker in _FORBIDDEN_TEXT:
        if marker.encode() in payload:
            raise ReleaseCheckError(f"forbidden private marker in {label}")
    if _FORBIDDEN_PRIVATE_WORD.search(payload):
        raise ReleaseCheckError(f"forbidden private vocabulary in {label}")
    if _SECRET_ASSIGNMENT.search(payload):
        raise ReleaseCheckError(f"credential-like assignment in {label}")


def _tree_files(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in _IGNORED_GENERATED for part in relative.parts):
            continue
        if path.is_symlink():
            raise ReleaseCheckError(f"public tree contains a symlink: {relative.as_posix()}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ReleaseCheckError(f"public tree contains a non-file: {relative.as_posix()}")
        name = relative.as_posix()
        top = relative.parts[0]
        if top not in _ALLOWED_ROOT_FILES and top not in _ALLOWED_ROOT_DIRECTORIES:
            raise ReleaseCheckError(f"public tree member is outside the allowlist: {name}")
        payload = path.read_bytes()
        _scan_payload(name, payload)
        files[name] = payload
    missing = _ALLOWED_ROOT_FILES - files.keys()
    if missing:
        raise ReleaseCheckError(f"public tree is missing root files: {sorted(missing)}")
    return files


def _wheel_files(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ReleaseCheckError("wheel has duplicate members")
        files: dict[str, bytes] = {}
        for name in names:
            if name.endswith("/"):
                raise ReleaseCheckError(f"wheel contains a directory entry: {name}")
            _contained(name)
            if not (name.startswith("cernora/") or name.startswith("cernora-0.1.0.dist-info/")):
                raise ReleaseCheckError(f"wheel member is outside Cernora: {name}")
            payload = archive.read(name)
            _scan_payload(f"wheel:{name}", payload)
            files[name] = payload
    required = {
        "cernora/__init__.py",
        "cernora/conformance.py",
        "cernora/examples/coding_task/__main__.py",
        "cernora/examples/coding_task/resources/candidates/backend-v1.json",
        "cernora/examples/coding_task/resources/candidates/fail-closed-v1.json",
        "cernora/examples/coding_task/resources/candidates/frontend-v1.json",
        "cernora/examples/offline_workflow/__main__.py",
        "cernora-0.1.0.dist-info/METADATA",
        "cernora-0.1.0.dist-info/licenses/LICENSE",
    }
    if not required <= files.keys():
        raise ReleaseCheckError(
            f"wheel is missing required members: {sorted(required - files.keys())}"
        )
    return files


def _sdist_files(path: Path) -> dict[str, bytes]:
    prefix = "cernora-0.1.0/"
    files: dict[str, bytes] = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile() or not member.name.startswith(prefix):
                raise ReleaseCheckError(f"sdist has unsafe member: {member.name}")
            relative = member.name.removeprefix(prefix)
            _contained(relative)
            stream = archive.extractfile(member)
            if stream is None:
                raise ReleaseCheckError(f"sdist member cannot be read: {member.name}")
            payload = stream.read()
            _scan_payload(f"sdist:{relative}", payload)
            if relative in files:
                raise ReleaseCheckError(f"sdist has duplicate member: {relative}")
            files[relative] = payload
    return files


def check_release(tree: Path, wheel: Path, sdist: Path) -> None:
    """Verify tree closure and exact sdist correspondence plus wheel namespace closure."""

    tree_files = _tree_files(tree)
    wheel_files = _wheel_files(wheel)
    sdist_files = _sdist_files(sdist)
    expected_sdist = set(tree_files) | {"PKG-INFO"}
    if set(sdist_files) != expected_sdist:
        raise ReleaseCheckError(
            "sdist member set differs from public tree: "
            f"missing={sorted(expected_sdist - sdist_files.keys())}, "
            f"extra={sorted(sdist_files.keys() - expected_sdist)}"
        )
    for name, payload in tree_files.items():
        if sdist_files[name] != payload:
            raise ReleaseCheckError(f"sdist member differs from public tree: {name}")
    print(
        f"release check passed: tree={len(tree_files)} "
        f"wheel={len(wheel_files)} sdist={len(sdist_files)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    args = parser.parse_args()
    check_release(args.tree, args.wheel, args.sdist)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
