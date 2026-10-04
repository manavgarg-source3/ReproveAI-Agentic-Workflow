"""API contract tests for the existing PDF endpoint."""

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.research import (
    Artifact,
    ArtifactConfidence,
    ArtifactDiscoveryMethod,
    ArtifactStatus,
    ArtifactType,
    CitationStatus,
    Claim,
    ClaimEvidenceAssessment,
    ClaimSupportStatus,
    EvidenceRelevance,
    Experiment,
    PaperMetadata,
    Reference,
    ReferenceValidation,
    ReferenceValidationStatus,
    ResearchAnalysis,
)
from app.services.pdf_extractor import ExtractedPdf
from app.services.analyzer import ResearchAnalysisRun
from app.services.document.models import PreprocessingDiagnostics
from app.services.artifacts.discovery import discover_artifacts
from app.services.artifacts.provider import RepositoryMetadata
from app.services.artifacts.provider import RepositoryFileMetadata


client = TestClient(app)


def analysis_run(result: ResearchAnalysis, total: int = 20) -> ResearchAnalysisRun:
    return ResearchAnalysisRun(
        analysis=result,
        diagnostics=PreprocessingDiagnostics(
            total_characters=total,
            sections_detected=1,
            selected_sections=("OTHER",),
            selected_characters=total,
            chunks_created=1,
            gemini_input_characters=total,
            fallback_used=True,
        ),
    )


def test_existing_pdf_endpoint_behavior(monkeypatch) -> None:
    from app.routes import analysis as analysis_route

    monkeypatch.setattr(
        analysis_route,
        "extract_pdf_text",
        lambda _content: ExtractedPdf(text="Extracted paper text", page_count=3),
    )
    monkeypatch.setattr(
        analysis_route,
        "analyze_research_document",
        lambda _text, _pages: analysis_run(ResearchAnalysis(
            paper=PaperMetadata(title="Test Paper", authors=["Test Author"], year=2026)
        )),
    )

    response = client.post(
        "/api/v1/analyze-paper",
        files={"file": ("paper.pdf", b"%PDF-test", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "analysis": {
            "paper": {
                "title": "Test Paper",
                "authors": ["Test Author"],
                "year": 2026,
                "abstract": None,
            },
            "claims": [],
            "experiments": [],
            "methods": [],
            "references": [],
        },
        "reference_validation": [],
        "evidence_items": [],
        "claim_evidence": [],
        "artifacts": [],
        "artifact_files": [],
        "experiment_artifact_maps": [],
        "analysis_context": {
            "total_characters": 20,
            "sections_detected": 1,
            "selected_sections": ["OTHER"],
            "selected_characters": 20,
            "chunks_created": 1,
            "gemini_input_characters": 20,
            "fallback_used": True,
        },
        "extraction": {"page_count": 3, "character_count": 20},
    }


def test_non_pdf_is_rejected() -> None:
    response = client.post(
        "/api/v1/analyze-paper",
        files={"file": ("notes.txt", b"not a PDF", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Only PDF files are accepted."


def test_endpoint_returns_reference_validation(monkeypatch) -> None:
    from app.routes import analysis as analysis_route

    reference = Reference(
        id="REF-001",
        citation_text="Example citation",
        title="Example title",
        authors=["Example Author"],
        year=2020,
        doi="10.1000/example",
    )
    monkeypatch.setattr(
        analysis_route,
        "extract_pdf_text",
        lambda _content: ExtractedPdf(text="Extracted paper text", page_count=1),
    )
    monkeypatch.setattr(
        analysis_route,
        "analyze_research_document",
        lambda _text, _pages: analysis_run(ResearchAnalysis(
            paper=PaperMetadata(title="Test Paper"),
            references=[reference],
        )),
    )
    monkeypatch.setattr(
        analysis_route,
        "validate_references",
        lambda references: [
            ReferenceValidation(
                reference_id=references[0].id,
                input_doi=references[0].doi,
                normalized_doi="10.1000/example",
                doi_resolves=True,
                status=ReferenceValidationStatus.VALID_CORRECT,
                metadata_match_score=0.96,
                source="crossref",
            )
        ],
    )

    response = client.post(
        "/api/v1/analyze-paper",
        files={"file": ("paper.pdf", b"%PDF-test", "application/pdf")},
    )

    assert response.status_code == 200
    evidence = response.json()["reference_validation"]
    assert len(evidence) == 1
    assert evidence[0]["reference_id"] == "REF-001"
    assert evidence[0]["status"] == "VALID_CORRECT"
    assert evidence[0]["source"] == "crossref"


def test_endpoint_returns_claim_evidence_without_changing_upload_flow(monkeypatch) -> None:
    from app.routes import analysis as analysis_route

    extracted_claim = Claim(
        id="CLM-001",
        claim_text="Prior work reports an improvement [1].",
        claim_type="PERFORMANCE",
    )
    monkeypatch.setattr(
        analysis_route,
        "extract_pdf_text",
        lambda _content: ExtractedPdf(text="Prior work reports an improvement [1].", page_count=1),
    )
    monkeypatch.setattr(
        analysis_route,
        "analyze_research_document",
        lambda _text, _pages: analysis_run(ResearchAnalysis(
            paper=PaperMetadata(title="Test Paper"), claims=[extracted_claim]
        ), total=45),
    )
    monkeypatch.setattr(analysis_route, "validate_references", lambda _refs: [])
    monkeypatch.setattr(
        analysis_route,
        "validate_claim_evidence",
        lambda _text, _analysis, _validations: (
            [],
            [ClaimEvidenceAssessment(
                claim_id="CLM-001",
                citation_status=CitationStatus.NO_ASSOCIATED_CITATION,
                support_status=ClaimSupportStatus.SOURCE_UNAVAILABLE,
                confidence=EvidenceRelevance.UNKNOWN,
                explanation="No citation was confidently associated.",
                requires_human_review=True,
            )],
        ),
    )

    response = client.post(
        "/api/v1/analyze-paper",
        files={"file": ("paper.pdf", b"%PDF-test", "application/pdf")},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["claim_evidence"][0]["claim_id"] == "CLM-001"
    assert result["claim_evidence"][0]["support_status"] == "SOURCE_UNAVAILABLE"


def test_endpoint_returns_artifacts_without_executing_them(monkeypatch) -> None:
    from app.routes import analysis as analysis_route

    class EndpointRepository:
        def inspect(self, url):
            return RepositoryMetadata(
                canonical_url=url,
                platform="github",
                owner="example",
                name="repo",
                accessible=True,
                readme_excerpt="Use evaluate.py to evaluate Model-X on Dataset-Y.",
                readme_available=True,
                file_tree=[RepositoryFileMetadata("evaluate.py")],
            )

    monkeypatch.setattr(
        analysis_route,
        "extract_pdf_text",
        lambda _content: ExtractedPdf(text="Code: https://github.com/example/repo", page_count=1),
    )
    monkeypatch.setattr(
        analysis_route,
        "analyze_research_document",
        lambda _text, _pages: analysis_run(
            ResearchAnalysis(
                paper=PaperMetadata(title="Test Paper"),
                experiments=[Experiment(
                    id="EXP-001",
                    objective="Evaluate Model-X on Dataset-Y",
                    dataset="Dataset-Y",
                    model="Model-X",
                    metric="F1",
                )],
            ),
            total=37,
        ),
    )
    monkeypatch.setattr(analysis_route, "validate_references", lambda _refs: [])
    monkeypatch.setattr(analysis_route, "validate_claim_evidence", lambda *_args: ([], []))
    monkeypatch.setattr(
        analysis_route,
        "discover_artifacts",
        lambda _text, _analysis, **_kwargs: [Artifact(
            artifact_id="ART-001",
            experiment_id="EXP-001",
            type=ArtifactType.CODE,
            name="repo",
            source="github",
            source_url="https://github.com/example/repo",
            repository="https://github.com/example/repo",
            discovery_method=ArtifactDiscoveryMethod.PAPER_URL,
            relationship_status=ArtifactStatus.FOUND,
            availability_status=ArtifactStatus.FOUND,
            confidence=ArtifactConfidence.MEDIUM,
            notes=["Metadata only; not executed."],
        )],
    )
    monkeypatch.setattr(
        analysis_route,
        "PublicRepositoryMetadataProvider",
        EndpointRepository,
    )

    response = client.post(
        "/api/v1/analyze-paper",
        files={"file": ("paper.pdf", b"%PDF-test", "application/pdf")},
    )

    assert response.status_code == 200
    artifact = response.json()["artifacts"][0]
    assert artifact["type"] == "CODE"
    assert artifact["relationship_status"] == "FOUND"
    assert response.json()["artifact_files"][0]["path"] == "evaluate.py"
    assert response.json()["experiment_artifact_maps"][0]["readiness"] == "LIMITED"


def test_endpoint_returns_wrapped_bert_repository_when_metadata_is_offline(
    monkeypatch,
) -> None:
    from app.routes import analysis as analysis_route

    bert_url = "https://github.com/google-research/bert"
    extracted_text = (
        "1 Introduction\nThe code and pre-trained mod-\nels are available at "
        "https://github.com/\ngoogle-research/bert.\n2 Related Work"
    )

    class OfflineRepository:
        def inspect(self, url):
            return RepositoryMetadata(
                canonical_url=url,
                platform="github",
                owner="google-research",
                name="bert",
                accessible=False,
            )

    monkeypatch.setattr(
        analysis_route,
        "extract_pdf_text",
        lambda _content: ExtractedPdf(text=extracted_text, page_count=1),
    )
    monkeypatch.setattr(
        analysis_route,
        "analyze_research_document",
        lambda _text, _pages: analysis_run(
            ResearchAnalysis(
                paper=PaperMetadata(
                    title="BERT: Pre-training of Deep Bidirectional Transformers for "
                    "Language Understanding"
                )
            ),
            total=len(extracted_text),
        ),
    )
    monkeypatch.setattr(analysis_route, "validate_references", lambda _refs: [])
    monkeypatch.setattr(
        analysis_route,
        "validate_claim_evidence",
        lambda *_args: ([], []),
    )
    monkeypatch.setattr(
        analysis_route,
        "discover_artifacts",
        lambda text, result, **_kwargs: discover_artifacts(
            text,
            result,
            repository_provider=OfflineRepository(),
        ),
    )
    monkeypatch.setattr(
        analysis_route,
        "PublicRepositoryMetadataProvider",
        OfflineRepository,
    )

    response = client.post(
        "/api/v1/analyze-paper",
        files={"file": ("bert.pdf", b"%PDF-test", "application/pdf")},
    )

    assert response.status_code == 200
    artifact = next(
        item for item in response.json()["artifacts"]
        if item["source_url"] == bert_url
    )
    assert artifact["type"] == "CODE"
    assert artifact["evidence_location"] == "1 Introduction"
    assert artifact["relationship_status"] == "PARTIAL"
    assert artifact["availability_status"] == "INACCESSIBLE"
