"use client";

import { ChangeEvent, DragEvent, useRef, useState, useEffect } from "react";
import {
  AnalysisResponse,
  analyzePaper,
  Artifact,
  ArtifactFile,
  Claim,
  ClaimEvidenceAssessment,
  EvidenceItem,
  Experiment,
  ExperimentArtifactMap,
  Reference,
  ReferenceValidation,
  EnvironmentSpecification,
  ReproductionPlan,
  ReproductionTargetSelection,
  ExecutionApproval,
  ExecutionRecord,
  DEFAULT_EXECUTION_POLICY,
  approveReproduction,
  executeReproduction,
  getReproductionRun,
  cancelReproductionRun,
  ResearchCase,
} from "@/lib/api";

function UploadIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-6 w-6" fill="none"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 15.5v2A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5v-2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function FileIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none"><path d="M7 3.5h6.6L18 7.9v12.6H7V3.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /><path d="M13.5 3.8V8H18" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /><path d="M9.5 12h6M9.5 15h4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>;
}

function EmptyList({ label }: { label: string }) {
  return <p className="empty-state">No {label} identified by the Step 1 analyzer.</p>;
}

function Claims({ items }: { items: Claim[] }) {
  if (!items.length) return <EmptyList label="claims" />;
  return <div className="result-list">{items.map((claim) => <article key={claim.id} className="result-item"><p>{claim.claim_text}</p><span>{claim.claim_type}</span></article>)}</div>;
}

function Experiments({ items }: { items: Experiment[] }) {
  if (!items.length) return <EmptyList label="experiments" />;
  return <div className="result-list">{items.map((experiment) => <article key={experiment.id} className="result-item"><p>{experiment.objective}</p><span>{[experiment.dataset, experiment.model].filter(Boolean).join(" · ")}</span></article>)}</div>;
}

function References({ items }: { items: Reference[] }) {
  if (!items.length) return <EmptyList label="references" />;
  return <ol className="result-list list-decimal pl-5">{items.map((reference) => <li key={reference.id} className="result-item pl-1"><p>{reference.citation_text}</p></li>)}</ol>;
}

function validationTone(status: string) {
  if (["VALID_CORRECT", "VALID_REDIRECT_CORRECT", "DOI_RECOVERED"].includes(status)) return "validation-good";
  if (["VALID_DOI_WRONG_REFERENCE", "INVALID_DOI", "BROKEN_URL", "ERROR"].includes(status)) return "validation-bad";
  if (["SOURCE_UNAVAILABLE", "DOI_MISSING", "UNVERIFIED"].includes(status)) return "validation-neutral";
  return "validation-review";
}

function ReferenceValidationResults({
  references,
  items,
}: {
  references: Reference[];
  items: ReferenceValidation[];
}) {
  if (!items.length) return <EmptyList label="bibliographic validation results" />;
  const citations = new Map(references.map((reference) => [reference.id, reference.citation_text]));

  return (
    <div className="grid gap-3">
      {items.map((item) => (
        <article key={item.reference_id} className="validation-item">
          <div className="min-w-0">
            <p className="line-clamp-2 text-sm font-medium leading-6 text-slate-800">
              {citations.get(item.reference_id) ?? item.matched_title ?? item.reference_id}
            </p>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
              <span>DOI: {item.normalized_doi ?? item.input_doi ?? "Not provided"}</span>
              <span>Source: {item.source ?? "—"}</span>
              <span>Match: {item.metadata_match_score === null ? "—" : `${Math.round(item.metadata_match_score * 100)}%`}</span>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:justify-end">
            <span className={`validation-badge ${validationTone(item.status)}`}>{item.status.replaceAll("_", " ")}</span>
            {item.needs_human_review && <span className="review-flag">Review</span>}
          </div>
        </article>
      ))}
    </div>
  );
}

function supportTone(status: string) {
  if (status === "SUPPORTED") return "evidence-supported";
  if (status === "PARTIALLY_SUPPORTED") return "evidence-partial";
  if (["NOT_SUPPORTED", "CONTRADICTED"].includes(status)) return "evidence-negative";
  return "evidence-unclear";
}

function ClaimEvidenceResults({
  claims,
  assessments = [],
  evidence = [],
}: {
  claims: Claim[];
  assessments?: ClaimEvidenceAssessment[];
  evidence?: EvidenceItem[];
}) {
  if (!assessments.length) return <EmptyList label="claim-evidence assessments" />;
  const claimsById = new Map(claims.map((claim) => [claim.id, claim]));
  const evidenceById = new Map(evidence.map((item) => [item.evidence_id, item]));

  return (
    <div className="grid gap-4">
      {assessments.map((assessment) => {
        const claim = claimsById.get(assessment.claim_id);
        const items = assessment.evidence_ids.flatMap((id) => {
          const item = evidenceById.get(id);
          return item ? [item] : [];
        });
        return (
          <article key={assessment.claim_id} className="evidence-card">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <p className="text-[0.68rem] font-bold uppercase tracking-[0.14em] text-slate-500">Author claim</p>
                <p className="mt-2 text-sm font-semibold leading-6 text-slate-900">{claim?.claim_text ?? assessment.claim_id}</p>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <span className={`evidence-badge ${supportTone(assessment.support_status)}`}>{assessment.support_status.replaceAll("_", " ")}</span>
                {assessment.requires_human_review && <span className="review-flag">Review</span>}
              </div>
            </div>

            {items.map((item) => (
              <div key={item.evidence_id} className="evidence-trace">
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                  <span>Citation: {item.citation_marker ?? "Not identified"}</span>
                  <span>Reference: {item.reference_id ?? "Not identified"}</span>
                  <span>Source: {item.source ?? "Unavailable"}</span>
                  <span>Quality: {item.quality.replaceAll("_", " ")}</span>
                </div>
                {item.citation_context && <p className="mt-3 text-sm leading-6 text-slate-700"><span className="font-semibold text-slate-900">Citation context:</span> “{item.citation_context}”</p>}
                <p className="mt-3 text-sm font-semibold text-slate-900">
                  {item.source_locator ? <a href={item.source_locator} target="_blank" rel="noreferrer" className="underline decoration-slate-300 underline-offset-4 hover:decoration-slate-600">{item.source_title ?? "Source record"}</a> : item.source_title ?? "Source text unavailable"}
                </p>
                {item.excerpt && <blockquote className="mt-2 border-l-2 border-indigo-200 pl-3 text-sm leading-6 text-slate-600">{item.excerpt}</blockquote>}
              </div>
            ))}

            {!items.length && <p className="mt-4 text-sm text-slate-600">No citation was confidently associated with this claim.</p>}
            <div className="mt-4 border-t border-slate-200 pt-4">
              <p className="text-sm leading-6 text-slate-700"><span className="font-semibold text-slate-950">Assessment:</span> {assessment.explanation}</p>
              {!!assessment.unresolved_questions.length && <div className="mt-3"><p className="text-xs font-bold uppercase tracking-[0.1em] text-slate-500">Unresolved</p><ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-600">{assessment.unresolved_questions.map((question) => <li key={question}>{question}</li>)}</ul></div>}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function artifactTone(status: string) {
  if (status === "VERIFIED") return "artifact-verified";
  if (status === "FOUND") return "artifact-found";
  if (["INACCESSIBLE", "MISSING"].includes(status)) return "artifact-missing";
  return "artifact-review";
}

function ArtifactDiscoveryResults({ items = [] }: { items?: Artifact[] }) {
  if (!items.length) return <EmptyList label="computational artifacts" />;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {items.map((item) => (
        <article key={item.artifact_id} className="artifact-card">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[0.68rem] font-bold uppercase tracking-[0.14em] text-indigo-700">{item.type.replaceAll("_", " ")}</p>
              <h4 className="mt-2 truncate text-sm font-semibold text-slate-950">{item.name ?? item.identifier ?? "Unnamed artifact"}</h4>
            </div>
            <span className={`artifact-badge ${artifactTone(item.relationship_status)}`}>{item.relationship_status}</span>
          </div>
          <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-xs leading-5">
            <dt className="font-semibold text-slate-500">Availability</dt><dd className="text-slate-700">{item.availability_status}</dd>
            <dt className="font-semibold text-slate-500">Experiment</dt><dd className="text-slate-700">{item.experiment_id ?? "Not confidently associated"}</dd>
            <dt className="font-semibold text-slate-500">Source</dt><dd className="text-slate-700">{item.source ?? "Paper text"}</dd>
            <dt className="font-semibold text-slate-500">Confidence</dt><dd className="text-slate-700">{item.confidence}</dd>
            <dt className="font-semibold text-slate-500">Discovered by</dt><dd className="text-slate-700">{item.discovery_method.replaceAll("_", " ")}</dd>
            <dt className="font-semibold text-slate-500">Evidence</dt><dd className="text-slate-700">{item.evidence_location ?? "Location unavailable"}</dd>
          </dl>
          {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer" className="mt-4 block truncate text-xs font-semibold text-indigo-700 underline decoration-indigo-200 underline-offset-4 hover:decoration-indigo-500">{item.source_url}</a>}
          {item.description && <p className="mt-3 text-xs leading-5 text-slate-600">{item.description}</p>}
          {!!item.notes.length && <ul className="mt-3 list-disc space-y-1 pl-4 text-xs leading-5 text-slate-500">{item.notes.map((note) => <li key={note}>{note}</li>)}</ul>}
        </article>
      ))}
    </div>
  );
}

function ArtifactReadinessResults({ experiments, artifacts, files, maps }: { experiments: Experiment[]; artifacts: Artifact[]; files: ArtifactFile[]; maps: ExperimentArtifactMap[] }) {
  if (!maps.length) return <p className="mt-6 empty-state">No experiment-to-file mappings were available from bounded repository metadata.</p>;
  const experimentsById = new Map(experiments.map((item) => [item.id, item]));
  const artifactsById = new Map(artifacts.map((item) => [item.artifact_id, item]));
  const filesById = new Map(files.map((item) => [item.file_id, item]));
  return <div className="mt-7 border-t border-slate-200 pt-6">
    <div><p className="text-[0.68rem] font-bold uppercase tracking-[0.14em] text-indigo-700">Artifact Readiness</p><p className="mt-1 text-xs leading-5 text-slate-500">Metadata and documentation inspection only. No listed file was downloaded or executed.</p></div>
    <div className="mt-4 grid gap-4">{maps.map((mapping) => {
      const experiment = experimentsById.get(mapping.experiment_id);
      const artifact = artifactsById.get(mapping.artifact_id);
      const mappedFiles = mapping.files.map((id) => filesById.get(id)).filter((item): item is ArtifactFile => Boolean(item));
      return <article key={`${mapping.experiment_id}-${mapping.artifact_id}`} className="readiness-card">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div><p className="text-xs font-semibold text-slate-500">{mapping.experiment_id} · {artifact?.name ?? "Repository artifact"}</p><h4 className="mt-1 text-sm font-semibold text-slate-950">{experiment?.objective ?? "Experiment mapping"}</h4><p className="mt-1 text-xs text-slate-600">{[experiment?.dataset, experiment?.model, experiment?.metric].filter(Boolean).join(" · ") || "Experiment metadata unavailable"}</p></div>
          <span className={`artifact-badge ${mapping.readiness === "COMPLETE" ? "artifact-verified" : mapping.readiness === "MISSING" ? "artifact-missing" : "artifact-review"}`}>{mapping.readiness}</span>
        </div>
        {mappedFiles.length ? <div className="mt-4 grid gap-2">{mappedFiles.map((file) => <div key={file.file_id} className="artifact-file-row"><div className="min-w-0"><p className="truncate font-mono text-xs font-semibold text-slate-800">{file.path}</p><p className="mt-1 text-[0.7rem] text-slate-500">{file.role.replaceAll("_", " ")} · {file.file_type.replaceAll("_", " ")}</p></div><span className="text-[0.65rem] font-bold uppercase tracking-wide text-slate-600">{file.relevance_status.replaceAll("_", " ")}</span></div>)}</div> : <p className="mt-4 text-xs text-slate-500">No bounded file paths were available for this mapping.</p>}
        <div className="mt-4 grid gap-2 text-xs text-slate-600 sm:grid-cols-2"><p><span className="font-semibold text-slate-800">Missing:</span> {mapping.missing_roles.length ? mapping.missing_roles.map((role) => role.replaceAll("_", " ")).join(", ") : "None identified"}</p><p><span className="font-semibold text-slate-800">Uncertain:</span> {mapping.unknown_roles.length ? mapping.unknown_roles.map((role) => role.replaceAll("_", " ")).join(", ") : "None"}</p></div>
        {mapping.inspection_partial && <p className="mt-3 text-xs font-semibold text-amber-700">Inspection reached a configured repository bound.</p>}
      </article>;
    })}</div>
  </div>;
}

function EnvironmentReconstructionResults({ envs, experiments, artifacts }: { envs: EnvironmentSpecification[]; experiments: Experiment[]; artifacts: Artifact[] }) {
  if (!envs?.length) return <p className="empty-state mt-6">No reconstructable repository environment was identified.</p>;
  const experimentsById = new Map(experiments.map(e => [e.id, e]));
  const artifactsById = new Map(artifacts.map(a => [a.artifact_id, a]));
  
  return (
    <div className="mt-7 border-t border-slate-200 pt-6">
      <div>
        <p className="text-[0.68rem] font-bold uppercase tracking-[0.14em] text-indigo-700">Environment Reconstruction</p>
        <p className="mt-1 text-xs leading-5 text-slate-500">Documented environment specification extracted via repository metadata.</p>
      </div>
      <div className="mt-4 grid gap-4">
        {envs.map(env => {
          const exp = env.experiment_id ? experimentsById.get(env.experiment_id) : null;
          const art = env.artifact_id ? artifactsById.get(env.artifact_id) : null;
          
          return (
            <article key={env.environment_id} className="readiness-card">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-xs font-semibold text-slate-500">{env.experiment_id ?? "Global Environment"} - {art?.name ?? "Repository artifact"}</p>
                  <h4 className="mt-1 text-sm font-semibold text-slate-950">{exp?.objective ?? "Artifact Environment Mapping"}</h4>
                </div>
                <span className={`artifact-badge ${env.status === 'RECONSTRUCTED' ? 'artifact-verified' : env.status === 'BLOCKED' || env.status === 'UNKNOWN' ? 'artifact-missing' : 'artifact-review'}`}>{env.status.replaceAll("_", " ")}</span>
              </div>
              <div className="mt-4 grid gap-x-3 gap-y-2 text-xs leading-5 sm:grid-cols-2 text-slate-600">
                <p><span className="font-semibold text-slate-800">OS:</span> {[env.operating_system, env.operating_system_version].filter(Boolean).join(" ") || "UNKNOWN"}</p>
                <p><span className="font-semibold text-slate-800">Python version:</span> {env.python_version ?? "UNKNOWN"}</p>
                <p><span className="font-semibold text-slate-800">Python constraint:</span> {env.python_constraint ?? "UNKNOWN"}</p>
                <p><span className="font-semibold text-slate-800">Frameworks:</span> {env.frameworks.length ? env.frameworks.join(", ") : "None detected"}</p>
                <p><span className="font-semibold text-slate-800">GPU:</span> {env.gpu ?? "UNKNOWN"}</p>
                <p><span className="font-semibold text-slate-800">GPU memory:</span> {env.gpu_memory ?? "UNKNOWN"}</p>
                <p><span className="font-semibold text-slate-800">CUDA:</span> {env.cuda_version ?? "UNKNOWN"}</p>
                <p><span className="font-semibold text-slate-800">cuDNN:</span> {env.cudnn_version ?? "UNKNOWN"}</p>
                <p><span className="font-semibold text-slate-800">Hardware:</span> {[env.cpu, env.memory, env.gpu_memory, env.storage].filter(Boolean).join(" / ") || "UNKNOWN"}</p>
                <p><span className="font-semibold text-slate-800">Container:</span> {env.container ?? "None detected"}</p>
                <p><span className="font-semibold text-slate-800">Env Vars:</span> {env.environment_variables.length ? `${env.environment_variables.length} (${env.environment_variables.filter(v => v.secret).length} secret)` : "None found"}</p>
                <p><span className="font-semibold text-slate-800">Confidence:</span> {env.confidence ?? "UNKNOWN"}</p>
              </div>
              <div className="mt-4 grid gap-3">
                <details className="border-t border-slate-200 pt-3">
                  <summary className="cursor-pointer text-xs font-semibold text-slate-800">Dependencies ({env.dependencies.length})</summary>
                  {env.dependencies.length ? <ul className="mt-2 space-y-2 text-xs text-slate-600">{env.dependencies.map((dependency, index) => <li key={`${dependency.name}-${dependency.source_path}-${index}`}><span className="font-semibold text-slate-800">{dependency.name}</span>{dependency.version_constraint ? ` ${dependency.version_constraint}` : ""}<br />Source: {dependency.source_path ?? "Unknown source"}<br />Evidence: {dependency.evidence ?? "Not available"}<br />Certainty: {dependency.certainty}</li>)}</ul> : <p className="mt-2 text-xs text-slate-500">No package dependencies recovered.</p>}
                </details>
                <details className="border-t border-slate-200 pt-3">
                  <summary className="cursor-pointer text-xs font-semibold text-slate-800">Variables, configuration, and commands</summary>
                  <div className="mt-2 space-y-3 text-xs text-slate-600">
                    <div><p className="font-semibold text-slate-800">Variables</p>{env.environment_variables.length ? <ul className="mt-1 space-y-1">{env.environment_variables.map((variable, index) => <li key={`${variable.name}-${variable.source_path}-${index}`}>{variable.name}{variable.secret ? " (secret)" : ""} - {variable.source_path ?? "Unknown source"}{variable.evidence ? ` - ${variable.evidence}` : ""}</li>)}</ul> : <p>None</p>}</div>
                    <div><p className="font-semibold text-slate-800">Configuration</p>{env.configuration_files.length ? <ul className="mt-1 space-y-1">{env.configuration_files.map((item, index) => <li key={`${item.path}-${index}`}>{item.path}{item.evidence ? ` - ${item.evidence}` : ""}{item.relevance_status ? ` - ${item.relevance_status}` : ""}</li>)}</ul> : <p>None</p>}</div>
                    <p><span className="font-semibold text-slate-800">System packages:</span> {env.system_dependencies.length ? env.system_dependencies.join(", ") : "None"}</p>
                    <p><span className="font-semibold text-slate-800">Commands:</span> {env.documented_commands.length ? env.documented_commands.join("; ") : "None"}</p>
                  </div>
                </details>
                <details className="border-t border-slate-200 pt-3" open={env.conflict_detected}>
                  <summary className="cursor-pointer text-xs font-semibold text-slate-800">Evidence and uncertainty</summary>
                  <div className="mt-2 space-y-3 text-xs text-slate-600">
                    <p><span className="font-semibold text-slate-800">Missing:</span> {env.missing_information.length ? env.missing_information.join(", ") : "None"}</p>
                    {env.conflicting_evidence.length > 0 && <div><p className="font-semibold text-red-700">Unresolved conflicts</p><ul className="mt-1 space-y-2">{env.conflicting_evidence.map((item, index) => <li key={`${item.category}-${item.source_path}-${index}`}><span className="font-semibold">{item.category}: {item.value}</span><br />Source: {item.source_path}<br />Evidence: {item.evidence}<br />Certainty: {item.certainty}</li>)}</ul></div>}
                    {env.evidence.length > 0 && <ul className="space-y-2">{env.evidence.map((item, index) => <li key={`${item.category}-${item.source_path}-${index}`}><span className="font-semibold text-slate-800">{item.category}: {item.value}</span><br />Source: {item.source_path}<br />Evidence: {item.evidence}<br />Certainty: {item.certainty}</li>)}</ul>}
                    {env.notes.length > 0 && <p><span className="font-semibold text-slate-800">Notes:</span> {env.notes.join(" ")}</p>}
                  </div>
                </details>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

const terminalExecutionStatuses: string[] = ["COMPLETED", "FAILED", "BLOCKED", "CANCELLED", "TIMED_OUT", "INTERRUPTED"];

function ReproductionTargetResults({ selection }: { selection: ReproductionTargetSelection }) {
  const target = selection.selected_target;
  const [approver, setApprover] = useState("");
  const [approval, setApproval] = useState<ExecutionApproval | null>(null);
  const [run, setRun] = useState<ExecutionRecord | null>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);
  const [executionBusy, setExecutionBusy] = useState(false);
  const [cancellationBusy, setCancellationBusy] = useState(false);
  useEffect(() => {
    if (!target || !run || terminalExecutionStatuses.includes(run.status)) return;
    const timer = window.setInterval(async () => {
      try { setRun(await getReproductionRun(target.target_id, run.run_id)); } catch { /* preserve last durable state */ }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [run, target]);
  if (!target) return <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-5 text-amber-900">
    <p className="font-semibold">No eligible primary AI/ML target</p>
    <p>{selection.notes.join(" ") || "Candidate evidence was insufficient for deterministic selection."}</p>
    <p className="mt-1">Candidates preserved: {selection.candidate_targets.length}</p>
  </div>;
  const missing = target.missing_requirements;
  return <article className="readiness-card mt-5 border-indigo-200 bg-indigo-50/30">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <p className="text-[0.68rem] font-bold uppercase tracking-[0.14em] text-indigo-700">Selected AI/ML reproduction target</p>
        <h4 className="mt-1 text-base font-semibold text-slate-950">{target.objective}</h4>
        <p className="mt-1 font-mono text-[0.68rem] text-slate-500">{target.target_id}</p>
      </div>
      <span className={`artifact-badge ${target.readiness_status === "READY_FOR_EXECUTION" ? "artifact-verified" : target.readiness_status === "BLOCKED" || target.readiness_status === "UNKNOWN" ? "artifact-missing" : "artifact-review"}`}>{target.readiness_status.replaceAll("_", " ")}</span>
    </div>
    <p className="mt-3 text-xs leading-5 text-slate-600">{target.selection_reason}</p>
    <p className="mt-1 text-xs text-slate-500">Evidence coverage: {target.selection_score.total}/{target.selection_score.maximum} · Rank {target.selection_rank ?? "N/A"} of {selection.candidate_targets.filter(item => item.eligible).length} eligible candidates</p>
    <div className="mt-4 grid gap-2 text-xs leading-5 text-slate-600 sm:grid-cols-2">
      <p><span className="font-semibold text-slate-800">Experiment:</span> {target.experiment_id}</p>
      <p><span className="font-semibold text-slate-800">Dataset:</span> {target.dataset?.dataset_name ?? "UNKNOWN"}{target.dataset?.split ? ` · ${target.dataset.split}` : " · split unknown"}{target.dataset_version ? ` · v${target.dataset_version}` : ""}</p>
      <p><span className="font-semibold text-slate-800">Model:</span> {target.model?.name ?? "UNKNOWN"}{target.model_version ? ` · v${target.model_version}` : ""}</p>
      <p><span className="font-semibold text-slate-800">Checkpoint:</span> {target.checkpoint?.name ?? "UNKNOWN / NOT IDENTIFIED"}</p>
      <p><span className="font-semibold text-slate-800">Metric:</span> {target.metric ?? "UNKNOWN"}</p>
      <p><span className="font-semibold text-slate-800">Evaluation protocol:</span> {target.evaluation_protocol ?? "UNKNOWN"}</p>
      <p><span className="font-semibold text-slate-800">Environment:</span> {target.environment_id ?? "UNKNOWN"} · {target.environment_status ?? "UNKNOWN"}</p>
      <p><span className="font-semibold text-slate-800">Code artifact:</span> {target.code_artifact_id ?? "MISSING"}</p>
    </div>
    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-950">
        <p className="font-semibold">Published Result</p>
        <p className="mt-1 text-base font-semibold">{target.published_result ? `${target.published_result.metric_name}: ${target.published_result.reported_value}${target.published_result.unit ? ` ${target.published_result.unit}` : ""}` : "NOT AVAILABLE"}</p>
        <p className="mt-1">{target.published_result?.source_location ?? "Source location unknown"} · author-reported evidence</p>
      </div>
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
        <p className="font-semibold">Observed Result</p>
        <p className="mt-1 text-base font-semibold">NOT AVAILABLE</p>
        <p className="mt-1">No research code has been executed in Step 5.</p>
      </div>
    </div>
    <div className="mt-4 space-y-3 text-xs leading-5 text-slate-600">
      <p><span className="font-semibold text-slate-800">Relevant files:</span> {target.file_mappings.length ? target.file_mappings.map(item => `${item.path} (${item.role.replaceAll("_", " ")})`).join(", ") : "None mapped"}</p>
      <p><span className="font-semibold text-slate-800">Configuration:</span> {target.configuration_files.length ? target.configuration_files.join(", ") : "None mapped"}</p>
      <p><span className="font-semibold text-slate-800">Dependencies:</span> {target.dependency_requirements.length ? target.dependency_requirements.map(item => `${item.name}${item.version_constraint ? ` ${item.version_constraint}` : ""}`).join(", ") : "None reconstructed"}</p>
      <p><span className="font-semibold text-slate-800">Hardware:</span> {target.hardware_requirements.length ? target.hardware_requirements.map(item => `${item.category}: ${item.value}`).join(", ") : "UNKNOWN"}</p>
      <p><span className="font-semibold text-slate-800">Documented command:</span> {target.documented_command ? <><code className="rounded bg-slate-100 px-1 py-0.5">{target.documented_command.command}</code>{target.documented_command_phase ? ` · ${target.documented_command_phase.replaceAll("_", " ")}` : ""}</> : "None identified"}</p>
      <p><span className="font-semibold text-slate-800">Required inputs:</span> {target.required_inputs.length ? target.required_inputs.join(", ") : "None identified"}</p>
      <div><p className="font-semibold text-slate-800">Missing requirements ({missing.length})</p>{missing.length ? <ul className="mt-1 list-disc pl-5">{missing.map((item, index) => <li key={`${item.category}-${item.requirement}-${index}`}>{item.requirement}: {item.detail}</li>)}</ul> : <p>None identified.</p>}</div>
    </div>
    <div className="mt-5 rounded-xl border-2 border-red-200 bg-red-50 p-4 text-xs leading-5 text-red-950">
      <p className="font-bold uppercase tracking-wide">Warning: untrusted research code</p>
      <p className="mt-1">Approval authorizes one original execution attempt inside the Docker sandbox. Completion means only that the process finished; it does not establish scientific reproduction.</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <p><span className="font-semibold">CPU:</span> {DEFAULT_EXECUTION_POLICY.cpu_limit}</p>
        <p><span className="font-semibold">Memory:</span> {DEFAULT_EXECUTION_POLICY.memory_limit_mb} MB</p>
        <p><span className="font-semibold">Runtime:</span> {DEFAULT_EXECUTION_POLICY.runtime_limit_seconds}s</p>
        <p><span className="font-semibold">Processes:</span> {DEFAULT_EXECUTION_POLICY.process_limit}</p>
        <p><span className="font-semibold">Output:</span> {DEFAULT_EXECUTION_POLICY.output_limit_mb} MB</p>
        <p><span className="font-semibold">Network:</span> disabled</p>
        <p><span className="font-semibold">GPU:</span> disabled</p>
        <p><span className="font-semibold">Root filesystem:</span> read-only</p>
        <p><span className="font-semibold">Image:</span> {DEFAULT_EXECUTION_POLICY.container_image}</p>
      </div>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <input className="min-w-0 flex-1 rounded-lg border border-red-200 bg-white px-3 py-2" value={approver} onChange={event => setApprover(event.target.value)} placeholder="Human approver identity" aria-label="Human approver identity" />
        <button className="rounded-lg bg-amber-700 px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50" disabled={executionBusy || !approver.trim() || target.readiness_status !== "READY_FOR_EXECUTION"} onClick={async () => {
          setExecutionBusy(true); setExecutionError(null);
          try { setApproval(await approveReproduction(target.target_id, approver.trim())); }
          catch (error) { setExecutionError(error instanceof Error ? error.message : "Approval failed."); }
          finally { setExecutionBusy(false); }
        }}>{approval ? "Approved" : "Approve execution"}</button>
        <button className="rounded-lg bg-red-800 px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50" disabled={executionBusy || !approval} onClick={async () => {
          if (!approval) return;
          setExecutionBusy(true); setExecutionError(null);
          try { setRun(await executeReproduction(target.target_id, approval.approval_id)); }
          catch (error) { setExecutionError(error instanceof Error ? error.message : "Execution failed."); }
          finally { setExecutionBusy(false); }
        }}>Execute reproduction</button>
      </div>
      {executionError && <p className="mt-3 font-semibold text-red-800">{executionError}</p>}
      {approval && <p className="mt-3">Approval: <span className="font-mono">{approval.approval_id}</span> · {approval.approver} · artifact {approval.artifact_hash.slice(0, 12)}…</p>}
      {run && <div className="mt-4 rounded-lg border border-slate-300 bg-white p-3 text-slate-700">
        <p className="font-semibold">Run status: {run.status}</p>
        <p>Run: <span className="font-mono">{run.run_id}</span> · Exit: {run.exit_code ?? "N/A"} · {run.runtime_seconds.toFixed(3)}s</p>
        {run.failure_reason && <p className="text-red-700">{run.failure_code}: {run.failure_reason}</p>}
        <p>Artifact hash: {run.artifact_hash ?? "Unavailable"} · Outputs: {run.outputs.length}</p>
        {run.observed_result && <div className="mt-3 rounded border border-indigo-200 bg-indigo-50 p-2 text-xs"><p className="font-semibold">Observed result (execution evidence only)</p><p>Status: {run.observed_result.status}</p><p>{run.observed_result.metric_name ?? "Metric unavailable"}: {run.observed_result.value ?? "Unavailable"}</p><p>Source: {run.observed_result.source_location ?? "None"} · {run.observed_result.extraction_method ?? "No extraction"}</p></div>}
        {run.comparison && <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-2 text-xs"><p className="font-semibold">Comparison assessment</p><p>{run.comparison.comparison_status} · {run.comparison.reproduction_status}</p><p>Difference: {run.comparison.absolute_difference ?? "Unavailable"} · Tolerance: {run.comparison.tolerance ?? "Not established"}</p><p className="mt-1">Investigation hypotheses are evidence-bound and require separate human-reviewed diagnostic planning.</p></div>}
        {!terminalExecutionStatuses.includes(run.status) && <button className="mt-2 rounded bg-slate-800 px-3 py-1 text-xs font-semibold text-white disabled:opacity-50" disabled={cancellationBusy} onClick={async () => { setCancellationBusy(true); setExecutionError(null); try { setRun(await cancelReproductionRun(target.target_id, run.run_id)); } catch (error) { setExecutionError(error instanceof Error ? error.message : "Cancellation failed."); } finally { setCancellationBusy(false); } }}>{cancellationBusy ? "Cancelling..." : "Cancel run"}</button>}
        {run.status === "INTERRUPTED" && <p className="mt-2 font-semibold text-amber-800">Execution was interrupted and was not automatically re-executed.</p>}
        <details className="mt-2"><summary className="cursor-pointer font-semibold">Bounded execution details</summary><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-slate-100 p-2">{run.stdout || "No stdout"}{run.stderr ? `\nSTDERR:\n${run.stderr}` : ""}</pre></details>
      </div>}
    </div>
  </article>;
}

function ReproductionPlanResults({ plans, experiments }: { plans: ReproductionPlan[]; experiments: Experiment[] }) {
  if (!plans.length) return <p className="empty-state mt-5">No experiment evidence was available for reproduction planning.</p>;
  const experimentsById = new Map(experiments.map(item => [item.id, item]));
  return <div className="mt-5 grid gap-4">{plans.map(plan => {
    const experiment = experimentsById.get(plan.experiment_id);
    const issues = [...plan.readiness.blocking_requirements, ...plan.missing_requirements];
    return <article key={plan.plan_id} className="readiness-card">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-[0.68rem] font-bold uppercase tracking-[0.14em] text-amber-700">PLANNED — NOT EXECUTED</p>
          <h4 className="mt-1 text-sm font-semibold text-slate-950">{experiment?.objective ?? plan.experiment_id}</h4>
          <p className="mt-1 font-mono text-[0.68rem] text-slate-500">{plan.plan_id}</p>
        </div>
        <span className={`artifact-badge ${plan.status === "READY_FOR_EXECUTION" ? "artifact-verified" : plan.status === "BLOCKED" || plan.status === "UNKNOWN" ? "artifact-missing" : "artifact-review"}`}>{plan.status.replaceAll("_", " ")}</span>
      </div>
      <div className="mt-4 grid gap-2 text-xs leading-5 text-slate-600 sm:grid-cols-2">
        <p><span className="font-semibold text-slate-800">Experiment:</span> {plan.experiment_id}</p>
        <p><span className="font-semibold text-slate-800">Artifact:</span> {plan.artifact_id ?? "UNKNOWN"}</p>
        <p><span className="font-semibold text-slate-800">Environment:</span> {plan.environment_id ?? "UNKNOWN"}</p>
        <p><span className="font-semibold text-slate-800">Confidence:</span> {plan.confidence}</p>
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-600">{plan.readiness.rationale}</p>
      <div className="mt-4 grid gap-3">
        <details className="border-t border-slate-200 pt-3" open>
          <summary className="cursor-pointer text-xs font-semibold text-slate-800">Entrypoints and planned steps ({plan.entrypoints.length})</summary>
          {plan.entrypoints.length ? <ol className="mt-2 space-y-2 text-xs text-slate-600">{plan.entrypoints.map(step => <li key={step.step_id}><span className="font-semibold text-slate-800">{step.order}. {step.phase.replaceAll("_", " ")}</span> - {step.script_path ?? "No path"}<br />Role: {step.role.replaceAll("_", " ")} - {step.certainty} - {step.confidence}{step.configuration.length ? <><br />Configuration: {step.configuration.join(", ")}</> : null}</li>)}</ol> : <p className="mt-2 text-xs text-slate-500">No mapped execution file was found.</p>}
        </details>
        <details className="border-t border-slate-200 pt-3" open={plan.commands.some(command => command.safety !== "SAFE_TO_PLAN")}>
          <summary className="cursor-pointer text-xs font-semibold text-slate-800">Documented commands ({plan.commands.length})</summary>
          {plan.commands.length ? <ul className="mt-2 space-y-3 text-xs text-slate-600">{plan.commands.map((command, index) => <li key={`${command.command}-${index}`}><code className="block overflow-x-auto bg-slate-100 p-2 text-[0.7rem] text-slate-800">{command.command}</code><span className={`mt-1 inline-block font-bold ${command.safety === "UNSAFE_TO_EXECUTE" ? "text-red-700" : command.safety === "REQUIRES_REVIEW" ? "text-amber-700" : "text-emerald-700"}`}>{command.safety.replaceAll("_", " ")}</span><br />Source: {command.source_path ?? command.source} - {command.certainty}{command.safety_reasons.length ? <><br />Review reasons: {command.safety_reasons.join(", ")}</> : null}</li>)}</ul> : <p className="mt-2 text-xs text-slate-500">No explicit command was recovered.</p>}
        </details>
        <details className="border-t border-slate-200 pt-3">
          <summary className="cursor-pointer text-xs font-semibold text-slate-800">Data, model, checkpoint, and configuration requirements</summary>
          <div className="mt-2 space-y-3 text-xs text-slate-600">
            <p><span className="font-semibold text-slate-800">Datasets:</span> {plan.data_requirements.length ? plan.data_requirements.map(item => `${item.dataset_name}${item.split ? ` (${item.split})` : ""} - ${item.status}`).join(", ") : "None reported"}</p>
            <p><span className="font-semibold text-slate-800">Models:</span> {plan.model_requirements.length ? plan.model_requirements.map(item => `${item.name} - ${item.availability}`).join(", ") : "None reported"}</p>
            <p><span className="font-semibold text-slate-800">Checkpoints:</span> {plan.checkpoint_requirements.length ? plan.checkpoint_requirements.map(item => `${item.name} - ${item.availability}`).join(", ") : "None reported"}</p>
            <p><span className="font-semibold text-slate-800">Configurations:</span> {plan.configuration_requirements.length ? plan.configuration_requirements.map(item => `${item.path} - ${item.status}`).join(", ") : "None mapped"}</p>
            <p><span className="font-semibold text-slate-800">Dependencies:</span> {plan.dependency_requirements.length ? plan.dependency_requirements.map(item => `${item.name}${item.version_constraint ? ` ${item.version_constraint}` : ""}`).join(", ") : "None reconstructed"}</p>
            <p><span className="font-semibold text-slate-800">Hardware:</span> {plan.hardware_requirements.length ? plan.hardware_requirements.map(item => `${item.category}: ${item.value}`).join(", ") : "UNKNOWN"}</p>
          </div>
        </details>
        <details className="border-t border-slate-200 pt-3">
          <summary className="cursor-pointer text-xs font-semibold text-slate-800">Reported parameters and expected results</summary>
          <div className="mt-2 space-y-3 text-xs text-slate-600">
            {plan.reported_parameters.length ? <ul className="space-y-2">{plan.reported_parameters.map((item, index) => <li key={`${item.name}-${item.value}-${index}`}><span className="font-semibold text-slate-800">{item.name}: {item.value}{item.unit ? ` ${item.unit}` : ""}</span><br />{item.status} - {item.certainty} - {item.evidence}</li>)}</ul> : <p>No reported parameters were recovered; no defaults were added.</p>}
            {plan.expected_results.length ? <ul className="space-y-2">{plan.expected_results.map((item, index) => <li key={`${item.metric_name}-${index}`}><span className="font-semibold text-slate-800">{item.metric_name}: {item.expected_value ?? "value not reported"}</span><br />{item.result_kind.replaceAll("_", " ")} - {item.split ?? "split unknown"}<br />Evidence: {item.evidence}</li>)}</ul> : <p>No expected reported result was available.</p>}
          </div>
        </details>
        <details className="border-t border-slate-200 pt-3" open={issues.length > 0 || plan.conflicts.length > 0}>
          <summary className="cursor-pointer text-xs font-semibold text-slate-800">Blockers, missing requirements, and conflicts</summary>
          <div className="mt-2 space-y-3 text-xs text-slate-600">
            {issues.length ? <ul className="space-y-2">{issues.map((item, index) => <li key={`${item.category}-${item.requirement}-${index}`}><span className="font-semibold text-slate-800">{item.status}: {item.requirement}</span><br />{item.detail}{item.source ? <><br />Source: {item.source}</> : null}</li>)}</ul> : <p>No blockers or missing requirements.</p>}
            {plan.conflicts.length ? <ul className="space-y-2 text-red-700">{plan.conflicts.map((item, index) => <li key={`${item.category}-${item.requirement}-${index}`}><span className="font-semibold">CONFLICTING: {item.requirement}</span><br />{item.detail}<br />Evidence: {item.evidence ?? "Unavailable"} - {item.certainty}</li>)}</ul> : null}
          </div>
        </details>
        <details className="border-t border-slate-200 pt-3">
          <summary className="cursor-pointer text-xs font-semibold text-slate-800">Plan evidence ({plan.evidence.length})</summary>
          {plan.evidence.length ? <ul className="mt-2 space-y-2 text-xs text-slate-600">{plan.evidence.map((item, index) => <li key={`${item.source}-${item.source_path}-${index}`}><span className="font-semibold text-slate-800">{item.source}</span> - {item.source_path ?? "No path"}<br />{item.evidence}<br />{item.certainty} - {item.confidence}</li>)}</ul> : <p className="mt-2 text-xs text-slate-500">No additional evidence trace was available.</p>}
        </details>
      </div>
      {plan.notes.length ? <p className="mt-4 text-xs text-slate-500">{plan.notes.join(" ")}</p> : null}
    </article>;
  })}</div>;
}

function verificationStatusTone(status: string) {
  if (["VERIFIABLE", "COMPUTATIONALLY_REPRODUCIBLE", "DOCUMENTARILY_VERIFIABLE"].includes(status)) return "artifact-verified";
  if (["PARTIALLY_VERIFIABLE", "REQUIRES_HUMAN_VALIDATION"].includes(status)) return "artifact-review";
  if (["INACCESSIBLE", "INSUFFICIENT_EVIDENCE"].includes(status)) return "artifact-missing";
  return "validation-neutral";
}

function ResearchVerificationStrategyResults({ researchCase }: { researchCase: ResearchCase | null }) {
  if (!researchCase) return <p className="empty-state mt-5">No domain-agnostic verification case available.</p>;

  return (
    <div className="mt-5 grid gap-4">
      <article className="readiness-card">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-[0.68rem] font-bold uppercase tracking-[0.14em] text-indigo-700">Domain-Agnostic Verification Framework</p>
            <h4 className="mt-1 text-base font-semibold text-slate-950">
              {researchCase.domain.replaceAll("_", " ")} Research Case
            </h4>
            <p className="mt-1 font-mono text-[0.68rem] text-slate-500">{researchCase.case_id}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`artifact-badge ${verificationStatusTone(researchCase.verification_status)}`}>
              {researchCase.verification_status.replaceAll("_", " ")}
            </span>
          </div>
        </div>

        <div className="mt-4 grid gap-2 text-xs leading-5 text-slate-600 sm:grid-cols-3">
          <p><span className="font-semibold text-slate-800">Domain:</span> {researchCase.domain.replaceAll("_", " ")}</p>
          <p><span className="font-semibold text-slate-800">Domain Confidence:</span> {researchCase.domain_confidence}</p>
          <p><span className="font-semibold text-slate-800">Status:</span> {researchCase.verification_status.replaceAll("_", " ")}</p>
        </div>

        <div className="mt-4">
          <p className="text-xs font-semibold text-slate-800">Verification Strategy & Candidate Methods:</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {researchCase.verification_methods.map((method) => (
              <span key={method} className="rounded-md border border-indigo-200 bg-indigo-50/80 px-2.5 py-1 text-xs font-medium text-indigo-800">
                {method.replaceAll("_", " ")}
              </span>
            ))}
          </div>
        </div>

        <div className="mt-4 grid gap-3">
          <details className="border-t border-slate-200 pt-3" open>
            <summary className="cursor-pointer text-xs font-semibold text-slate-800">
              Verification Boundary Partitioning
            </summary>
            <div className="mt-3 grid gap-3 text-xs text-slate-600 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-3">
                <p className="font-semibold text-emerald-800">✓ Automatable Planning Scope</p>
                <ul className="mt-2 list-disc space-y-1 pl-4 text-slate-700">
                  {researchCase.verification_boundary.automatable_scope.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-3">
                <p className="font-semibold text-amber-800">⚠ Requires Restricted Access</p>
                <ul className="mt-2 list-disc space-y-1 pl-4 text-slate-700">
                  {researchCase.verification_boundary.requires_restricted_access.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-3">
                <p className="font-semibold text-indigo-800">👤 Requires Human Expert Validation</p>
                <ul className="mt-2 list-disc space-y-1 pl-4 text-slate-700">
                  {researchCase.verification_boundary.requires_human_validation.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-3">
                <p className="font-semibold text-slate-700">⊘ Non-Executed / Boundary Scope</p>
                <ul className="mt-2 list-disc space-y-1 pl-4 text-slate-600">
                  {researchCase.verification_boundary.unverifiable_scope.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          </details>

          <details className="border-t border-slate-200 pt-3">
            <summary className="cursor-pointer text-xs font-semibold text-slate-800">
              Evidence Requirements Taxonomy ({researchCase.evidence_requirements.length})
            </summary>
            {researchCase.evidence_requirements.length ? (
              <div className="mt-3 grid gap-2">
                {researchCase.evidence_requirements.map((req) => (
                  <div key={req.requirement_id} className="artifact-file-row">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-slate-800">{req.description}</p>
                      <p className="mt-0.5 text-[0.7rem] text-slate-500">
                        Type: {req.evidence_type.replaceAll("_", " ")} · Certainty: {req.certainty}
                        {req.source ? ` · Source: ${req.source}` : ""}
                      </p>
                    </div>
                    <span className={`text-[0.65rem] font-bold uppercase tracking-wide ${req.status === "AVAILABLE" ? "text-emerald-700" : "text-amber-700"}`}>
                      {req.status}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-xs text-slate-500">No additional domain evidence requirements specified.</p>
            )}
          </details>

          <details className="border-t border-slate-200 pt-3">
            <summary className="cursor-pointer text-xs font-semibold text-slate-800">
              Domain Classification Evidence & Trace ({researchCase.domain_evidence.length})
            </summary>
            {researchCase.domain_evidence.length ? (
              <ul className="mt-2 space-y-1 text-xs text-slate-600">
                {researchCase.domain_evidence.map((item, idx) => (
                  <li key={idx} className="font-mono text-[0.7rem] text-slate-700">· {item}</li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-slate-500">No explicit domain evidence trace recorded.</p>
            )}
          </details>
        </div>

        {researchCase.notes.length > 0 && (
          <div className="mt-4 border-t border-slate-200 pt-3">
            <p className="text-[0.7rem] text-slate-500">{researchCase.notes.join(" ")}</p>
          </div>
        )}
      </article>
    </div>
  );
}

function Results({ result }: { result: AnalysisResponse }) {
  const { paper, claims, experiments, methods, references } = result.analysis;
  return (
    <section aria-labelledby="results-heading" className="mt-16 animate-reveal">
      <div className="mb-6 flex flex-col gap-4 border-b border-slate-200 pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div><p className="eyebrow">Structured output</p><h2 id="results-heading" className="mt-2 text-3xl font-semibold tracking-[-0.035em] text-slate-950">Analysis results</h2></div>
        <div className="flex gap-2 text-sm text-slate-600"><span className="stat-pill">{result.extraction.page_count} {result.extraction.page_count === 1 ? "page" : "pages"}</span><span className="stat-pill">{result.extraction.character_count.toLocaleString()} characters</span></div>
      </div>
      {result.analysis_context && <aside className="context-diagnostics" aria-label="Analysis context diagnostics">
        <div><p className="text-[0.68rem] font-bold uppercase tracking-[0.14em] text-indigo-700">Analysis Context</p><p className="mt-1 text-xs leading-5 text-slate-500">Full extraction was preserved; these bounded sections were sent to Gemini.</p></div>
        <div className="grid gap-1 text-xs text-slate-600 sm:text-right">
          <span>{[...new Set(result.analysis_context.selected_sections)].map((section) => section.replaceAll("_", " ")).join(", ")}</span>
          <span>{result.analysis_context.gemini_input_characters.toLocaleString()} input characters · {result.analysis_context.chunks_created} {result.analysis_context.chunks_created === 1 ? "chunk" : "chunks"} · Fallback: {result.analysis_context.fallback_used ? "Yes" : "No"}</span>
        </div>
      </aside>}
      <div className="grid gap-4 lg:grid-cols-2">
        <article className="result-card lg:col-span-2">
          <p className="section-number">01 / Paper</p>
          <h3 className="mt-5 max-w-3xl text-2xl font-semibold tracking-[-0.025em] text-slate-950">{paper.title ?? "Title not detected"}</h3>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-600"><span>{paper.authors.length ? paper.authors.join(", ") : "Authors not detected"}</span><span>{paper.year ?? "Year not detected"}</span></div>
          <p className="mt-5 max-w-4xl text-[15px] leading-7 text-slate-600">{paper.abstract ?? "Abstract not detected by the deterministic analyzer."}</p>
        </article>
        <article className="result-card"><p className="section-number">02 / Claims</p><div className="mt-5"><Claims items={claims} /></div></article>
        <article className="result-card"><p className="section-number">03 / Experiments</p><div className="mt-5"><Experiments items={experiments} /></div></article>
        <article className="result-card"><p className="section-number">04 / Methods</p><div className="mt-5">{methods.length ? <ul className="result-list list-disc pl-5">{methods.map((method) => <li key={method}>{method}</li>)}</ul> : <EmptyList label="methods" />}</div></article>
        <article className="result-card"><p className="section-number">05 / References</p><div className="mt-5"><References items={references} /></div></article>
        <article className="result-card lg:col-span-2">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div><p className="section-number">06 / Bibliographic Validation</p><h3 className="mt-3 text-lg font-semibold text-slate-950">Reference metadata evidence</h3></div>
            <p className="max-w-md text-xs leading-5 text-slate-500 sm:text-right">DOI and metadata validation does not verify the scientific claims made by a cited work.</p>
          </div>
          <div className="mt-5"><ReferenceValidationResults references={references} items={result.reference_validation} /></div>
        </article>
        <article className="result-card lg:col-span-2">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div><p className="section-number">07 / Claim Evidence</p><h3 className="mt-3 text-lg font-semibold text-slate-950">Citation-support assessment</h3></div>
            <p className="max-w-md text-xs leading-5 text-slate-500 sm:text-right">This compares author claims with available cited-source text. Support does not establish that a scientific claim is true.</p>
          </div>
          <div className="mt-5"><ClaimEvidenceResults claims={claims} assessments={result.claim_evidence} evidence={result.evidence_items} /></div>
        </article>
        <article className="result-card lg:col-span-2">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div><p className="section-number">08 / Artifact Discovery</p><h3 className="mt-3 text-lg font-semibold text-slate-950">Public computational artifacts</h3></div>
            <p className="max-w-md text-xs leading-5 text-slate-500 sm:text-right">Discovery confirms neither reproducibility nor successful execution. REPRO has not downloaded or run these artifacts.</p>
          </div>
          <div className="mt-5"><ArtifactDiscoveryResults items={result.artifacts} /></div>
          <ArtifactReadinessResults experiments={experiments} artifacts={result.artifacts} files={result.artifact_files} maps={result.experiment_artifact_maps} />
          <EnvironmentReconstructionResults envs={result.environment_specifications} experiments={experiments} artifacts={result.artifacts} />
        </article>
        <article className="result-card lg:col-span-2">
          <div><p className="section-number">09 / Reproduction Plans</p><h3 className="mt-3 text-lg font-semibold text-slate-950">Future execution specifications</h3><p className="mt-1 text-xs leading-5 text-slate-500">Evidence-backed planning only. No repository code, command, installation, download, or experiment has been executed.</p></div>
          <ReproductionTargetResults key={result.reproduction_targets.selected_target_id ?? "no-target"} selection={result.reproduction_targets} />
          <details className="mt-5 border-t border-slate-200 pt-4">
            <summary className="cursor-pointer text-xs font-semibold text-slate-800">All candidate reproduction plans ({result.reproduction_plans.length})</summary>
            <ReproductionPlanResults plans={result.reproduction_plans} experiments={experiments} />
          </details>
        </article>
        <article className="result-card lg:col-span-2">
          <div>
            <p className="section-number">10 / Research Verification Strategy</p>
            <h3 className="mt-3 text-lg font-semibold text-slate-950">Domain-agnostic verification case</h3>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              REPRO framework strategy and verification boundaries. Categorizes computational, statistical, documentary, and expert human review requirements.
            </p>
          </div>
          <ResearchVerificationStrategyResults researchCase={result.research_case} />
        </article>
      </div>
    </section>
  );
}

const loadingMessages = [
  "Extracting document text...",
  "Step 1: Analyzing sections with Gemini...",
  "Step 2: Extracting scientific claims and experiments...",
  "Step 3: Validating scholarly citations... (Wait for a few minutes)",
  "Step 4: Cross-referencing evidence locations...",
  "Finalizing analysis... please wait"
];

export default function Home() {
    const inputRef = useRef<HTMLInputElement>(null);
    const [file, setFile] = useState<File | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<AnalysisResponse | null>(null);
    
    const [elapsedSeconds, setElapsedSeconds] = useState(0);
    const [loadingIndex, setLoadingIndex] = useState(0);
    useEffect(() => {
      let interval: ReturnType<typeof setInterval> | undefined;
      if (isLoading) {
        let seconds = 0;
        interval = setInterval(() => {
          seconds += 1;
          setElapsedSeconds(seconds);
          if (seconds % 15 === 0) {
            setLoadingIndex(prev => (prev < loadingMessages.length - 1 ? prev + 1 : prev));
          }
        }, 1000);
      }
      return () => {
        if (interval) clearInterval(interval);
      };
    }, [isLoading]);

  function selectFile(nextFile: File | undefined) {
    setError(null); setResult(null);
    if (!nextFile) return;
    if (nextFile.type !== "application/pdf" && !nextFile.name.toLowerCase().endsWith(".pdf")) { setFile(null); setError("Please choose a PDF file."); return; }
    setFile(nextFile);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) { selectFile(event.target.files?.[0]); }
  function handleDrop(event: DragEvent<HTMLDivElement>) { event.preventDefault(); setIsDragging(false); selectFile(event.dataTransfer.files?.[0]); }

  const formatTime = (secs: number) => {
    if (secs < 60) return `${secs}s`;
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}m ${s}s`;
  };

  async function handleAnalyze() {
    if (!file) return;
    setIsLoading(true); setError(null); setResult(null); setLoadingIndex(0); setElapsedSeconds(0);
    try {
      const response = await analyzePaper(file, "all");
      setResult(response);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An unknown error occurred.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="min-h-screen overflow-hidden">
      <div className="paper-grid" aria-hidden="true" />
      <div className="relative mx-auto w-full max-w-6xl px-5 pb-20 pt-6 sm:px-8 lg:px-10">
        <header className="flex items-center justify-between border-b border-slate-300/70 pb-5">
          <div className="flex items-center gap-3"><span className="logo-mark">R</span><span className="text-sm font-semibold tracking-[0.22em] text-slate-950">REPRO</span></div>
          <span className="rounded-full border border-slate-300 bg-white/60 px-3 py-1.5 text-xs font-medium text-slate-600">Research Analyzer</span>
        </header>
        <section className="mx-auto max-w-3xl pb-8 pt-16 text-center sm:pt-24">
          <p className="eyebrow">Research, made inspectable</p>
          <h1 className="mt-5 text-balance text-5xl font-semibold leading-[0.98] tracking-[-0.055em] text-slate-950 sm:text-7xl">Turn a paper into structured evidence.</h1>
          <p className="mx-auto mt-6 max-w-2xl text-balance text-base leading-7 text-slate-600 sm:text-lg">Upload a research paper to extract its text and map it to a strict, reviewable schema—without black-box claims.</p>
        </section>
        <section aria-labelledby="upload-heading" className="mx-auto mt-8 max-w-3xl">
          <h2 id="upload-heading" className="sr-only">Upload a paper</h2>
          <div className={`upload-zone ${isDragging ? "upload-zone-active" : ""}`} onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setIsDragging(false)} onDrop={handleDrop}>
            <input ref={inputRef} type="file" accept="application/pdf,.pdf" onChange={handleFileChange} className="sr-only" />
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-indigo-200 bg-indigo-50 text-indigo-700 shadow-sm"><UploadIcon /></div>
            <p className="mt-5 text-lg font-semibold text-slate-950">Drop your paper here</p><p className="mt-1 text-sm text-slate-500">PDF only · up to 25 MB</p>
            <button type="button" onClick={() => inputRef.current?.click()} className="secondary-button mt-5">Choose PDF</button>
          </div>
          {file && <div className="mt-4 flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600"><FileIcon /></span><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-900">{file.name}</p><p className="text-xs text-slate-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p></div></div>
            <button type="button" onClick={handleAnalyze} disabled={isLoading} className="primary-button">{isLoading ? <><span className="spinner" />{loadingMessages[loadingIndex]} ({formatTime(elapsedSeconds)})</> : "Analyze paper"}</button>
          </div>}
          {error && <div role="alert" className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>}
        </section>
        
        {result && (
          <Results result={result} />
        )}
        <footer className="mt-20 border-t border-slate-200 pt-6 text-center text-xs leading-5 text-slate-500">Results are extracted from the paper by the Research Analyzer. Author-reported claims are not independently verified.</footer>
      </div>
    </main>
  );
}
