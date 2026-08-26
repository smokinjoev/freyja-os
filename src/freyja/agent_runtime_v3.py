from __future__ import annotations

import asyncio
import datetime as _datetime
import json
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
from freyja.freyja3_memory import Freyja3MemoryCandidateWrite, Freyja3MemoryQuery, Freyja3MemoryStore, Freyja3MemoryWrite
from freyja.inference_registry_v3 import InferenceRegistryV3
from freyja.media import AttachmentInput, images_from_attachments
from freyja.ollama_client import OllamaClient
from freyja.privacy_egress import PrivacyEgressGate
from freyja.tools.models import ToolDefinition, ToolExecutionRequest
from freyja.tools.registry import ToolRegistry
from freyja.tools.weather import classify_weather_request


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
        max_tool_iterations: int = 3,
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
        self._max_tool_iterations = max(1, max_tool_iterations)
        self._unhealthy_endpoint_ids = set(unhealthy_endpoint_ids)

    def run(self, handoff: GatewayHandoff) -> AgentExecutionResult:
        return asyncio.run(self.arun(handoff))

    async def arun(self, handoff: GatewayHandoff) -> AgentExecutionResult:
        agent = self._agent(handoff.target_agent_id)
        selected_tools = [] if self._run_inference else self.choose_tools(agent, handoff.prompt, handoff.available_tools)
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
        follow_up_questions = self._follow_up_questions(agent, handoff.prompt, selected_tools, steps, audit_events)
        self._record_plan(agent, selected_tools, follow_up_questions, steps, audit_events)
        for tool_id in selected_tools:
            self._record_tool_selection(agent, tool_id, steps, audit_events, reason="agent selected permitted tool")

        executable_tools = [tool_id for tool_id in selected_tools if tool_id not in _MUTATION_CAPABILITIES or not follow_up_questions]
        tool_results = await self._run_tool_loop(agent, handoff, selected_tools, executable_tools, steps, audit_events)

        inference_endpoint_id = None
        inference_model = None
        inference_machine_id = None
        inference_status = None
        inference_text = None
        degraded = False
        if endpoint is not None and not follow_up_questions:
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
                selected_tools=selected_tools,
                tool_results=tool_results,
                steps=steps,
                audit_events=audit_events,
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
        elif not follow_up_questions:
            degraded = True
            steps.append(AgentStep(kind="inference_unavailable", detail=f"no healthy endpoint for {capability}", success=False))

        memory_candidates = self._propose_memory_candidates(agent, handoff, steps, audit_events)
        written_memories = self._write_agent_memories(agent, handoff, selected_tools, tool_results, steps, audit_events)
        response = self._compose_response(
            agent,
            handoff,
            selected_tools,
            tool_results,
            recalled_memories,
            follow_up_questions,
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
            memory_candidates=tuple(memory_candidates),
            follow_up_questions=tuple(follow_up_questions),
            inference_endpoint_id=inference_endpoint_id,
            inference_model=inference_model,
            inference_machine_id=inference_machine_id,
            inference_status=inference_status,
            steps=tuple(steps),
            audit_events=tuple(audit_events),
            degraded=degraded,
        )

    def _propose_memory_candidates(
        self,
        agent: PersistentAgent,
        handoff: GatewayHandoff,
        steps: list[AgentStep],
        audit_events: list[AuditEvent],
    ) -> list[dict[str, Any]]:
        if not self._use_memory or self._memory_store is None or _explicit_memory_content(handoff.prompt):
            return []
        candidate_content = _memory_candidate_content(handoff.prompt)
        if not candidate_content:
            return []
        candidate = self._memory_store.propose_candidate(
            Freyja3MemoryCandidateWrite(
                owner_domain_id=agent.security_domain_id,
                scope=MemoryScope.PERSONAL if agent.security_domain_id != SecurityDomainId.HOUSEHOLD else MemoryScope.HOUSEHOLD,
                source_agent_id=agent.agent_id,
                content=candidate_content,
                provenance="agent-runtime-v3-memory-candidate",
                confidence=0.65,
                classification=_memory_classification_for_text(candidate_content),
                metadata={"conversation_id": handoff.conversation_id, "handoff_id": handoff.handoff_id},
            ),
            proposer_domain_id=agent.security_domain_id,
        )
        public = candidate.model_dump(mode="json")
        steps.append(AgentStep(kind="memory_candidate_proposed", detail="proposed reviewable Freyja 3 memory candidate", success=True))
        audit_events.append(
            AuditEvent(
                event_type=AuditEventType.AGENT_MEMORY_CANDIDATE_PROPOSED,
                actor_id=f"agent:{agent.agent_id}",
                domain_id=agent.security_domain_id,
                target_id=candidate.candidate_id,
                allowed=True,
                reason="agent proposed inferred memory candidate for review",
                metadata={"classification": candidate.classification.value, "scope": candidate.scope.value},
            )
        )
        return [public]

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
            ("browser.control", ("browser", "safari", "front tab", "current tab")),
            ("calendar.read", ("calendar", "schedule", "appointment")),
            ("email.read", ("email", "mail")),
            ("messaging.send", ("message", "imessage", "text ", "sms")),
            ("home-assistant.read", ("home assistant state", "home assistant states", "list home assistant", "show home assistant", "house state", "light states")),
            ("home-assistant.control", ("turn on", "turn off", "switch on", "switch off", "lock", "unlock", "open", "close")),
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
            ("system.health", ("system health", "diagnose", "diagnostic")),
        )
        for tool_id, terms in rules:
            if tool_id in allowed and any(term in lowered for term in terms):
                candidates.append(tool_id)
        return candidates

    def _follow_up_questions(
        self,
        agent: PersistentAgent,
        objective: str,
        selected_tools: list[str],
        steps: list[AgentStep],
        audit_events: list[AuditEvent],
    ) -> list[str]:
        questions: list[str] = []
        lowered = objective.lower()
        if "messaging.send" in selected_tools and not _has_message_target(objective):
            questions.append("Who should I send the message to, and what should it say?")
        if "scheduling.create" in selected_tools and not _has_time_detail(lowered):
            questions.append("When should I schedule that?")
        if "home-assistant.control" in selected_tools and not _has_home_action_detail(lowered):
            questions.append("Which Home Assistant device or area should I control, and what state should it be set to?")

        for question in questions:
            steps.append(AgentStep(kind="follow_up_question", detail=question, success=True))
            audit_events.append(
                AuditEvent(
                    event_type=AuditEventType.AGENT_FOLLOW_UP_REQUESTED,
                    actor_id=f"agent:{agent.agent_id}",
                    domain_id=agent.security_domain_id,
                    target_id="follow-up-question",
                    allowed=True,
                    reason="agent requested clarification before mutation tool execution",
                )
            )
        return questions

    def _choose_follow_up_tools(
        self,
        agent: PersistentAgent,
        selected_tools: list[str],
        available_tool_ids: Iterable[str],
        tool_results: list[dict[str, Any]],
        attempted_retries: set[str],
        steps: list[AgentStep],
        audit_events: list[AuditEvent],
    ) -> list[str]:
        failed_results = [result for result in tool_results if result.get("success") is False]
        if not failed_results:
            return []

        failed_capabilities = [str(result.get("capability_id")) for result in failed_results if result.get("capability_id")]
        steps.append(
            AgentStep(
                kind="observation",
                detail=f"{agent.agent_id} observed failed tool result(s): {', '.join(failed_capabilities)}",
                success=False,
            )
        )
        audit_events.append(
            AuditEvent(
                event_type=AuditEventType.AGENT_TOOL_SELECTED,
                actor_id=f"agent:{agent.agent_id}",
                domain_id=agent.security_domain_id,
                target_id="tool-failure-observation",
                allowed=True,
                reason="agent observed failed tool results before follow-up selection",
                metadata={"failed_capabilities": failed_capabilities},
            )
        )

        allowed = set(agent.tool_grants).intersection(set(available_tool_ids))
        failed_capability_set = set(failed_capabilities)
        if "system.health" not in selected_tools and "system.health" in allowed:
            self._record_tool_selection(
                agent,
                "system.health",
                steps,
                audit_events,
                reason="agent selected diagnostic follow-up after failed tool observation",
                detail=f"{agent.agent_id} selected system.health after observing failed tools",
            )
            return ["system.health"]
        retryable = [
            capability_id
            for capability_id in selected_tools
            if capability_id in failed_capability_set
            and capability_id not in attempted_retries
            and capability_id not in _MUTATION_CAPABILITIES
        ]
        if retryable:
            for capability_id in retryable:
                attempted_retries.add(capability_id)
                steps.append(
                    AgentStep(
                        kind="retry",
                        detail=f"{agent.agent_id} retrying {capability_id} after observation",
                        tool_id=capability_id,
                    )
                )
            return retryable
        return []

    async def _run_tool_loop(
        self,
        agent: PersistentAgent,
        handoff: GatewayHandoff,
        selected_tools: list[str],
        executable_tools: list[str],
        steps: list[AgentStep],
        audit_events: list[AuditEvent],
    ) -> list[dict[str, Any]]:
        tool_results: list[dict[str, Any]] = []
        next_tools = list(executable_tools)
        attempted_retries: set[str] = set()
        iteration = 0
        while next_tools and iteration < self._max_tool_iterations:
            iteration += 1
            steps.append(AgentStep(kind="tool_iteration", detail=f"agent tool loop iteration {iteration}", success=True))
            iteration_results = await self._execute_selected_tools(agent, handoff, next_tools, steps, audit_events)
            tool_results.extend(iteration_results)
            if iteration >= self._max_tool_iterations:
                break
            next_tools = self._choose_follow_up_tools(
                agent,
                selected_tools,
                handoff.available_tools,
                tool_results,
                attempted_retries,
                steps,
                audit_events,
            )
            for tool_id in next_tools:
                if tool_id not in selected_tools:
                    selected_tools.append(tool_id)
        return tool_results

    def _record_plan(
        self,
        agent: PersistentAgent,
        selected_tools: list[str],
        follow_up_questions: list[str],
        steps: list[AgentStep],
        audit_events: list[AuditEvent],
    ) -> None:
        if follow_up_questions:
            detail = "ask for missing details before mutation tool execution"
        elif selected_tools:
            detail = f"try permitted tools in order: {', '.join(selected_tools)}"
        else:
            detail = "answer with available context and selected inference"
        steps.append(AgentStep(kind="plan", detail=detail, success=True))
        audit_events.append(
            AuditEvent(
                event_type=AuditEventType.AGENT_TOOL_SELECTED,
                actor_id=f"agent:{agent.agent_id}",
                domain_id=agent.security_domain_id,
                target_id="agent-plan",
                allowed=True,
                reason="agent created bounded plan before tool execution",
                metadata={"selected_tools": list(selected_tools), "follow_up_questions": list(follow_up_questions)},
            )
        )

    def _record_tool_selection(
        self,
        agent: PersistentAgent,
        tool_id: str,
        steps: list[AgentStep],
        audit_events: list[AuditEvent],
        *,
        reason: str,
        detail: str | None = None,
    ) -> None:
        steps.append(AgentStep(kind="tool_selected", detail=detail or f"{agent.agent_id} selected {tool_id}", tool_id=tool_id))
        audit_events.append(
            AuditEvent(
                event_type=AuditEventType.AGENT_TOOL_SELECTED,
                actor_id=f"agent:{agent.agent_id}",
                domain_id=agent.security_domain_id,
                target_id=tool_id,
                allowed=True,
                reason=reason,
            )
        )

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
                    "approval_granted": _approval_granted(capability_id, handoff.permissions),
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
        selected_tools: list[str],
        tool_results: list[dict[str, Any]],
        steps: list[AgentStep],
        audit_events: list[AuditEvent],
    ) -> tuple[str, str | None]:
        if not self._run_inference:
            return "not_run", None
        if endpoint_provider != "ollama":
            return "unsupported_provider", None
        if self._tool_registry is not None:
            return await self._run_vulcan_tool_calling_inference(
                agent=agent,
                handoff=handoff,
                base_url=base_url,
                model=model,
                endpoint_id=endpoint_id,
                selected_tools=selected_tools,
                tool_results=tool_results,
                steps=steps,
                audit_events=audit_events,
            )
        prompt = self._inference_prompt(agent, handoff, tool_results)
        images = _images_from_handoff(handoff) if endpoint_id and "vision" in endpoint_id else []
        response = await OllamaClient(base_url=base_url, model=model).chat(
            prompt=prompt,
            model=model,
            images=images or None,
        )
        if "error" in response:
            return "error", None
        return "ok", str(response.get("message", {}).get("content") or "").strip() or None

    async def _run_vulcan_tool_calling_inference(
        self,
        *,
        agent: PersistentAgent,
        handoff: GatewayHandoff,
        base_url: str,
        model: str,
        endpoint_id: str,
        selected_tools: list[str],
        tool_results: list[dict[str, Any]],
        steps: list[AgentStep],
        audit_events: list[AuditEvent],
    ) -> tuple[str, str | None]:
        client = OllamaClient(base_url=base_url, model=model)
        tools = self._tool_definitions_for_agent(agent, handoff.available_tools)
        available_tool_names = [tool.name for tool in tools]
        images = _images_from_handoff(handoff) if endpoint_id and "vision" in endpoint_id else []
        for iteration in range(self._max_tool_iterations):
            prompt = self._agent_tool_prompt(
                agent,
                handoff,
                recalled=bool(tool_results),
                tool_results=tool_results,
                available_tool_names=available_tool_names,
            )
            response = await client.chat(
                prompt=prompt,
                model=model,
                tools_required=bool(tools),
                tools=tools,
                images=images or None,
            )
            if "error" in response:
                if tool_results:
                    break
                return "error", None
            calls = _ollama_tool_calls(response)
            if not calls:
                return "ok", str(response.get("message", {}).get("content") or "").strip() or None

            steps.append(AgentStep(kind="tool_iteration", detail=f"Vulcan tool-call loop iteration {iteration + 1}", success=True))
            for call in calls:
                result = await self._execute_model_tool_call(
                    agent=agent,
                    handoff=handoff,
                    call=call,
                    selected_tools=selected_tools,
                    steps=steps,
                    audit_events=audit_events,
                )
                tool_results.append(result)

        final_prompt = self._agent_tool_prompt(
            agent,
            handoff,
            recalled=True,
            tool_results=tool_results,
            available_tool_names=available_tool_names,
        )
        final = await client.chat(
            prompt=final_prompt,
            model=model,
            tools_required=False,
            images=images or None,
        )
        if "error" in final:
            return "error", None
        return "ok", str(final.get("message", {}).get("content") or "").strip() or None

    def _tool_definitions_for_agent(
        self,
        agent: PersistentAgent,
        available_tool_ids: Iterable[str],
    ) -> list[ToolDefinition]:
        if self._tool_registry is None:
            return []
        allowed_capabilities = set(agent.tool_grants).intersection(set(available_tool_ids))
        allowed_tool_names = {
            tool_name
            for capability_id, tool_name in _CONCRETE_TOOL_BY_CAPABILITY.items()
            if capability_id in allowed_capabilities
        }
        if {"web.search", "weather.current"}.issubset(allowed_capabilities):
            allowed_tool_names.add("event_weather")
        return [
            definition
            for definition in self._tool_registry.list_tools()
            if definition.name in allowed_tool_names and definition.risk_level.value == "read_only"
        ]

    async def _execute_model_tool_call(
        self,
        *,
        agent: PersistentAgent,
        handoff: GatewayHandoff,
        call: dict[str, Any],
        selected_tools: list[str],
        steps: list[AgentStep],
        audit_events: list[AuditEvent],
    ) -> dict[str, Any]:
        tool_name = str(call.get("tool_name") or "")
        capability_id = _CAPABILITY_BY_CONCRETE_TOOL.get(tool_name, tool_name)
        if capability_id not in selected_tools:
            selected_tools.append(capability_id)
        self._record_tool_selection(
            agent,
            capability_id,
            steps,
            audit_events,
            reason="agent model selected permitted tool",
            detail=f"{agent.agent_id} requested {tool_name}",
        )
        request = ToolExecutionRequest(
            tool_name=tool_name,
            arguments=call.get("arguments") if isinstance(call.get("arguments"), dict) else {},
            actor=f"agent:{agent.agent_id}",
            conversation_id=handoff.conversation_id,
            metadata={
                "agent_id": agent.agent_id,
                "source_domain_id": handoff.source_domain_id.value,
                "target_domain_id": handoff.target_domain_id.value,
                "director_authorized": True,
                "approval_granted": False,
                "person": _person_metadata(handoff.source_domain_id),
                "memory_principal": _memory_principal_metadata(handoff),
            },
        )
        result = await self._tool_registry.execute(request) if self._tool_registry else None
        if result is None:
            public_result = {
                "capability_id": capability_id,
                "tool_name": tool_name,
                "success": False,
                "error_code": "tool_registry_unavailable",
                "public_error_message": "Tool registry unavailable.",
                "output": {},
            }
        else:
            success = _tool_effective_success(result.success, result.output)
            public_result = {
                "capability_id": capability_id,
                "tool_name": tool_name,
                "success": success,
                "error_code": result.error_code,
                "public_error_message": result.public_error_message,
                "output": result.output,
            }
        steps.append(
            AgentStep(
                kind="tool_executed",
                detail=f"{tool_name} executed for {capability_id}",
                tool_id=capability_id,
                success=bool(public_result.get("success")),
            )
        )
        audit_events.append(
            AuditEvent(
                event_type=AuditEventType.AGENT_TOOL_EXECUTED,
                actor_id=f"agent:{agent.agent_id}",
                domain_id=agent.security_domain_id,
                target_id=tool_name,
                allowed=bool(public_result.get("success")),
                reason=str(public_result.get("public_error_message") or "tool execution completed"),
            )
        )
        return public_result

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
        follow_up_questions: list[str],
        endpoint_id: str | None,
        inference_text: str | None,
        degraded: bool,
    ) -> str:
        if follow_up_questions:
            return follow_up_questions[0]
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
            weather_request = classify_weather_request(objective)
            return {
                "location": weather_request.location,
                "request_type": weather_request.request_type.value,
                "target_date": weather_request.target_date.isoformat() if weather_request.target_date else None,
                "target_label": weather_request.target_label,
            }
        if capability_id == "memory.private":
            return {"conversation_id": handoff.conversation_id, "limit": 10}
        if capability_id == "memory.shared":
            return {"query": objective, "limit": 5}
        if capability_id == "home-assistant.control":
            return _home_assistant_control_arguments(objective)
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
    def _agent_tool_prompt(
        agent: PersistentAgent,
        handoff: GatewayHandoff,
        *,
        recalled: bool,
        tool_results: list[dict[str, Any]],
        available_tool_names: list[str] | None = None,
    ) -> str:
        observation = ""
        if recalled:
            tool_list = ", ".join(available_tool_names or [])
            observation = (
                "\n\nTool observations:\n"
                f"{json.dumps(_public_tool_results(tool_results), default=str)}\n\n"
                f"Still-available local tools: {tool_list}.\n"
                "Answer directly from these observations. Do not claim unavailable live data is available. "
                "Do not claim you called or observed a tool unless it appears in Tool observations."
            )
        return (
            f"You are {agent.display_name}, a persistent Freyja 3 agent. "
            f"Today's date is {_datetime.date.today().isoformat()}. "
            "You decide whether local tools are needed. If the request mentions an event, venue, or vague place, "
            "resolve when and where it occurs with web_search before checking weather or answering. "
            "For annual events without a year, use the next upcoming occurrence relative to today's date unless the user asks for a past year. "
            "Never pass an event name such as Dragon Con as a weather location; first find the city and dates, "
            "then call get_weather with the city and forecast date. "
            "If the user asks for weather, do not stop after only resolving the event; call get_weather or explain why the forecast is unavailable. "
            "If a tool observation reports missing or invalid arguments, call the tool again with corrected arguments before answering. "
            "Use tools when current facts, weather, local state, files, email, calendar, or web evidence are needed.\n\n"
            f"User objective:\n{handoff.prompt}"
            f"{observation}"
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
    "browser.control": "apple_browser_front_tab",
    "email.read": "apple_mailbox_counts",
    "macagent.apple": "macagent_health",
    "home-assistant.read": "home_assistant_list_states",
    "home-assistant.control": "home_assistant_control_state",
    "system.health": "system_health",
    "git.inspect": "repository_status",
    "memory.private": "recall_conversation",
    "memory.shared": "memory_recall_shared",
    "music.control": "apple_music_current_track",
}

_CAPABILITY_BY_CONCRETE_TOOL = {tool_name: capability_id for capability_id, tool_name in _CONCRETE_TOOL_BY_CAPABILITY.items()}

_MUTATION_CAPABILITIES = {"messaging.send", "scheduling.create", "home-assistant.control"}


def _has_message_target(objective: str) -> bool:
    lowered = objective.lower()
    if re.search(r"\b(to|text|message|imessage|sms)\s+([A-Z][A-Za-z]+|\+\d{7,}|[a-z0-9_.+-]+@[a-z0-9-]+\.[a-z0-9-.]+)", objective):
        return True
    return any(f" {name} " in f" {lowered} " for name in ("joe", "beth", "liam", "jenna", "mom", "dad"))


def _has_time_detail(lowered_objective: str) -> bool:
    return bool(
        re.search(r"\b(\d{1,2}(:\d{2})?\s?(am|pm)|today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lowered_objective)
    )


def _has_home_action_detail(lowered_objective: str) -> bool:
    has_action = any(term in lowered_objective for term in ("turn on", "turn off", "set ", "lock", "unlock", "open", "close"))
    has_target = any(term in lowered_objective for term in ("light", "thermostat", "door", "lock", "kitchen", "living room", "bedroom", "garage"))
    return has_action and has_target


def _approval_granted(capability_id: str, permissions: frozenset[str]) -> bool:
    return f"approval:{capability_id}" in permissions or f"approve:{capability_id}" in permissions


def _home_assistant_control_arguments(objective: str) -> dict[str, Any]:
    lowered = objective.lower()
    state = ""
    if any(term in lowered for term in ("turn on", "switch on", "set on")):
        state = "on"
    elif any(term in lowered for term in ("turn off", "switch off", "set off")):
        state = "off"
    entity_match = re.search(r"\b((?:light|switch|climate|cover|lock)\.[a-z0-9_]+)\b", lowered)
    arguments: dict[str, Any] = {}
    if entity_match:
        arguments["entity_id"] = entity_match.group(1)
    if state:
        arguments["state"] = state
    return arguments


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


def _images_from_handoff(handoff: GatewayHandoff) -> list[Any]:
    attachments: list[AttachmentInput] = []
    for attachment in handoff.attachments:
        if not isinstance(attachment, dict):
            continue
        source = attachment.get("source")
        path = str(source) if source and not str(source).startswith(("http://", "https://")) else None
        attachments.append(
            AttachmentInput(
                filename=attachment.get("filename"),
                mime_type=attachment.get("media_type"),
                path=path,
                data_base64=attachment.get("data_base64"),
                size_bytes=attachment.get("size"),
            )
        )
    return images_from_attachments(attachments)


def _ollama_tool_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    message = response.get("message") if isinstance(response.get("message"), dict) else {}
    calls = message.get("tool_calls") if isinstance(message, dict) else []
    parsed: list[dict[str, Any]] = []
    if not isinstance(calls, list):
        return parsed
    for call in calls:
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = function.get("name")
        arguments = function.get("arguments")
        if isinstance(name, str):
            parsed.append({"tool_name": name, "arguments": arguments if isinstance(arguments, dict) else {}})
    return parsed


def _public_tool_results(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for result in tool_results:
        output = result.get("output") if isinstance(result.get("output"), dict) else {}
        public.append(
            {
                "tool_name": result.get("tool_name"),
                "success": result.get("success"),
                "error": result.get("public_error_message") or result.get("error_code"),
                "output": _trim_tool_output(output),
            }
        )
    return public


def _trim_tool_output(output: dict[str, Any], *, max_chars: int = 6000) -> dict[str, Any]:
    raw = json.dumps(output, default=str)
    if len(raw) <= max_chars:
        return output
    return {"truncated": True, "partial_output": raw[:max_chars]}


_EXPLICIT_MEMORY_RE = re.compile(
    r"^\s*(?:please\s+)?remember(?:\s+that|\s+this)?\s+(?P<content>.+?)\s*$",
    re.IGNORECASE | re.DOTALL,
)

_MEMORY_CANDIDATE_RE = re.compile(
    r"\b(?P<content>(?:i|we|joe|beth|liam|jenna|the family)\s+"
    r"(?:prefer|prefers|like|likes|need|needs|use|uses|work|works|want|wants)\b[^.?!]{3,220})",
    re.IGNORECASE,
)


def _explicit_memory_content(objective: str) -> str | None:
    match = _EXPLICIT_MEMORY_RE.match(objective)
    if not match:
        return None
    content = " ".join(match.group("content").split())
    return content[:2000] if content else None


def _memory_candidate_content(objective: str) -> str | None:
    match = _MEMORY_CANDIDATE_RE.search(objective)
    if not match:
        return None
    content = " ".join(match.group("content").split())
    return content[:500] if content else None


def _memory_classification_for_text(content: str) -> MemoryClassification:
    lowered = content.lower()
    if any(term in lowered for term in ("password", "api key", "api_key", "token", "ssn", "social security")):
        return MemoryClassification.RESTRICTED
    if any(term in lowered for term in ("medical", "health", "bank", "legal", "attorney", "case")):
        return MemoryClassification.SENSITIVE
    return MemoryClassification.PRIVATE
