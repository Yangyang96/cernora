from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cernora import profile_workspace
from cernora.profile_workspace import ProfileWorkspaceError, init_profile


def test_default_init_uses_nearest_git_root_and_is_ignored(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    nested = tmp_path / "nested" / "work"
    nested.mkdir(parents=True)

    result = init_profile("private-profile", cwd=nested)
    target = tmp_path / ".cernora/profiles/private-profile"

    assert result.directory == ".cernora/profiles/private-profile"
    assert result.ignored is True
    assert (tmp_path / ".cernora/.gitignore").read_bytes() == b"*\n"
    assert (target / "profile.py").is_file()
    assert (target / "profile.json").is_file()
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".cernora/profiles/private-profile/profile.py"],
        cwd=tmp_path,
        check=False,
    )
    assert ignored.returncode == 0
    assert not (tmp_path / ".gitignore").exists()


def test_no_git_root_uses_cwd_and_explicit_output_is_not_hidden(tmp_path: Path) -> None:
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    private = init_profile("local-profile", cwd=isolated)
    assert private.ignored is True
    assert (isolated / ".cernora/profiles/local-profile/profile.py").is_file()

    public = init_profile(
        "public-profile",
        cwd=isolated,
        output=Path("profiles/public-profile"),
    )
    assert public.directory == "profiles/public-profile"
    assert public.ignored is False
    assert (isolated / "profiles/public-profile/profile.py").is_file()


def test_init_is_conflict_safe_and_never_overwrites(tmp_path: Path) -> None:
    destination = tmp_path / "profile"
    init_profile("safe-profile", output=destination, cwd=tmp_path)
    source = destination / "profile.py"
    original = source.read_bytes()
    source.write_bytes(original + b"# local edit\n")

    with pytest.raises(ProfileWorkspaceError, match="already exists"):
        init_profile("safe-profile", output=destination, cwd=tmp_path)

    assert source.read_bytes() == original + b"# local edit\n"


def test_init_never_deletes_concurrently_replaced_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "profile"
    original_mkdtemp = profile_workspace.tempfile.mkdtemp

    def create_foreign_after_precheck(
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | Path | None = None,
    ) -> str:
        staging = original_mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        destination.mkdir()
        (destination / "sentinel.txt").write_text("other owner", encoding="utf-8")
        return staging

    monkeypatch.setattr(
        profile_workspace.tempfile,
        "mkdtemp",
        create_foreign_after_precheck,
    )
    with pytest.raises(ProfileWorkspaceError, match="already exists"):
        init_profile("race-safe", output=destination, cwd=tmp_path)

    assert destination.is_dir()
    assert (destination / "sentinel.txt").read_text(encoding="utf-8") == "other owner"
    assert not (destination / "profile.py").exists()
    assert not (destination / "profile.json").exists()
    assert not tuple(tmp_path.glob(".profile.staging-*"))


def test_init_rejects_weakened_or_symlinked_private_workspace(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    private = tmp_path / ".cernora"
    private.mkdir()
    (private / ".gitignore").write_text("!profiles/\n", encoding="utf-8")
    with pytest.raises(ProfileWorkspaceError, match="must contain exactly"):
        init_profile("unsafe-profile", cwd=tmp_path)
    assert not (private / "profiles/unsafe-profile").exists()

    other = tmp_path / "other"
    other.mkdir()
    private.joinpath(".gitignore").unlink()
    private.rmdir()
    private.symlink_to(other, target_is_directory=True)
    with pytest.raises(ProfileWorkspaceError, match="ordinary directory"):
        init_profile("linked-profile", cwd=tmp_path)


@pytest.mark.parametrize("name", ["", "../escape", "UPPER", "-leading", "a" * 65])
def test_init_rejects_unsafe_names(tmp_path: Path, name: str) -> None:
    with pytest.raises(ProfileWorkspaceError, match="Profile name"):
        init_profile(name, cwd=tmp_path)
