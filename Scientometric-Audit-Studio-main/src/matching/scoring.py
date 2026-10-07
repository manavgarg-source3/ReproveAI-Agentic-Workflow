"""
Confidence scoring and taxonomy decision engine.
Assigns confidence bands and final status taxonomies based on multi-factor evidence.
"""
from typing import Dict, Any, Tuple, Optional
from config import HIGH_CONFIDENCE_THRESHOLD, MEDIUM_CONFIDENCE_THRESHOLD, WRONG_DOI_THRESHOLD
from src.models.verification import FinalStatus, ConfidenceLevel


class DecisionEngine:
    """
    Evaluates evidence vectors and classifies reference verification status.
    """

    @classmethod
    def classify_with_doi(
        cls,
        match_scores: Dict[str, Any],
        resolver_result: Dict[str, Any],
        is_retracted: bool = False,
    ) -> Tuple[FinalStatus, ConfidenceLevel, str, bool]:
        """
        Classifies references that had an explicit DOI.
        Returns (final_status, confidence, rationale, needs_human_review).
        """
        composite = match_scores.get("composite_score", 0.0)
        title_sim = match_scores.get("title_similarity", 0.0)
        doi_exists = resolver_result.get("doi_exists", False)
        doi_resolves = resolver_result.get("doi_resolves", False)
        http_status = resolver_result.get("http_status")
        redirects = resolver_result.get("redirect_count", 0)
        strong_core_match = (
            title_sim >= 0.95
            and match_scores.get("author_similarity", 0.0) >= 0.55
            and match_scores.get("year_match", False)
            and composite >= 0.75
        )

        # 1. DOI does not exist
        if not doi_exists or http_status == 404:
            return (
                FinalStatus.INVALID_DOI,
                ConfidenceLevel.HIGH,
                "DOI does not exist on resolver (HTTP 404).",
                True,
            )

        # 2. Retracted Reference
        if is_retracted and composite >= HIGH_CONFIDENCE_THRESHOLD:
            return (
                FinalStatus.RETRACTED_REFERENCE,
                ConfidenceLevel.HIGH,
                "Cited publication exists and matches reference but has been retracted.",
                True,
            )

        # 3. CRITICAL CASE: VALID DOI BUT WRONG REFERENCE
        # The DOI resolves, but the metadata does not match what the authors cited!
        if doi_resolves and (composite < WRONG_DOI_THRESHOLD or title_sim < 0.35):
            return (
                FinalStatus.VALID_DOI_WRONG_REFERENCE,
                ConfidenceLevel.HIGH if title_sim < 0.25 else ConfidenceLevel.MEDIUM,
                f"DOI resolves successfully (HTTP {http_status}) but points to a different work (Title similarity: {title_sim:.2f}, Composite: {composite:.2f}).",
                True,
            )

        # 4. HTTP Access Restricted (paywall/bot challenge)
        if http_status in (401, 403):
            if composite >= MEDIUM_CONFIDENCE_THRESHOLD:
                return (
                    FinalStatus.ACCESS_RESTRICTED,
                    ConfidenceLevel.HIGH if composite >= HIGH_CONFIDENCE_THRESHOLD else ConfidenceLevel.MEDIUM,
                    f"DOI metadata matches (score {composite:.2f}), but web access returned HTTP {http_status} (protected by auth/bot-check).",
                    False if composite >= HIGH_CONFIDENCE_THRESHOLD else True,
                )
            else:
                return (
                    FinalStatus.ACCESS_RESTRICTED,
                    ConfidenceLevel.UNCERTAIN,
                    f"Web access restricted (HTTP {http_status}) and metadata match uncertain (score {composite:.2f}).",
                    True,
                )

        # 5. Broken URL destination
        if not doi_resolves and http_status and http_status >= 400:
            return (
                FinalStatus.BROKEN_URL,
                ConfidenceLevel.MEDIUM,
                f"DOI resolution failed with HTTP status {http_status}.",
                True,
            )

        # 6. Correct Match
        if composite >= HIGH_CONFIDENCE_THRESHOLD or strong_core_match:
            if redirects > 0:
                return (
                    FinalStatus.VALID_REDIRECT_CORRECT,
                    ConfidenceLevel.HIGH,
                    f"Valid DOI matching citation metadata (score {composite:.2f}) with {redirects} redirect(s).",
                    False,
                )
            return (
                FinalStatus.VALID_CORRECT,
                ConfidenceLevel.HIGH,
                f"Valid DOI directly resolving and matching citation metadata (score {composite:.2f}).",
                False,
            )

        # 7. Borderline / Ambiguous
        if composite >= MEDIUM_CONFIDENCE_THRESHOLD:
            return (
                FinalStatus.METADATA_MISMATCH,
                ConfidenceLevel.MEDIUM,
                f"DOI resolves, but citation metadata has partial discrepancies (score {composite:.2f}).",
                True,
            )

        return (
            FinalStatus.AMBIGUOUS,
            ConfidenceLevel.LOW,
            f"Ambiguous bibliographic correspondence (score {composite:.2f}).",
            True,
        )

    @classmethod
    def semantic_audit(
        cls,
        cited_data: Dict[str, Any],
        resolved_data: Dict[str, Any],
        http_status: int = 200,
    ) -> Optional[Dict[str, Any]]:
        """
        Invokes LLMDiscrepancyAuditor to resolve borderline, ambiguous, or suspected wrong DOI cases.
        Returns dict with decision, confidence, reasoning, and recommendation.
        """
        from config import ENABLE_LLM_FALLBACK
        if not ENABLE_LLM_FALLBACK:
            return None
        try:
            from src.llm.discrepancy_auditor import LLMDiscrepancyAuditor
            from src.llm.client import LLMClient
            client = LLMClient.get_default()
            if client.is_available():
                return LLMDiscrepancyAuditor(client).audit(cited_data, resolved_data, http_status)
        except Exception:
            pass
        return None

    @classmethod
    def classify_recovered_doi(
        cls,
        match_scores: Dict[str, Any],
        candidate_meta: Dict[str, Any],
        resolver_result: Dict[str, Any],
    ) -> Tuple[FinalStatus, ConfidenceLevel, str, bool]:
        """
        Classifies references where DOI was missing and recovery was attempted.
        """
        composite = match_scores.get("composite_score", 0.0)
        title_sim = match_scores.get("title_similarity", 0.0)
        doi = candidate_meta.get("doi", "")
        strong_core_match = (
            title_sim >= 0.98
            and match_scores.get("author_similarity", 0.0) >= 0.30
            and match_scores.get("year_match", False)
            and composite >= 0.60
        )

        if not doi:
            return (
                FinalStatus.DOI_MISSING,
                ConfidenceLevel.UNCERTAIN,
                "Reference contains no explicit DOI and no candidate was discovered in external registries.",
                True,
            )

        if (composite >= HIGH_CONFIDENCE_THRESHOLD and title_sim >= 0.80) or strong_core_match:
            return (
                FinalStatus.DOI_RECOVERED,
                ConfidenceLevel.HIGH,
                f"Recovered DOI {doi} with high bibliographic confidence (score {composite:.2f}, title sim {title_sim:.2f}).",
                False,
            )

        if composite >= MEDIUM_CONFIDENCE_THRESHOLD:
            return (
                FinalStatus.DOI_RECOVERY_UNCERTAIN,
                ConfidenceLevel.MEDIUM,
                f"Discovered plausible candidate DOI {doi} (score {composite:.2f}), but requires human verification.",
                True,
            )

        return (
            FinalStatus.DOI_MISSING,
            ConfidenceLevel.UNCERTAIN,
            f"Reference has no DOI; nearest candidate had insufficient similarity (score {composite:.2f}).",
            True,
        )

