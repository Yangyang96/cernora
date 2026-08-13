from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


def test_release_metadata_and_governance_are_explicit() -> None:
    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["name"] == "cernora"
    assert project["version"] == "0.1.0"
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


def test_public_acceptance_summary_is_compact_and_explicit() -> None:
    root = Path(__file__).resolve().parents[2]
    summary = json.loads((root / "docs/public/acceptance-summary.json").read_text(encoding="utf-8"))

    assert summary["schema_version"] == "cernora.public-acceptance-summary/v1"
    assert summary["cernora_version"] == "0.1.0"
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
    assert summary["adversarial"] == {
        "authority_mismatch": "rejected",
        "behavioral_mismatch": "fail",
        "candidate_traversal": "rejected",
        "corrupt_artifact": "rejected",
        "missing_artifact": "rejected",
    }
    assert (root / "scripts/rebuild_acceptance.py").is_file()


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
    assert "## 0.1.0 - 2026-08-13" in changelog
    assert "Cernora `0.1.0` is the current release" in security
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

    ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "build-distributions:" in ci
    assert "wheel-acceptance:" in ci
    assert 'python-version: ["3.12", "3.13"]' in ci
    assert "name: cernora-dist-${{ github.sha }}" in ci
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in ci


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
