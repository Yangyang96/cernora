"""Generate the public Priority 4 batch and comparison JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from cernora.batch import BatchInput, BatchSummary
from cernora.comparison import ComparisonInput, ComparisonSummary

ROOT = Path(__file__).parents[1]
SCHEMA_ROOT = ROOT / "src" / "cernora" / "schemas"


def _schema(model: type[BaseModel], *, identifier: str) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = identifier
    return schema


def main() -> None:
    schemas = {
        "batch-input-v1.schema.json": _schema(
            BatchInput,
            identifier="https://cernora.dev/schemas/batch-input-v1.schema.json",
        ),
        "batch-summary-v1.schema.json": _schema(
            BatchSummary,
            identifier="https://cernora.dev/schemas/batch-summary-v1.schema.json",
        ),
        "comparison-input-v1.schema.json": _schema(
            ComparisonInput,
            identifier="https://cernora.dev/schemas/comparison-input-v1.schema.json",
        ),
        "comparison-summary-v1.schema.json": _schema(
            ComparisonSummary,
            identifier="https://cernora.dev/schemas/comparison-summary-v1.schema.json",
        ),
    }
    for name, schema in schemas.items():
        (SCHEMA_ROOT / name).write_text(
            json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
