from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from cernora import (
    PUBLIC_SCHEMAS,
    BatchAttempt,
    BatchAttemptResources,
    BatchEvaluationPackage,
    BatchInput,
    BatchLifecycleRecord,
    BatchPlannedTrial,
    BatchTrial,
    build_batch_summary,
    embed_evaluation_package,
    materialize_batch_input,
    read_public_schema,
    reload_batch_summary,
    summarize_batch,
    validate_batch_input,
)
from cernora.cli.main import main
from cernora.core.canonical import canonical_json
from cernora.evaluation.contracts import (
    ImportedEvaluationFileDigest,
    ImportedEvaluationManifest,
)
from cernora.evaluation.package import (
    evaluate_imported_case,
    validate_evaluation_package_content,
)
from cernora.examples.tool_workflow import materialize_fixture
from cernora.ingestion.errors import IngestionConfigurationError, IngestionIntegrityError
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profiles.tool_workflow import ToolWorkflowProfile

RUN_PLAN_ID = hashlib.sha256(b"batch-run-plan").hexdigest()
EXECUTION_ID = hashlib.sha256(b"batch-execution").hexdigest()


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _evaluations(tmp_path: Path) -> dict[str, BatchEvaluationPackage]:
    profile = ToolWorkflowProfile()
    result: dict[str, BatchEvaluationPackage] = {}
    for name in (
        "happy-path",
        "wrong-tool",
        "contradictory-runtime-evidence",
        "safe-recovery",
        "wrong-argument",
        "missing-runtime-evidence",
    ):
        root = tmp_path / f"evaluation-{name}"
        adapted = materialize_fixture(name, root / "bundle")
        imported = root / "imported"
        import_evidence_bundle_v2(
            profile=profile,
            bundle_path=adapted.bundle_path,
            output=imported,
        )
        evaluated = root / "evaluated"
        evaluate_imported_case(profile, imported, evaluated)
        result[name] = embed_evaluation_package(evaluated)
    return result


def _lifecycle_attempt(
    *, trial_id: str, label: str, ordinal: int = 1, predecessor: str | None = None
) -> BatchAttempt:
    retry_eligible = label.startswith("retryable")
    attempt_id = _digest(f"attempt-{label}")
    return BatchAttempt(
        schema_version="agent.evaluator.batch-attempt/v1",
        attempt_id=attempt_id,
        source_attempt_id=f"source-{label}",
        trial_id=trial_id,
        ordinal=ordinal,
        predecessor_attempt_id=predecessor,
        source_manifest_sha256=_digest(f"manifest-{label}"),
        retry_eligible=retry_eligible,
        resources=BatchAttemptResources(
            duration_milliseconds=100 + ordinal,
            input_tokens=None,
            output_tokens=None,
            cost_microunits=None,
            usage_receipt_sha256=None,
        ),
        lifecycle=BatchLifecycleRecord(
            schema_version="agent.evaluator.batch-lifecycle/v1",
            category=(
                "transient_provider_pre_terminal"
                if retry_eligible
                else "runtime_pre_terminal_failure"
            ),
            retry_eligible=retry_eligible,
            source_state=(
                "transient-provider-pre-terminal"
                if retry_eligible
                else "runtime-pre-terminal-failure"
            ),
            receipt_sha256=_digest(f"receipt-{label}"),
        ),
    )


def _evaluated_attempt(
    *,
    trial_id: str,
    package: BatchEvaluationPackage,
    ordinal: int = 1,
    predecessor: str | None = None,
) -> BatchAttempt:
    payload = package.model_dump(mode="json")
    attempt_id = next(
        item for item in payload["files"] if item["path"] == "evaluation-receipt.json"
    )
    receipt = json.loads(base64.b64decode(attempt_id["content_base64"]))
    return BatchAttempt(
        schema_version="agent.evaluator.batch-attempt/v1",
        attempt_id=_digest(f"attempt-{trial_id}-{ordinal}"),
        source_attempt_id=receipt["run"]["attempt_id"],
        trial_id=trial_id,
        ordinal=ordinal,
        predecessor_attempt_id=predecessor,
        source_manifest_sha256=_digest(f"manifest-{trial_id}-{ordinal}"),
        retry_eligible=False,
        resources=BatchAttemptResources(
            duration_milliseconds=200 + ordinal,
            input_tokens=None,
            output_tokens=None,
            cost_microunits=None,
            usage_receipt_sha256=None,
        ),
        evaluation=package,
    )


def _rehashed_evaluation_files(
    package: BatchEvaluationPackage,
    *,
    path: str,
    mutate: object,
) -> dict[str, bytes]:
    files = package.file_payloads()
    payload = json.loads(files[path])
    assert isinstance(payload, dict)
    assert callable(mutate)
    mutate(payload)
    files[path] = canonical_json(payload)
    manifest = ImportedEvaluationManifest(
        schema_version="agent.evaluator.imported-evaluation-manifest/v1",
        files=tuple(
            ImportedEvaluationFileDigest(
                path=name,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
            for name, content in sorted(files.items())
            if name != "digests.json"
        ),
    )
    files["digests.json"] = canonical_json(manifest)
    return files


def _embedded_package_payload(files: dict[str, bytes]) -> dict[str, object]:
    embedded = tuple(
        {
            "path": path,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "content_base64": base64.b64encode(payload).decode("ascii"),
        }
        for path, payload in sorted(files.items())
    )
    package_sha256 = hashlib.sha256(
        canonical_json(
            [
                {
                    "path": item["path"],
                    "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                }
                for item in embedded
            ]
        )
    ).hexdigest()
    return {
        "schema_version": "agent.evaluator.batch-evaluation-package/v1",
        "package_sha256": package_sha256,
        "files": embedded,
    }


def _batch_input(tmp_path: Path) -> BatchInput:
    evaluations = _evaluations(tmp_path)
    evaluation_names = iter(evaluations)
    planned: list[BatchPlannedTrial] = []
    trials: list[BatchTrial] = []
    slot_index = 0
    for case_id in ("create-request-v1", "no-tool-required-v1"):
        for configuration_id in ("configuration-a", "configuration-b"):
            for repetition in range(1, 4):
                slot_index += 1
                trial_id = _digest(f"trial-{slot_index}")
                slot = BatchPlannedTrial(
                    slot_index=slot_index,
                    trial_slot_id=_digest(f"slot-{slot_index}"),
                    case_id=case_id,
                    configuration_id=configuration_id,
                    experiment_id=_digest(f"experiment-{case_id}-{configuration_id}"),
                    repetition=repetition,
                )
                planned.append(slot)
                if case_id == "create-request-v1":
                    name = next(evaluation_names)
                    package = evaluations[name]
                    if slot_index == 1:
                        first = _lifecycle_attempt(trial_id=trial_id, label="retryable-first")
                        attempts = (
                            first,
                            _evaluated_attempt(
                                trial_id=trial_id,
                                package=package,
                                ordinal=2,
                                predecessor=first.attempt_id,
                            ),
                        )
                    else:
                        attempts = (_evaluated_attempt(trial_id=trial_id, package=package),)
                else:
                    attempts = (
                        _lifecycle_attempt(trial_id=trial_id, label=f"unavailable-{slot_index}"),
                    )
                trials.append(
                    BatchTrial(
                        schema_version="agent.evaluator.batch-trial/v1",
                        run_plan_id=RUN_PLAN_ID,
                        execution_id=EXECUTION_ID,
                        trial_id=trial_id,
                        slot_index=slot.slot_index,
                        trial_slot_id=slot.trial_slot_id,
                        case_id=slot.case_id,
                        configuration_id=slot.configuration_id,
                        experiment_id=slot.experiment_id,
                        repetition=slot.repetition,
                        selected_attempt_id=attempts[-1].attempt_id,
                        attempts=attempts,
                    )
                )
    payload = {
        "schema_version": "agent.evaluator.batch-input/v1",
        "run_plan_id": RUN_PLAN_ID,
        "execution_id": EXECUTION_ID,
        "execution_status": "completed",
        "budget_status": "within_budget",
        "companion_version": "0.2.1",
        "planned_trial_count": len(planned),
        "attempt_count": sum(len(item.attempts) for item in trials),
        "planned_trials": [item.model_dump(mode="json") for item in planned],
        "trials": [item.model_dump(mode="json") for item in trials],
    }
    return materialize_batch_input(payload)


@pytest.mark.integration
def test_two_by_two_by_three_summary_is_validity_first_and_deterministic(
    tmp_path: Path,
) -> None:
    batch_input = _batch_input(tmp_path)
    assert batch_input.planned_trial_count == 12
    assert batch_input.attempt_count == 13

    summaries = []
    trees = []
    for index in range(3):
        output = tmp_path / f"summary-{index}"
        summaries.append(summarize_batch(batch_input, output))
        trees.append(
            {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }
        )

    assert summaries[0] == summaries[1] == summaries[2]
    assert trees[0] == trees[1] == trees[2]
    summary = summaries[0]
    assert summary.overall.outcomes.model_dump() == {
        "passed": 2,
        "behavioral_failed": 2,
        "evaluation_invalid": 2,
        "infrastructure_unavailable": 6,
    }
    assert summary.overall.evaluation_validity_rate.value == 4 / 12
    assert summary.overall.behavioral_success_rate.value == 2 / 4
    assert summary.overall.reliable_success_rate.value == 2 / 12
    no_tool_groups = [item for item in summary.by_case if item.case_id == "no-tool-required-v1"]
    assert len(no_tool_groups) == 1
    assert no_tool_groups[0].behavioral_success_rate.value is None
    assert summary.attempt_diagnostics.retry_attempts == 1
    assert summary.attempt_diagnostics.trials_with_retry == 1
    assert summary.attempt_diagnostics.input_tokens.status == "unavailable"
    assert reload_batch_summary(tmp_path / "summary-0") == summary


def test_batch_input_and_summary_reject_corruption_unknown_fields_and_conflicts(
    tmp_path: Path,
) -> None:
    batch_input = _batch_input(tmp_path)
    input_path = tmp_path / "batch-input.json"
    input_path.write_bytes(canonical_json(batch_input))
    assert validate_batch_input(input_path) == batch_input

    payload = batch_input.model_dump(mode="json")
    payload["caller_success_rate"] = 1.0
    input_path.write_bytes(canonical_json(payload))
    with pytest.raises(IngestionIntegrityError, match="invalid Batch Input"):
        validate_batch_input(input_path)

    output = tmp_path / "summary"
    summarize_batch(batch_input, output)
    with pytest.raises(IngestionConfigurationError, match="must not already exist"):
        summarize_batch(batch_input, output)
    summary_payload = bytearray((output / "batch-summary.json").read_bytes())
    summary_payload[-2] = ord("0") if summary_payload[-2] != ord("0") else ord("1")
    (output / "batch-summary.json").write_bytes(bytes(summary_payload))
    with pytest.raises(IngestionIntegrityError, match="digest mismatch"):
        reload_batch_summary(output)


@pytest.mark.parametrize(
    ("evaluation_name", "path", "mutation"),
    (
        (
            "happy-path",
            "evidence.json",
            lambda payload: payload.__setitem__("case_id", "forged-case"),
        ),
        (
            "happy-path",
            "score.json",
            lambda payload: payload.__setitem__("evidence_id", "forged-evidence"),
        ),
        (
            "happy-path",
            "case-decision.json",
            lambda payload: payload.__setitem__("score_ids", ["forged-score"]),
        ),
        (
            "wrong-tool",
            "evaluation-report.json",
            lambda payload: payload["records"][0].__setitem__("id", "forged-outcome"),
        ),
    ),
)
def test_rehashed_cross_contract_mutations_fail_strict_embedded_reload(
    tmp_path: Path,
    evaluation_name: str,
    path: str,
    mutation: object,
) -> None:
    package = _evaluations(tmp_path)[evaluation_name]
    files = _rehashed_evaluation_files(package, path=path, mutate=mutation)

    with pytest.raises(IngestionIntegrityError):
        validate_evaluation_package_content(files)
    with pytest.raises(ValueError, match="strict reload"):
        BatchEvaluationPackage.model_validate(_embedded_package_payload(files))


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "unknown", "broken_chain"))
def test_batch_input_rejects_incomplete_or_broken_trial_authority(
    tmp_path: Path,
    mutation: str,
) -> None:
    payload = _batch_input(tmp_path).model_dump(mode="json")
    payload.pop("batch_input_id")
    payload.pop("batch_input_sha256")
    if mutation == "missing":
        payload["trials"].pop()
    elif mutation == "duplicate":
        payload["trials"][-1] = copy.deepcopy(payload["trials"][0])
    elif mutation == "unknown":
        payload["trials"][-1]["trial_slot_id"] = "f" * 64
    else:
        payload["trials"][0]["attempts"][1]["predecessor_attempt_id"] = "f" * 64
    with pytest.raises(ValueError):
        materialize_batch_input(payload)


def test_build_summary_does_not_publish_comparisons_or_winners(tmp_path: Path) -> None:
    summary = build_batch_summary(_batch_input(tmp_path))
    payload = canonical_json(summary)
    for forbidden in (b"winner", b"delta", b"confidence", b"pass@k", b"improvement"):
        assert forbidden not in payload.lower()


def test_batch_cli_validate_summarize_and_corruption_exit_classes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    batch_input = _batch_input(tmp_path)
    input_path = tmp_path / "batch-input.json"
    input_path.write_bytes(canonical_json(batch_input))

    assert main(["batch", "validate", str(input_path)]) == 0
    assert f'"batch_input_id":"{batch_input.batch_input_id}"' in capsys.readouterr().out

    output = tmp_path / "cli-summary"
    assert main(["batch", "summarize", str(input_path), "--output", str(output)]) == 0
    assert reload_batch_summary(output).batch_input_id == batch_input.batch_input_id
    capsys.readouterr()

    input_path.write_bytes(b"{}")
    assert main(["batch", "validate", str(input_path)]) == 3
    assert "invalid Batch Input" in capsys.readouterr().err


def test_batch_schemas_are_packaged_and_accept_authoritative_models(tmp_path: Path) -> None:
    batch_input = _batch_input(tmp_path)
    summary = build_batch_summary(batch_input)
    assert "batch-input-v1.schema.json" in PUBLIC_SCHEMAS
    assert "batch-summary-v1.schema.json" in PUBLIC_SCHEMAS
    input_validator = Draft202012Validator(
        json.loads(read_public_schema("batch-input-v1.schema.json"))
    )
    summary_validator = Draft202012Validator(
        json.loads(read_public_schema("batch-summary-v1.schema.json"))
    )
    input_validator.validate(batch_input.model_dump(mode="json"))
    summary_validator.validate(summary.model_dump(mode="json"))
    unknown = batch_input.model_dump(mode="json")
    unknown["caller_success_rate"] = 1.0
    assert not input_validator.is_valid(unknown)
