"""Public exports for the Agent Smith maintenance orchestrator."""

from freyja.tools.builtin import register_smith_read_only_tools, register_smith_write_pilot_tools
from freyja.tools.iris_maintenance import register_smith_controlled_tools

from .models import (
    ApprovalCallback,
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
    WritePilotRequest,
    WritePilotResult,
    WritePilotState,
)
from .policy import AgentPolicy
from .runtime import SmithRuntime
from .smith import PolicyViolationError, SmithOrchestrator, ToolInvocationError


def register_smith_tools(registry) -> None:
    """Register Smith read-only, controlled maintenance, and write-pilot tools."""
    register_smith_read_only_tools(registry)
    register_smith_controlled_tools(registry)
    register_smith_write_pilot_tools(registry)


__all__ = [
    "AgentPolicy",
    "ApprovalCallback",
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
    "WritePilotRequest",
    "WritePilotResult",
    "WritePilotState",
    "register_smith_tools",
]
