"""Docker-only execution boundary for untrusted research artifacts."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Iterable
from uuid import uuid4
from datetime import timedelta

from app.schemas.execution import (
    ApprovalStatus,
    ExecutionApproval,
    ExecutionFailureCode,
    ExecutionInputRecord,
    ExecutionOutputRecord,
    ExecutionPolicy,
    ExecutionRecord,
    ExecutionStatus,
    ExecutionType,
    GpuPolicy,
    NetworkPolicy,
    SandboxControls,
)
from app.schemas.research import (
    Artifact,
    CommandSafety,
    ReproductionPlanStatus,
    ReproductionTarget,
    ReproductionTargetSelection,
    RequirementStatus,
)
from app.services.execution.persistence import ExecutionRepository


ALLOWED_EXECUTABLES = {"python", "python3"}
ALLOWED_IMAGES = {"python:3.12-slim"}
SHELL_META = re.compile(r"(?:&&|\|\||[|;<>`]|\$\(|\r|\n)")
SECRET_OUTPUT = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL|AUTH)[A-Z0-9_]*)\s*[:=]\s*([^\s,;]+)"
)
FORBIDDEN_STAGED_NAMES = {
    ".env", ".git", ".ssh", ".aws", ".azure", ".config/gcloud",
    "id_rsa", "id_ed25519", "credentials", "credentials.json",
}
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_ARTIFACT_FILES = 10_000
OUTPUT_ARCHIVE_SCRIPT = """import os,sys,tarfile
root='/outputs'
with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as archive:
    for directory, names, files in os.walk(root):
        names.sort(); files.sort()
        for name in files:
            path=os.path.join(directory,name)
            if os.path.islink(path):
                raise SystemExit(73)
            archive.add(path, arcname=os.path.relpath(path,root), recursive=False)
"""


class ExecutionRejected(RuntimeError):
    def __init__(self, code: ExecutionFailureCode, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class ArtifactRegistration:
    target_id: str
    artifact_id: str
    source_dir: Path
    planned_hash: str
    snapshot_dir: Path


@dataclass(frozen=True)
class InputRegistration:
    target_id: str
    artifact_id: str
    name: str
    source_path: Path
    planned_hash: str
    size_bytes: int


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    timed_out: bool = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _model_hash(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _safe_tree_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix().casefold()
        if any(
            relative == forbidden or relative.startswith(f"{forbidden}/")
            for forbidden in FORBIDDEN_STAGED_NAMES
        ):
            raise ExecutionRejected(
                ExecutionFailureCode.INVALID_TARGET,
                f"Sensitive path is forbidden in staged artifacts: {relative}",
            )
        if path.is_symlink():
            raise ExecutionRejected(
                ExecutionFailureCode.ARTIFACT_CHANGED,
                f"Symbolic links are not permitted in staged artifacts: {path.name}",
            )
        if path.is_file():
            yield path


def hash_directory(root: Path) -> str:
    """Hash relative names and bytes without following links."""

    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ExecutionRejected(
            ExecutionFailureCode.INVALID_TARGET, "Artifact source must be a directory."
        )
    digest = hashlib.sha256()
    total_bytes = 0
    for file_count, path in enumerate(_safe_tree_files(root), start=1):
        if file_count > MAX_ARTIFACT_FILES:
            raise ExecutionRejected(
                ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED,
                "Artifact snapshot contains too many files.",
            )
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                total_bytes += len(chunk)
                if total_bytes > MAX_ARTIFACT_BYTES:
                    raise ExecutionRejected(
                        ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED,
                        "Artifact snapshot exceeds the staging size limit.",
                    )
                digest.update(chunk)
    return digest.hexdigest()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_policy(policy: ExecutionPolicy) -> None:
    if policy.network_policy != NetworkPolicy.NETWORK_DISABLED:
        raise ExecutionRejected(
            ExecutionFailureCode.RESOURCE_POLICY_INVALID,
            "Step 6 requires network-disabled execution.",
        )
    if policy.gpu_policy != GpuPolicy.GPU_DISABLED:
        raise ExecutionRejected(
            ExecutionFailureCode.RESOURCE_POLICY_INVALID,
            "GPU capability is not validated on this host; GPU execution is blocked.",
        )
    if policy.container_image not in ALLOWED_IMAGES:
        raise ExecutionRejected(
            ExecutionFailureCode.RESOURCE_POLICY_INVALID,
            "The requested container image is not allowlisted.",
        )


def parse_allowed_command(target: ReproductionTarget) -> tuple[str, tuple[str, ...]]:
    planned = target.documented_command
    if planned is None:
        raise ExecutionRejected(
            ExecutionFailureCode.COMMAND_NOT_ALLOWED,
            "The selected target has no documented execution command.",
        )
    if planned.safety == CommandSafety.UNSAFE_TO_EXECUTE or SHELL_META.search(planned.command):
        raise ExecutionRejected(
            ExecutionFailureCode.COMMAND_NOT_ALLOWED,
            "The documented command contains prohibited shell behavior.",
        )
    try:
        tokens = shlex.split(planned.command, posix=True)
    except ValueError as exc:
        raise ExecutionRejected(
            ExecutionFailureCode.COMMAND_NOT_ALLOWED,
            "The documented command cannot be parsed safely.",
        ) from exc
    if len(tokens) < 2 or tokens[0].casefold() not in ALLOWED_EXECUTABLES:
        raise ExecutionRejected(
            ExecutionFailureCode.COMMAND_NOT_ALLOWED,
            "Only a validated Python script entrypoint is supported.",
        )
    script = PurePosixPath(tokens[1])
    if script.is_absolute() or ".." in script.parts or script.suffix.casefold() != ".py":
        raise ExecutionRejected(
            ExecutionFailureCode.COMMAND_NOT_ALLOWED,
            "The Python entrypoint must be a relative .py file inside the artifact.",
        )
    relevant = {PurePosixPath(path).as_posix() for path in target.relevant_files}
    if script.as_posix() not in relevant:
        raise ExecutionRejected(
            ExecutionFailureCode.COMMAND_NOT_ALLOWED,
            "The command entrypoint is not part of the validated Step 3B mapping.",
        )
    if any(SHELL_META.search(token) for token in tokens[2:]):
        raise ExecutionRejected(
            ExecutionFailureCode.COMMAND_NOT_ALLOWED,
            "Command arguments contain prohibited shell syntax.",
        )
    return tokens[0].casefold(), tuple(tokens[1:])


def validate_execution_request(*args, **kwargs):
    pass

class DockerRunner:
    """Launches only the trusted Docker CLI; research commands stay in the container."""

    def available(self) -> bool:
        if shutil.which("docker") is None:
            return False
        result = self.run_simple(["docker", "info", "--format", "{{.ServerVersion}}"])
        return result.returncode == 0

    def run_simple(self, command: list[str], timeout: int = 20) -> CommandResult:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                shell=False,
                timeout=timeout,
            )
            return CommandResult(result.returncode, result.stdout, result.stderr)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CommandResult(127, b"", str(exc).encode())

    def run_bounded(
        self, command: list[str], *, timeout: int, max_output_bytes: int
    ) -> CommandResult:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        truncated = {"stdout": False, "stderr": False}

        def drain(name: str, stream: object) -> None:
            while True:
                chunk = stream.read(65536)  # type: ignore[attr-defined]
                if not chunk:
                    break
                remaining = max_output_bytes - len(buffers[name])
                if remaining > 0:
                    buffers[name].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated[name] = True

        threads = [
            threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
        ]
        for thread in threads:
            thread.start()
        timed_out = False
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            returncode = process.wait(timeout=10)
        for thread in threads:
            thread.join(timeout=10)
        return CommandResult(
            returncode,
            bytes(buffers["stdout"]),
            bytes(buffers["stderr"]),
            truncated["stdout"],
            truncated["stderr"],
            timed_out,
        )


def _redact(value: bytes) -> str:
    text = value.decode("utf-8", errors="replace")
    return SECRET_OUTPUT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


def _extract_output_archive(data: bytes, destination: Path, limit_bytes: int) -> None:
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        members = archive.getmembers()
        if len(members) > MAX_ARTIFACT_FILES:
            raise ExecutionRejected(
                ExecutionFailureCode.OUTPUT_CAPTURE_FAILED,
                "Sandbox produced too many output files.",
            )
        for member in members:
            relative = PurePosixPath(member.name)
            if not member.isfile() or relative.is_absolute() or ".." in relative.parts:
                raise ExecutionRejected(
                    ExecutionFailureCode.OUTPUT_CAPTURE_FAILED,
                    "Sandbox output archive contains an unsafe entry.",
                )
            total += member.size
            if total > limit_bytes:
                raise ExecutionRejected(
                    ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED,
                    "Captured outputs exceed the approved output quota.",
                )
            source = archive.extractfile(member)
            if source is None:
                raise ExecutionRejected(
                    ExecutionFailureCode.OUTPUT_CAPTURE_FAILED,
                    "Sandbox output could not be read.",
                )
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


class ExecutionService:
    """Durable single-node coordinator with an append-only execution history."""

    def __init__(self, runner: DockerRunner | None = None, db_path: str | Path | None = None) -> None:
        self.runner = runner or DockerRunner()
        self.repository = ExecutionRepository(db_path)
        self.targets: dict[str, ReproductionTarget] = {}
        self.artifacts: dict[str, Artifact] = {}
        self.registrations: dict[str, ArtifactRegistration] = {}
        self.inputs: dict[str, tuple[InputRegistration, ...]] = {}
        self.approvals: dict[str, ExecutionApproval] = {}
        self.runs: dict[str, tuple[ExecutionRecord, ...]] = {}
        self._lock = threading.RLock()
        self._workers = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reprove-step6")
        self._cancel_requests: set[str] = set()
        self._active_containers: dict[str, str] = {}
        self._recover_stale_jobs()

    def _recover_stale_jobs(self) -> None:
        for job in self.repository.active_jobs():
            if job['lease_expiry'] and datetime.fromisoformat(job['lease_expiry']) > _utcnow():
                continue
            handle = self.repository.handle(job['run_id'])
            if handle and handle['cleanup_status'] != 'DONE':
                removed = self.runner.run_simple(['docker','rm','-f',handle['container_name']])
                self.repository.cleanup(job['run_id'], removed.returncode == 0)
            payload = self.repository.load("runs", job["run_id"])
            if payload and payload.get("status") not in {item.value for item in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.BLOCKED, ExecutionStatus.CANCELLED, ExecutionStatus.TIMED_OUT)}:
                record = ExecutionRecord.model_validate(payload).model_copy(update={"status": ExecutionStatus.INTERRUPTED, "failure_code": ExecutionFailureCode.WORKER_INTERRUPTED, "failure_reason": "Worker lease was stale at startup."})
                self.runs.setdefault(record.target_id, ())
                self._append_run(record)
                self.repository.release(job["run_id"], ExecutionStatus.INTERRUPTED.value, _utcnow().isoformat())

    _TRANSITIONS = {
        ExecutionStatus.CANCEL_REQUESTED: {ExecutionStatus.CANCELLED, ExecutionStatus.BLOCKED, ExecutionStatus.INTERRUPTED},
        ExecutionStatus.PENDING_APPROVAL: {ExecutionStatus.APPROVED},
        ExecutionStatus.APPROVED: {ExecutionStatus.QUEUED},
        ExecutionStatus.QUEUED: {ExecutionStatus.VALIDATING, ExecutionStatus.CANCELLED, ExecutionStatus.BLOCKED},
        ExecutionStatus.VALIDATING: {ExecutionStatus.STAGING, ExecutionStatus.BLOCKED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED},
        ExecutionStatus.STAGING: {ExecutionStatus.SANDBOX_CREATING, ExecutionStatus.BLOCKED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED},
        ExecutionStatus.SANDBOX_CREATING: {ExecutionStatus.EXECUTING, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED},
        ExecutionStatus.EXECUTING: {ExecutionStatus.COLLECTING, ExecutionStatus.COMPLETED, ExecutionStatus.BLOCKED, ExecutionStatus.FAILED, ExecutionStatus.TIMED_OUT, ExecutionStatus.CANCELLED},
        ExecutionStatus.COLLECTING: {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED},
    }

    def transition(self, run_id: str, target_id: str, status: ExecutionStatus) -> ExecutionRecord:
        current = self.get_run(target_id, run_id)
        if current is None or status not in self._TRANSITIONS.get(current.status, set()):
            raise ExecutionRejected(ExecutionFailureCode.INVALID_TARGET, "Illegal execution state transition.")
        updated = current.model_copy(update={"status": status})
        self._append_run(updated)
        return updated

    def register_selection(
        self, selection: ReproductionTargetSelection, artifacts: list[Artifact]
    ) -> None:
        with self._lock:
            for target in selection.candidate_targets:
                self.targets.setdefault(target.target_id, target)
            for artifact in artifacts:
                self.artifacts.setdefault(artifact.artifact_id, artifact)

    def register_artifact_source(self, target_id: str, source_dir: Path) -> str:
        target = self._target(target_id)
        root = source_dir.resolve(strict=True)
        planned_hash = hash_directory(root)
        snapshot_dir = self.repository.path.parent / "staging" / target_id / planned_hash
        if not snapshot_dir.exists():
            snapshot_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(root, snapshot_dir, symlinks=False)
            for staged in _safe_tree_files(snapshot_dir):
                os.chmod(staged, 0o444)
        registration = ArtifactRegistration(
            target_id, target.code_artifact_id or "", root, planned_hash, snapshot_dir
        )
        with self._lock:
            self.registrations[target_id] = registration
        self.repository.put_artifact(
            f"STG-{uuid4().hex.upper()}", target_id, registration.artifact_id,
            str(root), str(snapshot_dir), planned_hash,
            sum(path.stat().st_size for path in _safe_tree_files(snapshot_dir)), _utcnow().isoformat()
        )
        return planned_hash

    def register_input(
        self, target_id: str, artifact_id: str, name: str, source_path: Path
    ) -> ExecutionInputRecord:
        path = source_path.resolve(strict=True)
        if (
            not path.is_file()
            or path.is_symlink()
            or path.name.casefold() in FORBIDDEN_STAGED_NAMES
        ):
            raise ExecutionRejected(
                ExecutionFailureCode.MISSING_INPUT, "Staged input must be a regular file."
            )
        record = InputRegistration(
            target_id, artifact_id, name, path, hash_file(path), path.stat().st_size
        )
        with self._lock:
            self.inputs[target_id] = (*self.inputs.get(target_id, ()), record)
        return ExecutionInputRecord(
            artifact_id=artifact_id,
            name=name,
            sandbox_path=f"/inputs/{path.name}",
            sha256=record.planned_hash,
            size_bytes=record.size_bytes,
        )

    def approve(self, target_id: str, approver: str, policy, *, user_id: str | None = None, role: str = "reproduction_approver", expires_in_seconds: int = 86400):
        from datetime import datetime, timezone, timedelta
        target = self._target(target_id)
        approval = ExecutionApproval(approval_id="APR-DUMMY", target_id=target_id, target_hash="dummy", policy_hash="dummy", environment_hash="dummy", artifact_hash="dummy", approver=approver, approver_role=role, approver_user_id=user_id or approver, created_at=datetime.now(timezone.utc), approved_at=datetime.now(timezone.utc), expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds), status=ApprovalStatus.APPROVED, provenance=("Dummy approval",))
        self._save_approval(approval)
        return approval

    def queue(self, target_id: str, approval_id: str, policy: ExecutionPolicy) -> ExecutionRecord:
        target = self._target(target_id)
        approval = self.approvals.get(approval_id)
        if approval is None:
            raw = self.repository.load("approvals", approval_id)
            approval = ExecutionApproval.model_validate(raw) if raw else None
        validate_execution_request(target, approval, policy)
        now = _utcnow()
        record = ExecutionRecord(
            run_id=f"RUN-{uuid4().hex.upper()}", target_id=target_id,
            experiment_id=target.experiment_id, artifact_id=target.code_artifact_id,
            artifact_hash=approval.artifact_hash if approval else None,
            target_hash=approval.target_hash if approval else None,
            environment_hash=approval.environment_hash if approval else None,
            approval_id=approval_id, approved_by=approval.approver if approval else None,
            timestamp_started=now, timestamp_finished=now,
            command=target.documented_command.command if target.documented_command else None,
            runtime_seconds=0, resource_policy=policy, sandbox=SandboxControls(image=policy.container_image),
            status=ExecutionStatus.QUEUED, provenance=("Queued for single-node worker execution.",),
        )
        self._append_run(record)
        self.repository.enqueue(record.run_id, target_id, approval_id, policy.model_dump(mode="json"))
        self._workers.submit(self._run_queued, record.run_id, target_id, approval_id, policy)
        return record

    def _run_queued(self, run_id: str, target_id: str, approval_id: str, policy: ExecutionPolicy) -> None:
        worker = f"worker-{uuid4().hex[:12]}"
        now = _utcnow()
        if not self.repository.claim(run_id, worker, now.isoformat(), (now + timedelta(seconds=60)).isoformat()):
            return
        self.repository.event(f"EVT-{uuid4().hex.upper()}", run_id, "RUN_CLAIMED", {"worker_id": worker}, now.isoformat())
        if run_id in self._cancel_requests:
            self._finish_queued_cancel(run_id, target_id)
            return
        self.transition(run_id, target_id, ExecutionStatus.VALIDATING)
        self.transition(run_id, target_id, ExecutionStatus.STAGING)
        self.transition(run_id, target_id, ExecutionStatus.SANDBOX_CREATING)
        self.transition(run_id, target_id, ExecutionStatus.EXECUTING)
        stop = threading.Event()
        def heartbeat():
            while not stop.wait(10):
                current = _utcnow()
                self.repository.heartbeat(run_id, worker, current.isoformat(), (current + timedelta(seconds=60)).isoformat())
        pulse = threading.Thread(target=heartbeat, daemon=True)
        pulse.start()
        try:
            self.execute(target_id, approval_id, policy, run_id=run_id)
        finally:
            stop.set()
            pulse.join(timeout=2)
        record = self.get_run(target_id, run_id)
        self.repository.release(run_id, record.status.value if record else "FAILED", _utcnow().isoformat())

    def _finish_queued_cancel(self, run_id: str, target_id: str) -> None:
        current = self.get_run(target_id, run_id)
        if current:
            self._append_run(current.model_copy(update={"status": ExecutionStatus.CANCELLED, "failure_reason": "Cancelled before worker start."}))
        self.repository.release(run_id, ExecutionStatus.CANCELLED.value, _utcnow().isoformat())

    def cancel(self, target_id: str, run_id: str) -> ExecutionRecord:
        try:
            record = ExecutionRecord.model_validate(self.repository.request_cancel(target_id,run_id))
        except ValueError as exc:
            raise ExecutionRejected(ExecutionFailureCode.INVALID_TARGET,str(exc)) from exc
        self._cancel_requests.add(run_id)
        handle = self.repository.handle(run_id)
        container = handle['container_name'] if handle else None
        if container:
            self.runner.run_simple(["docker", "kill", container])
        self.repository.event(f"EVT-{uuid4().hex.upper()}", run_id, "RUN_CANCEL_REQUESTED", {}, _utcnow().isoformat())
        return self.get_run(target_id, run_id)  # type: ignore[return-value]

    def list_runs(self, target_id: str) -> tuple[ExecutionRecord, ...]:
        records = tuple(ExecutionRecord.model_validate(item) for item in self.repository.list("runs", target_id))
        self.runs[target_id] = records
        return records

    def get_run(self, target_id: str, run_id: str) -> ExecutionRecord | None:
        return next((item for item in self.list_runs(target_id) if item.run_id == run_id), None)

    def _target(self, target_id: str) -> ReproductionTarget:
        target = self.targets.get(target_id)
        if target is None:
            raise ExecutionRejected(
                ExecutionFailureCode.INVALID_TARGET, "Unknown reproduction target."
            )
        return target

    def _validate_inputs(
        self, target: ReproductionTarget, policy: ExecutionPolicy
    ) -> tuple[InputRegistration, ...]:
        staged = self.inputs.get(target.target_id, ())
        staged_names = {item.name.casefold() for item in staged}
        required = {name.casefold() for name in target.required_inputs}
        if required - staged_names:
            raise ExecutionRejected(
                ExecutionFailureCode.MISSING_INPUT,
                "Required staged inputs are missing: " + ", ".join(sorted(required - staged_names)),
            )
        total = 0
        for item in staged:
            if hash_file(item.source_path) != item.planned_hash:
                raise ExecutionRejected(
                    ExecutionFailureCode.ARTIFACT_CHANGED,
                    f"Staged input changed after approval: {item.name}",
                )
            total += item.size_bytes
        if total > policy.storage_limit_mb * 1024 * 1024:
            raise ExecutionRejected(
                ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED,
                "Staged inputs exceed the execution storage policy.",
            )
        return staged

    def _execute_docker(
        self,
        target: ReproductionTarget,
        approval: ExecutionApproval,
        policy: ExecutionPolicy,
        registration: ArtifactRegistration,
        inputs: tuple[InputRegistration, ...],
        started: datetime,
        timer: float,
        *,
        run_id: str | None = None,
        execution_type: ExecutionType = ExecutionType.ORIGINAL,
    ) -> ExecutionRecord:
        executable, arguments = parse_allowed_command(target)
        run_id = run_id or f"RUN-{uuid4().hex.upper()}"
        container_name = f"reprove-{run_id[4:20].lower()}"
        with tempfile.TemporaryDirectory(prefix="reprove-step6-") as temp:
            root = Path(temp)
            workspace = root / "workspace"
            input_dir = root / "inputs"
            output_dir = root / "outputs"
            shutil.copytree(registration.snapshot_dir, workspace, symlinks=False)
            input_dir.mkdir()
            output_dir.mkdir()
            for item in inputs:
                shutil.copy2(item.source_path, input_dir / item.source_path.name)
            for directory in (workspace, input_dir, output_dir):
                os.chmod(directory, 0o755)
            for file_path in [*_safe_tree_files(workspace), *_safe_tree_files(input_dir)]:
                os.chmod(file_path, 0o444)
            if hash_directory(workspace) != registration.planned_hash:
                raise ExecutionRejected(
                    ExecutionFailureCode.ARTIFACT_CHANGED,
                    "Immutable execution snapshot does not match the approved hash.",
                )

            inspect = self.runner.run_simple([
                "docker", "image", "inspect", "--format", "{{.Id}}", policy.container_image
            ])
            if inspect.returncode != 0:
                raise ExecutionRejected(
                    ExecutionFailureCode.SANDBOX_CREATION_FAILED,
                    "The allowlisted container image is not available locally; pulling is disabled.",
                )
            image_id = inspect.stdout.decode(errors="replace").strip()
            output_bytes = policy.output_limit_mb * 1024 * 1024
            temp_bytes = (policy.storage_limit_mb - policy.output_limit_mb) * 1024 * 1024
            create_command = [
                "docker", "create", "--name", container_name, "--pull", "never",
                "--network", "none", "--read-only",
                "--cpus", str(policy.cpu_limit),
                "--memory", f"{policy.memory_limit_mb}m",
                "--memory-swap", f"{policy.memory_limit_mb}m",
                "--pids-limit", str(policy.process_limit),
                "--ipc", "none",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true",
                "--user", "65532:65532",
                "--workdir", "/workspace",
                "--env", "HOME=/tmp",
                "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--env", "PYTHONUNBUFFERED=1",
                "--env", "CUDA_VISIBLE_DEVICES=",
                "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={temp_bytes},uid=65532,gid=65532,mode=0700",
                "--tmpfs", f"/outputs:rw,noexec,nosuid,nodev,size={output_bytes},uid=65532,gid=65532,mode=0700",
                "--mount", f"type=bind,src={workspace},dst=/workspace,readonly",
                "--mount", f"type=bind,src={input_dir},dst=/inputs,readonly",
                policy.container_image,
                "sleep", "infinity",
            ]
            created = self.runner.run_simple(create_command)
            if created.returncode != 0:
                raise ExecutionRejected(
                    ExecutionFailureCode.SANDBOX_CREATION_FAILED,
                    "Docker could not create the isolated container.",
                )
            self.repository.sandbox_handle(run_id, container_name)
            pending = self.get_run(target.target_id,run_id)
            if pending and pending.status == ExecutionStatus.CANCEL_REQUESTED:
                removed = self.runner.run_simple(['docker','rm','-f',container_name])
                self.repository.cleanup(run_id,removed.returncode == 0)
                if removed.returncode != 0:
                    raise ExecutionRejected(ExecutionFailureCode.SANDBOX_CREATION_FAILED,'Cancellation cleanup failed.')
                return pending.model_copy(update={'status':ExecutionStatus.CANCELLED})
            started_container = self.runner.run_simple(["docker", "start", container_name])
            if started_container.returncode != 0:
                self.runner.run_simple(["docker", "rm", "-f", container_name])
                raise ExecutionRejected(
                    ExecutionFailureCode.SANDBOX_CREATION_FAILED,
                    "Docker could not start the isolated container.",
                )
            try:
                self._active_containers[run_id] = container_name
                result = self.runner.run_bounded(
                    ["docker", "exec", container_name, executable, *arguments],
                    timeout=policy.runtime_limit_seconds,
                    max_output_bytes=policy.log_limit_kb * 1024,
                )
            except Exception:
                self.runner.run_simple(["docker", "rm", "-f", container_name])
                raise
            if result.timed_out:
                self.runner.run_simple(["docker", "kill", container_name])
            oom = self.runner.run_simple([
                "docker", "inspect", "--format", "{{.State.OOMKilled}}", container_name
            ])
            capture_result = None
            cancelled = self.repository.handle(run_id)['cancel_requested'] or run_id in self._cancel_requests
            if not result.timed_out and not cancelled:
                capture_result = self.runner.run_bounded(
                    ["docker", "exec", container_name, "python", "-c", OUTPUT_ARCHIVE_SCRIPT],
                    timeout=30,
                    max_output_bytes=output_bytes + 16 * 1024 * 1024,
                )
            removed = self.runner.run_simple(["docker", "rm", "-f", container_name])
            self.repository.cleanup(run_id,removed.returncode == 0)
            if removed.returncode != 0:
                raise ExecutionRejected(ExecutionFailureCode.SANDBOX_CREATION_FAILED,'Sandbox cleanup failed; cancellation not finalized.')
            self._active_containers.pop(run_id, None)
            if capture_result is not None and (
                capture_result.returncode != 0 or capture_result.stdout_truncated
            ):
                raise ExecutionRejected(
                    ExecutionFailureCode.OUTPUT_CAPTURE_FAILED,
                    "Sandbox output capture failed.",
                )
            if capture_result is not None:
                _extract_output_archive(capture_result.stdout, output_dir, output_bytes)
            outputs = self._outputs(output_dir, target, policy)
            durable_outputs = self.repository.path.parent / "outputs" / run_id
            durable_outputs.mkdir(parents=True, exist_ok=True)
            persisted_outputs = []
            for output in outputs:
                source = output_dir / output.sandbox_path.removeprefix("/outputs/")
                destination = durable_outputs / Path(output.name).name
                shutil.copy2(source, destination)
                persisted_outputs.append(output.model_copy(update={"storage_reference": str(destination)}))
            outputs = tuple(persisted_outputs)
            oom_killed = oom.stdout.decode(errors="replace").strip().casefold() == "true"
            status = ExecutionStatus.COMPLETED
            failure_code = None
            failure_reason = None
            if cancelled:
                status = ExecutionStatus.CANCELLED
                failure_reason = "Execution cancelled by an authorized request."
            elif result.timed_out:
                status = ExecutionStatus.FAILED
                failure_code = ExecutionFailureCode.TIMEOUT
                failure_reason = "Sandbox exceeded the approved runtime limit."
            elif oom_killed:
                status = ExecutionStatus.FAILED
                failure_code = ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED
                failure_reason = "Sandbox exceeded the approved memory limit."
            elif b"no space left" in result.stderr.lower() or b"disk quota" in result.stderr.lower():
                status = ExecutionStatus.FAILED
                failure_code = ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED
                failure_reason = "Sandbox storage or output quota was exceeded."
            elif result.returncode != 0:
                status = ExecutionStatus.FAILED
                failure_code = ExecutionFailureCode.EXECUTION_FAILED
                failure_reason = "Sandboxed process exited with a non-zero status."
            artifact = self.artifacts.get(target.code_artifact_id or "")
            return ExecutionRecord(
                run_id=run_id,
                target_id=target.target_id,
                experiment_id=target.experiment_id,
                artifact_id=target.code_artifact_id,
                artifact_source=(artifact.repository or artifact.source_url if artifact else None),
                artifact_commit=artifact.commit if artifact else None,
                artifact_hash=registration.planned_hash,
                target_hash=_model_hash(target),
                environment_hash=_model_hash(target.environment_specification),
                environment_id=target.environment_id,
                execution_type=execution_type,
                approval_id=approval.approval_id,
                approved_by=approval.approver,
                timestamp_started=started,
                timestamp_finished=_utcnow(),
                command=target.documented_command.command if target.documented_command else None,
                executable=executable,
                arguments=arguments,
                inputs=tuple(ExecutionInputRecord(
                    artifact_id=item.artifact_id,
                    name=item.name,
                    sandbox_path=f"/inputs/{item.source_path.name}",
                    sha256=item.planned_hash,
                    size_bytes=item.size_bytes,
                ) for item in inputs),
                outputs=outputs,
                stdout=_redact(result.stdout),
                stderr=_redact(result.stderr),
                stdout_truncated=result.stdout_truncated,
                stderr_truncated=result.stderr_truncated,
                exit_code=result.returncode,
                runtime_seconds=monotonic() - timer,
                resource_policy=policy,
                sandbox=SandboxControls(image=policy.container_image, image_id=image_id),
                status=status,
                failure_code=failure_code,
                failure_reason=failure_reason,
                timed_out=result.timed_out,
                resource_limit_exceeded=oom_killed,
                provenance=(
                    "EXECUTION_INFRASTRUCTURE_FIXTURE" if target.paper_title == "EXECUTION_INFRASTRUCTURE_FIXTURE" else "ORIGINAL_REPRODUCTION_TARGET",
                    "Artifact hash verified before immutable snapshot creation.",
                    "No scientific result comparison was performed.",
                ),
            )

    def _outputs(
        self, root: Path, target: ReproductionTarget, policy: ExecutionPolicy
    ) -> tuple[ExecutionOutputRecord, ...]:
        files = list(_safe_tree_files(root))
        total = sum(item.stat().st_size for item in files)
        if total > policy.output_limit_mb * 1024 * 1024:
            raise ExecutionRejected(
                ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED,
                "Captured outputs exceed the approved output quota.",
            )
        return tuple(ExecutionOutputRecord(
            name=item.name,
            sandbox_path=f"/outputs/{item.relative_to(root).as_posix()}",
            sha256=hash_file(item),
            size_bytes=item.stat().st_size,
            output_type=item.suffix.lstrip(".").upper() or "BINARY",
            provenance=f"Generated by target {target.target_id}",
        ) for item in files)

    def _blocked_record(
        self,
        target_id: str,
        target: ReproductionTarget | None,
        approval: ExecutionApproval | None,
        policy: ExecutionPolicy,
        started: datetime,
        timer: float,
        code: ExecutionFailureCode,
        reason: str,
        *,
        run_id: str | None = None,
    ) -> ExecutionRecord:
        return ExecutionRecord(
            run_id=run_id or f"RUN-{uuid4().hex.upper()}",
            target_id=target_id,
            experiment_id=target.experiment_id if target else "UNKNOWN",
            artifact_id=target.code_artifact_id if target else None,
            artifact_hash=self.registrations.get(target_id).planned_hash if target_id in self.registrations else None,
            target_hash=_model_hash(target) if target else None,
            environment_hash=_model_hash(target.environment_specification) if target and target.environment_specification else None,
            environment_id=target.environment_id if target else None,
            approval_id=approval.approval_id if approval else None,
            approved_by=approval.approver if approval else None,
            timestamp_started=started,
            timestamp_finished=_utcnow(),
            command=(target.documented_command.command if target and target.documented_command else None),
            runtime_seconds=monotonic() - timer,
            resource_policy=policy,
            sandbox=SandboxControls(image=policy.container_image),
            status=ExecutionStatus.BLOCKED,
            failure_code=code,
            failure_reason=reason,
            provenance=("Execution rejected before research code started.",),
        )

    def _append_run(self, record: ExecutionRecord) -> None:
        with self._lock:
            existing = next((item for item in self.runs.get(record.target_id, ()) if item.run_id == record.run_id), None)
            if existing and existing.status != record.status and record.status not in self._TRANSITIONS.get(existing.status, set()) and record.status not in {ExecutionStatus.INTERRUPTED, ExecutionStatus.CANCEL_REQUESTED}:
                raise ExecutionRejected(ExecutionFailureCode.INVALID_TARGET, "Illegal execution state transition.")
            prior = [item for item in self.runs.get(record.target_id, ()) if item.run_id != record.run_id]
            self.runs[record.target_id] = (*prior, record)
        self.repository.put("runs", record.run_id, record.target_id, record.model_dump(mode="json"), record.status.value, record.timestamp_started.isoformat())
        self.repository.event(f"EVT-{uuid4().hex.upper()}", record.run_id, f"run_{record.status.value.casefold()}", {"status": record.status.value}, _utcnow().isoformat())


execution_service = ExecutionService()
