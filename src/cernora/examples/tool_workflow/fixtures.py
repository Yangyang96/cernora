"""Build frozen, neutral EvidenceBundle v2 fixtures without executing tools."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from cernora.adapter import AdaptedBundle
from cernora.core.canonical import canonical_json
from cernora.core.evidence_bundle_v2 import EvidenceBundleV2
from cernora.profiles.tool_workflow import ToolWorkflowProfile

FixtureConclusion = Literal["pass", "fail", "inconclusive", "import_rejection"]

_MATRIX_RESOURCE = "resources/scenarios.json"
_MATRIX_VERSION = "cernora.tool-workflow-fixture-matrix/v1"
_VARIANTS = frozenset(
    {
        "happy",
        "safe_recovery",
        "no_tool_required",
        "wrong_tool",
        "wrong_argument",
        "invalid_order",
        "fabricated_result",
        "missing_milestone",
        "premature_termination",
        "post_completion",
        "no_progress_loop",
        "harmless_extra",
        "duplicate_side_effect",
        "forbidden_action",
        "missing_runtime",
        "contradictory_runtime",
        "infrastructure_unavailable",
        "corrupt_artifact",
    }
)


@dataclass(frozen=True)
class FixtureExpectation:
    """One frozen tool-workflow acceptance row."""

    fixture_id: str
    case_id: str
    variant: str
    expected: FixtureConclusion
    advisory: bool


_EXPECTED_MATRIX = (
    FixtureExpectation("happy-path", "create-request-v1", "happy", "pass", False),
    FixtureExpectation("safe-recovery", "create-request-v1", "safe_recovery", "pass", False),
    FixtureExpectation(
        "no-tool-required", "no-tool-required-v1", "no_tool_required", "pass", False
    ),
    FixtureExpectation("wrong-tool", "create-request-v1", "wrong_tool", "fail", False),
    FixtureExpectation("wrong-argument", "create-request-v1", "wrong_argument", "fail", False),
    FixtureExpectation(
        "invalid-dependency-order", "create-request-v1", "invalid_order", "fail", False
    ),
    FixtureExpectation(
        "fabricated-result", "create-request-v1", "fabricated_result", "fail", False
    ),
    FixtureExpectation(
        "missing-required-milestone",
        "create-request-v1",
        "missing_milestone",
        "fail",
        False,
    ),
    FixtureExpectation(
        "premature-termination",
        "create-request-v1",
        "premature_termination",
        "fail",
        False,
    ),
    FixtureExpectation(
        "post-completion-forbidden-continuation",
        "create-request-v1",
        "post_completion",
        "fail",
        False,
    ),
    FixtureExpectation("no-progress-loop", "create-request-v1", "no_progress_loop", "fail", False),
    FixtureExpectation(
        "harmless-extra-action", "create-request-v1", "harmless_extra", "pass", True
    ),
    FixtureExpectation(
        "duplicate-side-effect", "create-request-v1", "duplicate_side_effect", "fail", False
    ),
    FixtureExpectation(
        "forbidden-action-or-state", "create-request-v1", "forbidden_action", "fail", False
    ),
    FixtureExpectation(
        "missing-runtime-evidence",
        "create-request-v1",
        "missing_runtime",
        "inconclusive",
        False,
    ),
    FixtureExpectation(
        "contradictory-runtime-evidence",
        "create-request-v1",
        "contradictory_runtime",
        "inconclusive",
        False,
    ),
    FixtureExpectation(
        "infrastructure-unavailable",
        "create-request-v1",
        "infrastructure_unavailable",
        "inconclusive",
        False,
    ),
    FixtureExpectation(
        "corrupt-artifact",
        "create-request-v1",
        "corrupt_artifact",
        "import_rejection",
        False,
    ),
)


@dataclass(frozen=True)
class _Action:
    tool: str
    argv: tuple[str, ...]
    stdout: dict[str, Any]
    status: Literal["completed", "failed"] = "completed"
    exit_code: int = 0
    committed: bool = False
    delivered: bool = True


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_object(payload: bytes, *, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"{label} has duplicate member {key!r}")
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise ValueError(f"{label} has non-finite number {value}")

    try:
        decoded = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not strict UTF-8 JSON") from exc
    if type(decoded) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    return decoded


def fixture_matrix() -> tuple[FixtureExpectation, ...]:
    """Return the packaged tool-workflow matrix after strict structural validation."""

    payload = resources.files(__package__).joinpath(_MATRIX_RESOURCE).read_bytes()
    value = _strict_object(payload, label="tool workflow fixture matrix")
    if set(value) != {"schema_version", "fixtures"}:
        raise ValueError("tool workflow fixture matrix has an invalid member set")
    if value["schema_version"] != _MATRIX_VERSION or type(value["fixtures"]) is not list:
        raise ValueError("tool workflow fixture matrix has an invalid version or fixture list")
    result: list[FixtureExpectation] = []
    for raw in value["fixtures"]:
        if type(raw) is not dict or set(raw) != {
            "id",
            "case_id",
            "variant",
            "expected",
            "advisory",
        }:
            raise ValueError("tool workflow fixture row has an invalid member set")
        if not all(type(raw[key]) is str and raw[key] for key in ("id", "case_id", "variant")):
            raise ValueError("tool workflow fixture row has an invalid identity")
        if raw["variant"] not in _VARIANTS:
            raise ValueError("tool workflow fixture row has an unknown variant")
        if raw["expected"] not in {"pass", "fail", "inconclusive", "import_rejection"}:
            raise ValueError("tool workflow fixture row has an invalid conclusion")
        if type(raw["advisory"]) is not bool:
            raise ValueError("tool workflow fixture row has an invalid advisory flag")
        result.append(
            FixtureExpectation(
                fixture_id=raw["id"],
                case_id=raw["case_id"],
                variant=raw["variant"],
                expected=raw["expected"],
                advisory=raw["advisory"],
            )
        )
    if tuple(result) != _EXPECTED_MATRIX:
        raise ValueError("tool workflow fixture matrix is not the frozen tool-workflow set")
    return tuple(result)


def _resolve(*, name: str = "alpha", tool: str = "resolve_target") -> _Action:
    target_id = "target-alpha" if name == "alpha" else f"target-{name}"
    return _Action(
        tool=tool,
        argv=(tool, "--name", name),
        stdout={"kind": "target", "target_id": target_id, "latency_ms": 5},
    )


def _capability(*, target_id: str = "target-alpha") -> _Action:
    return _Action(
        tool="obtain_capability",
        argv=("obtain_capability", "--target", target_id),
        stdout={
            "kind": "capability",
            "target_id": target_id,
            "capability_id": "capability-alpha",
            "latency_ms": 7,
        },
    )


def _failed_capability() -> _Action:
    return _Action(
        tool="obtain_capability",
        argv=("obtain_capability", "--target", "target-alpha"),
        stdout={"kind": "error", "code": "temporary_unavailable", "latency_ms": 3},
        status="failed",
        exit_code=75,
        delivered=True,
    )


def _create(*, target_id: str = "target-alpha") -> _Action:
    return _Action(
        tool="create_request",
        argv=(
            "create_request",
            "--target",
            target_id,
            "--capability",
            "capability-alpha",
            "--idempotency-key",
            "request-alpha",
        ),
        stdout={
            "kind": "request",
            "target_id": target_id,
            "capability_id": "capability-alpha",
            "idempotency_key": "request-alpha",
            "request_id": "request-alpha",
            "status": "created",
            "latency_ms": 11,
        },
        committed=True,
    )


def _inspect() -> _Action:
    return _Action(
        tool="inspect_status",
        argv=("inspect_status", "--target", "target-alpha"),
        stdout={"kind": "status", "status": "ready", "latency_ms": 2},
    )


def _contradictory_status() -> _Action:
    return _Action(
        tool="inspect_status",
        argv=("inspect_status", "--request", "request-alpha"),
        stdout={
            "kind": "request_status",
            "request_id": "request-alpha",
            "status": "missing",
            "latency_ms": 2,
        },
    )


def _forbidden() -> _Action:
    return _Action(
        tool="delete_target",
        argv=("delete_target", "--target", "target-alpha"),
        stdout={"kind": "forbidden", "state": "deleted", "latency_ms": 3},
        committed=True,
    )


def _scenario_actions(variant: str) -> tuple[_Action, ...]:
    happy = (_resolve(), _capability(), _create())
    if variant in {"happy", "fabricated_result", "corrupt_artifact"}:
        return happy
    if variant == "safe_recovery":
        return (_resolve(), _failed_capability(), _capability(), _create())
    if variant == "wrong_tool":
        return (_resolve(tool="locate_target"), _capability(), _create())
    if variant == "wrong_argument":
        return (
            _resolve(name="beta"),
            _capability(target_id="target-beta"),
            _create(target_id="target-beta"),
        )
    if variant == "invalid_order":
        return (_capability(), _resolve(), _create())
    if variant == "missing_milestone":
        return (_resolve(), _create())
    if variant == "premature_termination":
        return (_resolve(),)
    if variant == "post_completion":
        return (*happy, _forbidden())
    if variant == "no_progress_loop":
        return (_resolve(), _resolve())
    if variant == "harmless_extra":
        return (_inspect(), *happy)
    if variant == "duplicate_side_effect":
        return (*happy, _create())
    if variant == "forbidden_action":
        return (_resolve(), _capability(), _forbidden(), _create())
    if variant == "contradictory_runtime":
        return (*happy, _contradictory_status())
    if variant in {
        "no_tool_required",
        "missing_runtime",
        "infrastructure_unavailable",
    }:
        return ()
    raise ValueError(f"unknown tool workflow fixture variant: {variant}")


def _artifact(artifact_id: str, path: str, payload: bytes, media_type: str) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "path": path,
        "sha256": _sha256(payload),
        "size_bytes": len(payload),
        "media_type": media_type,
    }


def _terminal(
    variant: str,
    action_payloads: tuple[bytes, ...],
    actions: tuple[_Action, ...],
) -> tuple[dict[str, Any], tuple[tuple[str, bytes], ...], dict[str, Any]]:
    if variant in {"premature_termination", "no_progress_loop"}:
        return (
            {
                "status": "agent_failed",
                "answer": None,
                "failure": {
                    "domain": "agent",
                    "code": "premature_termination",
                    "message": "The synthetic run ended before the requested state was reached.",
                },
            },
            (),
            {"status": "valid", "failure": None},
        )
    if variant in {"missing_runtime", "contradictory_runtime", "infrastructure_unavailable"}:
        domain = "infrastructure" if variant == "infrastructure_unavailable" else "evidence"
        code = {
            "missing_runtime": "missing_runtime_evidence",
            "contradictory_runtime": "contradictory_runtime_evidence",
            "infrastructure_unavailable": "infrastructure_unavailable",
        }[variant]
        failure: dict[str, Any] = {
            "domain": domain,
            "code": code,
            "message": "The synthetic runtime evidence cannot support an eligible conclusion.",
        }
        infrastructure: dict[str, Any] = (
            {"status": "inconclusive", "failure": failure}
            if variant == "infrastructure_unavailable"
            else {"status": "valid", "failure": None}
        )
        return (
            {"status": "inconclusive", "answer": None, "failure": failure},
            (),
            infrastructure,
        )

    if variant == "no_tool_required":
        answer_value = {"status": "no_action_required", "target_id": "target-alpha"}
    else:
        create_index = next(
            index for index, action in enumerate(actions) if action.tool == "create_request"
        )
        request_id = "fabricated-request" if variant == "fabricated_result" else "request-alpha"
        answer_value = {
            "request_id": request_id,
            "status": "created",
            "result_sha256": _sha256(action_payloads[create_index]),
        }
    answer = canonical_json(answer_value)
    declaration = _artifact(
        "terminal-answer",
        "terminal/answer.json",
        answer,
        "application/json",
    )
    terminal = {
        "status": "completed",
        "answer": {
            "content": answer.decode("utf-8"),
            "sha256": declaration["sha256"],
            "artifact": {
                "artifact_id": declaration["artifact_id"],
                "sha256": declaration["sha256"],
            },
        },
        "failure": None,
    }
    return terminal, ((declaration["path"], answer),), {"status": "valid", "failure": None}


def _build_fixture(expectation: FixtureExpectation) -> tuple[EvidenceBundleV2, dict[str, bytes]]:
    profile = ToolWorkflowProfile()
    case = next(item for item in profile.authority.cases if item.case_id == expectation.case_id)
    scenario_actions = _scenario_actions(expectation.variant)
    artifacts: list[dict[str, Any]] = []
    action_payloads: list[bytes] = []
    files: dict[str, bytes] = {}
    actions: list[dict[str, Any]] = []
    previous_receipt: str | None = None
    for index, action in enumerate(scenario_actions):
        stdout = canonical_json(action.stdout)
        stderr = b""
        action_payloads.append(stdout)
        stdout_path = f"actions/{index:02d}-stdout.json"
        stderr_path = f"actions/{index:02d}-stderr.txt"
        stdout_artifact = _artifact(
            f"action-{index}-stdout", stdout_path, stdout, "application/json"
        )
        stderr_artifact = _artifact(
            f"action-{index}-stderr", stderr_path, stderr, "text/plain; charset=utf-8"
        )
        artifacts.extend((stdout_artifact, stderr_artifact))
        files[stdout_path] = stdout
        files[stderr_path] = stderr
        receipt: dict[str, Any] = {
            "sequence": index,
            "invocation_id": f"action-{index}",
            "tool": action.tool,
            "argv": action.argv,
            "result": {
                "status": action.status,
                "exit_code": action.exit_code,
                "committed": action.committed,
                "delivered": action.delivered,
                "stdout_artifact": {
                    "artifact_id": stdout_artifact["artifact_id"],
                    "sha256": stdout_artifact["sha256"],
                },
                "stderr_artifact": {
                    "artifact_id": stderr_artifact["artifact_id"],
                    "sha256": stderr_artifact["sha256"],
                },
            },
            "previous_receipt_sha256": previous_receipt,
        }
        receipt["receipt_sha256"] = _sha256(canonical_json(receipt))
        previous_receipt = receipt["receipt_sha256"]
        actions.append(receipt)

    terminal, terminal_files, infrastructure = _terminal(
        expectation.variant,
        tuple(action_payloads),
        scenario_actions,
    )
    for path, payload in terminal_files:
        artifacts.append(_artifact("terminal-answer", path, payload, "application/json"))
        files[path] = payload
    bundle_payload: dict[str, Any] = {
        "schema_version": "agent.evaluator.evidence-bundle/v2",
        "bundle_id": f"tool-workflow-{expectation.fixture_id}",
        "producer": {
            "producer_id": "cernora.synthetic.tool-workflow",
            "producer_version": "1.0.0",
        },
        "run": {"run_id": f"run-{expectation.fixture_id}", "attempt_id": "attempt-1"},
        "profile": {
            "profile_id": profile.authority.profile_id,
            "profile_version": profile.authority.profile_version,
            "sha256": _sha256(canonical_json(profile.authority)),
        },
        "case": {
            "case_id": case.case_id,
            "case_version": case.case_version,
            "case_set": case.case_set,
            "sha256": _sha256(canonical_json(case)),
        },
        "fixtures": tuple(item.model_dump(mode="json") for item in case.fixture_references),
        "tool_actions": tuple(actions),
        "artifacts": tuple(artifacts),
        "terminal": terminal,
        "infrastructure": infrastructure,
    }
    bundle_payload["bundle_sha256"] = _sha256(canonical_json(bundle_payload))
    return EvidenceBundleV2.model_validate(bundle_payload), files


def materialize_fixture(fixture_id: str, output: Path) -> AdaptedBundle:
    """Materialize one frozen synthetic bundle; no Agent or tool is executed."""

    matches = tuple(item for item in fixture_matrix() if item.fixture_id == fixture_id)
    if len(matches) != 1:
        raise ValueError("fixture id is not an exact packaged tool workflow fixture")
    if output.exists() or output.is_symlink():
        raise ValueError("fixture output must not already exist")
    bundle, files = _build_fixture(matches[0])
    if matches[0].variant == "corrupt_artifact":
        first_path = next(iter(sorted(files)))
        files[first_path] = b"corrupt"
    output.mkdir(parents=True)
    try:
        for relative, payload in sorted(files.items()):
            destination = output.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        (output / "bundle.json").write_bytes(canonical_json(bundle))
    except OSError:
        shutil.rmtree(output, ignore_errors=True)
        raise
    return AdaptedBundle(bundle_path=output / "bundle.json")


__all__ = ["FixtureExpectation", "fixture_matrix", "materialize_fixture"]
