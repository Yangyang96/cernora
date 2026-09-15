from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import pytest

from cernora.core.canonical import canonical_json
from cernora.core.errors import ContractError
from cernora.evaluation.agent_export import inspect_agent_run
from cernora.examples.minimal_adapter import adapt_record, export_record
from cernora.examples.minimal_adapter.__main__ import main


def _source(name: str = "success") -> bytes:
    return (
        resources.files("cernora.examples.minimal_adapter")
        .joinpath(f"resources/{name}.json")
        .read_bytes()
    )


@pytest.mark.parametrize(
    ("name", "state", "accuracy"),
    [
        ("success", "evidence_available", 1.0),
        ("failure", "evidence_available", 0.0),
        ("missing-evidence", "inconclusive", None),
    ],
)
def test_record_observations(name: str, state: str, accuracy: float | None) -> None:
    exports = [canonical_json(adapt_record(_source(name))) for _ in range(3)]
    assert exports[0] == exports[1] == exports[2]
    summary = inspect_agent_run(exports[0], reference={"/status": "ready"})
    assert summary["state"] == state
    assert summary["claims"].get("accuracy") == accuracy
    if name == "missing-evidence":
        assert summary["missing_result_count"] == 1
        assert not summary["tool_succeeded"]


def test_reference_cannot_change_exported_claims() -> None:
    export = canonical_json(adapt_record(_source()))
    assert (
        inspect_agent_run(export, reference={"/status": "unavailable"})["claims"]["accuracy"] == 0
    )
    assert adapt_record(_source()).claims[0].value == "ready"


@pytest.mark.parametrize("mutation", ["duplicate-id", "time", "claim", "unknown", "version"])
def test_inconsistent_native_record_is_rejected(mutation: str) -> None:
    value = json.loads(_source())
    if mutation == "duplicate-id":
        value["calls"].append(value["calls"][0])
    elif mutation == "time":
        value["calls"][0]["result"]["timestamp_ms"] = 9
    elif mutation == "claim":
        value["claims"][0]["invocation_id"] = "absent"
    elif mutation == "unknown":
        value["calls"][0]["result"]["exitCode"] = 0
    else:
        value["schema_version"] = "synthetic-completed-record/v2"
    with pytest.raises(ContractError):
        adapt_record(json.dumps(value).encode())


def test_missing_stdout_is_not_filled_in() -> None:
    value = json.loads(_source())
    value["calls"][0]["result"]["stdout"] = None
    value["claims"] = []
    export = adapt_record(json.dumps(value).encode())
    assert export.tool_outputs == {}
    assert inspect_agent_run(canonical_json(export), reference={"/status": "ready"})["state"] == (
        "inconclusive"
    )


def test_field_error_does_not_publish_and_existing_export_is_preserved(tmp_path: Path) -> None:
    assert main(["fixtures", str(tmp_path / "records")]) == 0
    destination = tmp_path / "run.json"
    assert main(["export", str(tmp_path / "records/field-error.json"), str(destination)]) == 3
    assert not destination.exists()
    source = tmp_path / "records/success.json"
    export_record(source, destination)
    before = destination.read_bytes()
    assert main(["export", str(source), str(destination)]) == 3
    assert destination.read_bytes() == before
    assert source.read_bytes() == _source()
