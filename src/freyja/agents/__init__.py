"""Public exports for the Agent Smith maintenance orchestrator."""

from freyja.tools.builtin import register_smith_read_only_tools

from .models import (
    ApprovalStatus,
    AuditEvent,
    PolicyCheckResult,
    PolicyDecision,
    SmithPlan,
    SmithRunSummary,
    SmithStepResult,
    SmithTask,
    TaskStatus,
)
from .policy import AgentPolicy
from .smith import PolicyViolationError, SmithOrchestrator, ToolInvocationError


def register_smith_tools(registry) -> None:
    """Register only the Smith-specific read-only tools."""
    register_smith_read_only_tools(registry)


__all__ = [
    "AgentPolicy",
    "ApprovalStatus",
    "AuditEvent",
    "PolicyCheckResult",
    "PolicyDecision",
    "PolicyViolationError",
    "SmithOrchestrator",
    "SmithPlan",
    "SmithRunSummary",
    "SmithStepResult",
    "SmithTask",
    "TaskStatus",
    "ToolInvocationError",
    "register_smith_tools",
]
