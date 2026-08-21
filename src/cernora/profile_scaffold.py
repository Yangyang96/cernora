"""Deterministic content builders for the guided Profile scaffold.

This module owns every file the ``profile init`` command publishes. It is pure
content generation: building the scaffold never touches the filesystem, so the
publication path in :mod:`cernora.profile_workspace` keeps its atomic, conflict-safe
guarantees without knowing what the scaffold contains.
"""

from __future__ import annotations

import hashlib
from typing import Any

from cernora.core.canonical import canonical_json
from cernora.core.case import CaseProfile
from cernora.core.evidence_bundle_v2 import EvidenceBundleV2

_SCHEMA_VERSION = "agent.evaluator.case-profile/v1"
_PROJECTION_VERSION = "scaffold-projection/v1"
_EXPECTED_VALUE_PATH = "resources/expected-value.json"
_FIXTURE_ID = "expected-value"
_TOOL = "check_value"
_TOOL_ARGV = ("check_value", "--key", "alpha")
_EXPECTED_VALUE: dict[str, str] = {"key": "alpha", "value": "confirmed"}
_PRODUCER_ID = "cernora.synthetic.local-scaffold"
_PRODUCER_VERSION = "1.0.0"

_VARIANTS = (
    "pass",
    "fail",
    "inconclusive",
    "corrupt-artifact",
    "authority-mismatch",
    "scorer-policy-mismatch",
    "gate-policy-mismatch",
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def expected_value_bytes() -> bytes:
    """Return the frozen expected stdout the scaffold Case compares against."""

    return canonical_json(_EXPECTED_VALUE)


def _authority_payload(
    name: str,
    profile_version: str = "1.0.0",
    *,
    scorer_policy_version: str = "1.0.0",
    gate_policy_version: str = "1.0.0",
) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "profile_id": name,
        "profile_version": profile_version,
        "description": "Local Cernora Profile scaffold.",
        "cases": [
            {
                "case_id": "check-v1",
                "case_version": "1.0.0",
                "case_set": "local-authoring",
                "input": {
                    "prompt": (
                        "Run exactly `check_value --key alpha`, preserve its response, and "
                        "return the key/value claim with the response SHA-256."
                    ),
                    "parameters": {},
                },
                "declared_capabilities": ["completed-evidence"],
                "fixture_references": [
                    {
                        "fixture_id": _FIXTURE_ID,
                        "path": _EXPECTED_VALUE_PATH,
                        "sha256": _sha256(expected_value_bytes()),
                    }
                ],
                "tags": ["local"],
            }
        ],
        "scorer_policy": {
            "policy_version": scorer_policy_version,
            "required_observations": ["claim_grounded"],
        },
        "gate_policy": {
            "policy_version": gate_policy_version,
            "required_score_ids": ["check-score"],
            "invalid_result": "inconclusive",
        },
    }


def scaffold_authority(name: str) -> CaseProfile:
    """Return the strict CaseProfile authority for a scaffold named ``name``."""

    return CaseProfile.model_validate_json(canonical_json(_authority_payload(name)))


def _artifact(
    artifact_id: str,
    path: str,
    payload: bytes,
    media_type: str,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "path": path,
        "sha256": _sha256(payload),
        "size_bytes": len(payload),
        "media_type": media_type,
    }


def _single_action(
    stdout: bytes,
    stdout_artifact: dict[str, Any],
    stderr_artifact: dict[str, Any],
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "sequence": 0,
        "invocation_id": "action-0",
        "tool": _TOOL,
        "argv": _TOOL_ARGV,
        "result": {
            "status": "completed",
            "exit_code": 0,
            "committed": True,
            "delivered": True,
            "stdout_artifact": {
                "artifact_id": stdout_artifact["artifact_id"],
                "sha256": stdout_artifact["sha256"],
            },
            "stderr_artifact": {
                "artifact_id": stderr_artifact["artifact_id"],
                "sha256": stderr_artifact["sha256"],
            },
        },
        "previous_receipt_sha256": None,
    }
    receipt["receipt_sha256"] = _sha256(canonical_json(receipt))
    return receipt


def _completed_terminal(
    stdout: bytes,
    *,
    claim_value: str,
) -> tuple[dict[str, Any], dict[str, Any], tuple[tuple[str, bytes], ...]]:
    answer_value = {
        "claim": {"key": "alpha", "value": claim_value},
        "evidence_sha256": _sha256(stdout),
    }
    answer = canonical_json(answer_value)
    declaration = _artifact("terminal-answer", "terminal/answer.json", answer, "application/json")
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
    infrastructure = {"status": "valid", "failure": None}
    return terminal, infrastructure, ((declaration["path"], answer),)


def _inconclusive_terminal() -> tuple[dict[str, Any], dict[str, Any]]:
    terminal = {
        "status": "inconclusive",
        "answer": None,
        "failure": {
            "domain": "evidence",
            "code": "missing_runtime_evidence",
            "message": "The synthetic run did not record the required completed evidence.",
        },
    }
    infrastructure = {"status": "valid", "failure": None}
    return terminal, infrastructure


def _build_bundle(
    name: str,
    *,
    variant: str,
) -> tuple[EvidenceBundleV2, dict[str, bytes]]:
    authority_payload = _authority_payload(name)
    if variant == "authority-mismatch":
        authority_payload = _authority_payload(name, profile_version="2.0.0")
    elif variant == "scorer-policy-mismatch":
        authority_payload = _authority_payload(name, scorer_policy_version="2.0.0")
    elif variant == "gate-policy-mismatch":
        authority_payload = _authority_payload(name, gate_policy_version="2.0.0")
    authority = CaseProfile.model_validate_json(canonical_json(authority_payload))
    case = authority.cases[0]
    stdout = expected_value_bytes()
    stderr = b""
    files: dict[str, bytes] = {}
    actions: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []

    if variant == "inconclusive":
        terminal, infrastructure = _inconclusive_terminal()
        terminal_files: tuple[tuple[str, bytes], ...] = ()
    else:
        stdout_artifact = _artifact(
            "action-0-stdout", "actions/00-stdout.json", stdout, "application/json"
        )
        stderr_artifact = _artifact(
            "action-0-stderr", "actions/00-stderr.txt", stderr, "text/plain; charset=utf-8"
        )
        artifacts.extend((stdout_artifact, stderr_artifact))
        files[stdout_artifact["path"]] = stdout
        files[stderr_artifact["path"]] = stderr
        actions.append(_single_action(stdout, stdout_artifact, stderr_artifact))
        claim_value = (
            "confirmed"
            if variant
            in {
                "pass",
                "corrupt-artifact",
                "authority-mismatch",
                "scorer-policy-mismatch",
                "gate-policy-mismatch",
            }
            else "wrong"
        )
        terminal, infrastructure, terminal_files = _completed_terminal(
            stdout, claim_value=claim_value
        )

    for path, payload in terminal_files:
        artifacts.append(_artifact("terminal-answer", path, payload, "application/json"))
        files[path] = payload

    bundle_payload: dict[str, Any] = {
        "schema_version": "agent.evaluator.evidence-bundle/v2",
        "bundle_id": f"{name}-{variant}",
        "producer": {
            "producer_id": _PRODUCER_ID,
            "producer_version": _PRODUCER_VERSION,
        },
        "run": {"run_id": f"run-{variant}", "attempt_id": "attempt-1"},
        "profile": {
            "profile_id": authority.profile_id,
            "profile_version": authority.profile_version,
            "sha256": _sha256(canonical_json(authority)),
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


def fixture_files(name: str, variant: str) -> dict[str, bytes]:
    """Return one fixture package keyed by path relative to ``fixtures/<variant>/``."""

    if variant not in _VARIANTS:
        raise ValueError(f"unknown scaffold fixture variant: {variant}")
    bundle, files = _build_bundle(name, variant=variant)
    if variant == "corrupt-artifact":
        first_path = next(iter(sorted(files)))
        files[first_path] = b"corrupt"
    return {"bundle.json": canonical_json(bundle), **files}


def _test_case(case_id: str, fixture: str, expected: str) -> bytes:
    payload = {
        "schema_version": "agent.evaluator.profile-test-case/v1",
        "case_id": case_id,
        "fixture": fixture,
        "expected": expected,
    }
    return canonical_json(payload)


def build_scaffold_files(name: str) -> dict[str, bytes]:
    """Return every scaffold file keyed by POSIX path relative to the Profile root."""

    files: dict[str, bytes] = {
        "profile.py": profile_source(name),
        "profile.json": canonical_json(scaffold_authority(name)),
        "resources/expected-value.json": expected_value_bytes(),
        "cases/pass.json": _test_case("check-v1", "pass", "pass"),
        "cases/fail.json": _test_case("check-v1", "fail", "fail"),
        "cases/inconclusive.json": _test_case("check-v1", "inconclusive", "inconclusive"),
        "cases/corrupt-artifact.json": _test_case(
            "check-v1", "corrupt-artifact", "import_rejection"
        ),
        "cases/authority-mismatch.json": _test_case(
            "check-v1", "authority-mismatch", "import_rejection"
        ),
        "cases/scorer-policy-mismatch.json": _test_case(
            "check-v1", "scorer-policy-mismatch", "import_rejection"
        ),
        "cases/gate-policy-mismatch.json": _test_case(
            "check-v1", "gate-policy-mismatch", "import_rejection"
        ),
        "tests/test_profile.py": test_source(name),
        "README.md": readme_source(name),
    }
    for variant in _VARIANTS:
        for path, payload in fixture_files(name, variant).items():
            files[f"fixtures/{variant}/{path}"] = payload
    return files


def profile_source(name: str) -> bytes:
    """Return the annotated, fail-closed ``profile.py`` scaffold source."""

    return f'''"""Cernora Profile scaffold. Local Profile code is trusted, not sandboxed.

Run exactly `create_profile()` when Cernora loads this directory. The returned object
must implement the Preview `Profile` protocol:

- `authority` returns the strict CaseProfile in profile.json;
- `projection_version` names the observation projection this Profile emits;
- `validate_import()` rejects evidence that is not bound to this authority;
- `assess()` turns one bound import package into a ProfileAssessment.

This template loads and passes static conformance, but `assess()` deliberately fails
closed. It can never pass evidence before you implement assessment.
"""

import hashlib
from pathlib import Path

from cernora import (
    AuthorityBoundImportPackageV2,
    CaseProfile,
    Profile,
    ProfileAssessment,
    ProfileEvaluationContext,
)

_PROJECTION_VERSION = "{_PROJECTION_VERSION}"
_EXPECTED_VALUE_PATH = "{_EXPECTED_VALUE_PATH}"


class ScaffoldProfile:
    """Fail-closed scaffold; implement assess before evaluating completed evidence."""

    def __init__(self) -> None:
        directory = Path(__file__).resolve().parent
        self._authority = CaseProfile.model_validate_json(
            (directory / "profile.json").read_bytes()
        )
        expected_bytes = (directory / _EXPECTED_VALUE_PATH).read_bytes()
        fixture = self._authority.cases[0].fixture_references[0]
        if fixture.path != _EXPECTED_VALUE_PATH:
            raise ValueError("scaffold fixture path does not match Profile authority")
        if fixture.sha256 != hashlib.sha256(expected_bytes).hexdigest():
            raise ValueError("scaffold fixture digest does not match Profile authority")
        self._expected_bytes = expected_bytes

    @property
    def authority(self) -> CaseProfile:
        return self._authority

    @property
    def projection_version(self) -> str:
        return _PROJECTION_VERSION

    def validate_import(self, package: AuthorityBoundImportPackageV2) -> None:
        if package.profile != self._authority:
            raise ValueError("import package is not bound to this Profile authority")
        if package.case != self._authority.cases[0]:
            raise ValueError("import package is not bound to the scaffold Case")
        bundle = package.content.bundle
        if (
            bundle.profile.profile_id,
            bundle.profile.profile_version,
        ) != (
            self._authority.profile_id,
            self._authority.profile_version,
        ):
            raise ValueError("bundle Profile identity does not match")
        if (
            bundle.case.case_id,
            bundle.case.case_version,
            bundle.case.case_set,
        ) != (
            package.case.case_id,
            package.case.case_version,
            package.case.case_set,
        ):
            raise ValueError("bundle Case identity does not match")
        actual_fixtures = tuple(item.model_dump(mode="json") for item in bundle.fixtures)
        expected_fixtures = tuple(
            item.model_dump(mode="json") for item in package.case.fixture_references
        )
        if actual_fixtures != expected_fixtures:
            raise ValueError("bundle Fixture identities do not match")
        # Add Profile-specific structural checks here: exact command, argument shape,
        # stdout member set and terminal answer shape.

    def assess(
        self,
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
    ) -> ProfileAssessment:
        del package, context
        # Implement one deterministic observation here. The scaffold Case declares a
        # single required observation `claim_grounded`:
        #
        #   claim_grounded is true exactly when:
        #     - the run recorded exactly one `check_value --key alpha` action;
        #     - its stdout equals resources/expected-value.json;
        #     - the terminal claim equals {{"key": "alpha", "value": "confirmed"}};
        #     - the claim's evidence_sha256 equals the stdout SHA-256.
        #
        # Emit `applicability="invalid"` (not False) when the terminal status is not
        # `completed`, so missing evidence stays inconclusive rather than behavioral
        # failure. Return a ProfileAssessment carrying Evidence v1, Score v1 and the
        # exact required_observations from the scorer policy.
        raise NotImplementedError("implement Profile.assess before evaluation")


def create_profile() -> Profile:
    """Fixed Cernora local Profile factory."""

    return ScaffoldProfile()
'''.encode()


def test_source(name: str) -> bytes:
    """Return the local pytest file that proves the fail-closed default."""

    return f'''"""Local behavior tests for the {name} scaffold.

Run with `pytest` from the Profile directory, or exercise the same flow through
`cernora profile test --profile-path .`. The fail-closed default must load and pass
static conformance while never silently passing completed evidence during evaluation.
"""

from pathlib import Path

from cernora import check_profile_conformance, load_local_profile
from cernora.profile_testing import run_profile_tests

_DIRECTORY = Path(__file__).resolve().parent.parent


def test_scaffold_loads_and_passes_static_conformance() -> None:
    profile = load_local_profile(_DIRECTORY)
    conformance = check_profile_conformance(profile)
    assert conformance.profile_id == "{name}"
    assert conformance.case_ids == ("check-v1",)


def test_fail_closed_default_never_passes(tmp_path: Path) -> None:
    profile = load_local_profile(_DIRECTORY)
    summary = run_profile_tests(profile, _DIRECTORY, tmp_path, repetitions=1)
    assert summary.ok is False
    by_fixture = {{row.fixture: row for row in summary.cases}}
    # Missing evidence stays inconclusive before assess() is implemented.
    assert by_fixture["inconclusive"].status == "pass"
    assert by_fixture["inconclusive"].actual == "inconclusive"
    # Completed evidence cannot be decided until assess() is implemented.
    assert by_fixture["pass"].status == "error"
    assert by_fixture["fail"].status == "error"
'''.encode()


def readme_source(name: str) -> bytes:
    """Return the scaffold README documenting authority roles and version bumps."""

    return f"""# {name}

A private Cernora Profile scaffold. Local Profile Python is trusted code, never a
sandbox: review `profile.py` before loading or evaluating anything.

## Files

- `profile.json` — strict CaseProfile v1 authority: Profile/Case identity, fixture
  references and digests, scorer policy and gate policy.
- `profile.py` — the fixed `create_profile()` factory. `assess()` fails closed until you
  implement it.
- `resources/expected-value.json` — the frozen expected stdout the Case compares against.
- `cases/*.json` — one ProfileTestCase per file, consumed by `cernora profile test`.
- `fixtures/*/` — synthetic EvidenceBundle v2 packages (bundle.json plus artifacts).
  The negative rows cover missing evidence, artifact corruption and stale Profile,
  scorer-policy and gate-policy authority.
- `tests/test_profile.py` — local pytest for load, conformance and the fail-closed default.

## Authority changes require a version bump

A change to the Profile identity, Case identity, fixture bytes, scorer policy or gate
policy is an authority change. Evidence produced under the previous authority must fail
closed, so update `profile_version` in `profile.json` and regenerate the fixtures under
`fixtures/`. Do not silently reuse stale fixtures.

## Workflow

```sh
cernora profile validate --profile-path .
cernora profile test --profile-path .
```

`profile test` runs static conformance plus real import, evaluation and strict reload for
every `cases/*.json` entry and requires byte-identical repeated results.
""".encode()


__all__ = [
    "build_scaffold_files",
    "expected_value_bytes",
    "fixture_files",
    "profile_source",
    "readme_source",
    "scaffold_authority",
    "test_source",
]
