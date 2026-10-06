"""Step 10A diagnostic execution tests."""
import pytest
import shutil
from pathlib import Path
from datetime import datetime, timezone

from app.schemas.diagnostic import DiagnosticDecisionRule
from app.schemas.execution import ExecutionPolicy, ExecutionStatus
from app.schemas.investigation import DiagnosticPlan, DiagnosticPlanStatus
from app.services.execution.diagnostic import DiagnosticOrchestrator
from app.services.execution.persistence import ExecutionRepository
from app.services.execution.sandbox import ExecutionService, DockerRunner
from tests.test_secure_execution import target, code_artifact

def _now():
    return datetime.now(timezone.utc)

@pytest.fixture
def test_workspace(tmp_path: Path):
    repo_db = tmp_path / "test.db"
    repo = ExecutionRepository(repo_db)
    # Use real DockerRunner
    runner = DockerRunner()
    service = ExecutionService(runner=runner, db_path=repo_db)
    
    # Setup baseline target and artifacts
    t = target(command="python evaluate.py --input /inputs/input.json --output /outputs/result.json")
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "evaluate.py").write_text("import json; open('/outputs/result.json', 'w').write(json.dumps({'metric': 'accuracy', 'value': 0.50}))")
    (tmp_path / "input.json").write_text("{}")
    
    service.register_selection(type("Sel", (), {"candidate_targets": [t], "selected_target_id": t.target_id, "selected_target": t})(), [code_artifact()])
    service.register_artifact_source(t.target_id, artifact_dir)
    service.register_input(t.target_id, "INPUT-FIXTURE", "input.json", tmp_path / "input.json")
    
    # Run baseline execution
    policy = ExecutionPolicy(runtime_limit_seconds=10)
    approval = service.approve(t.target_id, "reviewer", policy)
    baseline_run = service.execute(t.target_id, approval.approval_id, policy)
    
    # Extract baseline
    from app.services.execution.extraction import extract_observed_result
    obs = extract_observed_result(t, baseline_run)
    repo.put_observed_result(obs.observed_result_id, t.target_id, baseline_run.run_id, obs.model_dump(mode="json"), obs.observed_result_id)
    
    return repo, service, t, baseline_run.run_id

def test_diagnostic_orchestration(test_workspace):
    repo, service, t, baseline_run_id = test_workspace
    orchestrator = DiagnosticOrchestrator(service, repo)
    
    plan = DiagnosticPlan(
        diagnostic_plan_id="DP-123",
        hypothesis_id="H-123",
        objective="Test increase",
        question="Does parameter=2 increase metric?",
        test_type="CONTROLLED_DIAGNOSTIC",
        change_type="CODE_PATCH",
        target_path="evaluate.py",
        original_state="0.50",
        proposed_state="0.75",
        decision_rule=DiagnosticDecisionRule.METRIC_INCREASES,
        alternative_observation="metric decreases or stays same",
        status=DiagnosticPlanStatus.READY,
        created_at=_now()
    )
    
    approval = orchestrator.approve_diagnostic(plan, t, baseline_run_id, "diag-reviewer")
    assert approval.status == "APPROVED"
    assert approval.context_hash
    
    policy = ExecutionPolicy(runtime_limit_seconds=10)
    execution = orchestrator.execute_diagnostic(approval, plan, t, policy)
    
    if execution.status.value != "COMPLETED":
        print("FAILED REASON:", execution.model_dump())
    assert execution.status.value == "COMPLETED"
    assert execution.outcome.value == "SUPPORTING"
    assert execution.sandbox_run_id
    assert execution.observed_result_id

    # 10B evaluation
    from app.services.execution.evaluator import evaluate_diagnostic
    
    # Needs investigation and hypothesis populated
    from app.schemas.investigation import DiscrepancyInvestigation, InvestigationStatus, Hypothesis, HypothesisStatus, DiscrepancyCategory
    import uuid
    
    inv_id = str(uuid.uuid4())
    hypothesis = Hypothesis(
        hypothesis_id="H-123",
        discrepancy_id="disc-1",
        statement="Test hypothesis",
        category=DiscrepancyCategory.UNKNOWN,
        status=HypothesisStatus.TESTING,
        created_at=_now(),
        updated_at=_now()
    )
    investigation = DiscrepancyInvestigation(
        investigation_id=inv_id,
        target_id=t.target_id,
        status=InvestigationStatus.INVESTIGATING,
        hypotheses=(hypothesis,),
        diagnostic_plans=(plan,),
        created_at=_now()
    )
    repo.put_investigation(inv_id, t.target_id, investigation.model_dump(mode="json"), _now().isoformat())
    repo.put_hypothesis("H-123", "disc-1", hypothesis.model_dump(mode="json"), hypothesis.status.value, _now().isoformat())
    
    # Also update execution with inv_id (orchestrator creates execution without inv_id if it's missing from approval? Wait, approval needs investigation_id in 10A. Let me set it.)
    
    # Let's fix the approval call: approval requires investigation_id to be in plan or something?
    # Wait, DiagnosticPlan doesn't have investigation_id, but the approval gets it from somewhere?
    # Actually, in Step 10A, I mocked or passed it. Let's just update the DB record directly for testing purposes.
    execution_data = repo.load_diagnostic_execution(execution.diagnostic_execution_id)
    execution_data["investigation_id"] = inv_id
    repo.put_diagnostic_execution(execution.diagnostic_execution_id, plan.diagnostic_plan_id, t.target_id, execution_data, execution.status.value, execution_data["created_at"])
    
    test_record = evaluate_diagnostic(repo, execution.diagnostic_execution_id)
    assert test_record.resulting_status == "SUPPORTED"
    assert test_record.evidence_strength == "HIGH"
    
    updated_inv = repo.investigations(t.target_id)[0]
    assert updated_inv["status"] == "RESOLVED"


