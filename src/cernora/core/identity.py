"""Strict external producer and evaluator component identities."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field

from cernora.core.canonical import canonical_json
from cernora.core.case import StrictModel

SHA256_PATTERN = r"^[0-9a-f]{64}$"


def identity_digest(value: object) -> str:
    """Digest a declared semantic identity, not executable provenance bytes."""

    return hashlib.sha256(canonical_json(value)).hexdigest()


class ExternalProducerIdentity(StrictModel):
    schema_version: Literal["agent.evaluator.producer-identity/v1"]
    kind: Literal["external"]
    producer_id: str = Field(min_length=1)
    producer_version: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)


class ComponentIdentity(StrictModel):
    name: Literal["scorer", "gate_policy"]
    version: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    digest_kind: Literal["identity"] = "identity"


def external_producer_identity(
    producer_id: str,
    producer_version: str,
) -> ExternalProducerIdentity:
    declared = {
        "kind": "external",
        "producer_id": producer_id,
        "producer_version": producer_version,
    }
    return ExternalProducerIdentity(
        schema_version="agent.evaluator.producer-identity/v1",
        kind="external",
        producer_id=producer_id,
        producer_version=producer_version,
        sha256=identity_digest(declared),
    )


def component_identity(name: Literal["scorer", "gate_policy"], version: str) -> ComponentIdentity:
    return ComponentIdentity(
        name=name,
        version=version,
        sha256=identity_digest({"name": name, "version": version}),
    )


__all__ = [
    "ComponentIdentity",
    "ExternalProducerIdentity",
    "component_identity",
    "external_producer_identity",
    "identity_digest",
]
