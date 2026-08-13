"""Normalized execution Evidence contract without private chain-of-thought."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from cernora.core.case import StrictModel
from cernora.core.identity import ExternalProducerIdentity

SAFE_IDENTIFIER_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"
BEHAVIORAL_FAILURE_DOMAINS = frozenset({"agent", "candidate", "product_run"})


class EvidenceReference(StrictModel):
    evidence_id: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


def evidence_reference_sort_key(
    reference: EvidenceReference,
) -> tuple[str, str, bool, str]:
    """Return a total deterministic ordering key for nullable reference digests."""

    return (
        reference.evidence_id,
        reference.locator,
        reference.sha256 is not None,
        reference.sha256 or "",
    )


class ProcessResult(StrictModel):
    argv: tuple[str, ...] = Field(min_length=1)
    exit_code: int | None
    timed_out: bool
    stdout_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    stderr_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ToolAction(StrictModel):
    invocation_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    argv: tuple[str, ...] = Field(min_length=1)
    exit_code: int | None
    timed_out: bool
    response_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    committed: bool
    delivered: bool


class Artifact(StrictModel):
    artifact_id: str = Field(min_length=1, pattern=SAFE_IDENTIFIER_PATTERN)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str = Field(min_length=1)

    @model_validator(mode="after")
    def safe_relative_path(self) -> Artifact:
        path = Path(self.path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("artifact path must be relative and contained")
        return self


class AnswerClaim(StrictModel):
    name: str = Field(min_length=1)
    value: Any
    evidence_references: tuple[EvidenceReference, ...] = Field(min_length=1)


class StructuredAnswer(StrictModel):
    status: Literal["found", "not_found", "needs_clarification", "completed"]
    claims: tuple[AnswerClaim, ...]

    @model_validator(mode="after")
    def not_found_has_no_claims(self) -> StructuredAnswer:
        if self.status == "not_found" and self.claims:
            raise ValueError("not_found answers must not contain claims")
        return self


class Failure(StrictModel):
    domain: Literal[
        "agent",
        "candidate",
        "product_run",
        "tool",
        "runtime",
        "relay",
        "fixture",
        "infrastructure",
        "scorer",
        "evidence",
        "policy",
    ]
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    evidence_references: tuple[EvidenceReference, ...] = ()


def is_behavioral_failure(failure: Failure) -> bool:
    """Return whether a Failure represents an eligible evaluated outcome."""

    return failure.domain in BEHAVIORAL_FAILURE_DOMAINS


class Evidence(StrictModel):
    schema_version: Literal["agent.evaluator.evidence/v1"]
    evidence_id: str = Field(min_length=1)
    evaluation_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1, pattern=SAFE_IDENTIFIER_PATTERN)
    run_id: str = Field(min_length=1)
    producer: ExternalProducerIdentity
    process: ProcessResult | None
    tool_actions: tuple[ToolAction, ...]
    artifacts: tuple[Artifact, ...]
    answer: StructuredAnswer | None
    failures: tuple[Failure, ...]
    metadata: dict[str, Any] = Field(default_factory=dict)
