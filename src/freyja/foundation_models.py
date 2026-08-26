from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SecurityDomainId(StrEnum):
    FREYJA_HOUSEHOLD = "freyja-household"
    HOUSEHOLD = "household"
    PERSON_JOE = "person.joe"
    PERSON_BETH = "person.beth"
    PERSON_LIAM = "person.liam"
    PERSON_JENNA = "person.jenna"
    SYSTEM = "system"
    PARALEGAL_ENCLAVE = "paralegal-enclave"
    PARALEGAL = "paralegal"


class MemoryScope(StrEnum):
    PERSONAL = "personal"
    HOUSEHOLD = "household"
    ENCLAVE = "enclave"
    SYSTEM = "system"


class MemoryClassification(StrEnum):
    ROUTINE = "routine"
    PRIVATE = "private"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class AuditEventType(StrEnum):
    GATEWAY_HANDOFF_CREATED = "gateway_handoff_created"
    GATEWAY_HANDOFF_DENIED = "gateway_handoff_denied"
    AGENT_RUN_STARTED = "agent_run_started"
    AGENT_TOOL_SELECTED = "agent_tool_selected"
    AGENT_TOOL_EXECUTED = "agent_tool_executed"
    AGENT_INFERENCE_SELECTED = "agent_inference_selected"
    AGENT_INFERENCE_COMPLETED = "agent_inference_completed"
    AGENT_MEMORY_RECALLED = "agent_memory_recalled"
    AGENT_MEMORY_WRITTEN = "agent_memory_written"
    AGENT_MEMORY_CANDIDATE_PROPOSED = "agent_memory_candidate_proposed"
    AGENT_MEMORY_CANDIDATE_REVIEWED = "agent_memory_candidate_reviewed"
    AGENT_FOLLOW_UP_REQUESTED = "agent_follow_up_requested"
    PRIVACY_EGRESS_ALLOWED = "privacy_egress_allowed"
    PRIVACY_EGRESS_DENIED = "privacy_egress_denied"


class Machine(BaseModel):
    model_config = ConfigDict(frozen=True)

    machine_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    security_domain_id: SecurityDomainId
    capabilities: frozenset[str] = Field(default_factory=frozenset)
    active: bool = True


class SecurityDomain(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain_id: SecurityDomainId
    display_name: str = Field(min_length=1)
    parent_domain_id: SecurityDomainId | None = None
    allowed_domain_ids: frozenset[SecurityDomainId] = Field(default_factory=frozenset)
    classification_floor: MemoryClassification = MemoryClassification.ROUTINE

    def allows_domain(self, target_domain_id: SecurityDomainId) -> bool:
        return target_domain_id == self.domain_id or target_domain_id in self.allowed_domain_ids


class PersistentAgent(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    security_domain_id: SecurityDomainId
    home_machine_id: str | None = None
    aliases: frozenset[str] = Field(default_factory=frozenset)
    capabilities: frozenset[str] = Field(default_factory=frozenset)
    tool_grants: frozenset[str] = Field(default_factory=frozenset)
    private_memory_scope: str | None = None
    shared_memory_scopes: frozenset[str] = Field(default_factory=frozenset)
    default_inference_capabilities: tuple[str, ...] = ("general.large", "general.local")
    cloud_egress_policy_id: str = "household-default"
    active: bool = True

    def matches(self, value: str) -> bool:
        normalized = normalize_agent_key(value)
        return normalized == normalize_agent_key(self.agent_id) or normalized in self.aliases


class InferenceEndpoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    endpoint_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    machine_id: str | None = None
    base_url: str = ""
    model: str = ""
    capabilities: frozenset[str] = Field(default_factory=frozenset)
    security_domain_id: SecurityDomainId
    priority: int = 100
    enabled: bool = True


class GatewaySender(BaseModel):
    model_config = ConfigDict(frozen=True)

    sender_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    security_domain_id: SecurityDomainId
    authenticated: bool = True


class GatewayHandoff(BaseModel):
    model_config = ConfigDict(frozen=True)

    handoff_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str
    target_agent_id: str
    conversation_id: str
    source_domain_id: SecurityDomainId
    target_domain_id: SecurityDomainId
    prompt: str
    channel: str = "unknown"
    message_id: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    reply_context: dict[str, Any] = Field(default_factory=dict)
    permissions: frozenset[str] = Field(default_factory=frozenset)
    available_tools: frozenset[str] = Field(default_factory=frozenset)
    memory_scopes: frozenset[str] = Field(default_factory=frozenset)
    cloud_egress_policy_id: str = "household-default"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolCapabilityGrant(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    required_permission: str = Field(min_length=1)
    mutation: bool = False
    machine_affinity: str | None = None
    security_domain_id: SecurityDomainId = SecurityDomainId.HOUSEHOLD


class AgentStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    tool_id: str | None = None
    inference_endpoint_id: str | None = None
    success: bool | None = None


class AgentExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    trace_id: str
    agent_id: str
    conversation_id: str
    response_text: str
    selected_tools: tuple[str, ...] = ()
    tool_results: tuple[dict[str, Any], ...] = ()
    recalled_memories: tuple[dict[str, Any], ...] = ()
    written_memories: tuple[dict[str, Any], ...] = ()
    memory_candidates: tuple[dict[str, Any], ...] = ()
    follow_up_questions: tuple[str, ...] = ()
    inference_endpoint_id: str | None = None
    inference_model: str | None = None
    inference_machine_id: str | None = None
    inference_status: str | None = None
    steps: tuple[AgentStep, ...] = ()
    audit_events: tuple[AuditEvent, ...] = ()
    degraded: bool = False


class SemanticEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_machine_id: str
    event_type: str = Field(min_length=1)
    room: str | None = None
    subject: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: AuditEventType
    actor_id: str
    domain_id: SecurityDomainId
    target_id: str | None = None
    allowed: bool
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MemoryRecordMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: MemoryScope
    owner_domain_id: SecurityDomainId
    provenance: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    classification: MemoryClassification


def normalize_agent_key(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")
