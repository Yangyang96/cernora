"""Preview contracts for offline inspection of completed Agent exports."""

from __future__ import annotations

import hashlib
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from cernora.core.canonical import canonical_json
from cernora.core.case import StrictModel

Identifier = Annotated[str, Field(min_length=1)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class AgentCondition(StrictModel):
    agent: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    budget: int | None = Field(
        ge=0, description="Maximum model tokens allowed by the external harness; null if unrecorded"
    )
    toolset_version: str = Field(min_length=1)


class ToolCallPayload(StrictModel):
    invocation_id: Identifier
    tool: Identifier
    argv: tuple[str, ...] = Field(min_length=1)


class ToolResultPayload(StrictModel):
    invocation_id: Identifier
    exit_code: int | None
    timed_out: bool
    evidence_id: Identifier | None = None


class MessagePayload(StrictModel):
    text: str


class ErrorPayload(StrictModel):
    code: Identifier


class AgentEvent(StrictModel):
    seq: int = Field(ge=0)
    kind: Literal["user", "assistant", "tool_call", "tool_result", "error", "final"]
    timestamp_ms: int = Field(ge=0)
    payload: ToolCallPayload | ToolResultPayload | MessagePayload | ErrorPayload

    @model_validator(mode="after")
    def matching_payload(self) -> AgentEvent:
        expected = {
            "tool_call": ToolCallPayload,
            "tool_result": ToolResultPayload,
            "error": ErrorPayload,
        }.get(self.kind, MessagePayload)
        if not isinstance(self.payload, expected):
            raise ValueError("event kind and payload disagree")
        return self


class AgentClaim(StrictModel):
    path: Identifier
    value: Any
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)


class AgentRunExport(StrictModel):
    schema_version: Literal["agent-run-export/v1"]
    run_id: Identifier
    task_id: Identifier
    case_id: Identifier
    conditions: AgentCondition
    user_task: str = Field(min_length=1)
    events: tuple[AgentEvent, ...] = Field(min_length=1)
    final_answer: str
    claims: tuple[AgentClaim, ...] = ()
    tool_output_digests: dict[Identifier, Digest] = Field(default_factory=dict)
    tool_outputs: dict[Identifier, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def integrity(self) -> AgentRunExport:
        canonical_json(self.model_dump(mode="json"))
        if [e.seq for e in self.events] != list(range(len(self.events))):
            raise ValueError("events must have contiguous sequence numbers starting at zero")
        times = [e.timestamp_ms for e in self.events]
        if times != sorted(times):
            raise ValueError("event timestamps must be nondecreasing")
        if [e.seq for e in self.events if e.kind == "final"] != [len(self.events) - 1]:
            raise ValueError("exactly one final event must terminate the export")
        final = self.events[-1].payload
        if not isinstance(final, MessagePayload) or final.text != self.final_answer:
            raise ValueError("final event and final_answer disagree")
        paths = [c.path for c in self.claims]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate claim path")
        issues = validate_tool_observations(self)
        if issues:
            raise ValueError("; ".join(issues))
        if set(self.tool_outputs) != set(self.tool_output_digests):
            raise ValueError("tool output and digest IDs disagree")
        for key, content in self.tool_outputs.items():
            if hashlib.sha256(content.encode("utf-8")).hexdigest() != self.tool_output_digests[key]:
                raise ValueError("tool output digest mismatch")
        referenced = {
            e.payload.evidence_id
            for e in self.events
            if isinstance(e.payload, ToolResultPayload) and e.payload.evidence_id
        }
        if referenced != set(self.tool_outputs):
            raise ValueError("tool result evidence IDs and outputs disagree")
        for claim in self.claims:
            if len(set(claim.evidence_ids)) != len(claim.evidence_ids):
                raise ValueError("duplicate claim evidence ID")
            if not set(claim.evidence_ids) <= referenced:
                raise ValueError("claim references unknown evidence")
        return self


def validate_tool_observations(run: AgentRunExport) -> list[str]:
    """Check identity, ordering and uniqueness; allow missing results as incomplete evidence."""
    calls: set[str] = set()
    results: set[str] = set()
    issues: list[str] = []
    for event in run.events:
        payload = event.payload
        if isinstance(payload, ToolCallPayload):
            if payload.invocation_id in calls:
                issues.append("duplicate tool invocation ID")
            calls.add(payload.invocation_id)
        elif isinstance(payload, ToolResultPayload):
            if payload.invocation_id not in calls:
                issues.append("tool result precedes or lacks its call")
            if payload.invocation_id in results:
                issues.append("duplicate tool result ID")
            results.add(payload.invocation_id)
    return issues


def summarize_run(run: AgentRunExport) -> dict[str, Any]:
    calls = [e.payload for e in run.events if isinstance(e.payload, ToolCallPayload)]
    results = [e.payload for e in run.events if isinstance(e.payload, ToolResultPayload)]
    failed = sum(r.timed_out or (r.exit_code is not None and r.exit_code != 0) for r in results)
    errors = sum(e.kind == "error" for e in run.events)
    unknown = sum(r.exit_code is None and not r.timed_out for r in results)
    return {
        "tool_call_count": len(calls),
        "tool_result_count": len(results),
        "missing_result_count": len(calls) - len(results),
        "failed_result_count": failed,
        "unknown_result_count": unknown,
        "error_count": errors,
        "tool_called": bool(calls),
        "tool_succeeded": bool(calls)
        and len(calls) == len(results)
        and failed == 0
        and unknown == 0
        and errors == 0,
        "final_answer_present": bool(run.final_answer.strip()),
        "elapsed_ms": run.events[-1].timestamp_ms - run.events[0].timestamp_ms,
    }


def evaluate_run_state(run: AgentRunExport, *, reference_available: bool = False) -> str:
    """Describe execution only. Reference availability cannot imply task success."""
    summary = summarize_run(run)
    if summary["error_count"]:
        return "inconclusive"
    if not summary["tool_called"]:
        return "no_tool_call"
    if summary["failed_result_count"]:
        return "tool_failed"
    if not summary["tool_succeeded"] or not summary["final_answer_present"]:
        return "inconclusive"
    if not run.tool_outputs or not reference_available:
        return "inconclusive"
    return "evidence_available"


def score_claims(run: AgentRunExport, reference: dict[str, Any] | None) -> dict[str, Any]:
    """Exact canonical JSON comparison against an external flat path-to-value reference.

    This checks declared claims, not the meaning of free text or citation entailment.
    """
    if (
        not run.claims
        or not reference
        or evaluate_run_state(run, reference_available=True) != "evidence_available"
    ):
        return {"status": "inconclusive", "matched": 0, "total": len(run.claims)}
    canonical_json(reference)
    claims = {claim.path: claim.value for claim in run.claims}
    paths = sorted(set(reference) | set(claims))
    matched = sum(
        path in reference
        and path in claims
        and canonical_json(reference[path]) == canonical_json(claims[path])
        for path in paths
    )
    return {
        "status": "scored",
        "matched": matched,
        "total": len(paths),
        "accuracy": matched / len(paths),
        "missing_paths": sorted(set(reference) - set(claims)),
        "unexpected_paths": sorted(set(claims) - set(reference)),
    }
