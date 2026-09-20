"""Two neutral domains sharing the same opt-in Metric implementations."""

from __future__ import annotations

import json
from typing import ClassVar

from cernora.core.case import CaseProfile, StrictModel
from cernora.core.evidence import Artifact, Evidence, Failure, ToolAction
from cernora.core.identity import external_producer_identity
from cernora.core.result import ResultRecord
from cernora.core.score import Score
from cernora.ingestion.contracts_v2 import AuthorityBoundImportPackageV2
from cernora.metrics import (
    ArgumentMatch,
    FactMatch,
    Latency,
    MetricBinding,
    MetricContext,
    MetricDefinition,
    MetricPlan,
    ToolCalls,
    ToolSelection,
)
from cernora.profile import ProfileAssessment, ProfileEvaluationContext


class StockParameters(StrictModel):
    minimum: int


class MinimumStock:
    """Example domain constraint using the same interface as built-ins."""

    definition = MetricDefinition(
        metric_id="minimum_stock", metric_version="1.0.0", value_type="boolean"
    )

    def validate_parameters(self, parameters_json: str) -> None:
        StockParameters.model_validate_json(parameters_json)

    def evaluate(self, context: MetricContext, parameters_json: str) -> ResultRecord:
        p = StockParameters.model_validate_json(parameters_json)
        data, ref = context.json_artifact("source")
        if not isinstance(data, dict):
            raise ValueError("stock snapshot must be an object")
        value = data["available"]
        if type(value) is not int:
            raise ValueError("stock must be an integer")
        return ResultRecord(
            id="minimum_stock",
            version="agent.evaluator.result-record/v1",
            role="diagnostic",
            value=value >= p.minimum,
            value_type="boolean",
            validity="valid",
            failure_reason=None,
            evidence_refs=(ref,),
            unit=None,
            direction=None,
        )


class _PlanProfile:
    tool: str
    expected: ClassVar[dict[str, str | int]]
    custom: bool = False

    def __init__(self) -> None:
        bindings: tuple[MetricBinding, ...] = (
            MetricBinding(ToolSelection(), "required", json.dumps({"allowed_tools": [self.tool]})),
            MetricBinding(
                ArgumentMatch(),
                "required",
                json.dumps({"allowed_argv": {self.tool: [[self.tool, "--id", "alpha"]]}}),
            ),
            MetricBinding(
                FactMatch(),
                "required",
                json.dumps(
                    {
                        "answer_artifact": "answer",
                        "source_artifact": "source",
                        "expected": self.expected,
                    }
                ),
            ),
            MetricBinding(ToolCalls()),
            MetricBinding(Latency(), parameters_json='{"artifact":"stderr"}'),
        )
        if self.custom:
            bindings += (MetricBinding(MinimumStock(), "required", '{"minimum":1}'),)
        self.plan = MetricPlan(bindings)
        self._authority = CaseProfile.model_validate_json(
            json.dumps(
                {
                    "schema_version": "agent.evaluator.case-profile/v1",
                    "profile_id": "metric-" + self.tool,
                    "profile_version": "1.0.0",
                    "description": "Synthetic Metric Plan authoring example",
                    "cases": [
                        {
                            "case_id": "alpha",
                            "case_version": "1.0.0",
                            "case_set": "metric-examples",
                            "input": {"prompt": "Read the resource and report its recorded facts."},
                            "declared_capabilities": [],
                            "fixture_references": [
                                {
                                    "fixture_id": "metric-plan",
                                    "path": "metric-plan.json",
                                    "sha256": self.plan.sha256,
                                }
                            ],
                        }
                    ],
                    "scorer_policy": {
                        "policy_version": self.plan.scorer_version,
                        "required_observations": self.plan.required_observations,
                    },
                    "gate_policy": {
                        "policy_version": "1.0.0",
                        "required_score_ids": ["metric-score"],
                    },
                }
            )
        )

    @property
    def authority(self) -> CaseProfile:
        self.plan.validate_authority(self._authority)
        return self._authority

    @property
    def projection_version(self) -> str:
        return "cernora.metric-example-projection/v1"

    def validate_import(self, package: AuthorityBoundImportPackageV2) -> None:
        if package.profile != self.authority or package.case not in self.authority.cases:
            raise ValueError("metric Profile authority mismatch")

    def assess(
        self, package: AuthorityBoundImportPackageV2, context: ProfileEvaluationContext
    ) -> ProfileAssessment:
        self.validate_import(package)
        bundle = package.content.bundle
        records = self.plan.evaluate(MetricContext.from_import(package, context), self.authority)
        failure = bundle.terminal.failure
        evidence = Evidence(
            schema_version="agent.evaluator.evidence/v1",
            evidence_id=context.evidence_id,
            evaluation_id=context.evaluation_id,
            profile_id=package.profile.profile_id,
            case_id=package.case.case_id,
            run_id=bundle.run.run_id,
            producer=external_producer_identity(
                bundle.producer.producer_id, bundle.producer.producer_version
            ),
            process=None,
            answer=None,
            tool_actions=tuple(
                ToolAction(
                    invocation_id=a.invocation_id,
                    tool=a.tool,
                    argv=a.argv,
                    exit_code=a.result.exit_code,
                    timed_out=a.result.status == "timed_out",
                    response_sha256=a.result.stdout_artifact.sha256,
                    committed=a.result.committed,
                    delivered=a.result.delivered,
                )
                for a in bundle.tool_actions
            ),
            artifacts=tuple(
                Artifact(
                    artifact_id=a.artifact_id, path=a.path, sha256=a.sha256, media_type=a.media_type
                )
                for a in bundle.artifacts
            ),
            failures=()
            if failure is None
            else (
                Failure(
                    domain=failure.domain,
                    code=failure.code,
                    message=failure.message,
                    evidence_references=(),
                ),
            ),
            metadata={
                "projection_version": self.projection_version,
                "metric_plan_sha256": self.plan.sha256,
            },
        )
        score = Score(
            schema_version="agent.evaluator.score/v1",
            score_id=context.score_id,
            evidence_id=context.evidence_id,
            scorer_version=self.authority.scorer_policy.policy_version,
            observations=self.plan.observations(records),
        )
        return ProfileAssessment(evidence, score, self.plan.required_observations, records)


class ResourceStatusProfile(_PlanProfile):
    tool = "resource-status"
    expected: ClassVar[dict[str, str | int]] = {"status": "ready"}


class InventoryProfile(_PlanProfile):
    tool = "inventory"
    expected: ClassVar[dict[str, str | int]] = {"available": 3}
    custom = True


__all__ = ["InventoryProfile", "MinimumStock", "ResourceStatusProfile"]
