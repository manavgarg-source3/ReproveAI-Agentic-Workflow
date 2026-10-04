"""Step 3A artifact discovery tests with no live repository access."""

import pytest
from pydantic import ValidationError

from app.schemas.research import (
    Artifact,
    ArtifactStatus,
    ArtifactType,
    Experiment,
    PaperMetadata,
    ResearchAnalysis,
)
from app.services.artifacts.discovery import discover_artifacts
from app.services.artifacts.provider import RepositoryMetadata
from app.services.artifacts.repository import normalize_repository_url, parse_repository_url


def analysis(*, experiments=None) -> ResearchAnalysis:
    return ResearchAnalysis(
        paper=PaperMetadata(
            title="Example Paper",
            authors=["Ada Researcher"],
            year=2026,
        ),
        experiments=experiments or [],
    )


class StubRepositories:
    def __init__(self, records=None, failures=None):
        self.records = records or {}
        self.failures = failures or set()
        self.calls = []

    def inspect(self, url):
        self.calls.append(url)
        if url in self.failures:
            raise TimeoutError("private provider timeout detail")
        return self.records.get(url, RepositoryMetadata(
            canonical_url=url,
            platform="github" if "github" in url else "gitlab",
            owner="example",
            name=url.rsplit("/", 1)[-1],
            accessible=True,
            description="Research software",
        ))


def repository_record(url, *, platform="github", accessible=True, files=None, readme=None):
    return RepositoryMetadata(
        canonical_url=url,
        platform=platform,
        owner="example",
        name=url.rsplit("/", 1)[-1],
        accessible=accessible,
        description="Official implementation for Example Paper",
        default_branch="main",
        latest_commit="abc123",
        readme_excerpt=readme or "Example Paper by Ada Researcher",
        visible_files=files or [],
        license_name="MIT",
    )


def test_explicit_github_repository_url_is_discovered_and_verified() -> None:
    url = "https://github.com/example/research-model"
    artifacts = discover_artifacts(
        f"Our official implementation is available at {url}.",
        analysis(),
        repository_provider=StubRepositories({url: repository_record(url)}),
    )
    repo = next(item for item in artifacts if item.type == ArtifactType.CODE)
    assert repo.source == "github"
    assert repo.source_url == url
    assert repo.relationship_status == ArtifactStatus.VERIFIED
    assert repo.commit == "abc123"


def test_bert_repository_split_across_pdf_lines_remains_a_code_candidate() -> None:
    url = "https://github.com/google-research/bert"
    inaccessible = RepositoryMetadata(
        canonical_url=url,
        platform="github",
        owner="google-research",
        name="bert",
        accessible=False,
        notes=["Public repository metadata could not be retrieved."],
    )
    paper_text = (
        "1 Introduction\n"
        "BERT advances the state of the art for eleven NLP tasks. The code and "
        "pre-trained mod-\nels are available at https://github.com/\n"
        "google-research/bert.\n2 Related Work\n"
    )

    artifacts = discover_artifacts(
        paper_text,
        ResearchAnalysis(
            paper=PaperMetadata(
                title="BERT: Pre-training of Deep Bidirectional Transformers for "
                "Language Understanding"
            )
        ),
        repository_provider=StubRepositories({url: inaccessible}),
    )

    repository = next(item for item in artifacts if item.source_url == url)
    assert repository.type == ArtifactType.CODE
    assert repository.repository == url
    assert repository.evidence_location == "1 Introduction"
    assert repository.discovery_method.value == "PAPER_URL"
    assert repository.relationship_status == ArtifactStatus.PARTIAL
    assert repository.availability_status == ArtifactStatus.INACCESSIBLE


def test_explicit_gitlab_repository_url_is_supported() -> None:
    url = "https://gitlab.com/example/research-model"
    artifacts = discover_artifacts(
        f"Code is available at {url}.",
        analysis(),
        repository_provider=StubRepositories({url: repository_record(url, platform="gitlab")}),
    )
    assert artifacts[0].source == "gitlab"
    assert artifacts[0].source_url == url


@pytest.mark.parametrize(
    "raw",
    [
        "https://github.com/example/research-model/",
        "https://github.com/example/research-model.git",
        "http://github.com/example/research-model",
    ],
)
def test_repository_url_normalization(raw) -> None:
    assert normalize_repository_url(raw) == "https://github.com/example/research-model"


def test_duplicate_repository_references_cause_one_artifact_and_lookup() -> None:
    url = "https://github.com/example/research-model"
    provider = StubRepositories({url: repository_record(url)})
    artifacts = discover_artifacts(
        f"Code: {url}/ and mirror link {url}.git",
        analysis(),
        repository_provider=provider,
    )
    assert len([item for item in artifacts if item.type == ArtifactType.CODE]) == 1
    assert provider.calls == [url]


def test_dataset_url_discovery() -> None:
    artifacts = discover_artifacts(
        "The dataset is available at https://example.org/datasets/example-v1.",
        analysis(),
        repository_provider=StubRepositories(),
    )
    assert artifacts[0].type == ArtifactType.DATASET
    assert artifacts[0].source_url == "https://example.org/datasets/example-v1"


def test_checkpoint_link_discovery() -> None:
    artifacts = discover_artifacts(
        "Download the checkpoint from https://models.example.org/model.ckpt.",
        analysis(),
        repository_provider=StubRepositories(),
    )
    assert artifacts[0].type == ArtifactType.CHECKPOINT
    assert artifacts[0].availability_status == ArtifactStatus.FOUND


def test_repository_file_listing_detects_dependency_config_container_and_script() -> None:
    url = "https://github.com/example/research-model"
    files = ["requirements.txt", "experiment.yaml", "Dockerfile", "train.py", "README.md"]
    artifacts = discover_artifacts(
        f"Our official implementation: {url}",
        analysis(),
        repository_provider=StubRepositories({url: repository_record(url, files=files)}),
    )
    types = {item.type for item in artifacts}
    assert {ArtifactType.DEPENDENCY, ArtifactType.CONFIG, ArtifactType.CONTAINER, ArtifactType.EXECUTION_SCRIPT} <= types
    assert all("not downloaded or executed" in " ".join(item.notes) for item in artifacts if item.type in types - {ArtifactType.CODE})


def test_supplementary_link_detection() -> None:
    artifacts = discover_artifacts(
        "Supplementary material: https://example.org/paper/supplement.pdf",
        analysis(),
        repository_provider=StubRepositories(),
    )
    assert artifacts[0].type == ArtifactType.SUPPLEMENTARY
    assert artifacts[0].discovery_method.value == "SUPPLEMENTARY_LINK"


def test_artifact_is_associated_with_matching_experiment() -> None:
    experiment = Experiment(
        id="EXP-003",
        objective="Evaluate Model-X on Dataset-Y",
        dataset="Dataset-Y",
        model="Model-X",
        metric="F1",
    )
    artifacts = discover_artifacts(
        "Model-X code for Dataset-Y is available at https://github.com/example/model-x.",
        analysis(experiments=[experiment]),
        repository_provider=StubRepositories(),
    )
    repo = next(item for item in artifacts if item.type == ArtifactType.CODE)
    assert repo.experiment_id == "EXP-003"


def test_ambiguous_repository_relationship_remains_explicit() -> None:
    url = "https://github.com/example/mirror"
    artifacts = discover_artifacts(
        f"A possible unofficial related repository is {url}.",
        analysis(),
        repository_provider=StubRepositories({url: repository_record(url, readme="Unrelated utilities")}),
    )
    assert artifacts[0].relationship_status == ArtifactStatus.AMBIGUOUS
    assert artifacts[0].confidence.value == "LOW"


def test_inaccessible_repository_is_returned_not_dropped() -> None:
    url = "https://github.com/example/private-now"
    record = repository_record(url, accessible=False)
    artifacts = discover_artifacts(
        f"Code is available at {url}.",
        analysis(),
        repository_provider=StubRepositories({url: record}),
    )
    assert artifacts[0].availability_status == ArtifactStatus.INACCESSIBLE


def test_missing_dataset_and_model_are_reported_for_experiment() -> None:
    experiment = Experiment(
        id="EXP-001",
        objective="Evaluate a transformer",
        dataset="Dataset-Y",
        model="Model-X",
    )
    artifacts = discover_artifacts("No public artifact links are present.", analysis(experiments=[experiment]))
    assert {(item.type, item.availability_status) for item in artifacts} == {
        (ArtifactType.DATASET, ArtifactStatus.MISSING),
        (ArtifactType.MODEL, ArtifactStatus.MISSING),
    }
    assert all(item.experiment_id == "EXP-001" for item in artifacts)


def test_per_artifact_provider_failure_is_isolated() -> None:
    first = "https://github.com/example/working"
    second = "https://gitlab.com/example/unavailable"
    provider = StubRepositories(
        {first: repository_record(first)},
        failures={second},
    )
    artifacts = discover_artifacts(
        f"Code repositories: {first} and {second}.",
        analysis(),
        repository_provider=provider,
    )
    by_url = {item.source_url: item for item in artifacts}
    assert by_url[first].availability_status == ArtifactStatus.FOUND
    assert by_url[second].availability_status == ArtifactStatus.INACCESSIBLE
    assert "private" not in " ".join(by_url[second].notes)


def test_artifact_schema_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        Artifact.model_validate({
            "artifact_id": "ART-001",
            "type": "CODE",
            "discovery_method": "PAPER_URL",
            "relationship_status": "REPRODUCIBLE",
            "availability_status": "FOUND",
            "confidence": "HIGH",
        })
