"""Environment reconstruction, evidence, status, and isolation tests."""

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
    EnvironmentStatus,
    ExperimentArtifactMap,
    FileRelevanceStatus,
    PaperMetadata,
    ResearchAnalysis,
)
from app.services.artifacts.provider import RepositoryFileMetadata, RepositoryMetadata
from app.services.environment.reconstruction import reconstruct_environments


URL = "https://github.com/example/repository"


class StubRepositoryProvider:
    def __init__(self, contents: dict[str, str], *, accessible: bool = True) -> None:
        self.contents = contents
        self.content_calls: list[str] = []
        self.inspect_calls = 0
        self.metadata = RepositoryMetadata(
            canonical_url=URL,
            platform="github",
            owner="example",
            name="repository",
            accessible=accessible,
            default_branch="main",
            file_tree=[RepositoryFileMetadata(path) for path in contents],
            readme_excerpt=contents.get("README.md"),
            readme_available="README.md" in contents,
        )

    def inspect(self, _url: str) -> RepositoryMetadata:
        self.inspect_calls += 1
        return self.metadata

    def get_file_content(self, _url: str, path: str) -> str | None:
        self.content_calls.append(path)
        return self.contents.get(path)


def artifact(*, accessible: bool = True) -> Artifact:
    return Artifact(
        artifact_id="ART-001",
        type=ArtifactType.CODE,
        name="repository",
        source="github",
        source_url=URL,
        repository=URL,
        discovery_method=ArtifactDiscoveryMethod.PAPER_URL,
        relationship_status=ArtifactStatus.FOUND,
        availability_status=ArtifactStatus.FOUND if accessible else ArtifactStatus.INACCESSIBLE,
        confidence=ArtifactConfidence.HIGH,
    )


def repository_file(
    path: str,
    *,
    experiment_id: str = "EXP-001",
    relevance: FileRelevanceStatus = FileRelevanceStatus.RELEVANT,
) -> ArtifactFile:
    name = path.rsplit("/", 1)[-1].casefold()
    if name.startswith("requirements") or name in {
        "environment.yml", "environment.yaml", "pyproject.toml", "pipfile", "setup.cfg"
    }:
        file_type, role = ArtifactFileType.DEPENDENCY, ArtifactFileRole.DEPENDENCY
    elif name == "dockerfile":
        file_type, role = ArtifactFileType.CONTAINER, ArtifactFileRole.CONFIGURATION
    elif name.startswith("readme"):
        file_type, role = ArtifactFileType.DOCUMENTATION, ArtifactFileRole.DOCUMENTATION
    else:
        file_type, role = ArtifactFileType.CONFIG, ArtifactFileRole.CONFIGURATION
    return ArtifactFile(
        file_id=f"FILE-{path}",
        artifact_id="ART-001",
        experiment_id=experiment_id,
        path=path,
        file_type=file_type,
        role=role,
        relevance_status=relevance,
        confidence=ArtifactConfidence.HIGH,
    )


def mapping(experiment_id: str = "EXP-001") -> ExperimentArtifactMap:
    return ExperimentArtifactMap(
        experiment_id=experiment_id,
        artifact_id="ART-001",
        readiness=ArtifactReadiness.PARTIAL,
    )


def reconstruct(contents, paths, *, accessible=True, maps=None):
    provider = StubRepositoryProvider(contents, accessible=accessible)
    result = reconstruct_environments(
        ResearchAnalysis(paper=PaperMetadata(title="Test")),
        [artifact(accessible=accessible)],
        paths,
        maps or [mapping()],
        provider,
        "paper text",
    )
    return result, provider


def test_torch_does_not_imply_gpu_and_secret_values_are_not_retained() -> None:
    environments, _ = reconstruct(
        {
            "requirements.txt": "torch==2.1\ntransformers==4.40",
            "README.md": "export DATABASE_PASSWORD=never-return-this",
        },
        [repository_file("requirements.txt"), repository_file("README.md")],
    )

    environment = environments[0]
    assert environment.gpu is None
    assert environment.frameworks == ["PyTorch", "Transformers"]
    assert environment.environment_variables[0].name == "DATABASE_PASSWORD"
    assert environment.environment_variables[0].secret is True
    assert "never-return-this" not in environment.model_dump_json()


def test_bare_environment_assignment_values_are_never_serialized() -> None:
    environments, _ = reconstruct(
        {
            "config.env": (
                "API_KEY=abc123\nDATABASE_PASSWORD=supersecret\n"
                "TOKEN=secret123\nNORMAL_SETTING=value"
            ),
        },
        [repository_file("config.env")],
    )

    environment = environments[0]
    assert [(item.name, item.secret) for item in environment.environment_variables] == [
        ("API_KEY", True),
        ("DATABASE_PASSWORD", True),
        ("TOKEN", True),
        ("NORMAL_SETTING", False),
    ]
    serialized = environment.model_dump_json()
    assert all(value not in serialized for value in ("abc123", "supersecret", "secret123"))


def test_conflicting_python_and_dependency_versions_are_preserved() -> None:
    environments, _ = reconstruct(
        {
            "requirements.txt": "python==3.8\ntorch==2.0.0",
            "environment.yml": "dependencies:\n  - python=3.10\n  - torch=2.1.0",
        },
        [repository_file("requirements.txt"), repository_file("environment.yml")],
    )

    environment = environments[0]
    assert environment.python_version is None
    assert environment.conflict_detected is True
    assert {(item.name, item.version_constraint) for item in environment.dependencies} >= {
        ("python", "==3.8"), ("python", "==3.10"),
        ("torch", "==2.0.0"), ("torch", "==2.1.0"),
    }
    assert {item.source_path for item in environment.conflicting_evidence} == {
        "requirements.txt", "environment.yml"
    }


def test_all_four_statuses_are_reachable() -> None:
    reconstructed, _ = reconstruct(
        {
            "requirements.txt": "python==3.11\nnumpy==1.26",
            "Dockerfile": "FROM python:3.11-slim\nRUN apt-get install -y git",
        },
        [repository_file("requirements.txt"), repository_file("Dockerfile")],
    )
    partial, _ = reconstruct(
        {"requirements.txt": "numpy==1.26"}, [repository_file("requirements.txt")]
    )
    blocked, _ = reconstruct({}, [], accessible=False, maps=[])
    unknown, _ = reconstruct({}, [], maps=[])

    assert reconstructed[0].status == EnvironmentStatus.RECONSTRUCTED
    assert partial[0].status == EnvironmentStatus.PARTIALLY_RECONSTRUCTED
    assert blocked[0].status == EnvironmentStatus.BLOCKED
    assert unknown[0].status == EnvironmentStatus.UNKNOWN


def test_python_version_or_constraint_each_satisfies_completeness() -> None:
    version_environment, _ = reconstruct(
        {
            "requirements.txt": "numpy==1.26",
            "Dockerfile": "FROM python:3.11-slim",
        },
        [repository_file("requirements.txt"), repository_file("Dockerfile")],
    )
    constraint_environment, _ = reconstruct(
        {
            "requirements.txt": "python>=3.10\nnumpy==1.26",
            "Dockerfile": "FROM ubuntu:22.04",
        },
        [repository_file("requirements.txt"), repository_file("Dockerfile")],
    )

    assert version_environment[0].python_version == "3.11"
    assert version_environment[0].python_constraint is None
    assert version_environment[0].status == EnvironmentStatus.RECONSTRUCTED
    assert constraint_environment[0].python_version is None
    assert constraint_environment[0].python_constraint == ">=3.10"
    assert constraint_environment[0].status == EnvironmentStatus.RECONSTRUCTED


def test_supported_files_are_not_starved_by_untrusted_setup_py() -> None:
    contents = {
        "environment.yml": "dependencies:\n  - numpy=1.26",
        "pyproject.toml": '[project]\ndependencies = ["requests>=2"]',
        "setup.cfg": "[options]\ninstall_requires =\n  flask>=3",
        "Dockerfile": "FROM python:3.11-slim",
        "setup.py": "raise RuntimeError('must never execute')",
    }

    class FourRequestProvider(StubRepositoryProvider):
        def get_file_content(self, _url: str, path: str) -> str | None:
            if len(self.content_calls) >= 4:
                return None
            self.content_calls.append(path)
            return self.contents.get(path)

    provider = FourRequestProvider(contents)
    environment = reconstruct_environments(
        ResearchAnalysis(paper=PaperMetadata(title="Test")),
        [artifact()],
        [repository_file(path) for path in contents],
        [mapping()],
        provider,
        "paper text",
    )[0]

    assert provider.content_calls == [
        "environment.yml", "pyproject.toml", "setup.cfg", "Dockerfile"
    ]
    assert {item.name for item in environment.dependencies} >= {"numpy", "requests", "flask"}
    assert "setup.py" not in provider.content_calls
    assert any("did not fetch" in note and "setup.py" in note for note in environment.notes)


def test_explicit_cuda_and_gpu_are_evidence_backed() -> None:
    environments, _ = reconstruct(
        {
            "README.md": "Requires CUDA 12.1 and an NVIDIA V100 GPU.",
        },
        [repository_file("README.md")],
    )

    environment = environments[0]
    assert environment.cuda_version == "12.1"
    assert environment.gpu == "NVIDIA V100"
    assert {item.source_path for item in environment.evidence if item.category in {"cuda", "gpu"}} == {"README.md"}


def test_repository_level_files_create_one_global_environment_and_are_read_once() -> None:
    files = [
        repository_file("requirements.txt", experiment_id="EXP-A"),
        repository_file("requirements.txt", experiment_id="EXP-B"),
        repository_file("README.md", experiment_id="EXP-A"),
        repository_file("README.md", experiment_id="EXP-B"),
    ]
    environments, provider = reconstruct(
        {"requirements.txt": "python==3.11\nnumpy", "README.md": "Python 3.11"},
        files,
        maps=[mapping("EXP-A"), mapping("EXP-B")],
    )

    assert len(environments) == 1
    assert environments[0].experiment_id is None
    assert provider.content_calls == ["requirements.txt", "README.md"]


def test_relevant_nested_configuration_is_experiment_specific() -> None:
    environments, _ = reconstruct(
        {"configs/squad.yaml": "accelerator: gpu\nPython 3.10"},
        [repository_file("configs/squad.yaml", experiment_id="EXP-SQUAD")],
        maps=[mapping("EXP-SQUAD")],
    )

    assert len(environments) == 1
    assert environments[0].experiment_id == "EXP-SQUAD"
    assert environments[0].gpu == "GPU configuration: gpu"
    assert environments[0].configuration_files[0].path == "configs/squad.yaml"


def test_environment_ids_are_deterministic() -> None:
    first, _ = reconstruct(
        {"requirements.txt": "numpy"}, [repository_file("requirements.txt")]
    )
    second, _ = reconstruct(
        {"requirements.txt": "numpy"}, [repository_file("requirements.txt")]
    )

    assert first[0].environment_id == second[0].environment_id == "ENV-031AFD80D75255DB"
