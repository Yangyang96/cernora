"""Preview completed-export Adapter interface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CompletedExport:
    """One already terminal ordinary-file export supplied by a third party."""

    root: Path


@dataclass(frozen=True)
class AdaptedBundle:
    """Paths to one normalized EvidenceBundle v2 and its sibling artifacts."""

    bundle_path: Path


@runtime_checkable
class Adapter(Protocol):
    """Normalize completed local files without execution, credentials or network."""

    def adapt(self, completed_export: CompletedExport, output: Path) -> AdaptedBundle: ...


__all__ = ["AdaptedBundle", "Adapter", "CompletedExport"]
