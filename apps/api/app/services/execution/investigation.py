"""Evidence-bound Step 9 investigation planning; diagnostics are never executed."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from app.schemas.comparison import ComparisonAssessment, ReproductionStatus, ComparisonStatus, Compatibility
from app.schemas.execution import ExecutionRecord
from app.schemas.investigation import *
from app.schemas.research import ReproductionTarget

def _now(): return datetime.now(timezone.utc)

def _link(kind: EvidenceKind, statement: str, source: str) -> EvidenceLink:
    return EvidenceLink(kind=kind, statement=statement[:1000], source=source[:500])

def investigate(target: ReproductionTarget, run: ExecutionRecord, comparison: ComparisonAssessment) -> DiscrepancyInvestigation:
    now = _now()
    base_prov = (f"Step 8 comparison {comparison.comparison_id} is authoritative.", f"Run {run.run_id} supplied the observed evidence.")
    if comparison.reproduction_status == ReproductionStatus.VERIFIED:
        return DiscrepancyInvestigation(investigation_id=f"INV-{uuid4().hex.upper()}", target_id=target.target_id, comparison_id=comparison.comparison_id, status=InvestigationStatus.NO_DISCREPANCY, human_review_required=False, limitations=("No discrepancy was established by Step 8.",), provenance=base_prov, created_at=now)
    if comparison.reproduction_status == ReproductionStatus.BLOCKED:
        return DiscrepancyInvestigation(investigation_id=f"INV-{uuid4().hex.upper()}", target_id=target.target_id, comparison_id=comparison.comparison_id, status=InvestigationStatus.BLOCKED, human_review_required=True, limitations=("No discrepancy can be established because execution was blocked.",), provenance=base_prov, created_at=now)
    if comparison.reproduction_status != ReproductionStatus.NOT_REPRODUCED:
        return DiscrepancyInvestigation(investigation_id=f"INV-{uuid4().hex.upper()}", target_id=target.target_id, comparison_id=comparison.comparison_id, status=InvestigationStatus.INCONCLUSIVE, human_review_required=True, limitations=("Available comparison evidence is insufficient to establish a discrepancy.",), provenance=base_prov, created_at=now)
    did = f"DISC-{uuid4().hex.upper()}"
    evidence = (_link(EvidenceKind.OBSERVATION, f"Observed {comparison.observed_value} differs from published {comparison.published_value} by {comparison.absolute_difference}.", f"comparison:{comparison.comparison_id}"),)
    discrepancy = Discrepancy(discrepancy_id=did, target_id=target.target_id, experiment_id=target.experiment_id, run_id=run.run_id, comparison_id=comparison.comparison_id, metric_name=comparison.metric_name, published_value=comparison.published_value, observed_value=comparison.observed_value, difference=comparison.absolute_difference, tolerance=comparison.tolerance, status=InvestigationStatus.DETECTED, category=DiscrepancyCategory.UNKNOWN, statement="The observed result differs from the published result beyond the justified tolerance.", evidence=evidence, human_review_required=True, created_at=now)
    candidates = [
        (DiscrepancyCategory.DATASET, "Dataset identity, version, or split mismatch may explain the difference.", "Evaluate the same model/checkpoint against the documented dataset and split.", "DATASET", "data/split", "unknown", "documented dataset split"),
        (DiscrepancyCategory.PREPROCESSING, "Preprocessing mismatch may explain the difference.", "Evaluate the same data and model with the documented preprocessing configuration.", "PREPROCESSING", "config/preprocessing", "unknown", "documented preprocessing"),
        (DiscrepancyCategory.CONFIGURATION, "Configuration mismatch may explain the difference.", "Re-run with the documented evaluation configuration while holding data and model fixed.", "CONFIGURATION", "config/eval.yaml", "unknown", "documented configuration"),
    ]
    hypotheses=[]; plans=[]
    for category, statement, objective, c_type, t_path, o_state, p_state in candidates:
        hid=f"H-{uuid4().hex.upper()}"; pid=f"DP-{uuid4().hex.upper()}"
        links=(_link(EvidenceKind.HYPOTHESIS, statement, f"comparison:{comparison.comparison_id}"), _link(EvidenceKind.UNKNOWN, "Whether this factor was identical in the original publication is unknown.", "available metadata"))
        plan=DiagnosticPlan(diagnostic_plan_id=pid, hypothesis_id=hid, objective=objective, question=statement, test_type="CONTROLLED_DIAGNOSTIC", change_type=c_type, target_path=t_path, original_state=o_state, proposed_state=p_state, required_inputs=tuple(target.required_inputs), required_artifacts=tuple(target.relevant_files), required_environment=(target.environment_id or "unknown",), controls=("metric", "evaluation target", "secure execution policy"), variables=(category.value,), expected_observations=("The observed metric moves toward the published value.",), alternative_observation="The metric remains materially unchanged.", decision_rule="Support hypothesis if observed metric reaches within explicit tolerance T of published value while controls remain unchanged.", estimated_cost=DiagnosticCost.MEDIUM, execution_type=DiagnosticExecutionType.DIAGNOSTIC, evidence=links, created_at=now, status=DiagnosticPlanStatus.DRAFT)
        hypotheses.append(Hypothesis(hypothesis_id=hid, discrepancy_id=did, statement=f"[LOW EVIDENCE CANDIDATE] {statement}", category=category, prior_evidence=links, diagnostic_plan_ids=(pid,), confidence="LOW", created_at=now, updated_at=now))
        plans.append(plan)
    discrepancy=discrepancy.model_copy(update={"hypothesis_ids": tuple(h.hypothesis_id for h in hypotheses), "diagnostic_plan_ids": tuple(p.diagnostic_plan_id for p in plans)})
    return DiscrepancyInvestigation(investigation_id=f"INV-{uuid4().hex.upper()}", target_id=target.target_id, comparison_id=comparison.comparison_id, status=InvestigationStatus.DETECTED, discrepancy=discrepancy, hypotheses=tuple(hypotheses), diagnostic_plans=tuple(plans), human_review_required=True, limitations=("Hypotheses are low-evidence candidates only; no diagnostic execution was performed.",), provenance=base_prov, created_at=now)
