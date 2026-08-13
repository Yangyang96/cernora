"""Failures raised by the local EvidenceBundle ingestion boundary."""


class IngestionError(ValueError):
    """Base class for local ingestion failures."""


class IngestionConfigurationError(IngestionError):
    """A caller-supplied path, profile, or output configuration is invalid."""


class IngestionIntegrityError(IngestionError):
    """Bundle, binding, artifact, or persisted package integrity is invalid."""


class AuthorityIncompatibleError(IngestionConfigurationError):
    """Stored evidence is incompatible with the evaluator's current authority."""

    code = "authority_incompatible"


class UnsupportedEvidenceVersionError(IngestionConfigurationError):
    """The requested consumer does not support the recognized evidence version."""

    code = "unsupported_evidence_version"


class ProfileEvidenceIntegrityError(IngestionIntegrityError):
    """Authoritative Profile result bytes do not satisfy their frozen format."""

    code = "profile_evidence_integrity"
