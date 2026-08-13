"""Contract and canonicalization errors."""


class ContractError(ValueError):
    """Raised when versioned evaluator data is invalid."""


class DuplicateKeyError(ContractError):
    """Raised when JSON contains a duplicate object key."""


class UnsupportedVersionError(ContractError):
    """Raised when a contract schema version is unsupported."""
