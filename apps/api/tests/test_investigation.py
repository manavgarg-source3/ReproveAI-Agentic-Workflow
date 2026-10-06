from datetime import datetime, timezone
from app.schemas.comparison import ComparisonAssessment, ComparisonStatus, ReproductionStatus
from app.schemas.execution import ExecutionPolicy, ExecutionRecord, ExecutionStatus
from app.schemas.research import ObservedResult, ObservedResultStatus, PublishedResult, Certainty
from app.services.execution.investigation import investigate
from tests.test_secure_execution import target

def run(status=ExecutionStatus.COMPLETED):
    now=datetime.now(timezone.utc)
    return ExecutionRecord(run_id="RUN-INV",target_id="TARGET-FIXTURE",experiment_id="EXP-FIXTURE",timestamp_started=now,timestamp_finished=now,runtime_seconds=0,resource_policy=ExecutionPolicy(),sandbox={"image":"python:3.12-slim"},status=status)

def comparison(status):
    return ComparisonAssessment(comparison_id="CMP-INV",target_id="TARGET-FIXTURE",experiment_id="EXP-FIXTURE",run_id="RUN-INV",metric_name="accuracy",published_value=.75,observed_value=.70,absolute_difference=.05,tolerance=.01,comparison_status=ComparisonStatus.COMPARABLE,reproduction_status=status,created_at=datetime.now(timezone.utc))

def target_with_pub():
    return target().model_copy(update={"metric":"accuracy","published_result":PublishedResult(metric_name="accuracy",reported_value=.75,evidence="fixture",certainty=Certainty.EXPLICIT)})

def test_not_reproduced_creates_discrepancy_hypotheses_and_plans():
    result=investigate(target_with_pub(),run(),comparison(ReproductionStatus.NOT_REPRODUCED))
    assert result.status.value=="DETECTED" and result.discrepancy and len(result.hypotheses)==3 and len(result.diagnostic_plans)==3
    assert all(item.status.value=="PROPOSED" for item in result.hypotheses)
    assert all(item.status.value=="DRAFT" for item in result.diagnostic_plans)
    
    # Verify zero-evidence constraint (Finding 5)
    for h in result.hypotheses:
        assert h.confidence == "LOW"
        assert "[LOW EVIDENCE CANDIDATE]" in h.statement
        
    # Verify diagnostic plan executability constraint (Finding 6)
    for p in result.diagnostic_plans:
        assert p.change_type in ("DATASET", "PREPROCESSING", "CONFIGURATION")
        assert p.target_path and p.original_state and p.proposed_state and p.decision_rule

def test_verified_creates_no_discrepancy():
    result=investigate(target_with_pub(),run(),comparison(ReproductionStatus.VERIFIED))
    assert result.status.value=="NO_DISCREPANCY" and result.discrepancy is None and not result.hypotheses

def test_blocked_remains_blocked():
    result=investigate(target_with_pub(),run(ExecutionStatus.BLOCKED),comparison(ReproductionStatus.BLOCKED))
    assert result.status.value=="BLOCKED" and result.discrepancy is None

def test_inconclusive_has_no_strong_hypotheses():
    result=investigate(target_with_pub(),run(),comparison(ReproductionStatus.INCONCLUSIVE))
    assert result.status.value=="INCONCLUSIVE" and not result.hypotheses

def test_hypotheses_are_not_supported_without_diagnostics():
    result=investigate(target_with_pub(),run(),comparison(ReproductionStatus.NOT_REPRODUCED))
    assert all(item.status.value=="PROPOSED" for item in result.hypotheses)

def test_plans_never_execute():
    result=investigate(target_with_pub(),run(),comparison(ReproductionStatus.NOT_REPRODUCED))
    assert all(item.status.value != "EXECUTED" for item in result.diagnostic_plans)

def test_no_author_blame_language():
    result=investigate(target_with_pub(),run(),comparison(ReproductionStatus.NOT_REPRODUCED))
    text=" ".join(item.statement for item in result.hypotheses)
    assert "authors" not in text.casefold() and "fraud" not in text.casefold()

def test_provenance_links_comparison():
    result=investigate(target_with_pub(),run(),comparison(ReproductionStatus.NOT_REPRODUCED))
    assert result.comparison_id=="CMP-INV" and result.discrepancy.comparison_id=="CMP-INV"

def test_human_review_for_discrepancy():
    result=investigate(target_with_pub(),run(),comparison(ReproductionStatus.NOT_REPRODUCED))
    assert result.human_review_required is True and result.discrepancy.human_review_required is True

def test_unknown_cause_is_preserved():
    result=investigate(target_with_pub(),run(),comparison(ReproductionStatus.NOT_REPRODUCED))
    assert result.discrepancy.category.value=="UNKNOWN"
