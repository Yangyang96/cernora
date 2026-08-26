#!/usr/bin/env python3
"""Wheel-only acceptance for strict controlled Comparison Preview contracts."""

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
import cernora.comparison as comparison_module
from cernora import (
    BatchAttempt,
    BatchAttemptResources,
    BootstrapPlan,
    ComparisonArm,
    ComparisonCase,
    ComparisonGuardrail,
    ExperimentProjection,
    PassKPlan,
    PrimaryOutcome,
    TreatmentChange,
    embed_evaluation_package,
    materialize_batch_input,
    materialize_comparison_input,
    materialize_experiment_authority,
    materialize_treatment,
    reload_comparison_package,
    summarize_comparison,
)
from cernora.batch import BatchPlannedTrial, BatchTrial
from cernora.evaluation.package import (
    evaluate_imported_case,
    validate_evaluation_package_content,
)
from cernora.examples.tool_workflow import materialize_fixture
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profiles.tool_workflow import ToolWorkflowProfile


class ComparisonWheelCheckError(RuntimeError):
    """The installed wheel did not prove the complete Comparison flow."""


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _evaluated_attempt(root: Path, *, fixture: str, trial_id: str) -> BatchAttempt:
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
        attempt_id=_digest(f"attempt-{trial_id}"),
        source_attempt_id=receipt.run.attempt_id,
        trial_id=trial_id,
        ordinal=1,
        predecessor_attempt_id=None,
        source_manifest_sha256=_digest(f"manifest-{trial_id}"),
        retry_eligible=False,
        resources=BatchAttemptResources(
            duration_milliseconds=100,
            input_tokens=None,
            output_tokens=None,
            cost_microunits=None,
            usage_receipt_sha256=None,
        ),
        evaluation=embed_evaluation_package(evaluated),
    )


def _block_network(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise ComparisonWheelCheckError("comparison wheel acceptance attempted network access")


def _comparison(output: Path):  # type: ignore[no-untyped-def]
    run_plan_id = _digest("comparison-wheel-run-plan")
    execution_id = _digest("comparison-wheel-execution")
    planned: list[BatchPlannedTrial] = []
    trials: list[BatchTrial] = []
    fixtures = {
        "baseline": ("wrong-tool", "wrong-argument", "wrong-tool"),
        "candidate": ("happy-path", "safe-recovery", "happy-path"),
    }
    index = 0
    first_evaluation = None
    for configuration_id in ("baseline", "candidate"):
        for repetition, fixture in enumerate(fixtures[configuration_id], start=1):
            index += 1
            trial_id = _digest(f"comparison-wheel-trial-{index}")
            experiment_id = _digest(f"comparison-wheel-experiment-{configuration_id}")
            slot = BatchPlannedTrial(
                slot_index=index,
                trial_slot_id=_digest(f"comparison-wheel-slot-{index}"),
                case_id="create-request-v1",
                configuration_id=configuration_id,
                experiment_id=experiment_id,
                repetition=repetition,
            )
            attempt = _evaluated_attempt(
                output / f"source-{index}",
                fixture=fixture,
                trial_id=trial_id,
            )
            if first_evaluation is None:
                first_evaluation = attempt.evaluation
            planned.append(slot)
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
            "companion_version": "comparison-wheel-check",
            "planned_trial_count": len(planned),
            "attempt_count": len(trials),
            "planned_trials": [item.model_dump(mode="json") for item in planned],
            "trials": [item.model_dump(mode="json") for item in trials],
        }
    )
    assert first_evaluation is not None
    receipt, _ = validate_evaluation_package_content(first_evaluation.file_payloads())
    prompt_baseline = _digest("comparison-wheel-prompt-baseline")
    prompt_candidate = _digest("comparison-wheel-prompt-candidate")
    common = {
        "runtime_version_sha256": _digest("runtime"),
        "model_sha256": _digest("model"),
        "tool_schema_sha256": _digest("tools"),
        "generation_configuration_sha256": _digest("generation"),
        "timeout_sha256": _digest("timeout"),
        "resources_sha256": _digest("resources"),
        "retry_policy_sha256": _digest("retry"),
        "dataset_sha256": _digest("dataset"),
        "profile_sha256": receipt.profile.sha256,
        "evaluation_authority_sha256": receipt.authority_sha256,
        "evaluation_policy_sha256": comparison_module.evaluation_policy_sha256(receipt),
        "report_contract_sha256": _digest("report-contract"),
        "statistical_plan_sha256": _digest("statistical-plan"),
    }
    experiment_authorities = tuple(
        materialize_experiment_authority(
            {
                "schema_version": "agent.evaluator.comparison-experiment-authority/v1",
                "configuration_id": configuration_id,
                "case": receipt.case.model_dump(mode="json"),
                "projection": ExperimentProjection(
                    prompt_instruction_sha256=(
                        prompt_baseline if configuration_id == "baseline" else prompt_candidate
                    ),
                    **common,
                ).model_dump(mode="json"),
            }
        )
        for configuration_id in ("baseline", "candidate")
    )
    experiment_ids = {item.configuration_id: item.experiment_id for item in experiment_authorities}
    batch_payload = batch_input.model_dump(
        mode="json", exclude={"batch_input_id", "batch_input_sha256"}
    )
    for slot in batch_payload["planned_trials"]:
        slot["experiment_id"] = experiment_ids[slot["configuration_id"]]
    for trial in batch_payload["trials"]:
        trial["experiment_id"] = experiment_ids[trial["configuration_id"]]
    batch_input = materialize_batch_input(batch_payload)
    baseline = ComparisonArm(configuration_id="baseline")
    candidate = ComparisonArm(configuration_id="candidate")
    treatment = materialize_treatment(
        (
            TreatmentChange(
                kind="prompt_instruction",
                baseline_sha256=prompt_baseline,
                candidate_sha256=prompt_candidate,
            ),
        )
    )
    return materialize_comparison_input(
        {
            "schema_version": "agent.evaluator.comparison-input/v1",
            "batch_input": batch_input.model_dump(mode="json"),
            "baseline": baseline.model_dump(mode="json"),
            "candidate": candidate.model_dump(mode="json"),
            "experiment_authorities": [
                item.model_dump(mode="json") for item in experiment_authorities
            ],
            "cases": [
                ComparisonCase(
                    case=receipt.case,
                    split_id="development",
                    baseline_experiment_id=experiment_ids["baseline"],
                    candidate_experiment_id=experiment_ids["candidate"],
                ).model_dump(mode="json")
            ],
            "treatment": treatment.model_dump(mode="json"),
            "primary_outcome": PrimaryOutcome(
                metric="reliable_success_rate",
                scope="all",
                direction="higher_is_better",
                practical_threshold_basis_points=1_000,
            ).model_dump(mode="json"),
            "guardrails": [
                ComparisonGuardrail(
                    guardrail_id="evaluation-validity",
                    hard=True,
                    metric="evaluation_validity_rate",
                    scope="all",
                    direction="higher_is_better",
                    max_adverse_basis_points=0,
                ).model_dump(mode="json")
            ],
            "bootstrap": BootstrapPlan(
                method="case-clustered-paired-bootstrap/v1",
                confidence_basis_points=9_500,
                resamples=10_000,
                percentile="nearest_rank_closed",
                seed_source="comparison_input_sha256",
            ).model_dump(mode="json"),
            "pass_k": PassKPlan(k=2, independent_trials=True).model_dump(mode="json"),
        }
    )


def run(output: Path, *, allow_source: bool = False) -> dict[str, object]:
    """Prove deterministic controlled comparison from an installed wheel."""

    output = output.resolve()
    repository = Path(__file__).resolve().parents[1]
    module_path = Path(cernora.__file__).resolve()
    if module_path.is_relative_to(repository) and not allow_source:
        raise ComparisonWheelCheckError("Cernora must be imported from an installed wheel")
    if output.exists() or output.is_symlink():
        raise ComparisonWheelCheckError("comparison acceptance output must not already exist")
    output.mkdir(parents=True)
    with (
        patch.object(socket, "socket", _block_network),
        patch.object(socket, "create_connection", _block_network),
    ):
        comparison = _comparison(output)
        summaries = [
            summarize_comparison(comparison, output / f"summary-{index}") for index in range(3)
        ]
    trees = [_tree(output / f"summary-{index}") for index in range(3)]
    if (
        summaries[0] != summaries[1]
        or summaries[1] != summaries[2]
        or len(set(map(_tree_digest, trees))) != 1
    ):
        raise ComparisonWheelCheckError("identical Comparison Inputs produced different summaries")
    package = reload_comparison_package(output / "summary-0")
    authoritative = (output / "summary-0" / "comparison-summary.json").read_bytes().lower()
    for forbidden in (b"p-value", b"winner", b"ranking", b"promotion"):
        if forbidden in authoritative:
            raise ComparisonWheelCheckError("Comparison Summary contains a forbidden claim")
    result: dict[str, object] = {
        "schema_version": "cernora.comparison-wheel-check/v1",
        "cernora_version": metadata.version("cernora"),
        "comparison_id": comparison.comparison_id,
        "summary_id": package.summary.summary_id,
        "conclusion": package.summary.conclusion,
        "byte_identical_repetitions": 3,
        "network_blocked": True,
        "repository_source_import": False,
        "wheel_only": True,
    }
    (output / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def _tree_digest(tree: dict[str, bytes]) -> str:
    manifest = [
        {"path": path, "sha256": hashlib.sha256(payload).hexdigest()}
        for path, payload in sorted(tree.items())
    ]
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


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
