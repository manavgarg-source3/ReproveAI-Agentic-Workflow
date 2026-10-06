"""Deterministic Step 8 comparison; no extraction, execution, or diagnosis."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.comparison import ComparisonAssessment, ComparisonStatus, Compatibility, ReproductionStatus
from app.schemas.execution import ExecutionRecord, ExecutionStatus
from app.schemas.research import ObservedResult, ObservedResultStatus, ReproductionTarget


def _compat(left: str | None, right: str | None, *, unknown_if_missing: bool = True) -> Compatibility:
    if not left or not right:
        return Compatibility.UNKNOWN if unknown_if_missing else Compatibility.MISMATCH
    return Compatibility.MATCH if left.casefold() == right.casefold() else Compatibility.MISMATCH


def compare_result(target: ReproductionTarget, run: ExecutionRecord, observed: ObservedResult, *, tolerance: float | None = None, tolerance_basis: str | None = None, tolerance_source: str | None = None) -> ComparisonAssessment:
    published = target.published_result
    metric = target.metric or (observed.metric_name if observed else None)
    base = dict(
        comparison_id=f"CMP-{uuid4().hex.upper()}", target_id=target.target_id, experiment_id=target.experiment_id,
        published_result_id=published.source_claim_id if published else None,
        observed_result_id=observed.observed_result_id if observed else None, run_id=run.run_id,
        metric_name=metric, published_value=published.reported_value if published else None,
        observed_value=observed.value if observed else None, published_unit=published.unit if published else None,
        observed_unit=observed.unit if observed else None, tolerance=tolerance,
        tolerance_basis=tolerance_basis, tolerance_source=tolerance_source,
        created_at=datetime.now(timezone.utc),
    )
    if run.status in {ExecutionStatus.BLOCKED, ExecutionStatus.FAILED, ExecutionStatus.TIMED_OUT, ExecutionStatus.INTERRUPTED} or observed.status in {ObservedResultStatus.UNAVAILABLE, ObservedResultStatus.NOT_FOUND, ObservedResultStatus.NOT_AVAILABLE}:
        return ComparisonAssessment(**base, comparison_status=ComparisonStatus.INCONCLUSIVE, reproduction_status=ReproductionStatus.BLOCKED if run.status == ExecutionStatus.BLOCKED else ReproductionStatus.INCONCLUSIVE, limitations=("No usable observed execution result was available.",))
    if not published or observed.status != ObservedResultStatus.EXTRACTED or published.reported_value is None or observed.value is None:
        return ComparisonAssessment(**base, comparison_status=ComparisonStatus.INCONCLUSIVE, reproduction_status=ReproductionStatus.INCONCLUSIVE, limitations=("Published or observed evidence is incomplete.",))
    metric_compat = _compat(published.metric_name, observed.metric_name, unknown_if_missing=False)
    dataset_compat = _compat(target.dataset.dataset_name if target.dataset else None, observed.dataset, unknown_if_missing=True)
    split_compat = _compat(published.source_location if False else (target.dataset.split if target.dataset else None), observed.dataset_split)
    model_compat = _compat(target.model.name if target.model else None, observed.model)
    checkpoint_compat = _compat(target.checkpoint.name if target.checkpoint else None, observed.checkpoint)
    eval_compat = _compat(target.evaluation_protocol, observed.evaluation_protocol)
    incompat = [metric_compat, dataset_compat, split_compat, model_compat, checkpoint_compat, eval_compat]
    if Compatibility.MISMATCH in incompat:
        return ComparisonAssessment(**base, metric_compatibility=metric_compat, dataset_compatibility=dataset_compat, split_compatibility=split_compat, model_compatibility=model_compat, checkpoint_compatibility=checkpoint_compat, evaluation_protocol_compatibility=eval_compat, comparison_status=ComparisonStatus.NOT_COMPARABLE, reproduction_status=ReproductionStatus.INCONCLUSIVE, limitations=("At least one published/observed compatibility dimension mismatched.",))
    if (published.unit or "").strip() != (observed.unit or "").strip() and published.unit and observed.unit:
        if published.unit in {"%", "percent", "percentage"} and observed.unit in {"", "fraction", "ratio"}:
            published_value = published.reported_value / 100
            observed_value = observed.value
            conversion = "published percentage converted to fraction"
        elif observed.unit in {"%", "percent", "percentage"} and published.unit in {"", "fraction", "ratio"}:
            published_value = published.reported_value
            observed_value = observed.value / 100
            conversion = "observed percentage converted to fraction"
        else:
            return ComparisonAssessment(**base, comparison_status=ComparisonStatus.NOT_COMPARABLE, reproduction_status=ReproductionStatus.INCONCLUSIVE, limitations=("Units are incompatible and no deterministic conversion applies.",))
    else:
        published_value, observed_value, conversion = published.reported_value, observed.value, None
    if not math.isfinite(published_value) or not math.isfinite(observed_value):
        return ComparisonAssessment(**base, comparison_status=ComparisonStatus.INCONCLUSIVE, reproduction_status=ReproductionStatus.INCONCLUSIVE, limitations=("Non-finite values cannot be compared.",))
    difference = abs(observed_value - published_value)
    relative = difference / abs(published_value) if published_value != 0 else None
    compatible = ComparisonStatus.COMPARABLE if Compatibility.MISMATCH not in incompat else ComparisonStatus.NOT_COMPARABLE
    
    sufficient_context = Compatibility.UNKNOWN not in incompat
    has_valid_tolerance = tolerance is not None and bool((tolerance_basis and tolerance_basis.strip()) or (tolerance_source and tolerance_source.strip()))
    
    if not sufficient_context:
        reproduction = ReproductionStatus.INCONCLUSIVE
    elif difference == 0 or (has_valid_tolerance and difference <= tolerance):
        reproduction = ReproductionStatus.VERIFIED
    else:
        reproduction = ReproductionStatus.INCONCLUSIVE
        
    limitations = () if has_valid_tolerance or difference == 0 else ("No justified tolerance was supplied; agreement cannot be established from a nonzero difference.",)
    if not has_valid_tolerance and tolerance is not None:
        limitations = limitations + (f"Provided tolerance ({tolerance}) lacked explicit basis or source and was discarded.",)
        
    if compatible == ComparisonStatus.COMPARABLE and sufficient_context and has_valid_tolerance and difference > tolerance:
        reproduction = ReproductionStatus.NOT_REPRODUCED
    return ComparisonAssessment(**base, normalized_published_value=published_value, normalized_observed_value=observed_value, conversion_rule=conversion, metric_compatibility=metric_compat, dataset_compatibility=dataset_compat, split_compatibility=split_compat, model_compatibility=model_compat, checkpoint_compatibility=checkpoint_compat, evaluation_protocol_compatibility=eval_compat, absolute_difference=difference, relative_difference=relative, comparison_status=compatible, reproduction_status=reproduction, evidence=(f"published={published.reported_value}", f"observed={observed.value}"), limitations=limitations + (("Some compatibility metadata was unavailable.",) if Compatibility.UNKNOWN in incompat else ()))
