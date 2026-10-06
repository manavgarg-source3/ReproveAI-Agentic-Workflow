import pytest
from datetime import datetime, timezone
import uuid
import json

from app.schemas.diagnostic import DiagnosticExecution, DiagnosticOutcome, DiagnosticExecutionStatus
from app.schemas.investigation import (
    Hypothesis, HypothesisStatus, InvestigationStatus, DiscrepancyInvestigation, DiscrepancyCategory, DiagnosticPlan, DiagnosticExecutionType, DiagnosticPlanStatus
)
from app.services.execution.persistence import ExecutionRepository
from app.services.execution.evaluator import evaluate_diagnostic

@pytest.fixture
def repo(tmp_path):
    import sqlite3
    db_path = tmp_path / "test.db"
    repo = ExecutionRepository(str(db_path))
    return repo

def create_base_data(repo, target_id="target-1", outcome=DiagnosticOutcome.SUPPORTING, status=DiagnosticExecutionStatus.COMPLETED):
    inv_id = str(uuid.uuid4())
    hyp_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    exec_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    hypothesis = Hypothesis(
        hypothesis_id=hyp_id,
        discrepancy_id="disc-1",
        statement="Test hypothesis",
        category=DiscrepancyCategory.UNKNOWN,
        status=HypothesisStatus.TESTING,
        created_at=now,
        updated_at=now
    )
    
    plan = DiagnosticPlan(
        diagnostic_plan_id=plan_id,
        hypothesis_id=hyp_id,
        objective="Test plan",
        question="Why?",
        test_type="A",
        change_type="CODE_PATCH",
        target_path="main.py",
        original_state="a",
        proposed_state="b",
        decision_rule="METRIC_INCREASES",
        alternative_observation="c",
        created_at=now
    )
    
    investigation = DiscrepancyInvestigation(
        investigation_id=inv_id,
        target_id=target_id,
        status=InvestigationStatus.INVESTIGATING,
        hypotheses=(hypothesis,),
        diagnostic_plans=(plan,),
        created_at=now
    )
    
    repo.put_investigation(inv_id, target_id, investigation.model_dump(mode="json"), now.isoformat())
    repo.put_hypothesis(hyp_id, "disc-1", hypothesis.model_dump(mode="json"), hypothesis.status.value, now.isoformat())
    
    execution = DiagnosticExecution(
        diagnostic_execution_id=exec_id,
        investigation_id=inv_id,
        diagnostic_plan_id=plan_id,
        target_id=target_id,
        baseline_run_id="run-1",
        status=status,
        outcome=outcome,
        context_hash="hash",
        baseline_manifest_hash="bhash",
        created_at=now,
        completed_at=now
    )
    
    repo.put_diagnostic_execution(exec_id, plan_id, target_id, execution.model_dump(mode="json"), status.value, now.isoformat())
    
    return repo, exec_id, hyp_id, inv_id

def test_evaluator_supporting(repo):
    repo, exec_id, hyp_id, inv_id = create_base_data(repo, outcome=DiagnosticOutcome.SUPPORTING)
    test = evaluate_diagnostic(repo, exec_id)
    assert test.resulting_status == "SUPPORTED"
    
    hyp = repo.load_hypothesis(hyp_id)
    assert hyp["status"] == "SUPPORTED"
    
    invs = repo.investigations("target-1")
    assert invs[0]["status"] == "RESOLVED"

def test_evaluator_contradicting(repo):
    repo, exec_id, hyp_id, inv_id = create_base_data(repo, outcome=DiagnosticOutcome.CONTRADICTING)
    test = evaluate_diagnostic(repo, exec_id)
    assert test.resulting_status == "REJECTED"
    
    hyp = repo.load_hypothesis(hyp_id)
    assert hyp["status"] == "REJECTED"
    
    invs = repo.investigations("target-1")
    # if only 1 hypothesis and it's rejected, it becomes UNRESOLVED
    assert invs[0]["status"] == "UNRESOLVED"

def test_evaluator_inconclusive(repo):
    repo, exec_id, hyp_id, inv_id = create_base_data(repo, outcome=DiagnosticOutcome.INCONCLUSIVE)
    test = evaluate_diagnostic(repo, exec_id)
    assert test.resulting_status == "INCONCLUSIVE"
    
    hyp = repo.load_hypothesis(hyp_id)
    assert hyp["status"] == "INCONCLUSIVE"
    
    invs = repo.investigations("target-1")
    assert invs[0]["status"] == "INCONCLUSIVE"

def test_evaluator_blocked(repo):
    repo, exec_id, hyp_id, inv_id = create_base_data(repo, outcome=DiagnosticOutcome.BLOCKED)
    test = evaluate_diagnostic(repo, exec_id)
    assert test.resulting_status == "INCONCLUSIVE"
    
    hyp = repo.load_hypothesis(hyp_id)
    assert hyp["status"] == "INCONCLUSIVE"

def test_evaluator_idempotency(repo):
    repo, exec_id, hyp_id, inv_id = create_base_data(repo, outcome=DiagnosticOutcome.SUPPORTING)
    test1 = evaluate_diagnostic(repo, exec_id)
    test2 = evaluate_diagnostic(repo, exec_id)
    assert test1.id == test2.id
    tests = repo.hypothesis_tests(hyp_id)
    assert len(tests) == 1

def test_evaluator_conflict(repo):
    # Setup first test supporting
    repo, exec_id, hyp_id, inv_id = create_base_data(repo, outcome=DiagnosticOutcome.SUPPORTING)
    evaluate_diagnostic(repo, exec_id)
    
    # Setup second test contradicting
    exec_id2 = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    inv = repo.investigations("target-1")[0]
    plan_id = inv["diagnostic_plans"][0]["diagnostic_plan_id"]
    execution2 = DiagnosticExecution(
        diagnostic_execution_id=exec_id2,
        investigation_id=inv_id,
        diagnostic_plan_id=plan_id,
        target_id="target-1",
        baseline_run_id="run-1",
        status=DiagnosticExecutionStatus.COMPLETED,
        outcome=DiagnosticOutcome.CONTRADICTING,
        context_hash="hash2",
        baseline_manifest_hash="bhash",
        created_at=now,
        completed_at=now
    )
    repo.put_diagnostic_execution(exec_id2, plan_id, "target-1", execution2.model_dump(mode="json"), "COMPLETED", now.isoformat())
    
    test2 = evaluate_diagnostic(repo, exec_id2)
    assert test2.resulting_status == "INCONCLUSIVE"
    
    hyp = repo.load_hypothesis(hyp_id)
    assert hyp["status"] == "INCONCLUSIVE"
    
    invs = repo.investigations("target-1")
    assert invs[0]["status"] == "REQUIRES_HUMAN_REVIEW"

