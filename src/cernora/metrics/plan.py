"""Explicit, authority-bound Metric composition. No execution or discovery."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import Field, JsonValue

from cernora.core.canonical import canonical_json
from cernora.core.case import CaseProfile, StrictModel
from cernora.core.evidence import EvidenceReference
from cernora.core.result import ResultDirection, ResultRecord, ResultValueType
from cernora.core.score import ScoreObservation
from cernora.ingestion.contracts_v2 import AuthorityBoundImportPackageV2
from cernora.profile import ProfileEvaluationContext


def strict_json(raw: str | bytes) -> JsonValue:
    def pairs(items: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ValueError("nonfinite JSON")

    value: JsonValue = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    # Pydantic validates recursive JSON types; canonical serialization rejects nonfinite values.
    canonical_json(value)
    return value


class MetricDefinition(StrictModel):
    metric_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    metric_version: str = Field(min_length=1)
    value_type: ResultValueType
    unit: str | None = None
    direction: ResultDirection | None = None


@dataclass(frozen=True)
class MetricCall:
    invocation_id: str
    tool: str
    argv: tuple[str, ...]
    status: str
    delivered: bool


@dataclass(frozen=True)
class MetricContext:
    """Immutable snapshot of already validated evidence, with no filesystem access."""

    calls: tuple[MetricCall, ...]
    trace_complete: bool
    receipt: EvidenceReference
    artifacts: tuple[tuple[str, bytes, EvidenceReference], ...]
    terminal_artifact: str | None
    delivered_outputs: tuple[str, ...]

    @classmethod
    def from_import(
        cls, package: AuthorityBoundImportPackageV2, context: ProfileEvaluationContext
    ) -> MetricContext:
        bundle = package.content.bundle
        artifacts = []
        for artifact in bundle.artifacts:
            raw = package.content.artifact_bytes[artifact.artifact_id]
            if hashlib.sha256(raw).hexdigest() != artifact.sha256:
                raise ValueError("metric artifact digest mismatch")
            artifacts.append(
                (
                    artifact.artifact_id,
                    raw,
                    EvidenceReference(
                        evidence_id=context.evidence_id,
                        locator=f"artifacts/{artifact.path}",
                        sha256=artifact.sha256,
                    ),
                )
            )
        return cls(
            calls=tuple(
                MetricCall(a.invocation_id, a.tool, a.argv, a.result.status, a.result.delivered)
                for a in bundle.tool_actions
            ),
            trace_complete=bundle.terminal.status == "completed",
            receipt=EvidenceReference(
                evidence_id=context.evidence_id,
                locator="source-import/import-receipt.json",
                sha256=context.source_receipt_sha256,
            ),
            artifacts=tuple(artifacts),
            terminal_artifact=(
                bundle.terminal.answer.artifact.artifact_id
                if bundle.terminal.answer is not None
                else None
            ),
            delivered_outputs=tuple(
                a.result.stdout_artifact.artifact_id
                for a in bundle.tool_actions
                if a.result.delivered and a.result.status == "completed" and a.result.exit_code == 0
            ),
        )

    def artifact(self, artifact_id: str) -> tuple[bytes, EvidenceReference]:
        for identity, raw, reference in self.artifacts:
            if identity == artifact_id:
                return raw, reference
        raise ValueError("metric artifact unavailable")

    def json_artifact(self, artifact_id: str) -> tuple[JsonValue, EvidenceReference]:
        """Decode one bound artifact strictly; each call returns a fresh JSON value."""
        raw, reference = self.artifact(artifact_id)
        return strict_json(raw), reference

    def references_valid(self, refs: tuple[EvidenceReference, ...]) -> bool:
        allowed = (self.receipt, *(r for _, _, r in self.artifacts))
        return len(refs) == len(set(r.model_dump_json() for r in refs)) and all(
            ref in allowed for ref in refs
        )


class Metric(Protocol):
    @property
    def definition(self) -> MetricDefinition: ...

    def validate_parameters(self, parameters_json: str) -> None: ...

    def evaluate(self, context: MetricContext, parameters_json: str) -> ResultRecord: ...


@dataclass(frozen=True)
class MetricBinding:
    metric: Metric
    role: Literal["required", "advisory", "diagnostic"] = "diagnostic"
    parameters_json: str = "{}"
    maximum: int | float | None = None

    def __post_init__(self) -> None:
        if self.role not in {"required", "advisory", "diagnostic"}:
            raise ValueError("unknown metric role")
        definition = MetricDefinition.model_validate_json(self.metric.definition.model_dump_json())
        numeric = definition.value_type in {"integer", "number"}
        if numeric != (definition.unit is not None and definition.direction is not None):
            raise ValueError("metric units/direction must match value type")
        if not numeric and (definition.unit is not None or definition.direction is not None):
            raise ValueError("non-numeric metric cannot declare units")
        if self.maximum is not None:
            if type(self.maximum) not in {int, float} or not numeric or self.role != "required":
                raise ValueError("maximum requires a required numeric metric")
            canonical_json(self.maximum)
        if self.role == "required" and definition.value_type != "boolean" and self.maximum is None:
            raise ValueError("required numeric metrics need an explicit maximum")
        value = strict_json(self.parameters_json)
        if not isinstance(value, dict):
            raise ValueError("metric parameters must be a JSON object")
        canonical = canonical_json(value).decode()
        self.metric.validate_parameters(canonical)
        object.__setattr__(self, "parameters_json", canonical)

    def manifest(self) -> dict[str, JsonValue]:
        return {
            "metric": strict_json(self.metric.definition.model_dump_json()),
            "role": self.role,
            "parameters": strict_json(self.parameters_json),
            "maximum": self.maximum,
        }


@dataclass(frozen=True)
class MetricPlan:
    metrics: tuple[MetricBinding, ...]
    version: str = "cernora.metric-plan/v1"

    def __post_init__(self) -> None:
        if self.version != "cernora.metric-plan/v1" or type(self.metrics) is not tuple:
            raise ValueError("unsupported metric plan")
        ids = [b.metric.definition.metric_id for b in self.metrics]
        output_ids = ids + [
            b.metric.definition.metric_id + ".value" for b in self.metrics if b.maximum is not None
        ]
        if not ids or len(set(output_ids)) != len(output_ids):
            raise ValueError("metric output IDs must be nonempty and unique")
        if not self.required_observations:
            raise ValueError("metric plan needs at least one required binding")

    @property
    def required_observations(self) -> tuple[str, ...]:
        return tuple(b.metric.definition.metric_id for b in self.metrics if b.role == "required")

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json(
            {"version": self.version, "metrics": [b.manifest() for b in self.metrics]}
        )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def scorer_version(self) -> str:
        return "metric-plan/v1/" + self.sha256

    def validate_authority(self, authority: CaseProfile) -> None:
        if (
            authority.scorer_policy.policy_version != self.scorer_version
            or authority.scorer_policy.required_observations != self.required_observations
        ):
            raise ValueError("metric plan does not match scorer authority")

    def evaluate(self, context: MetricContext, authority: CaseProfile) -> tuple[ResultRecord, ...]:
        self.validate_authority(authority)
        frozen = self.canonical_bytes
        records = []
        for binding in self.metrics:
            definition = binding.metric.definition
            try:
                raw = binding.metric.evaluate(context, binding.parameters_json)
                record = ResultRecord.model_validate_json(raw.model_dump_json())
                if (
                    record.id != definition.metric_id
                    or record.role != "diagnostic"
                    or record.value_type != definition.value_type
                    or record.unit != definition.unit
                    or record.direction != definition.direction
                    or not context.references_valid(record.evidence_refs)
                ):
                    raise ValueError("metric result contract mismatch")
            except Exception:
                # Deliberately stable: exception text can contain secrets or nondeterministic paths.
                record = ResultRecord(
                    id=definition.metric_id,
                    version="agent.evaluator.result-record/v1",
                    role="diagnostic",
                    value=None,
                    value_type=definition.value_type,
                    validity="invalid",
                    failure_reason="metric_execution_or_contract_error",
                    evidence_refs=(context.receipt,),
                    unit=definition.unit,
                    direction=definition.direction,
                )
            if binding.maximum is not None:
                records.append(
                    ResultRecord.model_validate_json(
                        record.model_copy(update={"id": record.id + ".value"}).model_dump_json()
                    )
                )
                assert record.value is None or type(record.value) in {int, float}
                value = None if record.value is None else float(record.value) <= binding.maximum
                record = ResultRecord.model_validate_json(
                    record.model_copy(
                        update={
                            "value": value,
                            "value_type": "boolean",
                            "unit": None,
                            "direction": None,
                        }
                    ).model_dump_json()
                )
            role = "constraint" if binding.role == "required" else binding.role
            records.append(
                ResultRecord.model_validate_json(
                    record.model_copy(update={"role": role}).model_dump_json()
                )
            )
        if frozen != self.canonical_bytes:
            raise ValueError("metric plan changed during evaluation")
        self.validate_authority(authority)
        return tuple(records)

    def observations(self, records: tuple[ResultRecord, ...]) -> tuple[ScoreObservation, ...]:
        indexed = {r.id: r for r in records}
        observations = []
        for identity in self.required_observations:
            record = indexed[identity]
            if record.role != "constraint" or record.value_type != "boolean":
                raise ValueError("required records must be boolean constraints")
            if record.value is not None and type(record.value) is not bool:
                raise ValueError("invalid required value")
            observations.append(
                ScoreObservation(
                    observation_id=identity,
                    applicability=(
                        "observed"
                        if record.validity == "valid"
                        else "not_applicable"
                        if record.validity == "not_applicable"
                        else "invalid"
                    ),
                    value=record.value is True if record.validity == "valid" else None,
                    reason=record.failure_reason,
                    evidence_references=record.evidence_refs,
                )
            )
        return tuple(observations)
