"""Step 2 claim-citation-source alignment tests without external network calls."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.research import (
    CitationStatus,
    Claim,
    ClaimAlignmentDecision,
    ClaimEvidenceAssessment,
    ClaimSupportStatus,
    EvidenceDirectness,
    EvidenceRelevance,
    PaperMetadata,
    Reference,
    ReferenceValidation,
    ReferenceValidationStatus,
    ResearchAnalysis,
)
from app.services.analysis_errors import AnalysisResponseError
from app.services.evidence.citation_mapper import CitationAssociation, CitationMapper
from app.services.evidence.gemini import GeminiClaimEvidenceProvider
from app.services.evidence.provider import SourceEvidence
from app.services.evidence.scientometric_source import ScientometricSourceEvidenceProvider
from app.services.evidence.validation import validate_claim_evidence


def claim(identifier: str = "CLM-001") -> Claim:
    return Claim(
        id=identifier,
        claim_text="Prior work reports improved translation quality [1].",
        claim_type="PERFORMANCE",
        metric="BLEU",
    )


def reference(identifier: str = "REF-001") -> Reference:
    return Reference(
        id=identifier,
        citation_text="[1] A. Author. Translation Study. 2020.",
        title="Translation Study",
        authors=["A. Author"],
        year=2020,
        doi="10.1000/example",
    )


def analysis(*claims: Claim) -> ResearchAnalysis:
    return ResearchAnalysis(
        paper=PaperMetadata(title="Test"),
        claims=list(claims),
        references=[reference()],
    )


class StubMapper:
    def __init__(self, associated: set[str]) -> None:
        self.associated = associated

    def map_claims(self, _text, claims, _references):
        return {
            item.id: ([CitationAssociation(
                claim_id=item.id,
                reference_id="REF-001",
                marker="[1]",
                context_text="Prior work reports improved translation quality [1].",
                location="Introduction",
                similarity=1.0,
            )] if item.id in self.associated else [])
            for item in claims
        }


class StubSource:
    def __init__(self, excerpt: str | None = "The study reports improved translation quality.", fail: bool = False) -> None:
        self.excerpt = excerpt
        self.fail = fail
        self.seen_validation = None

    def retrieve(self, reference, validation):
        self.seen_validation = validation
        if self.fail:
            raise TimeoutError("provider timeout with private detail")
        return SourceEvidence(
            reference_id=reference.id,
            source="crossref",
            title=reference.title,
            locator="https://doi.org/10.1000/example",
            excerpt=self.excerpt,
            evidence_type="ABSTRACT" if self.excerpt else "METADATA_ONLY",
        )


class StubAligner:
    def __init__(self, statuses=None, fail_for: set[str] | None = None) -> None:
        self.statuses = statuses or {}
        self.fail_for = fail_for or set()
        self.closed = False

    def assess_claim(self, item, evidence):
        if item.id in self.fail_for:
            raise RuntimeError("malformed private provider response")
        status = self.statuses.get(item.id, ClaimSupportStatus.SUPPORTED)
        return ClaimAlignmentDecision(
            required_evidence=["A source result addressing translation quality."],
            support_status=status,
            confidence=EvidenceRelevance.HIGH,
            relevance=EvidenceRelevance.HIGH,
            directness=EvidenceDirectness.DIRECT,
            explanation="The supplied abstract explicitly reports the comparison.",
            unresolved_questions=[],
        )

    def close(self):
        self.closed = True


def validation() -> ReferenceValidation:
    return ReferenceValidation(
        reference_id="REF-001",
        normalized_doi="10.1000/example",
        doi_resolves=True,
        status=ReferenceValidationStatus.VALID_CORRECT,
        source="crossref",
    )


def test_claim_with_no_citation_is_explicitly_unassociated() -> None:
    items, assessments = validate_claim_evidence(
        "Paper", analysis(claim()), [validation()], citation_mapper=StubMapper(set())
    )

    assert items == []
    assert assessments[0].citation_status == CitationStatus.NO_ASSOCIATED_CITATION
    assert assessments[0].support_status == ClaimSupportStatus.SOURCE_UNAVAILABLE
    assert assessments[0].requires_human_review is True


def test_engine_context_maps_numeric_citation_to_reference() -> None:
    scanner = lambda _body: ("NUMERIC_BRACKETED", [{
        "marker": "[1]", "unrolled_keys": [1],
        "context": "Prior work reports improved translation quality [1].",
        "start": 20,
    }])
    mapper = CitationMapper(
        scanner=scanner,
        segmenter=lambda text: (text, "", {}),
        minimum_similarity=55,
    )

    mapped = mapper.map_claims("Introduction\nPrior work reports improved translation quality [1].", [claim()], [reference()])

    assert mapped["CLM-001"][0].reference_id == "REF-001"
    assert mapped["CLM-001"][0].context_text.endswith("[1].")


def test_valid_citation_reuses_bibliographic_validation_and_returns_evidence() -> None:
    source = StubSource()
    items, assessments = validate_claim_evidence(
        "Paper", analysis(claim()), [validation()],
        citation_mapper=StubMapper({"CLM-001"}), source_provider=source,
        alignment_provider=StubAligner(),
    )

    assert source.seen_validation.status == ReferenceValidationStatus.VALID_CORRECT
    assert items[0].classification.value == "AUTHOR_CLAIM"
    assert items[0].citation_context.endswith("[1].")
    assert assessments[0].support_status == ClaimSupportStatus.SUPPORTED
    assert assessments[0].requires_human_review is False


def test_missing_source_text_is_not_treated_as_support() -> None:
    items, assessments = validate_claim_evidence(
        "Paper", analysis(claim()), [validation()],
        citation_mapper=StubMapper({"CLM-001"}), source_provider=StubSource(None),
        alignment_provider=StubAligner(),
    )

    assert items[0].quality.value == "METADATA_ONLY"
    assert assessments[0].support_status == ClaimSupportStatus.SOURCE_UNAVAILABLE
    assert "metadata" in assessments[0].explanation.lower()


@pytest.mark.parametrize(
    "status",
    [
        ClaimSupportStatus.PARTIALLY_SUPPORTED,
        ClaimSupportStatus.NOT_SUPPORTED,
        ClaimSupportStatus.CONTRADICTED,
        ClaimSupportStatus.UNCLEAR,
    ],
)
def test_all_graded_support_statuses_are_preserved(status) -> None:
    _items, assessments = validate_claim_evidence(
        "Paper", analysis(claim()), [validation()],
        citation_mapper=StubMapper({"CLM-001"}), source_provider=StubSource(),
        alignment_provider=StubAligner({"CLM-001": status}),
    )
    assert assessments[0].support_status == status


def test_source_provider_failure_is_isolated_and_secret_free() -> None:
    _items, assessments = validate_claim_evidence(
        "Paper", analysis(claim()), [validation()],
        citation_mapper=StubMapper({"CLM-001"}), source_provider=StubSource(fail=True),
        alignment_provider=StubAligner(),
    )
    assert assessments[0].support_status == ClaimSupportStatus.SOURCE_UNAVAILABLE
    assert "private detail" not in assessments[0].explanation


def test_source_unavailable_model_status_becomes_unclear_when_text_was_inspected() -> None:
    _items, assessments = validate_claim_evidence(
        "Paper", analysis(claim()), [validation()],
        citation_mapper=StubMapper({"CLM-001"}), source_provider=StubSource(),
        alignment_provider=StubAligner({"CLM-001": ClaimSupportStatus.SOURCE_UNAVAILABLE}),
    )
    assert assessments[0].support_status == ClaimSupportStatus.UNCLEAR
    assert "excerpt was inspected" in assessments[0].explanation


def test_per_claim_alignment_failure_does_not_remove_other_results() -> None:
    first, second = claim("CLM-001"), claim("CLM-002")
    _items, assessments = validate_claim_evidence(
        "Paper", analysis(first, second), [validation()],
        citation_mapper=StubMapper({"CLM-001", "CLM-002"}), source_provider=StubSource(),
        alignment_provider=StubAligner(fail_for={"CLM-001"}),
    )
    by_id = {item.claim_id: item for item in assessments}
    assert by_id["CLM-001"].support_status == ClaimSupportStatus.UNCLEAR
    assert by_id["CLM-002"].support_status == ClaimSupportStatus.SUPPORTED


def test_malformed_gemini_alignment_response_is_rejected() -> None:
    client = SimpleNamespace(
        interactions=SimpleNamespace(
            create=lambda **_kwargs: SimpleNamespace(output_text="not-json")
        )
    )
    provider = GeminiClaimEvidenceProvider(client=client, model="test", timeout_seconds=1)
    with pytest.raises(AnalysisResponseError, match="invalid structured output"):
        provider.assess_claim(claim(), [])


def test_claim_assessment_schema_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        ClaimEvidenceAssessment.model_validate({
            "claim_id": "CLM-001",
            "citation_status": "ASSOCIATED",
            "reference_ids": ["REF-001"],
            "required_evidence": [],
            "support_status": "SUPPORTED",
            "evidence_ids": [],
            "confidence": "CERTAIN",
            "explanation": "Unsupported enum value must fail.",
            "unresolved_questions": [],
            "requires_human_review": False,
        })


class FakeCrossref:
    def __init__(self, work):
        self.work = work

    def get_work_details(self, _doi):
        return self.work


class FakeOpenAlex:
    BASE_URL = "https://api.openalex.org"

    def __init__(self, work=None):
        self.work = work or {}

    def _request_with_retry(self, _url):
        return self.work


def test_source_retrieval_cleans_and_bounds_crossref_abstract() -> None:
    provider = ScientometricSourceEvidenceProvider(
        crossref=FakeCrossref({
            "title": ["Translation Study"],
            "URL": "https://doi.org/10.1000/example",
            "abstract": "<jats:p>Evidence &amp; results are reported.</jats:p>",
        }),
        openalex=FakeOpenAlex(),
        max_characters=20,
    )
    result = provider.retrieve(reference(), validation())
    assert result.source == "crossref"
    assert result.excerpt == "Evidence & results a"
    assert len(result.excerpt) <= 20


def test_source_retrieval_uses_openalex_abstract_when_crossref_has_none() -> None:
    provider = ScientometricSourceEvidenceProvider(
        crossref=FakeCrossref({"title": ["Translation Study"]}),
        openalex=FakeOpenAlex({
            "display_name": "Translation Study",
            "abstract_inverted_index": {"Methods": [0], "improve": [1], "BLEU": [2]},
            "id": "https://openalex.org/W1",
        }),
        max_characters=100,
    )
    result = provider.retrieve(reference(), validation())
    assert result.source == "openalex"
    assert result.excerpt == "Methods improve BLEU"


def test_metadata_only_source_remains_non_evidentiary() -> None:
    provider = ScientometricSourceEvidenceProvider(
        crossref=FakeCrossref({"title": ["Translation Study"]}),
        openalex=FakeOpenAlex(),
        max_characters=100,
    )
    result = provider.retrieve(reference(), validation())
    assert result.evidence_type == "METADATA_ONLY"
    assert result.excerpt is None
