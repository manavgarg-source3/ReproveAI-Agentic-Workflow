"""Deterministic, non-executing Step 5 reproduction-planning tests."""

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
    DependencyType,
    EnvironmentConfiguration,
    EnvironmentDependency,
    EnvironmentEvidence,
    EnvironmentSpecification,
    EnvironmentStatus,
    Experiment,
    ExperimentArtifactMap,
    FileRelevanceStatus,
    PaperMetadata,
    ResearchAnalysis,
    ReproductionPlanStatus,
    RequirementStatus,
)
from app.services.reproduction.planning import (
    classify_command_safety,
    generate_reproduction_plans,
)


def experiment(
    experiment_id: str = "EXP-1",
    *,
    dataset: str | None = None,
    model: str | None = None,
    metric: str | None = None,
    result: float | None = None,
) -> Experiment:
    return Experiment(
        id=experiment_id,
        objective=f"Evaluate {model or experiment_id}",
        dataset=dataset,
        split="test" if dataset else None,
        model=model,
        metric=metric,
        reported_result=result,
        evidence_locations=["page 4"],
    )


def artifact(
    artifact_id: str,
    artifact_type: ArtifactType,
    *,
    name: str,
    experiment_id: str | None = "EXP-1",
    availability: ArtifactStatus = ArtifactStatus.FOUND,
) -> Artifact:
    return Artifact(
        artifact_id=artifact_id,
        experiment_id=experiment_id,
        type=artifact_type,
        name=name,
        source="fixture",
        source_url=f"https://example.org/{artifact_id}",
        repository=(f"https://github.com/example/{artifact_id}" if artifact_type == ArtifactType.CODE else None),
        discovery_method=ArtifactDiscoveryMethod.PAPER_URL,
        relationship_status=ArtifactStatus.FOUND,
        availability_status=availability,
        confidence=ArtifactConfidence.HIGH,
        evidence_location="page 4",
    )


def repository_file(
    path: str,
    role: ArtifactFileRole,
    *,
    experiment_id: str = "EXP-1",
    artifact_id: str = "ART-CODE",
) -> ArtifactFile:
    file_type = (
        ArtifactFileType.CONFIG
        if role == ArtifactFileRole.CONFIGURATION
        else ArtifactFileType.CHECKPOINT
        if role == ArtifactFileRole.CHECKPOINT
        else ArtifactFileType.PYTHON
    )
    return ArtifactFile(
        file_id=f"FILE-{experiment_id}-{path}",
        artifact_id=artifact_id,
        experiment_id=experiment_id,
        path=path,
        file_type=file_type,
        role=role,
        relevance_status=FileRelevanceStatus.RELEVANT,
        confidence=ArtifactConfidence.HIGH,
        evidence=[f"README maps {path} to {experiment_id}."],
    )


def environment(
    *,
    status: EnvironmentStatus = EnvironmentStatus.RECONSTRUCTED,
    experiment_id: str | None = None,
    commands: list[str] | None = None,
    conflicts: bool = False,
) -> EnvironmentSpecification:
    conflict_evidence = [EnvironmentEvidence(
        category="python",
        value="3.8",
        source_path="README.md",
        evidence="Python 3.8",
        certainty=Certainty.EXPLICIT,
    )] if conflicts else []
    return EnvironmentSpecification(
        environment_id="ENV-1",
        experiment_id=experiment_id,
        artifact_id="ART-CODE",
        status=status,
        python_version="3.11",
        container="python:3.11-slim",
        dependencies=[EnvironmentDependency(
            name="numpy",
            version_constraint="==1.26",
            dependency_type=DependencyType.PYTHON_PACKAGE,
            source_path="requirements.txt",
            evidence="numpy==1.26",
            certainty=Certainty.EXPLICIT,
        )],
        configuration_files=[EnvironmentConfiguration(
            path="configs/train.yaml",
            experiment_id=experiment_id,
            purpose="Training configuration",
            evidence="Observed repository configuration",
            relevance_status="RELEVANT",
        )],
        documented_commands=commands or ["python train.py --config configs/train.yaml"],
        gpu="NVIDIA V100",
        evidence=[
            EnvironmentEvidence(
                category="gpu",
                value="NVIDIA V100",
                source_path="README.md",
                evidence="Requires an NVIDIA V100 GPU.",
                certainty=Certainty.EXPLICIT,
            ),
            EnvironmentEvidence(
                category="container",
                value="python:3.11-slim",
                source_path="Dockerfile",
                evidence="FROM python:3.11-slim",
                certainty=Certainty.EXPLICIT,
            ),
        ],
        conflict_detected=conflicts,
        conflicting_evidence=conflict_evidence,
    )


def mapping(experiment_id: str = "EXP-1") -> ExperimentArtifactMap:
    return ExperimentArtifactMap(
        experiment_id=experiment_id,
        artifact_id="ART-CODE",
        readiness=ArtifactReadiness.COMPLETE,
    )


def generate(
    experiments: list[Experiment],
    artifacts: list[Artifact],
    files: list[ArtifactFile],
    environments: list[EnvironmentSpecification],
    paper_text: str = "",
    maps: list[ExperimentArtifactMap] | None = None,
):
    return generate_reproduction_plans(
        ResearchAnalysis(paper=PaperMetadata(title="Test"), experiments=experiments),
        [],
        [],
        artifacts,
        files,
        maps if maps is not None else [mapping(item.id) for item in experiments],
        environments,
        paper_text,
    )


def test_complete_plan_preserves_steps_requirements_parameters_and_expected_result() -> None:
    exp = experiment(dataset="Dataset-X", model="Model-X", metric="accuracy", result=0.91)
    artifacts = [
        artifact("ART-CODE", ArtifactType.CODE, name="code"),
        artifact("ART-DATA", ArtifactType.DATASET, name="Dataset-X"),
        artifact("ART-MODEL", ArtifactType.MODEL, name="Model-X"),
    ]
    files = [
        repository_file("train.py", ArtifactFileRole.TRAINING),
        repository_file("configs/train.yaml", ArtifactFileRole.CONFIGURATION),
    ]

    plan = generate(
        [exp], artifacts, files, [environment()],
        "Dataset-X Model-X used a learning rate of 2e-5 and batch size 32.",
    )[0]

    assert plan.status == ReproductionPlanStatus.READY_FOR_EXECUTION
    assert plan.entrypoints[0].script_path == "train.py"
    assert plan.training_steps[0].command.command.startswith("python train.py")
    assert plan.data_requirements[0].status == RequirementStatus.AVAILABLE
    assert plan.model_requirements[0].availability == RequirementStatus.AVAILABLE
    assert {item.name: item.value for item in plan.reported_parameters} == {
        "learning_rate": "2e-5", "batch_size": "32"
    }
    assert plan.expected_results[0].result_kind.value == "EXPECTED_REPORTED_RESULT"
    assert plan.expected_results[0].expected_value == 0.91
    assert plan.hardware_requirements[0].source_path == "README.md"
    assert plan.notes[0].startswith("PLANNED - NOT EXECUTED")


def test_command_safety_classifies_review_and_danger_without_execution() -> None:
    assert classify_command_safety("echo planning") == (classify_command_safety("echo planning")[0], [])
    assert classify_command_safety("python train.py")[0].value == "REQUIRES_REVIEW"
    safety, reasons = classify_command_safety("sudo pip install x && python train.py")
    assert safety.value == "UNSAFE_TO_EXECUTE"
    assert {"privilege escalation", "package installation", "shell composition"} <= set(reasons)


def test_readiness_partial_blocked_and_unknown_are_reachable() -> None:
    exp = experiment()
    code = artifact("ART-CODE", ArtifactType.CODE, name="code")
    partial = generate([exp], [code], [], [environment(commands=[])])[0]
    blocked = generate(
        [exp],
        [artifact("ART-CODE", ArtifactType.CODE, name="code", availability=ArtifactStatus.INACCESSIBLE)],
        [],
        [],
    )[0]
    unknown = generate([exp], [], [], [], maps=[])[0]

    assert partial.status == ReproductionPlanStatus.PARTIALLY_READY
    assert any(item.requirement == "execution entrypoint" for item in partial.missing_requirements)
    assert blocked.status == ReproductionPlanStatus.BLOCKED
    assert blocked.readiness.blocking_requirements[0].status == RequirementStatus.INACCESSIBLE
    assert unknown.status == ReproductionPlanStatus.UNKNOWN


def test_missing_dataset_model_and_inaccessible_checkpoint_remain_distinct() -> None:
    exp = experiment(dataset="Dataset-X", model="Model-X")
    artifacts = [
        artifact("ART-CODE", ArtifactType.CODE, name="code"),
        artifact("ART-DATA", ArtifactType.DATASET, name="Dataset-X", availability=ArtifactStatus.MISSING),
        artifact("ART-MODEL", ArtifactType.MODEL, name="Model-X", availability=ArtifactStatus.MISSING),
        artifact("ART-CKPT", ArtifactType.CHECKPOINT, name="Model-X checkpoint", availability=ArtifactStatus.INACCESSIBLE),
    ]

    plan = generate(
        [exp], artifacts, [repository_file("train.py", ArtifactFileRole.TRAINING)],
        [environment()],
    )[0]

    assert plan.data_requirements[0].status == RequirementStatus.MISSING
    assert plan.model_requirements[0].availability == RequirementStatus.MISSING
    assert plan.checkpoint_requirements[0].availability == RequirementStatus.INACCESSIBLE
    assert plan.status == ReproductionPlanStatus.BLOCKED


def test_environment_conflicts_and_incomplete_environment_lower_readiness() -> None:
    exp = experiment()
    code = artifact("ART-CODE", ArtifactType.CODE, name="code")
    files = [repository_file("train.py", ArtifactFileRole.TRAINING)]
    conflicted = generate([exp], [code], files, [environment(
        status=EnvironmentStatus.PARTIALLY_RECONSTRUCTED, conflicts=True
    )])[0]
    incomplete_env = environment(status=EnvironmentStatus.PARTIALLY_RECONSTRUCTED)
    incomplete_env = incomplete_env.model_copy(update={
        "missing_information": ["Operating system or container base image"]
    })
    incomplete = generate([exp], [code], files, [incomplete_env])[0]

    assert conflicted.status == ReproductionPlanStatus.PARTIALLY_READY
    assert conflicted.conflicts[0].status == RequirementStatus.CONFLICTING
    assert incomplete.status == ReproductionPlanStatus.PARTIALLY_READY
    assert incomplete.missing_requirements[0].requirement == "Operating system or container base image"


def test_parameters_preserve_conflicts_and_do_not_fabricate_defaults() -> None:
    exp = experiment(dataset="Dataset-X")
    code = artifact("ART-CODE", ArtifactType.CODE, name="code")
    text = (
        "Dataset-X learning rate was 1e-3.\n"
        "Dataset-X learning rate was 2e-3."
    )

    plan = generate(
        [exp], [code], [repository_file("train.py", ArtifactFileRole.TRAINING)],
        [environment()], text,
    )[0]

    assert [item.value for item in plan.reported_parameters] == ["1e-3", "2e-3"]
    assert all(item.name != "seed" for item in plan.reported_parameters)
    assert {item.detail for item in plan.conflicts} == {
        "Reported parameter value: 1e-3", "Reported parameter value: 2e-3"
    }


def test_multiple_experiments_keep_files_commands_and_parameters_isolated() -> None:
    experiments = [
        experiment("EXP-A", dataset="Data-A"),
        experiment("EXP-B", dataset="Data-B"),
    ]
    code = artifact("ART-CODE", ArtifactType.CODE, name="shared", experiment_id=None)
    files = [
        repository_file("train_a.py", ArtifactFileRole.TRAINING, experiment_id="EXP-A"),
        repository_file("train_b.py", ArtifactFileRole.TRAINING, experiment_id="EXP-B"),
    ]
    shared_environment = environment(commands=["python train_a.py", "python train_b.py"])
    plans = generate(
        experiments,
        [code],
        files,
        [shared_environment],
        "Data-A batch size 8.\nData-B batch size 16.",
        maps=[mapping("EXP-A"), mapping("EXP-B")],
    )

    by_id = {item.experiment_id: item for item in plans}
    assert [item.script_path for item in by_id["EXP-A"].entrypoints] == ["train_a.py"]
    assert [item.command for item in by_id["EXP-A"].commands] == ["python train_a.py"]
    assert [item.value for item in by_id["EXP-A"].reported_parameters] == ["8"]
    assert [item.script_path for item in by_id["EXP-B"].entrypoints] == ["train_b.py"]
    assert [item.command for item in by_id["EXP-B"].commands] == ["python train_b.py"]
    assert [item.value for item in by_id["EXP-B"].reported_parameters] == ["16"]


def test_docker_command_keeps_dockerfile_source_and_plan_ids_are_deterministic() -> None:
    exp = experiment()
    code = artifact("ART-CODE", ArtifactType.CODE, name="code")
    files = [repository_file("train.py", ArtifactFileRole.TRAINING)]
    docker_environment = environment(commands=['CMD ["python", "train.py"]'])

    first = generate([exp], [code], files, [docker_environment])[0]
    second = generate([exp], [code], files, [docker_environment])[0]

    assert first.commands[0].source_path == "Dockerfile"
    assert first.plan_id == second.plan_id
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
