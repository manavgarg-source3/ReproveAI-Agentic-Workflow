"""Versioned, derived Step 12 report contract. Scientific statuses are reused."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.comparison import ReproductionStatus
from app.schemas.research import EvidenceClassification


class ClaimAssurance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    claim_id: str
    claim_text: str
    claim_type: str
    epistemic_status: EvidenceClassification
    evidence_status: str
    reproduction_status: ReproductionStatus
    associated_evidence: list[str] = Field(default_factory=list)
    associated_source: list[str] = Field(default_factory=list)
    associated_experiment: list[str] = Field(default_factory=list)
    supporting_observations: list[str] = Field(default_factory=list)
    contradictory_observations: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)


class AssuranceReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    report_id: str
    research_case_id: str
    report_version: int = Field(ge=1)
    schema_version: str = "1.0"
    methodology_version: str = "assurance-1.0"
    status: ReproductionStatus
    title: str
    generated_at: datetime
    generated_by: str
    created_at: datetime
    graph_snapshot_id: str
    graph_version: str
    graph_hash: str
    report_hash: str
    summary: dict[str, Any]
    claim_summary: list[ClaimAssurance]
    evidence_summary: list[dict[str, Any]]
    source_summary: list[dict[str, Any]]
    experiment_summary: list[dict[str, Any]]
    method_summary: list[str]
    artifact_summary: list[dict[str, Any]]
    environment_summary: list[dict[str, Any]]
    reproduction_summary: list[dict[str, Any]]
    reproduction_plan_summary: list[dict[str, Any]]
    comparison_summary: list[dict[str, Any]]
    discrepancy_summary: list[dict[str, Any]]
    investigation_summary: list[dict[str, Any]]
    hypothesis_summary: list[dict[str, Any]]
    diagnostic_summary: list[dict[str, Any]]
    hypothesis_test_summary: list[dict[str, Any]]
    state_transition_summary: list[dict[str, Any]]
    limitations: list[dict[str, Any]]
    unresolved_questions: list[dict[str, Any]]
    provenance_summary: dict[str, Any]
    source_record_hashes: dict[str, str]
    immutable: Literal[True] = True
