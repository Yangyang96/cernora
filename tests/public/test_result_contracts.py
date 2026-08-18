from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError
from referencing import Registry, Resource

from cernora.core.canonical import strict_json_loads
from cernora.core.errors import ContractError
from cernora.core.evidence import EvidenceReference
from cernora.core.result import (
    MAX_ABSOLUTE_INTEGER_RESULT_VALUE,
    MAX_ABSOLUTE_RESULT_VALUE,
    EvaluationReport,
    ResultRecord,
)

SCHEMA_DIRECTORY = Path(__file__).parents[2] / "src" / "cernora" / "schemas"


def _reference(locator: str = "artifact:result") -> EvidenceReference:
    return EvidenceReference(
        evidence_id="evidence-1",
        locator=locator,
        sha256="0" * 64,
    )


def _record(**changes: object) -> ResultRecord:
    values: dict[str, object] = {
        "id": "task_outcome",
        "version": "agent.evaluator.result-record/v1",
        "role": "outcome",
        "value": True,
        "value_type": "boolean",
        "validity": "valid",
        "failure_reason": None,
        "evidence_refs": (_reference(),),
        "unit": None,
        "direction": None,
    }
    values.update(changes)
    return ResultRecord.model_validate(values)


def _report(*records: ResultRecord, **changes: object) -> EvaluationReport:
    records = records or (_record(),)
    values: dict[str, object] = {
        "schema_version": "agent.evaluator.evaluation-report/v1",
        "evaluation_id": "evaluation-1",
        "evidence_id": "evidence-1",
        "score_id": "score-1",
        "decision_id": "decision-1",
        "evaluation_input_sha256": "1" * 64,
        "authority_id": "authority-1",
        "authority_sha256": "2" * 64,
        "conclusion": "pass",
        "evaluation_validity": "valid",
        "records": records,
    }
    values.update(changes)
    return EvaluationReport.model_validate(values)


def test_valid_records_are_typed_evidence_bound_and_frozen() -> None:
    record = _record()
    measurement = _record(
        id="tool_calls",
        role="diagnostic",
        value=3,
        value_type="integer",
        unit="calls",
        direction="lower_is_better",
    )

    assert record.value is True
    assert measurement.value == 3
    with pytest.raises(ValidationError):
        record.value = False
    with pytest.raises(ValidationError, match="extra_forbidden"):
        _record(private_hint=True)


@pytest.mark.parametrize("value", [True, 1.5, float("nan"), float("inf"), 10**309])
def test_integer_records_reject_wrong_or_non_finite_values(value: object) -> None:
    with pytest.raises(ValidationError):
        _record(
            id="tool_calls",
            role="diagnostic",
            value=value,
            value_type="integer",
            unit="calls",
            direction="lower_is_better",
        )


def test_numeric_and_non_valid_record_invariants_fail_closed() -> None:
    with pytest.raises(ValidationError, match="require unit and direction"):
        _record(
            id="latency",
            role="diagnostic",
            value=1.25,
            value_type="number",
        )
    with pytest.raises(ValidationError, match="cannot carry a decision value"):
        _record(validity="unavailable", failure_reason="runtime_unavailable")
    with pytest.raises(ValidationError, match="deterministic failure reason"):
        _record(validity="invalid", value=None, failure_reason=" ")

    unavailable = _record(
        value=None,
        validity="unavailable",
        failure_reason="runtime_unavailable",
        evidence_refs=(),
    )
    assert unavailable.value is None

    with pytest.raises(ValidationError, match="must be boolean"):
        _record(
            value=1,
            value_type="integer",
            unit="count",
            direction="higher_is_better",
        )


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        ("integer", 10**309),
        ("number", 10**309),
        ("number", float("inf")),
        ("number", float("-inf")),
        ("number", float("nan")),
    ],
)
def test_numeric_records_reject_non_finite_and_out_of_range_values(
    value_type: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        _record(
            id="measurement",
            role="diagnostic",
            value=value,
            value_type=value_type,
            unit="count",
            direction="neutral",
        )


def test_evidence_references_are_canonicalized_without_standalone_deduplication() -> None:
    first = _reference("artifact:a")
    second = _reference("artifact:b")
    assert _record(evidence_refs=(first, second)).evidence_refs == (first, second)
    assert _record(evidence_refs=(second, first)).evidence_refs == (first, second)
    assert _record(evidence_refs=(first, first)).evidence_refs == (first, first)


def test_report_binds_identities_decision_records_and_validity() -> None:
    report = _report()
    assert report.conclusion == "pass"
    assert "required_result_ids" not in report.model_dump(mode="json")

    unavailable = _record(
        value=None,
        validity="unavailable",
        failure_reason="runtime_unavailable",
        evidence_refs=(),
    )
    inconclusive = _report(
        unavailable,
        conclusion="inconclusive",
        evaluation_validity="unavailable",
    )
    assert inconclusive.evaluation_validity == "unavailable"

    with pytest.raises(ValidationError, match="extra_forbidden"):
        _report(required_result_ids=("task_outcome",))
    with pytest.raises(ValidationError, match="extra_forbidden"):
        _report(report_id="report-1")
    with pytest.raises(ValidationError, match="at least one decision record"):
        _report(
            _record(
                id="tool_calls",
                role="diagnostic",
                value=1,
                value_type="integer",
                unit="calls",
                direction="lower_is_better",
            ),
        )
    with pytest.raises(ValidationError, match="match decision record validity"):
        _report(unavailable)
    with pytest.raises(ValidationError, match="match evaluation validity"):
        _report(conclusion="inconclusive")

    invalid = _record(
        value=None,
        validity="invalid",
        failure_reason="contradictory_evidence",
    )
    assert (
        _report(
            invalid,
            conclusion="inconclusive",
            evaluation_validity="invalid",
        ).evaluation_validity
        == "invalid"
    )
    with pytest.raises(ValidationError, match="decision record validity"):
        _report(
            invalid,
            conclusion="inconclusive",
            evaluation_validity="unavailable",
        )


def test_valid_report_conclusion_is_derived_from_decision_records() -> None:
    passing_outcome = _record()
    passing_constraint = _record(id="policy_compliance", role="constraint")
    report = _report(
        passing_outcome,
        passing_constraint,
    )
    assert report.conclusion == "pass"

    failed_constraint = _record(id="policy_compliance", role="constraint", value=False)
    failed = _report(
        passing_outcome,
        failed_constraint,
        conclusion="fail",
    )
    assert failed.conclusion == "fail"
    with pytest.raises(ValidationError, match="decision record values"):
        _report(
            passing_outcome,
            failed_constraint,
            conclusion="pass",
        )
    with pytest.raises(ValidationError, match="decision record values"):
        _report(conclusion="fail")


def test_public_result_schemas_validate_model_json_and_reject_unknown_fields() -> None:
    result_schema = json.loads((SCHEMA_DIRECTORY / "result-record-v1.schema.json").read_text())
    report_schema = json.loads((SCHEMA_DIRECTORY / "evaluation-report-v1.schema.json").read_text())
    Draft202012Validator.check_schema(result_schema)
    Draft202012Validator.check_schema(report_schema)

    record_payload = _record().model_dump(mode="json", exclude_none=False)
    Draft202012Validator(result_schema).validate(record_payload)

    unknown = copy.deepcopy(record_payload)
    unknown["private_hint"] = True
    assert not Draft202012Validator(result_schema).is_valid(unknown)
    whitespace_reason = _record(
        value=None,
        validity="unavailable",
        failure_reason="runtime_unavailable",
        evidence_refs=(),
    ).model_dump(mode="json", exclude_none=False)
    whitespace_reason["failure_reason"] = " "
    assert not Draft202012Validator(result_schema).is_valid(whitespace_reason)

    report_payload = _report().model_dump(mode="json", exclude_none=False)
    registry = Registry().with_resource(
        "result-record-v1.schema.json",
        Resource.from_contents(result_schema),
    )
    report_validator = Draft202012Validator(report_schema, registry=registry)
    report_validator.validate(report_payload)
    report_without_records = {**report_payload, "records": []}
    assert not report_validator.is_valid(report_without_records)

    diagnostic_only = copy.deepcopy(report_payload)
    diagnostic_only["records"] = [
        _record(
            id="tool_calls",
            role="diagnostic",
            value=1,
            value_type="integer",
            unit="calls",
            direction="lower_is_better",
        ).model_dump(mode="json", exclude_none=False)
    ]
    assert not report_validator.is_valid(diagnostic_only)

    false_decision = _report(
        _record(value=False),
        conclusion="fail",
    ).model_dump(mode="json", exclude_none=False)
    report_validator.validate(false_decision)
    false_decision["conclusion"] = "pass"
    assert not report_validator.is_valid(false_decision)

    invalid_report = _report(
        _record(
            value=None,
            validity="invalid",
            failure_reason="contradictory_evidence",
        ),
        conclusion="inconclusive",
        evaluation_validity="invalid",
    ).model_dump(mode="json", exclude_none=False)
    report_validator.validate(invalid_report)
    invalid_report["evaluation_validity"] = "unavailable"
    assert not report_validator.is_valid(invalid_report)

    unavailable_report = _report(
        _record(
            value=None,
            validity="unavailable",
            failure_reason="runtime_unavailable",
            evidence_refs=(),
        ),
        conclusion="inconclusive",
        evaluation_validity="unavailable",
    ).model_dump(mode="json", exclude_none=False)
    report_validator.validate(unavailable_report)
    unavailable_report["evaluation_validity"] = "invalid"
    assert not report_validator.is_valid(unavailable_report)

    numeric_outcome = copy.deepcopy(record_payload)
    numeric_outcome.update(
        value=1,
        value_type="integer",
        unit="count",
        direction="higher_is_better",
    )
    assert not Draft202012Validator(result_schema).is_valid(numeric_outcome)


def test_audit_payloads_have_matching_schema_and_model_acceptance() -> None:
    result_schema = json.loads((SCHEMA_DIRECTORY / "result-record-v1.schema.json").read_text())
    report_schema = json.loads((SCHEMA_DIRECTORY / "evaluation-report-v1.schema.json").read_text())
    result_validator = Draft202012Validator(result_schema)
    registry = Registry().with_resource(
        "result-record-v1.schema.json",
        Resource.from_contents(result_schema),
    )
    report_validator = Draft202012Validator(report_schema, registry=registry)

    report_payload = _report().model_dump(mode="json", exclude_none=False)
    report_validator.validate(report_payload)
    assert (
        EvaluationReport.model_validate_json(json.dumps(report_payload)).evaluation_id
        == "evaluation-1"
    )

    redundant_report_id = {**report_payload, "report_id": "imported-report-deadbeef"}
    assert not report_validator.is_valid(redundant_report_id)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EvaluationReport.model_validate_json(json.dumps(redundant_report_id))

    duplicate_ids = copy.deepcopy(report_payload)
    duplicate_ids["records"].append(copy.deepcopy(duplicate_ids["records"][0]))
    report_validator.validate(duplicate_ids)
    assert len(EvaluationReport.model_validate_json(json.dumps(duplicate_ids)).records) == 2

    reversed_references = _record(
        evidence_refs=(_reference("artifact:b"), _reference("artifact:a")),
    ).model_dump(mode="json", exclude_none=False)
    reversed_references["evidence_refs"].reverse()
    result_validator.validate(reversed_references)
    normalized = ResultRecord.model_validate_json(json.dumps(reversed_references))
    assert tuple(reference.locator for reference in normalized.evidence_refs) == (
        "artifact:a",
        "artifact:b",
    )

    duplicate_references = copy.deepcopy(reversed_references)
    duplicate_references["evidence_refs"] = [
        copy.deepcopy(duplicate_references["evidence_refs"][0]),
        copy.deepcopy(duplicate_references["evidence_refs"][0]),
    ]
    result_validator.validate(duplicate_references)
    assert (
        len(ResultRecord.model_validate_json(json.dumps(duplicate_references)).evidence_refs) == 2
    )

    missing_and_null_digest = copy.deepcopy(duplicate_references)
    missing_and_null_digest["evidence_refs"][0].pop("sha256")
    missing_and_null_digest["evidence_refs"][1]["sha256"] = None
    result_validator.validate(missing_and_null_digest)
    normalized_digests = ResultRecord.model_validate_json(json.dumps(missing_and_null_digest))
    assert tuple(reference.sha256 for reference in normalized_digests.evidence_refs) == (
        None,
        None,
    )

    integral_float = _record(
        id="tool_calls",
        role="diagnostic",
        value=1,
        value_type="integer",
        unit="calls",
        direction="lower_is_better",
    ).model_dump(mode="json", exclude_none=False)
    integral_float["value"] = 1.0
    result_validator.validate(integral_float)
    normalized_integer = ResultRecord.model_validate_json(json.dumps(integral_float))
    assert normalized_integer.value == 1
    assert type(normalized_integer.value) is int

    for boundary in (
        -MAX_ABSOLUTE_INTEGER_RESULT_VALUE,
        MAX_ABSOLUTE_INTEGER_RESULT_VALUE,
    ):
        safe_integral_float = {**integral_float, "value": float(boundary)}
        result_validator.validate(safe_integral_float)
        normalized_boundary = ResultRecord.model_validate_json(json.dumps(safe_integral_float))
        assert normalized_boundary.value == boundary
        assert type(normalized_boundary.value) is int

    unsafe_integer = {
        **integral_float,
        "value": MAX_ABSOLUTE_INTEGER_RESULT_VALUE + 1,
    }
    assert not result_validator.is_valid(unsafe_integer)
    with pytest.raises(ValidationError, match="JSON safe-integer range"):
        ResultRecord.model_validate_json(json.dumps(unsafe_integer))

    raw_rounded_integer = json.dumps(integral_float, separators=(",", ":")).replace(
        '"value":1.0',
        '"value":9007199254740993.0',
    )
    parsed_rounded_integer = strict_json_loads(raw_rounded_integer)
    assert parsed_rounded_integer["value"] == 9_007_199_254_740_992.0
    assert not result_validator.is_valid(parsed_rounded_integer)
    with pytest.raises(ValidationError, match="JSON safe-integer range"):
        ResultRecord.model_validate_json(raw_rounded_integer)

    boundary_number = {**integral_float, "value_type": "number"}
    boundary_number["value"] = MAX_ABSOLUTE_RESULT_VALUE
    result_validator.validate(boundary_number)
    assert (
        ResultRecord.model_validate_json(json.dumps(boundary_number)).value
        == MAX_ABSOLUTE_RESULT_VALUE
    )

    for value_type, value in (("integer", 10**309), ("number", 10**309)):
        out_of_range = {**integral_float, "value_type": value_type, "value": value}
        assert not result_validator.is_valid(out_of_range)
        with pytest.raises(ValidationError):
            ResultRecord.model_validate_json(json.dumps(out_of_range))

    overflow = {**boundary_number, "value": float("inf")}
    assert not result_validator.is_valid(overflow)
    with pytest.raises(ContractError, match="non-finite JSON number"):
        strict_json_loads(json.dumps(overflow))

    not_a_number = {**boundary_number, "value": float("nan")}
    with pytest.raises(ContractError, match="non-finite JSON number"):
        strict_json_loads(json.dumps(not_a_number))
