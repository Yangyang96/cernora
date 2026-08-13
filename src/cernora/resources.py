"""Stable access to wheel-packaged public schemas."""

from importlib.resources import files

PUBLIC_SCHEMAS = (
    "case-profile-v1.schema.json",
    "evidence-bundle-v2.schema.json",
    "evidence-v1.schema.json",
    "gate-decision-v1.schema.json",
    "import-manifest-v2.schema.json",
    "import-receipt-v2.schema.json",
    "imported-evaluation-authority-v1.schema.json",
    "imported-evaluation-manifest-v1.schema.json",
    "imported-evaluation-receipt-v1.schema.json",
    "score-v1.schema.json",
)


def read_public_schema(name: str) -> bytes:
    """Read one explicitly supported schema from package resources."""

    if name not in PUBLIC_SCHEMAS:
        raise ValueError(f"unsupported public schema: {name}")
    return files("cernora.schemas").joinpath(name).read_bytes()


__all__ = ["PUBLIC_SCHEMAS", "read_public_schema"]
