"""Bounded, deterministic environment reconstruction from Step 3 evidence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.schemas.research import (
    Artifact,
    ArtifactFile,
    ArtifactFileType,
    ArtifactStatus,
    ArtifactType,
    Certainty,
    EnvironmentConfiguration,
    EnvironmentDependency,
    EnvironmentEvidence,
    EnvironmentSpecification,
    EnvironmentStatus,
    EnvironmentVariableRequirement,
    ExperimentArtifactMap,
    FileRelevanceStatus,
    ResearchAnalysis,
)
from app.services.artifacts.provider import RepositoryMetadata
from app.services.artifacts.repository import PublicRepositoryMetadataProvider
from app.services.environment.parsers import (
    extract_env_vars,
    is_secret_variable,
    parse_dockerfile,
    parse_documentation,
    parse_environment_yml,
    parse_lock_file,
    parse_pipfile,
    parse_pyproject_toml_with_diagnostics,
    parse_requirements_txt,
    parse_setup_cfg,
)


FRAMEWORKS = {
    "torch": "PyTorch",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "jax": "JAX",
    "transformers": "Transformers",
    "keras": "Keras",
    "mxnet": "MXNet",
}
ENVIRONMENT_FILE_NAMES = {
    "requirements.txt", "environment.yml", "environment.yaml", "pyproject.toml",
    "pipfile", "pipfile.lock", "poetry.lock", "setup.py", "setup.cfg",
    "dockerfile", "docker-compose.yml", "docker-compose.yaml",
}


@dataclass(slots=True)
class RepositoryEvidence:
    artifact: Artifact
    repository_url: str
    metadata: RepositoryMetadata | None
    files: list[ArtifactFile]
    bounded_file_contents: dict[str, str] = field(default_factory=dict)
    retrieval_status: str = "AVAILABLE"
    retrieval_notes: list[str] = field(default_factory=list)


def _priority(path: str) -> tuple[int, str]:
    name = PurePosixPath(path).name.casefold()
    if name == "requirements.txt":
        rank = 0
    elif name.startswith("requirements") and name.endswith(".txt"):
        rank = 1
    elif name == "environment.yml":
        rank = 2
    elif name == "environment.yaml":
        rank = 3
    elif name == "pyproject.toml":
        rank = 4
    elif name == "pipfile":
        rank = 5
    elif name == "pipfile.lock":
        rank = 6
    elif name == "poetry.lock":
        rank = 7
    elif name == "setup.cfg":
        rank = 8
    elif name == "dockerfile":
        rank = 9
    elif name in {"docker-compose.yml", "docker-compose.yaml"}:
        rank = 10
    elif name == "setup.py":
        rank = 14
    elif name.startswith("readme"):
        rank = 13
    else:
        rank = 12
    return rank, path.casefold()


def collect_repository_evidence(
    artifacts: list[Artifact],
    files: list[ArtifactFile],
    repository_provider: PublicRepositoryMetadataProvider,
) -> dict[str, RepositoryEvidence]:
    """Fetch each prioritized, bounded environment file at most once."""

    files_by_artifact: dict[str, list[ArtifactFile]] = {}
    for item in files:
        files_by_artifact.setdefault(item.artifact_id, []).append(item)

    collected: dict[str, RepositoryEvidence] = {}
    for artifact in artifacts:
        repository_url = artifact.repository or artifact.source_url
        if artifact.type != ArtifactType.CODE or not repository_url:
            continue
        artifact_files = files_by_artifact.get(artifact.artifact_id, [])
        metadata = None
        notes: list[str] = []
        try:
            metadata = repository_provider.inspect(repository_url)
        except Exception:
            notes.append("Repository metadata inspection failed.")
        inaccessible = (
            artifact.availability_status == ArtifactStatus.INACCESSIBLE
            or (metadata is not None and not metadata.accessible)
        )
        evidence = RepositoryEvidence(
            artifact=artifact,
            repository_url=repository_url,
            metadata=metadata,
            files=artifact_files,
            retrieval_status="BLOCKED" if inaccessible else "AVAILABLE",
            retrieval_notes=notes + (list(metadata.notes) if metadata is not None else []),
        )
        seen: set[str] = set()
        prioritized: list[str] = []
        for item in sorted(artifact_files, key=lambda value: _priority(value.path)):
            name = PurePosixPath(item.path).name.casefold()
            if name == "setup.py":
                evidence.retrieval_notes.append(
                    f"Observed but did not fetch untrusted unsupported file: {item.path}"
                )
                continue
            useful = (
                name in ENVIRONMENT_FILE_NAMES
                or (name.startswith("requirements") and name.endswith(".txt"))
                or name.startswith("readme")
                or item.file_type == ArtifactFileType.CONFIG
            )
            key = item.path.casefold()
            if useful and key not in seen:
                seen.add(key)
                prioritized.append(item.path)
        for path in prioritized:
            content = repository_provider.get_file_content(repository_url, path)
            if content is not None:
                evidence.bounded_file_contents[path] = content
            else:
                evidence.retrieval_notes.append(f"Content unavailable: {path}")
        collected[artifact.artifact_id] = evidence
    return collected


def _environment_id(artifact_id: str, experiment_id: str | None) -> str:
    key = f"{artifact_id}:{experiment_id or 'global'}"
    return f"ENV-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16].upper()}"


def _normalized(value: str) -> str:
    return value.casefold().strip().lstrip("=<>~^! ")


def _resolve(
    category: str,
    evidence: list[EnvironmentEvidence],
    conflicts: list[EnvironmentEvidence],
) -> str | None:
    candidates = [item for item in evidence if item.category == category and item.value]
    unique = {_normalized(item.value) for item in candidates}
    if len(unique) > 1:
        conflicts.extend(candidates)
        return None
    return candidates[0].value if candidates else None


def _deduplicate_dependencies(
    dependencies: list[EnvironmentDependency],
    conflicts: list[EnvironmentEvidence],
) -> list[EnvironmentDependency]:
    result: list[EnvironmentDependency] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    by_name: dict[str, list[EnvironmentDependency]] = {}
    for dependency in dependencies:
        key = (
            dependency.name.casefold(),
            dependency.version_constraint,
            dependency.source_path,
        )
        if key not in seen:
            result.append(dependency)
            seen.add(key)
        by_name.setdefault(dependency.name.casefold(), []).append(dependency)
    for name, items in by_name.items():
        constraints = {
            _normalized(item.version_constraint)
            for item in items
            if item.version_constraint
        }
        if len(constraints) > 1:
            conflicts.extend(EnvironmentEvidence(
                category=f"dependency:{name}",
                value=item.version_constraint or "unversioned",
                source_path=item.source_path or "unknown",
                evidence=item.evidence or item.name,
                certainty=item.certainty,
            ) for item in items)
    return result


def _variable(name: str, path: str, origin: str) -> EnvironmentVariableRequirement:
    return EnvironmentVariableRequirement(
        name=name,
        required=True,
        secret=is_secret_variable(name),
        source_path=path,
        evidence=f"{origin} {name}",
        notes="Only the variable name was retained; assignment values were discarded.",
    )


def _reconstruct_scope(
    repository: RepositoryEvidence,
    paths: list[str],
    experiment_id: str | None,
) -> EnvironmentSpecification:
    dependencies: list[EnvironmentDependency] = []
    environment_evidence: list[EnvironmentEvidence] = []
    variables: list[EnvironmentVariableRequirement] = []
    configurations: list[EnvironmentConfiguration] = []
    system_dependencies: list[str] = []
    commands: list[str] = []
    notes = list(dict.fromkeys(repository.retrieval_notes))

    for path in paths:
        content = repository.bounded_file_contents.get(path)
        if content is None:
            continue
        name = PurePosixPath(path).name.casefold()
        if name.startswith("requirements") and name.endswith(".txt"):
            dependencies.extend(parse_requirements_txt(content, path))
        elif name in {"environment.yml", "environment.yaml"}:
            dependencies.extend(parse_environment_yml(content, path))
        elif name == "pyproject.toml":
            parsed, diagnostics = parse_pyproject_toml_with_diagnostics(content, path)
            dependencies.extend(parsed)
            notes.extend(diagnostics)
        elif name == "pipfile":
            parsed, diagnostics = parse_pipfile(content, path)
            dependencies.extend(parsed)
            notes.extend(diagnostics)
        elif name in {"pipfile.lock", "poetry.lock"}:
            parsed, diagnostics = parse_lock_file(content, path)
            dependencies.extend(parsed)
            notes.extend(diagnostics)
        elif name == "setup.cfg":
            parsed, diagnostics = parse_setup_cfg(content, path)
            dependencies.extend(parsed)
            notes.extend(diagnostics)
        elif name == "dockerfile":
            docker = parse_dockerfile(content, path)
            environment_evidence.extend(docker.evidence)
            if docker.operating_system:
                environment_evidence.append(EnvironmentEvidence(
                    category="operating_system", value=docker.operating_system,
                    source_path=path, evidence=f"FROM {docker.base_image}", certainty=Certainty.EXPLICIT,
                ))
            if docker.operating_system_version:
                environment_evidence.append(EnvironmentEvidence(
                    category="operating_system_version", value=docker.operating_system_version,
                    source_path=path, evidence=f"FROM {docker.base_image}", certainty=Certainty.EXPLICIT,
                ))
            if docker.python_version:
                environment_evidence.append(EnvironmentEvidence(
                    category="python", value=docker.python_version, source_path=path,
                    evidence=f"FROM {docker.base_image}", certainty=Certainty.EXPLICIT,
                ))
            if docker.cuda_version:
                environment_evidence.append(EnvironmentEvidence(
                    category="cuda", value=docker.cuda_version, source_path=path,
                    evidence=f"FROM {docker.base_image}", certainty=Certainty.EXPLICIT,
                ))
            if docker.cudnn_version:
                environment_evidence.append(EnvironmentEvidence(
                    category="cudnn", value=docker.cudnn_version, source_path=path,
                    evidence=f"FROM {docker.base_image}", certainty=Certainty.EXPLICIT,
                ))
            system_dependencies.extend(docker.system_dependencies)
            commands.extend(docker.commands)
            variables.extend(_variable(item, path, "ENV/ARG") for item in docker.environment_variables)
        elif name.startswith("readme") or PurePosixPath(path).suffix.casefold() in {".md", ".rst"}:
            documentation = parse_documentation(content, path)
            environment_evidence.extend(documentation.evidence)
            commands.extend(documentation.commands)
            system_dependencies.extend(documentation.system_dependencies)
            variables.extend(_variable(item, path, "export") for item in documentation.environment_variables)
        elif name == "setup.py":
            notes.append(f"Observed but unsupported dependency format: {path}")

        matching_file = next(
            (item for item in repository.files if item.path.casefold() == path.casefold()),
            None,
        )
        if matching_file is not None and matching_file.file_type == ArtifactFileType.CONFIG:
            configuration_evidence = parse_documentation(content, path)
            environment_evidence.extend(configuration_evidence.evidence)
            variables.extend(
                _variable(item, path, "configuration variable")
                for item in configuration_evidence.environment_variables
            )
            configurations.append(EnvironmentConfiguration(
                path=path,
                type=PurePosixPath(path).suffix.lstrip(".").upper() or "CONFIG",
                experiment_id=experiment_id,
                purpose="Observed repository configuration",
                evidence=f"Observed bounded repository path: {path}",
                relevance_status=matching_file.relevance_status.value,
            ))

    for dependency in dependencies:
        lower = dependency.name.casefold()
        category = None
        if lower == "python":
            category = "python_constraint"
        elif lower in {"cuda", "cudatoolkit", "nvidia-cuda-runtime-cu11", "nvidia-cuda-runtime-cu12"}:
            category = "cuda"
        elif "cudnn" in lower:
            category = "cudnn"
        if category and dependency.version_constraint:
            environment_evidence.append(EnvironmentEvidence(
                category=category,
                value=dependency.version_constraint,
                source_path=dependency.source_path or "unknown",
                evidence=dependency.evidence or dependency.name,
                certainty=dependency.certainty,
            ))
        if lower in FRAMEWORKS and dependency.version_constraint:
            environment_evidence.append(EnvironmentEvidence(
                category=f"framework:{FRAMEWORKS[lower]}",
                value=dependency.version_constraint,
                source_path=dependency.source_path or "unknown",
                evidence=dependency.evidence or dependency.name,
                certainty=dependency.certainty,
            ))

    conflicts: list[EnvironmentEvidence] = []
    dependencies = _deduplicate_dependencies(dependencies, conflicts)
    variables = list({(item.name, item.source_path): item for item in variables}.values())
    frameworks = list(dict.fromkeys(
        FRAMEWORKS[item.name.casefold()]
        for item in dependencies
        if item.name.casefold() in FRAMEWORKS
    ))

    scalar_categories = {
        "operating_system": "operating_system",
        "operating_system_version": "operating_system_version",
        "python_version": "python",
        "python_constraint": "python_constraint",
        "cuda_version": "cuda",
        "cudnn_version": "cudnn",
        "gpu": "gpu",
        "gpu_memory": "gpu_memory",
        "cpu": "cpu",
        "memory": "memory",
        "storage": "storage",
        "container": "container",
    }
    values = {
        field_name: _resolve(category, environment_evidence, conflicts)
        for field_name, category in scalar_categories.items()
    }
    conflict_keys = {
        (item.category, item.value, item.source_path, item.evidence)
        for item in conflicts
    }
    conflicts = [
        EnvironmentEvidence(
            category=category, value=value, source_path=source_path,
            evidence=evidence, certainty=next(
                item.certainty for item in conflicts
                if (item.category, item.value, item.source_path, item.evidence)
                == (category, value, source_path, evidence)
            ),
        )
        for category, value, source_path, evidence in sorted(conflict_keys)
    ]

    meaningful = bool(
        dependencies or variables or configurations or system_dependencies or commands
        or environment_evidence
    )
    blocked = repository.retrieval_status == "BLOCKED" and not meaningful
    missing: list[str] = []
    if not (values["python_version"] or values["python_constraint"]):
        missing.append("Python version or constraint")
    if not dependencies:
        missing.append("Package dependencies")
    if not (values["operating_system"] or values["container"]):
        missing.append("Operating system or container base image")
    if blocked:
        status = EnvironmentStatus.BLOCKED
        confidence = "LOW"
    elif not meaningful:
        status = EnvironmentStatus.UNKNOWN
        confidence = "LOW"
    elif not missing and not conflicts:
        status = EnvironmentStatus.RECONSTRUCTED
        confidence = "HIGH"
    else:
        status = EnvironmentStatus.PARTIALLY_RECONSTRUCTED
        confidence = "MEDIUM" if not conflicts else "LOW"

    return EnvironmentSpecification(
        environment_id=_environment_id(repository.artifact.artifact_id, experiment_id),
        experiment_id=experiment_id,
        artifact_id=repository.artifact.artifact_id,
        status=status,
        frameworks=frameworks,
        dependencies=dependencies,
        environment_variables=variables,
        configuration_files=configurations,
        documented_commands=list(dict.fromkeys(commands)),
        system_dependencies=list(dict.fromkeys(system_dependencies)),
        evidence=environment_evidence,
        confidence=confidence,
        notes=list(dict.fromkeys(notes)),
        missing_information=missing,
        conflict_detected=bool(conflicts),
        conflicting_evidence=conflicts,
        **values,
    )


def reconstruct_environments(
    analysis: ResearchAnalysis,
    artifacts: list[Artifact],
    files: list[ArtifactFile],
    experiment_maps: list[ExperimentArtifactMap],
    repository_provider: PublicRepositoryMetadataProvider,
    paper_text: str,
) -> list[EnvironmentSpecification]:
    """Reconstruct shared and clearly experiment-specific environments."""

    del analysis, paper_text  # Step 4 consumes bounded Step 3 evidence only.
    repository_evidence = collect_repository_evidence(artifacts, files, repository_provider)
    environments: list[EnvironmentSpecification] = []
    mapped_experiments = {
        (item.artifact_id, item.experiment_id)
        for item in experiment_maps
    }
    for artifact_id, repository in repository_evidence.items():
        all_paths = list(repository.bounded_file_contents)
        global_paths: list[str] = []
        experiment_paths: dict[str, list[str]] = {}
        files_by_path: dict[str, list[ArtifactFile]] = {}
        for item in repository.files:
            files_by_path.setdefault(item.path.casefold(), []).append(item)
        for path in all_paths:
            entries = files_by_path.get(path.casefold(), [])
            specific = {
                item.experiment_id for item in entries
                if item.relevance_status == FileRelevanceStatus.RELEVANT
                and (artifact_id, item.experiment_id) in mapped_experiments
                and "/" in path
                and PurePosixPath(path).name.casefold() not in ENVIRONMENT_FILE_NAMES
            }
            if len(specific) == 1:
                experiment_paths.setdefault(next(iter(specific)), []).append(path)
            else:
                global_paths.append(path)
        if global_paths or not experiment_paths:
            environments.append(_reconstruct_scope(repository, global_paths, None))
        for experiment_id, paths in sorted(experiment_paths.items()):
            environments.append(_reconstruct_scope(repository, paths, experiment_id))
    return environments
