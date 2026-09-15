from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from cernora.core.agent_run import AgentRunExport, score_claims, summarize_run
from cernora.core.errors import ContractError
from cernora.evaluation.agent_export import inspect_agent_run, load_agent_run_export
from cernora.resources import read_public_schema

FIXTURE = Path(__file__).parent / "fixtures" / "agent_run" / "success.json"


def payload() -> dict[str, Any]:
    return json.loads(FIXTURE.read_bytes())


def load(value: dict[str, Any]) -> AgentRunExport:
    return load_agent_run_export(json.dumps(value))


@pytest.mark.parametrize("failure", ["nonzero", "timeout", "missing", "unknown", "runtime"])
def test_execution_outcomes(failure: str) -> None:
    data = payload()
    if failure == "nonzero":
        data["events"][2]["payload"]["exit_code"] = 7
    elif failure == "timeout":
        data["events"][2]["payload"].update(exit_code=None, timed_out=True)
    elif failure == "missing":
        data["events"].pop(2)
        data["claims"] = []
        data["tool_outputs"] = {}
        data["tool_output_digests"] = {}
        data["events"][-1]["seq"] = 2
    elif failure == "unknown":
        data["events"][2]["payload"]["exit_code"] = None
    else:
        data["events"].insert(
            3, {"seq": 3, "kind": "error", "timestamp_ms": 20, "payload": {"code": "runtime_error"}}
        )
        data["events"][-1]["seq"] = 4
    result = inspect_agent_run(json.dumps(data), reference={"/status": "ready"})
    assert not result["tool_succeeded"]
    assert result["state"] == (
        "tool_failed" if failure in {"nonzero", "timeout"} else "inconclusive"
    )
    assert result["claims"]["status"] == "inconclusive"


@pytest.mark.parametrize(
    "corruption",
    [
        "orphan",
        "duplicate_call",
        "duplicate_result",
        "sequence",
        "time",
        "final",
        "digest",
        "missing_output",
        "unknown_ref",
        "duplicate_claim",
        "payload",
        "unknown_field",
        "blank_id",
    ],
)
def test_invalid_evidence_is_rejected(corruption: str) -> None:
    data = payload()
    if corruption == "orphan":
        data["events"][2]["payload"]["invocation_id"] = "other"
    elif corruption in {"duplicate_call", "duplicate_result"}:
        index = 1 if corruption == "duplicate_call" else 2
        data["events"].insert(index + 1, dict(data["events"][index]))
        for i, event in enumerate(data["events"]):
            event["seq"] = i
    elif corruption == "sequence":
        data["events"][0]["seq"] = 8
    elif corruption == "time":
        data["events"][0]["timestamp_ms"] = 99
    elif corruption == "final":
        data["final_answer"] = "different answer"
    elif corruption == "digest":
        data["tool_outputs"]["output-1"] += "tampered"
    elif corruption == "missing_output":
        data["tool_outputs"] = {}
    elif corruption == "unknown_ref":
        data["claims"][0]["evidence_ids"] = ["unknown"]
    elif corruption == "duplicate_claim":
        data["claims"] *= 2
    elif corruption == "payload":
        data["events"][1]["payload"] = {"text": "not a call"}
    elif corruption == "unknown_field":
        data["conditions"]["extra"] = True
    else:
        data["events"][1]["payload"]["invocation_id"] = ""
    with pytest.raises(ContractError):
        load(data)


def test_missing_reference_and_no_calls_are_not_success() -> None:
    assert score_claims(load(payload()), None)["status"] == "inconclusive"
    data = payload()
    data["events"] = [data["events"][0], data["events"][-1]]
    data["events"][-1]["seq"] = 1
    data.update(claims=[], tool_outputs={}, tool_output_digests={})
    run = load(data)
    assert not summarize_run(run)["tool_succeeded"]
    assert inspect_agent_run(json.dumps(data))["state"] == "no_tool_call"


@pytest.mark.parametrize(
    ("value", "reference", "matched", "total"),
    [
        ("ready", {"/status": "ready"}, 1, 1),
        ("wrong", {"/status": "ready"}, 0, 1),
        (None, {"/other": None}, 0, 2),
        (True, {"/status": 1}, 0, 1),
        ({"nested": [True]}, {"/status": {"nested": [1]}}, 0, 1),
        ("ready", {"/status": "ready", "/required": 7}, 1, 2),
    ],
)
def test_exact_claim_scoring(
    value: Any, reference: dict[str, Any], matched: int, total: int
) -> None:
    data = payload()
    data["claims"][0]["value"] = value
    result = score_claims(load(data), reference)
    assert result["matched"] == matched
    assert result["total"] == total


def test_schema_matches_model_and_accepts_fixture() -> None:
    schema = json.loads(read_public_schema("agent-run-export-v1.schema.json"))
    schema.pop("$schema")
    assert schema == AgentRunExport.model_json_schema()
    Draft202012Validator(schema).validate(payload())
