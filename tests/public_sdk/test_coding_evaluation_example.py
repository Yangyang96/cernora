from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

from cernora.examples.coding_evaluation import run_coding_evaluation


def test_packaged_coding_evaluation_runs_offline_and_persists_report(
    tmp_path: Path,
) -> None:
    assert run_coding_evaluation(tmp_path / "happy") == "pass"
    assert (tmp_path / "happy/evaluated/evaluation-report.json").is_file()
    assert run_coding_evaluation(tmp_path / "behavioral", "regression-failure") == "fail"
    assert (
        run_coding_evaluation(tmp_path / "uncertain", "missing-execution-evidence")
        == "inconclusive"
    )


def test_wheel_packaged_module_entry_runs_coding_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "module-example"
    monkeypatch.setattr(sys, "argv", ["coding_evaluation", str(output)])
    with pytest.raises(SystemExit, match="0"):
        runpy.run_module("cernora.examples.coding_evaluation", run_name="__main__")
    assert capsys.readouterr().out == "pass\n"
