"""Run: python -m cernora.examples.metric_plans NEW_DIRECTORY."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

from cernora import (
    EvidenceBundleV2,
    evaluate_imported_case,
    import_evidence_bundle_v2,
    read_evaluation_report,
    read_imported_evaluation,
)
from cernora.core.canonical import canonical_json
from cernora.examples._completed_export import publish_directory_no_replace, write_tree
from cernora.examples.metric_plans import InventoryProfile, ResourceStatusProfile, _PlanProfile
from cernora.ingestion.errors import IngestionIntegrityError


def materialize(profile: _PlanProfile, output: Path, variant: str = "pass") -> Path:
    if variant not in {"pass", "fail", "missing", "conflict"}:
        raise ValueError("unknown metric example variant")
    files = {
        "source": canonical_json(profile.expected),
        "answer": canonical_json(profile.expected if variant != "fail" else {"wrong": True}),
        "stderr": canonical_json(
            {"clock_id": "example-monotonic", "scope": "agent_wall", "start_ms": 10, "end_ms": 35}
        ),
    }
    if variant == "missing":
        del files["source"]
        del files["answer"]
        files["unavailable-source"] = b"{}"
    elif variant == "conflict":
        files["source"] = b'{"conflict":true}'
    artifacts = [
        {
            "artifact_id": name,
            "path": name + ".json",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "media_type": "application/json",
        }
        for name, raw in files.items()
    ]

    def pointer(name: str) -> dict[str, str]:
        return {"artifact_id": name, "sha256": hashlib.sha256(files[name]).hexdigest()}

    action: dict[str, Any] = {
        "sequence": 0,
        "invocation_id": "call-1",
        "tool": profile.tool,
        "argv": [profile.tool, "--id", "alpha"],
        "previous_receipt_sha256": None,
        "result": {
            "status": "completed",
            "exit_code": 0,
            "committed": True,
            "delivered": True,
            "stdout_artifact": pointer("unavailable-source" if variant == "missing" else "source"),
            "stderr_artifact": pointer("stderr"),
        },
    }
    action["receipt_sha256"] = hashlib.sha256(canonical_json(action)).hexdigest()
    authority = profile.authority
    case = authority.cases[0]
    payload: dict[str, Any] = {
        "schema_version": "agent.evaluator.evidence-bundle/v2",
        "bundle_id": "metric-example",
        "producer": {"producer_id": "metric-example", "producer_version": "1.0.0"},
        "run": {"run_id": "example", "attempt_id": "attempt-1"},
        "profile": {
            "profile_id": authority.profile_id,
            "profile_version": authority.profile_version,
            "sha256": hashlib.sha256(canonical_json(authority)).hexdigest(),
        },
        "case": {
            "case_id": case.case_id,
            "case_version": case.case_version,
            "case_set": case.case_set,
            "sha256": hashlib.sha256(canonical_json(case)).hexdigest(),
        },
        "fixtures": [f.model_dump(mode="json") for f in case.fixture_references],
        "tool_actions": [action],
        "artifacts": artifacts,
        "terminal": {
            "status": "completed",
            "failure": None,
            "answer": {
                "content": files.get("answer", b"{}").decode(),
                "sha256": hashlib.sha256(files.get("answer", b"{}")).hexdigest(),
                "artifact": {
                    "artifact_id": "answer",
                    "sha256": hashlib.sha256(files.get("answer", b"{}")).hexdigest(),
                },
            },
        },
        "infrastructure": {"status": "valid", "failure": None},
    }
    if variant == "missing":
        payload["terminal"] = {
            "status": "inconclusive",
            "answer": None,
            "failure": {
                "domain": "runtime",
                "code": "capture-incomplete",
                "message": "Final answer and source unavailable",
            },
        }
    payload["bundle_sha256"] = hashlib.sha256(canonical_json(payload)).hexdigest()
    bundle = EvidenceBundleV2.model_validate_json(canonical_json(payload))
    tree = {name + ".json": raw for name, raw in files.items()}
    tree["bundle.json"] = canonical_json(bundle)

    def publish(staging: Path, destination: Path) -> None:
        publish_directory_no_replace(staging, destination, error_type=ValueError)

    write_tree(output, tree, error_type=ValueError, publish=publish)
    return output / "bundle.json"


def run(root: Path) -> None:
    for profile in (ResourceStatusProfile(), InventoryProfile()):
        for variant in ("pass", "fail", "missing", "conflict"):
            path = root / profile.tool / variant
            bundle = materialize(profile, path / "bundle", variant)
            import_evidence_bundle_v2(profile=profile, bundle_path=bundle, output=path / "import")
            try:
                receipt = evaluate_imported_case(profile, path / "import", path / "evaluation")
            except IngestionIntegrityError:
                if variant != "conflict":
                    raise
                print(profile.tool, variant, "evaluation_rejection")
                continue
            assert read_imported_evaluation(path / "evaluation", profile) == receipt
            report = read_evaluation_report(path / "evaluation", profile)
            assert report is not None and report.conclusion == receipt.case_outcome
            print(profile.tool, variant, receipt.case_outcome)


if __name__ == "__main__":
    run(Path(sys.argv[1]))
