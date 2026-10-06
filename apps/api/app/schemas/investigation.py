"""Typed Step 9 discrepancy, hypothesis, and diagnostic-plan contracts."""
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

class InvestigationStatus(str, Enum):
    NO_DISCREPANCY = "NO_DISCREPANCY"
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"

class DiscrepancyCategory(str, Enum):
    DATASET = "DATASET"
    PREPROCESSING = "PREPROCESSING"
    DEPENDENCY = "DEPENDENCY"
    CONFIGURATION = "CONFIGURATION"
    RANDOM_SEED = "RANDOM_SEED"
    HARDWARE = "HARDWARE"
    IMPLEMENTATION = "IMPLEMENTATION"
    PAPER_CODE_CONSISTENCY = "PAPER_CODE_CONSISTENCY"
    UNDOCUMENTED_METHODOLOGY = "UNDOCUMENTED_METHODOLOGY"
    REPRODUCTION_ERROR = "REPRODUCTION_ERROR"
    UNKNOWN = "UNKNOWN"

class HypothesisStatus(str, Enum):
    PROPOSED = "PROPOSED"
    TESTING = "TESTING"
    SUPPORTED = "SUPPORTED"
    WEAKLY_SUPPORTED = "WEAKLY_SUPPORTED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"

class DiagnosticPlanStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    BLOCKED = "BLOCKED"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"
    EXECUTED = "EXECUTED"

class DiagnosticCost(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"

class DiagnosticExecutionType(str, Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    HYPOTHESIS_TEST = "HYPOTHESIS_TEST"

class EvidenceKind(str, Enum):
    FACT = "FACT"
    AUTHOR_CLAIM = "AUTHOR_CLAIM"
    OBSERVATION = "OBSERVATION"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"

class EvidenceLink(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: EvidenceKind
    statement: str = Field(max_length=1000)
    source: str = Field(max_length=500)

class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    hypothesis_id: str
    discrepancy_id: str
    statement: str
    category: DiscrepancyCategory
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    prior_evidence: tuple[EvidenceLink, ...] = ()
    supporting_evidence: tuple[EvidenceLink, ...] = ()
    contradicting_evidence: tuple[EvidenceLink, ...] = ()
    confidence: str = "UNKNOWN"
    diagnostic_plan_ids: tuple[str, ...] = ()
    diagnostic_run_ids: tuple[str, ...] = ()
    created_at: datetime
    updated_at: datetime

class DiagnosticPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    diagnostic_plan_id: str
    hypothesis_id: str
    objective: str
    question: str
    test_type: str
    change_type: str
    target_path: str
    original_state: str
    proposed_state: str
    decision_rule: str
    required_inputs: tuple[str, ...] = ()
    required_artifacts: tuple[str, ...] = ()
    required_environment: tuple[str, ...] = ()
    controls: tuple[str, ...] = ()
    variables: tuple[str, ...] = ()
    expected_observations: tuple[str, ...] = ()
    alternative_observation: str
    estimated_cost: DiagnosticCost = DiagnosticCost.UNKNOWN
    execution_type: DiagnosticExecutionType = DiagnosticExecutionType.DIAGNOSTIC
    status: DiagnosticPlanStatus = DiagnosticPlanStatus.DRAFT
    evidence: tuple[EvidenceLink, ...] = ()
    created_at: datetime

class Discrepancy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    discrepancy_id: str
    target_id: str
    experiment_id: str
    run_id: str
    comparison_id: str
    metric_name: str | None = None
    published_value: float | None = None
    observed_value: float | None = None
    difference: float | None = None
    tolerance: float | None = None
    status: InvestigationStatus
    severity: str = "UNKNOWN"
    category: DiscrepancyCategory = DiscrepancyCategory.UNKNOWN
    statement: str
    evidence: tuple[EvidenceLink, ...] = ()
    hypothesis_ids: tuple[str, ...] = ()
    diagnostic_plan_ids: tuple[str, ...] = ()
    human_review_required: bool = False
    created_at: datetime

class DiscrepancyInvestigation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    investigation_id: str
    target_id: str
    comparison_id: str | None = None
    status: InvestigationStatus
    discrepancy: Discrepancy | None = None
    hypotheses: tuple[Hypothesis, ...] = ()
    diagnostic_plans: tuple[DiagnosticPlan, ...] = ()
    human_review_required: bool = False
    limitations: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    created_at: datetime
