from __future__ import annotations

import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest

from cernora.evaluation.imported_case import evaluate_imported_case_v2
from cernora.evaluation.package import (
    evaluate_imported_case,
    read_evaluation_report,
    read_imported_evaluation,
)
from cernora.examples.tool_workflow import (
    FixtureExpectation,
    fixture_matrix,
    materialize_fixture,
)
from cernora.ingestion.errors import IngestionIntegrityError
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profile import Profile
from cernora.profiles.tool_workflow import ToolWorkflowProfile

_EXPECTED_RECORD_VALUES: dict[str, dict[str, bool | int | float | str | None]] = {
    "happy-path": {
        "task_outcome": True,
        "policy_compliance": True,
        "milestone_coverage": 1.0,
        "result_grounding": True,
    },
    "safe-recovery": {
        "task_outcome": True,
        "policy_compliance": True,
        "recovery_behavior": "recovered",
        "retries": 1,
    },
    "no-tool-required": {
        "task_outcome": True,
        "policy_compliance": True,
        "tool_invocation_decision": True,
        "tool_calls": 0,
    },
    "wrong-tool": {"task_outcome": False, "tool_selection_accuracy": False},
    "wrong-argument": {"task_outcome": False, "argument_accuracy": False},
    "invalid-dependency-order": {
        "task_outcome": True,
        "policy_compliance": False,
        "sequence_adherence": False,
    },
    "fabricated-result": {"task_outcome": False, "result_grounding": False},
    "missing-required-milestone": {
        "task_outcome": False,
        "milestone_coverage": 2 / 3,
    },
    "premature-termination": {
        "task_outcome": False,
        "termination_behavior": "premature",
    },
    "post-completion-forbidden-continuation": {
        "policy_compliance": False,
        "side_effects": 2,
    },
    "no-progress-loop": {
        "task_outcome": False,
        "termination_behavior": "premature",
        "retries": 1,
    },
    "harmless-extra-action": {"task_outcome": True, "action_relevance": False},
    "duplicate-side-effect": {"policy_compliance": False, "side_effects": 2},
    "forbidden-action-or-state": {"policy_compliance": False, "side_effects": 2},
    "missing-runtime-evidence": {"task_outcome": None, "policy_compliance": None},
    "contradictory-runtime-evidence": {"task_outcome": None, "policy_compliance": None},
    "infrastructure-unavailable": {"task_outcome": None, "policy_compliance": None},
}

_EXPECTED_RECORD_VALIDITIES = {
    "no-tool-required": {
        "tool_selection_accuracy": "not_applicable",
        "argument_accuracy": "not_applicable",
        "sequence_adherence": "not_applicable",
    },
    "missing-runtime-evidence": {
        "task_outcome": "unavailable",
        "policy_compliance": "unavailable",
    },
    "contradictory-runtime-evidence": {
        "task_outcome": "invalid",
        "policy_compliance": "invalid",
    },
    "infrastructure-unavailable": {
        "task_outcome": "unavailable",
        "policy_compliance": "unavailable",
    },
}


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_tool_workflow_profile_and_frozen_matrix_are_wheel_resources() -> None:
    profile = ToolWorkflowProfile()
    matrix = fixture_matrix()

    assert isinstance(profile, Profile)
    assert profile.authority.profile_id == "cernora-tool-workflow-v1"
    assert {case.case_id for case in profile.authority.cases} == {
        "create-request-v1",
        "no-tool-required-v1",
    }
    assert len(matrix) == 18
    assert {item.expected for item in matrix} == {
        "pass",
        "fail",
        "inconclusive",
        "import_rejection",
    }
    assert set(_EXPECTED_RECORD_VALUES) == {
        item.fixture_id for item in matrix if item.expected != "import_rejection"
    }


@pytest.mark.integration
@pytest.mark.parametrize(
    "expectation",
    tuple(item for item in fixture_matrix() if item.expected != "import_rejection"),
    ids=lambda item: item.fixture_id,
)
def test_tool_workflow_fixtures_are_three_run_byte_stable_and_strictly_reloaded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expectation: FixtureExpectation,
) -> None:
    def no_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("tool workflow acceptance attempted network access")

    monkeypatch.setattr(socket, "socket", no_network)
    profile = ToolWorkflowProfile()
    trees: list[dict[str, bytes]] = []
    for run in range(3):
        root = tmp_path / f"run-{run}"
        adapted = materialize_fixture(expectation.fixture_id, root / "bundle")
        imported = root / "imported"
        import_evidence_bundle_v2(
            profile=profile,
            bundle_path=adapted.bundle_path,
            output=imported,
        )
        evaluated = root / "evaluated"
        receipt = evaluate_imported_case(profile, imported, evaluated)
        report = read_evaluation_report(evaluated, profile)

        assert receipt.case_outcome == expectation.expected
        assert read_imported_evaluation(evaluated, profile) == receipt
        assert report is not None
        assert report.conclusion == receipt.case_outcome
        assert report.evaluation_input_sha256 == receipt.evaluation_input_sha256
        trees.append(_tree_bytes(evaluated))

    assert trees[0] == trees[1] == trees[2]
    report = read_evaluation_report(tmp_path / "run-0/evaluated", profile)
    assert report is not None
    evidence = json.loads((tmp_path / "run-0/evaluated/evidence.json").read_text(encoding="utf-8"))
    assert evidence["metadata"]["external_action_attested"] is False
    assert evidence["metadata"]["outcome_scope"] == "profile_owned_synthetic_observation"
    records = {record.id: record for record in report.records}
    assert records["task_outcome"].role == "outcome"
    assert records["policy_compliance"].role == "constraint"
    for record_id, expected_value in _EXPECTED_RECORD_VALUES[expectation.fixture_id].items():
        assert records[record_id].value == expected_value
    for record_id, expected_validity in _EXPECTED_RECORD_VALIDITIES.get(
        expectation.fixture_id, {}
    ).items():
        assert records[record_id].validity == expected_validity
    if expectation.fixture_id == "harmless-extra-action":
        assert records["action_relevance"].role == "advisory"
        assert records["action_relevance"].value is False
        assert report.conclusion == "pass"
    if expectation.expected == "inconclusive":
        expected_validity = (
            "invalid"
            if expectation.fixture_id == "contradictory-runtime-evidence"
            else "unavailable"
        )
        assert report.evaluation_validity == expected_validity
        assert records["task_outcome"].value is None
        if expectation.fixture_id == "contradictory-runtime-evidence":
            assert len(evidence["tool_actions"]) == 4
    else:
        assert report.evaluation_validity == "valid"


@pytest.mark.adversarial
def test_corrupt_fixture_is_rejected_before_behavioral_scoring(tmp_path: Path) -> None:
    profile = ToolWorkflowProfile()
    adapted = materialize_fixture("corrupt-artifact", tmp_path / "bundle")

    with pytest.raises(IngestionIntegrityError):
        import_evidence_bundle_v2(
            profile=profile,
            bundle_path=adapted.bundle_path,
            output=tmp_path / "imported",
        )
    assert not (tmp_path / "imported").exists()


@pytest.mark.adversarial
def test_persisted_report_tamper_is_rejected_by_strict_reload(tmp_path: Path) -> None:
    profile = ToolWorkflowProfile()
    adapted = materialize_fixture("happy-path", tmp_path / "bundle")
    imported = tmp_path / "imported"
    import_evidence_bundle_v2(
        profile=profile,
        bundle_path=adapted.bundle_path,
        output=imported,
    )
    evaluated = tmp_path / "evaluated"
    evaluate_imported_case(profile, imported, evaluated)
    (evaluated / "evaluation-report.json").write_bytes(b"{}")

    with pytest.raises(IngestionIntegrityError):
        read_evaluation_report(evaluated, profile)


@pytest.mark.adversarial
@pytest.mark.parametrize(
    "tamper",
    ("duplicate_reference", "unbound_reference", "score_contradiction"),
)
def test_deep_evaluator_rejects_untrusted_or_score_inconsistent_records(
    tmp_path: Path,
    tamper: str,
) -> None:
    base = ToolWorkflowProfile()
    adapted = materialize_fixture("happy-path", tmp_path / "bundle")
    imported = tmp_path / "imported"
    import_evidence_bundle_v2(
        profile=base,
        bundle_path=adapted.bundle_path,
        output=imported,
    )

    class TamperedProfile:
        authority = base.authority
        projection_version = base.projection_version

        def validate_import(self, package: object) -> None:
            base.validate_import(package)  # type: ignore[arg-type]

        def assess(self, package: object, context: object) -> object:
            assessment = base.assess(package, context)  # type: ignore[arg-type]
            first = assessment.result_records[0]
            payload = first.model_dump(mode="json", exclude_none=False)
            if tamper == "duplicate_reference":
                payload["evidence_refs"].append(payload["evidence_refs"][0])
            elif tamper == "unbound_reference":
                payload["evidence_refs"] = [
                    {
                        "evidence_id": first.evidence_refs[0].evidence_id,
                        "locator": "artifacts/not-declared.json",
                        "sha256": "f" * 64,
                    }
                ]
            else:
                payload["value"] = False
            changed = first.model_validate(payload)
            return replace(
                assessment,
                result_records=(changed, *assessment.result_records[1:]),
            )

    with pytest.raises(IngestionIntegrityError):
        evaluate_imported_case_v2(imported, TamperedProfile())  # type: ignore[arg-type]
