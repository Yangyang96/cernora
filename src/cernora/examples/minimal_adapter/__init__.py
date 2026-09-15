"""Synthetic, sequential completed-record adapter for the inspection Preview.

This example does not implement the EvidenceBundle Adapter protocol. It neither
runs an agent nor reads a reference answer to construct observations.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from cernora.core.agent_run import AgentCondition, AgentRunExport
from cernora.core.canonical import canonical_json, decode_contract
from cernora.core.case import StrictModel
from cernora.evaluation.agent_export import load_agent_run_export


class RecordedResult(StrictModel):
    timestamp_ms: int = Field(ge=0)
    exit_code: int | None
    timed_out: bool
    stdout: str | None
    stderr: str | None


class RecordedCall(StrictModel):
    invocation_id: str = Field(min_length=1)
    timestamp_ms: int = Field(ge=0)
    tool: str = Field(min_length=1)
    argv: tuple[str, ...] = Field(min_length=1)
    result: RecordedResult | None


class RecordedClaim(StrictModel):
    path: str = Field(min_length=1)
    value: Any
    invocation_id: str = Field(min_length=1)


class CompletedRecord(StrictModel):
    schema_version: Literal["synthetic-completed-record/v1"]
    run_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    conditions: AgentCondition
    user_task: str = Field(min_length=1)
    started_ms: int = Field(ge=0)
    finished_ms: int = Field(ge=0)
    final_answer: str
    calls: tuple[RecordedCall, ...]
    claims: tuple[RecordedClaim, ...]


def adapt_record(source: bytes) -> AgentRunExport:
    """Normalize a terminal sequential record; reject unrepresentable or invalid facts."""
    record = decode_contract(source, CompletedRecord)
    events: list[dict[str, Any]] = []
    outputs: dict[str, str] = {}

    def event(kind: str, timestamp: int, payload: dict[str, Any]) -> None:
        events.append(
            {"seq": len(events), "timestamp_ms": timestamp, "kind": kind, "payload": payload}
        )

    event("user", record.started_ms, {"text": record.user_task})
    for call in record.calls:
        event(
            "tool_call",
            call.timestamp_ms,
            {"invocation_id": call.invocation_id, "tool": call.tool, "argv": call.argv},
        )
        result = call.result
        if result is None:
            continue
        if result.stdout is not None:
            outputs[call.invocation_id] = result.stdout
        event(
            "tool_result",
            result.timestamp_ms,
            {
                "invocation_id": call.invocation_id,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "evidence_id": call.invocation_id if result.stdout is not None else None,
            },
        )
    event("final", record.finished_ms, {"text": record.final_answer})
    payload = {
        "schema_version": "agent-run-export/v1",
        "run_id": record.run_id,
        "task_id": record.task_id,
        "case_id": record.case_id,
        "conditions": record.conditions.model_dump(mode="json"),
        "user_task": record.user_task,
        "final_answer": record.final_answer,
        "events": events,
        "claims": [
            {"path": c.path, "value": c.value, "evidence_ids": [c.invocation_id]}
            for c in record.claims
        ],
        "tool_outputs": outputs,
        "tool_output_digests": {
            key: hashlib.sha256(value.encode("utf-8")).hexdigest() for key, value in outputs.items()
        },
    }
    return load_agent_run_export(canonical_json(payload))


def export_record(source: Path, output: Path) -> None:
    """Validate before creating a new export; never replace an existing file."""
    payload = canonical_json(adapt_record(source.read_bytes()))
    with output.open("xb") as stream:
        stream.write(payload)
