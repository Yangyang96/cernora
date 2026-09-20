"""Opt-in Plan authority, real import/reload, and adversarial Metric contracts."""

import hashlib
import json
from dataclasses import replace

import pytest

from cernora import (
    ArgumentMatch,
    FactMatch,
    Latency,
    MetricBinding,
    MetricContext,
    MetricDefinition,
    MetricPlan,
    ToolCalls,
    ToolSelection,
    evaluate_imported_case,
    import_evidence_bundle_v2,
    read_evaluation_report,
    read_imported_evaluation,
)
from cernora.core.case import CaseProfile
from cernora.core.evidence import EvidenceReference
from cernora.core.result import ResultRecord
from cernora.examples.metric_plans import InventoryProfile, ResourceStatusProfile
from cernora.examples.metric_plans.__main__ import materialize
from cernora.ingestion.errors import IngestionIntegrityError
from cernora.metrics.plan import MetricCall


@pytest.fixture
def context():
    receipt = EvidenceReference(
        evidence_id="e", locator="source-import/import-receipt.json", sha256="a" * 64
    )
    data = {
        "answer": b'{"status":"ready"}',
        "source": b'{"status":"ready"}',
        "timing": b'{"clock_id":"m","scope":"agent_wall","start_ms":5,"end_ms":30}',
    }
    artifacts = tuple(
        (
            k,
            v,
            EvidenceReference(
                evidence_id="e", locator=f"artifacts/{k}", sha256=hashlib.sha256(v).hexdigest()
            ),
        )
        for k, v in data.items()
    )
    return MetricContext(
        (MetricCall("one", "lookup", ("lookup", "alpha"), "completed", True),),
        True,
        receipt,
        artifacts,
        "answer",
        ("source",),
    )


def authority(plan):
    payload = ResourceStatusProfile().authority.model_dump(mode="json")
    payload["scorer_policy"] = {
        "policy_version": plan.scorer_version,
        "required_observations": plan.required_observations,
    }
    return CaseProfile.model_validate_json(json.dumps(payload))


def evaluate(metric, context, params="{}", **kwargs):
    plan = MetricPlan(
        (
            MetricBinding(ToolSelection(), "required", '{"allowed_tools":["lookup"]}'),
            MetricBinding(metric, parameters_json=params, **kwargs),
        )
    )
    return plan.evaluate(context, authority(plan))[-1]


@pytest.mark.parametrize("factory", [ResourceStatusProfile, InventoryProfile])
@pytest.mark.parametrize(
    "variant,expected", [("pass", "pass"), ("fail", "fail"), ("missing", "inconclusive")]
)
def test_real_profile_import_reload_determinism(tmp_path, factory, variant, expected):
    profile = factory()
    bundle = materialize(profile, tmp_path / "bundle", variant)
    import_evidence_bundle_v2(profile=profile, bundle_path=bundle, output=tmp_path / "import")
    outputs = []
    for i in range(3):
        output = tmp_path / str(i)
        receipt = evaluate_imported_case(profile, tmp_path / "import", output)
        assert receipt.case_outcome == expected
        assert read_imported_evaluation(output, profile) == receipt
        assert read_evaluation_report(output, profile).conclusion == expected
        outputs.append((output / "evaluation-report.json").read_bytes())
    assert outputs[0] == outputs[1] == outputs[2]


def test_two_domains_share_implementations():
    a, b = ResourceStatusProfile(), InventoryProfile()
    assert [type(x.metric) for x in a.plan.metrics] == [type(x.metric) for x in b.plan.metrics[:5]]
    assert len(b.plan.metrics) == 6
    assert a.plan.sha256 != b.plan.sha256


def test_complete_source_conflict_preserves_existing_boundary(tmp_path):
    p = ResourceStatusProfile()
    bundle = materialize(p, tmp_path / "bundle", "conflict")
    import_evidence_bundle_v2(profile=p, bundle_path=bundle, output=tmp_path / "import")
    with pytest.raises(IngestionIntegrityError, match="evidence boundary"):
        evaluate_imported_case(p, tmp_path / "import", tmp_path / "result")
    assert not (tmp_path / "result").exists()


def test_tampered_bytes_and_plan_drift_rejected(tmp_path):
    p = ResourceStatusProfile()
    bundle = materialize(p, tmp_path / "bundle")
    (bundle.parent / "source.json").write_bytes(b'{"status":"wrong"}')
    with pytest.raises(ValueError):
        import_evidence_bundle_v2(profile=p, bundle_path=bundle, output=tmp_path / "import")
    p.plan = replace(
        p.plan,
        metrics=(
            replace(p.plan.metrics[0], parameters_json='{"allowed_tools":["other"]}'),
            *p.plan.metrics[1:],
        ),
    )
    with pytest.raises(ValueError, match="authority"):
        _ = p.authority


@pytest.mark.parametrize("kind", ["parameters", "version", "role", "threshold"])
def test_complete_plan_identity_is_bound(context, kind):
    plan = MetricPlan(
        (
            MetricBinding(ToolSelection(), "required", '{"allowed_tools":["lookup"]}'),
            MetricBinding(ToolCalls(), "required", maximum=3),
        )
    )
    old = authority(plan)
    if kind == "parameters":
        bindings = (
            replace(plan.metrics[0], parameters_json='{"allowed_tools":["other"]}'),
            plan.metrics[1],
        )
    elif kind == "role":
        bindings = (plan.metrics[0], MetricBinding(ToolCalls(), "advisory"))
    elif kind == "threshold":
        bindings = (plan.metrics[0], replace(plan.metrics[1], maximum=2))
    else:

        class OtherCalls(ToolCalls):
            definition = ToolCalls.definition.model_copy(update={"metric_version": "2.0.0"})

        bindings = (plan.metrics[0], MetricBinding(OtherCalls(), "required", maximum=3))
    changed = MetricPlan(bindings)
    assert changed.sha256 != plan.sha256
    with pytest.raises(ValueError, match="authority"):
        changed.evaluate(context, old)


@pytest.mark.parametrize(
    "params",
    [
        '{"unknown":1}',
        '{"allowed_tools":[]}',
        '{"allowed_tools":["lookup"],"allow_empty":1}',
        '{"allowed_tools":["lookup"],"allowed_tools":["other"]}',
    ],
)
def test_invalid_configuration_not_silently_accepted(params):
    with pytest.raises(ValueError):
        MetricBinding(ToolSelection(), parameters_json=params)


def test_unknown_plan_version_and_duplicate_ids():
    binding = MetricBinding(ToolSelection(), "required", '{"allowed_tools":["lookup"]}')
    with pytest.raises(ValueError):
        MetricPlan((binding,), version="future")
    with pytest.raises(ValueError):
        MetricPlan((binding, binding))
    with pytest.raises(ValueError):
        MetricBinding(ToolCalls(), "required")
    with pytest.raises(ValueError):
        MetricBinding(ToolCalls(), "required", maximum=float("nan"))


def test_selection_empty_and_incomplete(context):
    metric = ToolSelection()
    assert metric.evaluate(context, '{"allowed_tools":["other"]}').value is False
    assert (
        metric.evaluate(replace(context, calls=()), '{"allowed_tools":["lookup"]}').value is False
    )
    assert (
        metric.evaluate(
            replace(context, calls=()), '{"allowed_tools":["lookup"],"allow_empty":true}'
        ).value
        is True
    )
    assert (
        metric.evaluate(
            replace(context, trace_complete=False), '{"allowed_tools":["lookup"]}'
        ).value
        is None
    )


def test_argument_equivalences_are_explicit(context):
    good = '{"allowed_argv":{"lookup":[["lookup","alpha"],["lookup","--id","alpha"]]}}'
    assert evaluate(ArgumentMatch(), context, good).value is True
    assert (
        evaluate(ArgumentMatch(), context, '{"allowed_argv":{"lookup":[["lookup","beta"]]}}').value
        is False
    )
    assert (
        evaluate(ArgumentMatch(), replace(context, trace_complete=False), good).validity
        == "unavailable"
    )


def test_calls_preserve_retries_and_unknowns(context):
    context = replace(
        context, calls=(*context.calls, replace(context.calls[0], invocation_id="two"))
    )
    assert evaluate(ToolCalls(), context).value == 2
    assert evaluate(ToolCalls(), replace(context, trace_complete=False)).value is None
    assert evaluate(ToolCalls(), replace(context, calls=(context.calls[0],) * 2)).value is None
    plan = MetricPlan((MetricBinding(ToolCalls(), "required", maximum=1),))
    raw, decision = plan.evaluate(context, authority(plan))
    assert raw.value == 2 and raw.id == "tool_calls.value" and decision.value is False
    assert plan.observations((raw, decision))[0].value is False


def test_facts_require_actual_answer_and_delivered_source(context):
    p = '{"answer_artifact":"answer","source_artifact":"source","expected":{"status":"ready"}}'
    assert evaluate(FactMatch(), context, p).value is True
    assert evaluate(FactMatch(), replace(context, delivered_outputs=()), p).value is None
    assert evaluate(FactMatch(), replace(context, terminal_artifact=None), p).value is None
    assert (
        evaluate(FactMatch(), context, p.replace('"ready"', '"wrong"')).failure_reason
        == "reference_source_conflict"
    )


def test_timing_requires_valid_interval(context):
    assert evaluate(Latency(), context, '{"artifact":"timing"}').value == 25
    assert evaluate(Latency(), context, '{"artifact":"absent"}').value is None
    assert evaluate(Latency(), context, '{"artifact":"source"}').value is None


@pytest.mark.parametrize("mode", ["raise", "foreign_reference", "wrong_type", "wrong_id"])
@pytest.mark.parametrize("role", ["required", "diagnostic"])
def test_custom_metric_errors_never_pass_or_change_other_results(context, mode, role):
    class Broken:
        definition = MetricDefinition(metric_id="custom", metric_version="1", value_type="boolean")

        def validate_parameters(self, parameters_json):
            pass

        def evaluate(self, context, parameters_json):
            if mode == "raise":
                raise RuntimeError("private failure text")
            record = ResultRecord(
                id="custom",
                version="agent.evaluator.result-record/v1",
                role="diagnostic",
                value=True,
                value_type="boolean",
                validity="valid",
                failure_reason=None,
                evidence_refs=(context.receipt,),
                unit=None,
                direction=None,
            )
            if mode == "foreign_reference":
                return record.model_copy(
                    update={
                        "evidence_refs": (
                            context.receipt.model_copy(update={"evidence_id": "other"}),
                        )
                    }
                )
            if mode == "wrong_type":
                return record.model_copy(update={"value": 3})
            return record.model_copy(update={"id": "tool_selection"})

    result = evaluate(Broken(), context, role=role)
    assert result.validity == "invalid" and result.value is None
    assert result.failure_reason == "metric_execution_or_contract_error"


def test_not_applicable_required_record_preserves_applicability(context):
    class Inapplicable(ToolSelection):
        def evaluate(self, context, parameters_json):
            return (
                super()
                .evaluate(context, parameters_json)
                .model_copy(
                    update={
                        "value": None,
                        "validity": "not_applicable",
                        "failure_reason": "not_applicable",
                    }
                )
            )

    plan = MetricPlan((MetricBinding(Inapplicable(), "required", '{"allowed_tools":["lookup"]}'),))
    records = plan.evaluate(context, authority(plan))
    assert records[0].value is None
    assert plan.observations(records)[0].applicability == "not_applicable"
