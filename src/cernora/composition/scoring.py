"""Generic score helpers shared by profile adapters."""

from __future__ import annotations

from collections.abc import Iterable

from cernora.core.score import Score


def index_scores(scores: Iterable[Score]) -> dict[str, Score]:
    """Index scores by ID and reject ambiguous duplicate identities."""

    indexed: dict[str, Score] = {}
    for score in scores:
        if score.score_id in indexed:
            raise ValueError(f"duplicate score ID: {score.score_id}")
        indexed[score.score_id] = score
    return indexed
