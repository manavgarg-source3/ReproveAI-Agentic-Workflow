"""
Scientometric Synthesizer & Executive Audit Generator.
Computes mathematical scientometric indicators (Price Index, citation half-life, venue diversity)
and uses LLM reasoning to produce an authoritative Executive Scientometric Audit report.
"""
import math
import logging
from typing import Dict, Any, List, Optional
from collections import Counter
from datetime import datetime

from src.llm.client import LLMClient

logger = logging.getLogger(__name__)
import re
from datetime import datetime

EXECUTIVE_SYNTHESIS_PROMPT = """
You are a senior scientometric editor and peer-review auditor. 
Synthesize an authoritative Executive Scientometric Audit Report for the provided manuscript bibliography.

MANUSCRIPT METADATA:
- Estimated Title: \"{doc_title}\"
- Total References: {total_refs}
- Citation Style Detected: {citation_style}
- In-Text Citation Consistency: {consistency_score}% (Orphans: {orphan_count}, Missing: {missing_count})

SCIENTOMETRIC METRICS:
SCIENTOMETRIC INDICATORS:
- Price's Index (Literature Freshness <= 5 years): {price_index}%
- Median Citation Age (Half-Life): {median_age} years
- Year Range: {min_year} - {max_year}
- Top Cited Venues: {top_venues}
- Citation Stances: {intent_breakdown}

CITATION INTEGRITY & VERIFICATION:
- Resolving DOIs: {resolving_dois} / {total_refs}
- Fabricated / Broken DOIs (HTTP 404): {invalid_doi_count}
- Semantic Discrepancies: {discrepancies_count}
- Integrity Alert: {integrity_alert}

REFERENCES SAMPLE (First 15):
{references_sample}

Analyze the intellectual pedigree and bibliographic health of this paper.
Analyze the intellectual pedigree, recency, and bibliographic health of this paper.
CRITICAL INSTRUCTION: If there are broken / fabricated 404 DOIs, or semantic discrepancies, explicitly call them out in the executive summary as evidence of potential hallucinated citations (characteristic of unverified generative AI assistance) and assign an appropriate audit grade ('C' or 'REQUIRES_REVISION').

Return ONLY a valid JSON object matching this schema:
{{
  "executive_summary": "Comprehensive 2-paragraph scientometric critique of the manuscript's literature grounding.",
  "methodological_backbone": "Identification of the core methods, foundational algorithms, or tools the paper relies upon.",
  "temporal_freshness_verdict": "CUTTING_EDGE | BALANCED | DATED_OBSOLESCENT",
  "temporal_analysis": "1-2 sentence commentary on the citation age distribution and Price's Index.",
  "diversity_and_coverage": "Commentary on venue diversity and interdisciplinary breadth.",
  "potential_blind_spots": [
    "Specific observation on literature gaps, lack of recent baselines, or overreliance on specific labs/venues."
  ],
  "audit_grade": "A+ | A | B | C | REQUIRES_REVISION"
}}
"""


class ScientometricSynthesizer:
    """
    Computes standard scientometric indicators and generates LLM-powered executive audit synthesis.
    """

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient.get_default()

    @staticmethod
    def compute_indicators(references: List[Dict[str, Any]], current_year: int = 2026) -> Dict[str, Any]:
        """
        Computes formal scientometric metrics across the reference collection.
        """
        total = len(references)
        if total == 0:
            return {
                "total_references": 0,
                "dated_references_count": 0,
                "price_index": 0.0,
                "median_citation_age": 0.0,
                "min_year": None,
                "max_year": None,
                "venue_diversity_score": 0.0,
                "intent_distribution": {},
                "top_venues": [],
                "resolving_dois": 0,
                "invalid_dois": 0,
                "discrepancies": 0,
                "hallucinated_citation_risk": "LOW",
            }

        years: List[int] = []
        venues: List[str] = []
        intents: List[str] = []
        year_regex = re.compile(r"\b(19\d\d|20[0-2]\d)\b")

        for r in references:
            y = r.get("cited_year") or r.get("resolved_year") or r.get("year")
            if not y and r.get("raw_reference"):
                matches = year_regex.findall(str(r.get("raw_reference", "")))
                if matches:
                    y = matches[-1]
            if y:
                try:
                    y_int = int(y)
                    if 1900 <= y_int <= current_year:
                        years.append(y_int)
                except (ValueError, TypeError):
                    pass

            v = (r.get("cited_journal") or r.get("resolved_journal") or r.get("journal") or "").strip()
            if v and len(v) > 2 and v.lower() not in ("unknown", "n/a", "{}"):
                venues.append(v)

            intent = r.get("citation_intent") or "BACKGROUND"
            intents.append(intent)

        # 1. Price's Index: % of references published within the last 5 years
        # (Derek de Solla Price standard indicator)
        five_year_cutoff = current_year - 5
        recent_refs = sum(1 for y in years if y >= five_year_cutoff)
        price_index = round((recent_refs / len(years) * 100.0), 1) if years else 0.0

        # 2. Citation Half-Life (Median Age)
        if years:
            sorted_years = sorted(years)
            n = len(sorted_years)
            if n % 2 == 1:
                median_year = sorted_years[n // 2]
            else:
                median_year = (sorted_years[n // 2 - 1] + sorted_years[n // 2]) / 2.0
            median_age = round(max(0.0, current_year - median_year), 1)
            min_year = sorted_years[0]
            max_year = sorted_years[-1]
        else:
            median_age = 0.0
            min_year = None
            max_year = None

        # 3. Venue Diversity (Normalized Shannon Entropy: 0.0 to 1.0)
        venue_counts = Counter(venues)
        if len(venues) > 1 and len(venue_counts) > 1:
            total_venues = len(venues)
            entropy = -sum((c / total_venues) * math.log(c / total_venues) for c in venue_counts.values())
            max_entropy = math.log(len(venue_counts))
            diversity = round(entropy / max_entropy if max_entropy > 0 else 1.0, 2)
        else:
            diversity = 1.0 if venues else 0.0

        top_venues = [f"{v} ({c})" for v, c in venue_counts.most_common(5)]
        intent_counts = dict(Counter(intents))

        # 4. Integrity Counts
        invalid_dois = sum(1 for r in references if r.get("final_status") == "INVALID_DOI" or str(r.get("http_status")) == "404")
        resolving_dois = sum(1 for r in references if (r.get("doi_resolves") is True or str(r.get("doi_resolves", "")).lower() == "true"))
        discrepancies = sum(1 for r in references if r.get("final_status") == "VALID_DOI_WRONG_REFERENCE")
        hallucination_risk = "HIGH" if invalid_dois >= 3 else ("MEDIUM" if invalid_dois >= 1 else "LOW")

        return {
            "total_references": total,
            "dated_references_count": len(years),
            "price_index": price_index,
            "median_citation_age": median_age,
            "min_year": min_year,
            "max_year": max_year,
            "venue_diversity_score": diversity,
            "intent_distribution": intent_counts,
            "top_venues": top_venues,
            "resolving_dois": resolving_dois,
            "invalid_dois": invalid_dois,
            "discrepancies": discrepancies,
            "hallucinated_citation_risk": hallucination_risk,
        }

    def generate_executive_audit(
        self,
        doc_title: str,
        references: List[Dict[str, Any]],
        document_diagnostics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Synthesizes indicators and LLM narrative critique into an executive audit card.
        """
        diag = document_diagnostics or {}
        indicators = self.compute_indicators(references)

        # Prepare snippet sample for the LLM
        sample_lines = []
        for i, r in enumerate(references[:15], 1):
            title = r.get("title") or r.get("cited_title") or r.get("raw_reference") or ""
            authors = r.get("cited_authors") or ""
            yr = r.get("cited_year") or r.get("year") or ""
            sample_lines.append(f"[{i}] {authors} ({yr}). {title[:80]}...")
            title = r.get("title") or r.get("cited_title") or r.get("resolved_title") or r.get("raw_reference") or ""
            authors = r.get("cited_authors") or r.get("resolved_authors") or ""
            yr = r.get("cited_year") or r.get("resolved_year") or r.get("year") or ""
            st = r.get("final_status", "")
            sample_lines.append(f"[{i}] {authors} ({yr}). {title[:75]}... [Status: {st}]")

        sample_text = "\n".join(sample_lines) if sample_lines else "No references extracted."

        inv_cnt = indicators.get("invalid_dois", 0)
        disc_cnt = indicators.get("discrepancies", 0)
        if inv_cnt > 0 or disc_cnt > 0:
            integrity_alert = f"CRITICAL: {inv_cnt} citations failed with HTTP 404 (non-existent/hallucinated DOIs) and {disc_cnt} citations resolved to mismatched works."
        else:
            integrity_alert = "All examined DOIs resolved normally."

        prompt = EXECUTIVE_SYNTHESIS_PROMPT.format(
            doc_title=doc_title or "Uploaded Manuscript",
            total_refs=len(references),
            citation_style=diag.get("citation_style_display") or diag.get("citation_style") or "Automated Detection",
            consistency_score=diag.get("consistency_score", 100),
            orphan_count=diag.get("orphan_count", 0),
            missing_count=diag.get("missing_count", 0),
            price_index=indicators["price_index"],
            median_age=indicators["median_citation_age"],
            min_year=indicators["min_year"] or "N/A",
            max_year=indicators["max_year"] or "N/A",
            top_venues=", ".join(indicators["top_venues"][:3]) or "Diverse academic sources",
            intent_breakdown=str(indicators["intent_distribution"]),
            resolving_dois=indicators["resolving_dois"],
            invalid_doi_count=inv_cnt,
            discrepancies_count=disc_cnt,
            integrity_alert=integrity_alert,
            references_sample=sample_text,
        )

        messages = [
            {"role": "system", "content": "You are a senior scientometric editor. Always respond in JSON."},
            {"role": "user", "content": prompt},
        ]

        resp = self.client.chat_completion(messages, temperature=0.1, max_tokens=700, json_mode=True)
        data = self.client.extract_json(resp)

        if data and isinstance(data, dict):
            return {
                "indicators": indicators,
                "executive_summary": data.get("executive_summary", "Audit completed."),
                "methodological_backbone": data.get("methodological_backbone", ""),
                "temporal_freshness_verdict": data.get("temporal_freshness_verdict", "BALANCED"),
                "temporal_analysis": data.get("temporal_analysis", ""),
                "diversity_and_coverage": data.get("diversity_and_coverage", ""),
                "potential_blind_spots": data.get("potential_blind_spots", []),
                "audit_grade": data.get("audit_grade", "A"),
            }

        # Deterministic fallback report if LLM unavailable
        p_idx = indicators["price_index"]
        verdict = "CUTTING_EDGE" if p_idx >= 50 else ("BALANCED" if p_idx >= 25 else "DATED_OBSOLESCENT")
        if inv_cnt >= 3:
            grade = "REQUIRES_REVISION"
        elif inv_cnt >= 1 or disc_cnt >= 1:
            grade = "C"
        elif diag.get("consistency_score", 100) >= 90:
            grade = "A"
        else:
            grade = "B"

        summary = (
            f"Bibliometric analysis completed across {len(references)} references. "
            f"The manuscript exhibits a Price's Index of {p_idx}% (citations from the last 5 years), "
            f"with a median citation age of {indicators['median_citation_age']} years."
        )
        if inv_cnt > 0:
            summary += f" Critical finding: {inv_cnt} citations have DOIs that return HTTP 404 (non-existent), indicating synthetic or severely malformed citations."

        return {
            "indicators": indicators,
            "executive_summary": (
                f"Bibliometric analysis completed across {len(references)} references. "
                f"The manuscript exhibits a Price's Index of {p_idx}% (citations from the last 5 years), "
                f"with a median citation age of {indicators['median_citation_age']} years."
            ),
            "executive_summary": summary,
            "methodological_backbone": "Foundational literature and standard domain references.",
            "temporal_freshness_verdict": verdict,
            "temporal_analysis": f"Citations span from {indicators['min_year']} to {indicators['max_year']}.",
            "diversity_and_coverage": f"Venue diversity score: {indicators['venue_diversity_score']}.",
            "potential_blind_spots": ["Ensure recent preprints and emerging benchmarks are represented."],
            "audit_grade": "A" if diag.get("consistency_score", 100) >= 90 else "B",
            "potential_blind_spots": [
                "Verify citations returning HTTP 404 on doi.org." if inv_cnt > 0 else "Ensure recent preprints and emerging benchmarks are represented."
            ],
            "audit_grade": grade,
        }

