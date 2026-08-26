from __future__ import annotations

from collections.abc import Iterable

from freyja.foundation_models import (
    AgentExecutionResult,
    AgentStep,
    AuditEvent,
    AuditEventType,
    GatewayHandoff,
    MemoryClassification,
    PersistentAgent,
    ToolCapabilityGrant,
)
from freyja.foundation_seed import PERSISTENT_AGENTS, TOOL_CAPABILITIES, agents_by_key, tools_by_id
from freyja.inference_registry_v3 import InferenceRegistryV3
from freyja.privacy_egress import PrivacyEgressGate


class MemoryBoundaryError(PermissionError):
    pass


class AgentRuntimeV3:
    """Persistent agent runtime contract for Freyja 3.

    The gateway has already selected an agent. This runtime receives the raw
    natural-language objective and makes agent-owned decisions about tools and
    inference capabilities.
    """

    def __init__(
        self,
        *,
        agents: tuple[PersistentAgent, ...] = PERSISTENT_AGENTS,
        tools: tuple[ToolCapabilityGrant, ...] = TOOL_CAPABILITIES,
        inference_registry: InferenceRegistryV3 | None = None,
        egress_gate: PrivacyEgressGate | None = None,
        unhealthy_endpoint_ids: Iterable[str] = (),
    ) -> None:
        self._agents = agents_by_key() if agents == PERSISTENT_AGENTS else self._index_agents(agents)
        self._tools = tools_by_id() if tools == TOOL_CAPABILITIES else {tool.tool_id: tool for tool in tools}
        self._inference_registry = inference_registry or InferenceRegistryV3()
        self._egress_gate = egress_gate or PrivacyEgressGate()
        self._unhealthy_endpoint_ids = set(unhealthy_endpoint_ids)

    def run(self, handoff: GatewayHandoff) -> AgentExecutionResult:
        agent = self._agent(handoff.target_agent_id)
        selected_tools = self.choose_tools(agent, handoff.prompt, handoff.available_tools)
        capability = self.choose_inference_capability(handoff.prompt, bool(handoff.attachments))
        endpoint = self._first_healthy_endpoint(agent, capability)
        steps: list[AgentStep] = [
            AgentStep(kind="objective_received", detail=handoff.prompt),
        ]
        audit_events: list[AuditEvent] = [
            AuditEvent(
                event_type=AuditEventType.AGENT_RUN_STARTED,
                actor_id=f"agent:{agent.agent_id}",
                domain_id=agent.security_domain_id,
                target_id=handoff.conversation_id,
                allowed=True,
                reason="agent received gateway handoff",
            )
        ]
        for tool_id in selected_tools:
            steps.append(AgentStep(kind="tool_selected", detail=f"{agent.agent_id} selected {tool_id}", tool_id=tool_id))
            audit_events.append(
                AuditEvent(
                    event_type=AuditEventType.AGENT_TOOL_SELECTED,
                    actor_id=f"agent:{agent.agent_id}",
                    domain_id=agent.security_domain_id,
                    target_id=tool_id,
                    allowed=True,
                    reason="agent selected permitted tool",
                )
            )

        inference_endpoint_id = None
        inference_model = None
        inference_machine_id = None
        degraded = False
        if endpoint is not None:
            inference_endpoint_id = endpoint.endpoint_id
            inference_model = endpoint.model or None
            inference_machine_id = endpoint.machine_id
            steps.append(
                AgentStep(
                    kind="inference_selected",
                    detail=f"{agent.agent_id} selected compute capability {capability}",
                    inference_endpoint_id=endpoint.endpoint_id,
                )
            )
            audit_events.append(
                AuditEvent(
                    event_type=AuditEventType.AGENT_INFERENCE_SELECTED,
                    actor_id=f"agent:{agent.agent_id}",
                    domain_id=agent.security_domain_id,
                    target_id=endpoint.endpoint_id,
                    allowed=True,
                    reason="agent selected endpoint from compute registry",
                )
            )
        else:
            degraded = True
            steps.append(AgentStep(kind="inference_unavailable", detail=f"no healthy endpoint for {capability}", success=False))

        response = self._compose_response(agent, handoff, selected_tools, inference_endpoint_id, degraded)
        return AgentExecutionResult(
            trace_id=handoff.handoff_id,
            agent_id=agent.agent_id,
            conversation_id=handoff.conversation_id,
            response_text=response,
            selected_tools=tuple(selected_tools),
            inference_endpoint_id=inference_endpoint_id,
            inference_model=inference_model,
            inference_machine_id=inference_machine_id,
            steps=tuple(steps),
            audit_events=tuple(audit_events),
            degraded=degraded,
        )

    def choose_tools(
        self,
        agent: PersistentAgent,
        objective: str,
        available_tool_ids: Iterable[str],
    ) -> list[str]:
        allowed = set(agent.tool_grants).intersection(set(available_tool_ids))
        lowered = objective.lower()
        candidates: list[str] = []
        rules = (
            ("web.search", ("search", "look up", "latest", "current")),
            ("weather.current", ("weather", "forecast", "temperature")),
            ("calendar.read", ("calendar", "schedule", "appointment")),
            ("email.read", ("email", "mail")),
            ("messaging.send", ("message", "imessage", "text ", "sms")),
            ("home-assistant.control", ("light", "home assistant", "thermostat", "door", "lock")),
            ("macagent.apple", ("mac", "finder", "safari", "shortcut", "apple")),
            ("shell.run", ("shell", "command", "terminal")),
            ("filesystem.read", ("file", "folder", "repo", "inspect")),
            ("filesystem.write", ("edit", "write", "patch", "create file")),
            ("git.inspect", ("git", "diff", "status", "commit")),
            ("coding.execute", ("code", "test", "build", "bug")),
            ("documents.process", ("pdf", "document", "docx")),
            ("vision.inspect", ("photo", "image", "picture", "see this")),
            ("music.control", ("music", "song", "playlist")),
            ("scheduling.create", ("remind", "schedule this", "timer")),
            ("memory.private", ("remember", "what do you know")),
            ("memory.shared", ("family", "household")),
        )
        for tool_id, terms in rules:
            if tool_id in allowed and any(term in lowered for term in terms):
                candidates.append(tool_id)
        return candidates

    def choose_inference_capability(self, objective: str, has_attachments: bool = False) -> str:
        lowered = objective.lower()
        if has_attachments or any(term in lowered for term in ("photo", "image", "picture")):
            return "vision.large"
        if any(term in lowered for term in ("code", "test", "build", "repo", "git")):
            return "code.large"
        return "general.large"

    def evaluate_cloud_request(
        self,
        *,
        agent_id: str,
        prompt: str,
        destination_provider: str = "openrouter",
        classification: MemoryClassification | None = None,
    ):
        return self._egress_gate.evaluate(
            agent=self._agent(agent_id),
            prompt=prompt,
            destination_provider=destination_provider,
            requested_classification=classification,
        )

    def assert_memory_read_allowed(self, agent_id: str, memory_scope: str) -> None:
        agent = self._agent(agent_id)
        if memory_scope == agent.private_memory_scope or memory_scope in agent.shared_memory_scopes:
            return
        raise MemoryBoundaryError(f"{agent.agent_id} cannot read memory scope {memory_scope}")

    def _first_healthy_endpoint(self, agent: PersistentAgent, capability: str):
        for endpoint in self._inference_registry.endpoints_for(capability=capability, domain_id=agent.security_domain_id):
            if endpoint.endpoint_id not in self._unhealthy_endpoint_ids:
                return endpoint
        for fallback in agent.default_inference_capabilities:
            if fallback == capability:
                continue
            for endpoint in self._inference_registry.endpoints_for(capability=fallback, domain_id=agent.security_domain_id):
                if endpoint.endpoint_id not in self._unhealthy_endpoint_ids:
                    return endpoint
        return None

    def _agent(self, agent_id: str) -> PersistentAgent:
        return self._agents[agent_id]

    @staticmethod
    def _compose_response(
        agent: PersistentAgent,
        handoff: GatewayHandoff,
        selected_tools: list[str],
        endpoint_id: str | None,
        degraded: bool,
    ) -> str:
        if degraded:
            return f"{agent.display_name} received the objective, but no healthy local inference endpoint is available."
        tool_text = ", ".join(selected_tools) if selected_tools else "no tools"
        return f"{agent.display_name} received the objective and selected {tool_text} using {endpoint_id}."

    @staticmethod
    def _index_agents(agents: tuple[PersistentAgent, ...]) -> dict[str, PersistentAgent]:
        indexed: dict[str, PersistentAgent] = {}
        for agent in agents:
            indexed[agent.agent_id] = agent
        return indexed
