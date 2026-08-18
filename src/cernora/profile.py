"""Preview Profile authoring interface.

Profiles validate and assess already completed, authority-bound evidence. They never
start an Agent or own persistence and GateDecision composition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from cernora.core.case import CaseProfile
from cernora.core.evidence import Evidence
from cernora.core.result import ResultRecord
from cernora.core.score import Score
from cernora.ingestion.contracts_v2 import AuthorityBoundImportPackageV2


@dataclass(frozen=True)
class ProfileEvaluationContext:
    """Evaluator-owned deterministic identities supplied to one Profile assessment."""

    evaluation_id: str
    evidence_id: str
    score_id: str
    source_receipt_sha256: str


@dataclass(frozen=True)
class ProfileAssessment:
    """Profile output consumed and cross-checked by the deep evaluator module."""

    evidence: Evidence
    score: Score
    required_observations: tuple[str, ...]
    result_records: tuple[ResultRecord, ...] = ()


@runtime_checkable
class Profile(Protocol):
    """Preview authoring seam for one explicit, offline Profile."""

    @property
    def authority(self) -> CaseProfile: ...

    @property
    def projection_version(self) -> str: ...

    def validate_import(self, package: AuthorityBoundImportPackageV2) -> None: ...

    def assess(
        self,
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
    ) -> ProfileAssessment: ...


__all__ = ["Profile", "ProfileAssessment", "ProfileEvaluationContext"]
