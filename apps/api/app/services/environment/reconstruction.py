import logging
import uuid
from typing import Any

from app.schemas.research import (
    Artifact,
    ArtifactFile,
    ArtifactFileType,
    Certainty,
    DependencyType,
    EnvironmentConfiguration,
    EnvironmentDependency,
    EnvironmentSpecification,
    EnvironmentStatus,
    EnvironmentVariableRequirement,
    ExperimentArtifactMap,
    ResearchAnalysis,
)
from app.services.artifacts.repository import PublicRepositoryMetadataProvider
from app.services.environment.parsers import (
    extract_env_vars,
    parse_dockerfile_system_deps,
    parse_environment_yml,
    parse_pyproject_toml,
    parse_requirements_txt,
)

logger = logging.getLogger(__name__)


def _extract_frameworks(dependencies: list[EnvironmentDependency]) -> list[str]:
    frameworks = []
    framework_pkgs = {"torch": "PyTorch", "tensorflow": "TensorFlow", "jax": "JAX", "transformers": "Transformers"}
    for dep in dependencies:
        if dep.name.lower() in framework_pkgs:
            frameworks.append(framework_pkgs[dep.name.lower()])
    return list(set(frameworks))


def reconstruct_environments(
    analysis: ResearchAnalysis,
    artifacts: list[Artifact],
    files: list[ArtifactFile],
    experiment_maps: list[ExperimentArtifactMap],
    repository_provider: PublicRepositoryMetadataProvider,
    paper_text: str,
) -> list[EnvironmentSpecification]:
    """Reconstruct environment specifications from artifacts without execution."""
    environments: list[EnvironmentSpecification] = []
    
    # Map files by artifact
    files_by_artifact = {}
    for f in files:
        files_by_artifact.setdefault(f.artifact_id, []).append(f)
        
    for artifact in artifacts:
        if not artifact.source_url:
            continue
            
        repo_files = files_by_artifact.get(artifact.artifact_id, [])
        
        # We need to construct environment specific to experiment mappings
        artifact_experiments = [m.experiment_id for m in experiment_maps if m.artifact_id == artifact.artifact_id]
        if not artifact_experiments:
            artifact_experiments = [None] # global artifact environment
            
        for exp_id in artifact_experiments:
            env_spec = EnvironmentSpecification(
                environment_id=str(uuid.uuid4()),
                experiment_id=exp_id,
                artifact_id=artifact.artifact_id,
                status=EnvironmentStatus.UNKNOWN,
            )
            
            # 1. Parse dependencies from config files
            dependencies = []
            configurations = []
            env_vars = []
            system_deps = []
            
            for f in repo_files:
                # Need to read the file content from provider
                content = repository_provider.get_file_content(artifact.source_url, f.path)
                if not content:
                    continue
                    
                if f.file_type == ArtifactFileType.DEPENDENCY:
                    if f.path.endswith("requirements.txt") or f.path.endswith("requirements-dev.txt"):
                        dependencies.extend(parse_requirements_txt(content, f.path))
                    elif f.path.endswith("environment.yml") or f.path.endswith("environment.yaml"):
                        dependencies.extend(parse_environment_yml(content, f.path))
                    elif f.path.endswith("pyproject.toml"):
                        dependencies.extend(parse_pyproject_toml(content, f.path))
                elif f.file_type == ArtifactFileType.CONTAINER:
                    system_deps.extend(parse_dockerfile_system_deps(content))
                    extracted_vars = extract_env_vars(content)
                    for var in extracted_vars:
                        env_vars.append(EnvironmentVariableRequirement(
                            name=var, required=True, secret="KEY" in var or "TOKEN" in var or "SECRET" in var,
                            source_path=f.path, evidence=f"ENV {var}", notes="Extracted from Dockerfile"
                        ))
                elif f.file_type == ArtifactFileType.CONFIG:
                    configurations.append(EnvironmentConfiguration(
                        path=f.path, type=f.path.split(".")[-1].upper(), experiment_id=exp_id,
                        purpose="Unknown config", evidence="Found in repo", relevance_status="POSSIBLY_RELEVANT"
                    ))
                elif f.file_type == ArtifactFileType.DOCUMENTATION and "readme" in f.path.lower():
                    # Extract any env vars shown in README
                    extracted_vars = extract_env_vars(content)
                    for var in extracted_vars:
                        # Avoid duplicates
                        if not any(v.name == var for v in env_vars):
                            env_vars.append(EnvironmentVariableRequirement(
                                name=var, required=True, secret="KEY" in var or "TOKEN" in var or "SECRET" in var,
                                source_path=f.path, evidence=f"export {var}", notes="Extracted from README"
                            ))
                            
            # Process dependencies to deduce frameworks, python, cuda
            frameworks = _extract_frameworks(dependencies)
            
            python_version = None
            python_constraint = None
            cuda_version = None
            gpu_required = None
            
            # Deduplicate dependencies
            unique_deps = {}
            for d in dependencies:
                if d.name not in unique_deps:
                    unique_deps[d.name] = d
            dependencies = list(unique_deps.values())
            
            for dep in dependencies:
                if dep.name.lower() == "python":
                    python_version = dep.version_constraint
                    python_constraint = dep.version_constraint
                elif "cuda" in dep.name.lower():
                    cuda_version = dep.version_constraint or "Required"
                    
            if "torch" in [d.name.lower() for d in dependencies]:
                gpu_required = "REPORTED" # heuristic
                
            env_spec.dependencies = dependencies
            env_spec.frameworks = frameworks
            env_spec.python_version = python_version
            env_spec.python_constraint = python_constraint
            env_spec.cuda_version = cuda_version
            if gpu_required:
                env_spec.gpu = gpu_required
            env_spec.environment_variables = env_vars
            env_spec.configuration_files = configurations
            env_spec.system_dependencies = system_deps
            
            if dependencies or system_deps or configurations or env_vars:
                env_spec.status = EnvironmentStatus.PARTIALLY_RECONSTRUCTED
            
            environments.append(env_spec)
            
    return environments
