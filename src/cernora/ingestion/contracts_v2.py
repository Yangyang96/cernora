"""Strict contracts for deterministic EvidenceBundle v2 import packages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cernora.core.case import Case, CaseProfile, StrictModel
from cernora.core.evidence_bundle_v2 import (
    IDENTIFIER_PATTERN,
    SHA256_PATTERN,
    BundleCaseIdentity,
    BundleProducerIdentity,
    BundleProfileIdentity,
    BundleRunIdentity,
    EvidenceBundleV2,
)


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


class ImportedBundleIdentityV2(StrictModel):
    bundle_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    schema_version: Literal["agent.evaluator.evidence-bundle/v2"]
    declared_sha256: str = Field(pattern=SHA256_PATTERN)


class ImportedToolArtifactOwnerV2(StrictModel):
    invocation_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    kind: Literal["tool_stdout", "tool_stderr"]


class ImportedTerminalArtifactOwnerV2(StrictModel):
    kind: Literal["terminal_answer"]


ImportedArtifactOwnerV2 = Annotated[
    ImportedToolArtifactOwnerV2 | ImportedTerminalArtifactOwnerV2,
    Field(discriminator="kind"),
]


class ImportedArtifactV2(StrictModel):
    artifact_id: str = Field(min_length=1, pattern=IDENTIFIER_PATTERN)
    declared_path: str = Field(min_length=1)
    package_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)
    owner: ImportedArtifactOwnerV2

    @model_validator(mode="after")
    def bound_package_path(self) -> Self:
        _validate_contained_path(self.declared_path, label="imported artifact declaration")
        if self.package_path != f"artifacts/{self.declared_path}":
            raise ValueError("imported artifact package path must preserve its declared path")
        return self


class ImportReceiptV2(StrictModel):
    schema_version: Literal["agent.evaluator.import-receipt/v2"]
    status: Literal["validated"]
    evaluation_status: Literal["not_evaluated"]
    bundle: ImportedBundleIdentityV2
    producer: BundleProducerIdentity
    run: BundleRunIdentity
    profile: BundleProfileIdentity
    case: BundleCaseIdentity
    raw_input_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    artifacts: tuple[ImportedArtifactV2, ...]
    evaluation_boundary: (
        tuple[Literal["pass"], Literal["fail"]]
        | tuple[Literal["fail"]]
        | tuple[Literal["inconclusive"]]
    )

    @model_validator(mode="after")
    def unique_artifacts_and_owners(self) -> Self:
        ids = tuple(item.artifact_id for item in self.artifacts)
        declared_paths = tuple(item.declared_path for item in self.artifacts)
        package_paths = tuple(item.package_path for item in self.artifacts)
        owners = tuple(
            (
                item.owner.kind,
                item.owner.invocation_id
                if isinstance(item.owner, ImportedToolArtifactOwnerV2)
                else None,
            )
            for item in self.artifacts
        )
        if len(ids) != len(set(ids)):
            raise ValueError("import receipt artifact IDs must be unique")
        if len(declared_paths) != len(set(declared_paths)):
            raise ValueError("import receipt declared artifact paths must be unique")
        if len(package_paths) != len(set(package_paths)):
            raise ValueError("import receipt package artifact paths must be unique")
        if len(owners) != len(set(owners)):
            raise ValueError("import receipt artifact owners must be unique")
        return self


class ImportFileDigestV2(StrictModel):
    path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def contained_payload_path(self) -> Self:
        _validate_contained_path(self.path, label="import manifest entry")
        if self.path == "digests.json":
            raise ValueError("import manifest entry must name a contained payload file")
        return self


class ImportManifestV2(StrictModel):
    schema_version: Literal["agent.evaluator.import-manifest/v2"]
    files: tuple[ImportFileDigestV2, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def sorted_unique_paths(self) -> Self:
        paths = tuple(item.path for item in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("import manifest paths must be sorted and unique")
        return self


@dataclass(frozen=True)
class LoadedImportPackageV2:
    bundle: EvidenceBundleV2
    raw_bundle_bytes: bytes
    canonical_bundle_bytes: bytes
    receipt: ImportReceiptV2
    receipt_bytes: bytes
    manifest: ImportManifestV2
    manifest_bytes: bytes
    artifact_bytes: Mapping[str, bytes]

    def __post_init__(self) -> None:
        byte_fields = (
            self.raw_bundle_bytes,
            self.canonical_bundle_bytes,
            self.receipt_bytes,
            self.manifest_bytes,
        )
        if any(type(value) is not bytes for value in byte_fields):
            raise TypeError("loaded import package serialized content must be immutable bytes")
        artifact_bytes = dict(self.artifact_bytes)
        if any(type(value) is not bytes for value in artifact_bytes.values()):
            raise TypeError("loaded import package artifacts must be immutable bytes")
        bundle_ids = tuple(item.artifact_id for item in self.bundle.artifacts)
        receipt_ids = tuple(item.artifact_id for item in self.receipt.artifacts)
        if bundle_ids != receipt_ids or set(artifact_bytes) != set(bundle_ids):
            raise ValueError("loaded import package artifact mapping is not exact")
        object.__setattr__(self, "artifact_bytes", MappingProxyType(artifact_bytes))


@dataclass(frozen=True)
class AuthorityBoundImportPackageV2:
    content: LoadedImportPackageV2
    profile: CaseProfile
    case: Case


__all__ = [
    "AuthorityBoundImportPackageV2",
    "ImportFileDigestV2",
    "ImportManifestV2",
    "ImportReceiptV2",
    "ImportedArtifactOwnerV2",
    "ImportedArtifactV2",
    "ImportedBundleIdentityV2",
    "ImportedTerminalArtifactOwnerV2",
    "ImportedToolArtifactOwnerV2",
    "LoadedImportPackageV2",
]
