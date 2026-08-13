"""Deterministic contracts for one authority-bound imported evaluation."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from cernora.core.canonical import canonical_json
from cernora.core.case import FixtureReference, StrictModel
from cernora.core.evidence import Evidence
from cernora.core.evidence_bundle_v2 import (
    BundleCaseIdentity,
    BundleProfileIdentity,
    BundleRunIdentity,
)
from cernora.core.gate import GateDecision
from cernora.core.identity import (
    ComponentIdentity,
    ExternalProducerIdentity,
    identity_digest,
)
from cernora.core.score import Score
from cernora.ingestion.contracts_v2 import ImportedBundleIdentityV2

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ImportedProjectionIdentity(StrictModel):
    name: Literal["imported_projection"]
    version: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    digest_kind: Literal["identity"] = "identity"

    @model_validator(mode="after")
    def valid_projection_identity(self) -> Self:
        expected = identity_digest({"name": self.name, "version": self.version})
        if self.sha256 != expected:
            raise ValueError("projection SHA-256 does not match semantic identity")
        return self


class ImportedEvaluationAuthority(StrictModel):
    schema_version: Literal["agent.evaluator.imported-evaluation-authority/v1"]
    profile: BundleProfileIdentity
    case: BundleCaseIdentity
    fixtures: tuple[FixtureReference, ...] = Field(min_length=1)
    projection: ImportedProjectionIdentity
    scorer: ComponentIdentity
    case_gate: ComponentIdentity
    authority_id: str = Field(min_length=1)
    authority_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("fixtures", mode="before")
    @classmethod
    def tuple_fixtures(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def valid_authority_identity(self) -> Self:
        fixture_ids = tuple(item.fixture_id for item in self.fixtures)
        fixture_paths = tuple(item.path for item in self.fixtures)
        if len(fixture_ids) != len(set(fixture_ids)) or len(fixture_paths) != len(
            set(fixture_paths)
        ):
            raise ValueError("authority fixture identities must be unique")
        if self.scorer.name != "scorer" or self.case_gate.name != "gate_policy":
            raise ValueError("authority component identities have invalid kinds")
        if self.scorer.sha256 != identity_digest(
            {"name": self.scorer.name, "version": self.scorer.version}
        ) or self.case_gate.sha256 != identity_digest(
            {"name": self.case_gate.name, "version": self.case_gate.version}
        ):
            raise ValueError("authority component SHA-256 does not match semantic identity")
        payload = self.model_dump(
            mode="json",
            exclude={"authority_id", "authority_sha256"},
        )
        digest = hashlib.sha256(canonical_json(payload)).hexdigest()
        if self.authority_sha256 != digest:
            raise ValueError("authority SHA-256 does not match canonical authority")
        if self.authority_id != f"imported-authority-{digest}":
            raise ValueError("authority ID does not match authority SHA-256")
        return self

    @property
    def scorer_policy_version(self) -> str:
        return self.scorer.version

    @property
    def gate_policy_version(self) -> str:
        return self.case_gate.version


class ImportedCaseEvaluation(StrictModel):
    authority: ImportedEvaluationAuthority
    evidence: Evidence
    score: Score
    decision: GateDecision


def _validate_contained_path(path: str, *, label: str) -> None:
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
        raise ValueError(f"{label} must be a contained canonical POSIX relative path")


class ImportedEvaluationFileDigest(StrictModel):
    path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def contained_payload_path(self) -> Self:
        _validate_contained_path(self.path, label="imported evaluation manifest entry")
        if self.path == "digests.json":
            raise ValueError("evaluation manifest cannot contain itself")
        return self


class ImportedEvaluationManifest(StrictModel):
    schema_version: Literal["agent.evaluator.imported-evaluation-manifest/v1"]
    files: tuple[ImportedEvaluationFileDigest, ...] = Field(min_length=6)

    @model_validator(mode="after")
    def sorted_unique_paths(self) -> Self:
        paths = tuple(item.path for item in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("evaluation manifest paths must be sorted and unique")
        return self


class ImportedEvaluationReceipt(StrictModel):
    schema_version: Literal["agent.evaluator.imported-evaluation-receipt/v1"]
    status: Literal["evaluated"]
    scope: Literal["single_case_attempt"]
    case_outcome: Literal["pass", "fail", "inconclusive"]
    eligible: bool
    profile_gate_status: Literal["not_evaluated"]
    harness_status: Literal["not_evaluated"]
    evaluation_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    score_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    evaluation_input_sha256: str = Field(pattern=SHA256_PATTERN)
    authority: ImportedEvaluationAuthority
    authority_sha256: str = Field(pattern=SHA256_PATTERN)
    bundle: ImportedBundleIdentityV2
    producer: ExternalProducerIdentity
    run: BundleRunIdentity
    profile: BundleProfileIdentity
    case: BundleCaseIdentity
    fixtures: tuple[FixtureReference, ...] = Field(min_length=1)
    source_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    declared_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    raw_input_sha256: str = Field(pattern=SHA256_PATTERN)
    scorer: ComponentIdentity
    case_gate: ComponentIdentity

    @model_validator(mode="after")
    def bound_result_identity(self) -> Self:
        digest = self.evaluation_input_sha256
        expected_ids = (
            (self.evaluation_id, f"imported-evaluation-{digest}"),
            (self.evidence_id, f"imported-evidence-{digest}"),
            (self.score_id, f"imported-score-{digest}"),
            (self.decision_id, f"imported-decision-{digest}"),
        )
        if any(actual != expected for actual, expected in expected_ids):
            raise ValueError("evaluation result IDs do not match evaluation input SHA-256")
        if self.eligible != (self.case_outcome != "inconclusive"):
            raise ValueError("evaluation eligibility does not match case outcome")
        if self.authority_sha256 != self.authority.authority_sha256:
            raise ValueError("receipt authority SHA-256 does not match authority record")
        if self.profile != self.authority.profile or self.case != self.authority.case:
            raise ValueError("receipt Profile or Case identity does not match authority")
        if self.fixtures != self.authority.fixtures:
            raise ValueError("receipt fixtures do not match authority")
        if self.scorer != self.authority.scorer or self.case_gate != self.authority.case_gate:
            raise ValueError("receipt component identity does not match authority")
        fixture_ids = tuple(item.fixture_id for item in self.fixtures)
        fixture_paths = tuple(item.path for item in self.fixtures)
        if len(fixture_ids) != len(set(fixture_ids)) or len(fixture_paths) != len(
            set(fixture_paths)
        ):
            raise ValueError("receipt fixture identities must be unique")
        return self


__all__ = [
    "ImportedCaseEvaluation",
    "ImportedEvaluationAuthority",
    "ImportedEvaluationFileDigest",
    "ImportedEvaluationManifest",
    "ImportedEvaluationReceipt",
    "ImportedProjectionIdentity",
]
