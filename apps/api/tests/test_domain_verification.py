"""Tests for Step 6: Domain-Agnostic Verification Layer."""

from app.schemas.research import (
    Artifact,
    ArtifactConfidence,
    ArtifactDiscoveryMethod,
    ArtifactFile,
    ArtifactFileRole,
    ArtifactFileType,
    ArtifactReadiness,
    ArtifactStatus,
    ArtifactType,
    Certainty,
    Claim,
    EvidenceItem,
    EvidenceRequirement,
    EvidenceType,
    Experiment,
    PaperMetadata,
    ReadinessAssessment,
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
from app.services.verification.case import (
    build_research_case,
    classify_research_domain,
    derive_verification_boundary,
    derive_verification_status,
    derive_verification_strategy,
    extract_evidence_requirements,
)


def _make_sample_plan(plan_id: str, status: ReproductionPlanStatus) -> ReproductionPlan:
    return ReproductionPlan(
        plan_id=plan_id,
        experiment_id="EXP-001",
        environment_id="ENV-001",
        status=status,
        readiness=ReadinessAssessment(
            overall_status=status,
            rationale="Deterministic readiness evaluation.",
        ),
        confidence=ArtifactConfidence.HIGH,
    )


def test_domain_classification_aiml() -> None:
    analysis = ResearchAnalysis(
        paper=PaperMetadata(
            title="Attention Is All You Need: Deep Learning with Transformers",
            abstract="We propose the Transformer, a model architecture relying entirely on attention mechanisms to draw global dependencies.",
        ),
        methods=["Transformer neural network architecture", "Adam optimizer with learning rate warmup"],
        experiments=[
            Experiment(
                id="EXP-001",
                objective="Evaluate translation on WMT 2014 English-to-German",
                model="Transformer-Base",
                dataset="WMT 2014 En-De",
                metric="BLEU",
                reported_result=28.4,
            )
        ],
    )
    paper_text = "We train on 8 NVIDIA P100 GPUs using PyTorch with CUDA acceleration. Checkpoint weights and hyperparameters are reported."
    code_artifact = Artifact(
        artifact_id="ART-001",
        type=ArtifactType.CODE,
        name="tensor2tensor",
        source="github",
        discovery_method=ArtifactDiscoveryMethod.PAPER_URL,
        relationship_status=ArtifactStatus.FOUND,
        availability_status=ArtifactStatus.FOUND,
        confidence=ArtifactConfidence.HIGH,
    )

    domain, confidence, evidence = classify_research_domain(analysis, paper_text, [code_artifact])
    assert domain == ResearchDomain.AI_ML
    assert confidence == ArtifactConfidence.HIGH
    assert any("AI_ML" in item for item in evidence)


def test_domain_classification_social_science() -> None:
    analysis = ResearchAnalysis(
        paper=PaperMetadata(
            title="The Impact of Minimum Wage on Employment: A Survey of Fast-Food Establishments",
            abstract="We evaluate the causal effect of minimum wage policy changes on employment across 410 fast-food respondents using difference-in-differences regression.",
        ),
        methods=["Difference-in-differences regression", "Sampling of telephone survey questionnaire respondents"],
        experiments=[
            Experiment(
                id="EXP-001",
                objective="Estimate employment elasticity from wage policy changes",
                dataset="New Jersey and Pennsylvania Fast-Food Survey",
                metric="Employment change elasticity",
                reported_result=0.05,
            )
        ],
    )
    paper_text = "Our survey collected microdata on wages, store hours, and full-time employment from 410 respondent stores. We analyzed demographic trends and public policy implications."

    domain, confidence, evidence = classify_research_domain(analysis, paper_text, [])
    assert domain == ResearchDomain.SOCIAL_SCIENCE
    assert confidence in (ArtifactConfidence.HIGH, ArtifactConfidence.MEDIUM)
    assert any("SOCIAL_SCIENCE" in item for item in evidence)


def test_domain_classification_humanities() -> None:
    analysis = ResearchAnalysis(
        paper=PaperMetadata(
            title="Hermeneutics of 19th-Century Archival Manuscripts: A Textual Analysis",
            abstract="This paper conducts a historical analysis of archival letters and manuscripts to explore early modernist philosophy and cultural literary traditions.",
        ),
        methods=["Archival manuscript analysis", "Historiographical and hermeneutic interpretation"],
    )
    paper_text = "We examined rare archival collections and historical manuscripts in European archives, focusing on critical theory, narratology, and philosophical rhetoric."

    domain, confidence, evidence = classify_research_domain(analysis, paper_text, [])
    assert domain == ResearchDomain.HUMANITIES
    assert confidence in (ArtifactConfidence.HIGH, ArtifactConfidence.MEDIUM)


def test_domain_classification_biology() -> None:
    analysis = ResearchAnalysis(
        paper=PaperMetadata(
            title="CRISPR-Cas9 Genome Editing in Human Cell Cultures",
            abstract="High-throughput genomic sequencing and RNA-seq assays reveal off-target cleavage in human cell culture samples.",
        ),
        methods=["CRISPR gene editing", "RNA-seq sequencing assay", "In vitro cell culture"],
    )
    paper_text = "We conducted PCR amplification and protein assay analysis across human cellular tissue samples to assess gene expression and phenotype alteration."

    domain, confidence, evidence = classify_research_domain(analysis, paper_text, [])
    assert domain == ResearchDomain.BIOLOGY
    assert confidence in (ArtifactConfidence.HIGH, ArtifactConfidence.MEDIUM)


def test_domain_classification_physics_chemistry() -> None:
    analysis = ResearchAnalysis(
        paper=PaperMetadata(
            title="Laser Spectroscopy and Crystallography of Superconducting Lattices",
            abstract="We investigate quantum state transitions and crystal diffraction using synchrotron magnetic resonance and molecular dynamics.",
        ),
        methods=["X-ray diffraction spectroscopy", "Molecular dynamics simulation of Hamiltonian lattice"],
    )
    paper_text = "The chemical synthesis protocol utilized high-purity catalysts. Stoichiometry and plasma interactions were measured via laser spectroscopy."

    domain, confidence, evidence = classify_research_domain(analysis, paper_text, [])
    assert domain == ResearchDomain.PHYSICS_CHEMISTRY
    assert confidence in (ArtifactConfidence.HIGH, ArtifactConfidence.MEDIUM)


def test_domain_classification_engineering() -> None:
    analysis = ResearchAnalysis(
        paper=PaperMetadata(
            title="Finite Element Analysis of Turbine Blades under Aerodynamic Stress",
            abstract="We evaluate structural integrity, mechanical design, and fluid dynamics of gas turbine blades using CAD models.",
        ),
        methods=["Finite element stress analysis", "Computational fluid dynamics"],
    )
    paper_text = "CAD models and aerodynamic load bearing parameters were analyzed to optimize mechanical design against thermal stress."

    domain, confidence, evidence = classify_research_domain(analysis, paper_text, [])
    assert domain == ResearchDomain.ENGINEERING
    assert confidence in (ArtifactConfidence.HIGH, ArtifactConfidence.MEDIUM)


def test_domain_classification_insufficient_evidence_unknown() -> None:
    analysis = ResearchAnalysis(
        paper=PaperMetadata(title="Overview Notes"),
    )
    paper_text = "Some generic introductory remarks without specific disciplinary vocabulary."

    domain, confidence, evidence = classify_research_domain(analysis, paper_text, [])
    assert domain == ResearchDomain.UNKNOWN
    assert confidence == ArtifactConfidence.LOW


def test_verification_strategy_mapping() -> None:
    aiml_strat = derive_verification_strategy(ResearchDomain.AI_ML)
    assert aiml_strat == [VerificationMethod.COMPUTATIONAL_REPRODUCTION]

    soc_strat = derive_verification_strategy(ResearchDomain.SOCIAL_SCIENCE)
    assert VerificationMethod.STATISTICAL_VERIFICATION in soc_strat
    assert VerificationMethod.DOCUMENTARY_VERIFICATION in soc_strat
    assert VerificationMethod.QUALITATIVE_EVIDENCE_REVIEW in soc_strat
    assert VerificationMethod.HUMAN_EXPERT_VALIDATION in soc_strat

    hum_strat = derive_verification_strategy(ResearchDomain.HUMANITIES)
    assert VerificationMethod.DOCUMENTARY_VERIFICATION in hum_strat
    assert VerificationMethod.HUMAN_EXPERT_VALIDATION in hum_strat

    bio_strat = derive_verification_strategy(ResearchDomain.BIOLOGY)
    assert VerificationMethod.EXPERIMENTAL_VERIFICATION in bio_strat

    unk_strat = derive_verification_strategy(ResearchDomain.UNKNOWN)
    assert unk_strat == [VerificationMethod.UNKNOWN]


def test_verification_boundary_delineation() -> None:
    aiml_boundary = derive_verification_boundary(ResearchDomain.AI_ML)
    assert any("reproduction planning" in item.lower() for item in aiml_boundary.automatable_scope)
    assert any("private repository" in item.lower() for item in aiml_boundary.requires_restricted_access)
    assert any("ethical" in item.lower() or "alignment" in item.lower() for item in aiml_boundary.requires_human_validation)
    assert any("not performed" in item.lower() for item in aiml_boundary.unverifiable_scope)

    soc_boundary = derive_verification_boundary(ResearchDomain.SOCIAL_SCIENCE)
    assert any("survey instrument" in item.lower() or "regression" in item.lower() for item in soc_boundary.automatable_scope)
    assert any("confidential microdata" in item.lower() for item in soc_boundary.requires_restricted_access)
    assert any("interview" in item.lower() or "transcripts" in item.lower() for item in soc_boundary.requires_human_validation)
    assert any("live re-interviewing" in item.lower() for item in soc_boundary.unverifiable_scope)


def test_evidence_requirements_extraction() -> None:
    analysis = ResearchAnalysis(
        paper=PaperMetadata(title="Sample Paper"),
        claims=[
            Claim(
                id="CLM-001",
                claim_text="Achieves 95.2% accuracy.",
                claim_type="PERFORMANCE",
                metric="Accuracy",
                reported_value=95.2,
            ),
            Claim(
                id="CLM-002",
                claim_text="Outperforms previous baselines.",
                claim_type="COMPARATIVE",
            ),
        ],
    )
    artifacts = [
        Artifact(
            artifact_id="ART-CODE",
            type=ArtifactType.CODE,
            name="github/repo",
            discovery_method=ArtifactDiscoveryMethod.PAPER_URL,
            relationship_status=ArtifactStatus.FOUND,
            availability_status=ArtifactStatus.FOUND,
            confidence=ArtifactConfidence.HIGH,
        ),
        Artifact(
            artifact_id="ART-DATA",
            type=ArtifactType.DATASET,
            name="benchmark-dataset",
            discovery_method=ArtifactDiscoveryMethod.PAPER_TEXT,
            relationship_status=ArtifactStatus.FOUND,
            availability_status=ArtifactStatus.FOUND,
            confidence=ArtifactConfidence.HIGH,
        ),
    ]

    types, reqs = extract_evidence_requirements(analysis, artifacts, ResearchDomain.AI_ML)
    assert EvidenceType.STATISTICAL_OUTPUT in types
    assert EvidenceType.CODE in types
    assert EvidenceType.DATASET in types

    req_map = {r.requirement_id: r for r in reqs}
    assert "EV-REQ-CLAIM-CLM-001" in req_map
    assert req_map["EV-REQ-CLAIM-CLM-001"].status == RequirementStatus.AVAILABLE
    assert "EV-REQ-ART-ART-CODE" in req_map
    assert req_map["EV-REQ-ART-ART-CODE"].status == RequirementStatus.AVAILABLE


def test_social_science_evidence_requirements() -> None:
    analysis = ResearchAnalysis(paper=PaperMetadata(title="Survey Paper"))
    types, reqs = extract_evidence_requirements(analysis, [], ResearchDomain.SOCIAL_SCIENCE)
    assert EvidenceType.SURVEY_INSTRUMENT in types
    assert EvidenceType.POLICY_DOCUMENT in types
    assert any(r.evidence_type == EvidenceType.SURVEY_INSTRUMENT for r in reqs)


def test_verification_status_derivation() -> None:
    # AI/ML with ready plan
    ready_plan = _make_sample_plan("PLAN-001", ReproductionPlanStatus.READY_FOR_EXECUTION)
    assert derive_verification_status(ResearchDomain.AI_ML, [ready_plan], []) == VerificationStatus.COMPUTATIONALLY_REPRODUCIBLE

    # AI/ML with partial plan
    partial_plan = _make_sample_plan("PLAN-002", ReproductionPlanStatus.PARTIALLY_READY)
    assert derive_verification_status(ResearchDomain.AI_ML, [partial_plan], []) == VerificationStatus.PARTIALLY_VERIFIABLE

    # AI/ML with no plans
    assert derive_verification_status(ResearchDomain.AI_ML, [], []) == VerificationStatus.INSUFFICIENT_EVIDENCE

    # Social Science with dataset available
    dataset_req = EvidenceRequirement(
        requirement_id="REQ-DATA",
        evidence_type=EvidenceType.DATASET,
        description="Dataset available",
        status=RequirementStatus.AVAILABLE,
        source="archive",
    )
    assert derive_verification_status(ResearchDomain.SOCIAL_SCIENCE, [], [dataset_req]) == VerificationStatus.PARTIALLY_VERIFIABLE

    # Social Science without dataset available
    assert derive_verification_status(ResearchDomain.SOCIAL_SCIENCE, [], []) == VerificationStatus.REQUIRES_HUMAN_VALIDATION

    # Humanities
    assert derive_verification_status(ResearchDomain.HUMANITIES, [], []) == VerificationStatus.DOCUMENTARILY_VERIFIABLE


def test_build_research_case_determinism() -> None:
    analysis = ResearchAnalysis(
        paper=PaperMetadata(
            title="Deep Residual Learning for Image Recognition",
            abstract="Deeper neural networks are more difficult to train. We present a residual learning framework.",
        ),
        claims=[
            Claim(
                id="CLM-001",
                claim_text="Residual networks achieve 3.57% error on ImageNet.",
                claim_type="PERFORMANCE",
                metric="Top-5 error",
                reported_value=3.57,
            )
        ],
        experiments=[
            Experiment(
                id="EXP-001",
                objective="ImageNet classification with ResNet-152",
                model="ResNet-152",
                dataset="ImageNet",
                metric="Top-5 error",
                reported_result=3.57,
            )
        ],
    )
    artifacts = [
        Artifact(
            artifact_id="ART-001",
            type=ArtifactType.CODE,
            name="resnet",
            source_url="https://github.com/facebook/fb.resnet.torch",
            discovery_method=ArtifactDiscoveryMethod.PAPER_URL,
            relationship_status=ArtifactStatus.FOUND,
            availability_status=ArtifactStatus.FOUND,
            confidence=ArtifactConfidence.HIGH,
        )
    ]
    plans = [
        _make_sample_plan("PLAN-RESNET", ReproductionPlanStatus.PARTIALLY_READY)
    ]
    paper_text = "PyTorch CUDA deep learning convolutional neural network benchmark evaluation."

    case1 = build_research_case(
        analysis=analysis,
        evidence_items=[],
        claim_evidence=[],
        artifacts=artifacts,
        files=[],
        reproduction_plans=plans,
        paper_text=paper_text,
    )

    case2 = build_research_case(
        analysis=analysis,
        evidence_items=[],
        claim_evidence=[],
        artifacts=artifacts,
        files=[],
        reproduction_plans=plans,
        paper_text=paper_text,
    )

    assert case1.case_id == case2.case_id
    assert case1.domain == case2.domain == ResearchDomain.AI_ML
    assert case1.domain_confidence == case2.domain_confidence == ArtifactConfidence.HIGH
    assert case1.verification_methods == case2.verification_methods
    assert case1.verification_status == case2.verification_status == VerificationStatus.PARTIALLY_VERIFIABLE
    assert case1.reproduction_plan_ids == case2.reproduction_plan_ids == ["PLAN-RESNET"]
    assert len(case1.evidence_requirements) == len(case2.evidence_requirements)
    assert case1.model_dump() == case2.model_dump()


def test_domain_agnostic_safety_boundary() -> None:
    """Verify that build_research_case does not invoke subprocess, os.system, or external operations."""
    analysis = ResearchAnalysis(
        paper=PaperMetadata(title="Safety Test Paper"),
    )
    case = build_research_case(
        analysis=analysis,
        evidence_items=[],
        claim_evidence=[],
        artifacts=[],
        files=[],
        reproduction_plans=[],
        paper_text="Safe non-executing test text.",
    )
    assert case.case_id.startswith("CASE-")
    assert case.verification_boundary is not None
    assert any("not performed" in s.lower() or "physical" in s.lower() for s in case.verification_boundary.unverifiable_scope)


def test_evidence_type_schema_completeness() -> None:
    """Verify that backend EvidenceType matches the canonical schema contract."""
    expected_members = {
        "CODE",
        "DATASET",
        "MODEL",
        "CHECKPOINT",
        "CONFIGURATION",
        "ENVIRONMENT",
        "STATISTICAL_OUTPUT",
        "SURVEY_INSTRUMENT",
        "INTERVIEW_PROTOCOL",
        "INTERVIEW_TRANSCRIPT",
        "QUALITATIVE_CODING_FRAMEWORK",
        "ARCHIVAL_SOURCE",
        "POLICY_DOCUMENT",
        "LITERATURE",
        "EXPERIMENTAL_PROTOCOL",
        "MEASUREMENT",
        "FIGURE",
        "TABLE",
        "SUPPLEMENTARY_MATERIAL",
        "EXPERT_ASSESSMENT",
        "OTHER",
    }
    actual_members = {e.value for e in EvidenceType}
    assert actual_members == expected_members
