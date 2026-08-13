"""Materialize and run the wheel-only offline workflow example."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from importlib import resources
from pathlib import Path

from cernora.adapter import CompletedExport
from cernora.evaluation.package import (
    evaluate_imported_case,
    read_imported_evaluation,
)
from cernora.examples.offline_workflow.adapter import (
    CompletedExportError,
    OfflineWorkflowAdapter,
    _publish_directory_no_replace,
)
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profiles.offline_workflow import OfflineWorkflowProfile


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def materialize_completed_export(output: Path) -> CompletedExport:
    """Create the packaged completed export without repository or network access."""

    if output.exists() or output.is_symlink():
        raise CompletedExportError("completed export output must not already exist")
    metadata = resources.files(__package__).joinpath("resources/completed-export.json").read_bytes()
    stdout = (
        resources.files("cernora.profiles.offline_workflow")
        .joinpath("resources/lookup-result.json")
        .read_bytes()
    )
    try:
        claim = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompletedExportError("packaged workflow result is malformed") from exc
    answer = _canonical(
        {
            "claim": claim,
            "evidence_sha256": hashlib.sha256(stdout).hexdigest(),
        }
    )
    files = {
        "export.json": metadata,
        "stdout.json": stdout,
        "stderr.txt": b"",
        "answer.json": answer,
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


def run_offline_workflow(workdir: Path) -> str:
    """Run materialize → adapt → import → evaluate → strict reload; return outcome."""

    profile = OfflineWorkflowProfile()
    completed = materialize_completed_export(workdir / "completed-export")
    adapted = OfflineWorkflowAdapter().adapt(completed, workdir / "bundle")
    imported = workdir / "imported"
    import_evidence_bundle_v2(
        profile=profile,
        bundle_path=adapted.bundle_path,
        output=imported,
    )
    evaluated = workdir / "evaluated"
    receipt = evaluate_imported_case(profile, imported, evaluated)
    reloaded = read_imported_evaluation(evaluated, profile)
    if receipt != reloaded:
        raise CompletedExportError("strictly reloaded evaluation differs from persisted receipt")
    return reloaded.case_outcome


__all__ = ["materialize_completed_export", "run_offline_workflow"]
