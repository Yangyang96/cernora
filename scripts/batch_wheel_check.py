#!/usr/bin/env python3
"""Wheel-only acceptance for the Runtime-neutral Batch Summary Preview."""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
from importlib import metadata
from pathlib import Path
from typing import NoReturn
from unittest.mock import patch

import cernora
from cernora import (
    BatchAttempt,
    BatchAttemptResources,
    BatchLifecycleRecord,
    BatchPlannedTrial,
    BatchTrial,
    embed_evaluation_package,
    materialize_batch_input,
    reload_batch_summary,
    summarize_batch,
)
from cernora.core.canonical import canonical_json
from cernora.evaluation.package import evaluate_imported_case
from cernora.examples.tool_workflow import materialize_fixture
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profiles.tool_workflow import ToolWorkflowProfile


class BatchWheelCheckError(RuntimeError):
    """The installed wheel did not prove the complete batch flow."""


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _block_network(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise BatchWheelCheckError("batch wheel acceptance attempted network access")


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _evaluated_attempt(
    root: Path,
    *,
    fixture: str,
    trial_id: str,
    ordinal: int,
    predecessor: str | None,
) -> BatchAttempt:
    profile = ToolWorkflowProfile()
    adapted = materialize_fixture(fixture, root / "bundle")
    imported = root / "imported"
    import_evidence_bundle_v2(
        profile=profile,
        bundle_path=adapted.bundle_path,
        output=imported,
    )
    evaluated = root / "evaluated"
    receipt = evaluate_imported_case(profile, imported, evaluated)
    return BatchAttempt(
        schema_version="agent.evaluator.batch-attempt/v1",
        attempt_id=_digest(f"attempt-{trial_id}-{ordinal}"),
        source_attempt_id=receipt.run.attempt_id,
        trial_id=trial_id,
        ordinal=ordinal,
        predecessor_attempt_id=predecessor,
        source_manifest_sha256=_digest(f"manifest-{trial_id}-{ordinal}"),
        retry_eligible=False,
        resources=BatchAttemptResources(
            duration_milliseconds=ordinal * 100,
            input_tokens=None,
            output_tokens=None,
            cost_microunits=None,
            usage_receipt_sha256=None,
        ),
        evaluation=embed_evaluation_package(evaluated),
    )


def _lifecycle_attempt(trial_id: str) -> BatchAttempt:
    return BatchAttempt(
        schema_version="agent.evaluator.batch-attempt/v1",
        attempt_id=_digest(f"attempt-{trial_id}-1"),
        source_attempt_id=f"source-{trial_id[:16]}",
        trial_id=trial_id,
        ordinal=1,
        predecessor_attempt_id=None,
        source_manifest_sha256=_digest(f"manifest-{trial_id}-1"),
        retry_eligible=False,
        resources=BatchAttemptResources(
            duration_milliseconds=100,
            input_tokens=None,
            output_tokens=None,
            cost_microunits=None,
            usage_receipt_sha256=None,
        ),
        lifecycle=BatchLifecycleRecord(
            schema_version="agent.evaluator.batch-lifecycle/v1",
            category="runtime_pre_terminal_failure",
            retry_eligible=False,
            source_state="runtime-pre-terminal-failure",
            receipt_sha256=_digest(f"receipt-{trial_id}"),
        ),
    )


def run(output: Path, *, allow_source: bool = False) -> dict[str, object]:
    """Prove all four outcomes and byte-stable publication from an installed wheel."""

    output = output.resolve()
    repository = Path(__file__).resolve().parents[1]
    module_path = Path(cernora.__file__).resolve()
    if module_path.is_relative_to(repository) and not allow_source:
        raise BatchWheelCheckError("Cernora must be imported from an installed wheel")
    if output.exists() or output.is_symlink():
        raise BatchWheelCheckError("batch acceptance output must not already exist")
    output.mkdir(parents=True)

    run_plan_id = _digest("wheel-run-plan")
    execution_id = _digest("wheel-execution")
    fixtures = ("happy-path", "wrong-tool", "contradictory-runtime-evidence", None)
    planned: list[BatchPlannedTrial] = []
    trials: list[BatchTrial] = []
    with (
        patch.object(socket, "socket", _block_network),
        patch.object(socket, "create_connection", _block_network),
    ):
        for index, fixture in enumerate(fixtures, start=1):
            trial_id = _digest(f"wheel-trial-{index}")
            slot = BatchPlannedTrial(
                slot_index=index,
                trial_slot_id=_digest(f"wheel-slot-{index}"),
                case_id=("create-request-v1" if fixture is not None else "unavailable-case-v1"),
                configuration_id="wheel-configuration",
                experiment_id=_digest(
                    "wheel-evaluated-experiment"
                    if fixture is not None
                    else "wheel-unavailable-experiment"
                ),
                repetition=index if fixture is not None else 1,
            )
            planned.append(slot)
            attempt = (
                _evaluated_attempt(
                    output / f"source-{index}",
                    fixture=fixture,
                    trial_id=trial_id,
                    ordinal=1,
                    predecessor=None,
                )
                if fixture is not None
                else _lifecycle_attempt(trial_id)
            )
            trials.append(
                BatchTrial(
                    schema_version="agent.evaluator.batch-trial/v1",
                    run_plan_id=run_plan_id,
                    execution_id=execution_id,
                    trial_id=trial_id,
                    slot_index=slot.slot_index,
                    trial_slot_id=slot.trial_slot_id,
                    case_id=slot.case_id,
                    configuration_id=slot.configuration_id,
                    experiment_id=slot.experiment_id,
                    repetition=slot.repetition,
                    selected_attempt_id=attempt.attempt_id,
                    attempts=(attempt,),
                )
            )
        batch_input = materialize_batch_input(
            {
                "schema_version": "agent.evaluator.batch-input/v1",
                "run_plan_id": run_plan_id,
                "execution_id": execution_id,
                "execution_status": "completed",
                "budget_status": "within_budget",
                "companion_version": "wheel-check",
                "planned_trial_count": len(planned),
                "attempt_count": len(trials),
                "planned_trials": [item.model_dump(mode="json") for item in planned],
                "trials": [item.model_dump(mode="json") for item in trials],
            }
        )
        (output / "batch-input.json").write_bytes(canonical_json(batch_input))
        summaries = [
            summarize_batch(batch_input, output / f"summary-{index}") for index in range(3)
        ]
    trees = [_tree(output / f"summary-{index}") for index in range(3)]
    if (
        summaries[0] != summaries[1]
        or summaries[1] != summaries[2]
        or not (trees[0] == trees[1] == trees[2])
    ):
        raise BatchWheelCheckError("identical Batch Inputs produced different summaries")
    summary = reload_batch_summary(output / "summary-0")
    if summary.overall.outcomes.model_dump() != {
        "passed": 1,
        "behavioral_failed": 1,
        "evaluation_invalid": 1,
        "infrastructure_unavailable": 1,
    }:
        raise BatchWheelCheckError("wheel Batch Summary did not retain all four outcomes")
    result: dict[str, object] = {
        "schema_version": "cernora.batch-wheel-check/v1",
        "cernora_version": metadata.version("cernora"),
        "batch_input_id": batch_input.batch_input_id,
        "summary_id": summary.summary_id,
        "byte_identical_repetitions": 3,
        "network_blocked": True,
        "repository_source_import": False,
        "wheel_only": True,
    }
    (output / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-source", action="store_true")
    args = parser.parse_args()
    run(args.output, allow_source=args.allow_source)
    print("pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
