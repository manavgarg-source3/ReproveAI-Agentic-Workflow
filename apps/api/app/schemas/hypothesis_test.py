"""Models for Step 10B Hypothesis Testing and State Transitions."""
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict

class EvidenceStrength(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"

class HypothesisTest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    hypothesis_id: str
    investigation_id: str
    diagnostic_plan_id: str
    diagnostic_execution_id: str
    baseline_observed_result_id: str
    diagnostic_observed_result_id: str | None = None
    diagnostic_outcome: str
    decision_rule: str
    decision_result: str | None = None
    evidence_strength: EvidenceStrength
    prior_status: str
    resulting_status: str
    decision_reason: str
    created_at: datetime
    completed_at: datetime | None = None

class StateTransitionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    entity_type: str  # "HYPOTHESIS" or "INVESTIGATION"
    entity_id: str
    previous_state: str
    new_state: str
    reason: str
    triggering_test_id: str | None = None
    triggering_diagnostic_execution_id: str | None = None
    actor_type: str = "SYSTEM"
    actor_id: str = "STEP_10B_EVALUATOR"
    created_at: datetime
    context_hash: str

