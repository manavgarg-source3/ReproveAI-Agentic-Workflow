"""Request-scoped orchestration for traceable claim-evidence assessment."""

import logging

from app.schemas.research import (
    CitationStatus,
    ClaimEvidenceAssessment,
    ClaimSupportStatus,
    EvidenceClassification,
    EvidenceDirectness,
    EvidenceItem,
    EvidenceQuality,
    EvidenceRelevance,
    ReferenceValidation,
    ResearchAnalysis,
)
from app.services.evidence.citation_mapper import CitationAssociation, CitationMapper
from app.services.evidence.gemini import GeminiClaimEvidenceProvider
from app.services.evidence.paper_source import PaperEvidenceMapper
from app.services.evidence.provider import ClaimEvidenceProvider, SourceEvidenceProvider
from app.services.evidence.scientometric_source import ScientometricSourceEvidenceProvider

logger = logging.getLogger(__name__)


def _unavailable_assessment(
    claim_id: str,
    *,
    citation_status: CitationStatus,
    reference_ids: list[str],
    evidence_ids: list[str],
    explanation: str,
    unresolved_questions: list[str],
    status: ClaimSupportStatus = ClaimSupportStatus.SOURCE_UNAVAILABLE,
) -> ClaimEvidenceAssessment:
    return ClaimEvidenceAssessment(
        claim_id=claim_id,
        citation_status=citation_status,
        reference_ids=reference_ids,
        required_evidence=[
            "Inspectable source text that explicitly addresses the author claim."
        ],
        support_status=status,
        evidence_ids=evidence_ids,
        confidence=EvidenceRelevance.UNKNOWN,
        explanation=explanation,
        unresolved_questions=unresolved_questions,
        requires_human_review=True,
    )


def _review_required(status: ClaimSupportStatus, confidence: EvidenceRelevance) -> bool:
    return status in {
        ClaimSupportStatus.NOT_SUPPORTED,
        ClaimSupportStatus.CONTRADICTED,
        ClaimSupportStatus.UNCLEAR,
        ClaimSupportStatus.SOURCE_UNAVAILABLE,
    } or confidence in {EvidenceRelevance.LOW, EvidenceRelevance.UNKNOWN}


def validate_claim_evidence(
    paper_text: str,
    analysis: ResearchAnalysis,
    reference_validation: list[ReferenceValidation],
    *,
    citation_mapper: CitationMapper | None = None,
    source_provider: SourceEvidenceProvider | None = None,
    alignment_provider: ClaimEvidenceProvider | None = None,
) -> tuple[list[EvidenceItem], list[ClaimEvidenceAssessment]]:
    """Evaluate each claim independently without allowing one failure to abort the paper."""

    if not analysis.claims:
        return [], []

    try:
        mapper = citation_mapper or CitationMapper()
        associations = mapper.map_claims(paper_text, analysis.claims, analysis.references)
    except Exception:
        logger.exception("Citation mapping unavailable")
        return [], [
            _unavailable_assessment(
                claim.id,
                citation_status=CitationStatus.NO_ASSOCIATED_CITATION,
                reference_ids=[],
                evidence_ids=[],
                explanation="Citation parsing was unavailable, so no source association was inferred.",
                unresolved_questions=["Which cited source, if any, is associated with this claim?"],
                status=ClaimSupportStatus.UNCLEAR,
            )
            for claim in analysis.claims
        ]

    references = {reference.id: reference for reference in analysis.references}
    validations = {item.reference_id: item for item in reference_validation}
    evidence_items: list[EvidenceItem] = []
    assessments: list[ClaimEvidenceAssessment] = []
    owned_alignment_provider = alignment_provider is None
    aligner = alignment_provider
    try:
        paper_mapper = PaperEvidenceMapper(paper_text)
    except Exception:
        logger.exception("Uploaded-paper evidence mapping unavailable")
        paper_mapper = None

    try:
        import concurrent.futures
        
        def _process_claim(claim):
            claim_evidence_items = []
            claim_associations = associations.get(claim.id, [])
            if not claim_associations:
                paper_match = paper_mapper.find(claim) if paper_mapper is not None else None
                if paper_match is not None:
                    evidence_id = f"evidence-{claim.id}-paper"
                    item = EvidenceItem(
                        evidence_id=evidence_id,
                        claim_id=claim.id,
                        evidence_type="PAPER_EXCERPT",
                        source="uploaded paper",
                        source_title=analysis.paper.title or "Uploaded paper",
                        excerpt=paper_match.excerpt,
                        citation_location=paper_match.location,
                        relevance=EvidenceRelevance.HIGH,
                        directness=EvidenceDirectness.DIRECT,
                        quality=EvidenceQuality.SOURCE_EXCERPT,
                        classification=EvidenceClassification.AUTHOR_CLAIM,
                    )
                    assessment = ClaimEvidenceAssessment(
                        claim_id=claim.id,
                        citation_status=CitationStatus.NO_ASSOCIATED_CITATION,
                        reference_ids=[],
                        required_evidence=[],
                        support_status=ClaimSupportStatus.SUPPORTED,
                        evidence_ids=[evidence_id],
                        confidence=EvidenceRelevance.HIGH,
                        explanation=(
                            "The uploaded paper explicitly reports this claim in the supplied "
                            "paper excerpt. This confirms textual support within the paper; it "
                            "does not independently establish scientific truth."
                        ),
                        unresolved_questions=[],
                        requires_human_review=False,
                    )
                    return claim.id, [item], assessment
                return claim.id, claim_evidence_items, _unavailable_assessment(
                    claim.id,
                    citation_status=CitationStatus.NO_ASSOCIATED_CITATION,
                    reference_ids=[],
                    evidence_ids=[],
                    explanation=(
                        "No external citation was associated with this claim, and no sufficiently "
                        "similar supporting passage was located in the uploaded paper."
                    ),
                    unresolved_questions=["Where in the paper is this claim supported?"],
                )

            reference_ids = []
            for index, association in enumerate(claim_associations, start=1):
                reference = references.get(association.reference_id)
                if reference is None:
                    continue
                if reference.id not in reference_ids:
                    reference_ids.append(reference.id)
                evidence_id = f"evidence-{claim.id}-{index}"
                try:
                    retriever = source_provider or ScientometricSourceEvidenceProvider()
                    source = retriever.retrieve(reference, validations.get(reference.id))
                    has_text = bool(source.excerpt)
                    item = EvidenceItem(
                        evidence_id=evidence_id,
                        claim_id=claim.id,
                        reference_id=reference.id,
                        evidence_type=source.evidence_type,
                        source=source.source,
                        source_title=source.title,
                        source_locator=source.locator,
                        excerpt=source.excerpt,
                        citation_marker=association.marker,
                        citation_context=association.context_text,
                        citation_location=association.location,
                        relevance=EvidenceRelevance.UNKNOWN,
                        directness=EvidenceDirectness.UNKNOWN,
                        quality=(
                            EvidenceQuality.ABSTRACT
                            if source.evidence_type == "ABSTRACT" and has_text
                            else EvidenceQuality.METADATA_ONLY
                        ),
                        classification=(
                            EvidenceClassification.AUTHOR_CLAIM
                            if has_text
                            else EvidenceClassification.UNKNOWN
                        ),
                    )
                except Exception:
                    item = EvidenceItem(
                        evidence_id=evidence_id,
                        claim_id=claim.id,
                        reference_id=reference.id,
                        evidence_type="UNAVAILABLE",
                        source_title=reference.title,
                        citation_marker=association.marker,
                        citation_context=association.context_text,
                        citation_location=association.location,
                    )
                claim_evidence_items.append(item)

            inspectable = [item for item in claim_evidence_items if item.excerpt]
            if not inspectable:
                return claim.id, claim_evidence_items, _unavailable_assessment(
                    claim.id,
                    citation_status=CitationStatus.ASSOCIATED,
                    reference_ids=reference_ids,
                    evidence_ids=[item.evidence_id for item in claim_evidence_items],
                    explanation=(
                        "A citation was associated, but no inspectable source abstract or excerpt "
                        "was available. Bibliographic metadata was not treated as scientific evidence."
                    ),
                    unresolved_questions=[
                        "What does the cited source report about this claim?"
                    ],
                )
            local_aligner = None
            try:
                local_aligner = aligner or GeminiClaimEvidenceProvider()
                decision = local_aligner.assess_claim(claim, claim_evidence_items)

                missing_associated_text = any(not item.excerpt for item in claim_evidence_items)
                support_status = decision.support_status
                explanation = decision.explanation
                unresolved_questions = list(decision.unresolved_questions)
                if support_status == ClaimSupportStatus.SOURCE_UNAVAILABLE:
                    support_status = ClaimSupportStatus.UNCLEAR
                    explanation = (
                        f"{explanation} At least one source excerpt was inspected, so the overall "
                        "relationship is classified as unclear rather than source unavailable."
                    )
                if (
                    support_status == ClaimSupportStatus.NOT_SUPPORTED
                    and missing_associated_text
                ):
                    support_status = ClaimSupportStatus.UNCLEAR
                    explanation = (
                        f"{explanation} Other associated sources were unavailable, so the "
                        "complete citation-support relationship remains unclear."
                    )
                    unresolved_questions.append(
                        "Would the unavailable associated sources support another part of the claim?"
                    )
                updated_items = []
                inspectable_ids = {item.evidence_id for item in inspectable}
                for item in claim_evidence_items:
                    updated = (
                        item.model_copy(
                            update={
                                "relevance": decision.relevance,
                                "directness": decision.directness,
                            }
                        )
                        if item.evidence_id in inspectable_ids
                        else item
                    )
                    updated_items.append(updated)
                    
                assessment = ClaimEvidenceAssessment(
                    claim_id=claim.id,
                    citation_status=CitationStatus.ASSOCIATED,
                    reference_ids=reference_ids,
                    required_evidence=decision.required_evidence,
                    support_status=support_status,
                    evidence_ids=[item.evidence_id for item in updated_items],
                    confidence=decision.confidence,
                    explanation=explanation,
                    unresolved_questions=unresolved_questions,
                    requires_human_review=_review_required(
                        support_status, decision.confidence
                    ),
                )
                return claim.id, updated_items, assessment
            except Exception:
                return claim.id, claim_evidence_items, _unavailable_assessment(
                    claim.id,
                    citation_status=CitationStatus.ASSOCIATED,
                    reference_ids=reference_ids,
                    evidence_ids=[item.evidence_id for item in claim_evidence_items],
                    explanation=(
                        "Source text was retrieved, but its alignment with the claim could not be "
                        "reliably assessed."
                    ),
                    unresolved_questions=[
                        "Does the supplied source excerpt support the complete claim?"
                    ],
                    status=ClaimSupportStatus.UNCLEAR,
                )
            finally:
                if aligner is None and local_aligner is not None:
                    try:
                        local_aligner.close()
                    except Exception:
                        pass


        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(analysis.claims))) as executor:
            future_to_claim = {executor.submit(_process_claim, claim): claim for claim in analysis.claims}
            for future in concurrent.futures.as_completed(future_to_claim):
                try:
                    claim_id, items, assessment = future.result()
                    for item in items:
                        evidence_items.append(item)
                    assessments.append(assessment)
                except Exception:
                    pass
    finally:
        if owned_alignment_provider and aligner is not None:
            try:
                aligner.close()
            except Exception:
                logger.warning("Could not close claim-evidence provider cleanly")

    return evidence_items, assessments
