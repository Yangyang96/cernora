"""Validity-first batch input and summary Preview contracts."""

from __future__ import annotations

import base64
import hashlib
import math
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cernora._closed_package import ordinary_tree_files, publish_closed_package
from cernora.core.canonical import canonical_json, decode_contract
from cernora.core.case import StrictModel
from cernora.core.errors import ContractError
from cernora.core.identity import SHA256_PATTERN
from cernora.evaluation.package import validate_evaluation_package_content
from cernora.ingestion.errors import IngestionIntegrityError

BATCH_INPUT_SCHEMA_VERSION = "agent.evaluator.batch-input/v1"
BATCH_SUMMARY_SCHEMA_VERSION = "agent.evaluator.batch-summary/v1"
BATCH_SUMMARY_RECEIPT_SCHEMA_VERSION = "agent.evaluator.batch-summary-receipt/v1"
BATCH_SUMMARY_MANIFEST_SCHEMA_VERSION = "agent.evaluator.batch-summary-manifest/v1"

IDENTIFIER_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"
SUMMARY_PATH = "batch-summary.json"
INPUT_PATH = "batch-input.json"
MARKDOWN_PATH = "batch-summary.md"
RECEIPT_PATH = "batch-summary-receipt.json"
MANIFEST_PATH = "digests.json"

BatchOutcome = Literal[
    "pass",
    "behavioral_fail",
    "evaluation_invalid",
    "infrastructure_unavailable",
]
LifecycleCategory = Literal[
    "timed_out",
    "interrupted",
    "infrastructure_start_failure",
    "transient_provider_pre_terminal",
    "runtime_pre_terminal_failure",
    "other_verified_infrastructure_failure",
]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _contained_path(path: str) -> None:
    parsed = PurePosixPath(path)
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
        or not parsed.parts
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or parsed.as_posix() != path
    ):
        raise ValueError("path must be a contained canonical POSIX relative path")


class BatchEvaluationFile(StrictModel):
    """One byte-exact file embedded from a closed Evaluation Package."""

    path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)
    content_base64: str

    @model_validator(mode="after")
    def valid_payload(self) -> Self:
        _contained_path(self.path)
        try:
            payload = base64.b64decode(self.content_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("Evaluation Package file is not canonical base64") from exc
        if base64.b64encode(payload).decode("ascii") != self.content_base64:
            raise ValueError("Evaluation Package file is not canonical base64")
        if len(payload) != self.size_bytes or _sha256(payload) != self.sha256:
            raise ValueError("Evaluation Package embedded file digest mismatch")
        return self

    def payload(self) -> bytes:
        return base64.b64decode(self.content_base64, validate=True)


class BatchEvaluationPackage(StrictModel):
    """A complete evaluator-owned package, embedded without host paths."""

    schema_version: Literal["agent.evaluator.batch-evaluation-package/v1"]
    package_sha256: str = Field(pattern=SHA256_PATTERN)
    files: Annotated[tuple[BatchEvaluationFile, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def valid_closed_package(self) -> Self:
        paths = tuple(item.path for item in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("Evaluation Package files must be sorted and unique")
        expected = _sha256(
            canonical_json(
                [
                    {
                        "path": item.path,
                        "sha256": item.sha256,
                        "size_bytes": item.size_bytes,
                    }
                    for item in self.files
                ]
            )
        )
        if self.package_sha256 != expected:
            raise ValueError("Evaluation Package identity mismatch")
        try:
            validate_evaluation_package_content(self.file_payloads())
        except IngestionIntegrityError as exc:
            raise ValueError("embedded Evaluation Package failed strict reload") from exc
        return self

    def file_payloads(self) -> dict[str, bytes]:
        return {item.path: item.payload() for item in self.files}


class BatchAttemptResources(StrictModel):
    """Verified resource facts for one Attempt; missing values remain unavailable."""

    duration_milliseconds: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_microunits: int | None = Field(default=None, ge=0)
    usage_receipt_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verified_usage(self) -> Self:
        metered = (self.input_tokens, self.output_tokens, self.cost_microunits)
        if any(value is not None for value in metered) and self.usage_receipt_sha256 is None:
            raise ValueError("token or cost values require a verified usage receipt")
        return self


class BatchLifecycleRecord(StrictModel):
    """Normalized, receipt-bound terminal state when no Evaluation Package exists."""

    schema_version: Literal["agent.evaluator.batch-lifecycle/v1"]
    category: LifecycleCategory
    retry_eligible: bool
    source_state: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)


class BatchAttempt(StrictModel):
    """One immutable Attempt in a complete Trial chain."""

    schema_version: Literal["agent.evaluator.batch-attempt/v1"]
    attempt_id: str = Field(pattern=SHA256_PATTERN)
    source_attempt_id: str = Field(pattern=IDENTIFIER_PATTERN)
    trial_id: str = Field(pattern=SHA256_PATTERN)
    ordinal: int = Field(gt=0)
    predecessor_attempt_id: str | None = Field(default=None, pattern=SHA256_PATTERN)
    source_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    retry_eligible: bool
    resources: BatchAttemptResources
    evaluation: BatchEvaluationPackage | None = None
    lifecycle: BatchLifecycleRecord | None = None

    @model_validator(mode="after")
    def one_authoritative_terminal(self) -> Self:
        if (self.evaluation is None) == (self.lifecycle is None):
            raise ValueError("Attempt requires exactly one Evaluation Package or lifecycle record")
        if self.lifecycle is not None and self.retry_eligible != self.lifecycle.retry_eligible:
            raise ValueError("Attempt retry eligibility contradicts lifecycle receipt")
        if self.evaluation is not None:
            receipt, _ = validate_evaluation_package_content(self.evaluation.file_payloads())
            if receipt.run.attempt_id != self.source_attempt_id:
                raise ValueError("Evaluation Package does not bind the source Attempt")
        if self.ordinal == 1 and self.predecessor_attempt_id is not None:
            raise ValueError("first Attempt cannot have a predecessor")
        if self.ordinal > 1 and self.predecessor_attempt_id is None:
            raise ValueError("retry Attempt requires a predecessor")
        return self


class BatchPlannedTrial(StrictModel):
    """One RunPlan-declared sample slot in authoritative order."""

    slot_index: int = Field(gt=0)
    trial_slot_id: str = Field(pattern=SHA256_PATTERN)
    case_id: str = Field(pattern=IDENTIFIER_PATTERN)
    configuration_id: str = Field(pattern=IDENTIFIER_PATTERN)
    experiment_id: str = Field(pattern=SHA256_PATTERN)
    repetition: int = Field(gt=0)


class BatchTrial(StrictModel):
    """One completed planned Trial and its lossless Attempt chain."""

    schema_version: Literal["agent.evaluator.batch-trial/v1"]
    run_plan_id: str = Field(pattern=SHA256_PATTERN)
    execution_id: str = Field(pattern=SHA256_PATTERN)
    trial_id: str = Field(pattern=SHA256_PATTERN)
    slot_index: int = Field(gt=0)
    trial_slot_id: str = Field(pattern=SHA256_PATTERN)
    case_id: str = Field(pattern=IDENTIFIER_PATTERN)
    configuration_id: str = Field(pattern=IDENTIFIER_PATTERN)
    experiment_id: str = Field(pattern=SHA256_PATTERN)
    repetition: int = Field(gt=0)
    selected_attempt_id: str = Field(pattern=SHA256_PATTERN)
    attempts: Annotated[tuple[BatchAttempt, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def valid_attempt_chain(self) -> Self:
        if tuple(item.ordinal for item in self.attempts) != tuple(range(1, len(self.attempts) + 1)):
            raise ValueError("Trial Attempt ordinals must be contiguous")
        ids = tuple(item.attempt_id for item in self.attempts)
        if len(ids) != len(set(ids)):
            raise ValueError("Trial Attempt IDs must be unique")
        if any(item.trial_id != self.trial_id for item in self.attempts):
            raise ValueError("Attempt binds another Trial")
        for previous, current in zip(self.attempts, self.attempts[1:], strict=False):
            if current.predecessor_attempt_id != previous.attempt_id:
                raise ValueError("Attempt retry predecessor chain is broken")
            if not previous.retry_eligible:
                raise ValueError("Attempt retries a non-eligible predecessor")
        if self.selected_attempt_id != self.attempts[-1].attempt_id:
            raise ValueError("Trial must select its final Attempt")
        selected = self.attempts[-1]
        if selected.evaluation is not None:
            receipt, _ = validate_evaluation_package_content(selected.evaluation.file_payloads())
            if receipt.case.case_id != self.case_id:
                raise ValueError("Evaluation Package Case does not match Trial")
        return self


class BatchInput(StrictModel):
    """Strict, canonical, content-identified input for Runtime-neutral aggregation."""

    schema_version: Literal["agent.evaluator.batch-input/v1"]
    batch_input_id: str = Field(min_length=1)
    batch_input_sha256: str = Field(pattern=SHA256_PATTERN)
    run_plan_id: str = Field(pattern=SHA256_PATTERN)
    execution_id: str = Field(pattern=SHA256_PATTERN)
    execution_status: Literal["completed"]
    budget_status: Literal["within_budget"]
    companion_version: str = Field(min_length=1)
    planned_trial_count: int = Field(gt=0)
    attempt_count: int = Field(gt=0)
    planned_trials: Annotated[tuple[BatchPlannedTrial, ...], Field(min_length=1)]
    trials: Annotated[tuple[BatchTrial, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def complete_matrix_and_identity(self) -> Self:
        if self.planned_trial_count != len(self.planned_trials):
            raise ValueError("planned Trial count does not match declared slots")
        if len(self.trials) != self.planned_trial_count:
            raise ValueError("Batch Input is incomplete")
        expected_indexes = tuple(range(1, self.planned_trial_count + 1))
        if tuple(item.slot_index for item in self.planned_trials) != expected_indexes:
            raise ValueError("planned Trials are not in complete canonical slot order")
        if tuple(item.slot_index for item in self.trials) != expected_indexes:
            raise ValueError("Trials are not in complete canonical slot order")
        slot_ids = tuple(item.trial_slot_id for item in self.planned_trials)
        trial_ids = tuple(item.trial_id for item in self.trials)
        coordinates = tuple(
            (item.case_id, item.configuration_id, item.repetition) for item in self.planned_trials
        )
        if len(slot_ids) != len(set(slot_ids)) or len(coordinates) != len(set(coordinates)):
            raise ValueError("planned Trial slots are duplicated")
        cells: dict[tuple[str, str], list[BatchPlannedTrial]] = {}
        for slot in self.planned_trials:
            cells.setdefault((slot.case_id, slot.configuration_id), []).append(slot)
        for slots in cells.values():
            if len({slot.experiment_id for slot in slots}) != 1:
                raise ValueError("planned Trial cell binds multiple Experiments")
            if tuple(slot.repetition for slot in slots) != tuple(range(1, len(slots) + 1)):
                raise ValueError("planned Trial cell repetitions must be contiguous")
        if len(trial_ids) != len(set(trial_ids)):
            raise ValueError("Trials are duplicated")
        for slot, trial in zip(self.planned_trials, self.trials, strict=True):
            if (
                trial.slot_index,
                trial.trial_slot_id,
                trial.case_id,
                trial.configuration_id,
                trial.experiment_id,
                trial.repetition,
            ) != (
                slot.slot_index,
                slot.trial_slot_id,
                slot.case_id,
                slot.configuration_id,
                slot.experiment_id,
                slot.repetition,
            ):
                raise ValueError("Trial does not match its declared planned slot")
            if trial.run_plan_id != self.run_plan_id or trial.execution_id != self.execution_id:
                raise ValueError("Trial binds another RunPlan or Execution")
        if self.attempt_count != sum(len(item.attempts) for item in self.trials):
            raise ValueError("Attempt count does not match complete Trial chains")
        all_attempt_ids = tuple(
            attempt.attempt_id for trial in self.trials for attempt in trial.attempts
        )
        if len(all_attempt_ids) != len(set(all_attempt_ids)):
            raise ValueError("Attempt IDs must be unique across the Batch Input")
        payload = self.model_dump(mode="json", exclude={"batch_input_id", "batch_input_sha256"})
        expected_sha256 = _sha256(canonical_json(payload))
        if self.batch_input_sha256 != expected_sha256:
            raise ValueError("Batch Input SHA-256 does not match canonical content")
        if self.batch_input_id != f"batch-input-{expected_sha256}":
            raise ValueError("Batch Input ID does not match canonical content")
        return self


class BatchRate(StrictModel):
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    value: float | None = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def exact_ratio(self) -> Self:
        if self.numerator > self.denominator:
            raise ValueError("rate numerator cannot exceed denominator")
        if self.denominator == 0:
            if self.numerator != 0 or self.value is not None:
                raise ValueError("unavailable rate must be 0/0 with a null value")
        else:
            expected = self.numerator / self.denominator
            if self.value is None or not math.isclose(self.value, expected, rel_tol=0, abs_tol=0):
                raise ValueError("rate value does not match exact counts")
        return self


class BatchOutcomeCounts(StrictModel):
    passed: int = Field(ge=0)
    behavioral_failed: int = Field(ge=0)
    evaluation_invalid: int = Field(ge=0)
    infrastructure_unavailable: int = Field(ge=0)

    @property
    def total(self) -> int:
        return (
            self.passed
            + self.behavioral_failed
            + self.evaluation_invalid
            + self.infrastructure_unavailable
        )


class BatchGroupSummary(StrictModel):
    case_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    configuration_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    planned_trials: int = Field(gt=0)
    outcomes: BatchOutcomeCounts
    evaluation_validity_rate: BatchRate
    behavioral_success_rate: BatchRate
    reliable_success_rate: BatchRate

    @model_validator(mode="after")
    def coherent_counts(self) -> Self:
        if self.outcomes.total != self.planned_trials:
            raise ValueError("group outcome counts do not match planned Trials")
        valid = self.outcomes.passed + self.outcomes.behavioral_failed
        expected = (
            _rate(valid, self.planned_trials),
            _rate(self.outcomes.passed, valid),
            _rate(self.outcomes.passed, self.planned_trials),
        )
        actual = (
            self.evaluation_validity_rate,
            self.behavioral_success_rate,
            self.reliable_success_rate,
        )
        if actual != expected:
            raise ValueError("group rates do not match authoritative outcome counts")
        return self


class BatchDistributionEntry(StrictModel):
    name: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    count: int = Field(gt=0)


class BatchVerifiedTotal(StrictModel):
    status: Literal["available", "unavailable"]
    value: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def coherent_availability(self) -> Self:
        if (self.status == "available") != (self.value is not None):
            raise ValueError("verified total status contradicts its value")
        return self


class BatchAttemptDiagnostics(StrictModel):
    total_attempts: int = Field(gt=0)
    first_attempts: int = Field(gt=0)
    retry_attempts: int = Field(ge=0)
    trials_with_retry: int = Field(ge=0)
    first_attempt_success_rate: BatchRate
    retry_rate: BatchRate
    evaluation_validity_rate: BatchRate
    infrastructure_failures: tuple[BatchDistributionEntry, ...]
    duration_milliseconds: BatchVerifiedTotal
    input_tokens: BatchVerifiedTotal
    output_tokens: BatchVerifiedTotal
    cost_microunits: BatchVerifiedTotal


class BatchFailureCodeCount(StrictModel):
    profile_id: str = Field(pattern=IDENTIFIER_PATTERN)
    profile_version: str = Field(min_length=1)
    code: str = Field(pattern=IDENTIFIER_PATTERN)
    count: int = Field(gt=0)


class BatchSummary(StrictModel):
    """Authoritative validity-first summary derived from one Batch Input."""

    schema_version: Literal["agent.evaluator.batch-summary/v1"]
    summary_id: str = Field(min_length=1)
    summary_sha256: str = Field(pattern=SHA256_PATTERN)
    batch_input_id: str = Field(min_length=1)
    batch_input_sha256: str = Field(pattern=SHA256_PATTERN)
    run_plan_id: str = Field(pattern=SHA256_PATTERN)
    execution_id: str = Field(pattern=SHA256_PATTERN)
    overall: BatchGroupSummary
    by_configuration: Annotated[tuple[BatchGroupSummary, ...], Field(min_length=1)]
    by_case: Annotated[tuple[BatchGroupSummary, ...], Field(min_length=1)]
    by_cell: Annotated[tuple[BatchGroupSummary, ...], Field(min_length=1)]
    attempt_diagnostics: BatchAttemptDiagnostics
    profile_failure_codes: tuple[BatchFailureCodeCount, ...]

    @model_validator(mode="after")
    def valid_identity_and_order(self) -> Self:
        if self.overall.case_id is not None or self.overall.configuration_id is not None:
            raise ValueError("overall group cannot declare a dimension")
        configurations = tuple(
            item.configuration_id
            for item in self.by_configuration
            if item.configuration_id is not None
        )
        cases = tuple(item.case_id for item in self.by_case if item.case_id is not None)
        cells = tuple((item.case_id, item.configuration_id) for item in self.by_cell)
        if (
            any(item.case_id is not None for item in self.by_configuration)
            or len(configurations) != len(self.by_configuration)
            or configurations != tuple(sorted(configurations))
            or len(configurations) != len(set(configurations))
        ):
            raise ValueError("Configuration summaries are not canonical")
        if (
            any(item.configuration_id is not None for item in self.by_case)
            or len(cases) != len(self.by_case)
            or cases != tuple(sorted(cases))
            or len(cases) != len(set(cases))
        ):
            raise ValueError("Case summaries are not canonical")
        if (
            any(case is None or configuration is None for case, configuration in cells)
            or cells != tuple(sorted(cells))
            or len(cells) != len(set(cells))
        ):
            raise ValueError("cell summaries are not canonical")
        payload = self.model_dump(mode="json", exclude={"summary_id", "summary_sha256"})
        expected_sha256 = _sha256(canonical_json(payload))
        if self.summary_sha256 != expected_sha256:
            raise ValueError("Batch Summary SHA-256 does not match canonical content")
        if self.summary_id != f"batch-summary-{expected_sha256}":
            raise ValueError("Batch Summary ID does not match canonical content")
        return self


class BatchSummaryPackage(StrictModel):
    """Path-free strict contents of one closed Batch Summary package."""

    batch_input: BatchInput
    summary: BatchSummary

    @model_validator(mode="after")
    def exact_derivation(self) -> Self:
        if self.summary != build_batch_summary(self.batch_input):
            raise ValueError("Batch Summary is not derived from its Batch Input")
        return self


class BatchSummaryReceipt(StrictModel):
    schema_version: Literal["agent.evaluator.batch-summary-receipt/v1"]
    status: Literal["summarized"]
    summary_id: str = Field(min_length=1)
    summary_sha256: str = Field(pattern=SHA256_PATTERN)
    batch_input_id: str = Field(min_length=1)
    batch_input_sha256: str = Field(pattern=SHA256_PATTERN)


class BatchSummaryFileDigest(StrictModel):
    path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def valid_path(self) -> Self:
        _contained_path(self.path)
        if self.path == MANIFEST_PATH:
            raise ValueError("Batch Summary manifest cannot contain itself")
        return self


class BatchSummaryManifest(StrictModel):
    schema_version: Literal["agent.evaluator.batch-summary-manifest/v1"]
    files: Annotated[tuple[BatchSummaryFileDigest, ...], Field(min_length=4)]

    @model_validator(mode="after")
    def sorted_unique_files(self) -> Self:
        paths = tuple(item.path for item in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("Batch Summary manifest paths must be sorted and unique")
        return self


def embed_evaluation_package(root: Path) -> BatchEvaluationPackage:
    """Read one ordinary closed Evaluation Package into a path-free Batch value."""

    files = _ordinary_tree_files(root, label="Evaluation Package")
    embedded = tuple(
        BatchEvaluationFile(
            path=path,
            size_bytes=len(payload),
            sha256=_sha256(payload),
            content_base64=base64.b64encode(payload).decode("ascii"),
        )
        for path, payload in sorted(files.items())
    )
    package_sha256 = _sha256(
        canonical_json(
            [
                {"path": item.path, "sha256": item.sha256, "size_bytes": item.size_bytes}
                for item in embedded
            ]
        )
    )
    return BatchEvaluationPackage(
        schema_version="agent.evaluator.batch-evaluation-package/v1",
        package_sha256=package_sha256,
        files=embedded,
    )


def materialize_batch_input(payload_without_identity: Mapping[str, object]) -> BatchInput:
    """Add the canonical Batch Input identity to a fully normalized payload."""

    if {"batch_input_id", "batch_input_sha256"}.intersection(payload_without_identity):
        raise ValueError("Batch Input materialization payload must omit identity fields")
    payload = dict(payload_without_identity)
    digest = _sha256(canonical_json(payload))
    payload["batch_input_id"] = f"batch-input-{digest}"
    payload["batch_input_sha256"] = digest
    return decode_contract(canonical_json(payload), BatchInput)


def validate_batch_input(path: Path) -> BatchInput:
    """Strictly load one canonical Batch Input JSON file."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise IngestionIntegrityError("cannot read Batch Input") from exc
    value = _decode_batch_input(raw)
    return value


def _decode_batch_input(raw: bytes) -> BatchInput:
    try:
        value = decode_contract(raw, BatchInput)
    except ContractError as exc:
        raise IngestionIntegrityError("invalid Batch Input") from exc
    if raw != canonical_json(value):
        raise IngestionIntegrityError("Batch Input is not canonical JSON")
    return value


def _rate(numerator: int, denominator: int) -> BatchRate:
    return BatchRate(
        numerator=numerator,
        denominator=denominator,
        value=None if denominator == 0 else numerator / denominator,
    )


def _attempt_outcome(attempt: BatchAttempt) -> BatchOutcome:
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


def _group(
    trials: Iterable[BatchTrial], *, case_id: str | None, configuration_id: str | None
) -> BatchGroupSummary:
    selected = tuple(trials)
    outcomes = Counter(_attempt_outcome(item.attempts[-1]) for item in selected)
    counts = BatchOutcomeCounts(
        passed=outcomes["pass"],
        behavioral_failed=outcomes["behavioral_fail"],
        evaluation_invalid=outcomes["evaluation_invalid"],
        infrastructure_unavailable=outcomes["infrastructure_unavailable"],
    )
    valid = counts.passed + counts.behavioral_failed
    return BatchGroupSummary(
        case_id=case_id,
        configuration_id=configuration_id,
        planned_trials=len(selected),
        outcomes=counts,
        evaluation_validity_rate=_rate(valid, len(selected)),
        behavioral_success_rate=_rate(counts.passed, valid),
        reliable_success_rate=_rate(counts.passed, len(selected)),
    )


def _verified_total(values: Iterable[int | None]) -> BatchVerifiedTotal:
    materialized = tuple(values)
    if any(value is None for value in materialized):
        return BatchVerifiedTotal(status="unavailable", value=None)
    return BatchVerifiedTotal(
        status="available", value=sum(value for value in materialized if value is not None)
    )


def _attempt_diagnostics(batch_input: BatchInput) -> BatchAttemptDiagnostics:
    attempts = tuple(attempt for trial in batch_input.trials for attempt in trial.attempts)
    first_attempts = tuple(trial.attempts[0] for trial in batch_input.trials)
    first_passes = sum(_attempt_outcome(attempt) == "pass" for attempt in first_attempts)
    valid_attempts = sum(
        _attempt_outcome(attempt) in {"pass", "behavioral_fail"} for attempt in attempts
    )
    infrastructure = Counter(
        attempt.lifecycle.category for attempt in attempts if attempt.lifecycle is not None
    )
    return BatchAttemptDiagnostics(
        total_attempts=len(attempts),
        first_attempts=len(first_attempts),
        retry_attempts=len(attempts) - len(first_attempts),
        trials_with_retry=sum(len(trial.attempts) > 1 for trial in batch_input.trials),
        first_attempt_success_rate=_rate(first_passes, len(first_attempts)),
        retry_rate=_rate(
            sum(len(trial.attempts) > 1 for trial in batch_input.trials),
            len(batch_input.trials),
        ),
        evaluation_validity_rate=_rate(valid_attempts, len(attempts)),
        infrastructure_failures=tuple(
            BatchDistributionEntry(name=name, count=count)
            for name, count in sorted(infrastructure.items())
        ),
        duration_milliseconds=_verified_total(
            attempt.resources.duration_milliseconds for attempt in attempts
        ),
        input_tokens=_verified_total(attempt.resources.input_tokens for attempt in attempts),
        output_tokens=_verified_total(attempt.resources.output_tokens for attempt in attempts),
        cost_microunits=_verified_total(attempt.resources.cost_microunits for attempt in attempts),
    )


def _failure_codes(batch_input: BatchInput) -> tuple[BatchFailureCodeCount, ...]:
    counts: Counter[tuple[str, str, str]] = Counter()
    for trial in batch_input.trials:
        package = trial.attempts[-1].evaluation
        if package is None:
            continue
        receipt, report = validate_evaluation_package_content(package.file_payloads())
        if report is None or receipt.case_outcome == "pass":
            continue
        for record in report.records:
            if record.role in {"outcome", "constraint"} and (
                record.validity != "valid" or record.value is False
            ):
                counts[
                    (receipt.profile.profile_id, receipt.profile.profile_version, record.id)
                ] += 1
    return tuple(
        BatchFailureCodeCount(
            profile_id=profile_id,
            profile_version=profile_version,
            code=code,
            count=count,
        )
        for (profile_id, profile_version, code), count in sorted(counts.items())
    )


def build_batch_summary(batch_input: BatchInput) -> BatchSummary:
    """Derive one deterministic validity-first summary without Runtime access."""

    cases = sorted({item.case_id for item in batch_input.trials})
    configurations = sorted({item.configuration_id for item in batch_input.trials})
    by_configuration = tuple(
        _group(
            (item for item in batch_input.trials if item.configuration_id == configuration),
            case_id=None,
            configuration_id=configuration,
        )
        for configuration in configurations
    )
    by_case = tuple(
        _group(
            (item for item in batch_input.trials if item.case_id == case),
            case_id=case,
            configuration_id=None,
        )
        for case in cases
    )
    cells = sorted({(item.case_id, item.configuration_id) for item in batch_input.trials})
    by_cell = tuple(
        _group(
            (
                item
                for item in batch_input.trials
                if item.case_id == case and item.configuration_id == configuration
            ),
            case_id=case,
            configuration_id=configuration,
        )
        for case, configuration in cells
    )
    overall = _group(batch_input.trials, case_id=None, configuration_id=None)
    attempt_diagnostics = _attempt_diagnostics(batch_input)
    failure_codes = _failure_codes(batch_input)
    payload: dict[str, object] = {
        "schema_version": BATCH_SUMMARY_SCHEMA_VERSION,
        "batch_input_id": batch_input.batch_input_id,
        "batch_input_sha256": batch_input.batch_input_sha256,
        "run_plan_id": batch_input.run_plan_id,
        "execution_id": batch_input.execution_id,
        "overall": overall.model_dump(mode="json"),
        "by_configuration": [item.model_dump(mode="json") for item in by_configuration],
        "by_case": [item.model_dump(mode="json") for item in by_case],
        "by_cell": [item.model_dump(mode="json") for item in by_cell],
        "attempt_diagnostics": attempt_diagnostics.model_dump(mode="json"),
        "profile_failure_codes": [item.model_dump(mode="json") for item in failure_codes],
    }
    digest = _sha256(canonical_json(payload))
    payload["summary_id"] = f"batch-summary-{digest}"
    payload["summary_sha256"] = digest
    return decode_contract(canonical_json(payload), BatchSummary)


def _format_rate(rate: BatchRate) -> str:
    return "unavailable" if rate.value is None else f"{rate.value:.6f}"


def render_batch_summary_markdown(summary: BatchSummary) -> bytes:
    """Render deterministic Markdown containing only authoritative Summary facts."""

    lines = [
        "# Cernora Batch Summary",
        "",
        f"- Summary ID: `{summary.summary_id}`",
        f"- Batch Input ID: `{summary.batch_input_id}`",
        f"- RunPlan ID: `{summary.run_plan_id}`",
        f"- Execution ID: `{summary.execution_id}`",
        "",
        "## Overall",
        "",
        "| Planned | Pass | Behavioral fail | Evaluation invalid | Infrastructure unavailable |",
        "| ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {summary.overall.planned_trials} | {summary.overall.outcomes.passed} | "
            f"{summary.overall.outcomes.behavioral_failed} | "
            f"{summary.overall.outcomes.evaluation_invalid} | "
            f"{summary.overall.outcomes.infrastructure_unavailable} |"
        ),
        "",
        "| Evaluation validity | Behavioral success | Reliable success |",
        "| ---: | ---: | ---: |",
        (
            f"| {_format_rate(summary.overall.evaluation_validity_rate)} | "
            f"{_format_rate(summary.overall.behavioral_success_rate)} | "
            f"{_format_rate(summary.overall.reliable_success_rate)} |"
        ),
        "",
        "## Attempt diagnostics",
        "",
        f"- Total Attempts: {summary.attempt_diagnostics.total_attempts}",
        f"- Retry Attempts: {summary.attempt_diagnostics.retry_attempts}",
        (
            "- First-attempt success rate: "
            f"{_format_rate(summary.attempt_diagnostics.first_attempt_success_rate)}"
        ),
        (
            "- Attempt evaluation-validity rate: "
            f"{_format_rate(summary.attempt_diagnostics.evaluation_validity_rate)}"
        ),
        "",
        "## Groups",
        "",
        "| Case | Configuration | Planned | Pass | Behavioral fail | Invalid | Unavailable |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for group in summary.by_cell:
        lines.append(
            f"| {group.case_id} | {group.configuration_id} | {group.planned_trials} | "
            f"{group.outcomes.passed} | {group.outcomes.behavioral_failed} | "
            f"{group.outcomes.evaluation_invalid} | "
            f"{group.outcomes.infrastructure_unavailable} |"
        )
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def _summary_files(summary: BatchSummary, batch_input: BatchInput) -> dict[str, bytes]:
    receipt = BatchSummaryReceipt(
        schema_version="agent.evaluator.batch-summary-receipt/v1",
        status="summarized",
        summary_id=summary.summary_id,
        summary_sha256=summary.summary_sha256,
        batch_input_id=summary.batch_input_id,
        batch_input_sha256=summary.batch_input_sha256,
    )
    files = {
        INPUT_PATH: canonical_json(batch_input),
        SUMMARY_PATH: canonical_json(summary),
        MARKDOWN_PATH: render_batch_summary_markdown(summary),
        RECEIPT_PATH: canonical_json(receipt),
    }
    manifest = BatchSummaryManifest(
        schema_version="agent.evaluator.batch-summary-manifest/v1",
        files=tuple(
            BatchSummaryFileDigest(path=path, size_bytes=len(payload), sha256=_sha256(payload))
            for path, payload in sorted(files.items())
        ),
    )
    files[MANIFEST_PATH] = canonical_json(manifest)
    return files


def _ordinary_tree_files(root: Path, *, label: str) -> dict[str, bytes]:
    return ordinary_tree_files(root, label=label)


def summarize_batch(batch_input: BatchInput, output: Path) -> BatchSummary:
    """Build, atomically publish, and strictly reload one Batch Summary package."""

    summary = build_batch_summary(batch_input)
    publish_closed_package(output, _summary_files(summary, batch_input), label="Batch Summary")
    reloaded = reload_batch_summary(output)
    if reloaded != summary:
        raise IngestionIntegrityError("published Batch Summary changed during strict reload")
    return reloaded


def reload_batch_summary_package(root: Path) -> BatchSummaryPackage:
    """Strictly reload the path-free contents of one closed Batch Summary package."""

    files = _ordinary_tree_files(root, label="Batch Summary package")
    try:
        manifest = decode_contract(files[MANIFEST_PATH], BatchSummaryManifest)
    except (KeyError, ContractError) as exc:
        raise IngestionIntegrityError("invalid Batch Summary manifest") from exc
    expected_paths = {MANIFEST_PATH, *(item.path for item in manifest.files)}
    if set(files) != expected_paths:
        raise IngestionIntegrityError("Batch Summary file set does not match manifest")
    for item in manifest.files:
        payload = files[item.path]
        if len(payload) != item.size_bytes or _sha256(payload) != item.sha256:
            raise IngestionIntegrityError("Batch Summary file digest mismatch")
    try:
        batch_input = _decode_batch_input(files[INPUT_PATH])
        summary = decode_contract(files[SUMMARY_PATH], BatchSummary)
        receipt = decode_contract(files[RECEIPT_PATH], BatchSummaryReceipt)
    except (KeyError, ContractError) as exc:
        raise IngestionIntegrityError("invalid Batch Summary contract") from exc
    if receipt != BatchSummaryReceipt(
        schema_version="agent.evaluator.batch-summary-receipt/v1",
        status="summarized",
        summary_id=summary.summary_id,
        summary_sha256=summary.summary_sha256,
        batch_input_id=summary.batch_input_id,
        batch_input_sha256=summary.batch_input_sha256,
    ):
        raise IngestionIntegrityError("Batch Summary receipt does not bind the Summary")
    expected_summary = build_batch_summary(batch_input)
    if summary != expected_summary:
        raise IngestionIntegrityError("Batch Summary is not derived from its Batch Input")
    if files != _summary_files(summary, batch_input):
        raise IngestionIntegrityError("Batch Summary package is not canonical")
    return BatchSummaryPackage(batch_input=batch_input, summary=summary)


def reload_batch_summary(root: Path) -> BatchSummary:
    """Strictly reload one closed deterministic Batch Summary package."""

    return reload_batch_summary_package(root).summary


__all__ = [
    "BATCH_INPUT_SCHEMA_VERSION",
    "BATCH_SUMMARY_SCHEMA_VERSION",
    "BatchAttempt",
    "BatchAttemptDiagnostics",
    "BatchAttemptResources",
    "BatchEvaluationFile",
    "BatchEvaluationPackage",
    "BatchFailureCodeCount",
    "BatchGroupSummary",
    "BatchInput",
    "BatchLifecycleRecord",
    "BatchOutcomeCounts",
    "BatchPlannedTrial",
    "BatchRate",
    "BatchSummary",
    "BatchSummaryPackage",
    "BatchTrial",
    "build_batch_summary",
    "embed_evaluation_package",
    "materialize_batch_input",
    "reload_batch_summary",
    "reload_batch_summary_package",
    "render_batch_summary_markdown",
    "summarize_batch",
    "validate_batch_input",
]
