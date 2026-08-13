"""Strict JSON decoding and stable canonical serialization."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ValidationError

from cernora.core.errors import ContractError, DuplicateKeyError


def _object_without_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON number is forbidden: {value}")


def strict_json_loads(raw: str | bytes) -> Any:
    """Decode one complete JSON value with duplicate and non-finite checks."""

    try:
        return json.loads(
            raw,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc


def decode_contract[ModelT: BaseModel](raw: str | bytes, model: type[ModelT]) -> ModelT:
    """Strictly decode JSON into a versioned Pydantic contract."""

    strict_json_loads(raw)
    try:
        return model.model_validate_json(raw, strict=True)
    except ValidationError as exc:
        raise ContractError(str(exc)) from exc


def canonical_json(value: BaseModel | Any) -> bytes:
    """Return byte-stable UTF-8 JSON with sorted keys and no insignificant space."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=False)
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ContractError(f"value is not canonicalizable JSON: {exc}") from exc
    return encoded.encode("utf-8")
