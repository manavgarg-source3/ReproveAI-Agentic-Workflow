"""Bounded, non-executing experiment-to-repository-file inspection."""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.schemas.research import (
    Artifact,
    ArtifactConfidence,
    ArtifactFile,
    ArtifactFileRole,
    ArtifactFileType,
    ArtifactReadiness,
    ArtifactStatus,
    ArtifactType,
    Experiment,
    ExperimentArtifactMap,
    FileRelevanceStatus,
    ResearchAnalysis,
)
from app.services.artifacts.provider import (
    RepositoryFileMetadata,
    RepositoryMetadata,
    RepositoryMetadataProvider,
)
from app.services.artifacts.repository import PublicRepositoryMetadataProvider


@dataclass(frozen=True, slots=True)
class ArtifactInspectionResult:
    files: list[ArtifactFile]
    experiment_maps: list[ExperimentArtifactMap]


DEPENDENCY_NAMES = {
    "requirements.txt", "environment.yml", "environment.yaml", "pyproject.toml",
    "setup.py", "setup.cfg", "pipfile", "package.json", "poetry.lock",
}
CONTAINER_NAMES = {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}
CONFIG_SUFFIXES = {".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf"}
CHECKPOINT_SUFFIXES = {".pt", ".pth", ".bin", ".ckpt", ".safetensors"}
DOCUMENTATION_SUFFIXES = {".md", ".rst", ".txt"}
STOPWORDS = {
    "and", "baseline", "dataset", "evaluate", "evaluation", "experiment", "for",
    "metric", "model", "on", "task", "test", "the", "train", "training", "using",
    "fine", "tune", "tuning", "performance", "results", "analysis", "with",
}


def classify_repository_file(path: str) -> tuple[ArtifactFileType, ArtifactFileRole]:
    """Classify an observed path conservatively without reading or executing it."""

    pure_path = PurePosixPath(path)
    name = pure_path.name.casefold()
    suffix = pure_path.suffix.casefold()
    stem = pure_path.stem.casefold()

    if name in DEPENDENCY_NAMES:
        return ArtifactFileType.DEPENDENCY, ArtifactFileRole.DEPENDENCY
    if name in CONTAINER_NAMES:
        return ArtifactFileType.CONTAINER, ArtifactFileRole.CONFIGURATION
    if name in {"makefile", "justfile"}:
        return ArtifactFileType.MAKEFILE, ArtifactFileRole.EXECUTION_SCRIPT
    if suffix in CHECKPOINT_SUFFIXES:
        return ArtifactFileType.CHECKPOINT, ArtifactFileRole.CHECKPOINT
    if suffix in CONFIG_SUFFIXES:
        return ArtifactFileType.CONFIG, ArtifactFileRole.CONFIGURATION
    if suffix in DOCUMENTATION_SUFFIXES or name.startswith("readme"):
        return ArtifactFileType.DOCUMENTATION, ArtifactFileRole.DOCUMENTATION

    file_type = {
        ".py": ArtifactFileType.PYTHON,
        ".ipynb": ArtifactFileType.NOTEBOOK,
        ".js": ArtifactFileType.JAVASCRIPT,
        ".ts": ArtifactFileType.TYPESCRIPT,
        ".cpp": ArtifactFileType.CPP,
        ".cc": ArtifactFileType.CPP,
        ".cxx": ArtifactFileType.CPP,
        ".java": ArtifactFileType.JAVA,
        ".go": ArtifactFileType.GO,
        ".rs": ArtifactFileType.RUST,
        ".sh": ArtifactFileType.SHELL,
        ".bash": ArtifactFileType.SHELL,
    }.get(suffix, ArtifactFileType.OTHER)

    searchable = f"{pure_path.parent.as_posix()} {stem}".casefold()
    if re.search(r"train|finetun|fine[_-]?tun", searchable):
        role = ArtifactFileRole.TRAINING
    elif re.search(r"eval|evaluate|evaluation|benchmark", searchable):
        role = ArtifactFileRole.EVALUATION
    elif re.search(r"infer|predict|demo", searchable):
        role = ArtifactFileRole.INFERENCE
    elif re.search(r"prepare|dataset|data[_-]?prep", searchable):
        role = ArtifactFileRole.DATA_PREPARATION
    elif re.search(r"model|network|architecture", searchable):
        role = ArtifactFileRole.MODEL_DEFINITION
    elif re.search(r"token|preprocess", searchable):
        role = ArtifactFileRole.PREPROCESSING
    elif re.search(r"postprocess", searchable):
        role = ArtifactFileRole.POSTPROCESSING
    elif re.search(r"metric|score", searchable):
        role = ArtifactFileRole.METRIC
    elif re.search(r"(?:^|[/_\- ])(?:run|main|cli)(?:$|[/_\- ])", searchable):
        role = ArtifactFileRole.ENTRYPOINT
    elif file_type in {ArtifactFileType.SHELL, ArtifactFileType.MAKEFILE}:
        role = ArtifactFileRole.EXECUTION_SCRIPT
    elif file_type == ArtifactFileType.OTHER:
        role = ArtifactFileRole.UNKNOWN
    else:
        role = ArtifactFileRole.UTILITY
    return file_type, role


def _terms(*values: str | None) -> set[str]:
    terms: set[str] = set()
    for value in values:
        for token in re.findall(r"[a-z0-9]+", (value or "").casefold()):
            if len(token) >= 3 and token not in STOPWORDS:
                terms.add(token)
    return terms


def _readme_path_evidence(readme: str | None, path: str) -> list[str]:
    if not readme:
        return []
    name = PurePosixPath(path).name.casefold()
    evidence: list[str] = []
    lowered = readme.casefold()
    start = 0
    while name:
        index = lowered.find(name, start)
        if index < 0:
            break
        compact = re.sub(
            r"\s+", " ", readme[max(0, index - 180):index + len(name) + 180]
        ).strip()
        evidence.append(f"README: {compact[:400]}")
        if len(evidence) == 2:
            break
        start = index + len(name)
    return evidence


def _classify_relevance(
    path: str,
    role: ArtifactFileRole,
    experiment: Experiment,
    artifact: Artifact,
    readme: str | None,
) -> tuple[FileRelevanceStatus, ArtifactConfidence, list[str]]:
    normalized_path = re.sub(r"[^a-z0-9]+", " ", path.casefold())
    model_terms = _terms(experiment.model)
    specific_terms = _terms(
        experiment.dataset,
        experiment.split,
        experiment.metric,
        experiment.baseline,
        experiment.objective,
    ) - model_terms
    matched_terms = sorted(
        term for term in specific_terms if term in normalized_path.split()
    )
    readme_evidence = _readme_path_evidence(readme, path)
    readme_text = " ".join(readme_evidence).casefold()
    readme_matches = sorted(term for term in specific_terms if term in readme_text)
    evidence = [f"Observed repository path: {path}", *readme_evidence]
    ambiguous = artifact.relationship_status in {
        ArtifactStatus.AMBIGUOUS,
        ArtifactStatus.PARTIAL,
    }

    if matched_terms or readme_matches:
        matched = sorted(set(matched_terms + readme_matches))
        evidence.append(f"Repository evidence matches experiment term(s): {', '.join(matched)}.")
        if ambiguous:
            return FileRelevanceStatus.POSSIBLY_RELEVANT, ArtifactConfidence.MEDIUM, evidence
        return FileRelevanceStatus.RELEVANT, ArtifactConfidence.HIGH, evidence
    if readme_evidence and role not in {
        ArtifactFileRole.DOCUMENTATION,
        ArtifactFileRole.UNKNOWN,
        ArtifactFileRole.UTILITY,
    }:
        return FileRelevanceStatus.POSSIBLY_RELEVANT, ArtifactConfidence.MEDIUM, evidence
    if role in {
        ArtifactFileRole.TRAINING,
        ArtifactFileRole.EVALUATION,
        ArtifactFileRole.INFERENCE,
        ArtifactFileRole.DATA_PREPARATION,
        ArtifactFileRole.MODEL_DEFINITION,
        ArtifactFileRole.CHECKPOINT,
        ArtifactFileRole.CONFIGURATION,
        ArtifactFileRole.DEPENDENCY,
        ArtifactFileRole.PREPROCESSING,
        ArtifactFileRole.METRIC,
        ArtifactFileRole.EXECUTION_SCRIPT,
    }:
        return FileRelevanceStatus.POSSIBLY_RELEVANT, ArtifactConfidence.LOW, evidence
    return FileRelevanceStatus.UNKNOWN, ArtifactConfidence.LOW, evidence


def _expected_roles(experiment: Experiment) -> list[ArtifactFileRole]:
    roles = [
        ArtifactFileRole.EVALUATION,
        ArtifactFileRole.DEPENDENCY,
        ArtifactFileRole.CONFIGURATION,
        ArtifactFileRole.CHECKPOINT,
    ]
    if experiment.model:
        roles.append(ArtifactFileRole.MODEL_DEFINITION)
    if experiment.dataset:
        roles.append(ArtifactFileRole.DATA_PREPARATION)
    return roles


def _readiness(
    files: list[ArtifactFile],
    missing_roles: list[ArtifactFileRole],
    *,
    accessible: bool,
) -> ArtifactReadiness:
    if not accessible:
        return ArtifactReadiness.MISSING
    relevant = sum(item.relevance_status == FileRelevanceStatus.RELEVANT for item in files)
    possible = sum(
        item.relevance_status == FileRelevanceStatus.POSSIBLY_RELEVANT for item in files
    )
    if relevant and not missing_roles:
        return ArtifactReadiness.COMPLETE
    if relevant:
        return ArtifactReadiness.PARTIAL
    if possible:
        return ArtifactReadiness.LIMITED
    return ArtifactReadiness.UNKNOWN


def inspect_artifacts(
    artifacts: list[Artifact],
    analysis: ResearchAnalysis,
    *,
    repository_provider: RepositoryMetadataProvider | None = None,
) -> ArtifactInspectionResult:
    """Map bounded observed repository paths to experiments without execution."""

    provider = repository_provider or PublicRepositoryMetadataProvider()
    metadata_cache: dict[str, RepositoryMetadata] = {}
    artifact_files: list[ArtifactFile] = []
    experiment_maps: list[ExperimentArtifactMap] = []

    for artifact in artifacts:
        if artifact.type != ArtifactType.CODE or not artifact.repository:
            continue
        metadata = metadata_cache.get(artifact.repository)
        if metadata is None:
            try:
                metadata = provider.inspect(artifact.repository)
            except Exception:
                metadata = RepositoryMetadata(
                    canonical_url=artifact.repository,
                    platform=artifact.source or "unknown",
                    owner="",
                    name=artifact.name or artifact.repository.rsplit("/", 1)[-1],
                    accessible=False,
                    notes=["Repository inspection failed."],
                )
            metadata_cache[artifact.repository] = metadata

        # A repository can implement multiple paper experiments even when the
        # nearby paper URL was associated with only one of them in Step 3A.
        # Non-associated mappings survive only when repository evidence creates
        # at least one strong file relationship.
        experiments = analysis.experiments
        observed = metadata.file_tree or [
            RepositoryFileMetadata(path=path) for path in metadata.visible_files
        ]
        unique_paths: list[str] = []
        seen_paths: set[str] = set()
        for entry in observed:
            normalized = entry.path.strip("/")
            key = normalized.casefold()
            if entry.is_directory or not normalized or key in seen_paths:
                continue
            seen_paths.add(key)
            unique_paths.append(normalized)

        for experiment in experiments:
            mapped: list[ArtifactFile] = []
            for path in unique_paths:
                file_type, role = classify_repository_file(path)
                if file_type == ArtifactFileType.OTHER and role == ArtifactFileRole.UNKNOWN:
                    continue
                relevance, confidence, evidence = _classify_relevance(
                    path, role, experiment, artifact, metadata.readme_excerpt
                )
                documented_evidence = " ".join(evidence).casefold()
                if role == ArtifactFileRole.ENTRYPOINT and (
                    "--do_eval" in documented_evidence
                    or "evaluation" in documented_evidence
                ):
                    role = ArtifactFileRole.EVALUATION
                mapped.append(ArtifactFile(
                    file_id="pending",
                    artifact_id=artifact.artifact_id,
                    experiment_id=experiment.id,
                    path=path,
                    file_type=file_type,
                    role=role,
                    relevance_status=relevance,
                    confidence=confidence,
                    evidence=evidence,
                    notes=["Metadata/documentation inspection only; this file was not downloaded or executed."],
                ))

            available_roles = {
                item.role for item in mapped
                if item.relevance_status == FileRelevanceStatus.RELEVANT
            }
            possible_roles = {
                item.role for item in mapped
                if item.relevance_status == FileRelevanceStatus.POSSIBLY_RELEVANT
            }
            if (
                artifact.experiment_id is not None
                and artifact.experiment_id != experiment.id
                and not available_roles
            ):
                continue
            expected = _expected_roles(experiment)
            missing_roles = [
                role for role in expected
                if role not in available_roles and role not in possible_roles
            ]
            unknown_roles = [
                role for role in expected
                if role in possible_roles and role not in available_roles
            ]
            start = len(artifact_files) + 1
            mapped = [
                item.model_copy(update={"file_id": f"FILE-{start + index:03d}"})
                for index, item in enumerate(mapped)
            ]
            artifact_files.extend(mapped)
            notes = list(metadata.notes)
            if not metadata.readme_available:
                notes.append("README evidence was unavailable.")
            if metadata.inspection_partial:
                notes.append("Repository file inspection reached a configured bound.")
            experiment_maps.append(ExperimentArtifactMap(
                experiment_id=experiment.id,
                artifact_id=artifact.artifact_id,
                files=[item.file_id for item in mapped],
                missing_roles=missing_roles,
                unknown_roles=unknown_roles,
                readiness=_readiness(
                    mapped, missing_roles, accessible=metadata.accessible
                ),
                inspection_partial=metadata.inspection_partial,
                notes=list(dict.fromkeys(notes)),
            ))

    return ArtifactInspectionResult(
        files=artifact_files,
        experiment_maps=experiment_maps,
    )
