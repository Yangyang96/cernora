from __future__ import annotations

import json
import re
import shutil
import subprocess
import tomllib
import zipfile
from pathlib import Path

import pytest

from scripts.check_release import (
    _ALLOWED_ROOT_FILES,
    ReleaseCheckError,
    _tree_files,
    artifact_paths,
    check_artifacts,
    project_version,
)
from scripts.release import ReleaseCommandError, _validate_release_metadata


def test_release_metadata_and_governance_are_explicit() -> None:
    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["name"] == "cernora"
    assert project["version"] == "0.1.1rc1"
    assert project["requires-python"] == ">=3.12,<3.14"
    assert project["license"] == "Apache-2.0"
    assert project["license-files"] == ["LICENSE"]
    assert project["maintainers"] == [{"name": "Yangyang96"}]
    assert project["scripts"] == {"cernora": "cernora.cli.main:main"}
    assert project["urls"] == {
        "Repository": "https://github.com/Yangyang96/cernora",
        "Issues": "https://github.com/Yangyang96/cernora/issues",
        "Documentation": "https://github.com/Yangyang96/cernora#readme",
    }
    for name in ("LICENSE", "NOTICE", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md"):
        assert (root / name).is_file()
    notice = (root / "NOTICE").read_text(encoding="utf-8")
    assert notice.startswith("Cernora\nCopyright 2026 杨杨\n")
    assert "does not identify or\nimply a sponsoring legal entity" in notice


def test_readme_language_switch_is_bidirectional() -> None:
    root = Path(__file__).resolve().parents[2]
    english = (root / "README.md").read_text(encoding="utf-8")
    chinese = (root / "README.zh-CN.md").read_text(encoding="utf-8")
    roadmap_english = (root / "ROADMAP.md").read_text(encoding="utf-8")
    roadmap_chinese = (root / "ROADMAP.zh-CN.md").read_text(encoding="utf-8")

    assert "[简体中文](https://github.com/Yangyang96/cernora/blob/main/README.zh-CN.md)" in english
    assert "[English](README.md)" in chinese
    assert (
        "[product roadmap](https://github.com/Yangyang96/cernora/blob/main/ROADMAP.md)" in english
    )
    assert "[产品路线图](ROADMAP.zh-CN.md)" in chinese
    assert "[简体中文](ROADMAP.zh-CN.md)" in roadmap_english
    assert "[English](ROADMAP.md)" in roadmap_chinese


def test_chinese_readme_links_to_complete_chinese_documentation() -> None:
    root = Path(__file__).resolve().parents[2]
    readme = (root / "README.zh-CN.md").read_text(encoding="utf-8")
    root_documents = {
        "CONTRIBUTING.zh-CN.md",
        "SECURITY.zh-CN.md",
        "CHANGELOG.zh-CN.md",
    }
    public_documents = {
        "README.zh-CN.md",
        "architecture.zh-CN.md",
        "profile-authoring.zh-CN.md",
        "adapter-conformance.zh-CN.md",
        "compatibility-matrix.zh-CN.md",
        "evidence-publication-and-rebuild.zh-CN.md",
        "acceptance.zh-CN.md",
        "local-release-checklist.zh-CN.md",
        "release-day-runbook.zh-CN.md",
    }

    for name in root_documents:
        assert (root / name).is_file()
        assert f"]({name})" in readme
    for name in public_documents:
        assert (root / "docs" / "public" / name).is_file()
        assert f"](docs/public/{name})" in readme


def test_public_acceptance_summary_is_compact_and_explicit() -> None:
    root = Path(__file__).resolve().parents[2]
    summary = json.loads((root / "docs/public/acceptance-summary.json").read_text(encoding="utf-8"))

    assert summary["schema_version"] == "cernora.public-acceptance-summary/v1"
    assert summary["cernora_version"] == "0.1.1rc1"
    assert summary["output_protocols"] == [
        "agent.evaluator.evidence/v1",
        "agent.evaluator.score/v1",
        "agent.evaluator.gate-decision/v1",
        "agent.evaluator.result-record/v1",
        "agent.evaluator.evaluation-report/v1",
    ]
    assert summary["execution"] == {
        "credentials_required": False,
        "network_blocked": True,
        "repository_source_import": False,
        "wheel_only": True,
    }
    assert summary["scope"] == {
        "agent_execution": False,
        "completed_export": "packaged_synthetic",
        "evaluation_core_path": True,
        "experiment_harness": False,
        "runtime_receipt_capture": False,
        "sandbox_execution": False,
    }
    assert summary["tasks"]["sanitized-v1-workflow"]["outcome"] == "pass"
    assert summary["tasks"]["sanitized-v1-workflow"]["repetitions"] == 3
    coding = summary["tasks"]["sanitized-v2-coding"]["cases"]
    assert set(coding) == {"backend-v1", "frontend-v1", "fail-closed-v1"}
    assert all(case["outcome"] == "pass" and case["repetitions"] == 3 for case in coding.values())
    tool_workflow = summary["tasks"]["tool-workflow"]["cases"]
    assert len(tool_workflow) == 18
    assert [case["outcome"] for case in tool_workflow.values()].count("rejected") == 1
    coding_evaluation = summary["tasks"]["coding-evaluation"]["cases"]
    assert len(coding_evaluation) == 20
    assert [case["outcome"] for case in coding_evaluation.values()].count("pass") == 2
    assert [case["outcome"] for case in coding_evaluation.values()].count("fail") == 8
    assert [case["outcome"] for case in coding_evaluation.values()].count("inconclusive") == 9
    assert [case["outcome"] for case in coding_evaluation.values()].count("rejected") == 1
    assert summary["adversarial"] == {
        "authority_mismatch": "rejected",
        "behavioral_mismatch": "fail",
        "candidate_traversal": "rejected",
        "corrupt_artifact": "rejected",
        "missing_artifact": "rejected",
    }
    assert (root / "scripts/rebuild_acceptance.py").is_file()
    assert (root / "scripts/release.py").is_file()
    rebuild_script = (root / "scripts/rebuild_acceptance.py").read_text(encoding="utf-8")
    assert "rebuilt public acceptance summary differs from the reviewed summary" in rebuild_script


def test_public_docs_preserve_composed_system_boundary() -> None:
    root = Path(__file__).resolve().parents[2]
    english = (root / "README.md").read_text(encoding="utf-8")
    chinese = (root / "README.zh-CN.md").read_text(encoding="utf-8")
    architecture = (root / "docs/public/architecture.md").read_text(encoding="utf-8")
    acceptance = (root / "docs/public/acceptance.md").read_text(encoding="utf-8")

    for readme in (english, chinese):
        assert "Experiment Harness" in readme
        assert "runtime receipt" in readme
    assert "independent evaluation core" in english
    assert "独立评测内核" in chinese
    assert "Complete-system composition" in architecture
    assert "packaged synthetic completed exports" in acceptance
    assert "not an operating-system sandbox claim" in acceptance


def test_release_docs_describe_production_installation() -> None:
    root = Path(__file__).resolve().parents[2]
    english = (root / "README.md").read_text(encoding="utf-8")
    chinese = (root / "README.zh-CN.md").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    security = (root / "SECURITY.md").read_text(encoding="utf-8")

    assert "**Current release:**" in english
    assert "**当前版本\N{FULLWIDTH COLON}**" in chinese
    for readme in (english, chinese):
        assert "python3.12 -m venv .venv" in readme
        assert "python -m pip install cernora" in readme
    assert "must not already exist" in english
    assert "必须尚不存在" in chinese
    assert "## 0.1.0 - 2026-08-14" in changelog
    assert "Cernora `0.1.1` is the current release" in security
    assert "security/advisories/new" in security


def test_platform_and_release_workflow_boundaries_are_explicit() -> None:
    root = Path(__file__).resolve().parents[2]
    matrix = (root / "docs/public/compatibility-matrix.md").read_text(encoding="utf-8")
    workflow = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")

    for platform in ("macOS", "Linux", "Windows"):
        assert f"| {platform} |" in matrix
    assert "| Linux |" in matrix and "| Not yet supported |" in matrix
    assert "environment: testpypi" in workflow
    assert "environment: pypi" in workflow
    assert workflow.count("id-token: write") == 2
    assert workflow.count("Require a successful CI run for this exact commit") == 2
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in workflow
    assert "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33" in workflow
    assert "python -m build" not in workflow
    assert "uv build" not in workflow
    assert "cernora-0.1.0" not in workflow
    assert "refs/tags/v${ARTIFACT_VERSION}" in workflow
    assert workflow.count("id: artifacts") == 2
    assert workflow.count('test "$(jq -r .path <<<"$run_json")" = .github/workflows/ci.yml') == 2
    assert workflow.count('test "$(jq -r .event <<<"$run_json")" = push') == 2
    assert workflow.count('test "$(jq -r .head_branch <<<"$run_json")" = main') == 2

    ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "build-distributions:" in ci
    assert "wheel-acceptance:" in ci
    assert 'python-version: ["3.12", "3.13"]' in ci
    assert "name: cernora-dist-${{ github.sha }}" in ci
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in ci
    assert "cernora-0.1.0" not in ci
    assert "scripts/check_release.py --tree . --dist-dir dist" in ci


def test_release_commands_and_runbook_are_version_generic() -> None:
    root = Path(__file__).resolve().parents[2]
    runbook = (root / "docs/public/release-day-runbook.md").read_text(encoding="utf-8")
    automation = (root / "scripts/release.py").read_text(encoding="utf-8")
    checker = (root / "scripts/check_release.py").read_text(encoding="utf-8")

    assert "# Release runbook for `0.1.x`" in runbook
    assert "scripts/release.py preflight" in runbook
    assert "scripts/release.py verify --version <version>" in runbook
    assert "cernora-0.1.0" not in automation
    assert "cernora-0.1.0" not in checker
    assert '"--isolated"' in automation
    assert "sys.version_info[:2]" in automation


def test_release_artifact_names_follow_the_declared_version(tmp_path: Path) -> None:
    wheel, sdist = artifact_paths(tmp_path, "0.1.7rc1")

    assert wheel.name == "cernora-0.1.7rc1-py3-none-any.whl"
    assert sdist.name == "cernora-0.1.7rc1.tar.gz"


def test_release_version_must_be_canonical_pep440(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "cernora"\nversion = "0.1-1"\n', encoding="utf-8"
    )

    with pytest.raises(ReleaseCheckError, match="canonical PEP 440"):
        project_version(tmp_path)


def test_release_metadata_rejects_nonempty_unreleased_section(tmp_path: Path) -> None:
    package = tmp_path / "src/cernora"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## Unreleased\n\n- later work\n\n## 0.1.0 - 2026-08-14\n",
        encoding="utf-8",
    )

    with pytest.raises(ReleaseCommandError, match="Unreleased"):
        _validate_release_metadata("0.1.0", tmp_path)

    changelog.write_text(
        "# Changelog\n\n## Unreleased\n\n## 0.1.0 - 2026-08-14\n", encoding="utf-8"
    )
    _validate_release_metadata("0.1.0", tmp_path)


def test_release_checker_rejects_oversized_compressed_members(tmp_path: Path) -> None:
    wheel, sdist = artifact_paths(tmp_path, "0.1.0")
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("cernora/oversized.bin", b"x" * 100_001)

    with pytest.raises(ReleaseCheckError, match="exceeds 100 KB"):
        check_artifacts(wheel, sdist, "0.1.0")


def test_release_tree_excludes_gitignored_private_state(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is unavailable")

    forbidden = "".join(("ob", "serv"))  # the word must not appear literally here
    for name in _ALLOWED_ROOT_FILES:
        (tmp_path / name).write_text("", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("private/\n", encoding="utf-8")
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "secret.md").write_text(f"{forbidden}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    files = _tree_files(tmp_path)
    assert "private/secret.md" not in files
    assert ".gitignore" in files


def test_release_tree_flags_force_tracked_private_state(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is unavailable")

    forbidden = "".join(("ob", "serv"))  # the word must not appear literally here
    for name in _ALLOWED_ROOT_FILES:
        (tmp_path / name).write_text("", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("private/\n", encoding="utf-8")
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "secret.md").write_text(f"{forbidden}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-f", "private/secret.md"], cwd=tmp_path, check=True)

    with pytest.raises(ReleaseCheckError, match="forbidden private vocabulary"):
        _tree_files(tmp_path)


def test_public_markdown_relative_links_resolve() -> None:
    root = Path(__file__).resolve().parents[2]
    markdown_files = sorted(
        path
        for path in root.rglob("*.md")
        if not any(
            part in {".git", ".pytest_cache", ".ruff_cache", ".venv", "dist"}
            for part in path.relative_to(root).parts
        )
    )
    relative_links: list[tuple[Path, str]] = []
    for document in markdown_files:
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_text = target.split("#", 1)[0]
            if not path_text:
                continue
            relative_links.append((document, path_text))
            assert (document.parent / path_text).resolve().is_file(), (
                f"broken relative link in {document.relative_to(root)}: {target}"
            )

    assert len(relative_links) >= 30
