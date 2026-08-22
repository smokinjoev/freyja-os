from __future__ import annotations

from dataclasses import dataclass
import uuid
from typing import Any

from freyja.tools.builtin import register_smith_read_only_tools, register_smith_write_pilot_tools
from freyja.tools.iris_maintenance import register_smith_controlled_tools
from freyja.tools.models import ToolExecutionRequest, ToolExecutionResult
from freyja.tools.registry import ToolRegistry, get_registry

from .household import HouseholdAgentRegistry, household_agents


CODER_TOOL_CAPABILITIES: dict[str, str] = {
    "repository_status": "code.inspect",
    "repository_diff_summary": "code.diff",
    "run_test_suite": "code.test",
    "compile_project": "code.test",
    "validate_diff": "code.diff",
    "bounded_file_write": "code.edit",
    "git_add": "code.commit",
    "git_commit": "code.commit",
    "write_pilot_file_write": "code.edit",
    "write_pilot_git_add": "code.commit",
    "write_pilot_git_commit": "code.commit",
}

CODER_WRITE_TOOLS = frozenset(
    {
        "bounded_file_write",
        "git_add",
        "git_commit",
        "write_pilot_file_write",
        "write_pilot_git_add",
        "write_pilot_git_commit",
    }
)

_CODING_PHRASES = (
    "write code",
    "edit the code",
    "change the code",
    "fix the code",
    "fix this test",
    "fix the test",
    "run pytest",
    "run the tests",
    "compile the project",
    "inspect the repo",
    "inspect the repository",
    "repository status",
    "review the diff",
    "validate the diff",
    "debug this",
    "refactor",
    "implement ",
    "patch ",
)


def is_coding_request(text: str) -> bool:
    """Conservative deterministic entry gate for Cloyd's local coding loop."""
    normalized = " ".join(text.lower().split())
    if any(phrase in normalized for phrase in _CODING_PHRASES):
        return True
    return normalized.startswith(("code:", "coder:", "cloyd, code", "cloyd code"))


@dataclass(frozen=True)
class CoderAccessDecision:
    allowed: bool
    capability: str | None = None
    approval_required: bool = False
    reason: str = ""


class CoderAccessPolicy:
    """Agent-level gate in front of the existing bounded repository tools."""

    def __init__(self, agents: HouseholdAgentRegistry | None = None) -> None:
        self._agents = agents or household_agents

    def authorize(
        self,
        *,
        agent_id: str,
        tool_name: str,
        approval_granted: bool = False,
    ) -> CoderAccessDecision:
        profile = next(
            (agent for agent in self._agents.all() if agent.agent_id == agent_id),
            None,
        )
        if profile is None:
            return CoderAccessDecision(False, reason="unknown agent")

        capability = CODER_TOOL_CAPABILITIES.get(tool_name)
        if capability is None:
            return CoderAccessDecision(False, reason="tool is not a coder module")
        if not profile.allows(capability):
            return CoderAccessDecision(
                False,
                capability=capability,
                reason=f"agent lacks {capability}",
            )

        approval_required = tool_name in CODER_WRITE_TOOLS
        if approval_required and not approval_granted:
            return CoderAccessDecision(
                False,
                capability=capability,
                approval_required=True,
                reason="explicit approval required for repository changes",
            )

        return CoderAccessDecision(
            True,
            capability=capability,
            approval_required=approval_required,
            reason="agent capability and approval policy satisfied",
        )


class CloydCoderRuntime:
    """Execute existing local coder modules only after Cloyd-specific policy."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        policy: CoderAccessPolicy | None = None,
    ) -> None:
        self._registry = registry or get_registry()
        register_smith_read_only_tools(self._registry)
        register_smith_write_pilot_tools(self._registry)
        register_smith_controlled_tools(self._registry)
        self._policy = policy or CoderAccessPolicy()

    async def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        request_id: str | None = None,
        approval_granted: bool = False,
    ) -> ToolExecutionResult:
        effective_request_id = request_id or str(uuid.uuid4())
        decision = self._policy.authorize(
            agent_id="cloyd-gibbler",
            tool_name=tool_name,
            approval_granted=approval_granted,
        )
        if not decision.allowed:
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                error_code="approval_required" if decision.approval_required else "authorization_denied",
                public_error_message=decision.reason,
                request_id=effective_request_id,
            )

        definition = self._registry.get_tool(tool_name)
        if definition is None:
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                error_code="tool_not_found",
                public_error_message="Coder module is not registered.",
                request_id=effective_request_id,
            )

        request = ToolExecutionRequest(
            tool_name=tool_name,
            arguments=arguments or {},
            request_id=effective_request_id,
            actor="cloyd-gibbler",
            metadata={
                "agent_id": "cloyd-gibbler",
                "person": {"person_id": "joe"},
                "director_authorized": True,
                "approval_granted": approval_granted,
                "coder_capability": decision.capability,
                "local_only": True,
            },
        )
        registry_decision = self._registry.authorize(definition, request)
        if not registry_decision.allowed:
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                error_code="authorization_denied",
                public_error_message="Coder module authorization denied.",
                request_id=effective_request_id,
            )
        return await self._registry.execute(request)
