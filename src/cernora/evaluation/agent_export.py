"""Strict offline inspection; does not publish an EvidenceBundle or task-quality gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cernora.core.agent_run import AgentRunExport, evaluate_run_state, score_claims, summarize_run
from cernora.core.canonical import decode_contract
from cernora.core.errors import ContractError


def load_agent_run_export(source: str | Path | bytes) -> AgentRunExport:
    """Path reads a file; str/bytes contain JSON. Duplicate keys are rejected."""
    try:
        raw = source.read_bytes() if isinstance(source, Path) else source
        return decode_contract(raw, AgentRunExport)
    except OSError as exc:
        raise ContractError("cannot read agent run export") from exc


def inspect_agent_run(
    source: str | Path | bytes,
    *,
    reference_available: bool = False,
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonicalizable observations, with no side effects and no overall pass verdict.

    The legacy reference_available flag is retained but cannot supply a reference.
    """
    run = load_agent_run_export(source)
    return {
        "run_id": run.run_id,
        "case_id": run.case_id,
        "state": evaluate_run_state(run, reference_available=bool(reference)),
        **summarize_run(run),
        "claims": score_claims(run, reference),
    }
