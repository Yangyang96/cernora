from __future__ import annotations

import os
import runpy
import socket
import sys
from pathlib import Path

import pytest

from cernora.adapter import Adapter, CompletedExport
from cernora.conformance import (
    ConformanceError,
    check_adapter_conformance,
    check_profile_conformance,
)
from cernora.core.evidence_bundle_v2 import decode_evidence_bundle_v2
from cernora.evaluation.package import (
    evaluate_imported_case,
    read_evaluation_report,
    read_imported_evaluation,
)
from cernora.examples.offline_workflow import (
    OfflineWorkflowAdapter,
    materialize_completed_export,
)
from cernora.examples.offline_workflow import adapter as offline_adapter
from cernora.examples.offline_workflow import workflow as offline_workflow
from cernora.examples.offline_workflow.adapter import CompletedExportError
from cernora.ingestion.errors import IngestionIntegrityError
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profiles.offline_workflow import OfflineWorkflowProfile


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_packaged_example_is_protocol_conformant_deterministic_and_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unrelated = tmp_path / "unrelated-cwd"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    def no_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("offline example attempted network access")

    monkeypatch.setattr(socket, "socket", no_network)
    for name in tuple(os.environ):
        if any(marker in name.upper() for marker in ("TOKEN", "PASSWORD", "API_KEY")):
            monkeypatch.delenv(name, raising=False)

    adapter = OfflineWorkflowAdapter()
    assert isinstance(adapter, Adapter)
    trees: list[dict[str, bytes]] = []
    adapted_paths: list[Path] = []
    for index in range(3):
        root = tmp_path / f"run-{index}"
        completed = materialize_completed_export(root / "completed")
        adapted = adapter.adapt(completed, root / "adapted")
        trees.append(_tree_bytes(root / "adapted"))
        adapted_paths.append(adapted.bundle_path)

    assert trees[0] == trees[1] == trees[2]
    public_export = (tmp_path / "run-0/completed/export.json").read_text(encoding="utf-8").lower()
    assert not any(
        marker in public_export
        for marker in ("http://", "https://", "token", "password", "api_key")
    )
    profile = OfflineWorkflowProfile()
    bundle = decode_evidence_bundle_v2(trees[0]["bundle.json"])
    assert bundle.profile.profile_id == profile.authority.profile_id
    assert bundle.terminal.status == "completed"

    imported = tmp_path / "imported"
    import_evidence_bundle_v2(
        profile=profile,
        bundle_path=adapted_paths[0],
        output=imported,
    )
    evaluated = tmp_path / "evaluated"
    receipt = evaluate_imported_case(profile, imported, evaluated)
    assert receipt.case_outcome == "pass"
    assert receipt.eligible is True
    assert read_imported_evaluation(evaluated, profile) == receipt
    assert read_evaluation_report(evaluated, profile) is None


def test_public_conformance_helpers_validate_profile_and_closed_adapter_tree(
    tmp_path: Path,
) -> None:
    profile = OfflineWorkflowProfile()
    profile_result = check_profile_conformance(profile)
    assert profile_result.profile_id == profile.authority.profile_id
    assert profile_result.case_ids == (profile.authority.cases[0].case_id,)

    completed = materialize_completed_export(tmp_path / "completed")
    adapter_result = check_adapter_conformance(
        OfflineWorkflowAdapter(),
        completed,
        tmp_path / "adapted",
    )
    assert adapter_result.bundle_id == "offline-workflow-example"
    assert adapter_result.bundle_path == tmp_path / "adapted/bundle.json"

    with pytest.raises(ConformanceError, match="must not already exist"):
        check_adapter_conformance(
            OfflineWorkflowAdapter(),
            completed,
            tmp_path / "adapted",
        )

    class MalformedAdapter:
        def adapt(self, completed_export: CompletedExport, output: Path) -> object:
            del completed_export, output
            return object()

    with pytest.raises(ConformanceError, match="AdaptedBundle"):
        check_adapter_conformance(
            MalformedAdapter(),
            completed,
            tmp_path / "malformed-adapter",
        )


def test_wheel_packaged_module_entry_runs_example(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "module-example"
    monkeypatch.setattr(sys, "argv", ["offline_workflow", str(output)])
    with pytest.raises(SystemExit, match="0"):
        runpy.run_module("cernora.examples.offline_workflow", run_name="__main__")
    assert capsys.readouterr().out == "pass\n"


@pytest.mark.parametrize(
    "attack",
    ("extra", "symlink", "fifo", "tampered", "duplicate-json", "invalid-utf8"),
)
def test_adapter_rejects_unsafe_or_malformed_completed_exports(
    tmp_path: Path,
    attack: str,
) -> None:
    completed = materialize_completed_export(tmp_path / "completed")
    if attack == "extra":
        (completed.root / "extra.txt").write_text("extra", encoding="utf-8")
    elif attack == "symlink":
        target = completed.root / "stdout.json"
        target.unlink()
        outside = tmp_path / "outside.json"
        outside.write_text('{"key":"alpha","value":"first"}', encoding="utf-8")
        target.symlink_to(outside)
    elif attack == "fifo":
        target = completed.root / "stderr.txt"
        target.unlink()
        os.mkfifo(target)
    elif attack == "tampered":
        (completed.root / "stdout.json").write_text("{}", encoding="utf-8")
    elif attack == "duplicate-json":
        payload = (completed.root / "export.json").read_bytes()
        (completed.root / "export.json").write_bytes(payload[:-1] + b',"run_id":"duplicate"}')
    else:
        (completed.root / "stderr.txt").write_bytes(b"\xff")

    output = tmp_path / "adapted"
    with pytest.raises(CompletedExportError):
        OfflineWorkflowAdapter().adapt(completed, output)
    assert not output.exists()


def test_adapter_rejects_root_symlink_overlap_and_late_tamper(tmp_path: Path) -> None:
    completed = materialize_completed_export(tmp_path / "completed")
    linked = tmp_path / "linked"
    linked.symlink_to(completed.root, target_is_directory=True)
    with pytest.raises(CompletedExportError):
        OfflineWorkflowAdapter().adapt(CompletedExport(linked), tmp_path / "linked-output")
    with pytest.raises(CompletedExportError, match="overlap"):
        OfflineWorkflowAdapter().adapt(completed, completed.root / "output")

    adapted = OfflineWorkflowAdapter().adapt(completed, tmp_path / "adapted")
    (adapted.bundle_path.parent / "streams/stdout.json").write_text("{}", encoding="utf-8")
    with pytest.raises(IngestionIntegrityError):
        import_evidence_bundle_v2(
            profile=OfflineWorkflowProfile(),
            bundle_path=adapted.bundle_path,
            output=tmp_path / "imported",
        )


@pytest.mark.parametrize("operation", ("adapter", "materializer"))
@pytest.mark.parametrize("foreign_kind", ("empty", "nonempty"))
def test_publication_race_never_replaces_foreign_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    foreign_kind: str,
) -> None:
    output = tmp_path / f"race-{operation}-{foreign_kind}"
    original = offline_adapter._publish_directory_no_replace
    foreign_inode: list[int] = []

    def inject_foreign_destination(staging: Path, destination: Path) -> None:
        destination.mkdir()
        if foreign_kind == "nonempty":
            (destination / "foreign.txt").write_text("foreign", encoding="utf-8")
        foreign_inode.append(destination.stat().st_ino)
        original(staging, destination)

    if operation == "adapter":
        materialize_completed_export(tmp_path / "completed")
        monkeypatch.setattr(
            offline_adapter,
            "_publish_directory_no_replace",
            inject_foreign_destination,
        )
    else:
        monkeypatch.setattr(
            offline_workflow,
            "_publish_directory_no_replace",
            inject_foreign_destination,
        )

    def invoke() -> object:
        if operation == "adapter":
            return OfflineWorkflowAdapter().adapt(CompletedExport(tmp_path / "completed"), output)
        return materialize_completed_export(output)

    with pytest.raises(CompletedExportError, match="destination already exists"):
        invoke()
    assert output.stat().st_ino == foreign_inode[0]
    expected = {"foreign.txt": b"foreign"} if foreign_kind == "nonempty" else {}
    assert _tree_bytes(output) == expected
    assert not tuple(output.parent.glob(f".{output.name}.staging-*"))
