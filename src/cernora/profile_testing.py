"""Behavioral Profile test workflow: conformance, import, evaluate and strict reload.

The ``profile test`` command treats "loads successfully" and "evaluates correctly" as
different claims. It runs every declared test case through the real importer and deep
evaluator, compares the strictly reloaded outcome to the declared expectation, and
requires byte-identical repeated results.
"""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path
from typing import Literal

from cernora.conformance import check_profile_conformance
from cernora.core.canonical import decode_contract
from cernora.core.case import StrictModel
from cernora.core.errors import ContractError
from cernora.core.evidence_bundle_v2 import decode_evidence_bundle_v2
from cernora.evaluation.package import evaluate_imported_case
from cernora.ingestion.errors import IngestionError
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profile import Profile

_SUMMARY_SCHEMA_VERSION: Literal["agent.evaluator.profile-test-summary/v1"] = (
    "agent.evaluator.profile-test-summary/v1"
)


class ProfileTestError(ValueError):
    """A Profile test matrix, case, or fixture is invalid."""


class ProfileTestCase(StrictModel):
    """One declared behavior test row read from ``cases/*.json``."""

    schema_version: Literal["agent.evaluator.profile-test-case/v1"]
    case_id: str
    fixture: str
    expected: Literal["pass", "fail", "inconclusive", "import_rejection"]


class ProfileTestCaseResult(StrictModel):
    """The outcome of one declared test case."""

    case_id: str
    fixture: str
    expected: str
    status: Literal["pass", "mismatch", "nondeterministic", "error"]
    actual: str | None = None
    detail: str | None = None


class ProfileTestSummary(StrictModel):
    """Canonical summary of one ``profile test`` run."""

    schema_version: Literal["agent.evaluator.profile-test-summary/v1"]
    profile_id: str
    ok: bool
    cases: tuple[ProfileTestCaseResult, ...]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ordinary_directory(path: Path, *, label: str) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ProfileTestError(f"{label} is not an ordinary directory") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ProfileTestError(f"{label} is not an ordinary directory")


def read_profile_test_cases(cases_directory: Path) -> tuple[ProfileTestCase, ...]:
    """Decode every strict ``cases/*.json`` row in stable name order."""

    _ordinary_directory(cases_directory, label="Profile cases directory")
    rows: list[ProfileTestCase] = []
    for path in sorted(cases_directory.glob("*.json")):
        try:
            info = path.lstat()
        except OSError as exc:
            raise ProfileTestError(f"Profile test case is not an ordinary file: {path}") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ProfileTestError(f"Profile test case is not an ordinary file: {path}")
        try:
            rows.append(decode_contract(path.read_bytes(), ProfileTestCase))
        except (OSError, ValueError) as exc:
            raise ProfileTestError(f"invalid Profile test case: {path.name}") from exc
    identities = [(row.case_id, row.fixture) for row in rows]
    if not identities or len(identities) != len(set(identities)):
        raise ProfileTestError("Profile test cases must be non-empty and uniquely identified")
    return tuple(rows)


def _fixture_bundle_path(profile_directory: Path, fixture: str) -> Path:
    if not fixture or "/" in fixture or "\\" in fixture or fixture in {".", ".."}:
        raise ProfileTestError(f"invalid fixture name: {fixture!r}")
    bundle = profile_directory / "fixtures" / fixture / "bundle.json"
    try:
        info = bundle.lstat()
    except OSError as exc:
        raise ProfileTestError(f"missing fixture bundle: {fixture}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ProfileTestError(f"fixture bundle is not an ordinary file: {fixture}")
    return bundle


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _failure_detail(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code
    # Ingestion and contract errors are evaluator-generated with deterministic text;
    # they never carry private Profile exception messages.
    if isinstance(exc, IngestionError | ContractError):
        return str(exc)
    return type(exc).__name__


def _validate_case_bindings(
    profile: Profile,
    profile_directory: Path,
    cases: tuple[ProfileTestCase, ...],
) -> None:
    authority_case_ids = {case.case_id for case in profile.authority.cases}
    for case in cases:
        if case.case_id not in authority_case_ids:
            raise ProfileTestError(
                f"Profile test case references unknown authority Case: {case.case_id}"
            )
        bundle_path = _fixture_bundle_path(profile_directory, case.fixture)
        try:
            bundle = decode_evidence_bundle_v2(bundle_path.read_bytes())
        except (OSError, ContractError) as exc:
            if case.expected == "import_rejection":
                continue
            raise ProfileTestError(
                f"Profile test fixture has an invalid bundle: {case.fixture}"
            ) from exc
        if bundle.case.case_id != case.case_id:
            raise ProfileTestError(
                "Profile test fixture Case does not match its declared Case: "
                f"fixture={case.fixture} expected={case.case_id} actual={bundle.case.case_id}"
            )


def _evaluate_once(
    profile: Profile,
    bundle_path: Path,
    import_root: Path,
    evaluate_root: Path,
) -> tuple[str, str, str | None]:
    """Import, evaluate and strict reload one fixture, returning outcome and tree digest."""

    try:
        import_evidence_bundle_v2(profile=profile, bundle_path=bundle_path, output=import_root)
    except Exception as exc:  # import rejection is a legitimate, expected outcome
        return "import_rejection", "", _failure_detail(exc)
    try:
        receipt = evaluate_imported_case(
            profile=profile, import_root=import_root, output=evaluate_root
        )
    except Exception as exc:
        return "error", "", _failure_detail(exc)
    return receipt.case_outcome, _tree_digest(evaluate_root), None


def _run_case(
    profile: Profile,
    profile_directory: Path,
    output: Path,
    case: ProfileTestCase,
    repetitions: int,
) -> ProfileTestCaseResult:
    bundle_path = _fixture_bundle_path(profile_directory, case.fixture)
    outcomes: list[str] = []
    digests: list[str] = []
    detail: str | None = None
    for index in range(repetitions):
        import_root = output / case.fixture / f"rep-{index}" / "import"
        evaluate_root = output / case.fixture / f"rep-{index}" / "evaluate"
        actual, digest, failure = _evaluate_once(profile, bundle_path, import_root, evaluate_root)
        outcomes.append(actual)
        if digest:
            digests.append(digest)
        if failure is not None and detail is None:
            detail = failure

    if case.expected == "import_rejection":
        if all(outcome == "import_rejection" for outcome in outcomes):
            return ProfileTestCaseResult(
                case_id=case.case_id,
                fixture=case.fixture,
                expected=case.expected,
                status="pass",
                actual="import_rejection",
                detail=detail,
            )
        first_other = next(outcome for outcome in outcomes if outcome != "import_rejection")
        return ProfileTestCaseResult(
            case_id=case.case_id,
            fixture=case.fixture,
            expected=case.expected,
            status="mismatch",
            actual=first_other,
            detail=detail,
        )

    if any(outcome == "error" for outcome in outcomes):
        return ProfileTestCaseResult(
            case_id=case.case_id,
            fixture=case.fixture,
            expected=case.expected,
            status="error",
            actual="error",
            detail=detail,
        )
    if any(outcome == "import_rejection" for outcome in outcomes):
        return ProfileTestCaseResult(
            case_id=case.case_id,
            fixture=case.fixture,
            expected=case.expected,
            status="mismatch",
            actual="import_rejection",
            detail=detail,
        )
    if any(outcome != case.expected for outcome in outcomes):
        first_other = next(outcome for outcome in outcomes if outcome != case.expected)
        return ProfileTestCaseResult(
            case_id=case.case_id,
            fixture=case.fixture,
            expected=case.expected,
            status="mismatch",
            actual=first_other,
            detail=detail,
        )
    if len(set(digests)) != 1:
        return ProfileTestCaseResult(
            case_id=case.case_id,
            fixture=case.fixture,
            expected=case.expected,
            status="nondeterministic",
            actual=case.expected,
            detail="persisted evaluation trees differ across repetitions",
        )
    return ProfileTestCaseResult(
        case_id=case.case_id,
        fixture=case.fixture,
        expected=case.expected,
        status="pass",
        actual=case.expected,
    )


def run_profile_tests(
    profile: Profile,
    profile_directory: Path,
    output: Path,
    *,
    repetitions: int = 3,
) -> ProfileTestSummary:
    """Run static conformance plus import/evaluate/reload for every declared case.

    ``output`` is a disposable directory the command may create; it never writes into
    the Profile directory itself. A behavioral mismatch and a nondeterministic result
    are both reported as failures, never as success.
    """

    check_profile_conformance(profile)
    if repetitions < 1:
        raise ProfileTestError("repetitions must be at least 1")
    try:
        profile_root = profile_directory.resolve(strict=True)
        output_root = output.resolve(strict=False)
    except OSError as exc:
        raise ProfileTestError("cannot resolve Profile test paths") from exc
    if profile_root.is_relative_to(output_root) or output_root.is_relative_to(profile_root):
        raise ProfileTestError("Profile directory and test output must not overlap")
    cases = read_profile_test_cases(profile_directory / "cases")
    _validate_case_bindings(profile, profile_directory, cases)
    results = tuple(
        _run_case(profile, profile_directory, output, case, repetitions) for case in cases
    )
    return ProfileTestSummary(
        schema_version=_SUMMARY_SCHEMA_VERSION,
        profile_id=profile.authority.profile_id,
        ok=all(result.status == "pass" for result in results),
        cases=results,
    )


def profile_test_exit_code(summary: ProfileTestSummary) -> int:
    """Map a test summary to a stable CLI exit code distinct from load/conformance."""

    return 0 if summary.ok else 4


__all__ = [
    "ProfileTestCase",
    "ProfileTestCaseResult",
    "ProfileTestError",
    "ProfileTestSummary",
    "profile_test_exit_code",
    "read_profile_test_cases",
    "run_profile_tests",
]
