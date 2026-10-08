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
export type RequirementStatus = "IDENTIFIED" | "AVAILABLE" | "PARTIALLY_AVAILABLE" | "MISSING" | "INACCESSIBLE" | "CONFLICTING" | "UNKNOWN" | "UNSUPPORTED";
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

export interface ReproductionTarget {
  target_id: string;
  plan_id: string;
  experiment_id: string;
  paper_title: string | null;
  objective: string;
  eligible: boolean;
  selected: boolean;
  selection_rank: number | null;
  selection_score: {
    total: number;
    maximum: number;
    dimensions: Array<{ name: string; satisfied: boolean; points: number; evidence: string }>;
  };
  dataset: ReproductionPlan["data_requirements"][number] | null;
  dataset_version: string | null;
  model: ReproductionPlan["model_requirements"][number] | null;
  model_version: string | null;
  checkpoint: ReproductionPlan["checkpoint_requirements"][number] | null;
  metric: string | null;
  evaluation_protocol: string | null;
  published_result: {
    metric_name: string;
    reported_value: number;
    unit: string | null;
    source_location: string | null;
    source_claim_id: string | null;
    evidence: string;
    certainty: string;
    result_kind: "PUBLISHED_RESULT";
  } | null;
  observed_result: { status: "NOT_AVAILABLE"; value: null; notes: string[] };
  baseline: string | null;
  random_seed: string | null;
  repeated_runs: string | null;
  code_artifact_id: string | null;
  relevant_files: string[];
  file_mappings: ArtifactFile[];
  configuration_files: string[];
  environment_id: string | null;
  environment_status: string | null;
  environment_specification: EnvironmentSpecification | null;
  dependency_requirements: ReproductionPlan["dependency_requirements"];
  hardware_requirements: ReproductionPlan["hardware_requirements"];
  documented_command: PlannedCommand | null;
  documented_command_phase: string | null;
  required_inputs: string[];
  missing_requirements: PlanIssue[];
  evidence: PlanEvidence[];
  certainty: string;
  readiness_status: ReproductionPlanStatus;
  selection_reason: string;
  notes: string[];
}

export interface ReproductionTargetSelection {
  candidate_targets: ReproductionTarget[];
  selected_target_id: string | null;
  selected_target: ReproductionTarget | null;
  selection_method: string;
  notes: string[];
}

export type ExecutionStatus = "PENDING_APPROVAL" | "APPROVED" | "QUEUED" | "VALIDATING" | "STAGING" | "SANDBOX_CREATING" | "EXECUTING" | "COLLECTING" | "COMPLETED" | "FAILED" | "BLOCKED" | "CANCELLED" | "TIMED_OUT" | "INTERRUPTED";

export interface ExecutionPolicy {
  cpu_limit: number;
  memory_limit_mb: number;
  runtime_limit_seconds: number;
  process_limit: number;
  storage_limit_mb: number;
  output_limit_mb: number;
  log_limit_kb: number;
  network_policy: "NETWORK_DISABLED";
  gpu_policy: "GPU_DISABLED";
  container_image: string;
}

export interface ExecutionApproval {
  approval_id: string;
  target_id: string;
  approver: string;
  status: "APPROVED" | "REJECTED";
  approved_at: string;
  target_hash: string;
  policy_hash: string;
  artifact_hash: string;
}

export interface ExecutionRecord {
  run_id: string;
  target_id: string;
  experiment_id: string;
  artifact_id: string | null;
  artifact_source: string | null;
  artifact_commit: string | null;
  artifact_hash: string | null;
  environment_id: string | null;
  execution_type: "ORIGINAL" | "DIAGNOSTIC" | "MODIFIED" | "HYPOTHESIS_TEST";
  approval_id: string | null;
  approved_by: string | null;
  timestamp_started: string;
  timestamp_finished: string;
  command: string | null;
  executable: string | null;
  arguments: string[];
  working_directory: string;
  inputs: Array<{ artifact_id: string; name: string; sandbox_path: string; sha256: string; size_bytes: number }>;
  outputs: Array<{ name: string; sandbox_path: string; sha256: string; size_bytes: number; output_type: string; provenance: string }>;
  stdout: string;
  stderr: string;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
  exit_code: number | null;
  runtime_seconds: number;
  resource_policy: ExecutionPolicy;
  sandbox: { technology: string; image: string; image_id: string | null; root_filesystem_read_only: boolean; network_disabled: boolean; non_root_user: string; capabilities_dropped: boolean; no_new_privileges: boolean; host_pid_namespace: boolean; host_ipc_namespace: boolean; privileged: boolean; gpu_exposed: boolean };
  status: ExecutionStatus;
  failure_code: string | null;
  failure_reason: string | null;
  timed_out: boolean;
  resource_limit_exceeded: boolean;
  provenance: string[];
  observed_result: {
    status: string;
    metric_name: string | null;
    value: number | null;
    source_location: string | null;
    extraction_method: string | null;
  } | null;
  comparison: {
    comparison_status: string;
    reproduction_status: string;
    absolute_difference: number | null;
    tolerance: number | null;
  } | null;
}

export const DEFAULT_EXECUTION_POLICY: ExecutionPolicy = {
  cpu_limit: 1,
  memory_limit_mb: 512,
  runtime_limit_seconds: 120,
  process_limit: 32,
  storage_limit_mb: 128,
  output_limit_mb: 64,
  log_limit_kb: 256,
  network_policy: "NETWORK_DISABLED",
  gpu_policy: "GPU_DISABLED",
  container_image: "reprove/hnn:1906.01563",
};

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
  reproduction_targets: ReproductionTargetSelection;
  research_case: ResearchCase | null;
  analysis_context: AnalysisContextDiagnostics | null;
  extraction: { page_count: number; character_count: number; };
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// A multi-chunk paper analysis may need several Gemini retries before falling
// back to the secondary model. Keep the browser request alive long enough for
// the API to return the completed audit instead of discarding a valid result.
const ANALYSIS_TIMEOUT_MINUTES = 10;
const ANALYSIS_TIMEOUT_MS = ANALYSIS_TIMEOUT_MINUTES * 60 * 1000;

function apiErrorDetail(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object" || !("detail" in body)) return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "reason" in detail) {
    return String((detail as { reason: unknown }).reason);
  }
  return fallback;
}

export async function approveReproduction(
  targetId: string,
  approver: string,
  policy: ExecutionPolicy = DEFAULT_EXECUTION_POLICY,
): Promise<ExecutionApproval> {
  const response = await fetch(`${API_URL}/api/v1/reproduction/${encodeURIComponent(targetId)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approver, policy }),
  });
  const body = await response.json().catch(() => null) as ExecutionApproval | unknown;
  if (!response.ok) throw new Error(apiErrorDetail(body, "The target could not be approved."));
  return body as ExecutionApproval;
}

export async function executeReproduction(
  targetId: string,
  approvalId: string,
  policy: ExecutionPolicy = DEFAULT_EXECUTION_POLICY,
): Promise<ExecutionRecord> {
  const response = await fetch(`${API_URL}/api/v1/reproduction/${encodeURIComponent(targetId)}/execute?asynchronous=true`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approval_id: approvalId, policy }),
  });
  const body = await response.json().catch(() => null) as ExecutionRecord | unknown;
  if (!response.ok) throw new Error(apiErrorDetail(body, "The sandbox execution request failed."));
  return body as ExecutionRecord;
}

export async function getReproductionRun(targetId: string, runId: string): Promise<ExecutionRecord> {
  const response = await fetch(`${API_URL}/api/v1/reproduction/${encodeURIComponent(targetId)}/runs/${encodeURIComponent(runId)}`);
  const body = await response.json().catch(() => null) as ExecutionRecord | unknown;
  if (!response.ok) throw new Error(apiErrorDetail(body, "The run could not be loaded."));
  return body as ExecutionRecord;
}

export async function cancelReproductionRun(targetId: string, runId: string): Promise<ExecutionRecord> {
  const response = await fetch(`${API_URL}/api/v1/reproduction/${encodeURIComponent(targetId)}/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
  const body = await response.json().catch(() => null) as ExecutionRecord | unknown;
  if (!response.ok) throw new Error(apiErrorDetail(body, "The run could not be cancelled."));
  return body as ExecutionRecord;
}

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
      throw new Error(
        `The audit exceeded ${ANALYSIS_TIMEOUT_MINUTES} minutes. Check the API log for the slow stage.`,
      );
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
    reproduction_targets: result.reproduction_targets ?? {
      candidate_targets: [], selected_target_id: null, selected_target: null,
      selection_method: "Deterministic evidence coverage ranking.", notes: [],
    },
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
    reproduction_targets: result.reproduction_targets ?? {
      candidate_targets: [], selected_target_id: null, selected_target: null,
      selection_method: "Deterministic evidence coverage ranking.", notes: [],
    },
    research_case: result.research_case ?? null,
    analysis_context: null,
    extraction: { page_count: 0, character_count: 0 }
  };
}


export interface DiagnosticApproval {
  approval_id: string;
  diagnostic_plan_id: string;
  investigation_id: string;
  target_id: string;
  baseline_run_id: string;
  context_hash: string;
  artifact_manifest_hash: string;
  environment_hash: string;
  policy_hash: string;
  diagnostic_plan_hash: string;
  approved_by: string;
  approved_at: string;
  status: string;
}

export interface DiagnosticExecution {
  diagnostic_execution_id: string;
  investigation_id: string;
  diagnostic_plan_id: string;
  target_id: string;
  baseline_run_id: string;
  execution_type: string;
  status: string;
  outcome: string | null;
  context_hash: string;
  baseline_manifest_hash: string;
  diagnostic_manifest_hash: string | null;
  modification_hash: string | null;
  sandbox_run_id: string | null;
  observed_result_id: string | null;
  decision_result: string | null;
  decision_reason: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  cancelled_at: string | null;
}

export async function approveDiagnostic(
  targetId: string,
  baselineRunId: string,
  plan: Record<string, unknown>,
): Promise<DiagnosticApproval> {
  const response = await fetch(`${API_URL}/api/v1/diagnostic/${encodeURIComponent(targetId)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ baseline_run_id: baselineRunId, plan }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(apiErrorDetail(body, "The diagnostic could not be approved."));
  return body as DiagnosticApproval;
}

export async function executeDiagnostic(
  targetId: string,
  approvalId: string,
  plan: Record<string, unknown>,
  policy: ExecutionPolicy = DEFAULT_EXECUTION_POLICY,
): Promise<DiagnosticExecution> {
  const response = await fetch(`${API_URL}/api/v1/diagnostic/${encodeURIComponent(targetId)}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approval_id: approvalId, plan, policy }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(apiErrorDetail(body, "The diagnostic execution request failed."));
  return body as DiagnosticExecution;
}

export async function getDiagnosticExecution(targetId: string, executionId: string): Promise<DiagnosticExecution> {
  const response = await fetch(`${API_URL}/api/v1/diagnostic/${encodeURIComponent(targetId)}/runs/${encodeURIComponent(executionId)}`);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(apiErrorDetail(body, "The diagnostic run could not be loaded."));
  return body as DiagnosticExecution;
}

export interface HypothesisTest {
  id: string;
  hypothesis_id: string;
  investigation_id: string;
  diagnostic_plan_id: string;
  diagnostic_execution_id: string;
  baseline_observed_result_id: string;
  diagnostic_observed_result_id: string | null;
  diagnostic_outcome: string;
  decision_rule: string;
  decision_result: string | null;
  evidence_strength: string;
  prior_status: string;
  resulting_status: string;
  decision_reason: string;
  created_at: string;
  completed_at: string | null;
}

export interface Hypothesis {
  hypothesis_id: string;
  discrepancy_id: string;
  statement: string;
  category: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface DiscrepancyInvestigation {
  investigation_id: string;
  target_id: string;
  status: string;
  hypotheses: Hypothesis[];
  created_at: string;
}

export async function evaluateDiagnostic(targetId: string, executionId: string): Promise<HypothesisTest> {
  const response = await fetch(`${API_URL}/api/v1/diagnostic/${encodeURIComponent(targetId)}/runs/${encodeURIComponent(executionId)}/evaluate`, { method: "POST" });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(apiErrorDetail(body, "The diagnostic evaluation failed."));
  return body as HypothesisTest;
}

export async function getHypothesis(targetId: string, hypothesisId: string): Promise<Hypothesis> {
  const response = await fetch(`${API_URL}/api/v1/diagnostic/${encodeURIComponent(targetId)}/hypotheses/${encodeURIComponent(hypothesisId)}`);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(apiErrorDetail(body, "The hypothesis could not be loaded."));
  return body as Hypothesis;
}

export async function getHypothesisTests(targetId: string, hypothesisId: string): Promise<HypothesisTest[]> {
  const response = await fetch(`${API_URL}/api/v1/diagnostic/${encodeURIComponent(targetId)}/hypotheses/${encodeURIComponent(hypothesisId)}/tests`);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(apiErrorDetail(body, "The hypothesis tests could not be loaded."));
  return body as HypothesisTest[];
}

export async function listInvestigations(targetId: string): Promise<DiscrepancyInvestigation[]> {
  const response = await fetch(`${API_URL}/api/v1/diagnostic/${encodeURIComponent(targetId)}/investigations`);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(apiErrorDetail(body, "The investigations could not be loaded."));
  return body as DiscrepancyInvestigation[];
}
