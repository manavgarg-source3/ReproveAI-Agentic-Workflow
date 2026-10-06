export interface PaperMetadata { title: string | null; authors: string[]; year: number | null; abstract: string | null; }
export interface Claim { id: string; claim_text: string; claim_type: string; metric: string | null; reported_value: number | null; evidence_locations: string[]; }
export interface Experiment { id: string; objective: string; dataset: string | null; split: string | null; model: string | null; metric: string | null; baseline: string | null; reported_result: number | null; evidence_locations: string[]; }
export interface Reference { id: string; citation_text: string; title: string | null; authors: string[]; year: number | null; doi: string | null; }
export interface ReferenceValidation {
  reference_id: string;
  input_doi: string | null;
  normalized_doi: string | null;
  doi_resolves: boolean | null;
  status: string;
  matched_title: string | null;
  matched_authors: string[];
  matched_year: number | null;
  matched_venue: string | null;
  metadata_match_score: number | null;
  source: string | null;
  confidence: string | null;
  needs_human_review: boolean;
  notes: string[];
}
export interface EvidenceItem {
  evidence_id: string;
  claim_id: string;
  reference_id: string | null;
  evidence_type: string;
  source: string | null;
  source_title: string | null;
  source_locator: string | null;
  excerpt: string | null;
  citation_marker: string | null;
  citation_context: string | null;
  citation_location: string | null;
  relevance: string;
  directness: string;
  quality: string;
  classification: string;
}
export interface ClaimEvidenceAssessment {
  claim_id: string;
  citation_status: string;
  reference_ids: string[];
  required_evidence: string[];
  support_status: string;
  evidence_ids: string[];
  confidence: string;
  explanation: string;
  unresolved_questions: string[];
  requires_human_review: boolean;
}
export interface Artifact {
  artifact_id: string;
  experiment_id: string | null;
  type: string;
  name: string | null;
  source: string | null;
  source_url: string | null;
  identifier: string | null;
  repository: string | null;
  version: string | null;
  commit: string | null;
  discovery_method: string;
  evidence_location: string | null;
  description: string | null;
  relationship_status: string;
  availability_status: string;
  confidence: string;
  notes: string[];
}
export interface ArtifactFile {
  file_id: string;
  artifact_id: string;
  experiment_id: string;
  path: string;
  file_type: string;
  role: string;
  relevance_status: string;
  confidence: string;
  evidence: string[];
  notes: string[];
}
export interface ExperimentArtifactMap {
  experiment_id: string;
  artifact_id: string;
  files: string[];
  missing_roles: string[];
  unknown_roles: string[];
  readiness: string;
  inspection_partial: boolean;
  notes: string[];
}
export interface AnalysisContextDiagnostics {
  total_characters: number;
  sections_detected: number;
  selected_sections: string[];
  selected_characters: number;
  chunks_created: number;
  gemini_input_characters: number;
  fallback_used: boolean;
}
export interface EnvironmentDependency {
  name: string;
  version_constraint: string | null;
  dependency_type: string;
  source_path: string | null;
  evidence: string | null;
  certainty: string;
}

export interface EnvironmentEvidence {
  category: string;
  value: string;
  source_path: string;
  evidence: string;
  certainty: "EXPLICIT" | "INFERRED" | "UNKNOWN";
}

export interface EnvironmentVariableRequirement {
  name: string;
  required: boolean;
  secret: boolean;
  source_path: string | null;
  evidence: string | null;
  notes: string | null;
}

export interface EnvironmentConfiguration {
  path: string;
  type: string | null;
  experiment_id: string | null;
  purpose: string | null;
  evidence: string | null;
  relevance_status: string | null;
}

export interface EnvironmentSpecification {
  environment_id: string;
  experiment_id: string | null;
  artifact_id: string | null;
  status: "RECONSTRUCTED" | "PARTIALLY_RECONSTRUCTED" | "BLOCKED" | "UNKNOWN";
  operating_system: string | null;
  operating_system_version: string | null;
  python_version: string | null;
  python_constraint: string | null;
  frameworks: string[];
  dependencies: EnvironmentDependency[];
  cuda_version: string | null;
  cudnn_version: string | null;
  gpu: string | null;
  gpu_memory: string | null;
  cpu: string | null;
  memory: string | null;
  storage: string | null;
  environment_variables: EnvironmentVariableRequirement[];
  configuration_files: EnvironmentConfiguration[];
  container: string | null;
  documented_commands: string[];
  system_dependencies: string[];
  evidence: EnvironmentEvidence[];
  confidence: string | null;
  notes: string[];
  missing_information: string[];
  conflict_detected: boolean;
  conflicting_evidence: EnvironmentEvidence[];
}

export type ReproductionPlanStatus = "READY_FOR_EXECUTION" | "PARTIALLY_READY" | "BLOCKED" | "UNKNOWN";
export type RequirementStatus = "AVAILABLE" | "MISSING" | "INACCESSIBLE" | "CONFLICTING" | "UNKNOWN" | "UNSUPPORTED";
export type CommandSafety = "SAFE_TO_PLAN" | "REQUIRES_REVIEW" | "UNSAFE_TO_EXECUTE" | "UNKNOWN";

export interface PlanEvidence {
  source: string;
  source_path: string | null;
  evidence: string;
  certainty: "EXPLICIT" | "INFERRED" | "UNKNOWN";
  confidence: "HIGH" | "MEDIUM" | "LOW";
}

export interface PlanIssue {
  category: string;
  requirement: string;
  status: RequirementStatus;
  detail: string;
  source: string | null;
  evidence: string | null;
  certainty: "EXPLICIT" | "INFERRED" | "UNKNOWN";
}

export interface PlannedCommand {
  command: string;
  source: string;
  source_path: string | null;
  evidence: string;
  certainty: "EXPLICIT" | "INFERRED" | "UNKNOWN";
  safety: CommandSafety;
  safety_reasons: string[];
}

export interface ExecutionStep {
  step_id: string;
  experiment_id: string;
  order: number;
  phase: string;
  role: string;
  entrypoint: boolean;
  script_path: string | null;
  command: PlannedCommand | null;
  arguments: string[];
  working_directory: string | null;
  inputs: Array<{ name: string; type: string; source: string | null; path: string | null; required: boolean; evidence: string | null; certainty: string; status: RequirementStatus }>;
  outputs: Array<{ name: string; type: string; path_pattern: string | null; expected_content: string | null; evidence: string | null; certainty: string; status: RequirementStatus }>;
  environment_id: string | null;
  configuration: string[];
  prerequisites: string[];
  evidence: PlanEvidence[];
  certainty: string;
  confidence: string;
  status: RequirementStatus;
  notes: string[];
}

export interface ReproductionPlan {
  plan_id: string;
  experiment_id: string;
  artifact_id: string | null;
  environment_id: string | null;
  status: ReproductionPlanStatus;
  readiness: {
    overall_status: ReproductionPlanStatus;
    blocking_requirements: PlanIssue[];
    missing_requirements: PlanIssue[];
    unresolved_conflicts: PlanIssue[];
    available_requirements: string[];
    rationale: string;
    evidence: PlanEvidence[];
  };
  entrypoints: ExecutionStep[];
  training_steps: ExecutionStep[];
  evaluation_steps: ExecutionStep[];
  inference_steps: ExecutionStep[];
  data_requirements: Array<{ dataset_name: string; dataset_type: string | null; source: string | null; access_requirement: string | null; split: string | null; preprocessing: string[]; expected_format: string | null; local_path_if_documented: string | null; download_required: boolean | null; evidence: PlanEvidence[]; certainty: string; confidence: string; status: RequirementStatus; notes: string[] }>;
  model_requirements: Array<{ name: string; artifact_id: string | null; type: string; source: string | null; expected_format: string | null; required: boolean; version: string | null; local_path: string | null; loading_method: string | null; evidence: PlanEvidence[]; certainty: string; confidence: string; availability: RequirementStatus; notes: string[] }>;
  checkpoint_requirements: ReproductionPlan["model_requirements"];
  configuration_requirements: Array<{ path: string; experiment_id: string; purpose: string | null; required: boolean; relevant_parameters: string[]; evidence: PlanEvidence[]; certainty: string; confidence: string; status: RequirementStatus }>;
  dependency_requirements: Array<{ name: string; version_constraint: string | null; dependency_type: string; source_path: string | null; evidence: string | null; certainty: string; status: RequirementStatus }>;
  hardware_requirements: Array<{ category: string; value: string; source_path: string | null; evidence: string | null; certainty: string; status: RequirementStatus }>;
  input_requirements: ExecutionStep["inputs"];
  output_requirements: ExecutionStep["outputs"];
  expected_metrics: Array<{ metric_name: string; expected_value: number | null; unit: string | null; split: string | null; source: string; experiment_id: string; evidence: string; certainty: string; confidence: string; result_kind: "EXPECTED_REPORTED_RESULT" }>;
  expected_results: ReproductionPlan["expected_metrics"];
  reported_parameters: Array<{ name: string; value: string; unit: string | null; source: string; experiment_id: string; evidence: string; certainty: string; confidence: string; status: "REPORTED" | "INFERRED" | "UNKNOWN" }>;
  commands: PlannedCommand[];
  prerequisites: string[];
  missing_requirements: PlanIssue[];
  conflicts: PlanIssue[];
  evidence: PlanEvidence[];
  confidence: "HIGH" | "MEDIUM" | "LOW";
  notes: string[];
}

export type ResearchDomain =
  | "AI_ML"
  | "SOCIAL_SCIENCE"
  | "HUMANITIES"
  | "ENGINEERING"
  | "BIOLOGY"
  | "PHYSICS_CHEMISTRY"
  | "OTHER"
  | "UNKNOWN";

export type VerificationMethod =
  | "COMPUTATIONAL_REPRODUCTION"
  | "STATISTICAL_VERIFICATION"
  | "DOCUMENTARY_VERIFICATION"
  | "QUALITATIVE_EVIDENCE_REVIEW"
  | "EXPERIMENTAL_VERIFICATION"
  | "HUMAN_EXPERT_VALIDATION"
  | "MIXED_METHOD"
  | "UNKNOWN";

export type VerificationStatus =
  | "VERIFIABLE"
  | "PARTIALLY_VERIFIABLE"
  | "COMPUTATIONALLY_REPRODUCIBLE"
  | "DOCUMENTARILY_VERIFIABLE"
  | "REQUIRES_HUMAN_VALIDATION"
  | "INSUFFICIENT_EVIDENCE"
  | "INACCESSIBLE"
  | "UNKNOWN";

export type EvidenceType =
  | "CODE"
  | "DATASET"
  | "MODEL"
  | "CHECKPOINT"
  | "CONFIG"
  | "LITERATURE"
  | "STATISTICAL_OUTPUT"
  | "SURVEY_INSTRUMENT"
  | "TRANSCRIPT"
  | "POLICY_DOCUMENT"
  | "LAB_PROTOCOL"
  | "PRE_REGISTRATION"
  | "OTHER";

export interface EvidenceRequirement {
  requirement_id: string;
  claim_id: string | null;
  evidence_type: EvidenceType;
  description: string;
  status: RequirementStatus;
  source: string | null;
  certainty: "EXPLICIT" | "INFERRED" | "UNKNOWN";
  notes: string[];
}

export interface VerificationBoundary {
  automatable_scope: string[];
  requires_restricted_access: string[];
  requires_human_validation: string[];
  unverifiable_scope: string[];
  notes: string[];
}

export interface ResearchCase {
  case_id: string;
  domain: ResearchDomain;
  domain_confidence: "HIGH" | "MEDIUM" | "LOW";
  claims: Claim[];
  evidence_types: EvidenceType[];
  verification_methods: VerificationMethod[];
  verification_status: VerificationStatus;
  verification_boundary: VerificationBoundary;
  evidence_requirements: EvidenceRequirement[];
  domain_evidence: string[];
  reproduction_plan_ids: string[];
  notes: string[];
}

export interface AnalysisResponse {
  success: boolean;
  paper_text: string | null;
  analysis: { paper: PaperMetadata; claims: Claim[]; experiments: Experiment[]; methods: string[]; references: Reference[]; };
  reference_validation: ReferenceValidation[];
  evidence_items: EvidenceItem[];
  claim_evidence: ClaimEvidenceAssessment[];
  artifacts: Artifact[];
  artifact_files: ArtifactFile[];
  experiment_artifact_maps: ExperimentArtifactMap[];
  environment_specifications: EnvironmentSpecification[];
  reproduction_plans: ReproductionPlan[];
  research_case: ResearchCase | null;
  analysis_context: AnalysisContextDiagnostics | null;
  extraction: { page_count: number; character_count: number; };
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ANALYSIS_TIMEOUT_MS = 3 * 60 * 1000;

export async function analyzePaper(file: File, stage: 'citation' | 'all' = 'all'): Promise<AnalysisResponse> {
  const formData = new FormData(); formData.append("file", file);
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/analyze-paper?stage=${stage}`, {
      method: "POST",
      body: formData,
      signal: AbortSignal.timeout(ANALYSIS_TIMEOUT_MS),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new Error("The audit exceeded three minutes. Check the API log for the slow stage.");
    }
    throw new Error(`Could not reach the analysis API at ${API_URL}. Make sure the backend is running.`);
  }
  const body = await response.json().catch(() => null) as AnalysisResponse | { detail?: string } | null;
  if (!response.ok) { const detail = body && "detail" in body ? body.detail : undefined; throw new Error(detail ?? "The paper could not be analyzed."); }
  const result = body as AnalysisResponse;
  return {
    ...result,
    paper_text: result.paper_text ?? null,
    reference_validation: result.reference_validation ?? [],
    evidence_items: result.evidence_items ?? [],
    claim_evidence: result.claim_evidence ?? [],
    artifacts: result.artifacts ?? [],
    artifact_files: result.artifact_files ?? [],
    experiment_artifact_maps: result.experiment_artifact_maps ?? [],
    environment_specifications: result.environment_specifications ?? [],
    reproduction_plans: result.reproduction_plans ?? [],
    research_case: result.research_case ?? null,
    analysis_context: result.analysis_context ?? null,
  };
}

export async function analyzeEnvironment(analysis: object, paperText: string): Promise<AnalysisResponse> {
  let response: Response;
  try { 
    response = await fetch(`${API_URL}/api/v1/analyze-environment`, { 
      method: "POST", 
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ analysis: analysis, paper_text: paperText }) 
    }); 
  }
  catch { throw new Error("Could not reach the analysis API."); }
  const body = await response.json().catch(() => null) as Partial<AnalysisResponse> | { detail?: string } | null;
  if (!response.ok) { const detail = body && "detail" in body ? body.detail : undefined; throw new Error(detail ?? "The environment could not be analyzed."); }
  const result = body as Partial<AnalysisResponse>;
  return {
    ...result,
    success: true,
    paper_text: paperText,
    analysis: analysis as AnalysisResponse['analysis'],
    reference_validation: [],
    evidence_items: [],
    claim_evidence: [],
    artifacts: result.artifacts ?? [],
    artifact_files: result.artifact_files ?? [],
    experiment_artifact_maps: result.experiment_artifact_maps ?? [],
    environment_specifications: result.environment_specifications ?? [],
    reproduction_plans: result.reproduction_plans ?? [],
    research_case: result.research_case ?? null,
    analysis_context: null,
    extraction: { page_count: 0, character_count: 0 }
  };
}
