"""Step 10A diagnostic execution models."""
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

class DiagnosticExecutionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    EXTRACTING = "EXTRACTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"

class DiagnosticOutcome(str, Enum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED"

class DiagnosticChangeType(str, Enum):
    CONFIGURATION = "CONFIGURATION"
    ENVIRONMENT = "ENVIRONMENT"
    INPUT = "INPUT"
    CODE_PATCH = "CODE_PATCH"
    COMMAND = "COMMAND"
    SEED = "SEED"
    OTHER = "OTHER"

class DiagnosticDecisionRule(str, Enum):
    METRIC_INCREASES = "METRIC_INCREASES"
    METRIC_DECREASES = "METRIC_DECREASES"
    METRIC_WITHIN_TOLERANCE = "METRIC_WITHIN_TOLERANCE"
    METRIC_OUTSIDE_TOLERANCE = "METRIC_OUTSIDE_TOLERANCE"
    MATCHES_EXPECTED_VALUE = "MATCHES_EXPECTED_VALUE"
    DIFFERS_FROM_EXPECTED_VALUE = "DIFFERS_FROM_EXPECTED_VALUE"

class ControlledModification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    change_id: str
    change_type: str
    target_path: str
    original_state: str
    proposed_state: str
    variable_name: str | None = None
    rationale: str | None = None
    applied: bool = False
    validation_status: str | None = None

class DiagnosticApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    approval_id: str
    diagnostic_plan_id: str
    investigation_id: str
    target_id: str
    baseline_run_id: str
    context_hash: str
    artifact_manifest_hash: str
    environment_hash: str
    policy_hash: str
    diagnostic_plan_hash: str
    approved_by: str
    approved_at: datetime
    status: str

class DiagnosticExecution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    diagnostic_execution_id: str
    investigation_id: str
    diagnostic_plan_id: str
    target_id: str
    baseline_run_id: str
    execution_type: str = "DIAGNOSTIC"
    status: DiagnosticExecutionStatus
    outcome: DiagnosticOutcome | None = None
    context_hash: str
    baseline_manifest_hash: str
    diagnostic_manifest_hash: str | None = None
    modification_hash: str | None = None
    sandbox_run_id: str | None = None
    observed_result_id: str | None = None
    decision_result: str | None = None
    decision_reason: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    cancelled_at: datetime | None = None

