from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from freyja.main import app
from freyja.open_webui_tools import ToolInvocationRequest, authorize_tool_invocation, load_operation_policies


def test_open_webui_tool_catalog_is_manifest_driven_and_fail_closed() -> None:
    policies = load_operation_policies()

    assert set(policies) == {
        "search",
        "remember",
        "update",
        "forget",
        "record-decision",
        "recent-events",
        "calendar.read",
        "calendar.create",
        "reminders.read",
        "reminders.create",
        "imessage.send.approved",
        "shortcuts.run",
        "home.status",
        "home.device_action",
        "files.household.read",
        "files.beth.read",
        "pdf.analyze",
        "image.analyze",
        "infrastructure.health",
        "weather.read",
    }
    assert all(policy.destructive_default == "deny" for policy in policies.values())
    assert policies["calendar.create"].confirmation_required is True
    assert policies["weather.read"].children_allowed is True
    assert policies["home.device_action"].children_allowed is False


def test_authorization_denies_unknown_or_unassigned_operations() -> None:
    with pytest.raises(HTTPException) as unknown:
        authorize_tool_invocation(ToolInvocationRequest(operation="shell.run", agent_id="cloyd"))
    assert unknown.value.status_code == 404

    with pytest.raises(HTTPException) as denied:
        authorize_tool_invocation(ToolInvocationRequest(operation="files.beth.read", agent_id="cloyd"))
    assert denied.value.status_code == 403


def test_authorization_requires_confirmation_for_sensitive_operations() -> None:
    with pytest.raises(HTTPException) as pending:
        authorize_tool_invocation(ToolInvocationRequest(operation="calendar.create", agent_id="freyja"))
    assert pending.value.status_code == 409

    policy = authorize_tool_invocation(
        ToolInvocationRequest(operation="calendar.create", agent_id="freyja", confirmed=True)
    )
    assert policy.operation == "calendar.create"


def test_authorization_enforces_child_and_benedict_boundaries() -> None:
    with pytest.raises(HTTPException) as child_admin:
        authorize_tool_invocation(ToolInvocationRequest(operation="infrastructure.health", agent_id="jenna"))
    assert child_admin.value.status_code == 403

    with pytest.raises(HTTPException) as benedict_household:
        authorize_tool_invocation(ToolInvocationRequest(operation="files.household.read", agent_id="benedict"))
    assert benedict_household.value.status_code == 403

    policy = authorize_tool_invocation(ToolInvocationRequest(operation="files.beth.read", agent_id="benedict"))
    assert policy.operation == "files.beth.read"


def test_open_webui_tool_router_redacts_arguments_and_does_not_execute_live_side_effects() -> None:
    client = TestClient(app)

    catalog = client.get("/open-webui-tools")
    assert catalog.status_code == 200
    assert catalog.json()["secrets_included"] is False

    response = client.post(
        "/open-webui-tools/invoke",
        json={
            "operation": "weather.read",
            "agent_id": "jenna",
            "actor": "person:jenna",
            "arguments": {"location": "home", "api_token": "do-not-log"},
            "request_id": "test-weather",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "stubbed"
    assert body["result"]["execution"] == "not_configured"
    assert body["audit"]["secrets_included"] is False
    assert "do-not-log" not in str(body)
    assert body["audit"]["argument_summary"]["keys"] == ["api_token", "location"]
