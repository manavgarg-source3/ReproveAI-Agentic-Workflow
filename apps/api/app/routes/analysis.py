"""Paper analysis endpoint."""

import logging
from time import perf_counter

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
from app.services.environment.reconstruction import reconstruct_environments
from app.services.reproduction.planning import (
    generate_reproduction_plans,
    generate_reproduction_targets,
)
from app.services.scholarly.validation import validate_references
from app.services.verification.case import build_research_case
from app.services.execution.sandbox import execution_service

router = APIRouter(prefix="/api/v1", tags=["analysis"])
logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 25 * 1024 * 1024


@router.post("/analyze-paper", response_model=AnalyzePaperResponse)
async def analyze_paper(file: UploadFile = File(...), stage: str = Query("all")) -> AnalyzePaperResponse:
    request_started = perf_counter()
    filename = file.filename or ""
    logger.info("Paper analysis started (stage=%s, file=%s)", stage, filename)
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

    stage_started = perf_counter()
    try:
        extracted = extract_pdf_text(content)
    except PdfExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    logger.info(
        "PDF extraction completed in %.2fs (pages=%d, characters=%d)",
        perf_counter() - stage_started,
        extracted.page_count,
        extracted.character_count,
    )

    stage_started = perf_counter()
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
    logger.info(
        "Research analysis completed in %.2fs (chunks=%d, claims=%d, references=%d)",
        perf_counter() - stage_started,
        analysis_run.diagnostics.chunks_created,
        len(analysis.claims),
        len(analysis.references),
    )

    stage_started = perf_counter()
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
    logger.info(
        "Citation and evidence analysis completed in %.2fs (validations=%d, evidence=%d)",
        perf_counter() - stage_started,
        len(reference_validation),
        len(evidence_items),
    )
    if stage == "citation":
        logger.info("Paper analysis completed in %.2fs (stage=citation)", perf_counter() - request_started)
        return AnalyzePaperResponse(
            paper_text=extracted.text,
            analysis=analysis,
            reference_validation=reference_validation,
            evidence_items=evidence_items,
            claim_evidence=claim_evidence,
            artifacts=[],
            artifact_files=[],
            experiment_artifact_maps=[],
            environment_specifications=[],
            reproduction_plans=[],
            research_case=None,
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

    stage_started = perf_counter()
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
    logger.info(
        "Artifact discovery and inspection completed in %.2fs (artifacts=%d, files=%d)",
        perf_counter() - stage_started,
        len(artifacts),
        len(artifact_inspection.files),
    )
    stage_started = perf_counter()
    environment_specifications = await run_in_threadpool(
        reconstruct_environments,
        analysis,
        artifacts,
        artifact_inspection.files,
        artifact_inspection.experiment_maps,
        repository_provider,
        extracted.text,
    )
    logger.info(
        "Environment reconstruction completed in %.2fs (environments=%d)",
        perf_counter() - stage_started,
        len(environment_specifications),
    )
    stage_started = perf_counter()
    reproduction_plans = await run_in_threadpool(
        generate_reproduction_plans,
        analysis,
        evidence_items,
        claim_evidence,
        artifacts,
        artifact_inspection.files,
        artifact_inspection.experiment_maps,
        environment_specifications,
        extracted.text,
    )
    reproduction_targets = await run_in_threadpool(
        generate_reproduction_targets,
        analysis,
        reproduction_plans,
        artifacts,
        artifact_inspection.files,
        artifact_inspection.experiment_maps,
        environment_specifications,
    )
    execution_service.register_selection(reproduction_targets, artifacts)
    logger.info(
        "Reproduction planning completed in %.2fs (plans=%d, targets=%d, eligible=%d)",
        perf_counter() - stage_started,
        len(reproduction_plans),
        len(reproduction_targets.candidate_targets),
        sum(item.eligible for item in reproduction_targets.candidate_targets),
    )
    stage_started = perf_counter()
    research_case = await run_in_threadpool(
        build_research_case,
        analysis,
        evidence_items,
        claim_evidence,
        artifacts,
        artifact_inspection.files,
        reproduction_plans,
        extracted.text,
    )
    logger.info(
        "Research-case verification completed in %.2fs (domain=%s)",
        perf_counter() - stage_started,
        research_case.domain.value,
    )
    logger.info("Paper analysis completed in %.2fs (stage=all)", perf_counter() - request_started)
    response = AnalyzePaperResponse(
        paper_text=extracted.text,
        analysis=analysis,
        reference_validation=reference_validation,
        evidence_items=evidence_items,
        claim_evidence=claim_evidence,
        artifacts=artifacts,
        artifact_files=artifact_inspection.files,
        experiment_artifact_maps=artifact_inspection.experiment_maps,
        environment_specifications=environment_specifications,
        reproduction_plans=reproduction_plans,
        reproduction_targets=reproduction_targets,
        research_case=research_case,
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
    from datetime import datetime, timezone
    execution_service.repository.put_research_case(
        research_case.case_id,
        response.model_dump(mode="json"),
        datetime.now(timezone.utc).isoformat()
    )
    return response

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
    reproduction_plans = await run_in_threadpool(
        generate_reproduction_plans,
        analysis,
        [],
        [],
        artifacts,
        artifact_inspection.files,
        artifact_inspection.experiment_maps,
        environment_specifications,
        request.paper_text,
    )
    reproduction_targets = await run_in_threadpool(
        generate_reproduction_targets,
        analysis,
        reproduction_plans,
        artifacts,
        artifact_inspection.files,
        artifact_inspection.experiment_maps,
        environment_specifications,
    )
    execution_service.register_selection(reproduction_targets, artifacts)
    research_case = await run_in_threadpool(
        build_research_case,
        analysis,
        [],
        [],
        artifacts,
        artifact_inspection.files,
        reproduction_plans,
        request.paper_text,
    )
    
    return {
        "artifacts": [a.model_dump() for a in artifacts],
        "artifact_files": [f.model_dump() for f in artifact_inspection.files],
        "experiment_artifact_maps": [m.model_dump() for m in artifact_inspection.experiment_maps],
        "environment_specifications": [e.model_dump() for e in environment_specifications],
        "reproduction_plans": [p.model_dump() for p in reproduction_plans],
        "reproduction_targets": reproduction_targets.model_dump(),
        "research_case": research_case.model_dump(),
    }

