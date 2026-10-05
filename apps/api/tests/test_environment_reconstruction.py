from app.services.environment.reconstruction import reconstruct_environments
from app.schemas.research import (
    Artifact,
    ArtifactFile,
    ArtifactFileType,
    ArtifactFileRole,
    FileRelevanceStatus,
    ArtifactConfidence,
    ArtifactType,
    ArtifactStatus,
    ArtifactDiscoveryMethod,
    ExperimentArtifactMap,
    ArtifactReadiness,
    ResearchAnalysis,
    PaperMetadata,
    EnvironmentStatus
)
from app.services.artifacts.repository import PublicRepositoryMetadataProvider

class MockRepositoryProvider(PublicRepositoryMetadataProvider):
    def get_file_content(self, repository_url: str, path: str) -> str | None:
        if path == "requirements.txt":
            return "torch>=1.9.0\ntransformers==4.11.3"
        elif path == "README.md":
            return "Requires GPU\nexport WANDB_API_KEY=xxx"
        return None

def test_reconstruct_environments_bert_mocked():
    provider = MockRepositoryProvider()
    
    artifact = Artifact(
        artifact_id="test_artifact",
        type=ArtifactType.CODE,
        discovery_method=ArtifactDiscoveryMethod.REPOSITORY_MENTION,
        relationship_status=ArtifactStatus.FOUND,
        availability_status=ArtifactStatus.FOUND,
        confidence=ArtifactConfidence.HIGH,
        source_url="https://github.com/google-research/bert"
    )
    
    files = [
        ArtifactFile(
            file_id="f1",
            artifact_id="test_artifact",
            experiment_id="exp1",
            path="requirements.txt",
            file_type=ArtifactFileType.DEPENDENCY,
            role=ArtifactFileRole.DEPENDENCY,
            relevance_status=FileRelevanceStatus.RELEVANT,
            confidence=ArtifactConfidence.HIGH
        ),
        ArtifactFile(
            file_id="f2",
            artifact_id="test_artifact",
            experiment_id="exp1",
            path="README.md",
            file_type=ArtifactFileType.DOCUMENTATION,
            role=ArtifactFileRole.DOCUMENTATION,
            relevance_status=FileRelevanceStatus.RELEVANT,
            confidence=ArtifactConfidence.HIGH
        )
    ]
    
    maps = [
        ExperimentArtifactMap(
            experiment_id="exp1",
            artifact_id="test_artifact",
            readiness=ArtifactReadiness.PARTIAL
        )
    ]
    
    analysis = ResearchAnalysis(paper=PaperMetadata(title="BERT"))
    
    envs = reconstruct_environments(analysis, [artifact], files, maps, provider, "Paper text")
    
    assert len(envs) == 1
    env = envs[0]
    
    assert env.experiment_id == "exp1"
    assert env.status == EnvironmentStatus.PARTIALLY_RECONSTRUCTED
    assert "PyTorch" in env.frameworks or "Transformers" in env.frameworks
    assert len(env.dependencies) == 2
    assert any(d.name == "torch" for d in env.dependencies)
    
    assert env.gpu == "REPORTED" # because torch was found
    
    assert len(env.environment_variables) == 1
    assert env.environment_variables[0].name == "WANDB_API_KEY"
    assert env.environment_variables[0].secret is True
