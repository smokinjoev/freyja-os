"""Public exports for the Agent Smith maintenance orchestrator."""

from freyja.tools.builtin import register_smith_read_only_tools, register_smith_write_pilot_tools
from freyja.tools.iris_maintenance import register_smith_controlled_tools

from .coder_access import CloydCoderRuntime, CoderAccessDecision, CoderAccessPolicy
from .household import HouseholdAgent, HouseholdAgentRegistry, household_agents

from .device_trust import DeviceCredentialKind, DeviceRegistry, TrustedDevice

from .hierarchy import (
    AgentHierarchy,
    AgentName,
    EscalationTarget,
    MaintenanceAuthority,
    MaintenanceRequest,
    MaintenanceResult,
    PersonalAgentMessage,
    PersonName,
)

from .models import (
    ApprovalCallback,
    ApprovalRecord,
    ApprovalRecordStatus,
    ApprovalStatus,
    ApprovalStoreError,
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
from .personal_data import (
    PersonalDataAction,
    PersonalDataAuthorization,
    PersonalDataDecision,
    PersonalDataPrincipal,
    PersonalDataResource,
    PersonalDataScope,
)
from .runtime import SmithRuntime
from .smith import PolicyViolationError, SmithOrchestrator, ToolInvocationError


def register_smith_tools(registry) -> None:
    """Register Smith read-only, controlled maintenance, and write-pilot tools."""
    register_smith_read_only_tools(registry)
    register_smith_controlled_tools(registry)
    register_smith_write_pilot_tools(registry)


__all__ = [
    "AgentHierarchy",
    "AgentName",
    "AgentPolicy",
    "CloydCoderRuntime",
    "CoderAccessDecision",
    "CoderAccessPolicy",
    "HouseholdAgent",
    "HouseholdAgentRegistry",
    "ApprovalCallback",
    "ApprovalRecord",
    "ApprovalRecordStatus",
    "ApprovalStatus",
    "ApprovalStoreError",
    "AuditEvent",
    "DeviceCredentialKind",
    "DeviceRegistry",
    "EscalationTarget",
    "MaintenanceAuthority",
    "MaintenanceRequest",
    "MaintenanceResult",
    "ObjectiveClass",
    "PolicyCheckResult",
    "PolicyDecision",
    "PolicyViolationError",
    "PersonalAgentMessage",
    "PersonName",
    "PersonalDataAction",
    "PersonalDataAuthorization",
    "PersonalDataDecision",
    "PersonalDataPrincipal",
    "PersonalDataResource",
    "PersonalDataScope",
    "SmithOrchestrator",
    "SmithPlan",
    "SmithRunSummary",
    "SmithRuntime",
    "SmithStepResult",
    "SmithTask",
    "TaskStatus",
    "ToolInvocationError",
    "TrustedDevice",
    "WritePilotRequest",
    "WritePilotResult",
    "WritePilotState",
    "household_agents",
    "register_smith_tools",
]
