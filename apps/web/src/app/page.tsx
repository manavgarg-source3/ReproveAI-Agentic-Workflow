"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { AnalysisResponse, analyzePaper, Artifact, ArtifactFile, Claim, ClaimEvidenceAssessment, EvidenceItem, Experiment, ExperimentArtifactMap, Reference, ReferenceValidation } from "@/lib/api";

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
            <p className="max-w-md text-xs leading-5 text-slate-500 sm:text-right">Discovery confirms neither reproducibility nor successful execution. REPROVE has not downloaded or run these artifacts.</p>
          </div>
          <div className="mt-5"><ArtifactDiscoveryResults items={result.artifacts} /></div>
          <ArtifactReadinessResults experiments={experiments} artifacts={result.artifacts} files={result.artifact_files} maps={result.experiment_artifact_maps} />
        </article>
      </div>
    </section>
  );
}

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);

  function selectFile(nextFile: File | undefined) {
    setError(null); setResult(null);
    if (!nextFile) return;
    if (nextFile.type !== "application/pdf" && !nextFile.name.toLowerCase().endsWith(".pdf")) { setFile(null); setError("Please choose a PDF file."); return; }
    setFile(nextFile);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) { selectFile(event.target.files?.[0]); }
  function handleDrop(event: DragEvent<HTMLDivElement>) { event.preventDefault(); setIsDragging(false); selectFile(event.dataTransfer.files?.[0]); }

  async function handleAnalyze() {
    if (!file || isLoading) return;
    setIsLoading(true); setError(null); setResult(null);
    try { setResult(await analyzePaper(file)); }
    catch (caughtError) { setError(caughtError instanceof Error ? caughtError.message : "Analysis failed. Please try again."); }
    finally { setIsLoading(false); }
  }

  return (
    <main className="min-h-screen overflow-hidden">
      <div className="paper-grid" aria-hidden="true" />
      <div className="relative mx-auto w-full max-w-6xl px-5 pb-20 pt-6 sm:px-8 lg:px-10">
        <header className="flex items-center justify-between border-b border-slate-300/70 pb-5">
          <div className="flex items-center gap-3"><span className="logo-mark">R</span><span className="text-sm font-semibold tracking-[0.22em] text-slate-950">REPROVE</span></div>
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
            <button type="button" onClick={handleAnalyze} disabled={isLoading} className="primary-button">{isLoading ? <><span className="spinner" />Analyzing paper…</> : "Analyze paper"}</button>
          </div>}
          {error && <div role="alert" className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>}
        </section>
        {result && <Results result={result} />}
        <footer className="mt-20 border-t border-slate-200 pt-6 text-center text-xs leading-5 text-slate-500">Results are extracted from the paper by the Research Analyzer. Author-reported claims are not independently verified.</footer>
      </div>
    </main>
  );
}
