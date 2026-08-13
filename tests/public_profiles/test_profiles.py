from __future__ import annotations

import hashlib
import json
from importlib import resources
from types import SimpleNamespace
from typing import Any, cast

import pytest

import cernora.profiles.offline_workflow as offline_workflow_module
from cernora.core.evidence_bundle_v2 import (
    ArtifactPointer,
    BundleArtifact,
    BundleCaseIdentity,
    BundleFailure,
    BundleFixtureIdentity,
    BundleProducerIdentity,
    BundleProfileIdentity,
    BundleRunIdentity,
    BundleTerminal,
    BundleToolActionV2,
    EvidenceBundleV2,
    InfrastructureStatus,
    TerminalAnswer,
    ToolResultReceiptV2,
)
from cernora.core.identity import external_producer_identity
from cernora.ingestion.contracts_v2 import (
    AuthorityBoundImportPackageV2,
    LoadedImportPackageV2,
)
from cernora.profile import Profile, ProfileEvaluationContext
from cernora.profiles.coding_task import CodingTaskProfile
from cernora.profiles.offline_workflow import OfflineWorkflowProfile

_SHA = "0" * 64
_CONTEXT = ProfileEvaluationContext(
    evaluation_id="evaluation-1",
    evidence_id="evidence-1",
    score_id="score-1",
    source_receipt_sha256=_SHA,
)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _completed_package(
    profile: Profile,
    case_id: str,
    stdout: bytes,
    terminal_value: dict[str, Any],
    *,
    tool: str,
    argv: tuple[str, ...],
) -> AuthorityBoundImportPackageV2:
    stderr = b""
    terminal_bytes = json.dumps(
        terminal_value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    stdout_pointer = ArtifactPointer(artifact_id="stdout", sha256=_digest(stdout))
    stderr_pointer = ArtifactPointer(artifact_id="stderr", sha256=_digest(stderr))
    terminal_pointer = ArtifactPointer(artifact_id="terminal", sha256=_digest(terminal_bytes))
    result = ToolResultReceiptV2(
        status="completed",
        exit_code=0,
        committed=True,
        delivered=True,
        stdout_artifact=stdout_pointer,
        stderr_artifact=stderr_pointer,
    )
    action = BundleToolActionV2.model_construct(
        sequence=0,
        invocation_id="invocation-1",
        tool=tool,
        argv=argv,
        result=result,
        previous_receipt_sha256=None,
        receipt_sha256=_SHA,
    )
    artifacts = (
        BundleArtifact(
            artifact_id="stdout",
            path="stdout.json",
            sha256=_digest(stdout),
            size_bytes=len(stdout),
            media_type="application/json",
        ),
        BundleArtifact(
            artifact_id="stderr",
            path="stderr.txt",
            sha256=_digest(stderr),
            size_bytes=0,
            media_type="text/plain",
        ),
        BundleArtifact(
            artifact_id="terminal",
            path="terminal.json",
            sha256=_digest(terminal_bytes),
            size_bytes=len(terminal_bytes),
            media_type="application/json",
        ),
    )
    terminal = BundleTerminal(
        status="completed",
        answer=TerminalAnswer(
            content=terminal_bytes.decode(),
            sha256=_digest(terminal_bytes),
            artifact=terminal_pointer,
        ),
        failure=None,
    )
    return _package(
        profile,
        case_id,
        (action,),
        artifacts,
        terminal,
        {
            "stdout": stdout,
            "stderr": stderr,
            "terminal": terminal_bytes,
        },
    )


def _agent_failed_package(profile: Profile, case_id: str) -> AuthorityBoundImportPackageV2:
    return _package(
        profile,
        case_id,
        (),
        (),
        BundleTerminal(
            status="agent_failed",
            answer=None,
            failure=BundleFailure(domain="agent", code="agent_failed", message="failed"),
        ),
        {},
    )


def _package(
    profile: Profile,
    case_id: str,
    actions: tuple[BundleToolActionV2, ...],
    artifacts: tuple[BundleArtifact, ...],
    terminal: BundleTerminal,
    payloads: dict[str, bytes],
) -> AuthorityBoundImportPackageV2:
    case = next(item for item in profile.authority.cases if item.case_id == case_id)
    producer = BundleProducerIdentity(producer_id="test-producer", producer_version="1")
    run = BundleRunIdentity(run_id="run-1", attempt_id="attempt-1")
    profile_identity = BundleProfileIdentity(
        profile_id=profile.authority.profile_id,
        profile_version=profile.authority.profile_version,
        sha256=_SHA,
    )
    case_identity = BundleCaseIdentity(
        case_id=case.case_id,
        case_version=case.case_version,
        case_set=case.case_set,
        sha256=_SHA,
    )
    bundle = EvidenceBundleV2.model_construct(
        schema_version="agent.evaluator.evidence-bundle/v2",
        bundle_id="bundle-1",
        producer=producer,
        run=run,
        profile=profile_identity,
        case=case_identity,
        fixtures=tuple(
            BundleFixtureIdentity(**item.model_dump()) for item in case.fixture_references
        ),
        tool_actions=actions,
        artifacts=artifacts,
        terminal=terminal,
        infrastructure=InfrastructureStatus(status="valid", failure=None),
        bundle_sha256=_SHA,
    )
    content = SimpleNamespace(bundle=bundle, artifact_bytes=payloads)
    return AuthorityBoundImportPackageV2(
        content=cast(LoadedImportPackageV2, content), profile=profile.authority, case=case
    )


def _candidate(profile: CodingTaskProfile, case_id: str) -> bytes:
    expected = {
        "backend-v1": {"app.py": 'def health() -> dict[str, str]:\n    return {"status": "ok"}\n'},
        "frontend-v1": {
            "index.html": '<!doctype html>\n<title>Status</title>\n<main id="status">ready</main>\n'
        },
        "fail-closed-v1": {"policy.py": "def accept(valid: bool) -> bool:\n    return valid\n"},
    }
    assert case_id in {case.case_id for case in profile.authority.cases}
    return json.dumps(
        {"files": expected[case_id]}, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()


def test_profile_authority_is_resource_backed_and_byte_deterministic(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    first_offline = OfflineWorkflowProfile()
    first_coding = CodingTaskProfile()
    assert isinstance(first_offline, Profile)
    assert isinstance(first_coding, Profile)
    assert first_offline.authority == OfflineWorkflowProfile().authority
    assert first_coding.authority == CodingTaskProfile().authority
    assert first_offline.authority.profile_id == "cernora-offline-workflow-v1"
    assert first_coding.authority.profile_id == "cernora-coding-task-v1"
    assert {case.case_id for case in first_coding.authority.cases} == {
        "backend-v1",
        "frontend-v1",
        "fail-closed-v1",
    }


def test_profile_resource_tamper_is_rejected(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = resources.files(offline_workflow_module)
    package = tmp_path / "offline_workflow"
    resource_directory = package / "resources"
    resource_directory.mkdir(parents=True)
    (resource_directory / "profile.json").write_bytes(
        source.joinpath("resources/profile.json").read_bytes()
    )
    (resource_directory / "lookup-result.json").write_bytes(b'{"key":"alpha","value":"tampered"}\n')
    resource_api = cast(Any, offline_workflow_module).__dict__["resources"]
    monkeypatch.setattr(resource_api, "files", lambda _: package)
    with pytest.raises(ValueError, match="fixture digest"):
        OfflineWorkflowProfile()


def test_offline_workflow_pass_and_behavioral_fail() -> None:
    profile = OfflineWorkflowProfile()
    stdout = b'{"key":"alpha","value":"bravo"}\n'
    passing = _completed_package(
        profile,
        "tool-result-grounding-v1",
        stdout,
        {"claim": {"key": "alpha", "value": "bravo"}, "evidence_sha256": _digest(stdout)},
        tool="lookup",
        argv=("lookup", "--key", "alpha"),
    )
    first = profile.assess(passing, _CONTEXT)
    second = profile.assess(passing, _CONTEXT)
    assert first == second
    assert all(item.value is True for item in first.score.observations)
    assert first.score.scorer_version == profile.authority.scorer_policy.policy_version
    assert first.evidence.producer == external_producer_identity("test-producer", "1")

    failing = _completed_package(
        profile,
        "tool-result-grounding-v1",
        stdout,
        {"claim": {"key": "alpha", "value": "wrong"}, "evidence_sha256": _digest(stdout)},
        tool="lookup",
        argv=("lookup", "--key", "wrong"),
    )
    observations = profile.assess(failing, _CONTEXT).score.observations
    values = {item.observation_id: item.value for item in observations}
    assert values == {"command_exact": False, "response_integrity": True, "claim_grounded": False}


@pytest.mark.parametrize("case_id", ["backend-v1", "frontend-v1", "fail-closed-v1"])
def test_coding_profiles_pass_exact_exports(case_id: str) -> None:
    profile = CodingTaskProfile()
    candidate = _candidate(profile, case_id)
    package = _completed_package(
        profile,
        case_id,
        candidate,
        {"candidate_sha256": _digest(candidate)},
        tool="export_candidate",
        argv=("export_candidate",),
    )
    assessment = profile.assess(package, _CONTEXT)
    assert assessment == profile.assess(package, _CONTEXT)
    assert assessment.required_observations == profile.authority.scorer_policy.required_observations
    assert all(item.value is True for item in assessment.score.observations)
    assert assessment.score.scorer_version == profile.authority.scorer_policy.policy_version
    assert assessment.evidence.producer == external_producer_identity("test-producer", "1")


def test_coding_behavioral_failure_and_agent_failure_never_pass() -> None:
    profile = CodingTaskProfile()
    candidate = b'{"files":{"app.py":"wrong"}}'
    behavioral = _completed_package(
        profile,
        "backend-v1",
        candidate,
        {"candidate_sha256": _digest(candidate)},
        tool="export_candidate",
        argv=("export_candidate",),
    )
    observations = profile.assess(behavioral, _CONTEXT).score.observations
    assert not all(item.value is True for item in observations)
    failed = profile.assess(_agent_failed_package(profile, "fail-closed-v1"), _CONTEXT)
    assert all(item.value is False for item in failed.score.observations)
    assert failed.evidence.failures[0].domain == "agent"


def test_coding_invalid_candidate_format_is_rejected() -> None:
    profile = CodingTaskProfile()
    malformed = b'{"files":{"app.py":"one"},"files":{"app.py":"two"}}'
    package = _completed_package(
        profile,
        "backend-v1",
        malformed,
        {"candidate_sha256": _digest(malformed)},
        tool="export_candidate",
        argv=("export_candidate",),
    )
    with pytest.raises(ValueError, match="duplicate JSON member"):
        profile.validate_import(package)


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        ("profile_version", "Profile identity"),
        ("case_version", "Case identity"),
        ("case_set", "Case identity"),
        ("fixtures", "Fixture identities"),
    ],
)
def test_bundle_authority_tamper_is_rejected(tamper: str, message: str) -> None:
    profile = CodingTaskProfile()
    candidate = _candidate(profile, "backend-v1")
    package = _completed_package(
        profile,
        "backend-v1",
        candidate,
        {"candidate_sha256": _digest(candidate)},
        tool="export_candidate",
        argv=("export_candidate",),
    )
    bundle = package.content.bundle
    if tamper == "profile_version":
        bundle = bundle.model_copy(
            update={"profile": bundle.profile.model_copy(update={tamper: "9.9.9"})}
        )
    elif tamper in {"case_version", "case_set"}:
        bundle = bundle.model_copy(
            update={"case": bundle.case.model_copy(update={tamper: "tampered"})}
        )
    else:
        bundle = bundle.model_copy(update={"fixtures": ()})
    tampered_content = SimpleNamespace(
        bundle=bundle,
        artifact_bytes=package.content.artifact_bytes,
    )
    tampered_package = AuthorityBoundImportPackageV2(
        content=cast(LoadedImportPackageV2, tampered_content),
        profile=package.profile,
        case=package.case,
    )
    with pytest.raises(ValueError, match=message):
        profile.validate_import(tampered_package)


def test_foreign_profile_authority_is_rejected() -> None:
    profile = CodingTaskProfile()
    candidate = _candidate(profile, "backend-v1")
    package = _completed_package(
        profile,
        "backend-v1",
        candidate,
        {"candidate_sha256": _digest(candidate)},
        tool="export_candidate",
        argv=("export_candidate",),
    )
    foreign = OfflineWorkflowProfile()
    foreign_package = AuthorityBoundImportPackageV2(
        content=package.content,
        profile=foreign.authority,
        case=foreign.authority.cases[0],
    )
    with pytest.raises(ValueError, match="this Profile authority"):
        profile.validate_import(foreign_package)
