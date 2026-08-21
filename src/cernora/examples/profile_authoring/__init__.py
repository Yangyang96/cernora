"""Wheel-bundled reference for the guided Profile authoring tutorial.

A third party starts from ``cernora profile init``, follows the annotations in the
generated ``profile.py``, and implements one deterministic observation. This module
ships the reference implementation the tutorial describes so the same exact flow can be
rebuilt from an installed wheel without importing a Cernora source checkout.
"""

from __future__ import annotations

from pathlib import Path

IMPLEMENTED_PROFILE_SOURCE = '''
"""Implemented minimal scaffold Profile for the wheel-only tutorial."""

import hashlib
import json
from pathlib import Path
from typing import Any

from cernora import (
    AnswerClaim,
    Artifact,
    AuthorityBoundImportPackageV2,
    CaseProfile,
    Evidence,
    EvidenceReference,
    Failure,
    Profile,
    ProfileAssessment,
    ProfileEvaluationContext,
    Score,
    ScoreObservation,
    StructuredAnswer,
    ToolAction,
    external_producer_identity,
)

_PROJECTION_VERSION = "scaffold-projection/v1"
_EXPECTED_VALUE_PATH = "resources/expected-value.json"
_OBSERVATION_ID = "claim_grounded"
_TOOL = "check_value"
_TOOL_ARGV = ("check_value", "--key", "alpha")


def _strict_object(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("terminal answer must be a JSON object")
    return value


class ScaffoldProfile:
    def __init__(self) -> None:
        directory = Path(__file__).resolve().parent
        self._authority = CaseProfile.model_validate_json(
            (directory / "profile.json").read_bytes()
        )
        self._expected_bytes = (directory / _EXPECTED_VALUE_PATH).read_bytes()
        self._expected_value = _strict_object(self._expected_bytes.decode("utf-8"))

    @property
    def authority(self) -> CaseProfile:
        return self._authority

    @property
    def projection_version(self) -> str:
        return _PROJECTION_VERSION

    def validate_import(self, package: AuthorityBoundImportPackageV2) -> None:
        if package.profile != self._authority:
            raise ValueError("import package is not bound to this Profile authority")
        if package.case != self._authority.cases[0]:
            raise ValueError("import package is not bound to the scaffold Case")

    def assess(
        self,
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
    ) -> ProfileAssessment:
        bundle = package.content.bundle
        receipt_reference = EvidenceReference(
            evidence_id=context.evidence_id,
            locator="source-import/import-receipt.json",
            sha256=context.source_receipt_sha256,
        )
        if bundle.terminal.status != "completed":
            observation = ScoreObservation(
                observation_id=_OBSERVATION_ID,
                applicability="invalid",
                value=None,
                reason="runtime_evidence_unavailable",
                evidence_references=(receipt_reference,),
            )
            answer = None
        else:
            action = bundle.tool_actions[0]
            stdout_id = action.result.stdout_artifact.artifact_id
            stdout = package.content.artifact_bytes[stdout_id]
            terminal = bundle.terminal.answer
            if terminal is None:
                raise ValueError("completed run requires a terminal answer")
            claim = _strict_object(terminal.content)
            grounded = (
                action.tool == _TOOL
                and action.argv == _TOOL_ARGV
                and action.result.status == "completed"
                and action.result.exit_code == 0
                and stdout == self._expected_bytes
                and claim["claim"] == self._expected_value
                and claim["evidence_sha256"] == hashlib.sha256(stdout).hexdigest()
            )
            stdout_path = next(a.path for a in bundle.artifacts if a.artifact_id == stdout_id)
            stdout_reference = EvidenceReference(
                evidence_id=context.evidence_id,
                locator=f"artifacts/{stdout_path}",
                sha256=action.result.stdout_artifact.sha256,
            )
            observation = ScoreObservation(
                observation_id=_OBSERVATION_ID,
                applicability="observed",
                value=grounded,
                evidence_references=(stdout_reference,),
            )
            answer = StructuredAnswer(
                status="completed",
                claims=(
                    AnswerClaim(
                        name="claim",
                        value=claim["claim"],
                        evidence_references=(stdout_reference,),
                    ),
                ),
            )

        score = Score(
            schema_version="agent.evaluator.score/v1",
            score_id=context.score_id,
            evidence_id=context.evidence_id,
            scorer_version=self._authority.scorer_policy.policy_version,
            observations=(observation,),
        )
        return ProfileAssessment(
            evidence=self._evidence(package, context, answer),
            score=score,
            required_observations=self._authority.scorer_policy.required_observations,
        )

    @staticmethod
    def _evidence(
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
        answer: StructuredAnswer | None,
    ) -> Evidence:
        bundle = package.content.bundle
        failure = bundle.terminal.failure
        failures: tuple[Failure, ...] = ()
        if failure is not None:
            failures = (
                Failure(
                    domain=failure.domain,
                    code=failure.code,
                    message=failure.message,
                    evidence_references=(),
                ),
            )
        return Evidence(
            schema_version="agent.evaluator.evidence/v1",
            evidence_id=context.evidence_id,
            evaluation_id=context.evaluation_id,
            profile_id=package.profile.profile_id,
            case_id=package.case.case_id,
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
                    artifact_id=artifact.artifact_id,
                    path=artifact.path,
                    sha256=artifact.sha256,
                    media_type=artifact.media_type,
                )
                for artifact in bundle.artifacts
            ),
            answer=answer,
            failures=failures,
            metadata={
                "projection_version": _PROJECTION_VERSION,
                "source_receipt_sha256": context.source_receipt_sha256,
                "terminal_status": bundle.terminal.status,
            },
        )


def create_profile() -> Profile:
    return ScaffoldProfile()
'''


def write_implemented_profile(directory: Path) -> None:
    """Write the tutorial's implemented ``profile.py`` into a scaffold directory."""

    (directory / "profile.py").write_text(IMPLEMENTED_PROFILE_SOURCE, encoding="utf-8")


__all__ = ["IMPLEMENTED_PROFILE_SOURCE", "write_implemented_profile"]
