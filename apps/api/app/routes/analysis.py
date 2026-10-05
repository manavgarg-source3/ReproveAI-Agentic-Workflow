"""Paper analysis endpoint."""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status, Query
from starlette.concurrency import run_in_threadpool

from pydantic import BaseModel
from app.schemas.research import AnalysisContextDiagnostics, AnalyzePaperResponse, ExtractionDiagnostics
from app.services.analyzer import analyze_research_document
from app.services.analysis_errors import (
    AnalysisConfigurationError,
    AnalysisInputTooLargeError,
    AnalysisProviderError,
    AnalysisRateLimitError,
    AnalysisResponseError,
    AnalysisTimeoutError,
)
from app.services.pdf_extractor import PdfExtractionError, extract_pdf_text
from app.services.artifacts.discovery import discover_artifacts
from app.services.artifacts.inspection import inspect_artifacts
from app.services.artifacts.repository import PublicRepositoryMetadataProvider
from app.services.evidence.validation import validate_claim_evidence
from app.services.scholarly.validation import validate_references

router = APIRouter(prefix="/api/v1", tags=["analysis"])
logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 25 * 1024 * 1024


@router.post("/analyze-paper", response_model=AnalyzePaperResponse)
async def analyze_paper(file: UploadFile = File(...), stage: str = Query("all")) -> AnalyzePaperResponse:
    filename = file.filename or ""
    if file.content_type != "application/pdf" or not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are accepted.",
        )

    try:
        content = await file.read(MAX_PDF_BYTES + 1)
    finally:
        await file.close()

    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF files must be 25 MB or smaller.",
        )

    try:
        extracted = extract_pdf_text(content)
    except PdfExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    try:
        analysis_run = await run_in_threadpool(
            analyze_research_document,
            extracted.text,
            extracted.pages,
        )
        analysis = analysis_run.analysis
    except AnalysisInputTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except AnalysisConfigurationError as exc:
        logger.error("Research analyzer configuration error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The research analyzer is not configured.",
        ) from exc
    except AnalysisRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except AnalysisTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except (AnalysisProviderError, AnalysisResponseError) as exc:
        logger.error("Research analyzer failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    reference_validation = await run_in_threadpool(
        validate_references,
        analysis.references,
    )
    evidence_items, claim_evidence = await run_in_threadpool(
        validate_claim_evidence,
        extracted.text,
        analysis,
        reference_validation,
    )
    if stage == "citation":
        return AnalyzePaperResponse(
            analysis=analysis,
            reference_validation=reference_validation,
            evidence_items=evidence_items,
            claim_evidence=claim_evidence,
            artifacts=[],
            artifact_files=[],
            experiment_artifact_maps=[],
            environment_specifications=[],
            analysis_context=AnalysisContextDiagnostics(
                total_characters=analysis_run.diagnostics.total_characters,
                sections_detected=analysis_run.diagnostics.sections_detected,
                selected_sections=list(analysis_run.diagnostics.selected_sections),
                selected_characters=analysis_run.diagnostics.selected_characters,
                chunks_created=analysis_run.diagnostics.chunks_created,
                gemini_input_characters=analysis_run.diagnostics.gemini_input_characters,
                fallback_used=analysis_run.diagnostics.fallback_used,
            ),
            extraction=ExtractionDiagnostics(
                page_count=extracted.page_count,
                character_count=extracted.character_count,
            ),
        )

    repository_provider = PublicRepositoryMetadataProvider()
    artifacts = await run_in_threadpool(
        discover_artifacts,
        extracted.text,
        analysis,
        repository_provider=repository_provider,
    )
    artifact_inspection = await run_in_threadpool(
        inspect_artifacts,
        artifacts,
        analysis,
        repository_provider=repository_provider,
    )
    return AnalyzePaperResponse(
        analysis=analysis,
        reference_validation=reference_validation,
        evidence_items=evidence_items,
        claim_evidence=claim_evidence,
        artifacts=artifacts,
        artifact_files=artifact_inspection.files,
        experiment_artifact_maps=artifact_inspection.experiment_maps,
        analysis_context=AnalysisContextDiagnostics(
            total_characters=analysis_run.diagnostics.total_characters,
            sections_detected=analysis_run.diagnostics.sections_detected,
            selected_sections=list(analysis_run.diagnostics.selected_sections),
            selected_characters=analysis_run.diagnostics.selected_characters,
            chunks_created=analysis_run.diagnostics.chunks_created,
            gemini_input_characters=analysis_run.diagnostics.gemini_input_characters,
            fallback_used=analysis_run.diagnostics.fallback_used,
        ),
        extraction=ExtractionDiagnostics(
            page_count=extracted.page_count,
            character_count=extracted.character_count,
        ),
    )

class AnalyzeEnvironmentRequest(BaseModel):
    analysis: dict
    paper_text: str

@router.post("/analyze-environment")
async def analyze_environment(request: AnalyzeEnvironmentRequest):
    from app.schemas.research import ResearchAnalysis
    try:
        analysis = ResearchAnalysis.model_validate(request.analysis)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid analysis object") from exc
        
    repository_provider = PublicRepositoryMetadataProvider()
    artifacts = await run_in_threadpool(
        discover_artifacts,
        request.paper_text,
        analysis,
        repository_provider=repository_provider,
    )
    artifact_inspection = await run_in_threadpool(
        inspect_artifacts,
        artifacts,
        analysis,
        repository_provider=repository_provider,
    )
    
    environment_specifications = await run_in_threadpool(
        reconstruct_environments,
        analysis,
        artifacts,
        artifact_inspection.files,
        artifact_inspection.experiment_maps,
        repository_provider,
        request.paper_text,
    )
    
    return {
        "artifacts": [a.model_dump() for a in artifacts],
        "artifact_files": [f.model_dump() for f in artifact_inspection.files],
        "experiment_artifact_maps": [m.model_dump() for m in artifact_inspection.experiment_maps],
        "environment_specifications": [e.model_dump() for e in environment_specifications]
    }
