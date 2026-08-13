from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any, cast

import pytest

from cernora.core.canonical import canonical_json
from cernora.core.case import CaseProfile
from cernora.evaluation.imported_case import evaluate_imported_case_v2
from cernora.ingestion import package_v2
from cernora.ingestion.contracts_v2 import AuthorityBoundImportPackageV2
from cernora.ingestion.errors import (
    AuthorityIncompatibleError,
    IngestionConfigurationError,
    IngestionIntegrityError,
)
from cernora.ingestion.package_v2 import (
    import_evidence_bundle_v2,
    read_import_package_v2_content,
)
from cernora.profile import ProfileAssessment, ProfileEvaluationContext
from tests.public.test_core_contracts import _bundle_payload, _profile, _sha_value


class _NeutralProfile:
    projection_version = "public-projection/v1"

    def __init__(self, authority: CaseProfile | None = None) -> None:
        self.authority = authority or _profile()

    def validate_import(self, bound: AuthorityBoundImportPackageV2) -> None:
        assert bound.profile == self.authority

    def assess(
        self,
        bound: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
    ) -> ProfileAssessment:
        del bound, context
        raise RuntimeError("neutral scorer unavailable")


def _write_bundle(
    root: Path,
    *,
    version: str | None = None,
    inconclusive: bool = False,
) -> Path:
    root.mkdir()
    payload, artifacts = _bundle_payload()
    if version is not None:
        payload["schema_version"] = version
        payload.pop("bundle_sha256")
        payload["bundle_sha256"] = _sha_value(payload)
    if inconclusive:
        payload["terminal"] = {
            "status": "inconclusive",
            "answer": None,
            "failure": {
                "domain": "evidence",
                "code": "insufficient_evidence",
                "message": "Evidence is insufficient for an eligible outcome",
            },
        }
        payload["artifacts"] = [
            item
            for item in cast(list[dict[str, Any]], payload["artifacts"])
            if item["artifact_id"] != "answer"
        ]
        artifacts.pop("answer")
        payload.pop("bundle_sha256")
        payload["bundle_sha256"] = _sha_value(payload)
    for declaration in cast(list[dict[str, Any]], payload["artifacts"]):
        path = root / cast(str, declaration["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(artifacts[cast(str, declaration["artifact_id"])])
    bundle_path = root / "bundle.json"
    bundle_path.write_bytes(canonical_json(payload))
    return bundle_path


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_v2_import_is_atomic_idempotent_and_authority_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path = _write_bundle(tmp_path / "source")
    profile = _NeutralProfile()
    output = tmp_path / "imported"
    first = import_evidence_bundle_v2(
        profile=profile,
        bundle_path=bundle_path,
        output=output,
    )
    before = _tree_bytes(output)
    mtimes = {name: (output / name).stat().st_mtime_ns for name in before}

    second = import_evidence_bundle_v2(
        profile=profile,
        bundle_path=bundle_path,
        output=output,
    )
    assert second == first
    assert _tree_bytes(output) == before
    assert {name: (output / name).stat().st_mtime_ns for name in before} == mtimes
    assert read_import_package_v2_content(output).receipt == first

    wrong = _NeutralProfile(_profile(profile_version="2.0.0"))
    with pytest.raises(AuthorityIncompatibleError):
        import_evidence_bundle_v2(
            profile=wrong,
            bundle_path=bundle_path,
            output=tmp_path / "wrong-authority",
        )

    def fail_write(root_descriptor: int, relative: str, payload: bytes) -> None:
        del root_descriptor, relative, payload
        raise OSError("injected publication failure")

    monkeypatch.setattr(package_v2, "_write_package_file", fail_write)
    failed = tmp_path / "failed"
    with pytest.raises(IngestionConfigurationError, match="publish"):
        import_evidence_bundle_v2(
            profile=profile,
            bundle_path=bundle_path,
            output=failed,
        )
    assert not failed.exists()
    assert not tuple(tmp_path.glob(".failed.staging-*"))


@pytest.mark.parametrize("attack", ["extra-file", "symlink", "fifo"])
def test_v2_import_rejects_nonordinary_source_entries(
    tmp_path: Path,
    attack: str,
) -> None:
    source = tmp_path / "source"
    bundle_path = _write_bundle(source)
    target = source / "streams/stderr.txt"
    if attack == "extra-file":
        (source / "undeclared.txt").write_text("undeclared", encoding="utf-8")
    elif attack == "symlink":
        target.unlink()
        outside = tmp_path / "outside.txt"
        outside.write_bytes(b"")
        target.symlink_to(outside)
    else:
        target.unlink()
        os.mkfifo(target)

    with pytest.raises(IngestionIntegrityError):
        import_evidence_bundle_v2(
            profile=_NeutralProfile(),
            bundle_path=bundle_path,
            output=tmp_path / "imported",
        )
    assert not (tmp_path / "imported").exists()


def test_v1_import_surface_is_absent_and_non_v2_is_rejected(tmp_path: Path) -> None:
    assert importlib.util.find_spec("cernora.ingestion.package") is None
    bundle_path = _write_bundle(
        tmp_path / "source",
        version="agent.evaluator.evidence-bundle/v1",
    )

    with pytest.raises(IngestionIntegrityError, match="EvidenceBundle v2"):
        import_evidence_bundle_v2(
            profile=_NeutralProfile(),
            bundle_path=bundle_path,
            output=tmp_path / "imported",
        )


def test_imported_evaluation_strictly_reloads_and_fails_closed(tmp_path: Path) -> None:
    profile = _NeutralProfile()
    completed_path = _write_bundle(tmp_path / "completed-source")
    completed_output = tmp_path / "completed-import"
    import_evidence_bundle_v2(
        profile=profile,
        bundle_path=completed_path,
        output=completed_output,
    )
    with pytest.raises(IngestionIntegrityError, match="evidence boundary"):
        evaluate_imported_case_v2(completed_output, profile)

    bundle_path = _write_bundle(tmp_path / "source", inconclusive=True)
    output = tmp_path / "imported"
    receipt = import_evidence_bundle_v2(
        profile=profile,
        bundle_path=bundle_path,
        output=output,
    )

    result = evaluate_imported_case_v2(output, profile)
    assert result.evidence.schema_version == "agent.evaluator.evidence/v1"
    assert result.score.schema_version == "agent.evaluator.score/v1"
    assert result.score.evidence_id == result.evidence.evidence_id
    assert result.evidence.failures[0].domain == "scorer"
    assert all(item.applicability == "invalid" for item in result.score.observations)
    assert all(
        reference.evidence_id == result.evidence.evidence_id
        for item in result.score.observations
        for reference in item.evidence_references
    )
    assert result.decision.decision == "inconclusive"
    assert result.decision.eligible is False
    assert result.decision.evidence_references

    artifact = output / receipt.artifacts[0].package_path
    artifact.write_bytes(b"tampered")
    with pytest.raises(IngestionIntegrityError):
        evaluate_imported_case_v2(output, profile)
