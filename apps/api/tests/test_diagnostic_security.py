"""Step 10A diagnostic execution security and edge case tests."""
import pytest
from pathlib import Path
import json

from app.schemas.diagnostic import DiagnosticDecisionRule, DiagnosticExecutionStatus
from app.schemas.execution import ExecutionPolicy
from app.schemas.investigation import DiagnosticPlan, DiagnosticPlanStatus
from app.services.execution.diagnostic import DiagnosticOrchestrator
from tests.test_diagnostic_execution import test_workspace, _now

def _make_plan(target_path, original_state, proposed_state, decision_rule=DiagnosticDecisionRule.METRIC_INCREASES):
    return DiagnosticPlan(
        diagnostic_plan_id="DP-SEC",
        hypothesis_id="H-SEC",
        objective="Test edge cases",
        question="Does this fail correctly?",
        test_type="CONTROLLED_DIAGNOSTIC",
        change_type="CODE_PATCH",
        target_path=target_path,
        original_state=original_state,
        proposed_state=proposed_state,
        decision_rule=decision_rule,
        alternative_observation="N/A",
        status=DiagnosticPlanStatus.READY,
        created_at=_now()
    )

def test_path_traversal_rejection(test_workspace):
    repo, service, t, baseline_run_id = test_workspace
    orchestrator = DiagnosticOrchestrator(service, repo)
    plan = _make_plan("../outside.py", "0.50", "0.75")
    
    approval = orchestrator.approve_diagnostic(plan, t, baseline_run_id, "reviewer")
    policy = ExecutionPolicy(runtime_limit_seconds=10)
    
    execution = orchestrator.execute_diagnostic(approval, plan, t, policy)
    assert execution.status == DiagnosticExecutionStatus.FAILED
    assert "traversal" in execution.decision_reason.lower()

def test_absolute_path_rejection(test_workspace):
    repo, service, t, baseline_run_id = test_workspace
    orchestrator = DiagnosticOrchestrator(service, repo)
    plan = _make_plan("/etc/passwd", "0.50", "0.75")
    
    approval = orchestrator.approve_diagnostic(plan, t, baseline_run_id, "reviewer")
    policy = ExecutionPolicy(runtime_limit_seconds=10)
    
    execution = orchestrator.execute_diagnostic(approval, plan, t, policy)
    assert execution.status == DiagnosticExecutionStatus.FAILED
    assert "traversal" in execution.decision_reason.lower()

def test_original_state_mismatch_blocking(test_workspace):
    repo, service, t, baseline_run_id = test_workspace
    orchestrator = DiagnosticOrchestrator(service, repo)
    plan = _make_plan("evaluate.py", "0.99", "0.75") # 0.99 doesn't exist in file
    
    approval = orchestrator.approve_diagnostic(plan, t, baseline_run_id, "reviewer")
    policy = ExecutionPolicy(runtime_limit_seconds=10)
    
    execution = orchestrator.execute_diagnostic(approval, plan, t, policy)
    assert execution.status == DiagnosticExecutionStatus.FAILED
    assert "not found in target file" in execution.decision_reason.lower()

def test_decision_rule_decreases(test_workspace):
    repo, service, t, baseline_run_id = test_workspace
    orchestrator = DiagnosticOrchestrator(service, repo)
    # 0.25 is < 0.50, so DECREASES should be SUPPORTING
    plan = _make_plan("evaluate.py", "0.50", "0.25", DiagnosticDecisionRule.METRIC_DECREASES)
    
    approval = orchestrator.approve_diagnostic(plan, t, baseline_run_id, "reviewer")
    policy = ExecutionPolicy(runtime_limit_seconds=10)
    
    execution = orchestrator.execute_diagnostic(approval, plan, t, policy)
    assert execution.status == DiagnosticExecutionStatus.COMPLETED
    assert execution.outcome.value == "SUPPORTING"


