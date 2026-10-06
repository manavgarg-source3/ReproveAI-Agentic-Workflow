"""Domain-agnostic verification case modeling, domain classification, and verification boundary derivation."""

from __future__ import annotations

import hashlib
import re

from app.schemas.research import (
    Artifact,
    ArtifactConfidence,
    ArtifactFile,
    ArtifactType,
    Certainty,
    Claim,
    ClaimEvidenceAssessment,
    EvidenceItem,
    EvidenceRequirement,
    EvidenceType,
    ReproductionPlan,
    ReproductionPlanStatus,
    RequirementStatus,
    ResearchAnalysis,
    ResearchCase,
    ResearchDomain,
    VerificationBoundary,
    VerificationMethod,
    VerificationStatus,
)

DOMAIN_KEYWORDS: dict[ResearchDomain, list[str]] = {
    ResearchDomain.AI_ML: [
        "transformer", "neural network", "deep learning", "machine learning",
        "training", "checkpoint", "gpu", "cuda", "pytorch", "tensorflow",
        "dataset", "bleu", "accuracy", "f1", "loss", "hyperparameter",
        "optimizer", "backpropagation", "bert", "gpt", "llm",
        "reinforcement learning", "fine-tuning", "inference", "benchmark",
        "pre-trained", "pretrained", "embeddings", "attention mechanism"
    ],
    ResearchDomain.SOCIAL_SCIENCE: [
        "survey", "respondent", "respondents", "sampling", "population",
        "interview", "interviews", "qualitative", "regression", "causal effect",
        "policy", "employment", "unemployment", "social", "sociology",
        "political science", "demographic", "fieldwork", "questionnaire",
        "ethnography", "microdata", "household", "socioeconomic", "labor market",
        "public policy", "quasi-experiment", "difference-in-differences", "census"
    ],
    ResearchDomain.HUMANITIES: [
        "archival", "archive", "manuscript", "historiography", "hermeneutics",
        "literary", "literature", "philosophy", "philosophical", "historical analysis",
        "cultural study", "textual analysis", "historical context", "epistemology",
        "ethics", "critical theory", "narratology", "rhetoric"
    ],
    ResearchDomain.ENGINEERING: [
        "finite element", "stress analysis", "aerodynamic", "mechanical design",
        "cad model", "electrical circuit", "structural integrity", "actuator",
        "embedded system", "pid controller", "turbine", "load bearing",
        "thermodynamics", "signal processing", "power grid", "fluid dynamics"
    ],
    ResearchDomain.BIOLOGY: [
        "genomic", "sequencing", "gene expression", "protein", "crispr",
        "in vitro", "in vivo", "assay", "enzyme", "cell culture",
        "organism", "phenotype", "tissue sample", "biochemical", "pathogen",
        "molecular biology", "rna-seq", "pcr", "antibiotic", "cellular"
    ],
    ResearchDomain.PHYSICS_CHEMISTRY: [
        "quantum state", "spectroscopy", "crystallography", "synthesis protocol",
        "chemical reaction", "superconductor", "molecular dynamics",
        "particle physics", "diffraction", "catalyst", "stoichiometry",
        "magnetic resonance", "laser", "plasma", "lattice", "hamiltonian"
    ],
}


def _stable_case_id(title: str | None, domain: ResearchDomain, claims_count: int) -> str:
    raw = f"{title or 'untitled'}:{domain.value}:{claims_count}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()
    return f"CASE-{digest}"


def classify_research_domain(
    analysis: ResearchAnalysis,
    paper_text: str,
    artifacts: list[Artifact],
) -> tuple[ResearchDomain, ArtifactConfidence, list[str]]:
    """Deterministically classify paper research domain with evidence trace and confidence."""

    title = (analysis.paper.title or "").casefold()
    abstract = (analysis.paper.abstract or "").casefold()
    methods = " ".join(analysis.methods).casefold()
    experiments_text = " ".join(
        f"{exp.objective} {exp.model or ''} {exp.dataset or ''} {exp.metric or ''}"
        for exp in analysis.experiments
    ).casefold()
    body_sample = paper_text[:15000].casefold()

    has_code_artifact = any(art.type == ArtifactType.CODE for art in artifacts)
    has_model_artifact = any(art.type == ArtifactType.MODEL for art in artifacts)

    scores: dict[ResearchDomain, int] = {domain: 0 for domain in DOMAIN_KEYWORDS}
    domain_evidence: list[str] = []

    for domain, keywords in DOMAIN_KEYWORDS.items():
        domain_matched_terms: list[str] = []
        for kw in keywords:
            count = 0
            if re.search(rf"\b{re.escape(kw)}\b", title):
                scores[domain] += 5
                count += 1
            if re.search(rf"\b{re.escape(kw)}\b", abstract):
                scores[domain] += 3
                count += 1
            if re.search(rf"\b{re.escape(kw)}\b", methods):
                scores[domain] += 2
                count += 1
            if re.search(rf"\b{re.escape(kw)}\b", experiments_text):
                scores[domain] += 2
                count += 1
            if re.search(rf"\b{re.escape(kw)}\b", body_sample):
                scores[domain] += 1
                count += 1
            if count > 0:
                domain_matched_terms.append(kw)

        if domain_matched_terms:
            domain_evidence.append(f"{domain.value}: matched keywords [{', '.join(domain_matched_terms[:6])}]")

    # Computational artifact reinforcement for AI_ML
    if has_code_artifact or has_model_artifact:
        scores[ResearchDomain.AI_ML] += 6
        domain_evidence.append("AI_ML: presence of discovered computational code/model artifacts")

    # Sort domains by score
    sorted_domains = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_domain, top_score = sorted_domains[0]
    runner_up_score = sorted_domains[1][1] if len(sorted_domains) > 1 else 0

    if top_score == 0:
        return ResearchDomain.UNKNOWN, ArtifactConfidence.LOW, ["Insufficient domain keywords or artifacts found."]

    if top_score < 4:
        return (
            top_domain if top_score >= 2 else ResearchDomain.UNKNOWN,
            ArtifactConfidence.LOW,
            domain_evidence or ["Low confidence domain signal."],
        )

    margin = top_score - runner_up_score
    if top_score >= 10 and margin >= 4:
        confidence = ArtifactConfidence.HIGH
    elif top_score >= 6:
        confidence = ArtifactConfidence.MEDIUM
    else:
        confidence = ArtifactConfidence.LOW

    return top_domain, confidence, domain_evidence


def derive_verification_strategy(domain: ResearchDomain) -> list[VerificationMethod]:
    """Map research domain to candidate domain-agnostic verification methods."""

    strategies: dict[ResearchDomain, list[VerificationMethod]] = {
        ResearchDomain.AI_ML: [
            VerificationMethod.COMPUTATIONAL_REPRODUCTION,
        ],
        ResearchDomain.SOCIAL_SCIENCE: [
            VerificationMethod.STATISTICAL_VERIFICATION,
            VerificationMethod.DOCUMENTARY_VERIFICATION,
            VerificationMethod.QUALITATIVE_EVIDENCE_REVIEW,
            VerificationMethod.HUMAN_EXPERT_VALIDATION,
        ],
        ResearchDomain.HUMANITIES: [
            VerificationMethod.DOCUMENTARY_VERIFICATION,
            VerificationMethod.QUALITATIVE_EVIDENCE_REVIEW,
            VerificationMethod.HUMAN_EXPERT_VALIDATION,
        ],
        ResearchDomain.ENGINEERING: [
            VerificationMethod.COMPUTATIONAL_REPRODUCTION,
            VerificationMethod.EXPERIMENTAL_VERIFICATION,
            VerificationMethod.DOCUMENTARY_VERIFICATION,
        ],
        ResearchDomain.BIOLOGY: [
            VerificationMethod.COMPUTATIONAL_REPRODUCTION,
            VerificationMethod.EXPERIMENTAL_VERIFICATION,
            VerificationMethod.DOCUMENTARY_VERIFICATION,
        ],
        ResearchDomain.PHYSICS_CHEMISTRY: [
            VerificationMethod.COMPUTATIONAL_REPRODUCTION,
            VerificationMethod.EXPERIMENTAL_VERIFICATION,
            VerificationMethod.DOCUMENTARY_VERIFICATION,
        ],
        ResearchDomain.OTHER: [
            VerificationMethod.DOCUMENTARY_VERIFICATION,
            VerificationMethod.HUMAN_EXPERT_VALIDATION,
        ],
        ResearchDomain.UNKNOWN: [
            VerificationMethod.UNKNOWN,
        ],
    }
    return strategies.get(domain, [VerificationMethod.UNKNOWN])


def derive_verification_boundary(domain: ResearchDomain) -> VerificationBoundary:
    """Explicitly delineate automatable planning scope vs restricted access vs human expert validation."""

    if domain == ResearchDomain.AI_ML:
        return VerificationBoundary(
            automatable_scope=[
                "Document extraction and scientific claim parsing",
                "Claim-to-citation evidence tracing and bibliographic verification",
                "Public repository and computational artifact discovery",
                "Repository file tree classification and experiment mapping",
                "Environment reconstruction and dependency specification",
                "Documented command extraction and safety classification",
                "Deterministic execution step and reproduction planning",
            ],
            requires_restricted_access=[
                "Private repository archives, restricted compute clusters, or gated checkpoint weights",
            ],
            requires_human_validation=[
                "Assessment of model alignment with paper's overarching theoretical claims",
                "Subjective qualitative inspection of generated model outputs",
                "Ethical and safety appraisal of generative or downstream applications",
            ],
            unverifiable_scope=[
                "Physical compute execution, model training, and inference are NOT performed in REPROVE planning stage",
            ],
            notes=[
                "AI/ML verification is currently structured through computational reproduction planning (Steps 1-5).",
                "No code execution or package installation has occurred.",
            ],
        )

    if domain == ResearchDomain.SOCIAL_SCIENCE:
        return VerificationBoundary(
            automatable_scope=[
                "Empirical claim and hypothesis extraction",
                "Citation and literature traceability verification",
                "Dataset, survey instrument, and policy document identification",
                "Statistical model specification and regression formula extraction",
                "Data accessibility and public archive availability assessment",
            ],
            requires_restricted_access=[
                "Confidential microdata, individual-level survey responses, or private administrative records",
            ],
            requires_human_validation=[
                "Contextual interpretation of interview transcripts and ethnographic observations",
                "Normative and domain-expert validation of causal identification strategies",
                "Evaluation of survey coding frameworks and field research protocols",
            ],
            unverifiable_scope=[
                "Live re-interviewing of respondents or field re-surveying without human domain researchers",
            ],
            notes=[
                "Social Science verification uses statistical, documentary, and qualitative review planning.",
                "Demonstration abstraction only; no statistical analysis or interview evaluation executed.",
            ],
        )

    if domain == ResearchDomain.HUMANITIES:
        return VerificationBoundary(
            automatable_scope=[
                "Scholarly claim and citation extraction",
                "Bibliographic and reference consistency verification",
                "Archival source and literature link identification",
            ],
            requires_restricted_access=[
                "Physical manuscript archives, rare book collections, or paywalled historical repositories",
            ],
            requires_human_validation=[
                "Hermeneutic, historical, and philosophical interpretation of primary and secondary texts",
                "Critical contextualization within historical and cultural frameworks",
            ],
            unverifiable_scope=[
                "Subjective interpretive synthesis cannot be replaced by automated verification",
            ],
            notes=[
                "Humanities verification is documentary and qualitative, centered on expert validation.",
            ],
        )

    return VerificationBoundary(
        automatable_scope=[
            "Claim extraction and bibliographic reference validation",
            "Artifact and document metadata identification",
        ],
        requires_restricted_access=[
            "Proprietary datasets, physical lab records, or specialized access repositories",
        ],
        requires_human_validation=[
            "Domain-expert peer validation of methodology and experimental conclusions",
        ],
        unverifiable_scope=[
            "Physical laboratory experimentation and automated empirical replication",
        ],
        notes=[
            "Domain-agnostic verification boundary planning only.",
        ],
    )


def extract_evidence_requirements(
    analysis: ResearchAnalysis,
    artifacts: list[Artifact],
    domain: ResearchDomain,
) -> tuple[list[EvidenceType], list[EvidenceRequirement]]:
    """Build domain-neutral evidence taxonomy requirements from analysis and artifacts."""

    types_set: set[EvidenceType] = set()
    requirements: list[EvidenceRequirement] = []

    # Claims evidence
    if analysis.claims:
        types_set.add(EvidenceType.LITERATURE)
        for i, claim in enumerate(analysis.claims):
            if claim.metric:
                types_set.add(EvidenceType.STATISTICAL_OUTPUT)
                requirements.append(EvidenceRequirement(
                    requirement_id=f"EV-REQ-CLAIM-{claim.id}",
                    claim_id=claim.id,
                    evidence_type=EvidenceType.STATISTICAL_OUTPUT,
                    description=f"Empirical metric measurement for claim: {claim.metric} = {claim.reported_value or 'reported'}",
                    status=RequirementStatus.AVAILABLE if claim.reported_value is not None else RequirementStatus.MISSING,
                    source="paper_text",
                    certainty=Certainty.EXPLICIT,
                ))

    # Artifacts evidence
    for art in artifacts:
        if art.type == ArtifactType.CODE:
            types_set.add(EvidenceType.CODE)
            requirements.append(EvidenceRequirement(
                requirement_id=f"EV-REQ-ART-{art.artifact_id}",
                evidence_type=EvidenceType.CODE,
                description=f"Source code artifact: {art.name or art.artifact_id}",
                status=RequirementStatus.AVAILABLE if art.availability_status.value == "FOUND" else RequirementStatus.INACCESSIBLE,
                source=art.source_url or art.repository,
                certainty=Certainty.EXPLICIT,
            ))
        elif art.type == ArtifactType.DATASET:
            types_set.add(EvidenceType.DATASET)
            requirements.append(EvidenceRequirement(
                requirement_id=f"EV-REQ-ART-{art.artifact_id}",
                evidence_type=EvidenceType.DATASET,
                description=f"Dataset artifact: {art.name or art.artifact_id}",
                status=RequirementStatus.AVAILABLE if art.availability_status.value == "FOUND" else RequirementStatus.MISSING,
                source=art.source_url,
                certainty=Certainty.EXPLICIT,
            ))
        elif art.type == ArtifactType.MODEL:
            types_set.add(EvidenceType.MODEL)
            requirements.append(EvidenceRequirement(
                requirement_id=f"EV-REQ-ART-{art.artifact_id}",
                evidence_type=EvidenceType.MODEL,
                description=f"Model specification: {art.name or art.artifact_id}",
                status=RequirementStatus.AVAILABLE if art.availability_status.value == "FOUND" else RequirementStatus.MISSING,
                source=art.source_url,
                certainty=Certainty.EXPLICIT,
            ))
        elif art.type == ArtifactType.CHECKPOINT:
            types_set.add(EvidenceType.CHECKPOINT)
            requirements.append(EvidenceRequirement(
                requirement_id=f"EV-REQ-ART-{art.artifact_id}",
                evidence_type=EvidenceType.CHECKPOINT,
                description=f"Pretrained checkpoint: {art.name or art.artifact_id}",
                status=RequirementStatus.AVAILABLE if art.availability_status.value == "FOUND" else RequirementStatus.MISSING,
                source=art.source_url,
                certainty=Certainty.EXPLICIT,
            ))

    # Domain specific evidence types
    if domain == ResearchDomain.SOCIAL_SCIENCE:
        types_set.add(EvidenceType.POLICY_DOCUMENT)
        types_set.add(EvidenceType.SURVEY_INSTRUMENT)
        types_set.add(EvidenceType.DATASET)
        if not any(req.evidence_type == EvidenceType.SURVEY_INSTRUMENT for req in requirements):
            requirements.append(EvidenceRequirement(
                requirement_id="EV-REQ-SOC-INSTRUMENT",
                evidence_type=EvidenceType.SURVEY_INSTRUMENT,
                description="Survey instrument / questionnaire protocol definition",
                status=RequirementStatus.UNKNOWN,
                source="methodology",
                certainty=Certainty.INFERRED,
                notes=["Inferred requirement for social science empirical verification"],
            ))

    # Literature / bibliographic
    if analysis.references:
        types_set.add(EvidenceType.LITERATURE)

    return sorted(types_set, key=lambda x: x.value), requirements


def derive_verification_status(
    domain: ResearchDomain,
    reproduction_plans: list[ReproductionPlan],
    requirements: list[EvidenceRequirement],
) -> VerificationStatus:
    """Determine top-level verification status across domains."""

    if domain == ResearchDomain.AI_ML:
        if not reproduction_plans:
            return VerificationStatus.INSUFFICIENT_EVIDENCE
        if any(p.status == ReproductionPlanStatus.READY_FOR_EXECUTION for p in reproduction_plans):
            return VerificationStatus.COMPUTATIONALLY_REPRODUCIBLE
        if any(p.status == ReproductionPlanStatus.PARTIALLY_READY for p in reproduction_plans):
            return VerificationStatus.PARTIALLY_VERIFIABLE
        if all(p.status == ReproductionPlanStatus.BLOCKED for p in reproduction_plans):
            return VerificationStatus.INACCESSIBLE
        return VerificationStatus.INSUFFICIENT_EVIDENCE

    if domain == ResearchDomain.SOCIAL_SCIENCE:
        has_dataset = any(r.evidence_type == EvidenceType.DATASET and r.status == RequirementStatus.AVAILABLE for r in requirements)
        if has_dataset:
            return VerificationStatus.PARTIALLY_VERIFIABLE
        return VerificationStatus.REQUIRES_HUMAN_VALIDATION

    if domain == ResearchDomain.HUMANITIES:
        return VerificationStatus.DOCUMENTARILY_VERIFIABLE

    if domain in {ResearchDomain.ENGINEERING, ResearchDomain.BIOLOGY, ResearchDomain.PHYSICS_CHEMISTRY}:
        return VerificationStatus.PARTIALLY_VERIFIABLE

    return VerificationStatus.UNKNOWN


def build_research_case(
    analysis: ResearchAnalysis,
    evidence_items: list[EvidenceItem],
    claim_evidence: list[ClaimEvidenceAssessment],
    artifacts: list[Artifact],
    files: list[ArtifactFile],
    reproduction_plans: list[ReproductionPlan],
    paper_text: str,
) -> ResearchCase:
    """Build a deterministic, domain-agnostic ResearchCase linking claims, evidence, strategy, and boundaries."""

    domain, confidence, domain_evidence = classify_research_domain(
        analysis, paper_text, artifacts
    )
    verification_methods = derive_verification_strategy(domain)
    verification_boundary = derive_verification_boundary(domain)
    evidence_types, evidence_requirements = extract_evidence_requirements(
        analysis, artifacts, domain
    )
    verification_status = derive_verification_status(
        domain, reproduction_plans, evidence_requirements
    )

    reproduction_plan_ids = [p.plan_id for p in reproduction_plans]
    case_id = _stable_case_id(analysis.paper.title, domain, len(analysis.claims))

    notes = [
        "Domain-agnostic verification case specification. REPROVE is a multi-domain verification framework.",
        f"Primary classification domain: {domain.value} (Confidence: {confidence.value}).",
    ]
    if domain == ResearchDomain.AI_ML and reproduction_plan_ids:
        notes.append(f"Linked to {len(reproduction_plan_ids)} computational reproduction plan(s).")
    elif domain == ResearchDomain.SOCIAL_SCIENCE:
        notes.append("Social science case structured for statistical, documentary, and expert qualitative validation.")

    return ResearchCase(
        case_id=case_id,
        domain=domain,
        domain_confidence=confidence,
        claims=analysis.claims,
        evidence_types=evidence_types,
        verification_methods=verification_methods,
        verification_status=verification_status,
        verification_boundary=verification_boundary,
        evidence_requirements=evidence_requirements,
        domain_evidence=domain_evidence,
        reproduction_plan_ids=reproduction_plan_ids,
        notes=notes,
    )
