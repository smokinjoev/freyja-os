from __future__ import annotations

import pytest
from pydantic import ValidationError

from freyja.agents import (
    AgentName,
    PersonalDataAction,
    PersonalDataAuthorization,
    PersonalDataDecision,
    PersonalDataPrincipal,
    PersonalDataResource,
    PersonalDataScope,
    PersonName,
)


def test_freyja_and_benedict_receive_separate_private_accounts() -> None:
    authorization = PersonalDataAuthorization()
    joe = authorization.private_account(
        person=PersonName.JOE,
        acting_agent=AgentName.FREYJA,
        resource=PersonalDataResource.EMAIL,
        account_id="joe-mail",
    )
    beth = authorization.private_account(
        person=PersonName.BETH,
        acting_agent=AgentName.BENEDICT,
        resource=PersonalDataResource.EMAIL,
        account_id="beth-mail",
    )

    assert joe.account_id != beth.account_id
    assert authorization.authorize(joe, PersonalDataAction.EMAIL_READ) is PersonalDataDecision.ALLOW
    assert authorization.authorize(beth, PersonalDataAction.EMAIL_READ) is PersonalDataDecision.ALLOW


def test_cross_person_private_access_is_rejected() -> None:
    authorization = PersonalDataAuthorization()

    with pytest.raises(PermissionError, match="primary agent"):
        authorization.private_account(
            person=PersonName.BETH,
            acting_agent=AgentName.FREYJA,
            resource=PersonalDataResource.CALENDAR,
            account_id="beth-calendar",
        )


def test_calendar_availability_does_not_reveal_event_details() -> None:
    authorization = PersonalDataAuthorization()
    grant = authorization.calendar_availability(
        calendar_owner=PersonName.BETH,
        acting_agent=AgentName.FREYJA,
        account_id="beth-calendar",
    )

    assert grant.scope is PersonalDataScope.AVAILABILITY_ONLY
    assert authorization.authorize(grant, PersonalDataAction.CALENDAR_AVAILABILITY) is PersonalDataDecision.ALLOW
    assert authorization.authorize(grant, PersonalDataAction.CALENDAR_READ) is PersonalDataDecision.DENY
    assert authorization.authorize(grant, PersonalDataAction.CALENDAR_CREATE) is PersonalDataDecision.DENY


def test_email_drafting_is_allowed_but_send_and_delete_require_approval() -> None:
    authorization = PersonalDataAuthorization()
    grant = authorization.private_account(
        person=PersonName.BETH,
        acting_agent=AgentName.BENEDICT,
        resource=PersonalDataResource.EMAIL,
        account_id="beth-mail",
    )

    assert authorization.authorize(grant, PersonalDataAction.EMAIL_DRAFT) is PersonalDataDecision.ALLOW
    assert authorization.authorize(grant, PersonalDataAction.EMAIL_SEND) is PersonalDataDecision.APPROVAL_REQUIRED
    assert authorization.authorize(grant, PersonalDataAction.EMAIL_DELETE) is PersonalDataDecision.APPROVAL_REQUIRED


def test_calendar_create_is_allowed_but_responses_and_deletes_require_approval() -> None:
    authorization = PersonalDataAuthorization()
    grant = authorization.private_account(
        person=PersonName.JOE,
        acting_agent=AgentName.FREYJA,
        resource=PersonalDataResource.CALENDAR,
        account_id="joe-calendar",
    )

    assert authorization.authorize(grant, PersonalDataAction.CALENDAR_CREATE) is PersonalDataDecision.ALLOW
    assert authorization.authorize(grant, PersonalDataAction.CALENDAR_RESPOND) is PersonalDataDecision.APPROVAL_REQUIRED
    assert authorization.authorize(grant, PersonalDataAction.CALENDAR_DELETE) is PersonalDataDecision.APPROVAL_REQUIRED


def test_resource_type_cannot_be_confused() -> None:
    authorization = PersonalDataAuthorization()
    email = authorization.private_account(
        person=PersonName.JOE,
        acting_agent=AgentName.FREYJA,
        resource=PersonalDataResource.EMAIL,
        account_id="joe-mail",
    )

    assert authorization.authorize(email, PersonalDataAction.CALENDAR_READ) is PersonalDataDecision.DENY


def test_household_account_retains_the_requesting_person_and_agent() -> None:
    authorization = PersonalDataAuthorization()
    joe = authorization.household_account(
        person=PersonName.JOE,
        acting_agent=AgentName.FREYJA,
        resource=PersonalDataResource.CALENDAR,
        account_id="household-calendar",
    )
    beth = authorization.household_account(
        person=PersonName.BETH,
        acting_agent=AgentName.BENEDICT,
        resource=PersonalDataResource.CALENDAR,
        account_id="household-calendar",
    )

    assert joe.person is PersonName.JOE
    assert beth.person is PersonName.BETH
    assert joe.acting_agent is AgentName.FREYJA
    assert beth.acting_agent is AgentName.BENEDICT


def test_constructed_principal_cannot_grant_itself_permissions_or_cross_person_access() -> None:
    authorization = PersonalDataAuthorization()
    with pytest.raises(ValidationError, match="allowed_actions"):
        PersonalDataPrincipal(
            person=PersonName.BETH,
            acting_agent=AgentName.FREYJA,
            resource=PersonalDataResource.EMAIL,
            account_id="beth-mail",
            scope=PersonalDataScope.PRIVATE,
            allowed_actions=frozenset({PersonalDataAction.EMAIL_READ, PersonalDataAction.EMAIL_SEND}),
        )

    cross_person = PersonalDataPrincipal(
        person=PersonName.BETH,
        acting_agent=AgentName.FREYJA,
        resource=PersonalDataResource.EMAIL,
        account_id="beth-mail",
        scope=PersonalDataScope.PRIVATE,
    )

    assert authorization.authorize(cross_person, PersonalDataAction.EMAIL_READ) is PersonalDataDecision.DENY
    assert authorization.authorize(cross_person, PersonalDataAction.EMAIL_SEND) is PersonalDataDecision.DENY


def test_constructed_owner_principal_still_cannot_bypass_send_approval() -> None:
    authorization = PersonalDataAuthorization()
    forged = PersonalDataPrincipal(
        person=PersonName.JOE,
        acting_agent=AgentName.FREYJA,
        resource=PersonalDataResource.EMAIL,
        account_id="joe-mail",
        scope=PersonalDataScope.PRIVATE,
    )

    assert authorization.authorize(forged, PersonalDataAction.EMAIL_SEND) is PersonalDataDecision.APPROVAL_REQUIRED
