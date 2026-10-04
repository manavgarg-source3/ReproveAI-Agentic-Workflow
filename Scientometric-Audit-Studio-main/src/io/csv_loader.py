"""
CSV loader for Scopus exports.
"""
import csv
import logging
from pathlib import Path
from typing import List, Generator
from src.models.document import SourceDocument

logger = logging.getLogger(__name__)


def load_scopus_csv(file_path: Path) -> List[SourceDocument]:
    """
    Loads a Scopus export CSV into a list of SourceDocument objects.
    Handles UTF-8 BOM, missing columns, and empty fields cleanly.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Scopus CSV not found at: {file_path}")

    documents: List[SourceDocument] = []
    
    with open(file_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        
        # Verify required columns exist
        headers = reader.fieldnames or []
        required_cols = {"Title", "EID"}
        if not required_cols.issubset(set(headers)):
            raise ValueError(f"CSV missing mandatory columns. Found: {headers}")

        for row_idx, row in enumerate(reader, start=1):
            eid = (row.get("EID") or f"doc_{row_idx}").strip()
            title = (row.get("Title") or "").strip()
            
            # Year conversion
            year_str = (row.get("Year") or "").strip()
            year = None
            if year_str.isdigit():
                year = int(year_str)

            doc = SourceDocument(
                eid=eid,
                title=title,
                year=year,
                source_title=(row.get("Source title") or "").strip(),
                doi=(row.get("DOI") or "").strip(),
                link=(row.get("Link") or "").strip(),
                authors=(row.get("Authors") or "").strip(),
                author_full_names=(row.get("Author full names") or "").strip(),
                author_ids=(row.get("Author(s) ID") or "").strip(),
                references_raw=(row.get("References") or "").strip(),
            )
            documents.append(doc)

    logger.info(f"Loaded {len(documents)} documents from {file_path}")
    return documents

