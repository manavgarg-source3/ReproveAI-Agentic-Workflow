"""Step 6 security, approval, integrity, and Docker-policy tests."""

from __future__ import annotations

import json
import inspect
import io
import shutil
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.execution import (
    ApprovalStatus,
    ExecutionApproval,
    ExecutionFailureCode,
    ExecutionPolicy,
    ExecutionStatus,
)
from app.schemas.research import (
    Artifact,
    ArtifactConfidence,
    ArtifactDiscoveryMethod,
    ArtifactFile,
    ArtifactFileRole,
    ArtifactFileType,
    ArtifactStatus,
    ArtifactType,
    Certainty,
    CommandSafety,
    EnvironmentSpecification,
    EnvironmentStatus,
    FileRelevanceStatus,
    PlanIssue,
    PlannedCommand,
    ReproductionPlanStatus,
    ReproductionTarget,
    ReproductionTargetSelection,
    RequirementStatus,
    TargetScoreDimension,
    TargetSelectionScore,
)
from app.services.execution.sandbox import (
    CommandResult,
    DockerRunner,
    ExecutionRejected,
    ExecutionService,
    hash_directory,
    parse_allowed_command,
    validate_execution_request,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "execution"


def target(
    *,
    command: str = "python evaluate.py --input /inputs/input.json --output /outputs/result.json",
    required_inputs: list[str] | None = None,
    missing: list[PlanIssue] | None = None,
    selected: bool = True,
    entrypoint: str = "evaluate.py",
) -> ReproductionTarget:
    environment = EnvironmentSpecification(
        environment_id="ENV-FIXTURE",
        experiment_id="EXP-FIXTURE",
        artifact_id="ART-FIXTURE",
        status=EnvironmentStatus.RECONSTRUCTED,
        python_constraint="==3.12",
    )
    file_mapping = ArtifactFile(
        file_id=f"FILE-{entrypoint}",
        artifact_id="ART-FIXTURE",
        experiment_id="EXP-FIXTURE",
        path=entrypoint,
        file_type=ArtifactFileType.PYTHON,
        role=ArtifactFileRole.EVALUATION,
        relevance_status=FileRelevanceStatus.RELEVANT,
        confidence=ArtifactConfidence.HIGH,
        evidence=["Controlled Step 6 fixture entrypoint."],
    )
    planned = PlannedCommand(
        command=command,
        source="fixture",
        source_path=entrypoint,
        evidence=command,
        certainty=Certainty.EXPLICIT,
        safety=CommandSafety.REQUIRES_REVIEW,
        safety_reasons=["Invokes a validated Python artifact inside Docker."],
    )
    return ReproductionTarget(
        target_id="TARGET-FIXTURE",
        plan_id="PLAN-FIXTURE",
        experiment_id="EXP-FIXTURE",
        paper_title="EXECUTION_INFRASTRUCTURE_FIXTURE",
        objective="Evaluate deterministic fixture predictions",
        eligible=True,
        selected=selected,
        selection_rank=1,
        selection_score=TargetSelectionScore(
            total=11,
            maximum=11,
            dimensions=[TargetScoreDimension(
                name="fixture", satisfied=True, points=1, evidence="Controlled fixture"
            )],
        ),
        code_artifact_id="ART-FIXTURE",
        relevant_files=[entrypoint],
        file_mappings=[file_mapping],
        environment_id=environment.environment_id,
        environment_status=environment.status,
        environment_specification=environment,
        documented_command=planned,
        required_inputs=["input.json"] if required_inputs is None else required_inputs,
        missing_requirements=[] if missing is None else missing,
        certainty=Certainty.EXPLICIT,
        readiness_status=ReproductionPlanStatus.READY_FOR_EXECUTION,
        selection_reason="Controlled infrastructure fixture.",
    )


def custom_target(script: str, command: str, *, target_id: str, required_inputs: list[str] | None = None) -> ReproductionTarget:
    base = target(command=command, required_inputs=required_inputs or [])
    mapping = base.file_mappings[0].model_copy(update={
        "file_id": f"FILE-{script}", "path": script,
    })
    return base.model_copy(update={
        "target_id": target_id,
        "plan_id": f"PLAN-{target_id}",
        "relevant_files": [script],
        "file_mappings": [mapping],
        "documented_command": base.documented_command.model_copy(update={
            "command": command, "source_path": script, "evidence": command,
        }),
        "required_inputs": required_inputs or [],
    })


def code_artifact() -> Artifact:
    return Artifact(
        artifact_id="ART-FIXTURE",
        experiment_id="EXP-FIXTURE",
        type=ArtifactType.CODE,
        name="execution-fixture",
        source="test fixture",
        discovery_method=ArtifactDiscoveryMethod.PAPER_TEXT,
        relationship_status=ArtifactStatus.VERIFIED,
        availability_status=ArtifactStatus.VERIFIED,
        confidence=ArtifactConfidence.HIGH,
    )


class FakeDockerRunner:
    def __init__(self, result: CommandResult | None = None, *, available: bool = True):
        self.result = result or CommandResult(0, b'{"metric":"accuracy","value":0.75}\n', b"")
        self.is_available = available
        self.calls: list[list[str]] = []

    def available(self) -> bool:
        return self.is_available

    def run_simple(self, command: list[str], timeout: int = 20) -> CommandResult:
        self.calls.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return CommandResult(0, b"sha256:fixture-image\n", b"")
        if command[:2] == ["docker", "inspect"]:
            return CommandResult(0, b"false\n", b"")
        return CommandResult(0, b"", b"")

    def run_bounded(
        self, command: list[str], *, timeout: int, max_output_bytes: int
    ) -> CommandResult:
        self.calls.append(command)
        if len(command) >= 6 and command[:2] == ["docker", "exec"] and command[-2] == "-c":
            payload = b'{"metric":"accuracy","value":0.75}'
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w") as archive:
                info = tarfile.TarInfo("result.json")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            return CommandResult(0, stream.getvalue(), b"")
        return self.result


def prepared_service(
    tmp_path: Path,
    runner: FakeDockerRunner | DockerRunner | None = None,
    *,
    fixture_name: str = "evaluate.py",
    fixture_target: ReproductionTarget | None = None,
):
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    shutil.copy2(FIXTURE_ROOT / fixture_name, artifact_dir / fixture_name)
    input_path = tmp_path / "input.json"
    shutil.copy2(FIXTURE_ROOT / "input.json", input_path)
    service = ExecutionService(runner=runner or FakeDockerRunner(), db_path=tmp_path / "execution.db")
    fixture_target = fixture_target or target()
    service.register_selection(
        ReproductionTargetSelection(
            candidate_targets=[fixture_target],
            selected_target_id=fixture_target.target_id,
            selected_target=fixture_target,
        ),
        [code_artifact()],
    )
    service.register_artifact_source(fixture_target.target_id, artifact_dir)
    if "input.json" in fixture_target.required_inputs:
        service.register_input(
            fixture_target.target_id, "INPUT-FIXTURE", "input.json", input_path
        )
    return service, fixture_target, artifact_dir, input_path


def test_unapproved_execution_request_is_blocked(tmp_path: Path) -> None:
    service, fixture_target, _, _ = prepared_service(tmp_path)
    record = service.execute(fixture_target.target_id, "UNKNOWN", ExecutionPolicy())
    assert record.status == ExecutionStatus.BLOCKED
    assert record.failure_code == ExecutionFailureCode.NOT_APPROVED


def test_approval_binds_target_policy_and_artifact_hash(tmp_path: Path) -> None:
    service, fixture_target, artifact_dir, _ = prepared_service(tmp_path)
    approval = service.approve(fixture_target.target_id, "human-reviewer", ExecutionPolicy())
    assert approval.status == ApprovalStatus.APPROVED
    assert approval.artifact_hash == hash_directory(artifact_dir)
    with pytest.raises(Exception):
        approval.approver = "mutated"  # type: ignore[misc]


def test_artifact_tampering_after_approval_is_rejected(tmp_path: Path) -> None:
    service, fixture_target, artifact_dir, _ = prepared_service(tmp_path)
    approval = service.approve(fixture_target.target_id, "reviewer", ExecutionPolicy())
    (artifact_dir / "evaluate.py").write_text("print('tampered')", encoding="utf-8")
    record = service.execute(fixture_target.target_id, approval.approval_id, ExecutionPolicy())
    assert record.status == ExecutionStatus.BLOCKED
    assert record.failure_code == ExecutionFailureCode.ARTIFACT_CHANGED


def test_changed_staged_dataset_is_rejected(tmp_path: Path) -> None:
    service, fixture_target, _, input_path = prepared_service(tmp_path)
    approval = service.approve(fixture_target.target_id, "reviewer", ExecutionPolicy())
    input_path.write_text("{}", encoding="utf-8")
    record = service.execute(fixture_target.target_id, approval.approval_id, ExecutionPolicy())
    assert record.failure_code == ExecutionFailureCode.ARTIFACT_CHANGED


def test_wrong_artifact_hash_in_approval_is_rejected(tmp_path: Path) -> None:
    service, fixture_target, _, _ = prepared_service(tmp_path)
    approval = service.approve(fixture_target.target_id, "reviewer", ExecutionPolicy())
    forged = approval.model_copy(update={"artifact_hash": "0" * 64})
    service.approvals[approval.approval_id] = forged
    with service.repository._connect() as db:
        db.execute("UPDATE approvals SET payload=? WHERE approval_id=?", (forged.model_dump_json(), forged.approval_id))
    record = service.execute(fixture_target.target_id, approval.approval_id, ExecutionPolicy())
    assert record.failure_code == ExecutionFailureCode.ARTIFACT_CHANGED


def test_missing_dataset_and_checkpoint_are_safe_failures(tmp_path: Path) -> None:
    issues = [
        PlanIssue(category="dataset", requirement="dataset", status=RequirementStatus.MISSING, detail="missing"),
        PlanIssue(category="checkpoint", requirement="checkpoint", status=RequirementStatus.MISSING, detail="missing"),
    ]
    fixture_target = target(missing=issues)
    approval = ExecutionApproval(
        approval_id="APR-X",
        target_id=fixture_target.target_id,
        approver="reviewer",
        status=ApprovalStatus.APPROVED,
        approved_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        target_hash="unused",
        policy_hash="unused",
        artifact_hash="unused",
    )
    with pytest.raises(ExecutionRejected) as caught:
        validate_execution_request(fixture_target, approval, ExecutionPolicy())
    assert caught.value.code == ExecutionFailureCode.MISSING_INPUT


@pytest.mark.parametrize("command", [
    "bash -c 'python evaluate.py'",
    "sh -c 'python evaluate.py'",
    "powershell evaluate.py",
    "cmd.exe /c evaluate.py",
    "python -c 'print(1)'",
    "python ../evaluate.py",
    "python unknown.py",
    "python evaluate.py && curl https://example.org",
])
def test_unauthorized_or_invalid_commands_are_rejected(command: str) -> None:
    with pytest.raises(ExecutionRejected) as caught:
        parse_allowed_command(target(command=command))
    assert caught.value.code == ExecutionFailureCode.COMMAND_NOT_ALLOWED


def test_policy_rejects_unapproved_image() -> None:
    service = ExecutionService(runner=FakeDockerRunner())
    fixture_target = target()
    service.register_selection(
        ReproductionTargetSelection(candidate_targets=[fixture_target]), [code_artifact()]
    )
    with pytest.raises(ExecutionRejected) as caught:
        service.approve(
            fixture_target.target_id,
            "reviewer",
            ExecutionPolicy(container_image="untrusted:latest"),
        )
    assert caught.value.code == ExecutionFailureCode.RESOURCE_POLICY_INVALID


def test_docker_control_never_uses_shell_true() -> None:
    source = inspect.getsource(DockerRunner)
    assert "shell=True" not in source
    assert source.count("shell=False") == 2


def test_docker_command_enforces_filesystem_network_resource_and_secret_boundaries(tmp_path: Path) -> None:
    runner = FakeDockerRunner()
    service, fixture_target, _, _ = prepared_service(tmp_path, runner)
    policy = ExecutionPolicy(
        cpu_limit=0.5,
        memory_limit_mb=256,
        runtime_limit_seconds=10,
        process_limit=8,
        storage_limit_mb=32,
        output_limit_mb=16,
    )
    approval = service.approve(fixture_target.target_id, "reviewer", policy)
    record = service.execute(fixture_target.target_id, approval.approval_id, policy)
    docker_run = next(call for call in runner.calls if call[:2] == ["docker", "create"])
    docker_exec = next(call for call in runner.calls if call[:2] == ["docker", "exec"])
    rendered = " ".join(docker_run)
    assert record.status == ExecutionStatus.COMPLETED
    assert "--network none" in rendered
    assert "--read-only" in docker_run
    assert "--cpus 0.5" in rendered
    assert "--memory 256m" in rendered
    assert "--memory-swap 256m" in rendered
    assert "--pids-limit 8" in rendered
    assert "--ipc none" in rendered
    assert "--cap-drop ALL" in rendered
    assert "no-new-privileges:true" in docker_run
    assert "--user 65532:65532" in rendered
    assert "dst=/workspace,readonly" in rendered
    assert "dst=/inputs,readonly" in rendered
    assert "--privileged" not in docker_run
    assert "host" not in docker_run[docker_run.index("--network") + 1]
    assert all(".env" not in token and ".ssh" not in token for token in docker_run)
    env_values = [docker_run[index + 1] for index, value in enumerate(docker_run[:-1]) if value == "--env"]
    assert env_values == [
        "HOME=/tmp", "PYTHONDONTWRITEBYTECODE=1", "PYTHONUNBUFFERED=1", "CUDA_VISIBLE_DEVICES="
    ]
    assert docker_exec[-5:] == [
        "evaluate.py", "--input", "/inputs/input.json", "--output", "/outputs/result.json"
    ]


def test_application_env_and_ssh_material_cannot_be_staged(tmp_path: Path) -> None:
    service, fixture_target, artifact_dir, _ = prepared_service(tmp_path)
    (artifact_dir / ".env").write_text("GEMINI_API_KEY=secret", encoding="utf-8")
    with pytest.raises(ExecutionRejected) as caught:
        service.register_artifact_source(fixture_target.target_id, artifact_dir)
    assert caught.value.code == ExecutionFailureCode.INVALID_TARGET
    ssh_key = tmp_path / "id_rsa"
    ssh_key.write_text("private-key", encoding="utf-8")
    with pytest.raises(ExecutionRejected):
        service.register_input(fixture_target.target_id, "SECRET", "id_rsa", ssh_key)


def test_timeout_is_terminated_and_recorded(tmp_path: Path) -> None:
    runner = FakeDockerRunner(CommandResult(-9, b"", b"", timed_out=True))
    service, fixture_target, _, _ = prepared_service(tmp_path, runner)
    policy = ExecutionPolicy(runtime_limit_seconds=1)
    approval = service.approve(fixture_target.target_id, "reviewer", policy)
    record = service.execute(fixture_target.target_id, approval.approval_id, policy)
    assert record.status == ExecutionStatus.FAILED
    assert record.failure_code == ExecutionFailureCode.TIMEOUT
    assert any(call[:2] == ["docker", "kill"] for call in runner.calls)
    assert any(call[:3] == ["docker", "rm", "-f"] for call in runner.calls)


def test_nonzero_exit_is_preserved(tmp_path: Path) -> None:
    service, fixture_target, _, _ = prepared_service(
        tmp_path, FakeDockerRunner(CommandResult(7, b"", b"failure"))
    )
    policy = ExecutionPolicy()
    approval = service.approve(fixture_target.target_id, "reviewer", policy)
    record = service.execute(fixture_target.target_id, approval.approval_id, policy)
    assert record.status == ExecutionStatus.FAILED
    assert record.exit_code == 7
    assert record.failure_code == ExecutionFailureCode.EXECUTION_FAILED


def test_excessive_output_is_bounded_and_secrets_are_redacted(tmp_path: Path) -> None:
    result = CommandResult(
        0,
        b"GEMINI_API_KEY=super-secret\n" + b"x" * 32,
        b"PASSWORD=hunter2",
        stdout_truncated=True,
        stderr_truncated=True,
    )
    service, fixture_target, _, _ = prepared_service(tmp_path, FakeDockerRunner(result))
    policy = ExecutionPolicy()
    approval = service.approve(fixture_target.target_id, "reviewer", policy)
    record = service.execute(fixture_target.target_id, approval.approval_id, policy)
    assert "super-secret" not in record.stdout
    assert "hunter2" not in record.stderr
    assert record.stdout_truncated and record.stderr_truncated


def test_memory_limit_failure_is_recorded(tmp_path: Path) -> None:
    class OomRunner(FakeDockerRunner):
        def run_simple(self, command: list[str], timeout: int = 20) -> CommandResult:
            if command[:2] == ["docker", "inspect"]:
                self.calls.append(command)
                return CommandResult(0, b"true\n", b"")
            return super().run_simple(command, timeout)

    service, fixture_target, _, _ = prepared_service(tmp_path, OomRunner(CommandResult(137, b"", b"")))
    policy = ExecutionPolicy()
    approval = service.approve(fixture_target.target_id, "reviewer", policy)
    record = service.execute(fixture_target.target_id, approval.approval_id, policy)
    assert record.failure_code == ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED
    assert record.resource_limit_exceeded is True


def test_fixture_record_contains_hashed_outputs_and_is_append_only(tmp_path: Path) -> None:
    service, fixture_target, _, _ = prepared_service(tmp_path)
    policy = ExecutionPolicy()
    approval = service.approve(fixture_target.target_id, "reviewer", policy)
    first = service.execute(fixture_target.target_id, approval.approval_id, policy)
    second = service.execute(fixture_target.target_id, approval.approval_id, policy)
    assert first.run_id != second.run_id
    assert len(service.list_runs(fixture_target.target_id)) == 2
    assert first.outputs[0].name == "result.json"
    assert len(first.outputs[0].sha256) == 64
    assert first.provenance[0] == "EXECUTION_INFRASTRUCTURE_FIXTURE"
    assert json.loads((FIXTURE_ROOT / "expected_output.json").read_text()) == {
        "metric": "accuracy", "value": 0.75
    }


def test_docker_unavailable_blocks_without_host_fallback(tmp_path: Path) -> None:
    service, fixture_target, _, _ = prepared_service(
        tmp_path, FakeDockerRunner(available=False)
    )
    policy = ExecutionPolicy()
    approval = service.approve(fixture_target.target_id, "reviewer", policy)
    record = service.execute(fixture_target.target_id, approval.approval_id, policy)
    assert record.status == ExecutionStatus.BLOCKED
    assert record.failure_code == ExecutionFailureCode.SANDBOX_CREATION_FAILED


def test_real_bert_target_without_local_snapshot_is_blocked() -> None:
    service = ExecutionService(runner=FakeDockerRunner())
    bert = target(required_inputs=["GLUE", "BERT-Large", "checkpoint"])
    bert = bert.model_copy(update={
        "target_id": "TARGET-BERT-GLUE",
        "experiment_id": "EXP-GLUE",
        "paper_title": "BERT",
        "objective": "Fine-tune BERT-Large on GLUE MRPC",
        "code_artifact_id": "ART-BERT",
    })
    service.register_selection(
        ReproductionTargetSelection(candidate_targets=[bert]), []
    )
    with pytest.raises(ExecutionRejected) as caught:
        service.approve(bert.target_id, "reviewer", ExecutionPolicy())
    assert caught.value.code == ExecutionFailureCode.MISSING_INPUT


def test_execution_api_approval_execute_and_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.routes import execution as execution_route

    service, fixture_target, _, _ = prepared_service(tmp_path)
    monkeypatch.setattr(execution_route, "execution_service", service)
    monkeypatch.setenv("AUTH_MODE", "development")
    client = TestClient(app)
    approval_response = client.post(
        f"/api/v1/reproduction/{fixture_target.target_id}/approve",
        json={"approver": "api-reviewer", "policy": ExecutionPolicy().model_dump(mode="json")},
    )
    assert approval_response.status_code == 201
    approval_id = approval_response.json()["approval_id"]
    execution_response = client.post(
        f"/api/v1/reproduction/{fixture_target.target_id}/execute",
        json={"approval_id": approval_id, "policy": ExecutionPolicy().model_dump(mode="json")},
    )
    assert execution_response.status_code == 200
    assert execution_response.json()["status"] == "COMPLETED"
    run_id = execution_response.json()["run_id"]
    history = client.get(f"/api/v1/reproduction/{fixture_target.target_id}/runs")
    assert [item["run_id"] for item in history.json()] == [run_id]
    detail = client.get(
        f"/api/v1/reproduction/{fixture_target.target_id}/runs/{run_id}"
    )
    assert detail.status_code == 200
    assert detail.json()["artifact_hash"]


def _docker_fixture_available() -> bool:
    runner = DockerRunner()
    if not runner.available():
        return False
    return runner.run_simple([
        "docker", "image", "inspect", "python:3.12-slim"
    ]).returncode == 0


@pytest.mark.skipif(
    not _docker_fixture_available(),
    reason="Docker and preloaded python:3.12-slim are required; host fallback is forbidden.",
)
def test_fixture_executes_in_real_docker_sandbox(tmp_path: Path) -> None:
    service, fixture_target, _, _ = prepared_service(tmp_path, DockerRunner())
    policy = ExecutionPolicy(runtime_limit_seconds=30)
    approval = service.approve(fixture_target.target_id, "integration-reviewer", policy)
    record = service.execute(fixture_target.target_id, approval.approval_id, policy)
    assert record.status == ExecutionStatus.COMPLETED
    assert record.exit_code == 0
    assert record.outputs
    assert json.loads(record.stdout) == {"metric": "accuracy", "value": 0.75}


@pytest.mark.skipif(not _docker_fixture_available(), reason="Docker required")
def test_real_filesystem_network_and_secret_isolation(tmp_path: Path) -> None:
    probe_target = custom_target(
        "security_probe.py",
        "python security_probe.py",
        target_id="TARGET-SECURITY-PROBE",
    )
    service, _, _, _ = prepared_service(
        tmp_path,
        DockerRunner(),
        fixture_name="security_probe.py",
        fixture_target=probe_target,
    )
    approval = service.approve(probe_target.target_id, "integration-reviewer", ExecutionPolicy())
    record = service.execute(probe_target.target_id, approval.approval_id, ExecutionPolicy())
    assert record.status == ExecutionStatus.COMPLETED
    observed = json.loads(record.stdout)
    assert all(value is False for value in observed["paths"].values())
    assert all(value is False for value in observed["network"].values())
    assert observed["secret_names"] == []
    assert record.outputs[0].sandbox_path.startswith("/outputs/")


@pytest.mark.parametrize(
    ("mode", "expected_code"),
    [
        ("timeout", ExecutionFailureCode.TIMEOUT),
        ("memory", ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED),
        ("storage", ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED),
        ("output", ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED),
    ],
)
@pytest.mark.skipif(not _docker_fixture_available(), reason="Docker required")
def test_real_resource_limits_and_cleanup(
    tmp_path: Path, mode: str, expected_code: ExecutionFailureCode
) -> None:
    probe_target = custom_target(
        "resource_probe.py",
        f"python resource_probe.py {mode}",
        target_id=f"TARGET-RESOURCE-{mode.upper()}",
    )
    service, _, _, _ = prepared_service(
        tmp_path,
        DockerRunner(),
        fixture_name="resource_probe.py",
        fixture_target=probe_target,
    )
    policy = ExecutionPolicy(
        runtime_limit_seconds=1 if mode == "timeout" else 10,
        memory_limit_mb=128 if mode == "memory" else 512,
        process_limit=16,
        storage_limit_mb=8,
        output_limit_mb=1,
    )
    approval = service.approve(probe_target.target_id, "integration-reviewer", policy)
    record = service.execute(probe_target.target_id, approval.approval_id, policy)
    assert record.status == ExecutionStatus.FAILED
    assert record.failure_code == expected_code
    assert service.list_runs(probe_target.target_id)[0].run_id == record.run_id


@pytest.mark.skipif(not _docker_fixture_available(), reason="Docker required")
def test_real_pid_limit_rejects_excess_processes(tmp_path: Path) -> None:
    probe_target = custom_target(
        "resource_probe.py",
        "python resource_probe.py pids",
        target_id="TARGET-RESOURCE-PIDS",
    )
    service, _, _, _ = prepared_service(
        tmp_path,
        DockerRunner(),
        fixture_name="resource_probe.py",
        fixture_target=probe_target,
    )
    policy = ExecutionPolicy(runtime_limit_seconds=15, process_limit=8)
    approval = service.approve(probe_target.target_id, "integration-reviewer", policy)
    record = service.execute(probe_target.target_id, approval.approval_id, policy)
    assert record.status == ExecutionStatus.FAILED
    assert record.failure_code in {
        ExecutionFailureCode.EXECUTION_FAILED,
        ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED,
    }


@pytest.mark.skipif(not _docker_fixture_available(), reason="Docker required")
def test_real_cpu_limited_fixture_completes_inside_sandbox(tmp_path: Path) -> None:
    probe_target = custom_target(
        "resource_probe.py",
        "python resource_probe.py cpu",
        target_id="TARGET-RESOURCE-CPU",
    )
    runner = DockerRunner()
    service, _, _, _ = prepared_service(
        tmp_path,
        runner,
        fixture_name="resource_probe.py",
        fixture_target=probe_target,
    )
    policy = ExecutionPolicy(runtime_limit_seconds=15, cpu_limit=0.5)
    approval = service.approve(probe_target.target_id, "integration-reviewer", policy)
    record = service.execute(probe_target.target_id, approval.approval_id, policy)
    assert record.status == ExecutionStatus.COMPLETED
    assert record.resource_policy.cpu_limit == 0.5
