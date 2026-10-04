"""
FastAPI REST API and Web Application Server for the Scientometric Dashboard.
Delivers sub-10ms query responses, JSON REST endpoints, and serves the dark-themed React SPA.
"""
import os
import io
import csv
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Query, HTTPException, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from config import BASE_DIR
from src.web.db import (
    init_search_db,
    get_kpi_stats,
    query_references,
    get_reference_by_id,
    update_reference_review,
    get_documents_summary,
)
from src.pipeline.custom_runner import run_custom_audit, CUSTOM_RUNS_DIR
from src.pipeline.v2_documents import (
    init_v2_documents_table,
    populate_v2_documents,
    query_v2_documents,
    get_v2_document_detail,
    run_llm_audit_for_document,
    get_v2_corpus_stats,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Scholarly Reference Validation API",
    description="High-performance backend for scientometric reference validation audit studio.",
    version="2.0.0",
)

# Enable CORS for local dev servers (e.g. Vite on port 5173 or 3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


class ReviewUpdateRequest(BaseModel):
    reviewed: bool
    user_notes: Optional[str] = ""
    status_override: Optional[str] = None


@app.on_event("startup")
def startup_event():
    """Ensure database indexes are initialized on startup."""
    init_search_db()
    init_v2_documents_table()
    logger.info("FastAPI Scientometric Dashboard backend initialized.")


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "scientometric-validator"}


@app.get("/api/stats")
def api_stats():
    """Returns top-level KPI metrics, status distributions, and confidence levels."""
    try:
        stats = get_kpi_stats()
        return stats
    except Exception as e:
        logger.error(f"Error fetching KPI stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/references")
def api_references(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=500, description="Number of items per page"),
    q: Optional[str] = Query(None, description="Search term across citation, title, author, DOI, or Ref ID"),
    status: Optional[str] = Query(None, description="Comma-separated final statuses (e.g. VALID_CORRECT,SCOPUS_UNLINKED)"),
    confidence: Optional[str] = Query(None, description="Comma-separated confidence levels (HIGH,MEDIUM,LOW,UNCERTAIN)"),
    scopus_linked: Optional[str] = Query("all", pattern="^(all|true|false)$", description="Filter by Scopus linkage"),
    needs_review: Optional[str] = Query("all", pattern="^(all|true|false)$", description="Filter by human review requirement"),
    has_doi: Optional[str] = Query("all", pattern="^(all|true|false)$", description="Filter by DOI presence"),
    source_eid: Optional[str] = Query(None, description="Filter by specific source manuscript EID"),
    sort_by: str = Query("reference_id", description="Column to sort by"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$", description="Sort direction"),
):
    """
    Sub-10ms paginated query with multi-faceted filtering.
    """
    try:
        status_list = [s.strip() for s in status.split(",") if s.strip()] if status else None
        conf_list = [c.strip() for c in confidence.split(",") if c.strip()] if confidence else None

        rows, total = query_references(
            page=page,
            page_size=page_size,
            search_query=q or "",
            statuses=status_list,
            confidences=conf_list,
            scopus_linked=scopus_linked,
            needs_review=needs_review,
            has_doi=has_doi,
            source_eid=source_eid,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        total_pages = max(1, (total + page_size - 1) // page_size)

        return {
            "items": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Error querying references: {e}")
        raise HTTPException(status_code=500, detail=str(e))


_CUSTOM_AUDIT_CACHE: Dict[str, Dict[str, Any]] = {}


@app.get("/api/references/{reference_id:path}")
def api_reference_detail(reference_id: str):
    """Returns single reference detail with full audit and diagnostics."""
    item = get_reference_by_id(reference_id)
    if not item:
        item = _CUSTOM_AUDIT_CACHE.get(reference_id)
    if not item:
        raise HTTPException(status_code=404, detail="Reference not found")
    return item


@app.patch("/api/references/{reference_id:path}")
def api_update_review(reference_id: str, req: ReviewUpdateRequest):
    """Updates researcher review status, notes, or manual classification override."""
    if reference_id in _CUSTOM_AUDIT_CACHE:
        c_item = _CUSTOM_AUDIT_CACHE[reference_id]
        c_item["reviewed_by_user"] = 1 if req.reviewed else 0
        c_item["user_notes"] = req.user_notes or ""
        if req.status_override:
            c_item["final_status"] = req.status_override
        return {"status": "success", "reference": c_item}

    success = update_reference_review(
        reference_id=reference_id,
        reviewed=req.reviewed,
        user_notes=req.user_notes or "",
        status_override=req.status_override,
    )
    if not success:
        raise HTTPException(status_code=400, detail="Update failed")
    updated = get_reference_by_id(reference_id)
    return {"status": "success", "reference": updated}


@app.get("/api/documents")
def api_documents(
    q: Optional[str] = Query("", description="Search term for citing manuscript"),
    limit: int = Query(1000, ge=1, le=2000),
):
    """Returns source manuscripts with reference metrics."""
    try:
        docs = get_documents_summary(search=q or "", limit=limit)
        return {"items": docs, "total": len(docs)}
    except Exception as e:
        logger.error(f"Error fetching documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# V2 Scientometric & AI Document-Wise Endpoints
# ==========================================

@app.get("/api/v2/stats")
def api_v2_stats():
    """Returns V2 Scientometric Corpus statistics (Price's Index, median age, risk distribution)."""
    try:
        return get_v2_corpus_stats()
    except Exception as e:
        logger.error(f"Error getting V2 stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v2/documents")
def api_v2_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    q: Optional[str] = Query("", description="Search manuscript title, author, or EID"),
    grade: Optional[str] = Query(None, description="Comma-separated audit grades (A+,A,B,C,REQUIRES_REVISION)"),
    risk: Optional[str] = Query(None, description="Comma-separated risk levels (HIGH,MEDIUM,LOW)"),
    freshness: Optional[str] = Query(None, description="Comma-separated freshness (CUTTING_EDGE,BALANCED,DATED_OBSOLESCENT)"),
    sort_by: str = Query("total_references"),
    sort_order: str = Query("desc"),
):
    """Returns paginated, searchable, filterable V2 document scientometric reports."""
    try:
        rows, total = query_v2_documents(
            page=page,
            page_size=page_size,
            search=q or "",
            grade=grade,
            risk=risk,
            freshness=freshness,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Error querying V2 documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v2/document/{source_eid:path}")
def api_v2_document_detail(source_eid: str):
    """Returns full V2 scientometric profile and reference collection for a single manuscript."""
    try:
        doc = get_v2_document_detail(source_eid)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching V2 document detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v2/document/{source_eid:path}/run-ai")
def api_v2_run_document_ai(source_eid: str):
    """Triggers the local Ollama LLM to synthesize/refresh the executive audit for a manuscript."""
    try:
        doc = run_llm_audit_for_document(source_eid)
        return {"status": "success", "document": doc}
    except Exception as e:
        logger.error(f"Error running LLM audit for document {source_eid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v2/run-models")
def api_v2_run_models():
    """Recalculates V2 scientometric indicators across all corpus manuscripts."""
    try:
        count = populate_v2_documents(force_recalculate=True)
        stats = get_v2_corpus_stats()
        return {"status": "success", "recalculated_documents": count, "stats": stats}
    except Exception as e:
        logger.error(f"Error running V2 models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export")
def api_export_csv(
    q: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    confidence: Optional[str] = Query(None),
    scopus_linked: Optional[str] = Query("all"),
    needs_review: Optional[str] = Query("all"),
    has_doi: Optional[str] = Query("all"),
    source_eid: Optional[str] = Query(None),
):
    """Streams filtered query results directly as CSV download."""
    status_list = [s.strip() for s in status.split(",") if s.strip()] if status else None
    conf_list = [c.strip() for c in confidence.split(",") if c.strip()] if confidence else None

    # Fetch up to 20,000 matches for export
    rows, total = query_references(
        page=1,
        page_size=20000,
        search_query=q or "",
        statuses=status_list,
        confidences=conf_list,
        scopus_linked=scopus_linked,
        needs_review=needs_review,
        has_doi=has_doi,
        source_eid=source_eid,
    )

    if not rows:
        raise HTTPException(status_code=404, detail="No matching records to export")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="references_export.csv"'},
    )


@app.post("/api/custom-audit/run")
async def api_run_custom_audit(
    scopus_link: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    """
    On-demand scientometric validation runner for custom Scopus link, uploaded CSV/XLS, or both.
    """
    try:
        file_bytes = None
        filename = None
        if file and file.filename:
            file_bytes = await file.read()
            filename = file.filename

        if not scopus_link and not file_bytes:
            raise HTTPException(
                status_code=400,
                detail="Please provide a Scopus publication link / EID or upload a PDF, Word (.docx), CSV, or Excel file."
            )

        job_data = run_custom_audit(
            scopus_identifier=scopus_link,
            uploaded_file_bytes=file_bytes,
            uploaded_filename=filename,
        )
        for r in job_data.get("items", []):
            if r.get("reference_id"):
                _CUSTOM_AUDIT_CACHE[r["reference_id"]] = r
        return job_data
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error in custom audit run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Audit execution error: {str(e)}")


@app.get("/api/custom-audit/download/{job_id}")
def api_download_custom_audit(
    job_id: str,
    format: str = Query("excel", pattern="^(excel|csv)$"),
):
    """
    Downloads the processed Excel report (.xlsx) or CSV export (.csv) for a completed custom audit job.
    """
    if format == "excel":
        file_path = CUSTOM_RUNS_DIR / f"{job_id}.xlsx"
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Excel report not found for this job ID")
        return FileResponse(
            path=str(file_path),
            filename=f"{job_id}_validation_report.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        file_path = CUSTOM_RUNS_DIR / f"{job_id}.csv"
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="CSV report not found for this job ID")
        return FileResponse(
            path=str(file_path),
            filename=f"{job_id}_references.csv",
            media_type="text/csv",
        )


# ==========================================
# LLM Bibliometric Intelligence Endpoints
# ==========================================

class CitationParseRequest(BaseModel):
    raw_reference: str


class DiscrepancyAuditRequest(BaseModel):
    cited_data: Dict[str, Any]
    resolved_data: Dict[str, Any]
    http_status: Optional[int] = 200


class CitationIntentRequest(BaseModel):
    sentence_context: str
    marker: Optional[str] = ""
    cited_title: Optional[str] = ""


class SynthesizeAuditRequest(BaseModel):
    doc_title: Optional[str] = "Manuscript"
    references: List[Dict[str, Any]]
    document_diagnostics: Optional[Dict[str, Any]] = None


@app.get("/api/llm/status")
def api_llm_status():
    """Returns status and configuration of active LLM provider."""
    from src.llm.client import LLMClient
    client = LLMClient.get_default()
    return client.get_status()


@app.post("/api/llm/parse-citation")
def api_llm_parse_citation(req: CitationParseRequest):
    """Parses complex raw reference string into structured bibliographic fields."""
    from src.llm.citation_extractor import LLMCitationExtractor
    extractor = LLMCitationExtractor()
    return extractor.parse(req.raw_reference)


@app.post("/api/llm/audit-discrepancy")
def api_llm_audit_discrepancy(req: DiscrepancyAuditRequest):
    """Semantically audits cited reference vs resolved Crossref/Scopus metadata."""
    from src.llm.discrepancy_auditor import LLMDiscrepancyAuditor
    auditor = LLMDiscrepancyAuditor()
    return auditor.audit(req.cited_data, req.resolved_data, req.http_status)


@app.post("/api/llm/citation-intent")
def api_llm_citation_intent(req: CitationIntentRequest):
    """Classifies in-text citation sentence into standard scientometric stances."""
    from src.llm.citation_intent import CitationIntentClassifier
    classifier = CitationIntentClassifier()
    return classifier.classify(req.sentence_context, req.marker or "", req.cited_title or "")


@app.post("/api/llm/synthesize-audit")
def api_llm_synthesize_audit(req: SynthesizeAuditRequest):
    """Generates Price Index, half-life, and full executive scientometric synthesis."""
    from src.llm.scientometric_synthesizer import ScientometricSynthesizer
    synthesizer = ScientometricSynthesizer()
    return synthesizer.generate_executive_audit(
        doc_title=req.doc_title or "Manuscript",
        references=req.references,
        document_diagnostics=req.document_diagnostics,
    )


# Serve built React frontend if frontend/dist exists
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend_spa(full_path: str):
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Frontend not built yet. Run npm run build in frontend directory."}
