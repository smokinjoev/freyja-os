"""Pydantic models for Agent Smith task orchestration and audit records."""

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ObjectiveClass(StrEnum):
    INSPECTION = "inspection"
    VALIDATION = "validation"
    DIAGNOSTICS = "diagnostics"
    PROHIBITED_WRITE = "prohibited_write"
    PROHIBITED_PRIVILEGED = "prohibited_privileged"
    AMBIGUOUS = "ambiguous"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"
    APPROVAL_REQUIRED = "approval_required"
    LOOP_DETECTED = "loop_detected"


class WritePilotState(StrEnum):
    PLANNED = "planned"
    AWAITING_PATH_APPROVAL = "awaiting_path_approval"
    AWAITING_CONTENT_APPROVAL = "awaiting_content_approval"
    WRITTEN = "written"
    VALIDATED = "validated"
    AWAITING_STAGE_APPROVAL = "awaiting_stage_approval"
    STAGED = "staged"
    AWAITING_COMMIT_APPROVAL = "awaiting_commit_approval"
    COMMITTED = "committed"
    VERIFIED = "verified"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ApprovalStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    REQUESTED = "requested"
    APPROVED = "approved"
    DENIED = "denied"


class SmithTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    request_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class SmithPlan(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    objective: str
    tasks: list[SmithTask] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def pending_tasks(self) -> list[SmithTask]:
        return [task for task in self.tasks if task.status == TaskStatus.PENDING]

    def next_runnable_task(self) -> SmithTask | None:
        completed = {task.id for task in self.tasks if task.status == TaskStatus.COMPLETED}
        for task in self.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            if all(dep in completed for dep in task.depends_on):
                return task
        return None

    def is_complete(self) -> bool:
        return all(
            task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ESCALATED}
            for task in self.tasks
        )


class SmithStepResult(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    request_id: str
    tool_name: str | None = None
    success: bool = True
    retryable: bool = False
    attempts: int = 1
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    approval_required: bool = False
    audit_record: dict[str, Any] | None = None
    duration_ms: int | None = None
    actor: str = "agent_smith"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WritePilotRequest(BaseModel):
    objective: str
    target_path: str
    proposed_content: str
    commit_message: str
    actor: str = "agent_smith"
    request_id: str | None = None


class WritePilotStateTransition(BaseModel):
    from_state: str
    to_state: str
    action: str
    outcome: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WritePilotApprovalRecord(BaseModel):
    approval_type: str
    request_id: str
    target_path: str | None = None
    approved: bool
    actor: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovalCallback:
    """One-time approval token returned by an approval callback."""

    def __init__(
        self,
        approval_type: str,
        request_id: str,
        approved: bool,
        target_path: str | None = None,
        commit_message: str | None = None,
    ) -> None:
        self.approval_type = approval_type
        self.request_id = request_id
        self.approved = approved
        self.target_path = target_path
        self.commit_message = commit_message


class WritePilotResult(BaseModel):
    request_id: str
    status: str
    state: str = "planned"
    message: str
    objective: str
    target_path: str
    wrote_content: bool = False
    staged: bool = False
    committed: bool = False
    rolled_back: bool = False
    commit_hash: str | None = None
    original_content: str | None = None
    final_content: str | None = None
    diff: str | None = None
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    state_transitions: list[dict[str, Any]] = Field(default_factory=list)
    audit_records: list[dict[str, Any]] = Field(default_factory=list)
    actor: str = "agent_smith"
    duration_ms: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SmithRunSummary(BaseModel):
    request_id: str
    objective: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    escalated_tasks: int
    approval_required_count: int
    loop_detected_count: int = 0
    status: str
    message: str
    audit_records: list[dict[str, Any]] = Field(default_factory=list)
    actor: str = "agent_smith"
    duration_ms: int | None = None
    metadata: dict[str, Any] | None = None
    plan: SmithPlan | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    APPROVE = "approve"
    DENY = "deny"


class PolicyCheckResult(BaseModel):
    decision: PolicyDecision
    reason: str | None = None
    approval_required: bool = False
    audit_record: dict[str, Any] | None = None


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    actor: str = "agent_smith"
    action: str
    outcome: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
