"""Build frozen coding-evaluation bundles without executing candidate code."""

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
from cernora.core.case import CaseProfile
from cernora.core.evidence_bundle_v2 import EvidenceBundleV2

FixtureConclusion = Literal["pass", "fail", "inconclusive", "import_rejection"]

_MATRIX_RESOURCE = "resources/scenarios.json"
_MATRIX_VERSION = "cernora.coding-evaluation-fixture-matrix/v1"
_TREE_VERSION = "cernora.candidate-tree/v1"
_TREE_DOMAIN = "cernora.candidate-tree-manifest/v1"
_CAPSULE_VERSION = "cernora.synthetic-execution-capsule/v1"
_TERMINAL_VERSION = "cernora.coding-terminal-binding/v1"
_ADVERSARIAL_VARIANTS = (
    "reject_noncanonical_path",
    "reject_normalization_collision",
    "reject_case_collision",
    "reject_prefix_collision",
    "reject_wrong_baseline_binding",
    "reject_wrong_test_plan_binding",
    "reject_wrong_harness_binding",
)


@dataclass(frozen=True)
class FixtureExpectation:
    """One frozen coding-evaluation acceptance row."""

    fixture_id: str
    variant: str
    expected: FixtureConclusion


_EXPECTED_MATRIX = (
    FixtureExpectation("happy-path", "happy", "pass"),
    FixtureExpectation("allowed-change", "allowed_change", "pass"),
    FixtureExpectation("build-failure", "build_failure", "fail"),
    FixtureExpectation("unresolved-f2p", "unresolved_f2p", "fail"),
    FixtureExpectation("regression-failure", "regression_failure", "fail"),
    FixtureExpectation("forbidden-file-change", "forbidden_file_change", "fail"),
    FixtureExpectation("protected-test-tamper", "protected_test_tamper", "fail"),
    FixtureExpectation("terminal-binding-mismatch", "terminal_binding_mismatch", "fail"),
    FixtureExpectation("candidate-self-mutation", "candidate_self_mutation", "fail"),
    FixtureExpectation("retry-policy-violation", "retry_policy_violation", "fail"),
    FixtureExpectation("missing-execution-evidence", "missing_execution_evidence", "inconclusive"),
    FixtureExpectation(
        "untrusted-execution-authority", "untrusted_execution_authority", "inconclusive"
    ),
    FixtureExpectation("wrong-capsule-binding", "wrong_capsule_binding", "inconclusive"),
    FixtureExpectation("partial-test-results", "partial_test_results", "inconclusive"),
    FixtureExpectation("duplicate-test-result", "duplicate_test_result", "inconclusive"),
    FixtureExpectation("skipped-test", "skipped_test", "inconclusive"),
    FixtureExpectation("xfailed-test", "xfailed_test", "inconclusive"),
    FixtureExpectation("infrastructure-unavailable", "infrastructure_unavailable", "inconclusive"),
    FixtureExpectation("conflicting-attempts", "conflicting_attempts", "inconclusive"),
    FixtureExpectation("corrupt-candidate-tree", "corrupt_candidate_tree", "import_rejection"),
)


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

    value = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs)
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def fixture_matrix() -> tuple[FixtureExpectation, ...]:
    """Return the strictly frozen 20-row coding-evaluation matrix."""

    payload = resources.files(__package__).joinpath(_MATRIX_RESOURCE).read_bytes()
    value = _strict_object(payload, label="coding fixture matrix")
    if set(value) != {"schema_version", "fixtures"} or value["schema_version"] != (_MATRIX_VERSION):
        raise ValueError("coding fixture matrix has an invalid member set or version")
    rows = value["fixtures"]
    if type(rows) is not list:
        raise ValueError("coding fixture matrix fixtures must be a list")
    result: list[FixtureExpectation] = []
    for row in rows:
        if type(row) is not dict or set(row) != {"id", "variant", "expected"}:
            raise ValueError("coding fixture row has an invalid member set")
        if row["expected"] not in {"pass", "fail", "inconclusive", "import_rejection"}:
            raise ValueError("coding fixture row has an invalid conclusion")
        result.append(FixtureExpectation(row["id"], row["variant"], row["expected"]))
    if tuple(result) != _EXPECTED_MATRIX:
        raise ValueError("coding fixture matrix is not the frozen coding-evaluation set")
    return tuple(result)


def _profile_and_spec() -> tuple[CaseProfile, dict[str, Any]]:
    package = resources.files("cernora.profiles.coding_evaluation")
    profile = CaseProfile.model_validate_json(
        package.joinpath("resources/profile.json").read_bytes()
    )
    spec = _strict_object(
        package.joinpath("resources/authority-v1.json").read_bytes(), label="coding authority"
    )
    return profile, spec


def _tree_from_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = [
        {
            "path": item["path"],
            "size_bytes": item["size_bytes"],
            "sha256": item["sha256"],
            "executable": item["executable"],
        }
        for item in entries
    ]
    return {
        "schema_version": _TREE_VERSION,
        "entries": entries,
        "tree_sha256": _sha256(canonical_json({"domain": _TREE_DOMAIN, "entries": manifest})),
    }


def _entry(path: str, content: str, *, executable: bool = False) -> dict[str, Any]:
    payload = content.encode("utf-8")
    return {
        "path": path,
        "size_bytes": len(payload),
        "sha256": _sha256(payload),
        "executable": executable,
        "content": content,
    }


def _candidate_tree(variant: str, spec: dict[str, Any]) -> dict[str, Any]:
    if variant == "reject_noncanonical_path":
        return _tree_from_entries([_entry("src/../escape.py", "pass\n")])
    if variant == "reject_normalization_collision":
        return _tree_from_entries(
            sorted(
                [_entry("src/cafe\u0301.py", "pass\n"), _entry("src/caf\u00e9.py", "pass\n")],
                key=lambda item: item["path"],
            )
        )
    if variant == "reject_case_collision":
        return _tree_from_entries(
            sorted(
                [_entry("src/Calc.py", "pass\n"), _entry("src/calc.py", "pass\n")],
                key=lambda item: item["path"],
            )
        )
    if variant == "reject_prefix_collision":
        return _tree_from_entries(
            [_entry("src/calc.py", "pass\n"), _entry("src/calc.py/helper", "pass\n")]
        )
    baseline = {item["path"]: dict(item) for item in spec["baseline_tree"]["entries"]}
    fixed = "def add(left: int, right: int) -> int:\n    return left + right\n"
    if variant not in {"unresolved_f2p"}:
        baseline["src/calc.py"] = _entry("src/calc.py", fixed)
    if variant == "allowed_change":
        baseline["README.md"] = _entry("README.md", "# Calculator\n\nFixed addition.\n")
    elif variant == "build_failure":
        baseline["src/calc.py"] = _entry(
            "src/calc.py", "def add(left: int, right: int) -> int:\n    return (\n"
        )
    elif variant == "forbidden_file_change":
        baseline["pyproject.toml"] = _entry(
            "pyproject.toml", '[project]\nname = "calculator"\nversion = "2"\n'
        )
    elif variant == "protected_test_tamper":
        baseline["tests/test_calc.py"] = _entry(
            "tests/test_calc.py", "def test_tampered() -> None:\n    assert True\n"
        )
    return _tree_from_entries([baseline[path] for path in sorted(baseline)])


def _test_results(
    spec: dict[str, Any],
    statuses: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    statuses = statuses or {}
    return [
        {
            "test_id": test["test_id"],
            "classification": test["classification"],
            "status": statuses.get(test["test_id"], "passed"),
            "output_sha256": _sha256(
                canonical_json(
                    {
                        "test_id": test["test_id"],
                        "status": statuses.get(test["test_id"], "passed"),
                    }
                )
            ),
        }
        for test in spec["test_plan"]["tests"]
    ]


def _attempt(
    number: int,
    candidate_sha: str,
    results: list[dict[str, Any]],
    *,
    build_status: str = "passed",
    exit_code: int | None = 0,
    retry_reason: str | None = None,
    post_sha: str | None = None,
) -> dict[str, Any]:
    raw = {
        "attempt": number,
        "build_status": build_status,
        "results": results,
    }
    return {
        "attempt": number,
        "retry_reason": retry_reason,
        "pre_tree_sha256": candidate_sha,
        "post_tree_sha256": post_sha or candidate_sha,
        "build": {"status": build_status, "exit_code": exit_code},
        "test_results": results,
        "raw_output_sha256": _sha256(canonical_json(raw)),
    }


def _capsule(variant: str, candidate_sha: str, spec: dict[str, Any]) -> dict[str, Any] | None:
    if variant == "missing_execution_evidence":
        return None
    statuses: dict[str, str] = {}
    build_status = "passed"
    exit_code: int | None = 0
    if variant == "build_failure":
        build_status, exit_code = "failed", 1
        statuses = {item["test_id"]: "not_run_build_failure" for item in spec["test_plan"]["tests"]}
    elif variant == "unresolved_f2p":
        statuses = {"f2p-add-negative": "failed"}
    elif variant == "regression_failure":
        statuses = {"p2p-type-contract": "failed"}
    elif variant == "partial_test_results":
        statuses = {}
    elif variant == "skipped_test":
        statuses = {"f2p-add-negative": "skipped"}
    elif variant == "xfailed_test":
        statuses = {"f2p-add-negative": "xfailed"}
    elif variant == "infrastructure_unavailable":
        build_status, exit_code = "infrastructure_unavailable", None
        statuses = {item["test_id"]: "skipped" for item in spec["test_plan"]["tests"]}
    results = _test_results(spec, statuses)
    if variant == "partial_test_results":
        results = results[:-1]
    elif variant == "duplicate_test_result":
        results = [*results, dict(results[0])]
    attempt = _attempt(
        1,
        candidate_sha,
        results,
        build_status=build_status,
        exit_code=exit_code,
        post_sha="f" * 64 if variant == "candidate_self_mutation" else None,
    )
    attempts = [attempt]
    if variant == "retry_policy_violation":
        attempts.append(
            _attempt(2, candidate_sha, _test_results(spec), retry_reason="test_failure")
        )
    elif variant == "conflicting_attempts":
        conflicting = _test_results(spec, {"f2p-add-negative": "failed"})
        attempts.append(
            _attempt(
                2,
                candidate_sha,
                conflicting,
                retry_reason="infrastructure_unavailable",
            )
        )
    value: dict[str, Any] = {
        "schema_version": _CAPSULE_VERSION,
        "authority_id": "cernora.synthetic-execution-authority/v1",
        "candidate_tree_sha256": (
            "f" * 64 if variant == "wrong_capsule_binding" else candidate_sha
        ),
        "baseline_tree_sha256": spec["baseline_tree"]["tree_sha256"],
        "test_plan_sha256": _sha256(canonical_json(spec["test_plan"])),
        "harness_sha256": _sha256(canonical_json(spec["harness"])),
        "toolchain": spec["execution"]["toolchain"],
        "platform": spec["execution"]["platform"],
        "command": spec["execution"]["command"],
        "limits": spec["execution"]["limits"],
        "attempt_policy": spec["execution"]["attempt_policy"],
        "attempts": attempts,
    }
    if variant == "untrusted_execution_authority":
        value["authority_id"] = "untrusted.synthetic-authority/v1"
    elif variant == "reject_wrong_baseline_binding":
        value["baseline_tree_sha256"] = "f" * 64
    elif variant == "reject_wrong_test_plan_binding":
        value["test_plan_sha256"] = "f" * 64
    elif variant == "reject_wrong_harness_binding":
        value["harness_sha256"] = "f" * 64
    return value


def _artifact(artifact_id: str, path: str, payload: bytes, media_type: str) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "path": path,
        "sha256": _sha256(payload),
        "size_bytes": len(payload),
        "media_type": media_type,
    }


def _action(
    sequence: int,
    invocation_id: str,
    tool: str,
    stdout: dict[str, Any],
    stderr: dict[str, Any],
    previous: str | None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "sequence": sequence,
        "invocation_id": invocation_id,
        "tool": tool,
        "argv": (tool, "--frozen-synthetic-fixture"),
        "result": {
            "status": "completed",
            "exit_code": 0,
            "committed": False,
            "delivered": True,
            "stdout_artifact": {
                "artifact_id": stdout["artifact_id"],
                "sha256": stdout["sha256"],
            },
            "stderr_artifact": {
                "artifact_id": stderr["artifact_id"],
                "sha256": stderr["sha256"],
            },
        },
        "previous_receipt_sha256": previous,
    }
    value["receipt_sha256"] = _sha256(canonical_json(value))
    return value


def _failure(variant: str) -> tuple[dict[str, Any], dict[str, Any]]:
    codes = {
        "missing_execution_evidence": "missing_execution_evidence",
        "untrusted_execution_authority": "untrusted_execution_authority",
        "wrong_capsule_binding": "wrong_capsule_binding",
        "partial_test_results": "partial_test_results",
        "duplicate_test_result": "duplicate_test_result",
        "skipped_test": "skipped_test",
        "xfailed_test": "xfailed_test",
        "infrastructure_unavailable": "infrastructure_unavailable",
        "conflicting_attempts": "conflicting_attempts",
    }
    code = codes[variant]
    domain = "infrastructure" if variant == "infrastructure_unavailable" else "evidence"
    failure = {
        "domain": domain,
        "code": code,
        "message": "Frozen synthetic evidence cannot support an eligible coding conclusion.",
    }
    terminal: dict[str, Any] = {
        "status": "inconclusive",
        "answer": None,
        "failure": failure,
    }
    infrastructure: dict[str, Any] = (
        {"status": "inconclusive", "failure": failure}
        if domain == "infrastructure"
        else {"status": "valid", "failure": None}
    )
    return terminal, infrastructure


def _build_fixture(row_id: str, variant: str) -> tuple[EvidenceBundleV2, dict[str, bytes]]:
    profile, spec = _profile_and_spec()
    case = profile.cases[0]
    candidate = _candidate_tree(variant, spec)
    candidate_payload = canonical_json(candidate)
    capsule = _capsule(variant, candidate["tree_sha256"], spec)
    capsule_payload = canonical_json(capsule) if capsule is not None else None
    files: dict[str, bytes] = {}
    artifacts: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    candidate_decl = _artifact(
        "candidate-tree", "candidate/tree.json", candidate_payload, "application/json"
    )
    candidate_stderr = _artifact(
        "candidate-tree-stderr", "candidate/stderr.txt", b"", "text/plain; charset=utf-8"
    )
    artifacts.extend((candidate_decl, candidate_stderr))
    files[candidate_decl["path"]] = candidate_payload
    files[candidate_stderr["path"]] = b""
    candidate_action = _action(
        0,
        "capture-candidate-tree",
        "capture_candidate_tree",
        candidate_decl,
        candidate_stderr,
        None,
    )
    actions.append(candidate_action)
    previous = candidate_action["receipt_sha256"]
    if capsule_payload is not None:
        capsule_decl = _artifact(
            "execution-capsule",
            "execution/capsule.json",
            capsule_payload,
            "application/json",
        )
        capsule_stderr = _artifact(
            "execution-capsule-stderr",
            "execution/stderr.txt",
            b"",
            "text/plain; charset=utf-8",
        )
        artifacts.extend((capsule_decl, capsule_stderr))
        files[capsule_decl["path"]] = capsule_payload
        files[capsule_stderr["path"]] = b""
        actions.append(
            _action(
                1,
                "observe-execution-capsule",
                "observe_frozen_execution_capsule",
                capsule_decl,
                capsule_stderr,
                previous,
            )
        )

    inconclusive = {item.variant for item in _EXPECTED_MATRIX if item.expected == "inconclusive"}
    if variant in inconclusive:
        terminal, infrastructure = _failure(variant)
    else:
        if capsule_payload is None:
            raise ValueError("completed fixture requires a capsule")
        terminal_value = {
            "schema_version": _TERMINAL_VERSION,
            "candidate_tree_sha256": (
                "f" * 64 if variant == "terminal_binding_mismatch" else candidate["tree_sha256"]
            ),
            "capsule_sha256": _sha256(capsule_payload),
        }
        terminal_payload = canonical_json(terminal_value)
        terminal_decl = _artifact(
            "terminal-binding",
            "terminal/binding.json",
            terminal_payload,
            "application/json",
        )
        artifacts.append(terminal_decl)
        files[terminal_decl["path"]] = terminal_payload
        terminal = {
            "status": "completed",
            "answer": {
                "content": terminal_payload.decode("utf-8"),
                "sha256": terminal_decl["sha256"],
                "artifact": {
                    "artifact_id": terminal_decl["artifact_id"],
                    "sha256": terminal_decl["sha256"],
                },
            },
            "failure": None,
        }
        infrastructure = {"status": "valid", "failure": None}
    payload: dict[str, Any] = {
        "schema_version": "agent.evaluator.evidence-bundle/v2",
        "bundle_id": f"coding-evaluation-{row_id}",
        "producer": {
            "producer_id": (
                "untrusted.synthetic.coding-evaluation"
                if variant == "untrusted_execution_authority"
                else "cernora.synthetic.coding-evaluation"
            ),
            "producer_version": "1.0.0",
        },
        "run": {"run_id": f"run-{row_id}", "attempt_id": "attempt-set-1"},
        "profile": {
            "profile_id": profile.profile_id,
            "profile_version": profile.profile_version,
            "sha256": _sha256(canonical_json(profile)),
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
    payload["bundle_sha256"] = _sha256(canonical_json(payload))
    return EvidenceBundleV2.model_validate(payload), files


def oracle_rows() -> tuple[dict[str, Any], ...]:
    """Return deterministic exact-envelope rows used to generate the packaged oracle."""

    pairs = [(item.fixture_id, item.variant) for item in _EXPECTED_MATRIX]
    pairs.extend((variant.replace("_", "-"), variant) for variant in _ADVERSARIAL_VARIANTS)
    rows: list[dict[str, Any]] = []
    for row_id, variant in pairs:
        bundle, _ = _build_fixture(row_id, variant)
        artifacts = {item.artifact_id: item.sha256 for item in bundle.artifacts}
        rows.append(
            {
                "row_id": row_id,
                "bundle_id": bundle.bundle_id,
                "candidate_sha256": artifacts["candidate-tree"],
                "capsule_sha256": artifacts.get("execution-capsule"),
                "terminal_sha256": artifacts.get("terminal-binding"),
                "action_shape": (
                    "candidate_only"
                    if "execution-capsule" not in artifacts
                    else "candidate_and_capsule"
                ),
                "terminal_status": bundle.terminal.status,
                "infrastructure_status": bundle.infrastructure.status,
            }
        )
    return tuple(rows)


def _materialize(row_id: str, variant: str, output: Path, *, corrupt: bool) -> AdaptedBundle:
    if output.exists() or output.is_symlink():
        raise ValueError("fixture output must not already exist")
    bundle, files = _build_fixture(row_id, variant)
    if corrupt:
        files["candidate/tree.json"] = b"corrupt"
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


def materialize_fixture(fixture_id: str, output: Path) -> AdaptedBundle:
    """Materialize one frozen 20-row fixture; no candidate or harness is executed."""

    matches = tuple(item for item in fixture_matrix() if item.fixture_id == fixture_id)
    if len(matches) != 1:
        raise ValueError("fixture id is not an exact packaged coding fixture")
    item = matches[0]
    return _materialize(
        item.fixture_id,
        item.variant,
        output,
        corrupt=item.variant == "corrupt_candidate_tree",
    )


def materialize_adversarial_fixture(variant: str, output: Path) -> AdaptedBundle:
    """Materialize one exact Profile-owned structural rejection fixture."""

    if variant not in _ADVERSARIAL_VARIANTS:
        raise ValueError("unknown coding adversarial fixture")
    return _materialize(variant.replace("_", "-"), variant, output, corrupt=False)


__all__ = [
    "FixtureExpectation",
    "fixture_matrix",
    "materialize_adversarial_fixture",
    "materialize_fixture",
]
