"""Small interfaces for source retrieval and evidence alignment."""

from dataclasses import dataclass
from typing import Protocol

from app.schemas.research import (
    Claim,
    ClaimAlignmentDecision,
    EvidenceItem,
    Reference,
    ReferenceValidation,
)


@dataclass(frozen=True)
class SourceEvidence:
    reference_id: str
    source: str | None
    title: str | None
    locator: str | None
    excerpt: str | None
    evidence_type: str


class SourceEvidenceProvider(Protocol):
    def retrieve(
        self,
        reference: Reference,
        validation: ReferenceValidation | None,
    ) -> SourceEvidence: ...


class ClaimEvidenceProvider(Protocol):
    def assess_claim(
        self,
        claim: Claim,
        evidence: list[EvidenceItem],
    ) -> ClaimAlignmentDecision: ...

    def close(self) -> None: ...
