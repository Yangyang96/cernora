from __future__ import annotations

import copy
import hashlib
import json
from typing import Literal

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from cernora import PUBLIC_SCHEMAS, read_public_schema
from cernora.composition.gating import compose_gate
from cernora.core.canonical import canonical_json
from cernora.core.case import (
    Case,
    CaseInput,
    CaseProfile,
    FixtureReference,
    GatePolicy,
    ScorerPolicy,
)
from cernora.core.errors import ContractError
from cernora.core.evidence import EvidenceReference
from cernora.core.evidence_bundle_v2 import (
    bind_evidence_bundle_v2,
    canonical_evidence_bundle_v2,
    decode_evidence_bundle_v2,
    verify_artifact_payloads_v2,
)
from cernora.core.score import Score, ScoreObservation


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_value(value: object) -> str:
    return _sha_bytes(canonical_json(value))


def _profile(*, profile_version: str = "1.0.0") -> CaseProfile:
    case = Case(
        case_id="public-case-v1",
        case_version="1.0.0",
        case_set="public",
        input=CaseInput(prompt="Use the completed evidence.", parameters={}),
        declared_capabilities=("completed_evidence",),
        fixture_references=(
            FixtureReference(
                fixture_id="public-fixture-v1",
                path="fixtures/public.json",
                sha256="1" * 64,
            ),
        ),
        tags=("public",),
    )
    return CaseProfile(
        schema_version="agent.evaluator.case-profile/v1",
        profile_id="public-profile-v1",
        profile_version=profile_version,
        description="Public contract test Profile.",
        cases=(case,),
        scorer_policy=ScorerPolicy(
            policy_version="public-scorer/v1",
            required_observations=("truth",),
        ),
        gate_policy=GatePolicy(
            policy_version="public-gate/v1",
            required_score_ids=("runtime-bound",),
        ),
    )


def _bundle_payload() -> tuple[dict[str, object], dict[str, bytes]]:
    profile = _profile()
    case = profile.cases[0]
    stdout = b'{"value":"ready"}'
    stderr = b""
    answer = b'{"status":"completed"}'
    result = {
        "status": "completed",
        "exit_code": 0,
        "committed": True,
        "delivered": True,
        "stdout_artifact": {"artifact_id": "stdout", "sha256": _sha_bytes(stdout)},
        "stderr_artifact": {"artifact_id": "stderr", "sha256": _sha_bytes(stderr)},
    }
    action: dict[str, object] = {
        "sequence": 0,
        "invocation_id": "step-1",
        "tool": "lookup",
        "argv": ["lookup", "sample"],
        "result": result,
        "previous_receipt_sha256": None,
    }
    action["receipt_sha256"] = _sha_value(action)
    payload: dict[str, object] = {
        "schema_version": "agent.evaluator.evidence-bundle/v2",
        "bundle_id": "bundle-1",
        "producer": {"producer_id": "public-exporter", "producer_version": "1.0.0"},
        "run": {"run_id": "run-1", "attempt_id": "attempt-1"},
        "profile": {
            "profile_id": profile.profile_id,
            "profile_version": profile.profile_version,
            "sha256": _sha_value(profile.model_dump(mode="json", exclude_none=False)),
        },
        "case": {
            "case_id": case.case_id,
            "case_version": case.case_version,
            "case_set": case.case_set,
            "sha256": _sha_value(case.model_dump(mode="json", exclude_none=False)),
        },
        "fixtures": [
            item.model_dump(mode="json", exclude_none=False) for item in case.fixture_references
        ],
        "tool_actions": [action],
        "artifacts": [
            {
                "artifact_id": "stdout",
                "path": "streams/stdout.json",
                "sha256": _sha_bytes(stdout),
                "size_bytes": len(stdout),
                "media_type": "application/json",
            },
            {
                "artifact_id": "stderr",
                "path": "streams/stderr.txt",
                "sha256": _sha_bytes(stderr),
                "size_bytes": len(stderr),
                "media_type": "text/plain",
            },
            {
                "artifact_id": "answer",
                "path": "terminal/answer.json",
                "sha256": _sha_bytes(answer),
                "size_bytes": len(answer),
                "media_type": "application/json",
            },
        ],
        "terminal": {
            "status": "completed",
            "answer": {
                "content": answer.decode(),
                "sha256": _sha_bytes(answer),
                "artifact": {"artifact_id": "answer", "sha256": _sha_bytes(answer)},
            },
            "failure": None,
        },
        "infrastructure": {"status": "valid", "failure": None},
    }
    payload["bundle_sha256"] = _sha_value(payload)
    return payload, {"stdout": stdout, "stderr": stderr, "answer": answer}


def test_bundle_v2_round_trip_and_authority_binding_are_byte_stable() -> None:
    payload, artifacts = _bundle_payload()
    bundle = decode_evidence_bundle_v2(canonical_json(payload))

    assert canonical_evidence_bundle_v2(bundle) == canonical_json(payload)
    assert verify_artifact_payloads_v2(bundle, artifacts) is bundle
    assert bind_evidence_bundle_v2(bundle, _profile()) is bundle
    assert bundle.evaluation_boundary == ("pass", "fail")


def test_bundle_v2_rejects_unknown_duplicate_digest_and_artifact_tampering() -> None:
    payload, artifacts = _bundle_payload()

    unknown = copy.deepcopy(payload)
    unknown["producer"]["private_hint"] = True  # type: ignore[index]
    unknown.pop("bundle_sha256")
    unknown["bundle_sha256"] = _sha_value(unknown)
    with pytest.raises(ContractError):
        decode_evidence_bundle_v2(canonical_json(unknown))

    raw = canonical_json(payload).decode()
    duplicated = raw.replace(
        '"bundle_id":"bundle-1"',
        '"bundle_id":"bundle-1","bundle_id":"bundle-2"',
        1,
    )
    with pytest.raises(ContractError):
        decode_evidence_bundle_v2(duplicated)

    changed = copy.deepcopy(payload)
    changed["run"]["run_id"] = "tampered"  # type: ignore[index]
    with pytest.raises(ContractError, match="bundle SHA-256"):
        decode_evidence_bundle_v2(canonical_json(changed))

    bundle = decode_evidence_bundle_v2(canonical_json(payload))
    with pytest.raises(ContractError, match="SHA-256"):
        verify_artifact_payloads_v2(bundle, {**artifacts, "stdout": b'{"value":"other"}'})


def test_gate_fails_closed_for_false_and_invalid_required_observations() -> None:
    reference = EvidenceReference(
        evidence_id="evidence-1",
        locator="artifact:stdout",
        sha256="0" * 64,
    )

    def decision(
        value: bool,
        applicability: Literal["observed", "invalid"],
    ) -> str:
        score = Score(
            schema_version="agent.evaluator.score/v1",
            score_id="score-1",
            evidence_id="evidence-1",
            scorer_version="public-scorer/v1",
            observations=(
                ScoreObservation(
                    observation_id="truth",
                    applicability=applicability,
                    value=value if applicability == "observed" else None,
                    reason=None if applicability == "observed" else "invalid evidence",
                    evidence_references=(reference,),
                ),
            ),
        )
        return compose_gate(
            decision_id="decision-1",
            policy_version="public-gate/v1",
            required_score_ids=("score-1",),
            required_observations=("truth",),
            scores=(score,),
        ).decision

    assert decision(False, "observed") == "fail"
    assert decision(False, "invalid") == "inconclusive"


def test_public_schemas_are_packaged_valid_and_exclude_legacy_fake_producer() -> None:
    assert "evidence-bundle-v1.schema.json" not in PUBLIC_SCHEMAS
    for name in PUBLIC_SCHEMAS:
        schema = json.loads(read_public_schema(name))
        Draft202012Validator.check_schema(schema)
    assert b"evaluator_fake" not in read_public_schema("evidence-v1.schema.json")
