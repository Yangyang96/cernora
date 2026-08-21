from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.profile_authoring_wheel_check import (
    ProfileAuthoringCheckError,
    run,
)


def test_wheel_check_authoring_loop_reaches_every_outcome(tmp_path: Path) -> None:
    output = tmp_path / "wheel-check"
    result = run(output, allow_source=True)

    assert result["repetitions"] == 3
    assert result["outcomes"] == {
        "pass": "pass",
        "fail": "fail",
        "inconclusive": "inconclusive",
        "corrupt-artifact": "import_rejection",
        "authority-mismatch": "import_rejection",
        "scorer-policy-mismatch": "import_rejection",
        "gate-policy-mismatch": "import_rejection",
    }
    assert result["execution"] == {
        "credentials_required": False,
        "network_blocked": True,
        "repository_source_import": False,
        "wheel_only": True,
    }
    assert (output / "summary.json").is_file()
    persisted = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert persisted == result


def test_wheel_check_accepts_relative_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = run(Path("wheel-check"), allow_source=True)

    assert result["repetitions"] == 3
    assert (tmp_path / "wheel-check" / "summary.json").is_file()


def test_wheel_check_rejects_source_checkout(tmp_path: Path) -> None:
    with pytest.raises(ProfileAuthoringCheckError, match="installed wheel"):
        run(tmp_path / "rejected", allow_source=False)
