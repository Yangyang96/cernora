"""Internal file operations shared by the completed-export examples."""

from __future__ import annotations

import ctypes
import errno
import json
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_RENAME_EXCL = 4


def publish_directory_no_replace(
    staging: Path, output: Path, *, error_type: type[ValueError]
) -> None:
    """Atomically publish staging without replacing any destination."""

    source_bytes = os.fsencode(staging)
    output_bytes = os.fsencode(output)
    try:
        if sys.platform == "darwin":
            libc = ctypes.CDLL(None, use_errno=True)
            renamex_np = libc.renamex_np
            renamex_np.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
            renamex_np.restype = ctypes.c_int
            if renamex_np(source_bytes, output_bytes, _RENAME_EXCL) != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), output)
        elif sys.platform.startswith("linux"):
            libc = ctypes.CDLL(None, use_errno=True)
            try:
                renameat2 = libc.renameat2
            except AttributeError as exc:
                raise error_type("atomic no-replace publication is unavailable") from exc
            renameat2.argtypes = (
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            )
            renameat2.restype = ctypes.c_int
            if (
                renameat2(
                    _AT_FDCWD,
                    source_bytes,
                    _AT_FDCWD,
                    output_bytes,
                    _RENAME_NOREPLACE,
                )
                != 0
            ):
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), output)
        elif sys.platform == "win32":
            os.rename(staging, output)
        else:
            raise error_type("atomic no-replace publication is unavailable")
    except OSError as exc:
        if exc.errno in {errno.EEXIST, errno.ENOTEMPTY}:
            raise error_type("publication destination already exists") from exc
        raise error_type("cannot atomically publish without replacement") from exc


def strict_object(payload: bytes, *, label: str, error_type: type[ValueError]) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise error_type(f"{label} has duplicate member {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise error_type(f"{label} has non-finite number {value}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise error_type(f"{label} is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise error_type(f"{label} must be a JSON object")
    return value


def read_closed_export(
    root: Path,
    *,
    expected_files: frozenset[str],
    max_file_bytes: int,
    error_type: type[ValueError],
) -> dict[str, bytes]:
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise error_type("cannot inspect completed export root") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise error_type("completed export root must be an ordinary directory")

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise error_type("cannot open completed export root") from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (root_info.st_dev, root_info.st_ino):
            raise error_type("completed export root changed during validation")
        entries: dict[str, tuple[int, int]] = {}
        try:
            with os.scandir(descriptor) as scan:
                for entry in scan:
                    info = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        raise error_type("completed export contains a non-ordinary entry")
                    entries[entry.name] = (info.st_dev, info.st_ino)
        except OSError as exc:
            raise error_type("cannot scan completed export") from exc
        if set(entries) != expected_files:
            raise error_type("completed export does not match its closed file set")
        if len(set(entries.values())) != len(entries):
            raise error_type("completed export files must have distinct identities")

        result: dict[str, bytes] = {}
        for name in sorted(expected_files):
            file_descriptor = -1
            try:
                file_descriptor = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
                    dir_fd=descriptor,
                )
                info = os.fstat(file_descriptor)
                if not stat.S_ISREG(info.st_mode) or entries[name] != (info.st_dev, info.st_ino):
                    raise error_type("completed export file changed during validation")
                if info.st_size > max_file_bytes:
                    raise error_type("completed export file exceeds size limit")
                with os.fdopen(file_descriptor, "rb", closefd=True) as stream:
                    file_descriptor = -1
                    result[name] = stream.read(max_file_bytes + 1)
                if len(result[name]) > max_file_bytes:
                    raise error_type("completed export file exceeds size limit")
            except OSError as exc:
                raise error_type("cannot read completed export file") from exc
            finally:
                if file_descriptor >= 0:
                    os.close(file_descriptor)
        final_entries: dict[str, tuple[int, int]] = {}
        try:
            with os.scandir(descriptor) as scan:
                for entry in scan:
                    info = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        raise error_type("completed export contains a non-ordinary entry")
                    final_entries[entry.name] = (info.st_dev, info.st_ino)
        except OSError as exc:
            raise error_type("cannot rescan completed export") from exc
        if final_entries != entries:
            raise error_type("completed export changed during reads")
        return result
    finally:
        os.close(descriptor)


def write_tree(
    output: Path,
    files: Mapping[str, bytes],
    *,
    error_type: type[ValueError],
    publish: Callable[[Path, Path], None],
) -> None:
    if output.exists() or output.is_symlink():
        raise error_type("Adapter output must not already exist")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    except OSError as exc:
        raise error_type("cannot create Adapter staging directory") from exc
    published = False
    try:
        for relative, payload in sorted(files.items()):
            destination = staging.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        if output.exists() or output.is_symlink():
            raise error_type("Adapter output appeared before publication")
        publish(staging, output)
        published = True
    except error_type:
        raise
    except OSError as exc:
        raise error_type("cannot atomically publish adapted Bundle") from exc
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)
