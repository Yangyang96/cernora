from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

from cernora.examples.tool_workflow import run_tool_workflow


def test_packaged_tool_workflow_runs_from_resources_and_persists_report(
    tmp_path: Path,
) -> None:
    assert run_tool_workflow(tmp_path / "happy") == "pass"
    assert (tmp_path / "happy/evaluated/evaluation-report.json").is_file()
    assert run_tool_workflow(tmp_path / "behavioral", "wrong-argument") == "fail"
    assert run_tool_workflow(tmp_path / "invalid", "missing-runtime-evidence") == "inconclusive"


def test_wheel_packaged_module_entry_runs_tool_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "module-example"
    monkeypatch.setattr(sys, "argv", ["tool_workflow", str(output)])
    with pytest.raises(SystemExit, match="0"):
        runpy.run_module("cernora.examples.tool_workflow", run_name="__main__")
    assert capsys.readouterr().out == "pass\n"
