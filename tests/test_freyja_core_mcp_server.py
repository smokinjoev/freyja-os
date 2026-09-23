from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER = REPO_ROOT / "scripts" / "freyja-core-mcp-server.py"


def _load_server_module():
    spec = importlib.util.spec_from_file_location("freyja_core_mcp_server", SERVER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_freyja_core_mcp_server_exposes_core_tools_with_canonical_names() -> None:
    module = _load_server_module()

    tool_names = {tool.name for tool in await module.mcp.list_tools()}
    gateway_tool_names = {tool.name for tool in await module.gateway_mcp.list_tools()}

    assert set(module.CORE_TOOL_NAMES) <= tool_names
    assert gateway_tool_names == {"tools.search", "tools.profile", "tools.call"}


async def test_freyja_core_mcp_wrapper_delegates_to_core_call_tool(monkeypatch) -> None:
    module = _load_server_module()
    calls = []

    async def fake_call_tool(tool: str, arguments: dict | None = None) -> dict:
        calls.append((tool, arguments or {}))
        return {"ok": True, "tool": tool, "arguments": arguments or {}}

    monkeypatch.setattr(module, "call_tool", fake_call_tool)

    context = module.set_current_agent("freyja-test")
    try:
        status = json.loads(await module.status_check())
        resolved = json.loads(await module.calendar_resolve_date("this weekend"))
        listed = json.loads(await module.calendar_list_events("2026-09-19T00:00:00+00:00", "2026-09-20T00:00:00+00:00"))
        opencode = json.loads(await module.opencode_status("freyja-test"))
        ha = json.loads(await module.home_assistant_list_states("sensor"))
        memory = json.loads(await module.memory_write("id-1", "hello", "project_state"))
    finally:
        module.reset_current_agent(context)

    assert status["tool"] == "status.check"
    assert resolved["arguments"] == {"phrase": "this weekend"}
    assert listed["arguments"]["start"] == "2026-09-19T00:00:00+00:00"
    assert opencode["arguments"] == {"alias": "freyja-test"}
    assert ha["arguments"] == {"include_all": False, "domain": "sensor"}
    assert memory["arguments"] == {"memory_id": "id-1", "content": "hello", "kind": "project_state"}
    assert calls == [
        ("status.check", {}),
        ("calendar.resolve_date", {"phrase": "this weekend"}),
        (
            "calendar.list_events",
            {
                "start": "2026-09-19T00:00:00+00:00",
                "end": "2026-09-20T00:00:00+00:00",
                "calendar_ids": [],
                "member_ids": [],
                "provider": "apple",
            },
        ),
        ("opencode.status", {"alias": "freyja-test"}),
        ("home_assistant.list_states", {"include_all": False, "domain": "sensor"}),
        ("memory.write", {"memory_id": "id-1", "content": "hello", "kind": "project_state"}),
    ]


async def test_freyja_core_mcp_health_reports_core_tool_list() -> None:
    module = _load_server_module()

    app = module.app()
    route = next(route for route in app.routes if getattr(route, "path", None) == "/healthz")
    response = await route.endpoint(None)
    body = json.loads(response.body)

    assert body["ok"] is True
    assert body["service"] == "freyja-core-mcp"
    assert body["path"] == "/mcp"
    assert body["core_tools"] == list(module.CORE_TOOL_NAMES)
    assert "calendar.list_events" in body["core_tools"]
    assert "home_assistant.list_states" in body["core_tools"]
    assert body["gateway"] == "freyja-mcp-gateway"
    assert "freyja-test" in body["agent_id_supported"]
    assert body["discovery_tools"] == ["tools.search", "tools.profile", "tools.call"]
