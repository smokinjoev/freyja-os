"""Authorization policy shared by personal calendar and email adapters."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .hierarchy import AgentHierarchy, AgentName, PersonName


class PersonalDataResource(StrEnum):
    CALENDAR = "calendar"
    EMAIL = "email"


class PersonalDataScope(StrEnum):
    PRIVATE = "private"
    HOUSEHOLD = "household"
    AVAILABILITY_ONLY = "availability_only"


class PersonalDataAction(StrEnum):
    CALENDAR_AVAILABILITY = "calendar_availability"
    CALENDAR_READ = "calendar_read"
    CALENDAR_CREATE = "calendar_create"
    CALENDAR_MODIFY = "calendar_modify"
    CALENDAR_DELETE = "calendar_delete"
    CALENDAR_RESPOND = "calendar_respond"
    EMAIL_SEARCH = "email_search"
    EMAIL_READ = "email_read"
    EMAIL_DRAFT = "email_draft"
    EMAIL_SEND = "email_send"
    EMAIL_DELETE = "email_delete"


class PersonalDataDecision(StrEnum):
    ALLOW = "allow"
    APPROVAL_REQUIRED = "approval_required"
    DENY = "deny"


class PersonalDataPrincipal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    person: PersonName
    acting_agent: AgentName
    resource: PersonalDataResource
    account_id: str = Field(min_length=1, max_length=160)
    scope: PersonalDataScope


class PersonalDataAuthorization:
    """Issue narrowly scoped grants and evaluate operations at service boundaries."""

    _owner_actions = {
        PersonalDataResource.CALENDAR: frozenset(
            {
                PersonalDataAction.CALENDAR_AVAILABILITY,
                PersonalDataAction.CALENDAR_READ,
                PersonalDataAction.CALENDAR_CREATE,
                PersonalDataAction.CALENDAR_MODIFY,
            }
        ),
        PersonalDataResource.EMAIL: frozenset(
            {
                PersonalDataAction.EMAIL_SEARCH,
                PersonalDataAction.EMAIL_READ,
                PersonalDataAction.EMAIL_DRAFT,
            }
        ),
    }
    _approval_actions = frozenset(
        {
            PersonalDataAction.CALENDAR_DELETE,
            PersonalDataAction.CALENDAR_RESPOND,
            PersonalDataAction.EMAIL_SEND,
            PersonalDataAction.EMAIL_DELETE,
        }
    )

    def __init__(self, hierarchy: AgentHierarchy | None = None) -> None:
        self._hierarchy = hierarchy or AgentHierarchy()

    def private_account(
        self,
        *,
        person: PersonName,
        acting_agent: AgentName,
        resource: PersonalDataResource,
        account_id: str,
    ) -> PersonalDataPrincipal:
        if person is PersonName.FAMILY:
            raise PermissionError("private personal data requires an individual person")
        if acting_agent is not self._hierarchy.primary_agent(person):
            raise PermissionError("private personal data is available only to the person's primary agent")
        return PersonalDataPrincipal(
            person=person,
            acting_agent=acting_agent,
            resource=resource,
            account_id=account_id,
            scope=PersonalDataScope.PRIVATE,
        )

    def calendar_availability(
        self,
        *,
        calendar_owner: PersonName,
        acting_agent: AgentName,
        account_id: str,
    ) -> PersonalDataPrincipal:
        if acting_agent not in self._hierarchy.primary_agents():
            raise PermissionError("only a personal agent may request shared availability")
        return PersonalDataPrincipal(
            person=calendar_owner,
            acting_agent=acting_agent,
            resource=PersonalDataResource.CALENDAR,
            account_id=account_id,
            scope=PersonalDataScope.AVAILABILITY_ONLY,
        )

    def household_account(
        self,
        *,
        person: PersonName,
        acting_agent: AgentName,
        resource: PersonalDataResource,
        account_id: str,
    ) -> PersonalDataPrincipal:
        if acting_agent is not self._hierarchy.primary_agent(person):
            raise PermissionError("household access must retain the requesting person's agent identity")
        return PersonalDataPrincipal(
            person=person,
            acting_agent=acting_agent,
            resource=resource,
            account_id=account_id,
            scope=PersonalDataScope.HOUSEHOLD,
        )

    def authorize(
        self,
        principal: PersonalDataPrincipal,
        action: PersonalDataAction,
    ) -> PersonalDataDecision:
        if not self._action_matches_resource(principal.resource, action):
            return PersonalDataDecision.DENY
        if not self._valid_authority_chain(principal):
            return PersonalDataDecision.DENY
        if action in self._policy_actions(principal):
            return PersonalDataDecision.ALLOW
        if principal.scope is not PersonalDataScope.AVAILABILITY_ONLY and action in self._approval_actions:
            return PersonalDataDecision.APPROVAL_REQUIRED
        return PersonalDataDecision.DENY

    def _valid_authority_chain(self, principal: PersonalDataPrincipal) -> bool:
        if principal.acting_agent not in self._hierarchy.primary_agents():
            return False
        if principal.scope is PersonalDataScope.PRIVATE:
            if principal.person is PersonName.FAMILY:
                return False
            return principal.acting_agent is self._hierarchy.primary_agent(principal.person)
        if principal.scope is PersonalDataScope.HOUSEHOLD:
            return principal.acting_agent is self._hierarchy.primary_agent(principal.person)
        return principal.scope is PersonalDataScope.AVAILABILITY_ONLY

    def _policy_actions(self, principal: PersonalDataPrincipal) -> frozenset[PersonalDataAction]:
        if principal.scope is PersonalDataScope.AVAILABILITY_ONLY:
            return frozenset({PersonalDataAction.CALENDAR_AVAILABILITY})
        return self._owner_actions[principal.resource]

    @staticmethod
    def _action_matches_resource(resource: PersonalDataResource, action: PersonalDataAction) -> bool:
        return action.value.startswith(f"{resource.value}_")
