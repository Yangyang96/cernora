"""Safe project-local workspace for Preview Profile authoring."""

from __future__ import annotations

import ctypes
import errno
import json
import os
import re
import stat
import sys
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Literal

from cernora.core.case import StrictModel

_PROFILE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_IGNORE_BYTES = b"*\n"
_PROFILE_SOURCE = '''"""Cernora Profile scaffold. Local Profile code is trusted, not sandboxed."""

from pathlib import Path

from cernora import (
    AuthorityBoundImportPackageV2,
    CaseProfile,
    Profile,
    ProfileAssessment,
    ProfileEvaluationContext,
)


class ScaffoldProfile:
    """Fail-closed scaffold; implement assess before evaluating completed evidence."""

    projection_version = "scaffold-projection/v1"

    def __init__(self) -> None:
        self._authority = CaseProfile.model_validate_json(
            Path(__file__).with_name("profile.json").read_bytes()
        )

    @property
    def authority(self) -> CaseProfile:
        return self._authority

    def validate_import(self, package: AuthorityBoundImportPackageV2) -> None:
        if package.profile != self._authority:
            raise ValueError("import package is not bound to this Profile authority")
        if package.case not in self._authority.cases:
            raise ValueError("import package Case is not in this Profile")

    def assess(
        self,
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
    ) -> ProfileAssessment:
        del package, context
        raise NotImplementedError("implement Profile.assess before evaluation")


def create_profile() -> Profile:
    """Fixed Cernora local Profile factory."""

    return ScaffoldProfile()
'''


class ProfileWorkspaceError(ValueError):
    """A Profile workspace cannot be created without overwriting or weakening privacy."""


class ProfileInitResult(StrictModel):
    status: Literal["created"]
    profile_name: str
    directory: str
    ignored: bool


def _existing_kind(path: Path) -> str | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if path.is_symlink():
        return "symlink"
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    return f"mode-{info.st_mode}"


def _nearest_git_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if _existing_kind(candidate / ".git") is not None:
            return candidate
    return current


def _ensure_directory(path: Path, *, label: str) -> None:
    kind = _existing_kind(path)
    if kind is None:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProfileWorkspaceError(f"cannot create {label}") from exc
        kind = _existing_kind(path)
    if kind != "directory":
        raise ProfileWorkspaceError(f"{label} must be an ordinary directory")


def _ensure_private_workspace(project_root: Path) -> Path:
    private_root = project_root / ".cernora"
    _ensure_directory(private_root, label="private Profile workspace")
    ignore = private_root / ".gitignore"
    kind = _existing_kind(ignore)
    if kind is None:
        try:
            with ignore.open("xb") as stream:
                stream.write(_IGNORE_BYTES)
        except FileExistsError:
            kind = _existing_kind(ignore)
        except OSError as exc:
            raise ProfileWorkspaceError("cannot create private workspace ignore file") from exc
    if _existing_kind(ignore) != "file":
        raise ProfileWorkspaceError("private workspace ignore entry must be an ordinary file")
    try:
        payload = ignore.read_bytes()
    except OSError as exc:
        raise ProfileWorkspaceError("cannot read private workspace ignore file") from exc
    if payload != _IGNORE_BYTES:
        raise ProfileWorkspaceError("private workspace ignore file must contain exactly '*'")
    profiles = private_root / "profiles"
    _ensure_directory(profiles, label="private Profile directory")
    return profiles


def _authority_payload(name: str) -> bytes:
    value = {
        "cases": [
            {
                "case_id": "example-v1",
                "case_set": "local-authoring",
                "case_version": "1.0.0",
                "declared_capabilities": ["completed-evidence"],
                "fixture_references": [],
                "input": {
                    "parameters": {},
                    "prompt": "Replace this prompt with the completed-evidence task.",
                },
                "tags": ["local"],
            }
        ],
        "description": "Local Cernora Profile scaffold.",
        "gate_policy": {
            "invalid_result": "inconclusive",
            "policy_version": "1.0.0",
            "required_score_ids": ["scaffold-score"],
        },
        "profile_id": name,
        "profile_version": "1.0.0",
        "schema_version": "agent.evaluator.case-profile/v1",
        "scorer_policy": {
            "policy_version": "1.0.0",
            "required_observations": ["implemented"],
        },
    }
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _publish_directory_no_replace(staging: Path, destination: Path) -> None:
    """Atomically publish a directory only when the destination is absent."""

    source = os.fsencode(staging)
    target = os.fsencode(destination)
    ctypes.set_errno(0)
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        try:
            rename = libc.renameat2
        except AttributeError as exc:
            raise ProfileWorkspaceError(
                "atomic no-replace Profile publication is unavailable"
            ) from exc
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(-100, source, -100, target, 1)  # AT_FDCWD, RENAME_NOREPLACE
    elif sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        try:
            rename = libc.renamex_np
        except AttributeError as exc:
            raise ProfileWorkspaceError(
                "atomic no-replace Profile publication is unavailable"
            ) from exc
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(source, target, 0x00000004)  # RENAME_EXCL
    elif os.name == "nt":
        try:
            os.rename(staging, destination)
        except FileExistsError as exc:
            raise ProfileWorkspaceError("Profile destination already exists") from exc
        return
    else:
        raise ProfileWorkspaceError("atomic no-replace Profile publication is unavailable")

    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise ProfileWorkspaceError("Profile destination already exists")
    raise OSError(error_number, os.strerror(error_number), destination)


def _create_scaffold(destination: Path, name: str) -> None:
    if _existing_kind(destination) is not None:
        raise ProfileWorkspaceError("Profile destination already exists")
    _ensure_directory(destination.parent, label="Profile destination parent")
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent)
        )
    except OSError as exc:
        raise ProfileWorkspaceError("cannot create Profile scaffold staging directory") from exc
    directory_descriptor = -1
    created_files: list[str] = []
    published = False
    reserved: os.stat_result | None = None
    try:
        reserved = staging.lstat()
        directory_descriptor = os.open(
            staging,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(directory_descriptor)
        if not stat.S_ISDIR(opened.st_mode) or (reserved.st_dev, reserved.st_ino) != (
            opened.st_dev,
            opened.st_ino,
        ):
            raise ProfileWorkspaceError("Profile destination changed during creation")
        for filename, payload in (
            ("profile.py", _PROFILE_SOURCE.encode("utf-8")),
            ("profile.json", _authority_payload(name)),
        ):
            file_descriptor = os.open(
                filename,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o644,
                dir_fd=directory_descriptor,
            )
            created_files.append(filename)
            with os.fdopen(file_descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
        _publish_directory_no_replace(staging, destination)
        published = True
    except FileExistsError as exc:
        raise ProfileWorkspaceError("Profile scaffold staging changed during creation") from exc
    except OSError as exc:
        raise ProfileWorkspaceError("cannot create Profile scaffold") from exc
    finally:
        if not published and directory_descriptor >= 0:
            # Remove only files reached through our private staging directory descriptor.
            # Never traverse or mutate a destination that appeared concurrently.
            for filename in reversed(created_files):
                with suppress(OSError):
                    os.unlink(filename, dir_fd=directory_descriptor)
        if directory_descriptor >= 0:
            os.close(directory_descriptor)
        if not published:
            # At most remove an empty staging entry; never recurse through any path.
            with suppress(OSError):
                current = staging.lstat()
                if reserved is not None and (current.st_dev, current.st_ino) == (
                    reserved.st_dev,
                    reserved.st_ino,
                ):
                    staging.rmdir()


def init_profile(
    name: str,
    *,
    output: Path | None = None,
    cwd: Path | None = None,
) -> ProfileInitResult:
    """Create one conflict-safe Profile scaffold, private by default."""

    if _PROFILE_NAME.fullmatch(name) is None:
        raise ProfileWorkspaceError(
            "Profile name must start with an alphanumeric and use at most 64 "
            "lowercase alphanumerics, '.', '_' or '-'"
        )
    working = (cwd or Path.cwd()).resolve()
    if _existing_kind(working) != "directory":
        raise ProfileWorkspaceError("current workspace must be an ordinary directory")
    if output is None:
        project_root = _nearest_git_root(working)
        destination = _ensure_private_workspace(project_root) / name
        display = Path(".cernora") / "profiles" / name
        ignored = True
    else:
        destination = output if output.is_absolute() else working / output
        display = output
        ignored = False
    _create_scaffold(destination, name)
    return ProfileInitResult(
        status="created",
        profile_name=name,
        directory=display.as_posix(),
        ignored=ignored,
    )


__all__ = ["ProfileInitResult", "ProfileWorkspaceError", "init_profile"]
