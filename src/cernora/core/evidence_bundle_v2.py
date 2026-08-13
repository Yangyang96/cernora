"""Runtime-neutral external execution EvidenceBundle v2 contract."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Literal, Self

from pydantic import Field, model_validator

from cernora.core.canonical import canonical_json, decode_contract
from cernora.core.case import CaseProfile, StrictModel
from cernora.core.errors import ContractError

IDENTIFIER_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
SCHEMA_VERSION = "agent.evaluator.evidence-bundle/v2"


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _validate_contained_path(path: str) -> None:
    if not path:
        raise ValueError("path must be non-empty")
    if path.startswith("/"):
        raise ValueError("path must be relative")
    if "\\" in path:
        raise ValueError("path must not contain backslashes")
    if any(ord(character) < 32 or ord(character) == 127 for character in path):
        raise ValueError("path must not contain control characters")
    for part in path.split("/"):
        if part == "" or part == "." or part == "..":
            raise ValueError("path must be a canonical POSIX relative path")


class BundleProducerIdentity(StrictModel):
    producer_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    producer_version: str = Field(min_length=1)


class BundleRunIdentity(StrictModel):
    run_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    attempt_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)


class BundleProfileIdentity(StrictModel):
    profile_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    profile_version: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)


class BundleCaseIdentity(StrictModel):
    case_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    case_version: str = Field(min_length=1)
    case_set: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)


class BundleFixtureIdentity(StrictModel):
    fixture_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def contained_path(self) -> Self:
        _validate_contained_path(self.path)
        return self


class BundleArtifact(StrictModel):
    artifact_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=0)
    media_type: str = Field(min_length=1)

    @model_validator(mode="after")
    def contained_path(self) -> Self:
        _validate_contained_path(self.path)
        return self


class ArtifactPointer(StrictModel):
    artifact_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)


class ToolResultReceiptV2(StrictModel):
    status: Literal["completed", "failed", "timed_out"]
    exit_code: int | None
    committed: bool
    delivered: bool
    stdout_artifact: ArtifactPointer
    stderr_artifact: ArtifactPointer

    @model_validator(mode="after")
    def coherent_process_status(self) -> Self:
        if self.status == "timed_out":
            if self.exit_code is not None:
                raise ValueError("timed_out tool results cannot have an exit code")
        else:
            if self.exit_code is None:
                raise ValueError("completed and failed tool results require an exit code")
            if self.status == "completed" and self.exit_code != 0:
                raise ValueError("completed tool results require exit code zero")
            if self.status == "failed" and self.exit_code == 0:
                raise ValueError("failed tool results require a non-zero exit code")
        return self


class BundleToolActionV2(StrictModel):
    sequence: int = Field(ge=0)
    invocation_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    tool: str = Field(min_length=1)
    argv: tuple[str, ...] = Field(min_length=1)
    result: ToolResultReceiptV2
    previous_receipt_sha256: str | None = Field(pattern=SHA256_PATTERN)
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def valid_receipt_digest(self) -> Self:
        payload = self.model_dump(mode="json", exclude_none=False)
        payload.pop("receipt_sha256")
        if self.receipt_sha256 != _canonical_sha256(payload):
            raise ValueError("tool action receipt SHA-256 does not match its canonical content")
        return self


class TerminalAnswer(StrictModel):
    content: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    artifact: ArtifactPointer

    @model_validator(mode="after")
    def valid_content_digest(self) -> Self:
        digest = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if self.sha256 != digest:
            raise ValueError("terminal answer SHA-256 does not match its UTF-8 content")
        if self.artifact.sha256 != self.sha256:
            raise ValueError("terminal answer artifact digest does not match answer content")
        return self


class BundleFailure(StrictModel):
    domain: Literal["agent", "tool", "runtime", "infrastructure", "evidence"]
    code: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    message: str = Field(min_length=1)


class BundleTerminal(StrictModel):
    status: Literal["completed", "agent_failed", "inconclusive"]
    answer: TerminalAnswer | None
    failure: BundleFailure | None

    @model_validator(mode="after")
    def coherent_terminal_state(self) -> Self:
        if self.status == "completed":
            if self.answer is None or self.failure is not None:
                raise ValueError("completed runs require an answer and no failure")
        elif self.status == "agent_failed":
            if self.answer is not None:
                raise ValueError("failure runs cannot contain an answer")
            if self.failure is None or self.failure.domain != "agent":
                raise ValueError("agent_failed runs require an agent failure")
        else:
            if self.answer is not None:
                raise ValueError("failure runs cannot contain an answer")
            if self.failure is None or self.failure.domain == "agent":
                raise ValueError("inconclusive runs require a non-agent failure")
        return self


class InfrastructureStatus(StrictModel):
    status: Literal["valid", "inconclusive"]
    failure: BundleFailure | None

    @model_validator(mode="after")
    def coherent_infrastructure_state(self) -> Self:
        if self.status == "valid" and self.failure is not None:
            raise ValueError("valid infrastructure cannot carry a failure")
        if self.status == "inconclusive" and (
            self.failure is None or self.failure.domain != "infrastructure"
        ):
            raise ValueError("inconclusive infrastructure requires an infrastructure failure")
        return self


class EvidenceBundleV2(StrictModel):
    schema_version: Literal["agent.evaluator.evidence-bundle/v2"]
    bundle_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    producer: BundleProducerIdentity
    run: BundleRunIdentity
    profile: BundleProfileIdentity
    case: BundleCaseIdentity
    fixtures: tuple[BundleFixtureIdentity, ...]
    tool_actions: tuple[BundleToolActionV2, ...]
    artifacts: tuple[BundleArtifact, ...]
    terminal: BundleTerminal
    infrastructure: InfrastructureStatus
    bundle_sha256: str = Field(pattern=SHA256_PATTERN)

    @property
    def evaluation_boundary(
        self,
    ) -> (
        tuple[Literal["pass"], Literal["fail"]]
        | tuple[Literal["fail"]]
        | tuple[Literal["inconclusive"]]
    ):
        """Return the only evaluator result class allowed by this evidence state."""

        if self.infrastructure.status != "valid" or self.terminal.status == "inconclusive":
            return ("inconclusive",)
        if self.terminal.status == "completed":
            return ("pass", "fail")
        return ("fail",)

    @model_validator(mode="after")
    def validate_bundle_integrity(self) -> Self:
        action_ids = [action.invocation_id for action in self.tool_actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("tool invocation IDs must be unique")

        for action in self.tool_actions:
            action_result = action.result
            stdout_id = action_result.stdout_artifact.artifact_id
            stderr_id = action_result.stderr_artifact.artifact_id
            if stdout_id == stderr_id:
                raise ValueError("stdout and stderr artifacts must be distinct")

        previous: str | None = None
        for expected_sequence, action in enumerate(self.tool_actions):
            if action.sequence != expected_sequence:
                raise ValueError("tool action sequence must be contiguous and ordered")
            if action.previous_receipt_sha256 != previous:
                raise ValueError("tool action receipt chain is broken")
            previous = action.receipt_sha256

        artifact_ids = [artifact.artifact_id for artifact in self.artifacts]
        artifact_paths = [artifact.path for artifact in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("artifact IDs must be unique")
        if len(artifact_paths) != len(set(artifact_paths)):
            raise ValueError("artifact paths must be unique")
        artifacts = {artifact.artifact_id: artifact for artifact in self.artifacts}

        pointer_ids: list[str] = []
        for action in self.tool_actions:
            pointer_ids.append(action.result.stdout_artifact.artifact_id)
            pointer_ids.append(action.result.stderr_artifact.artifact_id)
        if self.terminal.answer is not None:
            pointer_ids.append(self.terminal.answer.artifact.artifact_id)
        if sorted(pointer_ids) != sorted(artifact_ids):
            raise ValueError("every declared artifact must be referenced exactly once")

        if self.terminal.answer is not None:
            answer_artifact = artifacts[self.terminal.answer.artifact.artifact_id]
            if answer_artifact.size_bytes != len(self.terminal.answer.content.encode("utf-8")):
                raise ValueError("terminal answer artifact size does not match answer content")

        fixture_ids = [fixture.fixture_id for fixture in self.fixtures]
        if len(fixture_ids) != len(set(fixture_ids)):
            raise ValueError("fixture IDs must be unique")

        if self.infrastructure.status == "inconclusive":
            if self.terminal.status != "inconclusive":
                raise ValueError("inconclusive infrastructure requires an inconclusive terminal")
            if self.terminal.failure != self.infrastructure.failure:
                raise ValueError("infrastructure and terminal failures must agree")
        elif self.terminal.failure is not None and self.terminal.failure.domain == "infrastructure":
            raise ValueError("terminal infrastructure failure requires inconclusive infrastructure")

        payload = self.model_dump(mode="json", exclude_none=False)
        payload.pop("bundle_sha256")
        if self.bundle_sha256 != _canonical_sha256(payload):
            raise ValueError("bundle SHA-256 does not match its canonical content")

        for action in self.tool_actions:
            stdout = action.result.stdout_artifact
            stderr = action.result.stderr_artifact
            if artifacts[stdout.artifact_id].sha256 != stdout.sha256:
                raise ValueError("stdout artifact pointer digest does not match declaration")
            if artifacts[stderr.artifact_id].sha256 != stderr.sha256:
                raise ValueError("stderr artifact pointer digest does not match declaration")
        if self.terminal.answer is not None:
            answer_pointer = self.terminal.answer.artifact
            if artifacts[answer_pointer.artifact_id].sha256 != answer_pointer.sha256:
                raise ValueError("terminal answer artifact digest does not match declaration")
        return self


def decode_evidence_bundle_v2(raw: str | bytes) -> EvidenceBundleV2:
    """Strictly decode one EvidenceBundle v2, rejecting duplicate and unknown fields."""

    return decode_contract(raw, EvidenceBundleV2)


def canonical_evidence_bundle_v2(bundle: EvidenceBundleV2) -> bytes:
    """Return the canonical, digest-stable serialized EvidenceBundle v2."""

    return canonical_json(bundle)


def bind_evidence_bundle_v2(bundle: EvidenceBundleV2, profile: CaseProfile) -> EvidenceBundleV2:
    """Bind a decoded v2 bundle to one authoritative frozen Profile and Case."""

    expected_profile_sha256 = _canonical_sha256(profile.model_dump(mode="json", exclude_none=False))
    if (
        bundle.profile.profile_id != profile.profile_id
        or bundle.profile.profile_version != profile.profile_version
        or bundle.profile.sha256 != expected_profile_sha256
    ):
        raise ContractError("EvidenceBundle v2 profile identity does not match the frozen Profile")

    matching_cases = tuple(case for case in profile.cases if case.case_id == bundle.case.case_id)
    if len(matching_cases) != 1:
        raise ContractError("EvidenceBundle v2 Case is not a unique member of the frozen Profile")
    case = matching_cases[0]
    expected_case_sha256 = _canonical_sha256(case.model_dump(mode="json", exclude_none=False))
    if (
        bundle.case.case_version != case.case_version
        or bundle.case.case_set != case.case_set
        or bundle.case.sha256 != expected_case_sha256
    ):
        raise ContractError("EvidenceBundle v2 Case identity does not match the frozen Case")

    expected_fixtures = tuple(
        fixture.model_dump(mode="json", exclude_none=False) for fixture in case.fixture_references
    )
    actual_fixtures = tuple(
        fixture.model_dump(mode="json", exclude_none=False) for fixture in bundle.fixtures
    )
    if actual_fixtures != expected_fixtures:
        raise ContractError("EvidenceBundle v2 fixtures do not match the frozen Case fixtures")
    return bundle


def verify_artifact_payloads_v2(
    bundle: EvidenceBundleV2, payloads: Mapping[str, bytes]
) -> EvidenceBundleV2:
    """Verify the exact declared artifact set against caller-supplied bytes.

    All v2 streams are strict UTF-8 as a generic wire constraint. No replacement
    decoding, ignored errors, BOM special case, or fallback encoding is permitted.
    """

    expected_ids = {artifact.artifact_id for artifact in bundle.artifacts}
    actual_ids = set(payloads)
    if actual_ids != expected_ids:
        raise ContractError("artifact payload IDs must exactly match the declared artifact set")
    for artifact in bundle.artifacts:
        payload = payloads[artifact.artifact_id]
        if len(payload) != artifact.size_bytes:
            raise ContractError(
                f"artifact payload size does not match declaration: {artifact.artifact_id}"
            )
        if hashlib.sha256(payload).hexdigest() != artifact.sha256:
            raise ContractError(
                f"artifact payload SHA-256 does not match declaration: {artifact.artifact_id}"
            )
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractError(
                f"artifact payload is not strict UTF-8: {artifact.artifact_id}: {exc}"
            ) from exc
    return bundle


__all__ = [
    "ArtifactPointer",
    "BundleArtifact",
    "BundleCaseIdentity",
    "BundleFailure",
    "BundleFixtureIdentity",
    "BundleProducerIdentity",
    "BundleProfileIdentity",
    "BundleRunIdentity",
    "BundleTerminal",
    "BundleToolActionV2",
    "EvidenceBundleV2",
    "InfrastructureStatus",
    "TerminalAnswer",
    "ToolResultReceiptV2",
    "bind_evidence_bundle_v2",
    "canonical_evidence_bundle_v2",
    "decode_evidence_bundle_v2",
    "verify_artifact_payloads_v2",
]
