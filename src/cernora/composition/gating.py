"""Deterministic fail-closed GateDecision composition."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from cernora.composition.scoring import index_scores
from cernora.core.evidence import (
    EvidenceReference,
    Failure,
    evidence_reference_sort_key,
)
from cernora.core.gate import GateDecision
from cernora.core.identity import component_identity
from cernora.core.score import Score


def compose_gate(
    *,
    decision_id: str,
    policy_version: str,
    required_score_ids: Sequence[str],
    required_observations: Sequence[str],
    scores: Iterable[Score],
) -> GateDecision:
    """Compose a decision without converting invalid/missing observations into pass."""

    indexed = index_scores(scores)
    blocking: list[str] = []
    inconclusive: list[str] = []
    evidence: dict[tuple[str, str, str | None], EvidenceReference] = {}

    for score_id in required_score_ids:
        score = indexed.get(score_id)
        if score is None:
            inconclusive.append(f"missing required score: {score_id}")
            continue
        observations = {item.observation_id: item for item in score.observations}
        for observation in score.observations:
            for reference in observation.evidence_references:
                evidence[(reference.evidence_id, reference.locator, reference.sha256)] = reference
        for observation_id in required_observations:
            required = observations.get(observation_id)
            if required is None:
                inconclusive.append(f"missing required observation {score_id}/{observation_id}")
            elif required.applicability == "invalid":
                inconclusive.append(
                    f"invalid observation {score_id}/{required.observation_id}: {required.reason}"
                )
            elif required.applicability == "not_applicable":
                inconclusive.append(
                    f"required observation not applicable {score_id}/{required.observation_id}: "
                    f"{required.reason}"
                )
            elif required.applicability == "observed" and required.value is not True:
                blocking.append(f"failed observation {score_id}/{required.observation_id}")

    present_score_ids = tuple(score_id for score_id in required_score_ids if score_id in indexed)
    references = tuple(sorted(evidence.values(), key=evidence_reference_sort_key))
    scorer_identities = tuple(
        component_identity("scorer", indexed[score_id].scorer_version)
        for score_id in present_score_ids
    )
    input_digests = tuple(
        sorted({reference.sha256 for reference in references if reference.sha256 is not None})
    )
    if inconclusive:
        message = "; ".join(inconclusive)
        return GateDecision(
            schema_version="agent.evaluator.gate-decision/v1",
            decision_id=decision_id,
            decision="inconclusive",
            policy_version=policy_version,
            policy_identity=component_identity("gate_policy", policy_version),
            blocking_reasons=tuple(inconclusive),
            score_ids=present_score_ids,
            evidence_references=references,
            infrastructure_failure="required_score_invalid_or_missing",
            eligible=False,
            failure=Failure(
                domain="scorer",
                code="required_score_invalid_or_missing",
                message=message,
                evidence_references=references,
            ),
            scorer_identities=scorer_identities,
            input_digests=input_digests,
            harness_contribution="blocks_harness",
        )
    if blocking:
        message = "; ".join(blocking)
        return GateDecision(
            schema_version="agent.evaluator.gate-decision/v1",
            decision_id=decision_id,
            decision="fail",
            policy_version=policy_version,
            policy_identity=component_identity("gate_policy", policy_version),
            blocking_reasons=tuple(blocking),
            score_ids=present_score_ids,
            evidence_references=references,
            eligible=True,
            failure=Failure(
                domain="agent",
                code="required_observation_failed",
                message=message,
                evidence_references=references,
            ),
            scorer_identities=scorer_identities,
            input_digests=input_digests,
            harness_contribution="eligible_evaluation",
        )
    return GateDecision(
        schema_version="agent.evaluator.gate-decision/v1",
        decision_id=decision_id,
        decision="pass",
        policy_version=policy_version,
        policy_identity=component_identity("gate_policy", policy_version),
        blocking_reasons=(),
        score_ids=present_score_ids,
        evidence_references=references,
        eligible=True,
        failure=None,
        scorer_identities=scorer_identities,
        input_digests=input_digests,
        harness_contribution="eligible_evaluation",
    )
