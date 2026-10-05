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
  status: string;
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
  evidence: string[];
  confidence: string | null;
  notes: string[];
  conflict_detected: boolean;
  conflicting_evidence: string[];
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
  analysis_context: AnalysisContextDiagnostics | null;
  extraction: { page_count: number; character_count: number; };
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function analyzePaper(file: File, stage: 'citation' | 'all' = 'all'): Promise<AnalysisResponse> {
  const formData = new FormData(); formData.append("file", file);
  let response: Response;
  try { response = await fetch(`${API_URL}/api/v1/analyze-paper?stage=${stage}`, { method: "POST", body: formData }); }
  catch { throw new Error("Could not reach the analysis API. Make sure the backend is running."); }
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
    analysis_context: null,
    extraction: { page_count: 0, character_count: 0 }
  };
}
