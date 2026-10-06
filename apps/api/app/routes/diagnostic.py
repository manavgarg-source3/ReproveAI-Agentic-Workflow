"""Step 10A diagnostic endpoints."""

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from app.schemas.diagnostic import DiagnosticApproval, DiagnosticExecution
from app.schemas.execution import ExecutionPolicy
from app.schemas.investigation import DiagnosticPlan
from app.services.execution.diagnostic import DiagnosticOrchestrator
from app.services.execution.sandbox import execution_service
from app.routes.execution import _authenticated_principal

router = APIRouter(prefix="/api/v1/diagnostic", tags=["diagnostic"])

# Instantiate orchestrator
# Note: execution_service and its repository are global singletons
orchestrator = DiagnosticOrchestrator(execution_service, execution_service.repository)

class DiagnosticApproveRequest(BaseModel):
    plan: DiagnosticPlan
    baseline_run_id: str

class DiagnosticExecuteRequest(BaseModel):
    approval_id: str
    plan: DiagnosticPlan
    policy: ExecutionPolicy

@router.post(
    "/{target_id}/approve",
    response_model=DiagnosticApproval,
    status_code=status.HTTP_201_CREATED,
)
def approve_diagnostic(
    target_id: str,
    request: DiagnosticApproveRequest,
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> DiagnosticApproval:
    user_id, role = _authenticated_principal(authorization, x_user_id, x_user_role)
    if role not in {"reproduction_approver", "reviewer", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approval role required.")
    
    target = execution_service.targets.get(target_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found.")

    try:
        return orchestrator.approve_diagnostic(request.plan, target, request.baseline_run_id, user_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )

@router.post("/{target_id}/execute", response_model=DiagnosticExecution)
def execute_diagnostic(
    target_id: str,
    request: DiagnosticExecuteRequest
) -> DiagnosticExecution:
    target = execution_service.targets.get(target_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found.")
        
    approval_data = execution_service.repository.load("diagnostic_approvals", request.approval_id)
    if not approval_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found.")
    
    approval = DiagnosticApproval.model_validate(approval_data)
    
    try:
        return orchestrator.execute_diagnostic(approval, request.plan, target, request.policy)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@router.get("/{target_id}/runs/{execution_id}", response_model=DiagnosticExecution)
def get_diagnostic_execution(target_id: str, execution_id: str) -> DiagnosticExecution:
    execution_data = execution_service.repository.load("diagnostic_executions", execution_id)
    if not execution_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic execution not found.")
    return DiagnosticExecution.model_validate(execution_data)

from app.schemas.hypothesis_test import HypothesisTest
from app.schemas.investigation import Hypothesis, DiscrepancyInvestigation
from app.services.execution.evaluator import evaluate_diagnostic

@router.post("/{target_id}/runs/{execution_id}/evaluate", response_model=HypothesisTest)
def api_evaluate_diagnostic(target_id: str, execution_id: str) -> HypothesisTest:
    execution_data = execution_service.repository.load("diagnostic_executions", execution_id)
    if not execution_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic execution not found.")
    if execution_data.get("target_id") != target_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target ID mismatch.")
    try:
        return evaluate_diagnostic(execution_service.repository, execution_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@router.get("/{target_id}/hypotheses/{hypothesis_id}", response_model=Hypothesis)
def get_hypothesis(target_id: str, hypothesis_id: str) -> Hypothesis:
    data = execution_service.repository.load_hypothesis(hypothesis_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hypothesis not found.")
    return Hypothesis.model_validate(data)

@router.get("/{target_id}/hypotheses/{hypothesis_id}/tests", response_model=list[HypothesisTest])
def get_hypothesis_tests(target_id: str, hypothesis_id: str) -> list[HypothesisTest]:
    tests = execution_service.repository.hypothesis_tests(hypothesis_id)
    return [HypothesisTest.model_validate(t) for t in tests]

@router.get("/{target_id}/investigations", response_model=list[DiscrepancyInvestigation])
def list_investigations(target_id: str) -> list[DiscrepancyInvestigation]:
    invs = execution_service.repository.investigations(target_id)
    return [DiscrepancyInvestigation.model_validate(inv) for inv in invs]


