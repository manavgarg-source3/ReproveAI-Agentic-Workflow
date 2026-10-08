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
    generate_reproduction_targets,
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
        documented_commands=(
            ["python train.py --config configs/train.yaml"] if commands is None else commands
        ),
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


def select(
    experiments: list[Experiment],
    artifacts: list[Artifact],
    files: list[ArtifactFile],
    environments: list[EnvironmentSpecification],
    paper_text: str = "",
    maps: list[ExperimentArtifactMap] | None = None,
):
    actual_maps = maps if maps is not None else [mapping(item.id) for item in experiments]
    analysis = ResearchAnalysis(paper=PaperMetadata(title="Test"), experiments=experiments)
    plans = generate_reproduction_plans(
        analysis, [], [], artifacts, files, actual_maps, environments, paper_text
    )
    return generate_reproduction_targets(
        analysis, plans, artifacts, files, actual_maps, environments
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

    assert partial.status == ReproductionPlanStatus.UNKNOWN
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


def test_shared_main_entrypoint_commands_are_scoped_by_dataset_model_and_ipc() -> None:
    exp = Experiment(
        id="EXP-MNIST-50",
        objective="Evaluate ConvNet on MNIST with 50 images per class",
        dataset="MNIST",
        split="test",
        model="ConvNet",
        metric="testing accuracy",
        reported_result=98.8,
    )
    code = artifact(
        "ART-CODE", ArtifactType.CODE, name="DatasetCondensation",
        experiment_id="EXP-MNIST-50",
    )
    entrypoint = repository_file(
        "main.py", ArtifactFileRole.ENTRYPOINT,
        experiment_id="EXP-MNIST-50",
    )
    shared_environment = environment(commands=[
        "python main.py --dataset MNIST --model ConvNet --ipc 1",
        "python main.py --dataset CIFAR10 --model ConvNet --ipc 50",
        "python main.py --dataset MNIST --model ConvNet --ipc 50",
    ])

    plan = generate(
        [exp], [code], [entrypoint], [shared_environment],
        maps=[mapping("EXP-MNIST-50")],
    )[0]

    assert [item.command for item in plan.commands] == [
        "python main.py --dataset MNIST --model ConvNet --ipc 50"
    ]
    assert plan.entrypoints[0].phase.value == "TRAINING"


def test_commands_with_model_flags_are_not_assigned_when_model_is_unknown() -> None:
    exp = Experiment(
        id="EXP-MNIST-1",
        objective="Evaluate MNIST with 1 image per class",
        dataset="MNIST", split="test", metric="testing accuracy",
        reported_result=91.7,
    )
    plan = generate(
        [exp],
        [artifact("ART-CODE", ArtifactType.CODE, name="DatasetCondensation", experiment_id=exp.id)],
        [repository_file("main.py", ArtifactFileRole.ENTRYPOINT, experiment_id=exp.id)],
        [environment(commands=[
            "python main.py --dataset MNIST --model ConvNet --ipc 1",
            "python main.py --dataset MNIST --model MLP --ipc 1",
        ])],
        maps=[mapping(exp.id)],
    )[0]

    assert plan.commands == []


def test_named_dataset_without_verified_source_is_identified_not_unavailable() -> None:
    exp = experiment(dataset="MNIST", model="ConvNet")
    placeholder = artifact(
        "ART-DATA", ArtifactType.DATASET, name="MNIST",
        availability=ArtifactStatus.MISSING,
    ).model_copy(update={"source_url": None})
    plan = generate(
        [exp],
        [artifact("ART-CODE", ArtifactType.CODE, name="code"), placeholder],
        [repository_file("main.py", ArtifactFileRole.ENTRYPOINT)],
        [environment(commands=["python main.py --dataset MNIST --model ConvNet"])],
    )[0]

    assert plan.data_requirements[0].status == RequirementStatus.IDENTIFIED
    assert any(
        "identified in the paper" in item.detail
        for item in plan.missing_requirements
        if item.requirement == "MNIST"
    )


def test_named_model_placeholder_is_identified_not_unavailable() -> None:
    exp = experiment(dataset="MNIST", model="ConvNet")
    placeholder = artifact(
        "ART-MODEL", ArtifactType.MODEL, name="ConvNet",
        availability=ArtifactStatus.MISSING,
    ).model_copy(update={"source_url": None})
    plan = generate(
        [exp],
        [artifact("ART-CODE", ArtifactType.CODE, name="code"), placeholder],
        [repository_file("main.py", ArtifactFileRole.ENTRYPOINT)],
        [environment(commands=[])],
    )[0]

    assert plan.model_requirements[0].availability == RequirementStatus.IDENTIFIED


def test_plan_does_not_promote_unrelated_possible_files_or_install_command() -> None:
    exp = experiment(dataset="E2E NLG Challenge", model="GPT-2 Medium")
    code = artifact("ART-CODE", ArtifactType.CODE, name="LoRA code")
    create_data = repository_file(
        "examples/NLG/create_datasets.sh", ArtifactFileRole.DATA_PREPARATION
    )
    download_checkpoints = repository_file(
        "examples/NLG/download_pretrained_checkpoints.sh",
        ArtifactFileRole.DATA_PREPARATION,
    )
    unrelated = repository_file(
        "examples/NLU/roberta_large_mnli.sh", ArtifactFileRole.EXECUTION_SCRIPT
    ).model_copy(update={
        "relevance_status": FileRelevanceStatus.POSSIBLY_RELEVANT,
        "confidence": ArtifactConfidence.LOW,
    })
    shared_environment = environment(commands=["pip install loralib"]).model_copy(update={
        "configuration_files": [EnvironmentConfiguration(
            path="examples/NLU/ds_config.json",
            purpose="NLU-only configuration",
            evidence="Observed under examples/NLU",
            relevance_status="POSSIBLY_RELEVANT",
        )]
    })

    plan = generate(
        [exp], [code], [create_data, download_checkpoints, unrelated],
        [shared_environment], maps=[mapping("EXP-1")],
    )[0]

    assert {item.script_path for item in plan.entrypoints} == {
        "examples/NLG/create_datasets.sh",
        "examples/NLG/download_pretrained_checkpoints.sh",
    }
    assert all("examples/NLU" not in (item.script_path or "") for item in plan.entrypoints)
    assert plan.commands == []
    assert plan.configuration_requirements == []
    assert any(
        item.requirement == "training or evaluation entrypoint"
        for item in plan.missing_requirements
    )


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


def test_bert_candidates_rank_one_primary_glue_target_without_execution() -> None:
    experiments = [
        experiment("EXP-GLUE", dataset="GLUE", model="BERT-Large", metric="accuracy", result=0.914),
        experiment("EXP-SQUAD", dataset="SQuAD", model="BERT-Large", metric="F1", result=90.9),
    ]
    code = artifact("ART-CODE", ArtifactType.CODE, name="google-research/bert", experiment_id=None)
    artifacts = [
        code,
        artifact("ART-GLUE", ArtifactType.DATASET, name="GLUE", experiment_id="EXP-GLUE"),
        artifact("ART-SQUAD", ArtifactType.DATASET, name="SQuAD", experiment_id="EXP-SQUAD"),
        artifact("ART-BERT", ArtifactType.MODEL, name="BERT-Large", experiment_id=None),
    ]
    files = [
        repository_file("run_classifier.py", ArtifactFileRole.EVALUATION, experiment_id="EXP-GLUE"),
        repository_file("configs/glue.json", ArtifactFileRole.CONFIGURATION, experiment_id="EXP-GLUE"),
        repository_file("bert_large.ckpt", ArtifactFileRole.CHECKPOINT, experiment_id="EXP-GLUE"),
        repository_file("run_squad.py", ArtifactFileRole.EVALUATION, experiment_id="EXP-SQUAD"),
    ]
    env = environment(commands=["python run_classifier.py --task_name=MRPC"])

    selection = select(experiments, artifacts, files, [env])

    assert len(selection.candidate_targets) == 2
    assert selection.selected_target is not None
    assert selection.selected_target.experiment_id == "EXP-GLUE"
    assert selection.selected_target.published_result.reported_value == 0.914
    assert selection.selected_target.observed_result.status.value == "NOT_AVAILABLE"
    assert selection.selected_target.documented_command.command.startswith("python run_classifier.py")


def test_resnet_repository_backed_case_selects_image_net_target() -> None:
    exp = experiment("EXP-RESNET", dataset="ImageNet", model="ResNet-152", metric="Top-5 error", result=3.57)
    artifacts = [
        artifact("ART-CODE", ArtifactType.CODE, name="facebook/fb.resnet.torch", experiment_id="EXP-RESNET"),
        artifact("ART-DATA", ArtifactType.DATASET, name="ImageNet", experiment_id="EXP-RESNET"),
        artifact("ART-MODEL", ArtifactType.MODEL, name="ResNet-152", experiment_id="EXP-RESNET"),
    ]
    files = [repository_file("train.lua", ArtifactFileRole.TRAINING, experiment_id="EXP-RESNET")]
    env = environment(experiment_id="EXP-RESNET", commands=["th train.lua -dataset imagenet"])

    selection = select([exp], artifacts, files, [env], maps=[mapping("EXP-RESNET")])

    assert selection.selected_target.experiment_id == "EXP-RESNET"
    assert selection.selected_target.metric == "Top-5 error"
    assert selection.selected_target.published_result.result_kind == "PUBLISHED_RESULT"


def complete_target_inputs():
    complete = experiment(dataset="Dataset-X", model="Model-X", metric="accuracy", result=0.91)
    data = artifact("ART-DATA", ArtifactType.DATASET, name="Dataset-X")
    model = artifact("ART-MODEL", ArtifactType.MODEL, name="Model-X")
    code = artifact("ART-CODE", ArtifactType.CODE, name="code")
    entrypoint = repository_file("train.py", ArtifactFileRole.TRAINING)
    return complete, data, model, code, entrypoint


def test_paper_with_experiment_but_no_code_is_blocked() -> None:
    complete, data, model, _, _ = complete_target_inputs()
    no_code = select([complete], [data, model], [], [])
    assert no_code.selected_target.readiness_status == ReproductionPlanStatus.BLOCKED


def test_code_without_measurable_result_is_not_eligible() -> None:
    _, data, model, code, entrypoint = complete_target_inputs()
    no_result = select(
        [experiment(dataset="Dataset-X", model="Model-X", metric="accuracy")],
        [code, data, model], [entrypoint], [environment()],
    )
    assert no_result.selected_target is None
    assert no_result.candidate_targets[0].eligible is False


def test_identified_but_unavailable_dataset_blocks_target() -> None:
    complete, _, model, code, entrypoint = complete_target_inputs()
    missing_data = artifact(
        "ART-DATA", ArtifactType.DATASET, name="Dataset-X", availability=ArtifactStatus.MISSING
    )
    unavailable_dataset = select(
        [complete], [code, missing_data, model], [entrypoint], [environment()]
    )
    assert unavailable_dataset.selected_target.readiness_status == ReproductionPlanStatus.BLOCKED


def test_documented_training_entrypoint_is_checkpoint_free() -> None:
    complete, data, model, code, entrypoint = complete_target_inputs()
    missing_checkpoint = select(
        [complete], [code, data, model], [entrypoint], [environment()]
    )
    assert not any(
        item.requirement == "checkpoint identity"
        for item in missing_checkpoint.selected_target.missing_requirements
    )


def test_documented_synthetic_training_target_can_be_ready_without_external_artifacts() -> None:
    exp = Experiment(
        id="EXP-SPRING",
        objective="Model the dynamics of an ideal mass-spring system",
        dataset="Ideal mass-spring",
        split="test",
        model="Hamiltonian Neural Network (HNN)",
        metric="Energy MSE",
        reported_result=3.8416e-4,
        evidence_locations=["Table 1"],
    )
    code = artifact(
        "ART-CODE", ArtifactType.CODE, name="hamiltonian-nn",
        experiment_id=None,
    )
    files = [
        repository_file(
            "experiment-spring/data.py", ArtifactFileRole.DATA_PREPARATION,
            experiment_id="EXP-SPRING",
        ),
        repository_file(
            "experiment-spring/train.py", ArtifactFileRole.TRAINING,
            experiment_id="EXP-SPRING",
        ),
        repository_file(
            "hnn.py", ArtifactFileRole.UTILITY,
            experiment_id="EXP-SPRING",
        ),
    ]
    env = environment(
        commands=["python3 experiment-spring/train.py --verbose"]
    ).model_copy(update={"experiment_id": None})

    selection = select(
        [exp], [code], files, [env], maps=[mapping("EXP-SPRING")]
    )

    target = selection.selected_target
    assert target is not None
    assert target.readiness_status == ReproductionPlanStatus.READY_FOR_EXECUTION
    assert target.documented_command.command == "python3 experiment-spring/train.py --verbose"
    assert target.missing_requirements == []
    assert target.required_inputs == []


def test_missing_metric_is_not_eligible() -> None:
    _, data, model, code, entrypoint = complete_target_inputs()
    no_metric = select(
        [experiment(dataset="Dataset-X", model="Model-X", result=0.91)],
        [code, data, model], [entrypoint], [environment()],
    )
    assert no_metric.selected_target is None


def test_ambiguous_multi_metric_and_model_family_are_not_primary_targets() -> None:
    ambiguous = experiment(
        dataset="GLUE",
        model="RoBERTa base / large",
        metric="accuracy / correlation",
        result=87.2,
    )
    selection = select(
        [ambiguous],
        [artifact("ART-CODE", ArtifactType.CODE, name="code")],
        [repository_file(
            "examples/NLU/roberta_base_mnli.sh",
            ArtifactFileRole.EXECUTION_SCRIPT,
        )],
        [environment(commands=[])],
    )

    assert selection.selected_target is None
    candidate = selection.candidate_targets[0]
    assert candidate.eligible is False
    assert any(
        item.requirement == "single model configuration"
        for item in candidate.missing_requirements
    )
    assert any(
        item.requirement == "single metric definition"
        for item in candidate.missing_requirements
    )


def test_generic_convnet_family_is_not_a_deterministic_primary_target() -> None:
    generic = experiment(
        dataset="CIFAR10", model="ConvNets", metric="testing accuracy", result=84.5,
    )

    selection = select([generic], [], [], [])

    assert selection.selected_target is None
    assert selection.candidate_targets[0].eligible is False


def test_from_scratch_paper_does_not_require_a_checkpoint() -> None:
    exp = experiment(dataset="MNIST", model="ConvNet", metric="accuracy", result=0.988)
    analysis = ResearchAnalysis(
        paper=PaperMetadata(
            title="Dataset Condensation",
            abstract="We learn informative samples for training neural networks from scratch.",
        ),
        experiments=[exp],
    )
    plans = generate_reproduction_plans(analysis, [], [], [], [], [], [], "")

    selection = generate_reproduction_targets(analysis, plans, [], [], [], [])

    assert not any(
        item.requirement == "checkpoint identity"
        for item in selection.selected_target.missing_requirements
    )
    checkpoint_score = next(
        item for item in selection.selected_target.selection_score.dimensions
        if item.name == "checkpoint_availability"
    )
    assert checkpoint_score.satisfied is True


def test_unknown_evaluation_split_is_not_a_deterministic_primary_target() -> None:
    incomplete = Experiment(
        id="EXP-NO-SPLIT",
        objective="Evaluate Model-X",
        dataset="Dataset-X",
        model="Model-X",
        metric="accuracy",
        reported_result=0.91,
        evidence_locations=["Table 1"],
    )
    selection = select(
        [incomplete],
        [artifact(
            "ART-CODE",
            ArtifactType.CODE,
            name="code",
            experiment_id="EXP-NO-SPLIT",
        )],
        [repository_file(
            "train.py",
            ArtifactFileRole.TRAINING,
            experiment_id="EXP-NO-SPLIT",
        )],
        [environment(experiment_id="EXP-NO-SPLIT")],
        maps=[mapping("EXP-NO-SPLIT")],
    )

    assert selection.selected_target is None
    assert selection.candidate_targets[0].eligible is False
    assert any(
        item.requirement == "dataset split"
        for item in selection.candidate_targets[0].missing_requirements
    )


def test_target_exposes_only_files_with_verified_experiment_relevance() -> None:
    complete, data, model, code, entrypoint = complete_target_inputs()
    possible = entrypoint.model_copy(update={
        "file_id": "FILE-POSSIBLE",
        "path": "examples/NLG/create_datasets.sh",
        "role": ArtifactFileRole.DATA_PREPARATION,
        "relevance_status": FileRelevanceStatus.POSSIBLY_RELEVANT,
    })
    selection = select(
        [complete], [code, data, model], [entrypoint, possible], [environment()]
    )

    assert selection.selected_target is not None
    assert selection.selected_target.relevant_files == ["train.py"]
    assert [item.path for item in selection.selected_target.file_mappings] == ["train.py"]


def test_conflicting_experiment_information_lowers_readiness() -> None:
    complete, data, model, code, entrypoint = complete_target_inputs()
    conflicting = select(
        [complete], [code, data, model], [entrypoint], [environment()],
        "Dataset-X learning rate was 1e-3.\nDataset-X learning rate was 2e-3.",
    )
    assert conflicting.selected_target.readiness_status == ReproductionPlanStatus.PARTIALLY_READY


def test_missing_environment_remains_explicit() -> None:
    complete, data, model, code, entrypoint = complete_target_inputs()
    missing_environment = select([complete], [code, data, model], [entrypoint], [])
    assert missing_environment.selected_target.environment_id is None
    assert missing_environment.selected_target.readiness_status == ReproductionPlanStatus.PARTIALLY_READY


def test_missing_documented_command_remains_explicit() -> None:
    complete, data, model, code, entrypoint = complete_target_inputs()
    missing_command = select(
        [complete], [code, data, model], [entrypoint], [environment(commands=[])]
    )
    assert missing_command.selected_target.documented_command is None


def test_incomplete_step3b_mapping_remains_explicit() -> None:
    complete, data, model, code, _ = complete_target_inputs()
    incomplete_mapping = select([complete], [code, data, model], [], [environment()])
    assert not incomplete_mapping.selected_target.relevant_files
    assert any(
        item.requirement == "execution entrypoint"
        for item in incomplete_mapping.selected_target.missing_requirements
    )


def test_no_eligible_reproduction_target_returns_empty_selection() -> None:
    _, _, _, code, _ = complete_target_inputs()
    no_eligible = select([experiment()], [code], [], [])
    assert no_eligible.selected_target_id is None
    assert no_eligible.notes
