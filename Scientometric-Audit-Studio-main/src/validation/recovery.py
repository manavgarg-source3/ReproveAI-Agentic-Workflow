"""
Missing DOI recovery engine.
Searches Crossref, OpenAlex, and Scopus to discover intended DOIs for citations with missing DOIs.
Includes provider availability checks, rate-limit fallback, and multi-registry ranking.
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from src.providers.crossref import CrossrefClient
from src.providers.openalex import OpenAlexClient
from src.providers.scopus import ScopusClient
from src.matching.metadata_matcher import MetadataMatcher

logger = logging.getLogger(__name__)


class DOIRecoveryEngine:
    """
    Recovers missing DOIs by querying bibliographic registries.
    """

    def __init__(
        self,
        crossref: Optional[CrossrefClient] = None,
        openalex: Optional[OpenAlexClient] = None,
        scopus: Optional[ScopusClient] = None,
    ):
        self.crossref = crossref or CrossrefClient()
        self.openalex = openalex or OpenAlexClient()
        self.scopus = scopus or ScopusClient()

    def recover(self, cited_data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Searches registries for the cited work.
        Returns (best_candidate_metadata, match_scores_dict).
        """
        title = (cited_data.get("cited_title") or "").strip()
        authors = (cited_data.get("cited_authors") or "").strip()
        year = cited_data.get("cited_year")

        if not title or len(title) < 10:
            return None, {"composite_score": 0.0, "title_similarity": 0.0}

        query = f"{authors} {title}".strip()
        candidates: List[Dict[str, Any]] = []

        # 1. Scopus Search (fastest & high-quota authorized institutional API)
        if self.scopus.is_available():
            try:
                sc_results = self.scopus.search_by_title_and_author(title, authors, count=2)
                candidates.extend(sc_results)
            except Exception as e:
                logger.warning(f"Scopus search error: {e}")

        # If Scopus already found a candidate with DOI, evaluate early
        for cand in candidates:
            if cand.get("doi"):
                scores = MetadataMatcher.evaluate(cited_data, cand)
                if scores["composite_score"] >= 0.85:
                    return cand, scores

        # 2. Crossref Search (if available and not cooling down)
        if self.crossref.is_available():
            try:
                cr_results = self.crossref.search_bibliographic(query, rows=3)
                candidates.extend(cr_results)
            except Exception as e:
                logger.warning(f"Crossref search error: {e}")

        # 3. OpenAlex Search (if available and not cooling down)
        if self.openalex.is_available() and len(candidates) < 3:
            try:
                oa_results = self.openalex.search_by_title(title, rows=3)
                candidates.extend(oa_results)
            except Exception as e:
                logger.warning(f"OpenAlex search error: {e}")

        if not candidates:
            return None, {"composite_score": 0.0, "title_similarity": 0.0}

        # Evaluate all candidate metadata against cited fields
        best_candidate: Optional[Dict[str, Any]] = None
        best_scores: Dict[str, Any] = {"composite_score": 0.0, "title_similarity": 0.0}

        for cand in candidates:
            doi = cand.get("doi")
            if not doi:
                continue
            scores = MetadataMatcher.evaluate(cited_data, cand)
            if scores["composite_score"] > best_scores.get("composite_score", 0.0):
                best_scores = scores
                best_candidate = cand

        return best_candidate, best_scores
