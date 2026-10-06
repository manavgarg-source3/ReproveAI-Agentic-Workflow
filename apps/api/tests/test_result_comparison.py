"""Step 8 deterministic comparison and anti-fabrication tests."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.schemas.comparison import ComparisonStatus, ReproductionStatus
from app.schemas.research import Certainty, PublishedResult, ObservedResult, ObservedResultStatus
from app.services.execution.comparison import compare_result
from app.services.execution.extraction import extract_observed_result
from app.schemas.execution import ExecutionPolicy, ExecutionRecord, ExecutionStatus
from tests.test_secure_execution import target


def run(status=ExecutionStatus.COMPLETED):
    now = datetime.now(timezone.utc)
    return ExecutionRecord(run_id="RUN-CMP", target_id="TARGET-FIXTURE", experiment_id="EXP-FIXTURE", timestamp_started=now, timestamp_finished=now, runtime_seconds=0, resource_policy=ExecutionPolicy(), sandbox={"image": "python:3.12-slim"}, status=status)


from app.schemas.research import DataRequirement, ArtifactConfidence, RequirementStatus, ModelRequirement

def target_with_published(value=0.75, metric="accuracy"):
    t = target().model_copy(update={
        "metric": metric, 
        "dataset": DataRequirement(dataset_name="MNIST", split="test", certainty=Certainty.EXPLICIT, confidence=ArtifactConfidence.HIGH, status=RequirementStatus.IDENTIFIED),
        "model": ModelRequirement(name="resnet", type="model", required=True, certainty=Certainty.EXPLICIT, confidence=ArtifactConfidence.HIGH, availability=RequirementStatus.IDENTIFIED),
        "checkpoint": ModelRequirement(name="resnet-18", type="checkpoint", required=True, certainty=Certainty.EXPLICIT, confidence=ArtifactConfidence.HIGH, availability=RequirementStatus.IDENTIFIED),
        "evaluation_protocol": "Standard", 
        "published_result": PublishedResult(metric_name=metric, reported_value=value, evidence="Fixture publication", certainty=Certainty.EXPLICIT)
    })
    return t

def observed(value=0.75, metric="accuracy", unit=None):
    return ObservedResult(observed_result_id="OBS-CMP", run_id="RUN-CMP", target_id="TARGET-FIXTURE", experiment_id="EXP-FIXTURE", metric_name=metric, dataset="MNIST", dataset_split="test", model="resnet", checkpoint="resnet-18", evaluation_protocol="Standard", value=value, unit=unit, status=ObservedResultStatus.EXTRACTED, source_type="STRUCTURED_RESULT", source_location="result.json:$.value", extraction_method="JSON_PATH")


def test_exact_match_is_verified() -> None:
    result = compare_result(target_with_published(), run(), observed())
    assert result.comparison_status == ComparisonStatus.COMPARABLE and result.reproduction_status == ReproductionStatus.VERIFIED and result.absolute_difference == 0

def test_unknown_context_prevents_verified() -> None:
    t = target_with_published().model_copy(update={"evaluation_protocol": None})
    result = compare_result(t, run(), observed())
    assert result.reproduction_status == ReproductionStatus.INCONCLUSIVE


def test_within_explicit_tolerance_is_verified() -> None:
    result = compare_result(target_with_published(), run(), observed(0.756), tolerance=0.01, tolerance_basis="fixture policy", tolerance_source="test fixture")
    assert result.reproduction_status == ReproductionStatus.VERIFIED and result.tolerance == 0.01


def test_outside_explicit_tolerance_is_not_reproduced() -> None:
    result = compare_result(target_with_published(), run(), observed(0.70), tolerance=0.01, tolerance_basis="fixture policy", tolerance_source="test fixture")
    assert result.comparison_status == ComparisonStatus.COMPARABLE and result.reproduction_status == ReproductionStatus.NOT_REPRODUCED


def test_no_tolerance_does_not_invent_failure() -> None:
    result = compare_result(target_with_published(), run(), observed(0.70))
    assert result.reproduction_status == ReproductionStatus.INCONCLUSIVE and result.tolerance is None

def test_tolerance_without_basis_is_ignored() -> None:
    result = compare_result(target_with_published(), run(), observed(0.70), tolerance=0.01, tolerance_basis="", tolerance_source=None)
    assert result.reproduction_status == ReproductionStatus.INCONCLUSIVE
    assert "discarded" in " ".join(result.limitations)



def test_metric_mismatch_is_not_comparable() -> None:
    result = compare_result(target_with_published(metric="f1"), run(), observed(metric="accuracy"), tolerance=0.1)
    assert result.comparison_status == ComparisonStatus.NOT_COMPARABLE


def test_blocked_run_is_blocked_not_not_reproduced() -> None:
    result = compare_result(target_with_published(), run(ExecutionStatus.BLOCKED), ObservedResult(status=ObservedResultStatus.UNAVAILABLE))
    assert result.reproduction_status == ReproductionStatus.BLOCKED


def test_missing_published_result_is_inconclusive() -> None:
    result = compare_result(target().model_copy(update={"metric": "accuracy"}), run(), observed())
    assert result.reproduction_status == ReproductionStatus.INCONCLUSIVE


def test_nonfinite_observed_is_not_verified() -> None:
    bad = observed(float("nan"))
    result = compare_result(target_with_published(), run(), bad)
    assert result.reproduction_status == ReproductionStatus.INCONCLUSIVE


def test_zero_published_value_has_no_relative_difference() -> None:
    result = compare_result(target_with_published(0), run(), observed(0), tolerance=0)
    assert result.absolute_difference == 0 and result.relative_difference is None


def test_comparison_preserves_source_linkage() -> None:
    result = compare_result(target_with_published(), run(), observed())
    assert result.run_id == "RUN-CMP" and result.observed_result_id == "OBS-CMP" and result.published_result_id is None
