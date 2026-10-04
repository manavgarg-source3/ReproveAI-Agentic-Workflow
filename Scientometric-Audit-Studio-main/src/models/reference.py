"""
Data model for a parsed reference record.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class ParsedReference:
    source_eid: str
    reference_no: int
    raw_reference: str
    source_title: str = ""
    source_authors: str = ""
    source_year: Optional[int] = None
    source_doi: str = ""
    
    # Scopus Ground Truth Reference info
    scopus_linked: bool = False
    scopus_reference_link: str = ""
    scopus_id: str = ""
    
    # Bibliographic fields extracted from raw_reference
    cited_title: str = ""
    cited_authors: str = ""
    cited_year: Optional[int] = None
    cited_journal: str = ""
    cited_volume: str = ""
    cited_issue: str = ""
    cited_pages: str = ""
    
    # Extracted identifiers
    extracted_doi: str = ""
    extracted_url: str = ""
    
    # Quality & Diagnostic flags
    has_year: bool = False
    has_doi: bool = False
    has_url: bool = False
    year_marker_count: int = 0
    reference_year_detected: str = ""
    needs_review: bool = False
    review_reasons: List[str] = field(default_factory=list)

    @property
    def reference_id(self) -> str:
        """Unique deterministic identifier: source_eid:ref_num"""
        return f"{self.source_eid}_{self.reference_no:04d}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "source_eid": self.source_eid,
            "source_title": self.source_title,
            "source_authors": self.source_authors,
            "source_year": self.source_year,
            "source_doi": self.source_doi,
            "reference_no": self.reference_no,
            "raw_reference": self.raw_reference,
            "cited_title": self.cited_title,
            "cited_authors": self.cited_authors,
            "cited_year": self.cited_year,
            "cited_journal": self.cited_journal,
            "cited_volume": self.cited_volume,
            "cited_issue": self.cited_issue,
            "cited_pages": self.cited_pages,
            "extracted_doi": self.extracted_doi,
            "extracted_url": self.extracted_url,
            "has_year": self.has_year,
            "has_doi": self.has_doi,
            "has_url": self.has_url,
            "year_marker_count": self.year_marker_count,
            "reference_year_detected": self.reference_year_detected,
            "needs_review": self.needs_review,
            "review_reasons": "; ".join(self.review_reasons) if self.review_reasons else "",
        }

