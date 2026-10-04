"""
LLM Citation Extractor & Decomposer.
Deconstructs complex, malformed, or unstandardized bibliographic references into structured entities.
"""
import logging
import re
from typing import Dict, Any, Optional, List
from src.llm.client import LLMClient
from src.parsing.doi_extractor import extract_doi

logger = logging.getLogger(__name__)

CITATION_EXTRACTION_PROMPT = """
You are an expert bibliometric citation parser. 
Given a raw bibliographic reference from an academic paper, extract and return a valid JSON object containing the decomposed fields.

Raw Reference:
\"\"\"{raw_reference}\"\"\"

Return ONLY valid JSON with this exact schema:
{{
  "authors": "Comma-separated author names (e.g. Smith, J., Doe, A.)",
  "title": "Clean cited publication title without quotes",
  "journal": "Full journal name or conference venue",
  "year": 2020,
  "volume": "Volume number or null",
  "issue": "Issue number or null",
  "pages": "Page range e.g. 156-168 or article number or null",
  "doi": "Normalized DOI without https://doi.org/ or null",
  "document_type": "journal_article | conference_paper | book_chapter | book | preprint | patent | thesis | other"
}}
"""


class LLMCitationExtractor:
    """
    Deconstructs raw citation strings into structured entities using an LLM.
    """

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient.get_default()

    def parse(self, raw_reference: str) -> Dict[str, Any]:
        """
        Parses raw citation into structured fields.
        Falls back to rule extraction if LLM is unavailable.
        """
        if not raw_reference or not raw_reference.strip():
            return {
                "cited_authors": "",
                "cited_title": "",
                "cited_journal": "",
                "cited_volume": "",
                "cited_issue": "",
                "cited_pages": "",
                "cited_year": None,
                "extracted_doi": "",
                "document_type": "other",
            }

        clean_ref = raw_reference.strip()

        # Prompt LLM
        messages = [
            {"role": "system", "content": "You are a specialized bibliographic extraction system. Always reply with JSON."},
            {"role": "user", "content": CITATION_EXTRACTION_PROMPT.format(raw_reference=clean_ref)},
        ]

        resp = self.client.chat_completion(messages, temperature=0.0, max_tokens=500, json_mode=True)
        data = self.client.extract_json(resp)

        if data and isinstance(data, dict):
            # Normalize fields
            authors = data.get("authors") or ""
            if isinstance(authors, list):
                authors = ", ".join(str(a) for a in authors)

            year_val = data.get("year")
            parsed_year = None
            if year_val is not None:
                try:
                    y = int(year_val)
                    if 1800 <= y <= 2030:
                        parsed_year = y
                except (ValueError, TypeError):
                    pass

            doi_val = data.get("doi") or extract_doi(clean_ref) or ""
            if isinstance(doi_val, str) and doi_val.startswith("http"):
                m_doi = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", doi_val)
                if m_doi:
                    doi_val = m_doi.group(0)

            return {
                "cited_authors": str(authors).strip(),
                "cited_title": str(data.get("title") or "").strip().strip('"').strip("'"),
                "cited_journal": str(data.get("journal") or "").strip(),
                "cited_volume": str(data.get("volume") or "").strip() if data.get("volume") else "",
                "cited_issue": str(data.get("issue") or "").strip() if data.get("issue") else "",
                "cited_pages": str(data.get("pages") or "").strip() if data.get("pages") else "",
                "cited_year": parsed_year,
                "extracted_doi": str(doi_val).strip(),
                "document_type": str(data.get("document_type") or "other").strip(),
            }

        # Fallback if LLM failed
        return {
            "cited_authors": "",
            "cited_title": clean_ref,
            "cited_journal": "",
            "cited_volume": "",
            "cited_issue": "",
            "cited_pages": "",
            "cited_year": None,
            "extracted_doi": extract_doi(clean_ref) or "",
            "document_type": "other",
        }

