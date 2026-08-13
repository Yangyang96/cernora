"""Preview conformance helpers for public Profile and Adapter authors."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from cernora.adapter import AdaptedBundle, Adapter, CompletedExport
from cernora.core.canonical import canonical_json
from cernora.core.case import CaseProfile
from cernora.core.evidence_bundle_v2 import (
    decode_evidence_bundle_v2,
    verify_artifact_payloads_v2,
)
from cernora.profile import Profile

_MAX_CONFORMANCE_FILE_BYTES = 16_000_000


class ConformanceError(ValueError):
    """A public Profile or Adapter does not satisfy the Preview contract."""


@dataclass(frozen=True)
class ProfileConformance:
    """Validated public identity summary for one Profile."""

    profile_id: str
    profile_version: str
    projection_version: str
    case_ids: tuple[str, ...]


@dataclass(frozen=True)
class AdapterConformance:
    """Validated identity summary for one canonical Adapter output."""

    bundle_id: str
    bundle_sha256: str
    artifact_ids: tuple[str, ...]
    bundle_path: Path


def check_profile_conformance(candidate: object) -> ProfileConformance:
    """Validate the static public Profile contract without evaluating evidence.

    Local Profile Python is trusted code. This helper validates its exposed authority
    and identity; a real import/evaluation remains the behavioral acceptance test.
    """

    if not isinstance(candidate, Profile):
        raise ConformanceError("object does not implement the Cernora Profile contract")
    authority = candidate.authority
    if not isinstance(authority, CaseProfile):
        raise ConformanceError("Profile authority must be a CaseProfile")
    projection_version = candidate.projection_version
    if not isinstance(projection_version, str) or not projection_version:
        raise ConformanceError("Profile projection_version must be a non-empty string")
    case_ids = tuple(case.case_id for case in authority.cases)
    if not case_ids or len(case_ids) != len(set(case_ids)):
        raise ConformanceError("Profile authority must contain uniquely identified Cases")
    try:
        canonical_json(authority)
    except (TypeError, ValueError) as exc:
        raise ConformanceError("Profile authority must have canonical JSON bytes") from exc
    return ProfileConformance(
        profile_id=authority.profile_id,
        profile_version=authority.profile_version,
        projection_version=projection_version,
        case_ids=case_ids,
    )


def _read_ordinary_file(path: Path) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ConformanceError("Adapter output contains an unreadable path") from exc
    if not stat.S_ISREG(before.st_mode):
        raise ConformanceError("Adapter output files must be ordinary files")
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ConformanceError("Adapter output changed while it was inspected")
        if opened.st_size > _MAX_CONFORMANCE_FILE_BYTES:
            raise ConformanceError("Adapter output file exceeds the conformance size limit")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            payload = stream.read(_MAX_CONFORMANCE_FILE_BYTES + 1)
        if len(payload) > _MAX_CONFORMANCE_FILE_BYTES:
            raise ConformanceError("Adapter output file exceeds the conformance size limit")
        return payload
    except OSError as exc:
        raise ConformanceError("Adapter output contains an unreadable path") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _closed_output_files(root: Path) -> dict[str, bytes]:
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise ConformanceError("Adapter output root is missing or unreadable") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise ConformanceError("Adapter output root must be an ordinary directory")
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        try:
            info = path.lstat()
        except OSError as exc:
            raise ConformanceError("Adapter output contains an unreadable path") from exc
        if stat.S_ISLNK(info.st_mode):
            raise ConformanceError("Adapter output must not contain symbolic links")
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ConformanceError("Adapter output must contain only ordinary files")
        relative = path.relative_to(root).as_posix()
        files[relative] = _read_ordinary_file(path)
    return files


def check_adapter_conformance(
    candidate: object,
    completed_export: CompletedExport,
    output: Path,
) -> AdapterConformance:
    """Run one Adapter and verify its closed canonical EvidenceBundle v2 tree.

    The caller supplies a disposable, non-existing output path. Determinism should be
    tested by invoking this helper repeatedly with equivalent completed exports.
    """

    if not isinstance(candidate, Adapter):
        raise ConformanceError("object does not implement the Cernora Adapter contract")
    if output.exists() or output.is_symlink():
        raise ConformanceError("Adapter conformance output must not already exist")
    try:
        result = candidate.adapt(completed_export, output)
    except Exception as exc:
        raise ConformanceError("Adapter rejected the supplied completed export") from exc
    if not isinstance(result, AdaptedBundle):
        raise ConformanceError("Adapter must return a Cernora AdaptedBundle")
    try:
        expected_bundle_path = (output / "bundle.json").resolve(strict=True)
        actual_bundle_path = result.bundle_path.resolve(strict=True)
    except OSError as exc:
        raise ConformanceError("Adapter did not return a readable bundle path") from exc
    if actual_bundle_path != expected_bundle_path:
        raise ConformanceError("Adapter bundle path must be <output>/bundle.json")

    files = _closed_output_files(output)
    bundle_bytes = files.get("bundle.json")
    if bundle_bytes is None:
        raise ConformanceError("Adapter output is missing bundle.json")
    try:
        bundle = decode_evidence_bundle_v2(bundle_bytes)
    except (TypeError, ValueError) as exc:
        raise ConformanceError("Adapter bundle.json is not strict EvidenceBundle v2") from exc
    if bundle_bytes != canonical_json(bundle):
        raise ConformanceError("Adapter bundle.json is not canonical JSON")

    expected_files = {"bundle.json", *(artifact.path for artifact in bundle.artifacts)}
    if set(files) != expected_files:
        raise ConformanceError("Adapter output does not match the Bundle artifact set")
    payloads = {artifact.artifact_id: files[artifact.path] for artifact in bundle.artifacts}
    try:
        verify_artifact_payloads_v2(bundle, payloads)
    except (TypeError, ValueError) as exc:
        raise ConformanceError("Adapter artifact payloads do not match the Bundle") from exc
    if bundle.terminal.answer is not None:
        answer_id = bundle.terminal.answer.artifact.artifact_id
        if payloads[answer_id] != bundle.terminal.answer.content.encode("utf-8"):
            raise ConformanceError("Adapter terminal answer bytes do not match its artifact")

    return AdapterConformance(
        bundle_id=bundle.bundle_id,
        bundle_sha256=bundle.bundle_sha256,
        artifact_ids=tuple(artifact.artifact_id for artifact in bundle.artifacts),
        bundle_path=result.bundle_path,
    )


__all__ = [
    "AdapterConformance",
    "ConformanceError",
    "ProfileConformance",
    "check_adapter_conformance",
    "check_profile_conformance",
]
