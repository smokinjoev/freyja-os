from __future__ import annotations

import pytest

from freyja.macagent import MacAgentHealth, MacAgentOperationResult
from freyja.tools.builtin import register_builtin_tools
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.registry import ToolRegistry


@pytest.fixture
def registry() -> ToolRegistry:
    tool_registry = ToolRegistry(audit_enabled=False)
    register_builtin_tools(tool_registry)
    return tool_registry


def test_builtin_registry_exposes_macagent_read_tools(registry: ToolRegistry) -> None:
    assert registry.get_tool("macagent_health") is not None
    assert registry.get_tool("apple_contacts_list") is not None
    assert registry.get_tool("apple_messages_recent") is not None


@pytest.mark.asyncio
async def test_macagent_health_tool_uses_client(registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        async def health(self) -> MacAgentHealth:
            return MacAgentHealth(
                enabled=True,
                reachable=True,
                authenticated=True,
                host="iris",
                capabilities=["apple.messages.read", "apple.contacts.read"],
            )

    monkeypatch.setattr("freyja.tools.builtin.MacAgentClient", Client)

    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="macagent_health",
            metadata={"director_authorized": True, "person": {"person_id": "joe"}},
        )
    )

    assert result.success is True
    assert result.output["reachable"] is True
    assert "apple.contacts.read" in result.output["capabilities"]


@pytest.mark.asyncio
async def test_apple_contacts_tool_invokes_macagent_envelope(
    registry: ToolRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    class Client:
        async def invoke(self, request):
            captured["request"] = request
            return MacAgentOperationResult(
                ok=True,
                capability="apple.contacts.read",
                operation="list_contacts",
                output={"contacts": [{"person_id": "joe"}]},
            )

    monkeypatch.setattr("freyja.tools.builtin.MacAgentClient", Client)

    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="apple_contacts_list",
            arguments={"limit": 5},
            metadata={"director_authorized": True, "person": {"person_id": "joe"}},
        )
    )

    assert result.success is True
    assert result.output["contacts"][0]["person_id"] == "joe"
    assert captured["request"].director_authorized is True
    assert captured["request"].capability == "apple.contacts.read"
    assert captured["request"].operation == "list_contacts"
    assert captured["request"].arguments == {"include_identifiers": False, "limit": 5}


@pytest.mark.asyncio
async def test_apple_messages_recent_tool_invokes_macagent_envelope(
    registry: ToolRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    class Client:
        async def invoke(self, request):
            captured["request"] = request
            return MacAgentOperationResult(
                ok=True,
                capability="apple.messages.read",
                operation="recent_messages",
                output={"messages": [{"message_id": "m1"}]},
            )

    monkeypatch.setattr("freyja.tools.builtin.MacAgentClient", Client)

    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="apple_messages_recent",
            arguments={"limit": 3},
            metadata={"director_authorized": True, "person": {"person_id": "joe"}},
        )
    )

    assert result.success is True
    assert result.output["messages"][0]["message_id"] == "m1"
    assert captured["request"].director_authorized is True
    assert captured["request"].capability == "apple.messages.read"
    assert captured["request"].operation == "recent_messages"
    assert captured["request"].arguments == {"limit": 3}
