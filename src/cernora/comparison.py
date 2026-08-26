"""Strict controlled-comparison Preview contracts and deterministic statistics."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cernora._closed_package import ordinary_tree_files, publish_closed_package
from cernora.batch import BatchInput, BatchOutcome, BatchRate, BatchTrial
from cernora.core.canonical import canonical_json, decode_contract
from cernora.core.case import StrictModel
from cernora.core.errors import ContractError
from cernora.core.evidence_bundle_v2 import BundleCaseIdentity
from cernora.core.identity import SHA256_PATTERN
from cernora.evaluation.contracts import ImportedEvaluationReceipt
from cernora.evaluation.package import validate_evaluation_package_content
from cernora.ingestion.errors import IngestionIntegrityError

COMPARISON_INPUT_SCHEMA_VERSION = "agent.evaluator.comparison-input/v1"
COMPARISON_SUMMARY_SCHEMA_VERSION = "agent.evaluator.comparison-summary/v1"
TREATMENT_SCHEMA_VERSION = "agent.evaluator.treatment/v1"
BOOTSTRAP_METHOD = "case-clustered-paired-bootstrap/v1"
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_CONFIDENCE_BASIS_POINTS = 9_500
BOOTSTRAP_DOMAIN = b"agent.evaluator.case-clustered-paired-bootstrap/v1\0"
COMPARISON_INPUT_PATH = "comparison-input.json"
COMPARISON_SUMMARY_PATH = "comparison-summary.json"
COMPARISON_MARKDOWN_PATH = "comparison-summary.md"
COMPARISON_RECEIPT_PATH = "comparison-summary-receipt.json"
COMPARISON_MANIFEST_PATH = "digests.json"

IDENTIFIER_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"
TreatmentKind = Literal[
    "prompt_instruction",
    "model",
    "tool_schema",
    "generation_configuration",
    "runtime_version",
]
GuardrailMetric = Literal[
    "evaluation_validity_rate",
    "reliable_success_rate",
    "profile_failure_code_rate",
]
ComparisonConclusion = Literal[
    "improved",
    "no_change",
    "uncertain",
    "mixed",
    "regressed",
    "not_comparable",
]


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class TreatmentChange(StrictModel):
    """One declared semantic difference between controlled arms."""

    kind: TreatmentKind
    baseline_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def changed(self) -> Self:
        if self.baseline_sha256 == self.candidate_sha256:
            raise ValueError("Treatment change endpoints must differ")
        return self


class Treatment(StrictModel):
    """A content-identified, closed declaration of permitted arm differences."""

    schema_version: Literal["agent.evaluator.treatment/v1"]
    treatment_id: str = Field(min_length=1)
    treatment_sha256: str = Field(pattern=SHA256_PATTERN)
    changes: Annotated[tuple[TreatmentChange, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def identity_and_order(self) -> Self:
        kinds = tuple(item.kind for item in self.changes)
        if kinds != tuple(sorted(kinds)) or len(kinds) != len(set(kinds)):
            raise ValueError("Treatment changes must be sorted and unique by kind")
        payload = self.model_dump(mode="json", exclude={"treatment_id", "treatment_sha256"})
        digest = _sha256(payload)
        if self.treatment_sha256 != digest or self.treatment_id != f"treatment-{digest}":
            raise ValueError("Treatment identity does not match canonical content")
        return self


def materialize_treatment(changes: Sequence[TreatmentChange]) -> Treatment:
    """Create one canonical Treatment from predeclared changes."""

    ordered = tuple(sorted(changes, key=lambda item: item.kind))
    payload: dict[str, object] = {
        "schema_version": TREATMENT_SCHEMA_VERSION,
        "changes": [item.model_dump(mode="json") for item in ordered],
    }
    digest = _sha256(payload)
    payload["treatment_id"] = f"treatment-{digest}"
    payload["treatment_sha256"] = digest
    return decode_contract(canonical_json(payload), Treatment)


class ExperimentProjection(StrictModel):
    """Core-owned neutral projection extracted from one Experiment authority."""

    runtime_version_sha256: str = Field(pattern=SHA256_PATTERN)
    model_sha256: str = Field(pattern=SHA256_PATTERN)
    prompt_instruction_sha256: str = Field(pattern=SHA256_PATTERN)
    tool_schema_sha256: str = Field(pattern=SHA256_PATTERN)
    generation_configuration_sha256: str = Field(pattern=SHA256_PATTERN)
    timeout_sha256: str = Field(pattern=SHA256_PATTERN)
    resources_sha256: str = Field(pattern=SHA256_PATTERN)
    retry_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    dataset_sha256: str = Field(pattern=SHA256_PATTERN)
    profile_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_authority_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    report_contract_sha256: str = Field(pattern=SHA256_PATTERN)
    statistical_plan_sha256: str = Field(pattern=SHA256_PATTERN)


class ExperimentAuthority(StrictModel):
    """Canonical authority whose digest is the selected Batch Experiment identity."""

    schema_version: Literal["agent.evaluator.comparison-experiment-authority/v1"]
    experiment_id: str = Field(pattern=SHA256_PATTERN)
    experiment_sha256: str = Field(pattern=SHA256_PATTERN)
    configuration_id: str = Field(pattern=IDENTIFIER_PATTERN)
    case: BundleCaseIdentity
    projection: ExperimentProjection

    @model_validator(mode="after")
    def canonical_experiment_identity(self) -> Self:
        payload = self.model_dump(mode="json", exclude={"experiment_id", "experiment_sha256"})
        digest = _sha256(payload)
        if self.experiment_id != digest or self.experiment_sha256 != digest:
            raise ValueError("Experiment authority identity does not match canonical content")
        return self


def materialize_experiment_authority(
    payload_without_identity: Mapping[str, object],
) -> ExperimentAuthority:
    """Materialize one canonical neutral Experiment authority."""

    if {"experiment_id", "experiment_sha256"}.intersection(payload_without_identity):
        raise ValueError("Experiment authority materialization payload must omit identity fields")
    payload = dict(payload_without_identity)
    digest = _sha256(payload)
    payload["experiment_id"] = digest
    payload["experiment_sha256"] = digest
    return decode_contract(canonical_json(payload), ExperimentAuthority)


class ComparisonArm(StrictModel):
    """One ordered role selecting a configuration from bound Experiment authorities."""

    configuration_id: str = Field(pattern=IDENTIFIER_PATTERN)


class ComparisonCase(StrictModel):
    """One paired Case and its predeclared split and Experiment bindings."""

    case: BundleCaseIdentity
    split_id: str = Field(pattern=IDENTIFIER_PATTERN)
    baseline_experiment_id: str = Field(pattern=SHA256_PATTERN)
    candidate_experiment_id: str = Field(pattern=SHA256_PATTERN)


class PrimaryOutcome(StrictModel):
    metric: Literal["reliable_success_rate"]
    scope: Literal["all"]
    direction: Literal["higher_is_better"]
    practical_threshold_basis_points: int = Field(ge=0, le=10_000)


class ComparisonGuardrail(StrictModel):
    guardrail_id: str = Field(pattern=IDENTIFIER_PATTERN)
    hard: Literal[True]
    metric: GuardrailMetric
    scope: Literal["all", "split"]
    split_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    direction: Literal["higher_is_better", "lower_is_better"]
    max_adverse_basis_points: int = Field(ge=0, le=10_000)
    profile_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    profile_version: str | None = None
    failure_code: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)

    @model_validator(mode="after")
    def coherent_metric(self) -> Self:
        if (self.scope == "split") != (self.split_id is not None):
            raise ValueError("split-scoped Guardrail requires exactly one split ID")
        failure_fields = (self.profile_id, self.profile_version, self.failure_code)
        if self.metric == "profile_failure_code_rate":
            if self.direction != "lower_is_better" or any(item is None for item in failure_fields):
                raise ValueError(
                    "failure-code Guardrail requires lower-is-better Profile authority"
                )
        elif any(item is not None for item in failure_fields):
            raise ValueError("non-failure Guardrail cannot declare a failure code")
        elif self.direction != "higher_is_better":
            raise ValueError("success and validity Guardrails must be higher-is-better")
        return self


class BootstrapPlan(StrictModel):
    method: Literal["case-clustered-paired-bootstrap/v1"]
    confidence_basis_points: Literal[9500]
    resamples: Literal[10000]
    percentile: Literal["nearest_rank_closed"]
    seed_source: Literal["comparison_input_sha256"]


class PassKPlan(StrictModel):
    k: int = Field(gt=0)
    independent_trials: Literal[True]


class ComparisonInput(StrictModel):
    """Identity-closed declaration and full Trial evidence for one comparison."""

    schema_version: Literal["agent.evaluator.comparison-input/v1"]
    comparison_id: str = Field(min_length=1)
    comparison_input_sha256: str = Field(pattern=SHA256_PATTERN)
    batch_input: BatchInput
    baseline: ComparisonArm
    candidate: ComparisonArm
    experiment_authorities: Annotated[tuple[ExperimentAuthority, ...], Field(min_length=2)]
    cases: Annotated[tuple[ComparisonCase, ...], Field(min_length=1)]
    treatment: Treatment
    primary_outcome: PrimaryOutcome
    guardrails: Annotated[tuple[ComparisonGuardrail, ...], Field(min_length=1)]
    bootstrap: BootstrapPlan
    pass_k: PassKPlan | None = None

    @model_validator(mode="after")
    def complete_pairing_and_identity(self) -> Self:
        if self.baseline.configuration_id == self.candidate.configuration_id:
            raise ValueError("comparison arms require distinct configurations")
        configuration_ids = {item.configuration_id for item in self.batch_input.planned_trials}
        selected = {self.baseline.configuration_id, self.candidate.configuration_id}
        if configuration_ids != selected:
            raise ValueError("Batch Input must contain exactly the two selected configurations")
        case_ids = tuple(item.case.case_id for item in self.cases)
        if case_ids != tuple(sorted(case_ids)) or len(case_ids) != len(set(case_ids)):
            raise ValueError("Comparison Cases must be sorted and unique")
        if set(case_ids) != {item.case_id for item in self.batch_input.planned_trials}:
            raise ValueError("Comparison Cases do not exhaust the Batch Input")
        authority_coordinates = tuple(
            (item.case.case_id, item.configuration_id) for item in self.experiment_authorities
        )
        if authority_coordinates != tuple(sorted(authority_coordinates)) or len(
            authority_coordinates
        ) != len(set(authority_coordinates)):
            raise ValueError("Experiment authorities must be sorted and unique")
        expected_authority_coordinates = {
            (case_id, configuration_id) for case_id in case_ids for configuration_id in selected
        }
        if set(authority_coordinates) != expected_authority_coordinates:
            raise ValueError("Experiment authorities do not exhaust selected Case cells")
        authorities = {
            (item.case.case_id, item.configuration_id): item for item in self.experiment_authorities
        }
        guardrail_ids = tuple(item.guardrail_id for item in self.guardrails)
        if guardrail_ids != tuple(sorted(guardrail_ids)) or len(guardrail_ids) != len(
            set(guardrail_ids)
        ):
            raise ValueError("Guardrails must be sorted and unique")
        known_splits = {item.split_id for item in self.cases}
        if any(
            item.scope == "split" and item.split_id not in known_splits for item in self.guardrails
        ):
            raise ValueError("Guardrail references an unknown split")
        planned = {
            (item.case_id, item.configuration_id, item.repetition): item
            for item in self.batch_input.planned_trials
        }
        for case in self.cases:
            baseline_repetitions = sorted(
                repetition
                for case_id, configuration_id, repetition in planned
                if case_id == case.case.case_id
                and configuration_id == self.baseline.configuration_id
            )
            candidate_repetitions = sorted(
                repetition
                for case_id, configuration_id, repetition in planned
                if case_id == case.case.case_id
                and configuration_id == self.candidate.configuration_id
            )
            if not baseline_repetitions or baseline_repetitions != candidate_repetitions:
                raise ValueError("comparison arms require exact paired repetitions per Case")
            baseline_experiments = {
                planned[
                    (case.case.case_id, self.baseline.configuration_id, repetition)
                ].experiment_id
                for repetition in baseline_repetitions
            }
            candidate_experiments = {
                planned[
                    (case.case.case_id, self.candidate.configuration_id, repetition)
                ].experiment_id
                for repetition in candidate_repetitions
            }
            if baseline_experiments != {case.baseline_experiment_id} or candidate_experiments != {
                case.candidate_experiment_id
            }:
                raise ValueError("Comparison Case does not bind the selected Experiments")
            baseline_authority = authorities[(case.case.case_id, self.baseline.configuration_id)]
            candidate_authority = authorities[(case.case.case_id, self.candidate.configuration_id)]
            if (
                baseline_authority.case != case.case
                or candidate_authority.case != case.case
                or baseline_authority.experiment_id != case.baseline_experiment_id
                or candidate_authority.experiment_id != case.candidate_experiment_id
            ):
                raise ValueError("Comparison Case is not bound to Experiment authority")
        payload = self.model_dump(mode="json", exclude={"comparison_id", "comparison_input_sha256"})
        digest = _sha256(payload)
        if self.comparison_input_sha256 != digest or self.comparison_id != f"comparison-{digest}":
            raise ValueError("Comparison Input identity does not match canonical content")
        return self


def materialize_comparison_input(payload_without_identity: Mapping[str, object]) -> ComparisonInput:
    """Add the canonical identity to one complete controlled-comparison declaration."""

    if {"comparison_id", "comparison_input_sha256"}.intersection(payload_without_identity):
        raise ValueError("Comparison Input materialization payload must omit identity fields")
    payload = dict(payload_without_identity)
    digest = _sha256(payload)
    payload["comparison_id"] = f"comparison-{digest}"
    payload["comparison_input_sha256"] = digest
    return decode_contract(canonical_json(payload), ComparisonInput)


class ComparisonEstimate(StrictModel):
    numerator: int
    denominator: int = Field(gt=0)
    value: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def exact_value(self) -> Self:
        if not math.isclose(self.value, self.numerator / self.denominator, rel_tol=0, abs_tol=0):
            raise ValueError("estimate value does not match its exact fraction")
        return self


class ComparisonInterval(StrictModel):
    lower: ComparisonEstimate
    upper: ComparisonEstimate

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if Fraction(self.lower.numerator, self.lower.denominator) > Fraction(
            self.upper.numerator, self.upper.denominator
        ):
            raise ValueError("comparison interval bounds are reversed")
        return self


class PrimaryResult(StrictModel):
    metric: Literal["reliable_success_rate"]
    baseline: BatchRate
    candidate: BatchRate
    delta: ComparisonEstimate
    interval: ComparisonInterval

    @model_validator(mode="after")
    def exact_delta(self) -> Self:
        expected = Fraction(self.candidate.numerator, self.candidate.denominator) - Fraction(
            self.baseline.numerator, self.baseline.denominator
        )
        actual = Fraction(self.delta.numerator, self.delta.denominator)
        if actual != expected:
            raise ValueError("Primary delta does not match arm rates")
        return self


class GuardrailResult(StrictModel):
    guardrail_id: str = Field(pattern=IDENTIFIER_PATTERN)
    status: Literal["satisfied", "violated", "uncertain", "unavailable"]
    baseline: BatchRate | None
    candidate: BatchRate | None
    oriented_delta: ComparisonEstimate | None
    interval: ComparisonInterval | None
    unavailable_cases: tuple[str, ...] = ()

    @model_validator(mode="after")
    def coherent_availability(self) -> Self:
        statistics = (
            self.baseline,
            self.candidate,
            self.oriented_delta,
            self.interval,
        )
        if self.status == "unavailable":
            if any(item is not None for item in statistics) or not self.unavailable_cases:
                raise ValueError("unavailable Guardrail requires only unavailable Case facts")
        elif any(item is None for item in statistics) or self.unavailable_cases:
            raise ValueError("evaluated Guardrail requires complete statistics")
        return self


class OutcomeTransition(StrictModel):
    baseline: BatchOutcome
    candidate: BatchOutcome
    count: int = Field(ge=0)


class FailureMigration(StrictModel):
    profile_id: str = Field(pattern=IDENTIFIER_PATTERN)
    profile_version: str = Field(min_length=1)
    code: str = Field(pattern=IDENTIFIER_PATTERN)
    persisted: int = Field(ge=0)
    resolved: int = Field(ge=0)
    introduced: int = Field(ge=0)


class PassMetric(StrictModel):
    status: Literal["qualified", "not_applicable", "insufficient_trials"]
    k: int = Field(gt=0)
    baseline_pass_at_k: ComparisonEstimate | None
    candidate_pass_at_k: ComparisonEstimate | None
    pass_at_k_delta: ComparisonEstimate | None
    baseline_pass_power_k: ComparisonEstimate | None
    candidate_pass_power_k: ComparisonEstimate | None
    pass_power_k_delta: ComparisonEstimate | None

    @model_validator(mode="after")
    def coherent_status(self) -> Self:
        estimates = (
            self.baseline_pass_at_k,
            self.candidate_pass_at_k,
            self.pass_at_k_delta,
            self.baseline_pass_power_k,
            self.candidate_pass_power_k,
            self.pass_power_k_delta,
        )
        if self.status == "qualified" and any(item is None for item in estimates):
            raise ValueError("qualified pass metrics require complete estimates")
        if self.status != "qualified" and any(item is not None for item in estimates):
            raise ValueError("unqualified pass metrics cannot carry estimates")
        return self


class ComparisonSummary(StrictModel):
    """Derived, non-ranking result of one strict controlled comparison."""

    schema_version: Literal["agent.evaluator.comparison-summary/v1"]
    summary_id: str = Field(min_length=1)
    summary_sha256: str = Field(pattern=SHA256_PATTERN)
    comparison_id: str = Field(min_length=1)
    comparison_input_sha256: str = Field(pattern=SHA256_PATTERN)
    batch_input_id: str = Field(min_length=1)
    comparable: bool
    comparability_reasons: tuple[str, ...]
    primary: PrimaryResult | None
    guardrails: tuple[GuardrailResult, ...]
    outcome_transitions: tuple[OutcomeTransition, ...]
    failure_migration: tuple[FailureMigration, ...]
    failure_migration_unavailable_pairs: int = Field(ge=0)
    pass_metrics: PassMetric | None
    conclusion: ComparisonConclusion

    @model_validator(mode="after")
    def identity_and_state(self) -> Self:
        if self.comparable != (not self.comparability_reasons):
            raise ValueError("comparability status contradicts its reasons")
        if self.comparable != (self.primary is not None):
            raise ValueError("comparable Summary requires exactly one Primary result")
        if (self.conclusion == "not_comparable") != (not self.comparable):
            raise ValueError("not-comparable conclusion contradicts invariants")
        payload = self.model_dump(mode="json", exclude={"summary_id", "summary_sha256"})
        digest = _sha256(payload)
        if self.summary_sha256 != digest or self.summary_id != f"comparison-summary-{digest}":
            raise ValueError("Comparison Summary identity does not match canonical content")
        return self


class ComparisonSummaryReceipt(StrictModel):
    schema_version: Literal["agent.evaluator.comparison-summary-receipt/v1"]
    status: Literal["compared"]
    summary_id: str = Field(min_length=1)
    summary_sha256: str = Field(pattern=SHA256_PATTERN)
    comparison_id: str = Field(min_length=1)
    comparison_input_sha256: str = Field(pattern=SHA256_PATTERN)


class ComparisonFileDigest(StrictModel):
    path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)


class ComparisonManifest(StrictModel):
    schema_version: Literal["agent.evaluator.comparison-summary-manifest/v1"]
    files: Annotated[tuple[ComparisonFileDigest, ...], Field(min_length=4)]

    @model_validator(mode="after")
    def sorted_unique_paths(self) -> Self:
        paths = tuple(item.path for item in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("Comparison package manifest paths must be sorted and unique")
        if COMPARISON_MANIFEST_PATH in paths:
            raise ValueError("Comparison package manifest cannot contain itself")
        return self


class ComparisonSummaryPackage(StrictModel):
    """Path-free strict contents of one closed Comparison Summary package."""

    comparison_input: ComparisonInput
    summary: ComparisonSummary

    @model_validator(mode="after")
    def exact_derivation(self) -> Self:
        if self.summary != build_comparison_summary(self.comparison_input):
            raise ValueError("Comparison Summary is not derived from its Comparison Input")
        return self


_TREATMENT_FIELDS: dict[TreatmentKind, str] = {
    "prompt_instruction": "prompt_instruction_sha256",
    "model": "model_sha256",
    "tool_schema": "tool_schema_sha256",
    "generation_configuration": "generation_configuration_sha256",
    "runtime_version": "runtime_version_sha256",
}


def _outcome(trial: BatchTrial) -> BatchOutcome:
    attempt = trial.attempts[-1]
    if attempt.lifecycle is not None:
        return "infrastructure_unavailable"
    assert attempt.evaluation is not None
    receipt, _ = validate_evaluation_package_content(attempt.evaluation.file_payloads())
    outcomes: dict[Literal["pass", "fail", "inconclusive"], BatchOutcome] = {
        "pass": "pass",
        "fail": "behavioral_fail",
        "inconclusive": "evaluation_invalid",
    }
    return outcomes[receipt.case_outcome]


def _pairs(value: ComparisonInput) -> tuple[tuple[ComparisonCase, BatchTrial, BatchTrial], ...]:
    trials = {
        (item.case_id, item.configuration_id, item.repetition): item
        for item in value.batch_input.trials
    }
    result: list[tuple[ComparisonCase, BatchTrial, BatchTrial]] = []
    for case in value.cases:
        repetitions = sorted(
            repetition
            for case_id, configuration_id, repetition in trials
            if case_id == case.case.case_id and configuration_id == value.baseline.configuration_id
        )
        result.extend(
            (
                case,
                trials[(case.case.case_id, value.baseline.configuration_id, repetition)],
                trials[(case.case.case_id, value.candidate.configuration_id, repetition)],
            )
            for repetition in repetitions
        )
    return tuple(result)


def _comparability_reasons(value: ComparisonInput) -> tuple[str, ...]:
    reasons: set[str] = set()
    declared_fields = {_TREATMENT_FIELDS[item.kind] for item in value.treatment.changes}
    authorities = {
        (item.case.case_id, item.configuration_id): item for item in value.experiment_authorities
    }
    configuration_fields = set(ExperimentProjection.model_fields) - {"evaluation_authority_sha256"}
    for configuration_id in (
        value.baseline.configuration_id,
        value.candidate.configuration_id,
    ):
        projections = [
            authorities[(case.case.case_id, configuration_id)].projection.model_dump(mode="json")
            for case in value.cases
        ]
        for field in sorted(configuration_fields):
            if len({projection[field] for projection in projections}) != 1:
                reasons.add(f"arm_projection_incoherent:{configuration_id}:{field}")
    for case in value.cases:
        case_id = case.case.case_id
        baseline = authorities[(case_id, value.baseline.configuration_id)].projection.model_dump(
            mode="json"
        )
        candidate = authorities[(case_id, value.candidate.configuration_id)].projection.model_dump(
            mode="json"
        )
        actual_differences = {field for field in baseline if baseline[field] != candidate[field]}
        if actual_differences != declared_fields:
            reasons.add(f"treatment_does_not_exhaust_arm_differences:{case_id}")
        for change in value.treatment.changes:
            field = _TREATMENT_FIELDS[change.kind]
            if (
                baseline[field] != change.baseline_sha256
                or candidate[field] != change.candidate_sha256
            ):
                reasons.add(f"treatment_endpoint_mismatch:{change.kind}:{case_id}")
    repetitions = {
        sum(
            item.case_id == case.case.case_id
            and item.configuration_id == value.baseline.configuration_id
            for item in value.batch_input.trials
        )
        for case in value.cases
    }
    if len(repetitions) != 1:
        reasons.add("unequal_repetitions_across_cases")
    for trial in value.batch_input.trials:
        package = trial.attempts[-1].evaluation
        if package is None:
            continue
        receipt, _ = validate_evaluation_package_content(package.file_payloads())
        authority = authorities[(trial.case_id, trial.configuration_id)]
        if receipt.case != authority.case:
            reasons.add(f"case_authority_mismatch:{trial.case_id}")
        if receipt.profile.sha256 != authority.projection.profile_sha256:
            reasons.add(f"profile_authority_mismatch:{trial.case_id}")
        if receipt.authority_sha256 != authority.projection.evaluation_authority_sha256:
            reasons.add(f"evaluation_authority_mismatch:{trial.case_id}")
        if evaluation_policy_sha256(receipt) != authority.projection.evaluation_policy_sha256:
            reasons.add(f"evaluation_policy_mismatch:{trial.case_id}")
    return tuple(sorted(reasons))


def evaluation_policy_sha256(receipt: ImportedEvaluationReceipt) -> str:
    """Derive a case-neutral Profile/scorer/gate evaluation-policy identity."""

    authority = receipt.authority
    return _sha256(
        {
            "schema_version": "agent.evaluator.comparison-evaluation-policy/v1",
            "profile": receipt.profile.model_dump(mode="json"),
            "projection": authority.projection.model_dump(mode="json"),
            "scorer": receipt.scorer.model_dump(mode="json"),
            "case_gate": receipt.case_gate.model_dump(mode="json"),
        }
    )


def _estimate(value: Fraction) -> ComparisonEstimate:
    return ComparisonEstimate(
        numerator=value.numerator,
        denominator=value.denominator,
        value=float(value),
    )


def _rate(numerator: int, denominator: int) -> BatchRate:
    return BatchRate(
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator,
    )


def _cluster_index(seed_sha256: str, replicate: int, draw: int, size: int) -> int:
    """Return one unbiased, cross-version deterministic cluster index."""

    ceiling = 1 << 256
    limit = ceiling - (ceiling % size)
    rejection = 0
    while True:
        payload = (
            BOOTSTRAP_DOMAIN
            + bytes.fromhex(seed_sha256)
            + replicate.to_bytes(8, "big")
            + draw.to_bytes(8, "big")
            + rejection.to_bytes(8, "big")
        )
        candidate = int.from_bytes(hashlib.sha256(payload).digest(), "big")
        if candidate < limit:
            return candidate % size
        rejection += 1


def _bootstrap_interval(
    *, seed_sha256: str, case_numerators: Sequence[int], trials_per_case: int
) -> ComparisonInterval:
    case_count = len(case_numerators)
    denominator = case_count * trials_per_case
    values: list[int] = []
    for replicate in range(BOOTSTRAP_RESAMPLES):
        values.append(
            sum(
                case_numerators[_cluster_index(seed_sha256, replicate, draw, case_count)]
                for draw in range(case_count)
            )
        )
    values.sort()
    return ComparisonInterval(
        lower=_estimate(Fraction(values[249], denominator)),
        upper=_estimate(Fraction(values[9749], denominator)),
    )


def _metric_observations(
    value: ComparisonInput,
    *,
    metric: Literal["reliable_success_rate", "evaluation_validity_rate"],
    split_id: str | None = None,
) -> tuple[list[int], list[int], list[int], int]:
    selected_cases = [item for item in value.cases if split_id is None or item.split_id == split_id]
    pairs = _pairs(value)
    baseline_by_case: dict[str, int] = {item.case.case_id: 0 for item in selected_cases}
    candidate_by_case: dict[str, int] = {item.case.case_id: 0 for item in selected_cases}
    trial_counts: Counter[str] = Counter()
    for case, baseline, candidate in pairs:
        case_id = case.case.case_id
        if case_id not in baseline_by_case:
            continue
        baseline_outcome = _outcome(baseline)
        candidate_outcome = _outcome(candidate)
        if metric == "reliable_success_rate":
            baseline_by_case[case_id] += baseline_outcome == "pass"
            candidate_by_case[case_id] += candidate_outcome == "pass"
        else:
            baseline_by_case[case_id] += baseline_outcome in {"pass", "behavioral_fail"}
            candidate_by_case[case_id] += candidate_outcome in {"pass", "behavioral_fail"}
        trial_counts[case_id] += 1
    counts = set(trial_counts.values())
    if not selected_cases or len(counts) != 1:
        raise ValueError("metric scope requires equal nonempty Trial counts per Case")
    trials_per_case = next(iter(counts))
    baseline_values = [baseline_by_case[item.case.case_id] for item in selected_cases]
    candidate_values = [candidate_by_case[item.case.case_id] for item in selected_cases]
    deltas = [
        candidate - baseline
        for baseline, candidate in zip(baseline_values, candidate_values, strict=True)
    ]
    return baseline_values, candidate_values, deltas, trials_per_case


def _primary(value: ComparisonInput) -> PrimaryResult:
    baseline, candidate, deltas, trials_per_case = _metric_observations(
        value, metric="reliable_success_rate"
    )
    denominator = len(deltas) * trials_per_case
    return PrimaryResult(
        metric="reliable_success_rate",
        baseline=_rate(sum(baseline), denominator),
        candidate=_rate(sum(candidate), denominator),
        delta=_estimate(Fraction(sum(deltas), denominator)),
        interval=_bootstrap_interval(
            seed_sha256=value.comparison_input_sha256,
            case_numerators=deltas,
            trials_per_case=trials_per_case,
        ),
    )


def _failure_codes(trial: BatchTrial) -> tuple[str, str, str, set[str]] | None:
    package = trial.attempts[-1].evaluation
    if package is None:
        return None
    receipt, report = validate_evaluation_package_content(package.file_payloads())
    if receipt.case_outcome == "inconclusive" or report is None:
        return None
    codes = {
        item.id
        for item in report.records
        if item.role in {"outcome", "constraint"}
        and (item.validity != "valid" or item.value is False)
    }
    if receipt.case_outcome == "fail" and not codes:
        codes.add("unclassified")
    return (
        receipt.profile.profile_id,
        receipt.profile.profile_version,
        receipt.authority_sha256,
        codes,
    )


def _failure_migration(
    value: ComparisonInput,
) -> tuple[tuple[FailureMigration, ...], int]:
    counts: Counter[tuple[str, str, str, str]] = Counter()
    unavailable = 0
    for _, baseline, candidate in _pairs(value):
        baseline_codes = _failure_codes(baseline)
        candidate_codes = _failure_codes(candidate)
        if (
            baseline_codes is None
            or candidate_codes is None
            or baseline_codes[:3] != candidate_codes[:3]
        ):
            unavailable += 1
            continue
        profile_id, profile_version, _, baseline_set = baseline_codes
        candidate_set = candidate_codes[3]
        for code in baseline_set | candidate_set:
            state = (
                "persisted"
                if code in baseline_set and code in candidate_set
                else "resolved"
                if code in baseline_set
                else "introduced"
            )
            counts[(profile_id, profile_version, code, state)] += 1
    keys = sorted({key[:3] for key in counts})
    return (
        tuple(
            FailureMigration(
                profile_id=profile_id,
                profile_version=profile_version,
                code=code,
                persisted=counts[(profile_id, profile_version, code, "persisted")],
                resolved=counts[(profile_id, profile_version, code, "resolved")],
                introduced=counts[(profile_id, profile_version, code, "introduced")],
            )
            for profile_id, profile_version, code in keys
        ),
        unavailable,
    )


def _outcome_transitions(value: ComparisonInput) -> tuple[OutcomeTransition, ...]:
    outcomes: tuple[BatchOutcome, ...] = (
        "pass",
        "behavioral_fail",
        "evaluation_invalid",
        "infrastructure_unavailable",
    )
    counts = Counter(
        (_outcome(baseline), _outcome(candidate)) for _, baseline, candidate in _pairs(value)
    )
    return tuple(
        OutcomeTransition(
            baseline=baseline,
            candidate=candidate,
            count=counts[(baseline, candidate)],
        )
        for baseline in outcomes
        for candidate in outcomes
    )


def _guardrail(value: ComparisonInput, guardrail: ComparisonGuardrail) -> GuardrailResult:
    split_id = guardrail.split_id if guardrail.scope == "split" else None
    if guardrail.metric == "profile_failure_code_rate":
        selected_cases = {
            item.case.case_id
            for item in value.cases
            if split_id is None or item.split_id == split_id
        }
        baseline_by_case = {case_id: 0 for case_id in selected_cases}
        candidate_by_case = {case_id: 0 for case_id in selected_cases}
        unavailable: set[str] = set()
        counts: Counter[str] = Counter()
        for case, baseline, candidate in _pairs(value):
            case_id = case.case.case_id
            if case_id not in selected_cases:
                continue
            baseline_codes = _failure_codes(baseline)
            candidate_codes = _failure_codes(candidate)
            if baseline_codes is None or candidate_codes is None:
                unavailable.add(case_id)
                continue
            expected = (guardrail.profile_id, guardrail.profile_version)
            if baseline_codes[:2] != expected or candidate_codes[:2] != expected:
                unavailable.add(case_id)
                continue
            if baseline_codes[2] != candidate_codes[2]:
                unavailable.add(case_id)
                continue
            baseline_by_case[case_id] += guardrail.failure_code in baseline_codes[3]
            candidate_by_case[case_id] += guardrail.failure_code in candidate_codes[3]
            counts[case_id] += 1
        if unavailable or not selected_cases or len(set(counts.values())) != 1:
            return GuardrailResult(
                guardrail_id=guardrail.guardrail_id,
                status="unavailable",
                baseline=None,
                candidate=None,
                oriented_delta=None,
                interval=None,
                unavailable_cases=tuple(sorted(unavailable | (selected_cases - set(counts)))),
            )
        trials_per_case = next(iter(set(counts.values())))
        baseline_values = [baseline_by_case[item] for item in sorted(selected_cases)]
        candidate_values = [candidate_by_case[item] for item in sorted(selected_cases)]
        oriented = [
            baseline - candidate
            for baseline, candidate in zip(baseline_values, candidate_values, strict=True)
        ]
    else:
        metric = guardrail.metric
        baseline_values, candidate_values, raw, trials_per_case = _metric_observations(
            value, metric=metric, split_id=split_id
        )
        oriented = raw if guardrail.direction == "higher_is_better" else [-item for item in raw]
    denominator = len(oriented) * trials_per_case
    interval = _bootstrap_interval(
        seed_sha256=value.comparison_input_sha256,
        case_numerators=oriented,
        trials_per_case=trials_per_case,
    )
    delta = _estimate(Fraction(sum(oriented), denominator))
    tolerance = Fraction(-guardrail.max_adverse_basis_points, 10_000)
    lower = Fraction(interval.lower.numerator, interval.lower.denominator)
    upper = Fraction(interval.upper.numerator, interval.upper.denominator)
    status: Literal["satisfied", "violated", "uncertain", "unavailable"]
    if lower >= tolerance:
        status = "satisfied"
    elif upper < tolerance:
        status = "violated"
    else:
        status = "uncertain"
    return GuardrailResult(
        guardrail_id=guardrail.guardrail_id,
        status=status,
        baseline=_rate(sum(baseline_values), denominator),
        candidate=_rate(sum(candidate_values), denominator),
        oriented_delta=delta,
        interval=interval,
    )


def _combination_probability(n: int, c: int, k: int, *, at_least_one: bool) -> Fraction:
    denominator = math.comb(n, k)
    if at_least_one:
        numerator = denominator - (math.comb(n - c, k) if n - c >= k else 0)
    else:
        numerator = math.comb(c, k) if c >= k else 0
    return Fraction(numerator, denominator)


def _pass_metrics(value: ComparisonInput) -> PassMetric | None:
    if value.pass_k is None:
        return None
    repetitions = Counter(
        (item.case_id, item.configuration_id) for item in value.batch_input.planned_trials
    )
    n_values = set(repetitions.values())
    k = value.pass_k.k
    if len(n_values) != 1:
        return PassMetric(
            status="not_applicable",
            k=k,
            baseline_pass_at_k=None,
            candidate_pass_at_k=None,
            pass_at_k_delta=None,
            baseline_pass_power_k=None,
            candidate_pass_power_k=None,
            pass_power_k_delta=None,
        )
    n = next(iter(n_values))
    if k > n:
        return PassMetric(
            status="insufficient_trials",
            k=k,
            baseline_pass_at_k=None,
            candidate_pass_at_k=None,
            pass_at_k_delta=None,
            baseline_pass_power_k=None,
            candidate_pass_power_k=None,
            pass_power_k_delta=None,
        )
    trials: dict[tuple[str, str], list[BatchTrial]] = {
        (item.case_id, item.configuration_id): [] for item in value.batch_input.trials
    }
    for trial in value.batch_input.trials:
        trials[(trial.case_id, trial.configuration_id)].append(trial)
    baseline_at: list[Fraction] = []
    candidate_at: list[Fraction] = []
    baseline_power: list[Fraction] = []
    candidate_power: list[Fraction] = []
    for case in value.cases:
        baseline_successes = sum(
            _outcome(item) == "pass"
            for item in trials[(case.case.case_id, value.baseline.configuration_id)]
        )
        candidate_successes = sum(
            _outcome(item) == "pass"
            for item in trials[(case.case.case_id, value.candidate.configuration_id)]
        )
        baseline_at.append(_combination_probability(n, baseline_successes, k, at_least_one=True))
        candidate_at.append(_combination_probability(n, candidate_successes, k, at_least_one=True))
        baseline_power.append(
            _combination_probability(n, baseline_successes, k, at_least_one=False)
        )
        candidate_power.append(
            _combination_probability(n, candidate_successes, k, at_least_one=False)
        )
    case_count = len(value.cases)
    baseline_at_mean = sum(baseline_at, start=Fraction()) / case_count
    candidate_at_mean = sum(candidate_at, start=Fraction()) / case_count
    baseline_power_mean = sum(baseline_power, start=Fraction()) / case_count
    candidate_power_mean = sum(candidate_power, start=Fraction()) / case_count
    return PassMetric(
        status="qualified",
        k=k,
        baseline_pass_at_k=_estimate(baseline_at_mean),
        candidate_pass_at_k=_estimate(candidate_at_mean),
        pass_at_k_delta=_estimate(candidate_at_mean - baseline_at_mean),
        baseline_pass_power_k=_estimate(baseline_power_mean),
        candidate_pass_power_k=_estimate(candidate_power_mean),
        pass_power_k_delta=_estimate(candidate_power_mean - baseline_power_mean),
    )


def _conclusion(
    value: ComparisonInput, primary: PrimaryResult, guardrails: Sequence[GuardrailResult]
) -> ComparisonConclusion:
    lower = Fraction(primary.interval.lower.numerator, primary.interval.lower.denominator)
    upper = Fraction(primary.interval.upper.numerator, primary.interval.upper.denominator)
    delta = Fraction(primary.delta.numerator, primary.delta.denominator)
    violated = any(item.status == "violated" for item in guardrails)
    if violated:
        return "mixed" if lower > 0 else "regressed"
    if upper < 0:
        return "regressed"
    if lower <= 0 <= upper:
        return "uncertain"
    if any(item.status in {"uncertain", "unavailable"} for item in guardrails):
        return "uncertain"
    threshold = Fraction(value.primary_outcome.practical_threshold_basis_points, 10_000)
    if delta < threshold:
        return "no_change"
    return "improved"


def build_comparison_summary(value: ComparisonInput) -> ComparisonSummary:
    """Derive all comparison facts without Runtime access or authored claims."""

    reasons = _comparability_reasons(value)
    transitions = _outcome_transitions(value)
    migration, migration_unavailable = _failure_migration(value)
    primary = None if reasons else _primary(value)
    guardrails = () if reasons else tuple(_guardrail(value, item) for item in value.guardrails)
    pass_metrics = None if reasons else _pass_metrics(value)
    conclusion: ComparisonConclusion = (
        "not_comparable" if reasons else _conclusion(value, primary, guardrails)  # type: ignore[arg-type]
    )
    payload: dict[str, object] = {
        "schema_version": COMPARISON_SUMMARY_SCHEMA_VERSION,
        "comparison_id": value.comparison_id,
        "comparison_input_sha256": value.comparison_input_sha256,
        "batch_input_id": value.batch_input.batch_input_id,
        "comparable": not reasons,
        "comparability_reasons": list(reasons),
        "primary": None if primary is None else primary.model_dump(mode="json"),
        "guardrails": [item.model_dump(mode="json") for item in guardrails],
        "outcome_transitions": [item.model_dump(mode="json") for item in transitions],
        "failure_migration": [item.model_dump(mode="json") for item in migration],
        "failure_migration_unavailable_pairs": migration_unavailable,
        "pass_metrics": None if pass_metrics is None else pass_metrics.model_dump(mode="json"),
        "conclusion": conclusion,
    }
    digest = _sha256(payload)
    payload["summary_id"] = f"comparison-summary-{digest}"
    payload["summary_sha256"] = digest
    return decode_contract(canonical_json(payload), ComparisonSummary)


def validate_comparison_input(path: Path) -> ComparisonInput:
    """Strictly load one canonical Comparison Input JSON file."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise IngestionIntegrityError("cannot read Comparison Input") from exc
    return _decode_comparison_input(raw)


def _decode_comparison_input(raw: bytes) -> ComparisonInput:
    try:
        value = decode_contract(raw, ComparisonInput)
    except ContractError as exc:
        raise IngestionIntegrityError("invalid Comparison Input") from exc
    if raw != canonical_json(value):
        raise IngestionIntegrityError("Comparison Input is not canonical JSON")
    return value


def _format_estimate(value: ComparisonEstimate) -> str:
    return f"{value.value:.6f} ({value.numerator}/{value.denominator})"


def render_comparison_summary_markdown(summary: ComparisonSummary) -> bytes:
    """Render deterministic non-ranking Markdown from derived comparison facts."""

    lines = [
        "# Cernora Controlled Comparison",
        "",
        f"- Summary ID: `{summary.summary_id}`",
        f"- Comparison ID: `{summary.comparison_id}`",
        f"- Batch Input ID: `{summary.batch_input_id}`",
        f"- Comparable: `{'yes' if summary.comparable else 'no'}`",
        f"- Conclusion: `{summary.conclusion}`",
        "",
    ]
    if summary.comparability_reasons:
        lines.extend(("## Comparability", ""))
        lines.extend(f"- `{reason}`" for reason in summary.comparability_reasons)
        lines.append("")
    if summary.primary is not None:
        lines.extend(
            (
                "## Primary outcome",
                "",
                "| Metric | Baseline | Candidate | Delta | 95% interval |",
                "| --- | ---: | ---: | ---: | ---: |",
                (
                    f"| Reliable success rate | {summary.primary.baseline.value:.6f} | "
                    f"{summary.primary.candidate.value:.6f} | "
                    f"{_format_estimate(summary.primary.delta)} | "
                    f"[{_format_estimate(summary.primary.interval.lower)}, "
                    f"{_format_estimate(summary.primary.interval.upper)}] |"
                ),
                "",
            )
        )
    lines.extend(("## Hard guardrails", ""))
    if summary.guardrails:
        lines.extend(("| Guardrail | Status |", "| --- | --- |"))
        lines.extend(f"| {item.guardrail_id} | {item.status} |" for item in summary.guardrails)
    else:
        lines.append("Unavailable because controlled-comparison invariants did not hold.")
    lines.extend(
        (
            "",
            "This artifact reports a predeclared comparison. It does not rank, promote, or "
            "recommend a configuration.",
            "",
        )
    )
    return "\n".join(lines).encode("utf-8")


def _comparison_files(
    summary: ComparisonSummary, comparison_input: ComparisonInput
) -> dict[str, bytes]:
    receipt = ComparisonSummaryReceipt(
        schema_version="agent.evaluator.comparison-summary-receipt/v1",
        status="compared",
        summary_id=summary.summary_id,
        summary_sha256=summary.summary_sha256,
        comparison_id=summary.comparison_id,
        comparison_input_sha256=summary.comparison_input_sha256,
    )
    files = {
        COMPARISON_INPUT_PATH: canonical_json(comparison_input),
        COMPARISON_SUMMARY_PATH: canonical_json(summary),
        COMPARISON_MARKDOWN_PATH: render_comparison_summary_markdown(summary),
        COMPARISON_RECEIPT_PATH: canonical_json(receipt),
    }
    manifest = ComparisonManifest(
        schema_version="agent.evaluator.comparison-summary-manifest/v1",
        files=tuple(
            ComparisonFileDigest(
                path=path,
                size_bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
            for path, payload in sorted(files.items())
        ),
    )
    files[COMPARISON_MANIFEST_PATH] = canonical_json(manifest)
    return files


def summarize_comparison(value: ComparisonInput, output: Path) -> ComparisonSummary:
    """Build, atomically publish, and strictly reload one Comparison package."""

    summary = build_comparison_summary(value)
    publish_closed_package(
        output,
        _comparison_files(summary, value),
        label="Comparison Summary",
    )
    reloaded = reload_comparison_summary(output)
    if reloaded != summary:
        raise IngestionIntegrityError("published Comparison Summary changed during strict reload")
    return reloaded


def reload_comparison_package(root: Path) -> ComparisonSummaryPackage:
    """Strictly reload the path-free contents of one closed Comparison package."""

    files = ordinary_tree_files(root, label="Comparison Summary package")
    try:
        manifest = decode_contract(files[COMPARISON_MANIFEST_PATH], ComparisonManifest)
    except (KeyError, ContractError) as exc:
        raise IngestionIntegrityError("invalid Comparison Summary manifest") from exc
    expected_paths = {COMPARISON_MANIFEST_PATH, *(item.path for item in manifest.files)}
    if set(files) != expected_paths:
        raise IngestionIntegrityError("Comparison Summary file set does not match manifest")
    for item in manifest.files:
        payload = files[item.path]
        if len(payload) != item.size_bytes or hashlib.sha256(payload).hexdigest() != item.sha256:
            raise IngestionIntegrityError("Comparison Summary file digest mismatch")
    try:
        comparison_input = _decode_comparison_input(files[COMPARISON_INPUT_PATH])
        summary = decode_contract(files[COMPARISON_SUMMARY_PATH], ComparisonSummary)
        receipt = decode_contract(files[COMPARISON_RECEIPT_PATH], ComparisonSummaryReceipt)
    except (KeyError, ContractError) as exc:
        raise IngestionIntegrityError("invalid Comparison Summary contract") from exc
    expected_receipt = ComparisonSummaryReceipt(
        schema_version="agent.evaluator.comparison-summary-receipt/v1",
        status="compared",
        summary_id=summary.summary_id,
        summary_sha256=summary.summary_sha256,
        comparison_id=summary.comparison_id,
        comparison_input_sha256=summary.comparison_input_sha256,
    )
    if receipt != expected_receipt:
        raise IngestionIntegrityError("Comparison Summary receipt does not bind the Summary")
    expected_summary = build_comparison_summary(comparison_input)
    if summary != expected_summary:
        raise IngestionIntegrityError("Comparison Summary is not derived from its Comparison Input")
    if files != _comparison_files(summary, comparison_input):
        raise IngestionIntegrityError("Comparison Summary package is not canonical")
    return ComparisonSummaryPackage(comparison_input=comparison_input, summary=summary)


def reload_comparison_summary(root: Path) -> ComparisonSummary:
    """Strictly reload one closed deterministic Comparison Summary package."""

    return reload_comparison_package(root).summary


__all__ = [
    "BOOTSTRAP_CONFIDENCE_BASIS_POINTS",
    "BOOTSTRAP_METHOD",
    "BOOTSTRAP_RESAMPLES",
    "COMPARISON_INPUT_SCHEMA_VERSION",
    "COMPARISON_SUMMARY_SCHEMA_VERSION",
    "BootstrapPlan",
    "ComparisonArm",
    "ComparisonCase",
    "ComparisonConclusion",
    "ComparisonEstimate",
    "ComparisonGuardrail",
    "ComparisonInput",
    "ComparisonInterval",
    "ComparisonSummary",
    "ComparisonSummaryPackage",
    "ExperimentAuthority",
    "ExperimentProjection",
    "FailureMigration",
    "GuardrailResult",
    "OutcomeTransition",
    "PassKPlan",
    "PassMetric",
    "PrimaryOutcome",
    "PrimaryResult",
    "Treatment",
    "TreatmentChange",
    "build_comparison_summary",
    "evaluation_policy_sha256",
    "materialize_comparison_input",
    "materialize_experiment_authority",
    "materialize_treatment",
    "reload_comparison_package",
    "reload_comparison_summary",
    "render_comparison_summary_markdown",
    "summarize_comparison",
    "validate_comparison_input",
]
