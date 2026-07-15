"""Pydantic models for Agent Smith task orchestration and audit records."""

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"
    APPROVAL_REQUIRED = "approval_required"


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SmithRunSummary(BaseModel):
    request_id: str
    objective: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    escalated_tasks: int
    approval_required_count: int
    status: str
    message: str
    audit_records: list[dict[str, Any]] = Field(default_factory=list)
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
