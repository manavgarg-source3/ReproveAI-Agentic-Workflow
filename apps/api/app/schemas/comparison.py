"""Typed Step 8 published-versus-observed comparison contracts."""
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class ComparisonStatus(str, Enum):
    COMPARABLE = "COMPARABLE"
    PARTIALLY_COMPARABLE = "PARTIALLY_COMPARABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class ReproductionStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_REPRODUCED = "PARTIALLY_REPRODUCED"
    NOT_REPRODUCED = "NOT_REPRODUCED"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED"


class Compatibility(str, Enum):
    MATCH = "MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"


class ComparisonAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    comparison_id: str
    target_id: str
    experiment_id: str
    published_result_id: str | None = None
    observed_result_id: str | None = None
    run_id: str
    metric_name: str | None = None
    published_value: float | None = None
    observed_value: float | None = None
    published_unit: str | None = None
    observed_unit: str | None = None
    normalized_published_value: float | None = None
    normalized_observed_value: float | None = None
    conversion_rule: str | None = None
    metric_compatibility: Compatibility = Compatibility.UNKNOWN
    dataset_compatibility: Compatibility = Compatibility.UNKNOWN
    split_compatibility: Compatibility = Compatibility.UNKNOWN
    model_compatibility: Compatibility = Compatibility.UNKNOWN
    checkpoint_compatibility: Compatibility = Compatibility.UNKNOWN
    configuration_compatibility: Compatibility = Compatibility.UNKNOWN
    evaluation_protocol_compatibility: Compatibility = Compatibility.UNKNOWN
    run_count_published: int | None = None
    run_count_observed: int | None = None
    uncertainty_published: str | None = None
    uncertainty_observed: str | None = None
    tolerance: float | None = Field(default=None, ge=0)
    tolerance_basis: str | None = None
    tolerance_source: str | None = None
    absolute_difference: float | None = Field(default=None, ge=0)
    relative_difference: float | None = None
    comparison_status: ComparisonStatus
    reproduction_status: ReproductionStatus
    evidence: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    created_at: datetime
