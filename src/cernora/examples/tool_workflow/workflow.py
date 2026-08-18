"""Run one frozen tool-workflow fixture through the installed evaluation core."""

from __future__ import annotations

from pathlib import Path

from cernora.evaluation.package import (
    evaluate_imported_case,
    read_evaluation_report,
    read_imported_evaluation,
)
from cernora.examples.tool_workflow.fixtures import fixture_matrix, materialize_fixture
from cernora.ingestion.package_v2 import import_evidence_bundle_v2
from cernora.profiles.tool_workflow import ToolWorkflowProfile


def run_tool_workflow(workdir: Path, fixture_id: str = "happy-path") -> str:
    """Materialize, import, evaluate and strictly reload one accepted fixture."""

    matches = tuple(item for item in fixture_matrix() if item.fixture_id == fixture_id)
    if len(matches) != 1 or matches[0].expected == "import_rejection":
        raise ValueError("fixture id must select an accepted tool workflow fixture")
    profile = ToolWorkflowProfile()
    adapted = materialize_fixture(fixture_id, workdir / "bundle")
    imported = workdir / "imported"
    import_evidence_bundle_v2(
        profile=profile,
        bundle_path=adapted.bundle_path,
        output=imported,
    )
    evaluated = workdir / "evaluated"
    receipt = evaluate_imported_case(profile, imported, evaluated)
    if read_imported_evaluation(evaluated, profile) != receipt:
        raise ValueError("strictly reloaded evaluation differs from persisted receipt")
    report = read_evaluation_report(evaluated, profile)
    if report is None or report.conclusion != receipt.case_outcome:
        raise ValueError("strictly reloaded report differs from persisted decision")
    return receipt.case_outcome


__all__ = ["run_tool_workflow"]
