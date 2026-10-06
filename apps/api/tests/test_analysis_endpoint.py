"""API contract tests for the existing PDF endpoint."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.research import (
    Artifact,
    ArtifactConfidence,
    ArtifactDiscoveryMethod,
    ArtifactFile,
    ArtifactFileRole,
    ArtifactFileType,
    ArtifactReadiness,
    ArtifactStatus,
    ArtifactType,
    CitationStatus,
    Claim,
    ClaimEvidenceAssessment,
    ClaimSupportStatus,
    EvidenceRelevance,
    Experiment,
    ExperimentArtifactMap,
    FileRelevanceStatus,
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
from app.services.artifacts.inspection import ArtifactInspectionResult
from app.services.verification.case import build_research_case


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
        "/api/v1/analyze-paper?stage=citation",
        files={"file": ("paper.pdf", b"%PDF-test", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "paper_text": "Extracted paper text",
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
        "environment_specifications": [],
        "reproduction_plans": [],
        "research_case": None,
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


def test_environment_endpoint_continues_from_citation_result(monkeypatch) -> None:
    from app.routes import analysis as analysis_route

    monkeypatch.setattr(analysis_route, "discover_artifacts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        analysis_route,
        "inspect_artifacts",
        lambda *_args, **_kwargs: SimpleNamespace(files=[], experiment_maps=[]),
    )
    monkeypatch.setattr(
        analysis_route,
        "reconstruct_environments",
        lambda *_args, **_kwargs: [],
    )

    analysis_input = ResearchAnalysis(paper=PaperMetadata(title="Test Paper"))
    paper_text_input = "Extracted paper text"

    response = client.post(
        "/api/v1/analyze-environment",
        json={
            "analysis": analysis_input.model_dump(mode="json"),
            "paper_text": paper_text_input,
        },
    )

    assert response.status_code == 200
    expected_case = build_research_case(
        analysis=analysis_input,
        evidence_items=[],
        claim_evidence=[],
        artifacts=[],
        files=[],
        reproduction_plans=[],
        paper_text=paper_text_input,
    ).model_dump(mode="json")

    assert response.json() == {
        "artifacts": [],
        "artifact_files": [],
        "experiment_artifact_maps": [],
        "environment_specifications": [],
        "reproduction_plans": [],
        "research_case": expected_case,
    }


def test_primary_pipeline_returns_reconstructed_environment_without_duplicate_reads(monkeypatch) -> None:
    from app.routes import analysis as analysis_route

    repository_url = "https://github.com/example/repository"
    code_artifact = Artifact(
        artifact_id="ART-001",
        type=ArtifactType.CODE,
        name="repository",
        source="github",
        source_url=repository_url,
        repository=repository_url,
        discovery_method=ArtifactDiscoveryMethod.PAPER_URL,
        relationship_status=ArtifactStatus.FOUND,
        availability_status=ArtifactStatus.FOUND,
        confidence=ArtifactConfidence.HIGH,
    )
    files = [
        ArtifactFile(
            file_id="FILE-001",
            artifact_id="ART-001",
            experiment_id="EXP-001",
            path="requirements.txt",
            file_type=ArtifactFileType.DEPENDENCY,
            role=ArtifactFileRole.DEPENDENCY,
            relevance_status=FileRelevanceStatus.RELEVANT,
            confidence=ArtifactConfidence.HIGH,
        ),
        ArtifactFile(
            file_id="FILE-002",
            artifact_id="ART-001",
            experiment_id="EXP-001",
            path="Dockerfile",
            file_type=ArtifactFileType.CONTAINER,
            role=ArtifactFileRole.CONFIGURATION,
            relevance_status=FileRelevanceStatus.RELEVANT,
            confidence=ArtifactConfidence.HIGH,
        ),
    ]
    maps = [ExperimentArtifactMap(
        experiment_id="EXP-001",
        artifact_id="ART-001",
        readiness=ArtifactReadiness.PARTIAL,
    )]

    class EnvironmentRepository:
        instances = []

        def __init__(self):
            self.content_calls = []
            self.__class__.instances.append(self)

        def inspect(self, _url):
            return RepositoryMetadata(
                canonical_url=repository_url,
                platform="github",
                owner="example",
                name="repository",
                accessible=True,
                file_tree=[RepositoryFileMetadata("requirements.txt"), RepositoryFileMetadata("Dockerfile")],
            )

        def get_file_content(self, _url, path):
            self.content_calls.append(path)
            return {
                "requirements.txt": "python==3.11\nnumpy==1.26",
                "Dockerfile": "FROM python:3.11-slim",
            }[path]

    analysis = ResearchAnalysis(
        paper=PaperMetadata(title="Test Paper"),
        experiments=[Experiment(id="EXP-001", objective="Run the test")],
    )
    monkeypatch.setattr(
        analysis_route,
        "extract_pdf_text",
        lambda _content: ExtractedPdf(text=f"Code: {repository_url}", page_count=1),
    )
    monkeypatch.setattr(
        analysis_route,
        "analyze_research_document",
        lambda _text, _pages: analysis_run(analysis, total=50),
    )
    monkeypatch.setattr(analysis_route, "validate_references", lambda _refs: [])
    monkeypatch.setattr(analysis_route, "validate_claim_evidence", lambda *_args: ([], []))
    monkeypatch.setattr(analysis_route, "discover_artifacts", lambda *_args, **_kwargs: [code_artifact])
    monkeypatch.setattr(
        analysis_route,
        "inspect_artifacts",
        lambda *_args, **_kwargs: ArtifactInspectionResult(files=files, experiment_maps=maps),
    )
    monkeypatch.setattr(analysis_route, "PublicRepositoryMetadataProvider", EnvironmentRepository)

    response = client.post(
        "/api/v1/analyze-paper",
        files={"file": ("paper.pdf", b"%PDF-test", "application/pdf")},
    )

    assert response.status_code == 200
    environment = response.json()["environment_specifications"][0]
    assert environment["status"] == "RECONSTRUCTED"
    assert environment["python_constraint"] == "==3.11"
    plan = response.json()["reproduction_plans"][0]
    assert plan["experiment_id"] == "EXP-001"
    assert plan["environment_id"] == environment["environment_id"]
    assert plan["status"] == "PARTIALLY_READY"
    assert plan["notes"][0].startswith("PLANNED - NOT EXECUTED")
    assert response.json()["research_case"] is not None
    assert EnvironmentRepository.instances[0].content_calls == ["requirements.txt", "Dockerfile"]


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
