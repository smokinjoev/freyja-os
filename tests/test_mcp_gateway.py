from __future__ import annotations

from freyja.mcp_gateway import (
    current_agent,
    discover_tools,
    dispatch_tool,
    profile,
    reset_current_agent,
    set_current_agent,
)


async def test_default_gateway_context_is_generic_and_read_limited() -> None:
    calls = []

    async def caller(name, arguments):
        calls.append((name, arguments))
        return {"ok": True}

    assert current_agent() == "generic"
    prof = profile()
    assert prof["agent_id"] == "generic"
    assert prof["tools"] == ["status.check", "memory.search"]

    denied = await dispatch_tool("memory.write", {"record": "x"}, caller)

    assert denied["ok"] is False
    assert denied["agent_id"] == "generic"
    assert calls == []


def test_discovery_filters_catalog_by_authenticated_agent() -> None:
    context = set_current_agent("benedict")
    try:
        result = discover_tools()
        names = {tool["name"] for tool in result["tools"]}
        assert names == {
            "status.check",
            "calendar.resolve_date",
            "memory.search",
            "memory.write",
        }
        assert "opencode.send" not in names
        assert profile()["agent_id"] == "benedict"
    finally:
        reset_current_agent(context)


def test_freyja_test_policy_exposes_phase_one_core_tools_only() -> None:
    context = set_current_agent("freyja-test")
    try:
        names = {tool["name"] for tool in discover_tools()["tools"]}
        assert {
            "status.check",
            "calendar.resolve_date",
            "calendar.list_events",
            "calendar.create_event",
            "home_assistant.read_state",
            "home_assistant.list_states",
            "opencode.start",
            "opencode.send",
            "memory.search",
            "memory.write",
        } <= names
        assert "calendar.delete_event" not in names
    finally:
        reset_current_agent(context)


def test_discovery_supports_small_query_based_results() -> None:
    context = set_current_agent("freyja")
    try:
        result = discover_tools(query="calendar event", limit=2)
        names = [tool["name"] for tool in result["tools"]]
        assert names == ["calendar.list_events", "calendar.create_event"]
        assert result["count"] == 2
    finally:
        reset_current_agent(context)


async def test_dispatch_enforces_agent_policy_before_calling_backend() -> None:
    calls = []

    async def caller(name, arguments):
        calls.append((name, arguments))
        return {"ok": True}

    context = set_current_agent("jennacide")
    try:
        denied = await dispatch_tool("opencode.send", {"prompt": "x"}, caller)
        allowed = await dispatch_tool("memory.search", {"query": "x"}, caller)
    finally:
        reset_current_agent(context)

    assert denied["ok"] is False
    assert calls == [("memory.search", {"query": "x"})]
    assert allowed["gateway"]["agent_id"] == "jennacide"
