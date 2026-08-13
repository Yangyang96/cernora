"""Deterministic score contract."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from cernora.core.case import StrictModel
from cernora.core.evidence import EvidenceReference


class ScoreObservation(StrictModel):
    observation_id: str = Field(min_length=1)
    applicability: Literal["observed", "not_applicable", "invalid"]
    value: bool | int | str | dict[str, Any] | None
    reason: str | None = None
    evidence_references: tuple[EvidenceReference, ...]

    @model_validator(mode="after")
    def validate_observation(self) -> ScoreObservation:
        if self.applicability == "observed" and not self.evidence_references:
            raise ValueError("observed scores must reference Evidence")
        if self.applicability != "observed" and not self.reason:
            raise ValueError("non-observed scores require a reason")
        return self


class Score(StrictModel):
    schema_version: Literal["agent.evaluator.score/v1"]
    score_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    scorer_version: str = Field(min_length=1)
    observations: tuple[ScoreObservation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_observation_ids(self) -> Score:
        ids = [item.observation_id for item in self.observations]
        if len(ids) != len(set(ids)):
            raise ValueError("score observation IDs must be unique")
        return self
