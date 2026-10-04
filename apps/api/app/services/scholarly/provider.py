"""Provider-neutral contract for deterministic bibliographic validation."""

from typing import Protocol

from app.schemas.research import Reference, ReferenceValidation


class ScholarlyEvidenceProvider(Protocol):
    """Validate a paper reference against scholarly metadata sources."""

    def validate_reference(self, reference: Reference) -> ReferenceValidation:
        """Return deterministic bibliographic evidence for one reference."""
        ...

