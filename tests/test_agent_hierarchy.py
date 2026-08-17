from __future__ import annotations

import pytest

from freyja.agents import (
    AgentHierarchy,
    AgentName,
    EscalationTarget,
    MaintenanceAuthority,
    MaintenanceResult,
    PersonName,
)


def test_personal_agents_delegate_to_shared_maintenance_with_separate_scopes() -> None:
    hierarchy = AgentHierarchy()

    joe = hierarchy.maintenance_request(
        requested_by=AgentName.CLOYD_GIBBLER,
        owner=PersonName.JOE,
        objective="Inspect Iris disk health",
    )
    beth = hierarchy.maintenance_request(
        requested_by=AgentName.BENEDICT,
        owner=PersonName.BETH,
        objective="Inspect Beth's agent service",
    )

    assert joe.result_recipient is AgentName.CLOYD_GIBBLER
    assert joe.memory_principal.client_subject == "agent:cloyd-gibbler"
    assert joe.memory_principal.account_owner == "person:joe"
    assert beth.result_recipient is AgentName.BENEDICT
    assert beth.memory_principal.client_subject == "agent:benedict"
    assert beth.memory_principal.account_owner == "person:beth"
    assert joe.memory_principal.scope_key != beth.memory_principal.scope_key


def test_authenticated_people_message_only_their_primary_agent() -> None:
    hierarchy = AgentHierarchy()

    family = hierarchy.route_person_message(person=PersonName.FAMILY, content="Hello Freyja")
    joe = hierarchy.route_person_message(person=PersonName.JOE, content="Hello Cloyd")
    beth = hierarchy.route_person_message(person=PersonName.BETH, content="Hello Benedict")

    assert family.recipient is AgentName.FREYJA
    assert family.memory_principal.account_owner == "person:family"
    assert joe.recipient is AgentName.CLOYD_GIBBLER
    assert joe.memory_principal.account_owner == "person:joe"
    assert beth.recipient is AgentName.BENEDICT
    assert beth.memory_principal.account_owner == "person:beth"
    assert family.memory_principal.scope_key != joe.memory_principal.scope_key
    assert joe.memory_principal.scope_key != beth.memory_principal.scope_key


def test_agent_cannot_delegate_for_another_agents_person() -> None:
    hierarchy = AgentHierarchy()

    with pytest.raises(PermissionError, match="primary agent"):
        hierarchy.maintenance_request(
            requested_by=AgentName.FREYJA,
            owner=PersonName.JOE,
            objective="Read Cloyd status",
        )
    with pytest.raises(PermissionError, match="primary agent"):
        hierarchy.maintenance_request(
            requested_by=AgentName.MAINTENANCE,
            owner=PersonName.JOE,
            objective="Delegate work to myself",
        )


def test_results_return_only_to_the_requesting_agent_and_owner() -> None:
    hierarchy = AgentHierarchy()
    request = hierarchy.maintenance_request(
        requested_by=AgentName.BENEDICT,
        owner=PersonName.BETH,
        objective="Inspect a service",
    )
    result = MaintenanceResult(
        request_id=request.request_id,
        owner=request.owner,
        requested_by=request.requested_by,
        result_recipient=request.result_recipient,
        summary="Service is healthy.",
    )

    assert hierarchy.deliver_result(request, result, recipient=AgentName.BENEDICT, owner=PersonName.BETH) == (
        "Service is healthy."
    )
    with pytest.raises(PermissionError, match="private"):
        hierarchy.deliver_result(request, result, recipient=AgentName.FREYJA, owner=PersonName.BETH)
    with pytest.raises(PermissionError, match="private"):
        hierarchy.deliver_result(request, result, recipient=AgentName.BENEDICT, owner=PersonName.JOE)

    forged = result.model_copy(update={"request_id": "unrelated-request"})
    with pytest.raises(PermissionError, match="request envelope"):
        hierarchy.deliver_result(request, forged, recipient=AgentName.BENEDICT, owner=PersonName.BETH)


@pytest.mark.parametrize(
    ("authority", "target"),
    [
        (MaintenanceAuthority.INSPECT, EscalationTarget.NONE),
        (MaintenanceAuthority.SAFE_REVERSIBLE, EscalationTarget.REQUESTING_AGENT),
        (MaintenanceAuthority.CONSEQUENTIAL, EscalationTarget.PERSON),
    ],
)
def test_escalation_follows_authority_level(authority, target) -> None:
    request = AgentHierarchy().maintenance_request(
        requested_by=AgentName.CLOYD_GIBBLER,
        owner=PersonName.JOE,
        objective="Maintain a service",
        authority=authority,
    )

    assert request.escalation_target is target


def test_family_issue_review_belongs_to_freyja_and_stays_inspect_only() -> None:
    requests = AgentHierarchy().family_issue_review_requests(
        objective="Diagnose household system health and report issues"
    )

    assert len(requests) == 1
    request = requests[0]
    assert request.owner is PersonName.FAMILY
    assert request.requested_by is AgentName.FREYJA
    assert request.result_recipient is AgentName.FREYJA
    assert request.authority is MaintenanceAuthority.INSPECT
    assert request.escalation_target is EscalationTarget.NONE
    assert request.memory_principal.client_subject == "agent:freyja"
    assert request.memory_principal.account_owner == "person:family"
