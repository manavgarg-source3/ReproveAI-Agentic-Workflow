"""Authenticated Step 12 report generation, history and immutable exports."""
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from app.routes.execution import _authenticated_principal
from app.schemas.assurance import AssuranceReport
from app.services.assurance import generate_report, ReportInputError
from app.services.assurance_store import ReportStore
from app.services.assurance_export import report_html
from app.services.execution.sandbox import execution_service

router = APIRouter(prefix="/api/v1", tags=["assurance-reports"])


def report_store():
    return ReportStore(execution_service.repository.path)


def reader(authorization: str | None = Header(default=None)):
    # Reports may contain research evidence: require real credentials even if
    # the separate execution API has opted into its development mode.
    if os.getenv("AUTH_MODE", "authenticated").casefold() != "authenticated":
        raise HTTPException(401, "Reports require authenticated mode.")
    return _authenticated_principal(authorization, None, None)


def author(principal=Depends(reader)):
    if principal[1] not in {"admin", "reviewer"}:
        raise HTTPException(403, "Reviewer or admin role required to generate reports.")
    return principal


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.post("/reports/{research_case_id}/generate", response_model=AssuranceReport)
def generate(research_case_id: str, request: GenerateRequest | None = None,
             principal=Depends(author), store=Depends(report_store)):
    try:
        return generate_report(store, research_case_id, principal[0])
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(409, "Persisted source validation failed: " + (str(exc) if isinstance(exc, ReportInputError) else "invalid scientific record schema")) from exc


def _load(store, report_id):
    report = store.get(report_id)
    if report is None:
        raise HTTPException(404, "Report not found")
    return report


@router.get("/reports/{report_id}", response_model=AssuranceReport)
def get_report(report_id: str, principal=Depends(reader), store=Depends(report_store)):
    return _load(store, report_id)


@router.get("/reports/{report_id}/json")
def export_json(report_id: str, principal=Depends(reader), store=Depends(report_store)):
    report = _load(store, report_id)
    return Response(report.model_dump_json(indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{report.report_id}.json"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/reports/{report_id}/html", response_class=HTMLResponse)
def export_html(report_id: str, principal=Depends(reader), store=Depends(report_store)):
    return HTMLResponse(report_html(_load(store, report_id)), headers={
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


@router.get("/research-cases/{research_case_id}/reports")
def report_history(research_case_id: str, principal=Depends(reader), store=Depends(report_store)):
    return [{"report_id": r.report_id, "research_case_id": r.research_case_id, "report_version": r.report_version,
             "report_hash": r.report_hash, "status": r.status, "generated_at": r.generated_at} for r in store.list(research_case_id)]
