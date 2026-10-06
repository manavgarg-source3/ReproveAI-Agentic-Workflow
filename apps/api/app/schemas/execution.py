"""Immutable contracts for approved, sandboxed AI/ML execution."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.research import ObservedResult


class FrozenStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExecutionStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    STAGING = "STAGING"
    SANDBOX_CREATING = "SANDBOX_CREATING"
    COLLECTING = "COLLECTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    INTERRUPTED = "INTERRUPTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"


class ApprovalStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class ExecutionType(str, Enum):
    ORIGINAL = "ORIGINAL"
    DIAGNOSTIC = "DIAGNOSTIC"
    MODIFIED = "MODIFIED"
    HYPOTHESIS_TEST = "HYPOTHESIS_TEST"


class NetworkPolicy(str, Enum):
    NETWORK_DISABLED = "NETWORK_DISABLED"


class GpuPolicy(str, Enum):
    GPU_DISABLED = "GPU_DISABLED"
    GPU_REQUESTED = "GPU_REQUESTED"
    GPU_ALLOWED = "GPU_ALLOWED"


class ExecutionFailureCode(str, Enum):
    INVALID_TARGET = "INVALID_TARGET"
    NOT_APPROVED = "NOT_APPROVED"
    ARTIFACT_CHANGED = "ARTIFACT_CHANGED"
    MISSING_INPUT = "MISSING_INPUT"
    MISSING_ENVIRONMENT = "MISSING_ENVIRONMENT"
    SANDBOX_CREATION_FAILED = "SANDBOX_CREATION_FAILED"
    RESOURCE_POLICY_INVALID = "RESOURCE_POLICY_INVALID"
    COMMAND_NOT_ALLOWED = "COMMAND_NOT_ALLOWED"
    TIMEOUT = "TIMEOUT"
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    OUTPUT_CAPTURE_FAILED = "OUTPUT_CAPTURE_FAILED"
    WORKER_INTERRUPTED = "WORKER_INTERRUPTED"


class ExecutionPolicy(FrozenStrictModel):
    cpu_limit: float = Field(default=1.0, ge=0.1, le=4.0)
    memory_limit_mb: int = Field(default=512, ge=128, le=8192)
    runtime_limit_seconds: int = Field(default=120, ge=1, le=3600)
    process_limit: int = Field(default=32, ge=1, le=256)
    storage_limit_mb: int = Field(default=128, ge=8, le=1024)
    output_limit_mb: int = Field(default=64, ge=1, le=512)
    log_limit_kb: int = Field(default=256, ge=16, le=1024)
    network_policy: NetworkPolicy = NetworkPolicy.NETWORK_DISABLED
    gpu_policy: GpuPolicy = GpuPolicy.GPU_DISABLED
    container_image: str = "python:3.12-slim"

    @model_validator(mode="after")
    def validate_output_quota(self) -> "ExecutionPolicy":
        if self.output_limit_mb >= self.storage_limit_mb:
            raise ValueError("output_limit_mb must be smaller than storage_limit_mb")
        return self


class ExecutionApproval(FrozenStrictModel):
    approval_id: str
    target_id: str
    approver: str
    status: ApprovalStatus
    approved_at: datetime
    target_hash: str
    policy_hash: str
    artifact_hash: str
    environment_hash: str = ""
    approver_user_id: str = ""
    approver_role: str = ""
    created_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    provenance: tuple[str, ...] = ()


class ExecutionInputRecord(FrozenStrictModel):
    artifact_id: str
    name: str
    sandbox_path: str
    sha256: str
    size_bytes: int = Field(ge=0)


class ExecutionOutputRecord(FrozenStrictModel):
    name: str
    sandbox_path: str
    sha256: str
    size_bytes: int = Field(ge=0)
    output_type: str
    provenance: str
    storage_reference: str | None = None


class SandboxControls(FrozenStrictModel):
    technology: str = "DOCKER"
    image: str
    image_id: str | None = None
    root_filesystem_read_only: bool = True
    network_disabled: bool = True
    non_root_user: str = "65532:65532"
    capabilities_dropped: bool = True
    no_new_privileges: bool = True
    host_pid_namespace: bool = False
    host_ipc_namespace: bool = False
    privileged: bool = False
    gpu_exposed: bool = False


class ExecutionRecord(FrozenStrictModel):
    run_id: str
    target_id: str
    experiment_id: str
    artifact_id: str | None = None
    artifact_source: str | None = None
    artifact_commit: str | None = None
    artifact_hash: str | None = None
    target_hash: str | None = None
    environment_hash: str | None = None
    environment_id: str | None = None
    execution_type: ExecutionType = ExecutionType.ORIGINAL
    approval_id: str | None = None
    approved_by: str | None = None
    timestamp_started: datetime
    timestamp_finished: datetime
    command: str | None = None
    executable: str | None = None
    arguments: tuple[str, ...] = ()
    working_directory: str = "/workspace"
    inputs: tuple[ExecutionInputRecord, ...] = ()
    outputs: tuple[ExecutionOutputRecord, ...] = ()
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    exit_code: int | None = None
    runtime_seconds: float = Field(ge=0)
    resource_policy: ExecutionPolicy
    sandbox: SandboxControls
    status: ExecutionStatus
    failure_code: ExecutionFailureCode | None = None
    failure_reason: str | None = None
    timed_out: bool = False
    resource_limit_exceeded: bool = False
    provenance: tuple[str, ...] = ()
    observed_result: ObservedResult | None = None
    comparison: dict | None = None


class ApprovalRequest(FrozenStrictModel):
    approver: str | None = Field(default=None, max_length=200)
    policy: ExecutionPolicy = Field(default_factory=ExecutionPolicy)


class ExecuteRequest(FrozenStrictModel):
    approval_id: str = Field(min_length=1)
    policy: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
