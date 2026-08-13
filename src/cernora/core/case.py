"""Case and profile contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CASE_PROFILE_SCHEMA_VERSION = "agent.evaluator.case-profile/v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class FixtureReference(StrictModel):
    fixture_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CaseInput(StrictModel):
    prompt: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class Case(StrictModel):
    case_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    case_version: str = Field(min_length=1)
    case_set: str = Field(min_length=1)
    input: CaseInput
    declared_capabilities: tuple[str, ...]
    fixture_references: tuple[FixtureReference, ...]
    tags: tuple[str, ...] = ()


class ScorerPolicy(StrictModel):
    policy_version: str = Field(min_length=1)
    required_observations: tuple[str, ...] = Field(min_length=1)


class GatePolicy(StrictModel):
    policy_version: str = Field(min_length=1)
    required_score_ids: tuple[str, ...] = Field(min_length=1)
    invalid_result: Literal["inconclusive"] = "inconclusive"


class CaseProfile(StrictModel):
    schema_version: Literal["agent.evaluator.case-profile/v1"]
    profile_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    profile_version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    cases: tuple[Case, ...] = Field(min_length=1)
    scorer_policy: ScorerPolicy
    gate_policy: GatePolicy

    @model_validator(mode="after")
    def unique_case_ids(self) -> CaseProfile:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case IDs must be unique within a profile")
        return self
