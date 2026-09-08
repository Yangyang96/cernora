"""Strict Adapter for one neutral, already-completed offline workflow export."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cernora.adapter import AdaptedBundle, CompletedExport
from cernora.core.canonical import canonical_json
from cernora.core.evidence_bundle_v2 import EvidenceBundleV2
from cernora.examples import _completed_export as _export
from cernora.profiles.offline_workflow import OfflineWorkflowProfile

_EXPORT_VERSION = "cernora.offline-completed-export/v1"
_EXPECTED_FILES = frozenset({"export.json", "stdout.json", "stderr.txt", "answer.json"})
_EXPORT_KEYS = frozenset(
    {
        "schema_version",
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


class CompletedExportError(ValueError):
    """Completed export is unsafe, malformed, or incompatible."""


def _publish_directory_no_replace(staging: Path, output: Path) -> None:
    _export.publish_directory_no_replace(staging, output, error_type=CompletedExportError)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_object(payload: bytes, *, label: str) -> dict[str, Any]:
    return _export.strict_object(payload, label=label, error_type=CompletedExportError)


def _read_closed_export(root: Path) -> dict[str, bytes]:
    return _export.read_closed_export(
        root,
        expected_files=_EXPECTED_FILES,
        max_file_bytes=_MAX_FILE_BYTES,
        error_type=CompletedExportError,
    )


def _validated_export(files: Mapping[str, bytes]) -> dict[str, Any]:
    metadata = _strict_object(files["export.json"], label="export.json")
    if set(metadata) != _EXPORT_KEYS:
        raise CompletedExportError("export.json has an invalid member set")
    if metadata["schema_version"] != _EXPORT_VERSION:
        raise CompletedExportError("export.json has an unsupported schema version")
    for key in ("producer_id", "run_id", "attempt_id", "invocation_id"):
        if type(metadata[key]) is not str or _IDENTIFIER.fullmatch(metadata[key]) is None:
            raise CompletedExportError(f"export.json has invalid {key}")
    if type(metadata["producer_version"]) is not str or not metadata["producer_version"]:
        raise CompletedExportError("export.json has invalid producer_version")
    if type(metadata["tool"]) is not str or not metadata["tool"]:
        raise CompletedExportError("export.json has invalid tool")
    argv = metadata["argv"]
    if type(argv) is not list or not argv or not all(type(item) is str for item in argv):
        raise CompletedExportError("export.json has invalid argv")
    if (
        metadata["status"] != "completed"
        or type(metadata["exit_code"]) is not int
        or metadata["exit_code"] != 0
        or metadata["committed"] is not True
        or metadata["delivered"] is not True
    ):
        raise CompletedExportError("export.json is not a delivered completed result")

    for name in ("stdout.json", "stderr.txt", "answer.json"):
        try:
            files[name].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CompletedExportError(f"{name} is not strict UTF-8") from exc
    stdout = _strict_object(files["stdout.json"], label="stdout.json")
    if set(stdout) != {"key", "value"} or not all(
        type(stdout[key]) is str for key in ("key", "value")
    ):
        raise CompletedExportError("stdout.json has an invalid lookup result")
    answer = _strict_object(files["answer.json"], label="answer.json")
    if set(answer) != {"claim", "evidence_sha256"} or type(answer["claim"]) is not dict:
        raise CompletedExportError("answer.json has an invalid member set")
    claim = answer["claim"]
    if set(claim) != {"key", "value"} or not all(
        type(claim[key]) is str for key in ("key", "value")
    ):
        raise CompletedExportError("answer.json has an invalid claim")
    if claim != stdout:
        raise CompletedExportError("answer.json claim does not match stdout.json")
    if answer["evidence_sha256"] != _sha256(files["stdout.json"]):
        raise CompletedExportError("answer.json is not bound to stdout.json")
    return metadata


def _artifact(artifact_id: str, path: str, payload: bytes, media_type: str) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "path": path,
        "sha256": _sha256(payload),
        "size_bytes": len(payload),
        "media_type": media_type,
    }


def _build_bundle(files: Mapping[str, bytes], metadata: Mapping[str, Any]) -> EvidenceBundleV2:
    profile = OfflineWorkflowProfile()
    authority = profile.authority
    case = authority.cases[0]
    stdout = files["stdout.json"]
    stderr = files["stderr.txt"]
    answer = files["answer.json"]
    artifacts = (
        _artifact("tool-stdout", "streams/stdout.json", stdout, "application/json"),
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
            "stdout_artifact": {
                "artifact_id": "tool-stdout",
                "sha256": artifacts[0]["sha256"],
            },
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
        "bundle_id": "offline-workflow-example",
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
    _export.write_tree(
        output, files, error_type=CompletedExportError, publish=_publish_directory_no_replace
    )


class OfflineWorkflowAdapter:
    """Convert a closed neutral export into a canonical EvidenceBundle v2 tree."""

    def adapt(self, completed_export: CompletedExport, output: Path) -> AdaptedBundle:
        try:
            source = completed_export.root.resolve(strict=True)
            destination = output.resolve(strict=False)
        except OSError as exc:
            raise CompletedExportError("cannot resolve Adapter paths") from exc
        if destination.is_relative_to(source) or source.is_relative_to(destination):
            raise CompletedExportError("completed export and Adapter output must not overlap")
        files = _read_closed_export(completed_export.root)
        metadata = _validated_export(files)
        bundle = _build_bundle(files, metadata)
        output_files = {
            "bundle.json": canonical_json(bundle),
            "streams/stdout.json": files["stdout.json"],
            "streams/stderr.txt": files["stderr.txt"],
            "terminal/answer.json": files["answer.json"],
        }
        _write_tree(output, output_files)
        return AdaptedBundle(bundle_path=output / "bundle.json")


__all__ = ["CompletedExportError", "OfflineWorkflowAdapter"]
