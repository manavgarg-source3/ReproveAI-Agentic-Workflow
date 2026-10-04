"""
LLM Discrepancy & Hallucination Auditor.
Semantically compares cited bibliographic entries against authoritative Crossref/Scopus registry metadata.
Accurately classifies VALID_DOI_WRONG_REFERENCE, acceptable title variances, and fabricated AI citations.
"""
import logging
from typing import Dict, Any, Optional
from src.llm.client import LLMClient

logger = logging.getLogger(__name__)

DISCREPANCY_AUDIT_PROMPT = """
You are a forensic scientometric peer-review auditor. 
Evaluate whether the CITED REFERENCE from a scholarly manuscript matches the RESOLVED METADATA retrieved from Crossref / Scopus.

CITED IN MANUSCRIPT:
- Raw Citation: \"\"\"{raw_reference}\"\"\"
- Cited Title: \"{cited_title}\"
- Cited Authors: \"{cited_authors}\"
- Cited Year: {cited_year}
- Cited Venue: \"{cited_journal}\"
- Explicit DOI Cited: \"{cited_doi}\"

REGISTRY METADATA (Crossref / Scopus / OpenAlex):
- Registry Title: \"{resolved_title}\"
- Registry Authors: \"{resolved_authors}\"
- Registry Year: {resolved_year}
- Registry Venue: \"{resolved_journal}\"
- Registry DOI: \"{resolved_doi}\"
- HTTP Resolution Status: {http_status}

Analyze the intellectual match. 
Note: Minor differences like subtitle omissions, journal abbreviations (e.g. 'IEEE TPAMI' vs 'IEEE Transactions on Pattern Analysis'), or minor translation spelling do NOT constitute a wrong reference.
However, if the DOI points to a completely different paper on a different topic or by different authors, this is VALID_DOI_WRONG_REFERENCE.
If the reference contains plausible-sounding titles and authors that appear entirely fabricated/hallucinated, flag it.

Return ONLY a valid JSON object matching this schema:
{{
  "decision": "MATCH_CONFIRMED | VALID_DOI_WRONG_REFERENCE | HALLUCINATED_CITATION | UNCERTAIN",
  "confidence": 0.95,
  "reasoning": "Clear, concise 1-2 sentence forensic explanation.",
  "recommendation": "AUTO_APPROVE | FLAG_WRONG_DOI | FLAG_HALLUCINATION | HUMAN_REVIEW"
}}
"""


class LLMDiscrepancyAuditor:
    """
    Forensic auditor for bibliographic discrepancies using LLM semantic reasoning.
    """

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient.get_default()

    def audit(
        self,
        cited_data: Dict[str, Any],
        resolved_data: Dict[str, Any],
        http_status: Optional[int] = 200,
    ) -> Dict[str, Any]:
        """
        Audits semantic match between cited reference and resolved registry metadata.
        """
        raw_ref = cited_data.get("raw_reference") or ""
        cited_title = cited_data.get("cited_title") or cited_data.get("title") or ""
        cited_authors = cited_data.get("cited_authors") or ""
        cited_year = cited_data.get("cited_year") or "null"
        cited_journal = cited_data.get("cited_journal") or ""
        cited_doi = cited_data.get("extracted_doi") or cited_data.get("normalized_doi") or ""

        resolved_title = resolved_data.get("title") or resolved_data.get("resolved_title") or ""
        resolved_authors = resolved_data.get("authors") or resolved_data.get("resolved_authors") or ""
        resolved_year = resolved_data.get("year") or resolved_data.get("resolved_year") or "null"
        resolved_journal = resolved_data.get("journal") or resolved_data.get("resolved_journal") or ""
        resolved_doi = resolved_data.get("doi") or resolved_data.get("normalized_doi") or ""

        # If both titles are missing, fallback
        if not cited_title and not raw_ref:
            return {
                "decision": "UNCERTAIN",
                "confidence": 0.0,
                "reasoning": "Insufficient citation metadata to perform semantic audit.",
                "recommendation": "HUMAN_REVIEW",
            }

        prompt = DISCREPANCY_AUDIT_PROMPT.format(
            raw_reference=raw_ref,
            cited_title=cited_title,
            cited_authors=cited_authors,
            cited_year=cited_year,
            cited_journal=cited_journal,
            cited_doi=cited_doi,
            resolved_title=resolved_title,
            resolved_authors=resolved_authors,
            resolved_year=resolved_year,
            resolved_journal=resolved_journal,
            resolved_doi=resolved_doi,
            http_status=http_status or 200,
        )

        messages = [
            {"role": "system", "content": "You are an expert scientometric forensic auditor. Respond only in JSON."},
            {"role": "user", "content": prompt},
        ]

        resp = self.client.chat_completion(messages, temperature=0.0, max_tokens=350, json_mode=True)
        data = self.client.extract_json(resp)

        if data and isinstance(data, dict):
            decision = str(data.get("decision", "UNCERTAIN")).upper().strip()
            confidence = float(data.get("confidence", 0.5))
            reasoning = str(data.get("reasoning", "")).strip()
            recommendation = str(data.get("recommendation", "HUMAN_REVIEW")).upper().strip()

            return {
                "decision": decision,
                "confidence": min(1.0, max(0.0, confidence)),
                "reasoning": reasoning or "Automated semantic evaluation completed.",
                "recommendation": recommendation,
            }

        # Fallback if LLM unavailable
        return {
            "decision": "UNCERTAIN",
            "confidence": 0.5,
            "reasoning": "LLM auditor unavailable; fallback to heuristic match scores.",
            "recommendation": "HUMAN_REVIEW",
        }

