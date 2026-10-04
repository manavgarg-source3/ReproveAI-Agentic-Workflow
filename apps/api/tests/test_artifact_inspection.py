"""Step 3B bounded repository inspection and experiment mapping tests."""

import base64
import json

import pytest

from app.schemas.research import (
    Artifact,
    ArtifactConfidence,
    ArtifactDiscoveryMethod,
    ArtifactFileRole,
    ArtifactFileType,
    ArtifactReadiness,
    ArtifactStatus,
    ArtifactType,
    Experiment,
    FileRelevanceStatus,
    PaperMetadata,
    ResearchAnalysis,
)
from app.services.artifacts.inspection import (
    classify_repository_file,
    inspect_artifacts,
)
from app.services.artifacts.provider import RepositoryFileMetadata, RepositoryMetadata
from app.services.artifacts.repository import PublicRepositoryMetadataProvider


BERT_URL = "https://github.com/google-research/bert"


def code_artifact(*, status=ArtifactStatus.FOUND, experiment_id=None) -> Artifact:
    return Artifact(
        artifact_id="ART-001",
        experiment_id=experiment_id,
        type=ArtifactType.CODE,
        name="bert",
        source="github",
        source_url=BERT_URL,
        repository=BERT_URL,
        discovery_method=ArtifactDiscoveryMethod.PAPER_URL,
        relationship_status=status,
        availability_status=ArtifactStatus.FOUND,
        confidence=ArtifactConfidence.MEDIUM,
    )


def bert_analysis() -> ResearchAnalysis:
    return ResearchAnalysis(
        paper=PaperMetadata(title="BERT"),
        experiments=[
            Experiment(
                id="EXP-GLUE",
                objective="Fine-tune and evaluate BERT on GLUE",
                dataset="GLUE",
                model="BERT-Large",
                metric="accuracy",
            ),
            Experiment(
                id="EXP-SQUAD",
                objective="Fine-tune and evaluate BERT on SQuAD",
                dataset="SQuAD",
                model="BERT-Large",
                metric="F1",
            ),
        ],
    )


def bert_metadata(**overrides) -> RepositoryMetadata:
    values = {
        "canonical_url": BERT_URL,
        "platform": "github",
        "owner": "google-research",
        "name": "bert",
        "accessible": True,
        "readme_excerpt": (
            "Use run_classifier.py for GLUE fine-tuning and evaluation.\n"
            "Use run_squad.py for SQuAD fine-tuning and evaluation.\n"
            "The BERT model is defined in modeling.py and tokenization.py prepares input.\n"
            "Install requirements.txt."
        ),
        "readme_available": True,
        "file_tree": [
            RepositoryFileMetadata("run_classifier.py"),
            RepositoryFileMetadata("run_squad.py"),
            RepositoryFileMetadata("modeling.py"),
            RepositoryFileMetadata("tokenization.py"),
            RepositoryFileMetadata("requirements.txt"),
            RepositoryFileMetadata("README.md"),
        ],
    }
    values.update(overrides)
    return RepositoryMetadata(**values)


class StubProvider:
    def __init__(self, metadata):
        self.metadata = metadata
        self.calls = []

    def inspect(self, url):
        self.calls.append(url)
        if isinstance(self.metadata, Exception):
            raise self.metadata
        return self.metadata


@pytest.mark.parametrize(
    ("path", "file_type", "role"),
    [
        ("train.py", ArtifactFileType.PYTHON, ArtifactFileRole.TRAINING),
        ("evaluation/run_eval.py", ArtifactFileType.PYTHON, ArtifactFileRole.EVALUATION),
        ("requirements.txt", ArtifactFileType.DEPENDENCY, ArtifactFileRole.DEPENDENCY),
        ("configs/bert.yaml", ArtifactFileType.CONFIG, ArtifactFileRole.CONFIGURATION),
        ("scripts/launch.sh", ArtifactFileType.SHELL, ArtifactFileRole.EXECUTION_SCRIPT),
        ("models/model.ckpt", ArtifactFileType.CHECKPOINT, ArtifactFileRole.CHECKPOINT),
        ("Dockerfile", ArtifactFileType.CONTAINER, ArtifactFileRole.CONFIGURATION),
        ("README.md", ArtifactFileType.DOCUMENTATION, ArtifactFileRole.DOCUMENTATION),
    ],
)
def test_file_classifier_is_conservative(path, file_type, role) -> None:
    assert classify_repository_file(path) == (file_type, role)


def test_bert_files_map_to_glue_and_squad_using_only_observed_paths() -> None:
    metadata = bert_metadata()
    result = inspect_artifacts(
        [code_artifact(experiment_id="EXP-SQUAD")],
        bert_analysis(),
        repository_provider=StubProvider(metadata),
    )

    observed = {item.path for item in metadata.file_tree}
    assert {item.path for item in result.files} <= observed
    glue = [item for item in result.files if item.experiment_id == "EXP-GLUE"]
    squad = [item for item in result.files if item.experiment_id == "EXP-SQUAD"]
    assert next(item for item in glue if item.path == "run_classifier.py").relevance_status == FileRelevanceStatus.RELEVANT
    assert next(item for item in squad if item.path == "run_squad.py").relevance_status == FileRelevanceStatus.RELEVANT
    assert next(item for item in glue if item.path == "run_classifier.py").role == ArtifactFileRole.EVALUATION
    assert all(item.evidence for item in result.files)
    assert {item.readiness for item in result.experiment_maps} == {ArtifactReadiness.PARTIAL}
    assert {item.experiment_id for item in result.experiment_maps} == {"EXP-GLUE", "EXP-SQUAD"}


def test_missing_and_unknown_roles_are_explicit() -> None:
    metadata = bert_metadata(file_tree=[
        *bert_metadata().file_tree,
        RepositoryFileMetadata("config.yaml"),
    ])
    result = inspect_artifacts(
        [code_artifact()], bert_analysis(), repository_provider=StubProvider(metadata)
    )
    mapping = next(item for item in result.experiment_maps if item.experiment_id == "EXP-GLUE")
    assert ArtifactFileRole.CHECKPOINT in mapping.missing_roles
    assert ArtifactFileRole.CONFIGURATION in mapping.unknown_roles


def test_ambiguous_unrelated_repository_does_not_mark_generic_python_relevant() -> None:
    metadata = bert_metadata(
        readme_excerpt="Generic utilities with no experiment instructions.",
        file_tree=[
            RepositoryFileMetadata("utils.py"),
            RepositoryFileMetadata("common_model.py"),
        ],
    )
    result = inspect_artifacts(
        [code_artifact(status=ArtifactStatus.AMBIGUOUS)],
        bert_analysis(),
        repository_provider=StubProvider(metadata),
    )
    assert result.files
    assert all(item.relevance_status != FileRelevanceStatus.RELEVANT for item in result.files)


def test_repository_unavailable_returns_missing_maps_without_files() -> None:
    metadata = bert_metadata(
        accessible=False,
        readme_excerpt=None,
        readme_available=False,
        file_tree=[],
        notes=["Repository unavailable."],
    )
    result = inspect_artifacts(
        [code_artifact()], bert_analysis(), repository_provider=StubProvider(metadata)
    )
    assert result.files == []
    assert all(item.readiness == ArtifactReadiness.MISSING for item in result.experiment_maps)
    assert all("Repository unavailable." in item.notes for item in result.experiment_maps)


def test_readme_unavailable_keeps_file_tree_evidence() -> None:
    metadata = bert_metadata(
        readme_excerpt=None,
        readme_available=False,
        file_tree=[RepositoryFileMetadata("run_squad.py")],
    )
    result = inspect_artifacts(
        [code_artifact()], bert_analysis(), repository_provider=StubProvider(metadata)
    )
    assert any(item.path == "run_squad.py" for item in result.files)
    assert all("README evidence was unavailable." in item.notes for item in result.experiment_maps)


def test_duplicate_paths_are_inspected_once_per_experiment() -> None:
    metadata = bert_metadata(file_tree=[
        RepositoryFileMetadata("run_squad.py"),
        RepositoryFileMetadata("RUN_SQUAD.py"),
    ])
    result = inspect_artifacts(
        [code_artifact(experiment_id="EXP-SQUAD")],
        bert_analysis(),
        repository_provider=StubProvider(metadata),
    )
    assert len(result.files) == 1


def test_partial_repository_inspection_is_visible() -> None:
    result = inspect_artifacts(
        [code_artifact()],
        bert_analysis(),
        repository_provider=StubProvider(bert_metadata(inspection_partial=True)),
    )
    assert all(item.inspection_partial for item in result.experiment_maps)
    assert all(
        "Repository file inspection reached a configured bound." in item.notes
        for item in result.experiment_maps
    )


def test_provider_failure_is_isolated() -> None:
    result = inspect_artifacts(
        [code_artifact()],
        bert_analysis(),
        repository_provider=StubProvider(TimeoutError("private detail")),
    )
    assert result.files == []
    assert all(item.readiness == ArtifactReadiness.MISSING for item in result.experiment_maps)
    assert "private detail" not in " ".join(result.experiment_maps[0].notes)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status_code = status
        self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def iter_content(self, chunk_size):
        yield self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.headers = {}
        self.calls = []

    def get(self, url, **_kwargs):
        self.calls.append(url)
        return self.responses.get(url, FakeResponse({}, status=404))


def test_github_inspection_bounds_readme_tree_depth_requests_and_reuses_cache(monkeypatch) -> None:
    monkeypatch.setenv("MAX_REPOSITORY_FILES", "4")
    monkeypatch.setenv("MAX_REPOSITORY_DIRECTORY_DEPTH", "1")
    monkeypatch.setenv("MAX_REPOSITORY_README_CHARS", "12")
    monkeypatch.setenv("MAX_REPOSITORY_METADATA_REQUESTS", "4")
    api = "https://api.github.com/repos/google-research/bert"
    responses = {
        api: FakeResponse({"name": "bert", "default_branch": "master", "license": {"spdx_id": "Apache-2.0"}}),
        f"{api}/git/trees/master?recursive=1": FakeResponse({"tree": [
            {"path": "README.md", "type": "blob", "size": 100},
            {"path": "scripts", "type": "tree"},
            {"path": "scripts/train.py", "type": "blob", "size": 20},
            {"path": "scripts/deep/eval.py", "type": "blob", "size": 30},
            {"path": "extra.py", "type": "blob", "size": 40},
            {"path": "overflow.py", "type": "blob", "size": 50},
        ], "truncated": False}),
        f"{api}/readme": FakeResponse({
            "encoding": "base64",
            "content": base64.b64encode(b"bounded readme content").decode(),
        }),
        f"{api}/commits?per_page=1": FakeResponse([{"sha": "abc123"}]),
    }
    session = FakeSession(responses)
    provider = PublicRepositoryMetadataProvider(session=session)

    first = provider.inspect(BERT_URL)
    second = provider.inspect(BERT_URL)

    assert first is second
    assert first.readme_excerpt == "bounded read"
    assert len(first.file_tree) == 4
    assert "scripts/deep/eval.py" not in {item.path for item in first.file_tree}
    assert first.inspection_partial is True
    assert first.requests_made == 4
    assert len(session.calls) == 4


def test_tree_failure_preserves_bounded_readme(monkeypatch) -> None:
    monkeypatch.setenv("MAX_REPOSITORY_METADATA_REQUESTS", "4")
    api = "https://api.github.com/repos/google-research/bert"
    session = FakeSession({
        api: FakeResponse({"name": "bert", "default_branch": "master"}),
        f"{api}/git/trees/master?recursive=1": FakeResponse({}, status=503),
        f"{api}/readme": FakeResponse({
            "encoding": "base64",
            "content": base64.b64encode(b"README survived").decode(),
        }),
        f"{api}/commits?per_page=1": FakeResponse([], status=503),
    })

    metadata = PublicRepositoryMetadataProvider(session=session).inspect(BERT_URL)

    assert metadata.accessible is True
    assert metadata.readme_excerpt == "README survived"
    assert metadata.file_tree == []
    assert metadata.inspection_partial is True
    assert "Repository file tree could not be retrieved." in metadata.notes
