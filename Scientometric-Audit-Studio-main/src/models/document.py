"""
Data model for a source Scopus document.
"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class SourceDocument:
    eid: str
    title: str
    year: Optional[int] = None
    source_title: str = ""
    doi: str = ""
    link: str = ""
    authors: str = ""
    author_full_names: str = ""
    author_ids: str = ""
    references_raw: str = ""
    parsed_reference_count: int = 0

