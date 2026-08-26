from __future__ import annotations

import hashlib
import json
import os
import shutil
from fractions import Fraction
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

import cernora._closed_package as closed_package
import cernora.comparison as comparison_module
from cernora import (
    PUBLIC_SCHEMAS,
    ComparisonInput,
    ComparisonSummary,
    read_public_schema,
)
from cernora.batch import (
    materialize_batch_input,
    reload_batch_summary_package,
    summarize_batch,
)
from cernora.cli.main import main
from cernora.comparison import (
    BootstrapPlan,
    ComparisonArm,
    ComparisonCase,
    ComparisonEstimate,
    ComparisonGuardrail,
    ComparisonInterval,
    ExperimentProjection,
    GuardrailResult,
    PassKPlan,
    PrimaryOutcome,
    PrimaryResult,
    TreatmentChange,
    build_comparison_summary,
    materialize_comparison_input,
    materialize_experiment_authority,
    materialize_treatment,
    reload_comparison_package,
    reload_comparison_summary,
    summarize_comparison,
    validate_comparison_input,
)
from cernora.core.canonical import canonical_json, decode_contract
from cernora.core.evidence_bundle_v2 import BundleCaseIdentity
from cernora.evaluation.package import validate_evaluation_package_content
from cernora.ingestion.errors import IngestionConfigurationError, IngestionIntegrityError
from tests.public.test_batch_summary import _batch_input


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _comparison_input(
    tmp_path: Path,
    *,
    candidate_timeout: str | None = None,
    candidate_projection_overrides: dict[str, str] | None = None,
) -> ComparisonInput:
    original_batch = _batch_input(tmp_path)
    evaluated = next(
        trial.attempts[-1].evaluation
        for trial in original_batch.trials
        if trial.attempts[-1].evaluation is not None
    )
    assert evaluated is not None
    receipt, _ = validate_evaluation_package_content(evaluated.file_payloads())
    profile_sha256 = receipt.profile.sha256
    case_identities = {
        receipt.case.case_id: receipt.case,
        "no-tool-required-v1": BundleCaseIdentity(
            case_id="no-tool-required-v1",
            case_version="1.0.0",
            case_set="comparison-fixture",
            sha256=_digest("no-tool-required-v1"),
        ),
    }
    common_projection = {
        "runtime_version_sha256": _digest("runtime"),
        "model_sha256": _digest("model"),
        "tool_schema_sha256": _digest("tools"),
        "generation_configuration_sha256": _digest("generation"),
        "timeout_sha256": _digest("timeout"),
        "resources_sha256": _digest("resources"),
        "retry_policy_sha256": _digest("retry"),
        "dataset_sha256": _digest("dataset"),
        "profile_sha256": profile_sha256,
        "evaluation_policy_sha256": comparison_module.evaluation_policy_sha256(receipt),
        "report_contract_sha256": _digest("report-contract"),
        "statistical_plan_sha256": _digest("statistics"),
    }
    prompt_baseline = _digest("baseline-prompt")
    prompt_candidate = _digest("candidate-prompt")
    evaluation_authorities: dict[str, str] = {}
    for case_id in case_identities:
        packages = [
            trial.attempts[-1].evaluation
            for trial in original_batch.trials
            if trial.case_id == case_id and trial.attempts[-1].evaluation is not None
        ]
        if packages:
            package = packages[0]
            assert package is not None
            case_receipt, _ = validate_evaluation_package_content(package.file_payloads())
            evaluation_authorities[case_id] = case_receipt.authority_sha256
        else:
            evaluation_authorities[case_id] = _digest(f"evaluation-authority-{case_id}")
    experiment_authorities = []
    for case_id in sorted(case_identities):
        for configuration_id in ("configuration-a", "configuration-b"):
            prompt = prompt_baseline if configuration_id == "configuration-a" else prompt_candidate
            timeout = (
                candidate_timeout
                if configuration_id == "configuration-b" and candidate_timeout is not None
                else common_projection["timeout_sha256"]
            )
            overrides = (
                candidate_projection_overrides
                if configuration_id == "configuration-b"
                and candidate_projection_overrides is not None
                else {}
            )
            projection = ExperimentProjection(
                **{
                    **common_projection,
                    "prompt_instruction_sha256": prompt,
                    "timeout_sha256": timeout,
                    "evaluation_authority_sha256": evaluation_authorities[case_id],
                    **overrides,
                }
            )
            experiment_authorities.append(
                materialize_experiment_authority(
                    {
                        "schema_version": ("agent.evaluator.comparison-experiment-authority/v1"),
                        "configuration_id": configuration_id,
                        "case": case_identities[case_id].model_dump(mode="json"),
                        "projection": projection.model_dump(mode="json"),
                    }
                )
            )
    experiment_ids = {
        (item.case.case_id, item.configuration_id): item.experiment_id
        for item in experiment_authorities
    }
    batch_payload = original_batch.model_dump(
        mode="json", exclude={"batch_input_id", "batch_input_sha256"}
    )
    for slot in batch_payload["planned_trials"]:
        slot["experiment_id"] = experiment_ids[(slot["case_id"], slot["configuration_id"])]
    for trial in batch_payload["trials"]:
        trial["experiment_id"] = experiment_ids[(trial["case_id"], trial["configuration_id"])]
    batch_input = materialize_batch_input(batch_payload)
    baseline = ComparisonArm(configuration_id="configuration-a")
    candidate = ComparisonArm(configuration_id="configuration-b")
    treatment = materialize_treatment(
        (
            TreatmentChange(
                kind="prompt_instruction",
                baseline_sha256=prompt_baseline,
                candidate_sha256=prompt_candidate,
            ),
        )
    )
    cases = tuple(
        ComparisonCase(
            case=case_identities[case_id],
            split_id="development" if case_id == receipt.case.case_id else "regression",
            baseline_experiment_id=experiment_ids[(case_id, "configuration-a")],
            candidate_experiment_id=experiment_ids[(case_id, "configuration-b")],
        )
        for case_id in sorted(case_identities)
    )
    guardrails = (
        ComparisonGuardrail(
            guardrail_id="evaluation-validity",
            hard=True,
            metric="evaluation_validity_rate",
            scope="all",
            direction="higher_is_better",
            max_adverse_basis_points=0,
        ),
        ComparisonGuardrail(
            guardrail_id="regression-reliable-success",
            hard=True,
            metric="reliable_success_rate",
            scope="split",
            split_id="regression",
            direction="higher_is_better",
            max_adverse_basis_points=1_000,
        ),
    )
    return materialize_comparison_input(
        {
            "schema_version": "agent.evaluator.comparison-input/v1",
            "batch_input": batch_input.model_dump(mode="json"),
            "baseline": baseline.model_dump(mode="json"),
            "candidate": candidate.model_dump(mode="json"),
            "experiment_authorities": [
                item.model_dump(mode="json") for item in experiment_authorities
            ],
            "cases": [item.model_dump(mode="json") for item in cases],
            "treatment": treatment.model_dump(mode="json"),
            "primary_outcome": PrimaryOutcome(
                metric="reliable_success_rate",
                scope="all",
                direction="higher_is_better",
                practical_threshold_basis_points=1_000,
            ).model_dump(mode="json"),
            "guardrails": [item.model_dump(mode="json") for item in guardrails],
            "bootstrap": BootstrapPlan(
                method="case-clustered-paired-bootstrap/v1",
                confidence_basis_points=9_500,
                resamples=10_000,
                percentile="nearest_rank_closed",
                seed_source="comparison_input_sha256",
            ).model_dump(mode="json"),
            "pass_k": PassKPlan(k=2, independent_trials=True).model_dump(mode="json"),
        }
    )


def _replace_experiment_authority(
    comparison: ComparisonInput,
    *,
    case_id: str,
    configuration_id: str,
    projection_overrides: dict[str, str],
    update_bindings: bool,
) -> ComparisonInput:
    old = next(
        item
        for item in comparison.experiment_authorities
        if item.case.case_id == case_id and item.configuration_id == configuration_id
    )
    authority_payload = old.model_dump(mode="json", exclude={"experiment_id", "experiment_sha256"})
    authority_payload["projection"].update(projection_overrides)
    replacement = materialize_experiment_authority(authority_payload)
    payload = comparison.model_dump(
        mode="json", exclude={"comparison_id", "comparison_input_sha256"}
    )
    payload["experiment_authorities"] = [
        replacement.model_dump(mode="json")
        if item.case.case_id == case_id and item.configuration_id == configuration_id
        else item.model_dump(mode="json")
        for item in comparison.experiment_authorities
    ]
    if update_bindings:
        batch_payload = comparison.batch_input.model_dump(
            mode="json", exclude={"batch_input_id", "batch_input_sha256"}
        )
        for slot in batch_payload["planned_trials"]:
            if slot["case_id"] == case_id and slot["configuration_id"] == configuration_id:
                slot["experiment_id"] = replacement.experiment_id
        for trial in batch_payload["trials"]:
            if trial["case_id"] == case_id and trial["configuration_id"] == configuration_id:
                trial["experiment_id"] = replacement.experiment_id
        payload["batch_input"] = materialize_batch_input(batch_payload).model_dump(mode="json")
        for case in payload["cases"]:
            if case["case"]["case_id"] == case_id:
                role = (
                    "baseline_experiment_id"
                    if configuration_id == comparison.baseline.configuration_id
                    else "candidate_experiment_id"
                )
                case[role] = replacement.experiment_id
    return materialize_comparison_input(payload)


@pytest.mark.integration
def test_comparison_is_identity_closed_deterministic_and_attempts_are_not_samples(
    tmp_path: Path,
) -> None:
    comparison = _comparison_input(tmp_path)
    first = build_comparison_summary(comparison)
    second = build_comparison_summary(comparison)

    assert first == second
    assert first.comparable
    assert first.primary is not None
    assert first.primary.baseline.denominator == 6
    assert first.primary.candidate.denominator == 6
    assert sum(item.count for item in first.outcome_transitions) == 6
    assert first.pass_metrics is not None
    assert first.pass_metrics.status == "qualified"
    assert first.pass_metrics.k == 2
    assert first.pass_metrics.baseline_pass_at_k == _estimate(Fraction(1, 3))
    assert first.pass_metrics.candidate_pass_at_k == _estimate(Fraction(1, 3))
    assert first.pass_metrics.pass_at_k_delta == _estimate(Fraction())
    assert first.pass_metrics.baseline_pass_power_k == _estimate(Fraction())
    assert first.pass_metrics.candidate_pass_power_k == _estimate(Fraction())
    assert first.pass_metrics.pass_power_k_delta == _estimate(Fraction())
    assert first.conclusion in {"uncertain", "no_change", "mixed", "regressed", "improved"}
    assert comparison.batch_input.attempt_count == 13
    assert [item.model_dump(mode="json") for item in first.failure_migration] == [
        {
            "profile_id": "cernora-tool-workflow-v1",
            "profile_version": "1.0.0",
            "code": "task_outcome",
            "persisted": 1,
            "resolved": 0,
            "introduced": 0,
        }
    ]
    assert first.failure_migration_unavailable_pairs == 4
    authoritative = canonical_json(first).lower()
    for forbidden in (b"p_value", b"p-value", b"winner", b"ranking", b"promotion"):
        assert forbidden not in authoritative


def test_undeclared_invariant_difference_is_not_comparable(tmp_path: Path) -> None:
    comparison = _comparison_input(tmp_path, candidate_timeout=_digest("different-timeout"))
    summary = build_comparison_summary(comparison)

    assert not summary.comparable
    assert summary.conclusion == "not_comparable"
    assert summary.primary is None
    assert summary.comparability_reasons == (
        "treatment_does_not_exhaust_arm_differences:create-request-v1",
        "treatment_does_not_exhaust_arm_differences:no-tool-required-v1",
    )


@pytest.mark.parametrize(
    "field",
    (
        "timeout_sha256",
        "resources_sha256",
        "retry_policy_sha256",
        "dataset_sha256",
        "profile_sha256",
        "report_contract_sha256",
        "statistical_plan_sha256",
    ),
)
def test_treatment_cannot_hide_authority_bound_invariant_differences(
    tmp_path: Path, field: str
) -> None:
    comparison = _comparison_input(
        tmp_path,
        candidate_projection_overrides={field: _digest(f"different-{field}")},
    )
    summary = build_comparison_summary(comparison)
    assert not summary.comparable
    assert any(
        reason.startswith("treatment_does_not_exhaust_arm_differences:")
        for reason in summary.comparability_reasons
    )


def test_experiment_authority_is_recomputed_and_bound_to_batch_slots(tmp_path: Path) -> None:
    comparison = _comparison_input(tmp_path)
    payload = comparison.model_dump(mode="json")
    payload["experiment_authorities"][0]["projection"]["model_sha256"] = _digest("tampered-model")
    with pytest.raises(ValueError, match="Experiment authority identity"):
        decode_contract(canonical_json(payload), ComparisonInput)

    with pytest.raises(ValueError, match="not bound to Experiment authority"):
        _replace_experiment_authority(
            comparison,
            case_id="create-request-v1",
            configuration_id="configuration-a",
            projection_overrides={"model_sha256": _digest("replacement-model")},
            update_bindings=False,
        )


def test_arm_projection_must_be_coherent_across_cases(tmp_path: Path) -> None:
    comparison = _comparison_input(tmp_path)
    for configuration_id in ("configuration-a", "configuration-b"):
        comparison = _replace_experiment_authority(
            comparison,
            case_id="no-tool-required-v1",
            configuration_id=configuration_id,
            projection_overrides={"model_sha256": _digest("same-hidden-drift")},
            update_bindings=True,
        )
    summary = build_comparison_summary(comparison)
    assert not summary.comparable
    assert "arm_projection_incoherent:configuration-a:model_sha256" in summary.comparability_reasons
    assert "arm_projection_incoherent:configuration-b:model_sha256" in summary.comparability_reasons


def test_receipt_authority_and_policy_must_match_bound_projection(tmp_path: Path) -> None:
    comparison = _comparison_input(tmp_path)
    authority_mismatch = _replace_experiment_authority(
        comparison,
        case_id="create-request-v1",
        configuration_id="configuration-a",
        projection_overrides={
            "evaluation_authority_sha256": _digest("different-evaluation-authority")
        },
        update_bindings=True,
    )
    authority_summary = build_comparison_summary(authority_mismatch)
    assert not authority_summary.comparable
    assert (
        "evaluation_authority_mismatch:create-request-v1" in authority_summary.comparability_reasons
    )

    policy_mismatch = comparison
    for case_id in ("create-request-v1", "no-tool-required-v1"):
        for configuration_id in ("configuration-a", "configuration-b"):
            policy_mismatch = _replace_experiment_authority(
                policy_mismatch,
                case_id=case_id,
                configuration_id=configuration_id,
                projection_overrides={
                    "evaluation_policy_sha256": _digest("different-evaluation-policy")
                },
                update_bindings=True,
            )
    policy_summary = build_comparison_summary(policy_mismatch)
    assert not policy_summary.comparable
    assert "evaluation_policy_mismatch:create-request-v1" in policy_summary.comparability_reasons


def test_comparison_identity_and_pairing_reject_tamper(tmp_path: Path) -> None:
    comparison = _comparison_input(tmp_path)
    payload = comparison.model_dump(mode="json")
    payload["comparison_input_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="identity"):
        decode_contract(canonical_json(payload), comparison_module.ComparisonInput)

    without_identity = comparison.model_dump(
        mode="json", exclude={"comparison_id", "comparison_input_sha256"}
    )
    without_identity["cases"][0]["candidate_experiment_id"] = "f" * 64
    with pytest.raises(ValueError, match="selected Experiments"):
        materialize_comparison_input(without_identity)


def test_bootstrap_sampler_and_percentile_golden_vectors() -> None:
    seed = "0" * 64
    first_ten = tuple(
        tuple(comparison_module._cluster_index(seed, replicate, draw, 3) for draw in range(3))
        for replicate in range(10)
    )
    assert first_ten == (
        (0, 1, 0),
        (2, 2, 2),
        (2, 2, 1),
        (1, 1, 2),
        (2, 1, 1),
        (1, 1, 0),
        (1, 0, 0),
        (2, 1, 1),
        (2, 2, 1),
        (2, 0, 0),
    )
    interval = comparison_module._bootstrap_interval(
        seed_sha256=seed,
        case_numerators=(-1, 0, 2),
        trials_per_case=3,
    )
    assert Fraction(interval.lower.numerator, interval.lower.denominator) == Fraction(-3, 9)
    assert Fraction(interval.upper.numerator, interval.upper.denominator) == Fraction(6, 9)


def test_pass_at_k_and_pass_power_k_golden_vectors() -> None:
    pass_at = [
        comparison_module._combination_probability(3, successes, 2, at_least_one=True)
        for successes in range(4)
    ]
    pass_power = [
        comparison_module._combination_probability(3, successes, 2, at_least_one=False)
        for successes in range(4)
    ]
    assert sum(pass_at, start=Fraction()) / 4 == Fraction(2, 3)
    assert sum(pass_power, start=Fraction()) / 4 == Fraction(1, 3)


def test_percentile_indices_are_pinned_to_nearest_rank_edges() -> None:
    first = comparison_module._bootstrap_interval(
        seed_sha256="0" * 64,
        case_numerators=(-3, -3, -1, 0, 3, 3),
        trials_per_case=3,
    )
    assert first.lower.numerator == -13
    assert first.upper.numerator == 11
    assert first.lower.denominator == first.upper.denominator == 18

    second = comparison_module._bootstrap_interval(
        seed_sha256="0" * 64,
        case_numerators=(-3, -3, -2, -2, 1, 2),
        trials_per_case=3,
    )
    assert second.lower.numerator == -8
    assert second.lower.denominator == 9
    assert Fraction(second.upper.numerator, second.upper.denominator) == Fraction(1, 9)


def _estimate(value: Fraction) -> ComparisonEstimate:
    return ComparisonEstimate(
        numerator=value.numerator,
        denominator=value.denominator,
        value=float(value),
    )


def _primary_with_interval(point: Fraction, lower: Fraction, upper: Fraction) -> PrimaryResult:
    baseline_value = max(Fraction(), -point)
    candidate_value = max(Fraction(), point)
    return PrimaryResult(
        metric="reliable_success_rate",
        baseline=comparison_module.BatchRate(
            numerator=baseline_value.numerator,
            denominator=baseline_value.denominator,
            value=float(baseline_value),
        ),
        candidate=comparison_module.BatchRate(
            numerator=candidate_value.numerator,
            denominator=candidate_value.denominator,
            value=float(candidate_value),
        ),
        delta=_estimate(point),
        interval=ComparisonInterval(lower=_estimate(lower), upper=_estimate(upper)),
    )


def _guardrail(status: str) -> GuardrailResult:
    unavailable = status == "unavailable"
    rate = comparison_module.BatchRate(numerator=0, denominator=1, value=0.0)
    estimate = _estimate(Fraction())
    interval = ComparisonInterval(lower=estimate, upper=estimate)
    return GuardrailResult.model_validate(
        {
            "guardrail_id": "hard-guardrail",
            "status": status,
            "baseline": None if unavailable else rate,
            "candidate": None if unavailable else rate,
            "oriented_delta": None if unavailable else estimate,
            "interval": None if unavailable else interval,
            "unavailable_cases": ("case-v1",) if unavailable else (),
        }
    )


def test_conclusion_precedence_is_closed_and_guardrails_block_improved(tmp_path: Path) -> None:
    comparison = _comparison_input(tmp_path)
    satisfied = _guardrail("satisfied")
    violated = _guardrail("violated")
    unavailable = _guardrail("unavailable")

    assert (
        comparison_module._conclusion(
            comparison, _primary_with_interval(Fraction(), Fraction(), Fraction()), (satisfied,)
        )
        == "uncertain"
    )
    assert (
        comparison_module._conclusion(
            comparison,
            _primary_with_interval(Fraction(1, 20), Fraction(1, 100), Fraction(1, 10)),
            (satisfied,),
        )
        == "no_change"
    )
    assert (
        comparison_module._conclusion(
            comparison,
            _primary_with_interval(Fraction(1, 10), Fraction(1, 100), Fraction(1, 5)),
            (satisfied,),
        )
        == "improved"
    )
    assert (
        comparison_module._conclusion(
            comparison,
            _primary_with_interval(Fraction(1, 10), Fraction(1, 100), Fraction(1, 5)),
            (violated,),
        )
        == "mixed"
    )
    assert (
        comparison_module._conclusion(
            comparison,
            _primary_with_interval(Fraction(-1, 10), Fraction(-1, 5), Fraction(-1, 100)),
            (satisfied,),
        )
        == "regressed"
    )
    assert (
        comparison_module._conclusion(
            comparison,
            _primary_with_interval(Fraction(1, 10), Fraction(1, 100), Fraction(1, 5)),
            (unavailable,),
        )
        == "uncertain"
    )
    assert (
        comparison_module._conclusion(
            comparison,
            _primary_with_interval(Fraction(1, 10), Fraction(), Fraction(1, 5)),
            (violated,),
        )
        == "regressed"
    )
    assert (
        comparison_module._conclusion(
            comparison,
            _primary_with_interval(Fraction(1, 10), Fraction(1, 100), Fraction(1, 5)),
            (satisfied,),
        )
        == "improved"
    )
    assert (
        comparison_module._conclusion(
            comparison,
            _primary_with_interval(Fraction(1, 20), Fraction(1, 100), Fraction(1, 10)),
            (violated,),
        )
        == "mixed"
    )


def test_guardrail_tolerance_equality_is_satisfied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    comparison = _comparison_input(tmp_path)
    zero = _estimate(Fraction())
    monkeypatch.setattr(
        comparison_module,
        "_bootstrap_interval",
        lambda **_: ComparisonInterval(lower=zero, upper=zero),
    )

    result = comparison_module._guardrail(comparison, comparison.guardrails[0])

    assert comparison.guardrails[0].max_adverse_basis_points == 0
    assert result.interval is not None
    assert result.interval.lower == zero
    assert result.status == "satisfied"


def test_treatment_is_nonempty_sorted_unique_and_content_identified() -> None:
    changes = (
        TreatmentChange(
            kind="model",
            baseline_sha256=_digest("model-a"),
            candidate_sha256=_digest("model-b"),
        ),
        TreatmentChange(
            kind="prompt_instruction",
            baseline_sha256=_digest("prompt-a"),
            candidate_sha256=_digest("prompt-b"),
        ),
    )
    treatment = materialize_treatment(changes)
    assert tuple(item.kind for item in treatment.changes) == ("model", "prompt_instruction")
    assert treatment.treatment_id == f"treatment-{treatment.treatment_sha256}"
    with pytest.raises(ValueError, match="must differ"):
        TreatmentChange(
            kind="model",
            baseline_sha256=_digest("same"),
            candidate_sha256=_digest("same"),
        )


@pytest.mark.integration
def test_comparison_packages_are_byte_identical_and_strictly_rederived(tmp_path: Path) -> None:
    comparison = _comparison_input(tmp_path)
    trees = []
    summaries = []
    for index in range(3):
        output = tmp_path / f"comparison-{index}"
        summaries.append(summarize_comparison(comparison, output))
        trees.append(
            {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }
        )
    assert summaries[0] == summaries[1] == summaries[2]
    assert trees[0] == trees[1] == trees[2]
    assert reload_comparison_summary(tmp_path / "comparison-0") == summaries[0]
    package = reload_comparison_package(tmp_path / "comparison-0")
    assert package.comparison_input == comparison
    assert package.summary == summaries[0]

    input_path = tmp_path / "comparison-input.json"
    input_path.write_bytes(canonical_json(comparison))
    assert validate_comparison_input(input_path) == comparison
    with pytest.raises(IngestionConfigurationError, match="must not already exist"):
        summarize_comparison(comparison, tmp_path / "comparison-0")


def test_comparison_package_rejects_tamper_extra_files_and_symlinks(tmp_path: Path) -> None:
    comparison = _comparison_input(tmp_path)
    source = tmp_path / "source"
    summarize_comparison(comparison, source)

    tampered = tmp_path / "tampered"
    shutil.copytree(source, tampered)
    payload = bytearray((tampered / "comparison-summary.json").read_bytes())
    payload[-2] = ord("0") if payload[-2] != ord("0") else ord("1")
    (tampered / "comparison-summary.json").write_bytes(payload)
    with pytest.raises(IngestionIntegrityError, match="digest mismatch"):
        reload_comparison_summary(tampered)

    extra = tmp_path / "extra"
    shutil.copytree(source, extra)
    (extra / "unknown.txt").write_text("not declared", encoding="utf-8")
    with pytest.raises(IngestionIntegrityError, match="file set"):
        reload_comparison_summary(extra)

    linked = tmp_path / "linked"
    shutil.copytree(source, linked)
    (linked / "comparison-summary.md").unlink()
    (linked / "comparison-summary.md").symlink_to(source / "comparison-summary.md")
    with pytest.raises(IngestionIntegrityError, match="non-ordinary file"):
        reload_comparison_summary(linked)


@pytest.mark.parametrize("package_kind", ("batch", "comparison"))
@pytest.mark.parametrize("aba", (False, True), ids=("a-to-b", "aba"))
def test_closed_package_reload_rejects_valid_root_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    package_kind: str,
    aba: bool,
) -> None:
    root_a = tmp_path / "package-a"
    root_b = tmp_path / "package-b"
    if package_kind == "batch":
        batch_a = _batch_input(tmp_path / "batch-source")
        batch_b_payload = batch_a.model_dump(
            mode="json", exclude={"batch_input_id", "batch_input_sha256"}
        )
        batch_b_payload["companion_version"] = "0.2.1-replacement"
        batch_b = materialize_batch_input(batch_b_payload)
        summarize_batch(batch_a, root_a)
        summarize_batch(batch_b, root_b)
        reloader = reload_batch_summary_package
    else:
        comparison_a = _comparison_input(tmp_path / "comparison-source")
        comparison_b_payload = comparison_a.model_dump(
            mode="json", exclude={"comparison_id", "comparison_input_sha256"}
        )
        comparison_b_payload["primary_outcome"]["practical_threshold_basis_points"] = 2_000
        comparison_b = materialize_comparison_input(comparison_b_payload)
        summarize_comparison(comparison_a, root_a)
        summarize_comparison(comparison_b, root_b)
        reloader = reload_comparison_package

    original_open = closed_package.os.open
    backup = tmp_path / "package-a-backup"
    triggered = False

    def replace_before_root_open(  # type: ignore[no-untyped-def]
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal triggered
        if not triggered and dir_fd is None and Path(path) == root_a:
            triggered = True
            os.rename(root_a, backup)
            os.rename(root_b, root_a)
            if aba:
                os.rename(root_a, root_b)
                os.rename(backup, root_a)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(closed_package.os, "open", replace_before_root_open)
    with pytest.raises(IngestionIntegrityError, match="stable|changed"):
        reloader(root_a)
    assert triggered


def test_batch_package_reload_preserves_full_trial_authority(tmp_path: Path) -> None:
    batch_input = _batch_input(tmp_path)
    root = tmp_path / "batch-summary"
    summary = summarize_batch(batch_input, root)
    package = reload_batch_summary_package(root)
    assert package.batch_input == batch_input
    assert package.summary == summary


def test_comparison_root_exports_schemas_and_cli_exit_classes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    comparison = _comparison_input(tmp_path)
    summary = build_comparison_summary(comparison)
    assert isinstance(comparison, ComparisonInput)
    assert isinstance(summary, ComparisonSummary)
    assert "comparison-input-v1.schema.json" in PUBLIC_SCHEMAS
    assert "comparison-summary-v1.schema.json" in PUBLIC_SCHEMAS
    Draft202012Validator(
        json.loads(read_public_schema("comparison-input-v1.schema.json"))
    ).validate(comparison.model_dump(mode="json"))
    Draft202012Validator(
        json.loads(read_public_schema("comparison-summary-v1.schema.json"))
    ).validate(summary.model_dump(mode="json"))

    input_path = tmp_path / "comparison.json"
    input_path.write_bytes(canonical_json(comparison))
    assert main(["comparison", "validate", str(input_path)]) == 0
    assert f'"comparison_id":"{comparison.comparison_id}"' in capsys.readouterr().out
    output = tmp_path / "cli-comparison"
    assert main(["comparison", "summarize", str(input_path), "--output", str(output)]) == 0
    assert reload_comparison_summary(output) == summary
    capsys.readouterr()

    input_path.write_bytes(b"{}")
    assert main(["comparison", "validate", str(input_path)]) == 3
    assert "invalid Comparison Input" in capsys.readouterr().err
