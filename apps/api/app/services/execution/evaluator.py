from datetime import datetime, timezone
import hashlib
import uuid
import json

from app.schemas.diagnostic import DiagnosticExecution, DiagnosticOutcome
from app.schemas.investigation import Hypothesis, HypothesisStatus, InvestigationStatus, DiscrepancyInvestigation
from app.schemas.hypothesis_test import HypothesisTest, EvidenceStrength, StateTransitionEvent
from app.services.execution.persistence import ExecutionRepository

def evaluate_diagnostic(repo: ExecutionRepository, diagnostic_execution_id: str) -> HypothesisTest:
    # 1. Load Execution
    execution_dict = repo.load_diagnostic_execution(diagnostic_execution_id)
    if not execution_dict:
        raise ValueError("Diagnostic execution not found")
    
    execution = DiagnosticExecution.model_validate(execution_dict)
    
    # Check idempotency
    existing_test_dict = repo.load_hypothesis_test_by_diagnostic(diagnostic_execution_id)
    if existing_test_dict:
        return HypothesisTest.model_validate(existing_test_dict)
    
    # Ensure it's finished
    if execution.status not in ("COMPLETED", "FAILED", "BLOCKED"):
        raise ValueError(f"Execution not finished, status is {execution.status}")

    # Load context
    investigations_dicts = repo.investigations(execution.target_id)
    investigation_dict = next((inv for inv in investigations_dicts if inv["investigation_id"] == execution.investigation_id), None)
            
    if not investigation_dict:
        raise ValueError("Investigation not found")
        
    investigation = DiscrepancyInvestigation.model_validate(investigation_dict)
    
    # Find hypothesis and plan
    plan = next((p for p in investigation.diagnostic_plans if p.diagnostic_plan_id == execution.diagnostic_plan_id), None)
    if not plan:
        raise ValueError("Diagnostic plan not found in investigation")
        
    hypothesis = next((h for h in investigation.hypotheses if h.hypothesis_id == plan.hypothesis_id), None)
    if not hypothesis:
        raise ValueError("Hypothesis not found in investigation")
        
    # Determine Evidence Strength from Outcome
    outcome = execution.outcome
    if outcome == DiagnosticOutcome.SUPPORTING:
        evidence_strength = EvidenceStrength.HIGH
    elif outcome == DiagnosticOutcome.CONTRADICTING:
        evidence_strength = EvidenceStrength.HIGH
    elif outcome == DiagnosticOutcome.INCONCLUSIVE:
        evidence_strength = EvidenceStrength.INSUFFICIENT
    elif outcome == DiagnosticOutcome.BLOCKED:
        evidence_strength = EvidenceStrength.INSUFFICIENT
    else:
        # Default or FAILED without outcome
        evidence_strength = EvidenceStrength.INSUFFICIENT
        
    past_tests_dicts = repo.hypothesis_tests(hypothesis.hypothesis_id)
    past_tests = [HypothesisTest.model_validate(t) for t in past_tests_dicts]
    
    all_outcomes = [t.diagnostic_outcome for t in past_tests if t.diagnostic_outcome]
    if outcome:
        all_outcomes.append(outcome.value)
        
    has_supporting = "SUPPORTING" in all_outcomes
    has_contradicting = "CONTRADICTING" in all_outcomes
    has_inconclusive = "INCONCLUSIVE" in all_outcomes
    has_blocked = "BLOCKED" in all_outcomes
    
    new_status = hypothesis.status
    decision_reason = "Evaluated diagnostic execution"
    
    if has_supporting and has_contradicting:
        new_status = HypothesisStatus.INCONCLUSIVE
        decision_reason = "Conflicting evidence from multiple tests"
    elif has_supporting:
        if has_inconclusive or has_blocked:
            new_status = HypothesisStatus.WEAKLY_SUPPORTED
            decision_reason = "Supporting evidence exists but some tests were inconclusive or blocked"
        else:
            new_status = HypothesisStatus.SUPPORTED
            decision_reason = "Strong supporting evidence"
    elif has_contradicting:
        new_status = HypothesisStatus.REJECTED
        decision_reason = "Contradicting evidence found"
    else:
        if has_inconclusive:
            new_status = HypothesisStatus.INCONCLUSIVE
            decision_reason = "Test results were inconclusive"
        elif has_blocked:
            new_status = HypothesisStatus.INCONCLUSIVE
            decision_reason = "Test execution was blocked"
        else:
            new_status = HypothesisStatus.INCONCLUSIVE
            decision_reason = "No clear evidence produced"

    test_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    test = HypothesisTest(
        id=test_id,
        hypothesis_id=hypothesis.hypothesis_id,
        investigation_id=investigation.investigation_id,
        diagnostic_plan_id=plan.diagnostic_plan_id,
        diagnostic_execution_id=execution.diagnostic_execution_id,
        baseline_observed_result_id=execution.baseline_run_id,
        diagnostic_observed_result_id=execution.observed_result_id,
        diagnostic_outcome=execution.outcome.value if execution.outcome else "UNKNOWN",
        decision_rule=plan.decision_rule,
        decision_result=execution.decision_result,
        evidence_strength=evidence_strength,
        prior_status=hypothesis.status.value,
        resulting_status=new_status.value,
        decision_reason=decision_reason,
        created_at=now,
        completed_at=now
    )
    
    transitions = []
    
    if hypothesis.status != new_status:
        transitions.append(StateTransitionEvent(
            id=str(uuid.uuid4()),
            entity_type="HYPOTHESIS",
            entity_id=hypothesis.hypothesis_id,
            previous_state=hypothesis.status.value,
            new_state=new_status.value,
            reason=decision_reason,
            triggering_test_id=test.id,
            triggering_diagnostic_execution_id=execution.diagnostic_execution_id,
            created_at=now,
            context_hash=hashlib.sha256(execution.context_hash.encode()).hexdigest()
        ))
    
    inv_status = investigation.status
    inv_reason = "Hypothesis test completed"
    if new_status == HypothesisStatus.SUPPORTED:
        inv_status = InvestigationStatus.RESOLVED
        inv_reason = "A hypothesis was fully supported"
    elif new_status == HypothesisStatus.INCONCLUSIVE and (has_supporting and has_contradicting):
        inv_status = InvestigationStatus.REQUIRES_HUMAN_REVIEW
        inv_reason = "Conflicting hypothesis tests require human review"
    elif new_status == HypothesisStatus.REJECTED:
        # Check if all hypotheses are rejected
        # Need to consider other hypotheses that haven't been rejected
        all_other_rejected = True
        for h in investigation.hypotheses:
            if h.hypothesis_id != hypothesis.hypothesis_id:
                if h.status != HypothesisStatus.REJECTED:
                    all_other_rejected = False
                    break
        if all_other_rejected:
            inv_status = InvestigationStatus.UNRESOLVED
            inv_reason = "All hypotheses rejected"
        else:
            inv_status = InvestigationStatus.INVESTIGATING
            inv_reason = "Hypothesis rejected, continuing investigation"
    elif new_status == HypothesisStatus.INCONCLUSIVE:
        inv_status = InvestigationStatus.INCONCLUSIVE
        inv_reason = "Test results were inconclusive"
    elif new_status == HypothesisStatus.WEAKLY_SUPPORTED:
        inv_status = InvestigationStatus.INVESTIGATING
        inv_reason = "Hypothesis weakly supported, continuing investigation"

    if investigation.status != inv_status:
        transitions.append(StateTransitionEvent(
            id=str(uuid.uuid4()),
            entity_type="INVESTIGATION",
            entity_id=investigation.investigation_id,
            previous_state=investigation.status.value,
            new_state=inv_status.value,
            reason=inv_reason,
            triggering_test_id=test.id,
            triggering_diagnostic_execution_id=execution.diagnostic_execution_id,
            created_at=now,
            context_hash=hashlib.sha256(execution.context_hash.encode()).hexdigest()
        ))

    # Construct the updated entities to save
    updated_hypothesis = hypothesis.model_copy(update={
        "status": new_status,
        "updated_at": now
    })
    
    updated_hypotheses = list(investigation.hypotheses)
    for i, h in enumerate(updated_hypotheses):
        if h.hypothesis_id == updated_hypothesis.hypothesis_id:
            updated_hypotheses[i] = updated_hypothesis
            break
            
    updated_investigation = investigation.model_copy(update={
        "status": inv_status,
        "hypotheses": tuple(updated_hypotheses)
    })
    
    now_iso = now.isoformat()
    repo.save_evaluation_result(
        hypothesis=updated_hypothesis.model_dump(mode="json"),
        test=test.model_dump(mode="json"),
        transitions=[t.model_dump(mode="json") for t in transitions],
        investigation=updated_investigation.model_dump(mode="json"),
        test_created_at=now_iso
    )
    
    return test
