from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field
from typing import Any

from freyja.foundation_models import (
    AuditEvent,
    AuditEventType,
    GatewayHandoff,
    GatewaySender,
    PersistentAgent,
    SecurityDomain,
    SecurityDomainId,
    normalize_agent_key,
)
from freyja.foundation_seed import PERSISTENT_AGENTS, SECURITY_DOMAINS, agents_by_key, domains_by_id


class GatewayRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    sender: GatewaySender
    target_agent: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    conversation_id: str | None = None
    channel: str = "unknown"
    message_id: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    reply_context: dict[str, Any] = Field(default_factory=dict)
    permissions: frozenset[str] = Field(default_factory=frozenset)


class GatewayResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    handoff: GatewayHandoff | None
    audit_event: AuditEvent


class GatewayAuthenticationError(Exception):
    pass


class GatewayPermissionError(Exception):
    def __init__(self, audit_event: AuditEvent) -> None:
        super().__init__(audit_event.reason)
        self.audit_event = audit_event


class AgentGateway:
    """Deterministic transition gateway for agent handoff creation.

    The gateway identifies a sender, resolves an explicitly named target agent,
    checks top-level domain access, and emits audit. It intentionally does not
    classify intent, select tools, pick strategy, or plan execution.
    """

    def __init__(
        self,
        *,
        agents: tuple[PersistentAgent, ...] = PERSISTENT_AGENTS,
        domains: tuple[SecurityDomain, ...] = SECURITY_DOMAINS,
    ) -> None:
        self._agents = agents_by_key() if agents == PERSISTENT_AGENTS else self._index_agents(agents)
        self._domains = domains_by_id() if domains == SECURITY_DOMAINS else {d.domain_id: d for d in domains}

    def handle(self, request: GatewayRequest) -> GatewayResult:
        sender = self.authenticate_sender(request.sender)
        target = self.resolve_target_agent(request.target_agent)
        conversation_id = self.resolve_conversation(request)
        allowed, reason = self.check_domain_permission(sender.security_domain_id, target.security_domain_id)
        if not allowed:
            event = AuditEvent(
                event_type=AuditEventType.GATEWAY_HANDOFF_DENIED,
                actor_id=sender.sender_id,
                domain_id=sender.security_domain_id,
                target_id=target.agent_id,
                allowed=False,
                reason=reason,
            )
            raise GatewayPermissionError(event)

        handoff = GatewayHandoff(
            sender_id=sender.sender_id,
            target_agent_id=target.agent_id,
            conversation_id=conversation_id,
            source_domain_id=sender.security_domain_id,
            target_domain_id=target.security_domain_id,
            prompt=request.prompt,
            channel=request.channel,
            message_id=request.message_id,
            attachments=request.attachments,
            reply_context=request.reply_context,
            permissions=request.permissions,
            available_tools=target.tool_grants,
            memory_scopes=frozenset(
                scope
                for scope in (target.private_memory_scope, *target.shared_memory_scopes)
                if scope
            ),
            cloud_egress_policy_id=target.cloud_egress_policy_id,
        )
        event = AuditEvent(
            event_type=AuditEventType.GATEWAY_HANDOFF_CREATED,
            actor_id=sender.sender_id,
            domain_id=sender.security_domain_id,
            target_id=target.agent_id,
            allowed=True,
            reason="explicit target agent resolved and domain access allowed",
            metadata={"conversation_id": conversation_id, "handoff_id": handoff.handoff_id},
        )
        return GatewayResult(handoff=handoff, audit_event=event)

    def authenticate_sender(self, sender: GatewaySender) -> GatewaySender:
        if not sender.authenticated:
            raise GatewayAuthenticationError("sender is not authenticated")
        return sender

    def resolve_target_agent(self, target_agent: str) -> PersistentAgent:
        agent = self._agents.get(normalize_agent_key(target_agent))
        if agent is None or not agent.active:
            raise KeyError(f"unknown target agent: {target_agent}")
        return agent

    def resolve_conversation(self, request: GatewayRequest) -> str:
        return request.conversation_id or str(uuid.uuid4())

    def check_domain_permission(
        self,
        source_domain_id: SecurityDomainId,
        target_domain_id: SecurityDomainId,
    ) -> tuple[bool, str]:
        source = self._domains[source_domain_id]
        target = self._domains[target_domain_id]
        legacy_household = source_domain_id == SecurityDomainId.FREYJA_HOUSEHOLD
        if (
            source.allows_domain(target_domain_id)
            or target.parent_domain_id == source_domain_id
            or (legacy_household and target.parent_domain_id == SecurityDomainId.HOUSEHOLD)
        ):
            return True, "domain access allowed"
        return False, f"{source_domain_id.value} cannot access {target_domain_id.value}"

    @staticmethod
    def _index_agents(agents: tuple[PersistentAgent, ...]) -> dict[str, PersistentAgent]:
        indexed: dict[str, PersistentAgent] = {}
        for agent in agents:
            indexed[normalize_agent_key(agent.agent_id)] = agent
            indexed[normalize_agent_key(agent.display_name)] = agent
            for alias in agent.aliases:
                indexed[normalize_agent_key(alias)] = agent
        return indexed
