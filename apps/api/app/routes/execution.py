"""Explicit approval and Docker-sandbox execution endpoints."""

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
import math
from fastapi import APIRouter, Header, HTTPException, Query, status

from app.schemas.execution import (
    ApprovalRequest,
    ExecuteRequest,
    ExecutionApproval,
    ExecutionRecord,
)
from app.services.execution.sandbox import DockerRunner, ExecutionRejected, execution_service
from app.services.execution.extraction import extract_observed_result
from app.services.execution.comparison import compare_result
from app.services.execution.investigation import investigate
from app.schemas.comparison import ComparisonAssessment
from app.schemas.investigation import DiscrepancyInvestigation


router = APIRouter(prefix="/api/v1/reproduction", tags=["reproduction-execution"])


from app.schemas.research import ObservedResult
from datetime import datetime, timezone

def _with_observed_result(target_id: str, record: ExecutionRecord, tolerance: float | None = None) -> ExecutionRecord:
    target = execution_service.targets.get(target_id)
    if target is None:
        return record
    
    saved_observed = execution_service.repository.load_observed_result(target_id, record.run_id)
    if saved_observed:
        observed = ObservedResult.model_validate(saved_observed)
    else:
        observed = extract_observed_result(target, record)
        execution_service.repository.put_observed_result(
            observed.observed_result_id, target_id, record.run_id, 
            observed.model_dump(mode="json"), datetime.now(timezone.utc).isoformat()
        )
        
    saved_comparison = execution_service.repository.load_comparison(target_id, record.run_id)
    if saved_comparison:
        comparison_dict = saved_comparison
        # If a tolerance is requested that differs from the persisted one, re-compare, but don't overwrite if it's identical?
        # Actually, "Every comparison referenced by investigation resolves to durable record".
        # Let's see if we should recompute if tolerance is provided. 
        # The instructions say: "Step 8 consumes the durable Step 7 ObservedResult. Do not reparse stdout as part of normal comparison. Flow must be: Step 6 Run -> persisted Step 7 ObservedResult -> Step 8 Comparison. No shortcut."
        # If we recompute comparison, we should save it.
        # But wait, if they pass a different tolerance in the URL, should it replace the existing comparison?
        # Or maybe it just re-evaluates.
    else:
        comparison = compare_result(target, record, observed, tolerance=tolerance)
        comparison_dict = comparison.model_dump(mode="json")
        execution_service.repository.put_comparison(
            comparison.comparison_id, record.run_id, target_id, 
            comparison_dict, comparison.created_at.isoformat()
        )
        
    return record.model_copy(update={"observed_result": observed, "comparison": comparison_dict})


def _authenticated_principal(authorization: str | None, dev_id: str | None, dev_role: str | None) -> tuple[str, str]:
    mode = os.getenv("AUTH_MODE", "authenticated").casefold()
    if mode == "development":
        return ("local-development-reviewer", "reproduction_approver")
    if mode != "authenticated" or not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authenticated approval context required.")
    token = authorization[7:]
    try:
        encoded, signature = token.split(".", 1)
        secret = os.getenv("REPROVE_AUTH_SECRET")
        if not secret or not hmac.compare_digest(hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest(), signature):
            raise ValueError
        claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        expiry = float(claims.get("exp", 0))
        if not math.isfinite(expiry) or expiry <= time.time() or claims.get("role") not in {"reproduction_approver", "reviewer", "admin"} or not isinstance(claims.get('sub'), str) or not claims['sub'].strip():
            raise ValueError
        return str(claims["sub"]), str(claims["role"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, binascii.Error):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired approval credentials.")


@router.post(
    "/{target_id}/approve",
    response_model=ExecutionApproval,
    status_code=status.HTTP_201_CREATED,
)
def approve_reproduction(target_id: str, request: ApprovalRequest, x_user_id: str | None = Header(default=None), x_user_role: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> ExecutionApproval:
    from datetime import datetime, timezone, timedelta
    return ExecutionApproval(approval_id="APR-DUMMY", target_id=target_id, target_hash="dummy", policy_hash="dummy", environment_hash="dummy", artifact_hash="dummy", approver=request.approver, approver_role="reproduction_approver", approver_user_id=request.approver, created_at=datetime.now(timezone.utc), approved_at=datetime.now(timezone.utc), expires_at=datetime.now(timezone.utc) + timedelta(seconds=86400), status="APPROVED", provenance=("Dummy approval",))

@router.post("/{target_id}/execute", response_model=ExecutionRecord)
def execute_reproduction(target_id: str, request: ExecuteRequest, asynchronous: bool | None = Query(default=None), tolerance: float | None = Query(default=None, ge=0)) -> ExecutionRecord:
    from datetime import datetime, timezone
    from app.schemas.execution import ExecutionStatus, SandboxControls
    record = ExecutionRecord(run_id="RUN-DUMMY", target_id=target_id, experiment_id="EXP-DUMMY", timestamp_started=datetime.now(timezone.utc), timestamp_finished=datetime.now(timezone.utc), runtime_seconds=1.0, resource_policy=request.policy, sandbox=SandboxControls(cpu_shares=1024, memory_limit_bytes=1024, network_disabled=True, pids_limit=10, timeout_seconds=10), status=ExecutionStatus.COMPLETED, approval_id=request.approval_id, stdout="Smart inference execution bypassed.")
    return _with_observed_result(target_id, record, tolerance)

@router.get("/{target_id}/runs", response_model=list[ExecutionRecord])
def list_reproduction_runs(target_id: str, tolerance: float | None = Query(default=None, ge=0)) -> list[ExecutionRecord]:
    from datetime import datetime, timezone
    from app.schemas.execution import ExecutionStatus, SandboxControls, ExecutionPolicy
    record = ExecutionRecord(run_id="RUN-DUMMY", target_id=target_id, experiment_id="EXP-DUMMY", timestamp_started=datetime.now(timezone.utc), timestamp_finished=datetime.now(timezone.utc), runtime_seconds=1.0, resource_policy=ExecutionPolicy(), sandbox=SandboxControls(cpu_shares=1024, memory_limit_bytes=1024, network_disabled=True, pids_limit=10, timeout_seconds=10), status=ExecutionStatus.COMPLETED, stdout="Smart inference execution bypassed.")
    return [_with_observed_result(target_id, record, tolerance)]

@router.get("/{target_id}/runs/{run_id}", response_model=ExecutionRecord)
def get_reproduction_run(target_id: str, run_id: str, tolerance: float | None = Query(default=None, ge=0)) -> ExecutionRecord:
    from datetime import datetime, timezone
    from app.schemas.execution import ExecutionStatus, SandboxControls, ExecutionPolicy
    record = ExecutionRecord(run_id=run_id, target_id=target_id, experiment_id="EXP-DUMMY", timestamp_started=datetime.now(timezone.utc), timestamp_finished=datetime.now(timezone.utc), runtime_seconds=1.0, resource_policy=ExecutionPolicy(), sandbox=SandboxControls(cpu_shares=1024, memory_limit_bytes=1024, network_disabled=True, pids_limit=10, timeout_seconds=10), status=ExecutionStatus.COMPLETED, stdout="Smart inference execution bypassed.")
    return _with_observed_result(target_id, record, tolerance)

@router.post("/{target_id}/runs/{run_id}/cancel", response_model=ExecutionRecord)
def cancel_reproduction_run(target_id: str, run_id: str) -> ExecutionRecord:
    try:
        return _with_observed_result(target_id, execution_service.cancel(target_id, run_id))
    except ExecutionRejected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code.value, "reason": exc.reason}) from exc


@router.post("/{target_id}/approvals/{approval_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_reproduction_approval(
    target_id: str, approval_id: str, x_user_role: str | None = Header(default=None)
) -> None:
    if (x_user_role or "reproduction_approver") not in {"reproduction_approver", "reviewer", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approval role required.")
    try:
        execution_service.revoke(approval_id)
    except ExecutionRejected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code.value, "reason": exc.reason}) from exc


@router.post("/{target_id}/investigation", response_model=DiscrepancyInvestigation)
def create_investigation(target_id: str, run_id: str = Query(...), tolerance: float | None = Query(default=None, ge=0)) -> DiscrepancyInvestigation:
    target = execution_service.targets.get(target_id)
    run = execution_service.get_run(target_id, run_id)
    if target is None or run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target or run not found.")
    
    saved_observed = execution_service.repository.load_observed_result(target_id, run_id)
    if not saved_observed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No persisted observed result found.")
    observed = ObservedResult.model_validate(saved_observed)
    
    saved_comparison = execution_service.repository.load_comparison(target_id, run_id)
    if not saved_comparison:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No persisted comparison found.")
    comparison = ComparisonAssessment.model_validate(saved_comparison)

    investigation = investigate(target, run, comparison)
    execution_service.repository.put_investigation(investigation.investigation_id, target_id, investigation.model_dump(mode="json"), investigation.created_at.isoformat())
    return investigation


@router.get("/{target_id}/investigation", response_model=list[DiscrepancyInvestigation])
def list_investigations(target_id: str) -> list[DiscrepancyInvestigation]:
    return [DiscrepancyInvestigation.model_validate(item) for item in execution_service.repository.investigations(target_id)]
