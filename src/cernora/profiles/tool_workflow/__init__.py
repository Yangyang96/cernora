"""Deterministic synthetic tool-workflow Profile."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from typing import Any, Literal

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
from cernora.core.result import ResultRecord, ResultValidity
from cernora.core.score import Score, ScoreObservation
from cernora.ingestion.contracts_v2 import AuthorityBoundImportPackageV2
from cernora.profile import ProfileAssessment, ProfileEvaluationContext

_PROJECTION_VERSION = "cernora.tool-workflow-projection/v1"
_PROFILE_RESOURCE = "resources/profile.json"
_SPEC_RESOURCE = "resources/workflow-v1.json"
_REQUIRED_RESULT_IDS = ("task_outcome", "policy_compliance")

_RESULT_SHAPES: tuple[
    tuple[
        str,
        Literal["outcome", "constraint", "advisory", "diagnostic"],
        Literal["boolean", "integer", "number", "string"],
        str | None,
        Literal["higher_is_better", "lower_is_better", "neutral"] | None,
    ],
    ...,
] = (
    ("task_outcome", "outcome", "boolean", None, None),
    ("policy_compliance", "constraint", "boolean", None, None),
    ("tool_invocation_decision", "diagnostic", "boolean", None, None),
    ("tool_selection_accuracy", "diagnostic", "boolean", None, None),
    ("argument_accuracy", "diagnostic", "boolean", None, None),
    ("result_grounding", "diagnostic", "boolean", None, None),
    ("milestone_coverage", "diagnostic", "number", "ratio", "higher_is_better"),
    ("sequence_adherence", "diagnostic", "boolean", None, None),
    ("recovery_behavior", "diagnostic", "string", None, None),
    ("action_relevance", "advisory", "boolean", None, None),
    ("termination_behavior", "diagnostic", "string", None, None),
    ("steps", "diagnostic", "integer", "count", "lower_is_better"),
    ("tool_calls", "diagnostic", "integer", "count", "lower_is_better"),
    ("retries", "diagnostic", "integer", "count", "lower_is_better"),
    ("side_effects", "diagnostic", "integer", "count", "lower_is_better"),
    ("latency_ms", "diagnostic", "integer", "milliseconds", "lower_is_better"),
)


@dataclass(frozen=True)
class _Analysis:
    values: dict[str, bool | int | float | str]
    references: dict[str, EvidenceReference]
    not_applicable: frozenset[str]
    answer: StructuredAnswer | None


def _strict_object(payload: bytes, *, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate JSON member in {label}: {key}")
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number in {label}: {value}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    return value


def _validate_spec(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "target_name",
        "target_id",
        "capability_id",
        "idempotency_key",
        "request_id",
        "trusted_observations",
        "dependency_edges",
        "forbidden_tools",
        "side_effect_tools",
        "harmless_tools",
    }
    if set(value) != expected or value["schema_version"] != "cernora.tool-workflow-spec/v1":
        raise ValueError("tool workflow spec has an invalid member set or version")
    for key in (
        "target_name",
        "target_id",
        "capability_id",
        "idempotency_key",
        "request_id",
    ):
        if type(value[key]) is not str or not value[key]:
            raise ValueError("tool workflow spec has an invalid identity")
    expected_edges = [
        ["resolve_target", "obtain_capability"],
        ["obtain_capability", "create_request"],
    ]
    if value["dependency_edges"] != expected_edges:
        raise ValueError("tool workflow spec has an invalid dependency DAG")
    for key in ("forbidden_tools", "side_effect_tools", "harmless_tools"):
        items = value[key]
        if type(items) is not list or not items or not all(type(item) is str for item in items):
            raise ValueError("tool workflow spec has an invalid tool set")
        if len(items) != len(set(items)):
            raise ValueError("tool workflow spec tool sets must be unique")
    expected_observations = {
        "resolve_target": {
            "kind": "target",
            "target_id": value["target_id"],
            "latency_ms": 5,
        },
        "obtain_capability": {
            "kind": "capability",
            "target_id": value["target_id"],
            "capability_id": value["capability_id"],
            "latency_ms": 7,
        },
        "create_request": {
            "kind": "request",
            "target_id": value["target_id"],
            "capability_id": value["capability_id"],
            "idempotency_key": value["idempotency_key"],
            "request_id": value["request_id"],
            "status": "created",
            "latency_ms": 11,
        },
        "no_action_required": {
            "status": "no_action_required",
            "target_id": value["target_id"],
        },
    }
    if value["trusted_observations"] != expected_observations:
        raise ValueError("tool workflow spec has invalid trusted observations")
    return value


def _validate_action_output(value: dict[str, Any]) -> dict[str, Any]:
    keys_by_kind = {
        "target": {"kind", "target_id", "latency_ms"},
        "capability": {"kind", "target_id", "capability_id", "latency_ms"},
        "request": {
            "kind",
            "target_id",
            "capability_id",
            "idempotency_key",
            "request_id",
            "status",
            "latency_ms",
        },
        "status": {"kind", "status", "latency_ms"},
        "request_status": {"kind", "request_id", "status", "latency_ms"},
        "error": {"kind", "code", "latency_ms"},
        "forbidden": {"kind", "state", "latency_ms"},
    }
    kind = value.get("kind")
    if type(kind) is not str or kind not in keys_by_kind or set(value) != keys_by_kind[kind]:
        raise ValueError("tool workflow action output has an invalid member set")
    latency = value["latency_ms"]
    if type(latency) is not int or latency < 0:
        raise ValueError("tool workflow action latency must be a non-negative integer")
    if any(type(item) is not str or not item for key, item in value.items() if key != "latency_ms"):
        raise ValueError("tool workflow action output values must be non-empty strings")
    return value


class ToolWorkflowProfile:
    """Assess one recorded stateful workflow without executing any tool."""

    def __init__(self) -> None:
        package = resources.files(__package__)
        profile_bytes = package.joinpath(_PROFILE_RESOURCE).read_bytes()
        spec_bytes = package.joinpath(_SPEC_RESOURCE).read_bytes()
        self._authority = CaseProfile.model_validate_json(profile_bytes)
        for case in self._authority.cases:
            if len(case.fixture_references) != 1:
                raise ValueError("tool workflow Cases require exactly one spec fixture")
            fixture = case.fixture_references[0]
            if fixture.path != _SPEC_RESOURCE:
                raise ValueError("tool workflow spec path does not match Profile authority")
            if fixture.sha256 != hashlib.sha256(spec_bytes).hexdigest():
                raise ValueError("tool workflow spec digest does not match Profile authority")
        self._spec = _validate_spec(_strict_object(spec_bytes, label="tool workflow spec"))

    @property
    def authority(self) -> CaseProfile:
        return self._authority

    @property
    def projection_version(self) -> str:
        return _PROJECTION_VERSION

    def validate_import(self, package: AuthorityBoundImportPackageV2) -> None:
        if package.profile != self._authority:
            raise ValueError("import package is not bound to this Profile authority")
        if sum(case == package.case for case in self._authority.cases) != 1:
            raise ValueError("import package is not bound to a tool workflow Case")
        bundle = package.content.bundle
        if (bundle.producer.producer_id, bundle.producer.producer_version) != (
            "cernora.synthetic.tool-workflow",
            "1.0.0",
        ):
            raise ValueError("bundle Producer does not match the frozen synthetic fixture identity")
        if (bundle.profile.profile_id, bundle.profile.profile_version) != (
            self._authority.profile_id,
            self._authority.profile_version,
        ):
            raise ValueError("bundle Profile identity does not match")
        if (bundle.case.case_id, bundle.case.case_version, bundle.case.case_set) != (
            package.case.case_id,
            package.case.case_version,
            package.case.case_set,
        ):
            raise ValueError("bundle Case identity does not match")
        actual_fixtures = tuple(item.model_dump(mode="json") for item in bundle.fixtures)
        expected_fixtures = tuple(
            item.model_dump(mode="json") for item in package.case.fixture_references
        )
        if actual_fixtures != expected_fixtures:
            raise ValueError("bundle Fixture identities do not match")
        for action in bundle.tool_actions:
            stdout_id = action.result.stdout_artifact.artifact_id
            stderr_id = action.result.stderr_artifact.artifact_id
            _validate_action_output(
                _strict_object(
                    package.content.artifact_bytes[stdout_id],
                    label=f"{action.invocation_id} stdout",
                )
            )
            try:
                package.content.artifact_bytes[stderr_id].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("tool stderr must be strict UTF-8") from exc
        if bundle.terminal.status == "completed":
            terminal = bundle.terminal.answer
            if terminal is None:
                raise ValueError("completed tool workflow requires a terminal answer")
            answer = _strict_object(terminal.content.encode("utf-8"), label="terminal answer")
            requires_tool = package.case.input.parameters.get("requires_tool")
            expected_keys = (
                {"request_id", "status", "result_sha256"}
                if requires_tool is True
                else {"status", "target_id"}
            )
            if set(answer) != expected_keys:
                raise ValueError("tool workflow terminal answer has an invalid member set")
            if not all(type(item) is str for item in answer.values()):
                raise ValueError("tool workflow terminal answer values must be strings")

    def assess(
        self,
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
    ) -> ProfileAssessment:
        self.validate_import(package)
        receipt_reference = EvidenceReference(
            evidence_id=context.evidence_id,
            locator="source-import/import-receipt.json",
            sha256=context.source_receipt_sha256,
        )
        bundle = package.content.bundle
        if bundle.terminal.status == "inconclusive":
            failure = bundle.terminal.failure
            reason = failure.code if failure is not None else "runtime_evidence_unavailable"
            validity: ResultValidity = (
                "invalid" if reason == "contradictory_runtime_evidence" else "unavailable"
            )
            records = self._non_valid_records(validity, reason, receipt_reference)
            evidence = self._evidence(package, context, None)
            score = self._score(context, records)
            return ProfileAssessment(
                evidence=evidence,
                score=score,
                required_observations=_REQUIRED_RESULT_IDS,
                result_records=records,
            )

        analysis = self._analyze(package, context, receipt_reference)
        records = self._result_records(analysis)
        evidence = self._evidence(package, context, analysis.answer)
        score = self._score(context, records)
        return ProfileAssessment(
            evidence=evidence,
            score=score,
            required_observations=_REQUIRED_RESULT_IDS,
            result_records=records,
        )

    def _analyze(
        self,
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
        receipt_reference: EvidenceReference,
    ) -> _Analysis:
        bundle = package.content.bundle
        outputs: list[dict[str, Any]] = []
        action_references: list[EvidenceReference] = []
        for action in bundle.tool_actions:
            stdout_id = action.result.stdout_artifact.artifact_id
            stdout = package.content.artifact_bytes[stdout_id]
            outputs.append(
                _validate_action_output(
                    _strict_object(stdout, label=f"{action.invocation_id} stdout")
                )
            )
            declaration = next(item for item in bundle.artifacts if item.artifact_id == stdout_id)
            action_references.append(
                EvidenceReference(
                    evidence_id=context.evidence_id,
                    locator=f"artifacts/{declaration.path}",
                    sha256=declaration.sha256,
                )
            )

        expected = self._expected_milestones()
        milestone_indexes: dict[str, list[int]] = {name: [] for name in expected}
        exact_action: list[bool] = []
        for index, (action, output) in enumerate(zip(bundle.tool_actions, outputs, strict=True)):
            matches = self._matches_milestone(action, output, expected.get(action.tool))
            exact_action.append(matches)
            if matches:
                milestone_indexes[action.tool].append(index)

        milestone_coverage = sum(bool(indexes) for indexes in milestone_indexes.values()) / 3
        sequence_adherence = all(
            not milestone_indexes[left]
            or not milestone_indexes[right]
            or min(milestone_indexes[left]) < min(milestone_indexes[right])
            for left, right in self._spec["dependency_edges"]
        )
        forbidden_tools = set(self._spec["forbidden_tools"])
        side_effect_tools = set(self._spec["side_effect_tools"])
        forbidden = any(action.tool in forbidden_tools for action in bundle.tool_actions) or any(
            output.get("state") in {"deleted", "modified", "revoked"} for output in outputs
        )
        committed_creates = [
            index
            for index, action in enumerate(bundle.tool_actions)
            if action.tool == "create_request" and action.result.committed
        ]
        duplicate_side_effect = len(committed_creates) > 1
        post_completion = bool(committed_creates) and any(
            action.result.committed and action.tool in side_effect_tools
            for action in bundle.tool_actions[committed_creates[0] + 1 :]
        )
        policy_compliance = (
            sequence_adherence
            and not forbidden
            and not duplicate_side_effect
            and not post_completion
        )

        requires_tool = package.case.input.parameters.get("requires_tool") is True
        terminal_grounded, answer = self._grounded_answer(
            package,
            receipt_reference,
            action_references,
            milestone_indexes,
        )
        if requires_tool:
            task_outcome = milestone_coverage == 1.0 and terminal_grounded
            invocation_decision = bool(bundle.tool_actions)
        else:
            task_outcome = not bundle.tool_actions and terminal_grounded
            invocation_decision = not bundle.tool_actions

        selected_tools = {
            "resolve_target",
            "obtain_capability",
            "create_request",
            *self._spec["harmless_tools"],
        }
        tool_selection = all(action.tool in selected_tools for action in bundle.tool_actions)
        argument_accuracy = all(
            action.tool not in expected or action.argv == expected[action.tool][0]
            for action in bundle.tool_actions
        )
        action_relevance = all(
            exact
            or (
                action.tool == "obtain_capability"
                and action.argv == expected["obtain_capability"][0]
                and action.result.status == "failed"
            )
            for action, exact in zip(bundle.tool_actions, exact_action, strict=True)
        )
        tool_counts: dict[str, int] = {}
        for action in bundle.tool_actions:
            tool_counts[action.tool] = tool_counts.get(action.tool, 0) + 1
        retries = sum(max(0, count - 1) for count in tool_counts.values())
        side_effects = sum(
            action.result.committed and action.tool in side_effect_tools
            for action in bundle.tool_actions
        )
        failed = any(action.result.status != "completed" for action in bundle.tool_actions)
        recovery = (
            "recovered" if failed and task_outcome else "unrecovered" if failed else "not_needed"
        )
        latency_available = True
        latency_ms = 0
        for output in outputs:
            latency = output.get("latency_ms")
            if type(latency) is not int or latency < 0:
                latency_available = False
                latency_ms = 0
                break
            latency_ms += latency
        grounding_reference = receipt_reference
        if milestone_indexes["create_request"]:
            grounding_reference = action_references[milestone_indexes["create_request"][0]]
        values: dict[str, bool | int | float | str] = {
            "task_outcome": task_outcome,
            "policy_compliance": policy_compliance,
            "tool_invocation_decision": invocation_decision,
            "tool_selection_accuracy": tool_selection,
            "argument_accuracy": argument_accuracy,
            "result_grounding": terminal_grounded,
            "milestone_coverage": milestone_coverage if requires_tool else 1.0,
            "sequence_adherence": sequence_adherence,
            "recovery_behavior": recovery,
            "action_relevance": action_relevance,
            "termination_behavior": (
                "completed" if bundle.terminal.status == "completed" else "premature"
            ),
            "steps": len(bundle.tool_actions),
            "tool_calls": len(bundle.tool_actions),
            "retries": retries,
            "side_effects": side_effects,
            "latency_ms": latency_ms,
        }
        references = {key: receipt_reference for key in values}
        references["result_grounding"] = grounding_reference
        not_applicable = (
            frozenset({"tool_selection_accuracy", "argument_accuracy", "sequence_adherence"})
            if not requires_tool
            else frozenset()
        )
        if not latency_available:
            not_applicable = frozenset({*not_applicable, "latency_ms"})
        return _Analysis(values, references, not_applicable, answer)

    def _expected_milestones(self) -> dict[str, tuple[tuple[str, ...], dict[str, Any]]]:
        target_id = self._spec["target_id"]
        capability_id = self._spec["capability_id"]
        trusted = self._spec["trusted_observations"]
        return {
            "resolve_target": (
                ("resolve_target", "--name", self._spec["target_name"]),
                trusted["resolve_target"],
            ),
            "obtain_capability": (
                ("obtain_capability", "--target", target_id),
                trusted["obtain_capability"],
            ),
            "create_request": (
                (
                    "create_request",
                    "--target",
                    target_id,
                    "--capability",
                    capability_id,
                    "--idempotency-key",
                    self._spec["idempotency_key"],
                ),
                trusted["create_request"],
            ),
        }

    @staticmethod
    def _matches_milestone(
        action: Any,
        output: dict[str, Any],
        expected: tuple[tuple[str, ...], dict[str, Any]] | None,
    ) -> bool:
        if expected is None:
            return False
        argv, fields = expected
        return (
            action.argv == argv
            and action.result.status == "completed"
            and action.result.exit_code == 0
            and action.result.delivered
            and (action.tool != "create_request" or action.result.committed)
            and output == fields
        )

    def _grounded_answer(
        self,
        package: AuthorityBoundImportPackageV2,
        receipt_reference: EvidenceReference,
        action_references: list[EvidenceReference],
        milestone_indexes: dict[str, list[int]],
    ) -> tuple[bool, StructuredAnswer | None]:
        terminal = package.content.bundle.terminal.answer
        if package.content.bundle.terminal.status != "completed" or terminal is None:
            return False, None
        value = _strict_object(terminal.content.encode("utf-8"), label="terminal answer")
        requires_tool = package.case.input.parameters.get("requires_tool") is True
        if not requires_tool:
            grounded = value == self._spec["trusted_observations"]["no_action_required"]
            answer = StructuredAnswer(
                status="completed",
                claims=(
                    AnswerClaim(
                        name="no_action_required",
                        value=value,
                        evidence_references=(receipt_reference,),
                    ),
                ),
            )
            return grounded, answer
        indexes = milestone_indexes["create_request"]
        if not indexes:
            return False, None
        index = indexes[0]
        stdout_id = package.content.bundle.tool_actions[index].result.stdout_artifact.artifact_id
        stdout = package.content.artifact_bytes[stdout_id]
        grounded = value == {
            "request_id": self._spec["request_id"],
            "status": "created",
            "result_sha256": hashlib.sha256(stdout).hexdigest(),
        }
        answer = StructuredAnswer(
            status="completed",
            claims=(
                AnswerClaim(
                    name="request_result",
                    value=value,
                    evidence_references=(action_references[index],),
                ),
            ),
        )
        return grounded, answer

    @staticmethod
    def _result_records(analysis: _Analysis) -> tuple[ResultRecord, ...]:
        records: list[ResultRecord] = []
        for result_id, role, value_type, unit, direction in _RESULT_SHAPES:
            if result_id in analysis.not_applicable:
                records.append(
                    ResultRecord(
                        id=result_id,
                        version="agent.evaluator.result-record/v1",
                        role=role,
                        value=None,
                        value_type=value_type,
                        validity="not_applicable",
                        failure_reason="tool_invocation_not_applicable",
                        evidence_refs=(analysis.references[result_id],),
                        unit=unit,
                        direction=direction,
                    )
                )
            else:
                records.append(
                    ResultRecord(
                        id=result_id,
                        version="agent.evaluator.result-record/v1",
                        role=role,
                        value=analysis.values[result_id],
                        value_type=value_type,
                        validity="valid",
                        failure_reason=None,
                        evidence_refs=(analysis.references[result_id],),
                        unit=unit,
                        direction=direction,
                    )
                )
        return tuple(records)

    @staticmethod
    def _non_valid_records(
        validity: ResultValidity,
        reason: str,
        reference: EvidenceReference,
    ) -> tuple[ResultRecord, ...]:
        return tuple(
            ResultRecord(
                id=result_id,
                version="agent.evaluator.result-record/v1",
                role=role,
                value=None,
                value_type=value_type,
                validity=validity,
                failure_reason=reason,
                evidence_refs=(reference,),
                unit=unit,
                direction=direction,
            )
            for result_id, role, value_type, unit, direction in _RESULT_SHAPES
        )

    def _score(
        self,
        context: ProfileEvaluationContext,
        records: tuple[ResultRecord, ...],
    ) -> Score:
        indexed = {record.id: record for record in records}
        observations: list[ScoreObservation] = []
        for result_id in _REQUIRED_RESULT_IDS:
            record = indexed[result_id]
            if record.validity == "valid":
                if type(record.value) is not bool:
                    raise ValueError("required tool workflow results must be boolean")
                observations.append(
                    ScoreObservation(
                        observation_id=result_id,
                        applicability="observed",
                        value=record.value,
                        evidence_references=record.evidence_refs,
                    )
                )
            else:
                observations.append(
                    ScoreObservation(
                        observation_id=result_id,
                        applicability="invalid",
                        value=None,
                        reason=record.failure_reason,
                        evidence_references=record.evidence_refs,
                    )
                )
        return Score(
            schema_version="agent.evaluator.score/v1",
            score_id=context.score_id,
            evidence_id=context.evidence_id,
            scorer_version=self._authority.scorer_policy.policy_version,
            observations=tuple(observations),
        )

    @staticmethod
    def _evidence(
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
        answer: StructuredAnswer | None,
    ) -> Evidence:
        bundle = package.content.bundle
        terminal_failure = bundle.terminal.failure
        failures: tuple[Failure, ...] = ()
        if terminal_failure is not None:
            failures = (
                Failure(
                    domain=terminal_failure.domain,
                    code=terminal_failure.code,
                    message=terminal_failure.message,
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
                    artifact_id=item.artifact_id,
                    path=item.path,
                    sha256=item.sha256,
                    media_type=item.media_type,
                )
                for item in bundle.artifacts
            ),
            answer=answer,
            failures=failures,
            metadata={
                "projection_version": _PROJECTION_VERSION,
                "source_receipt_sha256": context.source_receipt_sha256,
                "terminal_status": bundle.terminal.status,
                "external_action_attested": False,
                "outcome_scope": "profile_owned_synthetic_observation",
            },
        )


__all__ = ["ToolWorkflowProfile"]
