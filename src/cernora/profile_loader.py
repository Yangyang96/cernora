"""Explicit trusted local Profile loader with no discovery or registry."""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from pathlib import Path
from types import ModuleType

from cernora.core.case import CaseProfile
from cernora.profile import Profile

_ENTRY_POINT = "profile.py"
_FACTORY = "create_profile"
_MAX_SOURCE_BYTES = 1_000_000


class ProfileLoadError(ValueError):
    """An explicit local Profile cannot be loaded as the Preview contract."""


def _read_entry(directory: Path) -> tuple[Path, bytes]:
    try:
        directory_info = directory.lstat()
    except OSError as exc:
        raise ProfileLoadError("local Profile path is not an ordinary directory") from exc
    if stat.S_ISLNK(directory_info.st_mode) or not stat.S_ISDIR(directory_info.st_mode):
        raise ProfileLoadError("local Profile path is not an ordinary directory")
    entry = directory / _ENTRY_POINT
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(entry, flags)
    except OSError as exc:
        raise ProfileLoadError("local Profile entry point is not an ordinary file") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_SOURCE_BYTES:
            raise ProfileLoadError("local Profile entry point is not an ordinary bounded file")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            return entry, stream.read(_MAX_SOURCE_BYTES + 1)
    except OSError as exc:
        raise ProfileLoadError("cannot read local Profile entry point") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def load_local_profile(directory: Path) -> Profile:
    """Execute one explicit `profile.py:create_profile()` as trusted local Python."""

    entry, source = _read_entry(directory)
    if len(source) > _MAX_SOURCE_BYTES:
        raise ProfileLoadError("local Profile entry point exceeds the size limit")
    identity = hashlib.sha256(str(entry.absolute()).encode() + b"\0" + source).hexdigest()
    module_name = f"_cernora_local_profile_{identity}"
    module = ModuleType(module_name)
    module.__file__ = str(entry)
    module.__package__ = ""
    prior = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        code = compile(source, str(entry), "exec")
        exec(code, module.__dict__)
        factory = module.__dict__.get(_FACTORY)
        if not callable(factory):
            raise ProfileLoadError("local Profile must export callable create_profile()")
        candidate = factory()
    except ProfileLoadError:
        raise
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        raise ProfileLoadError(
            f"local Profile entry point failed closed: {type(exc).__name__}"
        ) from exc
    finally:
        if prior is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = prior
    if not isinstance(candidate, Profile):
        raise ProfileLoadError("create_profile() did not return a Cernora Profile")
    try:
        authority = candidate.authority
        projection_version = candidate.projection_version
    except Exception as exc:
        raise ProfileLoadError("local Profile authority cannot be loaded") from exc
    if not isinstance(authority, CaseProfile) or not isinstance(projection_version, str):
        raise ProfileLoadError("local Profile authority or projection version is invalid")
    if not projection_version:
        raise ProfileLoadError("local Profile projection version must not be empty")
    return candidate


__all__ = ["ProfileLoadError", "load_local_profile"]
