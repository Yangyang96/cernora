from __future__ import annotations

import hashlib
import json
import os
import runpy
import socket
import sys
from pathlib import Path

import pytest

from cernora.adapter import Adapter, CompletedExport
from cernora.core.evidence_bundle_v2 import decode_evidence_bundle_v2
from cernora.evaluation.package import evaluate_imported_case, read_imported_evaluation
from cernora.examples.coding_task import (
    CodingTaskAdapter,
    CompletedExportError,
    materialize_completed_export,
)
from cernora.examples.coding_task import adapter as coding_adapter
from cernora.examples.coding_task import workflow as coding_workflow
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profiles.coding_task import CodingTaskProfile

CASE_IDS = ("backend-v1", "frontend-v1", "fail-closed-v1")


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _rewrite_answer(root: Path) -> None:
    candidate = (root / "candidate.json").read_bytes()
    answer = json.dumps(
        {"candidate_sha256": hashlib.sha256(candidate).hexdigest()},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    (root / "answer.json").write_bytes(answer)


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_packaged_coding_examples_pass_deterministically_and_strictly_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
) -> None:
    unrelated = tmp_path / "unrelated-cwd"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    def no_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("coding example attempted network access")

    monkeypatch.setattr(socket, "socket", no_network)
    for name in tuple(os.environ):
        if any(marker in name.upper() for marker in ("TOKEN", "PASSWORD", "API_KEY")):
            monkeypatch.delenv(name, raising=False)

    adapter = CodingTaskAdapter()
    assert isinstance(adapter, Adapter)
    trees: list[dict[str, bytes]] = []
    bundle_paths: list[Path] = []
    for index in range(3):
        root = tmp_path / f"{case_id}-{index}"
        completed = materialize_completed_export(root / "completed", case_id)
        adapted = adapter.adapt(completed, root / "adapted")
        trees.append(_tree_bytes(root / "adapted"))
        bundle_paths.append(adapted.bundle_path)

    assert trees[0] == trees[1] == trees[2]
    bundle = decode_evidence_bundle_v2(trees[0]["bundle.json"])
    assert bundle.case.case_id == case_id
    assert bundle.terminal.status == "completed"

    profile = CodingTaskProfile()
    imported = tmp_path / f"{case_id}-imported"
    import_evidence_bundle_v2(profile=profile, bundle_path=bundle_paths[0], output=imported)
    evaluated = tmp_path / f"{case_id}-evaluated"
    receipt = evaluate_imported_case(profile, imported, evaluated)
    assert receipt.case_outcome == "pass"
    assert receipt.eligible is True
    assert read_imported_evaluation(evaluated, profile) == receipt


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_wheel_packaged_module_cli_runs_each_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case_id: str,
) -> None:
    output = tmp_path / f"module-{case_id}"
    monkeypatch.setattr(sys, "argv", ["coding_task", str(output), case_id])
    with pytest.raises(SystemExit, match="0"):
        runpy.run_module("cernora.examples.coding_task", run_name="__main__")
    assert capsys.readouterr().out == "pass\n"


@pytest.mark.parametrize(
    "attack",
    (
        "extra",
        "symlink",
        "fifo",
        "oversize",
        "malformed",
        "duplicate-json",
        "invalid-utf8",
        "wrong-case",
        "answer-mismatch",
    ),
)
def test_adapter_rejects_unsafe_or_malformed_completed_exports(
    tmp_path: Path,
    attack: str,
) -> None:
    completed = materialize_completed_export(tmp_path / "completed", "backend-v1")
    if attack == "extra":
        (completed.root / "extra.txt").write_text("extra", encoding="utf-8")
    elif attack == "symlink":
        target = completed.root / "candidate.json"
        target.unlink()
        outside = tmp_path / "outside.json"
        outside.write_text('{"files":{"app.py":"outside"}}', encoding="utf-8")
        target.symlink_to(outside)
    elif attack == "fifo":
        target = completed.root / "stderr.txt"
        target.unlink()
        os.mkfifo(target)
    elif attack == "oversize":
        (completed.root / "stderr.txt").write_bytes(b"x" * 1_000_001)
    elif attack == "malformed":
        (completed.root / "candidate.json").write_bytes(b"{")
    elif attack == "duplicate-json":
        (completed.root / "candidate.json").write_bytes(b'{"files":{},"files":{}}')
    elif attack == "invalid-utf8":
        (completed.root / "stderr.txt").write_bytes(b"\xff")
    elif attack == "wrong-case":
        metadata = json.loads((completed.root / "export.json").read_bytes())
        metadata["case_id"] = "Backend-v1"
        (completed.root / "export.json").write_text(json.dumps(metadata), encoding="utf-8")
    else:
        (completed.root / "answer.json").write_text(
            '{"candidate_sha256":"0000000000000000000000000000000000000000000000000000000000000000"}',
            encoding="utf-8",
        )

    output = tmp_path / "adapted"
    with pytest.raises(CompletedExportError):
        CodingTaskAdapter().adapt(completed, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "candidate",
    (
        {"files": {"../escape.py": "x"}},
        {"files": {"/absolute.py": "x"}},
        {"files": {"dir/../escape.py": "x"}},
        {"files": {"dir\\escape.py": "x"}},
        {"files": {"./escape.py": "x"}},
        {"files": {"dir//escape.py": "x"}},
    ),
)
def test_adapter_rejects_candidate_traversal_paths(
    tmp_path: Path,
    candidate: dict[str, dict[str, str]],
) -> None:
    completed = materialize_completed_export(tmp_path / "completed", "backend-v1")
    (completed.root / "candidate.json").write_text(json.dumps(candidate), encoding="utf-8")
    _rewrite_answer(completed.root)
    with pytest.raises(CompletedExportError, match="canonical contained"):
        CodingTaskAdapter().adapt(completed, tmp_path / "adapted")


def test_candidate_content_mismatch_evaluates_fail_closed(tmp_path: Path) -> None:
    completed = materialize_completed_export(tmp_path / "completed", "backend-v1")
    (completed.root / "candidate.json").write_text(
        '{"files":{"app.py":"def health(): return fail"}}', encoding="utf-8"
    )
    _rewrite_answer(completed.root)
    adapted = CodingTaskAdapter().adapt(completed, tmp_path / "adapted")
    profile = CodingTaskProfile()
    imported = tmp_path / "imported"
    import_evidence_bundle_v2(profile=profile, bundle_path=adapted.bundle_path, output=imported)
    receipt = evaluate_imported_case(profile, imported, tmp_path / "evaluated")
    assert receipt.case_outcome == "fail"
    assert receipt.eligible is True


def test_adapter_rejects_overlap_and_output_conflicts(tmp_path: Path) -> None:
    completed = materialize_completed_export(tmp_path / "completed", "backend-v1")
    with pytest.raises(CompletedExportError, match="overlap"):
        CodingTaskAdapter().adapt(completed, completed.root / "output")

    output = tmp_path / "owned-by-someone-else"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(CompletedExportError, match="must not already exist"):
        CodingTaskAdapter().adapt(completed, output)
    assert marker.read_text(encoding="utf-8") == "keep"


def test_materializer_rejects_unknown_case_and_existing_output(tmp_path: Path) -> None:
    with pytest.raises(CompletedExportError, match="exact packaged"):
        materialize_completed_export(tmp_path / "unknown", "Backend-v1")

    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(CompletedExportError, match="must not already exist"):
        materialize_completed_export(output, "backend-v1")
    assert marker.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("operation", ("adapter", "materializer"))
@pytest.mark.parametrize("foreign_kind", ("empty", "nonempty"))
def test_publication_race_never_replaces_foreign_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    foreign_kind: str,
) -> None:
    output = tmp_path / f"race-{operation}-{foreign_kind}"
    original = coding_adapter._publish_directory_no_replace
    foreign_inode: list[int] = []

    def inject_foreign_destination(staging: Path, destination: Path) -> None:
        destination.mkdir()
        if foreign_kind == "nonempty":
            (destination / "foreign.txt").write_text("foreign", encoding="utf-8")
        foreign_inode.append(destination.stat().st_ino)
        original(staging, destination)

    if operation == "adapter":
        materialize_completed_export(tmp_path / "completed", "backend-v1")
        monkeypatch.setattr(
            coding_adapter,
            "_publish_directory_no_replace",
            inject_foreign_destination,
        )
    else:
        monkeypatch.setattr(
            coding_workflow,
            "_publish_directory_no_replace",
            inject_foreign_destination,
        )

    def invoke() -> object:
        if operation == "adapter":
            return CodingTaskAdapter().adapt(CompletedExport(tmp_path / "completed"), output)
        return materialize_completed_export(output, "backend-v1")

    with pytest.raises(CompletedExportError, match="destination already exists"):
        invoke()
    assert output.stat().st_ino == foreign_inode[0]
    expected = {"foreign.txt": b"foreign"} if foreign_kind == "nonempty" else {}
    assert _tree_bytes(output) == expected
    assert not tuple(output.parent.glob(f".{output.name}.staging-*"))
