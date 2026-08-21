from __future__ import annotations

import json
from pathlib import Path

import pytest

from cernora import load_local_profile
from cernora.cli.main import main
from cernora.examples.profile_authoring import IMPLEMENTED_PROFILE_SOURCE
from cernora.profile_testing import ProfileTestError, run_profile_tests
from cernora.profile_workspace import init_profile


def _init(tmp_path: Path) -> Path:
    destination = tmp_path / "profile"
    init_profile("authored", output=destination, cwd=tmp_path)
    return destination


def _nondeterministic_source() -> str:
    source = IMPLEMENTED_PROFILE_SOURCE.replace(
        "class ScaffoldProfile:",
        "_ATTEMPT = 0\n\n\n"
        "def _next_attempt() -> int:\n"
        "    global _ATTEMPT\n"
        "    _ATTEMPT += 1\n"
        "    return _ATTEMPT\n\n\n"
        "class ScaffoldProfile:",
    )
    return source.replace(
        '"terminal_status": bundle.terminal.status,',
        '"terminal_status": bundle.terminal.status,\n'
        '                "attempt": str(_next_attempt()),',
    )


def test_scaffold_contains_guided_layout(tmp_path: Path) -> None:
    destination = _init(tmp_path)
    expected = (
        "profile.py",
        "profile.json",
        "resources/expected-value.json",
        "cases/pass.json",
        "cases/fail.json",
        "cases/inconclusive.json",
        "cases/corrupt-artifact.json",
        "cases/authority-mismatch.json",
        "cases/scorer-policy-mismatch.json",
        "cases/gate-policy-mismatch.json",
        "fixtures/pass/bundle.json",
        "fixtures/fail/bundle.json",
        "fixtures/inconclusive/bundle.json",
        "fixtures/corrupt-artifact/bundle.json",
        "fixtures/authority-mismatch/bundle.json",
        "fixtures/scorer-policy-mismatch/bundle.json",
        "fixtures/gate-policy-mismatch/bundle.json",
        "tests/test_profile.py",
        "README.md",
    )
    for relative in expected:
        assert (destination / relative).is_file(), relative


def test_fail_closed_default_never_passes(tmp_path: Path) -> None:
    destination = _init(tmp_path)
    profile = load_local_profile(destination)
    summary = run_profile_tests(profile, destination, tmp_path / "out", repetitions=1)
    assert summary.ok is False
    by_fixture = {row.fixture: row for row in summary.cases}
    assert by_fixture["inconclusive"].status == "pass"
    assert by_fixture["corrupt-artifact"].status == "pass"
    assert by_fixture["authority-mismatch"].status == "pass"
    assert by_fixture["scorer-policy-mismatch"].status == "pass"
    assert by_fixture["gate-policy-mismatch"].status == "pass"
    assert by_fixture["pass"].status == "error"
    assert by_fixture["fail"].status == "error"


def test_implemented_assessment_produces_every_outcome(tmp_path: Path) -> None:
    destination = _init(tmp_path)
    (destination / "profile.py").write_text(IMPLEMENTED_PROFILE_SOURCE, encoding="utf-8")
    profile = load_local_profile(destination)
    summary = run_profile_tests(profile, destination, tmp_path / "out")
    assert summary.ok is True
    by_fixture = {row.fixture: row for row in summary.cases}
    assert by_fixture["pass"].actual == "pass"
    assert by_fixture["fail"].actual == "fail"
    assert by_fixture["inconclusive"].actual == "inconclusive"
    assert by_fixture["corrupt-artifact"].actual == "import_rejection"
    assert by_fixture["authority-mismatch"].actual == "import_rejection"
    assert by_fixture["scorer-policy-mismatch"].actual == "import_rejection"
    assert by_fixture["gate-policy-mismatch"].actual == "import_rejection"
    assert by_fixture["scorer-policy-mismatch"].detail == "authority_incompatible"
    assert by_fixture["gate-policy-mismatch"].detail == "authority_incompatible"


def test_test_runner_rejects_missing_and_duplicate_cases(tmp_path: Path) -> None:
    destination = _init(tmp_path)
    profile = load_local_profile(destination)
    (destination / "cases").mkdir(exist_ok=True)
    for name in ("pass.json", "fail.json", "inconclusive.json", "corrupt-artifact.json"):
        (destination / "cases" / name).unlink()
    for name in (
        "authority-mismatch.json",
        "scorer-policy-mismatch.json",
        "gate-policy-mismatch.json",
    ):
        (destination / "cases" / name).unlink()
    with pytest.raises(ProfileTestError, match="non-empty"):
        run_profile_tests(profile, destination, tmp_path / "out", repetitions=1)

    (destination / "cases" / "a.json").write_text(
        json.dumps(
            {
                "schema_version": "agent.evaluator.profile-test-case/v1",
                "case_id": "check-v1",
                "fixture": "pass",
                "expected": "pass",
            }
        ),
        encoding="utf-8",
    )
    (destination / "cases" / "b.json").write_text(
        json.dumps(
            {
                "schema_version": "agent.evaluator.profile-test-case/v1",
                "case_id": "check-v1",
                "fixture": "pass",
                "expected": "pass",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ProfileTestError, match="uniquely"):
        run_profile_tests(profile, destination, tmp_path / "out", repetitions=1)


def test_test_runner_binds_declared_case_to_authority_and_fixture(tmp_path: Path) -> None:
    destination = _init(tmp_path)
    row_path = destination / "cases/pass.json"
    row = json.loads(row_path.read_text(encoding="utf-8"))
    row["case_id"] = "unknown-case"
    row_path.write_text(json.dumps(row), encoding="utf-8")
    profile = load_local_profile(destination)

    with pytest.raises(ProfileTestError, match="unknown authority Case: unknown-case"):
        run_profile_tests(profile, destination, tmp_path / "out", repetitions=1)


@pytest.mark.parametrize(
    ("old", "new", "detail"),
    [
        (
            '_OBSERVATION_ID = "claim_grounded"',
            '_OBSERVATION_ID = "unexpected_observation"',
            "missing=('claim_grounded',) unexpected=('unexpected_observation',)",
        ),
        (
            'locator=f"artifacts/{stdout_path}"',
            'locator="artifact:missing"',
            "Profile Score observation 'claim_grounded' has an unbound Evidence reference",
        ),
        (
            "scorer_version=self._authority.scorer_policy.policy_version",
            'scorer_version="2.0.0"',
            "Profile Score scorer version does not match authority: expected=1.0.0 actual=2.0.0",
        ),
    ],
)
def test_profile_contract_failures_have_specific_diagnostics(
    tmp_path: Path,
    old: str,
    new: str,
    detail: str,
) -> None:
    destination = _init(tmp_path)
    assert old in IMPLEMENTED_PROFILE_SOURCE
    (destination / "profile.py").write_text(
        IMPLEMENTED_PROFILE_SOURCE.replace(old, new),
        encoding="utf-8",
    )
    profile = load_local_profile(destination)

    summary = run_profile_tests(profile, destination, tmp_path / "out", repetitions=1)
    row = next(item for item in summary.cases if item.fixture == "pass")
    assert row.status == "error"
    assert row.detail is not None
    assert detail in row.detail


def test_nondeterministic_profile_is_rejected(tmp_path: Path) -> None:
    destination = _init(tmp_path)
    (destination / "profile.py").write_text(_nondeterministic_source(), encoding="utf-8")
    profile = load_local_profile(destination)
    summary = run_profile_tests(profile, destination, tmp_path / "out", repetitions=1)
    assert summary.ok is False
    row = next(item for item in summary.cases if item.fixture == "pass")
    assert row.status != "pass"


def test_authority_change_surfaces_specific_diagnostic(tmp_path: Path) -> None:
    destination = _init(tmp_path)
    (destination / "profile.py").write_text(IMPLEMENTED_PROFILE_SOURCE, encoding="utf-8")
    authority = json.loads((destination / "profile.json").read_text(encoding="utf-8"))
    authority["profile_version"] = "2.0.0"
    (destination / "profile.json").write_text(
        json.dumps(authority, sort_keys=True),
        encoding="utf-8",
    )
    profile = load_local_profile(destination)
    summary = run_profile_tests(profile, destination, tmp_path / "out", repetitions=1)
    row = next(item for item in summary.cases if item.fixture == "pass")
    assert row.status == "mismatch"
    assert row.actual == "import_rejection"
    assert row.detail == "authority_incompatible"


def test_cli_profile_test_reports_fail_closed_exit(
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
) -> None:
    destination = _init(tmp_path)
    code = main(["profile", "test", "--profile-path", str(destination), "--repetitions", "1"])
    assert code == 4
    summary = json.loads(capfd.readouterr().out)
    assert summary["ok"] is False
    assert summary["profile_id"] == "authored"

    (destination / "profile.py").write_text(IMPLEMENTED_PROFILE_SOURCE, encoding="utf-8")
    code = main(["profile", "test", "--profile-path", str(destination), "--repetitions", "1"])
    assert code == 0
    summary = json.loads(capfd.readouterr().out)
    assert summary["ok"] is True
