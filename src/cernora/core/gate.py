"""Fail-closed gate decision contract."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from cernora.core.case import StrictModel
from cernora.core.evidence import EvidenceReference, Failure, is_behavioral_failure
from cernora.core.identity import ComponentIdentity


class GateDecision(StrictModel):
    schema_version: Literal["agent.evaluator.gate-decision/v1"]
    decision_id: str = Field(min_length=1)
    decision: Literal["pass", "fail", "inconclusive"]
    policy_version: str = Field(min_length=1)
    policy_identity: ComponentIdentity
    blocking_reasons: tuple[str, ...]
    score_ids: tuple[str, ...]
    evidence_references: tuple[EvidenceReference, ...]
    infrastructure_failure: str | None = None
    eligible: bool
    failure: Failure | None
    scorer_identities: tuple[ComponentIdentity, ...]
    input_digests: tuple[str, ...]
    harness_contribution: Literal["eligible_evaluation", "blocks_harness"]

    @model_validator(mode="after")
    def validate_references(self) -> GateDecision:
        if self.eligible != (self.decision != "inconclusive"):
            raise ValueError("Gate eligibility must match terminal decision")
        expected_contribution = "eligible_evaluation" if self.eligible else "blocks_harness"
        if self.harness_contribution != expected_contribution:
            raise ValueError("Harness contribution does not match Gate eligibility")
        if self.decision == "pass" and self.failure is not None:
            raise ValueError("pass Gates cannot carry a terminal failure")
        if self.decision == "inconclusive" and self.failure is None:
            raise ValueError("inconclusive Gates require a terminal failure")
        if (
            self.decision == "inconclusive"
            and self.failure is not None
            and is_behavioral_failure(self.failure)
        ):
            raise ValueError("inconclusive Gates require a non-behavioral failure")
        if (
            self.decision == "fail"
            and self.failure is not None
            and not is_behavioral_failure(self.failure)
        ):
            raise ValueError("eligible fail Gates may carry only behavioral failures")
        if self.decision in {"pass", "fail"} and not self.score_ids:
            raise ValueError("pass/fail decisions must reference gating Scores")
        if self.decision == "inconclusive" and not (self.score_ids or self.infrastructure_failure):
            raise ValueError("inconclusive decisions require Scores or an infrastructure failure")
        if self.decision != "pass" and not self.blocking_reasons:
            raise ValueError("fail/inconclusive decisions require blocking reasons")
        if self.decision == "pass" and self.blocking_reasons:
            raise ValueError("pass decisions cannot contain blocking reasons")
        if self.score_ids and not self.evidence_references:
            raise ValueError("gating Scores require Evidence references")
        if self.score_ids and not self.scorer_identities:
            raise ValueError("gating Scores require typed scorer identities")
        if (
            self.policy_identity.name != "gate_policy"
            or self.policy_identity.version != self.policy_version
        ):
            raise ValueError("typed policy identity must match policy_version")
        if len(self.input_digests) != len(set(self.input_digests)):
            raise ValueError("Gate input digests must be unique")
        return self
