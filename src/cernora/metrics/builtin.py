"""Small deterministic catalogue. Domain extraction and references remain Profile-owned."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field, JsonValue, model_validator

from cernora.core.case import StrictModel
from cernora.core.evidence import EvidenceReference
from cernora.core.result import ResultRecord
from cernora.metrics.plan import MetricContext, MetricDefinition, strict_json


class SelectionParameters(StrictModel):
    allowed_tools: tuple[str, ...] = Field(min_length=1)
    allow_empty: bool = False


class ArgumentParameters(StrictModel):
    # Alternatives are explicit exact argv forms, not guessed CLI equivalences.
    allowed_argv: dict[str, tuple[tuple[str, ...], ...]]
    allow_empty: bool = False

    @model_validator(mode="after")
    def nonempty(self) -> ArgumentParameters:
        if not self.allowed_argv or any(
            not k or not v or any(not a for a in v) for k, v in self.allowed_argv.items()
        ):
            raise ValueError("argument rules cannot be empty")
        return self


class FactParameters(StrictModel):
    answer_artifact: str = Field(min_length=1)
    source_artifact: str = Field(min_length=1)
    answer_pointer: str = ""
    source_pointer: str = ""
    expected: dict[str, JsonValue]
    allow_extra: bool = False

    @model_validator(mode="after")
    def nonempty(self) -> FactParameters:
        if not self.expected:
            raise ValueError("facts cannot be empty")
        for pointer in (self.answer_pointer, self.source_pointer):
            if pointer and not pointer.startswith("/"):
                raise ValueError("invalid JSON pointer")
        return self


class EmptyParameters(StrictModel):
    pass


class TimingParameters(StrictModel):
    artifact: str = Field(min_length=1)
    scope: Literal["agent_wall"] = "agent_wall"


class Timing(StrictModel):
    clock_id: str = Field(min_length=1)
    scope: Literal["agent_wall"]
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)


class _Builtin:
    definition: ClassVar[MetricDefinition]
    parameters: ClassVar[type[StrictModel]]

    def validate_parameters(self, parameters_json: str) -> None:
        strict_json(parameters_json)
        self.parameters.model_validate_json(parameters_json)

    def result(
        self,
        context: MetricContext,
        value: bool | int | None,
        *,
        references: tuple[EvidenceReference, ...] = (),
        reason: str | None = None,
    ) -> ResultRecord:
        return ResultRecord(
            id=self.definition.metric_id,
            version="agent.evaluator.result-record/v1",
            role="diagnostic",
            value=value,
            value_type=self.definition.value_type,
            validity="valid" if reason is None else "unavailable",
            failure_reason=reason,
            evidence_refs=references or (context.receipt,),
            unit=self.definition.unit,
            direction=self.definition.direction,
        )


class ToolSelection(_Builtin):
    definition = MetricDefinition(
        metric_id="tool_selection", metric_version="1.0.0", value_type="boolean"
    )
    parameters = SelectionParameters

    def evaluate(self, context: MetricContext, parameters_json: str) -> ResultRecord:
        p = SelectionParameters.model_validate_json(parameters_json)
        if not context.trace_complete:
            return self.result(context, None, reason="incomplete_tool_trace")
        return self.result(
            context,
            (bool(context.calls) or p.allow_empty)
            and all(c.tool in p.allowed_tools for c in context.calls),
        )


class ArgumentMatch(_Builtin):
    definition = MetricDefinition(
        metric_id="argument_match", metric_version="1.0.0", value_type="boolean"
    )
    parameters = ArgumentParameters

    def evaluate(self, context: MetricContext, parameters_json: str) -> ResultRecord:
        p = ArgumentParameters.model_validate_json(parameters_json)
        if not context.trace_complete:
            return self.result(context, None, reason="incomplete_tool_trace")
        return self.result(
            context,
            (bool(context.calls) or p.allow_empty)
            and all(
                c.tool in p.allowed_argv and c.argv in p.allowed_argv[c.tool] for c in context.calls
            ),
        )


def _pointer(value: JsonValue, pointer: str) -> JsonValue:
    if not pointer:
        return value
    for part in pointer[1:].split("/"):
        # RFC 6901: reject malformed escapes instead of treating them as literal field names.
        if "~" in part.replace("~0", "").replace("~1", ""):
            raise ValueError("invalid JSON pointer escape")
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            value = value[key]
        elif isinstance(value, list) and key.isascii() and key.isdecimal() and str(int(key)) == key:
            value = value[int(key)]
        else:
            raise ValueError("JSON pointer unavailable")
    return value


class FactMatch(_Builtin):
    definition = MetricDefinition(
        metric_id="fact_match", metric_version="1.0.0", value_type="boolean"
    )
    parameters = FactParameters

    def evaluate(self, context: MetricContext, parameters_json: str) -> ResultRecord:
        from cernora.core.canonical import canonical_json

        p = FactParameters.model_validate_json(parameters_json)
        if (
            p.answer_artifact != context.terminal_artifact
            or p.source_artifact not in context.delivered_outputs
        ):
            return self.result(context, None, reason="fact_delivery_unavailable")
        refs: tuple[EvidenceReference, ...] = ()
        try:
            answer_raw, answer_ref = context.artifact(p.answer_artifact)
            source_raw, source_ref = context.artifact(p.source_artifact)
            refs = tuple(dict.fromkeys((answer_ref, source_ref)))
            answer = _pointer(strict_json(answer_raw), p.answer_pointer)
            source = _pointer(strict_json(source_raw), p.source_pointer)
        except (ValueError, KeyError, IndexError):
            return self.result(context, None, references=refs, reason="fact_evidence_unavailable")
        if not isinstance(answer, dict) or not isinstance(source, dict):
            return self.result(context, None, references=refs, reason="fact_mapping_unavailable")
        # An independent frozen expectation must agree with the cited source before scoring.
        if any(
            k not in source or canonical_json(source[k]) != canonical_json(v)
            for k, v in p.expected.items()
        ):
            return self.result(context, None, references=refs, reason="reference_source_conflict")
        matched = all(
            k in answer and canonical_json(answer[k]) == canonical_json(v)
            for k, v in p.expected.items()
        )
        return self.result(
            context, matched and (p.allow_extra or set(answer) == set(p.expected)), references=refs
        )


class ToolCalls(_Builtin):
    definition = MetricDefinition(
        metric_id="tool_calls",
        metric_version="1.0.0",
        value_type="integer",
        unit="calls",
        direction="lower_is_better",
    )
    parameters = EmptyParameters

    def evaluate(self, context: MetricContext, parameters_json: str) -> ResultRecord:
        self.validate_parameters(parameters_json)
        if not context.trace_complete:
            return self.result(context, None, reason="incomplete_tool_trace")
        ids = [c.invocation_id for c in context.calls]
        if len(set(ids)) != len(ids):
            return self.result(context, None, reason="ambiguous_tool_identity")
        return self.result(context, len(context.calls))


class Latency(_Builtin):
    definition = MetricDefinition(
        metric_id="latency_ms",
        metric_version="1.0.0",
        value_type="integer",
        unit="milliseconds",
        direction="lower_is_better",
    )
    parameters = TimingParameters

    def evaluate(self, context: MetricContext, parameters_json: str) -> ResultRecord:
        p = TimingParameters.model_validate_json(parameters_json)
        refs: tuple[EvidenceReference, ...] = ()
        try:
            raw, ref = context.artifact(p.artifact)
            refs = (ref,)
            strict_json(raw)
            timing = Timing.model_validate_json(raw)
            if timing.scope != p.scope or timing.end_ms < timing.start_ms:
                raise ValueError("invalid timing interval")
        except ValueError:
            return self.result(context, None, references=refs, reason="timing_unavailable")
        return self.result(context, timing.end_ms - timing.start_ms, references=refs)
