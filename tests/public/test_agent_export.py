from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cernora.core.canonical import canonical_json
from cernora.core.errors import ContractError
from cernora.evaluation.agent_export import inspect_agent_run, load_agent_run_export

FIXTURES = Path(__file__).parent / "fixtures" / "agent_run"


@pytest.mark.parametrize(
    "raw", [b'{"schema_version":"wrong"}', b'{"x":1,"x":2}', b'{"value":NaN}', b"\xff", b"[]"]
)
def test_loader_fails_closed(raw: bytes) -> None:
    with pytest.raises(ContractError):
        load_agent_run_export(raw)


def test_repeat_inspection_is_byte_stable_and_read_only() -> None:
    source = FIXTURES / "success.json"
    before = source.read_bytes()
    outputs = [
        canonical_json(inspect_agent_run(source, reference={"/status": "ready"})) for _ in range(3)
    ]
    assert outputs[0] == outputs[1] == outputs[2]
    assert source.read_bytes() == before
    assert load_agent_run_export(before) == load_agent_run_export(source)
    assert json.loads(outputs[0])["claims"]["accuracy"] == 1


def test_cli_inspection_and_reference_failure(tmp_path: Path) -> None:
    cmd = [sys.executable, "-m", "cernora", "agent-run", "inspect", str(FIXTURES / "success.json")]
    before = sorted(tmp_path.iterdir())
    first = subprocess.run(
        [*cmd, "--reference", str(FIXTURES / "reference.json")], capture_output=True, check=False
    )
    second = subprocess.run(
        [*cmd, "--reference", str(FIXTURES / "reference.json")], capture_output=True, check=False
    )
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert sorted(tmp_path.iterdir()) == before
    missing = subprocess.run(cmd, capture_output=True, check=False)
    assert missing.returncode == 3
    assert json.loads(missing.stdout)["state"] == "inconclusive"
    ref = tmp_path / "wrong.json"
    ref.write_text('{"/status":"wrong"}')
    wrong = subprocess.run([*cmd, "--reference", str(ref)], capture_output=True, check=False)
    assert wrong.returncode == 1
    ref.write_text("[]")
    invalid = subprocess.run([*cmd, "--reference", str(ref)], capture_output=True, check=False)
    assert invalid.returncode == 3
    assert not invalid.stdout
