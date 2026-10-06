"""Build evidence-backed reproduction plans without executing research artifacts."""

from __future__ import annotations

import hashlib
import re
import shlex
from pathlib import PurePosixPath

from app.schemas.research import (
    Artifact,
    ArtifactConfidence,
    ArtifactFile,
    ArtifactFileRole,
    ArtifactStatus,
    ArtifactType,
    Certainty,
    ClaimEvidenceAssessment,
    CommandSafety,
    ConfigurationRequirement,
    DataRequirement,
    DependencyRequirement,
    EnvironmentSpecification,
    EnvironmentStatus,
    EvidenceItem,
    ExecutionInput,
    ExecutionOutput,
    ExecutionPhase,
    ExecutionStep,
    ExpectedMetric,
    Experiment,
    ExperimentArtifactMap,
    FileRelevanceStatus,
    HardwareRequirement,
    ModelRequirement,
    ParameterStatus,
    PlanEvidence,
    PlanIssue,
    PlannedCommand,
    ReadinessAssessment,
    ReportedParameter,
    ReproductionPlan,
    ReproductionPlanStatus,
    RequirementStatus,
    ResearchAnalysis,
)


STEP_ROLES = {
    ArtifactFileRole.ENTRYPOINT,
    ArtifactFileRole.TRAINING,
    ArtifactFileRole.EVALUATION,
    ArtifactFileRole.INFERENCE,
    ArtifactFileRole.DATA_PREPARATION,
    ArtifactFileRole.EXECUTION_SCRIPT,
    ArtifactFileRole.PREPROCESSING,
    ArtifactFileRole.POSTPROCESSING,
    ArtifactFileRole.METRIC,
}
PHASE_BY_ROLE = {
    ArtifactFileRole.ENTRYPOINT: ExecutionPhase.PREPARATION,
    ArtifactFileRole.EXECUTION_SCRIPT: ExecutionPhase.PREPARATION,
    ArtifactFileRole.DATA_PREPARATION: ExecutionPhase.DATA_PREPARATION,
    ArtifactFileRole.PREPROCESSING: ExecutionPhase.DATA_PREPARATION,
    ArtifactFileRole.TRAINING: ExecutionPhase.TRAINING,
    ArtifactFileRole.CHECKPOINT: ExecutionPhase.CHECKPOINTING,
    ArtifactFileRole.INFERENCE: ExecutionPhase.INFERENCE,
    ArtifactFileRole.EVALUATION: ExecutionPhase.EVALUATION,
    ArtifactFileRole.METRIC: ExecutionPhase.EVALUATION,
    ArtifactFileRole.POSTPROCESSING: ExecutionPhase.POSTPROCESSING,
}
PHASE_ORDER = {phase: index for index, phase in enumerate(ExecutionPhase)}
UNSAFE_COMMAND_PATTERNS = {
    "privilege escalation": r"(?:^|\s)sudo(?:\s|$)",
    "filesystem deletion": r"(?:^|\s)(?:rm|rmdir|del)\s",
    "permission mutation": r"(?:^|\s)chmod\s",
    "network download": r"(?:^|\s)(?:curl|wget)\s|https?://",
    "package installation": r"(?:pip|pip3|conda|mamba|npm|yarn|pnpm)\s+install\b",
    "container execution": r"(?:docker|podman)\s+(?:run|build|compose)\b",
    "repository mutation": r"(?:^|\s)git\s+(?:clone|pull|checkout|reset)\b",
    "shell composition": r"&&|\|\||(?<!\|)\|(?!\|)|(?:^|\s)[<>](?:\s|$)",
    "credential reference": r"(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH)",
}
PARAMETER_PATTERNS = {
    "learning_rate": r"\blearning[ _-]?rate\b\s*(?:of|=|:|was|is)?\s*([0-9]+(?:\.[0-9]+)?(?:e[+-]?\d+)?)",
    "batch_size": r"\bbatch[ _-]?size\b\s*(?:of|=|:|was|is)?\s*(\d+)",
    "epochs": r"\b(?:number of )?epochs?\b\s*(?:of|=|:|was|is)?\s*(\d+)",
    "optimizer": r"\boptimizer\b\s*(?:of|=|:|was|is)?\s*([A-Za-z][A-Za-z0-9_-]*)",
    "scheduler": r"\b(?:learning rate )?scheduler\b\s*(?:of|=|:|was|is)?\s*([A-Za-z][A-Za-z0-9_-]*)",
    "seed": r"\b(?:random )?seed\b\s*(?:of|=|:|was|is)?\s*(\d+)",
    "max_sequence_length": r"\bmax(?:imum)?[ _-]?sequence[ _-]?length\b\s*(?:of|=|:|was|is)?\s*(\d+)",
    "hidden_size": r"\bhidden[ _-]?size\b\s*(?:of|=|:|was|is)?\s*(\d+)",
    "layers": r"\b(?:number of )?layers?\b\s*(?:of|=|:|was|is)?\s*(\d+)",
    "beam_size": r"\bbeam[ _-]?size\b\s*(?:of|=|:|was|is)?\s*(\d+)",
    "temperature": r"\btemperature\b\s*(?:of|=|:|was|is)?\s*([0-9]+(?:\.[0-9]+)?)",
}


def _stable_id(prefix: str, *parts: str | None) -> str:
    value = ":".join(part or "none" for part in parts)
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16].upper()}"


def _artifact_status(artifact: Artifact | None) -> RequirementStatus:
    if artifact is None or artifact.availability_status == ArtifactStatus.MISSING:
        return RequirementStatus.MISSING
    if artifact.availability_status == ArtifactStatus.INACCESSIBLE:
        return RequirementStatus.INACCESSIBLE
    if artifact.availability_status == ArtifactStatus.AMBIGUOUS:
        return RequirementStatus.UNKNOWN
    return RequirementStatus.AVAILABLE


def _artifact_evidence(artifact: Artifact, fallback: str) -> PlanEvidence:
    return PlanEvidence(
        source="artifact",
        source_path=artifact.source_url or artifact.repository,
        evidence=artifact.evidence_location or artifact.description or fallback,
        certainty=Certainty.EXPLICIT,
        confidence=artifact.confidence,
    )


def _file_evidence(item: ArtifactFile) -> list[PlanEvidence]:
    evidence = item.evidence or [f"Observed repository path: {item.path}"]
    certainty = (
        Certainty.EXPLICIT
        if item.relevance_status == FileRelevanceStatus.RELEVANT
        else Certainty.INFERRED
    )
    return [
        PlanEvidence(
            source="repository_file",
            source_path=item.path,
            evidence=value,
            certainty=certainty,
            confidence=item.confidence,
        )
        for value in evidence
    ]


def classify_command_safety(command: str) -> tuple[CommandSafety, list[str]]:
    """Classify command text only; this function never invokes it."""

    reasons = [
        label for label, pattern in UNSAFE_COMMAND_PATTERNS.items()
        if re.search(pattern, command, re.IGNORECASE)
    ]
    if reasons:
        return CommandSafety.UNSAFE_TO_EXECUTE, reasons
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return CommandSafety.UNKNOWN, ["Command could not be tokenized safely"]
    if not tokens:
        return CommandSafety.UNKNOWN, ["Empty command"]
    executable = tokens[0].casefold()
    if executable in {"python", "python3", "bash", "sh", "zsh", "powershell", "pwsh", "cmd"}:
        return CommandSafety.REQUIRES_REVIEW, ["Invokes an untrusted script or interpreter"]
    return CommandSafety.SAFE_TO_PLAN, []


def _command_source(command: str, environment: EnvironmentSpecification) -> str | None:
    if command.lstrip().upper().startswith(("CMD ", "ENTRYPOINT ")):
        container = next(
            (item.source_path for item in environment.evidence if item.category == "container"),
            None,
        )
        if container:
            return container
    return None


def _commands(
    environment: EnvironmentSpecification | None, files: list[ArtifactFile]
) -> list[PlannedCommand]:
    if environment is None:
        return []
    result: list[PlannedCommand] = []
    mapped_paths = {item.path.casefold() for item in files}
    mapped_names = {PurePosixPath(item.path).name.casefold() for item in files}
    for command in environment.documented_commands:
        referenced_scripts = {
            match.casefold() for match in re.findall(
                r"[A-Za-z0-9_./-]+\.(?:py|sh|bash|ipynb|js|ts|jar|exe)", command
            )
        }
        if referenced_scripts and not any(
            value in mapped_paths or PurePosixPath(value).name in mapped_names
            for value in referenced_scripts
        ):
            continue
        safety, reasons = classify_command_safety(command)
        source_path = _command_source(command, environment) or next(
            (
                item.path for item in files
                if item.path.casefold() in command.casefold()
                or PurePosixPath(item.path).name.casefold() in command.casefold()
            ),
            None,
        )
        result.append(PlannedCommand(
            command=command,
            source="repository_documentation" if source_path else environment.environment_id,
            source_path=source_path,
            evidence=command,
            certainty=Certainty.EXPLICIT,
            safety=safety,
            safety_reasons=reasons,
        ))
    return result


def _select_artifact(
    experiment: Experiment,
    artifacts: list[Artifact],
    mappings: list[ExperimentArtifactMap],
) -> Artifact | None:
    mapped_ids = {item.artifact_id for item in mappings if item.experiment_id == experiment.id}
    candidates = [
        item for item in artifacts
        if item.artifact_id in mapped_ids or item.experiment_id == experiment.id
    ]
    candidates.sort(key=lambda item: (
        item.type != ArtifactType.CODE,
        item.availability_status == ArtifactStatus.INACCESSIBLE,
        item.artifact_id,
    ))
    return candidates[0] if candidates else None


def _select_environment(
    experiment_id: str,
    artifact_id: str | None,
    environments: list[EnvironmentSpecification],
) -> EnvironmentSpecification | None:
    ranked = sorted(environments, key=lambda item: (
        item.artifact_id != artifact_id,
        item.experiment_id != experiment_id,
        item.experiment_id is None,
        item.environment_id,
    ))
    for item in ranked:
        if artifact_id is not None and item.artifact_id != artifact_id:
            continue
        if item.experiment_id in {experiment_id, None}:
            return item
    return next((item for item in ranked if item.experiment_id == experiment_id), None)


def _related_artifact(
    artifacts: list[Artifact], experiment: Experiment, artifact_type: ArtifactType, name: str | None
) -> Artifact | None:
    normalized = (name or "").casefold()
    candidates = [item for item in artifacts if item.type == artifact_type]
    candidates.sort(key=lambda item: (
        item.experiment_id != experiment.id,
        normalized not in (item.name or "").casefold(),
        item.artifact_id,
    ))
    return candidates[0] if candidates and (
        candidates[0].experiment_id == experiment.id
        or (normalized and normalized in (candidates[0].name or "").casefold())
    ) else None


def _data_requirements(
    experiment: Experiment, artifacts: list[Artifact], files: list[ArtifactFile]
) -> list[DataRequirement]:
    if not experiment.dataset:
        return []
    artifact = _related_artifact(artifacts, experiment, ArtifactType.DATASET, experiment.dataset)
    status = _artifact_status(artifact)
    preprocessing = sorted({
        item.path for item in files if item.role in {
            ArtifactFileRole.DATA_PREPARATION, ArtifactFileRole.PREPROCESSING
        }
    })
    evidence = [
        PlanEvidence(
            source="paper_experiment",
            source_path=location,
            evidence=f"Experiment identifies dataset {experiment.dataset}.",
            certainty=Certainty.EXPLICIT,
            confidence=ArtifactConfidence.HIGH,
        )
        for location in (experiment.evidence_locations or ["paper"])
    ]
    if artifact is not None:
        evidence.append(_artifact_evidence(artifact, f"Artifact for {experiment.dataset}"))
    return [DataRequirement(
        dataset_name=experiment.dataset,
        dataset_type="REPORTED_DATASET",
        source=(artifact.source_url or artifact.source) if artifact else None,
        access_requirement="External access required" if artifact and artifact.source_url else None,
        split=experiment.split,
        preprocessing=preprocessing,
        download_required=True if artifact and artifact.source_url else None,
        evidence=evidence,
        certainty=Certainty.EXPLICIT,
        confidence=artifact.confidence if artifact else ArtifactConfidence.MEDIUM,
        status=status,
        notes=[] if artifact else ["No accessible dataset artifact was associated with the experiment."],
    )]


def _model_requirements(
    experiment: Experiment, artifacts: list[Artifact]
) -> list[ModelRequirement]:
    if not experiment.model:
        return []
    artifact = _related_artifact(artifacts, experiment, ArtifactType.MODEL, experiment.model)
    evidence = [PlanEvidence(
        source="paper_experiment",
        source_path=(experiment.evidence_locations[0] if experiment.evidence_locations else "paper"),
        evidence=f"Experiment identifies model {experiment.model}.",
        certainty=Certainty.EXPLICIT,
        confidence=ArtifactConfidence.HIGH,
    )]
    if artifact:
        evidence.append(_artifact_evidence(artifact, f"Model artifact for {experiment.model}"))
    return [ModelRequirement(
        name=experiment.model,
        artifact_id=artifact.artifact_id if artifact else None,
        type="MODEL",
        source=(artifact.source_url or artifact.source) if artifact else None,
        version=artifact.version if artifact else None,
        evidence=evidence,
        certainty=Certainty.EXPLICIT,
        confidence=artifact.confidence if artifact else ArtifactConfidence.MEDIUM,
        availability=_artifact_status(artifact),
        notes=[] if artifact else ["No model artifact was associated with the experiment."],
    )]


def _checkpoint_requirements(
    experiment: Experiment, artifacts: list[Artifact], files: list[ArtifactFile]
) -> list[ModelRequirement]:
    result: list[ModelRequirement] = []
    for item in sorted((value for value in files if value.role == ArtifactFileRole.CHECKPOINT), key=lambda value: value.path):
        result.append(ModelRequirement(
            name=PurePosixPath(item.path).name,
            artifact_id=item.artifact_id,
            type="CHECKPOINT",
            local_path=item.path,
            expected_format=PurePosixPath(item.path).suffix.lstrip(".") or None,
            evidence=_file_evidence(item),
            certainty=Certainty.EXPLICIT,
            confidence=item.confidence,
            availability=RequirementStatus.AVAILABLE,
        ))
    artifact = _related_artifact(artifacts, experiment, ArtifactType.CHECKPOINT, experiment.model)
    if artifact and not result:
        result.append(ModelRequirement(
            name=artifact.name or "Reported checkpoint",
            artifact_id=artifact.artifact_id,
            type="CHECKPOINT",
            source=artifact.source_url or artifact.source,
            expected_format=PurePosixPath(artifact.name or "").suffix.lstrip(".") or None,
            version=artifact.version,
            evidence=[_artifact_evidence(artifact, "Checkpoint artifact")],
            certainty=Certainty.EXPLICIT,
            confidence=artifact.confidence,
            availability=_artifact_status(artifact),
        ))
    return result


def _configurations(
    experiment: Experiment,
    files: list[ArtifactFile],
    environment: EnvironmentSpecification | None,
) -> list[ConfigurationRequirement]:
    result: list[ConfigurationRequirement] = []
    seen: set[str] = set()
    for item in sorted((value for value in files if value.role == ArtifactFileRole.CONFIGURATION), key=lambda value: value.path):
        seen.add(item.path.casefold())
        result.append(ConfigurationRequirement(
            path=item.path,
            experiment_id=experiment.id,
            purpose="Repository configuration mapped to the experiment",
            evidence=_file_evidence(item),
            certainty=Certainty.EXPLICIT if item.relevance_status == FileRelevanceStatus.RELEVANT else Certainty.INFERRED,
            confidence=item.confidence,
            status=RequirementStatus.AVAILABLE,
        ))
    if environment:
        for item in environment.configuration_files:
            if item.path.casefold() in seen:
                continue
            result.append(ConfigurationRequirement(
                path=item.path,
                experiment_id=experiment.id,
                purpose=item.purpose,
                evidence=[PlanEvidence(
                    source="environment",
                    source_path=item.path,
                    evidence=item.evidence or f"Observed configuration: {item.path}",
                    certainty=Certainty.EXPLICIT,
                    confidence=ArtifactConfidence.MEDIUM,
                )],
                certainty=Certainty.EXPLICIT,
                confidence=ArtifactConfidence.MEDIUM,
                status=RequirementStatus.AVAILABLE,
            ))
    return result


def _dependencies(environment: EnvironmentSpecification | None) -> list[DependencyRequirement]:
    if environment is None:
        return []
    return [DependencyRequirement(
        name=item.name,
        version_constraint=item.version_constraint,
        dependency_type=item.dependency_type,
        source_path=item.source_path,
        evidence=item.evidence,
        certainty=item.certainty,
        status=RequirementStatus.AVAILABLE,
    ) for item in environment.dependencies]


def _hardware(environment: EnvironmentSpecification | None) -> list[HardwareRequirement]:
    if environment is None:
        return []
    values = {
        "gpu": environment.gpu,
        "gpu_memory": environment.gpu_memory,
        "cpu": environment.cpu,
        "system_memory": environment.memory,
        "storage": environment.storage,
        "cuda": environment.cuda_version,
        "cudnn": environment.cudnn_version,
    }
    result: list[HardwareRequirement] = []
    for category, value in values.items():
        if not value:
            continue
        matching = next((item for item in environment.evidence if item.category == category), None)
        result.append(HardwareRequirement(
            category=category,
            value=value,
            source_path=matching.source_path if matching else None,
            evidence=matching.evidence if matching else None,
            certainty=matching.certainty if matching else Certainty.EXPLICIT,
            status=RequirementStatus.AVAILABLE,
        ))
    return result


def _parameters(experiment: Experiment, paper_text: str, experiment_count: int) -> list[ReportedParameter]:
    terms = {
        value.casefold() for value in (
            experiment.dataset, experiment.model, experiment.metric
        ) if value and len(value) >= 3
    }
    result: list[ReportedParameter] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_line in paper_text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if experiment_count > 1 and terms and not any(term in line.casefold() for term in terms):
            continue
        for name, pattern in PARAMETER_PATTERNS.items():
            match = re.search(pattern, line, re.IGNORECASE)
            if not match:
                continue
            key = (name, match.group(1), line)
            if key in seen:
                continue
            seen.add(key)
            result.append(ReportedParameter(
                name=name,
                value=match.group(1),
                source="paper",
                experiment_id=experiment.id,
                evidence=line[:500],
                certainty=Certainty.EXPLICIT,
                confidence=ArtifactConfidence.HIGH,
                status=ParameterStatus.REPORTED,
            ))
    return result


def _expected_metrics(experiment: Experiment) -> list[ExpectedMetric]:
    if not experiment.metric:
        return []
    evidence = (
        f"Paper reports {experiment.metric} = {experiment.reported_result}."
        if experiment.reported_result is not None
        else f"Paper identifies {experiment.metric} as the evaluation metric."
    )
    return [ExpectedMetric(
        metric_name=experiment.metric,
        expected_value=experiment.reported_result,
        split=experiment.split,
        source="paper_experiment",
        experiment_id=experiment.id,
        evidence=evidence,
        certainty=Certainty.EXPLICIT,
        confidence=ArtifactConfidence.HIGH,
    )]


def _inputs(
    data: list[DataRequirement], models: list[ModelRequirement], checkpoints: list[ModelRequirement]
) -> list[ExecutionInput]:
    result = [ExecutionInput(
        name=item.dataset_name,
        type="DATASET",
        source=item.source,
        required=True,
        evidence=item.evidence[0].evidence if item.evidence else None,
        certainty=item.certainty,
        status=item.status,
    ) for item in data]
    result.extend(ExecutionInput(
        name=item.name,
        type=item.type,
        source=item.source,
        path=item.local_path,
        required=item.required,
        evidence=item.evidence[0].evidence if item.evidence else None,
        certainty=item.certainty,
        status=item.availability,
    ) for item in [*models, *checkpoints])
    return result


def _outputs(metrics: list[ExpectedMetric]) -> list[ExecutionOutput]:
    return [ExecutionOutput(
        name=item.metric_name,
        type="EXPECTED_METRIC",
        expected_content=(str(item.expected_value) if item.expected_value is not None else None),
        evidence=item.evidence,
        certainty=item.certainty,
        status=RequirementStatus.AVAILABLE,
    ) for item in metrics]


def _steps(
    experiment: Experiment,
    files: list[ArtifactFile],
    environment: EnvironmentSpecification | None,
    commands: list[PlannedCommand],
    inputs: list[ExecutionInput],
    outputs: list[ExecutionOutput],
    configurations: list[ConfigurationRequirement],
) -> list[ExecutionStep]:
    candidates = [item for item in files if item.role in STEP_ROLES]
    candidates.sort(key=lambda item: (
        PHASE_ORDER[PHASE_BY_ROLE[item.role]], item.path.casefold()
    ))
    result: list[ExecutionStep] = []
    for order, item in enumerate(candidates, start=1):
        basename = PurePosixPath(item.path).name.casefold()
        command = next(
            (value for value in commands if basename in value.command.casefold()),
            None,
        )
        phase = PHASE_BY_ROLE[item.role]
        step_outputs = outputs if phase == ExecutionPhase.EVALUATION else []
        arguments: list[str] = []
        if command:
            try:
                tokens = shlex.split(command.command, posix=True)
                script_idx = -1
                for i, token in enumerate(tokens):
                    if basename in token.casefold() or item.path.casefold() in token.casefold():
                        script_idx = i
                        break
                if script_idx >= 0 and script_idx + 1 < len(tokens):
                    arguments = tokens[script_idx + 1:]
            except Exception:
                pass
        result.append(ExecutionStep(
            step_id=_stable_id("STEP", experiment.id, item.artifact_id, item.path),
            experiment_id=experiment.id,
            order=order,
            phase=phase,
            role=item.role,
            entrypoint=item.role in {
                ArtifactFileRole.ENTRYPOINT, ArtifactFileRole.EXECUTION_SCRIPT,
                ArtifactFileRole.TRAINING, ArtifactFileRole.EVALUATION,
                ArtifactFileRole.INFERENCE, ArtifactFileRole.DATA_PREPARATION,
            },
            script_path=item.path,
            command=command,
            arguments=arguments,
            inputs=inputs,
            outputs=step_outputs,
            environment_id=environment.environment_id if environment else None,
            configuration=[value.path for value in configurations],
            prerequisites=[value.name for value in inputs if value.required],
            evidence=_file_evidence(item),
            certainty=Certainty.EXPLICIT if item.relevance_status == FileRelevanceStatus.RELEVANT else Certainty.INFERRED,
            confidence=item.confidence,
            status=(RequirementStatus.AVAILABLE if item.relevance_status != FileRelevanceStatus.UNRELATED else RequirementStatus.UNKNOWN),
            notes=["Planned from repository metadata only; the file was not executed."],
        ))
    return result


def _claim_evidence(
    experiment: Experiment,
    analysis: ResearchAnalysis,
    evidence_items: list[EvidenceItem],
    assessments: list[ClaimEvidenceAssessment],
) -> list[PlanEvidence]:
    claim_ids = {
        claim.id for claim in analysis.claims
        if experiment.metric and claim.metric and claim.metric.casefold() == experiment.metric.casefold()
    }
    evidence_by_id = {item.evidence_id: item for item in evidence_items}
    result: list[PlanEvidence] = []
    for assessment in assessments:
        if assessment.claim_id not in claim_ids:
            continue
        for evidence_id in assessment.evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                continue
            result.append(PlanEvidence(
                source=item.source or item.evidence_type,
                source_path=item.source_locator or item.citation_location,
                evidence=item.excerpt or item.citation_context or assessment.explanation,
                certainty=Certainty.EXPLICIT if item.directness.value == "DIRECT" else Certainty.INFERRED,
                confidence=ArtifactConfidence(item.relevance.value if item.relevance.value in {"HIGH", "MEDIUM", "LOW"} else "LOW"),
            ))
    return result


def _issue(
    category: str, requirement: str, status: RequirementStatus, detail: str,
    *, source: str | None = None, evidence: str | None = None,
    certainty: Certainty = Certainty.UNKNOWN,
) -> PlanIssue:
    return PlanIssue(
        category=category,
        requirement=requirement,
        status=status,
        detail=detail,
        source=source,
        evidence=evidence,
        certainty=certainty,
    )


def _readiness(
    artifact: Artifact | None,
    environment: EnvironmentSpecification | None,
    steps: list[ExecutionStep],
    commands: list[PlannedCommand],
    data: list[DataRequirement],
    models: list[ModelRequirement],
    checkpoints: list[ModelRequirement],
    configurations: list[ConfigurationRequirement],
    mappings: list[ExperimentArtifactMap],
    parameters: list[ReportedParameter],
    metrics: list[ExpectedMetric],
) -> tuple[ReadinessAssessment, ArtifactConfidence]:
    blocking: list[PlanIssue] = []
    missing: list[PlanIssue] = []
    conflicts: list[PlanIssue] = []
    available: list[str] = []

    artifact_state = _artifact_status(artifact)
    if artifact_state == RequirementStatus.INACCESSIBLE:
        blocking.append(_issue("artifact", "code artifact", artifact_state, "The mapped code artifact is inaccessible."))
    elif artifact_state == RequirementStatus.MISSING:
        missing.append(_issue("artifact", "code artifact", artifact_state, "No code artifact is mapped to the experiment."))
    else:
        available.append("code artifact")

    if environment is None:
        missing.append(_issue("environment", "environment specification", RequirementStatus.MISSING, "No environment specification is associated with the artifact."))
    elif environment.status == EnvironmentStatus.BLOCKED:
        blocking.append(_issue("environment", environment.environment_id, RequirementStatus.INACCESSIBLE, "Environment reconstruction is blocked.", source=environment.environment_id))
    elif environment.status == EnvironmentStatus.UNKNOWN:
        missing.append(_issue("environment", environment.environment_id, RequirementStatus.UNKNOWN, "Environment evidence is insufficient.", source=environment.environment_id))
    else:
        available.append("environment specification")
        for value in environment.missing_information:
            missing.append(_issue("environment", value, RequirementStatus.MISSING, value, source=environment.environment_id))
        for value in environment.conflicting_evidence:
            conflicts.append(_issue(
                "environment", value.category, RequirementStatus.CONFLICTING,
                f"Conflicting value: {value.value}", source=value.source_path,
                evidence=value.evidence, certainty=value.certainty,
            ))

    if not steps:
        missing.append(_issue("entrypoint", "execution entrypoint", RequirementStatus.MISSING, "No mapped entrypoint, training, evaluation, inference, or data-preparation file was found."))
    else:
        available.append("mapped execution files")
    if not commands:
        missing.append(_issue("command", "documented command", RequirementStatus.MISSING, "No explicit execution command was documented."))
    else:
        available.append("documented commands")
    if environment is not None and not environment.dependencies:
        missing.append(_issue("dependency", "package dependencies", RequirementStatus.MISSING, "No package dependencies were reconstructed.", source=environment.environment_id))

    for requirement in [*data, *models, *checkpoints]:
        state = requirement.status if isinstance(requirement, DataRequirement) else requirement.availability
        name = requirement.dataset_name if isinstance(requirement, DataRequirement) else requirement.name
        if state == RequirementStatus.INACCESSIBLE:
            blocking.append(_issue(requirement.__class__.__name__, name, state, f"{name} is inaccessible."))
        elif state != RequirementStatus.AVAILABLE:
            missing.append(_issue(requirement.__class__.__name__, name, state, f"{name} is not available."))
        else:
            available.append(name)

    mapped = [item for item in mappings if artifact and item.artifact_id == artifact.artifact_id]
    if any(ArtifactFileRole.CONFIGURATION in item.missing_roles for item in mapped) and not configurations:
        missing.append(_issue("configuration", "experiment configuration", RequirementStatus.MISSING, "Repository inspection did not identify a required configuration."))

    parameter_values: dict[str, set[str]] = {}
    for item in parameters:
        parameter_values.setdefault(item.name, set()).add(item.value)
    for name, values in parameter_values.items():
        if len(values) > 1:
            for value in sorted(values):
                conflicts.append(_issue(
                    "parameter", name, RequirementStatus.CONFLICTING,
                    f"Reported parameter value: {value}", source="paper",
                    certainty=Certainty.EXPLICIT,
                ))

    meaningful = bool(steps or commands or data or models or checkpoints or configurations or parameters or metrics or environment)
    if blocking:
        status = ReproductionPlanStatus.BLOCKED
        rationale = "Planning is blocked by an inaccessible required source or artifact."
        confidence = ArtifactConfidence.LOW
    elif not meaningful:
        status = ReproductionPlanStatus.UNKNOWN
        rationale = "Insufficient evidence exists to construct a meaningful reproduction plan."
        confidence = ArtifactConfidence.LOW
    elif not missing and not conflicts and environment and environment.status == EnvironmentStatus.RECONSTRUCTED and steps and commands:
        status = ReproductionPlanStatus.READY_FOR_EXECUTION
        rationale = "All deterministically required planning inputs are available with no unresolved conflicts. No execution has occurred."
        confidence = ArtifactConfidence.HIGH
    else:
        status = ReproductionPlanStatus.PARTIALLY_READY
        rationale = "A useful plan exists, but required information is missing, uncertain, or conflicting."
        confidence = ArtifactConfidence.LOW if conflicts else ArtifactConfidence.MEDIUM
    readiness_evidence: list[PlanEvidence] = []
    if artifact:
        readiness_evidence.append(_artifact_evidence(artifact, "Reproduction artifact readiness"))
    if environment:
        readiness_evidence.extend(
            PlanEvidence(
                source="environment",
                source_path=ev.source_path,
                evidence=ev.evidence,
                certainty=ev.certainty,
                confidence=ArtifactConfidence.HIGH if ev.certainty == Certainty.EXPLICIT else ArtifactConfidence.MEDIUM,
            )
            for ev in environment.evidence[:3]
        )
    return ReadinessAssessment(
        overall_status=status,
        blocking_requirements=blocking,
        missing_requirements=missing,
        unresolved_conflicts=conflicts,
        available_requirements=list(dict.fromkeys(available)),
        rationale=rationale,
        evidence=readiness_evidence,
    ), confidence


def generate_reproduction_plans(
    analysis: ResearchAnalysis,
    evidence_items: list[EvidenceItem],
    claim_evidence: list[ClaimEvidenceAssessment],
    artifacts: list[Artifact],
    files: list[ArtifactFile],
    experiment_maps: list[ExperimentArtifactMap],
    environments: list[EnvironmentSpecification],
    paper_text: str,
) -> list[ReproductionPlan]:
    """Create one deterministic, non-executing plan for each reported experiment."""

    plans: list[ReproductionPlan] = []
    for experiment in sorted(analysis.experiments, key=lambda item: item.id):
        artifact = _select_artifact(experiment, artifacts, experiment_maps)
        artifact_id = artifact.artifact_id if artifact else None
        mapped_files = [
            item for item in files
            if item.experiment_id == experiment.id
            and item.relevance_status != FileRelevanceStatus.UNRELATED
            and (artifact_id is None or item.artifact_id == artifact_id)
        ]
        environment = _select_environment(experiment.id, artifact_id, environments)
        commands = _commands(environment, mapped_files)
        data = _data_requirements(experiment, artifacts, mapped_files)
        models = _model_requirements(experiment, artifacts)
        checkpoints = _checkpoint_requirements(experiment, artifacts, mapped_files)
        configurations = _configurations(experiment, mapped_files, environment)
        dependencies = _dependencies(environment)
        hardware = _hardware(environment)
        parameters = _parameters(experiment, paper_text, len(analysis.experiments))
        metrics = _expected_metrics(experiment)
        inputs = _inputs(data, models, checkpoints)
        outputs = _outputs(metrics)
        steps = _steps(
            experiment, mapped_files, environment, commands, inputs, outputs, configurations
        )
        readiness, confidence = _readiness(
            artifact, environment, steps, commands, data, models, checkpoints,
            configurations, [item for item in experiment_maps if item.experiment_id == experiment.id],
            parameters, metrics,
        )
        plan_evidence = _claim_evidence(
            experiment, analysis, evidence_items, claim_evidence
        )
        plan_evidence.extend(
            evidence for step in steps for evidence in step.evidence[:1]
        )
        if artifact:
            plan_evidence.append(_artifact_evidence(artifact, "Mapped reproduction artifact"))
        notes = ["PLANNED - NOT EXECUTED. Repository files and commands remain untrusted text."]
        if environment and environment.experiment_id is None:
            notes.append("The environment specification is shared at repository scope.")
        plans.append(ReproductionPlan(
            plan_id=_stable_id("PLAN", experiment.id, artifact_id, environment.environment_id if environment else None),
            experiment_id=experiment.id,
            artifact_id=artifact_id,
            environment_id=environment.environment_id if environment else None,
            status=readiness.overall_status,
            readiness=readiness,
            entrypoints=[item for item in steps if item.entrypoint],
            training_steps=[item for item in steps if item.phase == ExecutionPhase.TRAINING],
            evaluation_steps=[item for item in steps if item.phase == ExecutionPhase.EVALUATION],
            inference_steps=[item for item in steps if item.phase == ExecutionPhase.INFERENCE],
            data_requirements=data,
            model_requirements=models,
            checkpoint_requirements=checkpoints,
            configuration_requirements=configurations,
            dependency_requirements=dependencies,
            hardware_requirements=hardware,
            input_requirements=inputs,
            output_requirements=outputs,
            expected_metrics=metrics,
            expected_results=[item for item in metrics if item.expected_value is not None],
            reported_parameters=parameters,
            commands=commands,
            prerequisites=list(dict.fromkeys([
                *(item.name for item in inputs if item.required),
                *(item.name for item in dependencies),
                *(item.path for item in configurations if item.required),
            ])),
            missing_requirements=readiness.missing_requirements,
            conflicts=readiness.unresolved_conflicts,
            evidence=plan_evidence,
            confidence=confidence,
            notes=notes,
        ))
    return plans
