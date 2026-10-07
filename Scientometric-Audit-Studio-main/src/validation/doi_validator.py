"""
Unified Reference and DOI Validation Coordinator.
Runs the complete multi-step verification pipeline on a single reference record.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from src.models.reference import ParsedReference
from src.models.verification import VerificationResult, FinalStatus, ConfidenceLevel
from src.providers.crossref import CrossrefClient
from src.providers.openalex import OpenAlexClient
from src.providers.scopus import ScopusClient
from src.providers.doi_resolver import DOIResolver
from src.matching.metadata_matcher import MetadataMatcher
from src.matching.scoring import DecisionEngine
from src.validation.recovery import DOIRecoveryEngine

logger = logging.getLogger(__name__)


class ReferenceValidator:
    """
    Coordinates verification of a single reference through resolvers,
    metadata registries, fuzzy matchers, and recovery heuristics.
    """

    def __init__(
        self,
        crossref: Optional[CrossrefClient] = None,
        openalex: Optional[OpenAlexClient] = None,
        scopus: Optional[ScopusClient] = None,
        resolver: Optional[DOIResolver] = None,
    ):
        self.crossref = crossref or CrossrefClient()
        self.openalex = openalex or OpenAlexClient()
        self.scopus = scopus or ScopusClient()
        self.resolver = resolver or DOIResolver()
        self.recovery_engine = DOIRecoveryEngine(
            crossref=self.crossref,
            openalex=self.openalex,
            scopus=self.scopus,
        )

    def validate_reference(
        self,
        ref: ParsedReference,
        scopus_ref: Optional[Dict[str, Any]] = None,
        assigned_dois: Optional[set] = None,
    ) -> VerificationResult:
        """
        Runs comprehensive validation for a given reference using Scopus ground truth
        when available, external registries, and strict anti-duplication checks.
        """
        if assigned_dois is None:
            assigned_dois = set()

        # Extract bibliographic dictionary from parsed citation
        cited_dict = {
            "cited_title": ref.cited_title,
            "cited_authors": ref.cited_authors,
            "cited_year": ref.cited_year,
            "cited_journal": ref.cited_journal,
            "cited_volume": ref.cited_volume,
            "cited_pages": ref.cited_pages,
        }

        # 1. Evaluate Scopus Ground Truth
        if scopus_ref:
            return self._validate_with_scopus_ground_truth(ref, cited_dict, scopus_ref, assigned_dois)

        # 2. Fallback: Case A - Reference contains an explicit extracted DOI
        if ref.extracted_doi:
            return self._validate_with_explicit_doi(ref, cited_dict, assigned_dois)

        # 3. Fallback: Case B - Missing DOI -> Attempt Recovery
        return self._validate_missing_doi(ref, cited_dict, assigned_dois)

    def _validate_with_scopus_ground_truth(
        self,
        ref: ParsedReference,
        cited_dict: Dict[str, Any],
        scopus_ref: Dict[str, Any],
        assigned_dois: set,
    ) -> VerificationResult:
        """
        Primary validation path when Scopus Abstract Retrieval ground truth is available.
        """
        scopus_linked = scopus_ref.get("scopus_linked", False)
        scopus_id = scopus_ref.get("scopus_id", "")
        scopus_link = scopus_ref.get("scopus_link", "Not linked in Scopus")
        scopus_doi = scopus_ref.get("doi", "")
        scopus_title = scopus_ref.get("title", "")
        if scopus_title == "{}":
            scopus_title = ""
        scopus_authors = scopus_ref.get("authors", "")
        if scopus_authors == "{}":
            scopus_authors = ""
        scopus_journal = scopus_ref.get("journal", "")
        if scopus_journal == "{}":
            scopus_journal = ""
        scopus_year = scopus_ref.get("year")
        scopus_volume = scopus_ref.get("volume", "")
        scopus_issue = scopus_ref.get("issue", "")
        scopus_pages = scopus_ref.get("pages", "")

        # Fallback for cited_dict if empty
        if not cited_dict.get("cited_title") and scopus_title:
            cited_dict["cited_title"] = scopus_title
        if not cited_dict.get("cited_authors") and scopus_authors:
            cited_dict["cited_authors"] = scopus_authors
        if not cited_dict.get("cited_year") and scopus_year:
            cited_dict["cited_year"] = scopus_year

        # Case 1: Scopus has an authoritative verified DOI
        if scopus_doi:
            doi = scopus_doi
            if doi.lower() in assigned_dois:
                logger.warning(f"Duplicate Scopus DOI {doi} detected in paper {ref.source_eid} at ref {ref.reference_no}")
            else:
                assigned_dois.add(doi.lower())

            resolve_data = self.resolver.resolve(doi)
            match_scores = MetadataMatcher.evaluate(cited_dict, scopus_ref)
            
            # Fetch authoritative metadata from Crossref or OpenAlex if Scopus title is brief/empty
            target_meta = dict(scopus_ref)
            if not scopus_title or len(scopus_title) < 5:
                reg_meta = self.crossref.get_by_doi(doi) or self.openalex.get_by_doi(doi)
                if reg_meta and reg_meta.get("title"):
                    target_meta["title"] = reg_meta["title"]
                    if reg_meta.get("authors"):
                        target_meta["authors"] = reg_meta["authors"]
                    if reg_meta.get("year"):
                        target_meta["year"] = reg_meta["year"]
                    if reg_meta.get("journal"):
                        target_meta["journal"] = reg_meta["journal"]
                    scopus_title = reg_meta["title"]
                    if not scopus_authors:
                        scopus_authors = reg_meta.get("authors", "")

            match_scores = MetadataMatcher.evaluate(cited_dict, target_meta)

            final_status = FinalStatus.VALID_CORRECT
            confidence = ConfidenceLevel.HIGH
            rationale = f"Verified and linked by Scopus index (type: {scopus_ref.get('scopus_type')}, Scopus ID: {scopus_id})."
            needs_review = False

            # Check if resolved URL has access restrictions
            http_st = resolve_data.get("http_status")
            if http_st in (401, 403):
                final_status = FinalStatus.ACCESS_RESTRICTED
                rationale += f" URL access restricted (HTTP {http_st})."
            elif http_st == 404:
                final_status = FinalStatus.BROKEN_URL
                rationale += f" DOI failed to resolve (HTTP {http_st})."
                needs_review = True

            return VerificationResult(
                reference_id=ref.reference_id,
                source_eid=ref.source_eid,
                source_title=ref.source_title,
                source_authors=ref.source_authors,
                source_year=ref.source_year,
                source_doi=ref.source_doi,
                reference_no=ref.reference_no,
                raw_reference=ref.raw_reference,
                scopus_linked=scopus_linked,
                scopus_reference_link=scopus_link,
                scopus_id=scopus_id,
                extracted_doi=ref.extracted_doi,
                normalized_doi=doi,
                doi_exists=resolve_data.get("doi_exists", True),
                doi_resolves=resolve_data.get("doi_resolves", True),
                http_status=resolve_data.get("http_status", 200),
                final_url=resolve_data.get("final_url", ""),
                redirect_count=resolve_data.get("redirect_count", 0),
                response_time_ms=resolve_data.get("response_time_ms"),
                metadata_source="scopus_index",
                resolved_title=scopus_title or cited_dict.get("cited_title", ""),
                resolved_authors=scopus_authors or cited_dict.get("cited_authors", ""),
                resolved_journal=scopus_journal or cited_dict.get("cited_journal", ""),
                resolved_year=scopus_year or cited_dict.get("cited_year"),
                resolved_volume=scopus_volume,
                resolved_issue=scopus_issue,
                resolved_pages=scopus_pages,
                is_retracted=False,
                title_similarity=match_scores.get("title_similarity", 1.0 if scopus_title else 0.0),
                author_similarity=match_scores.get("author_similarity", 1.0 if scopus_authors else 0.0),
                journal_similarity=match_scores.get("journal_similarity", 0.0),
                year_match=match_scores.get("year_match", True),
                volume_match=match_scores.get("volume_match", True),
                pages_match=match_scores.get("pages_match", True),
                composite_score=match_scores.get("composite_score", 0.95),
                confidence=confidence,
                final_status=final_status,
                decision_rationale=rationale,
                needs_human_review=needs_review,
            )

        # Case 2: Scopus links the paper, but no DOI is assigned
        if scopus_linked:
            # Check Crossref strictly to see if a DOI was assigned
            recovered_doi = ""
            if scopus_title and len(scopus_title) > 10:
                query_str = f"{scopus_title} {scopus_authors}".strip()
            search_title = scopus_title or cited_dict.get("cited_title", "")
            search_authors = scopus_authors or cited_dict.get("cited_authors", "")
            if search_title and len(search_title) > 10:
                query_str = f"{search_title} {search_authors}".strip()
                search_res = self.crossref.search_bibliographic(query_str, rows=2)
                for cand in search_res:
                    cand_doi = cand.get("doi", "")
                    if not cand_doi or cand_doi.lower() in assigned_dois:
                        continue
                    m = MetadataMatcher.evaluate({"cited_title": scopus_title, "cited_authors": scopus_authors, "cited_year": scopus_year}, cand)
                    m = MetadataMatcher.evaluate(
                        {"cited_title": search_title, "cited_authors": search_authors, "cited_year": scopus_year or cited_dict.get("cited_year")},
                        cand
                    )
                    if m.get("title_similarity", 0.0) >= 0.88 and m.get("year_match", True):
                        recovered_doi = cand_doi
                        assigned_dois.add(cand_doi.lower())
                        resolve_data = self.resolver.resolve(cand_doi)
                        return VerificationResult(
                            reference_id=ref.reference_id,
                            source_eid=ref.source_eid,
                            source_title=ref.source_title,
                            source_authors=ref.source_authors,
                            source_year=ref.source_year,
                            source_doi=ref.source_doi,
                            reference_no=ref.reference_no,
                            raw_reference=ref.raw_reference,
                            scopus_linked=True,
                            scopus_reference_link=scopus_link,
                            scopus_id=scopus_id,
                            extracted_doi=ref.extracted_doi,
                            normalized_doi=cand_doi,
                            doi_exists=resolve_data.get("doi_exists", True),
                            doi_resolves=resolve_data.get("doi_resolves", True),
                            http_status=resolve_data.get("http_status", 200),
                            final_url=resolve_data.get("final_url", ""),
                            redirect_count=resolve_data.get("redirect_count", 0),
                            response_time_ms=resolve_data.get("response_time_ms"),
                            metadata_source="crossref",
                            resolved_title=cand.get("title", search_title),
                            resolved_authors=cand.get("authors", search_authors),
                            resolved_journal=cand.get("journal", scopus_journal),
                            resolved_year=cand.get("year", scopus_year),
                            resolved_volume=str(cand.get("volume", "")),
                            resolved_issue=str(cand.get("issue", "")),
                            resolved_pages=str(cand.get("pages", "")),
                            is_retracted=cand.get("is_retracted", False),
                            title_similarity=m.get("title_similarity", 1.0),
                            author_similarity=m.get("author_similarity", 1.0),
                            journal_similarity=m.get("journal_similarity", 1.0),
                            year_match=m.get("year_match", True),
                            volume_match=m.get("volume_match", True),
                            pages_match=m.get("pages_match", True),
                            composite_score=m.get("composite_score", 0.95),
                            confidence=ConfidenceLevel.HIGH,
                            final_status=FinalStatus.DOI_RECOVERED,
                            decision_rationale=f"Linked in Scopus (Scopus ID: {scopus_id}); verified DOI {cand_doi} recovered from Crossref.",
                            needs_human_review=False,
                        )

            # Record verified in Scopus without DOI
            target_ref = dict(scopus_ref)
            if not target_ref.get("title") or target_ref.get("title") == "{}":
                target_ref["title"] = search_title
            match_scores = MetadataMatcher.evaluate(cited_dict, target_ref)
            res_title = scopus_title or cited_dict.get("cited_title", "")
            return VerificationResult(
                reference_id=ref.reference_id,
                source_eid=ref.source_eid,
                source_title=ref.source_title,
                source_authors=ref.source_authors,
                source_year=ref.source_year,
                source_doi=ref.source_doi,
                reference_no=ref.reference_no,
                raw_reference=ref.raw_reference,
                scopus_linked=True,
                scopus_reference_link=scopus_link,
                scopus_id=scopus_id,
                extracted_doi=ref.extracted_doi,
                normalized_doi="",
                doi_exists=False,
                doi_resolves=False,
                metadata_source="scopus_index",
                resolved_title=res_title,
                resolved_authors=scopus_authors or cited_dict.get("cited_authors", ""),
                resolved_journal=scopus_journal or cited_dict.get("cited_journal", ""),
                resolved_year=scopus_year or cited_dict.get("cited_year"),
                resolved_volume=scopus_volume,
                resolved_issue=scopus_issue,
                resolved_pages=scopus_pages,
                title_similarity=match_scores.get("title_similarity", 1.0 if res_title else 0.0),
                author_similarity=match_scores.get("author_similarity", 1.0 if scopus_authors else 0.0),
                journal_similarity=match_scores.get("journal_similarity", 0.0),
                year_match=match_scores.get("year_match", True),
                volume_match=match_scores.get("volume_match", True),
                pages_match=match_scores.get("pages_match", True),
                composite_score=match_scores.get("composite_score", 0.85),
                confidence=ConfidenceLevel.HIGH,
                final_status=FinalStatus.SCOPUS_LINKED_NO_DOI,
                decision_rationale=f"Indexed and linked in Scopus (Scopus ID: {scopus_id}), but published without a registered DOI.",
                needs_human_review=False,
            )

        # Case 3: Reference is unlinked in Scopus (originalReference/other)
        # Attempt strict recovery on external registries
        candidate_meta, match_scores = self.recovery_engine.recover(cited_dict)
        if candidate_meta and candidate_meta.get("doi"):
            cand_doi = candidate_meta["doi"]
            if cand_doi.lower() not in assigned_dois and match_scores.get("title_similarity", 0.0) >= 0.85 and match_scores.get("year_match", True):
                assigned_dois.add(cand_doi.lower())
                resolve_data = self.resolver.resolve(cand_doi)
                return VerificationResult(
                    reference_id=ref.reference_id,
                    source_eid=ref.source_eid,
                    source_title=ref.source_title,
                    source_authors=ref.source_authors,
                    source_year=ref.source_year,
                    source_doi=ref.source_doi,
                    reference_no=ref.reference_no,
                    raw_reference=ref.raw_reference,
                    scopus_linked=False,
                    scopus_reference_link="Not linked in Scopus",
                    scopus_id="",
                    extracted_doi=ref.extracted_doi,
                    normalized_doi=cand_doi,
                    doi_exists=resolve_data.get("doi_exists", False),
                    doi_resolves=resolve_data.get("doi_resolves", False),
                    http_status=resolve_data.get("http_status"),
                    final_url=resolve_data.get("final_url", ""),
                    redirect_count=resolve_data.get("redirect_count", 0),
                    response_time_ms=resolve_data.get("response_time_ms"),
                    metadata_source=candidate_meta.get("provider", ""),
                    resolved_title=candidate_meta.get("title", ""),
                    resolved_authors=candidate_meta.get("authors", ""),
                    resolved_journal=candidate_meta.get("journal", ""),
                    resolved_year=candidate_meta.get("year"),
                    resolved_volume=str(candidate_meta.get("volume", "")),
                    resolved_issue=str(candidate_meta.get("issue", "")),
                    resolved_pages=str(candidate_meta.get("pages", "")),
                    is_retracted=candidate_meta.get("is_retracted", False),
                    title_similarity=match_scores.get("title_similarity", 0.0),
                    author_similarity=match_scores.get("author_similarity", 0.0),
                    journal_similarity=match_scores.get("journal_similarity", 0.0),
                    year_match=match_scores.get("year_match", False),
                    volume_match=match_scores.get("volume_match", False),
                    pages_match=match_scores.get("pages_match", False),
                    composite_score=match_scores.get("composite_score", 0.0),
                    confidence=ConfidenceLevel.MEDIUM,
                    final_status=FinalStatus.DOI_RECOVERED,
                    decision_rationale=f"Not linked in Scopus (type: originalReference/other); recovered DOI {cand_doi} from external registry.",
                    needs_human_review=True,
                )

        # Unlinked in Scopus and unrecovered
        return VerificationResult(
            reference_id=ref.reference_id,
            source_eid=ref.source_eid,
            source_title=ref.source_title,
            source_authors=ref.source_authors,
            source_year=ref.source_year,
            source_doi=ref.source_doi,
            reference_no=ref.reference_no,
            raw_reference=ref.raw_reference,
            scopus_linked=False,
            scopus_reference_link="Not linked in Scopus",
            scopus_id="",
            extracted_doi=ref.extracted_doi,
            confidence=ConfidenceLevel.HIGH,
            final_status=FinalStatus.SCOPUS_UNLINKED,
            decision_rationale="Reference is unlinked in Scopus (type: originalReference/other) and has no registered DOI.",
            needs_human_review=True,
        )

    def _validate_with_explicit_doi(
        self,
        ref: ParsedReference,
        cited_dict: Dict[str, Any],
        assigned_dois: set,
    ) -> VerificationResult:
        doi = ref.extracted_doi
        if doi.lower() in assigned_dois:
            logger.warning(f"Duplicate explicit DOI {doi} detected in {ref.source_eid}")
        else:
            assigned_dois.add(doi.lower())
        
        # 1. Resolve DOI via resolver
        resolve_data = self.resolver.resolve(doi)
        
        # 2. Retrieve metadata from Crossref, then OpenAlex
        meta = self.crossref.get_by_doi(doi)
        source = "crossref"
        if not meta or not meta.get("title"):
            meta = self.openalex.get_by_doi(doi)
            source = "openalex" if meta else ""
        if (not meta or not meta.get("title")) and self.scopus.is_configured():
            meta = self.scopus.get_by_doi(doi)
            source = "scopus" if meta else ""

        resolved_meta = meta or {}
        
        # 3. Match citation info against resolved publication
        match_scores = MetadataMatcher.evaluate(cited_dict, resolved_meta)

        # 4. Decision Engine Classification
        is_retracted = resolved_meta.get("is_retracted", False)
        final_status, confidence, rationale, needs_review = DecisionEngine.classify_with_doi(
            match_scores=match_scores,
            resolver_result=resolve_data,
            is_retracted=is_retracted,
        )

        return VerificationResult(
            reference_id=ref.reference_id,
            source_eid=ref.source_eid,
            source_title=ref.source_title,
            source_authors=ref.source_authors,
            source_year=ref.source_year,
            source_doi=ref.source_doi,
            reference_no=ref.reference_no,
            raw_reference=ref.raw_reference,
            scopus_linked=ref.scopus_linked,
            scopus_reference_link=ref.scopus_reference_link or "Not linked in Scopus",
            scopus_id=ref.scopus_id,
            extracted_doi=ref.extracted_doi,
            normalized_doi=doi,
            doi_exists=resolve_data.get("doi_exists", False),
            doi_resolves=resolve_data.get("doi_resolves", False),
            http_status=resolve_data.get("http_status"),
            final_url=resolve_data.get("final_url", ""),
            redirect_count=resolve_data.get("redirect_count", 0),
            response_time_ms=resolve_data.get("response_time_ms"),
            metadata_source=source,
            resolved_title=resolved_meta.get("title", ""),
            resolved_authors=resolved_meta.get("authors", ""),
            resolved_journal=resolved_meta.get("journal", ""),
            resolved_year=resolved_meta.get("year"),
            resolved_volume=str(resolved_meta.get("volume", "")),
            resolved_issue=str(resolved_meta.get("issue", "")),
            resolved_pages=str(resolved_meta.get("pages", "")),
            is_retracted=is_retracted,
            title_similarity=match_scores.get("title_similarity", 0.0),
            author_similarity=match_scores.get("author_similarity", 0.0),
            journal_similarity=match_scores.get("journal_similarity", 0.0),
            year_match=match_scores.get("year_match", False),
            volume_match=match_scores.get("volume_match", False),
            pages_match=match_scores.get("pages_match", False),
            composite_score=match_scores.get("composite_score", 0.0),
            confidence=confidence,
            final_status=final_status,
            decision_rationale=rationale,
            needs_human_review=needs_review,
        )

    def _validate_missing_doi(
        self,
        ref: ParsedReference,
        cited_dict: Dict[str, Any],
        assigned_dois: set,
    ) -> VerificationResult:
        candidate_meta, match_scores = self.recovery_engine.recover(cited_dict)
        
        if candidate_meta and candidate_meta.get("doi"):
            cand_doi = candidate_meta["doi"]
            if cand_doi.lower() in assigned_dois or match_scores.get("title_similarity", 0.0) < 0.80:
                # Discard duplicate or low-similarity candidate
                candidate_meta = None
            else:
                assigned_dois.add(cand_doi.lower())
                resolve_data = self.resolver.resolve(cand_doi)
                final_status, confidence, rationale, needs_review = DecisionEngine.classify_recovered_doi(
                    match_scores=match_scores,
                    candidate_meta=candidate_meta,
                    resolver_result=resolve_data,
                )
                return VerificationResult(
                    reference_id=ref.reference_id,
                    source_eid=ref.source_eid,
                    source_title=ref.source_title,
                    source_authors=ref.source_authors,
                    source_year=ref.source_year,
                    source_doi=ref.source_doi,
                    reference_no=ref.reference_no,
                    raw_reference=ref.raw_reference,
                    scopus_linked=ref.scopus_linked,
                    scopus_reference_link=ref.scopus_reference_link or "Not linked in Scopus",
                    scopus_id=ref.scopus_id,
                    extracted_doi=ref.extracted_doi,
                    normalized_doi=cand_doi,
                    doi_exists=resolve_data.get("doi_exists", False),
                    doi_resolves=resolve_data.get("doi_resolves", False),
                    http_status=resolve_data.get("http_status"),
                    final_url=resolve_data.get("final_url", ""),
                    redirect_count=resolve_data.get("redirect_count", 0),
                    response_time_ms=resolve_data.get("response_time_ms"),
                    metadata_source=candidate_meta.get("provider", ""),
                    resolved_title=candidate_meta.get("title", ""),
                    resolved_authors=candidate_meta.get("authors", ""),
                    resolved_journal=candidate_meta.get("journal", ""),
                    resolved_year=candidate_meta.get("year"),
                    resolved_volume=str(candidate_meta.get("volume", "")),
                    resolved_issue=str(candidate_meta.get("issue", "")),
                    resolved_pages=str(candidate_meta.get("pages", "")),
                    is_retracted=candidate_meta.get("is_retracted", False),
                    title_similarity=match_scores.get("title_similarity", 0.0),
                    author_similarity=match_scores.get("author_similarity", 0.0),
                    journal_similarity=match_scores.get("journal_similarity", 0.0),
                    year_match=match_scores.get("year_match", False),
                    volume_match=match_scores.get("volume_match", False),
                    pages_match=match_scores.get("pages_match", False),
                    composite_score=match_scores.get("composite_score", 0.0),
                    confidence=confidence,
                    final_status=final_status,
                    decision_rationale=rationale,
                    needs_human_review=needs_review,
                )

        if candidate_meta and not candidate_meta.get("doi"):
            return VerificationResult(
                reference_id=ref.reference_id,
                source_eid=ref.source_eid,
                source_title=ref.source_title,
                source_authors=ref.source_authors,
                source_year=ref.source_year,
                source_doi=ref.source_doi,
                reference_no=ref.reference_no,
                raw_reference=ref.raw_reference,
                scopus_linked=candidate_meta.get("provider") == "scopus",
                scopus_reference_link=ref.scopus_reference_link or "Not linked in Scopus",
                scopus_id=str(candidate_meta.get("eid", "")),
                extracted_doi=ref.extracted_doi,
                normalized_doi="",
                doi_exists=False,
                doi_resolves=False,
                metadata_source=candidate_meta.get("provider", ""),
                resolved_title=candidate_meta.get("title", ""),
                resolved_authors=candidate_meta.get("authors", ""),
                resolved_journal=candidate_meta.get("journal", ""),
                resolved_year=candidate_meta.get("year"),
                resolved_volume=str(candidate_meta.get("volume", "")),
                resolved_issue=str(candidate_meta.get("issue", "")),
                resolved_pages=str(candidate_meta.get("pages", "")),
                is_retracted=candidate_meta.get("is_retracted", False),
                title_similarity=match_scores.get("title_similarity", 0.0),
                author_similarity=match_scores.get("author_similarity", 0.0),
                journal_similarity=match_scores.get("journal_similarity", 0.0),
                year_match=match_scores.get("year_match", False),
                volume_match=match_scores.get("volume_match", False),
                pages_match=match_scores.get("pages_match", False),
                composite_score=match_scores.get("composite_score", 0.0),
                confidence=ConfidenceLevel.HIGH,
                final_status=FinalStatus.WORK_FOUND_NO_DOI,
                decision_rationale=(
                    "The paper supplied no DOI; a high-confidence bibliographic record "
                    f"was found in {candidate_meta.get('provider', 'an external registry')}, "
                    "but that record has no registered DOI."
                ),
                needs_human_review=False,
            )

        # No candidate found
        return VerificationResult(
            reference_id=ref.reference_id,
            source_eid=ref.source_eid,
            source_title=ref.source_title,
            source_authors=ref.source_authors,
            source_year=ref.source_year,
            source_doi=ref.source_doi,
            reference_no=ref.reference_no,
            raw_reference=ref.raw_reference,
            scopus_linked=ref.scopus_linked,
            scopus_reference_link=ref.scopus_reference_link or "Not linked in Scopus",
            scopus_id=ref.scopus_id,
            extracted_doi=ref.extracted_doi,
            confidence=ConfidenceLevel.UNCERTAIN,
            final_status=FinalStatus.DOI_MISSING,
            decision_rationale="Reference contains no explicit DOI and no candidate was discovered in external registries.",
            needs_human_review=True,
        )

