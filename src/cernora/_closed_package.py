"""Internal ordinary-tree and atomic publication helpers for closed packages."""

from __future__ import annotations

import ctypes
import errno
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from cernora.ingestion.errors import IngestionConfigurationError, IngestionIntegrityError


def ordinary_tree_files(root: Path, *, label: str) -> dict[str, bytes]:
    """Read one metadata-stable tree through no-follow, directory-bound descriptors."""

    if os.name == "nt":
        return _ordinary_tree_files_path_bound(root, label=label)
    try:
        root_before = root.lstat()
        descriptor = os.open(
            root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise IngestionIntegrityError(f"cannot inspect {label}") from exc
    try:
        root_opened = os.fstat(descriptor)
        if not stat.S_ISDIR(root_before.st_mode) or not _same_metadata(root_before, root_opened):
            raise IngestionIntegrityError(f"{label} is not one stable ordinary directory")
        files: dict[str, bytes] = {}
        _walk_directory_descriptor(
            descriptor,
            prefix="",
            files=files,
            label=label,
        )
        root_finished = os.fstat(descriptor)
        root_after = root.lstat()
        if not (
            _same_metadata(root_opened, root_finished) and _same_metadata(root_opened, root_after)
        ):
            raise IngestionIntegrityError(f"{label} root changed during snapshot")
        return files
    except IngestionIntegrityError:
        raise
    except OSError as exc:
        raise IngestionIntegrityError(f"cannot snapshot {label}") from exc
    finally:
        os.close(descriptor)


def _metadata(value: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _same_metadata(left: os.stat_result, right: os.stat_result) -> bool:
    return _metadata(left) == _metadata(right)


def _walk_directory_descriptor(
    descriptor: int,
    *,
    prefix: str,
    files: dict[str, bytes],
    label: str,
) -> None:
    directory_opened = os.fstat(descriptor)
    with os.scandir(descriptor) as iterator:
        names = sorted(entry.name for entry in iterator)
    for name in names:
        before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        relative = f"{prefix}/{name}" if prefix else name
        if stat.S_ISDIR(before.st_mode):
            child = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            try:
                opened = os.fstat(child)
                if not stat.S_ISDIR(opened.st_mode) or not _same_metadata(before, opened):
                    raise IngestionIntegrityError(f"{label} directory changed before snapshot")
                _walk_directory_descriptor(
                    child,
                    prefix=relative,
                    files=files,
                    label=label,
                )
                finished = os.fstat(child)
                after = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if not (_same_metadata(opened, finished) and _same_metadata(opened, after)):
                    raise IngestionIntegrityError(f"{label} directory changed during snapshot")
            finally:
                os.close(child)
        elif stat.S_ISREG(before.st_mode):
            files[relative] = _read_file_descriptor(
                descriptor,
                name=name,
                before=before,
                label=label,
            )
        else:
            raise IngestionIntegrityError(f"{label} contains a non-ordinary file or directory")
    directory_finished = os.fstat(descriptor)
    if not _same_metadata(directory_opened, directory_finished):
        raise IngestionIntegrityError(f"{label} directory changed during enumeration")


def _read_file_descriptor(
    directory: int,
    *,
    name: str,
    before: os.stat_result,
    label: str,
) -> bytes:
    descriptor = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=directory,
    )
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or not _same_metadata(before, opened)
        ):
            raise IngestionIntegrityError(f"{label} file changed before snapshot")
        payload = handle.read()
        finished = os.fstat(handle.fileno())
    after = os.stat(name, dir_fd=directory, follow_symlinks=False)
    if not (_same_metadata(opened, finished) and _same_metadata(opened, after)):
        raise IngestionIntegrityError(f"{label} file changed during snapshot")
    return payload


def _ordinary_tree_files_path_bound(root: Path, *, label: str) -> dict[str, bytes]:
    """Windows fallback with descriptor-bound files and full pre/post fingerprints."""

    try:
        root_before = root.lstat()
    except OSError as exc:
        raise IngestionIntegrityError(f"cannot inspect {label}") from exc
    if not stat.S_ISDIR(root_before.st_mode) or root.is_symlink():
        raise IngestionIntegrityError(f"{label} is not an ordinary directory")
    files: dict[str, bytes] = {}
    try:
        for current, directory_names, file_names in os.walk(root, followlinks=False):
            current_path = Path(current)
            for name in directory_names:
                metadata = (current_path / name).lstat()
                if not stat.S_ISDIR(metadata.st_mode):
                    raise IngestionIntegrityError(f"{label} contains a non-ordinary directory")
            for name in file_names:
                candidate = current_path / name
                before = candidate.lstat()
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise IngestionIntegrityError(f"{label} contains a non-ordinary file")
                descriptor = os.open(
                    candidate,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                )
                with os.fdopen(descriptor, "rb") as handle:
                    opened = os.fstat(handle.fileno())
                    if not _same_metadata(before, opened):
                        raise IngestionIntegrityError(f"{label} file changed before snapshot")
                    payload = handle.read()
                    finished = os.fstat(handle.fileno())
                after = candidate.lstat()
                if not (_same_metadata(opened, finished) and _same_metadata(opened, after)):
                    raise IngestionIntegrityError(f"{label} file changed during snapshot")
                files[candidate.relative_to(root).as_posix()] = payload
        root_after = root.lstat()
    except IngestionIntegrityError:
        raise
    except OSError as exc:
        raise IngestionIntegrityError(f"cannot snapshot {label}") from exc
    if not _same_metadata(root_before, root_after):
        raise IngestionIntegrityError(f"{label} root changed during snapshot")
    return files


def publish_closed_package(output: Path, files: Mapping[str, bytes], *, label: str) -> None:
    """Publish one closed file tree atomically without replacing an existing path."""

    if output.exists() or output.is_symlink():
        raise IngestionConfigurationError(f"{label} output must not already exist")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    except OSError as exc:
        raise IngestionConfigurationError(f"cannot create {label} staging directory") from exc
    published = False
    try:
        for relative, payload in sorted(files.items()):
            destination = staging.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        _publish_directory_no_replace(staging, output, label=label)
        published = True
    except IngestionConfigurationError:
        raise
    except OSError as exc:
        raise IngestionConfigurationError(f"cannot atomically publish {label}") from exc
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)


def _publish_directory_no_replace(staging: Path, output: Path, *, label: str) -> None:
    source = os.fsencode(staging)
    target = os.fsencode(output)
    ctypes.set_errno(0)
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        try:
            rename = libc.renameat2
        except AttributeError as exc:
            raise IngestionConfigurationError(
                f"atomic no-replace {label} publication is unavailable"
            ) from exc
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(-100, source, -100, target, 1)
    elif sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        try:
            rename = libc.renamex_np
        except AttributeError as exc:
            raise IngestionConfigurationError(
                f"atomic no-replace {label} publication is unavailable"
            ) from exc
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(source, target, 0x00000004)
    elif os.name == "nt":
        try:
            os.rename(staging, output)
        except FileExistsError as exc:
            raise IngestionConfigurationError(f"{label} output already exists") from exc
        return
    else:
        raise IngestionConfigurationError(f"atomic no-replace {label} publication is unavailable")
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise IngestionConfigurationError(f"{label} output already exists")
    raise OSError(error_number, os.strerror(error_number), output)


__all__ = ["ordinary_tree_files", "publish_closed_package"]
