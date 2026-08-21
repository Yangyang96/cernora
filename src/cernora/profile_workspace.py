"""Safe project-local workspace for Preview Profile authoring."""

from __future__ import annotations

import ctypes
import errno
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Literal

from cernora.core.case import StrictModel
from cernora.profile_scaffold import build_scaffold_files

_PROFILE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_IGNORE_BYTES = b"*\n"


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


def _write_scaffold_files(root_descriptor: int, files: Mapping[str, bytes]) -> None:
    """Write every scaffold file below a private staging directory descriptor."""

    for relative, payload in sorted(files.items()):
        parts = PurePosixPath(relative).parts
        current = os.dup(root_descriptor)
        file_descriptor = -1
        try:
            for part in parts[:-1]:
                with suppress(FileExistsError):
                    os.mkdir(part, mode=0o700, dir_fd=current)
                next_descriptor = os.open(
                    part,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=current,
                )
                os.close(current)
                current = next_descriptor
            file_descriptor = os.open(
                parts[-1],
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o644,
                dir_fd=current,
            )
            with os.fdopen(file_descriptor, "wb", closefd=True) as stream:
                file_descriptor = -1
                stream.write(payload)
        finally:
            if file_descriptor >= 0:
                os.close(file_descriptor)
            os.close(current)


def _remove_scaffold_tree(root_descriptor: int) -> None:
    """Recursively remove entries reachable only through a private descriptor."""

    with os.scandir(root_descriptor) as entries:
        for entry in entries:
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(
                    entry.name,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=root_descriptor,
                )
                try:
                    _remove_scaffold_tree(child)
                finally:
                    os.close(child)
                with suppress(OSError):
                    os.rmdir(entry.name, dir_fd=root_descriptor)
            else:
                with suppress(OSError):
                    os.unlink(entry.name, dir_fd=root_descriptor)


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
        _write_scaffold_files(directory_descriptor, build_scaffold_files(name))
        _publish_directory_no_replace(staging, destination)
        published = True
    except FileExistsError as exc:
        raise ProfileWorkspaceError("Profile scaffold staging changed during creation") from exc
    except OSError as exc:
        raise ProfileWorkspaceError("cannot create Profile scaffold") from exc
    finally:
        if not published and directory_descriptor >= 0:
            # Remove only entries reached through our private staging descriptor.
            # Never traverse or mutate a destination that appeared concurrently.
            with suppress(OSError):
                _remove_scaffold_tree(directory_descriptor)
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
