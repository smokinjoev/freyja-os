"""Public exports for the Agent Smith maintenance orchestrator."""

from freyja.tools.builtin import register_smith_read_only_tools
from freyja.tools.iris_maintenance import register_smith_controlled_tools

from .models import (
    ApprovalStatus,
    AuditEvent,
    ObjectiveClass,
    PolicyCheckResult,
    PolicyDecision,
    SmithPlan,
    SmithRunSummary,
    SmithStepResult,
    SmithTask,
    TaskStatus,
)
from .policy import AgentPolicy
from .runtime import SmithRuntime
from .smith import PolicyViolationError, SmithOrchestrator, ToolInvocationError


def register_smith_tools(registry) -> None:
    """Register Smith read-only and controlled maintenance tools."""
    register_smith_read_only_tools(registry)
    register_smith_controlled_tools(registry)


__all__ = [
    "AgentPolicy",
    "ApprovalStatus",
    "AuditEvent",
    "ObjectiveClass",
    "PolicyCheckResult",
    "PolicyDecision",
    "PolicyViolationError",
    "SmithOrchestrator",
    "SmithPlan",
    "SmithRunSummary",
    "SmithRuntime",
    "SmithStepResult",
    "SmithTask",
    "TaskStatus",
    "ToolInvocationError",
    "register_smith_tools",
]
