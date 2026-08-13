"""Strict Adapter for neutral, already-completed coding exports."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from cernora.adapter import AdaptedBundle, CompletedExport
from cernora.core.canonical import canonical_json
from cernora.core.evidence_bundle_v2 import EvidenceBundleV2
from cernora.profiles.coding_task import CodingTaskProfile

_EXPORT_VERSION = "cernora.coding-completed-export/v1"
_EXPECTED_FILES = frozenset({"export.json", "candidate.json", "stderr.txt", "answer.json"})
_EXPORT_KEYS = frozenset(
    {
        "schema_version",
        "case_id",
        "producer_id",
        "producer_version",
        "run_id",
        "attempt_id",
        "invocation_id",
        "tool",
        "argv",
        "status",
        "exit_code",
        "committed",
        "delivered",
    }
)
_IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_MAX_FILE_BYTES = 1_000_000
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_RENAME_EXCL = 4


class CompletedExportError(ValueError):
    """Completed coding export is unsafe, malformed, or incompatible."""


def _publish_directory_no_replace(staging: Path, output: Path) -> None:
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
                raise CompletedExportError("atomic no-replace publication is unavailable") from exc
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
            raise CompletedExportError("atomic no-replace publication is unavailable")
    except OSError as exc:
        if exc.errno in {errno.EEXIST, errno.ENOTEMPTY}:
            raise CompletedExportError("publication destination already exists") from exc
        raise CompletedExportError("cannot atomically publish without replacement") from exc


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_object(payload: bytes, *, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise CompletedExportError(f"{label} has duplicate member {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise CompletedExportError(f"{label} has non-finite number {value}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompletedExportError(f"{label} is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise CompletedExportError(f"{label} must be a JSON object")
    return value


def _candidate_files(payload: bytes) -> dict[str, str]:
    candidate = _strict_object(payload, label="candidate.json")
    if set(candidate) != {"files"} or type(candidate["files"]) is not dict:
        raise CompletedExportError("candidate.json must contain exactly one files object")
    files = candidate["files"]
    if not files:
        raise CompletedExportError("candidate.json files must not be empty")
    for path, content in files.items():
        parsed = PurePosixPath(path)
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or parsed.as_posix() != path
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            raise CompletedExportError("candidate paths must be canonical contained POSIX paths")
        if type(content) is not str:
            raise CompletedExportError("candidate file contents must be strings")
    return files


def _read_closed_export(root: Path) -> dict[str, bytes]:
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise CompletedExportError("cannot inspect completed export root") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise CompletedExportError("completed export root must be an ordinary directory")

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise CompletedExportError("cannot open completed export root") from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (root_info.st_dev, root_info.st_ino):
            raise CompletedExportError("completed export root changed during validation")
        entries: dict[str, tuple[int, int]] = {}
        try:
            with os.scandir(descriptor) as scan:
                for entry in scan:
                    info = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        raise CompletedExportError("completed export contains a non-ordinary entry")
                    entries[entry.name] = (info.st_dev, info.st_ino)
        except OSError as exc:
            raise CompletedExportError("cannot scan completed export") from exc
        if set(entries) != _EXPECTED_FILES:
            raise CompletedExportError("completed export does not match its closed file set")
        if len(set(entries.values())) != len(entries):
            raise CompletedExportError("completed export files must have distinct identities")

        result: dict[str, bytes] = {}
        for name in sorted(_EXPECTED_FILES):
            file_descriptor = -1
            try:
                file_descriptor = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
                    dir_fd=descriptor,
                )
                info = os.fstat(file_descriptor)
                if not stat.S_ISREG(info.st_mode) or entries[name] != (info.st_dev, info.st_ino):
                    raise CompletedExportError("completed export file changed during validation")
                if info.st_size > _MAX_FILE_BYTES:
                    raise CompletedExportError("completed export file exceeds size limit")
                with os.fdopen(file_descriptor, "rb", closefd=True) as stream:
                    file_descriptor = -1
                    result[name] = stream.read(_MAX_FILE_BYTES + 1)
                if len(result[name]) > _MAX_FILE_BYTES:
                    raise CompletedExportError("completed export file exceeds size limit")
            except OSError as exc:
                raise CompletedExportError("cannot read completed export file") from exc
            finally:
                if file_descriptor >= 0:
                    os.close(file_descriptor)

        final_entries: dict[str, tuple[int, int]] = {}
        try:
            with os.scandir(descriptor) as scan:
                for entry in scan:
                    info = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        raise CompletedExportError("completed export contains a non-ordinary entry")
                    final_entries[entry.name] = (info.st_dev, info.st_ino)
        except OSError as exc:
            raise CompletedExportError("cannot rescan completed export") from exc
        if final_entries != entries:
            raise CompletedExportError("completed export changed during reads")
        return result
    finally:
        os.close(descriptor)


def _validated_export(
    files: Mapping[str, bytes], profile: CodingTaskProfile
) -> tuple[dict[str, Any], Any]:
    metadata = _strict_object(files["export.json"], label="export.json")
    if set(metadata) != _EXPORT_KEYS:
        raise CompletedExportError("export.json has an invalid member set")
    if metadata["schema_version"] != _EXPORT_VERSION:
        raise CompletedExportError("export.json has an unsupported schema version")
    for key in ("case_id", "producer_id", "run_id", "attempt_id", "invocation_id"):
        if type(metadata[key]) is not str or _IDENTIFIER.fullmatch(metadata[key]) is None:
            raise CompletedExportError(f"export.json has invalid {key}")
    matches = tuple(case for case in profile.authority.cases if case.case_id == metadata["case_id"])
    if len(matches) != 1:
        raise CompletedExportError("export.json case_id is not an exact packaged Case")
    if type(metadata["producer_version"]) is not str or not metadata["producer_version"]:
        raise CompletedExportError("export.json has invalid producer_version")
    if metadata["tool"] != "export_candidate" or metadata["argv"] != ["export_candidate"]:
        raise CompletedExportError("export.json has invalid export command")
    if (
        metadata["status"] != "completed"
        or type(metadata["exit_code"]) is not int
        or metadata["exit_code"] != 0
        or metadata["committed"] is not True
        or metadata["delivered"] is not True
    ):
        raise CompletedExportError("export.json is not a delivered completed result")

    _candidate_files(files["candidate.json"])
    try:
        files["stderr.txt"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CompletedExportError("stderr.txt is not strict UTF-8") from exc
    answer = _strict_object(files["answer.json"], label="answer.json")
    if set(answer) != {"candidate_sha256"}:
        raise CompletedExportError("answer.json has an invalid member set")
    if answer["candidate_sha256"] != _sha256(files["candidate.json"]):
        raise CompletedExportError("answer.json is not bound to candidate.json")
    return metadata, matches[0]


def _artifact(artifact_id: str, path: str, payload: bytes, media_type: str) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "path": path,
        "sha256": _sha256(payload),
        "size_bytes": len(payload),
        "media_type": media_type,
    }


def _build_bundle(
    files: Mapping[str, bytes], metadata: Mapping[str, Any], profile: CodingTaskProfile, case: Any
) -> EvidenceBundleV2:
    authority = profile.authority
    candidate = files["candidate.json"]
    stderr = files["stderr.txt"]
    answer = files["answer.json"]
    artifacts = (
        _artifact("candidate", "candidate/candidate.json", candidate, "application/json"),
        _artifact("tool-stderr", "streams/stderr.txt", stderr, "text/plain; charset=utf-8"),
        _artifact("terminal-answer", "terminal/answer.json", answer, "application/json"),
    )
    action: dict[str, Any] = {
        "sequence": 0,
        "invocation_id": metadata["invocation_id"],
        "tool": metadata["tool"],
        "argv": tuple(metadata["argv"]),
        "result": {
            "status": metadata["status"],
            "exit_code": metadata["exit_code"],
            "committed": metadata["committed"],
            "delivered": metadata["delivered"],
            "stdout_artifact": {"artifact_id": "candidate", "sha256": artifacts[0]["sha256"]},
            "stderr_artifact": {
                "artifact_id": "tool-stderr",
                "sha256": artifacts[1]["sha256"],
            },
        },
        "previous_receipt_sha256": None,
    }
    action["receipt_sha256"] = _sha256(canonical_json(action))
    payload: dict[str, Any] = {
        "schema_version": "agent.evaluator.evidence-bundle/v2",
        "bundle_id": f"coding-task-example-{case.case_id}",
        "producer": {
            "producer_id": metadata["producer_id"],
            "producer_version": metadata["producer_version"],
        },
        "run": {"run_id": metadata["run_id"], "attempt_id": metadata["attempt_id"]},
        "profile": {
            "profile_id": authority.profile_id,
            "profile_version": authority.profile_version,
            "sha256": _sha256(canonical_json(authority)),
        },
        "case": {
            "case_id": case.case_id,
            "case_version": case.case_version,
            "case_set": case.case_set,
            "sha256": _sha256(canonical_json(case)),
        },
        "fixtures": tuple(item.model_dump(mode="json") for item in case.fixture_references),
        "tool_actions": (action,),
        "artifacts": artifacts,
        "terminal": {
            "status": "completed",
            "answer": {
                "content": answer.decode("utf-8"),
                "sha256": artifacts[2]["sha256"],
                "artifact": {
                    "artifact_id": "terminal-answer",
                    "sha256": artifacts[2]["sha256"],
                },
            },
            "failure": None,
        },
        "infrastructure": {"status": "valid", "failure": None},
    }
    payload["bundle_sha256"] = _sha256(canonical_json(payload))
    return EvidenceBundleV2.model_validate(payload)


def _write_tree(output: Path, files: Mapping[str, bytes]) -> None:
    if output.exists() or output.is_symlink():
        raise CompletedExportError("Adapter output must not already exist")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    except OSError as exc:
        raise CompletedExportError("cannot create Adapter staging directory") from exc
    published = False
    try:
        for relative, payload in sorted(files.items()):
            destination = staging.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        if output.exists() or output.is_symlink():
            raise CompletedExportError("Adapter output appeared before publication")
        _publish_directory_no_replace(staging, output)
        published = True
    except CompletedExportError:
        raise
    except OSError as exc:
        raise CompletedExportError("cannot atomically publish adapted Bundle") from exc
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)


class CodingTaskAdapter:
    """Convert one closed coding export into canonical EvidenceBundle v2."""

    def adapt(self, completed_export: CompletedExport, output: Path) -> AdaptedBundle:
        try:
            source = completed_export.root.resolve(strict=True)
            destination = output.resolve(strict=False)
        except OSError as exc:
            raise CompletedExportError("cannot resolve Adapter paths") from exc
        if destination.is_relative_to(source) or source.is_relative_to(destination):
            raise CompletedExportError("completed export and Adapter output must not overlap")
        files = _read_closed_export(completed_export.root)
        profile = CodingTaskProfile()
        metadata, case = _validated_export(files, profile)
        bundle = _build_bundle(files, metadata, profile, case)
        output_files = {
            "bundle.json": canonical_json(bundle),
            "candidate/candidate.json": files["candidate.json"],
            "streams/stderr.txt": files["stderr.txt"],
            "terminal/answer.json": files["answer.json"],
        }
        _write_tree(output, output_files)
        return AdaptedBundle(bundle_path=output / "bundle.json")


__all__ = ["CodingTaskAdapter", "CompletedExportError"]
