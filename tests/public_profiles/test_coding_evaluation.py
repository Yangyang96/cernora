from __future__ import annotations

import json
import socket
from copy import deepcopy
from pathlib import Path

import pytest

from cernora.evaluation.package import (
    evaluate_imported_case,
    read_evaluation_report,
    read_imported_evaluation,
)
from cernora.examples.coding_evaluation import (
    FixtureExpectation,
    fixture_matrix,
    materialize_adversarial_fixture,
    materialize_fixture,
)
from cernora.ingestion.errors import IngestionIntegrityError
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profile import Profile
from cernora.profiles.coding_evaluation import CodingEvaluationProfile, validate_candidate_tree

_INVALID_ROWS = {
    "untrusted-execution-authority",
    "wrong-capsule-binding",
    "duplicate-test-result",
    "conflicting-attempts",
}

_DIAGNOSTICS: dict[str, dict[str, bool | int | float]] = {
    "happy-path": {
        "task_outcome": True,
        "policy_compliance": True,
        "resolution_test_rate": 1.0,
        "regression_test_rate": 1.0,
    },
    "allowed-change": {"task_outcome": True, "policy_compliance": True},
    "build-failure": {
        "task_outcome": False,
        "build_succeeded": False,
        "resolution_test_rate": 0.0,
    },
    "unresolved-f2p": {
        "task_outcome": False,
        "policy_compliance": True,
        "resolution_test_rate": 0.5,
    },
    "regression-failure": {
        "task_outcome": True,
        "policy_compliance": False,
        "regression_test_rate": 0.5,
    },
    "forbidden-file-change": {
        "policy_compliance": False,
        "forbidden_file_change": True,
    },
    "protected-test-tamper": {
        "policy_compliance": False,
        "protected_test_tamper": True,
    },
    "terminal-binding-mismatch": {
        "task_outcome": False,
        "terminal_binding": False,
    },
    "candidate-self-mutation": {
        "policy_compliance": False,
        "candidate_self_mutation": True,
    },
    "retry-policy-violation": {
        "policy_compliance": False,
        "retry_policy_compliance": False,
    },
}


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_profile_authority_and_matrix_are_frozen_wheel_resources() -> None:
    profile = CodingEvaluationProfile()
    matrix = fixture_matrix()

    assert isinstance(profile, Profile)
    assert (profile.authority.profile_id, profile.authority.profile_version) == (
        "cernora-coding-evaluation-v1",
        "1.0.0",
    )
    assert profile.authority.scorer_policy.required_observations == (
        "task_outcome",
        "policy_compliance",
    )
    assert tuple(item.fixture_id for item in profile.authority.cases[0].fixture_references) == (
        "coding-evaluation-authority-v1",
        "coding-evaluation-oracle-v1",
    )
    assert len(matrix) == 20
    assert [item.expected for item in matrix].count("pass") == 2
    assert [item.expected for item in matrix].count("fail") == 8
    assert [item.expected for item in matrix].count("inconclusive") == 9
    assert [item.expected for item in matrix].count("import_rejection") == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    "expectation",
    tuple(item for item in fixture_matrix() if item.expected != "import_rejection"),
    ids=lambda item: item.fixture_id,
)
def test_coding_evaluation_matrix_is_three_run_byte_stable_offline_and_strictly_reloaded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expectation: FixtureExpectation,
) -> None:
    def no_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("coding evaluation attempted network access")

    monkeypatch.setattr(socket, "socket", no_network)
    profile = CodingEvaluationProfile()
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
        assert report.conclusion == expectation.expected
        trees.append(_tree_bytes(evaluated))

    assert trees[0] == trees[1] == trees[2]
    report = read_evaluation_report(tmp_path / "run-0/evaluated", profile)
    assert report is not None
    records = {item.id: item for item in report.records}
    assert {item.id for item in report.records if item.role in {"outcome", "constraint"}} == {
        "task_outcome",
        "policy_compliance",
    }
    if expectation.expected == "inconclusive":
        validity = "invalid" if expectation.fixture_id in _INVALID_ROWS else "unavailable"
        assert report.evaluation_validity == validity
        assert records["task_outcome"].validity == validity
        assert records["policy_compliance"].value is None
        assert records["task_outcome"].failure_reason == expectation.variant
    else:
        assert report.evaluation_validity == "valid"
        assert records["resolution_tests_total"].value == 2
        assert records["regression_tests_total"].value == 2
        for result_id, value in _DIAGNOSTICS[expectation.fixture_id].items():
            assert records[result_id].value == value
    evidence = json.loads((tmp_path / "run-0/evaluated/evidence.json").read_text(encoding="utf-8"))
    assert evidence["metadata"]["external_action_attested"] is False
    assert evidence["metadata"]["outcome_scope"] == ("profile_owned_synthetic_execution_capsule")
    assert len(evidence["metadata"]["candidate_tree_sha256"]) == 64
    if expectation.fixture_id == "untrusted-execution-authority":
        assert evidence["producer"]["producer_id"] == ("untrusted.synthetic.coding-evaluation")


@pytest.mark.adversarial
def test_corrupt_candidate_tree_is_rejected_before_scoring(tmp_path: Path) -> None:
    profile = CodingEvaluationProfile()
    adapted = materialize_fixture("corrupt-candidate-tree", tmp_path / "bundle")

    with pytest.raises(IngestionIntegrityError):
        import_evidence_bundle_v2(
            profile=profile,
            bundle_path=adapted.bundle_path,
            output=tmp_path / "imported",
        )
    assert not (tmp_path / "imported").exists()


def _invalid_candidate_tree(value: dict[str, object], variant: str) -> dict[str, object]:
    candidate = deepcopy(value)
    entries = candidate["entries"]
    assert isinstance(entries, list)
    entry = entries[0]
    assert isinstance(entry, dict)

    if variant == "wrong_version":
        candidate["schema_version"] = "cernora.candidate-tree/v2"
    elif variant == "entries_wrong_type":
        candidate["entries"] = {"not": "a list"}
    elif variant == "unknown_tree_member":
        candidate["producer_claim"] = "trusted"
    elif variant == "entry_wrong_type":
        entries[0] = "not an entry"
    elif variant == "unknown_entry_member":
        entry["producer_claim"] = "trusted"
    elif variant == "content_wrong_type":
        entry["content"] = b"not JSON text"
    elif variant == "executable_wrong_type":
        entry["executable"] = 1
    elif variant == "wrong_size":
        entry["size_bytes"] += 1
    elif variant == "wrong_entry_sha":
        entry["sha256"] = "0" * 64
    elif variant == "wrong_tree_sha":
        candidate["tree_sha256"] = "0" * 64
    else:  # pragma: no cover - the parameter list is closed below
        raise AssertionError(f"unknown Candidate Tree mutation: {variant}")
    return candidate


@pytest.mark.adversarial
@pytest.mark.parametrize(
    "variant",
    (
        "wrong_version",
        "entries_wrong_type",
        "unknown_tree_member",
        "entry_wrong_type",
        "unknown_entry_member",
        "content_wrong_type",
        "executable_wrong_type",
        "wrong_size",
        "wrong_entry_sha",
        "wrong_tree_sha",
    ),
)
def test_candidate_tree_internal_contract_rejects_member_and_digest_tamper(
    tmp_path: Path,
    variant: str,
) -> None:
    materialize_fixture("happy-path", tmp_path / "bundle")
    candidate = json.loads((tmp_path / "bundle/candidate/tree.json").read_text(encoding="utf-8"))
    assert validate_candidate_tree(candidate, label="candidate tree") == candidate

    with pytest.raises(ValueError):
        validate_candidate_tree(
            _invalid_candidate_tree(candidate, variant),
            label="candidate tree",
        )


@pytest.mark.adversarial
@pytest.mark.parametrize(
    "variant",
    (
        "reject_noncanonical_path",
        "reject_normalization_collision",
        "reject_case_collision",
        "reject_prefix_collision",
        "reject_wrong_baseline_binding",
        "reject_wrong_test_plan_binding",
        "reject_wrong_harness_binding",
    ),
)
def test_structural_and_authority_binding_adversaries_are_rejected(
    tmp_path: Path,
    variant: str,
) -> None:
    profile = CodingEvaluationProfile()
    adapted = materialize_adversarial_fixture(variant, tmp_path / "bundle")

    with pytest.raises((ValueError, IngestionIntegrityError)):
        import_evidence_bundle_v2(
            profile=profile,
            bundle_path=adapted.bundle_path,
            output=tmp_path / "imported",
        )
    assert not (tmp_path / "imported").exists()


@pytest.mark.adversarial
def test_persisted_coding_report_tamper_is_rejected(tmp_path: Path) -> None:
    profile = CodingEvaluationProfile()
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


def test_capsule_binds_all_frozen_execution_dimensions(tmp_path: Path) -> None:
    materialize_fixture("happy-path", tmp_path / "bundle")
    capsule = json.loads((tmp_path / "bundle/execution/capsule.json").read_text(encoding="utf-8"))

    assert set(capsule) == {
        "schema_version",
        "authority_id",
        "candidate_tree_sha256",
        "baseline_tree_sha256",
        "test_plan_sha256",
        "harness_sha256",
        "toolchain",
        "platform",
        "command",
        "limits",
        "attempt_policy",
        "attempts",
    }
    assert capsule["attempt_policy"] == {
        "max_attempts": 2,
        "retry_only_after": "infrastructure_unavailable",
    }
    assert {item["classification"] for item in capsule["attempts"][0]["test_results"]} == {
        "fail_to_pass",
        "pass_to_pass",
    }
