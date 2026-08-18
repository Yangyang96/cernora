"""Preview contracts for evidence-derived single-run evaluation results."""

from __future__ import annotations

import math
from typing import Literal, Self

from pydantic import Field, model_validator

from cernora.core.case import StrictModel
from cernora.core.evidence import EvidenceReference, evidence_reference_sort_key
from cernora.core.identity import SHA256_PATTERN

RESULT_RECORD_VERSION = "agent.evaluator.result-record/v1"
EVALUATION_REPORT_SCHEMA_VERSION = "agent.evaluator.evaluation-report/v1"
MAX_ABSOLUTE_INTEGER_RESULT_VALUE = 9_007_199_254_740_991
MAX_ABSOLUTE_RESULT_VALUE = 1e308

ResultRole = Literal["outcome", "constraint", "advisory", "diagnostic"]
ResultValueType = Literal["boolean", "integer", "number", "string"]
ResultValidity = Literal["valid", "invalid", "unavailable", "not_applicable"]
ResultDirection = Literal["higher_is_better", "lower_is_better", "neutral"]
ResultValue = bool | int | float | str | None


class ResultRecord(StrictModel):
    """One typed observation or measurement derived from Evidence."""

    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    version: Literal["agent.evaluator.result-record/v1"]
    role: ResultRole
    value: ResultValue
    value_type: ResultValueType
    validity: ResultValidity
    failure_reason: str | None
    evidence_refs: tuple[EvidenceReference, ...]
    unit: str | None = Field(min_length=1)
    direction: ResultDirection | None

    @model_validator(mode="after")
    def coherent_result(self) -> Self:
        if self.validity == "valid":
            if self.value is None:
                raise ValueError("valid result records require a decision value")
            if self.failure_reason is not None:
                raise ValueError("valid result records cannot carry a failure reason")
            if not self.evidence_refs:
                raise ValueError("valid result records must reference Evidence")
        else:
            if self.value is not None:
                raise ValueError("non-valid result records cannot carry a decision value")
            if self.failure_reason is None or not self.failure_reason.strip():
                raise ValueError("non-valid result records require a deterministic failure reason")

        integer_value = self.value_type == "integer" and (
            type(self.value) is int
            or (type(self.value) is float and math.isfinite(self.value) and self.value.is_integer())
        )
        value_matches_type = self.value is None or (
            (self.value_type == "boolean" and type(self.value) is bool)
            or integer_value
            or (self.value_type == "number" and type(self.value) in {int, float})
            or (self.value_type == "string" and type(self.value) is str)
        )
        if not value_matches_type:
            raise ValueError("result value does not match its declared value_type")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("numeric result values must be finite")
        if (
            self.value_type == "integer"
            and isinstance(self.value, int | float)
            and not isinstance(self.value, bool)
            and abs(self.value) > MAX_ABSOLUTE_INTEGER_RESULT_VALUE
        ):
            raise ValueError("integer result values must be within the JSON safe-integer range")
        if (
            self.value_type == "number"
            and isinstance(self.value, int | float)
            and not isinstance(self.value, bool)
            and abs(self.value) > MAX_ABSOLUTE_RESULT_VALUE
        ):
            raise ValueError(f"numeric result values must be within +/-{MAX_ABSOLUTE_RESULT_VALUE}")
        if self.value_type == "integer" and type(self.value) is float:
            object.__setattr__(self, "value", int(self.value))

        numeric = self.value_type in {"integer", "number"}
        if self.role in {"outcome", "constraint"} and self.value_type != "boolean":
            raise ValueError("outcome and constraint result records must be boolean")
        if self.validity == "valid" and numeric and (not self.unit or self.direction is None):
            raise ValueError("valid numeric result records require unit and direction")
        if not numeric and (self.unit is not None or self.direction is not None):
            raise ValueError("non-numeric result records cannot declare unit or direction")
        if numeric and ((self.unit is None) != (self.direction is None)):
            raise ValueError("numeric unit and direction must be declared together")

        object.__setattr__(
            self,
            "evidence_refs",
            tuple(sorted(self.evidence_refs, key=evidence_reference_sort_key)),
        )
        return self


class EvaluationReport(StrictModel):
    """Authority- and input-bound Preview report for one completed evaluation."""

    schema_version: Literal["agent.evaluator.evaluation-report/v1"]
    evaluation_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    score_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    evaluation_input_sha256: str = Field(pattern=SHA256_PATTERN)
    authority_id: str = Field(min_length=1)
    authority_sha256: str = Field(pattern=SHA256_PATTERN)
    conclusion: Literal["pass", "fail", "inconclusive"]
    evaluation_validity: Literal["valid", "invalid", "unavailable"]
    records: tuple[ResultRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def coherent_report(self) -> Self:
        decision_records = tuple(
            record for record in self.records if record.role in {"outcome", "constraint"}
        )
        if not decision_records:
            raise ValueError("evaluation reports require at least one decision record")

        decision_validities = {record.validity for record in decision_records}
        if "invalid" in decision_validities:
            expected_validity = "invalid"
        elif decision_validities.intersection({"unavailable", "not_applicable"}):
            expected_validity = "unavailable"
        else:
            expected_validity = "valid"
        if self.evaluation_validity != expected_validity:
            raise ValueError("evaluation validity must match decision record validity")
        if (self.conclusion == "inconclusive") != (self.evaluation_validity != "valid"):
            raise ValueError("report conclusion must match evaluation validity")
        if self.evaluation_validity == "valid":
            all_decisions_pass = all(record.value is True for record in decision_records)
            expected_conclusion = "pass" if all_decisions_pass else "fail"
            if self.conclusion != expected_conclusion:
                raise ValueError("report conclusion must match decision record values")
        return self


__all__ = [
    "EVALUATION_REPORT_SCHEMA_VERSION",
    "MAX_ABSOLUTE_INTEGER_RESULT_VALUE",
    "MAX_ABSOLUTE_RESULT_VALUE",
    "RESULT_RECORD_VERSION",
    "EvaluationReport",
    "ResultDirection",
    "ResultRecord",
    "ResultRole",
    "ResultValidity",
    "ResultValueType",
]
