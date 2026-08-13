from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from cernora.cli.main import main
from cernora.profile import Profile
from cernora.profile_loader import ProfileLoadError, load_local_profile
from cernora.profile_workspace import init_profile


def test_generated_profile_loads_from_explicit_path_without_registry(tmp_path: Path) -> None:
    destination = tmp_path / "profile"
    init_profile("loaded-profile", output=destination, cwd=tmp_path)

    profile = load_local_profile(destination)

    assert isinstance(profile, Profile)
    assert profile.authority.profile_id == "loaded-profile"
    assert profile.projection_version == "scaffold-projection/v1"
    assert not any(name.startswith("_cernora_local_profile_") for name in sys.modules)


def test_loader_rejects_symlink_missing_factory_and_factory_failure(tmp_path: Path) -> None:
    destination = tmp_path / "profile"
    destination.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("def create_profile():\n    return object()\n", encoding="utf-8")
    (destination / "profile.py").symlink_to(outside)
    with pytest.raises(ProfileLoadError, match="ordinary file"):
        load_local_profile(destination)

    (destination / "profile.py").unlink()
    (destination / "profile.py").write_text("value = 1\n", encoding="utf-8")
    with pytest.raises(ProfileLoadError, match="create_profile"):
        load_local_profile(destination)

    (destination / "profile.py").write_text(
        "def create_profile():\n    raise RuntimeError('private detail')\n",
        encoding="utf-8",
    )
    with pytest.raises(ProfileLoadError, match="RuntimeError") as captured:
        load_local_profile(destination)
    assert "private detail" not in str(captured.value)


def test_cli_init_and_explicit_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)

    assert main(["profile", "init", "cli-profile"]) == 0
    created = json.loads(capfd.readouterr().out)
    assert created == {
        "directory": ".cernora/profiles/cli-profile",
        "ignored": True,
        "profile_name": "cli-profile",
        "status": "created",
    }

    profile_path = tmp_path / ".cernora/profiles/cli-profile"
    assert main(["profile", "validate", "--profile-path", str(profile_path)]) == 0
    authority = json.loads(capfd.readouterr().out)
    assert authority["profile_id"] == "cli-profile"

    assert main(["profile", "validate", "--profile", "builtin:offline-workflow"]) == 0
    built_in = json.loads(capfd.readouterr().out)
    assert built_in["profile_id"] == "cernora-offline-workflow-v1"


def test_cli_rejects_implicit_or_legacy_profile_selection() -> None:
    with pytest.raises(SystemExit) as missing:
        main(["profile", "validate"])
    assert missing.value.code == 2

    with pytest.raises(SystemExit) as legacy:
        main(["profile", "validate", "--profile", "offline-workflow"])
    assert legacy.value.code == 2
