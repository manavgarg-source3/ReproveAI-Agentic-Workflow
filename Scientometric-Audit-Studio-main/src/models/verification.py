"""
Data models and taxonomy for reference verification results.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timezone


class FinalStatus(str, Enum):
    VALID_CORRECT = "VALID_CORRECT"
    VALID_REDIRECT_CORRECT = "VALID_REDIRECT_CORRECT"
    VALID_DOI_WRONG_REFERENCE = "VALID_DOI_WRONG_REFERENCE"
    INVALID_DOI = "INVALID_DOI"
    BROKEN_URL = "BROKEN_URL"
    ACCESS_RESTRICTED = "ACCESS_RESTRICTED"
    DOI_MISSING = "DOI_MISSING"
    DOI_RECOVERED = "DOI_RECOVERED"
    DOI_RECOVERY_UNCERTAIN = "DOI_RECOVERY_UNCERTAIN"
    SCOPUS_LINKED_NO_DOI = "SCOPUS_LINKED_NO_DOI"
    SCOPUS_UNLINKED = "SCOPUS_UNLINKED"
    METADATA_MISMATCH = "METADATA_MISMATCH"
    RETRACTED_REFERENCE = "RETRACTED_REFERENCE"
    AMBIGUOUS = "AMBIGUOUS"
    UNVERIFIED = "UNVERIFIED"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class CandidateMatch:
    doi: str
    title: str
    authors: str = ""
    year: Optional[int] = None
    journal: str = ""
    volume: str = ""
    pages: str = ""
    similarity_score: float = 0.0
    provider: str = ""


@dataclass
class VerificationResult:
    reference_id: str
    source_eid: str
    source_title: str = ""
    source_authors: str = ""
    source_year: Optional[int] = None
    source_doi: str = ""
    reference_no: int = 0
    raw_reference: str = ""
    
    # Scopus Ground Truth Verification
    scopus_linked: bool = False
    scopus_reference_link: str = ""
    scopus_id: str = ""
    
    # DOI and URL Verification
    extracted_doi: str = ""
    normalized_doi: str = ""
    doi_exists: bool = False
    doi_resolves: bool = False
    http_status: Optional[int] = None
    final_url: str = ""
    redirect_count: int = 0
    response_time_ms: Optional[float] = None
    
    # Metadata resolution
    metadata_source: str = ""  # crossref, openalex, scopus
    resolved_title: str = ""
    resolved_authors: str = ""
    resolved_journal: str = ""
    resolved_year: Optional[int] = None
    resolved_volume: str = ""
    resolved_issue: str = ""
    resolved_pages: str = ""
    is_retracted: bool = False
    
    # Matching Scores
    title_similarity: float = 0.0
    author_similarity: float = 0.0
    journal_similarity: float = 0.0
    year_match: bool = False
    volume_match: bool = False
    pages_match: bool = False
    composite_score: float = 0.0
    
    # Final Decision
    confidence: ConfidenceLevel = ConfidenceLevel.UNCERTAIN
    final_status: FinalStatus = FinalStatus.UNVERIFIED
    decision_rationale: str = ""
    needs_human_review: bool = False
    
    # Audit info
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "source_eid": self.source_eid,
            "source_title": self.source_title,
            "source_authors": self.source_authors,
            "source_year": self.source_year,
            "source_doi": self.source_doi,
            "reference_no": self.reference_no,
            "scopus_link_valid": self.scopus_linked,
            "scopus_reference_link": self.scopus_reference_link,
            "scopus_id": self.scopus_id,
            "raw_reference": self.raw_reference,
            "extracted_doi": self.extracted_doi,
            "normalized_doi": self.normalized_doi,
            "doi_exists": self.doi_exists,
            "doi_resolves": self.doi_resolves,
            "http_status": self.http_status,
            "final_url": self.final_url,
            "redirect_count": self.redirect_count,
            "response_time_ms": self.response_time_ms,
            "metadata_source": self.metadata_source,
            "resolved_title": self.resolved_title,
            "resolved_authors": self.resolved_authors,
            "resolved_journal": self.resolved_journal,
            "resolved_year": self.resolved_year,
            "is_retracted": self.is_retracted,
            "title_similarity": round(self.title_similarity, 3),
            "author_similarity": round(self.author_similarity, 3),
            "journal_similarity": round(self.journal_similarity, 3),
            "year_match": self.year_match,
            "volume_match": self.volume_match,
            "pages_match": self.pages_match,
            "composite_score": round(self.composite_score, 3),
            "metadata_confidence": self.confidence.value,
            "confidence": self.confidence.value,
            "final_status": self.final_status.value,
            "decision_rationale": self.decision_rationale,
            "needs_human_review": self.needs_human_review,
            "checked_at": self.checked_at,
        }

