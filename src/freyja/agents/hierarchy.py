"""Authority and privacy boundaries between personal and maintenance agents."""

from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from freyja.memory.models import MemoryPrincipal
from freyja.memory.principal import build_memory_principal


class AgentName(StrEnum):
    FREYJA = "freyja"
    BENEDICT = "benedict"
    MAINTENANCE = "maintenance"


class PersonName(StrEnum):
    JOE = "joe"
    BETH = "beth"


class MaintenanceAuthority(StrEnum):
    INSPECT = "inspect"
    SAFE_REVERSIBLE = "safe_reversible"
    CONSEQUENTIAL = "consequential"


class EscalationTarget(StrEnum):
    NONE = "none"
    REQUESTING_AGENT = "requesting_agent"
    PERSON = "person"


class MaintenanceRequest(BaseModel):
    """A maintenance task whose owner and return path cannot be rewritten."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    objective: str = Field(min_length=1, max_length=4000)
    requested_by: AgentName
    owner: PersonName
    authority: MaintenanceAuthority
    result_recipient: AgentName
    memory_principal: MemoryPrincipal
    escalation_target: EscalationTarget


class PersonalAgentMessage(BaseModel):
    """An authenticated person's message routed to only their primary agent."""

    model_config = ConfigDict(frozen=True)

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    person: PersonName
    recipient: AgentName
    content: str = Field(min_length=1, max_length=16000)
    memory_principal: MemoryPrincipal


class MaintenanceResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    owner: PersonName
    requested_by: AgentName
    result_recipient: AgentName
    summary: str


class AgentHierarchy:
    """Route maintenance work without merging personal-agent privacy scopes."""

    _primary_agents = {
        PersonName.JOE: AgentName.FREYJA,
        PersonName.BETH: AgentName.BENEDICT,
    }

    def primary_agent(self, person: PersonName) -> AgentName:
        return self._primary_agents[person]

    def route_person_message(self, *, person: PersonName, content: str) -> PersonalAgentMessage:
        recipient = self.primary_agent(person)
        return PersonalAgentMessage(
            person=person,
            recipient=recipient,
            content=content,
            memory_principal=build_memory_principal(
                client_type="agent",
                client_subject=f"agent:{recipient.value}",
                account_owner=f"person:{person.value}",
            ),
        )

    def maintenance_request(
        self,
        *,
        requested_by: AgentName,
        owner: PersonName,
        objective: str,
        authority: MaintenanceAuthority = MaintenanceAuthority.INSPECT,
    ) -> MaintenanceRequest:
        if requested_by is not self.primary_agent(owner):
            raise PermissionError("only a person's primary agent may delegate maintenance for that person")
        escalation = {
            MaintenanceAuthority.INSPECT: EscalationTarget.NONE,
            MaintenanceAuthority.SAFE_REVERSIBLE: EscalationTarget.REQUESTING_AGENT,
            MaintenanceAuthority.CONSEQUENTIAL: EscalationTarget.PERSON,
        }[authority]
        return MaintenanceRequest(
            objective=objective,
            requested_by=requested_by,
            owner=owner,
            authority=authority,
            result_recipient=requested_by,
            memory_principal=build_memory_principal(
                client_type="agent",
                client_subject=f"agent:{requested_by.value}",
                account_owner=f"person:{owner.value}",
            ),
            escalation_target=escalation,
        )

    def deliver_result(
        self,
        request: MaintenanceRequest,
        result: MaintenanceResult,
        *,
        recipient: AgentName,
        owner: PersonName,
    ) -> str:
        if (
            result.request_id != request.request_id
            or result.owner is not request.owner
            or result.requested_by is not request.requested_by
            or result.result_recipient is not request.result_recipient
        ):
            raise PermissionError("maintenance result does not match its request envelope")
        if recipient is not result.result_recipient or owner is not result.owner:
            raise PermissionError("maintenance results are private to the requesting agent and owner")
        if result.requested_by is not self.primary_agent(result.owner):
            raise PermissionError("maintenance result has an invalid authority chain")
        return result.summary
