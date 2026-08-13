"""Evaluate one strict v2 import through one explicitly supplied Profile."""

from __future__ import annotations

import hashlib
from pathlib import Path

from cernora.composition.gating import compose_gate
from cernora.core.canonical import canonical_json
from cernora.core.evidence import Artifact, Evidence, EvidenceReference, Failure, ToolAction
from cernora.core.identity import component_identity, external_producer_identity, identity_digest
from cernora.core.score import Score, ScoreObservation
from cernora.evaluation.contracts import (
    ImportedCaseEvaluation,
    ImportedEvaluationAuthority,
    ImportedProjectionIdentity,
)
from cernora.ingestion.contracts_v2 import AuthorityBoundImportPackageV2
from cernora.ingestion.errors import IngestionIntegrityError
from cernora.ingestion.package_v2 import (
    bind_import_package_v2_authority,
    read_import_package_v2_content,
)
from cernora.profile import Profile, ProfileAssessment, ProfileEvaluationContext


def _authority(
    bound: AuthorityBoundImportPackageV2,
    profile: Profile,
) -> ImportedEvaluationAuthority:
    projection = ImportedProjectionIdentity(
        name="imported_projection",
        version=profile.projection_version,
        sha256=identity_digest(
            {"name": "imported_projection", "version": profile.projection_version}
        ),
    )
    scorer = component_identity("scorer", bound.profile.scorer_policy.policy_version)
    case_gate = component_identity("gate_policy", bound.profile.gate_policy.policy_version)
    payload = {
        "schema_version": "agent.evaluator.imported-evaluation-authority/v1",
        "profile": bound.content.bundle.profile.model_dump(mode="json", exclude_none=False),
        "case": bound.content.bundle.case.model_dump(mode="json", exclude_none=False),
        "fixtures": [
            item.model_dump(mode="json", exclude_none=False)
            for item in bound.case.fixture_references
        ],
        "projection": projection.model_dump(mode="json", exclude_none=False),
        "scorer": scorer.model_dump(mode="json", exclude_none=False),
        "case_gate": case_gate.model_dump(mode="json", exclude_none=False),
    }
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()
    return ImportedEvaluationAuthority(
        schema_version="agent.evaluator.imported-evaluation-authority/v1",
        profile=bound.content.bundle.profile,
        case=bound.content.bundle.case,
        fixtures=bound.case.fixture_references,
        projection=projection,
        scorer=scorer,
        case_gate=case_gate,
        authority_id=f"imported-authority-{digest}",
        authority_sha256=digest,
    )


def _scorer_failure_assessment(
    bound: AuthorityBoundImportPackageV2,
    context: ProfileEvaluationContext,
    exc: Exception,
) -> ProfileAssessment:
    bundle = bound.content.bundle
    reference = EvidenceReference(
        evidence_id=context.evidence_id,
        locator="source-import/import-receipt.json",
        sha256=context.source_receipt_sha256,
    )
    failure = Failure(
        domain="scorer",
        code="profile_assessment_failed",
        message=f"Profile assessment failed closed: {type(exc).__name__}",
        evidence_references=(reference,),
    )
    evidence = Evidence(
        schema_version="agent.evaluator.evidence/v1",
        evidence_id=context.evidence_id,
        evaluation_id=context.evaluation_id,
        profile_id=bundle.profile.profile_id,
        case_id=bundle.case.case_id,
        run_id=bundle.run.run_id,
        producer=external_producer_identity(
            bundle.producer.producer_id,
            bundle.producer.producer_version,
        ),
        process=None,
        tool_actions=tuple(
            ToolAction(
                invocation_id=action.invocation_id,
                tool=action.tool,
                argv=action.argv,
                exit_code=action.result.exit_code,
                timed_out=action.result.status == "timed_out",
                response_sha256=action.result.stdout_artifact.sha256,
                committed=action.result.committed,
                delivered=action.result.delivered,
            )
            for action in bundle.tool_actions
        ),
        artifacts=tuple(
            Artifact(
                artifact_id=item.artifact_id,
                path=item.path,
                sha256=item.sha256,
                media_type=item.media_type,
            )
            for item in bundle.artifacts
        ),
        answer=None,
        failures=(failure,),
        metadata={
            "attempt_id": bundle.run.attempt_id,
            "bundle_terminal_status": bundle.terminal.status,
            "infrastructure_valid": bundle.infrastructure.status == "valid",
        },
    )
    score = Score(
        schema_version="agent.evaluator.score/v1",
        score_id=context.score_id,
        evidence_id=context.evidence_id,
        scorer_version=bound.profile.scorer_policy.policy_version,
        observations=tuple(
            ScoreObservation(
                observation_id=observation_id,
                applicability="invalid",
                value=None,
                reason="Profile assessment failed closed",
                evidence_references=(reference,),
            )
            for observation_id in bound.profile.scorer_policy.required_observations
        ),
    )
    return ProfileAssessment(
        evidence=evidence,
        score=score,
        required_observations=bound.profile.scorer_policy.required_observations,
    )


def _check_assessment(
    bound: AuthorityBoundImportPackageV2,
    context: ProfileEvaluationContext,
    assessment: ProfileAssessment,
) -> None:
    evidence = assessment.evidence
    score = assessment.score
    bundle = bound.content.bundle
    expected_producer = external_producer_identity(
        bundle.producer.producer_id,
        bundle.producer.producer_version,
    )
    expected_actions = tuple(
        ToolAction(
            invocation_id=action.invocation_id,
            tool=action.tool,
            argv=action.argv,
            exit_code=action.result.exit_code,
            timed_out=action.result.status == "timed_out",
            response_sha256=action.result.stdout_artifact.sha256,
            committed=action.result.committed,
            delivered=action.result.delivered,
        )
        for action in bundle.tool_actions
    )
    expected_artifacts = tuple(
        Artifact(
            artifact_id=item.artifact_id,
            path=item.path,
            sha256=item.sha256,
            media_type=item.media_type,
        )
        for item in bundle.artifacts
    )
    if assessment.required_observations != bound.profile.scorer_policy.required_observations:
        raise IngestionIntegrityError("Profile assessment changed required observations")
    if (
        evidence.evaluation_id != context.evaluation_id
        or evidence.evidence_id != context.evidence_id
        or evidence.profile_id != bundle.profile.profile_id
        or evidence.case_id != bundle.case.case_id
        or evidence.run_id != bundle.run.run_id
    ):
        raise IngestionIntegrityError("Profile Evidence identity is not authority-bound")
    if (
        evidence.producer != expected_producer
        or evidence.process is not None
        or evidence.tool_actions != expected_actions
        or evidence.artifacts != expected_artifacts
    ):
        raise IngestionIntegrityError("Profile Evidence changed imported producer facts")
    if (
        score.score_id != context.score_id
        or score.evidence_id != context.evidence_id
        or score.scorer_version != bound.profile.scorer_policy.policy_version
    ):
        raise IngestionIntegrityError("Profile Score identity is not authority-bound")
    if tuple(item.observation_id for item in score.observations) != (
        bound.profile.scorer_policy.required_observations
    ):
        raise IngestionIntegrityError("Profile Score observations do not match authority order")


def evaluate_imported_case_v2(import_root: Path, profile: Profile) -> ImportedCaseEvaluation:
    """Strictly reload and evaluate one package without Profile discovery."""

    loaded = read_import_package_v2_content(import_root)
    bound = bind_import_package_v2_authority(loaded, profile.authority)
    profile.validate_import(bound)
    authority = _authority(bound, profile)
    source_receipt_sha256 = hashlib.sha256(loaded.receipt_bytes).hexdigest()
    evaluation_input_sha256 = hashlib.sha256(
        canonical_json(
            {
                "authority_sha256": authority.authority_sha256,
                "source_receipt_sha256": source_receipt_sha256,
            }
        )
    ).hexdigest()
    context = ProfileEvaluationContext(
        evaluation_id=f"imported-evaluation-{evaluation_input_sha256}",
        evidence_id=f"imported-evidence-{evaluation_input_sha256}",
        score_id=f"imported-score-{evaluation_input_sha256}",
        source_receipt_sha256=source_receipt_sha256,
    )
    try:
        assessment = profile.assess(bound, context)
    except Exception as exc:  # Profile exceptions are evidence uncertainty, never pass.
        assessment = _scorer_failure_assessment(bound, context, exc)
    _check_assessment(bound, context, assessment)
    decision = compose_gate(
        decision_id=f"imported-decision-{evaluation_input_sha256}",
        policy_version=authority.case_gate.version,
        required_score_ids=(assessment.score.score_id,),
        required_observations=assessment.required_observations,
        scores=(assessment.score,),
    )
    if decision.decision not in bound.content.bundle.evaluation_boundary:
        raise IngestionIntegrityError("Profile outcome contradicts the evidence boundary")
    return ImportedCaseEvaluation(
        authority=authority,
        evidence=assessment.evidence,
        score=assessment.score,
        decision=decision,
    )


__all__ = ["evaluate_imported_case_v2"]
