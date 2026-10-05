"""Stable data contract for paper analysis and bibliographic evidence."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base schema that rejects fields outside the public API contract."""

    model_config = ConfigDict(extra="forbid")


class PaperMetadata(StrictModel):
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    abstract: str | None = None


class Claim(StrictModel):
    id: str
    claim_text: str
    claim_type: str
    metric: str | None = None
    reported_value: float | None = None
    evidence_locations: list[str] = Field(default_factory=list)


class Experiment(StrictModel):
    id: str
    objective: str
    dataset: str | None = None
    split: str | None = None
    model: str | None = None
    metric: str | None = None
    baseline: str | None = None
    reported_result: float | None = None
    evidence_locations: list[str] = Field(default_factory=list)


class Reference(StrictModel):
    id: str
    citation_text: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None


class ResearchAnalysis(StrictModel):
    paper: PaperMetadata
    claims: list[Claim] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)


class ReferenceValidationStatus(str, Enum):
    VALID_CORRECT = "VALID_CORRECT"
    VALID_REDIRECT_CORRECT = "VALID_REDIRECT_CORRECT"
    VALID_DOI_WRONG_REFERENCE = "VALID_DOI_WRONG_REFERENCE"
    INVALID_DOI = "INVALID_DOI"
    BROKEN_URL = "BROKEN_URL"
    ACCESS_RESTRICTED = "ACCESS_RESTRICTED"
    DOI_MISSING = "DOI_MISSING"
    DOI_RECOVERED = "DOI_RECOVERED"
    DOI_RECOVERY_UNCERTAIN = "DOI_RECOVERY_UNCERTAIN"
    SCOPUS_LINKED_NO_DOI = "SCOPUS_LINKED_NO_DOI"
    SCOPUS_UNLINKED = "SCOPUS_UNLINKED"
    METADATA_MISMATCH = "METADATA_MISMATCH"
    RETRACTED_REFERENCE = "RETRACTED_REFERENCE"
    AMBIGUOUS = "AMBIGUOUS"
    UNVERIFIED = "UNVERIFIED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    ERROR = "ERROR"


class ReferenceValidation(StrictModel):
    reference_id: str
    input_doi: str | None = None
    normalized_doi: str | None = None
    doi_resolves: bool | None = None
    status: ReferenceValidationStatus
    matched_title: str | None = None
    matched_authors: list[str] = Field(default_factory=list)
    matched_year: int | None = None
    matched_venue: str | None = None
    metadata_match_score: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str | None = None
    confidence: str | None = None
    needs_human_review: bool = False
    notes: list[str] = Field(default_factory=list)


class CitationStatus(str, Enum):
    ASSOCIATED = "ASSOCIATED"
    NO_ASSOCIATED_CITATION = "NO_ASSOCIATED_CITATION"


class EvidenceClassification(str, Enum):
    FACT = "FACT"
    AUTHOR_CLAIM = "AUTHOR_CLAIM"
    OBSERVATION = "OBSERVATION"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


class EvidenceRelevance(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class EvidenceDirectness(str, Enum):
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"
    UNKNOWN = "UNKNOWN"


class EvidenceQuality(str, Enum):
    ABSTRACT = "ABSTRACT"
    SOURCE_EXCERPT = "SOURCE_EXCERPT"
    METADATA_ONLY = "METADATA_ONLY"
    UNKNOWN = "UNKNOWN"


class ClaimSupportStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNCLEAR = "UNCLEAR"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class EvidenceItem(StrictModel):
    evidence_id: str
    claim_id: str
    reference_id: str | None = None
    evidence_type: str
    source: str | None = None
    source_title: str | None = None
    source_locator: str | None = None
    excerpt: str | None = None
    citation_marker: str | None = None
    citation_context: str | None = None
    citation_location: str | None = None
    relevance: EvidenceRelevance = EvidenceRelevance.UNKNOWN
    directness: EvidenceDirectness = EvidenceDirectness.UNKNOWN
    quality: EvidenceQuality = EvidenceQuality.UNKNOWN
    classification: EvidenceClassification = EvidenceClassification.UNKNOWN


class ClaimAlignmentDecision(StrictModel):
    required_evidence: list[str] = Field(default_factory=list)
    support_status: ClaimSupportStatus
    confidence: EvidenceRelevance
    relevance: EvidenceRelevance
    directness: EvidenceDirectness
    explanation: str
    unresolved_questions: list[str] = Field(default_factory=list)


class ClaimEvidenceAssessment(StrictModel):
    claim_id: str
    citation_status: CitationStatus
    reference_ids: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    support_status: ClaimSupportStatus
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: EvidenceRelevance
    explanation: str
    unresolved_questions: list[str] = Field(default_factory=list)
    requires_human_review: bool = False


class ArtifactType(str, Enum):
    CODE = "CODE"
    DATASET = "DATASET"
    MODEL = "MODEL"
    CHECKPOINT = "CHECKPOINT"
    CONFIG = "CONFIG"
    DEPENDENCY = "DEPENDENCY"
    CONTAINER = "CONTAINER"
    SUPPLEMENTARY = "SUPPLEMENTARY"
    EXECUTION_SCRIPT = "EXECUTION_SCRIPT"


class ArtifactStatus(str, Enum):
    FOUND = "FOUND"
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    INACCESSIBLE = "INACCESSIBLE"
    AMBIGUOUS = "AMBIGUOUS"


class ArtifactConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ArtifactDiscoveryMethod(str, Enum):
    PAPER_URL = "PAPER_URL"
    PAPER_TEXT = "PAPER_TEXT"
    PAPER_LINK = "PAPER_LINK"
    REPOSITORY_MENTION = "REPOSITORY_MENTION"
    DATASET_MENTION = "DATASET_MENTION"
    MODEL_MENTION = "MODEL_MENTION"
    DOI_METADATA = "DOI_METADATA"
    PUBLIC_REPOSITORY_LOOKUP = "PUBLIC_REPOSITORY_LOOKUP"
    SUPPLEMENTARY_LINK = "SUPPLEMENTARY_LINK"


class Artifact(StrictModel):
    artifact_id: str
    experiment_id: str | None = None
    type: ArtifactType
    name: str | None = None
    source: str | None = None
    source_url: str | None = None
    identifier: str | None = None
    repository: str | None = None
    version: str | None = None
    commit: str | None = None
    discovery_method: ArtifactDiscoveryMethod
    evidence_location: str | None = None
    description: str | None = None
    relationship_status: ArtifactStatus
    availability_status: ArtifactStatus
    confidence: ArtifactConfidence
    notes: list[str] = Field(default_factory=list)


class ArtifactFileType(str, Enum):
    PYTHON = "PYTHON"
    NOTEBOOK = "NOTEBOOK"
    JAVASCRIPT = "JAVASCRIPT"
    TYPESCRIPT = "TYPESCRIPT"
    CPP = "CPP"
    JAVA = "JAVA"
    GO = "GO"
    RUST = "RUST"
    CONFIG = "CONFIG"
    DEPENDENCY = "DEPENDENCY"
    SHELL = "SHELL"
    MAKEFILE = "MAKEFILE"
    CONTAINER = "CONTAINER"
    CHECKPOINT = "CHECKPOINT"
    DOCUMENTATION = "DOCUMENTATION"
    OTHER = "OTHER"


class ArtifactFileRole(str, Enum):
    ENTRYPOINT = "ENTRYPOINT"
    TRAINING = "TRAINING"
    EVALUATION = "EVALUATION"
    INFERENCE = "INFERENCE"
    DATA_PREPARATION = "DATA_PREPARATION"
    MODEL_DEFINITION = "MODEL_DEFINITION"
    CHECKPOINT = "CHECKPOINT"
    CONFIGURATION = "CONFIGURATION"
    DEPENDENCY = "DEPENDENCY"
    UTILITY = "UTILITY"
    METRIC = "METRIC"
    PREPROCESSING = "PREPROCESSING"
    POSTPROCESSING = "POSTPROCESSING"
    EXECUTION_SCRIPT = "EXECUTION_SCRIPT"
    DOCUMENTATION = "DOCUMENTATION"
    UNKNOWN = "UNKNOWN"


class FileRelevanceStatus(str, Enum):
    RELEVANT = "RELEVANT"
    POSSIBLY_RELEVANT = "POSSIBLY_RELEVANT"
    UNRELATED = "UNRELATED"
    UNKNOWN = "UNKNOWN"


class ArtifactReadiness(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    LIMITED = "LIMITED"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class ArtifactFile(StrictModel):
    file_id: str
    artifact_id: str
    experiment_id: str
    path: str
    file_type: ArtifactFileType
    role: ArtifactFileRole
    relevance_status: FileRelevanceStatus
    confidence: ArtifactConfidence
    evidence: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ExperimentArtifactMap(StrictModel):
    experiment_id: str
    artifact_id: str
    files: list[str] = Field(default_factory=list)
    missing_roles: list[ArtifactFileRole] = Field(default_factory=list)
    unknown_roles: list[ArtifactFileRole] = Field(default_factory=list)
    readiness: ArtifactReadiness
    inspection_partial: bool = False
    notes: list[str] = Field(default_factory=list)


class ExtractionDiagnostics(StrictModel):
    page_count: int = Field(ge=1)
    character_count: int = Field(ge=1)


class AnalysisContextDiagnostics(StrictModel):
    total_characters: int = Field(ge=1)
    sections_detected: int = Field(ge=0)
    selected_sections: list[str] = Field(default_factory=list)
    selected_characters: int = Field(ge=1)
    chunks_created: int = Field(ge=1)
    gemini_input_characters: int = Field(ge=1)
    fallback_used: bool = False


class EnvironmentStatus(str, Enum):
    RECONSTRUCTED = "RECONSTRUCTED"
    PARTIALLY_RECONSTRUCTED = "PARTIALLY_RECONSTRUCTED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"

class DependencyType(str, Enum):
    PYTHON_PACKAGE = "PYTHON_PACKAGE"
    SYSTEM_PACKAGE = "SYSTEM_PACKAGE"
    FRAMEWORK = "FRAMEWORK"
    DRIVER = "DRIVER"
    TOOL = "TOOL"
    OTHER = "OTHER"

class Certainty(str, Enum):
    EXPLICIT = "EXPLICIT"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"

class EnvironmentDependency(StrictModel):
    name: str
    version_constraint: str | None = None
    dependency_type: DependencyType
    source_path: str | None = None
    evidence: str | None = None
    certainty: Certainty

class EnvironmentVariableRequirement(StrictModel):
    name: str
    required: bool = True
    secret: bool = False
    source_path: str | None = None
    evidence: str | None = None
    notes: str | None = None

class EnvironmentConfiguration(StrictModel):
    path: str
    type: str | None = None
    experiment_id: str | None = None
    purpose: str | None = None
    evidence: str | None = None
    relevance_status: str | None = None

class EnvironmentSpecification(StrictModel):
    environment_id: str
    experiment_id: str | None = None
    artifact_id: str | None = None
    status: EnvironmentStatus
    operating_system: str | None = None
    operating_system_version: str | None = None
    python_version: str | None = None
    python_constraint: str | None = None
    frameworks: list[str] = Field(default_factory=list)
    dependencies: list[EnvironmentDependency] = Field(default_factory=list)
    cuda_version: str | None = None
    cudnn_version: str | None = None
    gpu: str | None = None
    gpu_memory: str | None = None
    cpu: str | None = None
    memory: str | None = None
    storage: str | None = None
    environment_variables: list[EnvironmentVariableRequirement] = Field(default_factory=list)
    configuration_files: list[EnvironmentConfiguration] = Field(default_factory=list)
    container: str | None = None
    documented_commands: list[str] = Field(default_factory=list)
    system_dependencies: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    confidence: str | None = None
    notes: list[str] = Field(default_factory=list)
    conflict_detected: bool = False
    conflicting_evidence: list[str] = Field(default_factory=list)

class AnalyzePaperResponse(StrictModel):
    paper_text: str | None = None
    success: bool = True
    analysis: ResearchAnalysis
    reference_validation: list[ReferenceValidation] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    claim_evidence: list[ClaimEvidenceAssessment] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    artifact_files: list[ArtifactFile] = Field(default_factory=list)
    experiment_artifact_maps: list[ExperimentArtifactMap] = Field(default_factory=list)
    environment_specifications: list[EnvironmentSpecification] = Field(default_factory=list)
    analysis_context: AnalysisContextDiagnostics | None = None
    extraction: ExtractionDiagnostics
