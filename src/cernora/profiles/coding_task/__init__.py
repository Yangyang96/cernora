"""Sanitized, deterministic coding task Profile."""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import PurePosixPath
from typing import Any

from cernora.core.case import CaseProfile
from cernora.core.evidence import (
    AnswerClaim,
    Artifact,
    Evidence,
    EvidenceReference,
    Failure,
    StructuredAnswer,
    ToolAction,
)
from cernora.core.identity import external_producer_identity
from cernora.core.score import Score, ScoreObservation
from cernora.ingestion.contracts_v2 import AuthorityBoundImportPackageV2
from cernora.profile import ProfileAssessment, ProfileEvaluationContext

_PROJECTION_VERSION = "cernora.public-profile-projection/v1"
_PROFILE_RESOURCE = "resources/profile.json"
_CHECK_DIRECTORY = "resources/checks"
_EXPECTED_TOOL = "export_candidate"
_EXPECTED_ARGV = ("export_candidate",)


def _strict_object(text: str, *, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON member in {label}: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number in {label}: {value}")

    value = json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _candidate_files(raw: bytes) -> dict[str, str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("candidate file map must be strict UTF-8") from exc
    value = _strict_object(text, label="candidate file map")
    if set(value) != {"files"} or not isinstance(value["files"], dict):
        raise ValueError("candidate export must contain exactly one files object")
    files = value["files"]
    if not files:
        raise ValueError("candidate file map must not be empty")
    for path, content in files.items():
        parsed = PurePosixPath(path)
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or "\\" in path
            or parsed.as_posix() != path
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            raise ValueError("candidate paths must be canonical contained POSIX paths")
        if not isinstance(content, str):
            raise ValueError("candidate file contents must be strings")
    return files


class CodingTaskProfile:
    """Assess resource-backed candidate exports through the frozen Profile seam."""

    def __init__(self) -> None:
        package = resources.files(__package__)
        profile_bytes = package.joinpath(_PROFILE_RESOURCE).read_bytes()
        self._authority = CaseProfile.model_validate_json(profile_bytes)
        self._checks: dict[str, dict[str, Any]] = {}
        self._check_bytes: dict[str, bytes] = {}
        for case in self._authority.cases:
            check_path = f"{_CHECK_DIRECTORY}/{case.case_id}.json"
            check_bytes = package.joinpath(check_path).read_bytes()
            fixture = case.fixture_references[0]
            if fixture.path != check_path:
                raise ValueError("coding check path does not match Profile authority")
            if fixture.sha256 != hashlib.sha256(check_bytes).hexdigest():
                raise ValueError("coding check digest does not match Profile authority")
            self._checks[case.case_id] = _strict_object(
                check_bytes.decode("utf-8"), label=f"{case.case_id} check"
            )
            self._check_bytes[case.case_id] = check_bytes

    @property
    def authority(self) -> CaseProfile:
        return self._authority

    @property
    def projection_version(self) -> str:
        return _PROJECTION_VERSION

    def validate_import(self, package: AuthorityBoundImportPackageV2) -> None:
        if package.profile != self._authority:
            raise ValueError("import package is not bound to this Profile authority")
        matches = tuple(case for case in self._authority.cases if case == package.case)
        if len(matches) != 1:
            raise ValueError("import package is not bound to a coding Profile Case")
        bundle = package.content.bundle
        if (
            bundle.profile.profile_id,
            bundle.profile.profile_version,
        ) != (
            self._authority.profile_id,
            self._authority.profile_version,
        ):
            raise ValueError("bundle Profile identity does not match")
        if (
            bundle.case.case_id,
            bundle.case.case_version,
            bundle.case.case_set,
        ) != (
            package.case.case_id,
            package.case.case_version,
            package.case.case_set,
        ):
            raise ValueError("bundle Case identity does not match")
        fixtures = tuple(item.model_dump(mode="json") for item in bundle.fixtures)
        expected_fixtures = tuple(
            item.model_dump(mode="json") for item in package.case.fixture_references
        )
        if fixtures != expected_fixtures:
            raise ValueError("bundle Fixture identities do not match")
        if bundle.terminal.status == "completed":
            if len(bundle.tool_actions) != 1:
                raise ValueError("completed coding result requires exactly one export action")
            action = bundle.tool_actions[0]
            _candidate_files(
                package.content.artifact_bytes[action.result.stdout_artifact.artifact_id]
            )
            terminal = bundle.terminal.answer
            if terminal is None:
                raise ValueError("completed coding result requires a terminal answer")
            value = _strict_object(terminal.content, label="coding terminal answer")
            if set(value) != {"candidate_sha256"}:
                raise ValueError("coding terminal answer has an invalid member set")
            digest = value["candidate_sha256"]
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError("coding terminal candidate digest must be a SHA-256 string")
            try:
                bytes.fromhex(digest)
            except ValueError as exc:
                raise ValueError("coding terminal candidate digest must be hexadecimal") from exc

    def assess(
        self,
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
    ) -> ProfileAssessment:
        self.validate_import(package)
        bundle = package.content.bundle
        receipt_reference = EvidenceReference(
            evidence_id=context.evidence_id,
            locator="receipt.json",
            sha256=context.source_receipt_sha256,
        )
        values = {item: False for item in self._authority.scorer_policy.required_observations}
        references = {item: receipt_reference for item in values}
        answer: StructuredAnswer | None = None

        if bundle.terminal.status == "completed":
            action = bundle.tool_actions[0]
            stdout_id = action.result.stdout_artifact.artifact_id
            candidate = package.content.artifact_bytes[stdout_id]
            files = _candidate_files(candidate)
            candidate_digest = hashlib.sha256(candidate).hexdigest()
            stdout_path = next(
                artifact.path for artifact in bundle.artifacts if artifact.artifact_id == stdout_id
            )
            stdout_reference = EvidenceReference(
                evidence_id=context.evidence_id,
                locator=f"artifacts/{stdout_path}",
                sha256=action.result.stdout_artifact.sha256,
            )
            references = {item: stdout_reference for item in values}
            check = self._checks[package.case.case_id]
            expected_candidate = json.dumps(
                {"files": check["files"]},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            terminal_answer = bundle.terminal.answer
            if terminal_answer is None:
                raise ValueError("completed coding result requires a terminal answer")
            terminal_value = _strict_object(
                terminal_answer.content,
                label="coding terminal answer",
            )
            values["candidate_format"] = (
                action.tool == _EXPECTED_TOOL
                and action.argv == _EXPECTED_ARGV
                and action.result.status == "completed"
                and action.result.exit_code == 0
                and action.result.committed
                and action.result.delivered
            )
            values["candidate_digest"] = candidate == expected_candidate
            values["terminal_binding"] = terminal_value["candidate_sha256"] == candidate_digest
            required_fragments = check["required_fragments"]
            values["hidden_checks"] = all(
                path in files and all(fragment in files[path] for fragment in fragments)
                for path, fragments in required_fragments.items()
            )
            answer = StructuredAnswer(
                status="completed",
                claims=(
                    AnswerClaim(
                        name="candidate_sha256",
                        value=candidate_digest,
                        evidence_references=(stdout_reference,),
                    ),
                ),
            )

        evidence = _evidence(package, context, answer)
        observations = tuple(
            ScoreObservation(
                observation_id=item,
                applicability="observed",
                value=values[item],
                evidence_references=(references[item],),
            )
            for item in self._authority.scorer_policy.required_observations
        )
        score = Score(
            schema_version="agent.evaluator.score/v1",
            score_id=context.score_id,
            evidence_id=context.evidence_id,
            scorer_version=self._authority.scorer_policy.policy_version,
            observations=observations,
        )
        return ProfileAssessment(
            evidence=evidence,
            score=score,
            required_observations=self._authority.scorer_policy.required_observations,
        )


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
    return Evidence.model_validate(
        {
            "schema_version": "agent.evaluator.evidence/v1",
            "evidence_id": context.evidence_id,
            "evaluation_id": context.evaluation_id,
            "profile_id": package.profile.profile_id,
            "case_id": package.case.case_id,
            "run_id": bundle.run.run_id,
            "producer": external_producer_identity(
                bundle.producer.producer_id,
                bundle.producer.producer_version,
            ),
            "process": None,
            "tool_actions": tuple(
                ToolAction(
                    invocation_id=item.invocation_id,
                    tool=item.tool,
                    argv=item.argv,
                    exit_code=item.result.exit_code,
                    timed_out=item.result.status == "timed_out",
                    response_sha256=item.result.stdout_artifact.sha256,
                    committed=item.result.committed,
                    delivered=item.result.delivered,
                )
                for item in bundle.tool_actions
            ),
            "artifacts": tuple(
                Artifact(
                    artifact_id=item.artifact_id,
                    path=item.path,
                    sha256=item.sha256,
                    media_type=item.media_type,
                )
                for item in bundle.artifacts
            ),
            "answer": answer,
            "failures": failures,
            "metadata": {
                "projection_version": _PROJECTION_VERSION,
                "source_receipt_sha256": context.source_receipt_sha256,
                "terminal_status": bundle.terminal.status,
            },
        }
    )


__all__ = ["CodingTaskProfile"]
