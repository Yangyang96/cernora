#!/usr/bin/env python3
"""Rebuild sanitized V1/V2 representative acceptance from an installed wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import socket
from collections.abc import Callable
from importlib import metadata
from pathlib import Path
from typing import NoReturn
from unittest.mock import patch

import cernora
from cernora.core.errors import ContractError
from cernora.evaluation.package import evaluate_imported_case, read_imported_evaluation
from cernora.examples.coding_task import (
    CodingTaskAdapter,
    CompletedExportError,
    materialize_completed_export,
    run_coding_task,
)
from cernora.examples.offline_workflow import run_offline_workflow
from cernora.ingestion.errors import (
    AuthorityIncompatibleError,
    IngestionConfigurationError,
    IngestionIntegrityError,
)
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profiles.coding_task import CodingTaskProfile
from cernora.profiles.offline_workflow import OfflineWorkflowProfile

_CODING_CASES = ("backend-v1", "frontend-v1", "fail-closed-v1")
_REPETITIONS = 3
_EXPECTED_REJECTION = (
    AuthorityIncompatibleError,
    ContractError,
    IngestionConfigurationError,
    IngestionIntegrityError,
)


class AcceptanceError(RuntimeError):
    """Public acceptance could not prove its declared result."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise AcceptanceError("acceptance output contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise AcceptanceError("acceptance output contains a non-file")
        files.append(path)
    for path in sorted(files):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _same_digest(runs: list[Path]) -> str:
    digests = {_tree_digest(run) for run in runs}
    if len(digests) != 1:
        raise AcceptanceError("repeated acceptance outputs are not byte deterministic")
    return digests.pop()


def _rewrite_coding_answer(root: Path) -> None:
    candidate = (root / "candidate.json").read_bytes()
    (root / "answer.json").write_bytes(
        _canonical({"candidate_sha256": hashlib.sha256(candidate).hexdigest()})
    )


def _expect_rejection(action: Callable[[], object]) -> str:
    try:
        action()
    except _EXPECTED_REJECTION:
        return "rejected"
    raise AcceptanceError("invalid evidence was not rejected")


def _positive_runs(root: Path) -> tuple[dict[str, object], dict[str, Path]]:
    workflow_runs: list[Path] = []
    for index in range(_REPETITIONS):
        run = root / "workflow" / f"run-{index + 1}"
        if run_offline_workflow(run) != "pass":
            raise AcceptanceError("workflow representative did not pass")
        workflow_runs.append(run)

    coding_runs: dict[str, list[Path]] = {}
    for case_id in _CODING_CASES:
        runs: list[Path] = []
        for index in range(_REPETITIONS):
            run = root / "coding" / case_id / f"run-{index + 1}"
            if run_coding_task(run, case_id) != "pass":
                raise AcceptanceError(f"coding representative did not pass: {case_id}")
            runs.append(run)
        coding_runs[case_id] = runs

    workflow_case = OfflineWorkflowProfile().authority.cases[0].case_id
    summary = {
        "sanitized-v1-workflow": {
            "case_id": workflow_case,
            "outcome": "pass",
            "repetitions": _REPETITIONS,
            "strict_reload": True,
            "tree_sha256": _same_digest(workflow_runs),
        },
        "sanitized-v2-coding": {
            "cases": {
                case_id: {
                    "outcome": "pass",
                    "repetitions": _REPETITIONS,
                    "strict_reload": True,
                    "tree_sha256": _same_digest(runs),
                }
                for case_id, runs in coding_runs.items()
            }
        },
    }
    exemplars = {
        "workflow": workflow_runs[0],
        "coding": coding_runs["backend-v1"][0],
    }
    return summary, exemplars


def _adversarial_runs(root: Path, exemplars: dict[str, Path]) -> dict[str, str]:
    corrupt = root / "corrupt-artifact"
    shutil.copytree(exemplars["workflow"] / "bundle", corrupt / "bundle")
    (corrupt / "bundle/streams/stdout.json").write_bytes(b"{}")
    corrupt_result = _expect_rejection(
        lambda: import_evidence_bundle_v2(
            profile=OfflineWorkflowProfile(),
            bundle_path=corrupt / "bundle/bundle.json",
            output=corrupt / "imported",
        )
    )

    missing = root / "missing-artifact"
    shutil.copytree(exemplars["workflow"] / "bundle", missing / "bundle")
    (missing / "bundle/streams/stdout.json").unlink()
    missing_result = _expect_rejection(
        lambda: import_evidence_bundle_v2(
            profile=OfflineWorkflowProfile(),
            bundle_path=missing / "bundle/bundle.json",
            output=missing / "imported",
        )
    )

    mismatch = root / "authority-mismatch"
    shutil.copytree(exemplars["coding"] / "bundle", mismatch / "bundle")
    mismatch_result = _expect_rejection(
        lambda: import_evidence_bundle_v2(
            profile=OfflineWorkflowProfile(),
            bundle_path=mismatch / "bundle/bundle.json",
            output=mismatch / "imported",
        )
    )

    traversal = root / "candidate-traversal"
    completed = materialize_completed_export(traversal / "completed", "backend-v1")
    (completed.root / "candidate.json").write_bytes(
        _canonical({"files": {"../escape.py": "not contained"}})
    )
    _rewrite_coding_answer(completed.root)
    try:
        CodingTaskAdapter().adapt(completed, traversal / "bundle")
    except CompletedExportError:
        traversal_result = "rejected"
    else:
        raise AcceptanceError("candidate traversal was not rejected")

    behavioral = root / "behavioral-fail"
    completed = materialize_completed_export(behavioral / "completed", "backend-v1")
    (completed.root / "candidate.json").write_bytes(
        _canonical({"files": {"app.py": "def health():\n    return {'status': 'bad'}\n"}})
    )
    _rewrite_coding_answer(completed.root)
    adapted = CodingTaskAdapter().adapt(completed, behavioral / "bundle")
    profile = CodingTaskProfile()
    imported = behavioral / "imported"
    import_evidence_bundle_v2(
        profile=profile,
        bundle_path=adapted.bundle_path,
        output=imported,
    )
    evaluated = behavioral / "evaluated"
    receipt = evaluate_imported_case(profile, imported, evaluated)
    if receipt.case_outcome != "fail" or not receipt.eligible:
        raise AcceptanceError("behavioral mismatch did not produce an eligible fail")
    if read_imported_evaluation(evaluated, profile) != receipt:
        raise AcceptanceError("behavioral fail did not strictly reload")

    return {
        "authority_mismatch": mismatch_result,
        "behavioral_mismatch": "fail",
        "candidate_traversal": traversal_result,
        "corrupt_artifact": corrupt_result,
        "missing_artifact": missing_result,
    }


def _block_network(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise AcceptanceError("acceptance attempted network access")


def rebuild(output: Path) -> dict[str, object]:
    repository = Path(__file__).resolve().parents[1]
    module_path = Path(cernora.__file__).resolve()
    if module_path.is_relative_to(repository):
        raise AcceptanceError("Cernora must be imported from an installed wheel")
    if output.exists() or output.is_symlink():
        raise AcceptanceError("acceptance output must not already exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()

    with (
        patch.object(socket, "socket", _block_network),
        patch.object(socket, "create_connection", _block_network),
    ):
        tasks, exemplars = _positive_runs(output / "runs")
        adversarial = _adversarial_runs(output / "adversarial", exemplars)

    summary: dict[str, object] = {
        "schema_version": "cernora.public-acceptance-summary/v1",
        "cernora_version": metadata.version("cernora"),
        "input_protocol": "agent.evaluator.evidence-bundle/v2",
        "output_protocols": [
            "agent.evaluator.evidence/v1",
            "agent.evaluator.score/v1",
            "agent.evaluator.gate-decision/v1",
        ],
        "execution": {
            "credentials_required": False,
            "network_blocked": True,
            "repository_source_import": False,
            "wheel_only": True,
        },
        "scope": {
            "agent_execution": False,
            "completed_export": "packaged_synthetic",
            "evaluation_core_path": True,
            "experiment_harness": False,
            "runtime_receipt_capture": False,
            "sandbox_execution": False,
        },
        "tasks": tasks,
        "adversarial": adversarial,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rebuild(args.output)
    print("pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
