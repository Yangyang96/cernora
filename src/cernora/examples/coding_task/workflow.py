"""Materialize and run wheel-only coding task examples."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from importlib import resources
from pathlib import Path

from cernora.adapter import CompletedExport
from cernora.evaluation.package import evaluate_imported_case, read_imported_evaluation
from cernora.examples.coding_task.adapter import (
    CodingTaskAdapter,
    CompletedExportError,
    _publish_directory_no_replace,
)
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profiles.coding_task import CodingTaskProfile


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def materialize_completed_export(output: Path, case_id: str) -> CompletedExport:
    """Create one packaged coding export without repository or network access."""

    profile = CodingTaskProfile()
    if sum(case.case_id == case_id for case in profile.authority.cases) != 1:
        raise CompletedExportError("case id is not an exact packaged Coding Profile Case")
    if output.exists() or output.is_symlink():
        raise CompletedExportError("completed export output must not already exist")
    try:
        candidate_resource = (
            resources.files(__package__)
            .joinpath(f"resources/candidates/{case_id}.json")
            .read_bytes()
        )
    except (FileNotFoundError, OSError) as exc:
        raise CompletedExportError("packaged coding candidate is unavailable") from exc
    try:
        candidate = _canonical(json.loads(candidate_resource))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompletedExportError("packaged coding candidate is malformed") from exc
    metadata = _canonical(
        {
            "schema_version": "cernora.coding-completed-export/v1",
            "case_id": case_id,
            "producer_id": "cernora-coding-example",
            "producer_version": "1.0.0",
            "run_id": f"coding-example-{case_id}",
            "attempt_id": "attempt-1",
            "invocation_id": "export-1",
            "tool": "export_candidate",
            "argv": ["export_candidate"],
            "status": "completed",
            "exit_code": 0,
            "committed": True,
            "delivered": True,
        }
    )
    files = {
        "export.json": metadata,
        "candidate.json": candidate,
        "stderr.txt": b"",
        "answer.json": _canonical({"candidate_sha256": hashlib.sha256(candidate).hexdigest()}),
    }
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    except OSError as exc:
        raise CompletedExportError("cannot create completed export staging directory") from exc
    published = False
    try:
        for name, payload in sorted(files.items()):
            (staging / name).write_bytes(payload)
        if output.exists() or output.is_symlink():
            raise CompletedExportError("completed export output appeared before publication")
        _publish_directory_no_replace(staging, output)
        published = True
    except CompletedExportError:
        raise
    except OSError as exc:
        raise CompletedExportError("cannot publish completed export") from exc
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)
    return CompletedExport(root=output)


def run_coding_task(workdir: Path, case_id: str) -> str:
    """Run materialize → adapt → import → evaluate → strict reload."""

    profile = CodingTaskProfile()
    completed = materialize_completed_export(workdir / "completed-export", case_id)
    adapted = CodingTaskAdapter().adapt(completed, workdir / "bundle")
    imported = workdir / "imported"
    import_evidence_bundle_v2(profile=profile, bundle_path=adapted.bundle_path, output=imported)
    evaluated = workdir / "evaluated"
    receipt = evaluate_imported_case(profile, imported, evaluated)
    reloaded = read_imported_evaluation(evaluated, profile)
    if receipt != reloaded:
        raise CompletedExportError("strictly reloaded evaluation differs from persisted receipt")
    return reloaded.case_outcome


__all__ = ["materialize_completed_export", "run_coding_task"]
