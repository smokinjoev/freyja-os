from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable
from typing import Any

from freyja.foundation_models import (
    AgentExecutionResult,
    AgentStep,
    AuditEvent,
    AuditEventType,
    GatewayHandoff,
    MemoryClassification,
    MemoryScope,
    PersistentAgent,
    SecurityDomainId,
    ToolCapabilityGrant,
)
from freyja.foundation_seed import PERSISTENT_AGENTS, TOOL_CAPABILITIES, agents_by_key, tools_by_id
from freyja.freyja3_memory import Freyja3MemoryQuery, Freyja3MemoryStore, Freyja3MemoryWrite
from freyja.inference_registry_v3 import InferenceRegistryV3
from freyja.ollama_client import OllamaClient
from freyja.privacy_egress import PrivacyEgressGate
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.registry import ToolRegistry


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
        tool_registry: ToolRegistry | None = None,
        memory_store: Freyja3MemoryStore | None = None,
        execute_tools: bool | None = None,
        use_memory: bool | None = None,
        run_inference: bool | None = None,
        unhealthy_endpoint_ids: Iterable[str] = (),
    ) -> None:
        self._agents = agents_by_key() if agents == PERSISTENT_AGENTS else self._index_agents(agents)
        self._tools = tools_by_id() if tools == TOOL_CAPABILITIES else {tool.tool_id: tool for tool in tools}
        self._inference_registry = inference_registry or InferenceRegistryV3()
        self._egress_gate = egress_gate or PrivacyEgressGate()
        self._tool_registry = tool_registry
        self._memory_store = memory_store
        self._execute_tools = tool_registry is not None if execute_tools is None else execute_tools
        self._use_memory = memory_store is not None if use_memory is None else use_memory
        self._run_inference = run_inference if run_inference is not None else False
        self._unhealthy_endpoint_ids = set(unhealthy_endpoint_ids)

    def run(self, handoff: GatewayHandoff) -> AgentExecutionResult:
        return asyncio.run(self.arun(handoff))

    async def arun(self, handoff: GatewayHandoff) -> AgentExecutionResult:
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
        recalled_memories = self._recall_memories(agent, steps, audit_events)
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

        tool_results = await self._execute_selected_tools(agent, handoff, selected_tools, steps, audit_events)

        inference_endpoint_id = None
        inference_model = None
        inference_machine_id = None
        inference_status = None
        inference_text = None
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
            inference_status, inference_text = await self._run_selected_inference(
                agent=agent,
                handoff=handoff,
                endpoint_id=endpoint.endpoint_id,
                endpoint_provider=endpoint.provider,
                base_url=endpoint.base_url,
                model=endpoint.model,
                tool_results=tool_results,
            )
            steps.append(
                AgentStep(
                    kind="inference_completed",
                    detail=f"{endpoint.endpoint_id} returned {inference_status}",
                    inference_endpoint_id=endpoint.endpoint_id,
                    success=inference_status == "ok",
                )
            )
            audit_events.append(
                AuditEvent(
                    event_type=AuditEventType.AGENT_INFERENCE_COMPLETED,
                    actor_id=f"agent:{agent.agent_id}",
                    domain_id=agent.security_domain_id,
                    target_id=endpoint.endpoint_id,
                    allowed=inference_status == "ok",
                    reason=f"inference {inference_status}",
                )
            )
        else:
            degraded = True
            steps.append(AgentStep(kind="inference_unavailable", detail=f"no healthy endpoint for {capability}", success=False))

        written_memories = self._write_agent_memories(agent, handoff, selected_tools, tool_results, steps, audit_events)
        response = self._compose_response(
            agent,
            handoff,
            selected_tools,
            tool_results,
            recalled_memories,
            inference_endpoint_id,
            inference_text,
            degraded,
        )
        return AgentExecutionResult(
            trace_id=handoff.handoff_id,
            agent_id=agent.agent_id,
            conversation_id=handoff.conversation_id,
            response_text=response,
            selected_tools=tuple(selected_tools),
            tool_results=tuple(tool_results),
            recalled_memories=tuple(recalled_memories),
            written_memories=tuple(written_memories),
            inference_endpoint_id=inference_endpoint_id,
            inference_model=inference_model,
            inference_machine_id=inference_machine_id,
            inference_status=inference_status,
            steps=tuple(steps),
            audit_events=tuple(audit_events),
            degraded=degraded,
        )

    def _recall_memories(
        self,
        agent: PersistentAgent,
        steps: list[AgentStep],
        audit_events: list[AuditEvent],
    ) -> list[dict[str, Any]]:
        if not self._use_memory or self._memory_store is None:
            return []
        records = []
        for domain_id, scope in self._agent_memory_queries(agent):
            records.extend(
                self._memory_store.list(
                    Freyja3MemoryQuery(owner_domain_id=domain_id, scope=scope, limit=8),
                    reader_domain_id=agent.security_domain_id,
                )
            )
        public_records = [record.model_dump(mode="json") for record in records]
        steps.append(AgentStep(kind="memory_recalled", detail=f"recalled {len(public_records)} scoped memory record(s)", success=True))
        audit_events.append(
            AuditEvent(
                event_type=AuditEventType.AGENT_MEMORY_RECALLED,
                actor_id=f"agent:{agent.agent_id}",
                domain_id=agent.security_domain_id,
                target_id=agent.agent_id,
                allowed=True,
                reason="agent recalled permitted Freyja 3 memory scopes",
                metadata={"count": len(public_records)},
            )
        )
        return public_records

    def _write_agent_memories(
        self,
        agent: PersistentAgent,
        handoff: GatewayHandoff,
        selected_tools: list[str],
        tool_results: list[dict[str, Any]],
        steps: list[AgentStep],
        audit_events: list[AuditEvent],
    ) -> list[dict[str, Any]]:
        if not self._use_memory or self._memory_store is None:
            return []
        written = []
        explicit_memory = _explicit_memory_content(handoff.prompt)
        if explicit_memory:
            written.append(
                self._memory_store.put(
                    Freyja3MemoryWrite(
                        owner_domain_id=agent.security_domain_id,
                        scope=MemoryScope.PERSONAL
                        if agent.security_domain_id != SecurityDomainId.HOUSEHOLD
                        else MemoryScope.HOUSEHOLD,
                        source_agent_id=agent.agent_id,
                        content=explicit_memory,
                        provenance="agent-runtime-v3-explicit-remember",
                        classification=_memory_classification_for_text(explicit_memory),
                        metadata={"conversation_id": handoff.conversation_id, "handoff_id": handoff.handoff_id},
                    ),
                    writer_domain_id=agent.security_domain_id,
                ).model_dump(mode="json")
            )
            steps.append(AgentStep(kind="memory_written", detail="wrote explicit Freyja 3 memory", success=True))
            audit_events.append(
                AuditEvent(
                    event_type=AuditEventType.AGENT_MEMORY_WRITTEN,
                    actor_id=f"agent:{agent.agent_id}",
                    domain_id=agent.security_domain_id,
                    target_id=written[-1]["memory_id"],
                    allowed=True,
                    reason="agent wrote explicit Freyja 3 memory",
                )
            )

        failed_tools = [result["capability_id"] for result in tool_results if result.get("success") is False]
        content = (
            f"Conversation {handoff.conversation_id}: selected {', '.join(selected_tools) if selected_tools else 'no tools'}"
            f"; failed tools: {', '.join(failed_tools) if failed_tools else 'none'}."
        )
        record = self._memory_store.put(
            Freyja3MemoryWrite(
                owner_domain_id=agent.security_domain_id,
                scope=MemoryScope.PERSONAL if agent.security_domain_id != SecurityDomainId.HOUSEHOLD else MemoryScope.HOUSEHOLD,
                source_agent_id=agent.agent_id,
                content=content,
                provenance="agent-runtime-v3",
                classification=MemoryClassification.ROUTINE,
                metadata={"conversation_id": handoff.conversation_id, "handoff_id": handoff.handoff_id},
            ),
            writer_domain_id=agent.security_domain_id,
        )
        public = record.model_dump(mode="json")
        written.append(public)
        steps.append(AgentStep(kind="memory_written", detail="wrote Freyja 3 run summary memory", success=True))
        audit_events.append(
            AuditEvent(
                event_type=AuditEventType.AGENT_MEMORY_WRITTEN,
                actor_id=f"agent:{agent.agent_id}",
                domain_id=agent.security_domain_id,
                target_id=record.memory_id,
                allowed=True,
                reason="agent wrote Freyja 3 run summary memory",
            )
        )
        return written

    @staticmethod
    def _agent_memory_queries(agent: PersistentAgent) -> list[tuple[SecurityDomainId, MemoryScope]]:
        queries = [(agent.security_domain_id, MemoryScope.PERSONAL)]
        if {"family", "household", "household:shared"}.intersection(agent.shared_memory_scopes):
            queries.append((SecurityDomainId.HOUSEHOLD, MemoryScope.HOUSEHOLD))
        if agent.security_domain_id == SecurityDomainId.HOUSEHOLD:
            queries = [(SecurityDomainId.HOUSEHOLD, MemoryScope.HOUSEHOLD)]
        return queries

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

    async def _execute_selected_tools(
        self,
        agent: PersistentAgent,
        handoff: GatewayHandoff,
        selected_tools: list[str],
        steps: list[AgentStep],
        audit_events: list[AuditEvent],
    ) -> list[dict[str, Any]]:
        if not self._execute_tools or self._tool_registry is None:
            return []
        results: list[dict[str, Any]] = []
        for capability_id in selected_tools:
            tool_name = _CONCRETE_TOOL_BY_CAPABILITY.get(capability_id)
            if tool_name is None:
                continue
            request = ToolExecutionRequest(
                tool_name=tool_name,
                arguments=self._arguments_for_tool(capability_id, handoff.prompt, handoff),
                actor=f"agent:{agent.agent_id}",
                conversation_id=handoff.conversation_id,
                metadata={
                    "agent_id": agent.agent_id,
                    "source_domain_id": handoff.source_domain_id.value,
                    "target_domain_id": handoff.target_domain_id.value,
                    "director_authorized": True,
                    "person": _person_metadata(handoff.source_domain_id),
                    "memory_principal": _memory_principal_metadata(handoff),
                },
            )
            result = await self._tool_registry.execute(request)
            success = _tool_effective_success(result.success, result.output)
            public_result = {
                "capability_id": capability_id,
                "tool_name": tool_name,
                "success": success,
                "error_code": result.error_code,
                "public_error_message": result.public_error_message,
                "output": result.output,
            }
            results.append(public_result)
            steps.append(
                AgentStep(
                    kind="tool_executed",
                    detail=f"{tool_name} executed for {capability_id}",
                    tool_id=capability_id,
                    success=success,
                )
            )
            audit_events.append(
                AuditEvent(
                    event_type=AuditEventType.AGENT_TOOL_EXECUTED,
                    actor_id=f"agent:{agent.agent_id}",
                    domain_id=agent.security_domain_id,
                    target_id=tool_name,
                    allowed=success,
                    reason=result.public_error_message or "tool execution completed",
                )
            )
        return results

    async def _run_selected_inference(
        self,
        *,
        agent: PersistentAgent,
        handoff: GatewayHandoff,
        endpoint_id: str,
        endpoint_provider: str,
        base_url: str,
        model: str,
        tool_results: list[dict[str, Any]],
    ) -> tuple[str, str | None]:
        if not self._run_inference:
            return "not_run", None
        if endpoint_provider != "ollama":
            return "unsupported_provider", None
        prompt = self._inference_prompt(agent, handoff, tool_results)
        response = await OllamaClient(base_url=base_url, model=model).chat(prompt=prompt, model=model)
        if "error" in response:
            return "error", None
        return "ok", str(response.get("message", {}).get("content") or "").strip() or None

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
        tool_results: list[dict[str, Any]],
        recalled_memories: list[dict[str, Any]],
        endpoint_id: str | None,
        inference_text: str | None,
        degraded: bool,
    ) -> str:
        if degraded:
            return f"{agent.display_name} received the objective, but no healthy local inference endpoint is available."
        if inference_text:
            return inference_text
        tool_text = ", ".join(selected_tools) if selected_tools else "no tools"
        executed = [result for result in tool_results if result.get("success") is True]
        execution_text = f" and executed {len(executed)} tool(s)" if tool_results else ""
        memory_text = f" with {len(recalled_memories)} recalled memory record(s)" if recalled_memories else ""
        return f"{agent.display_name} received the objective and selected {tool_text}{execution_text}{memory_text} using {endpoint_id}."

    @staticmethod
    def _arguments_for_tool(capability_id: str, objective: str, handoff: GatewayHandoff) -> dict[str, Any]:
        if capability_id == "web.search":
            return {"query": objective, "max_results": 3}
        if capability_id == "weather.current":
            return {"location": "Aiken, South Carolina", "request_type": "current"}
        if capability_id == "memory.private":
            return {"conversation_id": handoff.conversation_id, "limit": 10}
        if capability_id == "memory.shared":
            return {"query": objective, "limit": 5}
        return {}

    @staticmethod
    def _inference_prompt(agent: PersistentAgent, handoff: GatewayHandoff, tool_results: list[dict[str, Any]]) -> str:
        return (
            f"You are {agent.display_name}, a persistent Freyja 3 agent. "
            "Answer the user's objective using only the supplied context.\n\n"
            f"Objective: {handoff.prompt}\n\n"
            f"Tool results: {tool_results}"
        )

    @staticmethod
    def _index_agents(agents: tuple[PersistentAgent, ...]) -> dict[str, PersistentAgent]:
        indexed: dict[str, PersistentAgent] = {}
        for agent in agents:
            indexed[agent.agent_id] = agent
        return indexed


_CONCRETE_TOOL_BY_CAPABILITY = {
    "web.search": "web_search",
    "weather.current": "get_weather",
    "macagent.apple": "macagent_health",
    "home-assistant.control": "home_assistant_list_states",
    "git.inspect": "repository_status",
    "memory.private": "recall_conversation",
    "memory.shared": "memory_recall_shared",
}


def _person_metadata(domain_id) -> dict[str, str]:
    value = str(domain_id.value)
    if value.startswith("person."):
        return {"person_id": value.removeprefix("person.")}
    return {"person_id": "family"}


def _memory_principal_metadata(handoff: GatewayHandoff) -> dict[str, str]:
    return {
        "client_type": handoff.channel or "gateway",
        "client_subject": handoff.sender_id,
    }


def _tool_effective_success(registry_success: bool, output: dict[str, Any]) -> bool:
    if not registry_success:
        return False
    if isinstance(output.get("success"), bool):
        return bool(output["success"])
    if output.get("error"):
        return False
    if output.get("live_data_available") is False:
        return False
    return True


_EXPLICIT_MEMORY_RE = re.compile(
    r"^\s*(?:please\s+)?remember(?:\s+that|\s+this)?\s+(?P<content>.+?)\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _explicit_memory_content(objective: str) -> str | None:
    match = _EXPLICIT_MEMORY_RE.match(objective)
    if not match:
        return None
    content = " ".join(match.group("content").split())
    return content[:2000] if content else None


def _memory_classification_for_text(content: str) -> MemoryClassification:
    lowered = content.lower()
    if any(term in lowered for term in ("password", "api key", "api_key", "token", "ssn", "social security")):
        return MemoryClassification.RESTRICTED
    if any(term in lowered for term in ("medical", "health", "bank", "legal", "attorney", "case")):
        return MemoryClassification.SENSITIVE
    return MemoryClassification.PRIVATE
